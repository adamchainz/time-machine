from __future__ import annotations

import datetime as dt
import os
import sys
import time
import uuid
import warnings
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from unittest import mock
from zoneinfo import ZoneInfo

import pytest

if sys.version_info[:2] == (3, 13) and not sys._is_gil_enabled():
    # Hypothesis has no free-threaded wheels for Python 3.13, and cannot be
    # built from source there, since PyO3 does not support free-threaded
    # Python < 3.14.
    pytest.skip("Hypothesis unavailable", allow_module_level=True)

from hypothesis import assume, given, settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, precondition, rule

import time_machine

NANOSECONDS_PER_SECOND = time_machine.NANOSECONDS_PER_SECOND
EPOCH_AWARE = dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)

# Bounds that keep generated timestamps positive, whatever timezone offset is
# applied, and well within the range that all supported platforms can convert.
MIN_DATETIME = dt.datetime(1970, 1, 2)
MAX_DATETIME = dt.datetime(2500, 1, 1)
MIN_TIMESTAMP = MIN_DATETIME.replace(tzinfo=dt.timezone.utc).timestamp()
MAX_TIMESTAMP = MAX_DATETIME.replace(tzinfo=dt.timezone.utc).timestamp()

# The "right/*" zones count leap seconds in POSIX timestamps, which makes
# timestamps inconsistent with datetime arithmetic. They're only installed on
# some systems.
zoneinfos = st.timezones().filter(lambda tz: not tz.key.startswith("right/"))

naive_datetimes = st.datetimes(min_value=MIN_DATETIME, max_value=MAX_DATETIME)
aware_datetimes = st.datetimes(
    min_value=MIN_DATETIME,
    max_value=MAX_DATETIME,
    timezones=st.just(dt.timezone.utc) | zoneinfos,
)
timestamps = st.floats(min_value=MIN_TIMESTAMP, max_value=MAX_TIMESTAMP)


def datetime_to_ns(destination: dt.datetime) -> int:
    # timedelta arithmetic is exact, unlike float timestamps.
    return (destination - EPOCH_AWARE) // dt.timedelta(microseconds=1) * 1_000


def timedelta_to_ns(delta: dt.timedelta) -> int:
    return delta // dt.timedelta(microseconds=1) * 1_000


@settings(deadline=None)
@given(timestamp=timestamps)
def test_travel_to_timestamp(timestamp):
    expected_ns = round(timestamp * NANOSECONDS_PER_SECOND)
    with time_machine.travel(timestamp, tick=False):
        assert time.time_ns() == expected_ns
        assert time.time() == expected_ns / NANOSECONDS_PER_SECOND


@settings(deadline=None)
@given(destination=aware_datetimes)
def test_travel_to_aware_datetime(destination):
    with time_machine.travel(destination, tick=False):
        assert time.time_ns() == datetime_to_ns(destination)
        now_utc = dt.datetime.now(dt.timezone.utc)
        assert now_utc == destination
        assert dt.datetime.now(destination.tzinfo) == now_utc


@settings(deadline=None)
@given(destination=naive_datetimes)
def test_travel_to_naive_datetime_treated_as_utc(destination):
    # In the default naive_mode (MIXED), naive datetimes are treated as UTC.
    with time_machine.travel(destination, tick=False):
        assert time.time_ns() == datetime_to_ns(
            destination.replace(tzinfo=dt.timezone.utc)
        )
        assert dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) == destination


@settings(deadline=None)
@given(
    destination=st.dates(min_value=MIN_DATETIME.date(), max_value=MAX_DATETIME.date())
)
def test_travel_to_date(destination):
    midnight = dt.datetime.combine(destination, dt.time(0, 0), tzinfo=dt.timezone.utc)
    with time_machine.travel(destination, tick=False):
        assert time.time_ns() == datetime_to_ns(midnight)
        assert time.time() == midnight.timestamp()
        now = dt.datetime.now(dt.timezone.utc)
        assert now == midnight
        assert now.date() == destination


@settings(deadline=None)
@given(destination=aware_datetimes)
def test_travel_to_isoformat_string(destination):
    with time_machine.travel(destination.isoformat(), tick=False):
        assert time.time_ns() == datetime_to_ns(destination)


