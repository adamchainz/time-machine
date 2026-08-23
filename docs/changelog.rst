=========
Changelog
=========

Unreleased
----------

* Extend the :ref:`Migration CLI <migration-cli>` to migrate aliased imports: ``import freezegun as fg`` and ``from freezegun import freeze_time as ft``, plus calls using such aliases.

* Extend the :ref:`Migration CLI <migration-cli>` to migrate the ``pytest.mark.freeze_time`` marker in module-level and class-level ``pytestmark`` assignments.

* Extend the :ref:`Migration CLI <migration-cli>` to migrate ``freeze_time()`` calls and markers that pass ``tz_offset`` with a literal zero value.
  The argument is dropped, since a zero offset has no effect.

* Extend the :ref:`Migration CLI <migration-cli>` to migrate ``freeze_time()`` calls and markers that pass ``real_asyncio=True``.
  The argument is dropped, since time-machine does not mock ``time.monotonic()``, so asyncio event loops always see real time.

3.4.0 (2026-08-10)
------------------

* Publish wheels for Python 3.15.

  Thanks to Edgar Ramírez Mondragón in `PR #655 <https://github.com/adamchainz/time-machine/pull/655>`__.

* Fix a reference leak in the patched ``datetime.datetime.utcnow()`` that occurred when its Python 3.12+ ``DeprecationWarning`` was raised as an error, such as under ``-W error``.
  Each such call leaked a reference to the active traveller object.

  `PR #656 <https://github.com/adamchainz/time-machine/pull/656>`__.

* Extend the :ref:`Migration CLI <migration-cli>` to migrate patterns from freezegun’s pytest plugins, pytest-freezegun and pytest-freezer: the ``freezer`` fixture and the ``pytest.mark.freeze_time`` marker.
  Also make it migrate ``freeze_time()`` context managers that bind the result with ``as``, including converting ``tick()`` method calls to ``shift()``.

  `PR #658 <https://github.com/adamchainz/time-machine/pull/658>`__.
  Thanks to Javier Buzzi for the initial work in `PR #562 <https://github.com/adamchainz/time-machine/pull/562>`__.

* Fix the :ref:`Migration CLI <migration-cli>` to handle trailing commas in ``freeze_time()`` calls when adding ``tick=False``.
  Previously, it produced invalid syntax, like ``travel("2023-01-01",, tick=False)``.

  `PR #658 <https://github.com/adamchainz/time-machine/pull/658>`__.

* Fix the :ref:`Migration CLI <migration-cli>` to not indent imports kept from a rewritten from-import when the import doesn’t start its line, such as after ``if True:`` on one line.
  Previously, the kept import gained leading whitespace, producing invalid syntax.

  `PR #658 <https://github.com/adamchainz/time-machine/pull/658>`__.

3.3.1 (2026-08-04)
------------------

* Fix small rounding errors in destination calculations.

  Previously, time-machine computed destinations in floating-point seconds, which could lead to small rounding errors: up to a few hundred nanoseconds for present-day destinations, growing to several microseconds by the year 2500.
  This change fixes the pipeline to use integer nanoseconds throughout, so time-travel is precise for any supported date.

  `PR #651 <https://github.com/adamchainz/time-machine/pull/651>`__.

3.3.0 (2026-07-31)
------------------

* Support Python 3.15.

  `PR #631 <https://github.com/adamchainz/time-machine/pull/631>`__.

* Mock ``datetime.date.today()`` directly, for Python 3.15 support.

  Previously time-machine was mocked only indirectly, since CPython implemented it by calling ``cls.fromtimestamp(time.time())``.
  Python 3.15 added a fast path that reads the system clock directly (`CPython Issue #130980 <https://github.com/python/cpython/pull/130980>`__), so time travel no longer affected it, which the new mock fixes.
  Consequently, there are new :ref:`escape hatch <escape-hatch>` functions: ``escape_hatch.datetime.date.today()`` and ``escape_hatch.datetime.datetime.today()``.

  Thanks to Miro Hrončok and Karolina Surma for the report in `Issue #610 <https://github.com/adamchainz/time-machine/issues/610>`__, Lumír 'Frenzy' Balhar for the fix in `PR #618 <https://github.com/adamchainz/time-machine/pull/618>`__, and Maurycy Pawłowski-Wieroński for review

* Support isolated subinterpreters, as created by |concurrent.interpreters|__ on Python 3.14+.
  Previously, importing time-machine in an isolated subinterpreter failed with an ``ImportError``.

  .. |concurrent.interpreters| replace:: ``concurrent.interpreters``
  __ https://docs.python.org/3.14/library/concurrent.interpreters.html

  `PR #644 <https://github.com/adamchainz/time-machine/pull/644>`__.

