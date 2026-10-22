r"""Cost-aware intraday strategy research on M5 history (gold + stock CFDs). Offline, read-only.

  .venv\Scripts\python.exe tools\research.py [--symbols XAUUSDm AAPLm ...] [--slip 0.5]

For every strategy x parameter combo the config is chosen on the TRAIN days (first 60%) and judged on the
held-out TEST days (last 40%). Costs: full bar spread per round trip + slip x spread. R = pnl / initial risk.
Timestamps are UTC (US regular session 13:30-20:00 UTC while EDT). SL is checked before TP inside a bar.
"""
import argparse
import itertools
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
STOCK_OPEN, STOCK_CLOSE = 13 * 60 + 30, 20 * 60  # minutes UTC


def load(sym):
    z = np.load(ROOT / "data" / f"{sym}_m5.npz")
    d = {k: z[k] for k in ("time", "open", "high", "low", "close", "tick_volume", "spread")}
    d["point"] = float(z["point"])
    d["sym"] = sym
    d["gold"] = sym.startswith("XAU")
    return d


def atr_series(h, l, c, n=14):
    tr = np.maximum(h[1:] - l[1:], np.maximum(abs(h[1:] - c[:-1]), abs(l[1:] - c[:-1])))
    tr = np.concatenate([[h[0] - l[0]], tr])
    out = np.empty_like(tr)
    out[:] = np.nan
    if len(tr) < n:
        return out
    a = tr[:n].mean()
    out[n - 1] = a
    for i in range(n, len(tr)):
        a = (a * (n - 1) + tr[i]) / n
        out[i] = a
    return out


def days(d):
    """Yield (day_ordinal, slice of bar indices in session) for each trading day."""
    t = d["time"]
    mins = (t % 86400) // 60
    day = t // 86400
    for u in np.unique(day):
        idx = np.where(day == u)[0]
        if not d["gold"]:
            idx = idx[(mins[idx] >= STOCK_OPEN) & (mins[idx] < STOCK_CLOSE)]
            if len(idx) < 60:
                continue
        elif len(idx) < 200:
            continue
        yield int(u), idx


def walk(d, i0, side, entry, sl, tp, last, atr_cost=0.0, slip=0.5):
    """Simulate from bar i0 to bar `last` inclusive. Returns net R after spread+slip."""
    risk = abs(entry - sl)
    if risk <= 0:
        return None
    s = 1 if side == "buy" else -1
    px = d["close"][last]
    for j in range(i0, last + 1):
        lo, hi = d["low"][j], d["high"][j]
        if (s == 1 and lo <= sl) or (s == -1 and hi >= sl):
            px = sl
            break
        if tp is not None and ((s == 1 and hi >= tp) or (s == -1 and lo <= tp)):
            px = tp
            break
    cost = d["spread"][i0] * d["point"] * (1 + slip)
    return ((px - entry) * s - cost) / risk


# --- strategies: each returns a list of net-R trades for one day --------------------------------------------

def orb(d, idx, A, n_bars=3, tp_r=None, min_atr=0.5, max_atr=4.0, **_):
    """Opening-range breakout (stocks: 13:30 open; gold: NY open, via `start_min`)."""
    t, c, h, l, o = d["time"], d["close"], d["high"], d["low"], d["open"]
    start = A.get("start_min", STOCK_OPEN)
    mins = (t[idx] % 86400) // 60
    k0 = np.where(mins >= start)[0]
    if len(k0) < n_bars + 3:
        return []
    k0 = k0[0]
    rng_idx = idx[k0:k0 + n_bars]
    hi, lo = h[rng_idx].max(), l[rng_idx].min()
    a = A["atr"][rng_idx[-1]]
    if not (min_atr * a <= hi - lo <= max_atr * a * 3):
        return []
    last = idx[min(len(idx) - 1, k0 + A.get("hold_bars", 10 ** 6))]
    for j in idx[k0 + n_bars:-1]:
        if c[j] > hi or c[j] < lo:
            side = "buy" if c[j] > hi else "sell"
            entry = o[j + 1]
            sl = lo if side == "buy" else hi
            tp = None if tp_r is None else entry + (1 if side == "buy" else -1) * tp_r * abs(entry - sl)
            r = walk(d, j + 1, side, entry, sl, tp, last)
            return [r] if r is not None else []
    return []


def vwap_fade(d, idx, A, k=2.0, stop_atr=1.5, hold=12, **_):
    """Fade stretches beyond k*ATR from session VWAP, target VWAP, time stop."""
    t, c, h, l, o, v = d["time"], d["close"], d["high"], d["low"], d["open"], d["tick_volume"] + 1.0
    tp_ = (h[idx] + l[idx] + c[idx]) / 3
    vw = np.cumsum(tp_ * v[idx]) / np.cumsum(v[idx])
    out, nxt = [], 8
    for q in range(8, len(idx) - hold - 2):
        if q < nxt or len(out) >= 3:
            continue
        j = idx[q]
        a = A["atr"][j]
        if not a == a:
            continue
        dev = c[j] - vw[q]
        if abs(dev) > k * a:
            side = "sell" if dev > 0 else "buy"
            entry = o[j + 1]
            sl = entry + (stop_atr * a if side == "sell" else -stop_atr * a)
            tp = vw[q]
            if (side == "sell" and tp >= entry) or (side == "buy" and tp <= entry):
                continue
            r = walk(d, j + 1, side, entry, sl, tp, idx[q + hold])
            if r is not None:
                out.append(r)
                nxt = q + hold + 1
    return out


