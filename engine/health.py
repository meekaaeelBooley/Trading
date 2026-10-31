"""Drift / health checks over journal records. Pure; returns a short list of human-readable warnings."""
from statistics import median

SLIP_WARN = 30        # median entry slippage (points) over the last 10 trades
SPREAD_FRAC_WARN = 0.8  # median entry spread vs spread_max
WIN_DRIFT_WARN = 0.25   # last-20 win rate vs earlier win rate (needs >= 40 exits)
ERRORS_WARN = 3       # error records among the last 20 records
MAE_SHIFT_WARN = 0.35   # median winner MAE (last 10 vs earlier), in R


def check(recs, spread_max):
    warns = []
    trades = [r for r in recs if r.get("type") == "trade"]
    exits = [r for r in recs if r.get("type") == "exit" and r.get("outcome_r") is not None]
    last = trades[-10:]
    if len(last) >= 5:
        slip = median(r.get("slippage") or 0 for r in last)
        if slip > SLIP_WARN:
            warns.append(f"slippage: median {slip:.0f}pt over last {len(last)} entries")
        spr = median(r.get("spread") or 0 for r in last)
        if spread_max and spr > SPREAD_FRAC_WARN * spread_max:
            warns.append(f"spread: median {spr:.0f}pt at entry vs max {spread_max}")
    if len(exits) >= 40:
        win = lambda xs: sum(1 for x in xs if x["outcome_r"] > 0.25) / len(xs)
        d = win(exits[-20:]) - win(exits[:-20])
        if abs(d) >= WIN_DRIFT_WARN:
            warns.append(f"win-rate drift: last20 {win(exits[-20:]):.0%} vs earlier {win(exits[:-20]):.0%}")
    errs = sum(1 for r in recs[-20:] if r.get("type") == "error")
    if errs >= ERRORS_WARN:
        warns.append(f"errors: {errs} error records in the last 20 journal entries")
    mae = [r["mae_r"] for r in exits if r["outcome_r"] >= 0.25 and r.get("mae_r") is not None]
    if len(mae) >= 20 and abs(median(mae[-10:]) - median(mae[:-10])) >= MAE_SHIFT_WARN:
        warns.append(f"MAE shift: winners' median MAE {median(mae[-10:]):.2f}R vs earlier {median(mae[:-10]):.2f}R")
    return warns
