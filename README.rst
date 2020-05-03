===========
tachyon-gun
===========

.. image:: https://github.com/adamchainz/tachyon-gun/workflows/CI/badge.svg?branch=master
   :target: https://github.com/adamchainz/tachyon-gun/actions?workflow=CI

.. image:: https://img.shields.io/pypi/v/tachyon-gun.svg
   :target: https://pypi.python.org/pypi/tachyon-gun

.. image:: https://img.shields.io/badge/code%20style-black-000000.svg
   :target: https://github.com/python/black

Warp time.

A quick example:

.. code-block:: python

    import datetime as dt
    import tachyon_gun

    with tachyon_gun.warp_time(0.0):
        print(dt.date.today().isoformat())  # 1970-01-01


Installation
============

Use **pip**:

.. code-block:: sh

    python -m pip install tachyon-gun

Python 3.6 to 3.8 supported (CPython only).

Usage
=====

TODO

Alternatives
============

TODO

* ``unittest.mock``
* ``freezegun``
* ``libfaketime``
