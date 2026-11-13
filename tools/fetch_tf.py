r"""Download M5/M15/H1/D1 history (chunked, with spread) for XAUUSDm + USTECm into data/<sym>_tf.npz (read-only MT5 calls).

  .venv\Scripts\python.exe tools\fetch_tf.py [--symbols XAUUSDm USTECm] [--years 12]
Needs MT5 `Max bars in chart` = Unlimited (Tools > Options > Charts, restart); with the old 100k cap M5 reached back only
17-20 months. Now XAUUSDm M5 reaches 2014 and USTECm M5 mid-2023 (the broker's own depth). Uses copy_rates_from_pos: a date-window
copy_rates_range returns nothing for periods the terminal has not cached yet. Older bars carry spread=0 (not recorded).
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
TFS = {"m5": (mt5.TIMEFRAME_M5, 30), "m15": (mt5.TIMEFRAME_M15, 60), "h1": (mt5.TIMEFRAME_H1, 180),
       "d1": (mt5.TIMEFRAME_D1, 700)}


def grab(sym, tf, years=None, step=None):
    r = mt5.copy_rates_from_pos(sym, tf, 0, 20_000_000)
    if r is None or not len(r):
        return None
    _, i = np.unique(r["time"], return_index=True)
    return r[i]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="+", default=["XAUUSDm", "USTECm"])
    ap.add_argument("--years", type=float, default=12)
    a = ap.parse_args()
    if not mt5.initialize(path=TERMINAL):
        sys.exit(f"MT5 initialize failed: {mt5.last_error()}")
    for sym in a.symbols:
        mt5.symbol_select(sym, True)
        info = mt5.symbol_info(sym)
        if info is None:
            print(sym, "not found")
            continue
        out = {"point": info.point, "contract": info.trade_contract_size, "vol_min": info.volume_min,
               "vol_step": info.volume_step}
        for name, (tf, step) in TFS.items():
            r = grab(sym, tf, a.years, step)
            if r is None:
                continue
            for k in ("time", "open", "high", "low", "close", "tick_volume", "spread"):
                out[f"{name}_{k}"] = r[k]
            print(f"{sym} {name}: {len(r)} bars {datetime.fromtimestamp(r['time'][0], timezone.utc):%Y-%m-%d} -> "
                  f"{datetime.fromtimestamp(r['time'][-1], timezone.utc):%Y-%m-%d}")
        np.savez_compressed(ROOT / "data" / f"{sym}_tf.npz", **out)
    mt5.shutdown()


if __name__ == "__main__":
    main()
