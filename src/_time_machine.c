#include "Python.h"
#include <stdlib.h>
#include <limits.h>

// Module state
typedef struct {
    _PyCFunctionFastWithKeywords original_now;
    PyCFunction original_utcnow;
    PyCFunction original_clock_gettime;
    PyCFunction original_clock_gettime_ns;
    PyCFunction original_gmtime;
    PyCFunction original_localtime;
    PyCFunction original_monotonic;
    PyCFunction original_monotonic_ns;
    PyCFunction original_strftime;
    PyCFunction original_time;
    PyCFunction original_time_ns;
} _time_machine_state;

static inline _time_machine_state*
get_time_machine_state(PyObject *module)
{
    void *state = PyModule_GetState(module);
    assert(state != NULL);
    return (_time_machine_state *)state;
}

/* datetime.datetime.now() */

static PyObject*
_time_machine_now(PyTypeObject *type, PyObject *const *args, Py_ssize_t nargs, PyObject *kwnames)

{
    PyObject *result = NULL;

    PyObject *time_machine_module = PyImport_ImportModule("time_machine");
    PyObject *time_machine_now = PyObject_GetAttrString(time_machine_module, "now");

    result = _PyObject_Vectorcall(time_machine_now, args, nargs, kwnames);

    Py_DECREF(time_machine_now);
    Py_DECREF(time_machine_module);

    return result;
}

static PyObject*
_time_machine_original_now(PyObject *module, PyObject *const *args, Py_ssize_t nargs, PyObject *kwnames)
{
    _time_machine_state *state = get_time_machine_state(module);

    PyObject *datetime_module = PyImport_ImportModule("datetime");
    PyObject *datetime_class = PyObject_GetAttrString(datetime_module, "datetime");

    PyObject* result = state->original_now(datetime_class, args, nargs, kwnames);

    Py_DECREF(datetime_class);
    Py_DECREF(datetime_module);

    return result;
}
PyDoc_STRVAR(original_now_doc,
"original_now() -> datetime\n\
\n\
Call datetime.datetime.now() after patching.");

/* datetime.datetime.utcnow() */

static PyObject*
_time_machine_utcnow(PyObject *cls, PyObject *args)
{
    PyObject *time_machine_module = PyImport_ImportModule("time_machine");
    PyObject *time_machine_utcnow = PyObject_GetAttrString(time_machine_module, "utcnow");

    PyObject* result = PyObject_CallObject(time_machine_utcnow, args);

    Py_DECREF(time_machine_utcnow);
    Py_DECREF(time_machine_module);

    return result;
}

static PyObject*
_time_machine_original_utcnow(PyObject *module, PyObject *args)
{
    _time_machine_state *state = get_time_machine_state(module);

    PyObject *datetime_module = PyImport_ImportModule("datetime");
    PyObject *datetime_class = PyObject_GetAttrString(datetime_module, "datetime");

    PyObject* result = state->original_utcnow(datetime_class, args);

    Py_DECREF(datetime_class);
    Py_DECREF(datetime_module);

    return result;
}
PyDoc_STRVAR(original_utcnow_doc,
"original_utcnow() -> datetime\n\
\n\
Call datetime.datetime.utcnow() after patching.");

/* time.clock_gettime() */

static PyObject*
_time_machine_clock_gettime(PyObject *self, PyObject *args)
{
    PyObject *time_machine_module = PyImport_ImportModule("time_machine");
    PyObject *time_machine_clock_gettime = PyObject_GetAttrString(time_machine_module, "clock_gettime");

    PyObject* result = PyObject_CallObject(time_machine_clock_gettime, args);

    Py_DECREF(time_machine_clock_gettime);
    Py_DECREF(time_machine_module);

    return result;
}

static PyObject*
_time_machine_original_clock_gettime(PyObject *module, PyObject *args)
{
    _time_machine_state *state = get_time_machine_state(module);

    PyObject *time_module = PyImport_ImportModule("time");

    PyObject* result = state->original_clock_gettime(time_module, args);

    Py_DECREF(time_module);

    return result;
}
PyDoc_STRVAR(original_clock_gettime_doc,
"original_clock_gettime() -> floating point number\n\
\n\
Call time.clock_gettime() after patching.");

/* time.clock_gettime_ns() */

static PyObject*
_time_machine_clock_gettime_ns(PyObject *self, PyObject *args)
{
    PyObject *time_machine_module = PyImport_ImportModule("time_machine");
    PyObject *time_machine_clock_gettime_ns = PyObject_GetAttrString(time_machine_module, "clock_gettime_ns");

    PyObject* result = PyObject_CallObject(time_machine_clock_gettime_ns, args);

    Py_DECREF(time_machine_clock_gettime_ns);
    Py_DECREF(time_machine_module);

    return result;
}

