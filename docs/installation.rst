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
