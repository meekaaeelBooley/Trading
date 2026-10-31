---
description: Stop the trading desk now - flatten both instruments, stop all desk agents, close out the runs
allowed-tools: PowerShell(.\tools\desk.ps1 *), mcp__xau__flatten_all, mcp__ustec__flatten_all, mcp__xau__positions, mcp__ustec__positions, mcp__xau__session_tick, mcp__ustec__session_tick, TaskStop, ListAgents
---
The user pressed stop. Do this immediately, in this order, with no commentary until the end:

1. Run `.\tools\desk.ps1 stop` (creates the KILL files so no shift can open anything new or keep running, and clears the `/desk-max` UNCAPPED flag).
2. Call `flatten_all(reason="user stop")` (closes scalp AND swing positions) on BOTH servers (`mcp__xau__flatten_all`, `mcp__ustec__flatten_all`) in parallel.
3. Call `positions` on both servers. If anything is still open, `flatten_all` again once and report it.
4. Stop every running desk subagent (`scalper-xau`, `scalper-ustec`, `swing-xau`, `swing-ustec`, `sentinel`, `coach`): use `ListAgents`, then `TaskStop` each
   (load `TaskStop` with `ToolSearch select:TaskStop` if it is not callable).
5. Call `session_tick` once on each server so the run is closed out and its report is written.
6. If you are inside `/loop`, end it with `ScheduleWakeup(stop: true)`.

Reply with 2-3 lines: positions closed, final day % per instrument, report path if any, and "resume with /desk".
