r"""Research lab: cost-realistic intraday strategy testing on Exness M5 history (XAUUSDm, USTECm). Offline, numpy only.

Library part (import it):  Mkt(sym), sim(...), run_signals(...), stats(...), report(...)
Prices: MT5 bars are BID. Longs buy at ask (= bid + spread) and exit at bid; shorts sell at bid and exit at ask.
Costs: real per-bar spread from the broker + `slip` x spread of adverse slippage on every market fill (entries,
stops, time exits). Limit-style target fills get no slippage. Stop is checked BEFORE target inside a bar (pessimistic).
Management (optional) sees only bars before the one being evaluated: no look-ahead.
R = net pnl / initial risk (entry-to-stop distance), so R already contains the spread.
"""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine import sessions as ss  # noqa: E402


def atr_series(h, l, c, n=14):
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc)))
    out = np.full(len(tr), np.nan)
    if len(tr) < n:
        return out
    a = tr[:n].mean()
    out[n - 1] = a
    for i in range(n, len(tr)):
        a = (a * (n - 1) + tr[i]) / n
        out[i] = a
    return out


class Mkt:
    """One instrument on M5 bars with precomputed session clocks."""

    def __init__(self, sym, tf="m5"):
        z = np.load(ROOT / "data" / f"{sym}_tf.npz")
        self.sym, self.point = sym, float(z["point"])
        k = lambda x: z[f"{tf}_{x}"]
        self.t = k("time").astype(np.int64)
        self.o, self.h, self.l, self.c = (k(x).astype(float) for x in ("open", "high", "low", "close"))
        sp = k("spread").astype(float) * self.point
        med = np.median(sp[sp > 0])
        self.sp = np.where(sp > 0, sp, med)
        self.tv = k("tick_volume").astype(float)
        self.n = len(self.t)
        self.atr = atr_series(self.h, self.l, self.c)
        self.nym, self.lonm = ss.local_minute(self.t, "ny"), ss.local_minute(self.t, "lon")
        self.nyd, self.lond = ss.local_day(self.t, "ny"), ss.local_day(self.t, "lon")
        self.wd = ss.weekday(self.t, "ny")
        self.year_frac = (self.t - self.t[0]) / (self.t[-1] - self.t[0])
        self.days = {}
        for i, d in enumerate(self.nyd):
            lo, hi = self.days.get(d, (i, i))
            self.days[d] = (lo, i)

    def gap_ok(self, i, j):
        """True when bars i..j are contiguous M5 bars (no weekend / maintenance gap inside)."""
        return self.t[j] - self.t[i] <= (j - i) * 300 * 1.01 + 60


def sim(m, i, side, sl, tp_r=None, last=None, be_r=None, trail_k=None, trail_after=1.0, slip=0.5, tp=None,
        partial=None):
    """Enter at the OPEN of bar i (market, with spread+slip). `sl` is an absolute price. Exits: stop (optionally moved to
    break-even after +be_r R and trailed trail_k x ATR(entry) behind the best price once +trail_after R), target `tp_r` R
    (or absolute `tp`), or the close of bar `last`. Returns dict(r, j, kind, mfe, mae) or None if the stop is invalid."""
    last = min(m.n - 1, i + 288) if last is None else min(last, m.n - 1)
    if last < i:
        return None
    sgn = 1 if side == "buy" else -1
    sl_ = slice(i, last + 1)
    SP = m.sp[sl_]
    if sgn == 1:
        O, H, L, C = m.o[sl_], m.h[sl_], m.l[sl_], m.c[sl_]
        entry = m.o[i] + m.sp[i] + slip * m.sp[i]
        stop0 = sl
    else:  # mirror shorts onto a long (ask-based, negated) series
        O, H, L, C = -(m.o[sl_] + SP), -(m.l[sl_] + SP), -(m.h[sl_] + SP), -(m.c[sl_] + SP)
        entry = -(m.o[i] - slip * m.sp[i])
        stop0 = -sl
    rd = entry - stop0
    if rd <= 0:
        return None
    tp_t = None
    if tp is not None:
        tp_t = tp if sgn == 1 else -tp
    elif tp_r is not None:
        tp_t = entry + tp_r * rd
    nb = len(H)
    stop = np.full(nb, stop0)
    if be_r is not None or trail_k is not None:
        prevmax = np.r_[-np.inf, np.maximum.accumulate(H)[:-1]]  # best price seen BEFORE each bar
        fav = prevmax - entry
        if be_r is not None:
            stop = np.where(fav >= be_r * rd, np.maximum(stop, entry), stop)
        if trail_k is not None:
            a = m.atr[i] if np.isfinite(m.atr[i]) else rd
            stop = np.where(fav >= trail_after * rd, np.maximum(stop, prevmax - trail_k * a), stop)
    hit_stop = L <= stop
    hit_tp = (H >= tp_t) if tp_t is not None else np.zeros(nb, bool)
    ev = hit_stop | hit_tp
    if ev.any():
        k = int(np.argmax(ev))
        if hit_stop[k]:
            fill, kind = min(stop[k], O[k]) - slip * SP[k], "sl"
        else:
            fill, kind = tp_t, "tp"
    else:
        k, kind = nb - 1, "time"
        fill = C[k] - slip * SP[k]
    r = (fill - entry) / rd
    if partial is not None:  # (at_r, frac): bank `frac` of the position when price first reaches +at_r R (before the exit)
        at_r, frac = partial
        lvl = entry + at_r * rd
        reach = np.where(H[:k + 1] >= lvl)[0]
        if len(reach) and not (kind == "sl" and reach[0] >= k):  # stop-first inside the exit bar: no partial
            r = frac * at_r + (1 - frac) * r
    mfe = (H[:k + 1].max() - entry) / rd
    mae = (entry - L[:k + 1].min()) / rd
    return {"r": float(r), "j": i + k, "kind": kind, "mfe": float(mfe), "mae": float(mae), "rd": float(rd),
            "bars": k + 1}


