"""MCP server exposing a local MetaTrader 5 (Exness) terminal to Claude Code.

Manual tools (account_info, get_price, ..., place_order) plus the autonomous-workflow tools
(session_tick, place_trade_checked, flatten_all, journal_pass, session_summary, review, deep_review,
health_report, set_risk_flag, refresh_calendar). All rules are enforced here in code; see CLAUDE.md for the operating procedure.
"""
import asyncio
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import MetaTrader5 as mt5
from mcp.server.fastmcp import FastMCP

from engine.defaults import DEFAULTS
from engine import (brief, clock, exits as ex_, filters as flt, gates, health, indicators as ind, journal as jr,
                    news, report, review as rv, risk, scout as sc, signal as sg)
from engine.run import roll_state, start_or_continue  # noqa: F401  (re-exported; logic lives in engine/run.py)

ROOT = Path(__file__).parent
# Experiment instances run beside the default one: TRADING_CONFIG / TRADING_STATE select their own config file
# and state directory (journal, run state, lessons), so symbols never share journals or run counters.
CONFIG_F = ROOT / os.environ.get("TRADING_CONFIG", "config.json")
STATE_DIR = ROOT / os.environ.get("TRADING_STATE", "state")
STATE_F, JOURNAL_F, CAL_F = STATE_DIR / "state.json", STATE_DIR / "journal.jsonl", STATE_DIR / "calendar_cache.json"
LESSONS_F, PROPOSALS_F = STATE_DIR / "lessons.md", STATE_DIR / "proposals.md"
FILTERS_F, REPORTS_DIR = STATE_DIR / "filters.json", ROOT / "reports"
TAG = STATE_DIR.name  # report-file prefix distinguishing instances
REVIEW_EVERY, MAX_LESSONS = 10, 25  # new closed trades between reviews; cap on lesson lines
TERMINAL_PATH = os.environ.get("MT5_PATH", r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe")
MAX_LOT = float(os.environ.get("MT5_MAX_LOT", "0.10"))  # cap for the manual place_order tool only
DRY = os.environ.get("DRY_RUN") == "1"

TF_MT5 = {1: mt5.TIMEFRAME_M1, 5: mt5.TIMEFRAME_M5, 15: mt5.TIMEFRAME_M15}

mcp = FastMCP("mt5")


# ---------------------------------------------------------------- helpers
UNCAPPED_F = ROOT / "UNCAPPED"  # set by `tools\desk.ps1 uncap` (/desk-max): the run has no time cap


def cfg():
    c = {**DEFAULTS, **json.loads(CONFIG_F.read_text())}
    c["spread_max_points"] = c["max_spread_r"] = None  # no spread limits (gate and cost guard), whatever the config file says
    if UNCAPPED_F.exists():
        c["run_max_minutes"] = 10 ** 7
    return c


rv.configure_bands(cfg())


def _ensure():
    if mt5.terminal_info() is None:
        if not mt5.initialize(path=TERMINAL_PATH):
            raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")


def _result(r):
    if r is None:
        return {"ok": False, "error": str(mt5.last_error())}
    d = r._asdict()
    d.pop("request", None)
    d["ok"] = r.retcode == mt5.TRADE_RETCODE_DONE
    return d


def load_state():
    try:
        return json.loads(STATE_F.read_text())
    except Exception:
        return {"positions": {}, "session": {}, "week": {}, "last_signal_id": None}


def save_state(s):
    STATE_DIR.mkdir(exist_ok=True)
    tmp = STATE_F.with_suffix(".tmp")  # atomic: several agents share this server, a torn file would reset the run
    tmp.write_text(json.dumps(s, indent=1))
    os.replace(tmp, STATE_F)


def is_demo():
    a = mt5.account_info()
    return bool(a) and (a.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO or cfg()["live_enabled"])


def _positions(c):
    return [p for p in (mt5.positions_get(symbol=c["symbol"]) or []) if p.magic == c["magic"]]


def _send(req):
    """order_check each filling mode, send with the first that validates. Returns result (or None)."""
    for filling in (mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_RETURN):
        req["type_filling"] = filling
        chk = mt5.order_check(req)
        if chk is not None and chk.retcode == 0:
            return mt5.order_send(req)
    return mt5.order_send(req)


def _close(p, comment="claude close"):
    tick = mt5.symbol_info_tick(p.symbol)
    buy = p.type == mt5.POSITION_TYPE_BUY
    return _send({"action": mt5.TRADE_ACTION_DEAL, "position": p.ticket, "symbol": p.symbol, "volume": p.volume,
                  "type": mt5.ORDER_TYPE_SELL if buy else mt5.ORDER_TYPE_BUY,
                  "price": tick.bid if buy else tick.ask, "deviation": 30, "magic": p.magic, "comment": comment})


def flatten(c, reason):
    """Close all bot positions and cancel pending orders."""
    acts = []
    for p in _positions(c):
        r = _close(p, "claude flat")
        acts.append({"close": p.ticket, "ok": bool(r and r.retcode == mt5.TRADE_RETCODE_DONE), "why": reason})
    for o in mt5.orders_get(symbol=c["symbol"]) or []:
        if o.magic == c["magic"]:
            mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": o.ticket})
            acts.append({"cancel": o.ticket})
    return acts


def snapshot(c):
    """Market facts + current signal from closed bars. Returns dict (never raises on missing data)."""
    sym = c["symbol"]
    mt5.symbol_select(sym, True)
    tick, info = mt5.symbol_info_tick(sym), mt5.symbol_info(sym)
    if tick is None or info is None:
        return {"ok": False}
    get = lambda tf: mt5.copy_rates_from_pos(sym, tf, 0, 320)
    tfm = int(c["tf_min"])
    m15, h1, h4 = get(TF_MT5[tfm]), get(mt5.TIMEFRAME_H1), get(mt5.TIMEFRAME_H4)
    if any(x is None or len(x) < 120 for x in (m15, h1, h4)):
        return {"ok": False}
    closed = m15[:-1]
    bias = ind.bias(h1[:-1]["close"], h4[:-1]["close"])
    atr = ind.atr(closed["high"], closed["low"], closed["close"], 14)
    sig, why = sg.find_any(closed, bias, c)
    if sig:
        sig["id"] = f"{sym}-{int(closed[-1]['time'])}-{sig['side']}"
    return {"ok": True, "tick": tick, "info": info, "closed": closed, "bias": bias, "atr": atr, "signal": sig,
            "why": why, "spread": (tick.ask - tick.bid) / info.point,
            "market_open": abs(time.time() - tick.time) <= c["tick_stale_s"],
            "data_fresh": int(m15[-1]["time"]) == int(tick.time) // (tfm * 60) * (tfm * 60)}


def reconcile(state, c):
    """Detect closed tracked positions, journal exits, update loss streak."""
    closed = []
    open_t = {str(p.ticket) for p in _positions(c)}
    for t, rec in list(state["positions"].items()):
        if t in open_t:
            continue
        all_deals = mt5.history_deals_get(position=int(t)) or []
        deals = [d for d in all_deals if d.entry == mt5.DEAL_ENTRY_OUT]
        if not deals:
            continue
        pnl = sum(d.profit + d.commission + d.swap for d in deals)
        r = pnl / rec["risk_money"] if rec["risk_money"] else None
        r = None if r is None else round(r, 2)
        why = _exit_reason(deals[-1], r, rec.get("closed_by"), c["loss_threshold_r"])
        t0 = next((d.time for d in all_deals if d.entry == mt5.DEAL_ENTRY_IN), None)
        mfe, mae = _excursions(c["symbol"], rec, t0, deals[-1].time)
        # exit records are self-contained (entry features copied in) so analysis never needs a join
        jr.append(JOURNAL_F, {"type": "exit", "ticket": int(t), "signal_id": rec["signal_id"], "pnl": round(pnl, 2),
                              "outcome_r": r, "exit_reason": why, "exit_price": deals[-1].price,
                              "mfe_r": mfe, "mae_r": mae,
                              "dur_min": None if t0 is None else round((deals[-1].time - t0) / 60),
                              "partial": bool(rec.get("partial_done")), "risk_pct": rec.get("risk_pct"),
                              **{k: rec.get(k) for k in ("side", "pattern", "bias", "atr", "spread", "hour", "regime", "thesis")}})
        closed.append({"ticket": int(t), "r": r, "why": why})
        s = state["run"]
        # only a real loss extends the streak; BE/scratch exits (> -loss_threshold_r) reset nothing
        if r is not None and r <= -c["loss_threshold_r"]:
            s["consec_losses"] += 1
        elif r is None or r > 0:
            s["consec_losses"] = 0
        del state["positions"][t]
    return closed


def _exit_reason(deal, r, closed_by=None, loss_r=0.25):
    kind = "tp" if deal.reason == mt5.DEAL_REASON_TP else "sl" if deal.reason == mt5.DEAL_REASON_SL else "other"
    return ex_.exit_reason(kind, r, closed_by, loss_r)


def _excursions(symbol, rec, t0, t1):
    """(MFE_R, MAE_R) from M1 bars between entry and exit; (None, None) if unavailable."""
    try:
        now_b = mt5.symbol_info_tick(symbol).time
        bars = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, min(5000, int((now_b - t0) / 60) + 3))
        return ex_.excursions(bars, rec["side"], rec["entry"], rec["r_dist"], t0, t1)
    except Exception:
        return None, None


def _partial(p, rec, c, snap, frac=None):
    """Bank part of the position at +partial_at_r (then break-even/trail run on the remainder). Never adds risk."""
    info = snap["info"]
    vol = risk.partial_close_lots(p.volume, frac or c["partial_frac"], info.volume_min, info.volume_step)
    if vol <= 0:
        rec["partial_done"] = True  # too small to split: do not retry every tick
        return {"partial": p.ticket, "ok": False, "why": "too_small"}
    buy = p.type == mt5.POSITION_TYPE_BUY
    tick = snap["tick"]
    r = _send({"action": mt5.TRADE_ACTION_DEAL, "position": p.ticket, "symbol": p.symbol, "volume": vol,
               "type": mt5.ORDER_TYPE_SELL if buy else mt5.ORDER_TYPE_BUY,
               "price": tick.bid if buy else tick.ask, "deviation": 30, "magic": p.magic, "comment": "claude partial"})
    ok = bool(r and r.retcode == mt5.TRADE_RETCODE_DONE)
    if ok:
        rec["partial_done"] = True
        jr.append(JOURNAL_F, {"type": "partial", "ticket": p.ticket, "closed_lots": vol, "left": round(p.volume - vol, 2)})
    return {"partial": p.ticket, "lots": vol, "ok": ok}


def manage(state, c, snap, now_ts=None):
    acts = []
    ev = news.next_event(str(CAL_F), now_ts or time.time(), 15) if c["pre_event_exit"] else None
    for p in _positions(c):
        rec = state["positions"].get(str(p.ticket))
        if not rec:
            continue
        buy = p.type == mt5.POSITION_TYPE_BUY
        price = snap["tick"].bid if buy else snap["tick"].ask
        # winners are banked before a high-impact release; a loser keeps its SL (never widened/removed)
        if ev and 0 <= ev["in_s"] <= c["pre_event_exit_min"] * 60 and p.profit > 0:
            rec["closed_by"] = "pre_event"
            r = _close(p, "claude pre-event")
            acts.append({"pre_event_exit": p.ticket, "event": ev["title"],
                         "ok": bool(r and r.retcode == mt5.TRADE_RETCODE_DONE)})
            continue
        if c["partial_tp"] and not rec.get("partial_done") and                 risk.partial_due(rec["side"], rec["entry"], price, rec["r_dist"], c["partial_at_r"]):
            acts.append(_partial(p, rec, c, snap))
        last5 = snap["closed"][-5:]
        swing = float(last5["low"].min()) if buy else float(last5["high"].max())
        new = risk.manage_sl(rec["side"], rec["entry"], price, p.sl, rec["r_dist"], snap["atr"], swing)
        if new is not None:
            new = round(new, snap["info"].digits)
            r = mt5.order_send({"action": mt5.TRADE_ACTION_SLTP, "position": p.ticket, "symbol": p.symbol,
                                "sl": new, "tp": p.tp})
            acts.append({"sl": p.ticket, "to": new, "ok": bool(r and r.retcode == mt5.TRADE_RETCODE_DONE)})
    return acts


def _gate_ctx(c, ph, snap, s, state, opens, nw, now, equity, kill, halt):
    """Facts for gates.blockers (shared by session_tick and place_trade_checked so both apply identical rules)."""
    day_pct = (equity - state["day"]["start_equity"]) / state["day"]["start_equity"] * 100
    rf = s.get("risk_flag") or {}
    flag = rf.get("reason", "flag") if rf.get("level") == "block" and (rf.get("until_ts") or 0) > now.timestamp() else ""
    return dict(entry_ok=ph["entry_ok"], phase=ph["phase"], kill=kill, halt=halt, stopped=s["stopped"],
                stop_reason=s["stop_reason"], demo_ok=is_demo(), market_open=snap["market_open"],
                data_fresh=snap["data_fresh"], open_positions=len(opens), max_positions=c["max_positions"],
                trades=s["trades"], max_trades=c["max_trades_session"], consec_losses=s["consec_losses"],
                max_consec=c["max_consec_losses"], day_pct=day_pct, daily_stop=c["daily_stop_pct"],
                news_blocked=nw["blocked"], news_reason=nw["reason"], spread=snap["spread"],
                spread_max=c["spread_max_points"], atr=snap["atr"], atr_min=c["atr_min"], atr_max=c["atr_max"],
                risk_flag=flag, desk_max=c["desk_max_positions"], desk_open=_desk_open(c))


def _desk_open(c):
    """Open positions across every bot magic of the desk (both instruments share one account)."""
    if not c["desk_max_positions"]:
        return 0
    return sum(1 for p in (mt5.positions_get() or []) if p.magic in c["desk_magics"])


def _filter_hit(sig, snap, s, now):
    """Mined-filter match for this signal (state/filters.json, script-written) or None."""
    rules = flt.load(str(FILTERS_F))
    if not rules or not sig:
        return None
    f = flt.features(sig["side"], sig["pattern"], snap["bias"], snap["atr"], snap["spread"],
                     now.astimezone(clock.SAST).hour, s.get("regime"))
    return flt.match(rules, f)


def _pos_view(state, c, snap):
    out = []
    for p in _positions(c):
        rec = state["positions"].get(str(p.ticket), {})
        r = round(p.profit / rec["risk_money"], 2) if rec.get("risk_money") else None
        out.append({"ticket": p.ticket,
                    "side": rec.get("side") or ("buy" if p.type == 0 else "sell"),
                    "lots": p.volume, "open": p.price_open, "sl": p.sl, "tp": p.tp, "pnl_r": r})
    return out


# ---------------------------------------------------------------- autonomous workflow tools
@mcp.tool()
def refresh_calendar() -> dict:
    """Fetch the USD high-impact economic calendar (ForexFactory JSON) into the local cache."""
    STATE_DIR.mkdir(exist_ok=True)
    return news.refresh(str(CAL_F), cfg()["calendar_url"])


@mcp.tool()
def session_tick() -> dict:
    """ONE call per wake. Runs safety checks, reconciles closed trades, manages open positions (BE/trail),
    auto-flattens on KILL/HALT/daily stop/01:00, and returns phase, gates, positions, any signal,
    next_wake_seconds and stop_loop. Claude only decides whether to act on `signal`."""
    _ensure()
    c = cfg()
    now = datetime.now(timezone.utc)
    acct = mt5.account_info()
    equity = acct.equity
    state = load_state()
    roll_state(state, equity, now)
    s, run_status = start_or_continue(state, now, c)
    if run_status == "just_ended":
        save_state(state)
        return {"phase": "ENDED", "stop_loop": True, "why_stop": "run_just_ended", "next_wake_seconds": None}
    ph = clock.phase(now, c, now.timestamp() - s["start_ts"])
    phase = ph["phase"]
    out = {"t": now.astimezone(clock.SAST).strftime("%H:%M"), "phase": phase, "dry_run": DRY,
           "run_left_min": ph["run_left_s"] // 60}
    actions = []

    if not CAL_F.exists() or time.time() - CAL_F.stat().st_mtime > 6 * 3600:
        r = refresh_calendar()
        if not r["ok"]:
            out["calendar_error"] = r["error"]
    closed = reconcile(state, c)
    if closed:
        out["closed"] = closed
        out["do"] = "closed trade(s): annotate_trade ONLY if |R|>=1 or the exit looks wrong; one line, else skip"

    kill, halt = (STATE_DIR / "KILL").exists(), (STATE_DIR / "HALT").exists()
    day_pct = (equity - state["day"]["start_equity"]) / state["day"]["start_equity"] * 100
    wk_pct = (equity - state["week"]["start_equity"]) / state["week"]["start_equity"] * 100
    if wk_pct <= -c["weekly_halt_pct"] and not halt:
        (STATE_DIR / "HALT").write_text(f"weekly drawdown {wk_pct:.1f}%")
        halt = True
    if day_pct <= -c["daily_stop_pct"] and not s["stopped"]:
        s["stopped"], s["stop_reason"] = True, "daily_stop"
    if s["consec_losses"] >= c["max_consec_losses"] and not s["stopped"]:
        s["stopped"], s["stop_reason"] = True, "consec_losses"

    opens = _positions(c)
    must_flat = kill or halt or phase == "FLATTEN" or s["stop_reason"] == "daily_stop"
    if must_flat and opens:
        actions += flatten(c, "kill" if kill else "halt" if halt else s["stop_reason"] or phase.lower())
        opens = _positions(c)
    if s["trades"] >= c["max_trades_session"] and not opens and not s["stopped"]:
        s["stopped"], s["stop_reason"] = True, "max_trades"

    stop_loop = ph["stop_loop"] or kill or halt or (s["stopped"] and not opens)
    snap = None
    if phase in ("ACTIVE", "MANAGE") and (opens or not stop_loop):
        snap = snapshot(c)
        if opens and snap["ok"]:
            actions += manage(state, c, snap, now.timestamp())
    if (c["flatten_before_break"] and phase == "MANAGE" and ph["next_boundary_s"] <= 300
            and ph["mins"] >= 22 * 60 and _positions(c)):
        actions += flatten(c, "pre_break")

    out.update({"eq": round(equity, 2), "day_pct": round(day_pct, 2), "trades": s["trades"],
                "streak": s["consec_losses"]})
    if actions:
        out["actions"] = actions
    opens = _positions(c)
    pos = _pos_view(state, c, snap) if opens else []
    if pos:
        out["pos"] = pos
    ev = news.next_event(str(CAL_F), now.timestamp(), 60)
    if ev:
        out["event_in_s"], out["event"] = ev["in_s"], ev["title"]

    if not s["warm_done"] or (stop_loop and not s["summarised"]):
        exits = [r for r in jr.read(JOURNAL_F) if r.get("type") == "exit" and r.get("style", "scalp") == "scalp"][-20:]
        out["last20"] = jr.stats(exits, c["risk_pct"])
        if not s["warm_done"]:
            todo = [] if c["desk_mode"] else ["run start: one WebSearch for USD/Nasdaq headline risk, then continue"]
            if LESSONS_F.exists():
                out["lessons"] = _lessons()
            if len([r for r in jr.read(JOURNAL_F) if r.get("type") == "exit"]) - state.get("last_review_n", 0) >= REVIEW_EVERY:
                if c["desk_mode"]:
                    out["review_due"] = True  # the coach agent owns reviews
                else:
                    todo.append(f"review due (>={REVIEW_EVERY} new closed trades): call review(), then set_lessons if warranted")
            if todo or "do" in out:
                out["do"] = "; ".join(([out["do"]] if "do" in out else []) + todo)
            s["warm_done"] = True
            s["last_headline_ts"] = now.timestamp()  # the run-start search counts as the first headline check
        else:
            s["summarised"] = True
            try:
                REPORTS_DIR.mkdir(exist_ok=True)
                rp = REPORTS_DIR / (f"run-{s['id']}.md" if TAG == "state" else f"run-{TAG}-{s['id']}.md")
                rp.write_text(report.build(s, jr.read(JOURNAL_F), c["risk_pct"],
                                           health.check(jr.read(JOURNAL_F), c["spread_max_points"])), encoding="utf-8")
                out["report"] = f"reports/{rp.name}"
            except Exception as e:  # a report must never break the stop path
                out["report_error"] = str(e)[:80]
        warns = health.check(jr.read(JOURNAL_F), c["spread_max_points"])
        if warns:
            out["health"] = warns

    # ---- gates + signal
    nw = news.gate(str(CAL_F), time.time(), c["news_before_min"], c["news_after_min"], c["calendar_max_age_h"])
    gate_list = []
    if snap and snap["ok"]:
        ctx = _gate_ctx(c, ph, snap, s, state, opens, nw, now, equity, kill, halt)
        gate_list = gates.blockers(ctx)
        out.update({"bias": snap["bias"], "atr": round(snap["atr"], 1), "spread": round(snap["spread"])})
        if ph["entry_ok"] and not gate_list and snap["signal"]:
            sig = snap["signal"]
            hit = _filter_hit(sig, snap, s, now)
            if hit:  # deterministic mined filter: skip without bothering Claude
                jr.append(JOURNAL_F, {"type": "pass", "signal_id": sig["id"], "reason": f"filter:{hit}"})
                out["filtered"] = hit
            else:
                out["signal"] = {k: (round(v, 2) if isinstance(v, float) else v) for k, v in sig.items()}
        elif ph["entry_ok"] and not gate_list:
            out["no_signal"] = snap["why"]
        if (not c["desk_mode"] and ph["entry_ok"] and not opens and not stop_loop and not ctx["risk_flag"]
                and now.timestamp() - s.get("last_headline_ts", s["start_ts"]) >= c["headline_check_min"] * 60):
            out["do"] = "; ".join(([out["do"]] if "do" in out else []) +
                                  ["headline check due: one WebSearch (USD/Nasdaq); then set_risk_flag('ok') if calm "
                                   "or set_risk_flag('block', reason) ONLY for a major unscheduled shock"])
    elif snap is not None:
        gate_list = ["no_data"]
    for g in gate_list:
        gc = s.setdefault("gate_counts", {})
        gc[g.split(":")[0]] = gc.get(g.split(":")[0], 0) + 1
    if gate_list:
        out["gates"] = gate_list
    if stop_loop:
        out["stop_loop"] = True
        out["why_stop"] = "kill" if kill else "halt" if halt else s["stop_reason"] or phase

    # ---- next wake
    if stop_loop:
        wake = None
        s["ended"], s["ended_ts"] = True, now.timestamp()
    elif phase == "BREAK":
        wake = min(3600, ph["next_boundary_s"] + 5)
    else:
        wake = clock.next_bar_close_s(now, c["tf_min"])
        if opens:
            wake = min(wake, 300)
            if ev and c["pre_event_exit"] and ev["in_s"] > c["pre_event_exit_min"] * 60:
                wake = min(wake, max(60, ev["in_s"] - c["pre_event_exit_min"] * 60 + 5))
        elif nw["blocked"] and nw["resume_s"]:
            wake = max(60, nw["resume_s"])
        elif phase == "MANAGE":
            wake = min(3600, ph["next_boundary_s"] + 5)
        wake = max(60, min(wake, ph["next_boundary_s"] + 5, 3600))
    out["next_wake_seconds"] = wake
    s["wake_due"] = now.timestamp() + wake if wake else None
    save_state(state)
    return out


_seen = {"bar": None, "event": None}  # wait_for_trigger memory (one server process = one symbol)
HARD_GATES = ("phase:", "KILL", "HALT", "stopped:", "not_demo", "market_closed", "stale_bars", "daily_stop", "desk_exposure")
WAIT_KEYS = ("t", "phase", "eq", "day_pct", "trades", "streak", "pos", "gates", "event_in_s", "event", "signal", "closed",
             "actions", "stop_loop", "why_stop", "last20", "lessons", "review_due", "health", "do", "bias", "atr",
             "spread", "report", "run_left_min", "filtered")


@mcp.tool()
async def wait_for_trigger(max_s: int = 45) -> dict:
    """Desk loop primitive: blocks (up to max_s, cap 55) while Python runs the full tick every ~3 s (reconcile, BE /
    partial / trail management, KILL / HALT / daily-stop flatten, run cap) and returns the moment something needs the
    agent: a closed trade, a Python action, stop_loop, a rule signal, an upcoming USD event, a new M1 bar while a
    position is open, or a scout hit on a fresh bar (impulse, range break, liquidity sweep). Otherwise trigger is
    ['quiet']. The tape being quiet costs the agent almost nothing; positions stay managed while it waits."""
    _ensure()
    t0, deadline = time.time(), time.time() + max(5, min(int(max_s), 55))
    while True:
        out = session_tick()
        c = cfg()
        why = [k for k in ("stop_loop", "do", "signal", "review_due") if out.get(k)]
        if out.get("closed"):
            why.append("closed")
        if out.get("actions"):
            why.append("actions")
        if not out.get("stop_loop") and out.get("phase") in ("ACTIVE", "MANAGE"):
            bar = mt5.copy_rates_from_pos(c["symbol"], TF_MT5[int(c["tf_min"])], 1, 1)
            bar_t = int(bar[0]["time"]) if bar is not None and len(bar) else None
            if bar_t is not None and bar_t != _seen["bar"]:
                first, _seen["bar"] = _seen["bar"] is None, bar_t
                if out.get("pos"):
                    why.append("pos_bar")
                if not first and not any(str(g).startswith(HARD_GATES) for g in out.get("gates", [])):
                    snap = snapshot(c)
                    if snap["ok"]:
                        why += sc.scout(snap["closed"], snap["atr"], c["scout_impulse_atr"], int(c["scout_break_bars"]))
            ev_in = out.get("event_in_s")
            if ev_in is not None and ev_in <= 300 and _seen["event"] != out.get("event"):
                _seen["event"] = out.get("event")
                why.append("event_soon")
        if why or time.time() >= deadline:
            res = {k: out[k] for k in WAIT_KEYS if k in out}
            res["trigger"] = why or ["quiet"]
            res["waited_s"] = round(time.time() - t0)
            return res
        await asyncio.sleep(3)


def _lessons():
    """Lessons for the trader. Lines tagged `SWING:` are leftovers from the removed swing book and are not shown."""
    lines = LESSONS_F.read_text().strip().splitlines() if LESSONS_F.exists() else []
    return "\n".join(x for x in lines if "swing:" not in x.lower())


@mcp.tool()
def desk_brief() -> dict:
    """Shift-start context for a trader agent: lessons, recent results (last 20 stats + last 8 exits), run counters,
    streak, active risk flag and regime. Call once at the start of each shift."""
    c = cfg()
    state = load_state()
    s = state.get("run") or {}
    exits = [r for r in jr.read(JOURNAL_F) if r.get("type") == "exit" and r.get("style", "scalp") == "scalp"]
    keys = ("side", "pattern", "outcome_r", "exit_reason", "dur_min", "mfe_r", "mae_r", "hour", "thesis")
    rf = s.get("risk_flag") or {}
    return {"symbol": c["symbol"], "lessons": _lessons(),
            "last20": jr.stats(exits[-20:], c["risk_pct"]), "recent": [{k: r.get(k) for k in keys} for r in exits[-8:]],
            "run_trades": s.get("trades", 0), "streak": s.get("consec_losses", 0), "regime": s.get("regime"),
            "risk_flag": rf if rf.get("level") == "block" and (rf.get("until_ts") or 0) > time.time() else None,
            "limits": {k: c[k] for k in ("risk_pct", "max_positions", "daily_stop_pct", "min_rr", "min_sl_atr",
                                         "max_sl_atr", "max_spread_r", "partial_at_r")}}


def _execute(c, state, s, snap, acct, now, nw, side, sl_raw, tp_raw, pattern, signal_id, risk_mult=1.0, extra=None):
    """Size, send and verify one trade (gates already checked by the caller). Shared by the rule-signal path
    (place_trade_checked) and the AI path (open_trade). Never raises the configured risk: risk_mult <= 1."""
    extra = extra or {}
    risk_pct, min_rr = c["risk_pct"], c["min_rr"]
    info, tick = snap["info"], snap["tick"]
    buy = side == "buy"
    entry = tick.ask if buy else tick.bid
    sl, d = round(sl_raw, info.digits), info.digits
    sl_dist = abs(entry - sl)
    if (buy and sl >= entry) or (not buy and sl <= entry) or sl_dist <= 0:
        return {"ok": False, "error": "sl_wrong_side_of_entry"}
    if tp_raw is None:
        tp = round(entry + c["tp_r"] * sl_dist if buy else entry - c["tp_r"] * sl_dist, d)
    else:
        tp = round(tp_raw, d)
        if (buy and tp <= entry) or (not buy and tp >= entry):
            return {"ok": False, "error": "tp_wrong_side_of_entry"}
    if abs(tp - entry) / sl_dist < min_rr:
        return {"ok": False, "error": "rr_below_min"}
    risk_money = acct.equity * risk_pct / 100 * risk_mult
    lots, why = risk.lots_for_risk(risk_money, sl_dist, info.trade_tick_size, info.trade_tick_value_loss,
                                   info.volume_min, info.volume_step, info.volume_max, c["max_lot"],
                                   c["min_lot_risk_mult"])
    if lots is None:
        return {"ok": False, "error": why}
    otype = mt5.ORDER_TYPE_BUY if buy else mt5.ORDER_TYPE_SELL
    margin = mt5.order_calc_margin(otype, c["symbol"], lots, entry)
    if margin is None or margin > acct.margin_free * c["margin_use_max"]:
        return {"ok": False, "error": f"margin_{margin}_vs_free_{acct.margin_free}"}

    plan = {"signal_id": signal_id, "side": side, "entry": entry, "sl": sl, "tp": tp, "lots": lots,
            "risk_money": round(risk_money, 2), "risk_pct": round(risk_pct * risk_mult, 3), "bias": snap["bias"],
            "atr": round(snap["atr"], 1), "spread": round(snap["spread"]), "pattern": pattern,
            "news": nw["reason"] or "clear", "hour": now.astimezone(clock.SAST).hour, "regime": s.get("regime"), **extra}
    if DRY:
        jr.append(JOURNAL_F, {"type": "dry_trade", **plan})
        return {"ok": True, "dry_run": True, **plan}

    req = {"action": mt5.TRADE_ACTION_DEAL, "symbol": c["symbol"], "volume": lots, "type": otype, "price": entry,
           "sl": sl, "tp": tp, "deviation": 30, "magic": c["magic"], "comment": "claude auto",
           "type_time": mt5.ORDER_TIME_GTC}
    r = _send(req)
    if r is None or r.retcode != mt5.TRADE_RETCODE_DONE:
        jr.append(JOURNAL_F, {"type": "error", "stage": "send", **plan, "retcode": getattr(r, "retcode", None)})
        return {"ok": False, "error": "send_failed", "detail": _result(r)}
    pos = None
    for _ in range(5):
        tracked = set(state["positions"])
        pos = next((p for p in _positions(c) if str(p.ticket) not in tracked), None)
        if pos:
            break
        time.sleep(0.4)
    tol = 3 * info.point
    if pos is None or abs(pos.sl - sl) > tol or abs(pos.tp - tp) > tol or abs(pos.volume - lots) > 1e-9:
        known = set(state["positions"])
        for p in _positions(c):
            if str(p.ticket) not in known:  # only the position this call opened, never an already-managed one
                _close(p, "claude mismatch")
        jr.append(JOURNAL_F, {"type": "error", "stage": "verify", **plan})
        return {"ok": False, "error": "verification_mismatch_closed"}
    r_dist = abs(pos.price_open - sl)
    state["positions"][str(pos.ticket)] = {"side": side, "entry": pos.price_open, "r_dist": r_dist,
                                           "risk_money": risk_money, "signal_id": signal_id, "lots": lots,
                                           **{k: plan[k] for k in ("pattern", "bias", "atr", "spread", "hour", "regime")},
                                           "thesis": extra.get("thesis"),
                                           "risk_pct": plan["risk_pct"], "opened_ts": time.time()}
    s["trades"] += 1
    state["last_signal_id"] = signal_id
    save_state(state)
    jr.append(JOURNAL_F, {"type": "trade", **plan, "ticket": pos.ticket, "fill": pos.price_open,
                          "slippage": round(abs(pos.price_open - entry) / info.point)})
    return {"ok": True, "ticket": pos.ticket, **plan, "fill": pos.price_open}


@mcp.tool()
def place_trade_checked(side: str, signal_id: str) -> dict:
    """Open the trade for the signal returned by session_tick. Re-validates every gate, sizes lots from
    risk_pct, sends with SL/TP, then verifies the fill; closes immediately on mismatch. side: buy|sell."""
    _ensure()
    c = cfg()
    now = datetime.now(timezone.utc)
    state = load_state()
    acct = mt5.account_info()
    roll_state(state, acct.equity, now)
    s = state.get("run")
    if not s or s.get("ended") or now.timestamp() - s["start_ts"] >= c["run_max_minutes"] * 60:
        return {"ok": False, "error": "no_active_run"}
    ph = clock.phase(now, c, now.timestamp() - s["start_ts"])
    snap = snapshot(c)
    if not snap["ok"]:
        return {"ok": False, "error": "no_data"}
    sig = snap["signal"]
    if not sig or sig["id"] != signal_id or sig["side"] != side:
        return {"ok": False, "error": "signal_changed_or_stale"}
    if state.get("last_signal_id") == signal_id:
        return {"ok": False, "error": "signal_already_traded"}
    nw = news.gate(str(CAL_F), time.time(), c["news_before_min"], c["news_after_min"], c["calendar_max_age_h"])
    opens = _positions(c)
    ctx = _gate_ctx(c, ph, snap, s, state, opens, nw, now, acct.equity,
                    (STATE_DIR / "KILL").exists(), (STATE_DIR / "HALT").exists())
    blk = gates.blockers(ctx)
    if blk:
        return {"ok": False, "error": "gated", "gates": blk}
    hit = _filter_hit(sig, snap, s, now)
    if hit:
        return {"ok": False, "error": "filtered", "filter": hit}

    return _execute(c, state, s, snap, acct, now, nw, side, sig["sl"], None, sig["pattern"], signal_id)


AI_SETUPS = ("pullback", "orb", "breakout", "reversal", "sweep", "trend", "other")


def _rates(c, tf, n=320):
    r = mt5.copy_rates_from_pos(c["symbol"], tf, 0, n)
    return None if r is None or len(r) < 60 else r[:-1]  # closed bars only


@mcp.tool()
def market_brief() -> dict:
    """AI analysis input: precomputed multi-timeframe brief (trend, EMA distances in ATR, RSI, momentum, previous-day
    and today's levels, VWAP, US-open range, last 12 M5 candles) plus the rule signal and open positions. Compact:
    never fetch raw candles for analysis."""
    _ensure()
    c = cfg()
    mt5.symbol_select(c["symbol"], True)
    tick, info = mt5.symbol_info_tick(c["symbol"]), mt5.symbol_info(c["symbol"])
    bars = [_rates(c, tf) for tf in (mt5.TIMEFRAME_M5, mt5.TIMEFRAME_M15, mt5.TIMEFRAME_H1, mt5.TIMEFRAME_H4)]
    if tick is None or info is None or any(b is None for b in bars):
        return {"ok": False, "error": "no_data"}
    m1 = _rates(c, mt5.TIMEFRAME_M1, 120) if c["tf_min"] == 1 else None
    out = brief.build(*bars, tick.bid, tick.ask, time.time(), info.digits, m1)
    snap = snapshot(c)
    out["symbol"] = c["symbol"]
    out["rule_signal"] = ({k: (round(v, 2) if isinstance(v, float) else v) for k, v in snap["signal"].items()}
                          if snap.get("ok") and snap["signal"] else snap.get("why"))
    state = load_state()
    out["pos"] = _pos_view(state, c, snap) if snap.get("ok") else []
    ev = news.next_event(str(CAL_F), time.time(), 120)
    if ev:
        out["event_in_s"], out["event"] = ev["in_s"], ev["title"]
    return out


@mcp.tool()
def open_trade(side: str, sl: float, tp: float, setup: str, thesis: str, risk_mult: float = 1.0,
               override: str = "") -> dict:
    """AI-originated entry. You choose side, stop and target from market_brief; code enforces everything else: the same
    gates as rule trades (phase, news, spread, ATR band, position/trade/loss limits, daily stop, risk flag, KILL/HALT),
    stop on the correct side and between min_sl_atr and max_sl_atr x ATR, reward:risk >= min_rr, lots sized from risk_pct
    x risk_mult (0.25-1.0: scale DOWN for lower conviction, never up), margin check, fill verification. One AI entry per
    side per bar. setup in pullback|orb|breakout|reversal|sweep|trend|other; thesis <=200 chars (why now, what
    invalidates it) is stored on the trade for the learning review.
    override: comma list of SOFT gates you choose to bypass for this trade (atr, spread, news, risk_flag, consec_losses,
    position_open [max +2], max_trades [max 2x]); logged with your thesis. Never bypassable: demo check, KILL/HALT, daily
    stop, closed market, stale data, break/flatten phases, margin, stop-on-correct-side."""
    _ensure()
    c = cfg()
    now = datetime.now(timezone.utc)
    ovr = [x.strip() for x in override.split(",") if x.strip()]
    if any(x not in gates.OVERRIDABLE for x in ovr):
        return {"ok": False, "error": f"override must be from {gates.OVERRIDABLE}"}
    if side not in ("buy", "sell") or setup not in AI_SETUPS or not thesis.strip() or not (0.25 <= risk_mult <= 1.0):
        return {"ok": False, "error": f"bad_args (side buy|sell, setup in {AI_SETUPS}, thesis required, risk_mult 0.25-1)"}
    state = load_state()
    acct = mt5.account_info()
    roll_state(state, acct.equity, now)
    s = state.get("run")
    if not s or s.get("ended") or now.timestamp() - s["start_ts"] >= c["run_max_minutes"] * 60:
        return {"ok": False, "error": "no_active_run"}
    ph = clock.phase(now, c, now.timestamp() - s["start_ts"])
    snap = snapshot(c)
    if not snap["ok"]:
        return {"ok": False, "error": "no_data"}
    sid = f"ai-{c['symbol']}-{int(snap['closed'][-1]['time'])}-{side}"
    if state.get("last_signal_id") == sid:
        return {"ok": False, "error": "already_traded_this_bar"}
    nw = news.gate(str(CAL_F), time.time(), c["news_before_min"], c["news_after_min"], c["calendar_max_age_h"])
    ctx = _gate_ctx(c, ph, snap, s, state, _positions(c), nw, now, acct.equity,
                    (STATE_DIR / "KILL").exists(), (STATE_DIR / "HALT").exists())
    blk = gates.blockers(gates.apply_overrides(ctx, ovr))
    if blk:
        return {"ok": False, "error": "gated", "gates": blk}
    if ovr:
        jr.append(JOURNAL_F, {"type": "override", "signal_id": sid, "gates": ovr, "thesis": thesis.strip()[:200]})
    hit = _filter_hit({"side": side, "pattern": "ai-" + setup}, snap, s, now)
    if hit:
        return {"ok": False, "error": "filtered", "filter": hit}
    entry = snap["tick"].ask if side == "buy" else snap["tick"].bid
    dist = abs(entry - sl)
    if "atr" not in ovr and not (c["min_sl_atr"] * snap["atr"] <= dist <= c["max_sl_atr"] * snap["atr"]):
        return {"ok": False, "error": f"sl_dist_{dist:.2f}_outside_{c['min_sl_atr']}-{c['max_sl_atr']}_atr({snap['atr']:.2f})"}
    spread_px = snap["tick"].ask - snap["tick"].bid
    if c["max_spread_r"] and "spread" not in ovr and spread_px > c["max_spread_r"] * dist:  # scalp cost guard: spread must be a small slice of R
        return {"ok": False, "error": f"spread_{spread_px:.2f}_exceeds_{c['max_spread_r']}R_of_stop_{dist:.2f}"}
    return _execute(c, state, s, snap, acct, now, nw, side, sl, tp, "ai-" + setup, sid, risk_mult,
                    {"thesis": thesis.strip()[:200], "ai": True})


@mcp.tool()
def adjust_position(ticket: int, action: str, value: float = 0.0, why: str = "") -> dict:
    """AI position management on a bot position. action: 'tighten_sl' (value = new stop; must be strictly closer to price
    than the current stop, on the protective side of price and beyond the broker stop level: a stop is NEVER widened or
    removed), 'widen_sl' (once per position, <=1.5x original risk, state your reason in why), 'set_tp' (move target),
    'partial' (value = fraction 0.1-0.9 to close), 'close' (exit now). Automatic BE/trail/partial/pre-event
    logic keeps running underneath."""
    return _adjust(ticket, action, value, why)


def _adjust(ticket, action, value, why):
    _ensure()
    c = cfg()
    p = next((x for x in _positions(c) if x.ticket == ticket), None)
    if p is None:
        return {"ok": False, "error": "no_such_bot_position"}
    state = load_state()
    rec = state["positions"].get(str(ticket))
    if rec is None:
        return {"ok": False, "error": "untracked_position"}
    info, tick = mt5.symbol_info(p.symbol), mt5.symbol_info_tick(p.symbol)
    buy = p.type == mt5.POSITION_TYPE_BUY
    if action == "tighten_sl":
        price = tick.bid if buy else tick.ask
        new = round(value, info.digits)
        gap = max(info.trade_stops_level, 1) * info.point
        if (buy and not (p.sl < new <= price - gap)) or (not buy and not (price + gap <= new < p.sl)):
            return {"ok": False, "error": f"sl_must_tighten_and_respect_stop_level (cur {p.sl}, price {price})"}
        res = _result(mt5.order_send({"action": mt5.TRADE_ACTION_SLTP, "position": ticket, "symbol": p.symbol,
                                      "sl": new, "tp": p.tp}))
        ok, detail = res["ok"], {"sl": new}
    elif action == "widen_sl":  # discretionary: once per position, at most 1.5x the original risk distance
        price = tick.bid if buy else tick.ask
        new = round(value, info.digits)
        if rec.get("widened") or not risk.widen_ok(rec["side"], rec["entry"], p.sl, new, rec["r_dist"], price):
            return {"ok": False, "error": "widen allowed once, wider than current, <=1.5x original risk, protective side"}
        res = _result(mt5.order_send({"action": mt5.TRADE_ACTION_SLTP, "position": ticket, "symbol": p.symbol,
                                      "sl": new, "tp": p.tp}))
        ok, detail = res["ok"], {"sl": new}
        if ok:
            rec["widened"] = True
    elif action == "set_tp":  # move the target either way (the stop is untouched)
        price = tick.bid if buy else tick.ask
        new = round(value, info.digits)
        if (buy and new <= price) or (not buy and new >= price):
            return {"ok": False, "error": "tp must be beyond current price in the profit direction"}
        res = _result(mt5.order_send({"action": mt5.TRADE_ACTION_SLTP, "position": ticket, "symbol": p.symbol,
                                      "sl": p.sl, "tp": new}))
        ok, detail = res["ok"], {"tp": new}
    elif action == "partial":
        if not (0.1 <= value <= 0.9):
            return {"ok": False, "error": "fraction 0.1-0.9"}
        vol = risk.partial_close_lots(p.volume, value, info.volume_min, info.volume_step)
        if vol <= 0:
            return {"ok": False, "error": "too_small_to_split"}
        r = _send({"action": mt5.TRADE_ACTION_DEAL, "position": ticket, "symbol": p.symbol, "volume": vol,
                   "type": mt5.ORDER_TYPE_SELL if buy else mt5.ORDER_TYPE_BUY,
                   "price": tick.bid if buy else tick.ask, "deviation": 30, "magic": p.magic, "comment": "claude ai partial"})
        ok, detail = bool(r and r.retcode == mt5.TRADE_RETCODE_DONE), {"lots": vol}
        if ok:
            rec["partial_done"] = True
    elif action == "close":
        rec["closed_by"] = "ai"
        r = _close(p, "claude ai close")
        ok, detail = bool(r and r.retcode == mt5.TRADE_RETCODE_DONE), {}
    else:
        return {"ok": False, "error": "action must be tighten_sl|widen_sl|set_tp|partial|close"}
    save_state(state)
    jr.append(JOURNAL_F, {"type": "ai_adjust", "ticket": ticket, "action": action, "value": value, "ok": ok,
                          "why": why[:160]})
    return {"ok": ok, "action": action, **detail}


@mcp.tool()
def flatten_all(reason: str = "manual") -> dict:
    """Close all bot positions (magic) and cancel its pending orders."""
    _ensure()
    return {"actions": flatten(cfg(), reason)}


@mcp.tool()
def journal_pass(reason: str, signal_id: str = "") -> dict:
    """Log a setup that was considered and skipped (keep reason short)."""
    jr.append(JOURNAL_F, {"type": "pass", "signal_id": signal_id, "reason": reason[:200]})
    return {"ok": True}


@mcp.tool()
def session_summary(n: int = 20) -> dict:
    """Stats over the last n closed trades."""
    c = cfg()
    ex = [r for r in jr.read(JOURNAL_F) if r.get("type") == "exit"][-n:]
    return jr.stats(ex, c["risk_pct"])


@mcp.tool()
def review() -> dict:
    """Learning review (call only when session_tick says it is due). Returns compact stats: overall,
    breakdown by side/pattern/bias/hour/ATR/spread, exit mix, MFE/MAE diagnostics, flagged buckets, the
    live-graduation check and recent errors. Hypotheses only; never a reason to change rules directly."""
    c = cfg()
    recs = jr.read(JOURNAL_F)
    exits = [r for r in recs if r.get("type") == "exit"]
    st = jr.stats(recs, c["risk_pct"])
    state = load_state()
    state["last_review_n"] = len(exits)
    save_state(state)
    return {"stats": st, "graduation": jr.graduation(st), "analysis": rv.analyze(exits),
            "lessons_now": LESSONS_F.read_text().strip() if LESSONS_F.exists() else "",
            "errors": [{k: r.get(k) for k in ("stage", "signal_id", "retcode")} for r in recs
                       if r.get("type") == "error"][-3:]}


@mcp.tool()
def set_lessons(lines: list[str]) -> dict:
    """Replace the lessons file (max 25 lines, each <=220 chars, each must start with '[n=<sample>, ...]').
    Merge new insight into existing lines, drop stale ones. Lessons are advisory: they may justify passing on a
    setup only when n>=20; they never override gates or hard rules."""
    if len(lines) > MAX_LESSONS:
        return {"ok": False, "error": f"max {MAX_LESSONS} lines; merge or drop some"}
    for ln in lines:
        if len(ln) > 220 or not ln.startswith("[n="):
            return {"ok": False, "error": f"bad line (<=220 chars, must start '[n=..]'): {ln[:40]}"}
    STATE_DIR.mkdir(exist_ok=True)
    LESSONS_F.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return {"ok": True, "lines": len(lines)}


@mcp.tool()
def propose_change(text: str) -> dict:
    """Queue a suggested rule/parameter change for the USER to review (state/proposals.md). Cite evidence
    (sample size, expectancy). Claude never applies changes to config itself."""
    STATE_DIR.mkdir(exist_ok=True)
    with open(PROPOSALS_F, "a", encoding="utf-8") as f:
        f.write(f"- {time.strftime('%Y-%m-%d')}: {text[:300]}\n")
    return {"ok": True}


@mcp.tool()
def annotate_trade(ticket: int, note: str) -> dict:
    """Attach a one-line qualitative note (<=160 chars) to a closed trade. Use sparingly (|R|>=1 or odd exits)."""
    jr.append(JOURNAL_F, {"type": "note", "ticket": ticket, "note": note[:160]})
    return {"ok": True}


@mcp.tool()
def set_risk_flag(level: str, reason: str = "", minutes: int = 30, regime: str = "") -> dict:
    """Headline check result (call when session_tick says a headline check is due). level 'ok' = checked, calm
    (clears any flag); level 'block' = major UNSCHEDULED shock (emergency Fed action, geopolitical event): blocks
    NEW entries for `minutes` (max 60). Veto-only: never touches open positions or stops. regime (optional, one of
    trend|chop|news|post-event) is stored on later trades for the learning review."""
    state = load_state()
    s = state.get("run")
    if not s or s.get("ended"):
        return {"ok": False, "error": "no_active_run"}
    if level not in ("ok", "block"):
        return {"ok": False, "error": "level must be ok|block"}
    now = time.time()
    s["last_headline_ts"] = now
    if regime in ("trend", "chop", "news", "post-event"):
        s["regime"] = regime
    if level == "block":
        s["risk_flag"] = {"level": "block", "reason": (reason or "headline")[:40].replace(":", "-"),
                          "until_ts": now + max(1, min(int(minutes), 60)) * 60}
    else:
        s["risk_flag"] = {"level": "ok"}
    save_state(state)
    jr.append(JOURNAL_F, {"type": "risk_flag", "level": level, "reason": reason[:120], "regime": regime or None})
    return {"ok": True, "level": level, "regime": s.get("regime")}


@mcp.tool()
def deep_review() -> dict:
    """Offline-style deeper analysis (use after review() when flags exist, or on request): two-feature
    interaction buckets with bootstrap confidence intervals, and CANDIDATE entry filters that pass strict
    evidence tests (n>=30, 95% CI below zero, both halves negative). Returns compact summaries only and writes
    reports/mining-<date>.md. Candidates are NOT applied: put them to the user with propose_change; the user
    runs tools/mine.py --apply to install state/filters.json."""
    c = cfg()
    exits = [r for r in jr.read(JOURNAL_F) if r.get("type") == "exit" and r.get("outcome_r") is not None]
    if len(exits) < 20:
        return {"n": len(exits), "note": "need >=20 closed trades for a deeper review"}
    an = rv.analyze(exits, 8)
    flagged = {k: {**v, "ci": rv.ci([e["outcome_r"] for e in exits if k in rv_keys(e)])}
               for k, v in an["interactions"].items() if abs(v["exp"]) >= 0.4}
    cand = rv.candidate_filters(exits)
    REPORTS_DIR.mkdir(exist_ok=True)
    rp = REPORTS_DIR / f"mining-{time.strftime('%Y-%m-%d')}.md"
    body = {"stats": jr.stats(exits, c["risk_pct"]), "interactions": an["interactions"], "candidates": cand}
    rp.write_text("# Mining\n\n" + json.dumps(body, indent=1), encoding="utf-8")
    return {"n": len(exits), "interactions_flagged": flagged, "candidate_filters": cand,
            "active_filters": flt.load(str(FILTERS_F)), "report": f"reports/{rp.name}",
            "note": "candidates are proposals; samples under 30 never qualify"}


def rv_keys(e):
    f = rv._feats(e)
    return {f"{a}={f[a]}&{b}={f[b]}" for a, b in rv.PAIRS if f.get(a) is not None and f.get(b) is not None}


@mcp.tool()
def health_report() -> dict:
    """Drift/health warnings from the journal (slippage, entry spread, win-rate drift, repeated errors, MAE shift)."""
    c = cfg()
    return {"warnings": health.check(jr.read(JOURNAL_F), c["spread_max_points"]) or ["ok"]}


# ---------------------------------------------------------------- manual tools
@mcp.tool()
def account_info() -> dict:
    """Account login, server, balance, equity, margin, leverage, demo flag, and whether trading is allowed."""
    _ensure()
    a = mt5.account_info()
    t = mt5.terminal_info()
    d = a._asdict() if a else {}
    d["terminal_trade_allowed"] = t.trade_allowed if t else None
    d["is_demo"] = bool(a) and a.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO
    return d


@mcp.tool()
def get_price(symbol: str) -> dict:
    """Current bid/ask and spread for a symbol (e.g. USTECm, XAUUSDm)."""
    _ensure()
    if not mt5.symbol_select(symbol, True):
        return {"error": f"unknown symbol {symbol}"}
    tick = mt5.symbol_info_tick(symbol)
    info = mt5.symbol_info(symbol)
    return {"symbol": symbol, "bid": tick.bid, "ask": tick.ask, "spread_points": info.spread,
            "volume_min": info.volume_min, "volume_step": info.volume_step,
            "time": datetime.fromtimestamp(tick.time).isoformat()}


@mcp.tool()
def search_symbols(pattern: str = "*") -> list[str]:
    """List symbol names matching a wildcard, e.g. '*USD*' or 'XAU*'."""
    _ensure()
    return [s.name for s in (mt5.symbols_get(pattern) or [])][:100]


@mcp.tool()
def get_rates(symbol: str, timeframe: str = "H1", count: int = 50) -> list[dict]:
    """Recent OHLCV candles. timeframe: M1 M5 M15 M30 H1 H4 D1 W1."""
    _ensure()
    tf = getattr(mt5, f"TIMEFRAME_{timeframe.upper()}", None)
    if tf is None:
        raise ValueError("bad timeframe")
    rates = mt5.copy_rates_from_pos(symbol, tf, 0, min(count, 500))
    if rates is None:
        return []
    return [{"time": datetime.fromtimestamp(int(r["time"])).isoformat(), "open": float(r["open"]),
             "high": float(r["high"]), "low": float(r["low"]), "close": float(r["close"]),
             "volume": int(r["tick_volume"])} for r in rates]


@mcp.tool()
def positions(symbol: str = "") -> list[dict]:
    """Open positions, optionally filtered by symbol."""
    _ensure()
    ps = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
    return [p._asdict() for p in (ps or [])]


@mcp.tool()
def pending_orders(symbol: str = "") -> list[dict]:
    """Pending (limit/stop) orders."""
    _ensure()
    os_ = mt5.orders_get(symbol=symbol) if symbol else mt5.orders_get()
    return [o._asdict() for o in (os_ or [])]


@mcp.tool()
def place_order(symbol: str, side: str, volume: float, sl: float = 0.0, tp: float = 0.0,
                price: float = 0.0, comment: str = "claude") -> dict:
    """MANUAL ONLY (not for the autonomous loop). side: buy|sell, or buy_limit|sell_limit|buy_stop|sell_stop
    (needs price). sl/tp absolute prices (0 = none). Volume capped at MT5_MAX_LOT (default 0.10)."""
    _ensure()
    if volume > MAX_LOT:
        return {"ok": False, "error": f"volume {volume} exceeds safety cap {MAX_LOT} (set MT5_MAX_LOT to change)"}
    if not is_demo():
        return {"ok": False, "error": "not a demo account and live_enabled is false"}
    if not mt5.symbol_select(symbol, True):
        return {"ok": False, "error": f"unknown symbol {symbol}"}
    tick = mt5.symbol_info_tick(symbol)
    types = {
        "buy": (mt5.ORDER_TYPE_BUY, tick.ask, mt5.TRADE_ACTION_DEAL),
        "sell": (mt5.ORDER_TYPE_SELL, tick.bid, mt5.TRADE_ACTION_DEAL),
        "buy_limit": (mt5.ORDER_TYPE_BUY_LIMIT, price, mt5.TRADE_ACTION_PENDING),
        "sell_limit": (mt5.ORDER_TYPE_SELL_LIMIT, price, mt5.TRADE_ACTION_PENDING),
        "buy_stop": (mt5.ORDER_TYPE_BUY_STOP, price, mt5.TRADE_ACTION_PENDING),
        "sell_stop": (mt5.ORDER_TYPE_SELL_STOP, price, mt5.TRADE_ACTION_PENDING),
    }
    if side not in types:
        return {"ok": False, "error": f"bad side {side}"}
    otype, px, action = types[side]
    if action == mt5.TRADE_ACTION_PENDING and price <= 0:
        return {"ok": False, "error": "pending order needs price"}
    return _result(_send({"action": action, "symbol": symbol, "volume": volume, "type": otype, "price": px,
                          "sl": sl, "tp": tp, "deviation": 20, "magic": 20260101, "comment": comment,
                          "type_time": mt5.ORDER_TIME_GTC}))


@mcp.tool()
def modify_position(ticket: int, sl: float = 0.0, tp: float = 0.0) -> dict:
    """MANUAL ONLY. Set stop loss / take profit (absolute prices) on an open position."""
    _ensure()
    p = mt5.positions_get(ticket=ticket)
    if not p:
        return {"ok": False, "error": "position not found"}
    return _result(mt5.order_send({"action": mt5.TRADE_ACTION_SLTP, "position": ticket,
                                   "symbol": p[0].symbol, "sl": sl, "tp": tp}))


@mcp.tool()
def close_position(ticket: int) -> dict:
    """Close an open position by ticket."""
    _ensure()
    p = mt5.positions_get(ticket=ticket)
    if not p:
        return {"ok": False, "error": "position not found"}
    return _result(_close(p[0]))


@mcp.tool()
def cancel_order(ticket: int) -> dict:
    """MANUAL ONLY. Cancel a pending order by ticket."""
    _ensure()
    return _result(mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": ticket}))


if __name__ == "__main__":
    mcp.run()
