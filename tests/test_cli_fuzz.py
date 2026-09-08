from __future__ import annotations

import ast
import sys

import pytest

if sys.version_info[:2] == (3, 13) and not sys._is_gil_enabled():
    # Hypothesis has no free-threaded wheels for Python 3.13, and cannot be
    # built from source there, since PyO3 does not support free-threaded
    # Python < 3.14.
    pytest.skip("Hypothesis unavailable", allow_module_level=True)

from hypothesis import given, settings
from hypothesis import strategies as st

from time_machine.cli import Report, migrate_contents

# Fuzz the migration CLI with generated source files combining the constructs
# that it targets, varying formatting. The generated code only needs to parse,
# not run, so undefined names are fine.


def indent(block: str) -> str:
    return "\n".join(f"    {line}" for line in block.splitlines())


freeze_time_callees = st.sampled_from(
    [
        "freeze_time",
        "freezegun.freeze_time",
        "(freeze_time)",
        "fg.freeze_time",
        "ft_alias",
        "freezegun.api.freeze_time",
        "(freezegun).freeze_time",
        "freezegun . freeze_time",
    ]
)

freeze_time_arglists = st.sampled_from(
    [
        (),
        ('"2023-01-01"',),
        ("dest",),
        ("dt.datetime(2023, 1, 1)",),
        ('"2023-01-01 ünïcode"',),
        ("*args",),
        ("**kwargs",),
        ('"2023-01-01"', "tick=True"),
        ('"2023-01-01"', "tick=False"),
        ('"2023-01-01"', "tick=tick"),
        ('"2023-01-01"', "auto_tick_seconds=1"),
        ('"2023-01-01"', "auto_tick_seconds=0"),
        ('"2023-01-01"', "as_arg=True"),
        ('"2023-01-01"', "tz_offset=0"),
        ('"2023-01-01"', "tz_offset=0.0"),
        ('"2023-01-01"', "tz_offset=-0"),
        ('"2023-01-01"', "tz_offset=-4"),
        ('"2023-01-01"', "tz_offset=0", "tick=True"),
        ('"2023-01-01"', "real_asyncio=True"),
        ('"2023-01-01"', "real_asyncio=False"),
        ('"2023-01-01"', 'ignore=["threading"]'),
        ('"2023-01-01"', "ignore=[]"),
        ("tz_offset=0",),
        ("tick=True",),
        ("real_asyncio=True",),
        ("tz_offset=0", "tick=True"),
        ("tz_offset=0", "real_asyncio=True", 'ignore=["threading"]'),
    ]
)

method_arglists = st.sampled_from(
    [
        (),
        ('"2023-01-01"',),
        ('"2023-01-01"', '"2024-01-01"'),
        ("1",),
        ("delta=1",),
        ("delta=1", "other=2"),
        ("tick=True",),
        ("*args",),
    ]
)


@st.composite
def calls(
    draw: st.DrawFn, callee: str, arglists: st.SearchStrategy[tuple[str, ...]]
) -> str:
    args = list(draw(arglists))
    style = draw(
        st.sampled_from(
            [
                "plain",
                "spaced",
                "trailing_comma",
                "multiline",
                "multiline_no_trailing_comma",
                "backslash",
                "comment_after_paren",
            ]
        )
    )
    if not args or style == "plain":
        return f"{callee}({', '.join(args)})"
    elif style == "spaced":
        return f"{callee} ( {' , '.join(args)} )"
    elif style == "trailing_comma":
        return f"{callee}({', '.join(args)},)"
    elif style == "multiline":
        comment = "  # comment" if draw(st.booleans()) else ""
        return f"{callee}(" + "".join(f"\n    {arg},{comment}" for arg in args) + "\n)"
    elif style == "multiline_no_trailing_comma":
        return f"{callee}(\n    " + ",\n    ".join(args) + "\n)"
    elif style == "backslash":
        return f"{callee}(\\\n    {', '.join(args)}\\\n)"
    else:
        return f"{callee}(  # comment\n    {', '.join(args)}\n)"


