r"""Out-of-sample style validation of the live playbook (engine/playbook.py) on Exness M5 history, per risk tier.

  .venv\Scripts\python.exe tools\playbook_backtest.py [--cache] [--paths 4000]

1. Replays the LIVE detect() bar by bar (no look-ahead: each call sees only bars up to that close) for the most permissive
   tier (extreme) and derives the stricter tiers by filtering (trend_day move threshold, strategy membership, size).
2. Simulates each signal with the runner management used live: market entry at the next open with real spread + 0.5 x
   spread slippage, stop (ATR re-based on the fill or bar extreme), break-even at +1.5R, NO partial, NO target (6R far
   order), time stop. Extreme tier adds one pyramid position when the parent is +1.5R (stop at the parent's break-even).
3. Reports per-strategy stats with an opposite-direction control and a chronological train/test split, then per-tier
   equity (risk per trade = risk_pct 5% x tier size) and a Monte Carlo of the next 12 months under skeptical edge scenarios.
Writes reports/playbook-backtest-<date>.md.
"""
import argparse
import pickle
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import lab  # noqa: E402
from engine import playbook as pb  # noqa: E402

RISK_PCT = 5.0  # config risk_pct (user-owned); tiers scale it with risk_mult
SYMS = {"USTECm": ("trend_day", "impulse_cont"), "XAUUSDm": ("news_drift",)}


def replay(m, symbol, tier="extreme"):
    arr = {"time": m.t, "open": m.o, "high": m.h, "low": m.l, "close": m.c}
    out = {}
    for k in range(330, m.n):
        b = {key: v[:k + 1] for key, v in arr.items()}
        for s in pb.detect(symbol, b, tier, max_age=0, include_shelved=True):
            s["k"] = k
            out.setdefault(s["strategy"], []).append(s)
    return out


def to_trade(m, s, be_r=pb.RUNNER["be_r"]):
    i = s["k"] + 1
    if i >= m.n:
        return None
    buy = s["side"] == "buy"
    e = m.o[i]
    sl = (e - s["sl_dist"] if buy else e + s["sl_dist"]) if s["sl_kind"] == "atr" else s["sl"]
    last = int(np.searchsorted(m.t, s["time_stop_ts"] + 60, "left")) - 1
    last = max(i, min(last, m.n - 1))
    res = lab.sim(m, i, s["side"], sl, last=last, be_r=be_r)
    if res is None:
        return None
    opp = "sell" if buy else "buy"
    d = abs(m.o[i] - sl)
    c2 = lab.sim(m, i, opp, m.o[i] + d if buy else m.o[i] - d, last=last, be_r=be_r)
    res.update(i=i, side=s["side"], t=int(m.t[i]), strategy=s["strategy"], ctrl=c2["r"] if c2 else np.nan,
               move=s.get("move_atr"), sl_abs=sl, entry=m.o[i], last=last)
    return res


def pyramid(m, parent):
    """Add at the bar after the parent first reaches +1.5R; stop = the parent's entry (its break-even)."""
    buy, e, rd = parent["side"] == "buy", parent["entry"], parent["rd"]
    for j in range(parent["i"], min(parent["j"], parent["last"])):
        fav = (m.h[j] - e) if buy else (e - (m.l[j] + m.sp[j]))
        if fav >= pb.ADD_AT_R * rd:
            k = j + 1
            if k >= m.n or k > parent["j"]:
                return None
            res = lab.sim(m, k, parent["side"], e, last=parent["last"])
            if res:
                res.update(i=k, side=parent["side"], t=int(m.t[k]), strategy="pyramid", ctrl=np.nan)
            return res
    return None


def tier_trades(trades_by_strat, tier):
    """Trades with the risk fraction (% of equity) the tier assigns them; extreme also adds the pyramids."""
    td, out = pb.TIERS[tier], []
    for name, lst in trades_by_strat.items():
        if name == "pyramid":
            if td["adds"]:
                out += [{**x, "risk": RISK_PCT * td["add_risk"]} for x in lst]
            continue
        cap = td["risk"].get(name)
        if not cap:
            continue
        for x in lst:
            if name == "trend_day" and x["move"] < td["min_move_atr"]:
                continue
            out.append({**x, "risk": RISK_PCT * cap})
    return sorted(out, key=lambda x: x["t"])


