"""
Propunerea de engine nou — portofoliu intraday ADAPTIV, evaluat strict WALK-FORWARD (out-of-sample la fiecare pas).

Componente candidate (toate intraday, fara nopti → fara swap):
  ORB   : 10 piete × 6 variante (interval 5/15/30 × breakout/direction)  — orb_trades_all.csv
  NOISE : 8 piete, parametrii din lucrare                                — noise_trades.csv
Regula PRE-SPECIFICATA (centrala: lookback 24 luni, t >= 2.0):
  - la inceputul fiecarui TRIMESTRU, pentru fiecare componenta: media R si t-stat pe ultimele `lookback` luni
    (doar trecut), minim 150 trade-uri
  - intra daca t >= t_min SI media >= 0,05R; cel mult 1 componenta pe piata (cea cu t maxim), cel mult 6 in total
  - trimestrul urmator se tranzactioneaza DOAR cu componentele alese → rezultatul trimestrului e out-of-sample
Sensibilitate: lookback {12, 24, 36} × t_min {1.5, 2.0, 2.5} — toate raportate.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import common as C  # noqa: E402


def load():
    o = pd.read_csv(os.path.join(C.OUT, "orb_trades_all.csv"), parse_dates=["entry_t", "exit_t"])
    o["comp"] = "ORB:" + o["sym"] + ":" + o["var"]
    n = pd.read_csv(os.path.join(C.OUT, "noise_trades_all.csv"), parse_dates=["entry_t", "exit_t"])
    n["comp"] = "NOISE:" + n["sym"]
    t = pd.concat([o, n], ignore_index=True)
    return t[["comp", "sym", "entry_t", "exit_t", "R"]].sort_values("entry_t").reset_index(drop=True)


def walk(t, lookback=24, t_min=2.0, min_n=150, min_mean=0.05, max_comp=6):
    q0 = (t.entry_t.min() + pd.DateOffset(months=lookback)).to_period("Q").start_time
    quarters = pd.date_range(q0, t.entry_t.max(), freq="QS")
    picked, log = [], []
    for qs in quarters:
        qe = qs + pd.DateOffset(months=3)
        hist = t[(t.entry_t >= qs - pd.DateOffset(months=lookback)) & (t.entry_t < qs)]
        g = hist.groupby("comp")["R"].agg(["count", "mean", "std"])
        g = g[g["count"] >= min_n]
        g["t"] = g["mean"] / (g["std"] / np.sqrt(g["count"]))
        g = g[(g["t"] >= t_min) & (g["mean"] >= min_mean)].sort_values("t", ascending=False)
        g["sym"] = [c.split(":")[1] for c in g.index]
        sel = g.drop_duplicates("sym").head(max_comp)
        log.append({"quarter": str(qs.date()), "components": list(sel.index)})
        if len(sel):
            picked.append(t[(t.entry_t >= qs) & (t.entry_t < qe) & t.comp.isin(sel.index)])
    oos = pd.concat(picked) if picked else t.iloc[0:0]
    return oos, log


def monthly_pct(df, risk):
    m = df.groupby(df.exit_t.dt.to_period("M"))["R"].sum()
    m = m.reindex(pd.period_range(m.index.min(), m.index.max(), freq="M"), fill_value=0) * risk
    eq = m.cumsum()
    return {"risk_pct": risk, "luna_medie": round(float(m.mean()), 2), "mediana": round(float(m.median()), 2),
            "luni_poz": round(float((m > 0).mean() * 100), 1), "luni_ge2": round(float((m >= 2).mean() * 100), 1),
            "cea_mai_slaba": round(float(m.min()), 1), "DD_max": round(float((eq - eq.cummax()).min()), 1),
            "ani": {int(y): round(float(v), 1) for y, v in m.groupby(m.index.year).sum().items()}}


def main():
    t = load()
    print("componente:", t.comp.nunique(), "| trade-uri:", len(t), "|", t.entry_t.min().date(), "→", t.entry_t.max().date())
    out = {}
    for lb in (12, 24, 36):
        for tm in (1.5, 2.0, 2.5):
            oos, log = walk(t, lb, tm)
            key = f"lb{lb}_t{tm}"
            rep = C.report(oos.to_dict("records"), label=f"WF {key}" + ("  ← REGULA CENTRALA" if (lb, tm) == (24, 2.0) else ""))
            out[key] = {"report": rep, "by_risk": [monthly_pct(oos, r) for r in (0.25, 0.5, 1.0)] if len(oos) else [],
                        "log": log}
            print(C.fmt(rep), flush=True)
            if len(oos):
                print("    risc 0,5%:", monthly_pct(oos, 0.5), flush=True)
    central = out["lb24_t2.0"]
    print("\nComponente alese (regula centrala), pe trimestre:")
    for q in central["log"]:
        print("  ", q["quarter"], q["components"])
    json.dump(out, open(os.path.join(C.OUT, "walkforward.json"), "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
