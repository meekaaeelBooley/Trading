"""Session clocks without tzdata: New York and London local time from UTC epoch seconds (vectorised, numpy only).

US DST: 02:00 local on the 2nd Sunday of March -> 1st Sunday of November.  UK DST: 01:00 UTC on the last Sunday of
March -> last Sunday of October.  Broker timestamps in this project are UTC (verified: USTECm range peaks at 13:30 UTC
in summer = 09:30 EDT).
"""
from datetime import datetime, timedelta, timezone

import numpy as np

_YEARS = range(2012, 2036)


def _sunday(year, month, n):
    """n-th Sunday of the month (n=-1: last)."""
    if n > 0:
        d = datetime(year, month, 1, tzinfo=timezone.utc)
        return d + timedelta(days=(6 - d.weekday()) % 7 + 7 * (n - 1))
    d = datetime(year + (month == 12), month % 12 + 1, 1, tzinfo=timezone.utc) - timedelta(days=1)
    return d - timedelta(days=(d.weekday() + 1) % 7)


def _edges(start, end):
    return np.array([(start(y).timestamp(), end(y).timestamp()) for y in _YEARS])


_US = _edges(lambda y: _sunday(y, 3, 2).replace(hour=7), lambda y: _sunday(y, 11, 1).replace(hour=6))
_UK = _edges(lambda y: _sunday(y, 3, -1).replace(hour=1), lambda y: _sunday(y, 10, -1).replace(hour=1))


def _in_dst(ts, edges):
    ts = np.asarray(ts, float)
    out = np.zeros(ts.shape, bool)
    for a, b in edges:
        out |= (ts >= a) & (ts < b)
    return out


def ny_offset_h(ts):
    """Hours to add to UTC for New York local time (-4 EDT / -5 EST)."""
    return np.where(_in_dst(ts, _US), -4, -5)


def lon_offset_h(ts):
    """Hours to add to UTC for London local time (+1 BST / 0 GMT)."""
    return np.where(_in_dst(ts, _UK), 1, 0)


def local_minute(ts, region="ny"):
    """Minute of the local day (0..1439) for each UTC epoch."""
    ts = np.asarray(ts, float)
    off = ny_offset_h(ts) if region == "ny" else lon_offset_h(ts)
    return (((ts + off * 3600) % 86400) // 60).astype(int)


def local_day(ts, region="ny"):
    """Integer local calendar-day id (days since epoch in local time)."""
    ts = np.asarray(ts, float)
    off = ny_offset_h(ts) if region == "ny" else lon_offset_h(ts)
    return ((ts + off * 3600) // 86400).astype(int)


def weekday(ts, region="ny"):
    """0=Monday .. 6=Sunday in local time."""
    return (local_day(ts, region) + 3) % 7  # 1970-01-01 was a Thursday
