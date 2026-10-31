"""Support/resistance, smart-money concepts, swing scoring and the swing book rules in the server."""
from datetime import datetime, timezone
from types import SimpleNamespace as NS

import numpy as np

from engine import gates, levels, risk, smc, swing
from engine.defaults import DEFAULTS
from engine.clock import SAST

C = dict(DEFAULTS)
DT = np.dtype([("time", np.int64), ("open", float), ("high", float), ("low", float), ("close", float),
               ("tick_volume", np.int64)])


def zig(points, per=6, wick=0.2):
    """Bars walking straight between turning points (per bars per leg)."""
    closes = [points[0]]
    for a, b in zip(points, points[1:]):
        closes += list(np.linspace(a, b, per + 1)[1:])
    rows = []
    for i, cl in enumerate(closes):
        op = closes[i - 1] if i else cl
        rows.append((i * 900, op, max(op, cl) + wick, min(op, cl) - wick, cl, 100))
    return np.array(rows, dtype=DT)


def test_swing_points_find_pivots():
    b = zig([100, 110, 100, 110, 100], per=6)
    hs, ls = levels.swing_points(b["high"], b["low"], 3)
    assert [round(p) for _, p in hs] == [110, 110] and [round(p) for _, p in ls] == [100]


def test_zones_cluster_repeated_turns_and_classify_by_price():
    b = zig([100, 110, 100.3, 110.2, 100.1, 109.9, 104], per=6)
    z = levels.zones(b["high"], b["low"], atr=1.5)
    assert len(z) == 2 and all(x["touches"] >= 2 for x in z)
    merged = levels.build([("h1", b["high"], b["low"], 1.5)], 104.0, 1.5)
    assert {m["kind"] for m in merged} == {"support", "resistance"}
    assert merged[0]["dist_atr"] <= merged[-1]["dist_atr"]
    assert levels.nearest(merged, "resistance", 1)[0]["lo"] > 104


def test_round_levels_scale_with_price():
    assert levels.round_levels(4012.0, 1) == {"above": [4050.0], "below": [4000.0]}
    assert levels.round_levels(25120.0, 1)["above"] == [25500.0]


def test_rejection_and_role_flip():
    zone = {"lo": 100.0, "hi": 101.0}
    h, l, c = [103, 103, 101.5], [101.5, 100.6, 100.4], [102, 101.8, 101.4]
    assert levels.rejection(h, l, c, zone, "buy", 3)  # wicked into the zone, closed above it
    assert not levels.rejection(h, l, c, zone, "sell", 3)
    closes = [98] * 6 + [103] * 6 + [101.5]  # was resistance (below), broken up, now retesting from above
    assert levels.broken_retest(closes, zone, "buy")
    assert not levels.broken_retest([103] * 13, zone, "buy")


def test_structure_bos_then_choch_and_order_block():
    b = zig([100, 110, 104, 116, 108, 98], per=6, wick=0.3)
    o, h, l, c = (b[k] for k in ("open", "high", "low", "close"))
    trend, events, _, _ = smc.structure(o, h, l, c, 3)
    kinds = [(e["kind"], e["dir"]) for e in events]
    assert ("BOS", "bull") in kinds and ("CHoCH", "bear") in kinds and trend == "bear"
    obs = smc.order_blocks(o, h, l, c, 2.0, events)
    assert any(x["dir"] == "bear" and x["lo"] > 110 for x in obs)  # last up candle before the sell-off that broke structure


def test_bullish_order_block_is_last_down_candle_before_displacement():
    rows = [(99.0, 99.6, 98.8, 99.4), (99.4, 100.2, 99.3, 100.0), (100.0, 101.0, 99.9, 100.8),  # swing high 101
            (100.8, 100.9, 100.0, 100.2), (100.2, 100.4, 99.4, 99.6)]
    rows += [(99.6, 99.8, 98.9, 99.0), (99.0, 99.2, 98.0, 98.4)]              # sell-off, last down candle = OB
    rows += [(98.4, 103.0, 98.3, 102.8), (102.8, 106.0, 102.5, 105.5)]        # displacement up through 101 (BOS)
    rows += [(105.5, 106.2, 104.8, 105.8), (105.8, 106.5, 105.2, 106.0), (106.0, 106.4, 105.5, 105.9),
             (105.9, 106.3, 105.4, 106.1), (106.1, 106.6, 105.7, 106.3)]
    b = np.array(rows, dtype=[("open", float), ("high", float), ("low", float), ("close", float)])
    o, h, l, c = (b[k] for k in ("open", "high", "low", "close"))
    trend, events, _, _ = smc.structure(o, h, l, c, 2)
    blocks = smc.order_blocks(o, h, l, c, 1.5, events)
    bull = [x for x in blocks if x["dir"] == "bull"]
    assert bull and abs(bull[0]["lo"] - 98.0) < 1e-9 and abs(bull[0]["hi"] - 99.2) < 1e-9 and not bull[0]["tested"]


