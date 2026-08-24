from __future__ import annotations

import argparse
import ast
import difflib
import sys
import warnings
from collections import defaultdict
from collections.abc import Callable, Generator, Mapping, MutableMapping, Sequence
from functools import partial
from pathlib import Path
from typing import NamedTuple

try:
    from tokenize_rt import (
        NON_CODING_TOKENS,
        UNIMPORTANT_WS,
        Offset,
        Token,
        reversed_enumerate,
        src_to_tokens,
        tokens_to_src,
    )
except ImportError:  # pragma: no cover
    print(
        "time-machine’s migrate command requires the 'cli' extra: "
        "install time-machine[cli]",
        file=sys.stderr,
    )
    raise SystemExit(1) from None

CODE = "CODE"
DEDENT = "DEDENT"
INDENT = "INDENT"

# freezegun’s fake classes and the real datetime classes to migrate their
# uses to.
FAKE_CLASSES = {
    "FakeDatetime": "datetime",
    "FakeDate": "date",
}
# The class of freezegun’s pytest fixture, often imported to annotate the
# fixture argument, migrated to time-machine’s equivalent.
FIXTURE_FACTORY = "FrozenDateTimeFactory"
MIGRATABLE_IMPORT_NAMES = frozenset(("freeze_time", FIXTURE_FACTORY, *FAKE_CLASSES))


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
    migrate_parser.add_argument(
        "file",
        nargs="+",
        help="Python files or directories to migrate, or '-' for stdin.",
    )
    migrate_parser.add_argument(
        "--check",
        action="store_true",
        help="Don’t write changes; report the files that would be rewritten.",
    )
    migrate_parser.add_argument(
        "--diff",
        action="store_true",
        help="Don’t write changes; print a diff of the changes that would be made.",
    )

    args = parser.parse_args(argv)

    if args.command == "migrate":
        return migrate_files(files=args.file, check=args.check, diff=args.diff)
    else:  # pragma: no cover
        # Unreachable
        raise NotImplementedError(f"Command {args.command} does not exist.")


def migrate_files(files: list[str], *, check: bool = False, diff: bool = False) -> int:
    returncode = 0
    for filename in expand_targets(files):
        returncode |= migrate_file(filename, check=check, diff=diff)
    return returncode


def expand_targets(files: list[str]) -> Generator[str, None, None]:
    """
    Expand any directories in the given list into the Python files within
    them, recursively.
    """
    for name in files:
        path = Path(name)
        if name != "-" and path.is_dir():
            yield from sorted(str(p) for p in path.rglob("*.py"))
        else:
            yield name


def migrate_file(filename: str, *, check: bool = False, diff: bool = False) -> int:
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

    contents_text, reports = migrate_contents(contents_text)
    changed = contents_text != contents_text_orig

    if diff and changed:
        diff_lines = difflib.unified_diff(
            contents_text_orig.splitlines(keepends=True),
            contents_text.splitlines(keepends=True),
            fromfile=filename,
            tofile=filename,
        )
        for line in diff_lines:
            # Lines from a file without a final newline lack one.
            print(line, end="" if line.endswith("\n") else "\n")

    if filename == "-":
        if not check and not diff:
            print(contents_text, end="")
    elif changed:
        if check or diff:
            print(f"Would rewrite {filename}", file=sys.stderr)
        else:
            print(f"Rewriting {filename}", file=sys.stderr)
            with open(filename, "w", encoding="UTF-8", newline="") as f:
                f.write(contents_text)

    for report in reports:
        print(
            f"{filename}:{report.lineno}:{report.col}: {report.message}",
            file=sys.stderr,
        )

    return changed


class Report(NamedTuple):
    """A freezegun-related usage that could not be migrated."""

    lineno: int
    col: int
    message: str


def migrate_contents(contents_text: str) -> tuple[str, list[Report]]:
    """Migrate a single text from freezegun to time-machine."""
    try:
        ast_obj = ast_parse(contents_text)
    except (SyntaxError, ValueError) as exc:
        # ValueError comes from e.g. null bytes in the source.
        lineno = getattr(exc, "lineno", None) or 1
        col = getattr(exc, "offset", None) or 1
        msg = getattr(exc, "msg", None) or str(exc)
        return contents_text, [Report(lineno, col, f"could not parse file: {msg}")]

    callbacks, reports = visit(ast_obj)

    if not callbacks:
        return contents_text, reports

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
    new_text: str = tokens_to_src(tokens)
    return new_text, reports


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


