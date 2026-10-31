# Multi-agent scalping + swing desk (Claude Code + MT5 demo)

Claude Code agents scalp (M1) and swing trade (D1/H4/H1 support/resistance + smart money concepts) **XAUUSDm** and **USTECm** on an **Exness MT5 demo account**. A chief session orchestrates specialist
subagents; Python enforces every limit. Demo only: this is an experiment, not financial advice, and no edge has been demonstrated.

```
you ──/desk──> chief (main session)
                 ├─ sentinel      macro/headline research, sets risk flags (veto only)
                 ├─ scalper-xau   5-min shifts on the `xau` MCP server    ┐ run in parallel, each isolated
                 ├─ scalper-ustec 5-min shifts on the `ustec` MCP server ┘ to its own instrument
                 ├─ swing-xau / swing-ustec  one analysis pass about hourly (and on a swing_alert), holds hours to days
                 └─ coach         reviews, lessons, rule proposals
Python (mt5_server.py + engine/): gates, sizing, stop band, reward:risk, cost guard, margin, fill check, partial/BE/trail,
KILL/HALT, daily stop, run cap, journal. wait_for_trigger wakes an agent only when something happens.
```

## Setup (once)
1. Exness MT5 terminal logged in to a **demo** account, Algo Trading on (green button), kept running.
2. `python -m venv .venv` then `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`.
3. Open Claude Code in this folder and approve the `xau` and `ustec` MCP servers (defined in `.mcp.json`).
4. `.\.venv\Scripts\python.exe -m pytest -q` should pass; ask Claude for `account_info` (must show `is_demo: true`).

## Daily use
- Keep the PC awake with Claude Code open. `/model sonnet`, then **`/desk`** (or `/desk xau`, `/desk ustec`).
- The run ends itself and flattens after `run_max_minutes` (240). Everything is a slash command in the session window:
  `/desk` start · `/desk-stop` flatten both instruments and stop all agents now · `/desk-status` · `/desk-resume` (clears KILL; `/desk` also does).
  They wrap `tools\desk.ps1`, which still works from a terminal.
- Peak sessions in SAST (until 1 Nov): London/NY overlap 14:00-18:00, US cash open 15:30, USTECm break 22:45-00:00.

## Swing book
`swing_brief` gives the swing trader a Python-computed read per timeframe (D1/H4/H1/M15): market structure (BOS/CHoCH), order blocks,
fair value gaps, liquidity pools and sweeps, premium/discount, merged support/resistance zones, previous day/week levels, round numbers,
and ranked trade candidates. The scalpers get a compact version in `market_brief`. Swings risk 1.5% (min lot may stretch to 3.75%),
need reward:risk >= 2, max 2 open / 3 per day, are managed in H1 units, closed before the weekend and after 96 h, and survive the scalp run
cap on their broker-side SL/TP. Details: `CLAUDE.md` (Swing book) and `desk/swing.md`.

## Limits (code-enforced, `config.xau.json` / `config.ustec.json`; edit by hand)
Risk 5% of equity per trade (`risk_mult` may only scale down) · no position-count cap (margin is the limit) · 150 trades per run ·
daily stop -12%, weekly halt -25% · stop 0.8-2.5 x ATR(M1), reward:risk >= 1.2, no spread limits · 6 real losses stops the run ·
USD high-impact news gate and pre-event exit · partial at 0.7R, then break-even and trail.
Agents can bypass soft gates per trade (journaled) and widen a stop once by up to 1.5x; they cannot touch KILL/HALT, daily stop,
weekly halt, desk cap, closed-market/stale-data checks or margin, and raw order tools are denied.

## Layout
`mt5_server.py` MCP server · `engine/` pure logic · `.claude/agents/` specialists · `.claude/commands/desk.md` chief ·
`desk/doctrine.md` shared trader rules · `tools/` desk.ps1 + offline research (`fetch_history`, `backtest`, `mine`, `research`, `summary`) ·
`state-xau/`, `state-ustec/` journals, lessons, proposals (gitignored) · `reports/` run and research reports.

## Honest status
Research so far (`reports/research-20261022-1745.md`) found no confirmed edge on M5 data, and the earlier strategies were about zero or
negative out of sample. Scalping on M1 is dominated by spread and slippage. The desk makes the experiment fast and well-instrumented;
it does not make it profitable. Judge it on the demo journal (>= 100 trades, expectancy > 0, PF > 1.2) before any live thought.
