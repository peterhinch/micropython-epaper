# schedsupport.py
# Peter Hinch
# 30th July 205
# Support for use in cooperative multi threading environments.
# Replace these two variables with functions that yield execution

import pyb
yield_to_scheduler = lambda : None  # 17uS. Yield of arbitrarily short duration
delay_ms = pyb.delay                # Takes a single millisecond argument: must yield for at least that long
