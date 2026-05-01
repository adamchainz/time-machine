from __future__ import annotations

import sys

from setuptools import Extension, setup

if hasattr(sys, "pypy_version_info"):
    raise RuntimeError(
        "PyPy is not currently supported by time-machine, see "
        "https://github.com/adamchainz/time-machine/issues/305"
    )

extra_compile_args = []
if sys.platform != "win32":
    extra_compile_args += [
        "-fno-omit-frame-pointer",
        "-mno-omit-leaf-frame-pointer",
    ]


setup(
    ext_modules=[
        Extension(
            name="_time_machine",
            sources=["src/_time_machine.c"],
            extra_compile_args=extra_compile_args,
        )
    ]
)
