from __future__ import annotations

import io
import subprocess
import sys
from pathlib import Path
from textwrap import dedent
from unittest import mock

import pytest

# import __main__ for coverage
from time_machine import __main__  # noqa: F401
from time_machine.cli import main, migrate_contents


class TestMain:
    def test_no_subcommand(self, capsys):
        with pytest.raises(SystemExit) as excinfo:
            main([])

        assert excinfo.value.code == 2
        out, err = capsys.readouterr()
        prog_name = (
            f"{Path(sys.executable).name} -m pytest"
            if sys.version_info >= (3, 14) and sys.modules["__main__"].__spec__
            else Path(sys.argv[0]).name
        )
        assert err == (
            f"usage: {prog_name} [-h] {{migrate}} ...\n"
            + f"{prog_name}: error: the following arguments are required: command\n"
        )
        assert out == ""

    def test_main_help(self):
        with pytest.raises(SystemExit) as excinfo:
            main(["--help"])

        assert excinfo.value.code == 0

    def test_main_help_subprocess(self):
        proc = subprocess.run(
            [sys.executable, "-m", "time_machine", "--help"],
            check=True,
            capture_output=True,
        )

        if sys.version_info >= (3, 14):
            assert proc.stdout.startswith(
                f"usage: {Path(sys.executable).name} -m time_machine ".encode()
            )
        else:
            assert proc.stdout.startswith(b"usage: __main__.py ")

    def test_migrate_help_command(self, capsys):
        with pytest.raises(SystemExit) as excinfo:
            main(["migrate", "--help"])
        assert excinfo.value.code == 0

    def test_migrate_no_files(self, capsys):
        with pytest.raises(SystemExit) as excinfo:
            main(["migrate"])

        assert excinfo.value.code == 2

    def test_migrate_empty(self, capsys, tmp_path):
        path = tmp_path / "example.py"
        path.write_text("\n")

        result = main(["migrate", str(path)])

        assert result == 0
        out, err = capsys.readouterr()
        assert out == ""
        assert err == ""

        assert path.read_text() == "\n"

    def test_migrate_syntax_error(self, capsys, tmp_path):
        path = tmp_path / "example.py"
        path.write_text("def def def\n")

        result = main(["migrate", str(path)])

        assert result == 0
        out, err = capsys.readouterr()
        assert out == ""
        assert err == f"{path}:1:5: could not parse file: invalid syntax\n"

        assert path.read_text() == "def def def\n"

    def test_migrate_null_byte(self, capsys, tmp_path):
        path = tmp_path / "example.py"
        path.write_bytes(b"x = 1\x00\n")

        result = main(["migrate", str(path)])

        assert result == 0
        out, err = capsys.readouterr()
        assert out == ""
        assert err == (
            f"{path}:1:1: could not parse file: "
            + "source code string cannot contain null bytes\n"
        )

        assert path.read_bytes() == b"x = 1\x00\n"

    def test_migrate_non_utf8(self, capsys, tmp_path):
        path = tmp_path / "example.py"
        path.write_bytes("# -*- coding: cp1252 -*-\nx = €\n".encode("cp1252"))

        result = main(["migrate", str(path)])

        assert result == 1
        out, err = capsys.readouterr()
        assert out == f"{path} is non-utf-8 (not supported)\n"
        assert err == ""

    def test_migrate_stdin_empty(self, capsys):
        stdin = io.TextIOWrapper(io.BytesIO(b""), "UTF-8")

        with mock.patch.object(sys, "stdin", stdin):
            result = main(["migrate", "-"])

        assert result == 0
        out, err = capsys.readouterr()
        assert out == ""
        assert err == ""

    def test_migrate_import(self, capsys, tmp_path):
        path = tmp_path / "example.py"
        path.write_text("import freezegun\n")

        result = main(["migrate", str(path)])

        assert result == 1
        out, err = capsys.readouterr()
        assert out == ""
        assert err == f"Rewriting {path}\n"

        assert path.read_text() == "import time_machine\n"

    def test_migrate_stdin_import(self, capsys):
        stdin = io.TextIOWrapper(io.BytesIO(b"import freezegun\n"), "UTF-8")

        with mock.patch.object(sys, "stdin", stdin):
            result = main(["migrate", "-"])

        assert result == 1
        out, err = capsys.readouterr()
        assert out == "import time_machine\n"
        assert err == ""

    def test_migrate_reports(self, capsys, tmp_path):
        path = tmp_path / "example.py"
        path.write_text(
            "from freezegun import freeze_time\n"
            "@freeze_time\n"
            "def test_function():\n"
            "    pass\n"
        )

        result = main(["migrate", str(path)])

        assert result == 1
        out, err = capsys.readouterr()
        assert out == ""
        assert err == (
            f"Rewriting {path}\n" + f"{path}:2:2: freeze_time usage not migrated\n"
        )

        assert path.read_text() == (
            "import time_machine\n@freeze_time\ndef test_function():\n    pass\n"
        )


def check_noop(
    given: str,
    reports: list[tuple[int, int, str]] | None = None,
) -> None:
    given = dedent(given)
    result, result_reports = migrate_contents(given)
    assert result == given
    assert result_reports == (reports or [])


def check_transformed(
    given: str,
    expected: str,
    reports: list[tuple[int, int, str]] | None = None,
) -> None:
    given = dedent(given)
    expected = dedent(expected)
    result, result_reports = migrate_contents(given)
    assert result == expected
    assert result_reports == (reports or [])


