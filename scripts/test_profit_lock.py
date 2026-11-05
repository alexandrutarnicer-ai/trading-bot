"""Teste profit_lock (Special Take Profit Mode) — offline, fara MT5.
Rulare: python scripts/test_profit_lock.py"""
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import numpy as np                      # noqa: E402
import pandas as pd                     # noqa: E402
import profit_lock as PL                # noqa: E402

N_OK = N_FAIL = 0


def check(name, cond, detail=""):
    global N_OK, N_FAIL
    if cond:
        N_OK += 1
    else:
        N_FAIL += 1
        print(f"  FAIL {name} {detail}")


ON = {"enabled": True, "mode": "special", "tp_extension_R": 0.10, "sl_offset_R": 0.10, "step_R": 0.50}

print("1. config")
check("lipsa → oprit", PL.sanitize(None)["enabled"] is False)
check("corupt → implicit", PL.sanitize({"step_R": "x", "mode": "zzz"})["step_R"] == 0.5)
check("clamp", PL.sanitize({"sl_offset_R": 9})["sl_offset_R"] == 1.0)
check("TP initial 2→2,1", abs(PL.initial_tp_R(2, ON) - 2.1) < 1e-12)
check("TP initial 3→3,1 / 4→4,1", abs(PL.initial_tp_R(3, ON) - 3.1) < 1e-12 and abs(PL.initial_tp_R(4, ON) - 4.1) < 1e-12)
check("TP initial oprit = rr", PL.initial_tp_R(2, {"enabled": False}) == 2)

print("2. treptele din exemplul userului (RR 1:2)")
for peak, sl, tp in ((2.0, 1.9, 2.6), (2.49, 1.9, 2.6), (2.5, 2.4, 3.1), (3.0, 2.9, 3.6)):
    lv = PL.levels(2.0, peak, ON)
    check(f"varf {peak}", lv and abs(lv["sl_R"] - sl) < 1e-9 and abs(lv["tp_R"] - tp) < 1e-9, str(lv))
check("sub 2R → neactivat", PL.levels(2.0, 1.99, ON) is None)
lv = PL.levels(3.0, 4.0, {**ON, "step_R": 1.0})
check("RR 3, pas 1: la 4R → SL 3,9 TP 5,1", abs(lv["sl_R"] - 3.9) < 1e-9 and abs(lv["tp_R"] - 5.1) < 1e-9, str(lv))
check("prag urmator < TP (TP atins doar prin gap)", all(
    PL.levels(2.0, p, ON)["threshold_R"] + 0.5 < PL.levels(2.0, p, ON)["tp_R"] for p in np.arange(2, 8, 0.07)))
lv = PL.levels(2.0, 3.7, {"enabled": True, "mode": "atr_trail", "atr_mult": 2.0, "sl_offset_R": 0.1}, atr_R=0.4)
check("atr_trail: max(rr−0,1 ; varf − 2×ATR)", abs(lv["sl_R"] - 2.9) < 1e-9 and lv["tp_R"] is None, str(lv))

print("3. pret: BUY / SELL, tick, monoton")
check("BUY 1,9R", abs(PL.r_to_price(1.1000, 1, 0.0010, 1.9) - 1.1019) < 1e-12)
check("SELL 1,9R", abs(PL.r_to_price(1.1000, -1, 0.0010, 1.9) - 1.0981) < 1e-12)
check("tick SL BUY in jos", PL.round_to_tick(1.101937, 0.00001, 1, "sl") == 1.10193)
check("tick SL SELL in sus", PL.round_to_tick(1.098063, 0.00001, -1, "sl") == 1.09807)
check("tick TP BUY in sus", PL.round_to_tick(1.102601, 0.00001, 1, "tp") == 1.10261)
check("tick indice 0,1", PL.round_to_tick(25432.37, 0.1, 1, "sl") == 25432.3)
check("monoton BUY", PL.improves(1, 1.1010, 1.1019) and not PL.improves(1, 1.1019, 1.1010))
check("monoton SELL", PL.improves(-1, 1.0990, 1.0981) and not PL.improves(-1, 1.0981, 1.0990))

print("4. plan_modification (live)")
base = dict(entry=1.1000, risk=0.0010, rr=2.0, cfg=ON, point=0.00001, tick=0.00001)
p = PL.plan_modification(side=1, peak_price=1.1021, current_sl=1.0990, current_tp=1.1021, bid=1.1020, ask=1.1021, **base)
check("BUY la 2,1R → modify SL 1,1019 / TP 1,1026", p["action"] == "modify" and p["sl"] == 1.1019 and p["tp"] == 1.1026, str(p))
p2 = PL.plan_modification(side=1, peak_price=1.1021, current_sl=1.1019, current_tp=1.1026, bid=1.1020, ask=1.1021, **base)
check("acelasi nivel → nimic (fara dubluri)", p2["action"] == "none", str(p2))
p3 = PL.plan_modification(side=1, peak_price=1.1021, current_sl=1.1023, current_tp=1.1026, bid=1.1024, ask=1.1025, **base)
check("SL curent mai sus (manual / restart) → nu coboara", p3["action"] == "none", str(p3))
p4 = PL.plan_modification(side=1, peak_price=1.1018, current_sl=1.0990, current_tp=1.1021, bid=1.1017, ask=1.1018, **base)
check("sub prag → nimic", p4["action"] == "none")
p5 = PL.plan_modification(side=-1, peak_price=1.0975, current_sl=1.1010, current_tp=1.0979, bid=1.0974, ask=1.0975, **base)
check("SELL la 2,5R → SL 1,0976", p5["action"] == "modify" and p5["sl"] == 1.0976 and p5["tp"] == 1.0969, str(p5))
p6 = PL.plan_modification(side=-1, peak_price=1.0975, current_sl=1.1010, current_tp=1.0979, bid=1.0980, ask=1.0981, **base)
check("SELL: pretul a revenit peste nivel → close", p6["action"] == "close", str(p6))
p7 = PL.plan_modification(side=1, peak_price=1.1021, current_sl=1.0990, current_tp=1.1021, bid=1.10195, ask=1.1020,
                          stops_level=10, **base)
