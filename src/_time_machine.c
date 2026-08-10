#include "Python.h"
#include <limits.h>
#include <stdlib.h>

// Module state
typedef struct {
    // Imported objects
    PyObject *datetime_module;
    PyObject *time_module;
    PyObject *datetime_class;
    PyObject *timezone_utc;
    PyObject *str_traveller_stack;
    PyObject *str_time_ns;
    PyObject *str_replace;
    PyObject *str_fromtimestamp;
    PyObject *tzinfo_kwnames;
    PyObject *microsecond_kwnames;
    PyObject *nanoseconds_per_second;
    PyObject *nanoseconds_per_microsecond;
    PyObject *microseconds_per_second;
    PyCFunctionObject *datetime_datetime_now;
    PyCFunctionObject *datetime_datetime_utcnow;
    PyCFunctionObject *date_today;
    PyCFunctionObject *time_clock_gettime;
    PyCFunctionObject *time_clock_gettime_ns;
    PyCFunctionObject *time_gmtime;
    PyCFunctionObject *time_localtime;
    PyCFunctionObject *time_strftime;
    PyCFunctionObject *time_time;
    PyCFunctionObject *time_time_ns;
    // Whether this interpreter has patched the date and time functions
    int patched;
} _time_machine_state;

static inline _time_machine_state *
get_time_machine_state(PyObject *module)
{
    void *state = PyModule_GetState(module);
    assert(state != NULL);
    return (_time_machine_state *)state;
}

/*
    Original method pointers from the patched date and time functions. These
    point to static C functions shared by every interpreter's copy of the
    datetime and time modules, so, unlike Python objects, they are safe to
    store in process-wide statics. They are captured at the first patch() and
    never reset, since unpatched method defs always hold these same pointers.
*/
#if PY_VERSION_HEX >= 0x030d00a4
static PyCFunctionFastWithKeywords original_now = NULL;
#else
static _PyCFunctionFastWithKeywords original_now = NULL;
#endif
static PyCFunction original_utcnow = NULL;
static PyCFunction original_date_today = NULL;
static PyCFunction original_clock_gettime = NULL;
static PyCFunction original_clock_gettime_ns = NULL;
static PyCFunction original_gmtime = NULL;
static PyCFunction original_localtime = NULL;
static PyCFunction original_strftime = NULL;
static PyCFunction original_time = NULL;
static PyCFunction original_time_ns = NULL;

// time.CLOCK_REALTIME, the same for every interpreter. Not always available,
// e.g. on builds against old macOS = official Python.org installer.
static int have_clock_realtime = 0;
static long clock_realtime = 0;

/*
    Mutex serializing patch() and unpatch() across interpreters, which may
    run concurrently under per-interpreter GILs (Python 3.12+) or
    free-threading. Use natively static-initializable locks since PyMutex is
    only available on Python 3.13+. The critical sections only read and write
    C pointers, making no blocking calls, so holding a (shared) GIL whilst
    waiting for this mutex cannot deadlock.
*/
#ifdef MS_WINDOWS
#include <windows.h>
static SRWLOCK patch_mutex = SRWLOCK_INIT;
static inline void
patch_mutex_lock(void)
{
    AcquireSRWLockExclusive(&patch_mutex);
}
static inline void
patch_mutex_unlock(void)
{
    ReleaseSRWLockExclusive(&patch_mutex);
}
#else
#include <pthread.h>
static pthread_mutex_t patch_mutex = PTHREAD_MUTEX_INITIALIZER;
static inline void
patch_mutex_lock(void)
{
    pthread_mutex_lock(&patch_mutex);
}
static inline void
patch_mutex_unlock(void)
{
    pthread_mutex_unlock(&patch_mutex);
}
#endif

/*
    Helpers for the patched functions. These functions are swapped into other
    modules' functions, so they don't receive this module as 'self'. Instead
    they look for the time_machine module in sys.modules and this module's
    state through its `_time_machine` attribute. This finds the state of the
    current interpreter's copy of the module, so all cached objects are only
    used within the interpreter that created them.
*/

/*
    Return the current interpreter's active traveller,
    time_machine.traveller_stack[-1], as a new reference, and set *state to
    the current interpreter's module state.

    Return NULL, with no exception set, if the current interpreter is not
    time travelling: because time_machine is not imported in it, or no travel
    is in progress. Patching applies process-wide, so this happens when
    another interpreter is travelling and this one is not. Callers should
    then fall back to the original functions.
*/
static PyObject *
_time_machine_current_traveller(_time_machine_state **state)
{
    PyObject *name = PyUnicode_FromString("time_machine");
    if (name == NULL) {
        PyErr_Clear();
        return NULL;
    }
    // Only look in sys.modules, to avoid triggering an import of
    // time_machine in interpreters that don't use it.
    PyObject *time_machine_module = PyImport_GetModule(name);
    Py_DECREF(name);
    if (time_machine_module == NULL) {
        PyErr_Clear();
        return NULL;
    }

    PyObject *c_module = PyObject_GetAttrString(time_machine_module, "_time_machine");
    if (c_module == NULL) {
        PyErr_Clear();
        Py_DECREF(time_machine_module);
        return NULL;
    }
    *state = (_time_machine_state *)PyModule_GetState(c_module);
    // The references in sys.modules and the time_machine module keep this
    // module, and thus its state, alive.
    Py_DECREF(c_module);
    if (*state == NULL || (*state)->str_traveller_stack == NULL) {
        PyErr_Clear();
        Py_DECREF(time_machine_module);
        return NULL;
    }

    PyObject *traveller_stack =
        PyObject_GetAttr(time_machine_module, (*state)->str_traveller_stack);
    Py_DECREF(time_machine_module);
    if (traveller_stack == NULL) {
        PyErr_Clear();
        return NULL;
    }
    PyObject *traveller = PySequence_GetItem(traveller_stack, -1);
    Py_DECREF(traveller_stack);
    if (traveller == NULL) {
        PyErr_Clear();
        return NULL;
    }
    return traveller;
}

