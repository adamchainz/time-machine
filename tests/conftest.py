from __future__ import annotations

import os
import time

# Isolate tests from the host machine’s timezone
if hasattr(time, "tzset"):
    os.environ["TZ"] = "UTC"
    time.tzset()