* Move the intermediary functions that patched functions call from Python to C.
  This change reduces the overhead of calling patched functions like ``time.time()`` while time travelling, making them around 10-20% faster.

  `PR #643 <https://github.com/adamchainz/time-machine/pull/643>`__.

* Fix returning ``datetime`` subclasses from their ``now()`` and ``utcnow()`` methods while time travelling.
  Previously, time-machine would always return a plain ``datetime.datetime`` instance, rather than the subclass.

  `PR #643 <https://github.com/adamchainz/time-machine/pull/643>`__.

* Fix hiding of the ``DeprecationWarning`` from |datetime.utcnow()|__ on Python 3.12+ while time travelling.
  Previously, the mocked version of the function did not raise the warning at all, so deprecated calls could pass unnoticed in tests.
  The warning is attributed to the calling code, like the real function does.

  .. |datetime.utcnow()| replace:: ``datetime.utcnow()``
  __ https://docs.python.org/3/library/datetime.html#datetime.datetime.utcnow

  The :ref:`escape hatch <escape-hatch>` function ``escape_hatch.datetime.datetime.utcnow()`` also now attributes its warning to the calling code, rather than to a line within time-machine.

  `PR #649 <https://github.com/adamchainz/time-machine/pull/>`__.
  Thanks to Tamir Duberstein for the report in `Issue #445 <https://github.com/adamchainz/time-machine/issues/445>`__ and Anders Kaseorg for the initial implementation in `PR #486 <https://github.com/adamchainz/time-machine/pull/486>`__.

* Fix the standard |uuid|__ library functions ``uuid1()``, ``uuid6()``, and ``uuid7()`` to correctly generate values for the destination when time travels backwards.
  These functions cache the timestamp of the value they generated most recently, and never generate a value stamped before it.
  Previously, after time-travelling backwards, these functions would keep generating values stamped for the cached timestamp, rather than the new destination.
  The caches are now reset whenever time travel starts, stops, or moves backwards.

  .. |uuid| replace:: ``uuid``
  __ https://docs.python.org/3/library/uuid.html

  `PR #648 <https://github.com/adamchainz/time-machine/pull/648>`__.
  Thanks to Diego Carrasco for the report in `Issue #601 <https://github.com/adamchainz/time-machine/issues/601>`__ and initial work in `PR #597 <https://github.com/adamchainz/time-machine/pull/597>`__.

* Build with frame pointers enabled, preparation for `PEP 831 <https://peps.python.org/pep-0831/>`__.

  `PR #627 <https://github.com/adamchainz/time-machine/issues/627>`__.

* Stop shipping wheels for 32-bit Linux and Windows.

  `PR #605 <https://github.com/adamchainz/time-machine/pull/605>`__.

* Stop shipping wheels for free-threaded Python 3.13 since `cibuildwheel 4.0.0 dropped support for building them <https://iscinumpy.dev/post/cibuildwheel-4-0-0/>`__.

* Extend the :ref:`Migration CLI <migration-cli>` to update ``freeze_time()`` calls that pass ``tick``.

  Thanks to George-Cristian Birzan for the report in `Issue #609 <https://github.com/adamchainz/time-machine/issues/609>`__ and tanren for the fix in `PR #636 <https://github.com/adamchainz/time-machine/pull/636>`__.

* Extend the :ref:`Migration CLI <migration-cli>` to rewrite ``freeze_time()`` decorators on async functions.

  Thanks to George-Cristian Birzan for the report in `Issue #608 <https://github.com/adamchainz/time-machine/issues/608>`__ and Sanjay Santhanam for the fix in `PR #640 <https://github.com/adamchainz/time-machine/pull/640>`__.

* Fix the :ref:`Migration CLI <migration-cli>` to leave relative imports called ``freezegun`` alone.
  Previously it rewrote ``from .freezegun import freeze_time``, which imports from a local module that happens to share freezegun’s name.

  `PR #645 <https://github.com/adamchainz/time-machine/pull/645>`__.

* Extend the :ref:`Migration CLI <migration-cli>` to rewrite from-imports that import ``freeze_time`` alongside other names.
  For example, ``from freezegun import freeze_time, FakeDate`` now becomes ``import time_machine`` plus ``from freezegun import FakeDate``.

  `PR #647 <https://github.com/adamchainz/time-machine/pull/647>`__.

3.2.0 (2025-12-17)
------------------

