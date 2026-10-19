r"""Replay the live rules on history and write a markdown report to reports/.

  .venv\Scripts\python.exe tools\backtest.py                    # baseline with current config
  .venv\Scripts\python.exe tools\backtest.py --sweep            # train/test parameter sweep
  .venv\Scripts\python.exe tools\backtest.py --ab-partial       # partial profit on vs off
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine import backtest as bt, review as rv  # noqa: E402
from engine.defaults import DEFAULTS  # noqa: E402

SWEEP_GRID = {"tp_r": [1.5, 2.0, 2.5, 3.0], "sl_atr_mult": [1.0, 1.5, 2.0], "partial_tp": [True, False]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=None)
    ap.add_argument("--runs", default="10:00,15:30", help="SAST run start times, or 'auto' for back-to-back runs")
    ap.add_argument("--spread", type=float, default=120.0, help="spread (points) when bars carry none")
    ap.add_argument("--slip", type=float, default=10.0)
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--ab-partial", action="store_true")
    ap.add_argument("--set", action="append", default=[], help="override cfg, e.g. --set tp_r=2.5")
    a = ap.parse_args()
    cfg = {**DEFAULTS, **json.loads((ROOT / "config.json").read_text())}
    for kv in a.set:
        k, v = kv.split("=")
        cfg[k] = (v.lower() == "true") if v.lower() in ("true", "false") else float(v)
    data = bt.load(a.data or str(ROOT / "data" / f"{cfg['symbol']}.npz"))
    sim = {"spread_points": a.spread, "slip_points": a.slip,
           "run_starts": "auto" if a.runs == "auto" else a.runs.split(",")}
    note = (f"runs: {a.runs} SAST, spread {a.spread}pt, slip {a.slip}pt, risk {cfg['risk_pct']}%/trade. "
            "No historical news calendar, so news gates are off. SL-before-TP inside a bar.")
    out = ROOT / "reports"
    out.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M")
    if a.sweep or a.ab_partial:
        grid = {"partial_tp": [True, False]} if a.ab_partial else SWEEP_GRID
        rows = bt.sweep(data, cfg, grid, sim)
        md = bt.markdown("Backtest sweep" if a.sweep else "Partial profit A/B", rows, note)
        path = out / f"backtest-{'sweep' if a.sweep else 'ab'}-{stamp}.md"
    else:
        ex = bt.run(data, cfg, sim)
        st = bt.summarise(ex, cfg["risk_pct"])
        an = rv.analyze(ex)
        md = (f"# Backtest {stamp}\n\n{note}\n\n- stats: {st}\n- exit mix: {an.get('exit_mix')}\n"
              f"- diag: {an.get('diag')}\n- flags: {an.get('flags')}\n")
        path = out / f"backtest-{stamp}.md"
    path.write_text(md, encoding="utf-8")
    print(md)
    print("written", path)


if __name__ == "__main__":
    main()
