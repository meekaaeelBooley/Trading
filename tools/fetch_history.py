r"""Download M1/M15/H1/H4 history for the configured symbol into data/<symbol>.npz (read-only MT5 calls).

  .venv\Scripts\python.exe tools\fetch_history.py --months 8
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import MetaTrader5 as mt5
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine import backtest as bt  # noqa: E402

TERMINAL = os.environ.get("MT5_PATH", r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe")
TF = {"m1": mt5.TIMEFRAME_M1, "m5": mt5.TIMEFRAME_M5, "m15": mt5.TIMEFRAME_M15, "h1": mt5.TIMEFRAME_H1, "h4": mt5.TIMEFRAME_H4}


def fetch(sym, tf, start, end, chunk_days):
    parts, t = [], start
    while t < end:
        t2 = min(t + timedelta(days=chunk_days), end)
        r = mt5.copy_rates_range(sym, tf, t, t2)
        if r is not None and len(r):
            parts.append(r)
        t = t2
    if not parts:
        return None
    a = np.concatenate(parts)
    _, idx = np.unique(a["time"], return_index=True)
    return a[idx]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=float, default=8)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    cfg = json.loads((ROOT / "config.json").read_text())
    sym = cfg["symbol"]
    if not mt5.initialize(path=TERMINAL):
        sys.exit(f"MT5 initialize failed: {mt5.last_error()}")
    mt5.symbol_select(sym, True)
    info = mt5.symbol_info(sym)
    if info is None:
        sys.exit(f"symbol {sym} not found")
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=int(a.months * 30.5))
    data = {"point": float(info.point)}
    for name, tf in TF.items():
        # H1/H4 get extra lead-in so the EMA200 trend filters are warm at the start of the test window
        s0 = start - timedelta(days=75 if name in ("h1", "h4", "m15") else 0)
        r = fetch(sym, tf, s0, end, 5 if name == "m1" else 20 if name == "m5" else 60)
        if r is None:
            if name in ("m1", "m5"):
                print(f"{name}: no data (skipped)")
                continue
            sys.exit(f"no {name} data returned (broker history limit?)")
        data[name] = {k: r[k] for k in ("time", "open", "high", "low", "close", "spread")}
        print(f"{name}: {len(r)} bars")
    out = Path(a.out or ROOT / "data" / f"{sym}.npz")
    out.parent.mkdir(exist_ok=True)
    bt.save(str(out), data)
    print("saved", out)
    mt5.shutdown()


if __name__ == "__main__":
    main()
