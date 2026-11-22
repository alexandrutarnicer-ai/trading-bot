"""Teste: regulile DETERMINISTE + briefing-ul AI Engine (23.11.2026) — offline, fara LLM / MT5.

    python scripts/test_ai_decision_rules.py
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ai_engine import council, executor, perception  # noqa: E402
from ai_engine.config import DEFAULTS  # noqa: E402

OK = FAIL = 0


def check(name, cond, info=None):
    global OK, FAIL
    OK += bool(cond)
    FAIL += not cond
    print(f"  {'OK  ' if cond else 'FAIL'} {name}" + ("" if cond or info is None else f"  → {info}"))


CFG = {**DEFAULTS}
SNAP = {"symbol": "EURUSD", "price": 1.10000, "atr": 0.0010, "regime": "TRENDING", "efficiency": 0.4, "high_20": 1.10050,
        "low_20": 1.09500, "swing_highs": [1.10050], "swing_lows": [1.09500], "trend_m30": 1, "trend_d1": 1, "weekly_up": 1,
        "adx_d1_gt25": 1, "ema_align": "bullish", "rsi": 58.0, "atr_pctile": 50.0, "efficiency_pctile": 70.0,
        "ret_1h_pct": 0.1, "ret_4h_pct": 0.2, "ret_1d_pct": 0.3, "weekday": 1, "hour": 11,
        "bar_time": "2026-11-24 11:00:00", "news": [], "news_status": "ok", "news_age_min": 5}

print("1. Regula CHOPPY (in cod)")
long_ok = {"action": "OPEN_LONG", "order_type": "stop", "entry": 1.10070, "sl": 1.09820, "tp": 1.10570}
ok, why, _ = executor.apply_decision_gates(long_ok, {**SNAP, "regime": "CHOPPY", "efficiency": 0.08}, CFG)
check("OPEN in regim CHOPPY → respins in cod", not ok and "CHOPPY" in why, why)
ok, why, _ = executor.apply_decision_gates(long_ok, {**SNAP, "regime": "CHOPPY"}, {**CFG, "gate_choppy": False})
check("gate_choppy oprit din config → permis", ok)
ok, why, d = executor.apply_decision_gates({"action": "WAIT"}, {**SNAP, "regime": "CHOPPY"}, CFG)
check("WAIT / CLOSE nu sunt atinse de reguli", ok and d == {"action": "WAIT"})

ok, why, _ = executor.apply_decision_gates(long_ok, {**SNAP, "trend_m30": -1, "trend_d1": -1}, CFG)
check("LONG contra AMBELOR trenduri (M30 + D1 jos) → respins in cod", not ok and "AMBELOR" in why, why)
ok, why, _ = executor.apply_decision_gates(long_ok, {**SNAP, "trend_m30": 1, "trend_d1": -1}, CFG)
check("LONG cu M30 sus, D1 jos (conflict partial) → permis (decide consiliul)", ok)
ok, why, _ = executor.apply_decision_gates(long_ok, {**SNAP, "trend_m30": -1, "trend_d1": -1}, {**CFG, "gate_counter_trend": False})
check("gate_counter_trend oprit → permis", ok)

print("2. SL minim 2,5 × ATR (largit, TP la acelasi RR)")
tight = {"action": "OPEN_LONG", "order_type": "stop", "entry": 1.10070, "sl": 1.09970, "tp": 1.10270}   # SL 1 ATR, RR 2
ok, why, d = executor.apply_decision_gates(tight, SNAP, CFG)
check("SL de 1 ATR → largit la 2,5 ATR", ok and abs((d["entry"] - d["sl"]) - 0.0025) < 1e-9, d)
check("... TP mutat la acelasi RR 2", abs((d["tp"] - d["entry"]) - 0.0050) < 1e-9, d)
short = {"action": "OPEN_SHORT", "order_type": "stop", "entry": 1.09480, "sl": 1.09560, "tp": 1.09320}
ok, why, d = executor.apply_decision_gates(short, {**SNAP, "trend_m30": -1, "trend_d1": -1}, CFG)
check("SHORT: SL largit DEASUPRA intrarii, TP dedesubt", ok and d["sl"] > d["entry"] > d["tp"]
      and abs((d["sl"] - d["entry"]) - 0.0025) < 1e-9, d)
ok, why, d = executor.apply_decision_gates(long_ok, SNAP, CFG)
check("SL deja >= 2,5 ATR → neschimbat", d is long_ok and why == "")
ok, why, d = executor.apply_decision_gates(tight, SNAP, {**CFG, "min_sl_atr": 0})
check("min_sl_atr 0 → regula oprita", d is tight)
bad = {"action": "OPEN_LONG", "order_type": "stop", "entry": 1.10070, "sl": 1.10170, "tp": 1.10270}
ok, why, d = executor.apply_decision_gates(bad, SNAP, CFG)
check("SL pe partea gresita → lasat neatins (respins de validate_decision)", d is bad
      and executor.validate_decision(bad, SNAP, CFG, 0, 0.0) is not None)
ok, why, d = executor.apply_decision_gates(tight, SNAP, CFG)
check("decizia largita trece rails-urile existente (SL ≤ 5 ATR, RR ≥ min)", executor.validate_decision(d, SNAP, CFG, 0, 0.0) is None,
      executor.validate_decision(d, SNAP, CFG, 0, 0.0))

print("3. Briefing: calendar indisponibil + niveluri de referinta calculate in cod")
b = perception.render_text({**SNAP, "news_status": "unavailable"})
check("calendar cazut → „UNAVAILABLE … UNKNOWN” (nu „nicio stire”)", "UNAVAILABLE" in b and "none relevant" not in b)
b = perception.render_text({**SNAP, "news_status": "stale", "news_age_min": 400})
check("calendar vechi → varsta afisata", "last updated 400 min ago" in b)
b = perception.render_text(SNAP)
check("intrarea LONG de referinta e DEASUPRA pretului", "buy-stop at or above 1.1006" in b, [l for l in b.splitlines() if "Reference" in l])
check("intrarea SHORT de referinta e SUB pret", "sell-stop at or below 1.0949" in b)
check("distanta minima SL = 2,5 ATR", "Minimum stop-loss distance: 0.0025" in b)
b = perception.render_text({**SNAP, "price": 1.10300})
check("pret deja peste range → „Location” negativ (intrare tarzie vizibila)", "-2.5 ATR from the 20-bar high" in b,
      [l for l in b.splitlines() if l.startswith("Location")])
off = perception.render_text(SNAP, regime_aware=False)
check("regime_aware=False → fara liniile noi (compat)", "Reference stop entries" not in off and "Location:" not in off)

print("4. Prompturi: WAIT implicit, simetrie, fara impingere spre trade; filtrul Custom neatins")
check("motorul foloseste preambulul NOU", council._TECH_SYS.startswith(council._ENGINE_PREAMBLE))
check("„No trade is the default”", "NO TRADE is the default" in council._ENGINE_PREAMBLE)
check("scara de incredere aliniata cu pragul de 80 al motorului", "Above 80 ONLY when" in council._ENGINE_PREAMBLE)
check("long si short pe acelasi standard", "same standard" in council._ENGINE_PREAMBLE)
check("regula „normal outcome … OPEN” a disparut", "normal" not in council._HEAD_SYS.lower() or "outcome of a desk" not in council._HEAD_SYS)
check("„a stop order costs NOTHING … no certainty” a disparut", "do not need certainty" not in council._HEAD_SYS)
check("ordinea optiunilor nu mai incepe cu long", '"bias": "short"|"neutral"|"long"' in council._TECH_USER)
check("analistul macro: calendar indisponibil → event_risk unknown", '"unknown"' in council._MACRO_USER)
from ai_engine import trade_filter  # noqa: E402
check("filtrul pre-trade Custom pastreaza preambulul VECHI (praguri calibrate)", trade_filter._TECH_SYS.startswith(council._PREAMBLE)
      and council._PREAMBLE != council._ENGINE_PREAMBLE)

print("5. Date vechi → fara consiliu")
from ai_engine import engine as E  # noqa: E402
import tz_helper  # noqa: E402
real = tz_helper.now_local
E.now_local = lambda: datetime(2026, 11, 24, 11, 20)
check("bara inchisa 11:00, acum 11:20 → varsta ~5 min", E._bar_age_min(SNAP) == 5, E._bar_age_min(SNAP))
E.now_local = lambda: datetime(2026, 11, 24, 13, 0)
check("acum 13:00 → 105 min > 45 → consiliul NU e convocat", E._bar_age_min(SNAP) > CFG["max_data_age_min"])
E.now_local = real

print(f"\n{OK} OK, {FAIL} FAIL")
sys.exit(1 if FAIL else 0)