@st.composite
def freeze_time_calls(draw: st.DrawFn) -> str:
    return draw(calls(draw(freeze_time_callees), freeze_time_arglists))


@st.composite
def decorators(draw: st.DrawFn) -> str:
    kind = draw(st.sampled_from(["freeze_time", "marker", "not_called", "unrelated"]))
    if kind == "freeze_time":
        return "@" + draw(freeze_time_calls())
    elif kind == "marker":
        return "@" + draw(calls("pytest.mark.freeze_time", freeze_time_arglists))
    elif kind == "not_called":
        return draw(
            st.sampled_from(
                [
                    "@freeze_time",
                    "@pytest.mark.freeze_time",
                    "@freezegun.freeze_time",
                    "@ft_alias",
                ]
            )
        )
    else:
        return '@mock.patch("example.thing")'


@st.composite
def pytestmark_statements(draw: st.DrawFn) -> str:
    markers = draw(
        st.lists(
            calls("pytest.mark.freeze_time", freeze_time_arglists)
            | st.sampled_from(["pytest.mark.freeze_time", "pytest.mark.django_db"]),
            min_size=1,
            max_size=2,
        )
    )
    if len(markers) == 1 and draw(st.booleans()):
        return f"pytestmark = {markers[0]}"
    wrapper = draw(st.sampled_from(["[{}]", "({},)"]))
    return "pytestmark = " + wrapper.format(", ".join(markers))


@st.composite
def raw_assignment_statements(draw: st.DrawFn) -> str:
    receiver = draw(st.sampled_from(["freezer", "ft", "self.freezer", "freeze_time"]))
    lines = [f"{receiver} = " + draw(freeze_time_calls())]
    for method in draw(
        st.lists(st.sampled_from(["start", "stop", "move_to", "tick"]), max_size=2)
    ):
        form = draw(st.sampled_from(["call", "call", "reference", "chained"]))
        if form == "call":
            lines.append(draw(calls(f"{receiver}.{method}", method_arglists)))
        elif form == "reference":
            lines.append(f"cleanup({receiver}.{method})")
        else:
            lines.append(f"x = {receiver}.{method}().other")
    if draw(st.booleans()):
        lines.append(f"{receiver} = other()")
    return "\n".join(lines)


@st.composite
def method_statements(draw: st.DrawFn) -> str:
    receiver = draw(st.sampled_from(["freezer", "t", "ft", "tick", "other"]))
    kind = draw(st.sampled_from(["call", "call", "call", "attribute", "reference"]))
    if kind == "attribute":
        return f"assert {receiver}.time_to_freeze"
    elif kind == "reference":
        return f"helper({receiver})"
    wrapped = draw(st.sampled_from(["{}", "({})", "( {} )", "({}\n)"])).format(receiver)
    dot = draw(st.sampled_from([".", " . "]))
    method = draw(st.sampled_from(["move_to", "tick", "shift", "start"]))
    statement = draw(calls(f"{wrapped}{dot}{method}", method_arglists))
    if draw(st.booleans()):
        statement = f"x = {statement}"
    if draw(st.booleans()):
        statement += "; " + draw(calls(f"{receiver}.tick", method_arglists))
    if draw(st.booleans()):
        statement = 'x = "ünïcode"; ' + statement
    return statement


@st.composite
def with_statements(draw: st.DrawFn) -> str:
    items = []
    for _ in range(draw(st.integers(1, 2))):
        item = draw(freeze_time_calls())
        as_name = draw(st.sampled_from([None, "t", "ft", "tick", "freezer"]))
        if as_name is not None:
            item += f" as {as_name}"
        items.append(item)
    body = draw(
        st.lists(
            st.just("pass") | method_statements() | nested_with_statements(),
            min_size=1,
            max_size=2,
        )
    )
    joined = ", ".join(items)
    if len(items) > 1 and draw(st.booleans()):
        joined = f"({joined})"
    statement = f"with {joined}:\n" + "\n".join(indent(s) for s in body)
    wrapper = draw(st.sampled_from([None, None, "if", "for", "try"]))
    if wrapper == "if":
        statement = "if True:\n" + indent(statement)
    elif wrapper == "for":
        statement = "for x in things:\n" + indent(statement)
    elif wrapper == "try":
        statement = "try:\n" + indent(statement) + "\nfinally:\n    pass"
    return statement


