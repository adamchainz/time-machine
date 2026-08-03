from __future__ import annotations

import datetime as dt
import time

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import time_machine

NANOSECONDS_PER_SECOND = time_machine.NANOSECONDS_PER_SECOND
EPOCH_AWARE = dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)

# Bounds that keep generated timestamps positive, whatever timezone offset is
# applied, and well within the range that all supported platforms can convert.
MIN_DATETIME = dt.datetime(1970, 1, 2)
MAX_DATETIME = dt.datetime(2500, 1, 1)
MIN_TIMESTAMP = MIN_DATETIME.replace(tzinfo=dt.timezone.utc).timestamp()
MAX_TIMESTAMP = MAX_DATETIME.replace(tzinfo=dt.timezone.utc).timestamp()

naive_datetimes = st.datetimes(min_value=MIN_DATETIME, max_value=MAX_DATETIME)
aware_datetimes = st.datetimes(
    min_value=MIN_DATETIME,
    max_value=MAX_DATETIME,
    timezones=st.just(dt.timezone.utc) | st.timezones(),
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
@given(destination=naive_datetimes, tz=st.timezones())
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


@given(destination=naive_datetimes, tz=st.timezones())
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
