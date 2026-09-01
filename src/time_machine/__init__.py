from __future__ import annotations

import datetime as dt
import functools
import inspect
import os
import sys
import time as time_module
import uuid
from collections.abc import Awaitable, Callable, Generator
from collections.abc import Generator as TypingGenerator
from enum import Enum
from time import gmtime as orig_gmtime
from time import struct_time
from types import TracebackType
from typing import Any, TypeAlias, TypeVar, cast, overload
from unittest import TestCase
from zoneinfo import ZoneInfo

import _time_machine

if sys.version_info >= (3, 11):
    from typing import assert_never
else:

    def assert_never(_: Any) -> None:  # pragma: no cover
        pass


try:
    from time import tzset
except ImportError:  # pragma: no cover
    HAVE_TZSET = False  # Windows
else:
    HAVE_TZSET = True

try:
    from dateutil.parser import parse as parse_datetime
except ImportError:  # pragma: no cover
    HAVE_DATEUTIL = False
else:
    HAVE_DATEUTIL = True

try:
    import pytest
except ImportError:  # pragma: no cover
    HAVE_PYTEST = False
else:
    HAVE_PYTEST = True

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

# uuid1(), uuid6(), and uuid7() cache the timestamp of the last value they
# generated in a module-level global, and never generate a value before it.
# We therefore clear those caches when we travel backwards in time, so that
# those functions generate values with correct timestamps.
_uuid_dict = uuid.__dict__
_uuid_reset = {"_last_timestamp": None}
if sys.version_info >= (3, 14):
    _uuid_reset["_last_timestamp_v6"] = None
    _uuid_reset["_last_timestamp_v7"] = None


def _reset_uuid_timestamps() -> None:
    _uuid_dict.update(_uuid_reset)


DestinationBaseType: TypeAlias = (
    int | float | dt.datetime | dt.timedelta | dt.date | str | None
)
DestinationType: TypeAlias = (
    DestinationBaseType
    | Callable[[], DestinationBaseType]
    | TypingGenerator[DestinationBaseType, None, None]
)

_F = TypeVar("_F", bound=Callable[..., Any])
_AF = TypeVar("_AF", bound=Callable[..., Awaitable[Any]])
TestCaseType = TypeVar("TestCaseType", bound=type[TestCase])

# copied from typeshed:
_TimeTuple = tuple[int, int, int, int, int, int, int, int, int]


class NaiveMode(Enum):
    MIXED = 1
    UTC = 2
    LOCAL = 3
    ERROR = 4


naive_mode = NaiveMode.MIXED


def _datetime_to_ns(destination: dt.datetime) -> int:
    # timestamp() on a whole-second datetime returns an integer-valued float,
    # exact for any supported year since UTC offsets are whole seconds, so the
    # nanosecond timestamp can be computed with exact integer arithmetic.
    seconds = int(destination.replace(microsecond=0).timestamp())
    return seconds * NANOSECONDS_PER_SECOND + destination.microsecond * 1_000


def _timedelta_to_ns(delta: dt.timedelta) -> int:
    return (
        delta.days * 86_400 + delta.seconds
    ) * NANOSECONDS_PER_SECOND + delta.microseconds * 1_000