def path_stats(trs, years):
    """Chronological compounded equity at each trade's own risk %; worst day and max drawdown."""
    eq, peak, dd, day, daily = 1.0, 1.0, 0.0, None, {}
    for x in trs:
        eq *= max(0.0, 1 + x["risk"] / 100 * x["r"])
        peak, dd = max(peak, eq), max(dd, 1 - eq / peak)
        d = x["t"] // 86400
        daily[d] = daily.get(d, 0.0) + x["risk"] / 100 * x["r"]
    worst = min(daily.values()) if daily else 0.0
    return {"ret": eq - 1, "cagr": eq ** (1 / years) - 1 if eq > 0 else -1, "dd": dd, "worst_day": worst,
            "days_stop": sum(1 for v in daily.values() if v <= -0.12), "n": len(trs), "n_yr": len(trs) / years}


def shrink_factors(trades_by_strat, prior_sd=0.10):
    """Skeptical prior on each strategy's true edge: mean ~ N(0, (prior_sd x trade SD)^2), i.e. true edges are at most
    ~0.1 Sharpe per trade. Posterior mean = observed mean x tau^2 / (tau^2 + SE^2). Thin samples shrink hardest."""
    out = {}
    for name, lst in trades_by_strat.items():
        r = np.array([x["r"] for x in lst])
        if len(r) < 5 or r.std() == 0:
            out[name] = 0.0
            continue
        tau2, se2 = (prior_sd * r.std()) ** 2, r.var(ddof=1) / len(r)
        out[name] = tau2 / (tau2 + se2)
    return out


