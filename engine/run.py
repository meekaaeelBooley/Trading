"""Run/day/week bookkeeping on a plain state dict (no broker, no MCP) so the live server, the headless
runner and the tests all share exactly the same logic."""
from . import clock


def roll_state(state, equity, now):
    """Day (SAST date) and ISO-week equity baselines for the daily stop / weekly halt."""
    sd = now.astimezone(clock.SAST).date().isoformat()
    if state.get("day", {}).get("date") != sd:
        state["day"] = {"date": sd, "start_equity": equity}
    y, w, _ = now.isocalendar()
    if state.get("week", {}).get("key") != f"{y}-W{w}":
        state["week"] = {"key": f"{y}-W{w}", "start_equity": equity}


def start_or_continue(state, now, c):
    """A run starts on the first tick after the user starts the loop and is hard-capped at run_max_minutes.
    Returns (run, status) with status new|cont|just_ended (anti-stray-wake guard right after a stop)."""
    ts, max_s = now.timestamp(), c["run_max_minutes"] * 60
    r = state.get("run")
    if r and r.get("ended"):
        if ts - r["ended_ts"] < 180:
            return r, "just_ended"
        r = None
    if r:
        # a tick arriving when the previous tick said it should (+2 min) is the same loop still running:
        # it continues into the cap and gets FLATTEN. Anything else is a manual restart: fresh run if the
        # old one is past its cap or has been idle too long, else it resumes (same cap).
        loop_alive = ts <= (r.get("wake_due") or ts) + 120
        if not loop_alive and (ts - r["start_ts"] >= max_s or ts - r["last_tick"] > c["run_gap_new_s"]):
            r = None
    status = "cont"
    if r is None:
        r = {"id": int(ts), "start_ts": ts, "trades": 0, "consec_losses": 0, "stopped": False,
             "stop_reason": "", "warm_done": False, "summarised": False, "ended": False}
        state["run"], status = r, "new"
    r["last_tick"] = ts
    return r, status
