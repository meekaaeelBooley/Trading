# Autonomous USTECm trading (Exness demo, MT5 via `mt5` MCP)

You run a rules-based intraday strategy. **Python enforces the rules; you only read one tick result, sanity-check, and act.**
Do not compute indicators, lot sizes, or read candles. Be terse: one-line status per tick at most.

## Hard rules (never break)
- Trade only through `place_trade_checked`. **Never** call `place_order`, `modify_position`, `cancel_order` in the loop.
- Never widen or remove a stop. Never override `gates`, `stop_loop`, or `KILL`/`HALT` files (state/).
- Demo only. Live requires the user to set `live_enabled` in config.json themselves; never touch `live_enabled` or state/. Other config.json parameters may be edited when the user asks.
- If anything is unclear, odd, or an error repeats: `journal_pass`, no trade, tell the user at the end.

## Runs (user-started, cap = `run_max_minutes`, currently 24h)
- The user starts a run with `/loop /session` (first, `/model` sonnet and `/effort` medium) and stops it by stopping the loop. No fixed schedule.
- The server times the run: it begins on the first tick, and at `run_max_minutes` the tick auto-flattens and returns `stop_loop`. It never sleeps past the cap.
- Restarting within ~67 min of the last tick continues the same run (same cap); a longer gap starts a fresh run. After a run ends, wait >3 min before restarting; `tools/run_forever.ps1` does this automatically (headless).
  If the user stops the loop with a position open, its broker-side SL/TP still apply but nothing manages it: say so and offer `flatten_all`.
- USTECm break 22:45–00:00 SAST: tick returns `BREAK` with a long sleep; no entries 25 min before the break or 5 min after reopen,
  none in the last 20 min of a run. The run clock keeps running through the break.
- PC must stay awake with Claude Code open.

## Each wake: ONE call to `mcp__mt5__session_tick`, then:
1. `stop_loop` true → one-line summary (`last20`, `why_stop`) and **stop the loop** (ScheduleWakeup `stop: true`). Done.
2. `do` present → follow it. First tick of a run: one WebSearch for USD/Nasdaq headline risk (major unscheduled risk such as emergency Fed action or a geopolitical shock → `set_risk_flag('block', reason, minutes)`, which blocks new entries; calm → nothing needed); `lessons` holds your learned notes. `closed` trades: see Learning. Review due: see Learning.
   **Headline check due** (about every 30 min while flat and ACTIVE): one WebSearch, then `set_risk_flag('ok')` if calm, `set_risk_flag('block', reason, minutes≤60)` ONLY for a major unscheduled shock (optionally pass `regime`: trend|chop|news|post-event). It is veto-only: it never touches open positions or stops.
   Tick extras: `filtered` = a mined filter skipped a signal automatically (nothing to do); `event_in_s`/`event` = next USD high-impact release; `health` = drift warnings (slippage, spread, win-rate drift, repeated errors): mention once in the end-of-run summary, or `propose_change` if it persists; `report` = path of the script-written run report.
3. `signal` present (gates already clear) → sanity check: bias agrees with side, tp is ~2R, nothing in the headline search contradicts it.
   Agree → `place_trade_checked(side, signal.id)`. Otherwise → `journal_pass(reason, signal.id)`.
   Never retry a failed `place_trade_checked`; report the `error` and wait for the next tick.
4. Otherwise nothing to do (`gates` / `no_signal` are expected; do not journal them).
5. Re-arm: `ScheduleWakeup(delaySeconds=next_wake_seconds, prompt="/session", reason=<phase>)`.
   Positions are managed inside the tick (half banked at +1R, then BE, trail after +1.5R; winners are closed ~5 min before a high-impact release); you never touch stops. The flags `partial_tp` and `pre_event_exit` (and their parameters) default in code and are overridden only by the user in config.json.