def visit(
    tree: ast.Module,
) -> tuple[Mapping[Offset, list[TokenFunc]], list[Report]]:
    """
    Visit the AST and return a mapping of callbacks to apply to the tokens,
    plus reports of freezegun-related usages that could not be migrated.
    """
    ret: defaultdict[Offset, list[TokenFunc]] = defaultdict(list)
    freezegun_module_names: set[str] = set()
    freeze_time_names: set[str] = set()
    report_module_names: set[str] = set()
    freezegun_from_imports: list[ast.ImportFrom] = []
    datetime_module_names: set[str] = set()
    datetime_from_names: set[str] = set()
    datetime_class_bindings: dict[str, str] = {}
    freezer_functions: list[FreezerFunction] = []
    marker_class_methods: set[ast.FunctionDef | ast.AsyncFunctionDef] = set()
    module_marker_seen = False
    traveller_vars: list[TravellerVar] = []
    module_stmts = module_scope_stmts(tree)
    for node in ast.walk(tree):
        match node:
            case ast.Module():
                for stmt in node.body:
                    if maybe_migrate_pytestmark(ret, stmt):
                        module_marker_seen = True
            case ast.Import():
                if node in module_stmts:
                    # Only module-level datetime imports are usable for
                    # rewriting FakeDatetime / FakeDate uses, which may be
                    # anywhere in the module.
                    datetime_module_names.update(
                        alias.asname or "datetime"
                        for alias in node.names
                        if alias.name == "datetime"
                    )
                if (
                    len(node.names) == 1
                    and (alias := node.names[0]).name == "freezegun"
                ):
                    freezegun_module_names.add(alias.asname or "freezegun")
                    if alias.asname is None:
                        ret[ast_start_offset(node)].append(replace_import)
                    else:
                        ret[ast_start_offset(node)].append(
                            partial(replace_aliased_import, node=node)
                        )
                else:
                    # Imports of freezegun that cannot be migrated, like
                    # `import freezegun, os` or `import freezegun.config`,
                    # still have their bound names tracked for reporting.
                    report_module_names.update(
                        alias.asname or "freezegun"
                        for alias in node.names
                        if alias.name == "freezegun"
                        or alias.name.startswith("freezegun.")
                    )
            case ast.ImportFrom(module="datetime", level=0) if node in module_stmts:
                for alias in node.names:
                    datetime_from_names.add(alias.asname or alias.name)
                    if alias.name in ("datetime", "date"):
                        datetime_class_bindings.setdefault(
                            alias.name, alias.asname or alias.name
                        )
            case ast.ImportFrom() if (
                node.level == 0
                and node.module in ("freezegun", "freezegun.api")
                and any(alias.name in MIGRATABLE_IMPORT_NAMES for alias in node.names)
            ):
                freeze_time_names.update(
                    alias.asname or alias.name
                    for alias in node.names
                    if alias.name == "freeze_time"
                )
                freezegun_from_imports.append(node)
            case ast.FunctionDef() | ast.AsyncFunctionDef():
                marker_seen = module_marker_seen or node in marker_class_methods
                for decorator in node.decorator_list:
                    if maybe_migrate_marker(ret, decorator):
                        marker_seen = True
                    else:
                        maybe_migrate_call(
                            ret,
                            decorator,
                            freezegun_module_names=freezegun_module_names,
                            freeze_time_names=freeze_time_names,
                            freezer_functions=freezer_functions,
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

            case ast.ClassDef():
                class_marker_seen = False
                if node.decorator_list:
                    unittest_class = looks_like_unittest_class(node)
                    for decorator in node.decorator_list:
                        if maybe_migrate_marker(ret, decorator):
                            class_marker_seen = True
                        elif unittest_class:
                            maybe_migrate_call(
                                ret,
                                decorator,
                                freezegun_module_names=freezegun_module_names,
                                freeze_time_names=freeze_time_names,
                                freezer_functions=freezer_functions,
                            )
                for stmt in node.body:
                    if maybe_migrate_pytestmark(ret, stmt):
                        class_marker_seen = True
                if class_marker_seen:
                    marker_class_methods.update(
                        stmt
                        for stmt in node.body
                        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef))
                    )

            case ast.With():
                for item in node.items:
                    match item.optional_vars:
                        case None:
                            maybe_migrate_call(
                                ret,
                                item.context_expr,
                                freezegun_module_names=freezegun_module_names,
                                freeze_time_names=freeze_time_names,
                                freezer_functions=freezer_functions,
                            )
                        case ast.Name(id=name) as binding:
                            if traveller_var_uses_compatible(
                                node, binding
                            ) and maybe_migrate_call(
                                ret,
                                item.context_expr,
                                freezegun_module_names=freezegun_module_names,
                                freeze_time_names=freeze_time_names,
                                freezer_functions=freezer_functions,
                            ):
                                traveller_vars.append(TravellerVar(name, node))

            case ast.Expr(
                value=ast.Call(
                    func=ast.Attribute(
                        value=ast.Name(id=receiver) as receiver_node,
                        attr="tick",
                    )
                ) as call_node
            ) if migratable_tick_call(call_node):
                # tick() is only migrated as a statement, since shift() does
                # not return the new time.
                if receiver == "freezer" and find_freezer_function(
                    freezer_functions, call_node
                ):
                    ret[ast_start_offset(receiver_node)].append(replace_freezer)
                    ret[ast_start_offset(receiver_node)].append(
                        partial(replace_tick_with_shift, node=call_node)
                    )
                elif any(
                    traveller_var.name == receiver
                    and (
                        traveller_var.lineno
                        <= call_node.lineno
                        <= traveller_var.end_lineno
                    )
                    for traveller_var in traveller_vars
                ):
                    ret[ast_start_offset(receiver_node)].append(
                        partial(replace_tick_with_shift, node=call_node)
                    )

            case ast.Call(
                func=ast.Attribute(
                    value=ast.Name(id="freezer") as receiver_node,
                    attr="move_to",
                )
            ) if (
                len(node.args) == 1
                and not node.keywords
                and (freezer_function := find_freezer_function(freezer_functions, node))
                is not None
            ):
                ret[ast_start_offset(receiver_node)].append(replace_freezer)
                if not freezer_function.marker_seen:
                    ret[ast_start_offset(node)].append(
                        partial(add_tick_false, node=node)
                    )

    # Process from-imports of freezegun after the main walk, since migrating
    # FakeDatetime / FakeDate uses to the real datetime classes depends on the
    # datetime imports of the whole module.
    fake_bound: dict[str, str] = {}
    for import_node in freezegun_from_imports:
        for alias in import_node.names:
            if alias.name in FAKE_CLASSES or alias.name == FIXTURE_FACTORY:
                fake_bound[alias.asname or alias.name] = alias.name

    fake_uses: dict[str, list[ast.Name]] = {name: [] for name in fake_bound}
    fake_blocked: set[str] = set()
    if fake_bound:
        fake_blocked = fake_rebindings(tree, set(fake_bound))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in fake_bound:
                if isinstance(node.ctx, ast.Load):
                    fake_uses[node.id].append(node)
                else:
                    fake_blocked.add(node.id)
            elif isinstance(node, ast.JoinedStr):
                # On Python < 3.12, names within f-strings have no tokens to
                # rewrite.
                fake_blocked.update(
                    subnode.id
                    for subnode in ast.walk(node)
                    if isinstance(subnode, ast.Name) and subnode.id in fake_bound
                )

    fake_migratable: set[str] = set()
    fake_fallback: dict[str, str] = {}
    fixture_fallback: dict[str, str] = {}
    for name, freezegun_name in fake_bound.items():
        if name in fake_blocked:
            continue
        if not fake_uses[name]:
            # Imported but unused: drop from the import without rewrites.
            fake_migratable.add(name)
            continue
        if freezegun_name == FIXTURE_FACTORY:
            # Requires an import of the replacement, so needs a module-level
            # carrier import (checked below), like the datetime fallback.
            fixture_fallback[name] = "TimeMachineFixture"
            continue
        class_name = FAKE_CLASSES[freezegun_name]
        if class_name in datetime_class_bindings:
            expr = datetime_class_bindings[class_name]
        elif datetime_module_names:
            if "datetime" in datetime_module_names:
                module_name = "datetime"
            else:
                module_name = sorted(datetime_module_names)[0]
            expr = f"{module_name}.{class_name}"
        elif "datetime" not in datetime_from_names:
            # No datetime import to use, but the name is free, so one could
            # be added, if a module-level import will be rewritten to carry
            # it (checked below).
            fake_fallback[name] = f"datetime.{class_name}"
            continue
        else:
            # The name `datetime` is bound to the class, and there is no
            # usable import for this class.
            continue
        fake_migratable.add(name)
        for use in fake_uses[name]:
            ret[ast_start_offset(use)].append(partial(replace_name, src=expr))

    import_carrier: ast.ImportFrom | None = None
    carried_imports: list[str] = []
    if fake_fallback or fixture_fallback:
        # Added imports have to go at module level, replacing part of a
        # rewritten module-level freezegun import.
        for import_node in freezegun_from_imports:
            if import_node in module_stmts and any(
                alias.name == "freeze_time"
                or (alias.asname or alias.name) in fake_migratable
                or (alias.asname or alias.name) in fake_fallback
                or (alias.asname or alias.name) in fixture_fallback
                for alias in import_node.names
            ):
                import_carrier = import_node
                break
        if import_carrier is not None:
            if fake_fallback:
                carried_imports.append("import datetime")
            if fixture_fallback:
                carried_imports.append("from time_machine import TimeMachineFixture")
            for name, expr in (fake_fallback | fixture_fallback).items():
                fake_migratable.add(name)
                for use in fake_uses[name]:
                    ret[ast_start_offset(use)].append(partial(replace_name, src=expr))

    for import_node in freezegun_from_imports:
        has_freeze_time = any(
            alias.name == "freeze_time" for alias in import_node.names
        )
        if not has_freeze_time and not any(
            (alias.asname or alias.name) in fake_migratable
            for alias in import_node.names
        ):
            # Nothing migrated from this import: leave it unchanged.
            continue

        keep = [
            unparse_alias(alias)
            for alias in import_node.names
            if alias.name != "freeze_time"
            and (alias.asname or alias.name) not in fake_migratable
        ]
        new_stmts = []
        if has_freeze_time:
            new_stmts.append("import time_machine")
        if import_node is import_carrier:
            new_stmts.extend(carried_imports)
        if keep:
            new_stmts.append(f"from {import_node.module} import {', '.join(keep)}")

        if new_stmts:
            ret[ast_start_offset(import_node)].append(
                partial(replace_import_from, node=import_node, new_stmts=new_stmts)
            )
        elif len(containing_block(tree, import_node)) >= 2:
            ret[ast_start_offset(import_node)].append(
                partial(remove_statement, node=import_node)
            )
        else:
            # The only statement in its block, so removing it would leave
            # invalid syntax.
            ret[ast_start_offset(import_node)].append(
                partial(replace_import_from, node=import_node, new_stmts=["pass"])
            )

    if freeze_time_names or freezegun_module_names:
        for assignment, use_scope in find_candidate_assignments(tree):
            value = assignment.value
            assert isinstance(value, ast.Call)
            if not is_freeze_time_call(
                value,
                freezegun_module_names=freezegun_module_names,
                freeze_time_names=freeze_time_names,
            ):
                continue
            target = assignment.targets[0]
            if isinstance(target, ast.Name):
                compatible = name_target_uses_compatible(use_scope, target)
            else:
                assert isinstance(target, ast.Attribute)
                compatible = self_attr_target_uses_compatible(use_scope, target)
            if compatible:
                maybe_migrate_call(
                    ret,
                    value,
                    freezegun_module_names=freezegun_module_names,
                    freeze_time_names=freeze_time_names,
                    freezer_functions=freezer_functions,
                )

    unmigrated_fake_names = {name for name in fake_bound if name not in fake_migratable}

    reports = []
    for node in ast.walk(tree):
        match node:
            case ast.Name(id=name) if (
                name in freeze_time_names
                or name in freezegun_module_names
                or name in report_module_names
                or name in unmigrated_fake_names
            ) and ast_start_offset(node) not in ret:
                reports.append(
                    Report(
                        node.lineno,
                        node.col_offset + 1,
                        f"{name} usage not migrated",
                    )
                )
            case ast.Attribute(
                attr="freeze_time",
                value=ast.Attribute(
                    attr="mark",
                    value=ast.Name(id="pytest"),
                ),
            ) if ast_start_offset(node) not in ret:
                reports.append(
                    Report(
                        node.lineno,
                        node.col_offset + 1,
                        "pytest.mark.freeze_time usage not migrated",
                    )
                )
    reports.sort()

    return ret, reports


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


