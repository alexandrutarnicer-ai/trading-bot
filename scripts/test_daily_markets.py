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
import json as _json
with open(C.CFG_PATH, "w", encoding="utf-8") as _f:          # pornim de la configuratia IMPLICITA (nu de la cea a masinii)
    _json.dump(C.DEFAULTS, _f)
from daily_engine import market_tools as T  # noqa: E402
from daily_engine.strategy import evaluate_day_multi  # noqa: E402
from api.routers import daily_engine as R  # noqa: E402
import api.audit_log as AL  # noqa: E402
AL.AUDIT_FILE = os.path.join(TMP, "audit.jsonl")       # testul nu scrie in jurnalul de audit real

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
# backtestul automat (api/backtest_refresh): store temporar + job simulat — testul nu atinge MT5-ul real / fisierul real
import api.backtest_refresh as BR  # noqa: E402
BR.STORE_PATHS = {"daily": os.path.join(TMP, "bt_auto_daily.json"), "noisy": os.path.join(TMP, "bt_auto_noisy.json")}
BT_JOBS = []
BR.daily_job = lambda m_: (BT_JOBS.append(m_["symbol"]), (lambda: {"ok": True, "trades": 1, "summary": m_["symbol"]}))[1]
pv = R.daily_market_preview({"slot": 0, "symbol": "de40", "preset": "frankfurt"})
check("previzualizare DE40 Frankfurt: ora / intervalul / modul din sablon, costuri auto, marja, backtest",
      pv["market"]["symbol"] == "DE40" and pv["market"]["open"] == "09:00" and pv["market"]["tz"] == "Europe/Berlin"
      and pv["costs"]["comm"] == 0 and pv["margin_min_lot"] == 144.5 and pv["backtest"]["ok"], pv.get("backtest"))
check("previzualizarea NU salveaza nimic", C.load_config()["markets"][0]["symbol"] == "GBPUSD")
SENT.clear()
out = R.daily_config_save({"markets": [{"slot": 0, "symbol": "DE40", "preset": "frankfurt"}]})
s0 = out["markets"][0]
check("salvat: slot 1 = DE40 Frankfurt, costuri AUTO; backtestul vechi scos din config",
      (s0["symbol"], s0["preset"], s0["open"], s0["costs_mode"], s0["slip"]) == ("DE40", "frankfurt", "09:00", "auto", 0.125)
      and "backtest" not in s0, s0)
check("... backtestul configuratiei noi pornit AUTOMAT in fundal (fingerprint nou)", "DE40" in BT_JOBS, BT_JOBS)
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

print("4. API: pauza per piata (Pause / Resume)")
SENT.clear()
r1 = R.daily_market_pause(1)
cfg_p = C.load_config()["markets"][1]
check("pause slot 2: persistat in config (paused + moment UTC), slotul 1 neatins",
      r1["paused"] and r1["changed"] and cfg_p["paused"] and cfg_p["paused_at"] and not C.load_config()["markets"][0]["paused"], cfg_p)
check("... Telegram o data", sum("PE PAUZĂ" in t for t in SENT) == 1, SENT)
check("pause repetat → fara schimbare / fara mesaj nou", R.daily_market_pause(1)["changed"] is False and
      sum("PE PAUZĂ" in t for t in SENT) == 1)
out = R.daily_config_save({"markets": [{"symbol": C.load_config()["markets"][1]["symbol"], "rr": 2}]})
check("salvarea altor optiuni (R:R) pastreaza pauza", C.load_config()["markets"][1]["paused"] is True)
r2 = R.daily_market_resume(1)
check("resume → activ, momentul pauzei sters", r2["paused"] is False and C.load_config()["markets"][1]["paused_at"] is None)
try:
    R.daily_market_pause(5)
    check("slot invalid → 400", False)
except R.HTTPException as e:
    check("slot invalid → 400", e.status_code == 400)

