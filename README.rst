============
time-machine
============

.. image:: https://img.shields.io/readthedocs/time-machine?style=for-the-badge
   :target: https://time-machine.readthedocs.io/en/latest/

.. image:: https://img.shields.io/github/actions/workflow/status/adamchainz/time-machine/main.yml.svg?branch=main&style=for-the-badge
   :target: https://github.com/adamchainz/time-machine/actions?workflow=CI

.. image:: https://img.shields.io/badge/Coverage-100%25-success?style=for-the-badge
   :target: https://github.com/adamchainz/time-machine/actions?workflow=CI

.. image:: https://img.shields.io/pypi/v/time-machine.svg?style=for-the-badge
   :target: https://pypi.org/project/time-machine/

.. image:: https://img.shields.io/badge/code%20style-black-000000.svg?style=for-the-badge
   :target: https://github.com/psf/black

.. image:: https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white&style=for-the-badge
   :target: https://github.com/pre-commit/pre-commit
   :alt: pre-commit

----

.. figure:: https://raw.githubusercontent.com/adamchainz/time-machine/main/docs/_static/logo.svg
  :alt: time-machine logo
  :align: center

*Travel through time in your tests.*

A quick example:

.. code-block:: python

    import datetime as dt
    from zoneinfo import ZoneInfo
    import time_machine

    hill_valley_tz = ZoneInfo("America/Los_Angeles")


    @time_machine.travel(dt.datetime(1985, 10, 26, 1, 24, tzinfo=hill_valley_tz))
    def test_delorean():
        assert dt.date.today().isoformat() == "1985-10-26"

Documentation
=============

Please see https://time-machine.readthedocs.io/.