def test_fvg_detected_and_tracks_fill():
    rows = [(100, 101, 99, 100.5), (100.5, 104, 100.4, 103.8), (103.8, 105, 102.5, 104.5)]  # gap 101..102.5
    rows += [(104.5, 105, 104, 104.8)] * 3
    a = np.array(rows, dtype=[("open", float), ("high", float), ("low", float), ("close", float)])
    g = smc.fvgs(a["open"], a["high"], a["low"], a["close"], atr=2.0)
    assert len(g) == 1 and g[0]["dir"] == "bull" and (g[0]["lo"], g[0]["hi"]) == (101.0, 102.5) and g[0]["fill"] == 0.0
    rows += [(104.8, 105, 101.8, 102.0)]  # price dips halfway into the gap
    a = np.array(rows, dtype=a.dtype)
    g = smc.fvgs(a["open"], a["high"], a["low"], a["close"], atr=2.0)
    assert 0.4 < g[0]["fill"] < 0.6
    rows += [(102.0, 102.1, 99.0, 99.5)]  # closes through it: mitigated, no longer listed
    a = np.array(rows, dtype=a.dtype)
    assert [g for g in smc.fvgs(a["open"], a["high"], a["low"], a["close"], atr=2.0) if g["dir"] == "bull"] == []


def test_liquidity_pool_and_sweep():
    b = zig([100, 110, 102, 109.9, 101, 106], per=6, wick=0.2)
    h, l, c = b["high"], b["low"], b["close"]
    hs, ls = levels.swing_points(h, l, 3)
    liq = smc.liquidity(h, l, c, hs, ls, atr=2.0)
    assert any(p["eq"] for p in liq["bsl"])  # equal highs at ~110 are one pool
    # a wick above the pool that closes back below is a sweep
    extra = np.array([(0, 106, 111.5, 105.5, 109.0, 1)], dtype=DT)
    b2 = np.concatenate([b, extra])
    liq = smc.liquidity(b2["high"], b2["low"], b2["close"], hs, ls, atr=2.0)
    assert liq["sweep"] and liq["sweep"]["side"] == "bsl" and liq["sweep"]["bars_ago"] == 0


def test_dealing_range_brackets_price_and_gives_ote():
    hs, ls = [(10, 120.0), (30, 118.0)], [(20, 100.0), (40, 104.0)]
    d = smc.dealing_range(hs, ls, 108.0)
    assert d and d["lo"] <= 108 <= d["hi"] and d["eq"] == (d["lo"] + d["hi"]) / 2
    assert smc.dealing_range(hs, ls, 130.0) is None  # breakout: no premium/discount reading


def test_analyze_and_compact_on_trend():
    b = zig([100, 110, 104, 116, 108, 122, 114, 126], per=8, wick=0.3)
    a = smc.analyze(b, 3)
    assert a["ok"] and a["trend"] == "bull"
    out = smc.compact(a, 120.0, 2)
    assert out["trend"] == "bull" and isinstance(out["events"], list)


# ---- risk / gates / rules
def test_manage_sl_thresholds_are_configurable():
    # long entry 100, risk 2: at +1R break-even by default; with be_r=1.5 nothing yet
    assert risk.manage_sl("buy", 100, 102.2, 98, 2, 1.0, 101) == 100
    assert risk.manage_sl("buy", 100, 102.2, 98, 2, 1.0, 101, be_r=1.5) is None
    # trail only after trail_r: price 105 (+2.5R) with trail_r 2 trails behind the swing, at 1.5 it also does
    assert risk.manage_sl("buy", 100, 106, 100, 2, 1.0, 104, be_r=1.0, trail_r=2.0) > 100
    assert risk.manage_sl("buy", 100, 103, 100, 2, 1.0, 102, be_r=1.0, trail_r=2.0) is None


def _ctx(**kw):
    base = dict(entry_ok=True, phase="ACTIVE", kill=False, halt=False, stopped=False, stop_reason="", demo_ok=True,
                market_open=True, data_fresh=True, open_positions=0, max_positions=99, trades=0, max_trades=150,
                consec_losses=0, max_consec=6, day_pct=0, daily_stop=12, news_blocked=False, news_reason="",
                spread=10, spread_max=None, atr=100.0, atr_min=0.6, atr_max=6, risk_flag="")
    return {**base, **kw}


