from __future__ import annotations

import argparse
import ast
import sys
import warnings
from collections import defaultdict
from collections.abc import Callable, Mapping, MutableMapping, Sequence
from functools import partial

from tokenize_rt import (
    NON_CODING_TOKENS,
    UNIMPORTANT_WS,
    Offset,
    Token,
    reversed_enumerate,
    src_to_tokens,
    tokens_to_src,
)

CODE = "CODE"
DEDENT = "DEDENT"
INDENT = "INDENT"


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

    callbacks = visit(ast_obj)

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


class FreezerFunction:
    """
    Details of a function taking pytest-freezegun / pytest-freezer’s
    ``freezer`` fixture as an argument.
    """

    __slots__ = ("lineno", "end_lineno", "marker_seen")

    def __init__(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef, *, marker_seen: bool
    ) -> None:
        assert node.end_lineno is not None
        self.lineno = node.lineno
        self.end_lineno = node.end_lineno
        self.marker_seen = marker_seen


class TravellerVar:
    """
    Details of a variable bound with ``as`` to a migrated freeze_time()
    context manager.
    """

    __slots__ = ("name", "lineno", "end_lineno")

    def __init__(self, name: str, node: ast.With) -> None:
        assert node.end_lineno is not None
        self.name = name
        self.lineno = node.lineno
        self.end_lineno = node.end_lineno


def visit(tree: ast.Module) -> Mapping[Offset, list[TokenFunc]]:
    """
    Visit the AST and return a list of callbacks to apply to the tokens.
    """
    ret: defaultdict[Offset, list[TokenFunc]] = defaultdict(list)
    freezegun_import_seen = False
    freeze_time_import_seen = False
    freezer_functions: list[FreezerFunction] = []
    marker_class_methods: set[ast.FunctionDef | ast.AsyncFunctionDef] = set()
    traveller_vars: list[TravellerVar] = []
    for node in ast.walk(tree):
        match node:
            case ast.Import() if (
                len(node.names) == 1
                and (alias := node.names[0]).name == "freezegun"
                and alias.asname is None
            ):
                freezegun_import_seen = True
                ret[ast_start_offset(node)].append(replace_import)
            case ast.ImportFrom() if (
                node.level == 0
                and node.module == "freezegun"
                and any(
                    alias.name == "freeze_time" and alias.asname is None
                    for alias in node.names
                )
            ):
                freeze_time_import_seen = True
                ret[ast_start_offset(node)].append(
                    partial(
                        replace_import_from,
                        node=node,
                        keep=[
                            unparse_alias(alias)
                            for alias in node.names
                            if alias.name != "freeze_time" or alias.asname is not None
                        ],
                    )
                )
            case ast.FunctionDef() | ast.AsyncFunctionDef():
                marker_seen = node in marker_class_methods
                for decorator in node.decorator_list:
                    if maybe_migrate_marker(ret, decorator):
                        marker_seen = True
                    else:
                        maybe_migrate_call(
                            ret,
                            decorator,
                            freezegun_import_seen=freezegun_import_seen,
                            freeze_time_import_seen=freeze_time_import_seen,
                        )

                freezer_args = [
                    arg
                    for arg in (*node.args.args, *node.args.kwonlyargs)
                    if arg.arg == "freezer"
                ]
                if freezer_args:
                    for arg in freezer_args:
                        ret[ast_start_offset(arg)].append(replace_freezer)
                    freezer_functions.append(
                        FreezerFunction(node, marker_seen=marker_seen)
                    )

            case ast.ClassDef() if node.decorator_list:
                unittest_class = looks_like_unittest_class(node)
                for decorator in node.decorator_list:
                    if maybe_migrate_marker(ret, decorator):
                        marker_class_methods.update(
                            stmt
                            for stmt in node.body
                            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef))
                        )
                    elif unittest_class:
                        maybe_migrate_call(
                            ret,
                            decorator,
                            freezegun_import_seen=freezegun_import_seen,
                            freeze_time_import_seen=freeze_time_import_seen,
                        )

            case ast.With():
                for item in node.items:
                    match item.optional_vars:
                        case None:
                            maybe_migrate_call(
                                ret,
                                item.context_expr,
                                freezegun_import_seen=freezegun_import_seen,
                                freeze_time_import_seen=freeze_time_import_seen,
                            )
                        case ast.Name(id=name):
                            if maybe_migrate_call(
                                ret,
                                item.context_expr,
                                freezegun_import_seen=freezegun_import_seen,
                                freeze_time_import_seen=freeze_time_import_seen,
                            ):
                                traveller_vars.append(TravellerVar(name, node))

            case ast.Call(
                func=ast.Attribute(
                    value=ast.Name(id=receiver) as receiver_node,
                    attr=("move_to" | "tick") as attr,
                )
            ):
                if receiver == "freezer" and (
                    freezer_function := find_freezer_function(freezer_functions, node)
                ):
                    if attr == "move_to" and len(node.args) == 1 and not node.keywords:
                        ret[ast_start_offset(receiver_node)].append(replace_freezer)
                        if not freezer_function.marker_seen:
                            ret[ast_start_offset(node)].append(
                                partial(add_tick_false, node=node)
                            )
                    elif attr == "tick" and migratable_tick_call(node):
                        ret[ast_start_offset(receiver_node)].append(replace_freezer)
                        ret[ast_start_offset(receiver_node)].append(
                            partial(replace_tick_with_shift, node=node)
                        )
                elif (
                    attr == "tick"
                    and migratable_tick_call(node)
                    and any(
                        traveller_var.name == receiver
                        and (
                            traveller_var.lineno
                            <= node.lineno
                            <= traveller_var.end_lineno
                        )
                        for traveller_var in traveller_vars
                    )
                ):
                    ret[ast_start_offset(receiver_node)].append(
                        partial(replace_tick_with_shift, node=node)
                    )

    return ret


