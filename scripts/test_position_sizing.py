"""
QA: dimensionarea pozitiei (Fraction Account -> Risk -> Position Size -> MT5) pe TOATE cele 3
engine-uri. Offline (MT5 simulat), fara ordine reale.
    python scripts/test_position_sizing.py

Verifica:
 1. componenta comuna position_sizing: rotunjire, lot min / max / step, tick-uri diferite,
    valori foarte mici / foarte mari, volum invalid, capital de baza (sync / fix / equity lipsa)
 2. ACEEASI configuratie -> ACELASI lot si risc pe Custom Engine, AI Engine si Daily Engine
 3. cazurile care inainte erau gresite: 0.5 -> 0.49, fara plafon volume_max, $1000 orb
"""
import os
import sys
from types import SimpleNamespace as NS

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import position_sizing as ps  # noqa: E402

PASS = FAIL = 0


def check(cond, name, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name} {detail}")


def info(vmin=0.01, step=0.01, vmax=100.0, tick_size=0.00001, tick_value=1.0):
    return NS(volume_min=vmin, volume_step=step, volume_max=vmax,
              trade_tick_size=tick_size, trade_tick_value=tick_value, point=tick_size)


FX = info()                                                   # EURUSD: 0.00001 -> $1 / lot
IDX = info(vmin=0.1, step=0.1, vmax=50, tick_size=0.01, tick_value=0.01)   # US500: $1/punct/lot
XRP = info(vmin=100, step=100, vmax=1_000_000, tick_size=0.00001, tick_value=0.01)
JPY = info(tick_size=0.001, tick_value=0.64)                   # cross JPY, cont USD

print("1. Componenta comuna")
check(ps.snap_volume(FX, 0.5) == 0.5, "0.5 ramane 0.50 (fara eroarea float 0.49)", ps.snap_volume(FX, 0.5))
check(ps.snap_volume(FX, 0.299999999) == 0.29, "floor la pas (nu creste expunerea)", ps.snap_volume(FX, 0.299999999))
check(ps.snap_volume(FX, 0.001) == 0.01, "sub minim -> lotul minim")
check(ps.snap_volume(FX, 1e6) == 100.0, "peste maxim -> plafonat la volume_max")
check(ps.snap_volume(IDX, 0.37) == 0.3, "pas 0.1 (indici)")
check(ps.snap_volume(XRP, 1234) == 1200, "pas 100 (XRPUSD)")
check(ps.snap_volume(info(step=0.001, vmin=0.001), 0.0567) == 0.056, "pas 0.001 -> 3 zecimale")

r = ps.size_by_risk(FX, 1.10000, 1.09800, capital=10_000, risk_pct=0.01)   # $100 risc, 200 puncte
check(r["lots"] == 0.5 and abs(r["risk_money"] - 100) < 1e-6 and not r["at_min_lot"], "cont mare: lotul corect, risc = tinta", r)
r = ps.size_by_risk(FX, 1.10000, 1.09800, capital=206 * 0.2, risk_pct=0.01)
check(r["lots"] == 0.01 and r["at_min_lot"] and r["ratio"] > 4, "cont mic: lot minim, risc real > tinta (marcat)", r)
r = ps.size_by_risk(IDX, 6000, 5990, capital=206, risk_pct=0.01)
check(r["lots"] == 0.2 and abs(r["risk_money"] - 2.0) < 1e-9, "indice: $2.06 / 10 puncte = 0.206 -> 0.2 lot ($2)", r)
r = ps.size_by_risk(JPY, 150.000, 149.500, capital=5000, risk_pct=0.01)
check(abs(r["risk_money"] - r["lots"] * 500 * 0.64) < 1e-6, "cross JPY: tick_value MT5 deja in moneda contului", r)
r = ps.size_by_risk(FX, 1.1, 1.1, capital=1000, risk_pct=0.01)
check(r["lots"] == 0 and "SL" in r["reason"], "SL zero -> fara ordin")
r = ps.size_by_risk(None, 1.1, 1.09, capital=1000, risk_pct=0.01)
check(r["lots"] == 0, "simbol fara specificatii -> fara ordin")
r = ps.size_by_risk(info(tick_value=0), 1.1, 1.09, capital=1000, risk_pct=0.01)
check(r["lots"] == 0, "tick_value 0 -> fara ordin (volum invalid evitat)")
r = ps.size_by_risk(FX, 1.1, 1.09, capital=0, risk_pct=0.01)
check(r["lots"] == 0 and "capital" in r["reason"], "capital 0 (equity lipsa) -> fara ordin")
r = ps.size_by_risk(FX, 1.10000, 1.09999, capital=10_000_000, risk_pct=0.02)
check(r["lots"] == 100.0 and r["capped_max"], "valoare foarte mare -> plafon volume_max, marcat", r)
check(ps.capital_base(True, 1000, 206.09) == 206.09, "sync: equity real MT5")
check(ps.capital_base(False, 1000, 206.09) == 206.09, "capital fix plafonat la equity (typo-safe)")
check(ps.capital_base(False, 150, 206.09) == 150, "capital fix sub equity")
check(ps.capital_base(True, 1000, None) == 0.0, "sync + equity indisponibil -> 0 (nu $1000)")
check(ps.clamp_fraction(1.7) == 1.0 and ps.clamp_fraction(-1) == 0 and ps.clamp_fraction("x") == 0, "fractie limitata la 0..1")
lots, red = ps.fit_to_margin(FX, 1.0, margin_need=400, free_margin=206, cap_fraction=0.8)
check(red and lots == 0.41, "marja: lot redus sa incapa sub 80% din marja libera", (lots, red))
check(ps.fit_to_margin(FX, 1.0, None, 206, 0.8) == (1.0, False), "marja necunoscuta -> nemodificat")

