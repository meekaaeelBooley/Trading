"""Tests for the engine extensions: exits, partial TP, risk flag, filters, mining, health, report, backtest and a
fake-MT5 harness for reconcile/manage/set_risk_flag."""
import json
from types import SimpleNamespace as NS

import numpy as np
import pytest

from engine import (backtest as bt, exits, filters, gates, health, journal, news, report, review, risk,
                    run as runmod)
from engine.defaults import DEFAULTS

CFG = {**DEFAULTS, **json.load(open("config.json"))}


# ---- exits
def test_exit_reason_and_excursions():
    assert exits.exit_reason("tp", 2.0) == "tp"
    assert exits.exit_reason("sl", -1.0) == "sl"
    assert exits.exit_reason("sl", 0.0) == "be"
    assert exits.exit_reason("sl", 0.8) == "trail"
    assert exits.exit_reason("other", 0.3) == "flat"
    assert exits.exit_reason("other", 0.3, "pre_event") == "pre_event"
    bars = [{"time": 100, "high": 103.0, "low": 99.5}, {"time": 160, "high": 101.0, "low": 98.0},
            {"time": 9999, "high": 500.0, "low": 1.0}]
    assert exits.excursions(bars, "buy", 100.0, 1.0, 100, 200) == (3.0, 2.0)
    assert exits.excursions(bars, "sell", 100.0, 2.0, 100, 200) == (1.0, 1.5)
    assert exits.excursions([], "buy", 100, 1, 0, 1) == (None, None)


# ---- partial profit
def test_partial_lots_and_due():
    assert risk.partial_close_lots(0.10, 0.5, 0.01, 0.01) == 0.05
    assert risk.partial_close_lots(0.01, 0.5, 0.01, 0.01) == 0.0  # cannot split the minimum lot
    assert risk.partial_close_lots(0.03, 0.5, 0.01, 0.01) == 0.01
    assert risk.partial_close_lots(0.02, 0.5, 0.01, 0.01) == 0.01
    assert risk.partial_due("buy", 100, 101.0, 1.0, 1.0)
    assert not risk.partial_due("buy", 100, 100.9, 1.0, 1.0)
    assert risk.partial_due("sell", 100, 98.9, 1.0, 1.0)


# ---- risk flag gate
def _gate_ctx(**kw):
    c = dict(entry_ok=True, phase="ACTIVE", kill=False, halt=False, stopped=False, stop_reason="", demo_ok=True,
             market_open=True, data_fresh=True, open_positions=0, max_positions=1, trades=0, max_trades=4,
             consec_losses=0, max_consec=2, day_pct=0, daily_stop=6, news_blocked=False, news_reason="",
             spread=100, spread_max=200, atr=50, atr_min=35, atr_max=100)
    c.update(kw)
    return c


def test_risk_flag_gate():
    assert gates.blockers(_gate_ctx()) == []
    assert gates.blockers(_gate_ctx(risk_flag="fed-emergency")) == ["risk_flag:fed-emergency"]


# ---- news.next_event
def test_next_event(tmp_path):
    p = tmp_path / "cal.json"
    p.write_text(json.dumps({"fetched": 0, "events": [{"title": "CPI", "ts": 1000}, {"title": "FOMC", "ts": 9000}]}))
    assert news.next_event(str(p), 900, 5) == {"title": "CPI", "in_s": 100}
    assert news.next_event(str(p), 1050, 5) == {"title": "CPI", "in_s": -50}  # just released
    assert news.next_event(str(p), 2000, 5) is None
    assert news.next_event(str(tmp_path / "missing.json"), 0) is None


# ---- filters
def test_filters_match(tmp_path):
    p = tmp_path / "f.json"
    p.write_text(json.dumps([{"rule": {"pattern": "pin", "hour": 10}, "n": 40}, {"rule": {}}, "junk"]))
    rules = filters.load(str(p))
    assert len(rules) == 1
    f = filters.features("buy", "pin", "long", 50, 120, 10)
    assert f["atr_band"] == "atr45-70" and f["spread_band"] == "spr<130"
    assert filters.match(rules, f) == "pattern=pin,hour=10"
    assert filters.match(rules, filters.features("buy", "pin", "long", 50, 120, 11)) is None
    assert filters.load(str(tmp_path / "nope.json")) == []


