r"""Calendar-driven event study: do USD releases leave a tradable post-release drift, on XAUUSDm and USTECm?

  .venv\Scripts\python.exe tools\event_study.py [--min-year-xau 2017.3]

Uses the MT5 historical USD calendar (tools/usdcal.py) and the deep M5 history (XAU 2017-2026, USTEC 2024-2026).
For every tier-1 release the event bar is the M5 bar that opens at the release time. A trade follows the event bar's
direction from the NEXT bar's open (market entry, real spread + 0.5 x spread slippage), stop = `stop_atr` x ATR re-based on
the fill, break-even at +1.5R, no partial, no target, closed at the time stop (same runner management and closure rule as
engine/playbook.py). Reported against the opposite-direction control with the same stop geometry.

Tests, in this order (the first is the ONLY confirmatory one; the rest are exploratory and say so):
  T1  the live `news_drift` rule (impulse >= 2.5 ATR, body >= 0.6, release minute 08:30/10:00 NY) on XAU 2017-2024.
      The rule was tuned on 2025-26 only, so 2017-2024 is a true hold-out.
  T2  the same rule using the REAL calendar (all tier-1 releases, any minute) instead of the hard-coded minutes.
  T3  threshold surface and per-family breakdown (exploratory; the multiple-comparison count is printed).
  T4  the same rule on USTEC (exploratory).
"""
import argparse
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import lab  # noqa: E402
import usdcal  # noqa: E402
from engine import playbook as pb  # noqa: E402

P = pb.STRATEGIES["news_drift"]["p"]
OOS_END = datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp()


def event_sigs(m, events, thr, body, minutes=None, start_ts=0.0, end_ts=1e12, hold=None, stop_atr=None):
    """One signal per release whose event bar is an impulse (range >= thr x ATR before it, |body| >= `body` x range)."""
    hold = hold or P["hold"]
    stop_atr = stop_atr or P["stop_atr"]
    out = []
    for e in events:
        if not (start_ts <= e["ts"] < end_ts):
            continue
        t0 = e["ts"] // 300 * 300
        i0 = int(np.searchsorted(m.t, t0))
        if i0 >= m.n - hold - 4 or i0 < 340 or m.t[i0] != t0:
            continue
        if not m.gap_ok(i0 - 14, i0 + hold + 3):
            continue
        if minutes is not None and m.nym[i0] not in minutes:
            continue
        a = pb._atr(m.h, m.l, m.c, i0)
        rng, bd = m.h[i0] - m.l[i0], m.c[i0] - m.o[i0]
        if not a > 0 or rng < thr * a or abs(bd) < body * rng:
            continue
        if m.nym[i0] < 1020 and m.nym[i0] + (hold + 2) * 5 - 1 > pb.SESSION_END_MIN:
            continue  # the hold would cross the daily closure (same rule as live)
        i = i0 + 1
        side = "buy" if bd > 0 else "sell"
        ts_stop = m.t[i0] + (hold + 2) * 300 - 60
        last = max(i, min(int(np.searchsorted(m.t, ts_stop + 60, "left")) - 1, m.n - 1))
        e0 = m.o[i]
        sl = e0 - stop_atr * a if side == "buy" else e0 + stop_atr * a
        out.append(dict(i=i, side=side, sl=sl, last=last, tag=e["family"], be_r=pb.RUNNER["be_r"], move=rng / a, name=e["name"]))
    return out


def run(m, sigs):
    res = lab.run_signals(m, sigs, one_at_a_time=True)
    by_i = {s["i"]: s for s in sigs}
    for r in res:
        r["tag"] = by_i[r["i"]]["tag"]
    return res


def line(label, trs):
    return f"{label:<46s} {lab.fmt(lab.stats(trs, boot=1000))}"


