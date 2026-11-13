"""MT5 calendar export: family mapping, CSV fallback for the live news gate, loader dedupe."""
import os
import sys
import time
from pathlib import Path

import pytest

from engine import news

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import usdcal  # noqa: E402

HDR = "ts_server,period_ts,event_id,event_code,name,importance,sector,frequency,actual,forecast,prev,revised_prev,impact\n"


def write_csv(path, rows, age_days=0.0):
    with open(path, "w", encoding="cp1252", newline="") as f:
        f.write(HDR)
        for ts, name, imp in rows:
            f.write(f"{int(ts)},0,1,code,{name},{imp},0,0,1.0,,0.5,,0\n")
    t = time.time() - age_days * 86400
    os.utime(path, (t, t))


def test_families_and_gate_set():
    assert news.family("Nonfarm Payrolls") == "nfp" and news.family("Unemployment Rate") == "nfp"
    assert news.family("Fed Chair Powell Speech") == "powell" and news.family("Baker Hughes US Oil Rig Count") == "other"
    assert "claims" not in news.GATE_FAMILIES and "fomc_presser" in news.GATE_FAMILIES


def test_events_from_csv_filters_window_family_and_dedupes(tmp_path):
    now = time.time()
    p = tmp_path / "c.csv"
    write_csv(p, [(now + 3600, "Nonfarm Payrolls", 3), (now + 3600, "Nonfarm Payrolls", 3), (now + 7200, "Initial Jobless Claims", 3),
                  (now + 9000, "Core CPI m/m", 3), (now - 3 * 86400, "CPI m/m", 3), (now + 40 * 86400, "CPI m/m", 3)])
    evs, src, age = news.events_from_csv([p], now)
    assert [e["title"] for e in evs] == ["Nonfarm Payrolls", "Core CPI m/m"]  # claims not a gate family; out-of-window dropped


def test_stale_or_missing_export_is_not_used(tmp_path):
    p = tmp_path / "c.csv"
    write_csv(p, [(time.time() + 3600, "CPI m/m", 3)], age_days=20)
    assert news.events_from_csv([p, tmp_path / "none.csv"], time.time()) is None


def test_refresh_falls_back_to_csv_only_when_web_fails(tmp_path):
    p, cache = tmp_path / "c.csv", str(tmp_path / "cache.json")
    write_csv(p, [(time.time() + 3600, "Nonfarm Payrolls", 3)], age_days=1)
    down = lambda u: (_ for _ in ()).throw(OSError("down"))  # noqa: E731
    r = news.refresh(cache, "x", fetch=down, fallback_csv=[p])
    assert r["ok"] and r["events"] == 1 and r["source"].startswith("mt5_csv")
    g = news.gate(cache, time.time() + 3600 - 60, 15, 10, 12)
    assert g["blocked"] and g["reason"] == "news:Nonfarm Payrolls"
    assert news.refresh(cache, "x", fetch=lambda u: [], fallback_csv=[p])["source"] == "web"
    assert not news.refresh(str(tmp_path / "c2.json"), "x", fetch=down)["ok"]  # no fallback given -> fail closed (unchanged)
    write_csv(p, [(time.time() + 3600, "Nonfarm Payrolls", 3)], age_days=30)
    assert not news.refresh(str(tmp_path / "c3.json"), "x", fetch=down, fallback_csv=[p])["ok"]


def test_loader_collapses_one_release_into_one_moment(tmp_path):
    p = tmp_path / "u.csv"
    write_csv(p, [(1000, "Nonfarm Payrolls", 3), (1000, "Unemployment Rate", 3), (1000, "Average Hourly Earnings m/m", 3),
                  (2000, "CPI m/m", 3), (2000, "Core CPI m/m", 3), (3000, "EIA Crude Oil Stocks Change", 3)])
    ev = usdcal.moments(usdcal.TIER1, path=p)
    assert [(e["ts"], e["family"]) for e in ev] == [(1000, "nfp"), (2000, "cpi")]


@pytest.mark.skipif(not usdcal.DST.exists(), reason="data/usd_events.csv not synced")
def test_real_export_nfp_is_0830_new_york_in_both_dst_regimes():
    from engine import sessions as ss
    import numpy as np
    nfp = [e for e in usdcal.moments(("nfp",)) if 1_420_000_000 < e["ts"] < 1_780_000_000]
    mins = ss.local_minute(np.array([e["ts"] for e in nfp], np.int64), "ny")
    assert (mins == 510).mean() > 0.95, "calendar times are not UTC / DST-aligned"