* Add :attr:`time_machine.naive_mode` to control how time-machine interprets naive datetimes.

  The default mode is ``MIXED``, which preserves existing behaviour: naive ``datetime`` objects and ``date`` objects are interpreted as UTC, while naive datetime strings are interpreted as local time.

  Three alternative modes are available:

  * ``UTC``: naive datetimes are always interpreted as UTC.
  * ``LOCAL``: naive datetimes are interpreted as local time, matching Python's default semantics, and freezegun.
  * ``ERROR``: naive datetimes raise a ``RuntimeError``, ensuring your tests are isolated from the current timezone.

  .. note::

    It’s recommended you use ``LOCAL`` or ``ERROR`` to avoid confusion around naive datetimes.

  `PR #591 <https://github.com/adamchainz/time-machine/pull/591>`__. Thanks to Paolo Melchiorre for review.

  Thanks to PhML, Stefaan Lippens, Matthieu Rigal, Nikita Demir, Steve Mavens, Andy Freeland, and Paul Ganssle for their input on `Issue #257 <https://github.com/adamchainz/time-machine/issues/257>`__.

* Raise ``RuntimeError`` when attempting to start time travelling if `freezegun <https://pypi.org/project/freezegun/>`__ is active.

  This change should help avoid surprises when migrating complex test suites from freezegun to time-machine.

  `PR #590 <https://github.com/adamchainz/time-machine/pull/590>`__.

3.1.0 (2025-11-21)
------------------

* Optimize patching of ``uuid`` module.
  By avoiding using ``unittest.mock``, this small overhead from starting ``time_machine.travel()`` has been reduced about 20x, from ~600ns to ~30ns by one benchmark.

  `PR #585 <https://github.com/adamchainz/time-machine/pull/585>`__.

3.0.0 (2025-11-18)
------------------

* Remove mocking of ``time.monotonic()`` and ``time.monotonic_ns()``.

  This mocking caused too many issues, such as causing freezes in asyncio event loops (`Issue #387 <https://github.com/adamchainz/time-machine/issues/387>`__), preventing pytest-durations from timing tests correctly (`Issue #505 <https://github.com/adamchainz/time-machine/issues/505>`__), and triggering timeouts in psycopg (`Issue #509 <https://github.com/adamchainz/time-machine/issues/509>`__).
  The root cause here is that mocking the monotonic clock breaks its contract, allowing it to move backwards when it’s meant to only move forwards.

  As an alternative, use |unittest.mock|__ to mock the monotonic function for the specific tested modules that need it.
  That means that your code should import ``monotonic()`` or ``monotonic_ns()`` directly, so that your tests can mock it in those places only.
  For example, if your system under test looks like:

  .. |unittest.mock| replace:: ``unittest.mock``
  __ https://docs.python.org/3/library/unittest.mock.html

  .. code-block:: python

      # example.py
      from time import monotonic


      def measurement():
          start = monotonic()
          ...
          end = monotonic()
          return end - start

  …then your tests can mock ``monotonic()`` like this:

  .. code-block:: python

      from unittest import TestCase, mock

      import example


      class MeasurementTests(TestCase):
          def test_success(self):
              with mock.patch.object(example, "monotonic", side_effect=[0.0, 1.23]):
                  result = example.measurement()
              assert result == 1.23

  `PR #560 <https://github.com/adamchainz/time-machine/pull/560>`__.

* Parse ``str`` destinations with |datetime.fromisoformat()|__ first, before falling back to dateutil if installed.
  ``datetime.fromisoformat()`` can parse most valid ISO 8601 formats, with better performance and no extra dependencies.

  .. |datetime.fromisoformat()| replace:: ``datetime.fromisoformat()``
  __ https://docs.python.org/3/library/datetime.html#datetime.datetime.fromisoformat

  `PR #578 <https://github.com/adamchainz/time-machine/pull/578>`__.

* Make the dependency on `dateutil <https://dateutil.readthedocs.io/en/stable/>`__ optional.
  To include dateutil support, install with the ``dateutil`` extra:

  .. code-block:: sh

      python -m pip install time-machine[dateutil]

  Beware that some of the formats that dateutil parses are ambiguous and may lead to unexpected results.

  `PR #576 <https://github.com/adamchainz/time-machine/pull/576>`__.

* Rename the ``Coordinates`` class to ``Traveller``, to match the recommended context manager variable name.

  Thanks to Matt Wang in `PR #535 <https://github.com/adamchainz/time-machine/pull/535>`__.

* Drop Python 3.9 support.