def extract_timestamp_tzname(
    destination: DestinationType,
) -> tuple[int, str | None]:
    dest: DestinationBaseType
    if isinstance(destination, Generator):
        dest = next(destination)
    elif callable(destination):
        dest = destination()
    else:
        dest = destination

    timestamp_ns: int
    tzname: str | None = None
    if dest is None:
        timestamp_ns = time_module.time_ns()
    elif isinstance(dest, int):
        timestamp_ns = dest * NANOSECONDS_PER_SECOND
    elif isinstance(dest, float):
        timestamp_ns = round(dest * NANOSECONDS_PER_SECOND)
    elif isinstance(dest, dt.datetime):
        if isinstance(dest.tzinfo, ZoneInfo):
            tzname = dest.tzinfo.key
        elif dest.tzinfo == dt.timezone.utc:
            tzname = "UTC"
        elif dest.tzinfo is None:
            if naive_mode == NaiveMode.MIXED or naive_mode == NaiveMode.UTC:
                dest = dest.replace(tzinfo=dt.timezone.utc)
            elif naive_mode == NaiveMode.LOCAL:
                pass
            elif naive_mode == NaiveMode.ERROR:
                raise RuntimeError(
                    "Naive datetime provided while time_machine.naive_mode is set to ERROR. "
                    "Please provide a timezone-aware datetime."
                )
            else:  # pragma: no cover
                assert_never(naive_mode)
        timestamp_ns = _datetime_to_ns(dest)
    elif isinstance(dest, dt.timedelta):
        timestamp_ns = time_module.time_ns() + _timedelta_to_ns(dest)
    elif isinstance(dest, dt.date):
        if naive_mode == NaiveMode.MIXED or naive_mode == NaiveMode.UTC:
            timestamp_ns = _datetime_to_ns(
                dt.datetime.combine(dest, dt.time(0, 0), tzinfo=dt.timezone.utc)
            )
        elif naive_mode == NaiveMode.LOCAL:
            timestamp_ns = _datetime_to_ns(dt.datetime.combine(dest, dt.time(0, 0)))
        elif naive_mode == NaiveMode.ERROR:
            raise RuntimeError(
                "date object provided while time_machine.naive_mode is set to ERROR. "
                "Please provide a timezone-aware datetime."
            )
        else:  # pragma: no cover
            assert_never(naive_mode)
    elif isinstance(dest, str):
        try:
            parsed = dt.datetime.fromisoformat(dest)
        except ValueError as exc:
            if HAVE_DATEUTIL:
                try:
                    parsed = parse_datetime(dest)
                except ValueError as dateutil_exc:
                    raise dateutil_exc from None
            else:
                raise exc

        if parsed.tzinfo is None:
            if naive_mode == NaiveMode.MIXED:
                # Keep as naive, for backwards compatibility
                pass
            elif naive_mode == NaiveMode.UTC:
                parsed = parsed.replace(tzinfo=dt.timezone.utc)
            elif naive_mode == NaiveMode.LOCAL:
                pass
            elif naive_mode == NaiveMode.ERROR:
                raise RuntimeError(
                    "Naive datetime string provided while time_machine.naive_mode is set to ERROR. "
                    "Please provide a timezone-aware datetime string."
                )
            else:  # pragma: no cover
                assert_never(naive_mode)
        timestamp_ns = _datetime_to_ns(parsed)
    else:
        raise TypeError(f"Unsupported destination {dest!r}")

    return timestamp_ns, tzname


class Traveller:
    def __init__(
        self,
        destination_timestamp_ns: int,
        destination_tzname: str | None,
        tick: bool,
    ) -> None:
        self._destination_timestamp_ns = destination_timestamp_ns
        self._destination_tzname = destination_tzname
        self._tick = tick
        self._requested = False

    def time_ns(self) -> int:
        if not self._tick:
            return self._destination_timestamp_ns

        base = SYSTEM_EPOCH_TIMESTAMP_NS + self._destination_timestamp_ns
        now_ns: int = _time_machine.original_time_ns()

        if not self._requested:
            self._requested = True
            self._real_start_timestamp_ns = now_ns
            return base

        return base + (now_ns - self._real_start_timestamp_ns)

    def shift(self, delta: dt.timedelta | int | float) -> None:
        if isinstance(delta, dt.timedelta):
            delta_ns = _timedelta_to_ns(delta)
        elif isinstance(delta, int):
            delta_ns = delta * NANOSECONDS_PER_SECOND
        elif isinstance(delta, float):
            delta_ns = round(delta * NANOSECONDS_PER_SECOND)
        else:
            raise TypeError(f"Unsupported type for delta argument: {delta!r}")

        self._destination_timestamp_ns += delta_ns

        if delta_ns < 0:
            # Moving forwards leaves the cached uuid timestamps in the past, so
            # only pay for resetting them when moving backwards.
            _reset_uuid_timestamps()

    def move_to(
        self,
        destination: DestinationType,
        tick: bool | None = None,
    ) -> None:
        self._stop()
        self._destination_timestamp_ns, self._destination_tzname = (
            extract_timestamp_tzname(destination)
        )
        self._requested = False
        self._start()
        if tick is not None:
            self._tick = tick

    def _start(self) -> None:
        _reset_uuid_timestamps()

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


