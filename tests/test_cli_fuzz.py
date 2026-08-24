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

from time_machine.cli import migrate_contents

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
    ]
)

freeze_time_arglists = st.sampled_from(
    [
        (),
        ('"2023-01-01"',),
        ("dest",),
        ('"2023-01-01"', "tick=True"),
        ('"2023-01-01"', "tick=False"),
        ('"2023-01-01"', "auto_tick_seconds=1"),
        ('"2023-01-01"', "tz_offset=0"),
        ('"2023-01-01"', "tz_offset=-4"),
        ('"2023-01-01"', "tz_offset=0", "tick=True"),
    ]
)

method_arglists = st.sampled_from(
    [
        (),
        ('"2023-01-01"',),
        ('"2023-01-01"', '"2024-01-01"'),
        ("1",),
        ("delta=1",),
        ("tick=True",),
    ]
)


@st.composite
def calls(
    draw: st.DrawFn, callee: str, arglists: st.SearchStrategy[tuple[str, ...]]
) -> str:
    args = list(draw(arglists))
    style = draw(st.sampled_from(["plain", "spaced", "trailing_comma", "multiline"]))
    if not args or style == "plain":
        return f"{callee}({', '.join(args)})"
    elif style == "spaced":
        return f"{callee} ( {' , '.join(args)} )"
    elif style == "trailing_comma":
        return f"{callee}({', '.join(args)},)"
    else:
        comment = "  # comment" if draw(st.booleans()) else ""
        return f"{callee}(" + "".join(f"\n    {arg},{comment}" for arg in args) + "\n)"


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
                ["@freeze_time", "@pytest.mark.freeze_time", "@freezegun.freeze_time"]
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
    body = draw(st.lists(st.just("pass") | method_statements(), min_size=1, max_size=2))
    joined = ", ".join(items)
    if len(items) > 1 and draw(st.booleans()):
        joined = f"({joined})"
    return f"with {joined}:\n" + "\n".join(indent(s) for s in body)


@st.composite
def function_defs(draw: st.DrawFn) -> str:
    lines = draw(st.lists(decorators(), max_size=2))
    prefix = "async " if draw(st.booleans()) else ""
    params = draw(
        st.sampled_from(
            ["", "freezer", "self, freezer", "*, freezer", "freezer, other", "other"]
        )
    )
    lines.append(f"{prefix}def test_function({params}):")
    body = draw(
        st.lists(
            st.just("pass")
            | st.just("from freezegun import freeze_time, FakeDate")
            | method_statements()
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
            st.just("pass") | pytestmark_statements() | function_defs(),
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
        "from freezegun import freeze_time",
        "from freezegun import freeze_time, FakeDate",
        "if True: from freezegun import freeze_time, FakeDate",
        "import pytest",
    ]
)


@st.composite
def modules(draw: st.DrawFn) -> str:
    parts = draw(st.lists(imports, unique=True, max_size=3))
    parts.extend(
        draw(
            st.lists(
                function_defs()
                | class_defs()
                | with_statements()
                | method_statements()
                | pytestmark_statements(),
                min_size=1,
                max_size=3,
            )
        )
    )
    return "\n\n".join(parts) + "\n"


@settings(deadline=None, max_examples=200)
@given(source=modules())
def test_migrate_contents_properties(source: str) -> None:
    ast.parse(source)  # the grammar should only generate valid code

    migrated = migrate_contents(source)  # must not crash

    # the output must still be valid Python
    ast.parse(migrated)

    # migration must be idempotent
    assert migrate_contents(migrated) == migrated
