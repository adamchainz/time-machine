=======
History
=======

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
