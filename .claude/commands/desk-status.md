---
description: Show desk status - KILL/HALT flags, equity, open positions, Nasdaq results
allowed-tools: PowerShell(.\tools\desk.ps1 *), mcp__ustec__account_info, mcp__ustec__positions, mcp__ustec__session_summary, ListAgents
---
Run `.\tools\desk.ps1 status`, then `mcp__ustec__account_info` (equity, is_demo, symbol, utc_offset_h) and `mcp__ustec__positions`,
then `ListAgents` to see which desk agents are running. Reply in at most 6 lines: KILL/HALT flags, equity, open
positions (symbol, side, lots, profit), results (n, expectancy), and which agents are running.
Do not change anything.
