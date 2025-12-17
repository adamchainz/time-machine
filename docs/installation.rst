============
Installation
============

Requirements
------------

Python 3.10 to 3.14 supported, including free-threaded variants from Python 3.13 onwards.

Only CPython is supported at this time because time-machine directly hooks into the C-level API.

Installation
------------

Use **pip**:

.. code-block:: sh

    python -m pip install time-machine

For support parsing strings as datetimes, include the ``dateutil`` extra:

.. code-block:: sh

    python -m pip install time-machine[dateutil]

For support running the :ref:`migration CLI <migration-cli>`, include the ``cli`` extra:

.. code-block:: sh

    python -m pip install time-machine[cli]

Consider setting naive mode
~~~~~~~~~~~~~~~~~~~~~~~~~~~

By default, time-machine has mixed behaviour for naive datetimes: it interprets naive ``datetime`` and ``date`` objects as UTC, but naive datetime strings as local time.
This mixed behaviour is probably surprising, is definitely regrettable, but is left, for now, for backwards compatibility.

When adding time-machine to a new project, consider changing :attr:`time_machine.naive_mode` to one of these clearer modes:

* ``NaiveMode.LOCAL`` - for consistency with Python’s default semantics, especially when migrating from freezegun.
* ``NaiveMode.ERROR`` - for maximum test reproducibility.

See :attr:`time_machine.naive_mode` for details.
