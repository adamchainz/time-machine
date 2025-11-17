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

    def test_main_help(
        self,
    ):
        with pytest.raises(SystemExit) as excinfo:
            main(["--help"])

        assert excinfo.value.code == 0

    def test_main_help_subprocess(
        self,
    ):
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
        check_noop(
            "import freezegun as fg",
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

    def test_import_from_freezegun_aliased(self):
        check_noop(
            "from freezegun import freeze_time as ft",
        )

    def test_import_from_freezegun_multiple(self):
        check_noop(
            "from freezegun import freeze_time, FakeDate",
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

            with freezegun.freeze_time("2023-01-01") as ft:
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

            with freeze_time("2023-01-01") as ft:
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

    def test_freezer_decorator(self):
        check_transformed(
            """
            import pytest

            @pytest.mark.freeze_time("2000-01-01")
            def test_function():
                pass
            """,
            """
            import pytest

            @pytest.mark.time_machine("2000-01-01", tick=False)
            def test_function():
                pass
            """,
        )

    def test_freezer_tick(self):
        check_transformed(
            """
            from datetime import timedelta
            import pytest

            @pytest.mark.freeze_time("2000-01-01")
            def test_function(freezer):
                freezer.tick()
                freezer.tick(10.0)
                freezer.tick(100)
                freezer.tick(timedelta(seconds=100))
                freezer.tick(delta=timedelta(seconds=100))
            """,
            """
            from datetime import timedelta
            import pytest

            @pytest.mark.time_machine("2000-01-01", tick=False)
            def test_function(time_machine):
                time_machine.shift(1)
                time_machine.shift(10.0)
                time_machine.shift(100)
                time_machine.shift(timedelta(seconds=100))
                time_machine.shift(delta=timedelta(seconds=100))
            """,
        )

    def test_freezer_decorator_and_fixture(self):
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
                time_machine.move_to("2023-01-01", tick=False)
            """,
        )

    def test_freezegun_freezer_decorator_and_fixture_mix(self):
        check_transformed(
            """
            import freezegun
            import pytest

            @freezegun.freeze_time("2000-01-01")
            def test_function(freezer):
                freezer.move_to("2023-01-01")

            def test_function2():
                with freezegun.freeze_time("2000-01-01") as t:
                    t.move_to("2023-01-01")
                    t.tick()

            @pytest.mark.freeze_time("2000-01-01")
            def test_function3(freezer):
                freezer.move_to("2023-01-01")
            """,
            """
            import pytest

            @pytest.mark.time_machine("2000-01-01", tick=False)
            def test_function(time_machine):
                time_machine.move_to("2023-01-01", tick=False)

            def test_function2():
                import time_machine
                with time_machine.travel("2000-01-01", tick=False) as t:
                    t.move_to("2023-01-01")
                    t.shift(1)

            @pytest.mark.time_machine("2000-01-01", tick=False)
            def test_function3(time_machine):
                time_machine.move_to("2023-01-01", tick=False)
            """,
        )

    def test_freezegun_freezer_decorator_and_fixture_mix_tick_false(self):
        check_transformed(
            """
            import freezegun
            import pytest

            @freezegun.freeze_time("2000-01-01", tick=True)
            def test_function(freezer):
                freezer.move_to("2023-01-01")

            def test_function2():
                with freezegun.freeze_time("2000-01-01", tick=True) as t:
                    t.move_to("2023-01-01")
                    t.tick()

            @pytest.mark.freeze_time("2000-01-01", tick=False)
            def test_function3(freezer):
                freezer.move_to("2023-01-01")
            """,
            """
            import pytest

            @pytest.mark.time_machine("2000-01-01", tick=True)
            def test_function(time_machine):
                time_machine.move_to("2023-01-01", tick=True)

            def test_function2():
                import time_machine
                with time_machine.travel("2000-01-01", tick=True) as t:
                    t.move_to("2023-01-01", tick=True)
                    t.shift(1)

            @pytest.mark.time_machine("2000-01-01", tick=False)
            def test_function3(time_machine):
                time_machine.move_to("2023-01-01", tick=False)
            """,
        )