static PyObject*
_time_machine_original_clock_gettime_ns(PyObject *module, PyObject *args)
{
    _time_machine_state *state = get_time_machine_state(module);

    PyObject *time_module = PyImport_ImportModule("time");

    PyObject* result = state->original_clock_gettime_ns(time_module, args);

    Py_DECREF(time_module);

    return result;
}
PyDoc_STRVAR(original_clock_gettime_ns_doc,
"original_clock_gettime_ns() -> int\n\
\n\
Call time.clock_gettime_ns() after patching.");

/* time.gmtime() */

static PyObject*
_time_machine_gmtime(PyObject *self, PyObject *args)
{
    PyObject *time_machine_module = PyImport_ImportModule("time_machine");
    PyObject *time_machine_gmtime = PyObject_GetAttrString(time_machine_module, "gmtime");

    PyObject* result = PyObject_CallObject(time_machine_gmtime, args);

    Py_DECREF(time_machine_gmtime);
    Py_DECREF(time_machine_module);

    return result;
}

static PyObject*
_time_machine_original_gmtime(PyObject *module, PyObject *args)
{
    _time_machine_state *state = get_time_machine_state(module);

    PyObject *time_module = PyImport_ImportModule("time");

    PyObject* result = state->original_gmtime(time_module, args);

    Py_DECREF(time_module);

    return result;
}
PyDoc_STRVAR(original_gmtime_doc,
"original_gmtime() -> floating point number\n\
\n\
Call time.gmtime() after patching.");

/* time.localtime() */

static PyObject*
_time_machine_localtime(PyObject *self, PyObject *args)
{
    PyObject *time_machine_module = PyImport_ImportModule("time_machine");
    PyObject *time_machine_localtime = PyObject_GetAttrString(time_machine_module, "localtime");

    PyObject* result = PyObject_CallObject(time_machine_localtime, args);

    Py_DECREF(time_machine_localtime);
    Py_DECREF(time_machine_module);

    return result;
}

static PyObject*
_time_machine_original_localtime(PyObject *module, PyObject *args)
{
    _time_machine_state *state = get_time_machine_state(module);

    PyObject *time_module = PyImport_ImportModule("time");

    PyObject* result = state->original_localtime(time_module, args);

    Py_DECREF(time_module);

    return result;
}
PyDoc_STRVAR(original_localtime_doc,
"original_localtime() -> floating point number\n\
\n\
Call time.localtime() after patching.");

/* time.monotonic() */

static PyObject*
_time_machine_original_monotonic(PyObject* module, PyObject* args)
{
    _time_machine_state *state = get_time_machine_state(module);

    PyObject *time_module = PyImport_ImportModule("time");

    PyObject* result = state->original_monotonic(time_module, args);

    Py_DECREF(time_module);

    return result;
}
PyDoc_STRVAR(original_monotonic_doc,
"original_monotonic() -> floating point number\n\
\n\
Call time.monotonic() after patching.");

/* time.monotonic_ns() */

static PyObject*
_time_machine_original_monotonic_ns(PyObject* module, PyObject* args)
{
    _time_machine_state *state = get_time_machine_state(module);

    PyObject *time_module = PyImport_ImportModule("time");

    PyObject* result = state->original_monotonic_ns(time_module, args);

    Py_DECREF(time_module);

    return result;
}
PyDoc_STRVAR(original_monotonic_ns_doc,
"original_monotonic_ns() -> int\n\
\n\
Call time.monotonic_ns() after patching.");

/* time.strftime() */

static PyObject*
_time_machine_strftime(PyObject *self, PyObject *args)
{
    PyObject *time_machine_module = PyImport_ImportModule("time_machine");
    PyObject *time_machine_strftime = PyObject_GetAttrString(time_machine_module, "strftime");

    PyObject* result = PyObject_CallObject(time_machine_strftime, args);

    Py_DECREF(time_machine_strftime);
    Py_DECREF(time_machine_module);

    return result;
}

static PyObject*
_time_machine_original_strftime(PyObject *module, PyObject *args)
{
    _time_machine_state *state = get_time_machine_state(module);

    PyObject *time_module = PyImport_ImportModule("time");

    PyObject* result = state->original_strftime(time_module, args);

    Py_DECREF(time_module);

    return result;
}
PyDoc_STRVAR(original_strftime_doc,
"original_strftime() -> floating point number\n\
\n\
Call time.strftime() after patching.");

