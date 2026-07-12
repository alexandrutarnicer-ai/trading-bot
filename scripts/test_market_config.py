# -*- coding: utf-8 -*-
"""
Teste pentru configurarea PER PIATA (market_overrides):
  capital_fraction / risk_pct cap / max_rr / max_daily_loss_R /
  max_trades_per_day / isolated (date separate per piata).

Rulare:  python scripts/test_market_config.py     (fara MT5/Ollama — totul simulat)

Acopera si "ordine false": sizing-ul e calculat exact ca la plasare (calc_lots cu
specificatii de simbol simulate) si place() e exersat in mode=shadow (fluxul
complet FARA ordin real in MT5).
"""

import io
import os
import sys
import tempfile
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from ai_engine import config as C, council, executor
from ai_engine.ledger import Ledger

PASS, FAIL = [], []


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  {extra}" if extra else ""))


# ═════════════════════════════════════════════════════════════════════════════
# 1. Config: sanitize + resolver + backward compat
# ═════════════════════════════════════════════════════════════════════════════

s = C.sanitize_market_overrides({
    "eurusd": {"capital_fraction": 0.5, "max_rr": 3.0},
    "XRPUSD": {"risk_pct": 0.5, "max_daily_loss_R": 1.5, "max_trades_per_day": 2,
               "isolated": True},
    "BAD":    "nu-e-dict",
    "GBPUSD": {"capital_fraction": 99, "max_rr": 0.2, "max_trades_per_day": 1000},
}, risk_pct_max=0.02)
check("sanitize: simbol normalizat uppercase", "EURUSD" in s and "eurusd" not in s)
check("sanitize: valori valide pastrate", s["EURUSD"]["capital_fraction"] == 0.5
      and s["EURUSD"]["max_rr"] == 3.0)
check("sanitize: risk_pct clamp la risk_pct_max", s["XRPUSD"]["risk_pct"] == 0.02)
check("sanitize: izolare + limite zilnice", s["XRPUSD"]["isolated"] is True
      and s["XRPUSD"]["max_daily_loss_R"] == 1.5 and s["XRPUSD"]["max_trades_per_day"] == 2)
check("sanitize: override corupt ignorat", "BAD" not in s)
check("sanitize: clamp fraction<=1, max_rr>=1, trades<=20",
      s["GBPUSD"]["capital_fraction"] == 1.0 and s["GBPUSD"]["max_rr"] == 1.0
      and s["GBPUSD"]["max_trades_per_day"] == 20)

cfg = C.load_config()
check("load_config: market_overrides exista (default gol)",
      isinstance(cfg.get("market_overrides"), dict))

m = C.market_cfg({"market_overrides": {}}, "EURUSD")
check("resolver: piata FARA override = pure default-uri (comportament vechi)",
      m["capital_fraction"] == 1.0 and m["risk_pct"] is None and m["max_rr"] is None
      and m["max_daily_loss_R"] is None and m["max_trades_per_day"] is None
      and m["isolated"] is False and m["_has_overrides"] is False)
m = C.market_cfg({"market_overrides": {"EURUSD": {"max_rr": 2.5}}}, "EURUSD")
check("resolver: override partial → doar campul setat difera",
      m["max_rr"] == 2.5 and m["capital_fraction"] == 1.0 and m["_has_overrides"] is True)

# ═════════════════════════════════════════════════════════════════════════════
# 2. Ledger: stop zilnic per piata, anti-overtrading, scorecard izolat
# ═════════════════════════════════════════════════════════════════════════════

