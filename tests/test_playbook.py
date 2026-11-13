"""Playbook (engine/playbook.py) and session clocks (engine/sessions.py): synthetic bars, no broker, no history files."""
from datetime import datetime, timezone

import numpy as np
import pytest

from engine import playbook as pb, sessions as ss

UTC = timezone.utc


def ts(y, m, d, hh=0, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=UTC).timestamp()


def make_bars(end_ts, n=700, steps=None, base_range=8.0, price=1000.0):
    """n contiguous M5 bars ending with the bar that STARTS at end_ts. steps: {index_from_end: close-to-close step}."""
    t = (end_ts - (n - 1 - np.arange(n)) * 300).astype(np.int64)
    step = np.where(np.arange(n) % 2 == 0, 0.5, -0.5)  # tiny deterministic wiggle: ATR stays ~ base_range
    for k, v in (steps or {}).items():
        step[n - 1 - k] = v
    c = price + np.cumsum(step)
    o = np.r_[price, c[:-1]]
    h = np.maximum(o, c) + base_range / 2
    l = np.minimum(o, c) - base_range / 2
    return {"time": t, "open": o, "high": h, "low": l, "close": c}


def window_steps(end_ts, per_bar, n=700):
    """Steps for the 09:30-09:55 NY bars (six bars) given the final bar start end_ts (10:55 NY)."""
    t = (end_ts - (n - 1 - np.arange(n)) * 300)
    nym = ss.local_minute(t, "ny")
    idx = [i for i in range(n) if 570 <= nym[i] <= 595]
    return {n - 1 - i: per_bar for i in idx[-6:]}


# ---------------------------------------------------------------- session clocks (DST without tzdata)
def test_ny_open_is_570_minutes_in_summer_and_winter():
    assert ss.local_minute([ts(2026, 7, 14, 13, 30)], "ny")[0] == 570  # EDT
    assert ss.local_minute([ts(2026, 11, 4, 14, 30)], "ny")[0] == 570  # EST (after 1 Nov)
    assert ss.local_minute([ts(2026, 3, 9, 13, 30)], "ny")[0] == 570  # EDT since 8 Mar 2026
    assert ss.local_minute([ts(2026, 3, 6, 14, 30)], "ny")[0] == 570  # still EST on 6 Mar


def test_us_and_uk_dst_edges():
    assert ss.ny_offset_h([ts(2026, 11, 1, 5, 59)])[0] == -4 and ss.ny_offset_h([ts(2026, 11, 1, 6, 1)])[0] == -5
    assert ss.lon_offset_h([ts(2026, 10, 25, 0, 30)])[0] == 1 and ss.lon_offset_h([ts(2026, 10, 25, 1, 30)])[0] == 0
    assert ss.lon_offset_h([ts(2026, 3, 29, 0, 59)])[0] == 0 and ss.lon_offset_h([ts(2026, 3, 29, 1, 1)])[0] == 1


def test_weekday_and_local_day():
    assert ss.weekday([ts(2026, 11, 4, 15)], "ny")[0] == 2  # Wednesday
    assert ss.local_day([ts(2026, 11, 4, 3)], "ny")[0] == ss.local_day([ts(2026, 11, 3, 20)], "ny")[0]  # 03:00 UTC = 22:00 NY the day before


# ---------------------------------------------------------------- trend_day
@pytest.mark.parametrize("y,m,d,hh", [(2026, 11, 4, 15), (2026, 7, 14, 14)])  # 10:55 NY in winter / summer (UTC hour)
def test_trend_day_buys_a_strong_open(y, m, d, hh):
    end = ts(y, m, d, hh, 55)
    bars = make_bars(end, steps=window_steps(end, 6.0))
    sigs = pb.detect("USTECm", bars, "high", max_age=0)
    assert [s["strategy"] for s in sigs] == ["trend_day"]
    s = sigs[0]
    assert s["side"] == "buy" and s["sl_kind"] == "atr" and s["mgmt"] == "runner" and s["grade"] == "B-"
    assert s["sl_dist"] == pytest.approx(3.0 * s["atr"]) and s["sl"] < s["entry_ref"]
    # time stop = 15:59 New York of the same day: 4 h 4 min after the 10:55 bar starts
    assert s["time_stop_ts"] == int(end + (960 - 655) * 60 - 60)


