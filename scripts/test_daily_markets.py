"""
Teste offline pentru schimbarea pietei unui slot Daily (daily_engine/market_tools.py + API /daily/market-preview,
PUT /daily/config {markets:[{slot,...}]}). MT5 simulat, config intr-un director temporar, fara Telegram.
    python scripts/test_daily_markets.py
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import threading
from datetime import datetime, timedelta
from types import SimpleNamespace

import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import daily_engine.config as C  # noqa: E402

TMP = tempfile.mkdtemp()
C.CFG_PATH = os.path.join(TMP, "config.json")
shutil.copy(os.path.join(ROOT, "daily_engine", "config.json"), C.CFG_PATH)
from daily_engine import market_tools as T  # noqa: E402
from daily_engine.strategy import evaluate_day_multi  # noqa: E402
from api.routers import daily_engine as R  # noqa: E402

FAIL = 0
SENT: list[str] = []
import api.telegram as TG  # noqa: E402
TG.send_message = lambda t: SENT.append(t)


def check(name, cond, info=None):
    global FAIL
    print(("  OK  " if cond else "  FAIL ") + name + ("" if cond or info is None else f"  -> {info}"))
    if not cond:
        FAIL += 1


def rates_for(open_server: datetime, days: int, n: int, pattern, spread_pts=2):
    rows = []
    for d in range(days):
        day0 = open_server + timedelta(days=d)
        if day0.weekday() >= 5:
            continue
        for i in range(n):
            o, h, l, c = pattern(d, i)
            # epoch = ora SERVERULUI tratata ca UTC naiv (asa vine din MT5), nu ora locala a PC-ului
            rows.append((int(((day0 + timedelta(minutes=5 * i)) - datetime(1970, 1, 1)).total_seconds()), o, h, l, c, 10, spread_pts, 0))
    return np.array(rows, dtype=[("time", "i8"), ("open", "f8"), ("high", "f8"), ("low", "f8"), ("close", "f8"),
                                 ("tick_volume", "i8"), ("spread", "i4"), ("real_volume", "i8")])


class FakeMT5:
    TIMEFRAME_M5, ORDER_TYPE_BUY, SYMBOL_TRADE_MODE_FULL = 5, 0, 4
    SYMS = {"DE40": dict(point=0.01, digits=2, bid=24000.0, ask=24000.5, mode=4, vmin=0.1, desc="Germany 40"),
            "GBPUSD": dict(point=0.00001, digits=5, bid=1.30000, ask=1.30010, mode=4, vmin=0.01, desc="GBP/USD"),
            "US500": dict(point=0.01, digits=2, bid=6000.0, ask=6000.5, mode=4, vmin=0.1, desc="US 500"),
            "OLD": dict(point=0.01, digits=2, bid=1.0, ask=1.1, mode=0, vmin=1, desc="close only")}

    def __init__(self):
        self.rates = None

    def symbol_select(self, s, f=True):
        return s in self.SYMS

    def symbol_info(self, s):
        x = self.SYMS.get(s)
        return None if x is None else SimpleNamespace(point=x["point"], digits=x["digits"], trade_mode=x["mode"],
                                                     volume_min=x["vmin"], description=x["desc"])

    def symbol_info_tick(self, s):
        x = self.SYMS.get(s)
        return None if x is None else SimpleNamespace(bid=x["bid"], ask=x["ask"])

    def copy_rates_from_pos(self, s, tf, a, n):
        hist_pts = {"GBPUSD": 1, "DE40": 50, "US500": 50}.get(s, 2)      # spread-ul istoric al barelor (points)
        return np.array([(0, 1, 1, 1, 1, 1, hist_pts, 0)] * 50,
                        dtype=[("time", "i8"), ("open", "f8"), ("high", "f8"), ("low", "f8"), ("close", "f8"),
                               ("tick_volume", "i8"), ("spread", "i4"), ("real_volume", "i8")])

    def copy_rates_range(self, s, tf, a, b):
        return self.rates

    def order_calc_margin(self, t, s, v, p):
        return 144.5 if s == "DE40" else 33.3


print("1. Sabloane de bursa + costuri AUTO")
check("3 burse: Londra 08:00, Frankfurt 09:00, New York 09:30 (varianta testata)",
      [(k, p["open"], p["or_minutes"], p["entry"]) for k, p in T.PRESETS.items()]
      == [("london", "08:00", 5, "breakout"), ("frankfurt", "09:00", 5, "breakout"), ("new_york", "09:30", 30, "direction")])
check("config implicita recunoscuta: GBPUSD = london, US500 = new_york",
      [T.preset_for(m) for m in C.load_config()["markets"]] == ["london", "new_york"])
fm = FakeMT5()
c = T.estimate_costs(fm, "GBPUSD", [1] * 100)
check("FX Standard: spread live 10 points vs 1 in istoric → comision (markup) 9 points, slip 25% din live",
      abs(c["comm"] - 0.00009) < 1e-12 and abs(c["slip"] - 0.000025) < 1e-12 and c["markup_points"] == 9.0, c)
c = T.estimate_costs(fm, "DE40", [50] * 100)
check("indice fara markup (live 50 = istoric 50 points) → comision 0, slip 25% din live", c["comm"] == 0 and abs(c["slip"] - 0.125) < 1e-12, c)
c = T.estimate_costs(fm, "DE40", None)
check("fara istoric → doar spread-ul live (comision 0)", c["comm"] == 0 and c["spread_hist"] is None)
check("simbol necunoscut → ok False, fara exceptie", T.estimate_costs(fm, "NOPE")["ok"] is False)

print("2. Backtest rapid = aceeasi functie ca engine-ul (ora serverului = New York + 7)")
ny0 = datetime(2026, 3, 2, 9, 30)                 # luni, ora NEW YORK → server = +7h
srv0 = ny0 + timedelta(hours=7)
m = {"symbol": "US500", **T.PRESETS["new_york"], "slip": 0.1, "comm": 0.0, "rr": None, "reentry": None}
n = (C.hm_to_min(m["last_bar"]) - C.hm_to_min(m["open"])) // 5 + 1
pat = lambda d, i: (6000 + i * (1 if d % 2 == 0 else -1), 6001.5 + i * (1 if d % 2 == 0 else -1) + 0.5,  # noqa: E731
                    5999.5 + i * (1 if d % 2 == 0 else -1) - 0.5, 6001 + i * (1 if d % 2 == 0 else -1))
rates = rates_for(srv0, 14, n, pat)
bt = T.backtest_rates(rates, m, 0.01)
# referinta: aceleasi zile direct prin evaluate_day_multi
import pandas as pd  # noqa: E402
d = pd.DataFrame(rates)
d["t"] = pd.to_datetime(d.time, unit="s") - pd.Timedelta(hours=7)
d["day"] = d.t.dt.normalize()
d["mins"] = d.t.dt.hour * 60 + d.t.dt.minute
ref = []
for _, g in d.groupby("day"):
    r = evaluate_day_multi(g.open, g.high, g.low, g.close, g.spread.to_numpy(float) * 0.01, g.mins, open_min=570, or_minutes=30,
                           mode="dir", rr=None, slip=0.1, comm=0.0, day_complete=True)
    ref += [t["R"] for t in r["trades"]]
check("backtest_rates = evaluate_day_multi zi cu zi (aceleasi trade-uri, acelasi R)",
      bt["trades"] == len(ref) and abs(bt["expectancy_R"] - round(float(np.mean(ref)), 3)) < 1e-9, (bt, len(ref)))
check("zile de weekend ignorate, rezumat complet (trade-uri / sapt, WR, DD, perioada)",
      bt["days"] == 10 and {"per_week", "win_rate", "max_dd_R", "period"} <= set(bt))
check("fara bare → ok False cu motiv", T.backtest_rates([], m, 0.01)["ok"] is False)

print("3. API: previzualizare + schimbarea slotului")
fm.rates = rates_for(datetime(2026, 3, 2, 10, 0), 10, 102,   # Frankfurt 09:00 = NY 03:00 = server 10:00 (martie)
                      lambda dd, i: (24000 + i, 24002 + i, 23999 + i, 24001 + i), 50)
R._mt5_read = lambda: (threading.RLock(), lambda: fm)
R._slot_busy = lambda sym: None
pv = R.daily_market_preview({"slot": 0, "symbol": "de40", "preset": "frankfurt"})
check("previzualizare DE40 Frankfurt: ora / intervalul / modul din sablon, costuri auto, marja, backtest",
      pv["market"]["symbol"] == "DE40" and pv["market"]["open"] == "09:00" and pv["market"]["tz"] == "Europe/Berlin"
      and pv["costs"]["comm"] == 0 and pv["margin_min_lot"] == 144.5 and pv["backtest"]["ok"], pv.get("backtest"))
check("previzualizarea NU salveaza nimic", C.load_config()["markets"][0]["symbol"] == "GBPUSD")
SENT.clear()
out = R.daily_config_save({"markets": [{"slot": 0, "symbol": "DE40", "preset": "frankfurt"}]})
s0 = out["markets"][0]
check("salvat: slot 1 = DE40 Frankfurt, costuri AUTO, backtest pastrat langa piata",
      (s0["symbol"], s0["preset"], s0["open"], s0["costs_mode"], s0["slip"]) == ("DE40", "frankfurt", "09:00", "auto", 0.125)
      and (s0.get("backtest") or {}).get("ok"), s0)
check("slotul 2 (US500) neatins; re-intrari / R:R ale slotului pastrate",
      out["markets"][1]["symbol"] == "US500" and s0["reentry"]["enabled"] is False and s0["rr"] is None)
check("Telegram: diff-ul schimbarii de piata", any("GBPUSD (london) → DE40 (frankfurt)" in t for t in SENT), SENT)
out = R.daily_config_save({"markets": [{"slot": 0, "symbol": "DE40", "preset": "frankfurt", "costs_mode": "manual",
                                        "slip": 0.3, "comm": 0.1}]})
check("costuri MANUALE respectate", (out["markets"][0]["costs_mode"], out["markets"][0]["slip"], out["markets"][0]["comm"]) == ("manual", 0.3, 0.1))


def refused(body, code):
    try:
        R.daily_config_save(body)
    except Exception as e:
        return getattr(e, "status_code", None) == code
    return False


check("simbol inexistent → 400", refused({"markets": [{"slot": 0, "symbol": "NOPE", "preset": "london"}]}, 400))
check("simbol netranzactionabil → 400", refused({"markets": [{"slot": 0, "symbol": "OLD", "preset": "london"}]}, 400))
check("aceeasi piata in ambele sloturi → 400", refused({"markets": [{"slot": 0, "symbol": "US500", "preset": "frankfurt"}]}, 400))
check("bursa necunoscuta → 400", refused({"markets": [{"slot": 0, "symbol": "DE40", "preset": "tokyo"}]}, 400))
check("slot inexistent → 400", refused({"markets": [{"slot": 5, "symbol": "DE40", "preset": "london"}]}, 400))
R._slot_busy = lambda sym: f"{sym} ocupat"
check("pozitie / ordin in curs pe slot → 409 (piata nu se schimba)",
      refused({"markets": [{"slot": 1, "symbol": "GBPUSD", "preset": "london"}]}, 409))
R._slot_busy = lambda sym: None
out = R.daily_config_save({"markets": [{"symbol": "DE40", "rr": 3, "reentry": {"enabled": True}}]})
check("R:R / re-intrari se schimba in continuare pe simbol", out["markets"][0]["rr"] == 3.0 and out["markets"][0]["reentry"]["enabled"])
out = R.daily_config_save({"markets": [{"slot": 0, "symbol": "GBPUSD", "preset": "london"}]})
check("revenire la GBPUSD Londra: costuri auto (slip 25% din 10 points, markup 9 points)",
      out["markets"][0]["symbol"] == "GBPUSD" and abs(out["markets"][0]["comm"] - 0.00009) < 1e-12, out["markets"][0])
check("engine-ul citeste piata noua (hot-reload)", [m_["symbol"] for m_ in C.load_config()["markets"]] == ["GBPUSD", "US500"])
shutil.rmtree(TMP, ignore_errors=True)
print(f"\n{'TOATE TESTELE AU TRECUT' if not FAIL else f'{FAIL} TESTE ESUATE'}")
sys.exit(1 if FAIL else 0)
