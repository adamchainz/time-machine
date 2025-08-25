from __future__ import annotations

import argparse
import ast
import sys
import warnings
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import partial

from tokenize_rt import (
    UNIMPORTANT_WS,
    Offset,
    Token,
    reversed_enumerate,
    src_to_tokens,
    tokens_to_src,
)

CODE = "CODE"
DEDENT = "DEDENT"


@dataclass
class State:
    """State collected during preprocessing to guide transformations."""

    # Import tracking
    freezegun_import_seen: bool = False
    freeze_time_import_seen: bool = False

    # Nodes that need transformation
    import_nodes: list[ast.Import] = field(default_factory=list)
    import_from_nodes: list[ast.ImportFrom] = field(default_factory=list)
    freezer_args: list[ast.arg] = field(default_factory=list)
    functions_needing_import: list[ast.FunctionDef] = field(default_factory=list)
    functions_with_tick_decorators: set[ast.FunctionDef] = field(default_factory=set)
    function_tick_values: dict[ast.FunctionDef, bool] = field(
        default_factory=dict
    )  # maps function to its tick value
    freezer_method_calls: list[ast.Call] = field(default_factory=list)
    freezer_method_calls_with_tick: list[ast.Call] = field(default_factory=list)
    freezer_method_calls_with_tick_value: list[tuple[ast.Call, bool]] = field(
        default_factory=list
    )  # (call, tick_value)
    context_var_method_calls_with_tick_value: list[tuple[ast.Call, bool]] = field(
        default_factory=list
    )  # (call, tick_value) for context vars
    freezer_tick_calls: list[ast.Call] = field(default_factory=list)
    freezer_tick_calls_with_tick: list[ast.Call] = field(default_factory=list)
    context_var_method_calls: dict[str, list[ast.Call]] = field(default_factory=dict)
    context_var_tick_calls: dict[str, list[ast.Call]] = field(default_factory=dict)
    freeze_time_decorators: list[ast.Call] = field(default_factory=list)
    freeze_time_with_statements: list[ast.Call] = field(default_factory=list)
    pytest_mark_decorators: list[ast.Call] = field(default_factory=list)


def main(argv: Sequence[str] | None = None) -> int:
    """Main entry point for the migration tool."""
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(
        dest="command", help="Available commands", required=True
    )

    migrate_parser = subparsers.add_parser(
        "migrate",
        help="Migrate Python files from freezegun to time-machine",
    )
    migrate_parser.add_argument("file", nargs="+")

    args = parser.parse_args(argv)

    if args.command == "migrate":
        return migrate_files(files=args.file)
    else:  # pragma: no cover
        # Unreachable
        raise NotImplementedError(f"Command {args.command} does not exist.")


def migrate_files(files: list[str]) -> int:
    returncode = 0
    for filename in files:
        returncode |= migrate_file(filename)
    return returncode


def migrate_file(filename: str) -> int:
    if filename == "-":
        contents_bytes = sys.stdin.buffer.read()
    else:
        with open(filename, "rb") as fb:
            contents_bytes = fb.read()

    try:
        contents_text_orig = contents_text = contents_bytes.decode()
    except UnicodeDecodeError:
        print(f"{filename} is non-utf-8 (not supported)")
        return 1

    contents_text = migrate_contents(contents_text)

    if filename == "-":
        print(contents_text, end="")
    elif contents_text != contents_text_orig:
        print(f"Rewriting {filename}", file=sys.stderr)
        with open(filename, "w", encoding="UTF-8", newline="") as f:
            f.write(contents_text)

    return contents_text != contents_text_orig


def migrate_contents(contents_text: str) -> str:
    """Migrate a single text from freezegun to time-machine."""
    try:
        ast_obj = ast_parse(contents_text)
    except SyntaxError:
        return contents_text

    # Phase 1: Collect all information
    state = collect_migration_state(ast_obj)

    # Phase 2: Generate callbacks based on collected state
    callbacks = generate_callbacks(state)

    if not callbacks:
        return contents_text

    tokens = src_to_tokens(contents_text)

    fixup_dedent_tokens(tokens)

    for i, token in reversed_enumerate(tokens):
        if not token.src:
            continue
        # though this is a defaultdict, by using `.get()` this function's
        # self time is almost 50% faster
        for callback in callbacks.get(token.offset, ()):
            callback(tokens, i)

    # no types for tokenize-rt
    return tokens_to_src(tokens)  # type: ignore [no-any-return]