def run_signals(m, sigs, one_at_a_time=True, control=True, **simkw):
    """sigs: list of dicts {i, side, sl, [tp_r|tp], [last], [be_r], [trail_k], ...}. Runs each (skipping signals that
    start before the previous trade of this run closed), plus an opposite-direction control with the mirrored stop
    distance at the same entry (what a coin-flip on direction would have earned with the same geometry)."""
    out, busy = [], -1
    for s in sorted(sigs, key=lambda x: x["i"]):
        if one_at_a_time and s["i"] <= busy:
            continue
        kw = {**simkw, **{k: v for k, v in s.items() if k in ("tp_r", "tp", "last", "be_r", "trail_k", "trail_after", "slip", "partial")}}
        res = sim(m, s["i"], s["side"], s["sl"], **kw)
        if res is None:
            continue
        res.update(i=s["i"], side=s["side"], t=int(m.t[s["i"]]), tag=s.get("tag"))
        if control:
            opp = "sell" if s["side"] == "buy" else "buy"
            entry_ref = m.o[s["i"]]
            d = abs(entry_ref - s["sl"])
            sl2 = entry_ref - d if opp == "buy" else entry_ref + d
            kw2 = dict(kw)
            kw2.pop("tp", None)
            if "tp" in kw:
                kw2["tp_r"] = abs(kw["tp"] - entry_ref) / d if d else None
            c2 = sim(m, s["i"], opp, sl2, **kw2)
            res["ctrl"] = c2["r"] if c2 else np.nan
        out.append(res)
        busy = res["j"]
    return out


def stats(trs, boot=2000, seed=1):
    r = np.array([x["r"] for x in trs], float)
    n = len(r)
    if n < 3:
        return {"n": n, "E": np.nan, "win": np.nan, "pf": np.nan, "t": np.nan, "lo": np.nan, "hi": np.nan,
                "ctrl": np.nan, "edge": np.nan}
    rng = np.random.default_rng(seed)
    bs = rng.choice(r, (boot, n)).mean(axis=1)
    w, ls = r[r > 0].sum(), -r[r < 0].sum()
    ctrl = np.array([x.get("ctrl", np.nan) for x in trs], float)
    return {"n": n, "E": r.mean(), "win": (r > 0).mean(), "pf": w / ls if ls else np.inf,
            "t": r.mean() / (r.std(ddof=1) / np.sqrt(n)) if r.std() > 0 else 0.0,
            "lo": np.percentile(bs, 2.5), "hi": np.percentile(bs, 97.5),
            "ctrl": np.nanmean(ctrl) if np.isfinite(ctrl).any() else np.nan,
            "edge": r.mean() - np.nanmean(ctrl) if np.isfinite(ctrl).any() else np.nan}


def split(trs, frac=0.6, m=None):
    """Chronological split by entry time."""
    trs = sorted(trs, key=lambda x: x["t"])
    h = int(len(trs) * frac)
    return trs[:h], trs[h:]


def fmt(s):
    if s["n"] < 3:
        return f"n={s['n']}"
    return (f"n={s['n']:4d} E={s['E']:+.3f}R win={s['win']:.0%} PF={s['pf']:.2f} t={s['t']:+.1f} "
            f"CI=({s['lo']:+.2f},{s['hi']:+.2f}) ctrl={s['ctrl']:+.3f} edge={s['edge']:+.3f}")


def equity(trs, risk_frac):
    """Compounded equity curve (list) risking `risk_frac` of equity per trade, trades in time order."""
    eq, curve = 1.0, [1.0]
    for x in sorted(trs, key=lambda x: x["t"]):
        eq *= max(0.0, 1 + risk_frac * x["r"])
        curve.append(eq)
    return np.array(curve)


def max_dd(curve):
    peak = np.maximum.accumulate(curve)
    return float(((peak - curve) / peak).max())


def by_period(trs, m, k=4):
    """Stats in k equal chronological slices (to see whether the edge is steady or one lucky stretch)."""
    trs = sorted(trs, key=lambda x: x["t"])
    n = len(trs)
    return [stats(trs[a * n // k:(a + 1) * n // k], boot=300) for a in range(k)]