@settings(deadline=None)
@given(outer=timestamps, inner=timestamps)
def test_travel_nested(outer, inner):
    with time_machine.travel(outer, tick=False):
        with time_machine.travel(inner, tick=False):
            assert time.time_ns() == round(inner * NANOSECONDS_PER_SECOND)
        assert time.time_ns() == round(outer * NANOSECONDS_PER_SECOND)


@settings(deadline=None)
@given(timestamp=timestamps)
def test_travel_tick_monotonic(timestamp):
    expected_ns = round(timestamp * NANOSECONDS_PER_SECOND)
    with time_machine.travel(timestamp):
        first = time.time_ns()
        second = time.time_ns()
        assert expected_ns <= first <= second
        assert second - first < 10 * NANOSECONDS_PER_SECOND


@settings(deadline=None)
@given(
    delta=st.timedeltas(
        min_value=dt.timedelta(days=-18_000), max_value=dt.timedelta(days=18_000)
    )
)
def test_shift_timedelta(delta):
    start = dt.datetime(2020, 4, 29, tzinfo=dt.timezone.utc)
    with time_machine.travel(start, tick=False) as traveller:
        traveller.shift(delta)
        assert time.time_ns() == datetime_to_ns(start) + timedelta_to_ns(delta)


@settings(deadline=None)
@given(
    delta_seconds=st.integers(min_value=-(2**30), max_value=2**30)
    | st.floats(min_value=-(2.0**30), max_value=2.0**30)
)
def test_shift_number(delta_seconds):
    start = dt.datetime(2020, 4, 29, tzinfo=dt.timezone.utc)
    expected_delta_ns = round(delta_seconds * NANOSECONDS_PER_SECOND)
    with time_machine.travel(start, tick=False) as traveller:
        traveller.shift(delta_seconds)
        assert time.time_ns() == datetime_to_ns(start) + expected_delta_ns


@settings(deadline=None)
@given(first=timestamps, second=timestamps)
def test_move_to(first, second):
    with time_machine.travel(first, tick=False) as traveller:
        assert time.time_ns() == round(first * NANOSECONDS_PER_SECOND)
        traveller.move_to(second)
        assert time.time_ns() == round(second * NANOSECONDS_PER_SECOND)


@pytest.mark.skipif(
    not hasattr(time, "tzset"), reason="Doesn't have tzset, so travel() can't set TZ"
)
@settings(deadline=None)
@given(
    # Past 2038, some platforms' time functions stop applying zones' POSIX DST
    # rules, diverging from zoneinfo.
    destination=st.datetimes(min_value=MIN_DATETIME, max_value=dt.datetime(2038, 1, 1)),
    tz=zoneinfos,
)
def test_localtime_and_gmtime_match_datetime(destination, tz):
    aware = destination.replace(tzinfo=tz)
    with time_machine.travel(aware, tick=False):
        seconds = time.time_ns() // NANOSECONDS_PER_SECOND

        local = time.localtime()
        expected_local = dt.datetime.fromtimestamp(seconds, tz)
        assert (
            local.tm_year,
            local.tm_mon,
            local.tm_mday,
            local.tm_hour,
            local.tm_min,
            local.tm_sec,
        ) == (
            expected_local.year,
            expected_local.month,
            expected_local.day,
            expected_local.hour,
            expected_local.minute,
            expected_local.second,
        )
        utcoffset = expected_local.utcoffset()
        assert utcoffset is not None
        assert local.tm_gmtoff == int(utcoffset.total_seconds())

        utc = time.gmtime()
        expected_utc = dt.datetime.fromtimestamp(seconds, dt.timezone.utc)
        assert (
            utc.tm_year,
            utc.tm_mon,
            utc.tm_mday,
            utc.tm_hour,
            utc.tm_min,
            utc.tm_sec,
        ) == (
            expected_utc.year,
            expected_utc.month,
            expected_utc.day,
            expected_utc.hour,
            expected_utc.minute,
            expected_utc.second,
        )


@given(timestamp=timestamps)
def test_extract_timestamp_tzname_number(timestamp):
    assert time_machine.extract_timestamp_tzname(timestamp) == (
        round(timestamp * NANOSECONDS_PER_SECOND),
        None,
    )
    int_timestamp = int(timestamp)
    assert time_machine.extract_timestamp_tzname(int_timestamp) == (
        int_timestamp * NANOSECONDS_PER_SECOND,
        None,
    )


