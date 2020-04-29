import datetime as dt
import time

import pytest

import tachyon_gun


def test_time_time():
    with tachyon_gun.warp_time(0.0):
        assert 0.0 < time.time() < 1.0
    assert time.time() >= dt.datetime(2020, 4, 29).timestamp()


def test_time_localtime():
    with tachyon_gun.warp_time(0.0):
        local_time = time.localtime()
        assert local_time.tm_year == 1970
        assert local_time.tm_mon == 1
        assert local_time.tm_mday == 1
    now_time = time.localtime()
    assert now_time.tm_year >= 2020


def test_time_gmtime():
    with tachyon_gun.warp_time(0.0):
        local_time = time.gmtime()
        assert local_time.tm_year == 1970
        assert local_time.tm_mon == 1
        assert local_time.tm_mday == 1
    now_time = time.gmtime()
    assert now_time.tm_year >= 2020


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
