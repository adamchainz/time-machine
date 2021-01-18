import asyncio
import datetime as dt
import sys
import time
import uuid
from importlib.util import module_from_spec, spec_from_file_location
from unittest import SkipTest, TestCase, mock

import pytest
from dateutil import tz

import time_machine

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

NANOSECONDS_PER_SECOND = time_machine.NANOSECONDS_PER_SECOND
EPOCH_DATETIME = dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)
EPOCH = EPOCH_DATETIME.timestamp()
EPOCH_PLUS_ONE_YEAR_DATETIME = dt.datetime(1971, 1, 1, tzinfo=dt.timezone.utc)
EPOCH_PLUS_ONE_YEAR = EPOCH_PLUS_ONE_YEAR_DATETIME.timestamp()
LIBRARY_EPOCH_DATETIME = dt.datetime(2020, 4, 29)  # The day this library was made
LIBRARY_EPOCH = LIBRARY_EPOCH_DATETIME.timestamp()

py_3_7_plus = pytest.mark.skipif(sys.version_info < (3, 7), reason="Python 3.7+")
py_have_clock_gettime = pytest.mark.skipif(
    not hasattr(time, "clock_gettime"), reason="Doesn't have clock_gettime"
)


@pytest.mark.skipif(
    not hasattr(time, "CLOCK_REALTIME"), reason="No time.CLOCK_REALTIME"
)
def test_import_without_clock_realtime():
    orig = time.CLOCK_REALTIME
    del time.CLOCK_REALTIME
    try:
        # Recipe for importing from path as documented in importlib
        spec = spec_from_file_location(
            f"{__name__}.time_machine_without_clock_realtime", time_machine.__file__
        )
        module = module_from_spec(spec)
        spec.loader.exec_module(module)

    finally:
        time.CLOCK_REALTIME = orig

    # No assertions - testing for coverage only


# datetime module


def test_datetime_now_no_args():
    with time_machine.travel(EPOCH):
        now = dt.datetime.now()
        assert now.year == 1970
        assert now.month == 1
        assert now.day == 1
        # Not asserting on hour/minute because local timezone could shift it
        assert now.second == 0
        assert now.microsecond == 0
    assert dt.datetime.now() >= LIBRARY_EPOCH_DATETIME


def test_datetime_now_no_args_no_tick():
    with time_machine.travel(EPOCH, tick=False):
        now = dt.datetime.now()
        assert now.microsecond == 0
    assert dt.datetime.now() >= LIBRARY_EPOCH_DATETIME


def test_datetime_now_arg():
    with time_machine.travel(EPOCH):
        now = dt.datetime.now(tz=dt.timezone.utc)
        assert now.year == 1970
        assert now.month == 1
        assert now.day == 1
    assert dt.datetime.now(dt.timezone.utc) >= LIBRARY_EPOCH_DATETIME.replace(
        tzinfo=dt.timezone.utc
    )


def test_datetime_utcnow():
    with time_machine.travel(EPOCH):
        now = dt.datetime.utcnow()
        assert now.year == 1970
        assert now.month == 1
        assert now.day == 1
        assert now.hour == 0
        assert now.minute == 0
        assert now.second == 0
        assert now.microsecond == 0
        assert now.tzinfo is None
    assert dt.datetime.utcnow() >= LIBRARY_EPOCH_DATETIME


def test_datetime_utcnow_no_tick():
    with time_machine.travel(EPOCH, tick=False):
        now = dt.datetime.utcnow()
        assert now.microsecond == 0


def test_date_today():
    with time_machine.travel(EPOCH):
        today = dt.date.today()
        assert today.year == 1970
        assert today.month == 1
        assert today.day == 1
    assert dt.datetime.today() >= LIBRARY_EPOCH_DATETIME


# time module


@py_have_clock_gettime
def test_time_clock_gettime_realtime():
    with time_machine.travel(EPOCH + 180.0):
        now = time.clock_gettime(time.CLOCK_REALTIME)
        assert isinstance(now, float)
        assert now == EPOCH + 180.0

    now = time.clock_gettime(time.CLOCK_REALTIME)
    assert isinstance(now, float)
    assert now >= LIBRARY_EPOCH