db = os.path.join(tempfile.mkdtemp(), "test.db")
L = Ledger(db)
cid = L.add_council("EURUSD", "t", L.add_snapshot("EURUSD", {}), {}, 1.0)
d1 = L.add_decision("EURUSD", cid, {"action": "OPEN_LONG"}, "placed", "", ticket=1)
d2 = L.add_decision("EURUSD", cid, {"action": "OPEN_LONG"}, "placed", "", ticket=2)
d3 = L.add_decision("XRPUSD", cid, {"action": "OPEN_LONG"}, "placed", "", ticket=3)
d4 = L.add_decision("XRPUSD", cid, {"action": "WAIT"}, "skipped", "")
L.add_outcome(d1, "EURUSD", "SL", 1.09, -1.0, -5.0)
L.add_outcome(d2, "EURUSD", "SL", 1.09, -0.8, -4.0)
L.add_outcome(d3, "XRPUSD", "TP", 1.12, 2.0, 10.0)
from datetime import datetime
today = datetime.now().date().isoformat()

check("daily_loss_R global (toate pietele)", abs(L.daily_loss_R(today) - 0.2) < 1e-9)
check("daily_loss_R PER PIATA (EURUSD -1.8R)", abs(L.daily_loss_R(today, "EURUSD") + 1.8) < 1e-9)
check("daily_loss_R PER PIATA (XRPUSD +2.0R)", abs(L.daily_loss_R(today, "XRPUSD") - 2.0) < 1e-9)
check("placed_count per piata (EURUSD=2, XRPUSD=1; WAIT nu conteaza)",
      L.placed_count(today, "EURUSD") == 2 and L.placed_count(today, "XRPUSD") == 1)

sc_all = L.scorecard()
sc_iso = L.scorecard(exclude_symbols=["XRPUSD"])
check("scorecard fara exclude = comportament vechi", sc_all["closed_trades"] == 3
      and abs(sc_all["total_R"] - 0.2) < 1e-9)
check("scorecard cu XRPUSD izolat: doar EURUSD in principal",
      sc_iso["closed_trades"] == 2 and abs(sc_iso["total_R"] + 1.8) < 1e-9
      and sc_iso["decisions"] == 2)
by = L.scorecard_by_symbol()
check("scorecard_by_symbol: date SEPARATE per piata",
      by["XRPUSD"]["total_R"] == 2.0 and by["XRPUSD"]["closed_trades"] == 1
      and by["EURUSD"]["closed_trades"] == 2 and by["EURUSD"]["decisions"] == 2)
L.close()

# ═════════════════════════════════════════════════════════════════════════════
# 3. Rails per piata in validate_decision
# ═════════════════════════════════════════════════════════════════════════════

CFG = C.load_config()
SNAP = {"symbol": "EURUSD", "price": 1.0850, "atr": 0.0009}
GOOD = {"action": "OPEN_LONG", "order_type": "stop", "entry": 1.0862,
        "sl": 1.0832, "tp": 1.0922, "risk_pct": 0.005}

check("compat: fara market_state → decizie valida trece (ca inainte)",
      executor.validate_decision(GOOD, SNAP, CFG, 0, 0.0) is None)
ms = {"symbol": "EURUSD", "daily_r": -1.6, "trades_today": 0,
      "max_daily_loss_R": 1.5, "max_trades_per_day": None}
r = executor.validate_decision(GOOD, SNAP, CFG, 0, 0.0, market_state=ms)
check("stop zilnic PE PIATA: -1.6R cu limita 1.5R → respins", r is not None and "PE PIATA" in r)
ms = {"symbol": "EURUSD", "daily_r": -1.0, "trades_today": 0,
      "max_daily_loss_R": 1.5, "max_trades_per_day": None}
check("stop zilnic PE PIATA: -1.0R cu limita 1.5R → trece",
      executor.validate_decision(GOOD, SNAP, CFG, 0, 0.0, market_state=ms) is None)
ms = {"symbol": "EURUSD", "daily_r": 0.0, "trades_today": 2,
      "max_daily_loss_R": None, "max_trades_per_day": 2}
r = executor.validate_decision(GOOD, SNAP, CFG, 0, 0.0, market_state=ms)
check("anti-overtrading: 2 plasate cu max 2/zi → respins", r is not None and "overtrading" in r)
ms["trades_today"] = 1
check("anti-overtrading: 1 plasat cu max 2/zi → trece",
      executor.validate_decision(GOOD, SNAP, CFG, 0, 0.0, market_state=ms) is None)