# ---- review: CI, interactions, candidate filters
def _ex(r, pattern="pin", hour=10, side="buy"):
    return {"outcome_r": r, "side": side, "pattern": pattern, "bias": "long", "hour": hour, "atr": 50, "spread": 100}


def test_ci_is_deterministic_and_brackets_mean():
    rs = [1.0, -1.0, 2.0, -1.0, 0.5, -0.5, 1.5, -1.0]
    lo, hi = review.ci(rs)
    assert lo <= sum(rs) / len(rs) <= hi and review.ci(rs) == (lo, hi)
    assert review.ci([1.0]) is None


def test_candidate_filters_need_robust_evidence():
    losers = [_ex(-1.0 + (0.1 if i % 5 == 0 else 0), "pin", 10) for i in range(40)]
    winners = [_ex(1.5 if i % 3 else -0.5, "engulfing", 14) for i in range(40)]
    cand = review.candidate_filters(losers + winners)
    rules = [c["rule"] for c in cand]
    assert {"pattern": "pin"} in rules and {"hour": 10} in rules
    assert not any(r.get("pattern") == "engulfing" for r in rules)
    assert not any(len(r) == 2 and r.get("pattern") == "pin" and r.get("hour") == 10 for r in rules)  # subsumed
    assert review.candidate_filters(losers[:20]) == []  # n < 30
    # losing only in the first half: second half positive -> rejected
    mixed = [_ex(-1.0, "pin", 10) for _ in range(20)] + [_ex(0.5, "pin", 10) for _ in range(20)]
    assert review.candidate_filters(mixed) == []


def test_analyze_interactions():
    ex = [_ex(-1.0, "pin", 10) for _ in range(9)] + [_ex(2.0, "engulfing", 14) for _ in range(9)]
    a = review.analyze(ex)
    assert a["interactions"]["hour=10&pattern=pin"]["exp"] == -1.0
    assert any(f.startswith("hour=10&pattern=pin") for f in a["flags"])


# ---- health
def test_health_warnings():
    recs = [{"type": "trade", "slippage": 80, "spread": 190} for _ in range(6)]
    recs += [{"type": "error"} for _ in range(3)]
    w = health.check(recs, 200)
    assert any(x.startswith("slippage") for x in w) and any(x.startswith("spread") for x in w)
    assert any(x.startswith("errors") for x in w)
    assert health.check([{"type": "trade", "slippage": 2, "spread": 100} for _ in range(6)], 200) == []
    wins = [{"type": "exit", "outcome_r": 2.0} for _ in range(20)] + [{"type": "exit", "outcome_r": -1.0} for _ in range(20)]
    assert any("drift" in x for x in health.check(wins, 200))


# ---- report
def test_run_report(tmp_path):
    p = str(tmp_path / "j.jsonl")
    journal.append(p, {"type": "exit", "ticket": 1, "outcome_r": 2.0, "side": "buy", "pattern": "pin"})
    journal.append(p, {"type": "pass", "reason": "headline"})
    run = {"id": 5, "start_ts": 0, "trades": 1, "consec_losses": 0, "stop_reason": "max_trades",
           "gate_counts": {"phase": 3, "spread": 1}}
    md = report.build(run, journal.read(p), 3.0, ["slippage: x"])
    assert "Run 5" in md and "phase=3" in md and "headline" in md and "slippage: x" in md


