# Nasdaq trading desk (Claude Code + MetaTrader 5, demo only)

Claude Code agents trade the **Nasdaq 100 CFD** on a **demo** MetaTrader 5 account (Exness or XM). You start it with one command (`/desk`);
Python code enforces every risk limit and the agents only decide when to enter.

> **Demo money only.** This is an experiment, not financial advice. The code refuses to trade on a real account, and our research found
> no proven edge (see [Honest status](#honest-status)). Never point it at a live account.

```
you ── /desk ──> chief (your Claude Code session)
                  ├─ sentinel   reads the news, can veto trading for a while
                  ├─ scalper    the trader: checks the market every 5 min, opens/manages/closes trades
                  └─ coach      reviews results, writes lessons
Python (mt5_server.py + engine/) enforces: position size, stops, daily loss stop, news filter, demo-only check
```

## What you need

| Need | Notes |
|---|---|
| **Windows 10/11, 64-bit** | The `MetaTrader5` Python package only runs on Windows. |
| **Python 3.10 - 3.13** (64-bit) | From python.org; tick "Add python.exe to PATH". |
| **Git** | To clone this repo. |
| **Claude Code** | [Install guide](https://docs.claude.com/en/docs/claude-code/overview). Needs a Claude subscription; a trading day uses a fair amount of usage. |
| **An Exness or XM account** | Free. You only need a **demo** MT5 account. |

## Setup (about 20 minutes, once)

### 1. Open a demo account
Register with your broker, then create a **Demo** account of type **MT5** (not MT4):
- **Exness**: Personal Area > *My Accounts* > *Open New Account* > **Demo** > **MT5** > Standard.
- **XM**: register at xm.com, then in the Members Area open a **Demo** account on **MT5**.

Menu names change over time; what matters is: *demo*, *MT5*. Write down the **login**, **password** and **server** name the broker shows you.

### 2. Install and prepare MetaTrader 5
1. Download MetaTrader 5 **from your broker's website** (the broker-branded version already knows its servers).
2. Start it and log in: *File > Login to Trade Account* > your demo login, password and server. The account name in the top-left of the
   *Navigator* panel should show a demo account.
3. Press the **Algo Trading** button in the toolbar so it turns **green**.
4. Open *View > Market Watch*, right-click > *Symbols* and make sure the broker's Nasdaq 100 instrument is visible
   (Exness: `USTECm` or `USTEC`; XM: `US100Cash`). The next steps find it for you.
5. **Leave MetaTrader 5 running** whenever the desk runs.

### 3. Get the code and run the setup script
The repository is private: ask the owner to add you as a collaborator on GitHub first. Then open PowerShell:

```powershell
git clone https://github.com/<owner>/Trading.git
cd Trading
powershell -ExecutionPolicy Bypass -File tools\setup.ps1
```

The script: creates the Python environment and installs packages, finds your MT5 terminal, lists the Nasdaq-like symbols on **your** broker
and lets you pick one, writes a private `.mcp.json` for this PC (never committed), then runs the broker check. Use `-Symbol US100Cash`
or `-Terminal "C:\...\terminal64.exe"` to skip a question, `-Force` to rewrite an existing `.mcp.json`.

### 4. Read the broker check
`setup.ps1` ends with a PASS / WARN / FAIL list (run it again any time: `.venv\Scripts\python.exe tools\check_broker.py`).
You want **0 FAIL**. Common results:

| Line | Meaning / fix |
|---|---|
| `account is NOT a demo account` | You are logged in to a real account. Log in to the demo account. The desk will refuse to trade anyway. |
| `Algo Trading is OFF` | Click the Algo Trading toolbar button until it is green. |
| `symbol '...' does not exist` | Wrong symbol name for your broker. Pick one from the list it prints, then set `TRADING_SYMBOL` in `.mcp.json` (or rerun `setup.ps1 -Force`). |
| `not recognised as a Nasdaq index` | The name must start with `USTEC`, `US100`, `NAS100` or `NDX`, otherwise the strategy never fires. |
| `broker server time is UTC+2` (or +3) | Fine: the desk detects the broker's clock offset by itself and converts everything to real UTC. |
| `market looks closed` (WARN) | Weekend or break. Rerun while the market is open so the clock offset can be confirmed. |
| `not enough price history` | In MT5 open the symbol's M5, H1 and H4 charts once and scroll left to download history, then rerun. |
| `cannot connect to MetaTrader 5` | Start the terminal and log in. With several terminals installed, set `MT5_PATH` in `.mcp.json`. |

### 5. Start the desk
1. Open the `Trading` folder in Claude Code (`claude` in a terminal there, or the VS Code extension).
2. Approve the **ustec** MCP server when Claude Code asks (it comes from `.mcp.json`).
3. Run **`/desk`**.

The chief checks the account is a demo, starts the run, and launches the trader in 5-minute shifts. You will see one short status line
per event. Keep the PC awake and Claude Code open while it runs.

## Daily use

| Command | What it does |
|---|---|
| `/desk` | Start Nasdaq trading (moderate risk tier). `/desk high` or `/desk extreme` for bigger sizes (more variance, see below). |
| `/desk-max` | Same, with no time cap. Use inside `/loop /desk-max`; it keeps the desk alive and restarts after usage-limit gaps. |
| `/desk-status` | Equity, open positions, today's results, which agents are running. |
| `/desk-stop` | **Emergency stop**: closes all positions, stops every agent. Pressing Esc alone does *not* close positions. |
| `/desk-resume` | Clears the stop flag so `/desk` can trade again. |

**When to start.** The one tested strategy (`trend_day`) enters at 11:00 New York time and holds about 5 hours. Start `/desk` between
**08:00 and 11:00 New York time** so the 8-hour run covers the hold:

| | New York | UTC | South Africa (SAST) |
|---|---|---|---|
| US winter time (early Nov - mid Mar) | 08:00 - 11:00 | 13:00 - 16:00 | 15:00 - 18:00 |
| US summer time (mid Mar - early Nov) | 08:00 - 11:00 | 12:00 - 15:00 | 14:00 - 17:00 |

Outside that window `/desk` still runs but will often be flat: the strategy only trades about once a day, and only when the setup is there.
Times in logs and the daily-loss reset use South African time (SAST).

## Exness vs XM

| | Exness | XM |
|---|---|---|
| Nasdaq symbol | `USTECm` or `USTEC` (the `m` suffix depends on the account type) | `US100Cash` |
| Gold symbol (switched off, for reference) | `XAUUSDm` | `GOLDmicro` |
| Server clock | UTC | often GMT+2/+3: **auto-detected**; pin it with `BROKER_UTC_OFFSET_H` in `.mcp.json` if the check cannot see a live tick |
| Where to change | `TRADING_SYMBOL`, `MT5_PATH`, `BROKER_UTC_OFFSET_H` in the `env` block of `.mcp.json` | same |

The project was developed and tested on an Exness demo. XM (and any other MT5 broker) is supported through the same checks, but treat the
first session as a trial: run `check_broker.py`, then `/desk`, and watch the first status lines (`/desk-status` shows the symbol and clock offset).
Also check the index's daily break: `config.ustec.json` has `"break": ["22:45", "00:00"]` (SAST, the Exness USTECm break). If your broker's
Nasdaq closes at a different time, change the **first** value only (the end must stay `00:00`).

## Troubleshooting

| Symptom | Fix |
|---|---|
| Claude Code does not list the `ustec` server | Run `setup.ps1` (creates `.mcp.json`), then restart Claude Code and approve the server. |
| `MT5 initialize failed` | The terminal is not running / not logged in. Start it, or set `MT5_PATH`. |
| `/desk` says not a demo account | Log in to a demo account in MT5. This check cannot be bypassed. |
| Desk says `market_closed` / `stale_bars` | Weekend, daily break or holiday - or the broker's clock offset is unknown. Run `check_broker.py` while the market is open. |
| Nothing trades for hours | Normal: one strategy, about one trade a day, many filters. Check `/desk-status`. |
| Trading stopped by itself | A safety stop hit (daily -12%, 6 losing trades, run cap). `/desk-status` shows why. A **weekly halt** (-25%) needs you to delete `state-ustec\HALT` yourself. |
| `/desk-stop` was used | `/desk` clears it when you start again (or use `/desk-resume`). |

## Safety limits (enforced in code, not by the agents)
Demo accounts only · risk per trade 5% of equity at tier size 1.0 (the default `moderate` tier uses half that) · daily stop -12%, weekly halt -25% ·
6 real losses stop the run · stop-loss 0.8-2.5 x ATR · margin use <= 80% · USD high-impact news gate · every exit is journaled.
Limits live in `config.ustec.json` and are changed by hand, never by the agents.

## Honest status
Research in `reports/` (about 9 years of gold and 2+ years of Nasdaq data, with costs) found **no confirmed edge** in classic M1/M5 scalping.
One narrow idea, `trend_day` (Nasdaq, wide stop, hold about 5 hours), is the only strategy kept; its confidence interval still includes zero.
The desk makes the experiment fast and well-instrumented; it does not make it profitable. Judge it on the demo journal
(at least 100 trades, positive expectancy, profit factor above 1.2) before any live thought, and even then the decision is yours.

Risk tiers (`/desk high`, `/desk extreme`) scale position size; simulations show `high` raises both upside and the chance of a deep drawdown,
and `extreme` is a variance experiment that loses in the median simulated year. Start with `moderate`.

## Layout
`mt5_server.py` MCP server and risk enforcement · `engine/` pure logic (gates, sizing, playbook, sessions, broker clock) ·
`.claude/commands/` slash commands · `.claude/agents/` the agents · `desk/doctrine.md` trader rules · `config.ustec.json` limits ·
`tools/` `setup.ps1`, `check_broker.py`, `desk.ps1` (stop/resume/status from a plain terminal) and offline research scripts ·
`state-ustec/` journal and lessons (gitignored) · `reports/` run and research reports · `tests/`.
Gold (`config.xau.json`, `scalper-xau`) is kept in the repo but switched off: no command uses it.

Run the tests: `.venv\Scripts\python.exe -m pytest -q`. Dry run (logs trades without sending them): set env `DRY_RUN=1` for the server.
