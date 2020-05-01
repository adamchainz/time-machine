import datetime as dt
import time

import pytest

import tachyon_gun

EPOCH = 0.0
EPOCH_PLUS_ONE_YEAR = 31_536_000.0
LIBRARY_EPOCH = dt.datetime(2020, 4, 29)  # The day this library was made


def test_time_time():
    with tachyon_gun.warp_time(EPOCH):
        assert EPOCH < time.time() < EPOCH + 1.0
    assert time.time() >= LIBRARY_EPOCH.timestamp()


def test_time_localtime():
    with tachyon_gun.warp_time(EPOCH):
        local_time = time.localtime()
        assert local_time.tm_year == 1970
        assert local_time.tm_mon == 1
        assert local_time.tm_mday == 1
    now_time = time.localtime()
    assert now_time.tm_year >= 2020


def test_time_localtime_arg():
    with tachyon_gun.warp_time(EPOCH):
        local_time = time.localtime(EPOCH_PLUS_ONE_YEAR)
        assert local_time.tm_year == 1971
        assert local_time.tm_mon == 1
        assert local_time.tm_mday == 1


def test_time_gmtime_no_args():
    with tachyon_gun.warp_time(EPOCH):
        local_time = time.gmtime()
        assert local_time.tm_year == 1970
        assert local_time.tm_mon == 1
        assert local_time.tm_mday == 1
    now_time = time.gmtime()
    assert now_time.tm_year >= 2020


def test_time_gmtime_arg():
    with tachyon_gun.warp_time(EPOCH):
        local_time = time.gmtime(EPOCH_PLUS_ONE_YEAR)
        assert local_time.tm_year == 1971
        assert local_time.tm_mon == 1
        assert local_time.tm_mday == 1


def test_time_strftime_no_args():
    with tachyon_gun.warp_time(EPOCH):
        assert time.strftime("%Y-%m-%d") == "1970-01-01"
    assert int(time.strftime("%Y")) >= 2020


def test_time_strftime_arg():
    with tachyon_gun.warp_time(EPOCH):
        assert (
            time.strftime("%Y-%m-%d", time.localtime(EPOCH_PLUS_ONE_YEAR))
            == "1971-01-01"
        )


def test_not_nestable():
    with tachyon_gun.warp_time(0.0):
        with pytest.raises(RuntimeError) as excinfo:
            with tachyon_gun.warp_time(1.0):
                pass

    assert excinfo.value.args == ("Cannot warp during a warp.",)


def test_exceptions_dont_break_it():
    with pytest.raises(ValueError), tachyon_gun.warp_time(0.0):
        raise ValueError("Hi")
    with tachyon_gun.warp_time(0.0):
        pass


def test_datetime_now_no_args():
    with tachyon_gun.warp_time(EPOCH):
        now = dt.datetime.now()
        assert now.year == 1970
        assert now.month == 1
        assert now.day == 1
    assert dt.datetime.now() >= LIBRARY_EPOCH


def test_datetime_now_arg():
    with tachyon_gun.warp_time(EPOCH):
        now = dt.datetime.now(tz=dt.timezone.utc)
        assert now.year == 1970
        assert now.month == 1
        assert now.day == 1
    assert dt.datetime.now(dt.timezone.utc) >= LIBRARY_EPOCH


def test_datetime_utcnow():
    with tachyon_gun.warp_time(EPOCH):
        now = dt.datetime.utcnow()
        assert now.year == 1970
        assert now.month == 1
        assert now.day == 1
    assert dt.datetime.utcnow() >= LIBRARY_EPOCH


def test_date_today():
    with tachyon_gun.warp_time(EPOCH):
        today = dt.date.today()
        assert today.year == 1970
        assert today.month == 1
        assert today.day == 1
    assert dt.datetime.today() >= LIBRARY_EPOCH