print("2. Aceeasi configuratie -> acelasi rezultat pe toate 3 engine-urile")
import live.global_guard as GG  # noqa: E402
GG.risk_cap_pct = lambda settings=None: None     # limita globala testata separat (sectiunea 4)


class FakeMt5:
    ORDER_TYPE_BUY, ORDER_TYPE_SELL = 0, 1

    def __init__(self, sym_info, equity, balance=None):
        self.si, self.eq, self.bal = sym_info, equity, balance or equity

    def symbol_info(self, s): return self.si
    def account_info(self): return NS(equity=self.eq, balance=self.bal, margin_free=self.eq, currency="USD")
    def order_calc_margin(self, *a): return 1.0


import live.signal_generator as sg  # noqa: E402
import ai_engine.executor as ex  # noqa: E402
from daily_engine import engine as de  # noqa: E402


class Log:
    def info(self, *a): pass
    def debug(self, *a): pass
    def warning(self, *a): pass


CASES = [  # (eticheta, specificatii, equity, balance, fractie, risc, entry, sl)
    ("FX cont mic", FX, 206.09, 206.09, 0.2, 0.01, 1.10000, 1.09800),
    ("FX cont mare", FX, 50_000, 50_000, 0.25, 0.01, 1.10000, 1.09800),
    ("equity < balance", FX, 9_000, 10_000, 0.5, 0.01, 1.30000, 1.29500),
    ("equity > balance", FX, 11_000, 10_000, 0.5, 0.01, 1.30000, 1.29500),
    ("indice pas 0.1", IDX, 206.09, 206.09, 1.0, 0.01, 6000.0, 5980.0),
    ("XRP pas 100", XRP, 2_000, 2_000, 1.0, 0.01, 0.5000, 0.4900),
    ("cross JPY", JPY, 5_000, 5_000, 0.3, 0.01, 150.000, 149.400),
    ("valoare uriasa", FX, 50_000_000, 50_000_000, 1.0, 0.02, 1.10000, 1.09990),
]
for label, si, eq, bal, frac, risk, entry, sl in CASES:
    fake = FakeMt5(si, eq, bal)
    # Custom Engine
    sg._mt5_exec = fake
    cfg = {"account_fraction": frac, "capital_sync_mt5": True}
    cap_bot = sg._session_capital(cfg, Log())
    bot_lots, bot_risk = sg._calc_lots("X", entry, sl, cap_bot, risk)
    # AI Engine (aceeasi fractie / risc)
    ex.mt5 = fake
    ex.equity = lambda: fake.eq
    cap_ai = ex.capital_base({"capital_sync_mt5": True}) * ps.clamp_fraction(frac)
    ai_lots, ai_risk = ex.calc_lots("X", entry, sl, cap_ai, risk)
    # Daily Engine
    d = de.DailyEngine(mt5_module=fake)
    d.cfg = {"sizing": {"capital_sync_mt5": True, "capital_usd": None, "fraction": frac, "risk_pct": risk}}
    dz = d.virtual_size("X", {"entry": entry, "sl": sl})
    same = bot_lots == ai_lots == dz["lots"] and abs(cap_bot - cap_ai) < 1e-9
    risk_same = abs((bot_risk or 0) - (ai_risk or 0)) < 0.01 and abs((bot_risk or 0) - dz["risk_money"]) < 0.01
    check(same and risk_same, f"{label}: lot {bot_lots} / risc {bot_risk} identice (Custom = AI = Daily)",
          (bot_lots, ai_lots, dz["lots"], bot_risk, ai_risk, dz["risk_money"]))