def test_swing_ctx_drops_scalp_gates_but_keeps_hard_ones():
    busy = _ctx(atr=100.0, open_positions=99, trades=500, consec_losses=9)
    assert gates.blockers(busy)  # the scalp gates do block this
    assert gates.blockers(swing.swing_ctx(busy)) == []
    for bad in (dict(kill=True), dict(halt=True), dict(day_pct=-13), dict(market_open=False), dict(data_fresh=False),
                dict(demo_ok=False), dict(entry_ok=False, phase="MANAGE")):
        assert gates.blockers(swing.swing_ctx(_ctx(**bad)))
    assert "risk_flag:x" in gates.blockers(swing.swing_ctx(_ctx(risk_flag="x")))
    assert gates.blockers(gates.apply_overrides(swing.swing_ctx(_ctx(risk_flag="x")), ["risk_flag"])) == []


def _sast(y, m, d, hh, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=SAST)


def test_swing_blockers_limits_and_weekend():
    thu, fri_am, fri_pm, sat = (_sast(2026, 10, 22, 12), _sast(2026, 10, 23, 12), _sast(2026, 10, 23, 18, 30),
                                _sast(2026, 10, 24, 10))
    assert swing.swing_blockers(0, 0, None, "buy", thu, C) == []
    assert "swing_positions_max" in swing.swing_blockers(2, 0, "buy", "buy", thu, C)
    assert "swing_day_max" in swing.swing_blockers(0, 3, None, "buy", thu, C)
    assert "opposite_swing_open" in swing.swing_blockers(1, 0, "buy", "sell", thu, C)
    assert swing.swing_blockers(1, 0, "buy", "buy", fri_am, C) == []
    assert "weekend_no_entry" in swing.swing_blockers(0, 0, None, "buy", fri_pm, C)
    assert "weekend_no_entry" in swing.swing_blockers(0, 0, None, "buy", sat, C)
    assert "swing_disabled" in swing.swing_blockers(0, 0, None, "buy", thu, {**C, "swing_enabled": False})


def test_weekend_flat_and_time_stop():
    assert not swing.weekend_flat_due(_sast(2026, 10, 23, 21, 0), C)
    assert swing.weekend_flat_due(_sast(2026, 10, 23, 21, 30), C)
    assert swing.weekend_flat_due(_sast(2026, 10, 24, 9), C)
    assert not swing.weekend_flat_due(_sast(2026, 10, 26, 9), C)
    assert not swing.weekend_flat_due(_sast(2026, 10, 23, 23), {**C, "swing_weekend_flat": False})
    assert swing.held_too_long(1, 97 * 3600, 96) and not swing.held_too_long(1, 10 * 3600, 96)
    assert not swing.held_too_long(None, 10 ** 9, 96)


def test_stop_band_in_h1_atr():
    assert swing.stop_in_band(100, 90, 10, C) and not swing.stop_in_band(100, 99, 10, C)
    assert not swing.stop_in_band(100, 60, 10, C)


# ---- scoring on a hand-built multi-timeframe context
def _tf(trend, n=100, obs=(), fvgs=(), events=(), bsl=(), ssl=(), sweep=None, rng=None, atr=10.0):
    return {"ok": True, "n": n, "atr": atr, "trend": trend, "events": list(events), "obs": list(obs), "fvgs": list(fvgs),
            "liq": {"bsl": [{"level": x, "eq": False} for x in bsl], "ssl": [{"level": x, "eq": False} for x in ssl],
                    "sweep": sweep}, "range": rng}


def _bars(prices):
    return np.array([(p, p + 1, p - 1, p) for p in prices], dtype=[("open", float), ("high", float), ("low", float),
                                                                     ("close", float)])


def _ctx_bull(trend_h4="bull"):
    rng = {"lo": 80.0, "hi": 130.0, "eq": 105.0, "leg": "up", "ote": (90.0, 99.0)}
    ob = {"dir": "bull", "lo": 99.0, "hi": 101.0, "i": 60, "formed": 65, "tested": False, "kind": "BOS"}
    A = {"d1": _tf("bull"), "h4": _tf(trend_h4, rng=rng),
         "h1": _tf("bull", obs=[ob], rng=rng, bsl=[140.0]),
         "m15": _tf("bull", events=[{"i": 97, "kind": "CHoCH", "dir": "bull", "level": 100.0, "swing_i": 90}])}
    Z = [{"lo": 98.5, "hi": 101.5, "mid": 100, "kind": "support", "dist_atr": 0.0, "touches": 4, "tfs": {"h4"}, "score": 9},
         {"lo": 125.0, "hi": 127.0, "mid": 126, "kind": "resistance", "dist_atr": 2.4, "touches": 3, "tfs": {"h1"}, "score": 5}]
    return {"A": A, "Z": Z, "atr": 10.0, "key": {}, "round": {}, "bars": {"h1": _bars([100] * 40), "m15": _bars([100] * 40)}}


