=============
pytest plugin
=============

time-machine also works as a pytest plugin.
It provides a marker and function-scoped fixture called ``time_machine`` with methods ``move_to()`` and ``shift()``, which have the same signature as their equivalents in ``Coordinates``.
This can be used to mock your test at different points in time and will automatically be un-mock when the test is torn down.

For example:

.. code-block:: python

    import datetime as dt


    @pytest.mark.time_machine(dt.datetime(1985, 10, 26))
    def test_delorean_marker(time_machine):
        assert dt.date.today().isoformat() == "1985-10-26"
        time_machine.move_to(dt.datetime(2015, 10, 21))
        assert dt.date.today().isoformat() == "2015-10-21"


    def test_delorean(time_machine):
        time_machine.move_to(dt.datetime(1985, 10, 26))

        assert dt.date.today().isoformat() == "1985-10-26"

        time_machine.move_to(dt.datetime(2015, 10, 21))

        assert dt.date.today().isoformat() == "2015-10-21"

        time_machine.shift(dt.timedelta(days=1))

        assert dt.date.today().isoformat() == "2015-10-22"

If you are using pytest test classes, you can apply the fixture to all test methods in a class by adding an autouse fixture:

.. code-block:: python

    import time

    import pytest


    class TestSomething:
        @pytest.fixture(autouse=True)
        def set_time(self, time_machine):
            time_machine.move_to(1000.0)

        def test_one(self):
            assert int(time.time()) == 1000.0

        def test_two(self, time_machine):
            assert int(time.time()) == 1000.0
            time_machine.move_to(2000.0)
            assert int(time.time()) == 2000.0
