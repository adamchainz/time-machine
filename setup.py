from __future__ import annotations

import sys

from setuptools import Extension
from setuptools import setup


if hasattr(sys, "pypy_version_info"):
    raise RuntimeError(
        "PyPy is not currently supported by time-machine, see "
        "https://github.com/adamchainz/time-machine/issues/305"
    )


setup(ext_modules=[Extension(name="_time_machine", sources=["src/_time_machine.c"])])