def collect_migration_state(tree: ast.Module) -> State:
    """Phase 1: Collect all information about what needs to be migrated."""
    state = State()

    # First pass: collect all nodes
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if (
                len(node.names) == 1
                and (alias := node.names[0]).name == "freezegun"
                and alias.asname is None
            ):
                state.freezegun_import_seen = True
                state.import_nodes.append(node)

        elif isinstance(node, ast.ImportFrom):
            if (
                node.module == "freezegun"
                and len(node.names) == 1
                and (alias := node.names[0]).name == "freeze_time"
                and alias.asname is None
            ):
                state.freeze_time_import_seen = True
                state.import_from_nodes.append(node)

        elif isinstance(node, ast.FunctionDef):
            # Check for freezer args
            has_freezer_arg = False
            for arg in node.args.args:
                if arg.arg == "freezer":
                    state.freezer_args.append(arg)
                    has_freezer_arg = True

            # Check for pytest.mark decorators and track if decorators have tick arguments
            has_pytest_mark = False
            has_decorator_with_tick = False
            decorator_tick_value = None
            for decorator in node.decorator_list:
                if is_migratable_freeze_time_call(decorator, state):
                    state.freeze_time_decorators.append(decorator)
                    # Check if this decorator has tick argument
                    for keyword in decorator.keywords:
                        if keyword.arg == "tick":
                            has_decorator_with_tick = True
                            decorator_tick_value = (
                                keyword.value.value
                                if hasattr(keyword.value, "value")
                                else False
                            )
                elif is_pytest_mark_freeze_time(decorator):
                    state.pytest_mark_decorators.append(decorator)
                    has_pytest_mark = True
                    # Check if this decorator has tick argument
                    for keyword in decorator.keywords:
                        if keyword.arg == "tick":
                            has_decorator_with_tick = True
                            decorator_tick_value = (
                                keyword.value.value
                                if hasattr(keyword.value, "value")
                                else False
                            )

            # Track functions that have decorators with tick arguments
            if has_decorator_with_tick:
                state.functions_with_tick_decorators.add(node)
                state.function_tick_values[node] = decorator_tick_value

            # Check for context managers within the function
            has_context_manager = False
            context_vars = set()
            context_var_tick_values = {}  # maps context var name to tick value
            for subnode in ast.walk(node):
                if (
                    isinstance(subnode, ast.With)
                    and len(subnode.items) > 0
                    and subnode.items[0].optional_vars is not None
                ):
                    item = subnode.items[0]
                    context_expr = item.context_expr
                    if (
                        isinstance(context_expr, ast.Call)
                        and migratable_call(context_expr)
                        and is_migratable_freeze_time_call(context_expr, state)
                        and isinstance(item.optional_vars, ast.Name)
                    ):
                        has_context_manager = True
                        context_var_name = item.optional_vars.id
                        context_vars.add(context_var_name)
                        # Collect the with statement for transformation
                        state.freeze_time_with_statements.append(context_expr)

                        # Extract tick value from context manager
                        context_tick_value = None
                        for keyword in context_expr.keywords:
                            if keyword.arg == "tick":
                                context_tick_value = (
                                    keyword.value.value
                                    if hasattr(keyword.value, "value")
                                    else False
                                )
                                break

                        if context_tick_value is not None:
                            context_var_tick_values[context_var_name] = (
                                context_tick_value
                            )

            # If function has context managers but no freezer arg, it needs an import
            if has_context_manager and not has_freezer_arg:
                state.functions_needing_import.append(node)

            # Check for freezer method calls and context variable calls within the function
            for subnode in ast.walk(node):
                if (
                    isinstance(subnode, ast.Call)
                    and isinstance(subnode.func, ast.Attribute)
                    and isinstance(subnode.func.value, ast.Name)
                ):
                    var_name = subnode.func.value.id
                    if var_name == "freezer":
                        if (
                            subnode.func.attr == "move_to"
                            and len(subnode.args) >= 1
                            and len(subnode.keywords) == 0
                        ):
                            if has_decorator_with_tick:
                                # Function has decorator with tick, use the decorator's tick value
                                state.freezer_method_calls_with_tick_value.append(
                                    (subnode, decorator_tick_value)
                                )
                            elif has_pytest_mark:
                                state.freezer_method_calls_with_tick.append(subnode)
                            else:
                                state.freezer_method_calls.append(subnode)
                        elif subnode.func.attr == "tick":
                            if has_pytest_mark:
                                state.freezer_tick_calls_with_tick.append(subnode)
                            else:
                                state.freezer_tick_calls.append(subnode)
                    elif var_name in context_vars:
                        # Handle context variable method calls
                        if (
                            subnode.func.attr == "move_to"
                            and len(subnode.args) >= 1
                            and len(subnode.keywords) == 0
                        ):
                            if var_name in context_var_tick_values:
                                # Context manager has tick value, add it to method call
                                state.context_var_method_calls_with_tick_value.append(
                                    (subnode, context_var_tick_values[var_name])
                                )
                            else:
                                # Store in original context var method calls for normal processing
                                if var_name not in state.context_var_method_calls:
                                    state.context_var_method_calls[var_name] = []
                                state.context_var_method_calls[var_name].append(subnode)
                        elif subnode.func.attr == "tick":
                            if var_name not in state.context_var_tick_calls:
                                state.context_var_tick_calls[var_name] = []
                            state.context_var_tick_calls[var_name].append(subnode)

        elif isinstance(node, ast.ClassDef):
            if node.decorator_list and looks_like_unittest_class(node):
                for decorator in node.decorator_list:
                    if is_migratable_freeze_time_call(decorator, state):
                        state.freeze_time_decorators.append(decorator)

        elif isinstance(node, ast.With):
            for item in node.items:
                context_expr = item.context_expr
                if (
                    isinstance(context_expr, ast.Call)
                    and migratable_call(context_expr)
                    and item.optional_vars is None
                    and is_migratable_freeze_time_call(context_expr, state)
                ):
                    state.freeze_time_with_statements.append(context_expr)

    return state


