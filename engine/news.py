import csv
import json
import os
import time
import urllib.request
from datetime import datetime
from pathlib import Path

# ---- MetaQuotes calendar (exported from MT5 by tools/mql5/*.mq5 -> data/usd_events.csv): release families and fallback source
FAMILY_BY_NAME = {
    "Nonfarm Payrolls": "nfp", "Unemployment Rate": "nfp", "Average Hourly Earnings m/m": "nfp",
    "CPI m/m": "cpi", "Core CPI m/m": "cpi", "CPI y/y": "cpi", "CPI": "cpi", "Core CPI n.s.a. m/m": "cpi",
    "Fed Interest Rate Decision": "fomc", "FOMC Statement": "fomc", "FOMC Economic Projections": "fomc",
    "FOMC Press Conference": "fomc_presser", "FOMC Minutes": "fomc_minutes",
    "Core PCE Price Index m/m": "pce", "Core PCE Price Index y/y": "pce",
    "ADP Nonfarm Employment Change": "adp",
    "ISM Manufacturing PMI": "ism", "ISM Non-Manufacturing PMI": "ism",
    "Retail Sales m/m": "retail", "Core Retail Sales m/m": "retail",
    "PPI m/m": "ppi", "Core PPI m/m": "ppi",
    "GDP q/q": "gdp", "GDP Sales q/q": "gdp",
    "Initial Jobless Claims": "claims", "JOLTS Job Openings": "jolts",
    "Durable Goods Orders m/m": "durables", "CB Consumer Confidence Index": "confidence",
}
TIER1 = ("nfp", "cpi", "fomc", "pce", "adp", "ism", "retail", "ppi", "gdp")  # releases that move gold and indices
GATE_FAMILIES = TIER1 + ("fomc_presser", "powell")  # what the live news gate blocks around (the FF "High" USD set)
CSV_MAX_AGE_DAYS = 14


def family(name):
    if name in FAMILY_BY_NAME:
        return FAMILY_BY_NAME[name]
    if "Powell" in name and ("Speech" in name or "Testimony" in name):
        return "powell"
    return "other"


def default_csv_paths(root=None):
    """Where the MT5 calendar export may live: the repo copy (tools/usdcal.py sync) and the terminal's Common/Files."""
    out = []
    if root:
        out.append(Path(root) / "data" / "usd_events.csv")
    app = os.environ.get("APPDATA")
    if app:
        out.append(Path(app) / "MetaQuotes" / "Terminal" / "Common" / "Files" / "usd_calendar.csv")
    return out


def events_from_csv(paths, now_ts, back_h=24, ahead_days=21, max_age_days=CSV_MAX_AGE_DAYS):
    """Gate events (USD, tier-1 + FOMC presser + Powell) in [now-back_h, now+ahead_days] from the freshest usable CSV.
    Returns (events, source_path, age_days) or None when no export is fresh enough (fail closed upstream)."""
    best = None
    for p in paths:
        try:
            age = (now_ts - Path(p).stat().st_mtime) / 86400
        except OSError:
            continue
        if age <= max_age_days and (best is None or age < best[1]):
            best = (p, age)
    if best is None:
        return None
    lo, hi, seen, evs = now_ts - back_h * 3600, now_ts + ahead_days * 86400, set(), []
    with open(best[0], encoding="cp1252", newline="") as fh:
        for r in csv.DictReader(fh):
            ts = int(r["ts_server"])
            if not lo <= ts <= hi:
                continue
            fam = family(r["name"])
            if fam not in GATE_FAMILIES or (ts, fam) in seen:
                continue
            seen.add((ts, fam))
            evs.append({"title": r["name"], "ts": float(ts)})
    return sorted(evs, key=lambda e: e["ts"]), str(best[0]), best[1]


def fetch_events(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = json.load(r)
    evs = [{"title": e["title"], "ts": datetime.fromisoformat(e["date"]).timestamp()}
           for e in raw if e.get("country") == "USD" and e.get("impact") == "High"]
    return sorted(evs, key=lambda x: x["ts"])


def refresh(path, url, fetch=fetch_events, fallback_csv=None, now_ts=None):
    """Web feed first. If it fails and `fallback_csv` (list of paths) holds a fresh MT5 calendar export, use that
    (scheduled events rarely change within two weeks). Otherwise fail closed: the old cache is left to go stale."""
    try:
        evs, src = fetch(url), "web"
    except Exception as ex:
        if not fallback_csv:
            return {"ok": False, "error": str(ex)}
        got = events_from_csv(fallback_csv, now_ts if now_ts is not None else time.time())
        if got is None:
            return {"ok": False, "error": f"{ex}; and no MT5 calendar export newer than {CSV_MAX_AGE_DAYS} days"}
        evs, src = got[0], f"mt5_csv({Path(got[1]).name}, {got[2]:.1f} d old)"
    with open(path, "w") as f:
        json.dump({"fetched": time.time(), "events": evs, "source": src}, f)
    return {"ok": True, "events": len(evs), "source": src}


def gate(path, now_ts, before_min, after_min, max_age_h):
    """dict(blocked, reason, resume_s, next_block_s). Fails closed on missing/stale calendar."""
    try:
        with open(path) as f:
            d = json.load(f)
    except Exception:
        return {"blocked": True, "reason": "no_calendar", "resume_s": None, "next_block_s": None}
    if now_ts - d["fetched"] > max_age_h * 3600:
        return {"blocked": True, "reason": "calendar_stale", "resume_s": None, "next_block_s": None}
    for e in d["events"]:
        if e["ts"] - before_min * 60 <= now_ts <= e["ts"] + after_min * 60:
            return {"blocked": True, "reason": f"news:{e['title']}",
                    "resume_s": int(e["ts"] + after_min * 60 - now_ts) + 15, "next_block_s": None}
    upcoming = [e for e in d["events"] if e["ts"] - before_min * 60 > now_ts]
    nxt = int(upcoming[0]["ts"] - before_min * 60 - now_ts) if upcoming else None
    return {"blocked": False, "reason": "", "resume_s": None, "next_block_s": nxt}


def next_event(path, now_ts, horizon_min=60):
    """Nearest high-impact event within horizon_min ahead (or up to 2 min past): {title, in_s} or None."""
    try:
        with open(path) as f:
            d = json.load(f)
    except Exception:
        return None
    for e in d.get("events", []):
        dt = e["ts"] - now_ts
        if -120 <= dt <= horizon_min * 60:
            return {"title": e["title"], "in_s": int(dt)}
    return None