def test_score_side_long_at_fresh_ob_on_support_with_choch():
    cand = swing.score_side("buy", _ctx_bull(), 101.0, C)
    assert cand and cand["status"] == "ready" and cand["score"] >= C["swing_min_score"]
    assert cand["sl"] < 99.0 and cand["tp"] < 125.0 and cand["rr"] >= C["swing_min_rr"]
    assert C["swing_min_sl_atr"] <= cand["sl_atr"] <= C["swing_max_sl_atr"]
    assert "M15 CHoCH" in cand["why"] and cand["setup"] == "ob_retest"


def test_no_counter_trend_swing_and_no_idea_without_poi():
    assert swing.score_side("sell", _ctx_bull(), 101.0, C) is None  # H4 bullish: no short
    bare = _ctx_bull()
    bare["A"]["h1"]["obs"], bare["Z"] = [], [bare["Z"][1]]
    assert swing.score_side("buy", bare, 101.0, C) is None  # no POI and no support zone near price


def test_watch_status_when_price_is_away_from_poi_and_no_target_no_candidate():
    cand = swing.score_side("buy", _ctx_bull(), 108.0, C)
    assert cand is None or cand["status"] in ("watch", "at_poi")
    ctx = _ctx_bull()
    ctx["Z"] = ctx["Z"][:1]
    ctx["A"]["h1"]["liq"]["bsl"] = []
    assert swing.score_side("buy", ctx, 101.0, C) is None  # nothing to target at >= 2R


def test_candidates_sorted_ready_first_and_filtered_by_score():
    out = swing.candidates(_ctx_bull(), 101.0, C)
    assert out and out[0]["status"] == "ready" and all(x["score"] >= C["swing_min_score"] - 1 for x in out)


# ---- server harness: swing positions are tagged, managed in H1 units and exempt from scalp rules
def _srv(tmp_path, monkeypatch):
    import mt5_server as s
    from tests.test_features import FakeMT5
    fake = FakeMT5()
    monkeypatch.setattr(s, "mt5", fake)
    monkeypatch.setattr(s, "STATE_DIR", tmp_path)
    monkeypatch.setattr(s, "STATE_F", tmp_path / "state.json")
    monkeypatch.setattr(s, "JOURNAL_F", tmp_path / "journal.jsonl")
    monkeypatch.setattr(s, "CAL_F", tmp_path / "cal.json")
    monkeypatch.setattr(s, "LESSONS_F", tmp_path / "lessons.md")
    monkeypatch.setattr(s, "_ensure", lambda: None)
    fake.orders_get = lambda symbol=None: []
    fake.TIMEFRAME_H1, fake.TIMEFRAME_M15 = 16385, 15
    return s, fake


def _pos(ticket, c, **kw):
    return NS(ticket=ticket, symbol=c["symbol"], magic=c["magic"], type=0, volume=0.10, price_open=100.0, sl=98.0, tp=110.0,
              profit=0.0, **kw)


def test_flatten_only_scalps_leaves_swings(tmp_path, monkeypatch):
    s, fake = _srv(tmp_path, monkeypatch)
    c = s.cfg()
    fake.positions = [_pos(1, c), _pos(2, c)]
    state = {"positions": {"1": {"style": "scalp"}, "2": {"style": "swing"}}}
    acts = s.flatten(c, "cap", state, "scalp")
    assert [a["close"] for a in acts] == [1]
    assert [a["close"] for a in s.flatten(c, "kill", state)] == [1, 2]
    assert s._style(state, fake.positions[1]) == "swing" and s._style({"positions": {}}, fake.positions[0]) == "scalp"


def test_adjust_refuses_the_other_books_tickets(tmp_path, monkeypatch):
    s, fake = _srv(tmp_path, monkeypatch)
    c = s.cfg()
    fake.positions = [_pos(1, c), _pos(2, c)]
    fake.symbol_info = lambda sym: NS(digits=2, point=0.01, trade_stops_level=0)
    s.save_state({"positions": {"1": {"style": "scalp", "side": "buy", "entry": 100.0, "r_dist": 2.0},
                                "2": {"style": "swing", "side": "buy", "entry": 100.0, "r_dist": 2.0}}})
    assert "adjust_swing" in s.adjust_position(2, "close")["error"]
    assert "adjust_position" in s.adjust_swing(1, "close")["error"]
    assert s.adjust_swing(2, "close")["ok"] and s.load_state()["positions"]["2"]["closed_by"] == "ai"