print("3. Erorile reparate")
sg._mt5_exec = NS(account_info=lambda: None, symbol_info=lambda s: FX)
check(sg._session_capital({"account_fraction": 0.2}, Log()) == 0.0,
      "Custom: equity MT5 indisponibil -> capital 0 (inainte: $1000 orb)")
sg._mt5_exec = FakeMt5(FX, 206.09)
check(sg._session_capital({"account_fraction": None}, Log()) == 0.0, "Custom: fara fractie -> 0 (inainte: $1000)")
check(sg._session_capital({"fixed_lots_enabled": True, "fixed_lots": 0.05}, Log()) == 0.0,
      "Custom lot fix: capitalul nu se foloseste (fara avertisment fals)")
check(sg._snap_lots_to_broker(FX, 0.5) == 0.5, "Custom lot fix: 0.5 ramane 0.50")
check(ex.snap_fixed_lots("X", 0.5, 1.1, 1.098)[0] == 0.5, "AI lot fix: 0.5 ramane 0.50 (aceeasi componenta)")
ex.mt5 = FakeMt5(FX, 1e9)
check(ex.calc_lots("X", 1.10000, 1.09999, 1e9, 0.02)[0] == 100.0, "AI dinamic: plafonat la volume_max (inainte: nelimitat)")


class _L:
    msgs = []
    def warning(self, m): self.msgs.append(m)
    def info(self, m): pass


lg = _L()
sg._mt5_exec = FakeMt5(FX, 206.09)
check(sg._place_order({"signal_id": "S1-T", "symbol": "EURUSD", "direction": 1, "entry": 1.1, "sl": 1.09},
                      0.0, 4, 15, lg) is None, "Custom: volum 0 -> ordinul NU se trimite (reincercare la bara urmatoare)")

print("4. Limita de risc pe trade (Setari Globale → risk_cap) — aceeasi pe toate engine-urile")
# EURUSD: SL 100 puncte (0.00100) -> $1 / 0.01 lot; equity $206, limita 2% = $4.12
check(ps.apply_risk_cap(FX, 0.01, 1.101, 1.100, 206, 2.0) == (0.01, None), "risc $1 (0,49%) sub limita -> neschimbat")
lots, why = ps.apply_risk_cap(FX, 0.10, 1.101, 1.100, 206, 2.0)
check(lots == 0.04 and "redus" in why, "lot fix 0.10 ($10) peste 2% -> redus la 0.04 ($4)", (lots, why))
lots, why = ps.apply_risk_cap(IDX, 0.1, 6100, 6000, 206, 2.0)            # 0.1 lot × 100 pct = $10 = 4,9%
check(lots == 0 and "lotul minim" in why, "lot minim peste limita -> 0 (ordinul NU se plaseaza)", (lots, why))
check(ps.apply_risk_cap(IDX, 0.1, 6100, 6000, 206, None) == (0.1, None), "limita oprita -> neschimbat")
check(ps.apply_risk_cap(IDX, 0.1, 6100, 6000, None, 2.0) == (0.1, None), "equity necunoscut -> neschimbat (nu se poate evalua)")

import live.global_guard as GG  # noqa: E402
GG.risk_cap_pct = lambda settings=None: 2.0
sg._mt5_exec = FakeMt5(IDX, 206.09)
lots_c, risk_c, _ = sg._resolve_order_lots("US500", 6100, 6000, 1, 206.09, 0.01, {"account_fraction": 1.0}, Log())
ex.mt5 = FakeMt5(IDX, 206.09)
ex.equity = lambda: 206.09
lots_a, why_a = ex._risk_cap("US500", 0.1, 6100, 6000)
d = de.DailyEngine(mt5_module=FakeMt5(IDX, 206.09))
d.cfg = {"sizing": {"capital_sync_mt5": True, "capital_usd": None, "fraction": 1.0, "risk_pct": 0.01}}
dz = d.virtual_size("US500", {"entry": 6100, "sl": 6000})
check(lots_c == 0 and lots_a == 0 and dz["lots"] == 0,
      "SL de 100 puncte pe US500 (4,9% la lot minim): Custom = AI = Daily -> 0, ordin neplasat", (lots_c, lots_a, dz))
sg._mt5_exec = FakeMt5(FX, 206.09)
lots_c, _, _ = sg._resolve_order_lots("EURUSD", 1.10, 1.098, 1, 206.09 * 0.2, 0.01, {"account_fraction": 0.2}, Log())
check(lots_c == 0.01, "risc normal (lot minim, ~1%) -> neafectat de limita", lots_c)

print(f"\nREZULTAT: {PASS} PASS / {FAIL} FAIL")
sys.exit(1 if FAIL else 0)
