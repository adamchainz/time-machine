import datetime as dt
from contextlib import contextmanager

import _time_machine


class Coordinates:
    def __init__(self, destination_timestamp: float, real_start_timestamp: float):
        self.destination_timestamp = destination_timestamp
        self.real_start_timestamp = real_start_timestamp


current_coordinates = None


@contextmanager
def travel(destination):
    global current_coordinates
    if current_coordinates is not None:
        raise RuntimeError("Cannot time travel whilst already travelling.")

    if isinstance(destination, (int, float)):
        destination_timestamp = destination
    else:
        raise TypeError(f"Unsupported destination {destination!r}")

    _time_machine.patch()

    current_coordinates = Coordinates(
        destination_timestamp=destination_timestamp,
        real_start_timestamp=_time_machine.original_time(),
    )
    try:
        yield
    finally:
        current_coordinates = None


# datetime module


def now(tz=None):
    if current_coordinates is None:
        return _time_machine.original_now()
    else:
        return dt.datetime.fromtimestamp(time(), tz)


def utcnow():
    if current_coordinates is None:
        return _time_machine.original_utcnow()
    else:
        return dt.datetime.fromtimestamp(time(), dt.timezone.utc)


# time module


def time():
    if current_coordinates is None:
        return _time_machine.original_time()
    else:
        return current_coordinates.destination_timestamp + (
            _time_machine.original_time() - current_coordinates.real_start_timestamp
        )


def localtime(secs=None):
    if current_coordinates is None or secs is not None:
        return _time_machine.original_localtime(secs)
    else:
        return _time_machine.original_localtime(
            current_coordinates.destination_timestamp
            + (_time_machine.original_time() - current_coordinates.real_start_timestamp)
        )


def gmtime(secs=None):
    if current_coordinates is None or secs is not None:
        return _time_machine.original_gmtime(secs)
    else:
        return _time_machine.original_gmtime(
            current_coordinates.destination_timestamp
            + (_time_machine.original_time() - current_coordinates.real_start_timestamp)
        )


def strftime(format, t=None):
    if t is not None:
        return _time_machine.original_strftime(format, t)
    elif current_coordinates is None:
        return _time_machine.original_strftime(format)
    else:
        return _time_machine.original_strftime(format, localtime())
