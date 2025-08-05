==========
Comparison
==========

There are some prior libraries that try to achieve the same thing, with their own strengths and weaknesses.
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
