"""Pure exit classification and excursion maths (shared by the live server and the backtester)."""


def exit_reason(kind, r, closed_by=None, loss_r=0.25):
    """kind: 'tp' | 'sl' | 'other' (deal reason). closed_by: bot-initiated close tag ('pre_event', ...)."""
    if kind == "tp":
        return "tp"
    if kind == "sl":
        return "sl" if r is None or r <= -loss_r else "be" if r < loss_r else "trail"
    return closed_by or "flat"  # closed by the bot itself (run cap, KILL, daily stop, mismatch, pre-event)


def excursions(bars, side, entry, r_dist, t0, t1):
    """(MFE_R, MAE_R) from bars (dicts/records with time/high/low) between entry and exit; (None, None) if none."""
    sel = [b for b in bars if t0 - 60 <= b["time"] <= t1]
    if not sel or not r_dist:
        return None, None
    hi, lo = max(b["high"] for b in sel), min(b["low"] for b in sel)
    fav, adv = (hi - entry, entry - lo) if side == "buy" else (entry - lo, hi - entry)
    return round(max(fav, 0) / r_dist, 2), round(max(adv, 0) / r_dist, 2)
