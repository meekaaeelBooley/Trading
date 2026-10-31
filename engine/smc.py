"""Smart money concepts on closed bars (pure numpy): market structure (BOS / CHoCH), order blocks, fair value gaps,
liquidity pools and sweeps, premium / discount. Everything is derived mechanically so an agent reads a few numbers
instead of candles. Directions are 'bull' / 'bear'.
"""
import numpy as np

from . import indicators as ind, levels


def structure(o, h, l, c, k=3):
    """Walk the bars: a close beyond the latest confirmed swing is a break. With the trend it is a BOS, against it a
    CHoCH (change of character) that flips the trend. Returns (trend|None, events, last_high, last_low)."""
    hs, ls = levels.swing_points(h, l, k)
    trend, events, hp, lp, last_hi, last_lo = None, [], 0, 0, None, None
    for i in range(len(c)):
        while hp < len(hs) and hs[hp][0] + k <= i:
            last_hi, hp = [hs[hp][0], hs[hp][1], False], hp + 1
        while lp < len(ls) and ls[lp][0] + k <= i:
            last_lo, lp = [ls[lp][0], ls[lp][1], False], lp + 1
        if last_hi and not last_hi[2] and c[i] > last_hi[1]:
            events.append({"i": i, "kind": "CHoCH" if trend == "bear" else "BOS", "dir": "bull",
                           "level": last_hi[1], "swing_i": last_hi[0]})
            last_hi[2], trend = True, "bull"
        elif last_lo and not last_lo[2] and c[i] < last_lo[1]:
            events.append({"i": i, "kind": "CHoCH" if trend == "bull" else "BOS", "dir": "bear",
                           "level": last_lo[1], "swing_i": last_lo[0]})
            last_lo[2], trend = True, "bear"
    return trend, events, last_hi, last_lo


def order_blocks(o, h, l, c, atr, events, disp_atr=0.9):
    """Order block = the last opposite candle before the displacement that broke structure. Dropped once price closes
    through it; `tested` once price has traded back into it (a fresh, untested block is the better entry)."""
    n, out = len(c), []
    for e in events:
        b, j = e["i"], e["swing_i"]
        if b - j < 2:
            continue
        bull = e["dir"] == "bull"
        seg = slice(j, b + 1)
        origin = j + int(np.argmin(l[seg]) if bull else np.argmax(h[seg]))
        d = next((x for x in range(origin + 1, b + 1)
                  if (c[x] > o[x] if bull else c[x] < o[x]) and h[x] - l[x] >= disp_atr * atr), None)
        if d is None:
            continue
        cand = [x for x in range(origin, d) if (c[x] < o[x] if bull else c[x] > o[x])]
        if not cand:
            continue
        x = cand[-1]
        lo, hi = float(l[x]), float(h[x])
        after = slice(b + 1, n)
        if (c[after] < lo).any() if bull else (c[after] > hi).any():
            continue  # invalidated
        tested = bool((l[after] <= hi).any() if bull else (h[after] >= lo).any())
        out.append({"dir": e["dir"], "lo": lo, "hi": hi, "i": x, "formed": b, "tested": tested, "kind": e["kind"]})
    return out


def fvgs(o, h, l, c, atr, min_atr=0.15):
    """Fair value gaps (three-candle imbalance) not yet fully filled; `fill` = share of the gap already traded back."""
    n, out = len(c), []
    for i in range(2, n):
        if l[i] > h[i - 2] and l[i] - h[i - 2] >= min_atr * atr:
            lo, hi, d = float(h[i - 2]), float(l[i]), "bull"
            low_after = float(l[i + 1:].min()) if i + 1 < n else hi
            fill = min(max((hi - low_after) / (hi - lo), 0.0), 1.0)
            if i + 1 < n and (c[i + 1:] < lo).any():
                fill = 1.0
        elif h[i] < l[i - 2] and l[i - 2] - h[i] >= min_atr * atr:
            lo, hi, d = float(h[i]), float(l[i - 2]), "bear"
            high_after = float(h[i + 1:].max()) if i + 1 < n else lo
            fill = min(max((high_after - lo) / (hi - lo), 0.0), 1.0)
            if i + 1 < n and (c[i + 1:] > hi).any():
                fill = 1.0
        else:
            continue
        if fill < 0.99:
            out.append({"dir": d, "lo": lo, "hi": hi, "i": i, "fill": round(fill, 2)})
    return out