def module_scope_stmts(tree: ast.Module) -> set[ast.stmt]:
    """
    Collect the statements that execute at module scope, including within
    module-level compound statements like `if` and `try`, but not within
    functions or classes.
    """
    result: set[ast.stmt] = set()

    def add(body: list[ast.stmt]) -> None:
        for stmt in body:
            result.add(stmt)
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            for field in ("body", "orelse", "finalbody"):
                sub_body = getattr(stmt, field, None)
                if isinstance(sub_body, list):
                    add(sub_body)
            if isinstance(stmt, ast.Try):
                for handler in stmt.handlers:
                    add(handler.body)

    add(tree.body)
    return result


def fake_rebindings(tree: ast.Module, names: set[str]) -> set[str]:
    """
    Find which of the given fake class names are also bound by something
    other than their freezegun imports, such as function parameters, def or
    class statements, or imports from other modules. Rewriting uses of such
    names would be unsafe. (Heuristic: some rarer rebindings, like
    ``except ... as`` names, are not detected.)
    """
    rebound = set()
    for node in ast.walk(tree):
        match node:
            case ast.FunctionDef() | ast.AsyncFunctionDef() | ast.Lambda():
                if not isinstance(node, ast.Lambda) and node.name in names:
                    rebound.add(node.name)
                rebound.update(
                    arg.arg
                    for arg in (
                        *node.args.posonlyargs,
                        *node.args.args,
                        *node.args.kwonlyargs,
                    )
                    if arg.arg in names
                )
            case ast.ClassDef(name=name) if name in names:
                rebound.add(name)
            case ast.Import() | ast.ImportFrom():
                from_freezegun = isinstance(node, ast.ImportFrom) and node.module in (
                    "freezegun",
                    "freezegun.api",
                )
                for alias in node.names:
                    bound = alias.asname or alias.name.split(".")[0]
                    if bound in names and not (
                        from_freezegun and alias.name in MIGRATABLE_IMPORT_NAMES
                    ):
                        rebound.add(bound)
    return rebound