def find_freezer_function(
    freezer_functions: list[FreezerFunction], node: ast.expr
) -> FreezerFunction | None:
    """
    Find the innermost function with a freezer fixture argument containing the
    given node, if any.
    """
    for function in reversed(freezer_functions):
        if function.lineno <= node.lineno <= function.end_lineno:
            return function
    return None


def maybe_migrate_call(
    ret: MutableMapping[Offset, list[TokenFunc]],
    node: ast.expr,
    *,
    freezegun_import_seen: bool,
    freeze_time_import_seen: bool,
) -> bool:
    """
    Add the callbacks to rewrite the given expression, if it is a migratable
    call to freezegun’s freeze_time(), returning whether that was the case.
    """
    if not isinstance(node, ast.Call) or not migratable_call(node):
        return False

    func = node.func
    if not (
        (
            freezegun_import_seen
            and isinstance(func, ast.Attribute)
            and func.attr == "freeze_time"
            and isinstance(func.value, ast.Name)
            and func.value.id == "freezegun"
        )
        or (
            freeze_time_import_seen
            and isinstance(func, ast.Name)
            and func.id == "freeze_time"
        )
    ):
        return False

    ret[ast_start_offset(func)].append(partial(switch_to_travel, node=func))
    if not any(kw.arg == "tick" for kw in node.keywords):
        ret[ast_start_offset(node)].append(partial(add_tick_false, node=node))
    return True


def maybe_migrate_marker(
    ret: MutableMapping[Offset, list[TokenFunc]],
    node: ast.expr,
) -> bool:
    """
    Add the callbacks to rewrite the given decorator, if it is a migratable
    use of pytest-freezegun / pytest-freezer’s pytest.mark.freeze_time()
    marker, returning whether that was the case.
    """
    if not (
        isinstance(node, ast.Call)
        and migratable_call(node)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "freeze_time"
        and isinstance(node.func.value, ast.Attribute)
        and node.func.value.attr == "mark"
        and isinstance(node.func.value.value, ast.Name)
        and node.func.value.value.id == "pytest"
    ):
        return False

    ret[ast_start_offset(node.func)].append(partial(switch_to_marker, node=node.func))
    if not any(kw.arg == "tick" for kw in node.keywords):
        ret[ast_start_offset(node)].append(partial(add_tick_false, node=node))
    return True


