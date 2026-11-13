"""Signal generators for the strategy families (research versions; vectorised-ish)."""
import sys; sys.path.insert(0, r"C:\Users\meeka\Desktop\Trading\tools")
import numpy as np, lab

def first_idx(m, region, minute):
    """dict local_day -> index of the bar at local minute `minute` (if present)."""
    mins, day = (m.nym, m.nyd) if region == "ny" else (m.lonm, m.lond)
    sel = np.where(mins == minute)[0]
    return {int(day[i]): int(i) for i in sel}

def orb(m, region="ny", start=570, n=3, window=12, tp_r=2.0, hold=60, sl_mode="opp", min_cost_mult=4.0, max_atr=None, only=None):
    out = []
    for d, i0 in first_idx(m, region, start).items():
        if i0 + n + window + 2 >= m.n or not m.gap_ok(i0, i0 + n + window + 2): continue
        rng = slice(i0, i0 + n)
        hi, lo = m.h[rng].max(), m.l[rng].min()
        a = m.atr[i0 - 1] if i0 > 0 else np.nan
        if not np.isfinite(a): continue
        width = hi - lo
        for j in range(i0 + n, i0 + n + window):
            c = m.c[j]
            if c > hi or c < lo:
                side = "buy" if c > hi else "sell"
                if only and side != only: break
                entry = m.o[j + 1]
                sl = lo if side == "buy" else hi
                if sl_mode == "mid": sl = (hi + lo) / 2
                rd = abs(entry - sl)
                cost = 2 * (m.sp[j + 1] * 1.5)  # spread + slip in + slip out + spread ~ 3 half units
                if rd < min_cost_mult * cost: break
                if max_atr and rd > max_atr * a: break
                out.append(dict(i=j + 1, side=side, sl=sl, tp_r=tp_r, last=i0 + hold, tag=d))
                break
    return out

def asian_break(m, rng_start=0, rng_end_lon=480, window_bars=36, tp_r=2.0, hold_lon_end=17*60, min_atr=1.5, max_atr=14, region="lon", fade=False, confirm=1):
    """Range = bars from rng_start..rng_end (local London minutes); trade the first close beyond it within window."""
    out = []
    mins, day = (m.lonm, m.lond) if region == "lon" else (m.nym, m.nyd)
    for d in np.unique(day):
        lo_i, hi_i = m.days.get(d, (None, None)) if region == "ny" else (None, None)
        idx = np.where(day == d)[0]
        if len(idx) < 150: continue
        rs = idx[(mins[idx] >= rng_start) & (mins[idx] < rng_end_lon)]
        if len(rs) < 40: continue
        hi, lo = m.h[rs].max(), m.l[rs].min()
        a = m.atr[rs[-1]]
        if not np.isfinite(a) or not (min_atr * a <= hi - lo <= max_atr * a): continue
        ws = idx[(mins[idx] >= rng_end_lon)][:window_bars]
        endbar = idx[mins[idx] < hold_lon_end]
        if len(ws) < 3 or len(endbar) == 0: continue
        last = int(endbar[-1])
        for q, j in enumerate(ws[:-1]):
            c = m.c[j]
            if not fade:
                if c > hi or c < lo:
                    side = "buy" if c > hi else "sell"
                    sl = lo if side == "buy" else hi
                    out.append(dict(i=int(j + 1), side=side, sl=sl, tp_r=tp_r, last=last, tag=int(d))); break
            else:
                # sweep: a bar pokes beyond the range but CLOSES back inside -> fade toward the other side
                if m.h[j] > hi and c < hi:
                    ext = m.h[j]
                    side, sl = "sell", ext + 0.1 * a
                    out.append(dict(i=int(j + 1), side=side, sl=sl, tp_r=tp_r, last=last, tag=int(d))); break
                if m.l[j] < lo and c > lo:
                    ext = m.l[j]
                    side, sl = "buy", ext - 0.1 * a
                    out.append(dict(i=int(j + 1), side=side, sl=sl, tp_r=tp_r, last=last, tag=int(d))); break
    return out

def intraday_mom(m, lead_start=570, lead_bars=6, enter=930, hold_to=955, stop_atr=3.0, region="ny", min_move_atr=0.0):
    """Sign of the first `lead_bars` bars' return -> trade in that direction at local minute `enter`, flat at `hold_to`."""
    out = []
    f0, f1, f2 = first_idx(m, region, lead_start), first_idx(m, region, enter), first_idx(m, region, hold_to)
    for d, i0 in f0.items():
        if d not in f1 or d not in f2 or i0 + lead_bars >= m.n: continue
        ie, il = f1[d], f2[d]
        if not m.gap_ok(i0, il): continue
        ret = m.c[i0 + lead_bars - 1] - m.o[i0]
        a = m.atr[ie - 1]
        if not np.isfinite(a) or abs(ret) < min_move_atr * a or ret == 0: continue
        side = "buy" if ret > 0 else "sell"
        sl = m.o[ie] - stop_atr * a if side == "buy" else m.o[ie] + stop_atr * a
        out.append(dict(i=ie, side=side, sl=sl, last=il, tag=d))
    return out

def gap(m, open_min=570, close_min=955, fade=True, hold_bars=48, stop_atr=2.0, min_gap_atr=0.5, tp_gap=True):
    """US cash gap = open(09:30) vs previous day's last cash bar close. fade -> trade toward the gap fill."""
    out = []
    f_open, f_close = first_idx(m, "ny", open_min), first_idx(m, "ny", close_min)
    days = sorted(f_open)
    for d in days:
        i0 = f_open[d]
        # previous cash close = close of bar at 15:55 on the previous available day
        pd = [x for x in days if x < d]
        if not pd or pd[-1] not in f_close: continue
        pc = m.c[f_close[pd[-1]]]
        a = m.atr[i0 - 1] if i0 > 0 else np.nan
        if not np.isfinite(a): continue
        gp = m.o[i0] - pc
        if abs(gp) < min_gap_atr * a: continue
        if fade:
            side = "sell" if gp > 0 else "buy"
        else:
            side = "buy" if gp > 0 else "sell"
        entry = m.o[i0]
        sl = entry - stop_atr * a if side == "buy" else entry + stop_atr * a
        sig = dict(i=i0, side=side, sl=sl, last=i0 + hold_bars, tag=d)
        if fade and tp_gap: sig["tp"] = pc
        out.append(sig)
    return out

def evaluate(m, sigs, label="", **kw):
    trs = lab.run_signals(m, sigs, **kw)
    tr, te = lab.split(trs, 0.6)
    return trs, lab.stats(trs), lab.stats(tr), lab.stats(te)
