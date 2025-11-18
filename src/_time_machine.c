#include "Python.h"
#include <limits.h>
#include <stdlib.h>

// Module state
typedef struct {
    // Imported objects
    PyObject *datetime_module;
    PyObject *time_module;
    PyObject *datetime_class;
    PyCFunctionObject *datetime_datetime_now;
    PyCFunctionObject *datetime_datetime_utcnow;
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

/* datetime.datetime.now() */

static PyObject *
_time_machine_now(
    PyTypeObject *type, PyObject *const *args, Py_ssize_t nargs, PyObject *kwnames)

{
    PyObject *result = NULL;

    PyObject *time_machine_module = PyImport_ImportModule("time_machine");
    if (time_machine_module == NULL) {
        return NULL;  // Propagate ImportError
    }
    PyObject *time_machine_now = PyObject_GetAttrString(time_machine_module, "now");
    if (time_machine_now == NULL) {
        Py_DECREF(time_machine_module);
        return NULL;  // Propagate AttributeError
    }

    result = _PyObject_Vectorcall(time_machine_now, args, nargs, kwnames);

    Py_DECREF(time_machine_now);
    Py_DECREF(time_machine_module);

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

static PyObject *
_time_machine_utcnow(PyObject *cls, PyObject *args)
{
    PyObject *time_machine_module = PyImport_ImportModule("time_machine");
    if (time_machine_module == NULL) {
        return NULL;  // Propagate ImportError
    }
    PyObject *time_machine_utcnow = PyObject_GetAttrString(time_machine_module, "utcnow");
    if (time_machine_utcnow == NULL) {
        Py_DECREF(time_machine_module);
        return NULL;  // Propagate AttributeError
    }

    PyObject *result = PyObject_CallObject(time_machine_utcnow, args);

    Py_DECREF(time_machine_utcnow);
    Py_DECREF(time_machine_module);

    return result;
}

static PyObject *
_time_machine_original_utcnow(PyObject *module, PyObject *args)
{
    _time_machine_state *state = get_time_machine_state(module);

    if (state->original_utcnow == NULL) {
        PyErr_SetString(PyExc_ValueError, "Not currently time-travelling.");
        return NULL;
    }

    PyObject *result = state->original_utcnow(state->datetime_class, args);

    return result;
}
PyDoc_STRVAR(original_utcnow_doc,
    "original_utcnow() -> datetime\n\
\n\
Call datetime.datetime.utcnow() after patching.");

/* time.clock_gettime() */

static PyObject *
_time_machine_clock_gettime(PyObject *self, PyObject *args)
{
    PyObject *time_machine_module = PyImport_ImportModule("time_machine");
    if (time_machine_module == NULL) {
        return NULL;  // Propagate ImportError
    }
    PyObject *time_machine_clock_gettime =
        PyObject_GetAttrString(time_machine_module, "clock_gettime");
    if (time_machine_clock_gettime == NULL) {
        Py_DECREF(time_machine_module);
        return NULL;  // Propagate AttributeError
    }

#if PY_VERSION_HEX >= 0x030d00a2
    PyObject *result = PyObject_CallOneArg(time_machine_clock_gettime, args);
#else
    PyObject *result = PyObject_CallObject(time_machine_clock_gettime, args);
#endif

    Py_DECREF(time_machine_clock_gettime);
    Py_DECREF(time_machine_module);

    return result;
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
    PyObject *time_machine_module = PyImport_ImportModule("time_machine");
    if (time_machine_module == NULL) {
        return NULL;  // Propagate ImportError
    }
    PyObject *time_machine_clock_gettime_ns =
        PyObject_GetAttrString(time_machine_module, "clock_gettime_ns");
    if (time_machine_clock_gettime_ns == NULL) {
        Py_DECREF(time_machine_module);
        return NULL;  // Propagate AttributeError
    }

#if PY_VERSION_HEX >= 0x030d00a2
    PyObject *result = PyObject_CallOneArg(time_machine_clock_gettime_ns, args);
#else
    PyObject *result = PyObject_CallObject(time_machine_clock_gettime_ns, args);
#endif

    Py_DECREF(time_machine_clock_gettime_ns);
    Py_DECREF(time_machine_module);

    return result;
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
    PyObject *time_machine_module = PyImport_ImportModule("time_machine");
    if (time_machine_module == NULL) {
        return NULL;  // Propagate ImportError
    }
    PyObject *time_machine_gmtime = PyObject_GetAttrString(time_machine_module, "gmtime");
    if (time_machine_gmtime == NULL) {
        Py_DECREF(time_machine_module);
        return NULL;  // Propagate AttributeError
    }

    PyObject *result = PyObject_CallObject(time_machine_gmtime, args);

    Py_DECREF(time_machine_gmtime);
    Py_DECREF(time_machine_module);

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
    PyObject *time_machine_module = PyImport_ImportModule("time_machine");
    if (time_machine_module == NULL) {
        return NULL;  // Propagate ImportError
    }
    PyObject *time_machine_localtime =
        PyObject_GetAttrString(time_machine_module, "localtime");
    if (time_machine_localtime == NULL) {
        Py_DECREF(time_machine_module);
        return NULL;  // Propagate AttributeError
    }

    PyObject *result = PyObject_CallObject(time_machine_localtime, args);

    Py_DECREF(time_machine_localtime);
    Py_DECREF(time_machine_module);

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
    PyObject *time_machine_module = PyImport_ImportModule("time_machine");
    if (time_machine_module == NULL) {
        return NULL;  // Propagate ImportError
    }
    PyObject *time_machine_strftime = PyObject_GetAttrString(time_machine_module, "strftime");
    if (time_machine_strftime == NULL) {
        Py_DECREF(time_machine_module);
        return NULL;  // Propagate AttributeError
    }

    PyObject *result = PyObject_CallObject(time_machine_strftime, args);

    Py_DECREF(time_machine_strftime);
    Py_DECREF(time_machine_module);

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
    PyObject *time_machine_module = PyImport_ImportModule("time_machine");
    if (time_machine_module == NULL) {
        return NULL;  // Propagate ImportError
    }
    PyObject *time_machine_time = PyObject_GetAttrString(time_machine_module, "time");
    if (time_machine_time == NULL) {
        Py_DECREF(time_machine_module);
        return NULL;  // Propagate AttributeError
    }

    PyObject *result = PyObject_CallObject(time_machine_time, args);

    Py_DECREF(time_machine_time);
    Py_DECREF(time_machine_module);

    return result;
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
    PyObject *time_machine_module = PyImport_ImportModule("time_machine");
    if (time_machine_module == NULL) {
        return NULL;  // Propagate ImportError
    }
    PyObject *time_machine_time_ns = PyObject_GetAttrString(time_machine_module, "time_ns");
    if (time_machine_time_ns == NULL) {
        Py_DECREF(time_machine_module);
        return NULL;  // Propagate AttributeError
    }

    PyObject *result = PyObject_CallObject(time_machine_time_ns, args);

    Py_DECREF(time_machine_time_ns);
    Py_DECREF(time_machine_module);

    return result;
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

    state->time_module = PyImport_ImportModule("time");
    if (state->time_module == NULL) {
        goto error;
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
    Py_CLEAR(state->datetime_datetime_now);
    Py_CLEAR(state->datetime_datetime_utcnow);
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
    Py_VISIT(state->datetime_datetime_now);
    Py_VISIT(state->datetime_datetime_utcnow);
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
    Py_CLEAR(state->datetime_datetime_now);
    Py_CLEAR(state->datetime_datetime_utcnow);
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
    PyObject *result = PyModuleDef_Init(&_time_machine_module);
    return result;
}
