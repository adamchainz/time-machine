from contextlib import contextmanager
from dataclasses import dataclass

import _tachyongun


@dataclass
class Warp:
    destination: float
    start_time: float

    def seconds_since_warp(self):
        return _tachyongun.original_time() - self.start_time


current_warp = None


@contextmanager
def warp_time(destination):
    global current_warp
    if current_warp is not None:
        raise RuntimeError("Cannot warp during a warp.")

    _tachyongun.patch()
    current_warp = Warp(
        destination=destination,
        start_time=_tachyongun.original_time(),
    )
    yield
    current_warp = None


def time():
    if current_warp is None:
        return _tachyongun.original_time()
    else:
        return (
            current_warp.destination +
            (_tachyongun.original_time() - current_warp.start_time)
        )


def localtime(secs=None):
    if current_warp is None:
        return _tachyongun.original_localtime(secs)
    else:
        return _tachyongun.original_localtime(
            current_warp.destination +
            (_tachyongun.original_time() - current_warp.start_time)
        )
