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
    // time.CLOCK_REALTIME, not always available, e.g. on builds against
    // old macOS = official Python.org installer
    int have_clock_realtime;
    long clock_realtime;
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
    // Original method pointers from date and time functions
#if PY_VERSION_HEX >= 0x030d00a4
    PyCFunctionFastWithKeywords original_now;
#else
    _PyCFunctionFastWithKeywords original_now;
#endif
    PyCFunction original_utcnow;
    PyCFunction original_date_today;
    PyCFunction original_clock_gettime;
    PyCFunction original_clock_gettime_ns;
    PyCFunction original_gmtime;
    PyCFunction original_localtime;
    PyCFunction original_strftime;
    PyCFunction original_time;
    PyCFunction original_time_ns;
} _time_machine_state;

static inline _time_machine_state *
get_time_machine_state(PyObject *module)
{
    void *state = PyModule_GetState(module);
    assert(state != NULL);
    return (_time_machine_state *)state;
}

/*
    Helpers for the patched functions. These functions are swapped into other
    modules' functions, so they don't receive this module as 'self' and
    instead find its state through sys.modules.
*/

// Constants used by the patched functions, initialized on first module exec
// and deliberately never freed, since the patched functions cannot access
// module state.
static PyObject *str_traveller_stack = NULL;
static PyObject *str_time_ns = NULL;
static PyObject *str_replace = NULL;
static PyObject *str_fromtimestamp = NULL;
static PyObject *tzinfo_kwnames = NULL;
static PyObject *nanoseconds_per_second = NULL;

static _time_machine_state *
_time_machine_get_module_state(void)
{
    PyObject *module = PyImport_ImportModule("_time_machine");
    if (module == NULL) {
        return NULL;  // Propagate ImportError
    }
    void *state = PyModule_GetState(module);
    // The reference in sys.modules keeps the module, and thus its state, alive.
    Py_DECREF(module);
    return (_time_machine_state *)state;
}

/* Call time_machine.traveller_stack[-1].time_ns() */
static PyObject *
_time_machine_traveller_time_ns(void)
{
    PyObject *time_machine_module = PyImport_ImportModule("time_machine");
    if (time_machine_module == NULL) {
        return NULL;  // Propagate ImportError
    }
    PyObject *traveller_stack = PyObject_GetAttr(time_machine_module, str_traveller_stack);
    Py_DECREF(time_machine_module);
    if (traveller_stack == NULL) {
        return NULL;  // Propagate AttributeError
    }

    PyObject *traveller = PySequence_GetItem(traveller_stack, -1);
    Py_DECREF(traveller_stack);
    if (traveller == NULL) {
        return NULL;  // Propagate IndexError
    }

    PyObject *result = PyObject_VectorcallMethod(
        str_time_ns, &traveller, 1 | PY_VECTORCALL_ARGUMENTS_OFFSET, NULL);
    Py_DECREF(traveller);
    return result;
}

/* Compute time_machine.traveller_stack[-1].time_ns() / NANOSECONDS_PER_SECOND */
static PyObject *
_time_machine_traveller_time(void)
{
    PyObject *time_ns = _time_machine_traveller_time_ns();
    if (time_ns == NULL) {
        return NULL;
    }
    PyObject *result = PyNumber_TrueDivide(time_ns, nanoseconds_per_second);
    Py_DECREF(time_ns);
    return result;
}

/* datetime.datetime.now() */

static PyObject *
_time_machine_now(
    PyTypeObject *type, PyObject *const *args, Py_ssize_t nargs, PyObject *kwnames)