print("5. Cardurile sunt INDEPENDENTE (orice setare a unui slot nu atinge celalalt slot)")
import copy as _copy  # noqa: E402


def _slot_raw(i):
    with open(C.CFG_PATH, encoding="utf-8") as f_:
        return _json.load(f_)["markets"][i]


def _iso(slot, actions):
    other = 1 - slot
    before = _copy.deepcopy(_slot_raw(other))
    BT_JOBS.clear()
    for a in actions:
        a()
    after = _slot_raw(other)
    return before == after, (before, after)


for slot in (0, 1):
    sym = C.load_config()["markets"][slot]["symbol"]
    other_sym = C.load_config()["markets"][1 - slot]["symbol"]
    BR.STORE_PATHS["daily"] = os.path.join(TMP, f"bt_iso_{slot}.json")
    R.daily_config_save({})                                   # backtest_auto initial pe ambele sloturi
    ok, info = _iso(slot, [
        lambda: R.daily_config_save({"markets": [{"symbol": sym, "rr": 4}]}),
        lambda: R.daily_config_save({"markets": [{"symbol": sym, "reentry": {"enabled": True, "max_trades": 5}}]}),
        lambda: R.daily_market_pause(slot),
        lambda: R.daily_market_resume(slot),
    ])
    check(f"slot {slot + 1}: R:R + re-intrari + pauza / resume → slotul {2 - slot} identic (byte cu byte)", ok, info)
    check(f"... backtestul automat pornit DOAR pentru slotul {slot + 1} ({sym})",
          BT_JOBS and set(BT_JOBS) == {sym}, BT_JOBS)
    new_sym = "DE40" if "DE40" not in (sym, other_sym) else "GBPUSD"
    if new_sym == other_sym:
        new_sym = "US500"
    ok, info = _iso(slot, [lambda: R.daily_config_save({"markets": [{"slot": slot, "symbol": new_sym, "preset": "frankfurt",
                                                                        "costs_mode": "manual", "slip": 0.2, "comm": 0.05}]})])
    check(f"slot {slot + 1}: schimbarea PIETEI + costuri manuale ({sym} → {new_sym}) → slotul {2 - slot} identic", ok, info)
    check(f"... backtestul automat doar pentru piata noua a slotului {slot + 1}", set(BT_JOBS) == {new_sym}, BT_JOBS)
    m_ = C.load_config()["markets"]
    check(f"... setarile slotului {slot + 1} raman ale lui (R:R 4, re-intrari 5)",
          m_[slot]["rr"] == 4.0 and m_[slot]["reentry"]["enabled"] and m_[slot]["reentry"]["max_trades"] == 5, m_[slot])
    check(f"... slotul {2 - slot} are in continuare setarile lui (nu le-a preluat pe ale slotului {slot + 1})",
          m_[1 - slot]["rr"] != 4.0 or m_[1 - slot]["reentry"].get("max_trades") != 5, m_[1 - slot])
    R.daily_config_save({"markets": [{"symbol": m_[slot]["symbol"], "rr": None, "reentry": {"enabled": False}}]})

print("6. Modul PER PIATA (Live / Shadow / Pauza), Profit Lock, audit")
SENT.clear()
R.daily_config_save({"mode": "shadow"})
r = R.daily_market_mode(0, {"mode": "live"})
cm = C.load_config()["markets"]
check("slot 1 → LIVE; slotul 2 rămâne SHADOW (independent)", r["changed"] and cm[0]["mode"] == "live"
      and cm[1]["mode"] == "shadow" and C.load_config()["mode"] == "execute", [x["mode"] for x in cm])
check("... Telegram + audit (live)", any("pe LIVE" in t for t in SENT) and any(a["action"] == "mode" and a["after"] == "live"
                                                                              for a in AL.read()), SENT)