class TestMigrateContents:
    def test_import_unrelated(self):
        check_noop(
            "import libfaketime",
        )

    def test_aliased(self):
        check_transformed(
            "import freezegun as fg",
            "import time_machine",
        )

    def test_aliased_used(self):
        check_transformed(
            """
            import freezegun as fg

            @fg.freeze_time("2023-01-01")
            def test_function():
                pass
            """,
            """
            import time_machine

            @time_machine.travel("2023-01-01", tick=False)
            def test_function():
                pass
            """,
        )

    def test_import_freezegun(self):
        check_transformed(
            "import freezegun",
            "import time_machine",
        )

    def test_import_from_unrelated(self):
        check_noop(
            "from libfaketime import freeze_time",
        )

    def test_import_from_relative(self):
        check_noop(
            "from .freezegun import freeze_time",
        )

    def test_import_from_freezegun_aliased(self):
        check_transformed(
            "from freezegun import freeze_time as ft",
            "import time_machine",
        )

    def test_import_from_freezegun_aliased_used(self):
        check_transformed(
            """
            from freezegun import freeze_time as ft

            @ft("2023-01-01")
            def test_function():
                pass
            """,
            """
            import time_machine

            @time_machine.travel("2023-01-01", tick=False)
            def test_function():
                pass
            """,
        )

    def test_import_from_freezegun_aliased_used_with(self):
        check_transformed(
            """
            from freezegun import freeze_time as ft

            with ft("2023-01-01") as t:
                t.tick()
            """,
            """
            import time_machine

            with time_machine.travel("2023-01-01", tick=False) as t:
                t.shift(1)
            """,
        )

    def test_import_from_freezegun_multiple(self):
        check_transformed(
            "from freezegun import freeze_time, FakeDate",
            "import time_machine\nfrom freezegun import FakeDate",
        )

    def test_import_from_freezegun_multiple_aliased(self):
        check_transformed(
            "from freezegun import freeze_time, FakeDate as FD",
            "import time_machine\nfrom freezegun import FakeDate as FD",
        )

    def test_import_from_freezegun_multiple_only_aliased_freeze_time(self):
        check_transformed(
            "from freezegun import freeze_time as ft, FakeDate",
            "import time_machine\nfrom freezegun import FakeDate",
        )

    def test_import_from_freezegun_multiple_parenthesized(self):
        check_transformed(
            """\
            from freezegun import (
                freeze_time,
                FakeDate,
            )
            """,
            """\
            import time_machine
            from freezegun import FakeDate
            """,
        )

    def test_import_from_freezegun_multiple_indented(self):
        check_transformed(
            """\
            def f():
                from freezegun import freeze_time, FakeDate
            """,
            """\
            def f():
                import time_machine
                from freezegun import FakeDate
            """,
        )

    def test_import_from_freezegun_multiple_indented_not_first_statement(self):
        check_transformed(
            """\
            def f():
                x = 1
                from freezegun import freeze_time, FakeDate
            """,
            """\
            def f():
                x = 1
                import time_machine
                from freezegun import FakeDate
            """,
        )

    def test_import_from_freezegun_multiple_compound_statement(self):
        check_transformed(
            "if True: from freezegun import freeze_time, FakeDate\n",
            "if True: import time_machine\nfrom freezegun import FakeDate\n",
        )

    def test_import_from_freezegun_multiple_indented_after_dedent(self):
        check_transformed(
            """\
            def f():
                if True:
                    pass
                from freezegun import freeze_time, FakeDate
            """,
            """\
            def f():
                if True:
                    pass
                import time_machine
                from freezegun import FakeDate
            """,
        )

    def test_import_from_freezegun_multiple_used(self):
        check_transformed(
            """\
            from freezegun import freeze_time, FakeDate

            @freeze_time("2023-01-01")
            def test_function():
                pass
            """,
            """\
            import time_machine
            from freezegun import FakeDate

            @time_machine.travel("2023-01-01", tick=False)
            def test_function():
                pass
            """,
        )

    def test_fixture_factory_annotation(self):
        check_transformed(
            """
            from freezegun.api import FrozenDateTimeFactory

            def test_function(freezer: FrozenDateTimeFactory):
                freezer.move_to("2023-01-01")
            """,
            """
            from time_machine import TimeMachineFixture

            def test_function(time_machine: TimeMachineFixture):
                time_machine.move_to("2023-01-01", tick=False)
            """,
        )

    def test_fixture_factory_annotation_aliased(self):
        check_transformed(
            """
            from freezegun.api import FrozenDateTimeFactory as FDF

            def test_function(freezer: FDF):
                freezer.move_to("2023-01-01")
            """,
            """
            from time_machine import TimeMachineFixture

            def test_function(time_machine: TimeMachineFixture):
                time_machine.move_to("2023-01-01", tick=False)
            """,
        )

    def test_fixture_factory_annotation_helper(self):
        check_transformed(
            """
            from freezegun.api import FrozenDateTimeFactory

            def advance(freezer: FrozenDateTimeFactory, days: int):
                pass
            """,
            """
            from time_machine import TimeMachineFixture

            def advance(time_machine: TimeMachineFixture, days: int):
                pass
            """,
        )

    def test_fixture_factory_with_freeze_time_import(self):
        check_transformed(
            """
            from freezegun import freeze_time
            from freezegun.api import FrozenDateTimeFactory

            def test_function(freezer: FrozenDateTimeFactory):
                freezer.move_to("2023-01-01")

            @freeze_time("2023-06-01")
            def test_function2():
                pass
            """,
            """
            import time_machine
            from time_machine import TimeMachineFixture

            def test_function(time_machine: TimeMachineFixture):
                time_machine.move_to("2023-01-01", tick=False)

            @time_machine.travel("2023-06-01", tick=False)
            def test_function2():
                pass
            """,
        )

    def test_fixture_factory_unused(self):
        check_transformed(
            """
            from freezegun.api import FrozenDateTimeFactory

            x = 1
            """,
            """

            x = 1
            """,
        )

    def test_fixture_factory_function_local_kept(self):
        check_noop(
            """
            def test_function():
                from freezegun.api import FrozenDateTimeFactory
                return FrozenDateTimeFactory
            """,
            reports=[(4, 12, "FrozenDateTimeFactory usage not migrated")],
        )

    def test_fixture_factory_store_kept(self):
        check_transformed(
            """
            from freezegun import freeze_time, FrozenDateTimeFactory

            FrozenDateTimeFactory = None

            @freeze_time("2023-01-01")
            def test_function():
                pass
            """,
            """
            import time_machine
            from freezegun import FrozenDateTimeFactory

            FrozenDateTimeFactory = None

            @time_machine.travel("2023-01-01", tick=False)
            def test_function():
                pass
            """,
            reports=[(4, 1, "FrozenDateTimeFactory usage not migrated")],
        )

    def test_fixture_factory_fstring_kept(self):
        check_noop(
            """
            from freezegun import FrozenDateTimeFactory

            x = f"{FrozenDateTimeFactory} here"
            """,
            reports=[(4, 8, "FrozenDateTimeFactory usage not migrated")],
        )

    def test_fixture_factory_shadow_parameter_kept(self):
        check_noop(
            """
            from freezegun import FrozenDateTimeFactory

            def check(FrozenDateTimeFactory):
                return FrozenDateTimeFactory
            """,
            reports=[(5, 12, "FrozenDateTimeFactory usage not migrated")],
        )

    def test_fixture_factory_shadow_def_kept(self):
        check_noop(
            """
            from freezegun import FrozenDateTimeFactory

            def FrozenDateTimeFactory():
                pass

            x = FrozenDateTimeFactory()
            """,
            reports=[(7, 5, "FrozenDateTimeFactory usage not migrated")],
        )

    def test_fixture_factory_shadow_class_kept(self):
        check_noop(
            """
            from freezegun import FrozenDateTimeFactory

            class FrozenDateTimeFactory:
                pass
            """,
        )

    def test_fixture_factory_shadow_import_kept(self):
        check_noop(
            """
            from freezegun import FrozenDateTimeFactory
            from othermod import FrozenDateTimeFactory

            x: FrozenDateTimeFactory = None
            """,
            reports=[(5, 4, "FrozenDateTimeFactory usage not migrated")],
        )

    def test_fixture_factory_shadow_lambda_kept(self):
        check_noop(
            """
            from freezegun import FrozenDateTimeFactory

            f = lambda FrozenDateTimeFactory: FrozenDateTimeFactory
            """,
            reports=[(4, 35, "FrozenDateTimeFactory usage not migrated")],
        )

    def test_fixture_factory_function_local_import_module_carrier(self):
        check_transformed(
            """
            from freezegun import freeze_time

            @freeze_time("2023-01-01")
            def test_function():
                from freezegun.api import FrozenDateTimeFactory
                x: FrozenDateTimeFactory = None
            """,
            """
            import time_machine
            from time_machine import TimeMachineFixture

            @time_machine.travel("2023-01-01", tick=False)
            def test_function():
                x: TimeMachineFixture = None
            """,
        )

    def test_fixture_factory_import_in_try(self):
        check_transformed(
            """
            try:
                import zoneinfo
            except ImportError:
                pass

            from freezegun import FrozenDateTimeFactory

            x: FrozenDateTimeFactory = None
            """,
            """
            try:
                import zoneinfo
            except ImportError:
                pass

            from time_machine import TimeMachineFixture

            x: TimeMachineFixture = None
            """,
        )

    def test_fixture_factory_unused_removed_trailing_comment(self):
        check_transformed(
            """
            from freezegun.api import FrozenDateTimeFactory  # noqa

            x = 1
            """,
            """

            x = 1
            """,
        )

    def test_fixture_factory_unused_semicolon_before(self):
        check_transformed(
            """
            x = 1; from freezegun import FrozenDateTimeFactory

            y = 2
            """,
            """
            x = 1; pass

            y = 2
            """,
        )

    def test_fixture_factory_unused_only_statement_in_block(self):
        check_transformed(
            """
            if True: from freezegun.api import FrozenDateTimeFactory

            x = 1
            """,
            """
            if True: pass

            x = 1
            """,
        )

    def test_import_from_freezegun(self):
        check_transformed(
            "from freezegun import freeze_time",
            "import time_machine",
        )

    def test_import_from_freezegun_more(self):
        check_transformed(
            """
            from freezegun import freeze_time
            pass
            """,
            """
            import time_machine
            pass
            """,
        )

    def test_function_decorator_attr_unrelated(self):
        check_noop(
            """
            import libfaketime

            @libfaketime.freeze_time("2023-01-01")
            def test_function():
                pass
            """,
        )

    def test_function_decorator_attr_not_called(self):
        check_transformed(
            """
            import freezegun

            @freezegun.freeze_time
            def test_function():
                pass
            """,
            """
            import time_machine

            @freezegun.freeze_time
            def test_function():
                pass
            """,
            reports=[(4, 2, "freezegun usage not migrated")],
        )

    def test_function_decorator_attr(self):
        check_transformed(
            """
            import freezegun

            @freezegun.freeze_time("2023-01-01")
            def test_function():
                pass
            """,
            """
            import time_machine

            @time_machine.travel("2023-01-01", tick=False)
            def test_function():
                pass
            """,
        )

    def test_async_function_decorator_attr(self):
        check_transformed(
            """
            import freezegun

            @freezegun.freeze_time("2023-01-01")
            async def test_function():
                pass
            """,
            """
            import time_machine

            @time_machine.travel("2023-01-01", tick=False)
            async def test_function():
                pass
            """,
        )

    def test_function_decorator_attr_tick(self):
        check_transformed(
            """
            import freezegun

            @freezegun.freeze_time("2023-01-01", tick=True)
            def test_function():
                pass
            """,
            """
            import time_machine

            @time_machine.travel("2023-01-01", tick=True)
            def test_function():
                pass
            """,
        )

    def test_function_decorator_attr_tick_false(self):
        check_transformed(
            """
            import freezegun

            @freezegun.freeze_time("2023-01-01", tick=False)
            def test_function():
                pass
            """,
            """
            import time_machine

            @time_machine.travel("2023-01-01", tick=False)
            def test_function():
                pass
            """,
        )

    def test_function_decorator_no_arguments(self):
        check_transformed(
            """
            from freezegun import freeze_time

            @freeze_time()
            def test_function():
                pass
            """,
            """
            import time_machine

            @time_machine.travel(None, tick=False)
            def test_function():
                pass
            """,
        )

    def test_function_decorator_no_arguments_attr(self):
        check_transformed(
            """
            import freezegun

            @freezegun.freeze_time()
            def test_function():
                pass
            """,
            """
            import time_machine

            @time_machine.travel(None, tick=False)
            def test_function():
                pass
            """,
        )

    def test_function_decorator_no_arguments_tick(self):
        check_transformed(
            """
            from freezegun import freeze_time

            @freeze_time(tick=True)
            def test_function():
                pass
            """,
            """
            import time_machine

            @time_machine.travel(None, tick=True)
            def test_function():
                pass
            """,
        )

    def test_function_decorator_no_arguments_tz_offset_zero(self):
        check_transformed(
            """
            from freezegun import freeze_time

            @freeze_time(tz_offset=0)
            def test_function():
                pass
            """,
            """
            import time_machine

            @time_machine.travel(None, tick=False)
            def test_function():
                pass
            """,
        )

    def test_function_decorator_no_arguments_tz_offset_zero_trailing_comma(self):
        check_transformed(
            """
            from freezegun import freeze_time

            @freeze_time(tz_offset=0,)
            def test_function():
                pass
            """,
            """
            import time_machine

            @time_machine.travel(None, tick=False)
            def test_function():
                pass
            """,
        )

    def test_function_decorator_no_arguments_tz_offset_zero_before_tick(self):
        check_transformed(
            """
            from freezegun import freeze_time

            @freeze_time(tz_offset=0, tick=True)
            def test_function():
                pass
            """,
            """
            import time_machine

            @time_machine.travel(None, tick=True)
            def test_function():
                pass
            """,
        )

    def test_function_decorator_no_arguments_tz_offset_zero_after_tick(self):
        check_transformed(
            """
            from freezegun import freeze_time

            @freeze_time(tick=True, tz_offset=0)
            def test_function():
                pass
            """,
            """
            import time_machine

            @time_machine.travel(None, tick=True)
            def test_function():
                pass
            """,
        )

    def test_function_decorator_no_arguments_tz_offset_zero_spaced(self):
        check_transformed(
            """
            from freezegun import freeze_time

            @freeze_time( tz_offset=0 , tick=True )
            def test_function():
                pass
            """,
            """
            import time_machine

            @time_machine.travel( None, tick=True )
            def test_function():
                pass
            """,
        )

    def test_function_decorator_no_arguments_tz_offset_zero_only_spaced(self):
        check_transformed(
            """
            from freezegun import freeze_time

            @freeze_time( tz_offset=0 )
            def test_function():
                pass
            """,
            """
            import time_machine

            @time_machine.travel(None  , tick=False)
            def test_function():
                pass
            """,
        )

    def test_with_no_arguments(self):
        check_transformed(
            """
            from freezegun import freeze_time

            with freeze_time() as ft:
                ft.tick()
            """,
            """
            import time_machine

            with time_machine.travel(None, tick=False) as ft:
                ft.shift(1)
            """,
        )

    def test_marker_no_arguments(self):
        check_transformed(
            """
            import pytest

            @pytest.mark.freeze_time()
            def test_function():
                pass
            """,
            """
            import pytest

            @pytest.mark.time_machine(None, tick=False)
            def test_function():
                pass
            """,
        )

    def test_function_decorator_tz_offset_zero(self):
        check_transformed(
            """
            from freezegun import freeze_time

            @freeze_time("2023-01-01", tz_offset=0)
            def test_function():
                pass
            """,
            """
            import time_machine

            @time_machine.travel("2023-01-01", tick=False)
            def test_function():
                pass
            """,
        )

    def test_function_decorator_tz_offset_zero_float(self):
        check_transformed(
            """
            from freezegun import freeze_time

            @freeze_time("2023-01-01", tz_offset=0.0)
            def test_function():
                pass
            """,
            """
            import time_machine

            @time_machine.travel("2023-01-01", tick=False)
            def test_function():
                pass
            """,
        )

    def test_function_decorator_tz_offset_zero_before_tick(self):
        check_transformed(
            """
            from freezegun import freeze_time

            @freeze_time("2023-01-01", tz_offset=0, tick=True)
            def test_function():
                pass
            """,
            """
            import time_machine

            @time_machine.travel("2023-01-01", tick=True)
            def test_function():
                pass
            """,
        )

    def test_function_decorator_tz_offset_zero_after_tick(self):
        check_transformed(
            """
            from freezegun import freeze_time

            @freeze_time("2023-01-01", tick=True, tz_offset=0)
            def test_function():
                pass
            """,
            """
            import time_machine

            @time_machine.travel("2023-01-01", tick=True)
            def test_function():
                pass
            """,
        )

    def test_function_decorator_tz_offset_zero_trailing_comma(self):
        check_transformed(
            """
            from freezegun import freeze_time

            @freeze_time("2023-01-01", tz_offset=0,)
            def test_function():
                pass
            """,
            """
            import time_machine

            @time_machine.travel("2023-01-01", tick=False)
            def test_function():
                pass
            """,
        )

    def test_function_decorator_tz_offset_zero_multiline(self):
        check_transformed(
            """
            from freezegun import freeze_time

            @freeze_time(
                "2023-01-01",
                tz_offset=0,
            )
            def test_function():
                pass
            """,
            """
            import time_machine

            @time_machine.travel(
                "2023-01-01", tick=False
            )
            def test_function():
                pass
            """,
        )

    def test_function_decorator_tz_offset_nonzero(self):
        check_transformed(
            """
            from freezegun import freeze_time

            @freeze_time("2023-01-01", tz_offset=-4)
            def test_function():
                pass
            """,
            """
            import time_machine

            @freeze_time("2023-01-01", tz_offset=-4)
            def test_function():
                pass
            """,
            reports=[(4, 2, "freeze_time usage not migrated")],
        )

    def test_function_decorator_tz_offset_false(self):
        check_transformed(
            """
            from freezegun import freeze_time

            @freeze_time("2023-01-01", tz_offset=False)
            def test_function():
                pass
            """,
            """
            import time_machine

            @freeze_time("2023-01-01", tz_offset=False)
            def test_function():
                pass
            """,
            reports=[(4, 2, "freeze_time usage not migrated")],
        )

    def test_function_decorator_tz_offset_variable(self):
        check_transformed(
            """
            from freezegun import freeze_time

            @freeze_time("2023-01-01", tz_offset=offset)
            def test_function():
                pass
            """,
            """
            import time_machine

            @freeze_time("2023-01-01", tz_offset=offset)
            def test_function():
                pass
            """,
            reports=[(4, 2, "freeze_time usage not migrated")],
        )

    def test_function_decorator_real_asyncio_true(self):
        check_transformed(
            """
            from freezegun import freeze_time

            @freeze_time("2023-01-01", real_asyncio=True)
            async def test_function():
                pass
            """,
            """
            import time_machine

            @time_machine.travel("2023-01-01", tick=False)
            async def test_function():
                pass
            """,
        )

    def test_function_decorator_real_asyncio_false(self):
        check_transformed(
            """
            from freezegun import freeze_time

            @freeze_time("2023-01-01", real_asyncio=False)
            async def test_function():
                pass
            """,
            """
            import time_machine

            @time_machine.travel("2023-01-01", tick=False)
            async def test_function():
                pass
            """,
        )

    def test_function_decorator_real_asyncio_variable(self):
        check_transformed(
            """
            from freezegun import freeze_time

            @freeze_time("2023-01-01", real_asyncio=real_asyncio)
            async def test_function():
                pass
            """,
            """
            import time_machine

            @time_machine.travel("2023-01-01", tick=False)
            async def test_function():
                pass
            """,
        )

    def test_function_decorator_ignore(self):
        check_transformed(
            """
            from freezegun import freeze_time

            @freeze_time("2023-01-01", ignore=["threading"])
            def test_function():
                pass
            """,
            """
            import time_machine

            @time_machine.travel("2023-01-01", tick=False)
            def test_function():
                pass
            """,
        )

    def test_function_decorator_ignore_variable(self):
        check_transformed(
            """
            from freezegun import freeze_time

            @freeze_time("2023-01-01", ignore=IGNORED_MODULES, tick=True)
            def test_function():
                pass
            """,
            """
            import time_machine

            @time_machine.travel("2023-01-01", tick=True)
            def test_function():
                pass
            """,
        )

    def test_marker_ignore(self):
        check_transformed(
            """
            import pytest

            @pytest.mark.freeze_time("2023-01-01", ignore=["threading"])
            def test_function():
                pass
            """,
            """
            import pytest

            @pytest.mark.time_machine("2023-01-01", tick=False)
            def test_function():
                pass
            """,
        )

    def test_with_tz_offset_zero(self):
        check_transformed(
            """
            from freezegun import freeze_time

            with freeze_time("2023-01-01", tz_offset=0):
                pass
            """,
            """
            import time_machine

            with time_machine.travel("2023-01-01", tick=False):
                pass
            """,
        )

    def test_marker_tz_offset_zero(self):
        check_transformed(
            """
            import pytest

            @pytest.mark.freeze_time("2023-01-01", tz_offset=0)
            def test_function():
                pass
            """,
            """
            import pytest

            @pytest.mark.time_machine("2023-01-01", tick=False)
            def test_function():
                pass
            """,
        )

    def test_function_decorator_name_unrelated(self):
        check_noop(
            """
            from libfaketime import freeze_time

            @freeze_time("2023-01-01")
            def test_function():
                pass
            """,
        )

    def test_function_decorator_name_not_called(self):
        check_transformed(
            """
            from freezegun import freeze_time

            @freeze_time
            def test_function():
                pass
            """,
            """
            import time_machine

            @freeze_time
            def test_function():
                pass
            """,
            reports=[(4, 2, "freeze_time usage not migrated")],
        )

    def test_function_decorator_name(self):
        check_transformed(
            """
            from freezegun import freeze_time

            @freeze_time("2023-01-01")
            def test_function():
                pass
            """,
            """
            import time_machine

            @time_machine.travel("2023-01-01", tick=False)
            def test_function():
                pass
            """,
        )

    def test_function_decorator_name_trailing_comma(self):
        check_transformed(
            """
            from freezegun import freeze_time

            @freeze_time("2023-01-01",)
            def test_function():
                pass
            """,
            """
            import time_machine

            @time_machine.travel("2023-01-01", tick=False)
            def test_function():
                pass
            """,
        )

    def test_function_decorator_name_multiline(self):
        check_transformed(
            """
            from freezegun import freeze_time

            @freeze_time(
                "2023-01-01",
            )
            def test_function():
                pass
            """,
            """
            import time_machine

            @time_machine.travel(
                "2023-01-01", tick=False
            )
            def test_function():
                pass
            """,
        )

    def test_function_decorator_name_tick(self):
        check_transformed(
            """
            from freezegun import freeze_time

            @freeze_time("2023-01-01", tick=True)
            def test_function():
                pass
            """,
            """
            import time_machine

            @time_machine.travel("2023-01-01", tick=True)
            def test_function():
                pass
            """,
        )

    def test_async_function_decorator_name(self):
        check_transformed(
            """
            from freezegun import freeze_time

            @freeze_time("2023-01-01")
            async def test_function():
                pass
            """,
            """
            import time_machine

            @time_machine.travel("2023-01-01", tick=False)
            async def test_function():
                pass
            """,
        )

    def test_class_decorator_attr_unrelated(self):
        check_noop(
            """
            import libfaketime

            @libfaketime.freeze_time("2023-01-01")
            class TestClass:
                pass
            """,
        )

    def test_class_decorator_attr_not_called(self):
        check_transformed(
            """
            import freezegun

            @freezegun.freeze_time
            class TestClass:
                pass
            """,
            """
            import time_machine

            @freezegun.freeze_time
            class TestClass:
                pass
            """,
            reports=[(4, 2, "freezegun usage not migrated")],
        )

    def test_class_decorator_attr_not_unittest_class(self):
        check_transformed(
            """
            import freezegun

            @freezegun.freeze_time("2023-01-01")
            class TestClass:
                pass
            """,
            """
            import time_machine

            @freezegun.freeze_time("2023-01-01")
            class TestClass:
                pass
            """,
            reports=[(4, 2, "freezegun usage not migrated")],
        )

    def test_class_decorator_attr_unittest_class_base_name(self):
        check_transformed(
            """
            import freezegun
            from django.test import SimpleTestCase

            @freezegun.freeze_time("2023-01-01")
            class TestClass(SimpleTestCase):
                pass
            """,
            """
            import time_machine
            from django.test import SimpleTestCase

            @time_machine.travel("2023-01-01", tick=False)
            class TestClass(SimpleTestCase):
                pass
            """,
        )

    def test_class_decorator_attr_unittest_class_base_attr(self):
        check_transformed(
            """
            import freezegun
            import unittest

            @freezegun.freeze_time("2023-01-01")
            class TestClass(unittest.TestCase):
                pass
            """,
            """
            import time_machine
            import unittest

            @time_machine.travel("2023-01-01", tick=False)
            class TestClass(unittest.TestCase):
                pass
            """,
        )

    def test_class_decorator_attr_unittest_class_method(self):
        check_transformed(
            """
            import freezegun
            from testing import TestBase

            @freezegun.freeze_time("2023-01-01")
            class TestClass(TestBase):
                def setUp(self):
                    print("I look like a unittest class!")
            """,
            """
            import time_machine
            from testing import TestBase

            @time_machine.travel("2023-01-01", tick=False)
            class TestClass(TestBase):
                def setUp(self):
                    print("I look like a unittest class!")
            """,
        )

    def test_class_decorator_attr_unittest_class_async_method(self):
        check_transformed(
            """
            import freezegun
            from testing import TestBase

            @freezegun.freeze_time("2023-01-01")
            class TestClass(TestBase):
                async def asyncSetUp(self):
                    print("I look like a unittest class!")
            """,
            """
            import time_machine
            from testing import TestBase

            @time_machine.travel("2023-01-01", tick=False)
            class TestClass(TestBase):
                async def asyncSetUp(self):
                    print("I look like a unittest class!")
            """,
        )

    def test_class_decorator_attr_multiple(self):
        check_transformed(
            """
            import freezegun
            from testing import TestBase
            from unittest import mock

            @freezegun.freeze_time("2023-01-01")
            @mock.patch("example.connect")
            class TestClass(TestBase):
                def setUp(self):
                    print("I look like a unittest class!")
            """,
            """
            import time_machine
            from testing import TestBase
            from unittest import mock

            @time_machine.travel("2023-01-01", tick=False)
            @mock.patch("example.connect")
            class TestClass(TestBase):
                def setUp(self):
                    print("I look like a unittest class!")
            """,
        )

    def test_class_decorator_attr_unittest_class_base_name_tick(self):
        check_transformed(
            """
            import freezegun
            from django.test import SimpleTestCase

            @freezegun.freeze_time("2023-01-01", tick=True)
            class TestClass(SimpleTestCase):
                pass
            """,
            """
            import time_machine
            from django.test import SimpleTestCase

            @time_machine.travel("2023-01-01", tick=True)
            class TestClass(SimpleTestCase):
                pass
            """,
        )

    def test_class_decorator_name_unrelated(self):
        check_noop(
            """
            from libfaketime import freeze_time

            @freeze_time("2023-01-01")
            class TestClass:
                pass
            """,
        )

    def test_class_decorator_name_not_called(self):
        check_transformed(
            """
            from freezegun import freeze_time

            @freeze_time
            class TestClass:
                pass
            """,
            """
            import time_machine

            @freeze_time
            class TestClass:
                pass
            """,
            reports=[(4, 2, "freeze_time usage not migrated")],
        )

    def test_class_decorator_name_not_unittest_class(self):
        check_transformed(
            """
            from freezegun import freeze_time

            @freeze_time("2023-01-01")
            class TestClass:
                pass
            """,
            """
            import time_machine

            @freeze_time("2023-01-01")
            class TestClass:
                pass
            """,
            reports=[(4, 2, "freeze_time usage not migrated")],
        )

    def test_class_decorator_name_unittest_class_base_name(self):
        check_transformed(
            """
            from freezegun import freeze_time
            from django.test import SimpleTestCase

            @freeze_time("2023-01-01")
            class TestClass(SimpleTestCase):
                pass
            """,
            """
            import time_machine
            from django.test import SimpleTestCase

            @time_machine.travel("2023-01-01", tick=False)
            class TestClass(SimpleTestCase):
                pass
            """,
        )

    def test_class_decorator_name_unittest_class_base_attr(self):
        check_transformed(
            """
            from freezegun import freeze_time
            import unittest

            @freeze_time("2023-01-01")
            class TestClass(unittest.TestCase):
                pass
            """,
            """
            import time_machine
            import unittest

            @time_machine.travel("2023-01-01", tick=False)
            class TestClass(unittest.TestCase):
                pass
            """,
        )

    def test_class_decorator_name_unittest_class_method(self):
        check_transformed(
            """
            from freezegun import freeze_time
            from testing import TestBase

            @freeze_time("2023-01-01")
            class TestClass(TestBase):
                def setUp(self):
                    print("I look like a unittest class!")
            """,
            """
            import time_machine
            from testing import TestBase

            @time_machine.travel("2023-01-01", tick=False)
            class TestClass(TestBase):
                def setUp(self):
                    print("I look like a unittest class!")
            """,
        )

    def test_class_decorator_name_unittest_class_uses_assert_method(self):
        check_transformed(
            """
            from freezegun import freeze_time
            from testing import TestBase

            @freeze_time("2023-01-01")
            class TestClass(TestBase):
                def test_something(self):
                    self.assertTrue(True)
            """,
            """
            import time_machine
            from testing import TestBase

            @time_machine.travel("2023-01-01", tick=False)
            class TestClass(TestBase):
                def test_something(self):
                    self.assertTrue(True)
            """,
        )

    def test_with_attr_unrelated(self):
        check_noop(
            """
            import libfaketime

            with libfaketime.freeze_time("2023-01-01"):
                pass
            """,
        )

    def test_with_attr_not_called(self):
        check_transformed(
            """
            import freezegun

            with freezegun.freeze_time:
                pass
            """,
            """
            import time_machine

            with freezegun.freeze_time:
                pass
            """,
            reports=[(4, 6, "freezegun usage not migrated")],
        )

    def test_with_attr_as(self):
        check_transformed(
            """
            import freezegun

            with freezegun.freeze_time("2023-01-01") as ft:
                pass
            """,
            """
            import time_machine

            with time_machine.travel("2023-01-01", tick=False) as ft:
                pass
            """,
        )

    def test_with_attr(self):
        check_transformed(
            """
            import freezegun

            with freezegun.freeze_time("2023-01-01"):
                pass
            """,
            """
            import time_machine

            with time_machine.travel("2023-01-01", tick=False):
                pass
            """,
        )

    def test_with_attr_tick(self):
        check_transformed(
            """
            import freezegun

            with freezegun.freeze_time("2023-01-01", tick=True):
                pass
            """,
            """
            import time_machine

            with time_machine.travel("2023-01-01", tick=True):
                pass
            """,
        )

    def test_with_name_unrelated(self):
        check_noop(
            """
            from libfaketime import freeze_time

            with freeze_time("2023-01-01"):
                pass
            """,
        )

    def test_with_name_not_called(self):
        check_transformed(
            """
            from freezegun import freeze_time

            with freeze_time:
                pass
            """,
            """
            import time_machine

            with freeze_time:
                pass
            """,
            reports=[(4, 6, "freeze_time usage not migrated")],
        )

    def test_with_name_as(self):
        check_transformed(
            """
            from freezegun import freeze_time

            with freeze_time("2023-01-01") as ft:
                pass
            """,
            """
            import time_machine

            with time_machine.travel("2023-01-01", tick=False) as ft:
                pass
            """,
        )

    def test_with_name(self):
        check_transformed(
            """
            from freezegun import freeze_time

            with freeze_time("2023-01-01"):
                pass
            """,
            """
            import time_machine

            with time_machine.travel("2023-01-01", tick=False):
                pass
            """,
        )

    def test_with_as_move_to(self):
        check_transformed(
            """
            from freezegun import freeze_time

            with freeze_time("2023-01-01") as ft:
                ft.move_to("2023-06-01")
            """,
            """
            import time_machine

            with time_machine.travel("2023-01-01", tick=False) as ft:
                ft.move_to("2023-06-01")
            """,
        )

    def test_with_as_attribute_target(self):
        check_transformed(
            """
            from freezegun import freeze_time

            with freeze_time("2023-01-01") as obj.ft:
                pass
            """,
            """
            import time_machine

            with freeze_time("2023-01-01") as obj.ft:
                pass
            """,
            reports=[(4, 6, "freeze_time usage not migrated")],
        )

    def test_with_as_tick(self):
        check_transformed(
            """
            from freezegun import freeze_time

            with freeze_time("2023-01-01") as ft:
                ft.tick()
            """,
            """
            import time_machine

            with time_machine.travel("2023-01-01", tick=False) as ft:
                ft.shift(1)
            """,
        )

    def test_with_as_tick_arguments(self):
        check_transformed(
            """
            from datetime import timedelta
            from freezegun import freeze_time

            with freeze_time("2023-01-01") as ft:
                ft.tick(10.0)
                ft.tick(timedelta(seconds=100))
                ft.tick(delta=timedelta(seconds=100))
            """,
            """
            from datetime import timedelta
            import time_machine

            with time_machine.travel("2023-01-01", tick=False) as ft:
                ft.shift(10.0)
                ft.shift(timedelta(seconds=100))
                ft.shift(delta=timedelta(seconds=100))
            """,
        )

    def test_with_as_tick_too_many_arguments(self):
        check_transformed(
            """
            from freezegun import freeze_time

            with freeze_time("2023-01-01") as ft:
                ft.tick(1, 2)
            """,
            """
            import time_machine

            with time_machine.travel("2023-01-01", tick=False) as ft:
                ft.tick(1, 2)
            """,
        )

    def test_with_as_tick_other_name(self):
        check_transformed(
            """
            from freezegun import freeze_time

            with freeze_time("2023-01-01") as ft:
                other.tick()
            """,
            """
            import time_machine

            with time_machine.travel("2023-01-01", tick=False) as ft:
                other.tick()
            """,
        )

    def test_with_as_tick_outside_block(self):
        check_transformed(
            """
            from freezegun import freeze_time

            with freeze_time("2023-01-01") as ft:
                pass
            ft.tick()
            """,
            """
            import time_machine

            with time_machine.travel("2023-01-01", tick=False) as ft:
                pass
            ft.tick()
            """,
        )

    def test_with_as_tick_assigned(self):
        check_transformed(
            """
            from freezegun import freeze_time

            with freeze_time("2023-01-01") as ft:
                now = ft.tick()
            """,
            """
            import time_machine

            with freeze_time("2023-01-01") as ft:
                now = ft.tick()
            """,
            reports=[(4, 6, "freeze_time usage not migrated")],
        )

    def test_with_as_incompatible_attribute(self):
        check_transformed(
            """
            from freezegun import freeze_time

            with freeze_time("2023-01-01") as ft:
                assert ft.time_to_freeze.year == 2023
            """,
            """
            import time_machine

            with freeze_time("2023-01-01") as ft:
                assert ft.time_to_freeze.year == 2023
            """,
            reports=[(4, 6, "freeze_time usage not migrated")],
        )

    def test_with_as_incompatible_reference(self):
        check_transformed(
            """
            from freezegun import freeze_time

            with freeze_time("2023-01-01") as ft:
                helper(ft)
            """,
            """
            import time_machine

            with freeze_time("2023-01-01") as ft:
                helper(ft)
            """,
            reports=[(4, 6, "freeze_time usage not migrated")],
        )

    def test_with_as_unmigratable_call(self):
        check_transformed(
            """
            from freezegun import freeze_time

            with freeze_time("2023-01-01", auto_tick_seconds=1) as ft:
                ft.tick()
            """,
            """
            import time_machine

            with freeze_time("2023-01-01", auto_tick_seconds=1) as ft:
                ft.tick()
            """,
            reports=[(4, 6, "freeze_time usage not migrated")],
        )

    def test_assign_start_stop(self):
        check_transformed(
            """
            from freezegun import freeze_time

            def test_function():
                freezer = freeze_time("2023-01-01")
                freezer.start()
                freezer.stop()
            """,
            """
            import time_machine

            def test_function():
                freezer = time_machine.travel("2023-01-01", tick=False)
                freezer.start()
                freezer.stop()
            """,
        )

    def test_assign_start_stop_module_level(self):
        check_transformed(
            """
            from freezegun import freeze_time

            freezer = freeze_time("2023-01-01")
            freezer.start()
            freezer.stop()
            """,
            """
            import time_machine

            freezer = time_machine.travel("2023-01-01", tick=False)
            freezer.start()
            freezer.stop()
            """,
        )

    def test_assign_start_stop_attr_call(self):
        check_transformed(
            """
            import freezegun

            def test_function():
                freezer = freezegun.freeze_time("2023-01-01")
                freezer.start()
                freezer.stop()
            """,
            """
            import time_machine

            def test_function():
                freezer = time_machine.travel("2023-01-01", tick=False)
                freezer.start()
                freezer.stop()
            """,
        )

    def test_assign_start_stop_tick(self):
        check_transformed(
            """
            from freezegun import freeze_time

            def test_function():
                freezer = freeze_time("2023-01-01", tick=True)
                freezer.start()
                freezer.stop()
            """,
            """
            import time_machine

            def test_function():
                freezer = time_machine.travel("2023-01-01", tick=True)
                freezer.start()
                freezer.stop()
            """,
        )

    def test_assign_stop_reference(self):
        check_transformed(
            """
            from freezegun import freeze_time

            def test_function():
                freezer = freeze_time("2023-01-01")
                freezer.start()
                atexit.register(freezer.stop)
            """,
            """
            import time_machine

            def test_function():
                freezer = time_machine.travel("2023-01-01", tick=False)
                freezer.start()
                atexit.register(freezer.stop)
            """,
        )

    def test_assign_start_arguments_incompatible(self):
        check_transformed(
            """
            from freezegun import freeze_time

            def test_function():
                freezer = freeze_time("2023-01-01")
                freezer.start(1)
            """,
            """
            import time_machine

            def test_function():
                freezer = freeze_time("2023-01-01")
                freezer.start(1)
            """,
            reports=[(5, 15, "freeze_time usage not migrated")],
        )

    def test_assign_start_assigned_incompatible(self):
        check_transformed(
            """
            from freezegun import freeze_time

            def test_function():
                freezer = freeze_time("2023-01-01")
                x = freezer.start()
            """,
            """
            import time_machine

            def test_function():
                freezer = freeze_time("2023-01-01")
                x = freezer.start()
            """,
            reports=[(5, 15, "freeze_time usage not migrated")],
        )

    def test_assign_move_to_incompatible(self):
        check_transformed(
            """
            from freezegun import freeze_time

            def test_function():
                freezer = freeze_time("2023-01-01")
                freezer.start()
                freezer.move_to("2023-06-01")
                freezer.stop()
            """,
            """
            import time_machine

            def test_function():
                freezer = freeze_time("2023-01-01")
                freezer.start()
                freezer.move_to("2023-06-01")
                freezer.stop()
            """,
            reports=[(5, 15, "freeze_time usage not migrated")],
        )

    def test_assign_reference_incompatible(self):
        check_transformed(
            """
            from freezegun import freeze_time

            def test_function():
                freezer = freeze_time("2023-01-01")
                helper(freezer)
            """,
            """
            import time_machine

            def test_function():
                freezer = freeze_time("2023-01-01")
                helper(freezer)
            """,
            reports=[(5, 15, "freeze_time usage not migrated")],
        )

    def test_assign_reassigned_incompatible(self):
        check_transformed(
            """
            from freezegun import freeze_time

            def test_function():
                freezer = freeze_time("2023-01-01")
                freezer.start()
                freezer = freeze_time("2024-01-01")
                freezer.stop()
            """,
            """
            import time_machine

            def test_function():
                freezer = freeze_time("2023-01-01")
                freezer.start()
                freezer = freeze_time("2024-01-01")
                freezer.stop()
            """,
            reports=[
                (5, 15, "freeze_time usage not migrated"),
                (7, 15, "freeze_time usage not migrated"),
            ],
        )

    def test_assign_unmigratable_call(self):
        check_transformed(
            """
            from freezegun import freeze_time

            def test_function():
                freezer = freeze_time("2023-01-01", auto_tick_seconds=1)
                freezer.start()
                freezer.stop()
            """,
            """
            import time_machine

            def test_function():
                freezer = freeze_time("2023-01-01", auto_tick_seconds=1)
                freezer.start()
                freezer.stop()
            """,
            reports=[(5, 15, "freeze_time usage not migrated")],
        )

    def test_assign_other_call_noop(self):
        check_noop(
            """
            def test_function():
                freezer = make_freezer("2023-01-01")
                freezer.start()
            """,
        )

    def test_assign_class_body_noop(self):
        check_transformed(
            """
            from freezegun import freeze_time

            class TestSomething:
                freezer = freeze_time("2023-01-01")
            """,
            """
            import time_machine

            class TestSomething:
                freezer = freeze_time("2023-01-01")
            """,
            reports=[(5, 15, "freeze_time usage not migrated")],
        )

    def test_assign_self_attr(self):
        check_transformed(
            """
            from freezegun import freeze_time

            class TestSomething(TestCase):
                def setUp(self):
                    self.freezer = freeze_time("2023-01-01")
                    self.freezer.start()
                    self.addCleanup(self.freezer.stop)
            """,
            """
            import time_machine

            class TestSomething(TestCase):
                def setUp(self):
                    self.freezer = time_machine.travel("2023-01-01", tick=False)
                    self.freezer.start()
                    self.addCleanup(self.freezer.stop)
            """,
        )

    def test_assign_self_attr_teardown(self):
        check_transformed(
            """
            from freezegun import freeze_time

            class TestSomething(TestCase):
                def setUp(self):
                    self.freezer = freeze_time("2023-01-01")
                    self.freezer.start()

                def tearDown(self):
                    self.freezer.stop()
            """,
            """
            import time_machine

            class TestSomething(TestCase):
                def setUp(self):
                    self.freezer = time_machine.travel("2023-01-01", tick=False)
                    self.freezer.start()

                def tearDown(self):
                    self.freezer.stop()
            """,
        )

    def test_assign_self_attr_incompatible(self):
        check_transformed(
            """
            from freezegun import freeze_time

            class TestSomething(TestCase):
                def setUp(self):
                    self.freezer = freeze_time("2023-01-01")
                    self.freezer.start()

                def test_function(self):
                    self.freezer.tick()
            """,
            """
            import time_machine

            class TestSomething(TestCase):
                def setUp(self):
                    self.freezer = freeze_time("2023-01-01")
                    self.freezer.start()

                def test_function(self):
                    self.freezer.tick()
            """,
            reports=[(6, 24, "freeze_time usage not migrated")],
        )

    def test_assign_self_attr_outside_class(self):
        check_transformed(
            """
            from freezegun import freeze_time

            def helper(self):
                self.freezer = freeze_time("2023-01-01")
            """,
            """
            import time_machine

            def helper(self):
                self.freezer = freeze_time("2023-01-01")
            """,
            reports=[(5, 20, "freeze_time usage not migrated")],
        )

    def test_marker(self):
        check_transformed(
            """
            import pytest

            @pytest.mark.freeze_time("2023-01-01")
            def test_function():
                pass
            """,
            """
            import pytest

            @pytest.mark.time_machine("2023-01-01", tick=False)
            def test_function():
                pass
            """,
        )

    def test_marker_async_function(self):
        check_transformed(
            """
            import pytest

            @pytest.mark.freeze_time("2023-01-01")
            async def test_function():
                pass
            """,
            """
            import pytest

            @pytest.mark.time_machine("2023-01-01", tick=False)
            async def test_function():
                pass
            """,
        )

    def test_marker_tick(self):
        check_transformed(
            """
            import pytest

            @pytest.mark.freeze_time("2023-01-01", tick=True)
            def test_function():
                pass
            """,
            """
            import pytest

            @pytest.mark.time_machine("2023-01-01", tick=True)
            def test_function():
                pass
            """,
        )

    def test_marker_not_called(self):
        check_noop(
            """
            import pytest

            @pytest.mark.freeze_time
            def test_function():
                pass
            """,
            reports=[(4, 2, "pytest.mark.freeze_time usage not migrated")],
        )

    def test_marker_unmigratable_call(self):
        check_noop(
            """
            import pytest

            @pytest.mark.freeze_time("2023-01-01", auto_tick_seconds=1)
            def test_function():
                pass
            """,
            reports=[(4, 2, "pytest.mark.freeze_time usage not migrated")],
        )

    def test_marker_unrelated(self):
        check_noop(
            """
            import pytest

            @pytest.mark.slow_time("2023-01-01")
            def test_function():
                pass
            """,
        )

    def test_marker_class(self):
        check_transformed(
            """
            import pytest

            @pytest.mark.freeze_time("2023-01-01")
            class TestSomething:
                def test_function(self):
                    pass
            """,
            """
            import pytest

            @pytest.mark.time_machine("2023-01-01", tick=False)
            class TestSomething:
                def test_function(self):
                    pass
            """,
        )

    def test_pytestmark_module(self):
        check_transformed(
            """
            import pytest

            pytestmark = pytest.mark.freeze_time("2023-01-01")
            """,
            """
            import pytest

            pytestmark = pytest.mark.time_machine("2023-01-01", tick=False)
            """,
        )

    def test_pytestmark_module_tick(self):
        check_transformed(
            """
            import pytest

            pytestmark = pytest.mark.freeze_time("2023-01-01", tick=True)
            """,
            """
            import pytest

            pytestmark = pytest.mark.time_machine("2023-01-01", tick=True)
            """,
        )

    def test_pytestmark_module_list(self):
        check_transformed(
            """
            import pytest

            pytestmark = [
                pytest.mark.freeze_time("2023-01-01"),
                pytest.mark.django_db,
            ]
            """,
            """
            import pytest

            pytestmark = [
                pytest.mark.time_machine("2023-01-01", tick=False),
                pytest.mark.django_db,
            ]
            """,
        )

    def test_pytestmark_module_tuple(self):
        check_transformed(
            """
            import pytest

            pytestmark = (pytest.mark.freeze_time("2023-01-01"),)
            """,
            """
            import pytest

            pytestmark = (pytest.mark.time_machine("2023-01-01", tick=False),)
            """,
        )

    def test_pytestmark_module_unrelated_marker(self):
        check_noop(
            """
            import pytest

            pytestmark = pytest.mark.django_db()
            """,
        )

    def test_pytestmark_module_not_called(self):
        check_noop(
            """
            import pytest

            pytestmark = pytest.mark.freeze_time
            """,
            reports=[(4, 14, "pytest.mark.freeze_time usage not migrated")],
        )

    def test_pytestmark_module_other_value(self):
        check_noop(
            """
            pytestmark = marks
            """,
        )

    def test_pytestmark_class(self):
        check_transformed(
            """
            import pytest

            class TestSomething:
                pytestmark = pytest.mark.freeze_time("2023-01-01")
            """,
            """
            import pytest

            class TestSomething:
                pytestmark = pytest.mark.time_machine("2023-01-01", tick=False)
            """,
        )

    def test_pytestmark_module_freezer_fixture(self):
        check_transformed(
            """
            import pytest

            pytestmark = pytest.mark.freeze_time("2000-01-01")

            def test_function(freezer):
                freezer.move_to("2023-01-01")
            """,
            """
            import pytest

            pytestmark = pytest.mark.time_machine("2000-01-01", tick=False)

            def test_function(time_machine):
                time_machine.move_to("2023-01-01")
            """,
        )

    def test_pytestmark_module_freezer_fixture_defined_after(self):
        check_transformed(
            """
            import pytest

            def test_function(freezer):
                freezer.move_to("2023-01-01")

            pytestmark = pytest.mark.freeze_time("2000-01-01")
            """,
            """
            import pytest

            def test_function(time_machine):
                time_machine.move_to("2023-01-01")

            pytestmark = pytest.mark.time_machine("2000-01-01", tick=False)
            """,
        )

    def test_pytestmark_class_freezer_fixture(self):
        check_transformed(
            """
            import pytest

            class TestSomething:
                pytestmark = [pytest.mark.freeze_time("2000-01-01")]

                def test_function(self, freezer):
                    freezer.move_to("2023-01-01")
            """,
            """
            import pytest

            class TestSomething:
                pytestmark = [pytest.mark.time_machine("2000-01-01", tick=False)]

                def test_function(self, time_machine):
                    time_machine.move_to("2023-01-01")
            """,
        )

    def test_reports_import_multiple(self):
        check_noop(
            """
            import freezegun, os

            @freezegun.freeze_time("2023-01-01")
            def test_function():
                pass
            """,
            reports=[(4, 2, "freezegun usage not migrated")],
        )

    def test_reports_import_dotted(self):
        check_noop(
            """
            import freezegun.config

            freezegun.config.configure(extend_ignore_list=["tensorflow"])
            """,
            reports=[(4, 1, "freezegun usage not migrated")],
        )

    def test_reports_import_dotted_aliased(self):
        check_noop(
            """
            import freezegun.api as fg_api

            x = fg_api.FakeDatetime(2020, 1, 1)
            """,
            reports=[(4, 5, "fg_api usage not migrated")],
        )

    def test_reports_sorted(self):
        check_transformed(
            """
            import freezegun

            @freezegun.freeze_time
            def test_one():
                pass

            def test_two():
                with freezegun.freeze_time("2023-01-01") as ft:
                    helper(ft)
            """,
            """
            import time_machine

            @freezegun.freeze_time
            def test_one():
                pass

            def test_two():
                with freezegun.freeze_time("2023-01-01") as ft:
                    helper(ft)
            """,
            reports=[
                (4, 2, "freezegun usage not migrated"),
                (9, 10, "freezegun usage not migrated"),
            ],
        )

    def test_freezer_fixture(self):
        check_transformed(
            """
            def test_function(freezer):
                freezer.move_to("2023-01-01")
            """,
            """
            def test_function(time_machine):
                time_machine.move_to("2023-01-01", tick=False)
            """,
        )

    def test_freezer_fixture_async_function(self):
        check_transformed(
            """
            async def test_function(freezer):
                freezer.move_to("2023-01-01")
            """,
            """
            async def test_function(time_machine):
                time_machine.move_to("2023-01-01", tick=False)
            """,
        )

    def test_freezer_fixture_keyword_only(self):
        check_transformed(
            """
            def test_function(*, freezer):
                freezer.move_to("2023-01-01")
            """,
            """
            def test_function(*, time_machine):
                time_machine.move_to("2023-01-01", tick=False)
            """,
        )

    def test_freezer_fixture_move_to_extra_arguments(self):
        check_transformed(
            """
            def test_function(freezer):
                freezer.move_to("2023-01-01", "2024-01-01")
            """,
            """
            def test_function(time_machine):
                freezer.move_to("2023-01-01", "2024-01-01")
            """,
        )

    def test_freezer_fixture_parenthesized_receiver(self):
        check_transformed(
            """
            def test_function(freezer):
                (freezer).move_to("2023-01-01")
                (freezer).tick()
            """,
            """
            def test_function(time_machine):
                (time_machine).move_to("2023-01-01", tick=False)
                (time_machine).shift(1)
            """,
        )

    def test_with_as_tick_parenthesized_receiver(self):
        check_transformed(
            """
            from freezegun import freeze_time

            with freeze_time("2023-01-01") as tick:
                (tick).tick()
            """,
            """
            import time_machine

            with time_machine.travel("2023-01-01", tick=False) as tick:
                (tick).shift(1)
            """,
        )

    def test_freezer_fixture_other_method(self):
        check_transformed(
            """
            def test_function(freezer):
                freezer.move_to("2023-01-01")
                freezer.start()
            """,
            """
            def test_function(time_machine):
                time_machine.move_to("2023-01-01", tick=False)
                freezer.start()
            """,
        )

    def test_freezer_fixture_tick(self):
        check_transformed(
            """
            from datetime import timedelta

            def test_function(freezer):
                freezer.tick()
                freezer.tick(10.0)
                freezer.tick(100)
                freezer.tick(timedelta(seconds=100))
                freezer.tick(delta=timedelta(seconds=100))
            """,
            """
            from datetime import timedelta

            def test_function(time_machine):
                time_machine.shift(1)
                time_machine.shift(10.0)
                time_machine.shift(100)
                time_machine.shift(timedelta(seconds=100))
                time_machine.shift(delta=timedelta(seconds=100))
            """,
        )

    def test_freezer_fixture_tick_assigned(self):
        check_transformed(
            """
            def test_function(freezer):
                now = freezer.tick()
            """,
            """
            def test_function(time_machine):
                now = freezer.tick()
            """,
        )

    def test_freezer_fixture_move_to_assigned(self):
        check_transformed(
            """
            def test_function(freezer):
                result = freezer.move_to("2023-01-01")
            """,
            """
            def test_function(time_machine):
                result = time_machine.move_to("2023-01-01", tick=False)
            """,
        )

    def test_freezer_fixture_shadowed_freeze_time(self):
        check_transformed(
            """
            from freezegun import freeze_time

            def test_function(freezer):
                freezer.move_to("2023-01-01")
                with freeze_time("2024-01-01"):
                    pass
            """,
            """
            import time_machine

            def test_function(time_machine):
                time_machine.move_to("2023-01-01", tick=False)
                with freeze_time("2024-01-01"):
                    pass
            """,
            reports=[(6, 10, "freeze_time usage not migrated")],
        )

    def test_freezer_fixture_no_argument_noop(self):
        check_noop(
            """
            def test_function():
                freezer.move_to("2023-01-01")
            """,
        )

    def test_freezer_fixture_module_level_noop(self):
        check_noop(
            """
            freezer.move_to("2023-01-01")
            """,
        )

    def test_freezer_fixture_with_marker(self):
        check_transformed(
            """
            import pytest

            @pytest.mark.freeze_time("2000-01-01")
            def test_function(freezer):
                freezer.move_to("2023-01-01")
            """,
            """
            import pytest

            @pytest.mark.time_machine("2000-01-01", tick=False)
            def test_function(time_machine):
                time_machine.move_to("2023-01-01")
            """,
        )

    def test_freezer_fixture_with_marker_tick(self):
        check_transformed(
            """
            import pytest

            @pytest.mark.freeze_time("2000-01-01", tick=True)
            def test_function(freezer):
                freezer.move_to("2023-01-01")
            """,
            """
            import pytest

            @pytest.mark.time_machine("2000-01-01", tick=True)
            def test_function(time_machine):
                time_machine.move_to("2023-01-01")
            """,
        )

    def test_freezer_fixture_with_class_marker(self):
        check_transformed(
            """
            import pytest

            @pytest.mark.freeze_time("2000-01-01")
            class TestSomething:
                def test_function(self, freezer):
                    freezer.move_to("2023-01-01")
            """,
            """
            import pytest

            @pytest.mark.time_machine("2000-01-01", tick=False)
            class TestSomething:
                def test_function(self, time_machine):
                    time_machine.move_to("2023-01-01")
            """,
        )

    def test_freezer_fixture_with_decorator(self):
        check_transformed(
            """
            import freezegun

            @freezegun.freeze_time("2000-01-01")
            def test_function(freezer):
                freezer.move_to("2023-01-01")
            """,
            """
            import time_machine

            @time_machine.travel("2000-01-01", tick=False)
            def test_function(time_machine):
                time_machine.move_to("2023-01-01", tick=False)
            """,
        )

    def test_freezer_fixture_mix(self):
        check_transformed(
            """
            import freezegun
            import pytest

            def test_function():
                with freezegun.freeze_time("2000-01-01") as t:
                    t.move_to("2023-01-01")
                    t.tick()

            @pytest.mark.freeze_time("2000-01-01")
            def test_function2(freezer):
                freezer.move_to("2023-01-01")
                freezer.tick()
            """,
            """
            import time_machine
            import pytest

            def test_function():
                with time_machine.travel("2000-01-01", tick=False) as t:
                    t.move_to("2023-01-01")
                    t.shift(1)

            @pytest.mark.time_machine("2000-01-01", tick=False)
            def test_function2(time_machine):
                time_machine.move_to("2023-01-01")
                time_machine.shift(1)
            """,
        )
