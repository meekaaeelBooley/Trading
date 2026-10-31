---
description: Show desk status - KILL/HALT flags, equity, open positions, results per instrument
allowed-tools: PowerShell(.\tools\desk.ps1 *), mcp__xau__account_info, mcp__xau__positions, mcp__xau__session_summary, mcp__ustec__session_summary, ListAgents
---
Run `.\tools\desk.ps1 status`, then `mcp__xau__account_info` (equity, is_demo) and `mcp__xau__positions` (account-wide, covers both
instruments), then `ListAgents` to see which desk agents are running. Reply in at most 6 lines: KILL/HALT flags, equity, open
positions (symbol, side, lots, profit), results per instrument (n, expectancy), and which agents are running.
Do not change anything.