/* Call traveller.time_ns() */
static PyObject *
_time_machine_traveller_time_ns(PyObject *traveller, _time_machine_state *state)
{
    return PyObject_VectorcallMethod(
        state->str_time_ns, &traveller, 1 | PY_VECTORCALL_ARGUMENTS_OFFSET, NULL);
}

/* Compute traveller.time_ns() / NANOSECONDS_PER_SECOND */
static PyObject *
_time_machine_traveller_time(PyObject *traveller, _time_machine_state *state)
{
    PyObject *time_ns = _time_machine_traveller_time_ns(traveller, state);
    if (time_ns == NULL) {
        return NULL;
    }
    PyObject *result = PyNumber_TrueDivide(time_ns, state->nanoseconds_per_second);
    Py_DECREF(time_ns);
    return result;
}

/* Compute traveller.time_ns() // NANOSECONDS_PER_SECOND */
static PyObject *
_time_machine_traveller_seconds(PyObject *traveller, _time_machine_state *state)
{
    PyObject *time_ns = _time_machine_traveller_time_ns(traveller, state);
    if (time_ns == NULL) {
        return NULL;
    }
    PyObject *result = PyNumber_FloorDivide(time_ns, state->nanoseconds_per_second);
    Py_DECREF(time_ns);
    return result;
}

/*
    Build the exact datetime for the traveller's current time:

        cls.fromtimestamp(seconds, tz).replace(microsecond=microseconds)
*/
static PyObject *
_time_machine_traveller_datetime(
    PyObject *cls, PyObject *tz, PyObject *traveller, _time_machine_state *state)
{
    PyObject *time_ns = _time_machine_traveller_time_ns(traveller, state);
    if (time_ns == NULL) {
        return NULL;
    }
    PyObject *total_microseconds =
        PyNumber_FloorDivide(time_ns, state->nanoseconds_per_microsecond);
    Py_DECREF(time_ns);
    if (total_microseconds == NULL) {
        return NULL;
    }
    PyObject *seconds_microseconds =
        PyNumber_Divmod(total_microseconds, state->microseconds_per_second);
    Py_DECREF(total_microseconds);
    if (seconds_microseconds == NULL) {
        return NULL;
    }
    PyObject *seconds = PyTuple_GET_ITEM(seconds_microseconds, 0);
    PyObject *microseconds = PyTuple_GET_ITEM(seconds_microseconds, 1);

    PyObject *fromtimestamp_stack[3] = {cls, seconds, tz};
    PyObject *whole_second = PyObject_VectorcallMethod(state->str_fromtimestamp,
        fromtimestamp_stack,
        3 | PY_VECTORCALL_ARGUMENTS_OFFSET,
        NULL);
    if (whole_second == NULL) {
        Py_DECREF(seconds_microseconds);
        return NULL;
    }

    PyObject *replace_stack[2] = {whole_second, microseconds};
    PyObject *result = PyObject_VectorcallMethod(state->str_replace,
        replace_stack,
        1 | PY_VECTORCALL_ARGUMENTS_OFFSET,
        state->microsecond_kwnames);
    Py_DECREF(whole_second);
    Py_DECREF(seconds_microseconds);
    return result;
}

/* datetime.datetime.now() */

static PyObject *
_time_machine_now(
    PyTypeObject *type, PyObject *const *args, Py_ssize_t nargs, PyObject *kwnames)

{
    _time_machine_state *state;
    PyObject *traveller = _time_machine_current_traveller(&state);
    if (traveller == NULL) {
        return original_now((PyObject *)type, args, nargs, kwnames);
    }

    PyObject *tz = Py_None;
    Py_ssize_t nkwargs = (kwnames != NULL) ? PyTuple_GET_SIZE(kwnames) : 0;
    for (Py_ssize_t i = 0; i < nkwargs; i++) {
        PyObject *name = PyTuple_GET_ITEM(kwnames, i);
        if (PyUnicode_CompareWithASCIIString(name, "tz") != 0) {
            PyErr_Format(
                PyExc_TypeError, "now() got an unexpected keyword argument '%U'", name);
            Py_DECREF(traveller);
            return NULL;
        }
        tz = args[nargs + i];
    }
    if (nargs + nkwargs > 1) {
        PyErr_Format(
            PyExc_TypeError, "now() takes at most 1 argument (%zd given)", nargs + nkwargs);
        Py_DECREF(traveller);
        return NULL;
    }
    if (nargs == 1) {
        tz = args[0];
    }

    PyObject *result =
        _time_machine_traveller_datetime((PyObject *)type, tz, traveller, state);
    Py_DECREF(traveller);
    return result;
}

static PyObject *
_time_machine_original_now(
    PyObject *module, PyObject *const *args, Py_ssize_t nargs, PyObject *kwnames)
{
    _time_machine_state *state = get_time_machine_state(module);

    if (!state->patched) {
        PyErr_SetString(PyExc_ValueError, "Not currently time-travelling.");
        return NULL;
    }

    PyObject *result = original_now(state->datetime_class, args, nargs, kwnames);

    return result;
}
PyDoc_STRVAR(original_now_doc,
    "original_now() -> datetime\n\
\n\
Call datetime.datetime.now() after patching.");

