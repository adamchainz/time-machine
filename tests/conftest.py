from __future__ import annotations

import os
import time

# Isolate tests from the host machine’s timezone
os.environ["TZ"] = "UTC"
time.tzset()


def _have_64_bit_time_t() -> bool:
    # Probe with a post-2038 timestamp: platforms with 32-bit time_t raise
    # OverflowError (or OSError) when converting it.
    try:
        time.gmtime(2**31)
    except (OverflowError, OSError):  # pragma: no cover
        return False
    return True


HAVE_64_BIT_TIME_T = _have_64_bit_time_t()
