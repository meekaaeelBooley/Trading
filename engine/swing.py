"""Swing book: multi-timeframe S/R + smart-money read, candidate scoring, and the rules unique to swing positions.

Timeframes: D1 and H4 give bias and big zones, H1 gives structure, points of interest (POI) and the ATR unit for stops,
M15 gives confirmation. Pure functions over closed bars; the server fetches the bars and enforces every limit.

Entry model (long shown, short mirrors): H4 structure bullish -> price pulls back into discount -> reacts at a POI
(fresh order block or fair value gap) that sits on an S/R zone -> a liquidity sweep and/or an M15 BOS/CHoCH confirms ->
stop beyond the POI / sweep extreme -> target the next opposing S/R zone or liquidity pool at >= swing_min_rr.
"""
from . import levels, risk, smc

SETUPS = ("ob_retest", "fvg_fill", "sr_bounce", "sweep_reversal", "break_retest", "choch_reversal", "other")
SWING_OVERRIDABLE = ("news", "risk_flag")  # the only soft gates a swing entry may bypass


def swing_ctx(ctx):
    """Gate facts for a swing entry: M1-scale ATR band, scalp position count, scalp trade count and scalp loss streak
    do not apply (swing has its own limits in swing_blockers). Everything else, incl. every hard gate, is unchanged."""
    return {**ctx, "atr": ctx["atr_min"], "open_positions": 0, "trades": 0, "consec_losses": 0}


def swing_blockers(n_open, n_today, side_open, side, now_sast, c):
    """Swing-only hard limits (never bypassable)."""
    b = []
    if not c["swing_enabled"]:
        b.append("swing_disabled")
    if n_open >= c["swing_max_positions"]:
        b.append("swing_positions_max")
    if n_today >= c["swing_max_per_day"]:
        b.append("swing_day_max")
    if side_open and side_open != side:
        b.append("opposite_swing_open")
    if c["swing_weekend_flat"] and now_sast.weekday() == 4 and _hm(now_sast) >= _min(c["swing_no_entry_friday_after"]):
        b.append("weekend_no_entry")
    if c["swing_weekend_flat"] and now_sast.weekday() == 5:
        b.append("weekend_no_entry")
    return b


def weekend_flat_due(now_sast, c):
    """True from Friday swing_friday_flat (SAST) until the weekend ends: swing positions are closed, no gap risk."""
    if not c["swing_weekend_flat"]:
        return False
    wd = now_sast.weekday()
    return (wd == 4 and _hm(now_sast) >= _min(c["swing_friday_flat"])) or wd == 5


def _hm(t):
    return t.hour * 60 + t.minute


def _min(s):
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def held_too_long(opened_ts, now_ts, max_hours):
    return bool(opened_ts) and now_ts - opened_ts >= max_hours * 3600


def stop_in_band(entry, sl, atr_h1, c):
    d = abs(entry - sl)
    return c["swing_min_sl_atr"] * atr_h1 <= d <= c["swing_max_sl_atr"] * atr_h1


# ---------------------------------------------------------------- analysis
def analyze_all(d1, h4, h1, m15, price, now_ts, c):
    """Per-timeframe SMC reads plus merged S/R zones, key levels and round numbers."""
    k = int(c["swing_pivot_k"])
    A = {name: smc.analyze(b, k) for name, b in (("d1", d1), ("h4", h4), ("h1", h1), ("m15", m15)) if b is not None}
    if not A.get("h1", {}).get("ok") or not A.get("h4", {}).get("ok"):
        return None
    atr = A["h1"]["atr"]
    frames = [(n, b["high"], b["low"], A[n]["atr"]) for n, b in (("d1", d1), ("h4", h4), ("h1", h1), ("m15", m15))
              if b is not None and A[n].get("ok")]
    Z = levels.build(frames, price, atr)
    return {"A": A, "Z": Z, "atr": atr, "key": levels.key_levels(d1, now_ts), "round": levels.round_levels(price),
            "bars": {"h1": h1, "m15": m15}}


def _fresh_pois(A, want, price, atr):
    """Order blocks and fair value gaps of direction `want` on H1/H4 that price is in, or could retrace to."""
    out = []
    for tf in ("h1", "h4"):
        a = A.get(tf)
        if not a or not a.get("ok"):
            continue
        for z in a["obs"]:
            if z["dir"] == want:
                out.append({"kind": "ob", "tf": tf, "lo": z["lo"], "hi": z["hi"], "fresh": not z["tested"]})
        for z in a["fvgs"]:
            if z["dir"] == want and z["fill"] < 0.9:
                out.append({"kind": "fvg", "tf": tf, "lo": z["lo"], "hi": z["hi"], "fresh": z["fill"] < 0.3})
    return out


