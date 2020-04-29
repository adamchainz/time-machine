from setuptools import Extension, setup

setup(
    name="tachyongun",
    version="1.0.0",
    description="uh",

    zip_safe=False,
    python_requires=">=2.7, !=3.0.*, !=3.1.*, !=3.2.*, !=3.3.*, <4",
    py_modules=["tachyongun"],
    ext_modules=[
        Extension(
            name="_tachyongun",
            sources=["_tachyongun.c"],
        )
    ],
)
