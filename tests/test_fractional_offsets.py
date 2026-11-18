from __future__ import annotations

import datetime as dt
import time
from zoneinfo import ZoneInfo

import pytest

import time_machine


@pytest.mark.parametrize(
    "offset_us", [1, -1, 500_000, -500_000, 30_123_456, -30_123_456]
)
def test_aware_destination_preserves_fractional_offset(offset_us):
    destination = dt.datetime(
        2000,
        1,
        1,
        microsecond=123_456,
        tzinfo=dt.timezone(dt.timedelta(microseconds=offset_us)),
    )
    expected = destination.astimezone(dt.UTC)

    with time_machine.travel(destination, tick=False):
        assert time.time_ns() == 946_684_800_123_456_000 - offset_us * 1_000
        assert dt.datetime.now(dt.UTC) == expected


@pytest.mark.parametrize("offset_us", [30_123_456, -30_123_456])
def test_string_destination_preserves_fractional_offset(offset_us):
    destination = dt.datetime(
        2000,
        1,
        1,
        microsecond=123_456,
        tzinfo=dt.timezone(dt.timedelta(microseconds=offset_us)),
    )
    with time_machine.travel(destination.isoformat(), tick=False):
        assert dt.datetime.now(dt.UTC) == destination.astimezone(dt.UTC)


@pytest.mark.parametrize(
    ("destination", "expected_ns"),
    [
        (
            dt.datetime(
                1969,
                12,
                31,
                23,
                59,
                59,
                875_000,
                tzinfo=dt.timezone(dt.timedelta(microseconds=500_000)),
            ),
            -625_000_000,
        ),
        (
            dt.datetime(
                2500,
                1,
                1,
                microsecond=1,
                tzinfo=dt.timezone(dt.timedelta(microseconds=-1)),
            ),
            16_725_225_600_000_002_000,
        ),
        (
            dt.datetime(1, 1, 1, tzinfo=dt.timezone(dt.timedelta(microseconds=1))),
            -62_135_596_800_000_001_000,
        ),
        (
            dt.datetime(
                9999,
                12,
                31,
                23,
                59,
                59,
                999_999,
                tzinfo=dt.timezone(dt.timedelta(microseconds=-1)),
            ),
            253_402_300_800_000_000_000,
        ),
    ],
)
def test_fractional_offset_timestamp_is_exact(destination, expected_ns):
    with time_machine.travel(destination, tick=False):
        assert time.time_ns() == expected_ns


def test_move_to_preserves_fractional_offset():
    destination = dt.datetime(
        2000, 1, 1, tzinfo=dt.timezone(dt.timedelta(microseconds=500_000))
    )
    with time_machine.travel(0, tick=False) as traveller:
        traveller.move_to(destination)
        assert time.time_ns() == 946_684_799_500_000_000


@pytest.mark.parametrize("fold", [0, 1])
def test_aware_destination_preserves_fold(fold):
    destination = dt.datetime(
        2020, 11, 1, 1, 30, fold=fold, tzinfo=ZoneInfo("America/New_York")
    )
    expected = destination.astimezone(dt.UTC)
    with time_machine.travel(destination, tick=False):
        assert dt.datetime.now(dt.UTC) == expected


def test_timezone_with_no_offset_preserves_error():
    class NoOffset(dt.tzinfo):
        def utcoffset(self, value):
            return None

        def dst(self, value):
            return None

        def tzname(self, value):
            return None

    with pytest.raises(TypeError):
        time_machine.travel(dt.datetime(2000, 1, 1, tzinfo=NoOffset()), tick=False)