def generate_callbacks(state: State) -> Mapping[Offset, list[TokenFunc]]:
    """Phase 2: Generate callbacks based on collected state."""
    ret = defaultdict(list)

    # Determine if we should convert freeze_time decorators to pytest.mark
    has_freezer_fixtures = len(state.freezer_args) > 0

    # Handle imports
    for node in state.import_nodes:
        if has_freezer_fixtures:
            # Remove import entirely when converting to pytest.mark
            ret[ast_start_offset(node)].append(remove_import)
        else:
            # Convert to time_machine import when no freezer fixtures
            ret[ast_start_offset(node)].append(replace_import)

    for node in state.import_from_nodes:
        ret[ast_start_offset(node)].append(partial(replace_import_from, node=node))

    # Handle freezer arguments
    for arg in state.freezer_args:
        ret[ast_start_offset(arg)].append(partial(replace_function_arg, node=arg))

    # Handle functions needing import inside function body
    for func in state.functions_needing_import:
        ret[ast_start_offset(func)].append(
            partial(add_import_inside_function, node=func)
        )

    # Handle freezer method calls (always add tick=False)
    for call in state.freezer_method_calls:
        ret[ast_start_offset(call.func.value)].append(
            partial(replace_freezer_name, node=call.func.value)
        )
        ret[ast_start_offset(call)].append(partial(add_tick_false, node=call))

    # Handle freezer method calls (with tick=False)
    for call in state.freezer_method_calls_with_tick:
        ret[ast_start_offset(call.func.value)].append(
            partial(replace_freezer_name, node=call.func.value)
        )
        ret[ast_start_offset(call)].append(partial(add_tick_false, node=call))

    # Handle freezer method calls with specific tick values from decorators
    for call, tick_value in state.freezer_method_calls_with_tick_value:
        ret[ast_start_offset(call.func.value)].append(
            partial(replace_freezer_name, node=call.func.value)
        )
        ret[ast_start_offset(call)].append(
            partial(add_tick_value, node=call, tick_value=tick_value)
        )

    # Handle freezer tick calls (without tick=False)
    for call in state.freezer_tick_calls:
        ret[ast_start_offset(call.func.value)].append(
            partial(replace_freezer_name, node=call.func.value)
        )
        ret[ast_start_offset(call.func)].append(
            partial(replace_tick_with_shift, node=call)
        )

    # Handle freezer tick calls (with tick=False)
    for call in state.freezer_tick_calls_with_tick:
        ret[ast_start_offset(call.func.value)].append(
            partial(replace_freezer_name, node=call.func.value)
        )
        ret[ast_start_offset(call.func)].append(
            partial(replace_tick_with_shift, node=call)
        )

    # Handle context variable method calls with tick values
    for call, tick_value in state.context_var_method_calls_with_tick_value:
        ret[ast_start_offset(call)].append(
            partial(add_tick_value, node=call, tick_value=tick_value)
        )

    # Handle context variable tick calls
    for calls in state.context_var_tick_calls.values():
        for call in calls:
            ret[ast_start_offset(call.func)].append(
                partial(replace_tick_with_shift, node=call)
            )

    # Handle freeze_time decorators - convert based on presence of freezer fixtures
    for decorator in state.freeze_time_decorators:
        if has_freezer_fixtures:
            # Convert to pytest.mark.time_machine when freezer fixtures present
            ret[ast_start_offset(decorator.func)].append(
                partial(replace_freezegun_to_pytest_mark, node=decorator.func)
            )
        else:
            # Convert to time_machine.travel when no freezer fixtures
            ret[ast_start_offset(decorator.func)].append(
                partial(switch_to_travel, node=decorator.func)
            )
        ret[ast_start_offset(decorator)].append(partial(add_tick_false, node=decorator))

    # Handle pytest.mark.freeze_time decorators
    for decorator in state.pytest_mark_decorators:
        ret[ast_start_offset(decorator.func)].append(
            partial(replace_pytest_mark, node=decorator.func)
        )
        ret[ast_start_offset(decorator)].append(partial(add_tick_false, node=decorator))

    # Handle with statements
    for context_expr in state.freeze_time_with_statements:
        ret[ast_start_offset(context_expr.func)].append(
            partial(switch_to_traveller, node=context_expr.func)
        )
        ret[ast_start_offset(context_expr)].append(
            partial(add_tick_false, node=context_expr)
        )

    return ret