{
    PyObject *tz = Py_None;
    Py_ssize_t nkwargs = (kwnames != NULL) ? PyTuple_GET_SIZE(kwnames) : 0;
    for (Py_ssize_t i = 0; i < nkwargs; i++) {
        PyObject *name = PyTuple_GET_ITEM(kwnames, i);
        if (PyUnicode_CompareWithASCIIString(name, "tz") != 0) {
            PyErr_Format(
                PyExc_TypeError, "now() got an unexpected keyword argument '%U'", name);
            return NULL;
        }
        tz = args[nargs + i];
    }
    if (nargs + nkwargs > 1) {
        PyErr_Format(
            PyExc_TypeError, "now() takes at most 1 argument (%zd given)", nargs + nkwargs);
        return NULL;
    }
    if (nargs == 1) {
        tz = args[0];
    }

    // cls.fromtimestamp(traveller_time, tz)
    PyObject *timestamp = _time_machine_traveller_time();
    if (timestamp == NULL) {
        return NULL;
    }
    PyObject *stack[3] = {(PyObject *)type, timestamp, tz};
    PyObject *result = PyObject_VectorcallMethod(
        str_fromtimestamp, stack, 3 | PY_VECTORCALL_ARGUMENTS_OFFSET, NULL);
    Py_DECREF(timestamp);
    return result;
}

static PyObject *
_time_machine_original_now(
    PyObject *module, PyObject *const *args, Py_ssize_t nargs, PyObject *kwnames)
{
    _time_machine_state *state = get_time_machine_state(module);

    if (state->original_now == NULL) {
        PyErr_SetString(PyExc_ValueError, "Not currently time-travelling.");
        return NULL;
    }

    PyObject *result = state->original_now(state->datetime_class, args, nargs, kwnames);

    return result;
}
PyDoc_STRVAR(original_now_doc,
    "original_now() -> datetime\n\
\n\
Call datetime.datetime.now() after patching.");

/* datetime.datetime.utcnow() */

/* Return aware.replace(tzinfo=None), stealing the reference to aware. */
static PyObject *
_time_machine_drop_tzinfo(PyObject *aware)
{
    PyObject *stack[2] = {aware, Py_None};
    PyObject *result = PyObject_VectorcallMethod(
        str_replace, stack, 1 | PY_VECTORCALL_ARGUMENTS_OFFSET, tzinfo_kwnames);
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
    _time_machine_state *state = _time_machine_get_module_state();
    if (state == NULL) {
        return NULL;
    }

    // Warn as the original function would, pointing at its caller.
    if (_time_machine_warn_utcnow_deprecated(1) < 0) {
        return NULL;
    }

    // cls.fromtimestamp(traveller_time, timezone.utc)
    PyObject *timestamp = _time_machine_traveller_time();
    if (timestamp == NULL) {
        return NULL;
    }
    PyObject *fromtimestamp_stack[3] = {cls, timestamp, state->timezone_utc};
    PyObject *aware = PyObject_VectorcallMethod(
        str_fromtimestamp, fromtimestamp_stack, 3 | PY_VECTORCALL_ARGUMENTS_OFFSET, NULL);
    Py_DECREF(timestamp);
    if (aware == NULL) {
        return NULL;
    }

    // aware.replace(tzinfo=None)
    return _time_machine_drop_tzinfo(aware);
}

static PyObject *
_time_machine_original_utcnow(PyObject *module, PyObject *args)
{
    _time_machine_state *state = get_time_machine_state(module);

    if (state->original_now == NULL) {
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
    PyObject *aware = state->original_now(state->datetime_class, now_args, 1, NULL);
    if (aware == NULL) {
        return NULL;
    }

    return _time_machine_drop_tzinfo(aware);
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
    PyObject *timestamp = _time_machine_traveller_time();
    if (timestamp == NULL) {
        return NULL;
    }

    PyObject *stack[2] = {cls, timestamp};
    PyObject *result = PyObject_VectorcallMethod(
        str_fromtimestamp, stack, 2 | PY_VECTORCALL_ARGUMENTS_OFFSET, NULL);
    Py_DECREF(timestamp);
    return result;
}

/* time.clock_gettime() */

static PyObject *
_time_machine_clock_gettime(PyObject *self, PyObject *args)
{
    _time_machine_state *state = _time_machine_get_module_state();
    if (state == NULL) {
        return NULL;
    }

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
        if (!overflow && state->have_clock_realtime && clk_id == state->clock_realtime) {
            return _time_machine_traveller_time();
        }
        // Fall through: non-realtime clocks, and out-of-range values, get the
        // original function's behaviour, including its error messages.
    }

    return state->original_clock_gettime(state->time_module, args);
}