@py_have_clock_gettime
def test_time_clock_gettime_monotonic_unaffected():
    start = time.clock_gettime(time.CLOCK_MONOTONIC)
    with time_machine.travel(EPOCH + 180.0):
        frozen = time.clock_gettime(time.CLOCK_MONOTONIC)
        assert isinstance(frozen, float)
        assert frozen > start

    now = time.clock_gettime(time.CLOCK_MONOTONIC)
    assert isinstance(now, float)
    assert now > frozen


@py_3_7_plus
@py_have_clock_gettime
def test_time_clock_gettime_ns_realtime():
    with time_machine.travel(EPOCH + 190.0):
        first = time.clock_gettime_ns(time.CLOCK_REALTIME)
        assert isinstance(first, int)
        assert first == int((EPOCH + 190.0) * NANOSECONDS_PER_SECOND)
        second = time.clock_gettime_ns(time.CLOCK_REALTIME)
        assert first < second < int((EPOCH + 191.0) * NANOSECONDS_PER_SECOND)

    now = time.clock_gettime_ns(time.CLOCK_REALTIME)
    assert isinstance(now, int)
    assert now >= int(LIBRARY_EPOCH * NANOSECONDS_PER_SECOND)


@py_3_7_plus
@py_have_clock_gettime
def test_time_clock_gettime_ns_monotonic_unaffected():
    start = time.clock_gettime_ns(time.CLOCK_MONOTONIC)
    with time_machine.travel(EPOCH + 190.0):
        frozen = time.clock_gettime_ns(time.CLOCK_MONOTONIC)
        assert isinstance(frozen, int)
        assert frozen > start

    now = time.clock_gettime_ns(time.CLOCK_MONOTONIC)
    assert isinstance(now, int)
    assert now > frozen


def test_time_gmtime_no_args():
    with time_machine.travel(EPOCH):
        local_time = time.gmtime()
        assert local_time.tm_year == 1970
        assert local_time.tm_mon == 1
        assert local_time.tm_mday == 1
    now_time = time.gmtime()
    assert now_time.tm_year >= 2020


def test_time_gmtime_no_args_no_tick():
    with time_machine.travel(EPOCH, tick=False):
        local_time = time.gmtime()
        assert local_time.tm_sec == 0


def test_time_gmtime_arg():
    with time_machine.travel(EPOCH):
        local_time = time.gmtime(EPOCH_PLUS_ONE_YEAR)
        assert local_time.tm_year == 1971
        assert local_time.tm_mon == 1
        assert local_time.tm_mday == 1


def test_time_localtime():
    with time_machine.travel(EPOCH):
        local_time = time.localtime()
        assert local_time.tm_year == 1970
        assert local_time.tm_mon == 1
        assert local_time.tm_mday == 1
    now_time = time.localtime()
    assert now_time.tm_year >= 2020


def test_time_localtime_no_tick():
    with time_machine.travel(EPOCH, tick=False):
        local_time = time.localtime()
        assert local_time.tm_sec == 0


def test_time_localtime_arg():
    with time_machine.travel(EPOCH):
        local_time = time.localtime(EPOCH_PLUS_ONE_YEAR)
        assert local_time.tm_year == 1971
        assert local_time.tm_mon == 1
        assert local_time.tm_mday == 1


def test_time_strftime_no_args():
    with time_machine.travel(EPOCH):
        assert time.strftime("%Y-%m-%d") == "1970-01-01"
    assert int(time.strftime("%Y")) >= 2020


def test_time_strftime_no_args_no_tick():
    with time_machine.travel(EPOCH, tick=False):
        assert time.strftime("%S") == "00"


def test_time_strftime_arg():
    with time_machine.travel(EPOCH):
        assert (
            time.strftime("%Y-%m-%d", time.localtime(EPOCH_PLUS_ONE_YEAR))
            == "1971-01-01"
        )


def test_time_time():
    with time_machine.travel(EPOCH):
        first = time.time()
        assert isinstance(first, float)
        assert first == EPOCH
        second = time.time()
        assert first < second < EPOCH + 1.0

    now = time.time()
    assert isinstance(now, float)
    assert now >= LIBRARY_EPOCH