def migratable_call(node: ast.Call) -> bool:
    return len(node.args) == 1 and (
        len(node.keywords) == 0
        or (len(node.keywords) == 1 and node.keywords[0].arg == "tick")
    )


def migratable_tick_call(node: ast.Call) -> bool:
    """
    freezegun’s tick() takes a single optional argument, delta.
    """
    if node.args:
        return len(node.args) == 1 and not node.keywords
    return not node.keywords or (
        len(node.keywords) == 1 and node.keywords[0].arg == "delta"
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


def ast_start_offset(
    node: ast.alias | ast.arg | ast.expr | ast.keyword | ast.stmt,
) -> Offset:
    return Offset(node.lineno, node.col_offset)


def replace_import(tokens: list[Token], i: int) -> None:
    while True:
        if tokens[i].name == "NAME" and tokens[i].src == "freezegun":
            break
        i += 1
    tokens[i] = Token(name="NAME", src="time_machine")


def unparse_alias(alias: ast.alias) -> str:
    if alias.asname is not None:
        return f"{alias.name} as {alias.asname}"
    return alias.name


def replace_import_from(
    tokens: list[Token], i: int, node: ast.ImportFrom, keep: list[str]
) -> None:
    """
    Replace a from-import of freeze_time with `import time_machine`, re-adding
    a from-import of any other names that were imported alongside it.
    """
    j = find_last_token(tokens, i, node=node)
    src = "import time_machine"
    if keep:
        src += f"\n{line_indent(tokens, i)}from {node.module} import {', '.join(keep)}"
    tokens[i : j + 1] = [Token(name=CODE, src=src)]


def line_indent(tokens: list[Token], i: int) -> str:
    """
    Return the whitespace indenting the line that the given token starts.
    """
    if i > 0 and tokens[i - 1].name in (INDENT, UNIMPORTANT_WS):
        # no types for tokenize-rt
        return tokens[i - 1].src  # type: ignore [no-any-return]
    return ""


def switch_to_travel(
    tokens: list[Token], i: int, node: ast.Attribute | ast.Name
) -> None:
    j = find_last_token(tokens, i, node=node)
    tokens[i : j + 1] = [Token(name=CODE, src="time_machine.travel")]


def switch_to_marker(tokens: list[Token], i: int, node: ast.Attribute) -> None:
    j = find_last_token(tokens, i, node=node)
    tokens[i : j + 1] = [Token(name=CODE, src="pytest.mark.time_machine")]


def replace_freezer(tokens: list[Token], i: int) -> None:
    tokens[i] = Token(name="NAME", src="time_machine")


def replace_tick_with_shift(tokens: list[Token], i: int, node: ast.Call) -> None:
    """
    Replace a tick() method call with shift(), making freezegun’s default
    delta of one second explicit if no argument was passed.
    """
    i += 1  # skip the receiver name
    while not (tokens[i].name == "NAME" and tokens[i].src == "tick"):
        i += 1
    tokens[i] = Token(name="NAME", src="shift")
    if not node.args and not node.keywords:
        while tokens[i].src != "(":
            i += 1
        tokens.insert(i + 1, Token(name=CODE, src="1"))


def add_tick_false(tokens: list[Token], i: int, node: ast.Call) -> None:
    """
    Add `tick=False` to the function call, unless `tick` is already set.
    """
    j = find_last_token(tokens, i, node=node)
    k = j - 1
    while tokens[k].name in NON_CODING_TOKENS:
        k -= 1
    if tokens[k].src == ",":
        # trailing comma: insert after it
        tokens.insert(k + 1, Token(name=CODE, src=" tick=False"))
    else:
        tokens.insert(j, Token(name=CODE, src=", tick=False"))


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
