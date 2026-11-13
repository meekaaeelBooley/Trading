"""Evidence-graded intraday playbook for USTECm (index) and XAUUSDm (gold). Pure numpy, closed M5 bars only.

Why this exists (research 2026-11-04, see reports/strategy-research-20261104.md): on 17-20 months of Exness M5 data
no classic pattern (opening-range break, London break, sweep reversal, scout impulse/break/sweep events, session
momentum, trend-following) has a net edge after spread+slippage. Short-hold tight-stop trades lose 0.07-0.3 ATR per
round trip to cost alone. Three narrow pockets survived the first (17-month) tests; with the deep history (XAU 2017-2026 and the MetaQuotes calendar,
2026-11-04) only trend_day survived, so the other two are SHELVED (kept for replays, in no tier):

  trend_day     USTEC  first 30 min of the US cash session sets the direction; enter 11:00 NY, hold to 16:00 NY.
                       (Gao-Han-Li-Zhou intraday momentum.) Deep history (2.2 effective years): +0.07R at >=1.5 ATR, t=+1.2, opposite-direction
                       control -0.20R, plateau stable from 1.0 to 2.5 ATR; buys +0.12R vs sells +0.02R (the sample is a +94% bull run).
  impulse_cont  USTEC  SHELVED 2026-11-04: continuation after a >=3 ATR impulse bar outside scheduled releases; structural stop.
                       +0.05R on 17 months, but -0.03R (t=-0.7, n=1109) on 2.6 y of deep history, first half -0.14R, second +0.13R.
  news_drift    XAU    SHELVED 2026-11-04 (see SHELVED): continuation after a >=2.5 ATR impulse bar on a scheduled USD release.
                       It looked like +1.45R on 44 events of 2025-26, but on the 2017-2024 hold-out (211 events, never used
                       for tuning, real MT5 calendar) it is -0.26R (t=-1.9): the earlier result was the 2025-26 gold bull run.

These are WIDE-STOP, FEW-TRADE, LET-IT-RUN strategies: that is what makes spread a small slice of R. The one live strategy is
graded B- (not statistically proven: its confidence interval includes 0). The demo is the out-of-sample test:
every trade is journaled under its strategy tag and `suspended()` switches a strategy off if live results are clearly bad.
Management differs from the scalp rules on purpose: the 50% partial at 0.7R cuts these edges by 35-95% in the backtests.
"""
import numpy as np

from . import indicators as ind, sessions as ss

REL_MIN = (510, 600, 840)  # New York minute-of-day of scheduled USD releases: 08:30, 10:00, 14:00
TP_R = 6.0  # far target so the broker-side order is a formality; exits are the stop, break-even and the time stop

STRATEGIES = {
    "trend_day": {"cls": "index", "grade": "B-", "hold": "to 16:00 New York",
                  "p": {"lead_bars": 6, "enter_min": 660, "exit_min": 960, "stop_atr": 3.0}},
    "impulse_cont": {"cls": "index", "grade": "D", "hold": "36 M5 bars",
                     "p": {"thr": 3.0, "body": 0.5, "hold": 36, "cooldown": 12, "min_stop_atr": 1.0, "max_stop_atr": 8.0}},
    "news_drift": {"cls": "gold", "grade": "D", "hold": "36 M5 bars",
                   "p": {"thr": 2.5, "body": 0.6, "hold": 36, "stop_atr": 1.5}},
}
PLAYBOOK_SETUPS = tuple(STRATEGIES) + ("pyramid",)
# Strategies that failed validation: kept for research replays (detect(..., include_shelved=True)) but in NO tier, so the
# desk never trades them. To re-enable one, add it to a tier's `risk` dict (and expect to justify it with new evidence).
SHELVED = {"impulse_cont": "deep history 2024-2026 n=1109 E=-0.03R t=-0.7, sign flips between halves (reports/playbook-backtest-20261104.md)",
           "news_drift": "hold-out 2017-2024 n=211 E=-0.26R t=-1.9; in-sample 2025-26 result was the gold bull run (reports/event-study-20261104.md)"}