windows_epoch_in_posix = -11_644_445_222


@mock.patch.object(
    time_machine,
    "SYSTEM_EPOCH_TIMESTAMP_NS",
    (windows_epoch_in_posix * NANOSECONDS_PER_SECOND),
)
def test_time_time_windows():
    with time_machine.travel(EPOCH):
        first = time.time()
        assert isinstance(first, float)
        assert first == windows_epoch_in_posix

        second = time.time()
        assert isinstance(second, float)
        assert windows_epoch_in_posix < second < windows_epoch_in_posix + 1.0


def test_time_time_no_tick():
    with time_machine.travel(EPOCH, tick=False):
        assert time.time() == EPOCH


@py_3_7_plus
def test_time_time_ns():
    with time_machine.travel(EPOCH + 150.0):
        first = time.time_ns()
        assert isinstance(first, int)
        assert first == int((EPOCH + 150.0) * NANOSECONDS_PER_SECOND)
        second = time.time_ns()
        assert first < second < int((EPOCH + 151.0) * NANOSECONDS_PER_SECOND)

    now = time.time_ns()
    assert isinstance(now, int)
    assert now >= int(LIBRARY_EPOCH * NANOSECONDS_PER_SECOND)


@py_3_7_plus
def test_time_time_ns_no_tick():
    with time_machine.travel(EPOCH, tick=False):
        assert time.time_ns() == int(EPOCH * NANOSECONDS_PER_SECOND)


# all supported forms


def test_nestable():
    with time_machine.travel(EPOCH + 55.0):
        assert time.time() == EPOCH + 55.0
        with time_machine.travel(EPOCH + 50.0):
            assert time.time() == EPOCH + 50.0


def test_unsupported_type():
    with pytest.raises(TypeError) as excinfo:
        with time_machine.travel([]):
            pass

    assert excinfo.value.args == ("Unsupported destination []",)


def test_exceptions_dont_break_it():
    with pytest.raises(ValueError), time_machine.travel(0.0):
        raise ValueError("Hi")
    with time_machine.travel(0.0):
        pass


@time_machine.travel(EPOCH_DATETIME + dt.timedelta(seconds=70))
def test_destination_datetime():
    assert time.time() == EPOCH + 70.0


@time_machine.travel(EPOCH_DATETIME.replace(tzinfo=tz.gettz("America/Chicago")))
def test_destination_datetime_tzinfo_non_zoneinfo():
    assert time.time() == EPOCH + 21600.0


@pytest.mark.skipif(ZoneInfo is None, reason="Requires ZoneInfo")
def test_destination_datetime_tzinfo_zoneinfo():
    orig_timezone = time.timezone
    orig_altzone = time.altzone
    orig_tzname = time.tzname
    orig_daylight = time.daylight

    dest = LIBRARY_EPOCH_DATETIME.replace(tzinfo=ZoneInfo("Africa/Addis_Ababa"))
    with time_machine.travel(dest):
        assert time.timezone == -3 * 3600
        assert time.altzone == -3 * 3600
        assert time.tzname == ("EAT", "EAT")
        assert time.daylight == 0

        assert time.localtime() == time.struct_time(
            (
                2020,
                4,
                29,
                0,
                0,
                0,
                2,
                120,
                0,
            )
        )

    assert time.timezone == orig_timezone
    assert time.altzone == orig_altzone
    assert time.tzname == orig_tzname
    assert time.daylight == orig_daylight


@pytest.mark.skipif(ZoneInfo is None, reason="Requires ZoneInfo")
def test_destination_datetime_tzinfo_zoneinfo_nested():
    orig_tzname = time.tzname

    dest = LIBRARY_EPOCH_DATETIME.replace(tzinfo=ZoneInfo("Africa/Addis_Ababa"))
    with time_machine.travel(dest):
        assert time.tzname == ("EAT", "EAT")

        dest2 = LIBRARY_EPOCH_DATETIME.replace(tzinfo=ZoneInfo("Pacific/Auckland"))
        with time_machine.travel(dest2):
            assert time.tzname == ("NZST", "NZDT")

        assert time.tzname == ("EAT", "EAT")

    assert time.tzname == orig_tzname


