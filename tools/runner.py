r"""Headless runner: the same session_tick / place_trade_checked logic, no LLM.

  .venv\Scripts\python.exe tools\runner.py [--dry-run]

Rule-only: every signal that clears the gates (and state/filters.json) is taken; there is no headline search,
so run-start / headline / review prompts are ignored. Same 2h cap, break handling, KILL/HALT and demo gate.
Ctrl+C stops the loop; any open position keeps its broker-side SL/TP but is no longer managed.
"""
import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if a.dry_run:
        os.environ["DRY_RUN"] = "1"
    import mt5_server as s  # after DRY_RUN is set; the module reads it at import

    errors = 0
    while True:
        try:
            t = s.session_tick()
            errors = 0
        except Exception as e:
            errors += 1
            print("tick error:", e)
            if errors >= 3:
                print("3 consecutive errors: stopping")
                return
            time.sleep(60)
            continue
        print({k: t.get(k) for k in ("t", "phase", "eq", "trades", "gates", "no_signal", "signal", "filtered",
                                       "closed", "health", "report")})
        sig = t.get("signal")
        if sig and not t.get("stop_loop"):
            print("trade:", s.place_trade_checked(sig["side"], sig["id"]))
        if t.get("stop_loop"):
            print("stop:", t.get("why_stop"))
            return
        time.sleep(max(60, t.get("next_wake_seconds") or 60))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("interrupted: open positions are no longer managed (use flatten_all or state/KILL)")