# ═════════════════════════════════════════════════════════════════════════════
# 4. Plafon RR (max_rr) — TP adus la plafon, consiliul informat
# ═════════════════════════════════════════════════════════════════════════════

d = {"action": "OPEN_LONG", "order_type": "stop", "entry": 1.10, "sl": 1.09,
     "tp": 1.15,   # 5R propus
     "risk_pct": 0.005, "rationale": "x"}
changed = council.clamp_tp_to_max_rr(d, 2.0)
check("max_rr: TP 5R plafonat la 2R", changed and abs(d["tp"] - 1.12) < 1e-9
      and "plafonat" in d["rationale"])
d2 = {"action": "OPEN_SHORT", "entry": 1.10, "sl": 1.11, "tp": 1.05,  # 5R short
      "risk_pct": 0.005, "rationale": "x"}
check("max_rr SHORT: TP plafonat pe partea corecta",
      council.clamp_tp_to_max_rr(d2, 3.0) and abs(d2["tp"] - 1.07) < 1e-9)
d3 = {"action": "OPEN_LONG", "entry": 1.10, "sl": 1.09, "tp": 1.115,  # 1.5R
      "risk_pct": 0.005, "rationale": "x"}
check("max_rr: TP sub plafon ramane NEATINS",
      not council.clamp_tp_to_max_rr(d3, 2.0) and d3["tp"] == 1.115)
check("max_rr None → nimic (comportament vechi)",
      not council.clamp_tp_to_max_rr(dict(d), None))
check("max_rr pe WAIT → nimic",
      not council.clamp_tp_to_max_rr({"action": "WAIT"}, 2.0))

# dupa plafonare, decizia trece de rail-ul RR>=min (geometria ramane valida)
check("dupa plafonare: validate_decision accepta geometria",
      executor.validate_decision(d, {"symbol": "EURUSD", "price": 1.0950, "atr": 0.004},
                                 CFG, 0, 0.0) is None)

# ═════════════════════════════════════════════════════════════════════════════
# 5. Sizing cu capital_fraction — "ordin fals": exact calculul de la plasare
# ═════════════════════════════════════════════════════════════════════════════

_real_mt5 = executor.mt5
executor.mt5 = SimpleNamespace(symbol_info=lambda s: SimpleNamespace(
    trade_tick_value=1.0, trade_tick_size=0.00001,   # 1$ per 0.00001 → 100k$/unit
    volume_step=0.01, volume_min=0.01))
try:
    # echity 1000$, risc 1%, SL la 30 pips (0.0030)
    lots_full, risk_full = executor.calc_lots("EURUSD", 1.0862, 1.0832, 1000 * 1.0, 0.01)
    lots_half, risk_half = executor.calc_lots("EURUSD", 1.0862, 1.0832, 1000 * 0.5, 0.01)
    lots_min,  _         = executor.calc_lots("EURUSD", 1.0862, 1.0832, 1000 * 0.05, 0.01)
    # Nota: calc_lots rotunjeste loturile IN JOS la volume_step (0.01), deci riscul
    # real e cuantizat sub tinta — comportament existent, corect (niciodata peste).
    check("sizing: fraction 1.0 → risc <= tinta 10$ si aproape de ea",
          7.0 <= risk_full <= 10.0, f"lots={lots_full} risk=${risk_full}")
    check("sizing: fraction 0.5 → tinta injumatatita (risc <= 5$, lots mai mici)",
          risk_half <= 5.0 and lots_half < lots_full,
          f"lots={lots_half} risk=${risk_half}")
    check("sizing: fraction mica → clamp la volume_min (nu 0, nu negativ)",
          lots_min >= 0.01)
finally:
    executor.mt5 = _real_mt5