@st.composite
def nested_with_statements(draw: st.DrawFn) -> str:
    item = draw(freeze_time_calls())
    as_name = draw(st.sampled_from([None, "ft", "inner"]))
    if as_name is not None:
        item += f" as {as_name}"
    body = draw(method_statements())
    return f"with {item}:\n" + indent(body)


@st.composite
def annotation_statements(draw: st.DrawFn) -> str:
    annotation = draw(
        st.sampled_from(
            [
                "FrozenDateTimeFactory",
                '"FrozenDateTimeFactory"',
                "'FrozenDateTimeFactory'",
                '"FrozenDateTimeFactory | None"',
                'Optional["FrozenDateTimeFactory"]',
                "FDF",
                '"FDF"',
            ]
        )
    )
    return f"fixture: {annotation} = None"


other_statements = st.sampled_from(
    [
        "FrozenDateTimeFactory = None",
        'name = "FrozenDateTimeFactory"',
        'print(f"{FrozenDateTimeFactory} here")',
        "x = FrozenDateTimeFactory()",
        "freeze_time = None",
        "x = freeze_time",
        'freeze_time("2023-01-01")(function)',
        'freeze_time("2023-01-01").start()',
        "from freezegun import freeze_time, FakeDate",
        "from freezegun.api import FrozenDateTimeFactory",
        "import freezegun",
    ]
)


@st.composite
def function_defs(draw: st.DrawFn) -> str:
    lines = draw(st.lists(decorators(), max_size=2))
    prefix = "async " if draw(st.booleans()) else ""
    params = draw(
        st.sampled_from(
            [
                "",
                "freezer",
                "self, freezer",
                "*, freezer",
                "freezer, other",
                "freezer=None",
                "other",
                "freezer: FrozenDateTimeFactory",
                'freezer: "FrozenDateTimeFactory"',
                'freezer: Optional["FrozenDateTimeFactory"]',
                'freezer: "FrozenDateTimeFactory | None"',
                "freezer: FDF",
                "freezer, time_machine",
                "FrozenDateTimeFactory",
                "freeze_time",
            ]
        )
    )
    returns = draw(
        st.sampled_from(["", " -> None", " -> FrozenDateTimeFactory", ' -> "FDF"'])
    )
    lines.append(f"{prefix}def test_function({params}){returns}:")
    body = draw(
        st.lists(
            st.just("pass")
            | other_statements
            | annotation_statements()
            | method_statements()
            | raw_assignment_statements()
            | with_statements(),
            min_size=1,
            max_size=3,
        )
    )
    lines.extend(indent(s) for s in body)
    return "\n".join(lines)


@st.composite
def class_defs(draw: st.DrawFn) -> str:
    lines = draw(st.lists(decorators(), max_size=1))
    bases = draw(st.sampled_from(["", "(unittest.TestCase)", "(TestBase)"]))
    lines.append(f"class TestSomething{bases}:")
    body = draw(
        st.lists(
            st.just("pass")
            | pytestmark_statements()
            | function_defs()
            | raw_assignment_statements()
            | with_statements(),
            min_size=1,
            max_size=2,
        )
    )
    lines.extend(indent(s) for s in body)
    return "\n".join(lines)


imports = st.sampled_from(
    [
        "import freezegun",
        "import freezegun as fg",
        "import freezegun.api",
        "import freezegun, os",
        "from freezegun import freeze_time",
        "from freezegun import freeze_time as ft_alias",
        "from freezegun import freeze_time, FakeDate",
        "from freezegun import freeze_time, FrozenDateTimeFactory",
        "from freezegun.api import freeze_time",
        "from freezegun.api import FrozenDateTimeFactory",
        "from freezegun.api import FrozenDateTimeFactory as FDF",
        "from freezegun import FrozenDateTimeFactory  # noqa",
        "if True: from freezegun import freeze_time, FakeDate",
        "if TYPE_CHECKING: from freezegun.api import FrozenDateTimeFactory",
        "if TYPE_CHECKING:\n    from freezegun.api import FrozenDateTimeFactory",
        "import os; from freezegun import freeze_time; import sys",
        (
            "try:\n"
            "    from freezegun import freeze_time\n"
            "except ImportError:\n"
            "    freeze_time = None"
        ),
        "import pytest",
        "import time_machine",
        "from typing import Optional, TYPE_CHECKING",
        "from __future__ import annotations",
        "from othermod import FrozenDateTimeFactory",
    ]
)