def is_freeze_time_call(
    node: ast.Call,
    *,
    freezegun_module_names: set[str],
    freeze_time_names: set[str],
) -> bool:
    """
    Check if the given call is of freezegun’s freeze_time(), per the names
    bound by the module’s imports.
    """
    func = node.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "freeze_time"
        and isinstance(func.value, ast.Name)
        and func.value.id in freezegun_module_names
    ) or (isinstance(func, ast.Name) and func.id in freeze_time_names)


def find_candidate_assignments(
    tree: ast.Module,
) -> Generator[tuple[ast.Assign, ast.AST], None, None]:
    """
    Yield assignments of call results that may be freeze_time() calls bound
    for "raw use" with start() and stop(), paired with the node to search for
    uses of the bound name: the enclosing function or module for plain names,
    or the enclosing class for `self.` attributes.
    """

    def recurse(
        node: ast.AST, scope: ast.AST | None, class_node: ast.ClassDef | None
    ) -> Generator[tuple[ast.Assign, ast.AST], None, None]:
        for child in ast.iter_child_nodes(node):
            match child:
                case ast.Assign(
                    targets=[ast.Name()],
                    value=ast.Call(),
                ) if scope is not None:
                    yield (child, scope)
                case ast.Assign(
                    targets=[ast.Attribute(value=ast.Name(id="self"))],
                    value=ast.Call(),
                ) if class_node is not None:
                    yield (child, class_node)

            match child:
                case ast.FunctionDef() | ast.AsyncFunctionDef():
                    yield from recurse(child, child, class_node)
                case ast.ClassDef():
                    # Plain-name assignments directly in a class body are not
                    # tracked, since their uses cannot be checked simply.
                    yield from recurse(child, None, child)
                case _:
                    yield from recurse(child, scope, class_node)

    yield from recurse(tree, tree, None)


