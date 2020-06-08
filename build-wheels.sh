#!/bin/sh

mkdir -p wheelhouse
rm -rf wheelhouse/*

# Adapted from https://github.com/pypa/python-manylinux-demo/

# shellcheck disable=SC2016
DOCKER_SCRIPT='
for PYBIN in /opt/python/*/bin; do
    "${PYBIN}/pip" wheel /io/ --no-deps -w /io/wheelhouse/
done'


docker run --rm -e PLAT=manylinux1_i686 -v "$(pwd)":/io quay.io/pypa/manylinux1_i686 linux32 bash -c "$DOCKER_SCRIPT"
docker run --rm -e PLAT=manylinux1_x86_64 -v "$(pwd)":/io quay.io/pypa/manylinux1_x86_64 bash -c "$DOCKER_SCRIPT"
docker run --rm -e PLAT=manylinux2010_x86_64 -v "$(pwd)":/io quay.io/pypa/manylinux2010_x86_64 bash -c "$DOCKER_SCRIPT"

# Only manylinux wheels
rm wheelhouse/*-linux*

twine check wheelhouse/*