def _targets(side, price, ctx):
    """Prices where the move meets opposition, nearest first: opposing S/R zones, liquidity pools, key highs / lows."""
    A, buy = ctx["A"], side == "buy"
    t = []
    for z in ctx["Z"]:
        if buy and z["kind"] == "resistance":
            t.append((z["lo"], "res"))
        elif not buy and z["kind"] == "support":
            t.append((z["hi"], "sup"))
    for tf in ("h1", "h4"):
        if A.get(tf, {}).get("ok"):
            for p in A[tf]["liq"]["bsl" if buy else "ssl"]:
                if (p["level"] > price) if buy else (p["level"] < price):
                    t.append((p["level"], "bsl" if buy else "ssl"))
    for name, d in ctx["key"].items():
        lvl = d.get("high" if buy else "low")
        if lvl is not None and ((lvl > price) if buy else (lvl < price)):
            t.append((lvl, name))
    return sorted(t, key=lambda x: x[0] if buy else -x[0])


def score_side(side, ctx, price, c):
    """Score one direction. Returns a candidate dict or None when no sound idea exists (counter-trend, no POI/zone,
    stop out of band, no target with enough reward)."""
    A, Z, atr = ctx["A"], ctx["Z"], ctx["atr"]
    buy = side == "buy"
    want, why, pts = ("bull" if buy else "bear"), [], 0.0
    h4, h1, m15, d1 = A["h4"], A["h1"], A.get("m15"), A.get("d1")
    last = (h4["events"] or [None])[-1]
    if h4["trend"] == want:
        pts += 2
        why.append(f"H4 structure {want}")
    elif last and last["dir"] == want and last["kind"] == "CHoCH" and h4["n"] - 1 - last["i"] <= 12:
        pts += 1
        why.append("fresh H4 CHoCH")
    else:
        return None
    if d1 and d1.get("ok"):
        if d1["trend"] == want:
            pts += 1
            why.append("D1 aligned")
        elif d1["trend"]:
            pts -= 1
            why.append("D1 against")
    if h1["trend"] == want:
        pts += 1
    rng = h1["range"] or h4["range"]
    if rng:
        loc = (price - rng["lo"]) / (rng["hi"] - rng["lo"])
        if (loc <= 0.5) if buy else (loc >= 0.5):
            pts += 1
            why.append(f"{'discount' if buy else 'premium'} {loc:.2f}")
        elif (loc > 0.75) if buy else (loc < 0.25):
            pts -= 1
            why.append("chasing the wrong end of the range")

    near = 0.35 * atr
    pois = [p for p in _fresh_pois(A, want, price, atr)
            if (p["hi"] < price + near if buy else p["lo"] > price - near) and abs((p["lo"] + p["hi"]) / 2 - price) <= 4 * atr]
    zone_side = "support" if buy else "resistance"
    zones_ = [z for z in Z if z["kind"] in (zone_side, "inside") and z["dist_atr"] <= 4]
    if not pois and not zones_:
        return None

    def at(p):
        return p["lo"] - near <= price <= p["hi"] + near

    def conf(p):  # S/R zone overlapping the POI
        return next((z for z in zones_ if z["lo"] - 0.25 * atr <= p["hi"] and p["lo"] - 0.25 * atr <= z["hi"]), None)

    def rank(p):
        s = (2.0 if p["kind"] == "ob" else 1.0) + (0.5 if p["fresh"] else 0) + (0.5 if p["tf"] == "h4" else 0)
        return s + (2.0 if conf(p) else 0) - 0.3 * abs((p["lo"] + p["hi"]) / 2 - price) / atr

    poi = max(pois, key=rank) if pois else None
    if poi:
        pts += 2.0 if poi["kind"] == "ob" else 1.0
        pts += 0.5 if poi["fresh"] else 0
        why.append(f"{poi['tf'].upper()} {'fresh ' if poi['fresh'] else ''}{'order block' if poi['kind'] == 'ob' else 'FVG'}")
        zone = conf(poi)
        if any(p is not poi and p["kind"] != poi["kind"] and p["lo"] <= poi["hi"] and poi["lo"] <= p["hi"] for p in pois):
            pts += 1
            why.append("OB+FVG stacked")
    else:
        zone = min(zones_, key=lambda z: z["dist_atr"])
        poi = {"kind": "zone", "tf": "/".join(sorted(zone["tfs"])), "lo": zone["lo"], "hi": zone["hi"], "fresh": False}
    if zone:
        pts += 2 + (1 if zone["touches"] >= 4 or zone["tfs"] & {"h4", "d1"} else 0)
        why.append(f"{zone_side} zone {'/'.join(sorted(zone['tfs']))} x{zone['touches']}")

    sweep_tf = next((tf for tf in ("m15", "h1") if A.get(tf, {}).get("ok") and A[tf]["liq"]["sweep"]
                     and A[tf]["liq"]["sweep"]["side"] == ("ssl" if buy else "bsl")
                     and A[tf]["liq"]["sweep"]["bars_ago"] <= (12 if tf == "m15" else 6)), None)
    sweep = A[sweep_tf]["liq"]["sweep"] if sweep_tf else None
    if sweep:
        pts += 1.5
        why.append(f"{sweep_tf.upper()} liquidity sweep")
    confirm = None
    if m15 and m15.get("ok") and m15["events"]:
        e = m15["events"][-1]
        if e["dir"] == want and m15["n"] - 1 - e["i"] <= 16:
            confirm = f"M15 {e['kind']}"
            pts += 2
            why.append(confirm)
    m15b = ctx["bars"].get("m15")
    rej = bool(zone and m15b is not None and levels.rejection(m15b["high"], m15b["low"], m15b["close"], zone, side, 4))
    if rej:
        pts += 1
        why.append("zone rejection")
    flip = bool(zone and levels.broken_retest(ctx["bars"]["h1"]["close"], zone, side))
    if flip:
        pts += 1.5
        why.append("break & retest")

    # trade construction
    buf = 0.3 * atr
    edge = min(poi["lo"], sweep["extreme"]) if buy and sweep else poi["lo"] if buy else \
        max(poi["hi"], sweep["extreme"]) if sweep else poi["hi"]
    sl = edge - buf if buy else edge + buf
    dist = abs(price - sl)
    if dist < c["swing_min_sl_atr"] * atr:
        sl = price - c["swing_min_sl_atr"] * atr if buy else price + c["swing_min_sl_atr"] * atr
        dist = abs(price - sl)
    if dist > c["swing_max_sl_atr"] * atr:
        return None
    tp = None
    targets = _targets(side, price, ctx)
    for lvl, name in targets:
        reach = abs(lvl - price) - 0.1 * atr
        if reach >= c["swing_min_rr"] * dist:
            tp = (lvl - 0.1 * atr if buy else lvl + 0.1 * atr, name)
            break
    if tp is None:
        return None
    setup = ("break_retest" if flip else "sweep_reversal" if sweep and not (poi["kind"] in ("ob", "fvg"))
             else "ob_retest" if poi["kind"] == "ob" else "fvg_fill" if poi["kind"] == "fvg" else "sr_bounce")
    if m15 and confirm and "CHoCH" in confirm and not zone:
        setup = "choch_reversal"
    confirmed = bool(confirm or sweep or rej or flip)
    status = ("ready" if confirmed else "at_poi") if at(poi) else "watch"
    return {"side": side, "status": status, "score": round(pts, 1), "setup": setup, "poi": poi["kind"],
            "zone": [round(poi["lo"], 2), round(poi["hi"], 2)], "sl": sl, "tp": tp[0], "tp_at": tp[1],
            "rr": round(abs(tp[0] - price) / dist, 2), "sl_atr": round(dist / atr, 2), "why": why,
            "key": f"{side}:{int(poi['lo'] / (0.5 * atr))}"}


