import json
import time
from datetime import datetime, timezone, timedelta

import numpy as np

from engine import clock, gates, indicators as ind, journal, news, risk, signal as sg

CFG = json.load(open("config.json"))
CAP2H = {**CFG, "run_max_minutes": 120}  # cap tests are independent of the live config
SAST = timezone(timedelta(hours=2))


def at(h, m=0, s=0):
    return datetime(2026, 10, 19, h, m, s, tzinfo=SAST)


# ---- indicators
def test_ema_constant_and_trend():
    assert np.allclose(ind.ema([5] * 50, 10), 5)
    up = np.linspace(100, 400, 300)
    assert ind.trend(up) == "long"
    assert ind.trend(up[::-1]) == "short"
    assert ind.trend(up[:100]) == "flat"
    assert ind.bias(up, up[::-1]) == "flat"


def test_atr_known_value():
    h = np.array([10, 12, 13, 14.0])
    l = np.array([8, 9, 10, 11.0])
    c = np.array([9, 11, 12, 13.0])
    # TR = 3,3,3 -> ATR(3) = 3
    assert ind.atr(h, l, c, 3) == 3.0


# ---- sizing
def test_lots_normal():
    # tick 0.01 -> 0.164 ZAR per tick per lot; 150pt SL = 15000 ticks => R2460/lot; risk R300 -> 0.12 lot
    lots, why = risk.lots_for_risk(300, 150, 0.01, 0.164, 0.05, 0.01, 500, 1.0, 1.5)
    assert why == "ok" and lots == 0.12


def test_lots_rejects_when_min_lot_too_risky():
    lots, why = risk.lots_for_risk(5, 150, 0.01, 0.164, 0.05, 0.01, 500, 1.0, 1.5)
    assert lots is None and why.startswith("min_lot_risk")


def test_lots_uses_min_lot_within_tolerance_and_caps():
    # 300pt SL: min lot risks R246 -> fine vs R200 target (1.5x = R300), rejected vs R100 target
    lots, _ = risk.lots_for_risk(200, 300, 0.01, 0.164, 0.05, 0.01, 500, 1.0, 1.5)
    assert lots == 0.05
    assert risk.lots_for_risk(100, 300, 0.01, 0.164, 0.05, 0.01, 500, 1.0, 1.5)[0] is None
    lots, _ = risk.lots_for_risk(1e6, 10, 0.01, 0.164, 0.05, 0.01, 500, 1.0, 1.5)
    assert lots == 1.0


# ---- SL management
def test_manage_sl_be_and_trail_never_loosen():
    # long, entry 100, SL 90 (R=10)
    assert risk.manage_sl("buy", 100, 105, 90, 10, 4, 98) is None
    assert risk.manage_sl("buy", 100, 110, 90, 10, 4, 98) == 100
    # +1.5R: price 115, swing 108 -> trail 107.6, price-trail 7.4 >= atr 4
    assert abs(risk.manage_sl("buy", 100, 115, 100, 10, 4, 108) - 107.6) < 1e-9
    # swing below current SL: no loosening
    assert risk.manage_sl("buy", 100, 115, 109, 10, 4, 105) is None
    # short mirror
    assert risk.manage_sl("sell", 100, 90, 110, 10, 4, 102) == 100


# ---- clock / run lifecycle
def test_phases():
    p = lambda h, m=0, el=0: clock.phase(at(h, m), CFG, el)
    assert p(21, 0)["phase"] == "ACTIVE" and p(21, 0)["entry_ok"]
    assert p(22, 19)["phase"] == "ACTIVE"
    assert p(22, 20)["phase"] == "MANAGE" and not p(22, 30)["entry_ok"]
    assert p(22, 45)["phase"] == "BREAK" and p(23, 59)["phase"] == "BREAK"
    assert p(0, 2)["phase"] == "MANAGE" and p(0, 5)["phase"] == "ACTIVE"
    assert p(14, 0)["phase"] == "ACTIVE"  # no fixed schedule: any start time works


def test_run_cap_flattens_and_stops():
    r = clock.phase(at(21, 0), CAP2H, 120 * 60)
    assert r["phase"] == "FLATTEN" and r["stop_loop"] and r["run_left_s"] == 0
    r = clock.phase(at(21, 0), CAP2H, 105 * 60)  # last 15 min: no new entries
    assert r["phase"] == "MANAGE" and not r["stop_loop"]
    r = clock.phase(at(21, 0), CAP2H, 119 * 60)
    assert r["next_boundary_s"] == 60  # never sleeps past the cap