/* time.time() */

static PyObject*
_time_machine_time(PyObject *self, PyObject *args)
{
    PyObject *time_machine_module = PyImport_ImportModule("time_machine");
    PyObject *time_machine_time = PyObject_GetAttrString(time_machine_module, "time");

    PyObject* result = PyObject_CallObject(time_machine_time, args);

    Py_DECREF(time_machine_time);
    Py_DECREF(time_machine_module);

    return result;
}

static PyObject*
_time_machine_original_time(PyObject *module, PyObject *args)
{
    _time_machine_state *state = get_time_machine_state(module);

    PyObject *time_module = PyImport_ImportModule("time");

    PyObject* result = state->original_time(time_module, args);

    Py_DECREF(time_module);

    return result;
}
PyDoc_STRVAR(original_time_doc,
"original_time() -> floating point number\n\
\n\
Call time.time() after patching.");

/* time.time_ns() */

static PyObject*
_time_machine_time_ns(PyObject *self, PyObject *args)
{
    PyObject *time_machine_module = PyImport_ImportModule("time_machine");
    PyObject *time_machine_time_ns = PyObject_GetAttrString(time_machine_module, "time_ns");

    PyObject* result = PyObject_CallObject(time_machine_time_ns, args);

    Py_DECREF(time_machine_time_ns);
    Py_DECREF(time_machine_module);

    return result;
}

static PyObject*
_time_machine_original_time_ns(PyObject *module, PyObject *args)
{
    _time_machine_state *state = get_time_machine_state(module);

    PyObject *time_module = PyImport_ImportModule("time");

    PyObject* result = state->original_time_ns(time_module, args);

    Py_DECREF(time_module);

    return result;
}
PyDoc_STRVAR(original_time_ns_doc,
"original_time_ns() -> int\n\
\n\
Call time.time_ns() after patching.");

static PyObject*
_time_machine_patch_if_needed(PyObject *module, PyObject *unused)
{
    _time_machine_state *state = PyModule_GetState(module);
    if (state == NULL) {
        return NULL;
    }

    if (state->original_time)
        Py_RETURN_NONE;

    PyObject *datetime_module = PyImport_ImportModule("datetime");
    PyObject *datetime_class = PyObject_GetAttrString(datetime_module, "datetime");

    PyCFunctionObject *datetime_datetime_now = (PyCFunctionObject *) PyObject_GetAttrString(datetime_class, "now");
    state->original_now = (_PyCFunctionFastWithKeywords) datetime_datetime_now->m_ml->ml_meth;
    datetime_datetime_now->m_ml->ml_meth = (PyCFunction) _time_machine_now;
    Py_DECREF(datetime_datetime_now);

    PyCFunctionObject *datetime_datetime_utcnow = (PyCFunctionObject *) PyObject_GetAttrString(datetime_class, "utcnow");
    state->original_utcnow = datetime_datetime_utcnow->m_ml->ml_meth;
    datetime_datetime_utcnow->m_ml->ml_meth = _time_machine_utcnow;
    Py_DECREF(datetime_datetime_utcnow);

    Py_DECREF(datetime_class);
    Py_DECREF(datetime_module);

    PyObject *time_module = PyImport_ImportModule("time");



    PyCFunctionObject *time_clock_gettime = (PyCFunctionObject *) PyObject_GetAttrString(time_module, "clock_gettime");
    /*
        time.clock_gettime() is not always available
        e.g. on builds against old macOS = official Python.org installer
    */
    if (time_clock_gettime != NULL) {
        state->original_clock_gettime = time_clock_gettime->m_ml->ml_meth;
        time_clock_gettime->m_ml->ml_meth = _time_machine_clock_gettime;
        Py_DECREF(time_clock_gettime);
    }

    PyCFunctionObject *time_clock_gettime_ns = (PyCFunctionObject *) PyObject_GetAttrString(time_module, "clock_gettime_ns");
    if (time_clock_gettime_ns != NULL) {
        state->original_clock_gettime_ns = time_clock_gettime_ns->m_ml->ml_meth;
        time_clock_gettime_ns->m_ml->ml_meth = _time_machine_clock_gettime_ns;
        Py_DECREF(time_clock_gettime_ns);
    }

    PyCFunctionObject *time_gmtime = (PyCFunctionObject *) PyObject_GetAttrString(time_module, "gmtime");
    state->original_gmtime = time_gmtime->m_ml->ml_meth;
    time_gmtime->m_ml->ml_meth = _time_machine_gmtime;
    Py_DECREF(time_gmtime);

    PyCFunctionObject *time_localtime = (PyCFunctionObject *) PyObject_GetAttrString(time_module, "localtime");
    state->original_localtime = time_localtime->m_ml->ml_meth;
    time_localtime->m_ml->ml_meth = _time_machine_localtime;
    Py_DECREF(time_localtime);

    PyCFunctionObject *time_monotonic = (PyCFunctionObject *) PyObject_GetAttrString(time_module, "monotonic");
    state->original_monotonic = time_monotonic->m_ml->ml_meth;
    time_monotonic->m_ml->ml_meth = _time_machine_time;
    Py_DECREF(time_monotonic);

    PyCFunctionObject *time_monotonic_ns = (PyCFunctionObject *) PyObject_GetAttrString(time_module, "monotonic_ns");
    state->original_monotonic_ns = time_monotonic_ns->m_ml->ml_meth;
    time_monotonic_ns->m_ml->ml_meth = _time_machine_time_ns;
    Py_DECREF(time_monotonic_ns);

    PyCFunctionObject *time_strftime = (PyCFunctionObject *) PyObject_GetAttrString(time_module, "strftime");
    state->original_strftime = time_strftime->m_ml->ml_meth;
    time_strftime->m_ml->ml_meth = _time_machine_strftime;
    Py_DECREF(time_strftime);

    PyCFunctionObject *time_time = (PyCFunctionObject *) PyObject_GetAttrString(time_module, "time");
    state->original_time = time_time->m_ml->ml_meth;
    time_time->m_ml->ml_meth = _time_machine_time;
    Py_DECREF(time_time);

    PyCFunctionObject *time_time_ns = (PyCFunctionObject *) PyObject_GetAttrString(time_module, "time_ns");
    state->original_time_ns = time_time_ns->m_ml->ml_meth;
    time_time_ns->m_ml->ml_meth = _time_machine_time_ns;
    Py_DECREF(time_time_ns);

    Py_DECREF(time_module);

    Py_RETURN_NONE;
}
PyDoc_STRVAR(patch_if_needed_doc,
"patch_if_needed() -> None\n\
\n\
Swap in helpers.");



