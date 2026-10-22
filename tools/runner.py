r"""Headless runner: the same session_tick / place_trade_checked logic, no LLM.

  .venv\Scripts\python.exe tools\runner.py [--dry-run]

Rule-only: every signal that clears the gates (and state/filters.json) is taken; there is no headline search,
so run-start / headline / review prompts are ignored. Same 2h cap, break handling, KILL/HALT and demo gate.
Ctrl+C stops the loop; any open position keeps its broker-side SL/TP but is no longer managed.

Experiment instances: set TRADING_CONFIG (e.g. config.exp-xau.json) and TRADING_STATE (e.g. state-exp-xau) before
starting; see tools/run_experiment.ps1. The learning loop runs here without an LLM: every REVIEW_EVERY new closed
trades the runner calls review(), writes reports/learn-<instance>.md and rewrites the lessons file from buckets
with enough support (n>=20); at >=30 trades deep_review() adds candidate filters (never auto-applied).
"""
import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def learn(s, state_tag):
    """Headless learning step: review -> report + evidence-gated lessons. Returns the number of exits reviewed."""
    r = s.review()
    an = r.get("analysis", {})
    lines = [f"# Learning report ({state_tag}) {time.strftime('%Y-%m-%d %H:%M')}", "",
             f"- stats: {r['stats']}", f"- graduation: {r['graduation']}", f"- exit mix: {an.get('exit_mix')}",
             f"- diag: {an.get('diag')}", "", "## Flags"] + [f"- {f}" for f in an.get("flags", [])] + ["", "## By feature"]
    lessons = []
    for dim, buckets in (an.get("by") or {}).items():
        for k, b in buckets.items():
            lines.append(f"- {dim}={k}: n={b['n']} E={b['exp']:+.2f}R win={b['win']:.0%}")
            if b["n"] >= 20 and abs(b["exp"]) >= 0.3:
                lessons.append(f"[n={b['n']}, E={b['exp']:+.2f}R] {dim}={k} " +
                               ("underperforms: prefer passing" if b["exp"] < 0 else "outperforms: keep"))
    if r["stats"].get("n", 0) >= 30:
        d = s.deep_review()
        lines += ["", "## Candidate filters (user applies with tools/mine.py --apply)", f"{d.get('candidate_filters')}"]
    if lessons:
        s.set_lessons(lessons[:25])
    out = Path(ROOT / "reports")
    out.mkdir(exist_ok=True)
    (out / f"learn-{state_tag}.md").write_text("
".join(lines) + "
", encoding="utf-8")
    return r["stats"].get("n", 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if a.dry_run:
        os.environ["DRY_RUN"] = "1"
    import mt5_server as s  # after DRY_RUN is set; the module reads it at import

    errors = 0
    reviewed = 0
    while True:
        try:
            t = s.session_tick()
            errors = 0
        except Exception as e:
            errors += 1
            print("tick error:", e)
            if errors >= 3:
                print("3 consecutive errors: stopping")
                return
            time.sleep(60)
            continue
        print({k: t.get(k) for k in ("t", "phase", "eq", "trades", "gates", "no_signal", "signal", "filtered",
                                       "closed", "health", "report")})
        if t.get("closed") or t.get("stop_loop"):
            try:
                n = len([x for x in s.jr.read(s.JOURNAL_F) if x.get("type") == "exit"])
                if n - reviewed >= s.REVIEW_EVERY or (t.get("stop_loop") and n > reviewed):
                    reviewed = learn(s, s.TAG)
            except Exception as e:  # learning must never stop trading
                print("learn error:", e)
        sig = t.get("signal")
        if sig and not t.get("stop_loop"):
            print("trade:", s.place_trade_checked(sig["side"], sig["id"]))
        if t.get("stop_loop"):
            print("stop:", t.get("why_stop"))
            return
        time.sleep(max(60, t.get("next_wake_seconds") or 60))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("interrupted: open positions are no longer managed (use flatten_all or state/KILL)")