def test_swing_closed_does_not_touch_scalp_streak_and_is_journalled(tmp_path, monkeypatch):
    s, fake = _srv(tmp_path, monkeypatch)
    c = s.cfg()
    fake.deals = [NS(entry=0, time=1_999_100, profit=0, commission=0, swap=0, price=100.0, reason=0),
                  NS(entry=1, time=1_999_900, profit=-100.0, commission=0, swap=0, price=98.0, reason=4)]
    state = {"positions": {"7": {"side": "buy", "entry": 100.0, "r_dist": 2.0, "risk_money": 100.0, "signal_id": "sw",
                                 "style": "swing", "risk_pct": 1.0}}, "run": {"consec_losses": 0}}
    closed = s.reconcile(state, c)
    assert closed[0]["style"] == "swing" and state["run"]["consec_losses"] == 0
    ex = [r for r in s.jr.read(str(s.JOURNAL_F)) if r["type"] == "exit"][0]
    assert ex["style"] == "swing" and ex["risk_pct"] == 1.0 and ex["outcome_r"] == -1.0


def _h1_array(n=59):
    return np.array([(0, 100, 101.0, 99.0, 100.0, 1)] * n, dtype=DT)


def test_manage_swing_breakeven_in_h1_units_and_no_pre_event_exit(tmp_path, monkeypatch):
    s, fake = _srv(tmp_path, monkeypatch)
    c = s.cfg()
    fake.positions = [_pos(7, c)]
    monkeypatch.setattr(s, "_rates", lambda *a, **k: _h1_array())
    monkeypatch.setattr(s.ind, "atr", lambda *a, **k: 1.0)
    state = {"positions": {"7": {"side": "buy", "entry": 100.0, "r_dist": 2.0, "risk_money": 100.0, "style": "swing",
                                 "opened_ts": datetime(2026, 10, 22, 9, 0, tzinfo=SAST).timestamp()}}}
    snap = {"tick": NS(bid=102.4, ask=102.5), "closed": _h1_array(), "atr": 99.0,
            "info": NS(volume_min=0.01, volume_step=0.01, digits=2)}
    ts = datetime(2026, 10, 22, 10, 0, tzinfo=SAST).timestamp()  # Thursday morning
    acts = s.manage(state, c, snap, ts)
    assert any(a.get("sl") == 7 and a["to"] == 100.0 and a["swing"] for a in acts)  # +1.2R -> break-even
    assert not any("partial" in a for a in acts)  # partial waits for +1.5R
    assert state["positions"]["7"].get("closed_by") is None


def test_manage_swing_closes_before_weekend_and_throttles_retries(tmp_path, monkeypatch):
    s, fake = _srv(tmp_path, monkeypatch)
    c = s.cfg()
    fake.positions = [_pos(7, c)]
    monkeypatch.setattr(s, "_rates", lambda *a, **k: _h1_array())
    state = {"positions": {"7": {"side": "buy", "entry": 100.0, "r_dist": 2.0, "risk_money": 100.0, "style": "swing",
                                 "opened_ts": datetime(2026, 10, 23, 9, 0, tzinfo=SAST).timestamp()}}}
    snap = {"tick": NS(bid=100.4, ask=100.5), "closed": _h1_array(), "atr": 1.0,
            "info": NS(volume_min=0.01, volume_step=0.01, digits=2)}
    fri = datetime(2026, 10, 23, 21, 40, tzinfo=SAST).timestamp()
    acts = s.manage(state, c, snap, fri)
    assert acts and acts[0]["swing_exit"] == 7 and acts[0]["why"] == "weekend" and acts[0]["ok"]
    assert state["positions"]["7"]["closed_by"] == "weekend"
    assert s.manage(state, c, snap, fri + 5) == []  # throttled: no close spam every tick
    # time stop
    state["positions"]["7"].update(closed_by=None, flat_try_ts=0)
    thu = datetime(2026, 10, 22, 10, 0, tzinfo=SAST).timestamp()
    state["positions"]["7"]["opened_ts"] = thu - 100 * 3600
    acts = s.manage(state, c, snap, thu)
    assert acts[0]["why"] == "time_stop"


def test_stats_use_per_trade_risk_for_drawdown():
    from engine import journal
    recs = [{"type": "exit", "outcome_r": -1.0, "risk_pct": 1.0}, {"type": "exit", "outcome_r": -1.0}]
    st = journal.stats(recs, 5.0)
    assert abs(st["max_dd_pct"] - (1 - 0.99 * 0.95) * 100) < 0.11