def liquidity(h, l, c, hs, ls, atr, k=3, eq_atr=0.2, recent=8):
    """Resting liquidity: swing highs / lows nothing has traded beyond yet (BSL above, SSL below; equal levels flagged),
    and the most recent sweep (wick through a pivot, close back inside) within `recent` bars."""
    n = len(c)
    bsl, ssl, sweep = [], [], None
    for pivots, is_high in ((hs, True), (ls, False)):
        for i, p in pivots[-30:]:
            beyond = np.where((h[i + 1:] > p) if is_high else (l[i + 1:] < p))[0]
            if beyond.size == 0:
                (bsl if is_high else ssl).append((i, p))
                continue
            x = i + 1 + int(beyond[0])
            if n - 1 - x < recent and (c[x] <= p if is_high else c[x] >= p):
                s = {"side": "bsl" if is_high else "ssl", "level": p, "bars_ago": n - 1 - x, "i": x,
                     "extreme": float(h[x] if is_high else l[x])}
                if sweep is None or x > sweep["i"]:
                    sweep = s
    def pools(items):
        prices = sorted(p for _, p in items)
        eq = set()
        for lo_p, hi_p in zip(prices, prices[1:]):
            if hi_p - lo_p <= eq_atr * atr:  # equal highs / lows: the obvious stop cluster
                eq.update((lo_p, hi_p))
        return [{"level": p, "eq": p in eq} for p in prices]
    return {"bsl": pools(bsl), "ssl": pools(ssl), "sweep": sweep}


def dealing_range(hs, ls, price):
    """The most recent swing high / low pair that still brackets price: equilibrium 50%, premium above, discount below,
    and the OTE retracement band (62-79%) for the leg that just printed. None when price is outside every recent range
    (a breakout has no premium / discount reading)."""
    best = None
    for hi_i, hi in hs[-8:]:
        for lo_i, lo in ls[-8:]:
            if hi > lo and lo <= price <= hi:
                key = (min(hi_i, lo_i), max(hi_i, lo_i))
                if best is None or key > best[0]:
                    best = (key, hi_i, hi, lo_i, lo)
    if best is None:
        return None
    _, hi_i, hi, lo_i, lo = best
    r = hi - lo
    up = hi_i > lo_i  # last leg went up -> buyers want the pullback (discount)
    ote = (hi - 0.79 * r, hi - 0.62 * r) if up else (lo + 0.62 * r, lo + 0.79 * r)
    return {"lo": lo, "hi": hi, "eq": lo + r / 2, "leg": "up" if up else "down", "ote": ote}


def analyze(bars, k=3, atr=None):
    """Full SMC read of closed bars (structured array or dict with open/high/low/close)."""
    o, h, l, c = (np.asarray(bars[x], float) for x in ("open", "high", "low", "close"))
    n = len(c)
    atr = atr or ind.atr(h, l, c, 14)
    if n < 30 or not atr or atr != atr:
        return {"ok": False}
    trend, events, _, _ = structure(o, h, l, c, k)
    hs, ls = levels.swing_points(h, l, k)
    return {"ok": True, "n": n, "atr": float(atr), "trend": trend, "events": events[-4:],
            "obs": order_blocks(o, h, l, c, atr, events[-8:]), "fvgs": [g for g in fvgs(o, h, l, c, atr) if g["i"] >= n - 80],
            "liq": liquidity(h, l, c, hs, ls, atr, k), "range": dealing_range(hs, ls, float(c[-1])),
            "swing_high": hs[-1] if hs else None, "swing_low": ls[-1] if ls else None}


def compact(a, price, digits=2, n=2):
    """Token-light view of analyze() for a brief: nearest unmitigated blocks/gaps, pools, last events, location."""
    if not a.get("ok"):
        return None
    r = lambda x: round(float(x), digits)
    pool = lambda x: f"{r(x['level'])} EQ" if x["eq"] else r(x["level"])  # EQ = equal highs/lows
    near = lambda items: sorted(items, key=lambda z: abs((z["lo"] + z["hi"]) / 2 - price))[:n]
    out = {"trend": a["trend"], "events": [f"{e['kind']} {e['dir']} {a['n'] - 1 - e['i']}b ago @{r(e['level'])}" for e in a["events"][-2:]],
           "ob": [[z["dir"], r(z["lo"]), r(z["hi"]), "tested" if z["tested"] else "fresh"] for z in near(a["obs"])],
           "fvg": [[z["dir"], r(z["lo"]), r(z["hi"]), z["fill"]] for z in near(a["fvgs"])],
           "bsl": [pool(x) for x in [p for p in a["liq"]["bsl"] if p["level"] > price][:n]],
           "ssl": [pool(x) for x in [p for p in reversed(a["liq"]["ssl"]) if p["level"] < price][:n]]}
    sw = a["liq"]["sweep"]
    if sw:
        out["sweep"] = f"{sw['side']} {sw['bars_ago']}b ago @{r(sw['level'])}"
    d = a["range"]
    if d:
        out["pd"] = {"loc": round((price - d["lo"]) / (d["hi"] - d["lo"]), 2), "eq": r(d["eq"]), "leg": d["leg"]}
    return out
