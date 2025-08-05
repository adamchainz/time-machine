=====
Usage
=====

This document covers time-machine’s API.

.. warning::

    Time is a global state.
    When mocking it, all concurrent threads or asynchronous functions are also affected.
    Some aren't ready for time to move so rapidly or backwards, and may crash or produce unexpected results.

    Also beware that other processes are not affected.
    For example, if you call datetime functions on a database server, they will return the real time.

Main API
========

``travel(destination, *, tick=True)``
-------------------------------------

``travel()`` is a class that allows time travel, to the datetime specified by ``destination``.
It does so by mocking all functions from Python's standard library that return the current date or datetime.
It can be used independently, as a function decorator, or as a context manager.

``destination`` specifies the datetime to move to.
It may be:

* A ``datetime.datetime``.
  If it is naive, it will be assumed to have the UTC timezone.
  If it has ``tzinfo`` set to a |zoneinfo-instance|_, the current timezone will also be mocked.
* A ``datetime.date``.
  This will be converted to a UTC datetime with the time 00:00:00.
* A ``datetime.timedelta``.
  This will be interpreted relative to the current time.
  If already within a ``travel()`` block, the ``shift()`` method is easier to use (documented below).
* A ``float`` or ``int`` specifying a `Unix timestamp <https://en.m.wikipedia.org/wiki/Unix_time>`__
* A string, which will be parsed with `dateutil.parse <https://dateutil.readthedocs.io/en/stable/parser.html>`__ and converted to a timestamp.
  If the result is naive, it will be assumed to be local time.

.. |zoneinfo-instance| replace:: ``zoneinfo.ZoneInfo`` instance
.. _zoneinfo-instance: https://docs.python.org/3/library/zoneinfo.html#zoneinfo.ZoneInfo

Additionally, you can provide some more complex types:

* A generator, in which case ``next()`` will be called on it, with the result treated as above.
* A callable, in which case it will be called with no parameters, with the result treated as above.

``tick`` defines whether time continues to "tick" after travelling, or is frozen.
If ``True``, the default, successive calls to mocked functions return values increasing by the elapsed real time *since the first call.*
So after starting travel to ``0.0`` (the UNIX epoch), the first call to any datetime function will return its representation of ``1970-01-01 00:00:00.000000`` exactly.
The following calls "tick," so if a call was made exactly half a second later, it would return ``1970-01-01 00:00:00.500000``.

Mocked Functions
^^^^^^^^^^^^^^^^

All datetime functions in the standard library are mocked to move to the destination current datetime:

* ``datetime.datetime.now()``
* ``datetime.datetime.utcnow()``
* ``time.clock_gettime()`` (only for ``CLOCK_REALTIME``)
* ``time.clock_gettime_ns()`` (only for ``CLOCK_REALTIME``)
* ``time.gmtime()``
* ``time.localtime()``
* ``time.monotonic()`` (not a real monotonic clock, returns ``time.time()``)
* ``time.monotonic_ns()`` (not a real monotonic clock, returns ``time.time_ns()``)
* ``time.strftime()``
* ``time.time()``
* ``time.time_ns()``

The mocking is done at the C layer, replacing the function pointers for these built-ins.
Therefore, it automatically affects everywhere those functions have been imported, unlike use of ``unittest.mock.patch()``.

Usage with ``start()`` / ``stop()``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

To use independently, create an instance, use ``start()`` to move to the destination time, and ``stop()`` to move back.
For example:

.. code-block:: python

    import datetime as dt
    import time_machine

    traveller = time_machine.travel(dt.datetime(1985, 10, 26))
    traveller.start()
    # It's the past!
    assert dt.date.today() == dt.date(1985, 10, 26)
    traveller.stop()
    # We've gone back to the future!
    assert dt.date.today() > dt.date(2020, 4, 29)

``travel()`` instances are nestable, but you'll need to be careful when manually managing to call their ``stop()`` methods in the correct order, even when exceptions occur.
It's recommended to use the decorator or context manager forms instead, to take advantage of Python features to do this.

Function Decorator
^^^^^^^^^^^^^^^^^^

When used as a function decorator, time is mocked during the wrapped function's duration:

.. code-block:: python

    import time
    import time_machine


    @time_machine.travel("1970-01-01 00:00 +0000")
    def test_in_the_deep_past():
        assert 0.0 < time.time() < 1.0

You can also decorate asynchronous functions (coroutines):

.. code-block:: python

    import time
    import time_machine


    @time_machine.travel("1970-01-01 00:00 +0000")
    async def test_in_the_deep_past():
        assert 0.0 < time.time() < 1.0

Beware: time is a *global* state - `see below <#caveats>`__.

Context Manager
^^^^^^^^^^^^^^^

When used as a context manager, time is mocked during the ``with`` block:

.. code-block:: python

    import time
    import time_machine


    def test_in_the_deep_past():
        with time_machine.travel(0.0):
            assert 0.0 < time.time() < 1.0

Class Decorator
^^^^^^^^^^^^^^^

Only ``unittest.TestCase`` subclasses are supported.
When applied as a class decorator to such classes, time is mocked from the start of ``setUpClass()`` to the end of ``tearDownClass()``:

.. code-block:: python

    import time
    import time_machine
    import unittest


    @time_machine.travel(0.0)
    class DeepPastTests(TestCase):
        def test_in_the_deep_past(self):
            assert 0.0 < time.time() < 1.0

Note this is different to ``unittest.mock.patch()``\'s behaviour, which is to mock only during the test methods.
For pytest-style test classes, see the pattern `documented below <#pytest-plugin>`__.

Timezone mocking
^^^^^^^^^^^^^^^^

If the ``destination`` passed to ``time_machine.travel()`` or ``Coordinates.move_to()`` has its ``tzinfo`` set to a |zoneinfo-instance2|_, the current timezone will be mocked.
This will be done by calling |time-tzset|_, so it is only available on Unix.

.. |zoneinfo-instance2| replace:: ``zoneinfo.ZoneInfo`` instance
.. _zoneinfo-instance2: https://docs.python.org/3/library/zoneinfo.html#zoneinfo.ZoneInfo

.. |time-tzset| replace:: ``time.tzset()``
.. _time-tzset: https://docs.python.org/3/library/time.html#time.tzset

``time.tzset()`` changes the ``time`` module’s `timezone constants <https://docs.python.org/3/library/time.html#timezone-constants>`__ and features that rely on those, such as ``time.localtime()``.
It won’t affect other concepts of “the current timezone”, such as Django’s (which can be changed with its |timezone-override|_).

.. |timezone-override| replace:: ``timezone.override()``
.. _timezone-override: https://docs.djangoproject.com/en/stable/ref/utils/#django.utils.timezone.override

Here’s a worked example changing the current timezone:

.. code-block:: python

    import datetime as dt
    import time
    from zoneinfo import ZoneInfo
    import time_machine

    hill_valley_tz = ZoneInfo("America/Los_Angeles")


    @time_machine.travel(dt.datetime(2015, 10, 21, 16, 29, tzinfo=hill_valley_tz))
    def test_hoverboard_era():
        assert time.tzname == ("PST", "PDT")
        now = dt.datetime.now()
        assert (now.hour, now.minute) == (16, 29)

``Coordinates``
---------------

The ``start()`` method and entry of the context manager both return a ``Coordinates`` object that corresponds to the given "trip" in time.
This has a couple methods that can be used to travel to other times.

``move_to(destination, tick=None)``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

``move_to()`` moves the current time to a new destination.
``destination`` may be any of the types supported by ``travel``.

``tick`` may be set to a boolean, to change the ``tick`` flag of ``travel``.

For example:

.. code-block:: python

    import datetime as dt
    import time
    import time_machine

    with time_machine.travel(0, tick=False) as traveller:
        assert time.time() == 0

        traveller.move_to(234)
        assert time.time() == 234

``shift(delta)``
^^^^^^^^^^^^^^^^

``shift()`` takes one argument, ``delta``, which moves the current time by the given offset.
``delta`` may be a ``timedelta`` or a number of seconds, which will be added to destination.
It may be negative, in which case time will move to an earlier point.

For example:

.. code-block:: python

    import datetime as dt
    import time
    import time_machine

    with time_machine.travel(0, tick=False) as traveller:
        assert time.time() == 0

        traveller.shift(dt.timedelta(seconds=100))
        assert time.time() == 100

        traveller.shift(-dt.timedelta(seconds=10))
        assert time.time() == 90

Escape hatch API
================

``escape_hatch``
----------------

The ``escape_hatch`` object provides functions to bypass time-machine, calling the real datetime functions, without any mocking.
It also provides a way to check if time-machine is currently time travelling.

These capabilities are useful in rare circumstances.
For example, if you need to authenticate with an external service during time travel, you may need the real value of ``datetime.now()``.

The functions are:

* ``escape_hatch.is_travelling() -> bool`` - returns ``True`` if ``time_machine.travel()`` is active, ``False`` otherwise.

* ``escape_hatch.datetime.datetime.now()`` - wraps the real ``datetime.datetime.now()``.

* ``escape_hatch.datetime.datetime.utcnow()`` - wraps the real ``datetime.datetime.utcnow()``.

* ``escape_hatch.time.clock_gettime()`` - wraps the real ``time.clock_gettime()``.

* ``escape_hatch.time.clock_gettime_ns()`` - wraps the real ``time.clock_gettime_ns()``.

* ``escape_hatch.time.gmtime()`` - wraps the real ``time.gmtime()``.

* ``escape_hatch.time.localtime()`` - wraps the real ``time.localtime()``.

* ``escape_hatch.time.strftime()`` - wraps the real ``time.strftime()``.

* ``escape_hatch.time.time()`` - wraps the real ``time.time()``.

* ``escape_hatch.time.time_ns()`` - wraps the real ``time.time_ns()``.

For example:

.. code-block:: python

    import time_machine


    with time_machine.travel(...):
        if time_machine.escape_hatch.is_travelling():
            print("We need to go back to the future!")

        real_now = time_machine.escape_hatch.datetime.datetime.now()
        external_authenticate(now=real_now)