/* datetime.datetime.utcnow() */

/* Return aware.replace(tzinfo=None), stealing the reference to aware. */
static PyObject *
_time_machine_drop_tzinfo(PyObject *aware, _time_machine_state *state)
{
    PyObject *stack[2] = {aware, Py_None};
    PyObject *result = PyObject_VectorcallMethod(
        state->str_replace, stack, 1 | PY_VECTORCALL_ARGUMENTS_OFFSET, state->tzinfo_kwnames);
    Py_DECREF(aware);
    return result;
}

/*
    Copy Python 3.12’s DeprecationWarning for datetime.datetime.utcnow().
    Returns 0 on success, -1 with an exception set, like PyErr_WarnEx().
*/
static int
_time_machine_warn_utcnow_deprecated(Py_ssize_t stacklevel)
{
#if PY_VERSION_HEX >= 0x030c0000
    return PyErr_WarnEx(PyExc_DeprecationWarning,
        "datetime.datetime.utcnow() is deprecated and scheduled for removal in "
        "a future version. Use timezone-aware objects to represent datetimes "
        "in UTC: datetime.datetime.now(datetime.UTC).",
        stacklevel);
#else
    (void)stacklevel;
    return 0;
#endif
}

static PyObject *
_time_machine_utcnow(PyObject *cls, PyObject *args)
{
    _time_machine_state *state;
    PyObject *traveller = _time_machine_current_traveller(&state);
    if (traveller == NULL) {
        return original_utcnow(cls, args);
    }

    // Warn as the original function would, pointing at its caller.
    if (_time_machine_warn_utcnow_deprecated(1) < 0) {
        Py_DECREF(traveller);
        return NULL;
    }

    PyObject *aware =
        _time_machine_traveller_datetime(cls, state->timezone_utc, traveller, state);
    Py_DECREF(traveller);
    if (aware == NULL) {
        return NULL;
    }

    // aware.replace(tzinfo=None)
    return _time_machine_drop_tzinfo(aware, state);
}

static PyObject *
_time_machine_original_utcnow(PyObject *module, PyObject *args)
{
    _time_machine_state *state = get_time_machine_state(module);

    if (!state->patched) {
        PyErr_SetString(PyExc_ValueError, "Not currently time-travelling.");
        return NULL;
    }

    /*
        Warn pointing at the caller of the Python wrapper in time_machine that
        calls this function (stacklevel 2), rather than the wrapper itself.
    */
    if (_time_machine_warn_utcnow_deprecated(2) < 0) {
        return NULL;
    }

    /*
        Calling the original datetime.datetime.utcnow() would raise a second,
        misattributed DeprecationWarning on Python 3.12+. Use the original
        datetime.datetime.now(timezone.utc) instead, which is equivalent apart
        from returning an aware datetime.
    */
    PyObject *now_args[1] = {state->timezone_utc};
    PyObject *aware = original_now(state->datetime_class, now_args, 1, NULL);
    if (aware == NULL) {
        return NULL;
    }

    return _time_machine_drop_tzinfo(aware, state);
}
PyDoc_STRVAR(original_utcnow_doc,
    "original_utcnow() -> datetime\n\
\n\
Return what datetime.datetime.utcnow() would, after patching.");

/* datetime.date.today() and datetime.datetime.today()
 * Note: datetime.datetime doesn't define its own today(), it inherits from date.
 * So we patch date.today() with a wrapper that calls cls.fromtimestamp(), which
 * returns the right type for date, datetime, and subclasses of either.
 */

static PyObject *
_time_machine_today(PyObject *cls, PyObject *args)
{
    _time_machine_state *state;
    PyObject *traveller = _time_machine_current_traveller(&state);
    if (traveller == NULL) {
        return original_date_today(cls, args);
    }

    PyObject *timestamp = _time_machine_traveller_time(traveller, state);
    Py_DECREF(traveller);
    if (timestamp == NULL) {
        return NULL;
    }

    PyObject *stack[2] = {cls, timestamp};
    PyObject *result = PyObject_VectorcallMethod(
        state->str_fromtimestamp, stack, 2 | PY_VECTORCALL_ARGUMENTS_OFFSET, NULL);
    Py_DECREF(timestamp);
    return result;
}

/* time.clock_gettime() */

static PyObject *
_time_machine_clock_gettime(PyObject *self, PyObject *args)
{
#if PY_VERSION_HEX >= 0x030d00a2
    // METH_O - args is the clk_id itself
    PyObject *clk_id_obj = args;
#else
    // METH_VARARGS - args is a tuple
    PyObject *clk_id_obj = NULL;
    if (PyTuple_GET_SIZE(args) == 1) {
        clk_id_obj = PyTuple_GET_ITEM(args, 0);
    }
#endif

    if (clk_id_obj != NULL && PyLong_Check(clk_id_obj)) {
        int overflow = 0;
        long clk_id = PyLong_AsLongAndOverflow(clk_id_obj, &overflow);
        if (!overflow && have_clock_realtime && clk_id == clock_realtime) {
            _time_machine_state *state;
            PyObject *traveller = _time_machine_current_traveller(&state);
            if (traveller != NULL) {
                PyObject *result = _time_machine_traveller_time(traveller, state);
                Py_DECREF(traveller);
                return result;
            }
        }
        // Fall through: non-realtime clocks, out-of-range values, and
        // interpreters that are not travelling get the original function's
        // behaviour, including its error messages.
    }

    return original_clock_gettime(self, args);
}