def name_target_uses_compatible(scope: ast.AST, target: ast.Name) -> bool:
    """
    Check that a plain variable assigned a freeze_time() call is only used in
    ways that work the same on time-machine's travel(): start() and stop()
    calls as statements, and bare start / stop references passed as call
    arguments, like `atexit.register(freezer.stop)`.
    """
    name = target.id
    allowed: set[ast.AST] = {target}
    for subnode in ast.walk(scope):
        match subnode:
            case ast.Expr(
                value=ast.Call(
                    func=ast.Attribute(
                        value=ast.Name(id=receiver) as receiver_node,
                        attr="start" | "stop",
                    ),
                    args=[],
                    keywords=[],
                )
            ) if receiver == name:
                allowed.add(receiver_node)
            case ast.Call(args=args):
                for arg in args:
                    match arg:
                        case ast.Attribute(
                            value=ast.Name(id=receiver) as receiver_node,
                            attr="start" | "stop",
                        ) if receiver == name:
                            allowed.add(receiver_node)
    return all(
        subnode in allowed
        for subnode in ast.walk(scope)
        if isinstance(subnode, ast.Name) and subnode.id == name
    )


def self_attr_target_uses_compatible(scope: ast.AST, target: ast.Attribute) -> bool:
    """
    As for name_target_uses_compatible(), but for a `self.` attribute
    assigned a freeze_time() call, checked across the enclosing class, so
    unittest setUp() / tearDown() / addCleanup() patterns are covered.
    """
    name = target.attr
    allowed: set[ast.AST] = {target}
    for subnode in ast.walk(scope):
        match subnode:
            case ast.Expr(
                value=ast.Call(
                    func=ast.Attribute(
                        value=ast.Attribute(
                            value=ast.Name(id="self"),
                            attr=receiver,
                        ) as receiver_node,
                        attr="start" | "stop",
                    ),
                    args=[],
                    keywords=[],
                )
            ) if receiver == name:
                allowed.add(receiver_node)
            case ast.Call(args=args):
                for arg in args:
                    match arg:
                        case ast.Attribute(
                            value=ast.Attribute(
                                value=ast.Name(id="self"),
                                attr=receiver,
                            ) as receiver_node,
                            attr="start" | "stop",
                        ) if receiver == name:
                            allowed.add(receiver_node)
    return all(
        subnode in allowed
        for subnode in ast.walk(scope)
        if isinstance(subnode, ast.Attribute)
        and isinstance(subnode.value, ast.Name)
        and subnode.value.id == "self"
        and subnode.attr == name
    )


