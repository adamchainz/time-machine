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

``travel(destination)``
-----------------------

``travel()`` is a class that allows movement to a given time specified by ``destination``.
It can be used independently, as a function decorator, or as a context manager.

``destination`` specifies the time to move to.
It may be:

* A ``datetime.datetime``.
  If it is naive, it will be assumed to have the UTC timezone.
* A ``float`` or ``int`` specifying a `Unix timestamp <https://en.m.wikipedia.org/wiki/Unix_time>`__
* A string, which will be parsed with `dateutil.parse <https://dateutil.readthedocs.io/en/stable/parser.html>`__ and converted to a timestamp.

To use independently, instantiate, then use ``start()`` to move to the destination time, and ``stop()`` to move back.

.. code-block:: python

    import datetime as dt
    import time_machine

    traveller = time_machine.travel(dt.datetime(1985, 11, 5))
    traveller.start()
    # It's the past!
    assert dt.date.today() == dt.date(1985, 11, 5)
    traveller.stop()
    # We've gone back to the future!
    assert dt.date.today() > dt.date(2020, 4, 29)

Once started, all datetime functions in the standard library are mocked to pretend the current time is that time:

* ``datetime.datetime.now()``
* ``datetime.datetime.utcnow()``
* ``time.time()``
* ``time.gmtime()``
* ``time.localtime()``
* ``time.strftime()``

At least two functions are currently missing:

* ``time.clock_gettime``
* ``time.time_ns()``

This mocking is at the C layer, replacing the function pointers for these built-ins.
Therefore, it automatically affects everywhere those functions were imported.

Any other functions that make system calls to retrieve the clock time will not be affected, but these are rare.
Most Python libraries use the above standard library functions.

Beware that time is global state.
Any concurrent threads or async functions will also be affected.
Some aren't ready for time to move so rapidly and may crash or produce unexpected results.
But other processes are not affected, for example if you use datetime functions in a client/server database, they will still return the real time.

Time "continues ticking," so two calls to ``time.time()`` will return results separated by the time elapsed between them.

When used as a function decorator, time is mocked during the wrapped function's duration:

.. code-block:: python

    import time
    import time_machine

    @time_machine.travel("1970-01-01 00:00 +0000")
    def test_in_the_deep_past():
        assert 0.0 < time.time() < 1.0

When used as a context manager, time is mocked during the ``with`` block:

.. code-block:: python

    def test_time_time():
        with time_machine.travel(0.0):
            assert EPOCH < time.time() < EPOCH + 1.0

Comparison
==========

There are some prior libraries that try to achieve the same thing.
They have their own strengths and weaknesses.
Here's a quick comparison.

``unittest.mock``
-----------------

The standard library's `unittest.mock <https://docs.python.org/3/library/unittest.mock.html>`__ can be used to target ``datetime`` or ``time`` imports to change the returned value for current time.
Unfortunately, this is fragile as it only affects the import location the mock targets.
Therefore, if you have several call sites checking the time, you may need several mocks.

See `Why Your Mock Doesn't Work <https://nedbatchelder.com//blog/201908/why_your_mock_doesnt_work.html>`__.

``freezegun``
-------------

Steve Pulec's `freezegun <https://github.com/spulec/freezegun>`__ library is a popular solution.
It provides a nice API which was much of the inspiration for time-machine.

The main drawback is its slow implementation.
It essentially does a find-and-replace mock of all the places that the ``datetime`` and ``time`` modules have been imported.
This gets around the problems with using ``unittest.mock``, but it means the time to mock is linear to the number of loaded modules, making it several seconds to start in large projects.

It also can't affect C extensions that call the standard library functions, including Cython.
And it can be subverted even in Python by code that stores the standard library functions in data structures or local scopes.

``libfaketime``
---------------

Simon Weber's `python-libfaketime <https://github.com/simon-weber/python-libfaketime/>`__ wraps the ``LD_PRELOAD`` library `libfaketime <https://github.com/wolfcw/libfaketime>`__.
``libfaketime`` replaces all the C-level system calls for the current time with its own wrappers.
It's therefore a "perfect" mock for the current process, affecting every single point the current time might be fetched, and performs much faster than ``freezegun``.

Unfortunately it comes with the limitations of ``LD_PRELOAD`` (`explanation <http://www.goldsborough.me/c/low-level/kernel/2016/08/29/16-48-53-the_-ld_preload-_trick/>`__).
First, this is only available on Unix platforms, which prevents it from working on Windows.
Seccond, you either use its ``reexec_if_needed()`` function, which restarts (re-execs) your tests' process once while loading, or manually manage the ``LD_PRELOAD`` environment variable everywhere you run your tests.
Re-execing breaks profilers, use of ``python -m pdb`` and similar, and other things that might wrap your test process.
Manually managing the environment variable is a bit of overhead for each environment you want to run your tests in.

``time-machine``
----------------

``time-machine`` is intended to combine the advantages of ``freezegun`` and ``libfaketime``.
It works without ``LD_PRELOAD`` but still mocks the standard library functions everywhere they may be referenced.
Its weak point is that other libraries using date/time system calls won't be mocked.
Thankfully this is rare - all Python libraries I've seen use the standard library functions.
And other python libraries can probably be added to the set detected and mocked by ``time-machine``.

One drawback is that it only works with CPython, so can't be used with other Python interpreters like PyPy.
However it may possible to extend it to use different mocking mechanisms there.
