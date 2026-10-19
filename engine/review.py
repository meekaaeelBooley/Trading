"""Compact trade-review statistics. Pure Python so the LLM only ever reads the (small) result.

Input: exit records from the journal. Each is self-contained (features captured at entry are copied into the
exit record), so no joins and Claude never has to read the raw journal.
"""
import random
from statistics import median

ATR_BANDS = [(0, 45, "atr<45"), (45, 70, "atr45-70"), (70, 1e9, "atr>70")]
SPREAD_BANDS = [(0, 130, "spr<130"), (130, 170, "spr130-170"), (170, 1e9, "spr>170")]


def band(v, bands):
    if v is None:
        return "n/a"
    return next((name for lo, hi, name in bands if lo <= v < hi), "n/a")


_band = band


def ci(rs, iters=1000, alpha=0.05, seed=7):
    """Deterministic bootstrap CI of the mean: (lo, hi). Needs >= 2 values."""
    if len(rs) < 2:
        return None
    rng = random.Random(seed)
    n = len(rs)
    means = sorted(sum(rs[rng.randrange(n)] for _ in range(n)) / n for _ in range(iters))
    return round(means[int(iters * alpha / 2)], 2), round(means[int(iters * (1 - alpha / 2)) - 1], 2)


def _stat(rs):
    n = len(rs)
    return {"n": n, "exp": round(sum(rs) / n, 2), "win": round(sum(1 for r in rs if r > 0.25) / n, 2)}


def _group(exits, keyfn):
    g = {}
    for e in exits:
        g.setdefault(str(keyfn(e)), []).append(e["outcome_r"])
    return {k: _stat(v) for k, v in sorted(g.items())}


def analyze(exits, min_flag_n=8):
    """Return a compact dict: breakdowns by feature, exit mix, MFE/MAE diagnostics, flagged buckets."""
    ex = [e for e in exits if e.get("outcome_r") is not None]
    if not ex:
        return {"n": 0}
    dims = {
        "side": _group(ex, lambda e: e.get("side")),
        "pattern": _group(ex, lambda e: e.get("pattern")),
        "bias": _group(ex, lambda e: e.get("bias")),
        "hour": _group(ex, lambda e: e.get("hour")),
        "atr": _group(ex, lambda e: _band(e.get("atr"), ATR_BANDS)),
        "spread": _group(ex, lambda e: _band(e.get("spread"), SPREAD_BANDS)),
    }
    if any(e.get("regime") for e in ex):
        dims["regime"] = _group(ex, lambda e: e.get("regime") or "n/a")
    mix = {}
    for e in ex:
        mix[e.get("exit_reason", "?")] = mix.get(e.get("exit_reason", "?"), 0) + 1

    mf = [e for e in ex if e.get("mfe_r") is not None and e.get("mae_r") is not None]
    losers = [e for e in mf if e["outcome_r"] <= -0.25]
    winners = [e for e in mf if e["outcome_r"] >= 0.25]
    reached_1r = [e for e in mf if e["mfe_r"] >= 1.0]
    reached_tp = [e for e in mf if e["mfe_r"] >= 2.0]
    diag = {}
    if losers:
        diag["losers_med_mfe_r"] = round(median(e["mfe_r"] for e in losers), 2)  # high => entries ok, exits/mgmt weak
    if winners:
        diag["winners_med_mae_r"] = round(median(e["mae_r"] for e in winners), 2)  # low => SL has spare room
    if mf:
        diag["reached_1r"] = len(reached_1r)
        diag["reached_1r_but_lost"] = sum(1 for e in reached_1r if e["outcome_r"] <= -0.25)
        diag["reached_2r_not_banked"] = sum(1 for e in reached_tp if e["outcome_r"] < 1.75)
        diag["med_duration_min"] = round(median(e.get("dur_min", 0) for e in mf))

    flags = []
    for dim, buckets in dims.items():
        for k, s in buckets.items():
            if s["n"] >= min_flag_n and (s["exp"] <= -0.4 or s["exp"] >= 0.6):
                flags.append(f"{dim}={k}: n={s['n']} E={s['exp']:+.2f}R win={s['win']:.0%}")
    inter = interactions(ex, min_flag_n)
    for k, s_ in inter.items():
        if s_["exp"] <= -0.4 or s_["exp"] >= 0.6:
            flags.append(f"{k}: n={s_['n']} E={s_['exp']:+.2f}R win={s_['win']:.0%}")
    return {"n": len(ex), "by": dims, "interactions": inter, "exit_mix": mix, "diag": diag, "flags": flags,
            "note": "hypotheses only; act on a bucket only with n>=20"}


FEATS = ("side", "pattern", "bias", "hour", "atr_band", "spread_band", "regime")
PAIRS = (("hour", "pattern"), ("pattern", "atr_band"), ("side", "bias"), ("pattern", "side"),
         ("hour", "side"), ("pattern", "spread_band"))


def _feats(e):
    f = {k: e.get(k) for k in ("side", "pattern", "bias", "hour")}
    f["atr_band"], f["spread_band"] = band(e.get("atr"), ATR_BANDS), band(e.get("spread"), SPREAD_BANDS)
    f["regime"] = e.get("regime")
    return f


def interactions(ex, min_n=8):
    """Two-feature buckets with at least min_n trades: {'hour=10&pattern=pin': {n, exp, win}}."""
    g = {}
    for e in ex:
        f = _feats(e)
        for a, b in PAIRS:
            if f.get(a) is None or f.get(b) is None:
                continue
            g.setdefault(f"{a}={f[a]}&{b}={f[b]}", []).append(e["outcome_r"])
    return {k: _stat(v) for k, v in sorted(g.items()) if len(v) >= min_n}


def candidate_filters(exits, min_n=30, max_exp=-0.3):
    """Buckets (single or paired features) where trading has lost money robustly: n >= min_n, mean <= max_exp,
    95% bootstrap CI upper bound < 0, and BOTH chronological halves negative. Returns rule dicts for
    state/filters.json. Deliberately strict: many buckets are tested, so weak evidence must not become a rule."""
    ex = [e for e in exits if e.get("outcome_r") is not None]
    buckets = {}
    for e in ex:
        f = _feats(e)
        for k in FEATS:
            if f.get(k) is not None:
                buckets.setdefault(((k, f[k]),), []).append(e["outcome_r"])
        for a, b in PAIRS:
            if f.get(a) is not None and f.get(b) is not None:
                buckets.setdefault(((a, f[a]), (b, f[b])), []).append(e["outcome_r"])
    out = []
    for key, rs in sorted(buckets.items(), key=lambda kv: sorted(kv[0])):
        if len(rs) < min_n or sum(rs) / len(rs) > max_exp:
            continue
        lo_hi = ci(rs)
        h = len(rs) // 2
        if lo_hi is None or lo_hi[1] >= 0 or sum(rs[:h]) >= 0 or sum(rs[h:]) >= 0:
            continue
        out.append({"rule": dict(key), "n": len(rs), "exp": round(sum(rs) / len(rs), 2), "ci": list(lo_hi)})
    singles = [set(o["rule"].items()) for o in out if len(o["rule"]) == 1]
    return [o for o in out if len(o["rule"]) == 1 or not any(sg <= set(o["rule"].items()) for sg in singles)]
