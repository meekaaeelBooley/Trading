---
description: Stop the trading desk now - flatten Nasdaq, stop all desk agents, close out the run
allowed-tools: PowerShell(.\tools\desk.ps1 *), mcp__ustec__flatten_all, mcp__ustec__positions, mcp__ustec__session_tick, TaskStop, ListAgents
---
The user pressed stop. Do this immediately, in this order, with no commentary until the end:

1. Run `.\tools\desk.ps1 stop` (creates the KILL file so no shift can open anything new or keep running, and clears the `/desk-max` UNCAPPED flag).
2. Call `mcp__ustec__flatten_all(reason="user stop")`.
3. Call `mcp__ustec__positions`. If anything is still open, `flatten_all` again once and report it.
4. Stop every running desk subagent (`scalper-ustec`, `sentinel`, `coach`): use `ListAgents`, then `TaskStop` each
   (load `TaskStop` with `ToolSearch select:TaskStop` if it is not callable).
5. Call `mcp__ustec__session_tick` once so the run is closed out and its report is written.
6. If you are inside `/loop`, end it with `ScheduleWakeup(stop: true)`.

Reply with 2-3 lines: positions closed, final day %, report path if any, and "resume with /desk".
