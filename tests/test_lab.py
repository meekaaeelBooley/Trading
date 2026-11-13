"""tools/lab.py trade simulator: exact fills against hand calculations (bid/ask, slippage, stop-first, BE, partial, shorts)."""
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import lab  # noqa: E402

SP = 0.2  # spread in price units


def mkt(bars):
    """bars: list of (open, high, low, close) bid prices."""
    a = np.array(bars, float)
    n = len(a)
    return SimpleNamespace(o=a[:, 0], h=a[:, 1], l=a[:, 2], c=a[:, 3], sp=np.full(n, SP), atr=np.full(n, 2.0), n=n,
                           t=np.arange(n) * 300)


def test_long_time_exit_pays_spread_and_slippage_both_ways():
    m = mkt([(100, 100.5, 99.5, 100)] * 6)
    r = lab.sim(m, 0, "buy", 95.0, last=5)  # stop far away, nothing happens
    entry = 100 + SP + 0.5 * SP  # buy at ask + slippage
    exit_ = 100 - 0.5 * SP  # sell at bid - slippage
    assert r["kind"] == "time" and r["r"] == pytest.approx((exit_ - entry) / (entry - 95.0))


def test_short_mirror_uses_ask_on_exit():
    m = mkt([(100, 100.5, 99.5, 100)] * 6)
    r = lab.sim(m, 0, "sell", 105.0, last=5)
    entry = 100 - 0.5 * SP  # sell at bid - slippage
    exit_ = 100 + SP + 0.5 * SP  # buy back at ask + slippage
    assert r["r"] == pytest.approx((entry - exit_) / (105.0 - entry))


def test_stop_beats_target_inside_one_bar_and_gaps_fill_at_the_open():
    wide = mkt([(100, 100.5, 99.5, 100), (100, 110, 90, 100)])  # one bar touches both the 1R target and the stop
    r = lab.sim(wide, 0, "buy", 98.0, tp_r=1.0, last=1)
    assert r["kind"] == "sl"
    gap = mkt([(100, 100.5, 99.5, 100), (90, 91, 89, 90)])  # opens below the stop: fills at the open, worse than -1R
    r = lab.sim(gap, 0, "buy", 98.0, last=1)
    assert r["kind"] == "sl" and r["r"] < -4.0


def test_target_fill_is_a_limit_without_slippage():
    m = mkt([(100, 100.5, 99.5, 100), (100, 103, 99.8, 102)])
    r = lab.sim(m, 0, "buy", 98.0, tp_r=1.0, last=1)
    entry = 100 + 1.5 * SP
    assert r["kind"] == "tp" and r["r"] == pytest.approx(1.0)  # exactly +1R: target = entry + 1 x risk, no slippage


def test_break_even_arms_only_from_the_NEXT_bar_and_never_looks_ahead():
    # bar1 reaches +2R but BE only applies from bar2; bar2 falls back through entry -> stopped at break-even (~0R)
    m = mkt([(100, 100.5, 99.5, 100), (100, 104.5, 99.9, 104), (104, 104, 99, 99.5)])
    r = lab.sim(m, 0, "buy", 98.0, be_r=1.5, last=2)
    entry = 100 + 1.5 * SP
    assert r["kind"] == "sl" and r["r"] == pytest.approx((min(entry, 104) - 0.5 * SP - entry) / (entry - 98.0))
    no_be = lab.sim(m, 0, "buy", 98.0, last=2)  # without BE the same path ends at the time exit, a loss on the way back
    assert no_be["kind"] == "time"


def test_partial_banks_half_at_the_level_and_runs_the_rest():
    m = mkt([(100, 100.5, 99.5, 100), (100, 102.2, 99.9, 102), (102, 102.5, 101.8, 102)])
    full = lab.sim(m, 0, "buy", 98.0, last=2)
    part = lab.sim(m, 0, "buy", 98.0, last=2, partial=(0.7, 0.5))
    risk = 100 + 1.5 * SP - 98.0
    assert part["r"] == pytest.approx(0.5 * 0.7 + 0.5 * full["r"])
    assert risk > 0


def test_invalid_stop_returns_none():
    m = mkt([(100, 100.5, 99.5, 100)] * 3)
    assert lab.sim(m, 0, "buy", 101.0, last=2) is None
    assert lab.sim(m, 0, "sell", 99.0, last=2) is None


def test_run_signals_control_is_the_opposite_direction_with_mirrored_stop():
    m = mkt([(100, 100.5, 99.5, 100)] * 8)
    out = lab.run_signals(m, [dict(i=0, side="buy", sl=98.0, last=6)], one_at_a_time=True)
    assert len(out) == 1 and np.isfinite(out[0]["ctrl"])
    mirror = lab.sim(m, 0, "sell", 102.0, last=6)
    assert out[0]["ctrl"] == pytest.approx(mirror["r"])


def test_sessions_clock_agrees_with_lab_market_fields():
    # lab.Mkt needs data files; the clock functions it relies on are covered in test_playbook. Here: stats() sanity.
    s = lab.stats([{"r": 1.0, "ctrl": 0.0}] * 10 + [{"r": -1.0, "ctrl": 0.0}] * 10)
    assert s["n"] == 20 and s["E"] == pytest.approx(0.0) and s["win"] == pytest.approx(0.5) and s["pf"] == pytest.approx(1.0)
