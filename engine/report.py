"""Script-written end-of-run report (Claude reads only the one-line pointer)."""
from collections import Counter
from datetime import datetime, timezone

from . import journal as jr


def _after(rec, start_ts):
    try:
        t = datetime.fromisoformat(rec["ts"].rstrip("Z")).replace(tzinfo=timezone.utc).timestamp()
    except Exception:
        return False
    return t >= start_ts - 1


def build(run, recs, risk_pct, warns):
    mine = [r for r in recs if _after(r, run["start_ts"])]
    exits = [r for r in mine if r.get("type") == "exit"]
    st = jr.stats(exits, risk_pct)
    kinds = Counter(r.get("type") for r in mine)
    passes = [r.get("reason", "") for r in mine if r.get("type") == "pass"]
    lines = [f"# Run {run['id']} report", "",
             f"- stop: `{run.get('stop_reason') or 'cap/loop'}` · trades: {run.get('trades', 0)} · "
             f"streak: {run.get('consec_losses', 0)}",
             f"- records: " + ", ".join(f"{k}={v}" for k, v in sorted(kinds.items())),
             f"- stats: {st}"]
    gc = run.get("gate_counts") or {}
    if gc:
        lines.append("- gates hit (ticks): " + ", ".join(f"{k}={v}" for k, v in sorted(gc.items(), key=lambda kv: -kv[1])))
    if passes:
        lines.append("- passes: " + "; ".join(passes[:10]))
    if exits:
        lines += ["", "## Exits"] + [f"- #{e.get('ticket')} {e.get('side')} {e.get('pattern')} "
                                      f"R={e.get('outcome_r')} {e.get('exit_reason')} mfe={e.get('mfe_r')} "
                                      f"mae={e.get('mae_r')}" for e in exits]
    lines += ["", "## Health"] + ([f"- {w}" for w in warns] or ["- ok"])
    return "\n".join(lines) + "\n"
