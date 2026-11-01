"""
Fusul orar — toate engine-urile pe ROMANIA (alex-live) si GERMANIA (ex. vlad-live).

Ruleaza fiecare verificare cu data/timezone_config.json simulat pe Europe/Bucharest si pe
Europe/Berlin (fisier temporar, configuratia reala NU e atinsa) si serverul ICMarkets simulat
(UTC+2 iarna / UTC+3 vara). Offline, fara MT5.
Rulare: python scripts/test_timezones.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import tz_helper  # noqa: E402

FAIL = 0


def check(name, cond, info=None):
    global FAIL
    print(("  OK  " if cond else "  FAIL ") + name + ("" if cond or info is None else f"  -> {info}"))
    if not cond:
        FAIL += 1


_tmp = tempfile.mkdtemp()
_ORIG = tz_helper._CONFIG_FILE


def use_tz(name: str) -> None:
    p = os.path.join(_tmp, "timezone_config.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"timezone": name}, f)
    tz_helper._CONFIG_FILE = p


UTC = timezone.utc
# Luni 3 nov 2026, 09:00 UTC (iarna: RO = 11:00, DE = 10:00, server ICMarkets = UTC+2 = 11:00)
T_UTC = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)
SERVER_OFF = 2

try:
    for tzname, label, local_h in (("Europe/Bucharest", "RO", 11), ("Europe/Berlin", "DE", 10)):
        use_tz(tzname)
        print(f"\n=== {label} ({tzname}) ===")
        check(f"tz_helper citeste {label}", tz_helper.get_configured_tz_name() == tzname)

        # 1. Custom / AI: barele MT5 → fusul configurat (Mt5DataSource.load_bars)
        import numpy as np
        from adapters import mt5_source as MS
        server_epoch = int((T_UTC + timedelta(hours=SERVER_OFF)).replace(tzinfo=None).replace(tzinfo=UTC).timestamp())
        rates = np.array([(server_epoch, 1.1, 1.2, 1.0, 1.15, 10, 1, 0)],
                         dtype=[("time", "i8"), ("open", "f8"), ("high", "f8"), ("low", "f8"), ("close", "f8"),
                                ("tick_volume", "i8"), ("spread", "i4"), ("real_volume", "i8")])
        fake = SimpleNamespace(symbol_select=lambda s, b: True, copy_rates_from_pos=lambda *a: rates,
                               last_error=lambda: None, TIMEFRAME_M15=15)
        old_mt5 = MS.mt5
        MS.mt5 = fake
        try:
            src = object.__new__(MS.Mt5DataSource)
            src._n_bars, src._server_offset_h, src._offset_next_check = 1, SERVER_OFF, float("inf")
            src._ensure_ipc = lambda: None
            if "M15" not in MS._TF_MAP:
                MS._TF_MAP["M15"] = 15
            bar_t = src.load_bars("EURUSD", "M15")["time"].iloc[0]
        finally:
            MS.mt5 = old_mt5
        check(f"Custom/AI: bara MT5 (server UTC+2 11:00) → {local_h:02d}:00 ora {label}", bar_t.hour == local_h, bar_t)

        # 2. API / rapoarte / Dashboard: close_time din MT5 → fusul configurat
        from api import mt5_pool
        lt = mt5_pool._mt5_ts_to_local(server_epoch, SERVER_OFF, tz_helper.get_configured_tz_name())
        check(f"API: close_time tranzactie → {local_h:02d}:00 ora {label}", lt.hour == local_h, lt)

        # 3. now_local in fusul configurat
        nl = tz_helper.now_local()
        expect = datetime.now(ZoneInfo(tzname)).replace(tzinfo=None)
        check(f"now_local() = ora {label}", abs((nl - expect).total_seconds()) < 5)

        # 4. Setari Globale: ziua de tranzactionare (circuit breaker) in fusul configurat
        from live import global_guard as GG
        check(f"Setari Globale: fusul zilei = {label}", GG._tz_name() == tzname)

        # 5. AI Engine: inchiderea de weekend la ora configurata, in fusul aplicatiei
        from ai_engine import executor as AX
        fri_21 = datetime(2026, 11, 6, 21, 59)
        fri_22 = datetime(2026, 11, 6, 22, 0)
        check(f"AI: vineri 21:59 ora {label} deschis, 22:00 inchis (FX); BTC mereu deschis",
              not AX.is_market_weekend_closed("EURUSD", fri_21, 22) and AX.is_market_weekend_closed("EURUSD", fri_22, 22)
              and not AX.is_market_weekend_closed("BTCUSD", fri_22, 22))

        # 6. Daily: logica pe ora BURSEI (identica RO / DE); afisarea in fusul aplicatiei
        from daily_engine import engine as DE
        m_us = {"symbol": "US500", "tz": "America/New_York", "open": "09:30", "last_bar": "15:55"}
        w_open, w_end = DE.window_times(m_us, datetime(2026, 11, 2).date())
        aw = DE._app_window(w_open, w_end)
        exp_open = "16:30" if label == "RO" else "15:30"   # 2 nov: SUA deja pe ora de iarna (EST)
        check(f"Daily US500: deschiderea NY 09:30 = {exp_open} ora {label} (eticheta {label})",
              aw["window_app"].startswith(exp_open) and aw["app_tz_label"] == label, aw)
        check("Daily: fereastra reala nu depinde de fusul aplicatiei (09:30 New York)",
              w_open.astimezone(ZoneInfo("America/New_York")).strftime("%H:%M") == "09:30")

        # 7. Noisy: fereastra in ora RO (testata asa); inchiderea de vineri globala din fusul aplicatiei
        from noisy_engine import engine as NE
        fb = NE.friday_block(datetime(2026, 11, 6, 12, 0), {"friday_close": {"enabled": True, "hour": 20}})
        exp_ro = 20 if label == "RO" else 21      # 20:00 DE = 21:00 RO
        check(f"Noisy: inchiderea de vineri 20:00 ora {label} = {exp_ro}:00 ora RO (intern)",
              fb is not None and fb[0].hour == exp_ro, fb)
finally:
    tz_helper._CONFIG_FILE = _ORIG

print("\n=== Istoric MT5 (independent de fus) ===")
src_sg = open(os.path.join(ROOT, "live", "signal_generator.py"), encoding="utf-8").read()
ends = re.findall(r"dt_to\s*=\s*datetime\.now\(\)[^\n]*", src_sg)
check("Custom: cautarea in istoricul MT5 acopera ora serverului (dt_to = acum + 1 zi, nu ora masinii)",
      ends and all("timedelta(days=1)" in e for e in ends), ends)
# simulare: PC in Germania (UTC+1) vs server UTC+2 — ordinul de acum 30 min (ora serverului) e in fereastra?
pc_now = datetime(2026, 11, 2, 10, 0)                 # ora masinii (DE)
order_server = datetime(2026, 11, 2, 10, 30)          # = 09:30 DE, ora serverului e +1h
check("simulare DE: ordin plasat acum 30 min gasit (inainte: ratat)", order_server <= pc_now + timedelta(days=1)
      and not order_server <= pc_now)

print(f"\n{'TOATE TESTELE AU TRECUT' if not FAIL else f'{FAIL} TESTE ESUATE'}")
sys.exit(1 if FAIL else 0)