def is_migratable_freeze_time_call(node: ast.expr, state: State) -> bool:
    """Check if a node is a migratable freeze_time call."""
    return (
        isinstance(node, ast.Call)
        and migratable_call(node)
        and (
            (
                state.freezegun_import_seen
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "freeze_time"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "freezegun"
            )
            or (
                state.freeze_time_import_seen
                and isinstance(node.func, ast.Name)
                and node.func.id == "freeze_time"
            )
        )
    )


def is_pytest_mark_freeze_time(node: ast.expr) -> bool:
    """Check if a node is a pytest.mark.freeze_time decorator."""
    return (
        isinstance(node, ast.Call)
        and migratable_call(node)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "freeze_time"
        and isinstance(node.func.value, ast.Attribute)
        and node.func.value.attr == "mark"
        and isinstance(node.func.value.value, ast.Name)
        and node.func.value.value.id == "pytest"
    )


def ast_parse(contents_text: str) -> ast.Module:
    # intentionally ignore warnings, we can't do anything about them
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return ast.parse(contents_text.encode())


def fixup_dedent_tokens(tokens: list[Token]) -> None:  # pragma: no cover
    """For whatever reason the DEDENT / UNIMPORTANT_WS tokens are misordered

    | if True:
    |     if True:
    |         pass
    |     else:
    |^    ^- DEDENT
    |+----UNIMPORTANT_WS
    """
    for i, token in enumerate(tokens):
        if token.name == UNIMPORTANT_WS and tokens[i + 1].name == DEDENT:
            tokens[i], tokens[i + 1] = tokens[i + 1], tokens[i]


TokenFunc = Callable[[list[Token], int], None]


def migratable_call(node: ast.Call) -> bool:
    return (
        len(node.args) == 1
        # Allow tick keyword argument, we handle it properly in add_tick_false
        and (
            len(node.keywords) == 0
            or (len(node.keywords) == 1 and node.keywords[0].arg == "tick")
        )
    )


