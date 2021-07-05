============
time-machine
============

.. image:: https://img.shields.io/github/workflow/status/adamchainz/time-machine/CI/main?style=for-the-badge
   :target: https://github.com/adamchainz/time-machine/actions?workflow=CI

.. image:: https://img.shields.io/codecov/c/github/adamchainz/time-machine/main?style=for-the-badge
  :target: https://app.codecov.io/gh/adamchainz/time-machine

.. image:: https://img.shields.io/pypi/v/time-machine.svg?style=for-the-badge
   :target: https://pypi.org/project/time-machine/

.. image:: https://img.shields.io/badge/code%20style-black-000000.svg?style=for-the-badge
   :target: https://github.com/psf/black

.. image:: https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white&style=for-the-badge
   :target: https://github.com/pre-commit/pre-commit
   :alt: pre-commit

Travel through time in your tests.

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

Installation
============

Use **pip**:

.. code-block:: sh

    python -m pip install time-machine

Python 3.6 to 3.9 supported.
Only CPython is supported at this time because time-machine directly hooks into the C-level API.

----

**Testing a Django project?**
Check out my book `Speed Up Your Django Tests <https://gumroad.com/l/suydt>`__ which covers loads of best practices so you can write faster, more accurate tests.
I created time-machine whilst writing the book.

----

Usage
=====

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
* A ``float`` or ``int`` specifying a `Unix timestamp <https://en.m.wikipedia.org/wiki/Unix_time>`__
* A string, which will be parsed with `dateutil.parse <https://dateutil.readthedocs.io/en/stable/parser.html>`__ and converted to a timestamp.

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
* ``time.gmtime()``
* ``time.localtime()``
* ``time.clock_gettime()`` (only for ``CLOCK_REALTIME``)
* ``time.clock_gettime_ns()`` (only for ``CLOCK_REALTIME``)
* ``time.strftime()``
* ``time.time()``
* ``time.time_ns()``

The mocking is done at the C layer, replacing the function pointers for these built-ins.
Therefore, it automatically affects everywhere those functions have been imported, unlike use of ``unittest.mock.patch()``.

Usage with ``start()`` / ``stop()``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

To use independently, create and instance, use ``start()`` to move to the destination time, and ``stop()`` to move back.
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

Beware: time is a *global* state - see below.

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

Timezone mocking
^^^^^^^^^^^^^^^^

If the ``destination`` passed to ``time_machine.travel()`` or ``Coordinates.move_to()`` has its ``tzinfo`` set to a |zoneinfo-instance2|_, the current timezone will be mocked.
This will be done by calling |time-tzset|_, so it is only available on Unix.
The ``zoneinfo`` module is new in Python 3.8 - on older Python versions use the |backports-zoneinfo-package|_, by the original ``zoneinfo`` author.

.. |zoneinfo-instance2| replace:: ``zoneinfo.ZoneInfo`` instance
.. _zoneinfo-instance2: https://docs.python.org/3/library/zoneinfo.html#zoneinfo.ZoneInfo

.. |time-tzset| replace:: ``time.tzset()``
.. _time-tzset: https://docs.python.org/3/library/time.html#time.tzset

.. |backports-zoneinfo-package| replace:: ``backports.zoneinfo`` package
.. _backports-zoneinfo-package: https://pypi.org/project/backports.zoneinfo/

``time.tzset()`` changes the ``time`` module’s `timezone constants <https://docs.python.org/3/library/time.html#timezone-constants>`__ and features that rely on those, such as ``time.localtime()``.
It won’t affect other concepts of “the current timezone”, such as Django’s (which can be changed with its |timezone-override|_).

.. |timezone-override| replace:: ``time.override()``
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

pytest plugin
-------------

time-machine also works as a pytest plugin.
It provides a function-scoped fixture called ``time_machine`` that has one method, ``move_to()``, which has the same signature as ``Coordinates.move_to()``.
This can be used to mock your test at different points in time and will automatically be un-mock when the test is torn down.

For example:

.. code-block:: python

    import datetime as dt

    def test_delorean(time_machine):
        time_machine.move_to(dt.datetime(1985, 10, 26))

        assert dt.date.today().isoformat() == "1985-10-26"

        time_machine.move_to(dt.datetime(2015, 10, 21))

        assert dt.date.today().isoformat() == "2015-10-21"

Caveats
=======

Time is a global state.
Any concurrent threads or asynchronous functions are also be affected.
Some aren't ready for time to move so rapidly or backwards, and may crash or produce unexpected results.

Also beware that other processes are not affected.
For example, if you use SQL datetime functions on a database server, they will return the real time.

Comparison
==========

There are some prior libraries that try to achieve the same thing.
They have their own strengths and weaknesses.
Here's a quick comparison.

