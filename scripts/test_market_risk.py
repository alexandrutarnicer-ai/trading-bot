"""Teste: Market Risk Override (20.11.2026) — risc PER PIATA cu prioritate fata de setarile globale, plafonat de un
plafon ABSOLUT, fara a ocoli protectiile obligatorii. Comun Daily + Special (position_sizing + global_guard).

    python scripts/test_market_risk.py        # offline (MT5 simulat, Setari Globale izolate)
"""
from __future__ import annotations

import copy
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import position_sizing as ps  # noqa: E402
from live import global_guard as GG  # noqa: E402

OK = FAIL = 0


def check(name, cond, info=None):
    global OK, FAIL
    OK += bool(cond)
    FAIL += not cond
    print(f"  {'OK  ' if cond else 'FAIL'} {name}" + ("" if cond or info is None else f"  → {info}"))


def settings(cap_on=True, cap=2.0, hard=5.0, cp=False):
    s = copy.deepcopy(GG.DEFAULTS)
    s["risk_cap"].update(enabled=cap_on, max_risk_pct=cap, override_max_pct=hard)
    s["capital_protection"].update(enabled=cp, threshold_pct=90.0, start_balance=1000.0)
    return s


# DE40 la ICMarketsEU: lot minim 0,1 · pas 0,1 · 0,1105 $ / punct la lotul minim (1,105 $ / punct / lot)
DE40 = SimpleNamespace(volume_min=0.1, volume_step=0.1, volume_max=250.0, trade_tick_size=0.01, trade_tick_value=0.01105,
                       point=0.01, digits=2)
US500 = SimpleNamespace(volume_min=0.1, volume_step=0.1, volume_max=250.0, trade_tick_size=0.01, trade_tick_value=0.01,
                        point=0.01, digits=2)
EQ = 300.0

print("1. Validarea setarilor per piata")
check("lipsa → override oprit (comportamentul de dinainte)", ps.sanitize_market_risk(None) == ps.MARKET_RISK_DEFAULT)
r = ps.sanitize_market_risk({"override": True, "risk_pct": "abc", "max_risk_pct": -3})
check("valori invalide → implicite (1% / 1%)", r == {"override": True, "risk_pct": 1.0, "max_risk_pct": 1.0}, r)
r = ps.sanitize_market_risk({"override": True, "risk_pct": 9, "max_risk_pct": 50})
check("risk_pct plafonat la 5%, max la 10%", r["risk_pct"] == 5.0 and r["max_risk_pct"] == 10.0, r)
r = ps.sanitize_market_risk({"override": True, "risk_pct": 2, "max_risk_pct": 1})
check("max_risk_pct nu poate fi sub risk_pct", r["max_risk_pct"] == 2.0, r)

print("2. Ordinea de prioritate (global_guard.risk_policy)")
p = GG.risk_policy(0.01, None, settings(cap=2.0))
check("override OPRIT → riscul engine-ului + limita GLOBALA", p["source"] == "global" and p["risk_pct"] == 0.01
      and p["cap_pct"] == 2.0, p)
p = GG.risk_policy(0.01, None, settings(cap_on=False))
check("override oprit + limita globala oprita → fara plafon (ca inainte)", p["cap_pct"] is None, p)
p = GG.risk_policy(0.01, {"override": True, "risk_pct": 1.0, "max_risk_pct": 3.0}, settings(cap=2.0))
check("override PORNIT → setarile pietei (3%) au prioritate peste limita globala (2%)", p["source"] == "market"
      and p["cap_pct"] == 3.0, p)
p = GG.risk_policy(0.01, {"override": True, "risk_pct": 1.0, "max_risk_pct": 8.0}, settings(cap=2.0, hard=5.0))
check("plafonul ABSOLUT (5%) nu poate fi depasit de nicio piata (8% → 5%)", p["cap_pct"] == 5.0 and p["clamped"], p)
p = GG.risk_policy(0.01, {"override": True, "risk_pct": 1.0, "max_risk_pct": 3.0}, settings(cap_on=False))
check("override functioneaza si cu limita globala oprita", p["cap_pct"] == 3.0, p)

