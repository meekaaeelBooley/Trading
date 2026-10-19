# Autonomous USTECm trading with Claude Code

Claude Code trades the Nasdaq (USTECm) on an **Exness MT5 demo account** through a local MCP server.
Python code enforces every trading rule; Claude only reads one small result per check, sanity-checks a signal,
and places or skips it. Each run is started by you and ends itself after **2 hours at most**.

> Demo only. This is an experiment, not financial advice. Nothing here guarantees profit.
> Live trading stays off (`live_enabled: false`) until the graduation gate below is met and you turn it on yourself.

## 1. Setup (one time)

1. **MT5**: install the Exness terminal (`C:\Program Files\MetaTrader 5 EXNESS`), log in to a **demo** account, leave it running.
   In MT5 turn on **Algo Trading** (toolbar button must be green) and Tools → Options → Expert Advisors → *Allow algorithmic trading*.
2. **Python 3.12** and the packages (a venv keeps them separate from your system Python):
   ```powershell
   cd C:\Users\Meekaaeel\Desktop\Trading
   python -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```
3. **Register the MCP server** (already in `.mcp.json`; to redo it):
   ```powershell
   claude mcp add mt5 --scope project -- "C:\Users\Meekaaeel\Desktop\Trading\.venv\Scripts\python.exe" "C:\Users\Meekaaeel\Desktop\Trading\mt5_server.py"
   ```
   Start Claude Code in this folder and approve the `mt5` server when asked.
4. **Check it**: `.\.venv\Scripts\python.exe -m pytest -q` (all tests pass) and ask Claude to run `account_info` (should show your demo login and `is_demo: true`).

## 2. Running it

1. Open MT5 (logged in, Algo Trading on). Keep the PC awake (disable sleep) and Claude Code open.
2. In Claude Code, from this folder: `/model` → Sonnet, `/effort` → medium, then
   ```
   /loop /session
   ```
3. That's it. Claude checks every 15-minute candle close (every 5 min while a trade is open) and sleeps through the exchange break.
4. **Stop** by stopping the loop (Esc / interrupt). The run also ends itself and **flattens at 2 hours**, on a daily stop, a kill file, or 4 trades.
   If you stop manually with a trade open, its stop-loss/take-profit stay at the broker but nothing manages it: ask Claude to run `flatten_all`.
5. Emergency stop: create an empty file `state\KILL` (flattens and stops at the next check). Delete it to allow trading again.
6. Rehearsal without orders: set env `DRY_RUN=1` on the server (trades are only logged).

Restarting within ~67 min of the last check resumes the same run (same 2-hour cap); after a longer gap, or after a run has ended, you get a fresh 2 hours.

## 3. Strategy (all on closed candles)

- **Bias**: 4-hour **and** 1-hour charts must agree, EMA50 above EMA200 = long only, below = short only. Disagree = no trades.
- **Entry (15-min)**: price pulls back into the EMA20/EMA50 zone, then a candle closes rejecting it in the bias direction
  (engulfing candle or pin bar) while still holding the right side of EMA50.
- **Stop-loss**: beyond the rejection candle's extreme, or 1.5 x ATR(14), whichever is farther (trade skipped if wider than 3 x ATR).
- **Take-profit**: 2R (twice the risk). Minimum accepted reward:risk is 1.5.
- **Management (automatic)**: stop to break-even at +1R, then trail behind the latest 15-min swing after +1.5R (never loosened).
- **News**: USD high-impact events (from the ForexFactory calendar) block new trades from 15 min before to 10 min after.
  If the calendar can't be loaded or is stale, no new trades.
- Claude's judgement adds a final sanity check (bias agrees, nothing in the headline search contradicts it); it can pass on a setup but can never force one.

## 4. Rules and limits (enforced in code: `mt5_server.py`, `config.json`)

| Area | Limit |
|---|---|
| Account | Demo only (refuses real accounts unless `live_enabled` is set by you) |
| Instrument | USTECm only |
| Risk per trade | **3% of equity**; lots computed from stop distance; min-lot rounding refused if it would exceed 1.5 x the target risk |
| Open positions | 1 at a time |
| Trades per run | 4 |
| Loss streak | 2 real losses (worse than -0.25R) end the run; break-even exits don't count |
| Daily stop | -6% equity (floating included): flatten and stop |
| Weekly halt | -12%: `state\HALT` created, trading stays off until you delete it |
| Run length | **120 minutes max**, no new entries in the last 20 |
| Market filters | ATR(14, 15m) 35-100 points; spread <= 200 points; live price feed and fresh candles required |
| Exchange break | 22:45-00:00 SAST: no checks, no entries 25 min before or 5 min after |
| Every order | Validated before sending (margin, SL side, R:R), fill and SL/TP verified after; closed immediately on mismatch |
| Claude's access | Can't place raw orders, change stops, edit `config.json` or `state/` (blocked in `.claude/settings.json`) |

