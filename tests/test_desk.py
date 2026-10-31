import numpy as np

from engine import gates
from engine.scout import scout

DT = np.dtype([("open", float), ("high", float), ("low", float), ("close", float)])


def bars(rows):
    return np.array([tuple(r) for r in rows], dtype=DT)


def flat(n=30, px=100.0, rng=0.5):
    return [(px, px + rng / 2, px - rng / 2, px)] * n


def test_quiet_tape_is_silent():
    assert scout(bars(flat()), atr=0.5) == []


def test_impulse_and_range_break_up():
    rows = flat() + [(100.0, 102.0, 99.9, 101.9)]
    r = scout(bars(rows), atr=0.5)
    assert "impulse_up" in r and "range_break_up" in r and "sweep_high" not in r


def test_sweep_high_is_wick_through_with_close_back_inside():
    rows = flat() + [(100.0, 100.8, 99.9, 100.1)]  # prior high is 100.25
    r = scout(bars(rows), atr=1.0)
    assert r == ["sweep_high"]


def test_sweep_low_and_break_down():
    rows = flat() + [(100.0, 100.1, 98.0, 98.1)]
    r = scout(bars(rows), atr=0.5)
    assert "impulse_down" in r and "range_break_down" in r and "sweep_low" not in r
    rows = flat() + [(100.0, 100.1, 99.2, 99.9)]
    assert scout(bars(rows), atr=1.0) == ["sweep_low"]


def test_too_few_bars_or_zero_atr():
    assert scout(bars(flat(10)), atr=1.0) == []
    assert scout(bars(flat()), atr=0) == []


def _ctx(**kw):
    base = dict(entry_ok=True, phase="ACTIVE", kill=False, halt=False, stopped=False, stop_reason="", demo_ok=True,
                market_open=True, data_fresh=True, open_positions=0, max_positions=3, trades=0, max_trades=150,
                consec_losses=0, max_consec=6, day_pct=0, daily_stop=12, news_blocked=False, news_reason="",
                spread=10, spread_max=500, atr=1, atr_min=0.5, atr_max=5, risk_flag="")
    return {**base, **kw}


def test_desk_exposure_gate_is_account_wide_and_not_overridable():
    assert gates.blockers(_ctx()) == []
    assert gates.blockers(_ctx(desk_max=4, desk_open=3)) == []
    blk = gates.blockers(_ctx(desk_max=4, desk_open=4))
    assert blk == ["desk_exposure"]
    ovr = gates.apply_overrides(_ctx(desk_max=4, desk_open=4), list(gates.OVERRIDABLE))
    assert gates.blockers(ovr) == ["desk_exposure"]