static PyObject *
_time_machine_original_clock_gettime(PyObject *module, PyObject *args)
{
    _time_machine_state *state = get_time_machine_state(module);

    if (state->original_clock_gettime == NULL) {
        PyErr_SetString(PyExc_ValueError, "Not currently time-travelling.");
        return NULL;
    }

    PyObject *result = state->original_clock_gettime(state->time_module, args);

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
    _time_machine_state *state = _time_machine_get_module_state();
    if (state == NULL) {
        return NULL;
    }

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
        if (!overflow && state->have_clock_realtime && clk_id == state->clock_realtime) {
            return _time_machine_traveller_time_ns();
        }
        // Fall through: non-realtime clocks, and out-of-range values, get the
        // original function's behaviour, including its error messages.
    }

    return state->original_clock_gettime_ns(state->time_module, args);
}

static PyObject *
_time_machine_original_clock_gettime_ns(PyObject *module, PyObject *args)
{
    _time_machine_state *state = get_time_machine_state(module);

    if (state->original_clock_gettime_ns == NULL) {
        PyErr_SetString(PyExc_ValueError, "Not currently time-travelling.");
        return NULL;
    }

    PyObject *result = state->original_clock_gettime_ns(state->time_module, args);

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
    _time_machine_state *state = _time_machine_get_module_state();
    if (state == NULL) {
        return NULL;
    }

    Py_ssize_t nargs = PyTuple_GET_SIZE(args);
    if (nargs > 1 || (nargs == 1 && PyTuple_GET_ITEM(args, 0) != Py_None)) {
        // Pass through, including invalid arguments for their error messages.
        return state->original_gmtime(state->time_module, args);
    }

    PyObject *timestamp = _time_machine_traveller_time();
    if (timestamp == NULL) {
        return NULL;
    }
    PyObject *new_args = PyTuple_Pack(1, timestamp);
    Py_DECREF(timestamp);
    if (new_args == NULL) {
        return NULL;
    }
    PyObject *result = state->original_gmtime(state->time_module, new_args);
    Py_DECREF(new_args);
    return result;
}

static PyObject *
_time_machine_original_gmtime(PyObject *module, PyObject *args)
{
    _time_machine_state *state = get_time_machine_state(module);

    if (state->original_gmtime == NULL) {
        PyErr_SetString(PyExc_ValueError, "Not currently time-travelling.");
        return NULL;
    }

    PyObject *result = state->original_gmtime(state->time_module, args);

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
    _time_machine_state *state = _time_machine_get_module_state();
    if (state == NULL) {
        return NULL;
    }

    Py_ssize_t nargs = PyTuple_GET_SIZE(args);
    if (nargs > 1 || (nargs == 1 && PyTuple_GET_ITEM(args, 0) != Py_None)) {
        // Pass through, including invalid arguments for their error messages.
        return state->original_localtime(state->time_module, args);
    }

    PyObject *timestamp = _time_machine_traveller_time();
    if (timestamp == NULL) {
        return NULL;
    }
    PyObject *new_args = PyTuple_Pack(1, timestamp);
    Py_DECREF(timestamp);
    if (new_args == NULL) {
        return NULL;
    }
    PyObject *result = state->original_localtime(state->time_module, new_args);
    Py_DECREF(new_args);
    return result;
}