* Make the ``escape_hatch`` functions raise ``ValueError`` when called outside of time-travelling, rather than triggering segmentation faults.

  `PR #580 <https://github.com/adamchainz/time-machine/pull/580>`__.

2.19.0 (2025-08-19)
-------------------

* Add marker support to :doc:`the pytest plugin <pytest_plugin>`.
  Decorate tests with ``@pytest.mark.time_machine(<destination>)`` to set time during a test, affecting function-level fixtures as well.

  Thanks to Javier Buzzi in `PR #499 <https://github.com/adamchainz/time-machine/pull/499>`__.

* Add asynchronous context manager support to ``time_machine.travel()``.
  You can now use ``async with time_machine.travel(...):`` in asynchronous code, per :ref:`the documentation <travel-context-manager>`.

  `PR #556 <https://github.com/adamchainz/time-machine/issues/556>`__.

* Import date and time functions once in the C extension.

  This should improve speed a little bit, and avoid segmentation faults when the functions have been swapped out, such as when freezegun is in effect.
  (time-machine still won’t apply if freezegun is in effect.)

  `PR #555 <https://github.com/adamchainz/time-machine/issues/555>`__.

2.18.0 (2025-08-18)
-------------------

* Update the :ref:`migration CLI <migration-cli>` to detect unittest classes based on whether they use ``self.assert*`` methods like ``self.assertEqual()``.

* Fix free-threaded Python warning: ``RuntimeWarning: The global interpreter lock (GIL) has been enabled...`` as seen on Python 3.13+.

  Thanks to Javier Buzzi in `PR #531 <https://github.com/adamchainz/time-machine/pull/531>`__.

* Add support to ``travel()`` for ``datetime`` destinations with ``tzinfo`` set to ``datetime.UTC`` (``datetime.timezone.utc``).

  Thanks to Lawrence Law in `PR #502 <https://github.com/adamchainz/time-machine/pull/502>`__.

* Prevent segmentation faults in unlikely scenarios, such as if the ``time_machine`` module cannot be imported.

  `PR #543 <https://github.com/adamchainz/time-machine/pull/543>`__, `PR #545 <https://github.com/adamchainz/time-machine/pull/545>`__.

* Make ``travel()`` fully unpatch date and time functions when travel ends. This may fix certain edge cases.

  `Issue #532 <https://github.com/adamchainz/time-machine/issues/532>`__.

2.17.0 (2025-08-05)
-------------------

* Include wheels for Python 3.14.

  Thanks to Edgar Ramírez Mondragón in `PR #521 <https://github.com/adamchainz/time-machine/pull/521>`__.

* Support free-threaded Python.

  Thanks to Javier Buzzi in `PR #500 <https://github.com/adamchainz/time-machine/pull/500>`__.

* Add a new CLI for migrating code from freezegun to time-machine.

  Install with ``pip install time-machine[cli]`` and run with ``python -m time_machine migrate``.

  See more :ref:`in the documentation <migration-cli>`.

* Move the documentation to `Read the Docs <https://time-machine.readthedocs.io/>`__, and add a retro-futuristic logo.

2.16.0 (2024-10-08)
-------------------

* Drop Python 3.8 support.

2.15.0 (2024-08-06)
-------------------

* Include wheels for Python 3.13.

2.14.2 (2024-06-29)
-------------------

* Fix ``SystemError`` on Python 3.13 and Windows when starting time travelling.

  Thanks to Bernát Gábor for the report in `Issue #456 <https://github.com/adamchainz/time-machine/issues/456>`__.

2.14.1 (2024-03-22)
-------------------

* Fix segmentation fault when the first ``travel()`` call in a process uses a ``timedelta``.

  Thanks to Marcin Sulikowski for the report in `Issue #431 <https://github.com/adamchainz/time-machine/issues/431>`__.

2.14.0 (2024-03-03)
-------------------

* Fix ``utcfromtimestamp()`` warning on Python 3.12+.

  Thanks to Konstantin Baikov in `PR #424 <https://github.com/adamchainz/time-machine/pull/424>`__.

* Fix class decorator for classmethod overrides.

  Thanks to Pavel Bitiukov for the reproducer in `PR #404 <https://github.com/adamchainz/time-machine/pull/404>`__.

* Avoid calling deprecated ``uuid._load_system_functions()`` on Python 3.9+.

  Thanks to Nikita Sobolev for the ping in `CPython Issue #113308 <https://github.com/python/cpython/issues/113308>`__.

* Support Python 3.13 alpha 4.

  Thanks to Miro Hrončok in `PR #409 <https://github.com/adamchainz/time-machine/pull/409>`__.

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