# place() in mode=shadow — fluxul complet FARA ordin real (ordin fals, zero MT5)
st, detail, tk = executor.place(dict(GOOD), {"symbol": "EURUSD", "price": 1.085},
                                {**CFG, "mode": "shadow"}, 999, capital_fraction=0.5)
check("place shadow: fluxul ruleaza fara ordin real", st == "shadow" and tk is None)

# ═════════════════════════════════════════════════════════════════════════════
# 6. Briefing-ul consiliului: limitele injectate DOAR cand exista override
# ═════════════════════════════════════════════════════════════════════════════

from ai_engine.engine import _market_limits_text

m_def = C.market_cfg({"market_overrides": {}}, "EURUSD")
check("briefing: piata default → _has_overrides False → briefing neschimbat",
      m_def["_has_overrides"] is False)
m_ov = C.market_cfg({"market_overrides": {"EURUSD": {
    "capital_fraction": 0.5, "risk_pct": 0.008, "max_rr": 3.0,
    "max_daily_loss_R": 1.5, "max_trades_per_day": 2}}}, "EURUSD")
txt = _market_limits_text("EURUSD", m_ov, CFG, daily_r=-0.5, trades_today=1)
check("briefing: contine TOATE limitele pentru consiliu",
      all(x in txt for x in ["DESK LIMITS FOR EURUSD", "50% of account equity",
                             "0.80%", "between 1.0 and 3.0", "-1.5R", "-0.50R",
                             "placed today: 1, remaining: 1"]))
m_rr = C.market_cfg({"market_overrides": {"EURUSD": {"max_rr": 2.0}}}, "EURUSD")
txt2 = _market_limits_text("EURUSD", m_rr, CFG, 0.0, 0)
check("briefing: doar campurile configurate apar (max_rr singur)",
      "between" in txt2 and "capital allocated" not in txt2 and "daily loss stop" not in txt2)

# ═════════════════════════════════════════════════════════════════════════════
# 7. Add/remove piete — default-uri corecte + izolarea nu "scapa"
# ═════════════════════════════════════════════════════════════════════════════

# piata NOUA (fara override) → pure default-uri, comportament global, zero config necesar
m_new = C.market_cfg({"market_overrides": {"EURUSD": {"max_rr": 2.0}}}, "NZDUSD")
check("piata NOUA adaugata → default-uri (fara override, briefing neschimbat)",
      m_new["_has_overrides"] is False and m_new["capital_fraction"] == 1.0
      and m_new["max_rr"] is None and m_new["isolated"] is False)

# izolarea derivata din OVERRIDE-URI, nu din lista markets: o piata izolata
# SCOASA din urmarire ramane exclusa din scorecard-ul principal
cfg_iso = {"markets": ["EURUSD", "GBPUSD"],
           "market_overrides": {"XRPUSD": {"isolated": True},
                                "GBPUSD": {"isolated": True},
                                "EURUSD": {"max_rr": 2.0}}}
iso = C.isolated_markets(cfg_iso)
check("isolated_markets: derivat din overrides (include si piata scoasa din lista)",
      iso == ["GBPUSD", "XRPUSD"])
check("isolated_markets: piata cu override ne-izolat NU apare", "EURUSD" not in iso)
check("isolated_markets: fara overrides → gol (comportament vechi)",
      C.isolated_markets({"market_overrides": {}}) == [])

# piata stearsa din overrides → revine complet la default (config sters = promovare)
m_back = C.market_cfg({"market_overrides": {}}, "XRPUSD")
check("config sters → piata revine la comportament global", m_back["_has_overrides"] is False)

# ═════════════════════════════════════════════════════════════════════════════

print("\n" + "═" * 60)
print(f"REZULTAT: {len(PASS)} PASS / {len(FAIL)} FAIL din {len(PASS) + len(FAIL)}")
if FAIL:
    print("ESUATE:", FAIL)
    sys.exit(1)
print("TOATE TESTELE AU TRECUT ✓")
