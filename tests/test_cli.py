from __future__ import annotations

import io
import subprocess
import sys
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
        assert err == (
            "usage: __main__.py [-h] {migrate} ...\n"
            + "__main__.py: error: the following arguments are required: command\n"
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

    def test_decorator_attr_unrelated(self):
        check_noop(
            """
            import libfaketime

            @libfaketime.freeze_time("2023-01-01")
            def test_function():
                pass
            """,
        )

    def test_decorator_attr_not_called(self):
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

    def test_decorator_attr(self):
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

    def test_decorator_name_unrelated(self):
        check_noop(
            """
            from libfaketime import freeze_time

            @freeze_time("2023-01-01")
            def test_function():
                pass
            """,
        )

    def test_decorator_name_not_called(self):
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

    def test_decorator_name(self):
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