def test_trend_day_sells_a_weak_open_and_ignores_small_moves():
    end = ts(2026, 11, 4, 15, 55)
    assert pb.detect("USTECm", make_bars(end, steps=window_steps(end, -6.0)), "high", 0)[0]["side"] == "sell"
    assert pb.detect("USTECm", make_bars(end, steps=window_steps(end, 0.8)), "high", 0) == []


def test_trend_day_tier_threshold_and_age():
    end = ts(2026, 11, 4, 15, 55)
    weak = make_bars(end, steps=window_steps(end, 1.7))  # between 1.0 and 1.5 ATR in the first half hour
    ext = pb.detect("USTECm", weak, "extreme", 0)  # extreme: 1.0 ATR threshold
    assert ext and ext[0]["strategy"] == "trend_day"
    assert 1.0 <= 6 * 1.7 / ext[0]["atr"] < 1.5  # the fixture really sits between the two thresholds
    assert pb.detect("USTECm", weak, "high", 0) == []  # high needs 1.5 ATR
    nxt = make_bars(end + 300, steps={**{k + 1: v for k, v in window_steps(end, 6.0).items()}})
    assert pb.detect("USTECm", nxt, "high", max_age=0) == []  # the 10:55 trigger bar is now one bar old
    assert pb.detect("USTECm", nxt, "high", max_age=1)[0]["age_bars"] == 1


def test_trend_day_requires_contiguous_lead_window_and_index_class():
    end = ts(2026, 11, 4, 15, 55)
    bars = make_bars(end, steps=window_steps(end, 6.0))
    bars["time"] = bars["time"].copy()
    bars["time"][:-10] -= 300  # a data gap 10 bars before the end, inside the 09:30-10:55 span
    assert pb.detect("USTECm", bars, "high", 0) == []
    assert pb.detect("XAUUSDm", make_bars(end, steps=window_steps(end, 6.0)), "high", 0) == []  # gold: not a trend_day market


# ---------------------------------------------------------------- impulse_cont / news_drift
def test_impulse_cont_buys_a_big_bullish_unscheduled_bar_with_structural_stop():
    end = ts(2026, 11, 4, 16, 0)  # 11:00 NY: not a release minute, hold ends 14:xx NY, before the closure
    bars = make_bars(end, steps={0: 40.0})  # one bar of +40 on ~8 ATR-ish noise -> impulse
    assert pb.detect("USTECm", bars, "extreme", 0) == []  # shelved: in no tier
    sigs = pb.detect("USTECm", bars, "extreme", 0, include_shelved=True)
    assert [s["strategy"] for s in sigs] == ["impulse_cont"]
    s = sigs[0]
    assert s["side"] == "buy" and s["sl_kind"] == "bar" and s["sl"] == pytest.approx(bars["low"][-1])
    assert s["risk_mult"] == 0.0 and s["grade"] == "D" and "impulse_cont" in pb.SHELVED


def test_impulse_cont_not_on_release_minute_cooldown_or_late_hold():
    rel = ts(2026, 11, 4, 15, 0)  # 10:00 NY release minute (EST)
    assert [s["strategy"] for s in pb.detect("USTECm", make_bars(rel, steps={0: 40.0}), "extreme", 0, include_shelved=True)] == []
    end = ts(2026, 11, 4, 16, 0)
    two = make_bars(end, steps={0: 40.0, 3: 40.0})  # an earlier qualifying bar 3 bars before: same event
    assert pb.detect("USTECm", two, "extreme", 0, include_shelved=True) == []
    late = ts(2026, 11, 4, 20, 0)  # 15:00 NY: a 3 h hold would run through the 17:00 closure
    assert pb.detect("USTECm", make_bars(late, steps={0: 40.0}), "extreme", 0, include_shelved=True) == []


