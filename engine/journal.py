import json
import time


def append(path, rec):
    rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + "Z", **rec}
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


def read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return [json.loads(x) for x in f if x.strip()]
    except FileNotFoundError:
        return []


def stats(recs, risk_pct):
    ex = [r for r in recs if r.get("type") == "exit" and r.get("outcome_r") is not None]
    if not ex:
        return {"n": 0}
    rs = [r["outcome_r"] for r in ex]
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r <= 0]
    eq, peak, dd = 1.0, 1.0, 0.0
    for r, rec in zip(rs, ex):
        eq *= 1 + r * (rec.get("risk_pct") or risk_pct) / 100  # each exit carries the risk % it was sized with
        peak = max(peak, eq)
        dd = max(dd, 1 - eq / peak)
    return {"n": len(rs), "win_rate": round(len(wins) / len(rs), 2), "expectancy_r": round(sum(rs) / len(rs), 3),
            "profit_factor": round(sum(wins) / abs(sum(losses)), 2) if losses and sum(losses) != 0 else None,
            "max_dd_pct": round(dd * 100, 1), "net_r": round(sum(rs), 2)}


def graduation(st, n_min=100, pf_min=1.2, dd_max=20.0):
    ok = (st.get("n", 0) >= n_min and st.get("expectancy_r", 0) > 0 and (st.get("profit_factor") or 0) > pf_min
          and st.get("max_dd_pct", 100) < dd_max)
    return {"eligible": ok, "n_needed": max(0, n_min - st.get("n", 0))}
