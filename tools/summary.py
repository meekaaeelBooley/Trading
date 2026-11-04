r"""One-screen results for the experiment instances (and the default one): per-symbol and combined stats.

  .venv\Scripts\python.exe tools\summary.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine import journal as jr, review as rv  # noqa: E402

DIRS = ["state-xau", "state-ustec"]


def main():
    allx = []
    for d in DIRS:
        recs = jr.read(ROOT / d / "journal.jsonl")
        ex = [r for r in recs if r.get("type") == "exit" and r.get("outcome_r") is not None]
        if not recs:
            continue
        allx += ex
        errs = sum(1 for r in recs if r.get("type") == "error")
        print(f"{d:18s} {jr.stats(ex, 5.0)}  errors={errs}")
        by = rv.analyze(ex).get("by", {}).get("pattern", {})
        if by:
            print(f"{'':18s} by pattern: {by}")
    if allx:
        rs = [r["outcome_r"] for r in allx]
        print(f"{'COMBINED':18s} n={len(rs)} E={sum(rs)/len(rs):+.3f}R ci95={rv.ci(rs)} gate: {jr.graduation(jr.stats(allx, 5.0))}")


if __name__ == "__main__":
    main()