@pytest.mark.skipif(ZoneInfo is None, reason="Requires ZoneInfo")
def test_destination_datetime_tzinfo_zoneinfo_windows():
    orig_timezone = time.timezone

    pretend_windows_no_tzset = mock.patch.object(time_machine, "tzset", new=None)

    dest = LIBRARY_EPOCH_DATETIME.replace(tzinfo=ZoneInfo("Africa/Addis_Ababa"))
    with pretend_windows_no_tzset, time_machine.travel(dest):
        assert time.timezone == orig_timezone


@time_machine.travel(EPOCH_DATETIME.replace(tzinfo=None) + dt.timedelta(seconds=120))
def test_destination_datetime_naive():
    assert time.time() == EPOCH + 120.0


@time_machine.travel(EPOCH_DATETIME.date())
def test_destination_date():
    assert time.time() == EPOCH


@time_machine.travel("1970-01-01 00:01 +0000")
def test_destination_string():
    assert time.time() == EPOCH + 60.0


@time_machine.travel(lambda: EPOCH + 140.0)
def test_destination_callable_lambda_float():
    assert time.time() == EPOCH + 140.0


@time_machine.travel(lambda: "1970-01-01 00:02 +0000")
def test_destination_callable_lambda_string():
    assert time.time() == EPOCH + 120.0


@time_machine.travel((EPOCH + 13.0 for _ in range(1)))
def test_destination_generator():
    assert time.time() == EPOCH + 13.0


def test_traveller_object():
    traveller = time_machine.travel(EPOCH + 10.0)
    assert time.time() >= LIBRARY_EPOCH
    try:
        traveller.start()
        assert time.time() == EPOCH + 10.0
    finally:
        traveller.stop()
    assert time.time() >= LIBRARY_EPOCH


@time_machine.travel(EPOCH + 15.0)
def test_function_decorator():
    assert time.time() == EPOCH + 15.0


def test_coroutine_decorator():
    recorded_time = None

    @time_machine.travel(EPOCH + 140.0)
    async def record_time():
        nonlocal recorded_time
        recorded_time = time.time()

    if sys.version_info < (3, 7):
        loop = asyncio.get_event_loop()
        loop.run_until_complete(record_time())
        loop.close()
    else:
        asyncio.run(record_time())

    assert recorded_time == EPOCH + 140.0


def test_class_decorator_fails_non_testcase():
    with pytest.raises(TypeError) as excinfo:

        @time_machine.travel(EPOCH)
        class Something:
            pass

    assert excinfo.value.args == ("Can only decorate unittest.TestCase subclasses.",)


class MethodDecoratorTests:
    @time_machine.travel(EPOCH + 95.0)
    def test_method_decorator(self):
        assert time.time() == EPOCH + 25.0


class UnitTestMethodTests(TestCase):
    @time_machine.travel(EPOCH + 25.0)
    def test_method_decorator(self):
        assert time.time() == EPOCH + 25.0


@time_machine.travel(EPOCH + 95.0)
class UnitTestClassTests(TestCase):
    def test_class_decorator(self):
        assert EPOCH + 95.0 < time.time() < EPOCH + 96.0

    @time_machine.travel(EPOCH + 25.0)
    def test_stacked_method_decorator(self):
        assert time.time() == EPOCH + 25.0


@time_machine.travel(EPOCH + 95.0)
class UnitTestClassCustomSetUpClassTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.custom_setupclass_ran = True

    def test_class_decorator(self):
        assert EPOCH + 95.0 < time.time() < EPOCH + 96.0
        assert self.custom_setupclass_ran


@time_machine.travel(EPOCH + 110.0)
class UnitTestClassSetUpClassSkipTests(TestCase):
    @classmethod
    def setUpClass(cls):
        raise SkipTest("Not today")
        # Other tests would fail if the travel() wasn't stopped

    def test_thats_always_skipped(self):
        pass


# shift() tests


def test_shift_with_timedelta():
    with time_machine.travel(EPOCH, tick=False) as traveller:
        traveller.shift(dt.timedelta(days=1))
        assert time.time() == EPOCH + (3600.0 * 24)