def looks_like_unittest_class(node: ast.ClassDef) -> bool:
    """
    Heuristically determine if a class is a unittest.TestCase subclass.
    """
    for base in node.bases:
        if (
            isinstance(base, ast.Name)
            and base.id.endswith("TestCase")
            or (
                isinstance(base, ast.Attribute)
                and isinstance(base.value, ast.Name)
                and base.value.id == "unittest"
                and base.attr.endswith("TestCase")
            )
        ):
            return True

    subnode: ast.AST
    for subnode in node.body:
        if isinstance(subnode, ast.FunctionDef) and subnode.name in (
            "setUp",
            "setUpClass",
            "tearDown",
            "tearDownClass",
            "setUpTestData",
        ):
            return True
        if isinstance(subnode, ast.AsyncFunctionDef) and subnode.name in (
            "asyncSetUp",
            "asyncTearDown",
        ):
            return True

    for subnode in ast.walk(node):
        if (
            isinstance(subnode, ast.Attribute)
            and isinstance(subnode.value, ast.Name)
            and subnode.value.id == "self"
            and subnode.attr in UNITTEST_ASSERT_NAMES
        ):
            return True

    return False


UNITTEST_ASSERT_NAMES = frozenset(
    [
        "assertAlmostEqual",
        "assertCountEqual",
        "assertDictEqual",
        "assertEqual",
        "assertFalse",
        "assertGreater",
        "assertGreaterEqual",
        "assertIn",
        "assertIs",
        "assertIsInstance",
        "assertIsNone",
        "assertIsNot",
        "assertIsNotNone",
        "assertLess",
        "assertLessEqual",
        "assertListEqual",
        "assertLogs",
        "assertMultiLineEqual",
        "assertNoLogs",
        "assertNotAlmostEqual",
        "assertNotEqual",
        "assertNotIn",
        "assertNotIsInstance",
        "assertNotRegex",
        "assertRaises",
        "assertRaisesRegex",
        "assertRegex",
        "assertSequenceEqual",
        "assertSetEqual",
        "assertTrue",
        "assertTupleEqual",
        "assertWarns",
        "assertWarnsRegex",
    ]
)


def ast_start_offset(node: ast.alias | ast.expr | ast.keyword | ast.stmt) -> Offset:
    return Offset(node.lineno, node.col_offset)


def replace_import(tokens: list[Token], i: int) -> None:
    while True:
        if tokens[i].name == "NAME" and tokens[i].src == "freezegun":
            break
        i += 1
    tokens[i] = Token(name="NAME", src="time_machine")


def remove_import(tokens: list[Token], i: int) -> None:
    """Remove the import statement completely."""
    # Find the start of the import statement
    while i > 0 and not (tokens[i].name == "NAME" and tokens[i].src == "import"):
        i -= 1
    start = i

    # Find the end of the import statement (look for newline)
    while i < len(tokens) and tokens[i].name != "NEWLINE":
        i += 1
    if i < len(tokens):
        i += 1  # Include the newline after import

    # Remove the import statement completely (the blank line after will remain)
    del tokens[start:i]


def replace_import_from(tokens: list[Token], i: int, node: ast.ImportFrom) -> None:
    j = find_last_token(tokens, i, node=node)
    tokens[i : j + 1] = [Token(name=CODE, src="import time_machine")]


def replace_function_arg(tokens: list[Token], i: int, node: ast.Attr) -> None:
    j = find_last_token(tokens, i, node=node)
    tokens[i : j + 1] = [Token(name=CODE, src="time_machine")]


def add_time_machine_param(tokens: list[Token], i: int, node: ast.FunctionDef) -> None:
    """Add time_machine parameter to function that uses context managers."""
    # Find the opening parenthesis of the function
    while i < len(tokens) and tokens[i].src != "(":
        i += 1
    i += 1  # Move past the opening parenthesis

    # Insert the time_machine parameter
    tokens.insert(i, Token(name="NAME", src="time_machine"))


def add_import_inside_function(
    tokens: list[Token], i: int, node: ast.FunctionDef
) -> None:
    """Add import time_machine statement inside function body."""
    # Find the colon that ends the function definition
    while i < len(tokens) and tokens[i].src != ":":
        i += 1
    i += 1  # Move past the colon

    # Skip any whitespace/newlines
    while i < len(tokens) and tokens[i].name in (
        "NEWLINE",
        "NL",
        "INDENT",
        "UNIMPORTANT_WS",
    ):
        i += 1

    # Insert the import statement
    tokens.insert(i, Token(name="NAME", src="import"))
    tokens.insert(i + 1, Token(name="UNIMPORTANT_WS", src=" "))
    tokens.insert(i + 2, Token(name="NAME", src="time_machine"))
    tokens.insert(i + 3, Token(name="NEWLINE", src="\n"))
    tokens.insert(i + 4, Token(name="UNIMPORTANT_WS", src="    "))


