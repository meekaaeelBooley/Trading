"""Broker / terminal readiness check. Read-only: it never places an order.

    .venv\\Scripts\\python.exe tools\\check_broker.py [--symbol US100]

Reads the per-machine settings from `.mcp.json` (server `ustec`: MT5_PATH, TRADING_SYMBOL, BROKER_UTC_OFFSET_H) unless they are already in the
environment, connects to the running MetaTrader 5 terminal and prints a PASS / WARN / FAIL checklist. Exit code 1 if anything FAILs.
Works the same for Exness, XM or any other MT5 broker: it reports what it sees and what to change.
"""
import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

ap = argparse.ArgumentParser()
ap.add_argument("--symbol", help="Nasdaq symbol to test (default: TRADING_SYMBOL from .mcp.json, else config.ustec.json)")
ap.add_argument("--list", action="store_true", help="only print the Nasdaq-like symbols on the connected broker, one per line (used by setup.ps1)")
args = ap.parse_args()

# per-machine settings: .mcp.json -> environment (unless already set), before importing the server module
os.environ.setdefault("TRADING_CONFIG", "config.ustec.json")
os.environ.setdefault("TRADING_STATE", "state-ustec")
try:
    for k, v in (json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8-sig"))["mcpServers"]["ustec"].get("env") or {}).items():
        os.environ.setdefault(k, str(v))
except Exception:
    pass
if args.symbol:
    os.environ["TRADING_SYMBOL"] = args.symbol

import MetaTrader5 as mt5  # noqa: E402

import mt5_server as s  # noqa: E402
from engine import playbook as pb  # noqa: E402

fails = warns = 0


def line(level, msg):
    global fails, warns
    fails += level == "FAIL"
    warns += level == "WARN"
    print(f"[{level}] {msg}")


def candidates():
    names = []
    for pat in ("*USTEC*", "*US100*", "*NAS100*", "*NDX*", "*NASDAQ*", "*NQ100*", "*TECH100*"):
        names += [x.name for x in (mt5.symbols_get(pat) or [])]
    return sorted(set(names))


def main():
    c = s.cfg()
    sym = c["symbol"]
    try:
        s._ensure()
    except Exception as e:  # noqa: BLE001
        line("FAIL", f"cannot connect to MetaTrader 5: {e}")
        print("      Start the terminal, log in to your DEMO account, then retry. If you have several terminals, set MT5_PATH in .mcp.json.")
        return
    t, a = mt5.terminal_info(), mt5.account_info()
    line("PASS", f"terminal connected: {t.name} (build {t.build}) at {t.path}")
    if not a:
        line("FAIL", "terminal is not logged in to any account (log in to your demo account)")
        return
    line("PASS", f"account {a.login} on server '{a.server}' ({a.company}), {a.currency}, balance {a.balance:,.2f}, leverage 1:{a.leverage}")
    if a.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO:
        line("PASS", "account is a DEMO account")
    else:
        line("FAIL", "account is NOT a demo account - the desk refuses to trade (not_demo). Log in to a demo account.")
    if t.trade_allowed:
        line("PASS", "Algo Trading is enabled in the terminal")
    else:
        line("FAIL", "Algo Trading is OFF: click the 'Algo Trading' button in the MT5 toolbar so it turns green")
    if not a.trade_allowed:
        line("WARN", "the account itself reports trading as not allowed (broker/server restriction)")

    # ---- symbol
    info = mt5.symbol_info(sym)
    if info is None:
        line("FAIL", f"symbol '{sym}' does not exist on this broker")
        names = candidates()
        print("      Nasdaq-like symbols on this server: " + (", ".join(names[:20]) if names else "none found (open Market Watch > right-click > Symbols)"))
        print("      Set the right one with TRADING_SYMBOL in .mcp.json (or rerun tools\\setup.ps1).")
        return
    mt5.symbol_select(sym, True)
    line("PASS", f"symbol '{sym}' found ({info.description})")
    if pb.instrument_class(sym) == "index":
        line("PASS", "symbol name is recognised as a Nasdaq index (USTEC / US100 / NAS100 / NDX)")
    else:
        line("WARN", f"'{sym}' is not recognised as a Nasdaq index by the playbook (needs a name starting USTEC, US100, NAS100 or NDX): "
                     "no trend_day signal will ever fire")
    if info.trade_mode != mt5.SYMBOL_TRADE_MODE_FULL:
        line("FAIL", f"trading on {sym} is not fully enabled (trade_mode={info.trade_mode}); the market may be closed or restricted")
    line("PASS", f"contract size {info.trade_contract_size}, digits {info.digits}, min lot {info.volume_min}, lot step {info.volume_step}, "
                 f"max lot {info.volume_max}, stops level {info.trade_stops_level} pts")
    margin = mt5.order_calc_margin(mt5.ORDER_TYPE_BUY, sym, info.volume_min, info.ask or 1.0)
    if margin is not None and margin > a.balance * c["margin_use_max"]:
        line("FAIL", f"the minimum lot needs {margin:,.2f} {a.currency} margin, more than {c['margin_use_max']:.0%} of your balance")
    elif margin is not None:
        line("PASS", f"minimum lot margin {margin:,.2f} {a.currency}")

    # ---- time / data
    tick = mt5.symbol_info_tick(sym)
    if tick is None:
        line("FAIL", "no tick for the symbol (is it visible in Market Watch?)")
        return
    age = time.time() - tick.time
    ts = s._tick_ts(tick)
    off = s._bt_state()["off"]
    live = abs(time.time() - ts) <= c["tick_stale_s"] and off is not None
    if os.environ.get("BROKER_UTC_OFFSET_H", "").strip():
        line("PASS", f"broker UTC offset pinned by BROKER_UTC_OFFSET_H = {os.environ['BROKER_UTC_OFFSET_H']} h")
    elif live:
        line("PASS", f"live tick; broker server time is UTC{(off or 0) / 3600:+.0f} (detected automatically, converted to real UTC internally)")
    elif off is not None:
        line("WARN", f"market looks closed (last tick {abs(age) / 3600:.1f} h from now); using the saved broker offset UTC{off / 3600:+.0f}")
    else:
        line("WARN", "market looks closed, so the broker's server-time offset could not be detected. Rerun this check while the market is open "
                     "(or set BROKER_UTC_OFFSET_H in .mcp.json: 0 for Exness-style UTC servers, 2 or 3 for GMT+2/+3 servers)")
    sp = (tick.ask - tick.bid) / info.point if info.point else 0
    line("PASS", f"bid {tick.bid} / ask {tick.ask}, spread {sp:.0f} points")
    snap = s.snapshot(c)
    if snap.get("ok"):
        line("PASS", f"history OK (M5/H1/H4 bars loaded); market_open={snap['market_open']}, data_fresh={snap['data_fresh']}")
        if live and not snap["market_open"]:
            line("FAIL", "ticks are live but the server still reports market_open=False (time offset problem)")
    else:
        line("FAIL", "not enough price history (need >= 120 bars of M5, H1, H4). In MT5 open the symbol's M5/H1/H4 charts once and scroll back "
                     "to download history, then rerun")

    # ---- order filling modes (informational: the server tries IOC, FOK, then RETURN)
    fm = info.filling_mode
    modes = [n for bit, n in ((1, "FOK"), (2, "IOC")) if fm & bit] or ["RETURN"]
    line("PASS", f"order filling modes offered by the broker: {', '.join(modes)} (the desk tries each automatically)")

    # ---- economic calendar feed
    try:
        with urllib.request.urlopen(urllib.request.Request(c["calendar_url"], headers={"User-Agent": "desk-check"}), timeout=8) as r:
            line("PASS", f"news calendar feed reachable (HTTP {r.status})")
    except Exception as e:  # noqa: BLE001
        line("WARN", f"news calendar feed not reachable ({type(e).__name__}); the desk falls back to a stale cache and may refuse trades near news")


if args.list:
    try:
        s._ensure()
        print(chr(10).join(candidates()))
    except Exception as e:  # noqa: BLE001
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
    sys.exit(0)
main()
print()
print(f"{fails} FAIL, {warns} WARN" + ("  -> fix the FAIL lines above, then rerun." if fails else "  -> ready: open Claude Code here and run /desk"))
sys.exit(1 if fails else 0)
