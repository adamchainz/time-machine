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
        assert err == ""

        assert path.read_text() == "def def def\n"

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


def check_noop(given: str) -> None:
    given = dedent(given)
    result = migrate_contents(given)
    assert result == given


def check_transformed(given: str, expected: str) -> None:
    given = dedent(given)
    expected = dedent(expected)
    result = migrate_contents(given)
    assert result == expected


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
        )

    def test_marker_unmigratable_call(self):
        check_noop(
            """
            import pytest

            @pytest.mark.freeze_time("2023-01-01", auto_tick_seconds=1)
            def test_function():
                pass
            """,
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
