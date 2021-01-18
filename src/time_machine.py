import datetime as dt
import functools
import inspect
import os
import sys
import uuid
from time import gmtime as orig_gmtime
from types import GeneratorType
from typing import Optional
from unittest import TestCase, mock

import _time_machine
from dateutil.parser import parse as parse_datetime

# time.clock_gettime and time.CLOCK_REALTIME not always available
# e.g. on builds against old macOS = official Python.org installer
try:
    from time import CLOCK_REALTIME
except ImportError:
    # Dummy value that won't compare equal to any value
    CLOCK_REALTIME = float("inf")

try:
    from time import tzset
except ImportError:  # pragma: no cover
    # Windows
    tzset = None

try:
    # Python 3.8+ or have installed backports.zoneinfo
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

try:
    import pytest
except ImportError:  # pragma: no cover
    pytest = None

NANOSECONDS_PER_SECOND = 1_000_000_000

# Windows' time epoch is not unix epoch but in 1601. This constant helps us
# translate to it.
_system_epoch = orig_gmtime(0)
SYSTEM_EPOCH_TIMESTAMP_NS = int(
    dt.datetime(
        _system_epoch.tm_year,
        _system_epoch.tm_mon,
        _system_epoch.tm_mday,
        _system_epoch.tm_hour,
        _system_epoch.tm_min,
        _system_epoch.tm_sec,
        tzinfo=dt.timezone.utc,
    ).timestamp()
    * NANOSECONDS_PER_SECOND
)


def extract_timestamp_tzname(destination):
    if callable(destination):
        destination = destination()
    elif isinstance(destination, GeneratorType):
        destination = next(destination)

    tzname = None
    if isinstance(destination, (int, float)):
        timestamp = destination
    elif isinstance(destination, dt.datetime):
        if ZoneInfo is not None and isinstance(destination.tzinfo, ZoneInfo):
            tzname = destination.tzinfo.key
        if destination.tzinfo is None:
            destination = destination.replace(tzinfo=dt.timezone.utc)
        timestamp = destination.timestamp()
    elif isinstance(destination, dt.date):
        timestamp = dt.datetime.combine(
            destination, dt.time(0, 0), tzinfo=dt.timezone.utc
        ).timestamp()
    elif isinstance(destination, str):
        timestamp = parse_datetime(destination).timestamp()
    else:
        raise TypeError(f"Unsupported destination {destination!r}")

    return timestamp, tzname


class Coordinates:
    def __init__(
        self,
        destination_timestamp: float,
        destination_tzname: Optional[str],
        tick: bool,
    ):
        self._destination_timestamp_ns = int(
            destination_timestamp * NANOSECONDS_PER_SECOND
        )
        self._destination_tzname = destination_tzname
        self._tick = tick
        self._requested = False

    def time(self):
        return self.time_ns() / NANOSECONDS_PER_SECOND

    def time_ns(self):
        if not self._tick:
            return self._destination_timestamp_ns

        base = SYSTEM_EPOCH_TIMESTAMP_NS + self._destination_timestamp_ns
        now_ns = self._time_ns()

        if not self._requested:
            self._requested = True
            self._real_start_timestamp_ns = now_ns
            return base

        return base + (now_ns - self._real_start_timestamp_ns)

    if sys.version_info >= (3, 7):

        def _time_ns(self):
            return _time_machine.original_time_ns()

    else:

        def _time_ns(self):
            return _time_machine.original_time() * NANOSECONDS_PER_SECOND

    def shift(self, delta):
        if isinstance(delta, dt.timedelta):
            total_seconds = delta.total_seconds()
        elif isinstance(delta, (int, float)):
            total_seconds = delta
        else:
            raise TypeError(f"Unsupported type for delta argument: {delta!r}")

        self._destination_timestamp_ns += total_seconds * NANOSECONDS_PER_SECOND

    def move_to(self, destination):
        self._stop()
        timestamp, self._destination_tzname = extract_timestamp_tzname(destination)
        self._destination_timestamp_ns = timestamp * NANOSECONDS_PER_SECOND
        self._requested = False
        self._start()

    def _start(self):
        if tzset is not None and self._destination_tzname is not None:
            self._orig_tz = os.environ.get("TZ")
            os.environ["TZ"] = self._destination_tzname
            tzset()

    def _stop(self):
        if tzset is not None and self._destination_tzname is not None:
            if self._orig_tz is None:
                del os.environ["TZ"]
            else:
                os.environ["TZ"] = self._orig_tz
            tzset()


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
    def __init__(self, destination, *, tick=True):
        self.destination_timestamp, self.destination_tzname = extract_timestamp_tzname(
            destination
        )
        self.tick = tick

    def start(self):
        global coordinates_stack

        _time_machine.patch_if_needed()

        if not coordinates_stack:
            uuid_idempotent_load_system_functions()
            uuid_generate_time_patcher.start()
            uuid_uuid_create_patcher.start()

        coordinates = Coordinates(
            destination_timestamp=self.destination_timestamp,
            destination_tzname=self.destination_tzname,
            tick=self.tick,
        )
        coordinates_stack.append(coordinates)
        coordinates._start()

        return coordinates

    def stop(self):
        global coordinates_stack
        coordinates_stack.pop()._stop()

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
        return dt.datetime.utcfromtimestamp(time())


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
            return coordinates_stack[-1].time_ns()


# pytest plugin

if pytest is not None:  # pragma: no branch

    @pytest.fixture(name="time_machine")
    def time_machine_fixture():
        traveller = None
        coordinates = None

        class _fixture:
            def move_to(self, destination):
                nonlocal coordinates, traveller
                if traveller is None:
                    traveller = travel(destination)
                    coordinates = traveller.start()
                else:
                    coordinates.move_to(destination)

        try:
            yield _fixture()
        finally:
            if traveller is not None:
                traveller.stop()
