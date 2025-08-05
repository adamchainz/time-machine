time-machine documentation
==========================

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

For a bit of background, see `the introductory blog post <https://adamj.eu/tech/2020/06/03/introducing-time-machine/>`__ and `the benchmark blog post <https://adamj.eu/tech/2021/02/19/freezegun-versus-time-machine/>`__.

----

**Testing a Django project?**
Check out my book `Speed Up Your Django Tests <https://adamchainz.gumroad.com/l/suydt>`__ which covers loads of ways to write faster, more accurate tests.
I created time-machine whilst writing the book.

----

time-machine is a tool for mocking the time in tests.

To get started, see :doc:`installation`, :doc:`usage`, and :doc:`pytest_plugin`.
If you’re coming from freezegun or libfaketime, see :doc:`comparison` and :doc:`migration`.

.. toctree::
   :maxdepth: 1
   :caption: Contents:

   installation
   usage
   pytest_plugin
   changelog
   comparison
   migration