def test_shift_integer_delta():
    with time_machine.travel(EPOCH, tick=False) as traveller:
        traveller.shift(10)
        assert time.time() == EPOCH + 10


def test_shift_negative_delta():
    with time_machine.travel(EPOCH, tick=False) as traveller:
        traveller.shift(-10)

        assert time.time() == EPOCH - 10


def test_shift_wrong_delta():
    with time_machine.travel(EPOCH, tick=False) as traveller:
        with pytest.raises(TypeError) as excinfo:
            traveller.shift(delta="1.1")

    assert excinfo.value.args == ("Unsupported type for delta argument: '1.1'",)


def test_shift_when_tick():
    with time_machine.travel(EPOCH, tick=True) as traveller:
        traveller.shift(10.0)
        assert EPOCH + 10.0 <= time.time() < EPOCH + 20.0


# move_to() tests


def test_move_to_datetime():
    with time_machine.travel(EPOCH) as traveller:
        assert time.time() == EPOCH

        traveller.move_to(EPOCH_PLUS_ONE_YEAR_DATETIME)

        first = time.time()
        assert first == EPOCH_PLUS_ONE_YEAR

        second = time.time()
        assert first < second < first + 1.0


def test_move_to_datetime_no_tick():
    with time_machine.travel(EPOCH, tick=False) as traveller:
        traveller.move_to(EPOCH_PLUS_ONE_YEAR_DATETIME)
        assert time.time() == EPOCH_PLUS_ONE_YEAR
        assert time.time() == EPOCH_PLUS_ONE_YEAR


def test_move_to_past_datetime():
    with time_machine.travel(EPOCH_PLUS_ONE_YEAR) as traveller:
        assert time.time() == EPOCH_PLUS_ONE_YEAR
        traveller.move_to(EPOCH_DATETIME)
        assert time.time() == EPOCH


@pytest.mark.skipif(ZoneInfo is None, reason="Requires ZoneInfo")
def test_move_to_datetime_with_tzinfo_zoneinfo():
    orig_timezone = time.timezone
    orig_altzone = time.altzone
    orig_tzname = time.tzname
    orig_daylight = time.daylight

    with time_machine.travel(EPOCH) as traveller:
        assert time.time() == EPOCH
        assert time.timezone == orig_timezone
        assert time.altzone == orig_altzone
        assert time.tzname == orig_tzname
        assert time.daylight == orig_daylight

        dest = EPOCH_PLUS_ONE_YEAR_DATETIME.replace(
            tzinfo=ZoneInfo("Africa/Addis_Ababa")
        )
        traveller.move_to(dest)

        assert time.timezone == -3 * 3600
        assert time.altzone == -3 * 3600
        assert time.tzname == ("EAT", "EAT")
        assert time.daylight == 0

        assert time.localtime() == time.struct_time(
            (
                1971,
                1,
                1,
                0,
                0,
                0,
                4,
                1,
                0,
            )
        )

    assert time.timezone == orig_timezone
    assert time.altzone == orig_altzone
    assert time.tzname == orig_tzname
    assert time.daylight == orig_daylight


# uuid tests


def time_from_uuid1(value):
    return dt.datetime(1582, 10, 15) + dt.timedelta(microseconds=value.time // 10)


def test_uuid1():
    """
    Test that the uuid.uuid1() methods generate values for the destination.
    They are a known location in the stdlib that can make system calls to find
    the current datetime.
    """
    destination = dt.datetime(2017, 2, 6, 14, 8, 21)

    with time_machine.travel(destination, tick=False):
        assert time_from_uuid1(uuid.uuid1()) == destination


# pytest plugin tests


def test_fixture_unused(time_machine):
    assert time.time() >= LIBRARY_EPOCH


def test_fixture_used(time_machine):
    time_machine.move_to(EPOCH)
    assert time.time() == EPOCH


def test_fixture_used_twice(time_machine):
    time_machine.move_to(EPOCH)
    assert time.time() == EPOCH

    time_machine.move_to(EPOCH_PLUS_ONE_YEAR)
    assert time.time() == EPOCH_PLUS_ONE_YEAR
