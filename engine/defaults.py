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
            # evidence-graded playbook (engine/playbook.py): trend_day (USTEC; impulse_cont and news_drift are shelved); the risk tier
            # (moderate|high|extreme) comes from the root TIER flag file, not from config
            "playbook": True}
