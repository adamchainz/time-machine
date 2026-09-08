from __future__ import annotations

import os
import sys
import tempfile

from setuptools import Extension, setup
from setuptools.command.build_ext import build_ext
from setuptools.errors import CompileError

if hasattr(sys, "pypy_version_info"):
    raise RuntimeError(
        "PyPy is not currently supported by time-machine, see "
        "https://github.com/adamchainz/time-machine/issues/305"
    )


class BuildExt(build_ext):  # type: ignore[misc]
    def build_extensions(self) -> None:
        if self.compiler.compiler_type != "msvc":
            flags = ["-fno-omit-frame-pointer"]
            # Unsupported on some architectures, like PowerPC:
            if self._has_flag("-mno-omit-leaf-frame-pointer"):
                flags.append("-mno-omit-leaf-frame-pointer")
            for extension in self.extensions:
                extension.extra_compile_args.extend(flags)
        super().build_extensions()

    def _has_flag(self, flag: str) -> bool:
        with tempfile.TemporaryDirectory() as tmpdir:
            source = os.path.join(tmpdir, "probe.c")
            with open(source, "w") as fp:
                fp.write("int main(void) { return 0; }\n")
            try:
                self.compiler.compile(
                    [source],
                    output_dir=tmpdir,
                    # -Werror since Clang only warns on unknown -m… flags:
                    extra_postargs=[flag, "-Werror"],
                )
            except CompileError:
                return False
        return True


setup(
    cmdclass={"build_ext": BuildExt},
    ext_modules=[
        Extension(
            name="_time_machine",
            sources=["src/_time_machine.c"],
        )
    ],
)