def candidates(ctx, price, c, digits=2):
    """Both directions, best first; only ideas with score >= swing_min_score - 1 are listed (the server enforces the real
    threshold for alerts). Prices rounded for the brief."""
    out = []
    for side in ("buy", "sell"):
        cand = score_side(side, ctx, price, c)
        if cand and cand["score"] >= c["swing_min_score"] - 1:
            cand["sl"], cand["tp"] = round(cand["sl"], digits), round(cand["tp"], digits)
            out.append(cand)
    rank = {"ready": 0, "at_poi": 1, "watch": 2}
    return sorted(out, key=lambda x: (rank[x["status"]], -x["score"]))


def compact_zones(Z, digits=2, n=3):
    r = lambda x: round(float(x), digits)
    fmt = lambda z: [r(z["lo"]), r(z["hi"]), z["touches"], "/".join(sorted(z["tfs"])), round(z["dist_atr"], 1)]
    return {"res": [fmt(z) for z in levels.nearest(Z, "resistance", n)],
            "sup": [fmt(z) for z in levels.nearest(Z, "support", n)]}


def manage_levels(side, rec_entry, price, sl, r_dist, atr_h1, h1_closed, c):
    """New stop for a swing position or None: break-even at +swing_be_r, then trail behind the last 3 H1 bars once
    +swing_trail_r. Delegates to risk.manage_sl with H1 units. Never loosens."""
    last3 = h1_closed[-3:]
    swing = float(last3["low"].min()) if side == "buy" else float(last3["high"].max())
    return risk.manage_sl(side, rec_entry, price, sl, r_dist, atr_h1, swing, be_r=c["swing_be_r"], trail_r=c["swing_trail_r"])
