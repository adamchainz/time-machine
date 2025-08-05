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

* ``from freezegun import freeze_time`` -> ``from time_machine import travel``

* In function decorators, class decorators, and context managers: ``freeze_time(...)`` -> ``travel(..., tick=False)``.
  This change is only applied when ``freeze_time()`` is called with a single positional argument.
  In context managers, it’s only applied when the result isn’t assigned to a variable with ``as``.

The tool is open to extension to cover other compatible changes—PRs welcome!