static PyObject *
_time_machine_original_localtime(PyObject *module, PyObject *args)
{
    _time_machine_state *state = get_time_machine_state(module);

    if (state->original_localtime == NULL) {
        PyErr_SetString(PyExc_ValueError, "Not currently time-travelling.");
        return NULL;
    }

    PyObject *result = state->original_localtime(state->time_module, args);

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
    _time_machine_state *state = _time_machine_get_module_state();
    if (state == NULL) {
        return NULL;
    }

    Py_ssize_t nargs = PyTuple_GET_SIZE(args);
    if (nargs < 1 || nargs > 2 || (nargs == 2 && PyTuple_GET_ITEM(args, 1) != Py_None)) {
        // Pass through, including invalid arguments for their error messages.
        return state->original_strftime(state->time_module, args);
    }

    // time.strftime(format, time.localtime(traveller_time))
    PyObject *timestamp = _time_machine_traveller_time();
    if (timestamp == NULL) {
        return NULL;
    }
    PyObject *localtime_args = PyTuple_Pack(1, timestamp);
    Py_DECREF(timestamp);
    if (localtime_args == NULL) {
        return NULL;
    }
    PyObject *local_time = state->original_localtime(state->time_module, localtime_args);
    Py_DECREF(localtime_args);
    if (local_time == NULL) {
        return NULL;
    }
    PyObject *new_args = PyTuple_Pack(2, PyTuple_GET_ITEM(args, 0), local_time);
    Py_DECREF(local_time);
    if (new_args == NULL) {
        return NULL;
    }
    PyObject *result = state->original_strftime(state->time_module, new_args);
    Py_DECREF(new_args);
    return result;
}

static PyObject *
_time_machine_original_strftime(PyObject *module, PyObject *args)
{
    _time_machine_state *state = get_time_machine_state(module);

    if (state->original_strftime == NULL) {
        PyErr_SetString(PyExc_ValueError, "Not currently time-travelling.");
        return NULL;
    }

    PyObject *result = state->original_strftime(state->time_module, args);

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
    return _time_machine_traveller_time();
}

static PyObject *
_time_machine_original_time(PyObject *module, PyObject *args)
{
    _time_machine_state *state = get_time_machine_state(module);

    if (state->original_time == NULL) {
        PyErr_SetString(PyExc_ValueError, "Not currently time-travelling.");
        return NULL;
    }

    PyObject *result = state->original_time(state->time_module, args);

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
    return _time_machine_traveller_time_ns();
}