def maybe_migrate_call(
    ret: MutableMapping[Offset, list[TokenFunc]],
    node: ast.expr,
    *,
    freezegun_module_names: set[str],
    freeze_time_names: set[str],
    freezer_functions: list[FreezerFunction],
) -> bool:
    """
    Add the callbacks to rewrite the given expression, if it is a migratable
    call to freezegun’s freeze_time(), returning whether that was the case.
    """
    if (
        not isinstance(node, ast.Call)
        or not is_freeze_time_call(
            node,
            freezegun_module_names=freezegun_module_names,
            freeze_time_names=freeze_time_names,
        )
        or not migratable_call(node)
    ):
        return False

    if find_freezer_function(freezer_functions, node) is not None:
        # Inside a function whose freezer argument is renamed to
        # time_machine, shadowing the module, so a rewritten call would not
        # resolve to it.
        return False

    func = node.func
    assert isinstance(func, (ast.Attribute, ast.Name))
    ret[ast_start_offset(func)].append(partial(switch_to_travel, node=func))
    migrate_arguments(ret, node)
    return True


def traveller_var_uses_compatible(node: ast.With, binding: ast.Name) -> bool:
    """
    Check that a variable bound with ``as`` to a freeze_time() context manager
    is only used in ways that work the same on time-machine’s Traveller:
    move_to() calls, and tick() calls as statements, since shift() does not
    return the new time.
    """
    name = binding.id
    allowed = {binding}
    for subnode in ast.walk(node):
        match subnode:
            case ast.Expr(
                value=ast.Call(
                    func=ast.Attribute(
                        value=ast.Name(id=receiver) as receiver_node,
                        attr="tick",
                    )
                )
            ) if receiver == name:
                allowed.add(receiver_node)
            case ast.Call(
                func=ast.Attribute(
                    value=ast.Name(id=receiver) as receiver_node,
                    attr="move_to",
                )
            ) if receiver == name:
                allowed.add(receiver_node)
    return all(
        subnode in allowed
        for subnode in ast.walk(node)
        if isinstance(subnode, ast.Name) and subnode.id == name
    )