unittest.mock
-------------

The standard library's `unittest.mock <https://docs.python.org/3/library/unittest.mock.html>`__ can be used to target imports of ``datetime`` and ``time`` to change the returned value for current time.
Unfortunately, this is fragile as it only affects the import location the mock targets.
Therefore, if you have several modules in a call tree requesting the date/time, you need several mocks.
This is a general problem with unittest.mock - see `Why Your Mock Doesn't Work <https://nedbatchelder.com//blog/201908/why_your_mock_doesnt_work.html>`__.

It's also impossible to mock certain references, such as function default arguments:

.. code-block:: python

    def update_books(_now=time.time):  # set as default argument so faster lookup
        for book in books:
            ...

Although such references are rare, they are occasionally used to optimize highly repeated loops.

freezegun
---------

Steve Pulec's `freezegun <https://github.com/spulec/freezegun>`__ library is a popular solution.
It provides a clear API which was much of the inspiration for time-machine.

The main drawback is its slow implementation.
It essentially does a find-and-replace mock of all the places that the ``datetime`` and ``time`` modules have been imported.
This gets around the problems with using unittest.mock, but it means the time it takes to do the mocking is proportional to the number of loaded modules.
In large projects, this can take several seconds, an impractical overhead for an individual test.

It's also not a perfect search, since it searches only module-level imports.
Such imports are definitely the most common way projects use date and time functions, but they're not the only way.
freezegun won’t find functions that have been “hidden” inside arbitrary objects, such as class-level attributes.

It also can't affect C extensions that call the standard library functions, including (I believe) Cython-ized Python code.

python-libfaketime
------------------

Simon Weber's `python-libfaketime <https://github.com/simon-weber/python-libfaketime/>`__ wraps the `libfaketime <https://github.com/wolfcw/libfaketime>`__ library.
libfaketime replaces all the C-level system calls for the current time with its own wrappers.
It's therefore a "perfect" mock for the current process, affecting every single point the current time might be fetched, and performs much faster than freezegun.

Unfortunately python-libfaketime comes with the limitations of ``LD_PRELOAD``.
This is a mechanism to replace system libraries for a program as it loads (`explanation <http://www.goldsborough.me/c/low-level/kernel/2016/08/29/16-48-53-the_-ld_preload-_trick/>`__).
This causes two issues in particular when you use python-libfaketime.

First, ``LD_PRELOAD`` is only available on Unix platforms, which prevents you from using it on Windows.

Second, you have to help manage ``LD_PRELOAD``.
You either use python-libfaketime's ``reexec_if_needed()`` function, which restarts (*re-execs*) your test process while loading, or manually manage the ``LD_PRELOAD`` environment variable.
Neither is ideal.
Re-execing breaks anything that might wrap your test process, such as profilers, debuggers, and IDE test runners.
Manually managing the environment variable is a bit of overhead, and must be done for each environment you run your tests in, including each developer's machine.

time-machine
------------

time-machine is intended to combine the advantages of freezegun and libfaketime.
It works without ``LD_PRELOAD`` but still mocks the standard library functions everywhere they may be referenced.
Its weak point is that other libraries using date/time system calls won't be mocked.
Thankfully this is rare.
It's also possible such python libraries can be added to the set mocked by time-machine.

One drawback is that it only works with CPython, so can't be used with other Python interpreters like PyPy.
However it may possible to extend it to support other interpreters through different mocking mechanisms.

Migrating from libfaketime or freezegun
=======================================

freezegun has a useful API, and python-libfaketime copies some of it, with a different function name.
time-machine also copies some of freezegun's API, in ``travel()``\'s ``destination``, and ``tick`` arguments, and the ``shift()`` method.
There are a few differences:

* time-machine's ``tick`` argument defaults to ``True``, because code tends to make the (reasonable) assumption that time progresses between function calls, and should normally be tested as such.
  Testing with time frozen can make it easy to write complete assertions, but it's quite artificial.
* freezegun's ``tick()`` method has been implemented as ``shift()``, to avoid confusion with the ``tick`` argument.
  It also requires an explicit delta rather than defaulting to 1 second.
* freezegun's ``tz_offset`` argument only partially mocks the current time zone.
  Time zones are more complicated than a single offset from UTC, and freezegun only uses the offset in ``time.localtime()``.
  Instead, time-machine will mock the current time zone if you give it a ``datetime`` with a ``ZoneInfo`` timezone.

Some features aren't supported like the ``auto_tick_seconds`` argument.
These may be added in a future release.

If you are only fairly simple function calls, you should be able to migrate by replacing calls to ``freezegun.freeze_time()`` and ``libfaketime.fake_time()`` with ``time_machine.travel()``.