# Tiers differ in selection threshold, size and use of adds, NOT in lowering the bar to negative-edge setups.
#   moderate: only the best-evidenced strategy (trend_day) at half size
#   high:     the same at double the moderate size
#   extreme:  trend_day at full size with the looser 1.0 ATR threshold (more trades) and one pyramid add per winner. The add
#             has ~0 expectancy (variance only): this tier trades more variance, not more edge. With the failed strategies
#             shelved, tiers differ only in size, threshold and adds.
TIERS = {
    "moderate": {"risk": {"trend_day": 0.5}, "min_move_atr": 1.5, "adds": 0, "add_risk": 0.0},
    "high": {"risk": {"trend_day": 1.0}, "min_move_atr": 1.5, "adds": 0, "add_risk": 0.0},
    "extreme": {"risk": {"trend_day": 1.0}, "min_move_atr": 1.0, "adds": 1, "add_risk": 1.0},
}
DEFAULT_TIER = "moderate"  # highest P(profit) in every Monte Carlo scenario; `high`/`extreme` are opt-in
# Runner management (replaces the scalp defaults for playbook trades): no partial, break-even at +1.5R, no trail,
# no pre-event exit (the backtests held through every release), time stop from the signal.
RUNNER = {"be_r": 1.5, "partial": False, "trail": False, "pre_event_exit": False}
ADD_AT_R = 1.5  # a pyramid add is allowed once the parent is +1.5R with its stop at break-even or better
SESSION_END_MIN = 1015  # 16:55 New York: a hold that would run into the 17:00 NY daily closure is not taken (the backtests
#                         excluded those trades because the position would sit through a market closure / gap)


def instrument_class(symbol):
    s = (symbol or "").upper()
    if s.startswith(("XAU", "GOLD")):  # Exness XAUUSDm, XM GOLDmicro
        return "gold"
    if s.startswith(("USTEC", "US100", "NAS100", "NDX")):
        return "index"
    return None


def normalise_tier(name):
    return name if name in TIERS else DEFAULT_TIER


def read_tier(path):
    """Tier from the root TIER flag file (moderate|high|extreme); default `moderate`."""
    try:
        with open(path, encoding="utf-8") as f:
            return normalise_tier(f.read().split()[0].strip().lower())
    except (OSError, IndexError):
        return DEFAULT_TIER


def cost_r(spread_px, sl_dist, slip_frac=0.5):
    """Round-trip cost (spread + slippage on entry and exit) as a fraction of the stop distance (R)."""
    return (spread_px * (1 + 2 * slip_frac)) / sl_dist if sl_dist > 0 else float("inf")


def _atr(h, l, c, i, n=14, inclusive=False):
    """Wilder ATR over the (up to 300) bars before bar i (or through it when inclusive)."""
    end = i + 1 if inclusive else i
    lo = max(0, end - 300)
    return float(ind.atr(h[lo:end], l[lo:end], c[lo:end], n)) if end - lo > n else float("nan")


def _base(name, side, i, t, c, a, sl, sl_kind, tier, time_stop_ts, age, why):
    e = float(c[i])
    risk = TIERS[tier]["risk"].get(name, 0.0)
    return {"strategy": name, "pattern": name, "side": side, "entry_ref": e, "sl": float(sl), "sl_kind": sl_kind,
            "sl_dist": abs(e - float(sl)), "tp_r": TP_R, "atr": float(a), "trigger_ts": int(t[i]), "age_bars": age,
            "id": f"pb-{name}-{int(t[i])}-{side}", "time_stop_ts": int(time_stop_ts), "mgmt": "runner",
            "grade": STRATEGIES[name]["grade"], "risk_mult": risk, "max_chase_atr": 1.0, "why": why}


