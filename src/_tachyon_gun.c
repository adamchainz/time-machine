#include "Python.h"
#include <stdlib.h>
#include <limits.h>

/* datetime.datetime.now() */

static PyObject*
_tachyon_gun_now(PyTypeObject *type, PyObject *const *args, Py_ssize_t nargs, PyObject *kwnames)
{
    PyObject *tachyon_gun_module = PyImport_ImportModule("tachyon_gun");
    PyObject *tachyon_gun_now = PyObject_GetAttrString(tachyon_gun_module, "now");

    PyObject* result = _PyObject_Vectorcall(tachyon_gun_now, args, nargs, kwnames);

    Py_DECREF(tachyon_gun_now);
    Py_DECREF(tachyon_gun_module);

    return result;
}
PyDoc_STRVAR(now_doc,
"now() -> datetime\n\
\n\
Call tachyon_gun.now(), which replaces datetime.datetime.now().");

_PyCFunctionFastWithKeywords original_now = NULL;

static PyObject*
_tachyon_gun_original_now(PyTypeObject *type, PyObject *const *args, Py_ssize_t nargs, PyObject *kwnames)
{
    PyObject *datetime_module = PyImport_ImportModule("datetime");
    PyObject *datetime_class = PyObject_GetAttrString(datetime_module, "datetime");

    PyObject* result = original_now(datetime_class, args, nargs, kwnames);

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
_tachyon_gun_utcnow(PyObject *cls, PyObject *args)
{
    PyObject *tachyon_gun_module = PyImport_ImportModule("tachyon_gun");
    PyObject *tachyon_gun_utcnow = PyObject_GetAttrString(tachyon_gun_module, "utcnow");

    PyObject* result = PyObject_CallObject(tachyon_gun_utcnow, args);

    Py_DECREF(tachyon_gun_utcnow);
    Py_DECREF(tachyon_gun_module);

    return result;
}
PyDoc_STRVAR(utcnow_doc,
"utcnow() -> datetime\n\
\n\
Call tachyon_gun.utcnow(), which replaces datetime.datetime.utcnow().");

PyCFunction original_utcnow = NULL;

static PyObject*
_tachyon_gun_original_utcnow(PyObject *cls, PyObject *args)
{
    PyObject *datetime_module = PyImport_ImportModule("datetime");
    PyObject *datetime_class = PyObject_GetAttrString(datetime_module, "datetime");

    PyObject* result = original_utcnow(datetime_class, args);

    Py_DECREF(datetime_class);
    Py_DECREF(datetime_module);

    return result;
}
PyDoc_STRVAR(original_utcnow_doc,
"original_utcnow() -> datetime\n\
\n\
Call datetime.datetime.utcnow() after patching.");

/* time.time() */

static PyObject*
_tachyon_gun_time(PyObject *self, PyObject *args)
{
    PyObject *tachyon_gun_module = PyImport_ImportModule("tachyon_gun");
    PyObject *tachyon_gun_time = PyObject_GetAttrString(tachyon_gun_module, "time");

    PyObject* result = PyObject_CallObject(tachyon_gun_time, args);

    Py_DECREF(tachyon_gun_time);
    Py_DECREF(tachyon_gun_module);

    return result;
}
PyDoc_STRVAR(time_doc,
"time() -> floating point number\n\
\n\
Call tachyon_gun.time(), which replaces time.time().");

PyCFunction original_time = NULL;

static PyObject*
_tachyon_gun_original_time(PyObject *self, PyObject *args)
{
    return original_time(self, args);
}
PyDoc_STRVAR(original_time_doc,
"original_time() -> floating point number\n\
\n\
Call time.time() after patching.");

/* time.localtime() */

static PyObject*
_tachyon_gun_localtime(PyObject *self, PyObject *args)
{
    PyObject *tachyon_gun_module = PyImport_ImportModule("tachyon_gun");
    PyObject *tachyon_gun_localtime = PyObject_GetAttrString(tachyon_gun_module, "localtime");

    PyObject* result = PyObject_CallObject(tachyon_gun_localtime, args);

    Py_DECREF(tachyon_gun_localtime);
    Py_DECREF(tachyon_gun_module);

    return result;
}
PyDoc_STRVAR(localtime_doc,
"localtime([secs]) -> floating point number\n\
\n\
Call tachyon_gun.localtime(), which replaces time.localtime().");

PyCFunction original_localtime = NULL;

static PyObject*
_tachyon_gun_original_localtime(PyObject *self, PyObject *args)
{
    return original_localtime(self, args);
}
PyDoc_STRVAR(original_localtime_doc,
"original_localtime() -> floating point number\n\
\n\
Call time.localtime() after patching.");

/* time.gmtime() */

static PyObject*
_tachyon_gun_gmtime(PyObject *self, PyObject *args)
{
    PyObject *tachyon_gun_module = PyImport_ImportModule("tachyon_gun");
    PyObject *tachyon_gun_gmtime = PyObject_GetAttrString(tachyon_gun_module, "gmtime");

    PyObject* result = PyObject_CallObject(tachyon_gun_gmtime, args);

    Py_DECREF(tachyon_gun_gmtime);
    Py_DECREF(tachyon_gun_module);

    return result;
}
PyDoc_STRVAR(gmtime_doc,
"gmtime([secs]) -> floating point number\n\
\n\
Call tachyon_gun.gmtime(), which replaces time.gmtime().");

PyCFunction original_gmtime = NULL;

static PyObject*
_tachyon_gun_original_gmtime(PyObject *self, PyObject *args)
{
    return original_gmtime(self, args);
}
PyDoc_STRVAR(original_gmtime_doc,
"original_gmtime() -> floating point number\n\
\n\
Call time.gmtime() after patching.");

/* time.strftime() */

static PyObject*
_tachyon_gun_strftime(PyObject *self, PyObject *args)
{
    PyObject *tachyon_gun_module = PyImport_ImportModule("tachyon_gun");
    PyObject *tachyon_gun_strftime = PyObject_GetAttrString(tachyon_gun_module, "strftime");

    PyObject* result = PyObject_CallObject(tachyon_gun_strftime, args);

    Py_DECREF(tachyon_gun_strftime);
    Py_DECREF(tachyon_gun_module);

    return result;
}
PyDoc_STRVAR(strftime_doc,
"strftime([secs]) -> floating point number\n\
\n\
Call tachyon_gun.strftime(), which replaces time.strftime().");

PyCFunction original_strftime = NULL;

static PyObject*
_tachyon_gun_original_strftime(PyObject *self, PyObject *args)
{
    return original_strftime(self, args);
}
PyDoc_STRVAR(original_strftime_doc,
"original_strftime() -> floating point number\n\
\n\
Call time.strftime() after patching.");


static PyObject*
_tachyon_gun_patch(PyObject *self, PyObject *unused)
{
    if (original_time)
        Py_RETURN_NONE;

    PyObject *datetime_module = PyImport_ImportModule("datetime");
    PyObject *datetime_class = PyObject_GetAttrString(datetime_module, "datetime");

    PyCFunctionObject *datetime_datetime_now = (PyCFunctionObject *) PyObject_GetAttrString(datetime_class, "now");
    original_now = datetime_datetime_now->m_ml->ml_meth;
    datetime_datetime_now->m_ml->ml_meth = _tachyon_gun_now;
    Py_DECREF(datetime_datetime_now);

    PyCFunctionObject *datetime_datetime_utcnow = (PyCFunctionObject *) PyObject_GetAttrString(datetime_class, "utcnow");
    original_utcnow = datetime_datetime_utcnow->m_ml->ml_meth;
    datetime_datetime_utcnow->m_ml->ml_meth = _tachyon_gun_utcnow;
    Py_DECREF(datetime_datetime_utcnow);

    Py_DECREF(datetime_class);
    Py_DECREF(datetime_module);

    PyObject *time_module = PyImport_ImportModule("time");

    PyCFunctionObject *time_time = (PyCFunctionObject *) PyObject_GetAttrString(time_module, "time");
    original_time = time_time->m_ml->ml_meth;
    time_time->m_ml->ml_meth = _tachyon_gun_time;
    Py_DECREF(time_time);

    PyCFunctionObject *time_localtime = (PyCFunctionObject *) PyObject_GetAttrString(time_module, "localtime");
    original_localtime = time_localtime->m_ml->ml_meth;
    time_localtime->m_ml->ml_meth = _tachyon_gun_localtime;
    Py_DECREF(time_localtime);

    PyCFunctionObject *time_gmtime = (PyCFunctionObject *) PyObject_GetAttrString(time_module, "gmtime");
    original_gmtime = time_gmtime->m_ml->ml_meth;
    time_gmtime->m_ml->ml_meth = _tachyon_gun_gmtime;
    Py_DECREF(time_gmtime);

    PyCFunctionObject *time_strftime = (PyCFunctionObject *) PyObject_GetAttrString(time_module, "strftime");
    original_strftime = time_strftime->m_ml->ml_meth;
    time_strftime->m_ml->ml_meth = _tachyon_gun_strftime;
    Py_DECREF(time_strftime);

    Py_DECREF(time_module);

    Py_RETURN_NONE;
}
PyDoc_STRVAR(patch_doc,
"patch() -> None\n\
\n\
Swap in helpers.");



PyDoc_STRVAR(module_doc, "_tachyon_gun module");

static PyMethodDef module_methods[] = {
    {"original_now", (PyCFunction)_tachyon_gun_original_now, METH_FASTCALL|METH_KEYWORDS, original_now_doc},
    {"original_utcnow", (PyCFunction)_tachyon_gun_original_utcnow, METH_NOARGS, original_utcnow_doc},
    {"original_time", (PyCFunction)_tachyon_gun_original_time, METH_NOARGS, original_time_doc},
    {"original_localtime", (PyCFunction)_tachyon_gun_original_localtime, METH_VARARGS, original_localtime_doc},
    {"original_gmtime", (PyCFunction)_tachyon_gun_original_gmtime, METH_VARARGS, original_gmtime_doc},
    {"original_strftime", (PyCFunction)_tachyon_gun_original_strftime, METH_VARARGS, original_strftime_doc},
    {"patch", (PyCFunction)_tachyon_gun_patch, METH_NOARGS, patch_doc},
    {NULL, NULL}  /* sentinel */
};

static struct PyModuleDef _tachyon_gun_def = {
    PyModuleDef_HEAD_INIT,
    "_tachyon_gun",
    module_doc,
    -1,
    module_methods,
    NULL,
    NULL,
    NULL,
    NULL
};

PyMODINIT_FUNC
PyInit__tachyon_gun(void)
{
    PyObject *m;

    m = PyModule_Create(&_tachyon_gun_def);
    if (m == NULL)
        return NULL;

    return m;
}

