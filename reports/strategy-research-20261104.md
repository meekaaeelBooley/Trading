# Strategy research for XAUUSDm + USTECm, 2026-11-04

Written for: the desk's owner, deciding what the autonomous agents should trade and how aggressively.

## Addendum (same day, after raising MT5 "Max bars in chart" to Unlimited and exporting the MetaQuotes USD calendar)

The first pass below used 17-20 months of M5 (the terminal's 100k-bar cap). Re-run on the deep history (XAU M5/M1 2017-2026 = 9.6 effective
years; USTEC 2024-2026 = 2.2 effective years; 1,504 USD tier-1 releases 2014-2027), with the live `detect()` and the same simulator:

- **`news_drift` (XAU) FAILED its hold-out and is shelved.** The rule was tuned on 2025-26 (+1.45R on 44 events). On 2017-2024, which was never
  used for tuning (211 events at the real release times), it is **-0.26R, t=-1.9, win 9%**; every year 2017-2022 is negative. On all years: -0.10R
  (CI -0.39..+0.23). Using the real calendar instead of the hard-coded 08:30/10:00 minutes, or other thresholds (1.0-4.0 ATR), or any release family,
  or the same rule on USTEC, gives nothing positive that survives. The 2025-26 result was the gold bull run (control, i.e. the opposite side, was +0.49R there).
  (`reports/event-study-20261104.md`)
- **`impulse_cont` (USTEC) is shelved:** n=1109, -0.03R, t=-0.7, first half -0.14R, second half +0.13R (`reports/playbook-backtest-20261104.md`).
- **`trend_day` (USTEC) survives, weaker and regraded B-:** n=428 at the 1.0 ATR filter +0.056R; n=324 at >=1.5 ATR +0.071R (t=+1.2, CI -0.04..+0.19),
  opposite-direction control -0.20R, plateau stable from 1.0 to 2.5 ATR (+0.05..+0.10R), positive in 4 of the last 5 half-years (the first, n=32, is -0.26R).
  Buys +0.12R vs sells +0.02R: part of it is the +94% bull-run drift. The same recipe on gold is -0.08R (t=-2.6): it is an index effect.
- **The classic families on 9.6 years of gold** (ORB 3 variants, London range break, sweep fade, session momentum, gap fade/follow): all -0.01..-0.41R,
  none positive in both halves (`reports/deep-families-20261104.md`). This is the power the 17-month sample lacked, and it confirms the negative result.
- Data caveats: gold spread is recorded only from 2023 (older bars use the median recorded spread); USTEC has holes 2023-07..2024-03 and 2026-07..10;
  calendar forecasts are noisy (not used).

Net effect: the desk has ONE validated-ish strategy (`trend_day`), gold has none, and the tier Monte Carlo below the line is superseded by
`reports/playbook-backtest-20261104.md` (moderate P(profit) 68% / median +14% / P(DD>50%) 1%; high 62% / +19% / 32%; extreme 39% / -31% / 97%).
The text below is the original 17-month analysis, kept for the record; where it conflicts with this addendum, the addendum wins.

## Bottom line

1. **No classic intraday pattern has a verifiable net edge on these two instruments.** Opening-range breakouts, London/Asian-range breaks,
   sweep reversals, the scout's own impulse / range-break / sweep events, session-to-session momentum and trend-following all come out at about
   zero gross edge, which spread and slippage turn negative. This repeats and extends your 2026-10-22 report, and matches the independent
   MQL5 replication of the Zarattini-Aziz ORB paper (gross reproduced, net zero on NQ CFDs).
2. **Cost is the dominant, controllable variable.** Round-trip friction (spread + 0.5x slippage each way) is about 0.22R on USTEC and 0.09R on gold for a
   1-ATR(M5) stop, and about 0.04-0.07R for a 3-ATR stop. Tight-stop M5 scalping starts in a hole that no pattern here climbs out of. Frequency makes it worse.
3. **Three narrow pockets survived** every check I could run, none of them statistically proven (all confidence intervals include 0, except
   `news_drift`, whose sample is 44 events). They became the **playbook**: `trend_day` (grade B), `news_drift` (C+), `impulse_cont` (C).
