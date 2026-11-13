---
description: Start the Nasdaq desk with no run time cap - runs until you /desk-stop, survives usage-limit gaps and resumes after the reset (use inside /loop)
allowed-tools: PowerShell(.\tools\desk.ps1 *), ScheduleWakeup
---
You are the **chief** in **max mode**. Read `.claude/commands/desk.md` and follow it exactly (preflight, launching the shift, relaunch on
shift end, sentinel/coach scheduling), with the differences below. Scope: Nasdaq only (the `ustec` server); ignore any `xau` / `both` argument.

## Differences from /desk
1. Preflight: run `.\tools\desk.ps1 uncap` (instead of `cap`), then `resume`. The run has no time cap (no FLATTEN at the run cap).
   Tier as in /desk: `$ARGUMENTS` may name `moderate|high|extreme`; set it with `.\tools\desk.ps1 tier <name>` (default `moderate`).
   On heartbeat wakes do NOT touch the tier: it only changes when the user's command names one.
2. There is no run-cap ending. Never stop because of time. The run only stops for the reasons below.
3. **Keep going.** You must stay alive across turns: run inside `/loop` dynamic mode. If you are not inside `/loop`, say so once and
   tell the user to start it with `/loop /desk-max`; still run one cycle.
4. **Heartbeat.** At the end of EVERY turn call `ScheduleWakeup(delaySeconds=600, prompt="/desk-max", reason=...)`. Shift reports re-invoke you
   on their own; the heartbeat only covers the case where nothing does (agent died, usage limit hit).
   On a heartbeat wake: if the last launch is more than 8 minutes old with no report, its shift is dead
   (shifts last 5 min): relaunch it now with a fresh end time and the latest macro read. Run `session_tick` first to confirm the run state.
5. **Usage limit.** If a launch, tool call or turn fails with a usage/rate-limit message, do not retry in a tight loop and do not
   stop: `ScheduleWakeup(delaySeconds=3600, ...)` (or until the stated reset if sooner) and try again on wake. After the reset, run
   `session_tick`, relaunch the shift, and re-run the sentinel (the macro read is stale after a gap).
   Note: while no shift is alive nothing manages open positions except broker-side SL/TP; tell the user this once, at start.
6. **When the run stops** (the report says `stop_loop: yes` or `session_tick` shows `stop_loop`), look at `why_stop`:
   - `max_trades` or `consec_losses` or an ended run: wait 15 minutes (heartbeat), then `session_tick` to start a fresh run and relaunch.
   - `daily_stop`: no new run until the SAST date changes; heartbeat every 30 min and check `t`, then `session_tick` and relaunch.
   - `KILL`, `HALT`, `not_demo`, an error that repeats, or anything odd: the desk stays stopped; tell the user.
   - If the desk is permanently stopped: run the coach, print the final summary, and end the loop with `ScheduleWakeup(stop: true)`.
7. Run the **coach** on `review_due` as in /desk, plus once every ~3 hours of wall time.
8. Print one status line per event as in /desk. Stop everything only on `/desk-stop`.

Rules are unchanged from /desk: demo only, never touch config/state/HALT files, no raw order tools.