def year_of(r):
    return datetime.fromtimestamp(r["t"], timezone.utc).year


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-year-xau", type=float, default=2017.3)
    a = ap.parse_args()
    lines = []

    def out(s=""):
        print(s)
        lines.append(s)

    ev = usdcal.moments(usdcal.TIER1)
    out("# Calendar event study (USD tier-1 releases)\n")
    out(f"Calendar: {len(ev)} tier-1 release moments 2014-2027 (MT5/MetaQuotes). Families: " +
        ", ".join(f"{k}={v}" for k, v in sorted(defaultdict(int, {f: sum(1 for e in ev if e['family'] == f) for f in usdcal.TIER1}).items())))
    xau, ust = lab.Mkt("XAUUSDm"), lab.Mkt("USTECm")
    start = datetime(2017, 4, 1, tzinfo=timezone.utc).timestamp()
    out(f"XAU M5: {xau.n} bars {datetime.fromtimestamp(xau.t[0], timezone.utc):%Y-%m-%d} -> "
        f"{datetime.fromtimestamp(xau.t[-1], timezone.utc):%Y-%m-%d} (continuous from 2017-04; 2014-16 is sparse, excluded; "
        f"spread recorded only from 2023: earlier bars use the median of recorded spreads)")
    out(f"USTEC M5: {ust.n} bars from {datetime.fromtimestamp(ust.t[0], timezone.utc):%Y-%m-%d}; holes 2023-07..2024-03 and 2026-07..10\n")

    thr, body = P["thr"], P["body"]
    out(f"## T1 - live news_drift rule on XAU (thr {thr} ATR, body {body}, minutes 08:30/10:00 NY; 14:00 excluded by the closure rule)\n```")
    base = dict(thr=thr, body=body, minutes=(510, 600, 840))
    for lab_, s_, e_ in (("2017-04 .. 2024-12  HOLD-OUT (never tuned on)", start, OOS_END),
                         ("2025-01 .. 2026-11  (the tuning window)", OOS_END, 1e12), ("all", start, 1e12)):
        out(line(lab_, run(xau, event_sigs(xau, ev, start_ts=s_, end_ts=e_, **base))))
    out("```")
    ho = run(xau, event_sigs(xau, ev, start_ts=start, end_ts=OOS_END, **base))
    for y in range(2017, 2025):
        out(f"  {y}: {lab.fmt(lab.stats([r for r in ho if year_of(r) == y], boot=300))}")

    out(f"\n## T2 - same rule on EVERY tier-1 release (real calendar times) on XAU\n```")
    anym = dict(thr=thr, body=body, minutes=None)
    for lab_, s_, e_ in (("2017-04 .. 2024-12 hold-out", start, OOS_END), ("2025-01 .. 2026-11", OOS_END, 1e12), ("all", start, 1e12)):
        out(line(lab_, run(xau, event_sigs(xau, ev, start_ts=s_, end_ts=e_, **anym))))
    out("```")

    out("\n## T3 - exploratory: threshold surface and per-family (XAU, all years; read as a surface, not as picks)\n```")
    for thr_ in (1.0, 1.5, 2.0, 2.5, 3.0, 4.0):
        for b_ in (0.0, 0.6):
            out(line(f"thr {thr_} body {b_}", run(xau, event_sigs(xau, ev, start_ts=start, thr=thr_, body=b_))))
    out("--- per family at thr 1.5 body 0.5 (many cells: expect a few false positives) ---")
    allr = run(xau, event_sigs(xau, ev, start_ts=start, thr=1.5, body=0.5))
    for f in usdcal.TIER1:
        out(line(f"family {f}", [r for r in allr if r["tag"] == f]))
    out("```")

    out("\n## T4 - exploratory: the same rule on USTEC\n```")
    ust_start = datetime(2024, 4, 1, tzinfo=timezone.utc).timestamp()
    for thr_ in (1.5, 2.0, 2.5, 3.0):
        out(line(f"USTEC thr {thr_} body 0.6 all releases", run(ust, event_sigs(ust, ev, start_ts=ust_start, thr=thr_, body=0.6))))
    out(line("USTEC thr 2.5 body 0.6 minutes 08:30/10:00", run(ust, event_sigs(ust, ev, start_ts=ust_start, thr=2.5, body=0.6, minutes=(510, 600)))))
    out("```")
    p = ROOT / "reports" / f"event-study-{datetime.now():%Y%m%d}.md"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("wrote", p)


if __name__ == "__main__":
    main()
