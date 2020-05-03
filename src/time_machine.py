import datetime as dt
from contextlib import contextmanager

import _time_machine


class Warp:
    def __init__(self, destination: float, start_time: float):
        self.destination = destination
        self.start_time = start_time


current_warp = None


@contextmanager
def warp_time(destination):
    global current_warp
    if current_warp is not None:
        raise RuntimeError("Cannot warp during a warp.")

    _time_machine.patch()

    current_warp = Warp(
        destination=destination, start_time=_time_machine.original_time(),
    )
    try:
        yield
    finally:
        current_warp = None


# datetime module


def now(tz=None):
    if current_warp is None:
        return _time_machine.original_now()
    else:
        return dt.datetime.fromtimestamp(time(), tz)


def utcnow():
    if current_warp is None:
        return _time_machine.original_utcnow()
    else:
        return dt.datetime.fromtimestamp(time(), dt.timezone.utc)


# time


def time():
    if current_warp is None:
        return _time_machine.original_time()
    else:
        return current_warp.destination + (
            _time_machine.original_time() - current_warp.start_time
        )


def localtime(secs=None):
    if current_warp is None or secs is not None:
        return _time_machine.original_localtime(secs)
    else:
        return _time_machine.original_localtime(
            current_warp.destination
            + (_time_machine.original_time() - current_warp.start_time)
        )


def gmtime(secs=None):
    if current_warp is None or secs is not None:
        return _time_machine.original_gmtime(secs)
    else:
        return _time_machine.original_gmtime(
            current_warp.destination
            + (_time_machine.original_time() - current_warp.start_time)
        )


def strftime(format, t=None):
    if t is not None:
        return _time_machine.original_strftime(format, t)
    elif current_warp is None:
        return _time_machine.original_strftime(format)
    else:
        return _time_machine.original_strftime(format, localtime())
