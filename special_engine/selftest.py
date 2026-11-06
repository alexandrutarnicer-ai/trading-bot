"""Special Engine — selftest (offline; MT5 simulat pe istoricul din data/research_*; fara date → sectiunile sar).
Rulare: python -m special_engine.selftest"""
from __future__ import annotations

import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from types import SimpleNamespace

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from special_engine import data as D  # noqa: E402
from special_engine import engine as E  # noqa: E402
from special_engine.config import COSTS, NOISE_MARKETS, ORB_MARKETS, sanitize  # noqa: E402
from special_engine.strategies import nr_flag  # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  OK   {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name} {str(detail)[:300]}")


def load_hist(sym):
    for p in (os.path.join(ROOT, "data", "research_daily", f"{sym}_M5_server.csv"),
              os.path.join(ROOT, "data", "research_special", f"{sym}_M5.csv")):
        if os.path.exists(p):
            return pd.read_csv(p, parse_dates=["time"])
    return None


POINT = {"DE40": 0.01, "USTEC": 0.01, "US500": 0.01, "XAUUSD": 0.01}   # MT5 ICMarketsEU (symbol_info.point)


def t_config_and_safety():
    print("1. siguranta: DOAR shadow, zero ordine in pachet")
    check("mode fortat shadow", sanitize({"mode": "execute"})["mode"] == "shadow")
    check("config corupt → implicit (A: 36 luni, t 1,5, NR4; B: USTEC)",
          sanitize("x")["strategy_a"]["lookback_months"] == 36 and sanitize(None)["strategy_b"]["symbol"] == "USTEC")
    pkg = os.path.join(ROOT, "special_engine")
    bad = [f for f in os.listdir(pkg) if f.endswith(".py") and f != "selftest.py"
           and re.search(r"order_send|TRADE_ACTION_DEAL|TRADE_ACTION_PENDING|TRADE_ACTION_SLTP", open(os.path.join(pkg, f), encoding="utf-8").read())]
    check("niciun order_send / TRADE_ACTION in special_engine/", not bad, bad)


def t_equivalence():
    print("2. echivalenta cu cercetarea (aceleasi functii, aceleasi date)")
    ro = os.path.join(ROOT, "data", "research_special", "orb_trades_all.csv")
    rn = os.path.join(ROOT, "data", "research_special", "noise_trades_all.csv")
    if not (os.path.exists(ro) and os.path.exists(rn)):
        print("  (sarit: fara datele de cercetare)")
        return
    ref_o = pd.read_csv(ro, parse_dates=["entry_t"])
    for sym in ("DE40", "XAUUSD"):
        d = load_hist(sym)
        if d is None:
            continue
        tz, op, last = ORB_MARKETS[sym]
        mine = pd.DataFrame(D.orb_history(d, sym, tz, op, last, *COSTS[sym], POINT[sym]))
        r = ref_o[ref_o.sym == sym]
        a = mine.groupby("comp").R.agg(["count", "sum"]).round(6)
        b = r.assign(comp="ORB:" + r.sym + ":" + r["var"]).groupby("comp").R.agg(["count", "sum"]).round(6)
        check(f"ORB {sym}: 6 variante identice (n, ΣR)", a.equals(b), a.join(b, rsuffix="_ref") if not a.equals(b) else "")
    ref_n = pd.read_csv(rn, parse_dates=["entry_t"])
    d = load_hist("USTEC")
    if d is not None:
        tz, op, cl = NOISE_MARKETS["USTEC"]
        mine = pd.DataFrame(D.noise_history(d, "USTEC", tz, op, cl, 1.75, POINT["USTEC"]))  # costul din rularea de cercetare
        r = ref_n[ref_n.sym == "USTEC"].reset_index(drop=True)
        same = len(mine) == len(r) and (mine.entry_t.values == r.entry_t.values).all() and np.allclose(mine.R, r.R, atol=1e-9)
        check(f"NOISE USTEC: {len(mine)} trade-uri identice (intrare + R)", same)


def t_selection():
    print("3. selectia trimestriala: fara look-ahead, reguli")
    rng = np.random.default_rng(3)
    rows = []
    for comp, mu in (("ORB:AAA:5/breakout", 0.3), ("ORB:AAA:15/direction", 0.25), ("ORB:BBB:5/breakout", 0.0),
                     ("NOISE:CCC", 0.2), ("ORB:DDD:5/breakout", 0.4)):
        for t in pd.date_range("2022-01-03", "2026-12-28", freq="2D"):
            rows.append({"comp": comp, "sym": comp.split(":")[1], "entry_t": t, "R": rng.normal(mu, 1.0)})
    df = pd.DataFrame(rows)
    a = sanitize(None)["strategy_a"]
    q = pd.Timestamp("2025-07-01")
    comps, tab = D.select(df, q, a)
    check("o singura componenta pe piata (AAA: cea cu t maxim)", sum(c.startswith("ORB:AAA") for c in comps) == 1, comps)
    check("componenta fara edge (BBB, media 0) exclusa", "ORB:BBB:5/breakout" not in comps, comps)
    df2 = df.copy()
    df2.loc[df2.entry_t >= q, "R"] = 99.0                     # viitorul „perfect” nu trebuie sa conteze
    check("trade-urile de dupa inceputul trimestrului NU influenteaza selectia", D.select(df2, q, a)[0] == comps)
    d1 = pd.DataFrame({"time": pd.date_range("2026-11-02", periods=5, freq="D"), "high": [10, 9, 8, 7.5, 9],
                       "low": [0, 1, 2, 3, 0]})
    check("NR4: range-ul de ieri (4,5) = minimul ultimelor 4 → True", nr_flag(d1, pd.Timestamp("2026-11-06"), 4) is True)
    check("NR4: zi dupa o zi larga → False", nr_flag(d1, pd.Timestamp("2026-11-07"), 4) is False)


