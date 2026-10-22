r"""Download M5 history (with per-bar spread) for any symbols into data/<symbol>_m5.npz (read-only MT5 calls).

  .venv\Scripts\python.exe tools\fetch_m5.py XAUUSDm AAPLm NVDAm --months 6
"""
import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import MetaTrader5 as mt5
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
TERMINAL = os.environ.get("MT5_PATH", r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe")


def fetch(sym, start, end, chunk_days=20):
    parts, t = [], start
    while t < end:
        t2 = min(t + timedelta(days=chunk_days), end)
        r = mt5.copy_rates_range(sym, mt5.TIMEFRAME_M5, t, t2)
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
    ap.add_argument("symbols", nargs="+")
    ap.add_argument("--months", type=float, default=6)
    a = ap.parse_args()
    if not mt5.initialize(path=TERMINAL):
        sys.exit(f"MT5 initialize failed: {mt5.last_error()}")
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=int(a.months * 30.5))
    (ROOT / "data").mkdir(exist_ok=True)
    for sym in a.symbols:
        mt5.symbol_select(sym, True)
        info = mt5.symbol_info(sym)
        if info is None:
            print(sym, "not found")
            continue
        r = fetch(sym, start, end)
        if r is None:
            print(sym, "no data")
            continue
        np.savez_compressed(ROOT / "data" / f"{sym}_m5.npz", point=info.point, tick_size=info.trade_tick_size,
                            tick_value=info.trade_tick_value_loss, contract=info.trade_contract_size,
                            **{k: r[k] for k in ("time", "open", "high", "low", "close", "tick_volume", "spread")})
        print(f"{sym}: {len(r)} bars, {datetime.fromtimestamp(r['time'][0], timezone.utc):%Y-%m-%d} -> "
              f"{datetime.fromtimestamp(r['time'][-1], timezone.utc):%Y-%m-%d}, point={info.point}, "
              f"median spread={np.median(r['spread']):.0f}pt")
    mt5.shutdown()


if __name__ == "__main__":
    main()
