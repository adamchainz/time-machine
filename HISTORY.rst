History
=======

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