static PyObject *
_time_machine_original_clock_gettime(PyObject *module, PyObject *args)
{
    _time_machine_state *state = get_time_machine_state(module);

    if (!state->patched) {
        PyErr_SetString(PyExc_ValueError, "Not currently time-travelling.");
        return NULL;
    }

    PyObject *result = original_clock_gettime(state->time_module, args);

    return result;
}
PyDoc_STRVAR(original_clock_gettime_doc,
    "original_clock_gettime() -> floating point number\n\
\n\
Call time.clock_gettime() after patching.");

/* time.clock_gettime_ns() */

static PyObject *
_time_machine_clock_gettime_ns(PyObject *self, PyObject *args)
{
#if PY_VERSION_HEX >= 0x030d00a2
    // METH_O - args is the clk_id itself
    PyObject *clk_id_obj = args;
#else
    // METH_VARARGS - args is a tuple
    PyObject *clk_id_obj = NULL;
    if (PyTuple_GET_SIZE(args) == 1) {
        clk_id_obj = PyTuple_GET_ITEM(args, 0);
    }
#endif

    if (clk_id_obj != NULL && PyLong_Check(clk_id_obj)) {
        int overflow = 0;
        long clk_id = PyLong_AsLongAndOverflow(clk_id_obj, &overflow);
        if (!overflow && have_clock_realtime && clk_id == clock_realtime) {
            _time_machine_state *state;
            PyObject *traveller = _time_machine_current_traveller(&state);
            if (traveller != NULL) {
                PyObject *result = _time_machine_traveller_time_ns(traveller, state);
                Py_DECREF(traveller);
                return result;
            }
        }
        // Fall through: non-realtime clocks, out-of-range values, and
        // interpreters that are not travelling get the original function's
        // behaviour, including its error messages.
    }

    return original_clock_gettime_ns(self, args);
}

static PyObject *
_time_machine_original_clock_gettime_ns(PyObject *module, PyObject *args)
{
    _time_machine_state *state = get_time_machine_state(module);

    if (!state->patched) {
        PyErr_SetString(PyExc_ValueError, "Not currently time-travelling.");
        return NULL;
    }

    PyObject *result = original_clock_gettime_ns(state->time_module, args);

    return result;
}
PyDoc_STRVAR(original_clock_gettime_ns_doc,
    "original_clock_gettime_ns() -> int\n\
\n\
Call time.clock_gettime_ns() after patching.");

/* time.gmtime() */

static PyObject *
_time_machine_gmtime(PyObject *self, PyObject *args)
{
    Py_ssize_t nargs = PyTuple_GET_SIZE(args);
    if (nargs > 1 || (nargs == 1 && PyTuple_GET_ITEM(args, 0) != Py_None)) {
        // Pass through, including invalid arguments for their error messages.
        return original_gmtime(self, args);
    }

    _time_machine_state *state;
    PyObject *traveller = _time_machine_current_traveller(&state);
    if (traveller == NULL) {
        return original_gmtime(self, args);
    }

    PyObject *timestamp = _time_machine_traveller_seconds(traveller, state);
    Py_DECREF(traveller);
    if (timestamp == NULL) {
        return NULL;
    }
    PyObject *new_args = PyTuple_Pack(1, timestamp);
    Py_DECREF(timestamp);
    if (new_args == NULL) {
        return NULL;
    }
    PyObject *result = original_gmtime(self, new_args);
    Py_DECREF(new_args);
    return result;
}

static PyObject *
_time_machine_original_gmtime(PyObject *module, PyObject *args)
{
    _time_machine_state *state = get_time_machine_state(module);

    if (!state->patched) {
        PyErr_SetString(PyExc_ValueError, "Not currently time-travelling.");
        return NULL;
    }

    PyObject *result = original_gmtime(state->time_module, args);

    return result;
}
PyDoc_STRVAR(original_gmtime_doc,
    "original_gmtime() -> floating point number\n\
\n\
Call time.gmtime() after patching.");

/* time.localtime() */

static PyObject *
_time_machine_localtime(PyObject *self, PyObject *args)
{
    Py_ssize_t nargs = PyTuple_GET_SIZE(args);
    if (nargs > 1 || (nargs == 1 && PyTuple_GET_ITEM(args, 0) != Py_None)) {
        // Pass through, including invalid arguments for their error messages.
        return original_localtime(self, args);
    }

    _time_machine_state *state;
    PyObject *traveller = _time_machine_current_traveller(&state);
    if (traveller == NULL) {
        return original_localtime(self, args);
    }

    PyObject *timestamp = _time_machine_traveller_seconds(traveller, state);
    Py_DECREF(traveller);
    if (timestamp == NULL) {
        return NULL;
    }
    PyObject *new_args = PyTuple_Pack(1, timestamp);
    Py_DECREF(timestamp);
    if (new_args == NULL) {
        return NULL;
    }
    PyObject *result = original_localtime(self, new_args);
    Py_DECREF(new_args);
    return result;
}

static PyObject *
_time_machine_original_localtime(PyObject *module, PyObject *args)
{
    _time_machine_state *state = get_time_machine_state(module);

    if (!state->patched) {
        PyErr_SetString(PyExc_ValueError, "Not currently time-travelling.");
        return NULL;
    }

    PyObject *result = original_localtime(state->time_module, args);

    return result;
}
PyDoc_STRVAR(original_localtime_doc,
    "original_localtime() -> floating point number\n\
\n\
Call time.localtime() after patching.");

/* time.strftime() */

