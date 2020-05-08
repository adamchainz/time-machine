import datetime as dt
import functools
import inspect
import sys
from types import GeneratorType
from unittest import TestCase

from dateutil.parser import parse as parse_datetime

import _time_machine


class Coordinates:
    def __init__(
        self, destination_timestamp: float, real_start_timestamp: float, tick: bool
    ):
        self.destination_timestamp = destination_timestamp
        self.real_start_timestamp = real_start_timestamp
        self.tick = tick


current_coordinates = None


class travel:
    def __init__(self, destination, *, tick=True):
        if callable(destination):
            destination = destination()
        elif isinstance(destination, GeneratorType):
            destination = next(destination)

        if isinstance(destination, (int, float)):
            destination_timestamp = destination
        elif isinstance(destination, dt.datetime):
            if destination.tzinfo is None:
                destination = destination.replace(tzinfo=dt.timezone.utc)
            destination_timestamp = destination.timestamp()
        elif isinstance(destination, dt.date):
            destination_timestamp = dt.datetime.combine(
                destination, dt.time(0, 0), tzinfo=dt.timezone.utc
            ).timestamp()
        elif isinstance(destination, str):
            destination_timestamp = parse_datetime(destination).timestamp()
        else:
            raise TypeError(f"Unsupported destination {destination!r}")

        self.destination_timestamp = destination_timestamp
        self.tick = tick

    def start(self):
        global current_coordinates
        if current_coordinates is not None:
            raise RuntimeError("Cannot time travel whilst already travelling.")

        _time_machine.patch()

        current_coordinates = Coordinates(
            destination_timestamp=self.destination_timestamp,
            real_start_timestamp=_time_machine.original_time(),
            tick=self.tick,
        )

    def stop(self):
        global current_coordinates
        current_coordinates = None

    def __enter__(self):
        self.start()

    def __exit__(self, *exc_info):
        self.stop()

    def __call__(self, wrapped):
        if inspect.isclass(wrapped):
            # Class decorator
            if not issubclass(wrapped, TestCase):
                raise TypeError("Can only decorate unittest.TestCase subclasses.")

            # Modify the setUpClass method
            orig_setUpClass = wrapped.setUpClass

            @functools.wraps(orig_setUpClass)
            def setUpClass(cls):
                self.__enter__()
                try:
                    orig_setUpClass()
                except Exception:
                    self.__exit__(*sys.exc_info())
                    raise

            wrapped.setUpClass = classmethod(setUpClass)

            orig_tearDownClass = wrapped.tearDownClass

            @functools.wraps(orig_tearDownClass)
            def tearDownClass(cls):
                orig_tearDownClass()
                self.__exit__(None, None, None)

            wrapped.tearDownClass = classmethod(tearDownClass)
            return wrapped
        else:

            @functools.wraps(wrapped)
            def wrapper(*args, **kwargs):
                with self:
                    return wrapped(*args, **kwargs)

            return wrapper


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
    elif current_coordinates.tick:
        return current_coordinates.destination_timestamp + (
            _time_machine.original_time() - current_coordinates.real_start_timestamp
        )
    else:
        return current_coordinates.destination_timestamp


if sys.version_info >= (3, 7):

    def time_ns():
        if current_coordinates is None:
            return _time_machine.original_time_ns()
        elif current_coordinates.tick:
            return int(
                current_coordinates.destination_timestamp
                + (
                    _time_machine.original_time()
                    - current_coordinates.real_start_timestamp
                )
                * 1_000_000
            )
        else:
            return int(current_coordinates.destination_timestamp * 1_000_000)


def localtime(secs=None):
    if current_coordinates is None or secs is not None:
        return _time_machine.original_localtime(secs)
    elif current_coordinates.tick:
        return _time_machine.original_localtime(
            current_coordinates.destination_timestamp
            + (_time_machine.original_time() - current_coordinates.real_start_timestamp)
        )
    else:
        return _time_machine.original_localtime(
            current_coordinates.destination_timestamp
        )


def gmtime(secs=None):
    if current_coordinates is None or secs is not None:
        return _time_machine.original_gmtime(secs)
    elif current_coordinates.tick:
        return _time_machine.original_gmtime(
            current_coordinates.destination_timestamp
            + (_time_machine.original_time() - current_coordinates.real_start_timestamp)
        )
    else:
        return _time_machine.original_gmtime(current_coordinates.destination_timestamp)


def strftime(format, t=None):
    if t is not None:
        return _time_machine.original_strftime(format, t)
    elif current_coordinates is None:
        return _time_machine.original_strftime(format)
    elif current_coordinates.tick:
        return _time_machine.original_strftime(format, localtime())
    else:
        return _time_machine.original_strftime(format, localtime())