def mom_close(d, idx, A, lead=6, tail=6, **_):
    """Gao et al. intraday momentum: first `lead` bars' return predicts the last `tail` bars; hold to close."""
    c, o = d["close"], d["open"]
    if d["gold"] or len(idx) < lead + tail + 10:
        return []
    ret = c[idx[lead - 1]] - o[idx[0]]
    if ret == 0:
        return []
    side = "buy" if ret > 0 else "sell"
    j = idx[-tail]
    entry = o[j]
    a = A["atr"][j]
    sl = entry - (1 if side == "buy" else -1) * 2.0 * a * np.sqrt(tail)
    r = walk(d, j, side, entry, sl, None, idx[-1])
    return [r] if r is not None else []


def asian_break(d, idx, A, tp_r=None, end_hour=16, **_):
    """Gold: break of the 00:00-07:00 UTC range, entered between 07:00 and 12:00, flat by end_hour."""
    t, c, h, l, o = d["time"], d["close"], d["high"], d["low"], d["open"]
    mins = (t[idx] % 86400) // 60
    asia = idx[mins < 7 * 60]
    if len(asia) < 60:
        return []
    hi, lo = h[asia].max(), l[asia].min()
    a = A["atr"][asia[-1]]
    if not (1.0 * a <= hi - lo <= 12 * a):
        return []
    last = idx[np.where(mins < end_hour * 60)[0][-1]]
    for q in np.where((mins >= 7 * 60) & (mins < 12 * 60))[0]:
        j = idx[q]
        if c[j] > hi or c[j] < lo:
            side = "buy" if c[j] > hi else "sell"
            entry = o[j + 1]
            sl = lo if side == "buy" else hi
            tp = None if tp_r is None else entry + (1 if side == "buy" else -1) * tp_r * abs(entry - sl)
            r = walk(d, j + 1, side, entry, sl, tp, last)
            return [r] if r is not None else []
    return []


STRATS = {
    "orb": (orb, {"n_bars": [1, 3, 6], "tp_r": [None, 1.5, 2.5]}, True, True),
    "vwap_fade": (vwap_fade, {"k": [1.5, 2.0, 3.0], "stop_atr": [1.0, 2.0], "hold": [6, 12]}, True, True),
    "mom_close": (mom_close, {"lead": [3, 6], "tail": [6, 12]}, True, False),
    "asian_break": (asian_break, {"tp_r": [None, 1.5, 2.5], "end_hour": [13, 17]}, False, True),
}


def stats(r, rng):
    r = np.asarray(r, float)
    if len(r) < 5:
        return {"n": len(r), "E": float("nan"), "pf": float("nan"), "win": float("nan"), "lo": float("nan"),
                "hi": float("nan")}
    bs = rng.choice(r, (2000, len(r))).mean(axis=1)
    w, ls = r[r > 0].sum(), -r[r < 0].sum()
    return {"n": len(r), "E": r.mean(), "pf": w / ls if ls else float("inf"), "win": (r > 0).mean(),
            "lo": np.percentile(bs, 2.5), "hi": np.percentile(bs, 97.5)}


def run_combo(datasets, fn, params, split):
    tr, te = [], []
    for d in datasets:
        A = {"atr": atr_series(d["high"], d["low"], d["close"])}
        if d["gold"] and fn is orb:
            A["start_min"] = 13 * 60 + 30
            A["hold_bars"] = 78
        for u, idx in days(d):
            res = fn(d, idx, A, **params)
            (tr if u < split else te).extend(res)
    return tr, te


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="+", default=["XAUUSDm", "AAPLm", "NVDAm", "TSLAm", "MSFTm", "AMZNm", "METAm"])
    a = ap.parse_args()
    rng = np.random.default_rng(1)
    data = [load(s) for s in a.symbols]
    allday = sorted({u for d in data for u, _ in days(d)})
    split = allday[int(len(allday) * 0.6)]
    groups = {"gold": [d for d in data if d["gold"]], "stocks": [d for d in data if not d["gold"]]}
    lines = [f"# Strategy research {time.strftime('%Y%m%d-%H%M')}",
             f"\nSymbols {a.symbols}; train = days before ordinal {split}, test = after. Net of spread+0.5x slip.\n"]
    for name, (fn, grid, on_stock, on_gold) in STRATS.items():
        for gname, ds in groups.items():
            if not ds or (gname == "stocks" and not on_stock) or (gname == "gold" and not on_gold):
                continue
            rows = []
            for vals in itertools.product(*grid.values()):
                p = dict(zip(grid, vals))
                tr, te = run_combo(ds, fn, p, split)
                rows.append((p, stats(tr, rng), stats(te, rng)))
            rows.sort(key=lambda x: -(x[1]["E"] if x[1]["E"] == x[1]["E"] else -9))
            lines += [f"## {name} on {gname}  ({len(rows)} configs tried)\n",
                      "| params | train n/E/PF | test n/E/PF/win | test 95% CI |", "|---|---|---|---|"]
            for p, s1, s2 in rows[:4]:
                lines.append(f"| {p} | {s1['n']}/{s1['E']:+.2f}R/{s1['pf']:.2f} | {s2['n']}/{s2['E']:+.2f}R/"
                             f"{s2['pf']:.2f}/{s2['win']:.0%} | ({s2['lo']:+.2f}, {s2['hi']:+.2f}) |")
            lines.append("")
    md = "\n".join(lines)
    out = ROOT / "reports" / f"research-{time.strftime('%Y%m%d-%H%M')}.md"
    out.write_text(md, encoding="utf-8")
    print(md)
    print("written", out)


if __name__ == "__main__":
    main()
