"""Frozen clock for the rate-limit tests (T352).

planner/ratelimit.py counts in fixed windows keyed on time.time() // seconds. A test that posts
11 times can straddle a window edge, the count restarts and the 11th post is not refused. The
suite then goes red at random. rate_limits_on turns the limits on AND freezes the clock that
ratelimit.py reads, at the start of a window (FROZEN divides by one day, so it is the start of
every 60 s, 10 min and 1 h window). Production code does not change.
"""
import functools
from unittest import mock

from django.test import override_settings

FROZEN = 20000 * 86400.0  # 2024-10-04 00:00 UTC: a window start for every limit in use


class FrozenClock:
    """Stands in for the time module inside planner.ratelimit. Move it with .now = ..."""

    def __init__(self, now=FROZEN):
        self.now = now

    def time(self):
        return self.now


def frozen_clock(now=FROZEN):
    """Context manager: planner.ratelimit reads a FrozenClock. Yields the clock."""
    return mock.patch("planner.ratelimit.time", FrozenClock(now))


def rate_limits_on(test):
    """Decorator for a test method: RATE_LIMITS=True with a frozen rate-limit clock."""
    @functools.wraps(test)
    def inner(*args, **kwargs):
        with frozen_clock():
            return test(*args, **kwargs)
    return override_settings(RATE_LIMITS=True)(inner)