def test_news_drift_is_shelved_but_replayable_for_research():
    rel = ts(2026, 11, 4, 13, 30)  # 08:30 NY (winter)
    bars = make_bars(rel, steps={0: -40.0})
    for tier in ("moderate", "high", "extreme"):  # failed its 2017-2024 hold-out: in no tier, the desk never sees it
        assert pb.detect("XAUUSDm", bars, tier, 0) == []
    assert "news_drift" in pb.SHELVED and all("news_drift" not in t["risk"] for t in pb.TIERS.values())
    s = pb.detect("XAUUSDm", bars, "high", 0, include_shelved=True)  # research replays still produce it
    assert [x["strategy"] for x in s] == ["news_drift"] and s[0]["side"] == "sell" and s[0]["sl_kind"] == "atr"
    assert s[0]["sl_dist"] == pytest.approx(1.5 * s[0]["atr"]) and s[0]["grade"] == "D" and s[0]["risk_mult"] == 0.0
    kw = dict(include_shelved=True)
    assert pb.detect("USTECm", bars, "high", 0, **kw) == []  # index on the same bar: nothing
    assert pb.detect("XAUUSDm", make_bars(ts(2026, 11, 4, 14, 0), steps={0: -40.0}), "high", 0, **kw) == []  # 09:00 NY: not a release
    assert pb.detect("XAUUSDm", make_bars(ts(2026, 11, 4, 19, 0), steps={0: -40.0}), "high", 0, **kw) == []  # 14:00 NY: hold hits the closure


def test_tiers_select_strategies_and_size():
    rel = ts(2026, 11, 4, 13, 30)
    g = make_bars(rel, steps={0: 40.0})
    assert pb.detect("XAUUSDm", g, "moderate", 0) == [] and pb.detect("XAUUSDm", g, "extreme", 0) == []  # gold: no validated strategy
    end = ts(2026, 11, 4, 16, 0)
    assert pb.detect("USTECm", make_bars(end, steps={0: 40.0}), "moderate", 0) == []  # moderate: no impulse_cont
    assert pb.detect("USTECm", make_bars(end, steps={0: 40.0}), "nonsense", 0) == []  # unknown tier -> default (moderate)
    assert pb.detect("EURUSDm", g, "high", 0) == []


def test_suspended_strategies_are_skipped():
    end = ts(2026, 11, 4, 16, 0)
    bars = make_bars(end, steps={0: 40.0})
    assert pb.detect("USTECm", bars, "extreme", 0, suspended=("impulse_cont",), include_shelved=True) == []
    assert pb.detect("USTECm", bars, "extreme", 0, include_shelved=True)[0]["strategy"] == "impulse_cont"


def test_short_history_gives_nothing():
    assert pb.detect("USTECm", make_bars(ts(2026, 11, 4, 16, 0), n=30), "high", 0) == []


# ---------------------------------------------------------------- resolve / add_ok / suspended / time stop / cost
def _sig(**kw):
    base = {"strategy": "trend_day", "side": "buy", "entry_ref": 1000.0, "atr": 10.0, "sl": 970.0, "sl_kind": "atr",
            "sl_dist": 30.0, "max_chase_atr": 1.0}
    return {**base, **kw}


