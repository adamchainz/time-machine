import datetime as dt
import functools
import inspect
import sys
import uuid
from types import GeneratorType
from unittest import TestCase, mock

from dateutil.parser import parse as parse_datetime

import _time_machine

# time.clock_gettime and time.CLOCK_REALTIME not always available
# e.g. on builds against old macOS = official Python.org installer
try:
    from time import CLOCK_REALTIME
except ImportError:
    # Dummy value that won't compare equal to any value
    CLOCK_REALTIME = float("inf")

NANOSECONDS_PER_SECOND = 1_000_000_000


class Coordinates:
    def __init__(self, destination_timestamp: float, tick: bool):
        self.destination_timestamp = destination_timestamp
        self._tick = tick
        self.requested = False

    def time(self):
        if not self._tick:
            return self.destination_timestamp

        if not self.requested:
            self.requested = True
            self.real_start_timestamp = _time_machine.original_time()
            return self.destination_timestamp

        return self.destination_timestamp + (
            _time_machine.original_time() - self.real_start_timestamp
        )

    def shift(self, delta):
        if isinstance(delta, dt.timedelta):
            total_seconds = delta.total_seconds()
        elif isinstance(delta, (int, float)):
            total_seconds = delta
        else:
            raise TypeError(f"Unsupported type for delta argument: {delta!r}")

        self.destination_timestamp += total_seconds


coordinates_stack = []

# During time travel, patch the uuid module's time-based generation function to
# None, which makes it use time.time(). Otherwise it makes a system call to
# find the current datetime. The time it finds is stored in generated UUID1
# values.
if sys.version_info >= (3, 7):
    uuid_generate_time_attr = "_generate_time_safe"
else:
    uuid_generate_time_attr = "_uuid_generate_time"
uuid_generate_time_patcher = mock.patch.object(uuid, uuid_generate_time_attr, new=None)
uuid_uuid_create_patcher = mock.patch.object(uuid, "_UuidCreate", new=None)
# We need to cause the functions to be loaded before we try patch them out,
# which is done by this internal function in Python 3.7+
if sys.version_info >= (3, 7):
    uuid_idempotent_load_system_functions = uuid._load_system_functions
else:

    def uuid_idempotent_load_system_functions():
        pass


class travel:
    def __init__(self, destination, *, tick=True, tz_offset=None):
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

        if tz_offset is not None:
            if isinstance(tz_offset, dt.timedelta):
                tz_offset = tz_offset.total_seconds()

            if not isinstance(tz_offset, (float, int)):
                raise TypeError(f"Unsupported tz_offset {tz_offset!r}")

            destination_timestamp += tz_offset

        self.destination_timestamp = destination_timestamp
        self.tick = tick

    def start(self):
        global coordinates_stack

        _time_machine.patch_if_needed()

        if not coordinates_stack:
            uuid_idempotent_load_system_functions()
            uuid_generate_time_patcher.start()
            uuid_uuid_create_patcher.start()

        coordinates = Coordinates(
            destination_timestamp=self.destination_timestamp, tick=self.tick,
        )
        coordinates_stack.append(coordinates)
        return coordinates

    def stop(self):
        global coordinates_stack
        coordinates_stack = coordinates_stack[:-1]

        if not coordinates_stack:
            uuid_generate_time_patcher.stop()
            uuid_uuid_create_patcher.stop()

    def __enter__(self):
        return self.start()

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
        return _time_machine.original_now(tz)
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
    return time()


if sys.version_info >= (3, 7):

    def clock_gettime_ns(clk_id):
        if not coordinates_stack or clk_id != CLOCK_REALTIME:
            return _time_machine.original_clock_gettime_ns(clk_id)
        return time_ns()


def gmtime(secs=None):
    if not coordinates_stack or secs is not None:
        return _time_machine.original_gmtime(secs)
    return _time_machine.original_gmtime(coordinates_stack[-1].time())


def localtime(secs=None):
    if not coordinates_stack or secs is not None:
        return _time_machine.original_localtime(secs)
    return _time_machine.original_localtime(coordinates_stack[-1].time())


def strftime(format, t=None):
    if t is not None:
        return _time_machine.original_strftime(format, t)
    elif not coordinates_stack:
        return _time_machine.original_strftime(format)
    return _time_machine.original_strftime(format, localtime())


def time():
    if not coordinates_stack:
        return _time_machine.original_time()
    return coordinates_stack[-1].time()


if sys.version_info >= (3, 7):

    def time_ns():
        if not coordinates_stack:
            return _time_machine.original_time_ns()
        else:
            return int(coordinates_stack[-1].time() * NANOSECONDS_PER_SECOND)