static PyObject *
_time_machine_strftime(PyObject *self, PyObject *args)
{
    Py_ssize_t nargs = PyTuple_GET_SIZE(args);
    if (nargs < 1 || nargs > 2 || (nargs == 2 && PyTuple_GET_ITEM(args, 1) != Py_None)) {
        // Pass through, including invalid arguments for their error messages.
        return original_strftime(self, args);
    }

    _time_machine_state *state;
    PyObject *traveller = _time_machine_current_traveller(&state);
    if (traveller == NULL) {
        return original_strftime(self, args);
    }

    // time.strftime(format, time.localtime(traveller_seconds))
    PyObject *timestamp = _time_machine_traveller_seconds(traveller, state);
    Py_DECREF(traveller);
    if (timestamp == NULL) {
        return NULL;
    }
    PyObject *localtime_args = PyTuple_Pack(1, timestamp);
    Py_DECREF(timestamp);
    if (localtime_args == NULL) {
        return NULL;
    }
    PyObject *local_time = original_localtime(self, localtime_args);
    Py_DECREF(localtime_args);
    if (local_time == NULL) {
        return NULL;
    }
    PyObject *new_args = PyTuple_Pack(2, PyTuple_GET_ITEM(args, 0), local_time);
    Py_DECREF(local_time);
    if (new_args == NULL) {
        return NULL;
    }
    PyObject *result = original_strftime(self, new_args);
    Py_DECREF(new_args);
    return result;
}

static PyObject *
_time_machine_original_strftime(PyObject *module, PyObject *args)
{
    _time_machine_state *state = get_time_machine_state(module);

    if (!state->patched) {
        PyErr_SetString(PyExc_ValueError, "Not currently time-travelling.");
        return NULL;
    }

    PyObject *result = original_strftime(state->time_module, args);

    return result;
}
PyDoc_STRVAR(original_strftime_doc,
    "original_strftime() -> floating point number\n\
\n\
Call time.strftime() after patching.");

/* time.time() */

static PyObject *
_time_machine_time(PyObject *self, PyObject *args)
{
    _time_machine_state *state;
    PyObject *traveller = _time_machine_current_traveller(&state);
    if (traveller == NULL) {
        return original_time(self, args);
    }
    PyObject *result = _time_machine_traveller_time(traveller, state);
    Py_DECREF(traveller);
    return result;
}

static PyObject *
_time_machine_original_time(PyObject *module, PyObject *args)
{
    _time_machine_state *state = get_time_machine_state(module);

    if (!state->patched) {
        PyErr_SetString(PyExc_ValueError, "Not currently time-travelling.");
        return NULL;
    }

    PyObject *result = original_time(state->time_module, args);

    return result;
}
PyDoc_STRVAR(original_time_doc,
    "original_time() -> floating point number\n\
\n\
Call time.time() after patching.");

/* time.time_ns() */

static PyObject *
_time_machine_time_ns(PyObject *self, PyObject *args)
{
    _time_machine_state *state;
    PyObject *traveller = _time_machine_current_traveller(&state);
    if (traveller == NULL) {
        return original_time_ns(self, args);
    }
    PyObject *result = _time_machine_traveller_time_ns(traveller, state);
    Py_DECREF(traveller);
    return result;
}

static PyObject *
_time_machine_original_time_ns(PyObject *module, PyObject *args)
{
    _time_machine_state *state = get_time_machine_state(module);

    if (!state->patched) {
        PyErr_SetString(PyExc_ValueError, "Not currently time-travelling.");
        return NULL;
    }

    PyObject *result = original_time_ns(state->time_module, args);

    return result;
}
PyDoc_STRVAR(original_time_ns_doc,
    "original_time_ns() -> int\n\
\n\
Call time.time_ns() after patching.");

