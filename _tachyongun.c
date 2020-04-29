#include "Python.h"
#include <stdlib.h>
#include <limits.h>


static PyObject*
_tachyongun_time(PyObject *self, PyObject *unused)
{
    return PyObject_CallMethod(PyImport_ImportModule("tachyongun"), "time", NULL);
}
PyDoc_STRVAR(time_doc,
"time() -> floating point number\n\
\n\
Call tachyongun.time(), which replaces time.time().");

PyCFunction original_time = NULL;

static PyObject*
_tachyongun_original_time(PyObject *self, PyObject *unused)
{
    return original_time(self, unused);
}
PyDoc_STRVAR(original_time_doc,
"original_time() -> floating point number\n\
\n\
Call time.time() after patching.");


static PyObject*
_tachyongun_localtime(PyObject *self, PyObject *unused)
{
    return PyObject_CallMethod(PyImport_ImportModule("tachyongun"), "localtime", NULL);
}
PyDoc_STRVAR(localtime_doc,
"localtime([secs]) -> floating point number\n\
\n\
Call tachyongun.localtime(), which replaces time.localtime().");

PyCFunction original_localtime = NULL;

static PyObject*
_tachyongun_original_localtime(PyObject *self, PyObject *args)
{
    return original_localtime(self, args);
}
PyDoc_STRVAR(original_localtime_doc,
"original_localtime() -> floating point number\n\
\n\
Call time.localtime() after patching.");


static PyObject*
_tachyongun_patch(PyObject *self, PyObject *unused)
{
    if (original_time)
        Py_RETURN_NONE;

    PyObject *time_module = PyImport_ImportModule("time");

    PyCFunctionObject *time_time = (PyCFunctionObject *) PyObject_GetAttrString(time_module, "time");
    original_time = time_time->m_ml->ml_meth;
    time_time->m_ml->ml_meth = _tachyongun_time;
    Py_DECREF(time_time);

    PyCFunctionObject *time_localtime = (PyCFunctionObject *) PyObject_GetAttrString(time_module, "localtime");
    original_localtime = time_localtime->m_ml->ml_meth;
    time_localtime->m_ml->ml_meth = _tachyongun_localtime;
    Py_DECREF(time_localtime);

    Py_DECREF(time_module);

    Py_RETURN_NONE;
}
PyDoc_STRVAR(patch_doc,
"patch() -> None\n\
\n\
Swap in helpers.");



PyDoc_STRVAR(module_doc, "_tachyongun module");

static PyMethodDef module_methods[] = {
    {"time", (PyCFunction)_tachyongun_time, METH_NOARGS, time_doc},
    {"original_time", (PyCFunction)_tachyongun_original_time, METH_NOARGS, original_time_doc},
    {"localtime", (PyCFunction)_tachyongun_localtime, METH_NOARGS, time_doc},
    {"original_localtime", (PyCFunction)_tachyongun_original_localtime, METH_VARARGS, original_localtime_doc},
    {"patch", (PyCFunction)_tachyongun_patch, METH_NOARGS, patch_doc},
    {NULL, NULL}  /* sentinel */
};

static struct PyModuleDef _tachyongun_def = {
    PyModuleDef_HEAD_INIT,
    "_tachyongun",
    module_doc,
    -1,
    module_methods,
    NULL,
    NULL,
    NULL,
    NULL
};

PyMODINIT_FUNC
PyInit__tachyongun(void)
{
    PyObject *m;

    m = PyModule_Create(&_tachyongun_def);
    if (m == NULL)
        return NULL;

    return m;
}