check("prea aproape de pret (stops_level) → amanat", p7["action"] == "none" and "amânat" in p7["reason"], str(p7))
p8 = PL.plan_modification(side=1, peak_price=1.1021, current_sl=1.0990, current_tp=1.1050, bid=1.1020, ask=1.1021, **base)
check("TP nu se apropie de pret", p8["tp"] == 1.1050, str(p8))
check("oprit → nimic", PL.plan_modification(side=1, peak_price=1.2, current_sl=1.099, current_tp=1.1021, bid=1.12,
                                            ask=1.12, **{**base, "cfg": {"enabled": False}})["action"] == "none")

print("5. simulare pe bare")
def path(Rs):           # traseu in R (BUY, entry 0, risk 1): o, h, l, c
    o = np.array([r[0] for r in Rs]); h = np.array([r[1] for r in Rs]); l = np.array([r[2] for r in Rs]); c = np.array([r[3] for r in Rs])
    return o, h, l, c
up_down = path([(0, .5, -.2, .4), (.4, 1.5, .3, 1.4), (1.4, 2.2, 1.3, 2.1), (2.1, 3.2, 2.0, 3.1), (3.1, 3.1, 2.0, 2.2)])
kw = dict(side=1, entry=0.0, risk=1.0, sl_R=-1.0, tp_R=2.0, rr=2.0, start=0, end=5)
std = PL.simulate_path(*up_down, cfg=None, **kw)
spc = PL.simulate_path(*up_down, cfg=ON, **kw)
check("standard → TP 2R", std["why"] == "TP" and std["R"] == 2.0, str(std))
check("special → blocat la 2,9R (varf 3,2)", spc["why"] == "LOCK" and abs(spc["R"] - 2.9) < 1e-9, str(spc))
gap = path([(0, .5, -.2, .4), (2.6, 2.7, 2.5, 2.6)])
check("gap peste TP initial → iese la open", PL.simulate_path(*gap, cfg=None, **{**kw, "end": 2})["R"] == 2.6)
same_bar = path([(0, 2.3, -1.2, 0)])
check("SL si TP in aceeasi bara → SL (conservator)", PL.simulate_path(*same_bar, cfg=ON, **{**kw, "end": 1})["R"] == -1.0)
forced = path([(0, .5, -.2, .4), (.4, .8, .3, .7)])
check("iesire fortata la close", PL.simulate_path(*forced, cfg=ON, **{**kw, "end": 2})["R"] == 0.7)

print("6. oprit = identic cu engine/simulator.simulate_trade (cu si fara break-even), 400 trasee aleatoare")
from engine.simulator import simulate_trade   # noqa: E402
rng = random.Random(7)
mism = 0
for k in range(400):
    n = 120
    steps = np.cumsum([rng.gauss(0, 0.35) for _ in range(n)])
    o = np.r_[0, steps[:-1]]; c = steps
    h = np.maximum(o, c) + np.abs([rng.gauss(0, .2) for _ in range(n)])
    l = np.minimum(o, c) - np.abs([rng.gauss(0, .2) for _ in range(n)])
    d = 1 if k % 2 == 0 else -1
    be = None if k % 3 == 0 else {"enabled": True, "phase2_enabled": k % 4 != 1, "trigger_pct": 80, "lock1_pct": 30,
                                  "lock2_pct": 50, "phase2_zone_pct": 40}
    df = pd.DataFrame({"time": pd.date_range("2026-01-05", periods=n, freq="15min"), "open": o * d, "high": np.where(d == 1, h, -l),
                       "low": np.where(d == 1, l, -h), "close": c * d})
    p = {"dir": d, "entry": 0.0, "sl": -1.0 * d, "tp": 2.0 * d, "lots": 1, "R": 2, "time": df.time[0], "risk_usd": 1}
    ref = simulate_trade(df, 0, p, 0.0, 1.0, 1.0, 0.0, "X", be_cfg=be)
    got = PL.simulate_path(df.open.to_numpy(), df.high.to_numpy(), df.low.to_numpy(), df.close.to_numpy(), side=d,
                           entry=0.0, risk=1.0, sl_R=-1.0, tp_R=2.0, rr=2.0, cfg=None, start=0, end=min(400, n), be=be)
    ref_R = (ref["pnl_usd"]) * 1.0
    if ref["outcome"] == "timeout":
        continue
    if abs(ref_R - got["R"]) > 1e-9 or ref["exit_j"] != got["exit_i"]:
        mism += 1
check("echivalenta cu simulatorul Custom", mism == 0, f"{mism} nepotriviri")

print(f"\n{N_OK} OK, {N_FAIL} esuate")
sys.exit(1 if N_FAIL else 0)
