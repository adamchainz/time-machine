from __future__ import annotations

from setuptools import Extension, setup

setup(ext_modules=[Extension(name="_time_machine", sources=["src/_time_machine.c"])])