PyDoc_STRVAR(module_doc, "_time_machine module");

static PyMethodDef module_functions[] = {
    {"original_now", (PyCFunction)_time_machine_original_now, METH_FASTCALL|METH_KEYWORDS, original_now_doc},
    {"original_utcnow", (PyCFunction)_time_machine_original_utcnow, METH_NOARGS, original_utcnow_doc},
    {"original_clock_gettime", (PyCFunction)_time_machine_original_clock_gettime, METH_VARARGS, original_clock_gettime_doc},
    {"original_clock_gettime_ns", (PyCFunction)_time_machine_original_clock_gettime_ns, METH_VARARGS, original_clock_gettime_ns_doc},
    {"original_gmtime", (PyCFunction)_time_machine_original_gmtime, METH_VARARGS, original_gmtime_doc},
    {"original_localtime", (PyCFunction)_time_machine_original_localtime, METH_VARARGS, original_localtime_doc},
    {"original_monotonic", (PyCFunction)_time_machine_original_monotonic, METH_NOARGS, original_monotonic_doc},
    {"original_monotonic_ns", (PyCFunction)_time_machine_original_monotonic_ns, METH_NOARGS, original_monotonic_ns_doc},
    {"original_strftime", (PyCFunction)_time_machine_original_strftime, METH_VARARGS, original_strftime_doc},
    {"original_time", (PyCFunction)_time_machine_original_time, METH_NOARGS, original_time_doc},
    {"original_time_ns", (PyCFunction)_time_machine_original_time_ns, METH_NOARGS, original_time_ns_doc},
    {"patch_if_needed", (PyCFunction)_time_machine_patch_if_needed, METH_NOARGS, patch_if_needed_doc},
    {NULL, NULL}  /* sentinel */
};

static PyModuleDef_Slot _time_machine_slots[] = {
    {0, NULL}
};

static struct PyModuleDef _time_machine_module = {
    PyModuleDef_HEAD_INIT,
    .m_name = "_time_machine",
    .m_doc = module_doc,
    .m_size = sizeof(_time_machine_state),
    .m_methods = module_functions,
    .m_slots = _time_machine_slots,
    .m_traverse = NULL,
    .m_clear = NULL,
    .m_free = NULL
};

PyMODINIT_FUNC
PyInit__time_machine(void)
{
    return PyModuleDef_Init(&_time_machine_module);
}
