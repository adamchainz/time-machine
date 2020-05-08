import datetime as dt
import functools
import inspect
import sys
from time import CLOCK_REALTIME
from types import GeneratorType
from unittest import TestCase

from dateutil.parser import parse as parse_datetime

import _time_machine

NANOSECONDS_PER_SECOND = 1_000_000_000


class Coordinates:
    def __init__(
        self, destination_timestamp: float, real_start_timestamp: float, tick: bool
    ):
        self.destination_timestamp = destination_timestamp
        self.real_start_timestamp = real_start_timestamp
        self.tick = tick


coordinates_stack = []


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
        global coordinates_stack

        _time_machine.patch_if_needed()

        coordinates_stack.append(
            Coordinates(
                destination_timestamp=self.destination_timestamp,
                real_start_timestamp=_time_machine.original_time(),
                tick=self.tick,
            )
        )

    def stop(self):
        global coordinates_stack
        coordinates_stack = coordinates_stack[:-1]

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
        elif inspect.iscoroutinefunction(wrapped):

            @functools.wraps(wrapped)
            async def wrapper(*args, **kwargs):
                with self:
                    return await wrapped(*args, **kwargs)

            return wrapper
        else:

            @functools.wraps(wrapped)
            def wrapper(*args, **kwargs):
                with self:
                    return wrapped(*args, **kwargs)

            return wrapper


# datetime module


def now(tz=None):
    if not coordinates_stack:
        return _time_machine.original_now()
    else:
        return dt.datetime.fromtimestamp(time(), tz)


def utcnow():
    if not coordinates_stack:
        return _time_machine.original_utcnow()
    else:
        return dt.datetime.fromtimestamp(time(), dt.timezone.utc)


# time module


def clock_gettime(clk_id):
    if not coordinates_stack or clk_id != CLOCK_REALTIME:
        return _time_machine.original_clock_gettime(clk_id)
    else:
        return time()


if sys.version_info >= (3, 7):

    def clock_gettime_ns(clk_id):
        if not coordinates_stack or clk_id != CLOCK_REALTIME:
            return _time_machine.original_clock_gettime_ns(clk_id)
        else:
            return time_ns()


def gmtime(secs=None):
    if not coordinates_stack or secs is not None:
        return _time_machine.original_gmtime(secs)
    current_coordinates = coordinates_stack[-1]
    if current_coordinates.tick:
        return _time_machine.original_gmtime(
            current_coordinates.destination_timestamp
            + (_time_machine.original_time() - current_coordinates.real_start_timestamp)
        )
    else:
        return _time_machine.original_gmtime(current_coordinates.destination_timestamp)


def localtime(secs=None):
    if not coordinates_stack or secs is not None:
        return _time_machine.original_localtime(secs)
    current_coordinates = coordinates_stack[-1]
    if current_coordinates.tick:
        return _time_machine.original_localtime(
            current_coordinates.destination_timestamp
            + (_time_machine.original_time() - current_coordinates.real_start_timestamp)
        )
    else:
        return _time_machine.original_localtime(
            current_coordinates.destination_timestamp
        )


def strftime(format, t=None):
    if t is not None:
        return _time_machine.original_strftime(format, t)
    elif not coordinates_stack:
        return _time_machine.original_strftime(format)
    current_coordinates = coordinates_stack[-1]
    if current_coordinates.tick:
        return _time_machine.original_strftime(format, localtime())
    else:
        return _time_machine.original_strftime(format, localtime())


def time():
    if not coordinates_stack:
        return _time_machine.original_time()
    current_coordinates = coordinates_stack[-1]
    if current_coordinates.tick:
        return current_coordinates.destination_timestamp + (
            _time_machine.original_time() - current_coordinates.real_start_timestamp
        )
    else:
        return current_coordinates.destination_timestamp


if sys.version_info >= (3, 7):

    def time_ns():
        if not coordinates_stack:
            return _time_machine.original_time_ns()
        else:
            # Imprecise.
            return int(time() * NANOSECONDS_PER_SECOND)