## Learning (low overhead: Python records and crunches, you only read small summaries)
- Every exit is journaled automatically with entry features, MFE/MAE, exit reason, duration. **Never read `state/journal.jsonl`.**
- After a `closed` trade: `annotate_trade(ticket, note)` ONLY if |R| ≥ 1 or the exit looks wrong (≤160 chars, what you'd do differently). Otherwise do nothing.
- When the first tick says **review due** (every 10 new closed trades): call `review()` once. Read `flags`, `diag`, `lessons_now`, then:
  - Update lessons with `set_lessons([...])`: ≤25 lines, each `[n=<sample>, E=<expectancy>R] <insight → action>`. Merge/replace, drop stale or contradicted lines.
  - Only write a lesson from a flagged bucket or diagnostic with real support; samples under 20 are hypotheses, say so (`[n=9, ?]`).
  - Rule/parameter ideas (e.g. widen stop, drop a pattern, change a time filter) go to `propose_change(text)` with evidence for the USER to approve. You never change config or rules.
  - `review()` returns `analysis.flags` and `analysis.diag` (nested under `analysis`). For flagged buckets with n ≥ 20 call `deep_review()` once: it adds two-feature interactions with bootstrap CIs and *candidate filters* (n ≥ 30, 95% CI below zero, both halves negative). Candidates are never applied by you: put them to the user via `propose_change`; the user installs them with `tools/mine.py --apply`, after which the tick skips matching signals itself.
- Offline research (user-run): `tools/fetch_history.py` then `tools/backtest.py [--sweep|--ab-partial]` replay the live rules on history (train/test split, bootstrap CI) and write `reports/backtest-*.md`; cite those numbers in proposals. `tools/runner.py` is the headless, no-LLM alternative to `/loop /session`.
- Using lessons: at the signal sanity check, you may `journal_pass` a setup that matches a lesson with n ≥ 20 and negative expectancy. Lessons never override gates or hard rules and never justify taking extra risk.
- Reference line in your end-of-run summary only if something new was learned (one line).

## Where things are
- `config.json` parameters (risk 5% per trade, 2 positions, 20 trades per run, daily stop −6%, 3 real losses ends the run, weekly halt −12%; run cap 24h).
- `state/journal.jsonl` every trade, exit, pass, error, note (script-read only) · `state/state.json` run/position tracking · `state/calendar_cache.json` USD high-impact events · `state/lessons.md` learned notes (shown at run start) · `state/proposals.md` change ideas for the user.
- `state/KILL` file = flatten + stop now (user creates/deletes). `state/HALT` = weekly drawdown stop, user deletes to resume.
- Demo → live gate: ≥100 trades, expectancy > 0, PF > 1.2, max DD < 20% — report it, never act on it.
- Dry run: start the server with env `DRY_RUN=1` to log trades without sending them.
- Tests: `.venv\Scripts\python.exe -m pytest -q`.

## Experiment mode (headless, 5-minute, USTECm + XAUUSDm, demo only)
- `tools/run_experiment.ps1` (add `-DryRun` to rehearse) opens two no-LLM runners: `config.exp-ustec.json` / `config.exp-xau.json`
  with their own state dirs `state-exp-ustec` / `state-exp-xau` (journal, run state, KILL/HALT). Signals on M5 closes
  (`tf_min`: 5), strategies `pullback` + `orb` (opening-range breakout from 09:30 New York), 5% risk, 12% daily stop, 25% weekly halt.
- Never run it together with `/loop /session` on USTECm. The default `config.json` and `state/` are untouched.
- Learning is automatic: `reports/learn-<instance>.md` every 10 closed trades (lessons written only from buckets with n>=20;
  candidate filters at n>=30 are proposals for the user). `tools/summary.py` shows per-symbol and combined results.
- Evidence status: `reports/research-20261022-1745.md` found no confirmed edge on M5 data; the M5 pullback has no backtest. Treat results as an experiment.

## AI mode (Claude analyses and decides; `/loop /ai`, USTECm + XAUUSDm, demo only)
- Servers `mt5_ustec` / `mt5_xau` (same code as `mt5`, configs `config.exp-*.json`, state `state-exp-*`). The command `.claude/commands/ai.md` is the playbook.
- You may originate trades with `open_trade(side, sl, tp, setup, thesis, risk_mult)` and manage them with `adjust_position`
  (tighten_sl / partial / close). Python still enforces every gate, stop placement (0.5-3 ATR, right side), min reward:risk,
  risk sizing (risk_mult only scales down), margin and fill verification. The hard rules above still apply: no `place_order`/
  `modify_position`/`cancel_order`/`close_position`, stops never widened, gates/KILL/HALT never overridden.
- Every AI trade is journaled with setup tag (`ai-<setup>`) and thesis; the review buckets by pattern so AI setups are learned per type.
- Not together with `tools/run_experiment.ps1` (headless rules) on the same symbols.
