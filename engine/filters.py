"""Deterministic entry filters mined from the journal (state/filters.json, written by tools/mine.py).

A rule is a dict of feature=value pairs; a signal is blocked when it matches every pair of any rule.
Features: side, pattern, bias, hour (SAST), atr_band, spread_band, regime.
"""
import json

from .review import ATR_BANDS, SPREAD_BANDS, band


def features(side, pattern, bias, atr, spread, hour, regime=None):
    return {"side": side, "pattern": pattern, "bias": bias, "hour": hour,
            "atr_band": band(atr, ATR_BANDS), "spread_band": band(spread, SPREAD_BANDS), "regime": regime}


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            rules = json.load(f)
    except Exception:
        return []
    return [r for r in rules if isinstance(r, dict) and isinstance(r.get("rule"), dict) and r["rule"]]


def match(rules, feats):
    """Description of the first matching rule, or None."""
    for r in rules:
        if all(feats.get(k) == v for k, v in r["rule"].items()):
            return ",".join(f"{k}={v}" for k, v in r["rule"].items())
    return None