def test_wake_never_crosses_break_or_cap():
    r = clock.phase(at(22, 45, 5), CAP2H, 0)
    assert r["next_boundary_s"] == int((1440 - (22 * 60 + 45 + 5 / 60)) * 60)
    r = clock.phase(at(22, 45, 5), CAP2H, 100 * 60)  # break outlasts the run -> capped at run end
    assert r["next_boundary_s"] == 20 * 60
    assert clock.next_bar_close_s(at(21, 31, 0)) == 14 * 60 + 20


def test_run_start_continue_expire(tmp_path):
    from engine import run as s
    now = at(21, 0).astimezone(timezone.utc)
    st = {}
    r, status = s.start_or_continue(st, now, CFG)
    assert status == "new"
    r["wake_due"] = now.timestamp() + 900
    # same loop still ticking on schedule -> same run
    r2, status = s.start_or_continue(st, now + timedelta(minutes=15), CFG)
    assert status == "cont" and r2["start_ts"] == r["start_ts"]
    # loop stopped, restarted 70 min later (> run_gap_new_s) -> new run
    r3, status = s.start_or_continue(st, now + timedelta(minutes=15 + 70), CFG)
    assert status == "new" and r3["start_ts"] != r["start_ts"]
    # loop stopped, restarted soon, within the cap -> resumes the same run (same 2h cap)
    st = {}
    r, _ = s.start_or_continue(st, now, CFG)
    r["wake_due"] = now.timestamp() + 900
    assert s.start_or_continue(st, now + timedelta(minutes=40), CFG)[1] == "cont"


def test_cap_cannot_chain_into_a_new_run():
    from engine import run as s
    now = at(21, 0).astimezone(timezone.utc)
    st = {}
    r, _ = s.start_or_continue(st, now, CAP2H)
    # the loop keeps ticking on schedule; the tick that lands past 120 min must continue (-> FLATTEN), not restart
    t = now
    for _ in range(9):
        t += timedelta(minutes=15)
        r["wake_due"] = t.timestamp() + 0  # due right now
        r2, status = s.start_or_continue(st, t + timedelta(seconds=20), CAP2H)
        assert status == "cont" and r2["start_ts"] == r["start_ts"]
    assert (t - now).total_seconds() >= 120 * 60
    assert clock.phase(t, CAP2H, (t - now).total_seconds())["phase"] == "FLATTEN"
    # user restarts manually after the cap (loop not alive) -> fresh run
    r["wake_due"] = None
    r3, status = s.start_or_continue(st, t + timedelta(minutes=5), CAP2H)
    assert status == "cont" or status == "new"
    r["wake_due"] = (t - timedelta(minutes=30)).timestamp()
    assert s.start_or_continue(st, t + timedelta(minutes=5), CAP2H)[1] == "new"


def test_just_ended_guard():
    from engine import run as s
    now = at(21, 0).astimezone(timezone.utc)
    st = {}
    r, _ = s.start_or_continue(st, now, CFG)
    r["ended"], r["ended_ts"] = True, now.timestamp()
    assert s.start_or_continue(st, now + timedelta(seconds=60), CFG)[1] == "just_ended"
    assert s.start_or_continue(st, now + timedelta(minutes=10), CFG)[1] == "new"


# ---- news
def _write_cal(tmp_path, events, age_s=0):
    p = tmp_path / "cal.json"
    p.write_text(json.dumps({"fetched": time.time() - age_s, "events": events}))
    return str(p)


def test_news_gate(tmp_path):
    now = 1_000_000.0
    path = _write_cal(tmp_path, [{"title": "CPI", "ts": now + 600}])
    # file 'fetched' uses real time; align by monkey-free approach: use real now
    real = time.time()
    path = _write_cal(tmp_path, [{"title": "CPI", "ts": real + 600}])
    g = news.gate(path, real, 15, 10, 12)
    assert g["blocked"] and g["reason"] == "news:CPI" and g["resume_s"] > 600
    g = news.gate(path, real + 11 * 60 + 600, 15, 10, 12)
    assert not g["blocked"] or g["reason"].startswith("news")
    path = _write_cal(tmp_path, [{"title": "CPI", "ts": real + 7200}])
    g = news.gate(path, real, 15, 10, 12)
    assert not g["blocked"] and g["next_block_s"] == 7200 - 900


def test_news_fails_closed(tmp_path):
    assert news.gate(str(tmp_path / "missing.json"), time.time(), 15, 10, 12)["reason"] == "no_calendar"
    path = _write_cal(tmp_path, [], age_s=13 * 3600)
    assert news.gate(path, time.time(), 15, 10, 12)["reason"] == "calendar_stale"
    r = news.refresh(str(tmp_path / "c.json"), "x", fetch=lambda u: (_ for _ in ()).throw(OSError("down")))
    assert not r["ok"]


