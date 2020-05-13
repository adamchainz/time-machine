import asyncio
import datetime as dt
import sys
import time
import uuid
from unittest import SkipTest, TestCase

import pytest
from dateutil import tz

import time_machine

NANOSECONDS_PER_SECOND = time_machine.NANOSECONDS_PER_SECOND
EPOCH_DATETIME = dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)
EPOCH = EPOCH_DATETIME.timestamp()
EPOCH_PLUS_ONE_YEAR_DATETIME = dt.datetime(1971, 1, 1, tzinfo=dt.timezone.utc)
EPOCH_PLUS_ONE_YEAR = EPOCH_PLUS_ONE_YEAR_DATETIME.timestamp()
LIBRARY_EPOCH_DATETIME = dt.datetime(2020, 4, 29)  # The day this library was made
LIBRARY_EPOCH = LIBRARY_EPOCH_DATETIME.timestamp()

py_3_7_plus = pytest.mark.skipif(sys.version_info < (3, 7), reason="Python 3.7+")


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


def test_datetime_now_arg():
    with time_machine.travel(EPOCH):
        now = dt.datetime.now(tz=dt.timezone.utc)
        assert now.year == 1970
        assert now.month == 1
        assert now.day == 1
    assert dt.datetime.now(dt.timezone.utc) >= LIBRARY_EPOCH_DATETIME


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


def test_time_clock_gettime_realtime():
    with time_machine.travel(EPOCH + 180.0):
        assert time.clock_gettime(time.CLOCK_REALTIME) == EPOCH + 180.0
    assert time.clock_gettime(time.CLOCK_REALTIME) >= LIBRARY_EPOCH


def test_time_clock_gettime_monotonic_unaffected():
    start = time.clock_gettime(time.CLOCK_MONOTONIC)
    with time_machine.travel(EPOCH + 180.0):
        frozen = time.clock_gettime(time.CLOCK_MONOTONIC)
        assert frozen > start
    assert time.clock_gettime(time.CLOCK_MONOTONIC) > frozen


@py_3_7_plus
def test_time_clock_gettime_ns_realtime():
    with time_machine.travel(EPOCH + 190.0):
        first = time.clock_gettime_ns(time.CLOCK_REALTIME)
        assert first == int((EPOCH + 190.0) * NANOSECONDS_PER_SECOND)
        second = time.clock_gettime_ns(time.CLOCK_REALTIME)
        assert first < second < int((EPOCH + 191.0) * NANOSECONDS_PER_SECOND)
    assert time.clock_gettime_ns(time.CLOCK_REALTIME) >= int(
        LIBRARY_EPOCH * NANOSECONDS_PER_SECOND
    )


@py_3_7_plus
def test_time_clock_gettime_ns_monotonic_unaffected():
    start = time.clock_gettime_ns(time.CLOCK_MONOTONIC)
    with time_machine.travel(EPOCH + 190.0):
        frozen = time.clock_gettime_ns(time.CLOCK_MONOTONIC)
        assert frozen > start
    assert time.clock_gettime_ns(time.CLOCK_MONOTONIC) > frozen


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
        assert first == EPOCH
        second = time.time()
        assert first < second < EPOCH + 1.0
    assert time.time() >= LIBRARY_EPOCH


def test_time_time_no_tick():
    with time_machine.travel(EPOCH, tick=False):
        assert time.time() == EPOCH


@py_3_7_plus
def test_time_time_ns():
    with time_machine.travel(EPOCH + 150.0):
        first = time.time_ns()
        assert first == int((EPOCH + 150.0) * NANOSECONDS_PER_SECOND)
        second = time.time_ns()
        assert first < second < int((EPOCH + 151.0) * NANOSECONDS_PER_SECOND)
    assert time.time_ns() >= int(LIBRARY_EPOCH * NANOSECONDS_PER_SECOND)


@py_3_7_plus
def test_time_time_ns_no_tick():
    with time_machine.travel(EPOCH, tick=False):
        assert time.time_ns() == int(EPOCH * NANOSECONDS_PER_SECOND)


# other usage


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
def test_destination_datetime_timezone():
    assert time.time() == EPOCH + 21600.0


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