static PyObject *
_time_machine_patch(PyObject *module, PyObject *unused)
{
    _time_machine_state *state = PyModule_GetState(module);
    if (state == NULL) {
        return NULL;
    }

    patch_mutex_lock();

    if (state->patched) {
        patch_mutex_unlock();
        Py_RETURN_NONE;
    }

    /*
        Capture the original method pointers into the process-wide statics
        before swapping in the patched functions. The ml_meth checks make
        capture idempotent: if another interpreter has already patched, the
        patched functions are never captured as originals.
    */

    if (state->date_today->m_ml->ml_meth != _time_machine_today) {
        original_date_today = state->date_today->m_ml->ml_meth;
    }
    state->date_today->m_ml->ml_meth = _time_machine_today;

    if (state->datetime_datetime_now->m_ml->ml_meth != (PyCFunction)_time_machine_now) {
#if PY_VERSION_HEX >= 0x030d00a4
        original_now =
            (PyCFunctionFastWithKeywords)state->datetime_datetime_now->m_ml->ml_meth;
#else
        original_now =
            (_PyCFunctionFastWithKeywords)state->datetime_datetime_now->m_ml->ml_meth;
#endif
    }
    state->datetime_datetime_now->m_ml->ml_meth = (PyCFunction)_time_machine_now;

    if (state->datetime_datetime_utcnow->m_ml->ml_meth != _time_machine_utcnow) {
        original_utcnow = state->datetime_datetime_utcnow->m_ml->ml_meth;
    }
    state->datetime_datetime_utcnow->m_ml->ml_meth = _time_machine_utcnow;

    /*
        time.clock_gettime(), only available on Unix platforms.
    */
    if (state->time_clock_gettime != NULL) {
        if (state->time_clock_gettime->m_ml->ml_meth != _time_machine_clock_gettime) {
            original_clock_gettime = state->time_clock_gettime->m_ml->ml_meth;
        }
        state->time_clock_gettime->m_ml->ml_meth = _time_machine_clock_gettime;
    }

    /*
        time.clock_gettime_ns(), only available on Unix platforms.
    */
    if (state->time_clock_gettime_ns != NULL) {
        if (state->time_clock_gettime_ns->m_ml->ml_meth != _time_machine_clock_gettime_ns) {
            original_clock_gettime_ns = state->time_clock_gettime_ns->m_ml->ml_meth;
        }
        state->time_clock_gettime_ns->m_ml->ml_meth = _time_machine_clock_gettime_ns;
    }

    if (state->time_gmtime->m_ml->ml_meth != _time_machine_gmtime) {
        original_gmtime = state->time_gmtime->m_ml->ml_meth;
    }
    state->time_gmtime->m_ml->ml_meth = _time_machine_gmtime;

    if (state->time_localtime->m_ml->ml_meth != _time_machine_localtime) {
        original_localtime = state->time_localtime->m_ml->ml_meth;
    }
    state->time_localtime->m_ml->ml_meth = _time_machine_localtime;

    if (state->time_strftime->m_ml->ml_meth != _time_machine_strftime) {
        original_strftime = state->time_strftime->m_ml->ml_meth;
    }
    state->time_strftime->m_ml->ml_meth = _time_machine_strftime;

    if (state->time_time->m_ml->ml_meth != _time_machine_time) {
        original_time = state->time_time->m_ml->ml_meth;
    }
    state->time_time->m_ml->ml_meth = _time_machine_time;

    if (state->time_time_ns->m_ml->ml_meth != _time_machine_time_ns) {
        original_time_ns = state->time_time_ns->m_ml->ml_meth;
    }
    state->time_time_ns->m_ml->ml_meth = _time_machine_time_ns;

    state->patched = 1;

    patch_mutex_unlock();

    Py_RETURN_NONE;
}
PyDoc_STRVAR(patch_doc,
    "patch() -> None\n\
\n\
Swap in helpers.");

static PyObject *
_time_machine_unpatch(PyObject *module, PyObject *unused)
{
    _time_machine_state *state = PyModule_GetState(module);
    if (state == NULL) {
        return NULL;
    }

    patch_mutex_lock();

    if (!state->patched) {
        patch_mutex_unlock();
        Py_RETURN_NONE;
    }

    /*
        Restore the original method pointers from the process-wide statics,
        which are deliberately not reset: the patched functions use them to
        fall back for interpreters that are not travelling, which may be
        while another interpreter remains patched.
    */

    state->datetime_datetime_now->m_ml->ml_meth = (PyCFunction)original_now;

    state->datetime_datetime_utcnow->m_ml->ml_meth = original_utcnow;

    state->date_today->m_ml->ml_meth = original_date_today;

    /*
        time.clock_gettime(), only available on Unix platforms.
    */
    if (state->time_clock_gettime != NULL) {
        state->time_clock_gettime->m_ml->ml_meth = original_clock_gettime;
    }

    /*
        time.clock_gettime_ns(), only available on Unix platforms.
    */
    if (state->time_clock_gettime_ns != NULL) {
        state->time_clock_gettime_ns->m_ml->ml_meth = original_clock_gettime_ns;
    }

    state->time_gmtime->m_ml->ml_meth = original_gmtime;

    state->time_localtime->m_ml->ml_meth = original_localtime;

    state->time_strftime->m_ml->ml_meth = original_strftime;

    state->time_time->m_ml->ml_meth = original_time;

    state->time_time_ns->m_ml->ml_meth = original_time_ns;

    state->patched = 0;

    patch_mutex_unlock();

    Py_RETURN_NONE;
}
PyDoc_STRVAR(unpatch_doc,
    "unpatch() -> None\n\
\n\
Swap out helpers.");

PyDoc_STRVAR(module_doc, "_time_machine module");

static PyMethodDef module_functions[] = {
    {"original_now",
        (PyCFunction)_time_machine_original_now,
        METH_FASTCALL | METH_KEYWORDS,
        original_now_doc},
    {"original_utcnow",
        (PyCFunction)_time_machine_original_utcnow,
        METH_NOARGS,
        original_utcnow_doc},
#if PY_VERSION_HEX >= 0x030d00a2
    {"original_clock_gettime",
        (PyCFunction)_time_machine_original_clock_gettime,
        METH_O,
        original_clock_gettime_doc},
    {"original_clock_gettime_ns",
        (PyCFunction)_time_machine_original_clock_gettime_ns,
        METH_O,
        original_clock_gettime_ns_doc},
#else
    {"original_clock_gettime",
        (PyCFunction)_time_machine_original_clock_gettime,
        METH_VARARGS,
        original_clock_gettime_doc},
    {"original_clock_gettime_ns",
        (PyCFunction)_time_machine_original_clock_gettime_ns,
        METH_VARARGS,
        original_clock_gettime_ns_doc},
#endif
    {"original_gmtime",
        (PyCFunction)_time_machine_original_gmtime,
        METH_VARARGS,
        original_gmtime_doc},
    {"original_localtime",
        (PyCFunction)_time_machine_original_localtime,
        METH_VARARGS,
        original_localtime_doc},
    {"original_strftime",
        (PyCFunction)_time_machine_original_strftime,
        METH_VARARGS,
        original_strftime_doc},
    {"original_time",
        (PyCFunction)_time_machine_original_time,
        METH_NOARGS,
        original_time_doc},
    {"original_time_ns",
        (PyCFunction)_time_machine_original_time_ns,
        METH_NOARGS,
        original_time_ns_doc},
    {"patch", (PyCFunction)_time_machine_patch, METH_NOARGS, patch_doc},
    {"unpatch", (PyCFunction)_time_machine_unpatch, METH_NOARGS, unpatch_doc},
    {NULL, NULL} /* sentinel */
};