def monte_carlo(trs, years, scen, paths=4000, seed=3, shrink=None):
    """Bootstrap the tier's trades for 12 months. scen k scales every strategy's sample mean R (k=1 as observed, 0 none,
    <0 negative); k='bayes' applies the per-strategy skeptical shrinkage factors."""
    rng = np.random.default_rng(seed)
    r = np.array([x["r"] for x in trs])
    rk = np.array([x["risk"] for x in trs]) / 100
    if len(r) < 10:
        return None
    names = np.array([x["strategy"] for x in trs])
    mus = {n: r[names == n].mean() for n in set(names)}
    n = max(1, int(round(len(r) / years)))
    res = {}
    for k in scen:
        if k == "bayes":
            shift = np.array([mus[nm] * ((shrink or {}).get(nm, 0.0) - 1) for nm in names])
        else:
            shift = np.array([mus[nm] * (k - 1) for nm in names])
        idx = rng.integers(0, len(r), (paths, n))
        steps = np.maximum(1 + rk[idx] * (r[idx] + shift[idx]), 0.0)
        curve = np.cumprod(steps, axis=1)
        peak = np.maximum.accumulate(np.concatenate([np.ones((paths, 1)), curve], axis=1), axis=1)[:, 1:]
        dd = (1 - curve / peak).max(axis=1)
        end = curve[:, -1]
        res[k] = {"p_profit": float((end > 1).mean()), "med": float(np.median(end) - 1), "p5": float(np.percentile(end, 5) - 1),
                  "p95": float(np.percentile(end, 95) - 1), "p_dd30": float((dd > 0.30).mean()),
                  "p_dd50": float((dd > 0.50).mean()), "n": n}
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", action="store_true", help="reuse data/playbook_signals.pkl if present")
    ap.add_argument("--paths", type=int, default=4000)
    a = ap.parse_args()
    cache = ROOT / "data" / "playbook_signals.pkl"
    mk = {s: lab.Mkt(s) for s in SYMS}
    if a.cache and cache.exists():
        sigs = pickle.load(open(cache, "rb"))
    else:
        sigs = {}
        for s, m in mk.items():
            t0 = time.time()
            sigs[s] = replay(m, s)
            print(f"replayed {s}: {sum(len(v) for v in sigs[s].values())} signals in {time.time() - t0:.0f}s", flush=True)
        pickle.dump(sigs, open(cache, "wb"))
    lines = [f"# Playbook backtest {time.strftime('%Y-%m-%d')}", "",
             "Live `detect()` replayed bar by bar; runner management (BE +1.5R, no partial, no target, time stop); real "
             "per-bar spread + 0.5x slippage on every market fill; opposite-direction control = same entry and stop distance, "
             "other side. Train = first 60% of trades by time, test = last 40%.", ""]
    trades = {}
    span = {}
    for s, m in mk.items():
        span[s] = m.n / 70000.0  # effective years of data (~70k M5 bars a year): USTEC has two multi-month holes
        for name, lst in sigs[s].items():
            trs = [x for x in (to_trade(m, q) for q in lst) if x]
            trades[name] = trs
            span[name] = span[s]
            ptr = [p for p in (pyramid(m, x) for x in trs) if p] if name != "news_drift" or True else []
            trades.setdefault("pyramid", []).extend(ptr)
    years = max(span.values())
    notes = {n: f" (SHELVED: {pb.SHELVED[n]})" for n in pb.SHELVED}
    lines += ["## Per strategy (extreme-tier thresholds; one trade per signal, overlapping allowed as live has no position cap)", "",
              "| strategy | scope | n | E (R) | win | PF | t | 95% CI | control E | edge vs control |", "|---|---|---|---|---|---|---|---|---|---|"]
    for name in ("trend_day", "impulse_cont", "news_drift", "pyramid"):
        trs = sorted(trades.get(name, []), key=lambda x: x["t"])
        if not trs:
            continue
        for label, part in (("all", trs), ("train", lab.split(trs)[0]), ("test", lab.split(trs)[1])):
            st = lab.stats(part)
            lines.append(f"| {name}{' (shelved)' if name in pb.SHELVED else ''} | {label} | {st['n']} | {st['E']:+.3f} | {st['win']:.0%} | {st['pf']:.2f} | {st['t']:+.1f} | "
                         f"({st['lo']:+.2f}, {st['hi']:+.2f}) | {st['ctrl']:+.3f} | {st['edge']:+.3f} |")
        print(name, lab.fmt(lab.stats(trs)))
    # trend_day at the high/moderate threshold
    td15 = [x for x in trades.get("trend_day", []) if x["move"] >= 1.5]
    st = lab.stats(td15)
    lines += ["", f"trend_day restricted to the high/moderate threshold (>=1.5 ATR): n={st['n']} E={st['E']:+.3f}R "
                  f"win={st['win']:.0%} PF={st['pf']:.2f} t={st['t']:+.1f} CI=({st['lo']:+.2f},{st['hi']:+.2f}) edge vs control {st['edge']:+.3f}"]
    lines += ["", "Shelved strategies (in no tier): " + "; ".join(f"{n}: {w}" for n, w in pb.SHELVED.items()), "",
              f"## Tiers: chronological equity over each tier's own sample length (risk per trade = {RISK_PCT}% x tier size)", "",
              "| tier | trades/yr | total return | CAGR | max DD | worst day | days <= -12% | E (R) |", "|---|---|---|---|---|---|---|---|"]
    scen = ("bayes", 1.0, 0.5, 0.0, -0.5)
    shr = shrink_factors({k: v for k, v in trades.items() if k != "pyramid"})
    mc, lines_years = {}, {}
    for tier in ("moderate", "high", "extreme"):
        trs = tier_trades(trades, tier)
        years = max([span[n] for n in pb.TIERS[tier]["risk"] if n in span] or [1.0])  # the tier's strategies' data length
        ps = path_stats(trs, years)
        e = np.mean([x["r"] for x in trs]) if trs else float("nan")
        lines.append(f"| {tier} | {ps['n_yr']:.0f} | {ps['ret']:+.0%} | {ps['cagr']:+.0%} | {ps['dd']:.0%} | {ps['worst_day']:+.1%} | "
                     f"{ps['days_stop']} | {e:+.3f} |")
        mc[tier] = monte_carlo(trs, years, scen, a.paths, shrink=shr)
        lines_years[tier] = years
    lines += ["", "## Next 12 months, Monte Carlo (bootstrap of the tier's trades; edge scenario = fraction of the observed mean R)", "",
              "| tier | edge kept | P(profit) | median | 5th pct | 95th pct | P(DD>30%) | P(DD>50%) |", "|---|---|---|---|---|---|---|---|"]
    for tier, res in mc.items():
        for k, v in (res or {}).items():
            lab_k = "skeptical" if k == "bayes" else f"{k:+.0%}"
            lines.append(f"| {tier} | {lab_k} | {v['p_profit']:.0%} | {v['med']:+.0%} | {v['p5']:+.0%} | {v['p95']:+.0%} | "
                         f"{v['p_dd30']:.0%} | {v['p_dd50']:.0%} |")
    lines += ["", "Skeptical = each strategy's observed mean shrunk by its own Bayesian factor (" +
              ", ".join(f"{k} x{v:.2f}" for k, v in shr.items() if k in pb.TIERS["extreme"]["risk"]) + "); this is the planning case. Edge kept: 100% = the mean R observed in this sample continues; 50% = half of it; 0% = no edge (only costs and variance); "
                  "-50% = the sample edge was a mirage and the true mean is the mirror image."]
    md = "\n".join(lines) + "\n"
    out = ROOT / "reports" / f"playbook-backtest-{time.strftime('%Y%m%d')}.md"
    out.write_text(md, encoding="utf-8")
    print(md)
    print("written", out)


if __name__ == "__main__":
    main()