@given(destination=naive_datetimes, tz=zoneinfos)
def test_extract_timestamp_tzname_zoneinfo_datetime(destination, tz):
    aware = destination.replace(tzinfo=tz)
    timestamp_ns, tzname = time_machine.extract_timestamp_tzname(aware)
    assert timestamp_ns == datetime_to_ns(aware)
    assert tzname == tz.key


@given(destination=naive_datetimes)
def test_extract_timestamp_tzname_utc_datetime(destination):
    aware = destination.replace(tzinfo=dt.timezone.utc)
    timestamp_ns, tzname = time_machine.extract_timestamp_tzname(aware)
    assert timestamp_ns == datetime_to_ns(aware)
    assert tzname == "UTC"


@given(
    delta=st.timedeltas(
        min_value=dt.timedelta(days=-1_000), max_value=dt.timedelta(days=1_000)
    )
)
def test_extract_timestamp_tzname_timedelta(delta):
    delta_ns = timedelta_to_ns(delta)
    before_ns = time.time_ns()
    timestamp_ns, tzname = time_machine.extract_timestamp_tzname(delta)
    after_ns = time.time_ns()
    assert tzname is None
    assert before_ns + delta_ns <= timestamp_ns <= after_ns + delta_ns


# Consistency of all the mocked functions


