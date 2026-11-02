"""
Teste offline pentru modelul de cost / lot per simbol din backtest (strategy/costs.py, engine/portfolio.py) — fix-ul
XRPUSD (contract nou: 1 lot = 1 XRP, lot minim 100, pas 1) fara nicio schimbare pentru forex / indici / BTC.
    python scripts/test_backtest_costs.py
Baseline-urile complete: python -m m0.selftest (S1 280) · session2_backtest.py (1254) · session3_backtest.py (731).
"""
import os
import sys

import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from strategy import costs as K  # noqa: E402
from strategy.signals import pip_size  # noqa: E402
from engine.simulator import simulate_trade  # noqa: E402

FAIL = 0


def check(name, cond, info=None):
    global FAIL
    print(("  OK  " if cond else "  FAIL ") + name + ("" if cond or info is None else f"  -> {info}"))
    if not cond:
        FAIL += 1


print("1. Forex / indici / BTC: formula de lot IDENTICA cu cea veche (baseline-uri neschimbate)")
rng = np.random.default_rng(7)
raws = rng.uniform(0, 5, 20000)
for sym in ("EURUSD", "USDJPY", "US30", "BTCUSD", "XAUUSD"):
    old = np.floor(raws / 0.01) * 0.01
    new = np.array([K.round_lots(sym, r) for r in raws])
    check(f"{sym}: round_lots == np.floor(x / 0.01) * 0.01 (20.000 valori, bit cu bit)", np.array_equal(old, new))
check("lot minim implicit 0.01, comision si levier neschimbate", K.min_lot("EURUSD") == 0.01
      and K.commission_per_lot("EURUSD", 7.0) == 7.0 and K.leverage_for("BTCUSD", 30) == 30)

print("2. XRPUSD — contractul actual")
check("pip_size live neatins (0.00001 — buffer-ul SL din live)", pip_size("XRPUSD") == 0.00001)
check("valoarea pip-ului: 0.00001 USD pentru 1 lot (1 XRP)", K.pip_value_usd("XRPUSD", 1.25) == 0.00001)
check("lot minim 100, pas 1 (floor)", K.min_lot("XRPUSD") == 100 and K.round_lots("XRPUSD", 1666.9) == 1666.0)
check("fara comision forex pe lot (Standard)", K.commission_per_lot("XRPUSD", 7.0) == 0.0)
check("levier 1:2 → marja la 100 XRP @ 1,25 ≈ 62$", abs(K.notional_usd("XRPUSD", 1.25, 100) / K.leverage_for("XRPUSD", 30) - 62.5) < 1e-9)
check("swap ~0,0007 $ / XRP / noapte (nu 8 $ / lot implicit)", abs(K.swap_cost("XRPUSD", "2026-11-02 10:00", "2026-11-03 10:00", 1000) - 0.7) < 1e-9)
# un trade XRPUSD complet, ca in motor: risc 10$, SL 0.004 → TP 2R; R-ul trebuie sa fie plauzibil
import pandas as pd  # noqa: E402
entry, sl = 1.2500, 1.2460
risk_usd, pip = 10.0, pip_size("XRPUSD")
pv = K.pip_value_usd("XRPUSD", entry)
lots = K.round_lots("XRPUSD", risk_usd / ((entry - sl) / pip * pv))
bars = pd.DataFrame({"time": pd.date_range("2026-11-02 10:00", periods=4, freq="15min"),
                     "open": [1.25, 1.252, 1.256, 1.258], "high": [1.2505, 1.256, 1.259, 1.26],
                     "low": [1.2495, 1.251, 1.255, 1.257], "close": [1.2502, 1.255, 1.258, 1.259]})
p = {"dir": 1, "entry": entry, "sl": sl, "tp": entry + 2 * (entry - sl), "lots": lots, "R": 2.0, "time": bars.time[0],
     "risk_usd": risk_usd}
res = simulate_trade(bars, 1, p, 0.0025, pip, pv, K.commission_per_lot("XRPUSD", 7.0), "XRPUSD")
R = res["pnl_usd"] / risk_usd
check(f"trade la TP 2R cu spread real 0.0025: R plauzibil (≈ 2 − 0,6 = 1,4), nu −7445", 1.2 < R < 1.5, (lots, R))

print(f"\n{'TOATE TESTELE AU TRECUT' if not FAIL else f'{FAIL} TESTE ESUATE'}")
sys.exit(1 if FAIL else 0)
