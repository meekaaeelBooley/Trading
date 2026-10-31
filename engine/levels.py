"""Support / resistance: fractal pivots clustered into zones, multi-timeframe merge, key and round levels.

Pure numpy over closed bars. A zone is a price band where several pivots reacted; more touches, a recent touch and a
higher timeframe make it stronger. Retest helpers say whether price is rejecting a zone or retesting a broken one.
"""
import math

import numpy as np

TF_WEIGHT = {"d1": 3.0, "h4": 2.0, "h1": 1.5, "m15": 1.0, "m5": 0.7}


def swing_points(high, low, k=3):
    """Fractal pivots: ([(idx, price)] highs, [(idx, price)] lows). A pivot is confirmed k bars after it forms."""
    h, l = np.asarray(high, float), np.asarray(low, float)
    hs, ls = [], []
    for i in range(k, len(h) - k):
        if h[i] > h[i - k:i].max() and h[i] >= h[i + 1:i + k + 1].max():
            hs.append((i, float(h[i])))
        if l[i] < l[i - k:i].min() and l[i] <= l[i + 1:i + k + 1].min():
            ls.append((i, float(l[i])))
    return hs, ls


def zones(high, low, atr, k=3, tol_atr=0.6, min_touches=2, min_width_atr=0.15):
    """Cluster every pivot (highs and lows alike: price flips roles) into zones whose span is <= tol_atr x ATR.
    Returns [{lo, hi, mid, touches, last, score}] with last = bar index of the latest touch."""
    hs, ls = swing_points(high, low, k)
    n = len(high)
    if atr <= 0 or n == 0:
        return []
    tol, out = tol_atr * atr, []
    for i, p in sorted(hs + ls, key=lambda x: x[1]):
        if out and p - out[-1]["lo"] <= tol:
            z = out[-1]
            z["hi"], z["touches"], z["last"] = p, z["touches"] + 1, max(z["last"], i)
        else:
            out.append({"lo": p, "hi": p, "touches": 1, "last": i})
    res = []
    for z in out:
        if z["touches"] < min_touches:
            continue
        pad = max(0.0, min_width_atr * atr - (z["hi"] - z["lo"])) / 2
        lo, hi = z["lo"] - pad, z["hi"] + pad
        res.append({"lo": lo, "hi": hi, "mid": (lo + hi) / 2, "touches": z["touches"], "last": z["last"],
                    "score": z["touches"] + z["last"] / n})
    return res


def build(frames, price, atr_ref, max_dist_atr=10.0):
    """Merge zones from several timeframes into one list. frames = [(name, high, low, atr)].
    Returns zones sorted by distance from price: {lo, hi, mid, kind support|resistance|inside, dist_atr, touches, tfs, score}."""
    raw = []
    for name, high, low, atr in frames:
        for z in zones(high, low, atr):
            raw.append({**z, "tfs": {name}, "score": z["score"] * TF_WEIGHT.get(name, 1.0)})
    raw.sort(key=lambda z: z["mid"])
    merged = []
    for z in raw:
        m = merged[-1] if merged else None
        if m and z["lo"] <= m["hi"] + 0.25 * atr_ref and max(z["hi"], m["hi"]) - min(z["lo"], m["lo"]) <= 2 * atr_ref:
            m["lo"], m["hi"] = min(m["lo"], z["lo"]), max(m["hi"], z["hi"])
            m["touches"] += z["touches"]
            m["score"] += z["score"]
            m["tfs"] |= z["tfs"]
        else:
            merged.append({**z, "tfs": set(z["tfs"])})
    out = []
    for z in merged:
        z["mid"] = (z["lo"] + z["hi"]) / 2
        if z["lo"] - 0.1 * atr_ref <= price <= z["hi"] + 0.1 * atr_ref:
            z["kind"], z["dist_atr"] = "inside", 0.0
        elif z["hi"] < price:
            z["kind"], z["dist_atr"] = "support", (price - z["hi"]) / atr_ref
        else:
            z["kind"], z["dist_atr"] = "resistance", (z["lo"] - price) / atr_ref
        if z["dist_atr"] <= max_dist_atr:
            out.append(z)
    return sorted(out, key=lambda z: z["dist_atr"])


def nearest(zs, kind, n=3):
    """The n zones of a kind (support|resistance) nearest to price; 'inside' zones count for both."""
    return [z for z in zs if z["kind"] in (kind, "inside")][:n]


def round_levels(price, n=2):
    """Psychological levels around price. Step is price-scale aware: 4000 -> 50 (gold xx50/xx00), 25000 -> 500."""
    if price <= 0:
        return {"above": [], "below": []}
    step = 10 ** math.floor(math.log10(price)) / 20
    base = math.floor(price / step) * step
    return {"above": [round(base + step * (i + 1), 2) for i in range(n)],
            "below": [round(base - step * i, 2) for i in range(n) if base - step * i < price]}


def key_levels(d1, now_ts):
    """Previous day and previous week high/low/close from closed D1 bars (structured array with time/high/low/close)."""
    if d1 is None or len(d1) < 8:
        return {}
    out = {"prev_day": {"high": float(d1["high"][-1]), "low": float(d1["low"][-1]), "close": float(d1["close"][-1])}}
    wk = (np.asarray(d1["time"], dtype=np.int64) // 86400 + 3) // 7  # Monday-based week number
    prev = wk == (int(now_ts) // 86400 + 3) // 7 - 1
    if prev.any():
        out["prev_week"] = {"high": float(np.max(d1["high"][prev])), "low": float(np.min(d1["low"][prev]))}
    return out


def rejection(high, low, close, zone, side, lookback=3, buffer=0.0):
    """True when one of the last `lookback` bars wicked into the zone and closed back on the right side of it:
    side 'buy' = support held (low pierced into the zone, close above its upper edge), 'sell' = resistance held."""
    h, l, c = (np.asarray(v, float)[-lookback:] for v in (high, low, close))
    if side == "buy":
        return bool(np.any((l <= zone["hi"] + buffer) & (c > zone["hi"])))
    return bool(np.any((h >= zone["lo"] - buffer) & (c < zone["lo"])))


def broken_retest(close, zone, side, lookback=40):
    """Role flip: for 'buy' the zone was resistance (closes below it), got broken by a close above, and price is now
    back at it from above without losing it; for 'sell' the mirror image."""
    c = np.asarray(close, float)[-lookback:]
    if len(c) < 8:
        return False
    if side == "buy":
        below, above = np.where(c[:-1] < zone["lo"])[0], np.where(c[:-1] > zone["hi"])[0]
        return bool(below.size and above.size and above.max() > below.min() and c[-1] >= zone["lo"])
    above, below = np.where(c[:-1] > zone["hi"])[0], np.where(c[:-1] < zone["lo"])[0]
    return bool(above.size and below.size and below.max() > above.min() and c[-1] <= zone["hi"])