**Graduation to live** (reported, never automatic): >= 100 demo trades, positive expectancy, profit factor > 1.2, max drawdown < 20%.
3% risk is aggressive: five losses in a row is about a 14% drawdown. Change `risk_pct` in `config.json` if you want less.

## 5. How it learns (cheap by design)

Python does the recording and number-crunching; Claude only reads short summaries.

1. **Automatic journal** (`state/journal.jsonl`): every trade, pass, error and **exit**. Each exit record is self-contained:
   side, pattern, bias, ATR, spread, hour, R result, exit reason (tp/sl/be/trail/flat), max favourable/adverse excursion (MFE/MAE) and duration. Costs zero tokens.
2. **Optional notes**: after a trade with |R| >= 1 or an odd exit, Claude adds a one-line note (`annotate_trade`). Otherwise nothing.
3. **Review every 10 closed trades** (`review()`, ~1-2k tokens): breakdown by side/pattern/hour/ATR/spread, exit mix, MFE/MAE diagnostics
   (e.g. "losers that first reached +1R" = exits too late; "winners barely dipped" = stop has room), and flagged buckets with sample sizes.
4. **Lessons** (`state/lessons.md`, max 25 lines, each `[n=sample, E=expectancy] insight -> action`): shown to Claude at the start of each run (~500 tokens).
   A lesson can justify *passing* on a setup only with n >= 20 and negative expectancy, and never overrides a rule.
5. **Proposals** (`state/proposals.md`): rule or parameter ideas with evidence (sample size, expectancy). **You** read these and decide;
   Claude never edits its own rules. Check it after each review.

Per-run overhead: ~0.5k tokens for lessons plus a small review every few runs; the raw journal is never read by Claude.
To clear learned data after changing the strategy, archive or delete `state\journal.jsonl` and `state\lessons.md`.

## 6. Files

```
README.md  CLAUDE.md             this manual · Claude's operating procedure
config.json                      all parameters (edit by hand, not by Claude)
mt5_server.py                    MCP server: session_tick, place_trade_checked, review, ... + manual tools
engine/                          indicators, signal, risk, gates, clock, news, journal, review (pure, unit-tested)
tests/test_engine.py             run: .\.venv\Scripts\python.exe -m pytest -q
state/                           journal.jsonl, state.json, lessons.md, proposals.md, calendar_cache.json, KILL/HALT
.claude/settings.json            model + tool permissions · .claude/commands/session.md = the /session tick
```

## 6b. Research and automation tools

All in `tools/`, run with `.\.venv\Scripts\python.exe tools\<name>.py`:

| Tool | What it does |
|---|---|
| `fetch_history.py [--months 8]` | Read-only download of M1/M5/M15/H1/H4 history to `data/<symbol>.npz`. The broker caps M1 depth, so the backtester falls back to M5 when M1 is sparse. |
| `backtest.py [--runs 10:00,15:30\|auto] [--sweep] [--ab-partial] [--set key=value]` | Replays the live signal, gate, clock and SL-management code on history with a spread/slippage model and a train/test split with bootstrap CIs. Reports go to `reports/`. No historical news calendar, so news gates are off in backtests. |
| `mine.py [--apply\|--clear]` | Finds robustly losing buckets in the live journal (n>=30, 95% CI below zero, both halves negative). `--apply` writes `state/filters.json`; the tick then skips matching signals. Run it yourself: it changes which setups trade. |
| `runner.py [--dry-run]` | Headless, no-LLM loop over the same `session_tick` / `place_trade_checked`. Rule-only: no headline search, no sanity check. Ctrl+C leaves broker-side SL/TP in place but unmanaged. |

Behaviour added to the live tick (defaults live in `engine/defaults.py`; override in `config.json`):
`partial_tp` (bank `partial_frac` = 50% at +`partial_at_r` = 1R, then BE/trail on the rest), `pre_event_exit`
(close winners `pre_event_exit_min` = 5 min before a USD high-impact release; losers keep their SL),
`headline_check_min` (30: Claude re-checks headlines and may `set_risk_flag`, which can only block new entries).
Each run also writes `reports/run-<id>.md`, and `health` warnings appear in the tick when slippage, spread,
win rate or error counts drift.

## 7. Troubleshooting

| Symptom | Fix |
|---|---|
| Orders rejected / `terminal_trade_allowed: false` | Turn on Algo Trading in MT5 (green button) |
| Tick says `gates: ["market_closed"]` | Exchange is closed (break/weekend); it sleeps and retries |
| `gates: ["no_calendar"]` | News feed unreachable; check internet. Trades stay blocked by design |
| `not_demo` | Logged into a real account; switch the terminal to the demo login |
| Nothing trades for hours | Normal: signals need 4H+1H agreement, a pullback and a rejection candle, often none in a run |
| MCP tools missing | Restart Claude Code and approve the `mt5` server |