4. **Aggression is a sizing choice, not an edge.** With an edge near +0.1R, 5% risk per trade is far above Kelly. Monte Carlo on the playbook's own
   trades says the `extreme` tier has a negative *median* year (-11%) and a ~100% chance of a >50% drawdown even if the edge is real. The default tier is
   therefore `moderate`; `high` and `extreme` are opt-in experiments.

## Data and method

- Exness demo, M5 bars with per-bar spread: XAUUSDm 2025-06-09 to 2026-11-04 (100k bars), USTECm 2025-03-13 to 2026-11-04 (100k bars); M15 3.4-4.2 years;
  H1/D1 12 years (gold) / 3.4 years (USTEC). The terminal caps each timeframe at ~100k bars, so M5 is 17-20 months (~350-400 sessions).
- **Sample context:** USTEC rose 19,257 -> 28,409 (+47%) and gold 3,316 -> 4,042 (+22%) in the sample. Long-biased results are therefore suspect; every result
  carries an **opposite-direction control** (same entry, same stop distance, other side) and a buy/sell split.
- `tools/lab.py`: bid/ask-correct simulator (longs buy the ask, exit the bid; shorts the reverse), real per-bar spread + 0.5x spread slippage on every
  market fill, stop checked before target inside a bar, gaps fill at the open, management sees only earlier bars. Verified against hand calculations
  (`tests/test_lab.py`).
- Chronological 60/40 train/test split, parameter-surface maps (plateau, not peak), day-clustered event studies, bootstrap CIs.
- **Multiple-testing disclosure:** roughly 1,000+ parameter cells and statistical tests were run across the families below. A handful of positive cells are expected
  by chance, which is why only results that were positive in both halves, supported by a control edge and sitting on a plateau were kept, and why the
  surviving numbers are shrunk (Bayesian) before being used for planning.

## What was tested

| Family | Cells | Result |
|---|---|---|
| NY-open ORB, gold and USTEC (range 1/3/6 bars, windows, targets 1-5R, stops, holds) | 288 | Best train config +0.15 to +0.32R, test -0.02 to -0.32R; median cell ~0R. Classic overfit. |
| London-range breakout and sweep-fade, gold and USTEC | 192 | Breakout ~0R (best +0.01R test); sweep-fade 0 of 96 positive in both halves, median -0.2R. |
| Intraday momentum (open direction -> later session), gold and USTEC | 72 | Gold: 0 of 24 positive in both halves. **USTEC: broad plateau (see `trend_day`).** |
| USTEC opening gap fade / continuation | 54 | Fade to gap-fill positive only for a stop of 1.5 ATR (33% of cells, flips at 1.0 and 3.0): **rejected, parameter-fragile.** |
| Scout events on M5: impulse, N-bar break, sweep, at 3-24 bar horizons (thousands of events each) | 12 x 4 | Gross edge |<0.1| ATR; net -0.2 to -0.3 ATR (USTEC), -0.07 to -0.12 ATR (gold), t-stats up to -17. **The patterns that wake the agents lose money to cost alone.** |
| Time-of-day drift scan (34 buckets x 2 instruments) | 136 | Only gold 10:00 and 21:00 London (negative drift) consistent in both halves; about what chance produces. |
| Session-to-session momentum, 12 years of gold H1 | 16 | Every |t| < 2. |
| Trend-following (Donchian 20/55, EMA cross, RSI-3 pullback in trend), H1 and M15, 3.4-12 years | 16 | Gold H1 Donchian-55 +0.05R (t 1.1) over 12 years; USTEC train/test flip sign. |
| Impulse continuation (thresholds 2-5 ATR, holds, stops, scheduled vs unscheduled) | ~250 | Pockets found: gold on scheduled USD releases, USTEC on unscheduled >= 3 ATR bars. |

## The three survivors (live `detect()` replayed bar by bar, runner management, net of costs)