traveller_stack: list[Traveller] = []
original_uuid_generate_time_safe = None
original_uuid_uuid_create = None


class travel:
    def __init__(self, destination: DestinationType, *, tick: bool = True) -> None:
        self.destination_timestamp_ns, self.destination_tzname = (
            extract_timestamp_tzname(destination)
        )
        self.tick = tick

    def start(self) -> Traveller:
        if "freezegun" in sys.modules and dt.datetime.__name__ == "FakeDatetime":
            raise RuntimeError("time-machine cannot start when freezegun is active.")

        if not traveller_stack:
            _time_machine.patch()

            # During time travel, patch the uuid module's time-based generation function to
            # None, which makes it use time.time(). Otherwise it makes a system call to
            # find the current datetime. The time it finds is stored in generated UUID1
            # values.
            global original_uuid_generate_time_safe
            global original_uuid_uuid_create

            original_uuid_generate_time_safe = uuid._generate_time_safe  # type: ignore[attr-defined]
            original_uuid_uuid_create = uuid._UuidCreate  # type: ignore[attr-defined]
            uuid._generate_time_safe = None  # type: ignore[attr-defined]
            uuid._UuidCreate = None  # type: ignore[attr-defined]

        traveller = Traveller(
            destination_timestamp_ns=self.destination_timestamp_ns,
            destination_tzname=self.destination_tzname,
            tick=self.tick,
        )
        traveller_stack.append(traveller)
        traveller._start()

        return traveller

    def stop(self) -> None:
        traveller_stack.pop()._stop()

        _reset_uuid_timestamps()

        if not traveller_stack:
            _time_machine.unpatch()

            global original_uuid_generate_time_safe
            global original_uuid_uuid_create

            uuid._generate_time_safe = original_uuid_generate_time_safe  # type: ignore[attr-defined]
            uuid._UuidCreate = original_uuid_uuid_create  # type: ignore[attr-defined]
            original_uuid_generate_time_safe = None
            original_uuid_uuid_create = None

    def __enter__(self) -> Traveller:
        return self.start()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.stop()

    async def __aenter__(self) -> Traveller:
        return self.start()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.stop()

    @overload
    def __call__(self, wrapped: TestCaseType) -> TestCaseType:  # pragma: no cover
        ...

    @overload
    def __call__(self, wrapped: _AF) -> _AF:  # pragma: no cover
        ...

    @overload
    def __call__(self, wrapped: _F) -> _F:  # pragma: no cover
        ...

    # 'Any' below is workaround for Mypy error:
    # Overloaded function implementation does not accept all possible arguments
    # of signature
    def __call__(
        self, wrapped: TestCaseType | _AF | _F | Any
    ) -> TestCaseType | _AF | _F | Any:
        if isinstance(wrapped, type):
            # Class decorator
            if not issubclass(wrapped, TestCase):
                raise TypeError("Can only decorate unittest.TestCase subclasses.")

            # Modify the setUpClass method
            orig_setUpClass = wrapped.setUpClass.__func__  # type: ignore[attr-defined]

            @functools.wraps(orig_setUpClass)
            def setUpClass(cls: type[TestCase]) -> None:
                self.__enter__()
                try:
                    orig_setUpClass(cls)
                except Exception:
                    self.__exit__(*sys.exc_info())
                    raise

            wrapped.setUpClass = classmethod(setUpClass)  # type: ignore[assignment]

            orig_tearDownClass = (
                wrapped.tearDownClass.__func__  # type: ignore[attr-defined]
            )

            @functools.wraps(orig_tearDownClass)
            def tearDownClass(cls: type[TestCase]) -> None:
                orig_tearDownClass(cls)
                self.__exit__(None, None, None)

            wrapped.tearDownClass = classmethod(  # type: ignore[assignment]
                tearDownClass
            )
            return cast(TestCaseType, wrapped)
        elif inspect.iscoroutinefunction(wrapped):

            @functools.wraps(wrapped)
            async def wrapper(*args: Any, **kwargs: Any) -> Any:
                with self:
                    return await wrapped(*args, **kwargs)

            return cast(_AF, wrapper)
        else:
            assert callable(wrapped)

            @functools.wraps(wrapped)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                with self:
                    return wrapped(*args, **kwargs)

            return cast(_F, wrapper)


