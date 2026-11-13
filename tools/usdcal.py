r"""Historical USD economic calendar (MetaQuotes calendar via MT5, 2014 -> 4 months ahead): sync + loader.

  .venv\Scripts\python.exe tools\usdcal.py sync      # copy the MT5 export into data/usd_events.csv
  .venv\Scripts\python.exe tools\usdcal.py summary   # counts per family and year

The export is produced INSIDE the terminal by tools/mql5/ExportUsdCalendar.mq5 (the Python MT5 package has no calendar API):
  tools\refresh_calendar.ps1  (restarts the terminal once, only when no position/order is open), or run the script/service by hand.
Times are UTC epoch seconds (the Exness server clock is GMT): verified against NFP = 08:30 New York in both winter and summer.
Quality: timestamps and importance are reliable. `forecast` exists for ~75% of events and is noisy (e.g. NFP forecasts), so no
research here depends on surprise sizes; `actual`/`prev` are kept as given.
"""
import csv
import shutil
import sys
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
SRC = Path.home() / "AppData" / "Roaming" / "MetaQuotes" / "Terminal" / "Common" / "Files" / "usd_calendar.csv"
DST = ROOT / "data" / "usd_events.csv"

from engine.news import FAMILY_BY_NAME as _EXACT, TIER1, family  # noqa: E402,F401  (single source of truth, shared with the live gate)


def sync():
    """Copy the terminal's export into data/usd_events.csv."""
    if not SRC.exists():
        sys.exit(f"{SRC} not found: run tools\\refresh_calendar.ps1 (or the ExportUsdCalendar script in MT5) first")
    DST.parent.mkdir(exist_ok=True)
    shutil.copyfile(SRC, DST)
    meta = SRC.with_name(SRC.name + ".meta")
    return DST, (meta.read_text(encoding="utf-8", errors="ignore") if meta.exists() else "")


def _f(x):
    return float(x) if x not in ("", None) else np.nan


def load(path=None, min_importance=3, families=None):
    """Events as a list of dicts sorted by time: ts (UTC epoch), name, family, importance, actual, forecast, prev.
    One entry per (ts, family): the several lines of a single release (NFP + unemployment + earnings) collapse to one moment."""
    p = Path(path) if path else DST
    if not p.exists():
        raise FileNotFoundError(f"{p} missing: run `tools\\usdcal.py sync`")
    seen, out = set(), []
    with open(p, encoding="cp1252", newline="") as fh:
        for r in csv.DictReader(fh):
            imp = int(r["importance"])
            fam = family(r["name"])
            if imp < min_importance and fam not in (families or ()):
                continue
            if families is not None and fam not in families:
                continue
            ts = int(r["ts_server"])
            if (ts, fam) in seen:
                continue
            seen.add((ts, fam))
            out.append({"ts": ts, "name": r["name"], "family": fam, "importance": imp, "actual": _f(r["actual"]),
                        "forecast": _f(r["forecast"]), "prev": _f(r["prev"])})
    out.sort(key=lambda e: e["ts"])
    return out


def moments(families=TIER1, **kw):
    """Distinct release timestamps for the given families (default: the tier-1 set)."""
    return load(families=set(families), min_importance=0, **kw)


def summary():
    from datetime import datetime, timezone
    ev = load(min_importance=0)
    print(f"{len(ev)} release moments; range {datetime.fromtimestamp(ev[0]['ts'], timezone.utc):%Y-%m-%d} -> "
          f"{datetime.fromtimestamp(ev[-1]['ts'], timezone.utc):%Y-%m-%d}")
    fams = Counter(e["family"] for e in ev if e["family"] != "other")
    print("tier-1 and named families:", dict(fams.most_common()))
    yrs = Counter(datetime.fromtimestamp(e["ts"], timezone.utc).year for e in ev if e["family"] in TIER1)
    print("tier-1 per year:", dict(sorted(yrs.items())))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "summary"
    if cmd == "sync":
        dst, meta = sync()
        print("synced ->", dst)
        print(meta)
    summary()
