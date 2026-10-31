# Multi-agent scalping + swing desk (Exness demo, MT5, XAUUSDm + USTECm)

Start with `/desk`. The main session is the **chief** (orchestrator); specialists are subagents in `.claude/agents/`.
Python (`mt5_server.py` + `engine/`) enforces every limit and manages open positions; agents decide.

## Roster
- `scalper-xau`, `scalper-ustec`: one trader per instrument, 5-min background shifts, each isolated to its own MCP server
  (`xau` / `ustec`, configs `config.xau.json` / `config.ustec.json`, state `state-xau` / `state-ustec`). Shared rules: `desk/doctrine.md`.
- `swing-xau`, `swing-ustec`: swing traders (D1/H4/H1 support/resistance + smart money concepts), one analysis pass per launch on the same
  per-instrument servers; playbook `desk/swing.md`. The chief launches a pass at start, every `NEXT PASS` (default 60 min) and on a scalper's `swing_alert`.
- `sentinel`: web research on macro/headline risk; sets `set_risk_flag` on both servers (veto only) and returns a macro read.
- `coach`: runs `review()`/`deep_review()`, rewrites lessons (shown to traders at each shift start), queues `propose_change`.
- Chief (`.claude/commands/desk.md`): preflight, launches/relaunches shifts, schedules sentinel and coach, final summary.

## How it works
- Traders loop on `wait_for_trigger`: Python ticks every ~3 s (reconcile, partial at 0.7R, break-even, trail, flatten on
  KILL/HALT/daily stop/run cap) and wakes the agent only for: closed trade, Python action, rule signal, USD event within 5 min,
  new M1 bar while a position is open, or a scout hit (`engine/scout.py`: impulse, range break, liquidity sweep). Quiet tape costs ~nothing.
- Entries via `open_trade`, management via `adjust_position`. Sizing, stop band (0.8-2.5 x ATR M1), reward:risk >= 1.2,
  margin and fill verification are enforced in code. There are no spread limits (`cfg()` in `mt5_server.py` nulls `spread_max_points`
  and `max_spread_r`, so the spread gate and cost guard are off whatever the config files say).
- No position-count cap (`max_positions` 99, `desk_max_positions` off): margin (`margin_use_max` 0.8), the 5% per-trade risk and the
  12% daily stop are the only brakes on stacking. The `desk_exposure` gate still exists in code if the user sets `desk_max_positions`.

