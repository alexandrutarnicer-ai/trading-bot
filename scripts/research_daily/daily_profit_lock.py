"""
Daily Engine — Profit Lock (2026-11-12). DOAR backtest; aceeasi functie ca engine-ul (evaluate_day_multi, plock=).

Regula: cand trade-ul atinge +Trigger R, SL-ul se muta la +Lock R (de la bara URMATOARE — ordinea din bara nu se
cunoaste, deci conservator); o bara care deschide dincolo de SL-ul blocat se umple la open. Fara TP (ca acum),
inchidere la final de fereastra. Configuratia curenta a pietelor (daily_engine/config.json: bursa, interval,
mod, costuri, re-intrari), tot istoricul M5 din data/research_daily/<SIM>_M5_server.csv. Train = primele 70%.
Rezultat: data/research_daily/daily_profit_lock.json + tabel pe ecran.
    python scripts/research_daily/daily_profit_lock.py
"""
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from daily_engine.config import ENTRY_MODES, hm_to_min, load_config  # noqa: E402
from daily_engine.market_tools import server_to_exchange  # noqa: E402
from daily_engine.strategy import evaluate_day_multi  # noqa: E402

DATA = os.path.join(ROOT, "data", "research_daily")
VARIANTS = [("actual (fara)", None), ("3.5 -> 3", (3.5, 3)), ("4.5 -> 4", (4.5, 4)), ("5 -> 4", (5, 4)),
            ("6 -> 5", (6, 5)), ("8 -> 6", (8, 6)), ("10 -> 8", (10, 8))]
POINT = {"DE40": 0.01, "US500": 0.01, "GBPUSD": 0.00001, "US30": 0.01, "XAUUSD": 0.01}


def days_of(m: dict):
    d = pd.read_csv(os.path.join(DATA, f"{m['symbol']}_M5_server.csv"), parse_dates=["time"])
    d["loc"] = server_to_exchange(d["time"], m["tz"])
    d = d.dropna(subset=["loc"])
    d = d[d["loc"].dt.weekday < 5]
    om, lb = hm_to_min(m["open"]), hm_to_min(m["last_bar"])
    d["mins"] = d["loc"].dt.hour * 60 + d["loc"].dt.minute
    d = d[(d.mins >= om) & (d.mins <= lb)]
    d["day"] = d["loc"].dt.normalize()
    n_or = m["or_minutes"] // 5
    for day, g in d.groupby("day", sort=True):
        if g.mins.iloc[0] != om or len(g) < n_or + 6 or g.high.iloc[:n_or].max() - g.low.iloc[:n_or].min() <= 0:
            continue
        yield day, g


def run(m: dict, plock) -> list[dict]:
    pt = POINT.get(m["symbol"], 0.00001)
    rows = []
    for day, g in days_of(m):
        r = evaluate_day_multi(g.open, g.high, g.low, g.close, g.spread.to_numpy(float) * pt, g.mins,
                               open_min=hm_to_min(m["open"]), or_minutes=m["or_minutes"], mode=ENTRY_MODES[m["entry"]],
                               rr=m.get("rr"), slip=m["slip"], comm=m["comm"], day_complete=True,
                               reentry=m.get("reentry"), plock=plock)
        rows += [{"day": day, "k": t.get("k", 0), "R": float(t["R"]), "reason": t["reason"]} for t in r["trades"]]
    return rows


def stats(rows, base=None) -> dict:
    R = np.array([r["R"] for r in rows])
    eq = np.cumsum(R)
    w, ls = R[R > 0], R[R < 0]
    cut = int(0.7 * len(R))
    out = {"n": int(len(R)), "exp_R": round(float(R.mean()), 4), "net_R": round(float(R.sum()), 1),
           "pf": round(float(w.sum() / -ls.sum()), 3) if ls.sum() < 0 else None,
           "win_rate": round(float((R > 0).mean() * 100), 1), "max_dd_R": round(float((eq - np.maximum.accumulate(eq)).min()), 1),
           "train_R": round(float(R[:cut].mean()), 4), "test_R": round(float(R[cut:].mean()), 4),
           "p10": round(float(np.percentile(R, 10)), 2), "p50": round(float(np.percentile(R, 50)), 2),
           "p90": round(float(np.percentile(R, 90)), 2), "max": round(float(R.max()), 1),
           "locks": int(sum(1 for r in rows if r["reason"] == "LOCK"))}
    if base is not None:
        # acelasi trade (zi, index k) cu si fara Profit Lock — cu re-intrari, un lock poate schimba si trade-urile
        # urmatoare din zi; se compara doar perechile existente in ambele variante
        b = {(r["day"], r["k"]): r["R"] for r in base}
        d = np.array([r["R"] - b[(r["day"], r["k"])] for r in rows if (r["day"], r["k"]) in b])
        out["protected_R"] = round(float(d[d > 0].sum()), 1)       # trade-uri care fara lock s-ar fi intors mai jos
        out["given_up_R"] = round(float(d[d < 0].sum()), 1)        # trade-uri inchise mai devreme decat ar fi mers
    return out


def main():
    res = {}
    for m in load_config()["markets"]:
        if not os.path.exists(os.path.join(DATA, f"{m['symbol']}_M5_server.csv")):
            print(f"{m['symbol']}: lipsesc datele de cercetare — sarit")
            continue
        base = run(m, None)
        res[m["symbol"]] = {}
        print(f"\n{m['symbol']} ({m['tz'].split('/')[-1]} {m['or_minutes']}m {m['entry']}, re-intrari "
              f"{'pornite' if (m.get('reentry') or {}).get('enabled') else 'oprite'}) — {len(base)} trade-uri")
        for name, v in VARIANTS:
            rows = base if v is None else run(m, {"enabled": True, "trigger_R": v[0], "lock_R": v[1]})
            st = stats(rows, None if v is None else base)
            res[m["symbol"]][name] = st
            print(f"  {name:14} exp {st['exp_R']:+.4f} net {st['net_R']:+7.1f}R PF {st['pf']} WR {st['win_rate']:4.1f}% "
                  f"DD {st['max_dd_R']:6.1f} train {st['train_R']:+.4f} test {st['test_R']:+.4f} lock {st['locks']:4} "
                  f"protejat {st.get('protected_R', 0):+6.1f}R pierdut {st.get('given_up_R', 0):+6.1f}R")
    with open(os.path.join(DATA, "daily_profit_lock.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1)


if __name__ == "__main__":
    main()
