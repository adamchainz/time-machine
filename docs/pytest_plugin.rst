=============
pytest plugin
=============

time-machine works as a pytest plugin, which pytest will detect automatically.
The plugin supplies both a fixture and a marker to control the time during tests.

``time_machine`` marker
-----------------------

Use the ``time_machine`` `marker <https://docs.pytest.org/en/stable/how-to/mark.html>`__ with a valid destination for :class:`~.travel` to mock the time while a test function runs.
It applies for function-scoped fixtures too, meaning the time will be mocked for any setup or teardown code done in the test function.

For example:

.. code-block:: python

    import datetime as dt


    @pytest.mark.time_machine(dt.datetime(1985, 10, 26))
    def test_delorean_marker():
        assert dt.date.today().isoformat() == "1985-10-26"

Or for a class:

.. code-block:: python

    import datetime as dt

    import pytest


    @pytest.mark.time_machine(dt.datetime(1985, 10, 26))
    class TestSomething:
        def test_one(self):
            assert dt.date.today().isoformat() == "1985-10-26"

        def test_two(self):
            assert dt.date.today().isoformat() == "1985-10-26"

``time_machine`` fixture
------------------------

Use the function-scoped `fixture <https://docs.pytest.org/en/stable/explanation/fixtures.html#about-fixtures>`__ ``time_machine`` to control time in your tests.
It provides an object with two methods, ``move_to()`` and ``shift()``, which work the same as their equivalents in the :class:`time_machine.Traveller` class.
Until you call ``move_to()``, time is not mocked.

For example:

.. code-block:: python

    import datetime as dt


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

It’s possible to combine the marker and fixture in the same test:

.. code-block:: python

    import datetime as dt

    import pytest


    @pytest.mark.time_machine(dt.datetime(1985, 10, 26))
    def test_delorean_marker_and_fixture(time_machine):
        assert dt.date.today().isoformat() == "1985-10-26"
        time_machine.move_to(dt.datetime(2015, 10, 21))
        assert dt.date.today().isoformat() == "2015-10-21"
