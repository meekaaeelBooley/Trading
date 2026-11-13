# Playbook backtest 2026-11-04

Live `detect()` replayed bar by bar; runner management (BE +1.5R, no partial, no target, time stop); real per-bar spread + 0.5x slippage on every market fill; opposite-direction control = same entry and stop distance, other side. Train = first 60% of trades by time, test = last 40%.

## Per strategy (extreme-tier thresholds; one trade per signal, overlapping allowed as live has no position cap)

| strategy | scope | n | E (R) | win | PF | t | 95% CI | control E | edge vs control |
|---|---|---|---|---|---|---|---|---|---|
| trend_day | all | 428 | +0.056 | 46% | 1.14 | +1.1 | (-0.04, +0.16) | -0.167 | +0.224 |
| trend_day | train | 256 | +0.006 | 43% | 1.01 | +0.1 | (-0.12, +0.13) | -0.210 | +0.216 |
| trend_day | test | 172 | +0.131 | 49% | 1.35 | +1.6 | (-0.03, +0.29) | -0.104 | +0.235 |
| impulse_cont (shelved) | all | 1109 | -0.030 | 31% | 0.95 | -0.7 | (-0.12, +0.06) | -0.152 | +0.122 |
| impulse_cont (shelved) | train | 665 | -0.138 | 27% | 0.78 | -2.4 | (-0.25, -0.02) | -0.152 | +0.015 |
| impulse_cont (shelved) | test | 444 | +0.131 | 37% | 1.26 | +1.8 | (-0.01, +0.28) | -0.152 | +0.283 |
| news_drift (shelved) | all | 483 | +0.032 | 15% | 1.05 | +0.3 | (-0.18, +0.26) | -0.150 | +0.182 |
| news_drift (shelved) | train | 289 | -0.324 | 11% | 0.56 | -3.1 | (-0.52, -0.11) | -0.156 | -0.168 |
| news_drift (shelved) | test | 194 | +0.562 | 21% | 1.91 | +2.5 | (+0.13, +1.01) | -0.142 | +0.704 |
| pyramid | all | 625 | -0.014 | 40% | 0.97 | -0.3 | (-0.12, +0.09) | +nan | +nan |
| pyramid | train | 375 | -0.066 | 38% | 0.87 | -1.0 | (-0.19, +0.08) | +nan | +nan |
| pyramid | test | 250 | +0.065 | 42% | 1.17 | +0.8 | (-0.10, +0.25) | +nan | +nan |

trend_day restricted to the high/moderate threshold (>=1.5 ATR): n=324 E=+0.071R win=47% PF=1.18 t=+1.2 CI=(-0.04,+0.19) edge vs control +0.272

Shelved strategies (in no tier): impulse_cont: deep history 2024-2026 n=1109 E=-0.03R t=-0.7, sign flips between halves (reports/playbook-backtest-20261104.md); news_drift: hold-out 2017-2024 n=211 E=-0.26R t=-1.9; in-sample 2025-26 result was the gold bull run (reports/event-study-20261104.md)

## Tiers: chronological equity over each tier's own sample length (risk per trade = 5.0% x tier size)

| tier | trades/yr | total return | CAGR | max DD | worst day | days <= -12% | E (R) |
|---|---|---|---|---|---|---|---|
| moderate | 135 | +58% | +21% | 23% | -2.9% | 0 | +0.071 |
| high | 135 | +101% | +34% | 42% | -5.8% | 0 | +0.071 |
| extreme | 438 | -65% | -35% | 94% | -20.4% | 7 | +0.015 |

## Next 12 months, Monte Carlo (bootstrap of the tier's trades; edge scenario = fraction of the observed mean R)

| tier | edge kept | P(profit) | median | 5th pct | 95th pct | P(DD>30%) | P(DD>50%) |
|---|---|---|---|---|---|---|---|
| moderate | skeptical | 68% | +14% | -29% | +92% | 27% | 1% |
| moderate | +100% | 74% | +21% | -25% | +101% | 20% | 1% |
| moderate | +50% | 58% | +6% | -35% | +79% | 33% | 2% |
| moderate | +0% | 44% | -4% | -42% | +61% | 45% | 4% |
| moderate | -50% | 28% | -17% | -49% | +40% | 61% | 9% |
| high | skeptical | 62% | +19% | -54% | +231% | 86% | 32% |
| high | +100% | 69% | +35% | -48% | +264% | 82% | 26% |
| high | +50% | 52% | +3% | -61% | +191% | 90% | 40% |
| high | +0% | 38% | -17% | -69% | +133% | 94% | 53% |
| high | -50% | 24% | -36% | -76% | +77% | 98% | 68% |
| extreme | skeptical | 39% | -31% | -90% | +429% | 100% | 97% |
| extreme | +100% | 36% | -35% | -91% | +433% | 100% | 97% |
| extreme | +50% | 32% | -45% | -93% | +334% | 100% | 98% |
| extreme | +0% | 25% | -56% | -94% | +246% | 100% | 99% |
| extreme | -50% | 21% | -63% | -95% | +200% | 100% | 99% |

Skeptical = each strategy's observed mean shrunk by its own Bayesian factor (trend_day x0.81); this is the planning case. Edge kept: 100% = the mean R observed in this sample continues; 50% = half of it; 0% = no edge (only costs and variance); -50% = the sample edge was a mirage and the true mean is the mirror image.
