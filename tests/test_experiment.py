from datetime import datetime, timezone

import numpy as np

from engine import review as rv, signal as sg

CFG = {"orb_bars": 6, "orb_window_min": 120, "orb_require_bias": True, "max_sl_atr": 3.0, "tp_r": 2.0,
       "sl_atr_mult": 1.5, "strategies": ["pullback", "orb"]}


def ts(y, mo, d, h, mi):
    return datetime(y, mo, d, h, mi, tzinfo=timezone.utc).timestamp()


def test_us_open_follows_dst():
    assert sg.us_open_ts(ts(2026, 10, 22, 15, 0)) == ts(2026, 10, 22, 13, 30)  # EDT
    assert sg.us_open_ts(ts(2026, 11, 3, 15, 0)) == ts(2026, 11, 3, 14, 30)  # EST
    assert sg.us_open_ts(ts(2026, 3, 9, 15, 0)) == ts(2026, 3, 9, 13, 30)  # after 2nd Sunday of March


def _bars(break_at, direction=1):
    """100 flat M5 bars ending inside the opening window; range = first 6 bars from 13:30, break at index break_at."""
    open_ts = ts(2026, 10, 22, 13, 30)
    n = 70
    t = open_ts - 5 * 60 * 60 * 0 + 300 * (np.arange(n) - 30)  # 30 bars before the open
    c = np.full(n, 100.0)
    h, l, o = c + 0.5, c - 0.5, c.copy()
    for k in range(n):
        if k > 30 + 6 and k >= break_at:
            c[k] = 100.0 + direction * 1.0
            h[k], l[k] = c[k] + 0.2, c[k] - 0.2
    return t, o, h, l, c


def test_orb_fires_only_on_first_breakout_bar_with_bias():
    t, o, h, l, c = _bars(45)
    cut = lambda i: [x[:i + 1] for x in (t, o, h, l, c)]
    sig, why = sg.find_orb(*cut(45), "long", CFG)
    assert sig and sig["side"] == "buy" and sig["pattern"] == "orb" and sig["sl"] < sig["entry_ref"] < sig["tp"]
    assert sg.find_orb(*cut(46), "long", CFG)[0] is None  # breakout already happened one bar ago
    assert sg.find_orb(*cut(45), "short", CFG)[1] == "orb_against_bias"
    assert sg.find_orb(*cut(40), "long", CFG)[1] == "orb_no_fresh_break"


def test_orb_outside_window():
    t, o, h, l, c = _bars(45)
    t = t + 2 * 3600
    assert sg.find_orb(t, o, h, l, c, "long", CFG)[1] == "orb_outside_window"


def test_configure_bands_relabels_buckets():
    old_a, old_s = list(rv.ATR_BANDS), list(rv.SPREAD_BANDS)
    try:
        rv.configure_bands({"atr_bands": [3, 6], "spread_bands": [300, 450]})
        assert rv.band(2, rv.ATR_BANDS) == "atr<3" and rv.band(4, rv.ATR_BANDS) == "atr3-6"
        assert rv.band(9, rv.ATR_BANDS) == "atr>6" and rv.band(500, rv.SPREAD_BANDS) == "spr>450"
    finally:
        rv.ATR_BANDS[:], rv.SPREAD_BANDS[:] = old_a, old_s


def _rec(n, t0, base=100.0, step=0.01):
    t = t0 + 300 * np.arange(n)
    c = base + step * np.arange(n)
    return {"time": t, "open": c - 0.02, "high": c + 0.3, "low": c - 0.3, "close": c, "tick_volume": np.full(n, 50)}


def test_market_brief_is_compact_and_has_levels():
    from engine import brief
    now = ts(2026, 10, 22, 16, 0)
    m5 = _rec(400, now - 400 * 300)
    m5 = {k: v[:-1] for k, v in m5.items()}
    m15 = _rec(300, now - 300 * 900)
    m15["time"] = now - 900 * (300 - np.arange(300))
    h1 = _rec(320, now - 320 * 3600)
    h1["time"] = now - 3600 * (320 - np.arange(320))
    h4 = _rec(320, now - 320 * 14400)
    out = brief.build(m5, m15, h1, h4, 103.9, 104.0, now, 2)
    assert out["bias"] in ("long", "flat", "short") and len(out["last_m5"]) == 12
    assert "prev_day" in out and "today" in out and out["us_open_range"] != "forming"
    assert 0 <= out["rsi_m5"] <= 100
    assert len(str(out)) < 4000  # token budget