# ---- run lifecycle lives in the engine
def test_roll_state_baselines():
    from datetime import datetime, timezone
    st = {}
    runmod.roll_state(st, 1000, datetime(2026, 10, 19, 12, tzinfo=timezone.utc))
    runmod.roll_state(st, 900, datetime(2026, 10, 19, 13, tzinfo=timezone.utc))
    assert st["day"]["start_equity"] == 1000 and st["week"]["start_equity"] == 1000
    runmod.roll_state(st, 800, datetime(2026, 10, 20, 12, tzinfo=timezone.utc))
    assert st["day"]["start_equity"] == 800 and st["week"]["start_equity"] == 1000


# ---- backtester trade simulation on hand-built M1 bars
T0 = 1_800_000_000 // 300 * 300


def _m1(prices, spread=0.0):
    k = len(prices) - 1
    o = np.array(prices[:-1], float)
    c = np.array(prices[1:], float)
    return {"time": T0 + 60 * np.arange(k), "open": o, "close": c,
            "high": np.maximum(o, c), "low": np.minimum(o, c)}


def _sim_data(prices):
    n15 = 64
    m15 = {"time": T0 - 900 * 20 + 900 * np.arange(n15), "high": np.full(n15, 100.5), "low": np.full(n15, 99.5),
           "open": np.full(n15, 100.0), "close": np.full(n15, 100.0)}
    return {"point": 0.01, "m1": _m1(prices), "m15": m15}, m15["time"] + 900


def _trade(prices, side="buy", sl=99.0, sim_over=None, cfg_over=None, tweak=None):
    data, tcl = _sim_data(prices)
    if tweak:
        tweak(data["m1"])
    sim = {**bt.SIM, "spread_points": 0.0, "slip_points": 0.0, "events": [], **(sim_over or {})}
    cfg = {**CFG, **(cfg_over or {})}
    sig = {"side": side, "sl": sl, "atr": 1.0}
    return bt._trade(data["m1"], 60, data["m15"], cfg, sim, sig, 0, T0 + 10 ** 6, 0.01, lambda idx: 1.0, tcl)


UP = [100 + 0.12 * k for k in range(40)]
DOWN = [100 - 0.12 * k for k in range(40)]


def test_backtest_trade_tp_with_and_without_partial():
    full = _trade(UP, cfg_over={"partial_tp": False})
    assert full["exit_reason"] == "tp" and full["outcome_r"] == pytest.approx(2.0, abs=0.01) and not full["partial"]
    part = _trade(UP, cfg_over={"partial_tp": True})
    # half banked at ~+1R (first 5-min checkpoint past 1R), runner to TP: between 1.5R and 2R total
    assert part["partial"] and 1.4 <= part["outcome_r"] <= 1.75 and part["exit_reason"] == "tp"


def test_backtest_trade_sl_and_gap():
    r = _trade(DOWN)
    assert r["exit_reason"] == "sl" and r["outcome_r"] == pytest.approx(-1.0, abs=0.01)
    def gap_down(m1):  # bar 2 opens at 97, through the 99 stop
        m1["open"][2], m1["low"][2] = 97.0, 97.0

    gap = _trade([100, 100, 100, 97.0, 97.0, 97.0], tweak=gap_down)  # filled at the open, not at the stop
    assert gap["outcome_r"] == pytest.approx(-3.0, abs=0.01)


def test_backtest_trade_short_and_spread_cost():
    s = _trade([100 - 0.12 * k for k in range(40)], side="sell", sl=101.0, cfg_over={"partial_tp": False})
    assert s["exit_reason"] == "tp" and s["outcome_r"] == pytest.approx(2.0, abs=0.01)
    cheap = _trade(UP, cfg_over={"partial_tp": False})
    costly = _trade(UP, cfg_over={"partial_tp": False}, sim_over={"spread_points": 20.0})
    # buying at the ask widens the stop distance, so the 2R target is further away and takes longer to reach
    assert costly["dur_min"] > cheap["dur_min"] and costly["outcome_r"] == pytest.approx(2.0, abs=0.01)


