import numpy as np


def ema(x, n):
    x = np.asarray(x, float)
    a = 2.0 / (n + 1)
    out = np.empty_like(x)
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out


def atr(h, l, c, n=14):
    """Wilder ATR, last value."""
    h, l, c = (np.asarray(v, float) for v in (h, l, c))
    tr = np.maximum(h[1:] - l[1:], np.maximum(abs(h[1:] - c[:-1]), abs(l[1:] - c[:-1])))
    if len(tr) < n:
        return float("nan")
    a = tr[:n].mean()
    for v in tr[n:]:
        a = (a * (n - 1) + v) / n
    return float(a)


def trend(closes, min_bars=250):
    """'long' if EMA50 > EMA200, 'short' if below, else 'flat'."""
    if len(closes) < min_bars:
        return "flat"
    e50, e200 = ema(closes, 50)[-1], ema(closes, 200)[-1]
    return "long" if e50 > e200 else "short" if e50 < e200 else "flat"


def bias(closes_h1, closes_h4):
    a, b = trend(closes_h1), trend(closes_h4)
    return a if a == b else "flat"
