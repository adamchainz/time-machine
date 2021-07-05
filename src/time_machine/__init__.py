import datetime as dt
import functools
import inspect
import os
import sys
import uuid
from collections.abc import Generator
from time import gmtime as orig_gmtime
from time import struct_time
from types import TracebackType
from typing import Any, Callable, Coroutine
from typing import Generator as TypingGenerator
from typing import List, Optional, Tuple, Type, Union, overload
from unittest import TestCase, mock

from dateutil.parser import parse as parse_datetime

import _time_machine

# time.clock_gettime and time.CLOCK_REALTIME not always available
# e.g. on builds against old macOS = official Python.org installer
try:
    from time import CLOCK_REALTIME
except ImportError:
    # Dummy value that won't compare equal to any value
    CLOCK_REALTIME = sys.maxsize

try:
    from time import tzset

    HAVE_TZSET = True
except ImportError:  # pragma: no cover
    # Windows
    HAVE_TZSET = False

try:
    # Python 3.8+ or have installed backports.zoneinfo
    from zoneinfo import ZoneInfo

    HAVE_ZONEINFO = True
except ImportError:
    HAVE_ZONEINFO = False

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

DestinationBaseType = Union[
    int,
    float,
    dt.datetime,
    dt.date,
    str,
]
DestinationType = Union[
    DestinationBaseType,
    Callable[[], DestinationBaseType],
    TypingGenerator[DestinationBaseType, None, None],
]


def extract_timestamp_tzname(
    destination: DestinationType,
) -> Tuple[float, Union[str, None]]:
    dest: DestinationBaseType
    if isinstance(destination, Generator):
        dest = next(destination)
    elif callable(destination):
        dest = destination()
    else:
        dest = destination

    timestamp: float
    tzname: Optional[str] = None
    if isinstance(dest, int):
        timestamp = float(dest)
    elif isinstance(dest, float):
        timestamp = dest
    elif isinstance(dest, dt.datetime):
        if HAVE_ZONEINFO and isinstance(dest.tzinfo, ZoneInfo):
            tzname = dest.tzinfo.key
        if dest.tzinfo is None:
            dest = dest.replace(tzinfo=dt.timezone.utc)
        timestamp = dest.timestamp()
    elif isinstance(dest, dt.date):
        timestamp = dt.datetime.combine(
            dest, dt.time(0, 0), tzinfo=dt.timezone.utc
        ).timestamp()
    elif isinstance(dest, str):
        timestamp = parse_datetime(dest).timestamp()
    else:
        raise TypeError(f"Unsupported destination {dest!r}")

    return timestamp, tzname


class Coordinates:
    def __init__(
        self,
        destination_timestamp: float,
        destination_tzname: Optional[str],
        tick: bool,
    ) -> None:
        self._destination_timestamp_ns = int(
            destination_timestamp * NANOSECONDS_PER_SECOND
        )
        self._destination_tzname = destination_tzname
        self._tick = tick
        self._requested = False

    def time(self) -> float:
        return self.time_ns() / NANOSECONDS_PER_SECOND

    def time_ns(self) -> int:
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

        def _time_ns(self) -> int:
            return _time_machine.original_time_ns()

    else:

        def _time_ns(self) -> int:
            return _time_machine.original_time() * NANOSECONDS_PER_SECOND

    def shift(self, delta: Union[dt.timedelta, int, float]) -> None:
        if isinstance(delta, dt.timedelta):
            total_seconds = delta.total_seconds()
        elif isinstance(delta, (int, float)):
            total_seconds = delta
        else:
            raise TypeError(f"Unsupported type for delta argument: {delta!r}")

        self._destination_timestamp_ns += int(total_seconds * NANOSECONDS_PER_SECOND)

    def move_to(
        self,
        destination: DestinationType,
        tick: Optional[bool] = None,
    ) -> None:
        self._stop()
        timestamp, self._destination_tzname = extract_timestamp_tzname(destination)
        self._destination_timestamp_ns = int(timestamp * NANOSECONDS_PER_SECOND)
        self._requested = False
        self._start()
        if tick is not None:
            self._tick = tick

    def _start(self) -> None:
        if HAVE_TZSET and self._destination_tzname is not None:
            self._orig_tz = os.environ.get("TZ")
            os.environ["TZ"] = self._destination_tzname
            tzset()

    def _stop(self) -> None:
        if HAVE_TZSET and self._destination_tzname is not None:
            if self._orig_tz is None:
                del os.environ["TZ"]
            else:
                os.environ["TZ"] = self._orig_tz
            tzset()


coordinates_stack: List[Coordinates] = []

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
    uuid_idempotent_load_system_functions = (
        uuid._load_system_functions  # type: ignore[attr-defined]
    )
else:

    def uuid_idempotent_load_system_functions():
        pass


