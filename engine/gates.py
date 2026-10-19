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
    if c["spread"] > c["spread_max"]:
        b.append("spread:%.0f" % c["spread"])
    if not (c["atr_min"] <= c["atr"] <= c["atr_max"]):
        b.append("atr:%.1f" % c["atr"])
    return b