static int
_time_machine_exec(PyObject *module)
{
    _time_machine_state *state = get_time_machine_state(module);

    state->str_traveller_stack = PyUnicode_InternFromString("traveller_stack");
    if (state->str_traveller_stack == NULL) {
        goto error;
    }

    state->str_time_ns = PyUnicode_InternFromString("time_ns");
    if (state->str_time_ns == NULL) {
        goto error;
    }

    state->str_replace = PyUnicode_InternFromString("replace");
    if (state->str_replace == NULL) {
        goto error;
    }

    state->str_fromtimestamp = PyUnicode_InternFromString("fromtimestamp");
    if (state->str_fromtimestamp == NULL) {
        goto error;
    }

    PyObject *str_tzinfo = PyUnicode_InternFromString("tzinfo");
    if (str_tzinfo == NULL) {
        goto error;
    }
    state->tzinfo_kwnames = PyTuple_Pack(1, str_tzinfo);
    Py_DECREF(str_tzinfo);
    if (state->tzinfo_kwnames == NULL) {
        goto error;
    }

    state->nanoseconds_per_second = PyLong_FromLong(1000000000L);
    if (state->nanoseconds_per_second == NULL) {
        goto error;
    }

    PyObject *str_microsecond = PyUnicode_InternFromString("microsecond");
    if (str_microsecond == NULL) {
        goto error;
    }
    state->microsecond_kwnames = PyTuple_Pack(1, str_microsecond);
    Py_DECREF(str_microsecond);
    if (state->microsecond_kwnames == NULL) {
        goto error;
    }

    state->nanoseconds_per_microsecond = PyLong_FromLong(1000L);
    if (state->nanoseconds_per_microsecond == NULL) {
        goto error;
    }

    state->microseconds_per_second = PyLong_FromLong(1000000L);
    if (state->microseconds_per_second == NULL) {
        goto error;
    }

    state->datetime_module = PyImport_ImportModule("datetime");
    if (state->datetime_module == NULL) {
        goto error;
    }

    state->datetime_class = PyObject_GetAttrString(state->datetime_module, "datetime");
    if (state->datetime_class == NULL) {
        goto error;
    }

    state->datetime_datetime_now =
        (PyCFunctionObject *)PyObject_GetAttrString(state->datetime_class, "now");
    if (state->datetime_datetime_now == NULL) {
        goto error;
    }

    state->datetime_datetime_utcnow =
        (PyCFunctionObject *)PyObject_GetAttrString(state->datetime_class, "utcnow");
    if (state->datetime_datetime_utcnow == NULL) {
        goto error;
    }

    PyObject *timezone_class = PyObject_GetAttrString(state->datetime_module, "timezone");
    if (timezone_class == NULL) {
        goto error;
    }
    state->timezone_utc = PyObject_GetAttrString(timezone_class, "utc");
    Py_DECREF(timezone_class);
    if (state->timezone_utc == NULL) {
        goto error;
    }

    PyObject *date_class = PyObject_GetAttrString(state->datetime_module, "date");
    if (date_class == NULL) {
        goto error;
    }

    state->date_today = (PyCFunctionObject *)PyObject_GetAttrString(date_class, "today");
    Py_DECREF(date_class);
    if (state->date_today == NULL) {
        goto error;
    }

    state->time_module = PyImport_ImportModule("time");
    if (state->time_module == NULL) {
        goto error;
    }

    PyObject *clock_realtime_obj =
        PyObject_GetAttrString(state->time_module, "CLOCK_REALTIME");
    if (clock_realtime_obj == NULL) {
        if (!PyErr_ExceptionMatches(PyExc_AttributeError)) {
            goto error;
        }
        // time.CLOCK_REALTIME is not always available, per the comment on
        // the have_clock_realtime static.
        PyErr_Clear();
    }
    else {
        clock_realtime = PyLong_AsLong(clock_realtime_obj);
        Py_DECREF(clock_realtime_obj);
        if (clock_realtime == -1 && PyErr_Occurred()) {
            goto error;
        }
        have_clock_realtime = 1;
    }

    state->time_clock_gettime =
        (PyCFunctionObject *)PyObject_GetAttrString(state->time_module, "clock_gettime");
    if (state->time_clock_gettime == NULL) {
        // time.clock_gettime() is only available on Unix platforms.
        if (PyErr_ExceptionMatches(PyExc_AttributeError)) {
            PyErr_Clear();
        }
        else {
            goto error;
        }
    }

    state->time_clock_gettime_ns =
        (PyCFunctionObject *)PyObject_GetAttrString(state->time_module, "clock_gettime_ns");
    if (state->time_clock_gettime_ns == NULL) {
        // time.clock_gettime_ns() is only available on Unix platforms.
        if (PyErr_ExceptionMatches(PyExc_AttributeError)) {
            PyErr_Clear();
        }
        else {
            goto error;
        }
    }

    state->time_gmtime =
        (PyCFunctionObject *)PyObject_GetAttrString(state->time_module, "gmtime");
    if (state->time_gmtime == NULL) {
        goto error;
    }

    state->time_localtime =
        (PyCFunctionObject *)PyObject_GetAttrString(state->time_module, "localtime");
    if (state->time_localtime == NULL) {
        goto error;
    }

    state->time_strftime =
        (PyCFunctionObject *)PyObject_GetAttrString(state->time_module, "strftime");
    if (state->time_strftime == NULL) {
        goto error;
    }

    state->time_time = (PyCFunctionObject *)PyObject_GetAttrString(state->time_module, "time");
    if (state->time_time == NULL) {
        goto error;
    }

    state->time_time_ns =
        (PyCFunctionObject *)PyObject_GetAttrString(state->time_module, "time_ns");
    if (state->time_time_ns == NULL) {
        goto error;
    }

    return 0;

error:
    Py_CLEAR(state->datetime_module);
    Py_CLEAR(state->datetime_class);
    Py_CLEAR(state->timezone_utc);
    Py_CLEAR(state->str_traveller_stack);
    Py_CLEAR(state->str_time_ns);
    Py_CLEAR(state->str_replace);
    Py_CLEAR(state->str_fromtimestamp);
    Py_CLEAR(state->tzinfo_kwnames);
    Py_CLEAR(state->microsecond_kwnames);
    Py_CLEAR(state->nanoseconds_per_second);
    Py_CLEAR(state->nanoseconds_per_microsecond);
    Py_CLEAR(state->microseconds_per_second);
    Py_CLEAR(state->datetime_datetime_now);
    Py_CLEAR(state->datetime_datetime_utcnow);
    Py_CLEAR(state->date_today);
    Py_CLEAR(state->time_module);
    Py_CLEAR(state->time_clock_gettime);
    Py_CLEAR(state->time_clock_gettime_ns);
    Py_CLEAR(state->time_gmtime);
    Py_CLEAR(state->time_localtime);
    Py_CLEAR(state->time_strftime);
    Py_CLEAR(state->time_time);
    Py_CLEAR(state->time_time_ns);
    return -1;
}