class FakeMt5:
    TIMEFRAME_M5, TIMEFRAME_D1 = 5, 16408

    def __init__(self, m5: dict, d1: dict):
        self.m5, self.d1, self.now_server = m5, d1, None
        self.sent = []

    def initialize(self):
        return True

    def symbol_select(self, s, on):
        return s in self.m5

    def symbol_info(self, s):
        return SimpleNamespace(point=POINT[s])

    def account_info(self):
        return SimpleNamespace(equity=1000.0)

    def copy_rates_from_pos(self, s, tf, start, n):
        src = self.m5[s] if tf == self.TIMEFRAME_M5 else self.d1[s]
        x = src[src.time <= self.now_server].tail(n)
        arr = np.zeros(len(x), dtype=[("time", "i8"), ("open", "f8"), ("high", "f8"), ("low", "f8"), ("close", "f8"),
                                      ("tick_volume", "i8"), ("spread", "i8")])
        arr["time"] = ((x.time - pd.Timestamp("1970-01-01")) // pd.Timedelta(seconds=1)).to_numpy()
        for k in ("open", "high", "low", "close", "tick_volume", "spread"):
            arr[k] = x[k].to_numpy()
        return arr

    def order_send(self, req):                     # nu trebuie apelat niciodata
        self.sent.append(req)


def t_live_equals_backtest():
    print("4. engine-ul LIVE reluat pe zile istorice = backtestul (MT5 simulat)")
    d = load_hist("USTEC")
    if d is None:
        print("  (sarit: fara istoric USTEC)")
        return
    d1 = d.set_index("time").resample("1D").agg({"open": "first", "high": "max", "low": "min", "close": "last",
                                                "tick_volume": "sum", "spread": "max"}).dropna().reset_index()
    tmp = tempfile.mkdtemp()
    for n in ("STATUS_FILE", "STATE_FILE", "TRADES_FILE", "SELECTION_FILE"):
        setattr(E, n, os.path.join(tmp, os.path.basename(getattr(E, n))))
    E._notify = lambda cfg, text: None
    E.load_config = lambda: {**sanitize(None), "notify_telegram": False}
    fake = FakeMt5({"USTEC": d}, {"USTEC": d1})
    eng = E.SpecialEngine(mt5_module=fake)
    eng.selection = {"quarter": "x", "components": []}
    eng.ensure_selection = lambda now: None
    tz, op, cl = NOISE_MARKETS["USTEC"]
    ref = pd.DataFrame(D.noise_history(d, "USTEC", tz, op, cl, sum(COSTS["USTEC"]), POINT["USTEC"]))
    ref["day"] = ref.entry_t.dt.normalize()
    days = sorted(ref.day.unique())[-25:]
    bad = 0
    for dd in days:
        day = pd.Timestamp(dd)
        # ora 16:10 NY = sesiune incheiata; server = NY + 7h
        now_ny = day + pd.Timedelta(hours=16, minutes=10)
        fake.now_server = now_ny + pd.Timedelta(hours=7)
        now_utc = now_ny.tz_localize("America/New_York").tz_convert("UTC").to_pydatetime()
        st = eng.iteration(now_utc)
        live = [c for c in st["components"] if c["strategy"] == "B"][0]
        want = ref[ref.day == day]
        if live.get("trades_today") != len(want) or abs((live.get("R_today") or 0) - round(want.R.sum(), 3)) > 1e-6:
            bad += 1
    check(f"B pe ultimele {len(days)} zile cu trade-uri: aceleasi trade-uri si R ca backtestul", bad == 0, f"{bad} zile diferite")
    n1 = len(E.load_trades())
    eng.iteration(now_utc)
    eng2 = E.SpecialEngine(mt5_module=fake)          # „restart”
    eng2.selection, eng2.ensure_selection = eng.selection, (lambda now: None)
    eng2.iteration(now_utc)
    check("restart / re-iteratie: fara dubluri in jurnal", len(E.load_trades()) == n1, (n1, len(E.load_trades())))
    check("zero ordine trimise", not fake.sent)
    # bara IN FORMARE ignorata: la 10:02 NY nu exista inca bara inchisa 10:00 → fara intrare la 10:00
    day = pd.Timestamp(days[-1])
    fake.now_server = day + pd.Timedelta(hours=10, minutes=2) + pd.Timedelta(hours=7)
    eng3 = E.SpecialEngine(mt5_module=fake)
    b = eng3._today_bars("USTEC", tz, op, cl, False, (day + pd.Timedelta(hours=10, minutes=2)).tz_localize(tz).tz_convert("UTC").to_pydatetime())
    check("doar bare INCHISE (ultima bara = 09:55 la ora 10:02)", len(b) and int(b.mins.iloc[-1]) == 9 * 60 + 55,
          b.mins.tail(2).tolist() if len(b) else "gol")


if __name__ == "__main__":
    t_config_and_safety()
    t_equivalence()
    t_selection()
    t_live_equals_backtest()
    print(f"\n{PASS} OK, {FAIL} FAIL")
    sys.exit(1 if FAIL else 0)