| strategy | scope | n | E (R) | win | PF | t | 95% CI | control E |
|---|---|---|---|---|---|---|---|---|
| `trend_day` USTEC | all / train / test | 258 / 154 / 104 | +0.105 / +0.076 / +0.148 | 46% | 1.28 | +1.5 | (-0.03, +0.24) | -0.121 |
| `news_drift` XAU | all / train / test | 44 / 26 / 18 | +1.45 / +1.43 / +1.49 | 25% | 3.84 | +2.1 | (+0.27, +2.90) | -0.126 |
| `impulse_cont` USTEC | all / train / test | 651 / 390 / 261 | +0.051 / +0.012 / +0.111 | 34% | 1.10 | +0.9 | (-0.06, +0.17) | -0.091 |
| pyramid add (parent at +1.5R) | all | 305 | +0.040 | 42% | 1.10 | +0.5 | (-0.10, +0.19) | n/a |

- **`trend_day`** (grade B): the first 30 min of the US cash session (09:30-10:00 NY) sets the direction; enter 11:00 NY with a 3 ATR stop, hold to 16:00 NY.
  Literature prior: Gao, Han, Li, Zhou (first half-hour predicts the last; weaker on QQQ than SPY). Parameter surface: 80% of 108 cells positive in both halves.
  Two-sided (buys +0.12R, sells +0.09R), so not just drift. Quarterly E: +0.12, +0.07, **-0.11**, +0.34. Requires `/desk-max`: the hold is ~5 h.
- **`news_drift`** (grade C+): gold continues after a >= 2.5 ATR impulse bar on a scheduled USD release minute (08:30 / 10:00 NY; 14:00 is excluded because its 3 h hold
  would reach the daily closure). The same pattern on USTEC loses money. Mechanism is plausible (post-release drift) but **the evidence is 44 events and the
  threshold peaks sharply at 2.5 ATR** (44% of cells positive at 2.0, 28% at 3.0): classic winner's-curse territory. The latest quarter (11 trades) was -0.28R.
  Bayesian shrinkage (prior: true edge <= ~0.1 Sharpe per trade) keeps 30% of the observed mean, about +0.44R, which is what the planning case uses.
- **`impulse_cont`** (grade C): weakest. Buys +0.11R vs sells +0.01R (drift), quarterly E -0.09, +0.05, +0.25, -0.01. Kept only in the `extreme` tier as a variance experiment.
- **Pyramiding** earns ~0R per add: it raises variance, not edge.

### Management matters more than the entry filter
Emulating the live scalp rules (partial 50% at 0.7R, break-even at 1R, trail) on the same entries:

| strategy | pure / time exit | live scalp management | runner (BE at +1.5R, chosen) |
|---|---|---|---|
| trend_day | +0.115R | +0.073R (test +0.03) | +0.125R |
| impulse_cont | +0.103R | +0.005R | +0.093R |
| news_drift | +1.27R | +0.75R | +1.45R |

Playbook positions therefore use runner management; Python enforces it, including a time stop that also fires during the exchange break.

## Design that was implemented

- `engine/playbook.py` (pure; shared by live server and research), `engine/sessions.py` (NY/London DST without tzdata), wiring in `mt5_server.py`
  (signals in `wait_for_trigger`/`market_brief`, `open_trade(setup=...)` takes stop/target/size/time stop/management from the signal, `pyramid`, run-cap guard,
  per-position runner management, `_time_stops`), `tools\desk.ps1 tier`, `/desk <tier>`, doctrine and agent prompts rewritten around the playbook.
- **Validation:** replaying the live `detect()` over all history reproduces the research signals (trend_day 187/188, news_drift 44/44, impulse 581/596; extras explained by the
  hold-crosses-closure rule, now encoded); 84 tests pass; a smoke test through the real code path (real terminal, scratch state, DRY_RUN) passed, no orders sent.
- **Kill switch:** >= 20 live trades with mean R <= -0.3 suspends a strategy automatically. Forward results are journaled per strategy (`pattern = ai-<strategy>`).

### Tiers (`TIER` flag; default `moderate`)

| tier | strategies and size (x 5% risk) | adds |
|---|---|---|
| moderate | trend_day 0.5, news_drift 0.25 | none |
| high | trend_day 1.0, news_drift 0.5 | none |
| extreme | trend_day 1.0 (looser 1.0 ATR filter), news_drift 1.0, impulse_cont 1.0 | 1 pyramid add per winner |