# pytest plugin

if HAVE_PYTEST:  # pragma: no branch

    def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
        """
        Add the fixture to any tests with the marker.
        """
        for item in items:
            if item.get_closest_marker("time_machine"):
                item.fixturenames.insert(0, "time_machine")  # type: ignore[attr-defined]

    def pytest_configure(config: pytest.Config) -> None:
        """
        Register the marker.
        """
        config.addinivalue_line(
            "markers", "time_machine(...): set the time with time-machine"
        )

    class TimeMachineFixture:
        traveller: travel | None
        traveller_obj: Traveller | None

        def __init__(self) -> None:
            self.traveller = None
            self.traveller_obj = None

        def move_to(
            self,
            destination: DestinationType,
            tick: bool | None = None,
        ) -> None:
            if self.traveller is None:
                if tick is None:
                    tick = True
                self.traveller = travel(destination, tick=tick)
                self.traveller_obj = self.traveller.start()
            else:
                assert self.traveller_obj is not None
                self.traveller_obj.move_to(destination, tick=tick)

        def shift(self, delta: dt.timedelta | int | float) -> None:
            if self.traveller is None:
                raise RuntimeError(
                    "Initialize time_machine with move_to() before using shift()."
                )
            assert self.traveller_obj is not None
            self.traveller_obj.shift(delta=delta)

        def stop(self) -> None:
            if self.traveller is not None:
                self.traveller.stop()

    @pytest.fixture(name="time_machine")
    def time_machine_fixture(
        request: pytest.FixtureRequest,
    ) -> TypingGenerator[TimeMachineFixture, None, None]:
        fixture = TimeMachineFixture()
        marker = request.node.get_closest_marker("time_machine")
        if marker:
            fixture.move_to(*marker.args, **marker.kwargs)

        yield fixture
        fixture.stop()


# escape hatch


class _EscapeHatchDatetimeDate:
    def today(self) -> dt.date:
        # date.today() is equivalent to datetime.now().date().
        result: dt.datetime = _time_machine.original_now(None)
        return result.date()


class _EscapeHatchDatetimeDatetime:
    def now(self, tz: dt.tzinfo | None = None) -> dt.datetime:
        result: dt.datetime = _time_machine.original_now(tz)
        return result

    def today(self) -> dt.datetime:
        # datetime.today() is equivalent to datetime.now() without a timezone.
        result: dt.datetime = _time_machine.original_now(None)
        return result

    def utcnow(self) -> dt.datetime:
        result: dt.datetime = _time_machine.original_utcnow()
        return result


class _EscapeHatchDatetime:
    def __init__(self) -> None:
        self.date = _EscapeHatchDatetimeDate()
        self.datetime = _EscapeHatchDatetimeDatetime()


class _EscapeHatchTime:
    def clock_gettime(self, clk_id: int) -> float:
        result: float = _time_machine.original_clock_gettime(clk_id)
        return result

    def clock_gettime_ns(self, clk_id: int) -> int:
        result: int = _time_machine.original_clock_gettime_ns(clk_id)
        return result

    def gmtime(self, secs: float | None = None) -> struct_time:
        result: struct_time = _time_machine.original_gmtime(secs)
        return result

    def localtime(self, secs: float | None = None) -> struct_time:
        result: struct_time = _time_machine.original_localtime(secs)
        return result

    def strftime(self, format: str, t: _TimeTuple | struct_time | None = None) -> str:
        result: str
        if t is not None:
            result = _time_machine.original_strftime(format, t)
        else:
            result = _time_machine.original_strftime(format)
        return result

    def time(self) -> float:
        result: float = _time_machine.original_time()
        return result

    def time_ns(self) -> int:
        result: int = _time_machine.original_time_ns()
        return result


class _EscapeHatch:
    def __init__(self) -> None:
        self.datetime = _EscapeHatchDatetime()
        self.time = _EscapeHatchTime()

    def is_travelling(self) -> bool:
        return bool(traveller_stack)


escape_hatch = _EscapeHatch()