def test_backtest_trade_pre_event_and_run_end():
    ev = _trade([100 + 0.12 * k for k in range(40)], cfg_over={"partial_tp": False},
                sim_over={"events": [T0 + 11 * 60]})
    assert ev["exit_reason"] == "pre_event" and 0.5 < ev["outcome_r"] < 1.5
    flat = _trade([100, 100.2, 100.3, 100.2, 100.3, 100.2, 100.3], sim_over={})
    assert flat is None  # data ends while still open: dropped, never invented
    data, tcl = _sim_data([100, 100.2, 100.3, 100.2, 100.3, 100.2, 100.3])
    sim = {**bt.SIM, "spread_points": 0.0, "slip_points": 0.0}
    r = bt._trade(data["m1"], 60, data["m15"], CFG, sim, {"side": "buy", "sl": 99.0, "atr": 1.0}, 0, T0 + 120, 0.01,
                  lambda i: 1.0, tcl)
    assert r["exit_reason"] == "flat" and r["dur_min"] == 2


# ---- backtester end to end on synthetic data (deterministic, schema-correct)
def _synthetic(days=45, seed=3):
    rng = np.random.default_rng(seed)
    n = days * 1440
    drift = np.repeat(rng.choice([-0.4, 0.4], size=n // 720 + 1), 720)[:n]
    steps = drift + rng.normal(0, 9.0, n)
    close = 20000 + np.cumsum(steps)
    open_ = np.concatenate([[close[0]], close[:-1]])
    high = np.maximum(open_, close) + np.abs(rng.normal(0, 2.0, n))
    low = np.minimum(open_, close) - np.abs(rng.normal(0, 2.0, n))
    t0 = 1_760_000_000 // 14400 * 14400
    t = t0 + 60 * np.arange(n)

    def agg(k):
        m = n // k * k
        sl = lambda a: a[:m].reshape(-1, k)
        return {"time": t[:m:k], "open": sl(open_)[:, 0], "close": sl(close)[:, -1],
                "high": sl(high).max(1), "low": sl(low).min(1)}

    return {"point": 0.01, "m1": {"time": t, "open": open_, "high": high, "low": low, "close": close},
            "m15": agg(15), "h1": agg(60), "h4": agg(240)}


def test_backtest_end_to_end_deterministic():
    data = _synthetic()
    cfg = dict(CFG, atr_min=1, atr_max=1000)
    sim = {"run_starts": "auto", "spread_points": 50.0, "slip_points": 5.0}
    a = bt.run(data, cfg, sim)
    b = bt.run(data, cfg, sim)
    assert a == b and len(a) > 0
    for e in a:
        assert e["type"] == "exit" and e["side"] in ("buy", "sell") and e["pattern"] in ("pin", "engulfing")
        assert -10 < e["outcome_r"] <= cfg["tp_r"] + 0.05 and e["mfe_r"] >= 0 and e["mae_r"] >= 0
        assert e["exit_reason"] in ("tp", "sl", "be", "trail", "flat", "pre_event")
    st = bt.summarise(a, cfg["risk_pct"])
    assert st["n"] == len(a) and st["ci95"] is not None
    tr, te = bt.split(a, 0.6)
    assert len(tr) + len(te) == len(a)
    rows = bt.sweep(data, cfg, {"partial_tp": [True, False]}, sim)
    assert len(rows) == 2 and "| params |" in bt.markdown("t", rows)


def test_backtest_respects_run_cap_and_trade_limit():
    data = _synthetic()
    cfg = dict(CFG, atr_min=1, atr_max=1000, max_trades_session=1)
    ex = bt.run(data, cfg, {"run_starts": "auto", "spread_points": 50.0})
    by_run = {}
    for e in ex:
        by_run.setdefault(e["t"] // (cfg["run_max_minutes"] * 60), []).append(e)
    assert all(len(v) <= 2 for v in by_run.values())  # <=1 per run; two runs can straddle one time bucket


# ---- fake MT5 harness: reconcile / manage / set_risk_flag against the real server module
class FakeMT5:
    DEAL_ENTRY_IN, DEAL_ENTRY_OUT = 0, 1
    DEAL_REASON_TP, DEAL_REASON_SL = 3, 4
    POSITION_TYPE_BUY = 0
    TRADE_RETCODE_DONE = 10009
    TRADE_ACTION_DEAL, TRADE_ACTION_SLTP = 1, 6
    ORDER_TYPE_BUY, ORDER_TYPE_SELL = 0, 1
    ORDER_FILLING_IOC, ORDER_FILLING_FOK, ORDER_FILLING_RETURN = 1, 0, 2
    TIMEFRAME_M1 = 1

    def __init__(self):
        self.positions, self.deals, self.sent = [], [], []

    def positions_get(self, symbol=None):
        return self.positions

    def history_deals_get(self, position=None):
        return self.deals

    def symbol_info_tick(self, s):
        return NS(time=2_000_000, bid=100.0, ask=100.1)

    def copy_rates_from_pos(self, *a):
        return [{"time": 1_999_200, "high": 103.0, "low": 99.0}]

    def order_check(self, req):
        return NS(retcode=0)

    def order_send(self, req):
        self.sent.append(req)
        return NS(retcode=self.TRADE_RETCODE_DONE)


@pytest.fixture
def srv(tmp_path, monkeypatch):
    import mt5_server as s
    fake = FakeMT5()
    monkeypatch.setattr(s, "mt5", fake)
    monkeypatch.setattr(s, "STATE_DIR", tmp_path)
    monkeypatch.setattr(s, "STATE_F", tmp_path / "state.json")
    monkeypatch.setattr(s, "JOURNAL_F", tmp_path / "journal.jsonl")
    monkeypatch.setattr(s, "CAL_F", tmp_path / "cal.json")
    monkeypatch.setattr(s, "LESSONS_F", tmp_path / "lessons.md")
    return s, fake


def test_reconcile_sums_partial_and_final_deals(srv):
    s, fake = srv
    c = s.cfg()
    fake.deals = [NS(entry=0, time=1_999_100, profit=0, commission=-1.0, swap=0, price=100.0, reason=0),
                  NS(entry=1, time=1_999_400, profit=150.0, commission=-0.5, swap=0, price=101.0, reason=0),
                  NS(entry=1, time=1_999_900, profit=100.0, commission=-0.5, swap=0, price=102.0, reason=3)]
    state = {"positions": {"7": {"side": "buy", "entry": 100.0, "r_dist": 1.0, "risk_money": 200.0,
                                 "signal_id": "x", "partial_done": True, "pattern": "pin", "bias": "long",
                                 "atr": 50, "spread": 100, "hour": 10, "regime": "trend"}},
             "run": {"consec_losses": 1}}
    closed = s.reconcile(state, c)
    assert closed == [{"ticket": 7, "r": 1.25, "why": "tp", "style": "scalp"}] and state["positions"] == {}
    assert state["run"]["consec_losses"] == 0  # a real win resets the streak
    ex = [r for r in journal.read(str(s.JOURNAL_F)) if r["type"] == "exit"][0]
    assert ex["partial"] is True and ex["regime"] == "trend" and ex["mfe_r"] == 3.0


def test_manage_partial_then_breakeven(srv):
    s, fake = srv
    c = s.cfg()
    fake.positions = [NS(ticket=7, symbol="USTECm", magic=c["magic"], type=0, volume=0.10, price_open=100.0,
                         sl=99.0, tp=102.0, profit=100.0)]
    state = {"positions": {"7": {"side": "buy", "entry": 100.0, "r_dist": 1.0, "risk_money": 200.0}}}
    closed_arr = np.zeros(5, dtype=[("low", float), ("high", float)])
    closed_arr["low"], closed_arr["high"] = 100.0, 101.5
    snap = {"tick": NS(bid=101.2, ask=101.3), "closed": closed_arr, "atr": 1.0,
            "info": NS(volume_min=0.01, volume_step=0.01, digits=2)}
    acts = s.manage(state, c, snap, 0)
    assert any(a.get("partial") == 7 and a["ok"] and a["lots"] == 0.05 for a in acts)
    assert state["positions"]["7"]["partial_done"] is True
    assert any(a.get("sl") == 7 and a["to"] == 100.0 for a in acts)  # break-even follows
    again = s.manage(state, c, snap, 0)
    assert not any("partial" in a for a in again)  # only once


def test_manage_pre_event_exit_only_when_in_profit(srv):
    s, fake = srv
    c = s.cfg()
    s.CAL_F.write_text(json.dumps({"fetched": 0, "events": [{"title": "CPI", "ts": 1000}]}))
    mk = lambda profit: [NS(ticket=7, symbol="USTECm", magic=c["magic"], type=0, volume=0.10, price_open=100.0,
                            sl=99.0, tp=102.0, profit=profit)]
    arr = np.zeros(5, dtype=[("low", float), ("high", float)])
    snap = {"tick": NS(bid=100.5, ask=100.6), "closed": arr, "atr": 1.0,
            "info": NS(volume_min=0.01, volume_step=0.01, digits=2)}
    state = {"positions": {"7": {"side": "buy", "entry": 100.0, "r_dist": 1.0, "risk_money": 200.0}}}
    fake.positions = mk(-50.0)
    assert not any("pre_event_exit" in a for a in s.manage(state, c, snap, 800))  # loser keeps its SL
    fake.positions = mk(50.0)
    acts = s.manage(state, c, snap, 800)  # event in 200 s <= 300 s window
    assert any(a.get("pre_event_exit") == 7 and a["ok"] for a in acts)
    assert state["positions"]["7"]["closed_by"] == "pre_event"
    state["positions"]["7"].pop("closed_by")
    assert not any("pre_event_exit" in a for a in s.manage(state, c, snap, 100))  # event 900 s away


def test_set_risk_flag_blocks_then_clears(srv):
    s, fake = srv
    assert s.set_risk_flag("block", "x")["error"] == "no_active_run"
    s.save_state({"positions": {}, "run": {"start_ts": 1.0, "ended": False}})
    assert s.set_risk_flag("maybe")["ok"] is False
    r = s.set_risk_flag("block", "fed: emergency", minutes=500, regime="news")
    assert r["ok"] and r["regime"] == "news"
    run = s.load_state()["run"]
    assert run["risk_flag"]["level"] == "block" and ":" not in run["risk_flag"]["reason"]
    assert run["risk_flag"]["until_ts"] - run["last_headline_ts"] <= 3600 + 1  # capped at 60 min
    s.set_risk_flag("ok")
    assert s.load_state()["run"]["risk_flag"] == {"level": "ok"}


def test_set_lessons_validation(srv):
    s, _ = srv
    assert s.set_lessons(["no prefix"])["ok"] is False
    assert s.set_lessons(["[n=9, ?] x"] * 26)["ok"] is False
    assert s.set_lessons(["[n=25, E=-0.4R] skip pin at 10h"])["ok"] is True
    assert s.LESSONS_F.read_text().startswith("[n=25")


def test_deep_review_reports_candidates_without_applying(srv, monkeypatch, tmp_path):
    s, _ = srv
    monkeypatch.setattr(s, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(s, "FILTERS_F", tmp_path / "filters.json")
    assert s.deep_review()["n"] == 0
    for i in range(40):
        journal.append(str(s.JOURNAL_F), {"type": "exit", **_ex(-1.0, "pin", 10), "ticket": i})
    for i in range(40):
        journal.append(str(s.JOURNAL_F), {"type": "exit", **_ex(1.5 if i % 3 else -0.5, "engulfing", 14), "ticket": 100 + i})
    out = s.deep_review()
    assert {"pattern": "pin"} in [c["rule"] for c in out["candidate_filters"]]
    assert "hour=10&pattern=pin" in out["interactions_flagged"] and out["interactions_flagged"]["hour=10&pattern=pin"]["ci"]
    assert not (tmp_path / "filters.json").exists()  # never applied by the tool
    assert (tmp_path / "reports").is_dir()
