r"""Re-test the classic M5 intraday families on the DEEP history (XAU 2017-2026 = ~9.5 y; USTEC 2024-2026).
Same simulator and costs as the playbook (tools/lab.py). One pre-declared parameter set per family (the textbook one), a small
neighbourhood to show the surface, chronological 60/40 split, opposite-direction control. Writes reports/deep-families-<date>.md.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import families as fam  # noqa: E402
import lab  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
lines = []


def out(s=""):
    print(s)
    lines.append(s)


def trim(m, start):
    """View of Mkt from `start` (UTC datetime): keep arrays whole (ATR warm-up) but drop earlier signals via tag filter."""
    return start.timestamp()


def go(m, name, sigs, t0):
    sigs = [s for s in sigs if m.t[s["i"]] >= t0]
    trs = lab.run_signals(m, sigs)
    tr, te = lab.split(trs, 0.6)
    out(f"{name:<44s} ALL  {lab.fmt(lab.stats(trs, boot=800))}")
    out(f"{'':<44s} first60% {lab.fmt(lab.stats(tr, boot=300))}")
    out(f"{'':<44s} last40%  {lab.fmt(lab.stats(te, boot=300))}")
    return trs


def main():
    xau, ust = lab.Mkt("XAUUSDm"), lab.Mkt("USTECm")
    t_x = datetime(2017, 4, 3, tzinfo=timezone.utc).timestamp()
    t_u = datetime(2024, 4, 1, tzinfo=timezone.utc).timestamp()
    out("# Deep-history re-test of the classic families\n")
    out(f"XAUUSDm from 2017-04 ({(xau.t[-1] - t_x) / 86400 / 365.25:.1f} y), USTECm from 2024-04 ({(ust.t[-1] - t_u) / 86400 / 365.25:.1f} y, two data holes).")
    out("Gold spread is only recorded from 2023: earlier bars use the median recorded spread (conservative for the pre-2023 gold market).\n")
    for nm, m, t0 in (("XAUUSDm", xau, t_x), ("USTECm", ust, t_u)):
        out(f"## {nm}\n```")
        for start, n in ((570, 3), (570, 6), (480, 3)):
            go(m, f"ORB NY start {start // 60}:{start % 60:02d} n={n} tp2R", fam.orb(m, "ny", start, n, 12, 2.0, 60), t0)
        go(m, "London range break (00-08 UTC-ish) tp2R", fam.asian_break(m, 0, 480, 36, 2.0), t0)
        go(m, "London/Asian sweep fade", fam.asian_break(m, 0, 480, 36, 2.0, fade=True), t0)
        for lb in (6,):
            go(m, f"session momentum 09:30+{lb * 5}min -> 15:30 (stop 3 ATR)", fam.intraday_mom(m, 570, lb, 930, 955, 3.0), t0)
            go(m, f"session momentum 09:30+{lb * 5}min -> 11:00..16:00 (the trend_day recipe)", fam.intraday_mom(m, 570, lb, 660, 955, 3.0, min_move_atr=1.5), t0)
        go(m, "gap fade (2 ATR stop)", fam.gap(m, fade=True), t0)
        go(m, "gap follow", fam.gap(m, fade=False), t0)
        out("```\n")
    p = ROOT / "reports" / f"deep-families-{datetime.now():%Y%m%d}.md"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("wrote", p)


if __name__ == "__main__":
    main()
