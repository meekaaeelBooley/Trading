"""Historical replay of the live rules. Pure (numpy/stdlib): the same signal, gate, clock and SL-management
functions as the live server, with M15 closes for decisions and M1 bars for trade simulation.

Data dict: {"point": float, "m1"|"m15"|"h1"|"h4": {"time","open","high","low","close"[,"spread"]: np.ndarray}}.
Limitations (also stated in reports): news gating only if `events` are supplied; fills at bar prices plus a
fixed spread/slippage model; SL checked before TP inside one M1 bar (pessimistic); lot-step rounding ignored;
outcomes are in R (risk_pct of equity per trade), so margin limits are not modelled.
"""
import itertools
from datetime import datetime, timezone

import numpy as np

from . import clock, exits as ex_, gates, indicators as ind, journal as jr, review as rv, risk, signal as sg
from .defaults import DEFAULTS

SIM = {"spread_points": 120.0, "slip_points": 10.0, "commission_r": 0.0, "events": [],
       "run_starts": ["10:00", "15:30"], "start_ts": 0, "end_ts": 4e12}
CHECK_S = 300  # live manages open positions every <=5 min
TFS = ("m1", "m5", "m15", "h1", "h4")  # m1/m5 are alternative intrabar series; either may be absent


def load(path):
    z = np.load(path)
    data = {"point": float(z["point"])}
    for tf in TFS:
        if f"{tf}_time" in z:
            data[tf] = {k: z[f"{tf}_{k}"] for k in ("time", "open", "high", "low", "close", "spread")
                        if f"{tf}_{k}" in z}
    return data


def save(path, data):
    out = {"point": np.array(data["point"])}
    for tf in TFS:
        for k, v in data.get(tf, {}).items():
            out[f"{tf}_{k}"] = v
    np.savez_compressed(path, **out)


def _sched_ts(day, hhmm):
    h, m = hhmm.split(":")
    return datetime(day.year, day.month, day.day, int(h), int(m), tzinfo=clock.SAST).timestamp()


def pick_intrabar(data, which="auto"):
    """(series, step_seconds). auto: M1 when it covers >=80% of the M15 span, else M5 (broker M1 history is capped)."""
    if which in ("m1", "m5"):
        return data[which], 60 if which == "m1" else 300
    span = float(data["m15"]["time"][-1] - data["m15"]["time"][0]) or 1.0
    if "m1" in data and len(data["m1"]["time"]) * 60 >= 0.8 * span * 5 / 7:  # ~5/7 of calendar time is trading time
        return data["m1"], 60
    return data["m5"], 300