def maybe_migrate_pytestmark(
    ret: MutableMapping[Offset, list[TokenFunc]],
    node: ast.stmt,
) -> bool:
    """
    Add the callbacks to rewrite any migratable pytest.mark.freeze_time()
    markers in the given statement, if it is a ``pytestmark`` assignment,
    returning whether any were migrated.
    """
    elements: list[ast.expr]
    match node:
        case ast.Assign(
            targets=[ast.Name(id="pytestmark")],
            value=ast.Call() as single,
        ):
            elements = [single]
        case ast.Assign(
            targets=[ast.Name(id="pytestmark")],
            value=ast.List(elts=elements) | ast.Tuple(elts=elements),
        ):
            pass
        case _:
            return False

    migrated = False
    for element in elements:
        if maybe_migrate_marker(ret, element):
            migrated = True
    return migrated


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
    migrate_arguments(ret, node)
    return True


def migrate_arguments(
    ret: MutableMapping[Offset, list[TokenFunc]],
    node: ast.Call,
) -> None:
    """
    Add the callbacks to adjust the arguments of a migratable freeze_time()
    call: add a None destination if there is no positional argument, add
    tick=False if tick is not passed, and remove droppable keyword arguments.
    """
    tick_kwargs = [kw for kw in node.keywords if kw.arg == "tick"]
    if not node.args:
        if tick_kwargs:
            ret[ast_start_offset(tick_kwargs[0])].append(insert_none_arg)
        else:
            ret[ast_start_offset(node)].append(partial(add_none_arg, node=node))
    if not tick_kwargs:
        ret[ast_start_offset(node)].append(partial(add_tick_false, node=node))
    for kw in node.keywords:
        if droppable_kwarg(kw):
            ret[ast_start_offset(kw)].append(partial(remove_kwarg, node=kw))


def migratable_call(node: ast.Call) -> bool:
    return len(node.args) <= 1 and all(
        kw.arg == "tick" or droppable_kwarg(kw) for kw in node.keywords
    )


def droppable_kwarg(kw: ast.keyword) -> bool:
    """
    Check if the given freeze_time() keyword argument can be dropped when
    migrating, because its value makes it have no effect or requests
    behaviour that time-machine always provides.
    """
    if kw.arg == "tz_offset":
        # A zero offset has no effect.
        return (
            isinstance(kw.value, ast.Constant)
            and type(kw.value.value) in (int, float)
            and kw.value.value == 0
        )
    elif kw.arg == "real_asyncio":
        # time-machine does not mock time.monotonic(), so asyncio event
        # loops always see real time.
        return isinstance(kw.value, ast.Constant) and kw.value.value is True
    else:
        # ignore works around problems with freezegun’s module patching,
        # which time-machine’s C-level mocking doesn’t have.
        return kw.arg == "ignore"


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