In-sample chronological results over 1.6 years, at 5% x tier size (not a forecast; dominated by `news_drift`'s 44 trades):
moderate +243%, max DD 19%, worst day -3.8%; high +812%, DD 35%, worst day -7.6%; extreme +2715%, DD **88%**, worst day -20.8%, 53 days at/below the -12% daily stop.

**Monte Carlo, next 12 months** (bootstrap of each tier's trades; "skeptical" = per-strategy Bayesian shrinkage):

| tier | scenario | P(profit) | median | 5th pct | 95th pct | P(DD>50%) |
|---|---|---|---|---|---|---|
| moderate | skeptical | 77% | +37% | -29% | +170% | 2% |
| moderate | no edge | 40% | -9% | -52% | +85% | 16% |
| high | skeptical | 72% | +60% | -55% | +492% | 40% |
| high | no edge | 34% | -29% | -80% | +183% | 77% |
| extreme | skeptical | 48% | -11% | -97% | +3011% | 100% |
| extreme | no edge | 14% | -89% | -100% | +232% | 100% |

## Limits of this work (read before trusting any number)

- 17-20 months is short. `trend_day`'s CI includes zero; `news_drift` rests on 44 events and a threshold tuned on the same data.
- No historical economic calendar: scheduled-release minutes are a fixed 08:30/10:00 NY proxy (real FOMC/CPI/NFP dates were not separately identified).
- M5 bars hide intrabar order (stop-first is assumed) and real tick slippage on releases; spread was flat in the data, so a spread blow-out around news is not modelled.
- USTEC's +47% sample favours long-biased results; the controls and buy/sell splits reduce but cannot remove that.
- Backtested R counts costs but not swap on any overnight hold (none of the playbook holds overnight) or the ZAR conversion.

## Recommended operating procedure

1. Run `/loop /desk-max moderate` (both instruments) for at least two to three months. The expected volume is ~2-3 USTEC trend_day signals a week and ~2-3 gold news_drift signals a month.
   That is the point: at this evidence level the demo must collect an out-of-sample sample, not trade often.
2. Judge per strategy from the journal (`pattern = ai-<strategy>`), not the pooled number. The kill switch handles clear failure; do nothing else until n >= 30 per strategy.
3. Move to `high` only after `trend_day` shows >= 60 live trades with E > 0. Treat `extreme` as a lottery ticket you are willing to lose entirely.
4. Unlocking more research power is cheap: raise MT5 `Tools > Options > Charts > Max bars in chart` (a terminal setting; I did not change it) and re-run
   `tools\fetch_tf.py` / `tools\fetch_full.py` for years of M1/M5; add a historical USD event calendar to replace the fixed release minutes.
5. Config is untouched. Two settings are worth your decision: `run_max_minutes` 240 (a 4 h cap blocks `trend_day`; `/desk-max` removes it) and the fixed SAST
   `break` window (22:45-00:00) which, in US winter time, starts 75 minutes before USTEC's real 17:00 NY closure.

## Sources

- [The opening-range breakout paper, replicated on five indices: gross reproduced, net zero (MQL5)](https://www.mql5.com/en/blogs/post/776235): NQ gross +0.131R per trade, net +0.002R after 2.5 points of cost.
- [London Breakout on Gold: 3.7 Years of Backtests (MQL5)](https://www.mql5.com/en/blogs/post/777540): PF 1.31-1.38 claimed, no spread/slippage model stated, author does not claim live-cost survival.
- [Intraday Momentum: first half-hour predicts the last (Alpha Architect summary of Gao et al.)](https://alphaarchitect.com/2014/08/attention-prop-traders-the-first-half-hour-of-trading-predicts-the-last-half-hour/) and [CXO Advisory](https://www.cxoadvisory.com/calendar-effects/first-and-last-half-hours-of-trading-linked): effect weaker on QQQ than SPY.
- [QuantConnect recreation of Zarattini et al. ORB](https://www.quantconnect.com/research/18444/opening-range-breakout-for-stocks-in-play/): gross Sharpe 2.4 on US stocks, disputed in comments.
- [Gold price dynamics around the clock (CBS thesis)](https://research.cbs.dk/en/studentProjects/gold-price-dynamics-around-the-clock/): intraday gold seasonality, student work, weak evidence.
- This repo: `reports/research-20261022-1745.md`, `reports/playbook-backtest-20261104.md`, `tools/lab.py`, `tools/playbook_backtest.py`.
