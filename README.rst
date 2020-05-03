============
time-machine
============

.. image:: https://github.com/adamchainz/time-machine/workflows/CI/badge.svg?branch=master
   :target: https://github.com/adamchainz/time-machine/actions?workflow=CI

.. image:: https://img.shields.io/pypi/v/time-machine.svg
   :target: https://pypi.python.org/pypi/time-machine

.. image:: https://img.shields.io/badge/code%20style-black-000000.svg
   :target: https://github.com/python/black

Travel through time in your tests.

A quick example:

.. code-block:: python

    import datetime as dt
    import time_machine

    @time_machine.travel(0.0)
    def test_unix_epoch_timestamp():
        assert dt.date.today().isoformat() == "1970-01-01"

Installation
============

Use **pip**:

.. code-block:: sh

    python -m pip install time-machine

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