def _trend_day(x, i, age, tier):
    p = STRATEGIES["trend_day"]["p"]
    if x["nym"][i] != p["enter_min"] - 5:
        return None
    j0 = i - (p["enter_min"] - 5 - 570) // 5
    if j0 < 0 or x["nym"][j0] != 570 or x["nyd"][j0] != x["nyd"][i] or x["t"][i] - x["t"][j0] != (i - j0) * 300:
        return None  # lead window missing or a data gap inside it
    a = _atr(x["h"], x["l"], x["c"], i, inclusive=True)
    if not a > 0:
        return None
    move = x["c"][j0 + p["lead_bars"] - 1] - x["o"][j0]
    if abs(move) < TIERS[tier]["min_move_atr"] * a:
        return None
    side = "buy" if move > 0 else "sell"
    e = x["c"][i]
    sl = e - p["stop_atr"] * a if side == "buy" else e + p["stop_atr"] * a
    ts = x["t"][i] + (p["exit_min"] - x["nym"][i]) * 60 - 60
    sig = _base("trend_day", side, i, x["t"], x["c"], a, sl, "atr", tier, ts, age,
                f"first 30 min {move / a:+.1f} ATR: trade the open's direction until 16:00 NY")
    sig["move_atr"] = abs(float(move)) / a  # lets research tools derive the stricter tiers from one replay
    return sig


def _impulse(x, i, age, tier, news):
    name = "news_drift" if news else "impulse_cont"
    p = STRATEGIES[name]["p"]
    if (x["nym"][i] in REL_MIN) != news:
        return None
    a = _atr(x["h"], x["l"], x["c"], i)  # ATR BEFORE the impulse bar
    if not a > 0:
        return None
    rng = x["h"][i] - x["l"][i]
    body = x["c"][i] - x["o"][i]
    if rng < p["thr"] * a or abs(body) < p["body"] * rng:
        return None
    if not news:  # cooldown: an earlier qualifying impulse within the last bars means this is the same event
        for j in range(max(0, i - p["cooldown"]), i):
            if x["h"][j] - x["l"][j] >= p["thr"] * a and abs(x["c"][j] - x["o"][j]) >= p["body"] * (x["h"][j] - x["l"][j]) \
                    and x["nym"][j] not in REL_MIN:
                return None
    side = "buy" if body > 0 else "sell"
    e = x["c"][i]
    if news:
        sl, kind = (e - p["stop_atr"] * a if side == "buy" else e + p["stop_atr"] * a), "atr"
    else:
        sl, kind = (x["l"][i] if side == "buy" else x["h"][i]), "bar"
        d = abs(e - sl)
        if d < p["min_stop_atr"] * a:
            sl = e - a * p["min_stop_atr"] if side == "buy" else e + a * p["min_stop_atr"]
        if abs(e - sl) > p["max_stop_atr"] * a:
            return None
    if x["nym"][i] < 1020 and x["nym"][i] + (p["hold"] + 2) * 5 - 1 > SESSION_END_MIN:
        return None  # the hold would cross the daily closure
    ts = x["t"][i] + (p["hold"] + 2) * 300 - 60
    why = (f"{'scheduled-release' if news else 'unscheduled'} impulse bar {rng / a:.1f} ATR: "
           f"continuation for {p['hold'] * 5} min")
    return _base(name, side, i, x["t"], x["c"], a, sl, kind, tier, ts, age, why)