def utc_datetime_from_ns(timestamp_ns: int) -> dt.datetime:
    return EPOCH_AWARE + dt.timedelta(microseconds=timestamp_ns // 1_000)


def struct_time_fields(value: time.struct_time) -> tuple[int, ...]:
    return (
        value.tm_year,
        value.tm_mon,
        value.tm_mday,
        value.tm_hour,
        value.tm_min,
        value.tm_sec,
    )


def datetime_fields(value: dt.datetime) -> tuple[int, ...]:
    return (
        value.year,
        value.month,
        value.day,
        value.hour,
        value.minute,
        value.second,
    )


utc_datetimes = st.datetimes(
    min_value=MIN_DATETIME, max_value=MAX_DATETIME, timezones=st.just(dt.timezone.utc)
)


@settings(deadline=None)
@given(destination=utc_datetimes)
def test_mocked_functions_agree(destination):
    """
    Every mocked function returns its representation of the same instant.
    The local timezone is UTC, per conftest.py, and not changed by UTC
    destinations.
    """
    expected_ns = datetime_to_ns(destination)
    expected_utc = destination.astimezone(dt.timezone.utc)
    expected_naive = expected_utc.replace(tzinfo=None)
    expected_seconds = expected_ns // NANOSECONDS_PER_SECOND

    with time_machine.travel(destination, tick=False):
        assert time.time_ns() == expected_ns
        assert time.time() == expected_ns / NANOSECONDS_PER_SECOND
        assert time.clock_gettime_ns(time.CLOCK_REALTIME) == expected_ns
        assert time.clock_gettime(time.CLOCK_REALTIME) == time.time()

        assert dt.datetime.now(dt.timezone.utc) == expected_utc
        assert dt.datetime.now() == expected_naive
        assert dt.datetime.today() == expected_naive
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            assert dt.datetime.utcnow() == expected_naive
        assert dt.date.today() == expected_naive.date()

        assert struct_time_fields(time.gmtime()) == datetime_fields(expected_utc)
        assert struct_time_fields(time.localtime()) == datetime_fields(expected_utc)
        assert time.gmtime().tm_gmtoff == 0
        assert time.strftime("%Y-%m-%d %H:%M:%S") == expected_utc.strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        # Explicit arguments are unaffected.
        assert time.gmtime(expected_seconds) == time.gmtime()
        assert time.localtime(expected_seconds) == time.localtime()
        assert time.strftime("%Y-%m-%d", time.gmtime(0)) == "1970-01-01"

        # Other clocks are unaffected.
        assert abs(time.clock_gettime(time.CLOCK_MONOTONIC) - time.monotonic()) < 1.0


@settings(deadline=None)
@given(
    destination=aware_datetimes,
    offset=st.integers(min_value=-24 * 3600 + 1, max_value=24 * 3600 - 1),
)
def test_datetime_now_fixed_offset(destination, offset):
    tz = dt.timezone(dt.timedelta(seconds=offset))
    with time_machine.travel(destination, tick=False):
        assert dt.datetime.now(tz) == destination.astimezone(tz)
        assert dt.datetime.now(tz=tz) == destination.astimezone(tz)


@settings(deadline=None)
@given(destination=utc_datetimes)
def test_datetime_subclasses(destination):
    class MyDate(dt.date):
        pass

    class MyDateTime(dt.datetime):
        pass

    expected_naive = destination.astimezone(dt.timezone.utc).replace(tzinfo=None)

    with time_machine.travel(destination, tick=False):
        now = MyDateTime.now()
        assert type(now) is MyDateTime
        assert now == expected_naive

        now_utc = MyDateTime.now(dt.timezone.utc)
        assert type(now_utc) is MyDateTime
        assert now_utc == destination

        today = MyDateTime.today()
        assert type(today) is MyDateTime
        assert today == expected_naive

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            utcnow = MyDateTime.utcnow()
        assert type(utcnow) is MyDateTime
        assert utcnow == expected_naive

        date_today = MyDate.today()
        assert type(date_today) is MyDate
        assert date_today == expected_naive.date()


strftime_directives = st.sampled_from(
    [
        "%Y",
        "%m",
        "%d",
        "%H",
        "%M",
        "%S",
        "%j",
        "%a",
        "%A",
        "%b",
        "%B",
        "%p",
        "%y",
        "%Z",
        "%z",
        "%c",
        "%x",
        "%X",
        "%U",
        "%W",
        "%w",
        "%I",
        "%%",
        " ",
        "-",
        "ünïcode",
    ]
)


@settings(deadline=None)
@given(
    # Past 2038, some platforms' time functions stop applying zones' POSIX DST
    # rules, diverging from zoneinfo.
    destination=st.datetimes(
        min_value=MIN_DATETIME,
        max_value=dt.datetime(2038, 1, 1),
        timezones=st.just(dt.timezone.utc) | zoneinfos,
    ),
    directives=st.lists(strftime_directives, min_size=1, max_size=6),
)
def test_strftime_formats(destination, directives):
    fmt = "".join(directives)
    with time_machine.travel(destination, tick=False):
        assert time.strftime(fmt) == time.strftime(fmt, time.localtime())


# uuid


def time_from_uuid1(value: uuid.UUID) -> int:
    """The timestamp of a uuid1() or uuid6() value, in nanoseconds."""
    return (value.time - 0x01B21DD213814000) * 100


def time_from_uuid7(value: uuid.UUID) -> int:
    """The timestamp of a uuid7() value, in nanoseconds."""
    return value.time * 1_000_000


uuid_generators = [(uuid.uuid1, time_from_uuid1, 100)]
if sys.version_info >= (3, 14):
    uuid_generators.append((uuid.uuid6, time_from_uuid1, 100))
    uuid_generators.append((uuid.uuid7, time_from_uuid7, 1_000_000))


@settings(deadline=None)
@given(
    destination=aware_datetimes,
    delta=st.timedeltas(
        min_value=dt.timedelta(days=-1_000), max_value=dt.timedelta(days=1_000)
    ),
)
def test_uuid_timestamps(destination, delta):
    """
    Time-based UUIDs are generated for the mocked time, including after
    shifting in either direction, despite the uuid module's monotonicity
    caching.
    """
    # Without a shift, the second value is bumped to keep values monotonic.
    assume(delta != dt.timedelta(0))
    expected_ns = datetime_to_ns(destination)
    for generate, time_from, resolution_ns in uuid_generators:
        with time_machine.travel(destination, tick=False) as traveller:
            assert time_from(generate()) == expected_ns // resolution_ns * resolution_ns
            traveller.shift(delta)
            shifted_ns = expected_ns + timedelta_to_ns(delta)
            assert time_from(generate()) == shifted_ns // resolution_ns * resolution_ns


# Relative destinations


@settings(deadline=None)
@given(
    first=timestamps,
    delta=st.timedeltas(
        min_value=dt.timedelta(days=-1_000), max_value=dt.timedelta(days=1_000)
    ),
)
def test_relative_destinations_use_mocked_time(first, delta):
    first_ns = round(first * NANOSECONDS_PER_SECOND)
    delta_ns = timedelta_to_ns(delta)
    with time_machine.travel(first, tick=False) as traveller:
        with time_machine.travel(delta, tick=False):
            assert time.time_ns() == first_ns + delta_ns
        with time_machine.travel(None, tick=False):
            assert time.time_ns() == first_ns

        traveller.move_to(delta)
        assert time.time_ns() == first_ns + delta_ns
        traveller.move_to(None)
        assert time.time_ns() == first_ns + delta_ns


@settings(deadline=None)
@given(timestamp=timestamps)
def test_callable_and_generator_destinations(timestamp):
    expected_ns = round(timestamp * NANOSECONDS_PER_SECOND)

    def generate() -> Generator[float, None, None]:
        yield timestamp
        yield 0.0

    with time_machine.travel(lambda: timestamp, tick=False):
        assert time.time_ns() == expected_ns
    with time_machine.travel(generate(), tick=False):
        assert time.time_ns() == expected_ns


# Strings


@settings(deadline=None)
@given(
    destination=aware_datetimes,
    style=st.sampled_from(["T", "space", "milliseconds", "seconds", "Z"]),
)
def test_travel_to_string_variants(destination, style):
    if style == "T":
        value = destination.isoformat()
    elif style == "space":
        value = destination.isoformat(sep=" ")
    elif style == "milliseconds":
        value = destination.isoformat(timespec="milliseconds")
    elif style == "seconds":
        value = destination.isoformat(timespec="seconds")
    else:
        value = destination.astimezone(dt.timezone.utc).isoformat()
        value = value.replace("+00:00", "Z")
    expected = dt.datetime.fromisoformat(value)
    with time_machine.travel(value, tick=False):
        assert time.time_ns() == datetime_to_ns(expected)


# Naive modes and the local timezone


@contextmanager
def local_timezone(key: str) -> Iterator[None]:
    orig_tz = os.environ.get("TZ")
    os.environ["TZ"] = key
    time.tzset()
    try:
        yield
    finally:
        if orig_tz is None:
            del os.environ["TZ"]
        else:
            os.environ["TZ"] = orig_tz
        time.tzset()


def unambiguous_local(destination: dt.datetime, tz: ZoneInfo) -> bool:
    """
    Check that the naive datetime is neither in a gap nor a fold of the given
    zone, so its local interpretation is unambiguous.
    """
    aware = destination.replace(tzinfo=tz)
    if aware.utcoffset() != aware.replace(fold=1).utcoffset():
        return False
    return (
        dt.datetime.fromtimestamp(aware.timestamp(), tz).replace(tzinfo=None)
        == destination
    )


@pytest.mark.skipif(
    not hasattr(time, "tzset"), reason="Doesn't have tzset, so TZ can't be set"
)
@settings(deadline=None)
@given(
    destination=st.datetimes(min_value=MIN_DATETIME, max_value=dt.datetime(2038, 1, 1)),
    tz=zoneinfos,
    mode=st.sampled_from(list(time_machine.NaiveMode)),
)
def test_naive_datetime_modes(destination, tz, mode):
    assume(unambiguous_local(destination, tz))
    as_utc = destination.replace(tzinfo=dt.timezone.utc)
    as_local = destination.replace(tzinfo=tz)

    with (
        local_timezone(tz.key),
        mock.patch.object(time_machine, "naive_mode", mode),
    ):
        if mode == time_machine.NaiveMode.ERROR:
            with pytest.raises(RuntimeError):
                time_machine.travel(destination)
            with pytest.raises(RuntimeError):
                time_machine.travel(destination.date())
            with pytest.raises(RuntimeError):
                time_machine.travel(destination.isoformat())
            return

        if mode == time_machine.NaiveMode.LOCAL:
            expected = as_local
            expected_date = dt.datetime.combine(
                destination.date(), dt.time(0, 0), tzinfo=tz
            )
        else:
            expected = as_utc
            expected_date = dt.datetime.combine(
                destination.date(), dt.time(0, 0), tzinfo=dt.timezone.utc
            )
        if mode == time_machine.NaiveMode.UTC:
            expected_string = as_utc
        else:
            # Naive strings are local in MIXED mode, for backwards compatibility.
            expected_string = as_local

        with time_machine.travel(destination, tick=False):
            assert time.time_ns() == datetime_to_ns(expected)
        with time_machine.travel(destination.isoformat(), tick=False):
            assert time.time_ns() == datetime_to_ns(expected_string)
        assume(
            unambiguous_local(dt.datetime.combine(destination.date(), dt.time()), tz)
        )
        with time_machine.travel(destination.date(), tick=False):
            assert time.time_ns() == datetime_to_ns(expected_date)


# Escape hatch


@settings(deadline=None)
@given(destination=aware_datetimes)
def test_escape_hatch_returns_real_time(destination):
    with time_machine.travel(destination, tick=False):
        real_ns = time_machine.escape_hatch.time.time_ns()
        assert real_ns >= LIBRARY_EPOCH_NS
        assert time_machine.escape_hatch.time.time() >= LIBRARY_EPOCH_NS / 1e9
        assert time_machine.escape_hatch.datetime.datetime.now(
            dt.timezone.utc
        ) >= utc_datetime_from_ns(LIBRARY_EPOCH_NS)
        assert time_machine.escape_hatch.datetime.date.today() >= (
            utc_datetime_from_ns(LIBRARY_EPOCH_NS).date() - dt.timedelta(days=1)
        )
        assert time_machine.escape_hatch.time.gmtime().tm_year >= 2020
        assert time_machine.escape_hatch.time.localtime().tm_year >= 2020
        assert int(time_machine.escape_hatch.time.strftime("%Y")) >= 2020
        assert (
            time_machine.escape_hatch.time.clock_gettime_ns(time.CLOCK_REALTIME)
            >= LIBRARY_EPOCH_NS
        )


LIBRARY_EPOCH_NS = datetime_to_ns(dt.datetime(2020, 4, 29, tzinfo=dt.timezone.utc))


# Stateful testing of nested travel, shift() and move_to()


class TravelMachine(RuleBasedStateMachine):
    """
    Perform random sequences of travelling, shifting, moving and stopping,
    checking that the mocked time always matches a simple model.
    """

    def __init__(self) -> None:
        super().__init__()
        self.travels: list[time_machine.travel] = []
        self.travellers: list[time_machine.Traveller] = []
        self.expected_ns: list[int] = []

    @rule(
        timestamp=st.integers(
            min_value=int(MIN_TIMESTAMP), max_value=int(MAX_TIMESTAMP)
        )
    )
    def start(self, timestamp: int) -> None:
        travel = time_machine.travel(timestamp, tick=False)
        self.travels.append(travel)
        self.travellers.append(travel.start())
        self.expected_ns.append(timestamp * NANOSECONDS_PER_SECOND)

    @precondition(lambda self: self.travels)
    @rule()
    def stop(self) -> None:
        self.travels.pop().stop()
        self.travellers.pop()
        self.expected_ns.pop()

    @precondition(lambda self: self.travels)
    @rule(
        delta=st.integers(min_value=-(10**9), max_value=10**9)
        | st.timedeltas(
            min_value=dt.timedelta(days=-10_000), max_value=dt.timedelta(days=10_000)
        )
    )
    def shift(self, delta: int | dt.timedelta) -> None:
        self.travellers[-1].shift(delta)
        if isinstance(delta, int):
            self.expected_ns[-1] += delta * NANOSECONDS_PER_SECOND
        else:
            self.expected_ns[-1] += timedelta_to_ns(delta)

    @precondition(lambda self: self.travels)
    @rule(destination=aware_datetimes)
    def move_to(self, destination: dt.datetime) -> None:
        self.travellers[-1].move_to(destination)
        self.expected_ns[-1] = datetime_to_ns(destination)

    @precondition(lambda self: self.travels)
    @rule(delta=st.integers(min_value=-(10**6), max_value=10**6))
    def move_to_relative(self, delta: int) -> None:
        self.travellers[-1].move_to(dt.timedelta(seconds=delta))
        self.expected_ns[-1] += delta * NANOSECONDS_PER_SECOND

    @invariant()
    def time_matches_model(self) -> None:
        assert time_machine.escape_hatch.is_travelling() == bool(self.travels)
        if self.travels:
            assert time.time_ns() == self.expected_ns[-1]
            assert dt.datetime.now(dt.timezone.utc) == utc_datetime_from_ns(
                self.expected_ns[-1]
            )
        else:
            assert time.time_ns() >= LIBRARY_EPOCH_NS

    def teardown(self) -> None:
        while self.travels:
            self.travels.pop().stop()


TestTravelMachine = TravelMachine.TestCase
TestTravelMachine.settings = settings(
    deadline=None, max_examples=100, stateful_step_count=30
)
