"""Deterministic M1 scout: decides, without any LLM, whether the last closed bar is worth an agent's attention.

Pure numpy over closed bars. The desk's wait_for_trigger() calls this once per new bar so a scalper agent only
spends tokens on bars that did something (impulse, range break, liquidity sweep) or while it holds a position.
"""
import numpy as np


def scout(closed, atr, impulse_atr=1.4, break_bars=20):
    """Reasons the last closed bar is interesting (empty list = quiet tape).

    impulse_up/down : bar range >= impulse_atr x ATR and the body points that way
    range_break_*   : close beyond the extreme of the previous `break_bars` bars
    sweep_high/low  : wick beyond that extreme but close back inside it (liquidity grab, reversal candidate)
    """
    n = break_bars
    if atr <= 0 or len(closed) < n + 2:
        return []
    o, h, l, c = (np.asarray(closed[k], float) for k in ("open", "high", "low", "close"))
    hi, lo = h[-n - 1:-1].max(), l[-n - 1:-1].min()
    out = []
    if h[-1] - l[-1] >= impulse_atr * atr:
        out.append("impulse_up" if c[-1] > o[-1] else "impulse_down")
    if c[-1] > hi:
        out.append("range_break_up")
    elif c[-1] < lo:
        out.append("range_break_down")
    if h[-1] > hi >= c[-1]:
        out.append("sweep_high")
    if l[-1] < lo <= c[-1]:
        out.append("sweep_low")
    return out
