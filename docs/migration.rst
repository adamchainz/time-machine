=======================================
Migrating from freezegun or libfaketime
=======================================

freezegun has a useful API, and python-libfaketime copies some of it, with a different function name.
time-machine also copies some of freezegun's API, in ``travel()``\'s ``destination``, and ``tick`` arguments, and the ``shift()`` method.
There are a few differences:

* time-machine's ``tick`` argument defaults to ``True``, because code tends to make the (reasonable) assumption that time progresses whilst running, and should normally be tested as such.
  Testing with time frozen can make it easy to write exact assertions, but it's quite artificial.
  Write assertions against time ranges, rather than against exact values.

* freezegun interprets dates and naive datetimes in the local time zone (including those parsed from strings with ``dateutil``).
  This means tests can pass when run in one time zone and fail in another.
  time-machine instead interprets dates and naive datetimes in UTC so they are fixed points in time.
  Provide time zones where required.

* freezegun's ``tick()`` method has been implemented as ``shift()``, to avoid confusion with the ``tick`` argument.
  It also requires an explicit delta rather than defaulting to 1 second.

* freezegun's ``tz_offset`` argument is not supported, since it only partially mocks the current time zone.
  Time zones are more complicated than a single offset from UTC, and freezegun only uses the offset in ``time.localtime()``.
  Instead, time-machine will mock the current time zone if you give it a ``datetime`` with a ``ZoneInfo`` timezone.

Some features aren't supported like the ``auto_tick_seconds`` argument.
These may be added in a future release.

If you are only fairly simple function calls, you should be able to migrate by replacing calls to ``freezegun.freeze_time()`` and ``libfaketime.fake_time()`` with ``time_machine.travel()``.

.. _migration-cli:

Migration CLI
=============

time-machine comes with a command-line interface to help you migrate from freezegun.
It performs partial replacements on your code to update it to use time-machine's API.
It may leave your code in a broken state, for example where an import of ``freezegun`` has been replaced but calls using it remain—it’s recommended you have a good linting setup to find these, and then you can manually fix them up.

The tool edits files in place, reporting those that it changes.
It’s recommended you start from a clean, committed state in your version control system, so you can easily revert any broken changes.

Run with uv
-----------

If you have `uv <https://docs.astral.sh/uv/>`__ installed, you can use its ``uvx`` command to install and run the tool in one go:

.. code-block:: console

    $ uvx --from 'time-machine[cli]' python -m time_machine migrate example/tests.py

Replace ``example/tests.py`` with one or more target files.

Run directly
------------

To install the tool before using it, first install time-machine with its ``cli`` extra.
For example, with Pip:

.. code-block:: console

    $ python -m pip install time-machine[cli]

Then, run the ``migrate`` subcommand of the module on target files:

.. code-block:: console

    $ python -m time_machine migrate example/tests.py
    Rewriting example/tests.py

Replace ``example/tests.py`` with one or more target files.

Run against multiple files
--------------------------

To run the tool against all files from your Git repository, follow `this blog post <https://adamj.eu/tech/2022/03/09/how-to-run-a-command-on-many-files-in-your-git-repository/>`__.

Changes
-------

The changes the tool makes are:

* ``import freezegun`` -> ``import time_machine``

* ``from freezegun import freeze_time`` -> ``import time_machine``

* Aliased imports like ``import freezegun as fg`` or ``from freezegun import freeze_time as ft`` -> ``import time_machine``.
  The alias is dropped, since calls using it are migrated to use the ``time_machine`` module, per the below.

* ``from freezegun import freeze_time, FakeDate`` -> ``import time_machine`` plus ``from freezegun import FakeDate``, keeping the other imported names.

* In function decorators, class decorators, and context managers: ``freeze_time(...)`` -> ``travel(...)``.
  This change is applied only when ``freeze_time()`` is called with a single positional argument and only supported keyword arguments: ``tick``, ``tz_offset`` with a literal zero value, and ``real_asyncio``.
  If ``tick`` is passed, it is kept as-is, otherwise it is replaced with ``tick=False`` (matching freezegun’s default behaviour).
  ``tz_offset=0`` is dropped, since a zero offset has no effect.
  ``real_asyncio`` is dropped, whatever its value, since time-machine does not mock ``time.monotonic()``, so asyncio event loops always see real time.

* In context managers that bind the result with ``as``, additionally: calls of the bound variable’s ``tick()`` method -> ``shift()``, with freezegun’s default delta of one second made explicit, for example ``ft.tick()`` -> ``ft.shift(1)``.
  Calls of the ``move_to()`` method are left unchanged, since it behaves the same in both libraries.
  These changes are only applied when the bound variable is used solely for ``move_to()`` calls and ``tick()`` calls as statements, since ``tick()`` returns the new time whilst ``shift()`` returns ``None``, and other freezegun attributes have no equivalent on the object that ``travel()`` yields.

* The ``pytest.mark.freeze_time`` marker from `pytest-freezegun <https://pypi.org/project/pytest-freezegun/>`__ or `pytest-freezer <https://pypi.org/project/pytest-freezer/>`__: ``@pytest.mark.freeze_time(...)`` -> ``@pytest.mark.time_machine(...)``, the marker from time-machine’s :doc:`pytest plugin <pytest_plugin>`.
  This migration uses the same argument handling as for ``freeze_time()`` calls.

  As well as in decorators, the marker is migrated in module-level and class-level ``pytestmark`` assignments, whether assigned alone or within a list or tuple of markers.

* The ``freezer`` fixture from pytest-freezegun or pytest-freezer -> the ``time_machine`` fixture from time-machine’s pytest plugin.
  In functions with an argument named ``freezer``, the argument is renamed to ``time_machine`` and calls of the fixture’s methods are migrated:

  * ``freezer.move_to(...)`` -> ``time_machine.move_to(..., tick=False)``, again matching freezegun’s default behaviour.
    ``tick=False`` isn’t added in functions using a migrated ``pytest.mark.freeze_time`` marker, since there the fixture inherits the ``tick`` behaviour from the marker.

  * ``freezer.tick()`` -> ``time_machine.shift(1)``, as for context manager variables, again only for calls as statements.

  Other uses of ``freezer`` are left unchanged, for your linter to flag.
  ``freeze_time()`` calls within such functions are also left unchanged, because the renamed argument shadows the ``time_machine`` module.

  Note that the ``time_machine`` fixture doesn’t mock the time until its ``move_to()`` method is called, unlike ``freezer``, which mocks from the start of the test.
  Migrated tests that relied on that, for example by calling ``freezer.tick()`` before any ``move_to()``, will need manual adjustment.

The tool is open to extension to cover other compatible changes—PRs welcome!
