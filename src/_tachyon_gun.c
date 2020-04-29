#include "Python.h"
#include <stdlib.h>
#include <limits.h>

/* time.time() */

static PyObject*
_tachyon_gun_time(PyObject *self, PyObject *unused)
{
    return PyObject_CallMethod(PyImport_ImportModule("tachyon_gun"), "time", NULL);
}
PyDoc_STRVAR(time_doc,
"time() -> floating point number\n\
\n\
Call tachyon_gun.time(), which replaces time.time().");

PyCFunction original_time = NULL;

static PyObject*
_tachyon_gun_original_time(PyObject *self, PyObject *unused)
{
    return original_time(self, unused);
}
PyDoc_STRVAR(original_time_doc,
"original_time() -> floating point number\n\
\n\
Call time.time() after patching.");

/* time.localtime() */

static PyObject*
_tachyon_gun_localtime(PyObject *self, PyObject *unused)
{
    return PyObject_CallMethod(PyImport_ImportModule("tachyon_gun"), "localtime", NULL);
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
_tachyon_gun_gmtime(PyObject *self, PyObject *unused)
{
    return PyObject_CallMethod(PyImport_ImportModule("tachyon_gun"), "gmtime", NULL);
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


static PyObject*
_tachyon_gun_patch(PyObject *self, PyObject *unused)
{
    if (original_time)
        Py_RETURN_NONE;

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

    Py_DECREF(time_module);

    Py_RETURN_NONE;
}
PyDoc_STRVAR(patch_doc,
"patch() -> None\n\
\n\
Swap in helpers.");



PyDoc_STRVAR(module_doc, "_tachyon_gun module");

static PyMethodDef module_methods[] = {
    {"time", (PyCFunction)_tachyon_gun_time, METH_NOARGS, time_doc},
    {"original_time", (PyCFunction)_tachyon_gun_original_time, METH_NOARGS, original_time_doc},
    {"localtime", (PyCFunction)_tachyon_gun_localtime, METH_NOARGS, time_doc},
    {"original_localtime", (PyCFunction)_tachyon_gun_original_localtime, METH_VARARGS, original_localtime_doc},
    {"gmtime", (PyCFunction)_tachyon_gun_gmtime, METH_NOARGS, time_doc},
    {"original_gmtime", (PyCFunction)_tachyon_gun_original_gmtime, METH_VARARGS, original_gmtime_doc},
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