static PyObject *
_time_machine_original_time_ns(PyObject *module, PyObject *args)
{
    _time_machine_state *state = get_time_machine_state(module);

    if (state->original_time_ns == NULL) {
        PyErr_SetString(PyExc_ValueError, "Not currently time-travelling.");
        return NULL;
    }

    PyObject *result = state->original_time_ns(state->time_module, args);

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

    if (state->original_time)
        Py_RETURN_NONE;

    state->original_date_today = state->date_today->m_ml->ml_meth;
    state->date_today->m_ml->ml_meth = _time_machine_today;

#if PY_VERSION_HEX >= 0x030d00a4
    state->original_now =
        (PyCFunctionFastWithKeywords)state->datetime_datetime_now->m_ml->ml_meth;
#else
    state->original_now =
        (_PyCFunctionFastWithKeywords)state->datetime_datetime_now->m_ml->ml_meth;
#endif
    state->datetime_datetime_now->m_ml->ml_meth = (PyCFunction)_time_machine_now;

    state->original_utcnow = state->datetime_datetime_utcnow->m_ml->ml_meth;
    state->datetime_datetime_utcnow->m_ml->ml_meth = _time_machine_utcnow;

    /*
        time.clock_gettime(), only available on Unix platforms.
    */
    if (state->time_clock_gettime != NULL) {
        state->original_clock_gettime = state->time_clock_gettime->m_ml->ml_meth;
        state->time_clock_gettime->m_ml->ml_meth = _time_machine_clock_gettime;
    }

    /*
        time.clock_gettime_ns(), only available on Unix platforms.
    */
    if (state->time_clock_gettime_ns != NULL) {
        state->original_clock_gettime_ns = state->time_clock_gettime_ns->m_ml->ml_meth;
        state->time_clock_gettime_ns->m_ml->ml_meth = _time_machine_clock_gettime_ns;
    }

    state->original_gmtime = state->time_gmtime->m_ml->ml_meth;
    state->time_gmtime->m_ml->ml_meth = _time_machine_gmtime;

    state->original_localtime = state->time_localtime->m_ml->ml_meth;
    state->time_localtime->m_ml->ml_meth = _time_machine_localtime;

    state->original_strftime = state->time_strftime->m_ml->ml_meth;
    state->time_strftime->m_ml->ml_meth = _time_machine_strftime;

    state->original_time = state->time_time->m_ml->ml_meth;
    state->time_time->m_ml->ml_meth = _time_machine_time;

    state->original_time_ns = state->time_time_ns->m_ml->ml_meth;
    state->time_time_ns->m_ml->ml_meth = _time_machine_time_ns;

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

    if (!state->original_time)
        Py_RETURN_NONE;

#if PY_VERSION_HEX >= 0x030d00a4
    state->datetime_datetime_now->m_ml->ml_meth = (PyCFunction)state->original_now;
#else
    state->datetime_datetime_now->m_ml->ml_meth = (PyCFunction)state->original_now;
#endif
    state->original_now = NULL;

    state->datetime_datetime_utcnow->m_ml->ml_meth = state->original_utcnow;
    state->original_utcnow = NULL;

    state->date_today->m_ml->ml_meth = state->original_date_today;
    state->original_date_today = NULL;

    /*
        time.clock_gettime(), only available on Unix platforms.
    */
    if (state->time_clock_gettime != NULL) {
        state->time_clock_gettime->m_ml->ml_meth = state->original_clock_gettime;
        state->original_clock_gettime = NULL;
    }

    /*
        time.clock_gettime_ns(), only available on Unix platforms.
    */
    if (state->time_clock_gettime_ns != NULL) {
        state->time_clock_gettime_ns->m_ml->ml_meth = state->original_clock_gettime_ns;
        state->original_clock_gettime_ns = NULL;
    }

    state->time_gmtime->m_ml->ml_meth = state->original_gmtime;
    state->original_gmtime = NULL;

    state->time_localtime->m_ml->ml_meth = state->original_localtime;
    state->original_localtime = NULL;

    state->time_strftime->m_ml->ml_meth = state->original_strftime;
    state->original_strftime = NULL;

    state->time_time->m_ml->ml_meth = state->original_time;
    state->original_time = NULL;

    state->time_time_ns->m_ml->ml_meth = state->original_time_ns;
    state->original_time_ns = NULL;

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

    if (str_traveller_stack == NULL) {
        str_traveller_stack = PyUnicode_InternFromString("traveller_stack");
        if (str_traveller_stack == NULL) {
            goto error;
        }
    }
    if (str_time_ns == NULL) {
        str_time_ns = PyUnicode_InternFromString("time_ns");
        if (str_time_ns == NULL) {
            goto error;
        }
    }
    if (str_replace == NULL) {
        str_replace = PyUnicode_InternFromString("replace");
        if (str_replace == NULL) {
            goto error;
        }
    }
    if (str_fromtimestamp == NULL) {
        str_fromtimestamp = PyUnicode_InternFromString("fromtimestamp");
        if (str_fromtimestamp == NULL) {
            goto error;
        }
    }
    if (tzinfo_kwnames == NULL) {
        PyObject *str_tzinfo = PyUnicode_InternFromString("tzinfo");
        if (str_tzinfo == NULL) {
            goto error;
        }
        tzinfo_kwnames = PyTuple_Pack(1, str_tzinfo);
        Py_DECREF(str_tzinfo);
        if (tzinfo_kwnames == NULL) {
            goto error;
        }
    }
    if (nanoseconds_per_second == NULL) {
        nanoseconds_per_second = PyLong_FromLong(1000000000L);
        if (nanoseconds_per_second == NULL) {
            goto error;
        }
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

    PyObject *clock_realtime = PyObject_GetAttrString(state->time_module, "CLOCK_REALTIME");
    if (clock_realtime == NULL) {
        // time.CLOCK_REALTIME is not always available, e.g. on builds
        // against old macOS = official Python.org installer
        if (PyErr_ExceptionMatches(PyExc_AttributeError)) {
            PyErr_Clear();
            state->have_clock_realtime = 0;
        }
        else {
            goto error;
        }
    }
    else {
        state->clock_realtime = PyLong_AsLong(clock_realtime);
        Py_DECREF(clock_realtime);
        if (state->clock_realtime == -1 && PyErr_Occurred()) {
            goto error;
        }
        state->have_clock_realtime = 1;
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
