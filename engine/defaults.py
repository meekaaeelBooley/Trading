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
            "min_sl_atr": 0.5}
