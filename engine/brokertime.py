"""Broker server time -> UTC (pure, no MT5 import).

MT5 reports every timestamp (ticks, bars, deals) as "server time" encoded as if it were UTC epoch seconds. Some brokers (Exness)
run their servers on UTC; others use a fixed or DST-following offset such as GMT+2 / GMT+3. The rest of the project works on real
UTC epochs, so the server converts at the broker boundary: utc = broker_ts - offset.

The offset is detected from a live tick: a fresh tick is within seconds of "now", so (tick_ts - now) is a whole number of hours.
A stale tick (market closed) is ignored. A *change* of a known offset (DST switch) needs two different ticks that agree, so a
single tick that happens to be an exact hour old (a one-hour trading halt) cannot flip a good offset.
"""

MAX_OFFSET_H = 14
FRESH_TOL_S = 120  # |tick - now - whole hours| must be within this to count as a live tick


def new_state(fixed_h=None):
    """Offset state. `fixed_h` (float hours) pins the offset (manual override, never auto-updated)."""
    return {"off": None if fixed_h is None else int(round(fixed_h * 3600)), "cand": None, "fixed": fixed_h is not None}


def candidate(tick_ts, now, tol=FRESH_TOL_S):
    """Whole-hour offset in seconds implied by a live tick, or None if the tick is not live (or implausible)."""
    delta = float(tick_ts) - float(now)
    h = round(delta / 3600)
    if abs(h) > MAX_OFFSET_H or abs(delta - h * 3600) > tol:
        return None
    return int(h * 3600)


def update(state, tick_ts, now, tol=FRESH_TOL_S):
    """Fold one tick into the state (mutates and returns it). Returns the state; `state["off"]` is the offset in seconds or None."""
    if state.get("fixed"):
        return state
    off = candidate(tick_ts, now, tol)
    if off is None:
        return state
    if state["off"] is None or off == state["off"]:
        state["off"], state["cand"] = off, None
    else:
        cand = state.get("cand")
        if cand and cand[0] == off and tick_ts > cand[1]:  # confirmed by a second, later tick
            state["off"], state["cand"] = off, None
        else:
            state["cand"] = [off, float(tick_ts)]
    return state


def to_utc(ts, state):
    """Broker timestamp -> UTC epoch seconds (offset unknown counts as 0, the previous behaviour)."""
    return ts - (state.get("off") or 0)
