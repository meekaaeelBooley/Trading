r"""Download the deepest available M1 history (with per-bar spread) for XAUUSDm and USTECm into data/<sym>_m1.npz.
Read-only MT5 calls.

  .venv\Scripts\python.exe tools\fetch_full.py [--symbols XAUUSDm USTECm]

With MT5 `Max bars in chart` = Unlimited (Tools > Options > Charts, restart) the terminal serves the whole broker history:
XAUUSDm M1 back to 2014, USTECm M1 back to mid-2023. copy_rates_from_pos is used because copy_rates_range with a date window
returns nothing for periods the terminal has not cached yet. NOTE: older bars carry spread = 0 (the broker did not record it);
tools/lab.py replaces zero spreads with a calibrated figure.
Higher timeframes are derived from M1 in tools/lab.py, so there is exactly one source of truth for prices and spread.
"""
import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import MetaTrader5 as mt5
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
TERMINAL = os.environ.get("MT5_PATH", r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe")
BIG = 20_000_000


def fetch(sym, tf=None):
    r = mt5.copy_rates_from_pos(sym, tf or mt5.TIMEFRAME_M1, 0, BIG)
    if r is None or not len(r):
        return None
    _, idx = np.unique(r["time"], return_index=True)
    return r[idx]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="+", default=["XAUUSDm", "USTECm"])
    a = ap.parse_args()
    if not mt5.initialize(path=TERMINAL):
        sys.exit(f"MT5 initialize failed: {mt5.last_error()}")
    acct = mt5.account_info()
    print("account mode demo:", acct.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO, "| maxbars:", mt5.terminal_info().maxbars)
    (ROOT / "data").mkdir(exist_ok=True)
    for sym in a.symbols:
        mt5.symbol_select(sym, True)
        info = mt5.symbol_info(sym)
        if info is None:
            print(sym, "not found")
            continue
        r = fetch(sym)
        if r is None:
            print(sym, "no data")
            continue
        np.savez_compressed(ROOT / "data" / f"{sym}_m1.npz", point=info.point, contract=info.trade_contract_size,
                            tick_size=info.trade_tick_size, vol_min=info.volume_min, vol_step=info.volume_step,
                            **{k: r[k] for k in ("time", "open", "high", "low", "close", "tick_volume", "spread")})
        nz = r["spread"] > 0
        print(f"{sym}: {len(r)} M1 bars, {datetime.fromtimestamp(r['time'][0], timezone.utc):%Y-%m-%d} -> "
              f"{datetime.fromtimestamp(r['time'][-1], timezone.utc):%Y-%m-%d}, point={info.point}, "
              f"bars with spread>0: {nz.mean():.0%}, median nonzero spread={np.median(r['spread'][nz]) if nz.any() else 0:.0f}pt")
    mt5.shutdown()


if __name__ == "__main__":
    main()
