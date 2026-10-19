r"""Mine the live journal for robust losing buckets and (optionally) install them as entry filters.

  .venv\Scripts\python.exe tools\mine.py            # show candidates
  .venv\Scripts\python.exe tools\mine.py --apply    # write state/filters.json (the server then skips matching signals)
  .venv\Scripts\python.exe tools\mine.py --clear    # remove all filters

Candidates need n>=30, mean R <= -0.3, 95% bootstrap CI below zero and both chronological halves negative.
Run it yourself: filters change which setups get traded.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine import journal as jr, review as rv  # noqa: E402

STATE = ROOT / "state"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--clear", action="store_true")
    ap.add_argument("--min-n", type=int, default=30)
    a = ap.parse_args()
    f = STATE / "filters.json"
    if a.clear:
        f.unlink(missing_ok=True)
        print("filters cleared")
        return
    ex = [r for r in jr.read(str(STATE / "journal.jsonl")) if r.get("type") == "exit"]
    cand = rv.candidate_filters(ex, a.min_n)
    print(f"{len(ex)} exits, {len(cand)} candidate filter(s)")
    for c in cand:
        print(" ", c)
    if a.apply:
        STATE.mkdir(exist_ok=True)
        f.write_text(json.dumps(cand, indent=1), encoding="utf-8")
        print("written", f)


if __name__ == "__main__":
    main()