def run(data, cfg, sim=None):
    """Replay. Returns journal-schema `exit` records (chronological), each with an extra `t` (entry epoch)."""
    cfg, sim = {**DEFAULTS, **cfg}, {**SIM, **(sim or {})}
    point = data["point"]
    m15, h1, h4 = data["m15"], data["h1"], data["h4"]
    ib, step = pick_intrabar(data, sim.get("intrabar", "auto"))
    m1t = ib["time"]
    o, h, l, c, tm = (np.asarray(m15[k]) for k in ("open", "high", "low", "close", "time"))
    t_close = tm + 900
    h1_ct, h4_ct = h1["time"] + 3600, h4["time"] + 14400
    cap = cfg["run_max_minutes"] * 60
    sim["start_ts"] = max(sim["start_ts"], float(m1t[0]))  # M1 history is often shorter than the higher timeframes
    n, out, eq = len(tm), [], 1.0
    day_eq, used, bias_cache, atr_cache = {}, set(), {}, {}
    cur = None
    i = 0

    def atr_at(idx):
        if idx not in atr_cache:
            lo = max(0, idx - 318)
            atr_cache[idx] = ind.atr(h[lo:idx + 1], l[lo:idx + 1], c[lo:idx + 1], 14)
        return atr_cache[idx]

    while i < n:
        tc = float(t_close[i])
        if tc < sim["start_ts"] or tc > sim["end_ts"]:
            i += 1
            continue
        if cur and tc - cur["start"] >= cap:
            cur = None
        if cur is None:
            d = datetime.fromtimestamp(tc, clock.SAST).date()
            if sim["run_starts"] == "auto":
                cur = {"start": tc, "trades": 0, "consec": 0, "stopped": False}
            else:
                for hhmm in sim["run_starts"]:
                    st = _sched_ts(d, hhmm)
                    if (d, hhmm) not in used and st <= tc < st + cap:
                        used.add((d, hhmm))
                        cur = {"start": st, "trades": 0, "consec": 0, "stopped": False}
                        break
        if cur is None or cur["stopped"]:
            i += 1
            continue
        ph = clock.phase(datetime.fromtimestamp(tc, timezone.utc), cfg, tc - cur["start"])
        if not ph["entry_ok"]:
            i += 1
            continue
        k1, k4 = int(np.searchsorted(h1_ct, tc, "right")), int(np.searchsorted(h4_ct, tc, "right"))
        if (k1, k4) not in bias_cache:
            bias_cache[(k1, k4)] = ind.bias(h1["close"][max(0, k1 - 319):k1], h4["close"][max(0, k4 - 319):k4])
        bias = bias_cache[(k1, k4)]
        if bias == "flat" or i < 60:
            i += 1
            continue
        lo = max(0, i - 318)
        sig, _ = sg.find_signal(o[lo:i + 1], h[lo:i + 1], l[lo:i + 1], c[lo:i + 1], bias, cfg)
        if not sig:
            i += 1
            continue
        sp_pts = float(m15["spread"][i]) if "spread" in m15 and m15["spread"][i] > 0 else sim["spread_points"]
        day = datetime.fromtimestamp(tc, clock.SAST).date()
        day_eq.setdefault(day, eq)
        news_blocked = any(e - cfg["news_before_min"] * 60 <= tc <= e + cfg["news_after_min"] * 60
                           for e in sim["events"])
        blk = gates.blockers(dict(
            entry_ok=True, phase=ph["phase"], kill=False, halt=False, stopped=False, stop_reason="", demo_ok=True,
            market_open=True, data_fresh=True, open_positions=0, max_positions=cfg["max_positions"],
            trades=cur["trades"], max_trades=cfg["max_trades_session"], consec_losses=cur["consec"],
            max_consec=cfg["max_consec_losses"], day_pct=(eq / day_eq[day] - 1) * 100,
            daily_stop=cfg["daily_stop_pct"], news_blocked=news_blocked, news_reason="news:sim", spread=sp_pts,
            spread_max=cfg["spread_max_points"], atr=sig["atr"], atr_min=cfg["atr_min"], atr_max=cfg["atr_max"]))
        if blk:
            i += 1
            continue
        j = int(np.searchsorted(m1t, tc))
        if j >= len(m1t) or m1t[j] - tc > 5 * step:  # market closed / no data right after the close
            i += 1
            continue
        rec = _trade(ib, step, m15, cfg, sim, sig, j, cur["start"] + cap, point, atr_at, t_close)
        if rec is None:
            i += 1
            continue
        exit_ts = rec.pop("_exit_ts")
        rec.update({"type": "exit", "ticket": len(out) + 1, "signal_id": f"bt-{int(tc)}-{sig['side']}",
                    "side": sig["side"], "pattern": sig["pattern"], "bias": bias, "atr": round(sig["atr"], 1),
                    "spread": round(sp_pts), "hour": datetime.fromtimestamp(tc, clock.SAST).hour, "t": int(tc)})
        out.append(rec)
        r = rec["outcome_r"]
        cur["trades"] += 1
        eq *= 1 + r * cfg["risk_pct"] / 100
        if r <= -cfg["loss_threshold_r"]:
            cur["consec"] += 1
        elif r > 0:
            cur["consec"] = 0
        if cur["consec"] >= cfg["max_consec_losses"] or cur["trades"] >= cfg["max_trades_session"]:
            cur["stopped"] = True
        i = max(i + 1, int(np.searchsorted(t_close, exit_ts, "right")))
    return out


