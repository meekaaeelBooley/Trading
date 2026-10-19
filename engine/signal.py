"""15m pullback-to-EMA20/50 + rejection candle, in bias direction. Closed bars only."""
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
