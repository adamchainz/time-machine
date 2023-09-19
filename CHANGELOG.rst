=========
Changelog
=========

2.13.0 (2023-09-19)
-------------------

* Add support for ``datetime.timedelta`` to ``time_machine.travel()``.

  Thanks to Nate Dudenhoeffer in `PR #298 <https://github.com/adamchainz/time-machine/pull/298>`__.

* Fix documentation about using local time for naive date(time) strings.

  Thanks to Stefaan Lippens in `PR #306 <https://github.com/adamchainz/time-machine/pull/306>`__.

* Add ``shift()`` method to the ``time_machine`` pytest fixture.

  Thanks to Stefaan Lippens in `PR #312 <https://github.com/adamchainz/time-machine/pull/312>`__.

* Mock ``time.monotonic()`` and ``time.monotonic_ns()``.
  They return the values of ``time.time()`` and ``time.time_ns()`` respectively, rather than real monotonic clocks.

  Thanks to Anthony Sottile in `PR #382 <https://github.com/adamchainz/time-machine/pull/382>`__.

2.12.0 (2023-08-14)
-------------------

* Include wheels for Python 3.12.

2.11.0 (2023-07-10)
-------------------

* Drop Python 3.7 support.

2.10.0 (2023-06-16)
-------------------

* Support Python 3.12.

2.9.0 (2022-12-31)
------------------

* Build Windows ARM64 wheels.

* Explicitly error when attempting to install on PyPy.

Thanks to Michał Górny in `PR #315 <https://github.com/adamchainz/time-machine/pull/315>`__.

2.8.2 (2022-09-29)
------------------

* Improve type hints for ``time_machine.travel()`` to preserve the types of the wrapped function/coroutine/class.

2.8.1 (2022-08-16)
------------------

* Actually build Python 3.11 wheels.

2.8.0 (2022-08-15)
------------------

* Build Python 3.11 wheels.

2.7.1 (2022-06-24)
------------------

* Fix usage of ``ZoneInfo`` from the ``backports.zoneinfo`` package.
  This makes ``ZoneInfo`` support work for Python < 3.9.

2.7.0 (2022-05-11)
------------------

* Support Python 3.11 (no wheels yet, they will only be available when Python 3.11 is RC when the ABI is stable).

2.6.0 (2022-01-10)
------------------

* Drop Python 3.6 support.

2.5.0 (2021-12-14)
------------------

* Add ``time_machine.escape_hatch``, which provides functions to bypass time-machine.

  Thanks to Matt Pegler for the feature request in `Issue #206 <https://github.com/adamchainz/time-machine/issues/206>`__.

2.4.1 (2021-11-27)
------------------

* Build musllinux wheels.

2.4.0 (2021-09-01)
------------------

* Support Python 3.10.

2.3.1 (2021-07-13)
------------------

* Build universal2 wheels for Python 3.8 on macOS.

2.3.0 (2021-07-05)
------------------

* Allow passing ``tick`` to ``Coordinates.move_to()`` and the pytest fixture’s
  ``time_machine.move_to()``. This allows freezing or unfreezing of time when
  travelling.

2.2.0 (2021-07-02)
------------------

* Include type hints.

* Convert C module to use PEP 489 multi-phase extension module initialization.
  This makes the module ready for Python sub-interpreters.

* Release now includes a universal2 wheel for Python 3.9 on macOS, to work on
  Apple Silicon.

* Stop distributing tests to reduce package size. Tests are not intended to be
  run outside of the tox setup in the repository. Repackagers can use GitHub's
  tarballs per tag.

2.1.0 (2021-02-19)
------------------

* Release now includes wheels for ARM on Linux.

2.0.1 (2021-01-18)
------------------

* Prevent ``ImportError`` on Windows where ``time.tzset()`` is unavailable.

2.0.0 (2021-01-17)
------------------

* Release now includes wheels for Windows and macOS.
* Move internal calculations to use nanoseconds, avoiding a loss of precision.
* After a call to ``move_to()``, the first function call to retrieve the
  current time will return exactly the destination time, copying the behaviour
  of the first call to ``travel()``.
* Add the ability to shift timezone by passing in a ``ZoneInfo`` timezone.
* Remove ``tz_offset`` argument. This was incorrectly copied from
  ``freezegun``. Use the new timezone mocking with ``ZoneInfo`` instead.
* Add pytest plugin and fixture ``time_machine``.
* Work with Windows’ different epoch.

1.3.0 (2020-12-12)
------------------

* Support Python 3.9.
* Move license from ISC to MIT License.

1.2.1 (2020-08-29)
------------------

* Correctly return naive datetimes from ``datetime.utcnow()`` whilst time
  travelling.

  Thanks to Søren Pilgård and Bart Van Loon for the report in
  `Issue #52 <https://github.com/adamchainz/time-machine/issues/52>`__.

1.2.0 (2020-07-08)
------------------

* Add ``move_to()`` method to move to a different time whilst travelling.
  This is based on freezegun's ``move_to()`` method.

1.1.1 (2020-06-22)
------------------

* Move C-level ``clock_gettime()`` and ``clock_gettime_ns()`` checks to
  runtime to allow distribution of macOS wheels.

1.1.0 (2020-06-08)
------------------

* Add ``shift()`` method to move forward in time by a delta whilst travelling.
  This is based on freezegun's ``tick()`` method.

  Thanks to Alex Subbotin for the feature in
  `PR #27 <https://github.com/adamchainz/time-machine/pull/27>`__.

* Fix to work when either ``clock_gettime()`` or ``CLOCK_REALTIME`` is not
  present. This happens on some Unix platforms, for example on macOS with the
  official Python.org installer, which is compiled against macOS 10.9.

  Thanks to Daniel Crowe for the fix in
  `PR #30 <https://github.com/adamchainz/time-machine/pull/30>`__.

1.0.1 (2020-05-29)
------------------

* Fix ``datetime.now()`` behaviour with the ``tz`` argument when not time-travelling.

1.0.0 (2020-05-29)
------------------

* First non-beta release.
* Added support for ``tz_offset`` argument.
* ``tick=True`` will only start time ticking after the first method return that retrieves the current time.
* Added nestability of ``travel()``.
* Support for ``time.time_ns()`` and ``time.clock_gettime_ns()``.

1.0.0b1 (2020-05-04)
--------------------

* First release on PyPI.