def _trade(ib, step, m15, cfg, sim, sig, j, run_end, point, atr_at, t_close):
    mt, mo, mh, ml, mc = (ib[k] for k in ("time", "open", "high", "low", "close"))
    sp = (float(ib["spread"][j]) if "spread" in ib and ib["spread"][j] > 0 else sim["spread_points"]) * point
    slip = sim["slip_points"] * point
    buy = sig["side"] == "buy"
    sign = 1 if buy else -1
    entry = float(mo[j]) + (sp + slip if buy else -slip)  # buy at ask, sell at bid
    sl = sig["sl"]
    r_dist = abs(entry - sl)
    if r_dist <= 0 or (buy and sl >= entry) or (not buy and sl <= entry):
        return None
    tp = entry + sign * cfg["tp_r"] * r_dist
    if abs(tp - entry) / r_dist < cfg["min_rr"]:
        return None
    side = sig["side"]
    cur_sl, done_frac, realised, partial = sl, 0.0, 0.0, False
    hi, lo = -1e18, 1e18
    t_entry = int(mt[j])
    val = lambda bid: bid if buy else bid + sp  # price a position closes at: bid for longs, ask for shorts
    nb = len(mt)
    for k in range(j, nb):
        bo, bh, bl = float(mo[k]), float(mh[k]), float(ml[k])
        hi, lo = max(hi, bh), min(lo, bl)
        t_end = int(mt[k]) + step
        px, kind, closed_by = None, "other", None
        # SL first (pessimistic), then TP; gaps through the SL fill at the open
        if buy and bl <= cur_sl:
            px, kind = min(cur_sl, bo), "sl"
        elif not buy and bh + sp >= cur_sl:
            px, kind = max(cur_sl, bo + sp), "sl"
        elif buy and bh >= tp:
            px, kind = tp, "tp"
        elif not buy and bl + sp <= tp:
            px, kind = tp, "tp"
        elif t_end >= run_end:
            px = val(float(mc[k]))  # run cap: flatten
        elif t_end % CHECK_S == 0:  # live manages every <=5 min; M5 bars are always on that grid
            price = val(float(mc[k]))
            ev = next((e for e in sim["events"] if 0 <= e - t_end <= cfg["pre_event_exit_min"] * 60), None)
            if cfg["pre_event_exit"] and ev is not None and (price - entry) * sign > 0:
                px, closed_by = price, "pre_event"
            else:
                if cfg["partial_tp"] and not partial and risk.partial_due(side, entry, price, r_dist,
                                                                           cfg["partial_at_r"]):
                    realised += cfg["partial_frac"] * (price - entry) * sign / r_dist
                    done_frac, partial = cfg["partial_frac"], True
                idx = int(np.searchsorted(t_close, t_end, "right")) - 1
                if idx >= 5:
                    last5 = slice(idx - 4, idx + 1)
                    swing = float(m15["low"][last5].min()) if buy else float(m15["high"][last5].max())
                    new = risk.manage_sl(side, entry, price, cur_sl, r_dist, atr_at(idx), swing)
                    if new is not None:
                        cur_sl = new
        if px is not None:
            r = round(realised + (1 - done_frac) * (px - entry) * sign / r_dist - sim["commission_r"], 2)
            fav, adv = ((hi - entry), (entry - lo)) if buy else ((entry - lo), (hi - entry))
            return {"outcome_r": r, "exit_reason": ex_.exit_reason(kind, r, closed_by, cfg["loss_threshold_r"]),
                    "mfe_r": round(max(fav, 0) / r_dist, 2), "mae_r": round(max(adv, 0) / r_dist, 2),
                    "dur_min": round((t_end - t_entry) / 60), "partial": partial, "_exit_ts": t_end}
    return None  # ran off the end of the data: the unfinished trade is dropped


def split(exits, frac=0.6):
    """Chronological train/test split by entry time."""
    h = int(len(exits) * frac)
    return exits[:h], exits[h:]


def summarise(exits, risk_pct):
    st = jr.stats(exits, risk_pct)
    st["ci95"] = rv.ci([e["outcome_r"] for e in exits]) if len(exits) >= 2 else None
    return st


def sweep(data, cfg, grid, sim=None, frac=0.6, cap=64):
    """Grid over cfg overrides {key: [values]}. Each row reports train and held-out test stats; rank by train and
    judge by test so the winner is not just the best fit. Rows come back sorted by train expectancy."""
    keys = list(grid)
    rows = []
    for vals in list(itertools.product(*(grid[k] for k in keys)))[:cap]:
        over = dict(zip(keys, vals))
        ex = run(data, {**cfg, **over}, sim)
        tr, te = split(ex, frac)
        rows.append({"params": over, "all": summarise(ex, cfg["risk_pct"]), "train": summarise(tr, cfg["risk_pct"]),
                     "test": summarise(te, cfg["risk_pct"])})
    return sorted(rows, key=lambda r: -(r["train"].get("expectancy_r") or -9))


def markdown(title, rows, note=""):
    def f(s):
        if not s.get("n"):
            return "n=0"
        return (f"n={s['n']} E={s['expectancy_r']:+.2f}R win={s['win_rate']:.0%} PF={s['profit_factor']} "
                f"DD={s['max_dd_pct']}% ci={s.get('ci95')}")

    lines = [f"# {title}", "", note, "", "| params | train | test (held out) |", "|---|---|---|"]
    lines += [f"| {r['params']} | {f(r['train'])} | {f(r['test'])} |" for r in rows]
    return "\n".join(lines) + "\n"
