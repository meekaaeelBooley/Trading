import json
import time
import urllib.request
from datetime import datetime


def fetch_events(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = json.load(r)
    evs = [{"title": e["title"], "ts": datetime.fromisoformat(e["date"]).timestamp()}
           for e in raw if e.get("country") == "USD" and e.get("impact") == "High"]
    return sorted(evs, key=lambda x: x["ts"])


def refresh(path, url, fetch=fetch_events):
    try:
        evs = fetch(url)
    except Exception as ex:  # fail closed: old cache is left to go stale
        return {"ok": False, "error": str(ex)}
    with open(path, "w") as f:
        json.dump({"fetched": time.time(), "events": evs}, f)
    return {"ok": True, "events": len(evs)}


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
