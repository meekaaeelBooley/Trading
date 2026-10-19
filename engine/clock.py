from datetime import timedelta, timezone

SAST = timezone(timedelta(hours=2))


def _m(s):
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def phase(now, cfg, elapsed_s):
    """Phase for a run that started `elapsed_s` seconds ago (hard cap run_max_minutes).

    FLATTEN: run cap reached (stop). BREAK: exchange break (cfg break, SAST, must end at 00:00).
    MANAGE: open positions are managed but no new entries (around the break, last minutes of the run).
    ACTIVE: entries allowed.
    Returns dict(phase, entry_ok, stop_loop, next_boundary_s, run_left_s, mins).
    """
    t = now.astimezone(SAST)
    m = t.hour * 60 + t.minute + t.second / 60
    left = cfg["run_max_minutes"] * 60 - elapsed_s
    bs = _m(cfg["break"][0])
    pre, post, wind = cfg["no_entry_before_break_min"], cfg["no_entry_after_reopen_min"], cfg["no_entry_last_min"]
    stop = False
    if left <= 0:
        ph, stop = "FLATTEN", True
    elif bs <= m < 1440:
        ph = "BREAK"
    elif left < wind * 60 or bs - pre <= m < bs or m < post:
        ph = "MANAGE"
    else:
        ph = "ACTIVE"
    bounds = sorted({0, post, bs - pre, bs - 5, bs, 1440})
    nxt = next((b for b in bounds if b > m), bounds[0] + 1440)
    return {"phase": ph, "entry_ok": ph == "ACTIVE", "stop_loop": stop,
            "next_boundary_s": int(max(0, min((nxt - m) * 60, left))), "run_left_s": int(max(left, 0)), "mins": m}


def next_bar_close_s(now, minutes=15, grace=20):
    """Seconds until the next bar close (+grace)."""
    step = minutes * 60
    return step - ((now.minute * 60 + now.second) % step) + grace
