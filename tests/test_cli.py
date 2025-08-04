from __future__ import annotations

import subprocess
import sys

import pytest

from tests.backports import chdir

# import __main__ for coverage
from time_machine import __main__  # noqa: F401
from time_machine.cli import main


def test_no_subcommand(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main([])

    assert excinfo.value.code == 2
    out, err = capsys.readouterr()
    assert err == (
        "usage: __main__.py [-h] {migrate} ...\n"
        + "__main__.py: error: the following arguments are required: command\n"
    )
    assert out == ""


def test_main_help():
    with pytest.raises(SystemExit) as excinfo:
        main(["--help"])

    assert excinfo.value.code == 0


def test_main_help_subprocess():
    proc = subprocess.run(
        [sys.executable, "-m", "time_machine", "--help"],
        check=True,
        capture_output=True,
    )

    assert proc.stdout.startswith(b"usage: __main__.py ")


def test_migrate_help_command(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["migrate", "--help"])
    assert excinfo.value.code == 0


def test_migrate_no_files(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["migrate"])

    assert excinfo.value.code == 2


def test_migrate_unreadable(capsys, tmp_path):
    with chdir(tmp_path):
        result = main(["migrate", "unreadable.py"])
    assert result == 2
    out, err = capsys.readouterr()
    assert out == ""
    assert (
        err
        == "can't open unreadable.py: [Errno 2] No such file or directory: 'unreadable.py'\n"
    )


def test_migrate_empty(capsys, tmp_path):
    path = tmp_path / "example.py"
    path.write_text("\n")

    result = main(["migrate", str(path)])

    assert result == 0
    out, err = capsys.readouterr()
    assert out == ""
    assert err == ""

    assert path.read_text() == "\n"


def test_migrate_import(capsys, tmp_path):
    path = tmp_path / "example.py"
    path.write_text("import freezegun\n")

    result = main(["migrate", str(path)])

    assert result == 1
    out, err = capsys.readouterr()
    assert out == ""
    assert err == f"Rewriting {path}\n"

    assert path.read_text() == "import time_machine\n"
