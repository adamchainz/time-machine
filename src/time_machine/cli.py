from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence


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
    for file in files:
        try:
            fp = open(file, "r+", encoding="utf-8")  # noqa: SIM115
        except OSError as exc:
            print(f"can't open {file}: {exc}", file=sys.stderr)
            return 2
        else:
            with fp:
                content = fp.read()
                updated_content = migrate_text(content)
                if updated_content != content:
                    print(f"Rewriting {file}", file=sys.stderr)

                    returncode = 1

                    fp.seek(0)
                    fp.write(updated_content)
                    fp.truncate()

    return returncode


def migrate_text(text: str) -> str:
    """Migrate a single text from freezegun to time-machine."""
    return text.replace("freezegun", "time_machine")
