#!/usr/bin/env python
import os
import subprocess
import sys
from pathlib import Path


if __name__ == "__main__":
    os.chdir(Path(__file__).parent)
    os.environ["CUSTOM_COMPILE_COMMAND"] = "requirements/compile.py"
    common_args = ["-m", "piptools", "compile", "--generate-hashes"] + sys.argv[1:]
    subprocess.run(
        ["python3.5", *common_args, "-o", "py35.txt"], check=True,
    )
    subprocess.run(
        ["python3.6", *common_args, "-o", "py36.txt"], check=True,
    )
    subprocess.run(
        ["python3.7", *common_args, "-o", "py37.txt"], check=True,
    )
    subprocess.run(
        ["python3.8", *common_args, "-o", "py38.txt"], check=True,
    )
