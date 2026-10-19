---
description: One tick of the autonomous trading loop (start a run with `/loop /session`; hard 2h cap)
---
Run one tick of the autonomous trading loop exactly as described in CLAUDE.md ("Each wake"): call `mcp__mt5__session_tick`, act on the result, then re-arm with ScheduleWakeup (`prompt="/session"`, delay = `next_wake_seconds`) or stop the loop if `stop_loop` is true. Follow any `do` item too (headline check: one WebSearch, then `set_risk_flag`; veto-only).