r = R.daily_market_mode(1, {"mode": "pause"})
cm = C.load_config()["markets"]
check("slot 2 → PAUZĂ; slotul 1 rămâne LIVE", cm[0]["mode"] == "live" and cm[1]["mode"] == "pause" and cm[1]["paused"], cm[1])
r = R.daily_market_mode(1, {"mode": "shadow"})
cm = C.load_config()["markets"]
check("slot 2 din PAUZĂ → SHADOW: pauza scoasă, modul shadow", cm[1]["mode"] == "shadow" and not cm[1]["paused"], cm[1])
check("mod repetat → fără schimbare", R.daily_market_mode(0, {"mode": "live"})["changed"] is False)
try:
    R.daily_market_mode(0, {"mode": "turbo"})
    check("mod invalid → 400", False)
except R.HTTPException as e:
    check("mod invalid → 400", e.status_code == 400)
with open(C.CFG_PATH, encoding="utf-8") as f_:
    raw_ = _json.load(f_)
check("modul fiecărei piețe e scris explicit în fișier (persistă la restart)",
      [x.get("exec_mode") for x in raw_["markets"]] == ["live", "shadow"], [x.get("exec_mode") for x in raw_["markets"]])
sym0 = C.load_config()["markets"][0]["symbol"]
other = C.load_config()["markets"][1]["symbol"]
new0 = "DE40" if "DE40" not in (sym0, other) else ("GBPUSD" if other != "GBPUSD" else "US500")
out = R.daily_config_save({"markets": [{"slot": 0, "symbol": new0, "preset": "frankfurt"}]})
check(f"piață NOUĂ în slot ({sym0} → {new0}) pornește în SHADOW (Live se aprobă per piață)",
      C.load_config()["markets"][0]["mode"] == "shadow", C.load_config()["markets"][0]["mode"])
out = R.daily_config_save({"markets": [{"symbol": new0, "profit_lock": {"enabled": True, "trigger_R": 4.5, "lock_R": 4}}]})
cm = C.load_config()["markets"]
check("Profit Lock salvat pe o piață; cealaltă rămâne OPRITĂ", cm[0]["profit_lock"] == {"enabled": True, "trigger_R": 4.5,
      "lock_R": 4.0} and not cm[1]["profit_lock"]["enabled"], [x["profit_lock"] for x in cm])
check("... modificarea apare în audit + Telegram", any("Profit Lock PORNIT" in a["detail"] for a in AL.read()))
out = R.daily_config_save({"markets": [{"symbol": new0, "profit_lock": {"enabled": True, "trigger_R": 1, "lock_R": 9}}]})
check("Profit Lock invalid → corectat în limite (trigger 3R, lock < trigger)",
      C.load_config()["markets"][0]["profit_lock"] == {"enabled": True, "trigger_R": 3.0, "lock_R": 2.9})
R.daily_config_save({"mode": "execute"})
check("compat: modul global vechi „execute” → toate piețele LIVE", [x["exec_mode"] for x in C.load_config()["markets"]] == ["live", "live"])
R.daily_config_save({"mode": "shadow"})
check("compat: modul global „shadow” → toate piețele SHADOW", [x["exec_mode"] for x in C.load_config()["markets"]] == ["shadow", "shadow"])
out = R.daily_config_save({"sizing": {"max_margin_pct": 200}})
check("limita de marjă plafonată la 95%", C.load_config()["sizing"]["max_margin_pct"] == 95.0, C.load_config()["sizing"])

# engine-ul: fiecare piata e evaluata separat (o eroare pe un slot nu opreste celalalt)
import inspect  # noqa: E402
import daily_engine.engine as E  # noqa: E402
src = inspect.getsource(E.DailyEngine)
check("engine: bucla pe piete are try / except PER piata", "for m in self.cfg[\"markets\"]:\n            try:" in src)
shutil.rmtree(TMP, ignore_errors=True)
print(f"\n{'TOATE TESTELE AU TRECUT' if not FAIL else f'{FAIL} TESTE ESUATE'}")
sys.exit(1 if FAIL else 0)
