from setuptools import Extension, setup

setup(ext_modules=[Extension(name="_tachyon_gun", sources=["src/_tachyon_gun.c"])])