static int
_time_machine_traverse(PyObject *module, visitproc visit, void *arg)
{
    _time_machine_state *state = get_time_machine_state(module);
    Py_VISIT(state->datetime_module);
    Py_VISIT(state->datetime_class);
    Py_VISIT(state->timezone_utc);
    Py_VISIT(state->str_traveller_stack);
    Py_VISIT(state->str_time_ns);
    Py_VISIT(state->str_replace);
    Py_VISIT(state->str_fromtimestamp);
    Py_VISIT(state->tzinfo_kwnames);
    Py_VISIT(state->microsecond_kwnames);
    Py_VISIT(state->nanoseconds_per_second);
    Py_VISIT(state->nanoseconds_per_microsecond);
    Py_VISIT(state->microseconds_per_second);
    Py_VISIT(state->datetime_datetime_now);
    Py_VISIT(state->datetime_datetime_utcnow);
    Py_VISIT(state->date_today);
    Py_VISIT(state->time_module);
    Py_VISIT(state->time_clock_gettime);
    Py_VISIT(state->time_clock_gettime_ns);
    Py_VISIT(state->time_gmtime);
    Py_VISIT(state->time_localtime);
    Py_VISIT(state->time_strftime);
    Py_VISIT(state->time_time);
    Py_VISIT(state->time_time_ns);
    return 0;
}

static int
_time_machine_clear(PyObject *module)
{
    _time_machine_state *state = get_time_machine_state(module);
    Py_CLEAR(state->datetime_module);
    Py_CLEAR(state->datetime_class);
    Py_CLEAR(state->timezone_utc);
    Py_CLEAR(state->str_traveller_stack);
    Py_CLEAR(state->str_time_ns);
    Py_CLEAR(state->str_replace);
    Py_CLEAR(state->str_fromtimestamp);
    Py_CLEAR(state->tzinfo_kwnames);
    Py_CLEAR(state->microsecond_kwnames);
    Py_CLEAR(state->nanoseconds_per_second);
    Py_CLEAR(state->nanoseconds_per_microsecond);
    Py_CLEAR(state->microseconds_per_second);
    Py_CLEAR(state->datetime_datetime_now);
    Py_CLEAR(state->datetime_datetime_utcnow);
    Py_CLEAR(state->date_today);
    Py_CLEAR(state->time_module);
    Py_CLEAR(state->time_clock_gettime);
    Py_CLEAR(state->time_clock_gettime_ns);
    Py_CLEAR(state->time_gmtime);
    Py_CLEAR(state->time_localtime);
    Py_CLEAR(state->time_strftime);
    Py_CLEAR(state->time_time);
    Py_CLEAR(state->time_time_ns);
    return 0;
}

static PyModuleDef_Slot _time_machine_slots[] = {{Py_mod_exec, _time_machine_exec},
// On Python 3.12+, declare support for isolated subinterpreters, which may
// each import this module.
#if PY_VERSION_HEX >= 0x030c0000
    {Py_mod_multiple_interpreters, Py_MOD_PER_INTERPRETER_GIL_SUPPORTED},
#endif
// On Python 3.13+, declare free-threaded support.
// https://py-free-threading.github.io/porting-extensions/#declaring-free-threaded-support
#ifdef Py_GIL_DISABLED
    {Py_mod_gil, Py_MOD_GIL_NOT_USED},
#endif
    {0, NULL}};

static struct PyModuleDef _time_machine_module = {PyModuleDef_HEAD_INIT,
    .m_name = "_time_machine",
    .m_doc = module_doc,
    .m_size = sizeof(_time_machine_state),
    .m_methods = module_functions,
    .m_slots = _time_machine_slots,
    .m_traverse = _time_machine_traverse,
    .m_clear = _time_machine_clear};

PyMODINIT_FUNC
PyInit__time_machine(void)
{
    return PyModuleDef_Init(&_time_machine_module);
}