@st.composite
def modules(draw: st.DrawFn) -> str:
    parts = draw(st.lists(imports, unique=True, max_size=4))
    parts.extend(
        draw(
            st.lists(
                function_defs()
                | class_defs()
                | with_statements()
                | method_statements()
                | raw_assignment_statements()
                | pytestmark_statements()
                | annotation_statements()
                | other_statements,
                min_size=1,
                max_size=4,
            )
        )
    )
    source = "\n\n".join(parts) + "\n"
    if draw(st.booleans()):
        source = "# -*- coding: utf-8 -*-\n" + source
    return source


def freezegun_bound_names(tree: ast.Module) -> set[str]:
    """
    The names that the module's freezegun imports bind, that migration is
    expected to either rewrite or report.
    """
    names = set()
    for node in ast.walk(tree):
        match node:
            case ast.Import():
                for alias in node.names:
                    if alias.name == "freezegun" or alias.name.startswith("freezegun."):
                        names.add(alias.asname or "freezegun")
            case ast.ImportFrom(module="freezegun" | "freezegun.api"):
                for alias in node.names:
                    if alias.name in ("freeze_time", "FrozenDateTimeFactory"):
                        names.add(alias.asname or alias.name)
    return names


def check_report_positions(source: str, reports: list[Report]) -> None:
    """
    Each report must point at the reported name in the given source, by
    1-based line and 1-based UTF-8 byte column.
    """
    lines = source.splitlines()
    for report in reports:
        name = report.message.removesuffix(" usage not migrated")
        assert name != report.message, report.message
        expected = name.split(".")[0].encode()
        assert 1 <= report.lineno <= len(lines), report
        text = lines[report.lineno - 1].encode()[report.col - 1 :]
        if text.startswith(expected):
            continue
        # A string annotation containing the name.
        assert text.lstrip(b"rRuU")[:1] in (b'"', b"'"), (report, text)
        assert expected in text, (report, text)


@settings(deadline=None, max_examples=500)
@given(source=modules())
def test_migrate_contents_properties(source: str) -> None:
    tree = ast.parse(source)  # the grammar should only generate valid code

    migrated, reports = migrate_contents(source)  # must not crash

    # the output must still be valid Python
    migrated_tree = ast.parse(migrated)

    # migration must be idempotent
    assert migrate_contents(migrated)[0] == migrated

    # nothing to migrate means nothing changed
    if "freeze" not in source:
        assert migrated == source
        assert reports == []

    # reports are sorted and unique, and point at the named usage in the
    # migrated file, which is what the user sees them alongside.
    assert reports == sorted(set(reports))
    check_report_positions(migrated, reports)

    # migrated calls have a single destination and only the tick keyword
    for node in ast.walk(migrated_tree):
        match node:
            case ast.Call(
                func=ast.Attribute(
                    value=ast.Name(id="time_machine"),
                    attr="travel",
                )
                | ast.Attribute(
                    value=ast.Attribute(
                        value=ast.Name(id="pytest"),
                        attr="mark",
                    ),
                    attr="time_machine",
                )
            ):
                assert len(node.args) == 1, ast.unparse(node)
                assert [kw.arg for kw in node.keywords] == ["tick"], ast.unparse(node)

    # without reports, no uses of the names bound by freezegun imports remain
    if not reports:
        bound = freezegun_bound_names(tree)
        remaining = [
            node
            for node in ast.walk(migrated_tree)
            if isinstance(node, ast.Name) and node.id in bound
        ]
        assert remaining == [], [ast.unparse(node) for node in remaining]
