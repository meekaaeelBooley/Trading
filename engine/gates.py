def blockers(c):
    """List of reasons new entries are blocked. c is a plain dict of facts."""
    b = []
    if not c["entry_ok"]:
        b.append("phase:" + c["phase"])
    if c["kill"]:
        b.append("KILL")
    if c["halt"]:
        b.append("HALT")
    if c["stopped"]:
        b.append("stopped:" + str(c["stop_reason"]))
    if not c["demo_ok"]:
        b.append("not_demo")
    if not c["market_open"]:
        b.append("market_closed")
    if not c["data_fresh"]:
        b.append("stale_bars")
    if c["open_positions"] >= c["max_positions"]:
        b.append("position_open")
    if c.get("desk_max") and c.get("desk_open", 0) >= c["desk_max"]:  # account-wide cap across both instruments
        b.append("desk_exposure")
    if c["trades"] >= c["max_trades"]:
        b.append("max_trades")
    if c["consec_losses"] >= c["max_consec"]:
        b.append("consec_losses")
    if c["day_pct"] <= -c["daily_stop"]:
        b.append("daily_stop")
    if c["news_blocked"]:
        b.append(c["news_reason"])
    if c.get("risk_flag"):  # Claude's veto-only headline flag (can only block new entries)
        b.append("risk_flag:" + str(c["risk_flag"])[:40])
    if c["spread_max"] and c["spread"] > c["spread_max"]:  # None/0 = no spread limit
        b.append("spread:%.0f" % c["spread"])
    if not (c["atr_min"] <= c["atr"] <= c["atr_max"]):
        b.append("atr:%.1f" % c["atr"])
    return b


OVERRIDABLE = ("atr", "spread", "news", "risk_flag", "consec_losses", "position_open", "max_trades")


def apply_overrides(ctx, names, pos_extra=2):
    """Copy of the gate context with the named SOFT gates neutralised (AI discretion). Never touches demo, KILL/HALT,
    daily stop, market-closed, stale data or phase. position_open / max_trades only stretch by a bounded margin."""
    c = dict(ctx)
    for n in names:
        if n == "atr":
            c["atr"] = c["atr_min"]
        elif n == "spread":
            c["spread"] = 0
        elif n == "news":
            c["news_blocked"] = False
        elif n == "risk_flag":
            c["risk_flag"] = ""
        elif n == "consec_losses":
            c["consec_losses"] = 0
        elif n == "position_open" and c["open_positions"] < c["max_positions"] + pos_extra:
            c["open_positions"] = 0
        elif n == "max_trades" and c["trades"] < 2 * c["max_trades"]:
            c["trades"] = 0
    return c