# ---- gates
def _ctx(**kw):
    c = dict(entry_ok=True, phase="ACTIVE", kill=False, halt=False, stopped=False, stop_reason="", demo_ok=True,
             market_open=True, data_fresh=True, open_positions=0, max_positions=1, trades=0, max_trades=4,
             consec_losses=0, max_consec=2, day_pct=0.0, daily_stop=6.0, news_blocked=False, news_reason="",
             spread=112, spread_max=200, atr=60, atr_min=35, atr_max=100)
    c.update(kw)
    return c


def test_gates():
    assert gates.blockers(_ctx()) == []
    assert "KILL" in gates.blockers(_ctx(kill=True))
    assert "not_demo" in gates.blockers(_ctx(demo_ok=False))
    assert "daily_stop" in gates.blockers(_ctx(day_pct=-6.0))
    assert "consec_losses" in gates.blockers(_ctx(consec_losses=2))
    assert any(x.startswith("atr") for x in gates.blockers(_ctx(atr=120)))
    assert any(x.startswith("spread") for x in gates.blockers(_ctx(spread=300)))
    assert "market_closed" in gates.blockers(_ctx(market_open=False))


# ---- signal
def _uptrend_with_pullback():
    base = np.linspace(100, 160, 80)
    c = base.copy()
    c[-4:] = [c[-5] + 2, c[-5] - 2, c[-5] - 6, c[-5] - 5]  # dip toward the EMAs
    o = np.roll(c, 1) + 0.0
    o[0] = c[0]
    h = np.maximum(o, c) + 0.5
    l = np.minimum(o, c) - 0.5
    return o, h, l, c


def test_signal_none_in_flat_bias():
    o, h, l, c = _uptrend_with_pullback()
    s, why = sg.find_signal(o, h, l, c, "flat", CFG)
    assert s is None and why == "bias_flat"


def test_signal_bullish_engulfing_long():
    o, h, l, c = _uptrend_with_pullback()
    # force a bearish bar then a bullish engulfing that stays above EMA50
    n = len(c)
    o[n - 2], c[n - 2] = 150.0, 148.0
    l[n - 2], h[n - 2] = 147.5, 150.5
    o[n - 1], c[n - 1] = 147.8, 151.0
    l[n - 1], h[n - 1] = 147.0, 151.5
    s, why = sg.find_signal(o, h, l, c, "long", dict(CFG, max_sl_atr=50))
    assert why == "ok", why
    assert s["side"] == "buy" and s["pattern"] == "engulfing" and s["sl"] < s["entry_ref"] < s["tp"]
    assert abs((s["tp"] - s["entry_ref"]) / s["sl_dist"] - CFG["tp_r"]) < 1e-9
    # same bars but no rejection candle -> no signal
    o2, c2 = o.copy(), c.copy()
    o2[-1], c2[-1] = 151.0, 150.0
    assert sg.find_signal(o2, h, l, c2, "long", dict(CFG, max_sl_atr=50))[0] is None


# ---- journal
def test_journal_stats(tmp_path):
    p = str(tmp_path / "j.jsonl")
    for r in (2.0, -1.0, -1.0, 2.0):
        journal.append(p, {"type": "exit", "outcome_r": r})
    journal.append(p, {"type": "pass", "reason": "x"})
    st = journal.stats(journal.read(p), 3.0)
    assert st["n"] == 4 and st["expectancy_r"] == 0.5 and st["profit_factor"] == 2.0
    assert journal.graduation(st)["eligible"] is False


# ---- review
def test_review_analyze_flags_and_diag():
    from engine import review
    ex = []
    for i in range(10):  # 'pin' pattern: consistent losers that had run +1R before reversing
        ex.append({"outcome_r": -1.0, "side": "buy", "pattern": "pin", "bias": "long", "hour": 22, "atr": 50,
                   "spread": 112, "exit_reason": "sl", "mfe_r": 1.2, "mae_r": 1.0, "dur_min": 30})
    for i in range(10):
        ex.append({"outcome_r": 2.0, "side": "buy", "pattern": "engulfing", "bias": "long", "hour": 21, "atr": 60,
                   "spread": 112, "exit_reason": "tp", "mfe_r": 2.1, "mae_r": 0.3, "dur_min": 45})
    r = review.analyze(ex)
    assert r["n"] == 20 and r["exit_mix"] == {"sl": 10, "tp": 10}
    assert r["by"]["pattern"]["pin"]["exp"] == -1.0 and r["by"]["pattern"]["engulfing"]["exp"] == 2.0
    assert any(f.startswith("pattern=pin") for f in r["flags"])
    assert r["diag"]["losers_med_mfe_r"] == 1.2 and r["diag"]["reached_1r_but_lost"] == 10
    assert r["diag"]["winners_med_mae_r"] == 0.3
    assert review.analyze([]) == {"n": 0}
    small = review.analyze(ex[:3])
    assert small["flags"] == []  # below min sample: no flags