def replace_freezer_name(tokens: list[Token], i: int, node: ast.Name) -> None:
    """Replace 'freezer' name with 'time_machine'."""
    j = find_last_token(tokens, i, node=node)
    tokens[i : j + 1] = [Token(name=CODE, src="time_machine")]


def switch_to_travel(
    tokens: list[Token], i: int, node: ast.Attribute | ast.Name
) -> None:
    """Replace freezegun.freeze_time with time_machine.travel for decorators."""
    j = find_last_token(tokens, i, node=node)
    tokens[i : j + 1] = [Token(name=CODE, src="time_machine.travel")]


def replace_pytest_mark(tokens: list[Token], i: int, node: ast.Attribute) -> None:
    """Replace pytest.mark.freeze_time with pytest.mark.time_machine."""
    j = find_last_token(tokens, i, node=node)
    tokens[i : j + 1] = [Token(name=CODE, src="pytest.mark.time_machine")]


def replace_freezegun_to_pytest_mark(
    tokens: list[Token], i: int, node: ast.Attribute | ast.Name
) -> None:
    """Replace freezegun.freeze_time with pytest.mark.time_machine."""
    j = find_last_token(tokens, i, node=node)
    tokens[i : j + 1] = [Token(name=CODE, src="pytest.mark.time_machine")]


def switch_to_traveller(
    tokens: list[Token], i: int, node: ast.Attribute | ast.Name
) -> None:
    """Replace freezegun.freeze_time with time_machine.travel for context managers."""
    j = find_last_token(tokens, i, node=node)
    tokens[i : j + 1] = [Token(name=CODE, src="time_machine.travel")]


def replace_tick_with_shift(tokens: list[Token], i: int, node: ast.Call) -> None:
    """Replace tick method call with shift, adding default argument of 1 if no args."""
    # Find the position of the "tick" method name
    while i < len(tokens) and not (
        tokens[i].name == "NAME" and tokens[i].src == "tick"
    ):
        i += 1

    # Replace "tick" with "shift"
    tokens[i] = Token(name="NAME", src="shift")

    # If no arguments, add default argument of 1
    if len(node.args) == 0 and len(node.keywords) == 0:
        # Find the opening parenthesis
        j = i + 1
        while j < len(tokens) and tokens[j].src != "(":
            j += 1
        j += 1  # Move past the opening parenthesis

        # Insert "1" as the default argument
        tokens.insert(j, Token(name="NUMBER", src="1"))


def add_tick_false(tokens: list[Token], i: int, node: ast.Call) -> None:
    """
    Add `tick=False` to the function call if it doesn't already have a tick argument.
    """
    # Check if the node already has a tick keyword argument
    has_tick_arg = any(keyword.arg == "tick" for keyword in node.keywords)

    if not has_tick_arg:
        j = find_last_token(tokens, i, node=node)
        tokens.insert(j, Token(name=CODE, src=", tick=False"))


def add_tick_value(
    tokens: list[Token], i: int, node: ast.Call, tick_value: bool
) -> None:
    """
    Add `tick=True` or `tick=False` to the function call based on the tick_value.
    """
    # Check if the node already has a tick keyword argument
    has_tick_arg = any(keyword.arg == "tick" for keyword in node.keywords)

    if not has_tick_arg:
        j = find_last_token(tokens, i, node=node)
        tick_str = "True" if tick_value else "False"
        tokens.insert(j, Token(name=CODE, src=f", tick={tick_str}"))


# Token functions


def find_last_token(
    tokens: list[Token], i: int, *, node: ast.expr | ast.keyword | ast.stmt
) -> int:
    """
    Find the last token corresponding to the given ast node.
    """
    while (
        tokens[i].line is None or tokens[i].line < node.end_lineno
    ):  # pragma: no cover
        i += 1
    while (
        tokens[i].utf8_byte_offset is None
        or tokens[i].utf8_byte_offset < node.end_col_offset
    ):
        i += 1
    return i - 1