## Swing book (added Oct 2026)
- Same server and magic as the scalps; every tracked position carries `style` scalp|swing. Entry `open_swing`, management `adjust_swing`
  (`open_trade` / `adjust_position` refuse the other book's tickets); the scalpers' tools cannot open or touch swings.
- Analysis is Python (`engine/levels.py` S/R zones, `engine/smc.py` BOS/CHoCH, order blocks, FVGs, liquidity pools/sweeps, premium/discount,
  `engine/swing.py` multi-timeframe scoring): `swing_brief` returns it with ranked `candidates` (ready|at_poi|watch). `market_brief` carries a
  compact `sr` + `smc_m5`/`smc_m15` read for the scalpers too.
- Swing limits (defaults in `engine/defaults.py`, any key overridable in config): risk 1.5% of equity per trade (`risk_mult` only down; the minimum
  lot may stretch it to `swing_min_lot_risk_mult` 2.5x = 3.75%, shown as `risk_pct_est` / `feasible`), stop 0.7-3.0 x ATR(H1), reward:risk >= 2,
  max 2 open and 3 opened per SAST day, no opposite swing, no stacking within 1 ATR(H1), no entries Friday after 18:00 SAST. Own gates: the M1 ATR band,
  scalp position count/trade count/loss streak do not apply; every hard gate (KILL/HALT, daily stop, demo, closed market, stale data, news, risk flag) does.
- Management in Python (any tick): partial 50% at +1.5R, break-even at +1R, H1-structure trail from +2R, close before the weekend (Fri 21:30 SAST),
  close after 96 h. No pre-event exit. The scalp run cap (FLATTEN) closes scalps only: swings outlive a run on broker-side SL/TP and are managed again
  at the next tick. KILL, HALT and the daily stop close everything. Swing exits never touch the scalp loss streak and are journaled with `style`.

## Hard rules (never break)
- Demo only. Never touch `live_enabled`, `config*.json`, `state*/` files, or the HALT file (user-owned). KILL files are set/cleared only through `tools\desk.ps1`, and only when the
  user's `/desk`, `/desk-stop` or `/desk-resume` command directs it.
- Money moves only through `open_trade`, `adjust_position`, `flatten_all`. Raw `place_order` / `modify_position` /
  `cancel_order` / `close_position` / `place_trade_checked` are denied in `.claude/settings.json`.
- Soft gates may be bypassed per trade with `override=` (journaled, with the thesis). Never bypassable: demo check, KILL/HALT, daily stop
  (12%), weekly halt (25%), desk_exposure, closed market, stale data, break/flatten phases, margin, stop-on-correct-side.
- Stops are only tightened; one `widen_sl` per position (<= 1.5x original risk) with a stated reason.
- Anything unclear, odd, or an error that repeats: stop trading that instrument and tell the user.

## User controls (the user starts and stops it; planned use: ~2 h/day at peak sessions)
- Start: `/desk` (or `/desk xau` / `/desk ustec`). A run is capped at `run_max_minutes` (240): Python flattens and stops at the cap.
- `/loop /desk-max`: no time cap (`tools\desk.ps1 uncap` sets the root `UNCAPPED` flag, which `cfg()` turns into a huge cap; `/desk` and `/desk-stop`
  clear it). The chief heartbeats every 10 min, relaunches dead shifts, and after a usage-limit gap resumes once the limit resets.
  Runs still end on daily stop, max trades, consecutive losses, KILL/HALT; the chief restarts them as described in `desk-max.md`.
- All controls are slash commands in the session window: `/desk` start (also clears a KILL left by a stop), `/desk-stop` flatten both
  instruments + KILL files + stop every desk agent + close out runs, `/desk-status`, `/desk-resume` (only clears KILL).
  They call `tools\desk.ps1` (stop|resume|status), which also works from a plain terminal. HALT (weekly stop) is only ever deleted by the user.
  Interrupting Claude with Esc alone leaves running shifts alive until their end time (<= 5 min): use `/desk-stop` instead.
- Peak sessions (SAST, EDT until 1 Nov): London/NY overlap 14:00-18:00; US cash open 15:30; USTECm break 22:45-00:00.

## Learning
- Every exit is journaled with entry features, MFE/MAE, exit reason, duration, setup tag and thesis. Never read `journal.jsonl`.
- The coach turns reviews into `state-*/lessons.md`; rule/parameter ideas go to `state-*/proposals.md` for the user to approve.
- Evidence status: none for swing either (the S/R + SMC rules are untested mechanical definitions; no backtest, no live sample). Treat the swing
  book as an experiment with its own journal slice (`style: swing`) and judge it separately; it trades rarely, so expect n < 20 for weeks.
- Evidence status: none for M1 scalping. `reports/research-20261022-1745.md` found no confirmed edge on M5 data and ~0 or negative
  out-of-sample expectancy for the earlier strategies; frequency does not fix that and the 5%/trade risk amplifies it.
  Treat all results as an experiment. Demo -> live gate (>= 100 trades, expectancy > 0, PF > 1.2, max DD < 20%): report, never act.

## Where things are
`config.xau.json` / `config.ustec.json` limits (risk 5% per trade, no position cap, 150 trades, daily stop 12%, run 240 min) ·
`engine/` pure logic (gates, risk, scout, brief, journal, review, levels, smc, swing) · `desk/doctrine.md` scalp rules, `desk/swing.md` swing playbook · `tools/` offline research (`fetch_history`, `backtest`, `mine`,
`research`, `summary`) and `desk.ps1` · `config.json` is only the baseline for tests and offline tools.
Tests: `.venv\Scripts\python.exe -m pytest -q`. Dry run: env `DRY_RUN=1` on the server logs trades without sending them.
Backup of the pre-desk system: `Desktop\Trading-backup-20261022.zip` (git history also has the earlier modes).
