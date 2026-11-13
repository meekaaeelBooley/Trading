---
description: Clear the KILL file left by /desk-stop so /desk can trade again (does not start the desk)
allowed-tools: PowerShell(.\tools\desk.ps1 *)
---
Run `.\tools\desk.ps1 resume`, then `.\tools\desk.ps1 status`. Report in one line whether KILL is cleared for `state-ustec` and
whether a HALT file (weekly drawdown stop) remains. A HALT file is never removed by you: tell the user to delete it themselves
if they want to override it. Do not start the desk; the user starts it with `/desk`.