print("3. Dimensionarea (position_sizing.size_with_policy) — DE40, equity 300 $")
pol = GG.risk_policy(0.01, {"override": True, "risk_pct": 1.0, "max_risk_pct": 3.0}, settings())
r = ps.size_with_policy(DE40, 26000, 26000 - 50, EQ, EQ, pol)          # SL 50 pct → lot minim 5,53 $ = 1,8%
check("SL 50 pct: lotul minim (1,8%) incape sub maximul pietei 3% → 0,1", r["lots"] == 0.1 and r["at_min_lot"], r)
r = ps.size_with_policy(DE40, 26000, 26000 - 100, EQ, EQ, pol)         # 11,05 $ = 3,7% > 3%
check("SL 100 pct: lotul minim (3,7%) peste maximul pietei 3% → RESPINS, nu rotunjit in sus",
      r["lots"] == 0 and "override" in (r.get("risk_cap") or ""), r)
check("... motivul si riscul care ar fi fost sunt pastrate (afisare)", r.get("blocked_lots") == 0.1
      and abs(r.get("blocked_risk_money", 0) - 11.05) < 0.01, r)
pol_strict = GG.risk_policy(0.01, {"override": True, "risk_pct": 1.0}, settings())
r = ps.size_with_policy(DE40, 26000, 26000 - 50, EQ, EQ, pol_strict)
check("override 1% fara maxim separat: lotul minim 1,8% > 1% → RESPINS", r["lots"] == 0, r)
pol_g = GG.risk_policy(0.01, None, settings(cap=2.0))
r = ps.size_with_policy(DE40, 26000, 26000 - 50, EQ, EQ, pol_g)
check("aceeasi piata FARA override: limita globala 2% → 1,8% incape (0,1)", r["lots"] == 0.1, r)
r = ps.size_with_policy(DE40, 26000, 26000 - 60, EQ, EQ, pol_g)
check("fara override, SL 60 pct (2,2%) > limita globala 2% → respins", r["lots"] == 0, r)
r = ps.size_with_policy(DE40, 26000, 26000 - 60, EQ, EQ, pol)
check("cu override 3%, acelasi SL 60 pct → 0,1 (DE40 nu mai e blocat de limita globala)", r["lots"] == 0.1, r)
r = ps.size_with_policy(DE40, 26000, 26000 - 1000, EQ, EQ, pol)
check("SL foarte mare (1000 pct = 37%) → respins", r["lots"] == 0, r)
r = ps.size_with_policy(US500, 7000, 7000 - 0.001, EQ, EQ, GG.risk_policy(0.01, {"override": True, "risk_pct": 1, "max_risk_pct": 3}, settings()))
check("SL foarte mic (0,001 pct) → plafonat la volume_max 250 (marja decide mai departe)", r["lots"] == 250.0 and r["capped_max"], r)
r = ps.size_with_policy(DE40, 26000, 26000 - 50, 0.0, EQ, pol)
check("capital alocat 0 (equity indisponibil) → nimic", r["lots"] == 0 and "capital" in (r["reason"] or ""), r)
r = ps.size_with_policy(None, 26000, 25950, EQ, EQ, pol)
check("symbol_info indisponibil → nimic", r["lots"] == 0, r)
r1 = ps.size_with_policy(US500, 7000, 6970, 300, 300, GG.risk_policy(0.01, {"override": True, "risk_pct": 1, "max_risk_pct": 2}, settings()))
r2 = ps.size_with_policy(US500, 7000, 6970, 1200, 1200, GG.risk_policy(0.01, {"override": True, "risk_pct": 1, "max_risk_pct": 2}, settings()))
check("capitalul se schimba → lotul se recalculeaza (300 $ → 0,1 · 1200 $ → 0,4)", r1["lots"] == 0.1 and r2["lots"] == 0.4, (r1["lots"], r2["lots"]))

