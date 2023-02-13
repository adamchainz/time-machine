#!/usr/bin/env python
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

if __name__ == "__main__":
    os.chdir(Path(__file__).parent)

    os.environ["CUSTOM_COMPILE_COMMAND"] = "requirements/compile.py"
    os.environ["PIP_REQUIRE_VIRTUALENV"] = "0"

    for python_version in ["3.7", "3.8", "3.9", "3.10", "3.11"]:
        subprocess.run(
            [
                f"python{python_version}",
                "-m",
                "piptools",
                "compile",
                "--generate-hashes",
                "--allow-unsafe",
                *sys.argv[1:],
                "-o",
                f"py{python_version.replace('.', '')}.txt",
            ],
            check=True,
            capture_output=True,
        )
