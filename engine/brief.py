"""Compact multi-timeframe market brief for the AI decision step (pure numpy; the server fetches the bars).

All numbers are precomputed so Claude never reads raw candles: trend, levels, VWAP, opening range, momentum and the
last few M5 candles. Distances are in ATR units where that makes them comparable across instruments.
"""
import numpy as np

from . import indicators as ind, levels, signal as sg, smc, swing as sw


def rsi(c, n=14):
    c = np.asarray(c, float)
    if len(c) <= n:
        return None
    d = np.diff(c)
    up, dn = np.maximum(d, 0), np.maximum(-d, 0)
    au, ad = up[:n].mean(), dn[:n].mean()
    for u, w in zip(up[n:], dn[n:]):
        au, ad = (au * (n - 1) + u) / n, (ad * (n - 1) + w) / n
    return round(float(100.0 if ad == 0 else 100 - 100 / (1 + au / ad)), 1)


def build(m5, m15, h1, h4, bid, ask, now_ts, digits=2, m1=None):
    """m5/m15/h1/h4: closed-bar structured arrays (time/open/high/low/close/tick_volume). Returns a small dict."""
    r = lambda x: None if x is None else round(float(x), digits)
    c5, h5, l5 = (np.asarray(m5[k], float) for k in ("close", "high", "low"))
    a5 = ind.atr(h5, l5, c5, 14)
    a15 = ind.atr(m15["high"], m15["low"], m15["close"], 14)
    mid = (bid + ask) / 2
    day0 = now_ts // 86400 * 86400
    today = np.asarray(m5["time"]) >= day0
    out = {"price": r(mid), "spread": r(ask - bid), "atr_m5": r(a5), "atr_m15": r(a15),
           "bias_h1": ind.trend(h1["close"]), "bias_h4": ind.trend(h4["close"]), "bias": ind.bias(h1["close"], h4["close"])}
    for name, bars, ns in (("m5", m5, (20, 50)), ("m15", m15, (20, 50)), ("h1", h1, (20, 50))):
        c = np.asarray(bars["close"], float)
        a = ind.atr(bars["high"], bars["low"], c, 14)
        e = {n: ind.ema(c, n)[-1] for n in ns}
        out[f"{name}_vs_ema"] = {f"ema{n}": round(float((mid - e[n]) / a), 2) for n in ns}  # price - EMA, in that TF's ATR
        out[f"{name}_ema20_over_50"] = bool(e[20] > e[50])
    out["rsi_m5"], out["rsi_m15"] = rsi(c5), rsi(m15["close"])
    out["mom_m5_atr"] = {k: round(float((c5[-1] - c5[-1 - k]) / a5), 2) for k in (3, 12, 36) if len(c5) > k + 1}
    # levels: previous UTC day from H1, today's range/VWAP from M5, opening range from the US cash open
    ht = np.asarray(h1["time"])
    prev = (ht >= day0 - 86400) & (ht < day0)
    if prev.any():
        out["prev_day"] = {"high": r(np.max(h1["high"][prev])), "low": r(np.min(h1["low"][prev])),
                           "close": r(h1["close"][prev][-1])}
    if today.any():
        th, tl = h5[today], l5[today]
        tp = (th + tl + c5[today]) / 3
        v = np.asarray(m5["tick_volume"], float)[today] + 1
        vw = float(np.sum(tp * v) / np.sum(v))
        out["today"] = {"high": r(th.max()), "low": r(tl.min()), "vwap": r(vw), "vwap_dev_atr": round((mid - vw) / a5, 2)}
    open_ts = sg.us_open_ts(now_ts)
    orb = (np.asarray(m5["time"]) >= open_ts)
    if now_ts >= open_ts + 6 * 300 and orb.sum() >= 6:
        idx = np.where(orb)[0][:6]
        out["us_open_range"] = {"high": r(h5[idx].max()), "low": r(l5[idx].min())}
    elif now_ts >= open_ts:
        out["us_open_range"] = "forming"
    out["last_m5"] = [[int(t) % 86400 // 3600 * 100 + int(t) % 3600 // 60, r(o), r(h), r(l), r(c)]
                      for t, o, h, l, c in zip(m5["time"][-12:], m5["open"][-12:], m5["high"][-12:],
                                               m5["low"][-12:], m5["close"][-12:])]  # [HHMM utc, o, h, l, c]
    try:  # support/resistance and smart-money read for scalps (zones in M5-ATR units; the swing_brief carries the full read)
        frames = [(n, b["high"], b["low"], ind.atr(b["high"], b["low"], b["close"], 14))
                  for n, b in (("m5", m5), ("m15", m15), ("h1", h1), ("h4", h4))]
        out["sr"] = {**sw.compact_zones(levels.build(frames, mid, a5, 12), digits), "round": levels.round_levels(mid, 1)}
        out["smc_m5"], out["smc_m15"] = (smc.compact(smc.analyze(b), mid, digits) for b in (m5, m15))
    except Exception as e:  # the extra read must never break the base brief
        out["sr_error"] = str(e)[:60]
    if m1 is not None and len(m1["close"]) > 30:  # scalp view: M1 volatility, cost in ATR, tape of the last 15 minutes
        c1 = np.asarray(m1["close"], float)
        a1 = ind.atr(m1["high"], m1["low"], c1, 14)
        out["atr_m1"], out["spread_atr_m1"] = r(a1), round(float((ask - bid) / a1), 2)
        out["rsi_m1"] = rsi(c1)
        out["mom_m1_atr"] = {k: round(float((c1[-1] - c1[-1 - k]) / a1), 2) for k in (3, 10, 30)}
        out["last_m1"] = [[int(t) % 86400 // 3600 * 100 + int(t) % 3600 // 60, r(o), r(h), r(l), r(c)]
                          for t, o, h, l, c in zip(m1["time"][-15:], m1["open"][-15:], m1["high"][-15:],
                                                   m1["low"][-15:], m1["close"][-15:])]
    return out