print("4. Protectiile OBLIGATORII nu pot fi ocolite de override")
orig = GG.load_settings
GG.load_settings = lambda path=None: settings(cp=True)
try:
    acc = SimpleNamespace(equity=EQ, balance=EQ)
    mt5 = SimpleNamespace(account_info=lambda: acc, history_deals_get=lambda *a, **k: [], positions_get=lambda **k: [],
                          orders_get=lambda **k: [])
    ok, why = GG.check_open(mt5, "daily", "DE40")
    check("Protectia capitalului activa (equity 300 < 90% din 1000) → Daily blocat, indiferent de override",
          ok is False and "capital" in why.lower(), why)
finally:
    GG.load_settings = orig

print("5. Daily Engine — doua piete, una cu override, una pe setarile globale (MT5 simulat)")
import daily_engine.engine as DE  # noqa: E402
from daily_engine.config import _sanitize, load_config  # noqa: E402

cfg = load_config()
raw = copy.deepcopy(cfg)
raw["markets"][1]["risk"] = {"override": True, "risk_pct": 1.0, "max_risk_pct": 3.0}   # DE40 (slotul 2)
raw["markets"][0].pop("risk", None)                                                   # US500 → globale
clean = _sanitize(raw)
check("config: override pastrat dupa sanitize (restart / reincarcare)", clean["markets"][1]["risk"]["override"]
      and clean["markets"][1]["risk"]["max_risk_pct"] == 3.0 and not clean["markets"][0]["risk"]["override"])
eng = DE.DailyEngine.__new__(DE.DailyEngine)
eng.cfg = clean
infos = {"DE40": DE40, "US500": US500}
eng.mt5 = SimpleNamespace(account_info=lambda: SimpleNamespace(equity=EQ, currency="USD", margin=0.0),
                          symbol_info=lambda s: infos[s])
GG.load_settings = lambda path=None: settings(cap=2.0)
try:
    de = eng._sized("DE40", DE40, 26000, 26000 - 60, EQ, eng.mt5.account_info())
    us = eng._sized("US500", US500, 7000, 7000 - 70, EQ, eng.mt5.account_info())
    check("DE40 (override 3%): SL 60 pct → 0,1 loturi", de["lots"] == 0.1 and de["policy_source"] == "market", de)
    check("US500 (global 2%): SL 70 pct (2,3%) → respins de limita globala", us["lots"] == 0 and us["policy_source"] == "global", us)
    check("politica fiecarei piete e independenta", eng.risk_policy("DE40")["source"] == "market"
          and eng.risk_policy("US500")["source"] == "global")
    v = eng.virtual_size("DE40", {"entry": 26000, "sl": 26000 - 60})
    check("shadow: estimarea virtuala foloseste aceeasi politica (0,1 loturi)", v["lots"] == 0.1, v)
finally:
    GG.load_settings = orig

print("6. Special Engine — aceeasi politica (cod comun)")
try:
    import special_engine.engine as SE
    from special_engine.config import sanitize as s_sanitize
    sc = s_sanitize({"markets": {"JP225": {"mode": "shadow", "risk": {"override": True, "risk_pct": 1, "max_risk_pct": 2}},
                                 "USTEC": {"mode": "pause"}}})
    check("Special: override pastrat dupa sanitize, piata fara risk ramane pe global",
          sc["markets"]["JP225"]["risk"]["override"] and "risk" not in sc["markets"]["USTEC"])
    se = SE.SpecialEngine.__new__(SE.SpecialEngine)
    se.cfg = sc
    GG.load_settings = lambda path=None: settings(cap=2.0)
    try:
        check("Special: JP225 → market, USTEC → global", se.risk_policy("JP225")["source"] == "market"
              and se.risk_policy("USTEC")["source"] == "global")
    finally:
        GG.load_settings = orig
except ImportError:
    print("     sarit: special_engine indisponibil pe acest branch")

print(f"\n{OK} OK, {FAIL} FAIL")
sys.exit(1 if FAIL else 0)