class travel:
    def __init__(self, destination: DestinationType, *, tick: bool = True) -> None:
        self.destination_timestamp, self.destination_tzname = extract_timestamp_tzname(
            destination
        )
        self.tick = tick

    def start(self) -> Coordinates:
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

    def stop(self) -> None:
        global coordinates_stack
        coordinates_stack.pop()._stop()

        if not coordinates_stack:
            uuid_generate_time_patcher.stop()
            uuid_uuid_create_patcher.stop()

    def __enter__(self) -> Coordinates:
        return self.start()

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        self.stop()

    @overload
    def __call__(self, wrapped: Type[TestCase]) -> Type[TestCase]:  # pragma: no cover
        ...

    @overload
    def __call__(
        self, wrapped: Callable[..., Coroutine[Any, Any, Any]]
    ) -> Callable[..., Coroutine[Any, Any, Any]]:  # pragma: no cover
        ...

    @overload
    def __call__(
        self, wrapped: Callable[..., Any]
    ) -> Callable[..., Any]:  # pragma: no cover
        ...

    def __call__(
        self,
        wrapped: Union[
            Type[TestCase],
            Callable[..., Coroutine[Any, Any, Any]],
            Callable[..., Any],
        ],
    ) -> Union[
        Type[TestCase],
        Callable[..., Coroutine[Any, Any, Any]],
        Callable[..., Any],
    ]:
        if isinstance(wrapped, type):
            # Class decorator
            if not issubclass(wrapped, TestCase):
                raise TypeError("Can only decorate unittest.TestCase subclasses.")

            # Modify the setUpClass method
            orig_setUpClass = wrapped.setUpClass

            @functools.wraps(orig_setUpClass)
            def setUpClass(cls: Type[TestCase]) -> None:
                self.__enter__()
                try:
                    orig_setUpClass()
                except Exception:
                    self.__exit__(*sys.exc_info())
                    raise

            wrapped.setUpClass = classmethod(setUpClass)  # type: ignore[assignment]

            orig_tearDownClass = wrapped.tearDownClass

            @functools.wraps(orig_tearDownClass)
            def tearDownClass(cls: Type[TestCase]) -> None:
                orig_tearDownClass()
                self.__exit__(None, None, None)

            wrapped.tearDownClass = classmethod(  # type: ignore[assignment]
                tearDownClass
            )
            return wrapped
        elif inspect.iscoroutinefunction(wrapped):

            @functools.wraps(wrapped)
            async def wrapper(*args: Any, **kwargs: Any) -> Any:
                with self:
                    # mypy has not narrowed 'wrapped' to a coroutine function
                    return await wrapped(
                        *args,
                        **kwargs,
                    )  # type: ignore [misc,operator]

            return wrapper
        else:
            assert callable(wrapped)

            @functools.wraps(wrapped)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                with self:
                    return wrapped(*args, **kwargs)

            return wrapper


# datetime module


def now(tz: Optional[dt.tzinfo] = None) -> dt.datetime:
    if not coordinates_stack:
        return _time_machine.original_now(tz)
    else:
        return dt.datetime.fromtimestamp(time(), tz)


def utcnow() -> dt.datetime:
    if not coordinates_stack:
        return _time_machine.original_utcnow()
    else:
        return dt.datetime.utcfromtimestamp(time())


# time module


def clock_gettime(clk_id: int) -> float:
    if not coordinates_stack or clk_id != CLOCK_REALTIME:
        return _time_machine.original_clock_gettime(clk_id)
    return time()


if sys.version_info >= (3, 7):

    def clock_gettime_ns(clk_id: int) -> int:
        if not coordinates_stack or clk_id != CLOCK_REALTIME:
            return _time_machine.original_clock_gettime_ns(clk_id)
        return time_ns()


def gmtime(secs: Optional[float] = None) -> struct_time:
    if not coordinates_stack or secs is not None:
        return _time_machine.original_gmtime(secs)
    return _time_machine.original_gmtime(coordinates_stack[-1].time())


def localtime(secs: Optional[float] = None) -> struct_time:
    if not coordinates_stack or secs is not None:
        return _time_machine.original_localtime(secs)
    return _time_machine.original_localtime(coordinates_stack[-1].time())


# copied from typeshed:
_TimeTuple = Tuple[int, int, int, int, int, int, int, int, int]


def strftime(format: str, t: Union[_TimeTuple, struct_time, None] = None) -> str:
    if t is not None:
        return _time_machine.original_strftime(format, t)
    elif not coordinates_stack:
        return _time_machine.original_strftime(format)
    return _time_machine.original_strftime(format, localtime())


def time() -> float:
    if not coordinates_stack:
        return _time_machine.original_time()
    return coordinates_stack[-1].time()


if sys.version_info >= (3, 7):

    def time_ns() -> int:
        if not coordinates_stack:
            return _time_machine.original_time_ns()
        else:
            return coordinates_stack[-1].time_ns()


# pytest plugin

if pytest is not None:  # pragma: no branch

    class TimeMachineFixture:
        traveller: Optional[travel]
        coordinates: Optional[Coordinates]

        def __init__(self) -> None:
            self.traveller = None
            self.coordinates = None

        def move_to(
            self,
            destination: DestinationType,
            tick: Optional[bool] = None,
        ) -> None:
            if self.traveller is None:
                if tick is None:
                    tick = True
                self.traveller = travel(destination, tick=tick)
                self.coordinates = self.traveller.start()
            else:
                assert self.coordinates is not None
                self.coordinates.move_to(destination, tick=tick)

        def stop(self) -> None:
            if self.traveller is not None:
                self.traveller.stop()

    @pytest.fixture(name="time_machine")
    def time_machine_fixture() -> TypingGenerator[TimeMachineFixture, None, None]:
        fixture = TimeMachineFixture()
        try:
            yield fixture
        finally:
            fixture.stop()
