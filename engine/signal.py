"""15m pullback-to-EMA20/50 + rejection candle, in bias direction. Closed bars only."""
from datetime import datetime, timedelta, timezone

import numpy as np

from . import indicators as ind


def _bull_engulf(o, c, i):
    return c[i - 1] < o[i - 1] and c[i] > o[i] and c[i] >= o[i - 1] and o[i] <= c[i - 1]


def _bear_engulf(o, c, i):
    return c[i - 1] > o[i - 1] and c[i] < o[i] and c[i] <= o[i - 1] and o[i] >= c[i - 1]


def _pin(o, h, l, c, i, side):
    rng = h[i] - l[i]
    if rng <= 0:
        return False
    body = abs(c[i] - o[i])
    if side == "long":
        wick = min(o[i], c[i]) - l[i]
        return wick >= 0.6 * rng and wick >= 2 * body and c[i] > o[i]
    wick = h[i] - max(o[i], c[i])
    return wick >= 0.6 * rng and wick >= 2 * body and c[i] < o[i]


def find_signal(o, h, l, c, bias, cfg):
    """Return (signal|None, reason). o,h,l,c are closed M15 bars; entry reference = last close."""
    if bias not in ("long", "short"):
        return None, "bias_flat"
    o, h, l, c = (np.asarray(v, float) for v in (o, h, l, c))
    if len(c) < 60:
        return None, "not_enough_bars"
    e20, e50 = ind.ema(c, 20), ind.ema(c, 50)
    a = ind.atr(h, l, c, 14)
    i = len(c) - 1
    zone_hi, zone_lo = max(e20[i], e50[i]), min(e20[i], e50[i])
    entry = c[i]
    if bias == "long":
        touched = l[-3:].min() <= zone_hi
        held = c[i] > e50[i]
        pattern = "engulfing" if _bull_engulf(o, c, i) else "pin" if _pin(o, h, l, c, i, "long") else None
        sl = min(l[-3:].min() - 0.1 * a, entry - cfg["sl_atr_mult"] * a)
    else:
        touched = h[-3:].max() >= zone_lo
        held = c[i] < e50[i]
        pattern = "engulfing" if _bear_engulf(o, c, i) else "pin" if _pin(o, h, l, c, i, "short") else None
        sl = max(h[-3:].max() + 0.1 * a, entry + cfg["sl_atr_mult"] * a)
    if not touched:
        return None, "no_pullback_to_zone"
    if not held:
        return None, "closed_through_ema50"
    if pattern is None:
        return None, "no_rejection_candle"
    sl_dist = abs(entry - sl)
    if sl_dist > cfg["max_sl_atr"] * a:
        return None, "sl_too_wide"
    tp = entry + cfg["tp_r"] * sl_dist if bias == "long" else entry - cfg["tp_r"] * sl_dist
    return {"side": "buy" if bias == "long" else "sell", "pattern": pattern, "entry_ref": float(entry),
            "sl": float(sl), "tp": float(tp), "atr": float(a), "sl_dist": float(sl_dist)}, "ok"


def _nth_sunday(year, month, n):
    d = datetime(year, month, 1, tzinfo=timezone.utc)
    first = (6 - d.weekday()) % 7  # days to the first Sunday
    return d + timedelta(days=first + 7 * (n - 1))


def us_open_ts(ts):
    """Epoch of 09:30 New York on the UTC day of `ts` (US DST: 2nd Sunday of March to 1st Sunday of November)."""
    y = datetime.fromtimestamp(ts, timezone.utc).year
    start = _nth_sunday(y, 3, 2).replace(hour=7).timestamp()  # 02:00 EST
    end = _nth_sunday(y, 11, 1).replace(hour=6).timestamp()  # 02:00 EDT
    off_h = 4 if start <= ts < end else 5
    return ts // 86400 * 86400 + (9 * 60 + 30 + off_h * 60) * 60


def find_orb(t, o, h, l, c, bias, cfg):
    """Opening-range breakout. Range = first `orb_bars` bars from the US cash open; fires on the bar whose close is
    the FIRST close beyond it (within `orb_window_min` of the open). Stop = opposite side of the range, at least
    1 ATR away; target is set by place_trade_checked (tp_r)."""
    t, o, h, l, c = (np.asarray(v, float) for v in (t, o, h, l, c))
    n = int(cfg["orb_bars"])
    if len(c) < 30:
        return None, "not_enough_bars"
    open_ts = us_open_ts(t[-1])
    ks = np.where(t >= open_ts)[0]
    i = len(c) - 1
    if len(ks) < n + 1 or t[i] >= open_ts + cfg["orb_window_min"] * 60:
        return None, "orb_outside_window"
    rng = ks[:n]
    hi, lo = h[rng].max(), l[rng].min()
    brk = [j for j in ks[n:] if c[j] > hi or c[j] < lo]
    if not brk or brk[0] != i:
        return None, "orb_no_fresh_break"
    long_ = c[i] > hi
    if cfg["orb_require_bias"] and bias != ("long" if long_ else "short"):
        return None, "orb_against_bias"
    a = ind.atr(h, l, c, 14)
    entry = c[i]
    dist = max(abs(entry - (lo if long_ else hi)), a)
    if dist > cfg["max_sl_atr"] * a:
        return None, "sl_too_wide"
    sl = entry - dist if long_ else entry + dist
    tp = entry + cfg["tp_r"] * dist if long_ else entry - cfg["tp_r"] * dist
    return {"side": "buy" if long_ else "sell", "pattern": "orb", "entry_ref": float(entry), "sl": float(sl),
            "tp": float(tp), "atr": float(a), "sl_dist": float(dist)}, "ok"


def find_any(bars, bias, cfg):
    """First signal from cfg['strategies'] (in order) on closed bars (structured array with time/open/high/low/close)."""
    why = "no_strategy"
    for name in cfg.get("strategies", ["pullback"]):
        if name == "pullback":
            sig, why_ = find_signal(bars["open"], bars["high"], bars["low"], bars["close"], bias, cfg)
        elif name == "orb":
            sig, why_ = find_orb(bars["time"], bars["open"], bars["high"], bars["low"], bars["close"], bias, cfg)
        else:
            continue
        if sig:
            return sig, why_
        why = why_ if why in ("no_strategy", "bias_flat") else why
    return None, why