def replace_aliased_import(tokens: list[Token], i: int, node: ast.Import) -> None:
    """
    Replace an ``import freezegun as <name>`` statement with
    ``import time_machine``, dropping the alias since calls of
    ``<name>.freeze_time()`` are rewritten to ``time_machine.travel()``.
    """
    j = find_last_token(tokens, i, node=node)
    tokens[i : j + 1] = [Token(name=CODE, src="import time_machine")]


def unparse_alias(alias: ast.alias) -> str:
    if alias.asname is not None:
        return f"{alias.name} as {alias.asname}"
    return alias.name


def replace_import_from(
    tokens: list[Token], i: int, node: ast.ImportFrom, new_stmts: list[str]
) -> None:
    """
    Replace a from-import of freezegun with the given statements, indented to
    match.
    """
    j = find_last_token(tokens, i, node=node)
    src = f"\n{line_indent(tokens, i)}".join(new_stmts)
    tokens[i : j + 1] = [Token(name=CODE, src=src)]


def remove_statement(tokens: list[Token], i: int, node: ast.stmt) -> None:
    """
    Remove the given statement, including its line when nothing else shares
    it, otherwise replacing it with `pass`.
    """
    j = find_last_token(tokens, i, node=node)
    j2 = j
    while tokens[j2 + 1].name in (UNIMPORTANT_WS, "COMMENT"):
        j2 += 1
    k = i
    while k > 0 and tokens[k - 1].name in (INDENT, UNIMPORTANT_WS):
        k -= 1
    starts_line = k == 0 or tokens[k - 1].name in (
        "ENCODING",
        "NEWLINE",
        "NL",
        DEDENT,
    )
    if starts_line and tokens[j2 + 1].name == "NEWLINE":
        del tokens[k : j2 + 2]
    else:
        # Something else shares the line, like statements separated with `;`.
        tokens[i : j + 1] = [Token(name=CODE, src="pass")]


def containing_block(tree: ast.Module, stmt: ast.stmt) -> list[ast.stmt]:
    """
    Find the list of statements containing the given one.
    """
    for parent in ast.walk(tree):
        for field in ("body", "orelse", "finalbody"):
            block = getattr(parent, field, None)
            if isinstance(block, list) and stmt in block:
                return block
    raise AssertionError(f"Statement not found in tree: {stmt!r}")  # pragma: no cover


def replace_name(tokens: list[Token], i: int, *, src: str) -> None:
    tokens[i] = Token(name=CODE, src=src)


def line_indent(tokens: list[Token], i: int) -> str:
    """
    Return the whitespace indenting the line that the given token starts, or
    "" if the token does not start a line, like after `if ...:` or `;`.
    """
    if (
        i > 0
        and tokens[i - 1].name in (INDENT, UNIMPORTANT_WS)
        and tokens[i - 2].name in ("NEWLINE", "NL", DEDENT)
    ):
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


def remove_kwarg(tokens: list[Token], i: int, node: ast.keyword) -> None:
    """
    Remove the given keyword argument, along with the comma that precedes it,
    or, for a first argument, any comma and space that follow it.
    """
    j = find_last_token(tokens, i, node=node)
    k = i - 1
    while tokens[k].name in NON_CODING_TOKENS:
        k -= 1
    if tokens[k].src == ",":
        del tokens[k : j + 1]
        return
    k = j + 1
    while tokens[k].name in NON_CODING_TOKENS:
        k += 1
    if tokens[k].src == ",":
        j = k
        if tokens[j + 1].name == UNIMPORTANT_WS:
            j += 1
    del tokens[i : j + 1]


def insert_none_arg(tokens: list[Token], i: int) -> None:
    """
    Insert a `None` argument before the token at the given index, the start of
    the call’s tick keyword argument.
    """
    tokens.insert(i, Token(name=CODE, src="None, "))


def add_none_arg(tokens: list[Token], i: int, node: ast.Call) -> None:
    """
    Add a `None` argument to the function call, which has no remaining
    arguments, since any droppable keyword arguments were already removed.
    """
    j = find_last_token(tokens, i, node=node)
    k = j - 1
    while tokens[k].name in NON_CODING_TOKENS:
        k -= 1
    assert tokens[k].src == "("
    tokens.insert(k + 1, Token(name=CODE, src="None"))


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
