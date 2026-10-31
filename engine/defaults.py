"""Defaults for features added after config.json was written. config.json (user-owned) overrides any key."""
DEFAULTS = {"partial_tp": True, "partial_at_r": 1.0, "partial_frac": 0.5,
            "pre_event_exit": True, "pre_event_exit_min": 5, "headline_check_min": 30,
            # signal timeframe in minutes (5|15) and the ordered list of entry strategies (pullback|orb)
            "tf_min": 15, "strategies": ["pullback"],
            # opening-range breakout from the US cash open (09:30 New York): range bars, entry window, bias filter
            "orb_bars": 6, "orb_window_min": 120, "orb_require_bias": True,
            # optional bucket edges for the learning review (instrument-specific ATR / spread scales)
            "atr_bands": None, "spread_bands": None,
            # AI-originated trades: stop-distance floor (x ATR)
            "min_sl_atr": 0.5, "max_spread_r": None,
            # desk mode (multi-agent scalping): a sentinel agent owns headline checks and a coach owns reviews, so the
            # tick no longer asks the trader agent to web-search or review; the scout decides which bars wake it
            "desk_mode": False, "scout_impulse_atr": 1.4, "scout_break_bars": 20,
            # account-wide cap across every bot magic in desk_magics (None = off); a hard gate, not overridable
            "desk_magics": [], "desk_max_positions": None,
            # swing book (config.json may override any key). Swing positions are tagged style=swing, sized from their own
            # risk_pct, survive the scalp run cap, and are managed in H1 units. Stops are in x ATR(H1). On a small account the
            # minimum lot can exceed swing_risk_pct for an H1-scale stop: it is accepted up to swing_min_lot_risk_mult x that.
            "swing_enabled": True, "swing_risk_pct": 1.5, "swing_min_lot_risk_mult": 2.5, "swing_max_positions": 2, "swing_max_per_day": 3,
            "swing_min_rr": 2.0, "swing_min_sl_atr": 0.7, "swing_max_sl_atr": 3.0, "swing_min_score": 7.0,
            "swing_pivot_k": 3, "swing_be_r": 1.0, "swing_trail_r": 2.0, "swing_partial_at_r": 1.5, "swing_partial_frac": 0.5,
            "swing_max_hold_h": 96, "swing_weekend_flat": True, "swing_friday_flat": "21:30",
            "swing_no_entry_friday_after": "18:00", "swing_alert_min_score": 8.0}