def detect(symbol, bars, tier=DEFAULT_TIER, max_age=1, suspended=(), include_shelved=False):
    """Active playbook signals on the last closed M5 bars (trigger bar = last closed bar or `max_age` bars earlier).
    bars: structured array/dict with time/open/high/low/close (>= 60, ideally 320 closed bars). Newest first."""
    cls = instrument_class(symbol)
    tier = normalise_tier(tier)
    if cls is None or len(bars["close"]) < 60:
        return []
    keep = slice(-330, None)
    t = np.asarray(bars["time"][keep], np.int64)
    x = {"t": t, "o": np.asarray(bars["open"][keep], float), "h": np.asarray(bars["high"][keep], float),
         "l": np.asarray(bars["low"][keep], float), "c": np.asarray(bars["close"][keep], float),
         "nym": ss.local_minute(t, "ny"), "nyd": ss.local_day(t, "ny")}
    n, out = len(t), []
    for age in range(max_age + 1):
        i = n - 1 - age
        if i < 40:
            break
        for name, spec in STRATEGIES.items():
            if spec["cls"] != cls or name in suspended or not (
                    name in TIERS[tier]["risk"] or (include_shelved and name in SHELVED)):
                continue
            sig = (_trend_day(x, i, age, tier) if name == "trend_day"
                   else _impulse(x, i, age, tier, news=(name == "news_drift")))
            if sig:
                out.append(sig)
    return out


def add_ok(tier, side, entry, sl_cur, price, r_dist, adds_done):
    """Pyramid permission for a runner position: tier allows another add, price is >= +1.5R and the stop is already at
    break-even or better. The add's stop is the parent's current stop (so the parent stays risk-free).
    Returns {'sl', 'risk_mult'} or None."""
    td = TIERS[normalise_tier(tier)]
    sign = 1 if side == "buy" else -1
    if adds_done >= td["adds"] or r_dist <= 0 or (price - entry) * sign < ADD_AT_R * r_dist:
        return None
    if (sl_cur - entry) * sign < -1e-9 * max(1.0, abs(entry)):  # stop still on the losing side of entry
        return None
    return {"sl": sl_cur, "risk_mult": td["add_risk"]}


def suspended(exits, min_n=20, floor_r=-0.30):
    """Pre-registered kill switch. `exits`: journal exit records. A strategy is switched off once it has >= min_n closed
    live trades and its mean R is <= floor_r (the backtests promise >= 0; this level is >2 standard errors below)."""
    by = {}
    for e in exits:
        pat = str(e.get("pattern") or "")
        name = pat[3:] if pat.startswith("ai-") else pat
        if name in STRATEGIES and e.get("outcome_r") is not None:
            by.setdefault(name, []).append(float(e["outcome_r"]))
    return sorted(k for k, v in by.items() if len(v) >= min_n and sum(v) / len(v) <= floor_r)


def resolve(sig, entry, tier, risk_mult):
    """Map an active signal onto the live fill price. ATR-based stops are re-based on the actual entry so R stays what was
    tested; bar-extreme stops are absolute. Size is capped at the tier's cap for this strategy (never raised).
    Returns {'ok': True, 'sl', 'tp', 'risk_mult'} or {'ok': False, 'error'}."""
    tier = normalise_tier(tier)
    cap = TIERS[tier]["risk"].get(sig["strategy"], 0.0)
    if cap <= 0:
        return {"ok": False, "error": f"{sig['strategy']}_not_in_tier_{tier}"}
    if abs(entry - sig["entry_ref"]) > sig["max_chase_atr"] * sig["atr"]:
        return {"ok": False, "error": "price_moved_more_than_1_atr_since_the_trigger_bar"}
    buy = sig["side"] == "buy"
    sl = (entry - sig["sl_dist"] if buy else entry + sig["sl_dist"]) if sig["sl_kind"] == "atr" else sig["sl"]
    dist = abs(entry - sl)
    if dist <= 0 or (buy and sl >= entry) or (not buy and sl <= entry):
        return {"ok": False, "error": "sl_wrong_side_of_entry"}
    tp = entry + TP_R * dist if buy else entry - TP_R * dist
    return {"ok": True, "sl": sl, "tp": tp, "risk_mult": round(min(float(risk_mult), cap), 3), "sl_dist": dist}


def time_stop_due(rec, now_ts):
    """True when a runner position has reached the time stop written into its record at entry."""
    return bool(rec.get("mgmt") == "runner" and rec.get("time_stop_ts") and now_ts >= rec["time_stop_ts"])
