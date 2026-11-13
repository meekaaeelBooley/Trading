# Multi-agent desk (MT5 demo, Exness or XM, Nasdaq only)

Start with `/desk`. The main session is the **chief** (orchestrator); specialists are subagents in `.claude/agents/`.
Python (`mt5_server.py` + `engine/`) enforces every limit and manages open positions; agents decide.
**Nasdaq only** (since 2026-11-13): every slash command uses only the `ustec` MCP server. Gold (`scalper-xau`, `config.xau.json`, the `xau`
server) is dormant in the repo; no command, sentinel or coach uses it.

## Broker portability (2026-11-13)
- Per-machine settings live in the gitignored `.mcp.json` (`tools\setup.ps1` writes it; template `.mcp.json.example`): `TRADING_SYMBOL`
  (broker's Nasdaq symbol, overrides `config.ustec.json`), `MT5_PATH` (terminal; unset = default terminal, then the old Exness path), `BROKER_UTC_OFFSET_H`.
- MT5 timestamps are broker server time. `engine/brokertime.py` detects the offset from live ticks (Exness = 0, GMT+2/+3 brokers such as XM-style
  servers = 2/3), caches it in `state-ustec/broker_offset.json`; `mt5_server.py` converts ticks, bars and deal times to UTC at the boundary
  (`_tick_ts`, `_bars`). Use those wrappers for any new MT5 time access. `tools/check_broker.py` is the read-only readiness check.

## Roster
- `scalper-ustec`: the trader (playbook executor + cost-aware probes), 5-min background shifts, isolated to the `ustec` MCP server
  (`config.ustec.json`, state `state-ustec`). Shared rules: `desk/doctrine.md`. (`scalper-xau` exists but is not launched.)
- `sentinel`: web research on macro/headline risk; sets `set_risk_flag` on the `ustec` server (veto only) and returns a macro read.
- `coach`: runs `review()`/`deep_review()`, rewrites lessons (shown to traders at each shift start), queues `propose_change`.
- Chief (`.claude/commands/desk.md`): preflight, launches/relaunches shifts, schedules sentinel and coach, final summary.

## Playbook (`engine/playbook.py`, added 2026-11-04; the only entry with tested evidence is `trend_day`)
- `trend_day` (USTEC, grade B-): a wide-stop, few-trade, let-it-run strategy. **Gold has no validated strategy**: `news_drift` (XAU) and `impulse_cont` (USTEC) were
  SHELVED the same day after the deep-history re-test (`news_drift` hold-out 2017-2024 n=211: -0.26R, t=-1.9; `impulse_cont` n=1109: -0.03R, sign flips by half);
  they stay in the code (`pb.SHELVED`, `detect(include_shelved=True)` for research) but are in no tier. `detect()` runs on
  every snapshot; active signals appear as `playbook` in `wait_for_trigger` / `market_brief`. Entry is `open_trade(setup=<strategy>)`: the signal's
  stop, far target, size cap, time stop and runner management replace the agent's sl/tp (`pyramid` adds to a winner, extreme tier only).
- Runner management: no partial, break-even at +1.5R, time stop in every phase (also BREAK), no pre-event exit. The scalp partial at 0.7R cuts these edges 35-95%.
  An entry is refused when the run cap would flatten it before its time stop (`trend_day` holds ~5 h: needs `/desk-max`).
- Risk tier = root `TIER` flag (`tools\desk.ps1 tier moderate|high|extreme`, or `/desk ... <tier>`; default `moderate`). Sizes are multiples of `risk_pct`:
  moderate = trend_day 0.5; high = trend_day 1.0; extreme = trend_day 1.0 with the looser 1.0 ATR filter + one pyramid add per winner (adds earn ~0R: variance only).
  Monte Carlo (skeptical edge, 12 months, 2.2 effective years of USTEC data): moderate P(profit) 68% / median +14% / P(DD>50%) 1%; high 62% / +19% / 32%;
  extreme 39% / -31% / 97%. See `reports/playbook-backtest-*.md`. With one strategy the desk is mostly flat.
- Kill switch: a strategy with >= 20 live trades and mean R <= -0.3 is suspended automatically (`playbook_suspended` in `desk_brief`). Journal tags: pattern `ai-<strategy>`.
- Non-playbook (discretionary) trades are probes: the research found no net edge for any M5 pattern (see Learning). `config*.json` is changed only when the user asks for it in the session.

## How it works
- Traders loop on `wait_for_trigger`: Python ticks every ~3 s (reconcile, partial at 0.7R, break-even, trail, flatten on
  KILL/HALT/daily stop/run cap) and wakes the agent only for: closed trade, Python action, rule signal, USD event within 5 min,
  new M1 bar while a position is open, or a scout hit (`engine/scout.py`: impulse, range break, wick-through reversal). Quiet tape costs ~nothing.
- Entries via `open_trade`, management via `adjust_position`. Sizing, stop band (0.8-2.5 x ATR M1), reward:risk >= 1.2,
  margin and fill verification are enforced in code. There are no spread limits (`cfg()` in `mt5_server.py` nulls `spread_max_points`
  and `max_spread_r`, so the spread gate and cost guard are off whatever the config files say).
- No position-count cap (`max_positions` 99, `desk_max_positions` off): margin (`margin_use_max` 0.8), the 5% per-trade risk and the
  12% daily stop are the only brakes on stacking. The `desk_exposure` gate still exists in code if the user sets `desk_max_positions`.

## Hard rules (never break)
- Demo only (the demo check in code is not bypassable). The settings.json deny rules were removed at the user's request (2026-11-04): in an interactive session Claude may edit `config*.json`, `state*/`, `live_enabled` or the HALT file, but only when the user explicitly asks for that change. The chief and the trader/coach/sentinel agents never touch them on their own. KILL files are set/cleared only through `tools\desk.ps1`, and only when the
  user's `/desk`, `/desk-stop` or `/desk-resume` command directs it.
- Money moves only through `open_trade`, `adjust_position`, `flatten_all` (the agents' tool lists contain nothing else; the raw-order deny rules in `.claude/settings.json` were removed at the user's request).
- Soft gates may be bypassed per trade with `override=` (journaled, with the thesis). Never bypassable: demo check, KILL/HALT, daily stop
  (12%), weekly halt (25%), desk_exposure, closed market, stale data, break/flatten phases, margin, stop-on-correct-side.
- Stops are only tightened; one `widen_sl` per position (<= 1.5x original risk) with a stated reason.
- Anything unclear, odd, or an error that repeats: stop trading that instrument and tell the user.

## User controls (the user starts and stops it; planned use: ~2 h/day at peak sessions)
- Start: `/desk` = Nasdaq (the only instrument; `xau`/`both` args were removed 2026-11-13), optionally with a tier: `/desk high`. A run is capped at `run_max_minutes` (480 since 2026-11-04 so a 5 h `trend_day` hold fits when the desk is started between 08:00 and 11:00 New York time, i.e. 15:00-18:00 SAST in winter): Python flattens and stops at the cap.
- `/loop /desk-max`: no time cap (`tools\desk.ps1 uncap` sets the root `UNCAPPED` flag, which `cfg()` turns into a huge cap; `/desk` and `/desk-stop`
  clear it). The chief heartbeats every 10 min, relaunches dead shifts, and after a usage-limit gap resumes once the limit resets.
  Runs still end on daily stop, max trades, consecutive losses, KILL/HALT; the chief restarts them as described in `desk-max.md`.
- All controls are slash commands in the session window: `/desk` start (also clears a KILL left by a stop), `/desk-stop` flatten Nasdaq
  + KILL files + stop every desk agent + close out runs, `/desk-status`, `/desk-resume` (only clears KILL).
  They call `tools\desk.ps1` (stop|resume|status), which also works from a plain terminal. HALT (weekly stop) is only ever deleted by the user.
  Interrupting Claude with Esc alone leaves running shifts alive until their end time (<= 5 min): use `/desk-stop` instead.
- Peak sessions (SAST, EDT until 1 Nov): London/NY overlap 14:00-18:00; US cash open 15:30; USTECm break 22:45-00:00.

## Learning
- Every exit is journaled with entry features, MFE/MAE, exit reason, duration, setup tag and thesis. Never read `journal.jsonl`.
- The coach turns reviews into `state-*/lessons.md`; rule/parameter ideas go to `state-*/proposals.md` for the user to approve.
- The swing book and the S/R + smart-money (SMC/ICT) read were removed in Nov 2026: untested mechanical definitions, no backtest, no live
  sample (one swing loss on file). Old journal records may still carry `style: swing`; the scalp stats filter them out. Git history has the code.
- Evidence status: none for M1/M5 scalping. `reports/research-20261022-1745.md` and `reports/strategy-research-20261104.md` (17-20 months of M5, costs,
  train/test, opposite-direction controls, parameter-surface checks) found no net edge in ORB, London/Asian breaks, sweep reversals, scout events
  (impulse/break/sweep lose 0.07-0.3 ATR per trade to cost alone), session momentum, or trend-following. The deep re-test (`reports/deep-families-20261104.md`: XAU 2017-2026,
  USTEC 2024-2026; `reports/event-study-20261104.md`: 1,504 USD tier-1 releases from the MT5 calendar) confirmed that on 9.6 years of gold and shelved two of the three pockets.
  One narrow pocket survives (`trend_day`, +0.07R, CI includes 0). Frequency does not fix a cost-dominated negative edge, and 5%/trade risk amplifies variance (Kelly at a +0.1R edge is far below 5%).
  Treat all results as an experiment. Demo -> live gate (>= 100 trades, expectancy > 0, PF > 1.2, max DD < 20%): report, never act.

## Where things are
`config.xau.json` / `config.ustec.json` limits (risk 5% per trade, no position cap, 150 trades, daily stop 12%, run 240 min XAU / 480 min USTEC) ·
`engine/` pure logic (gates, risk, scout, brief, journal, review, **playbook**, **sessions**) · `desk/doctrine.md` trader rules · `tools/` offline research
(`fetch_full`/`fetch_tf` history, `lab` cost-realistic simulator, `playbook_backtest`, `event_study`, `deep_families`/`families`, `usdcal` calendar loader,
`fetch_history`, `backtest`, `mine`, `research`, `summary`) and `desk.ps1` · `tools/mql5/` MT5 calendar exporter (script + service) and `tools\refresh_calendar.ps1` ·
`config.json` is only the baseline for tests and offline tools.
History: MT5 `Max bars in chart` = Unlimited (set 2026-11-04): XAUUSDm M1/M5 back to 2017 (continuous; 2014-16 sparse), USTECm to mid-2023 (usable from 2024-04, holes 2023-07..2024-03 and 2026-07..10).
Older XAU bars have spread 0 (not recorded before 2023): `lab.Mkt` fills the median recorded spread. Refetch with `fetch_full.py` / `fetch_tf.py` (copy_rates_from_pos).
USD calendar: the Python MT5 package has no calendar API, so `tools/mql5/ExportUsdCalendar.mq5` runs inside the terminal (`tools\refresh_calendar.ps1` restarts it once when flat;
or start `UsdCalendarService` in Navigator > Services, re-exports every 3 h) -> `data/usd_events.csv` (`tools\usdcal.py sync`). UTC timestamps, importance reliable, forecasts noisy.
The live news gate (`engine/news.py`) uses the web feed first and falls back to this export when the feed is down and the export is < 14 days old.
Tests: `.venv\Scripts\python.exe -m pytest -q`. Dry run: env `DRY_RUN=1` on the server logs trades without sending them.
Backup of the pre-desk system: `Desktop\Trading-backup-20261022.zip` (git history also has the earlier modes).
