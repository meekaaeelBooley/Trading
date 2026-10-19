import math


def lots_for_risk(risk_money, sl_dist, tick_size, tick_value_loss, vol_min, vol_step, vol_max,
                  max_lot, min_lot_risk_mult):
    """Return (lots|None, reason). Never rounds up to min lot beyond min_lot_risk_mult x target."""
    if sl_dist <= 0 or tick_size <= 0 or tick_value_loss <= 0:
        return None, "bad_inputs"
    per_lot = (sl_dist / tick_size) * tick_value_loss
    raw = risk_money / per_lot
    lots = math.floor(raw / vol_step + 1e-9) * vol_step
    if lots < vol_min:
        if vol_min * per_lot > min_lot_risk_mult * risk_money:
            return None, f"min_lot_risk_{vol_min * per_lot:.0f}_exceeds_target_{risk_money:.0f}"
        lots = vol_min
    lots = min(lots, vol_max, max_lot)
    return round(lots, 2), "ok"


def manage_sl(side, entry, price, sl, r_dist, atr, swing_extreme):
    """New SL price or None. BE at +1R; after +1.5R trail behind swing (kept >= 1 ATR from price). Never loosens."""
    sign = 1 if side == "buy" else -1
    profit = (price - entry) * sign
    best = sl
    if profit >= 1.0 * r_dist and (best - entry) * sign < 0:
        best = entry
    if profit >= 1.5 * r_dist:
        trail = swing_extreme - sign * 0.1 * atr
        if (price - trail) * sign >= atr and (trail - best) * sign > 0:
            best = trail
    return best if (best - sl) * sign > 0 else None


def partial_close_lots(lots, frac, vol_min, vol_step):
    """Lots to close at the partial-profit point, or 0.0 when the position is too small to split
    (both the closed part and the remainder must be >= vol_min)."""
    if lots < 2 * vol_min - 1e-9:
        return 0.0
    part = math.floor(lots * frac / vol_step + 1e-9) * vol_step
    part = round(max(part, vol_min), 2)
    return part if lots - part >= vol_min - 1e-9 else 0.0


def partial_due(side, entry, price, r_dist, at_r):
    """True once price is at least at_r x R in profit."""
    sign = 1 if side == "buy" else -1
    return r_dist > 0 and (price - entry) * sign >= at_r * r_dist