def test_resolve_rebases_atr_stop_on_the_fill_and_caps_size():
    r = pb.resolve(_sig(), 1002.0, "high", 1.0)
    assert r["ok"] and r["sl"] == 972.0 and r["tp"] == pytest.approx(1002.0 + 6 * 30.0) and r["risk_mult"] == 1.0
    assert pb.resolve(_sig(), 1000.0, "moderate", 1.0)["risk_mult"] == 0.5  # capped by the tier, not raised
    assert pb.resolve(_sig(), 1000.0, "moderate", 0.25)["risk_mult"] == 0.25  # may scale down
    assert pb.resolve(_sig(strategy="impulse_cont"), 1000.0, "high", 1.0)["error"].endswith("not_in_tier_high")
    assert "price_moved" in pb.resolve(_sig(), 1011.0, "high", 1.0)["error"]


def test_resolve_bar_stop_is_absolute_and_validated():
    s = _sig(sl_kind="bar", sl=995.0, sl_dist=5.0)
    assert pb.resolve(s, 1001.0, "extreme", 1.0)["sl"] == 995.0
    assert pb.resolve(_sig(sl_kind="bar", sl=1003.0), 1001.0, "extreme", 1.0)["error"] == "sl_wrong_side_of_entry"
    sell = _sig(side="sell", sl=1030.0)
    assert pb.resolve(sell, 998.0, "high", 1.0)["sl"] == 1028.0


def test_pyramid_only_in_extreme_after_1_5r_with_stop_at_break_even():
    args = ("buy", 1000.0, 1000.0, 1046.0, 30.0, 0)  # +1.53R, stop at entry
    assert pb.add_ok("high", *args) is None and pb.add_ok("moderate", *args) is None
    assert pb.add_ok("extreme", *args) == {"sl": 1000.0, "risk_mult": 1.0}
    assert pb.add_ok("extreme", "buy", 1000.0, 1000.0, 1040.0, 30.0, 0) is None  # only +1.33R
    assert pb.add_ok("extreme", "buy", 1000.0, 970.0, 1046.0, 30.0, 0) is None  # stop still below entry
    assert pb.add_ok("extreme", "buy", 1000.0, 1000.0, 1046.0, 30.0, 1) is None  # one add per position
    assert pb.add_ok("extreme", "sell", 1000.0, 1000.0, 954.0, 30.0, 0) == {"sl": 1000.0, "risk_mult": 1.0}
    assert pb.add_ok("extreme", "sell", 1000.0, 1010.0, 954.0, 30.0, 0) is None  # short stop above entry


def test_kill_switch_needs_enough_live_trades_and_clearly_bad_results():
    ex = lambda pat, r: {"pattern": pat, "outcome_r": r}
    bad = [ex("ai-trend_day", -0.5)] * 20
    assert pb.suspended(bad) == ["trend_day"]
    assert pb.suspended(bad[:19]) == []  # not enough evidence yet
    assert pb.suspended([ex("ai-trend_day", 0.4)] * 20) == []
    assert pb.suspended([ex("ai-trend_day", -0.1)] * 30) == []  # mildly negative: within noise of the +0.1R backtest
    assert pb.suspended([ex("ai-breakout", -2.0)] * 40) == []  # not a playbook strategy


def test_time_stop_only_for_runner_records():
    rec = {"mgmt": "runner", "time_stop_ts": 1000}
    assert pb.time_stop_due(rec, 1000) and not pb.time_stop_due(rec, 999)
    assert not pb.time_stop_due({"time_stop_ts": 1000}, 2000) and not pb.time_stop_due({"mgmt": "runner"}, 2000)


def test_cost_r_and_tier_file(tmp_path):
    assert pb.cost_r(1.92, 75.0) == pytest.approx(0.0512)  # spread + 0.5x slip in and out = 2 x spread
    assert pb.cost_r(0.24, 0.0) == float("inf")
    f = tmp_path / "TIER"
    assert pb.read_tier(f) == "moderate"  # missing -> default
    f.write_text("Extreme\n")
    assert pb.read_tier(f) == "extreme"
    f.write_text("yolo")
    assert pb.read_tier(f) == "moderate"
    f.write_text("")
    assert pb.read_tier(f) == "moderate"
