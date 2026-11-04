"""Filtru Crabel (NR4 / NR7 = range-ul zilei anterioare e cel mai mic din ultimele 4 / 7 zile) aplicat UNIVERSAL pe toate
componentele ORB + NOISE (fara selectie pe componenta). Range-ul zilnic din D1 MT5 (zi server ≈ zi de bursa pt Europa/US)."""
import os, sys, json
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C
from walkforward import load, walk, monthly_pct
t = load()
flags = {}
for s in t.sym.unique():
    d = C.fetch(s, "D1", 3000).copy()
    d["rng"] = d.high - d.low
    d["nr4"] = d.rng <= d.rng.rolling(4).min()
    d["nr7"] = d.rng <= d.rng.rolling(7).min()
    d["wide"] = d.rng >= d.rng.rolling(20).median() * 1.5
    d["day"] = d.time.dt.normalize()
    # pentru ziua de tranzactionare X folosim bara D1 ANTERIOARA (deja inchisa)
    d[["nr4", "nr7", "wide"]] = d[["nr4", "nr7", "wide"]].shift(1)
    flags[s] = d.set_index("day")[["nr4", "nr7", "wide"]]
t["day"] = t.entry_t.dt.normalize()
parts = []
for s, g in t.groupby("sym"):
    f = flags[s].reindex(g["day"]).reset_index(drop=True)
    parts.append(pd.concat([g.reset_index(drop=True), f], axis=1))
t = pd.concat(parts)
t = t[t.entry_t >= "2015-03-01"].dropna(subset=["nr4"])
res = {}
for col in ("nr4", "nr7", "wide"):
    a, b = t[t[col] == True], t[t[col] == False]
    # cate componente se imbunatatesc
    g = t.groupby(["comp", col])["R"].mean().unstack()
    better = float((g[True] > g[False]).mean()) if True in g and False in g else None
    res[col] = {"n_on": len(a), "R_on": round(a.R.mean(), 4), "n_off": len(b), "R_off": round(b.R.mean(), 4),
                "componente_imbunatatite": round(better, 2) if better is not None else None}
    print(col, res[col], flush=True)
# walk-forward cu filtrul cel mai sustinut, regula centrala
for col in ("nr4", "nr7"):
    tf = t[t[col] == True][["comp", "sym", "entry_t", "exit_t", "R"]]
    for lb, tm, mn in ((24, 2.0, 60), (36, 1.5, 60)):
        oos, log = walk(tf, lb, tm, min_n=mn)
        rep = C.report(oos.to_dict("records"), label=f"WF+{col} lb{lb} t{tm}")
        print(C.fmt(rep)); print("    risc 0,5%:", monthly_pct(oos, 0.5) if len(oos) else None, flush=True)
        res[f"wf_{col}_lb{lb}_t{tm}"] = rep
json.dump(res, open(os.path.join(C.OUT, "crabel_filter.json"), "w"), indent=1, default=str)
# combinat: fara zile dupa o zi foarte larga (efect cvasi-universal) ; si NR4 + fara-larg
for name, mask in (("no_wide", t["wide"] == False), ("nr4_or_not_wide", (t["nr4"] == True) | (t["wide"] == False))):
    tf = t[mask][["comp", "sym", "entry_t", "exit_t", "R"]]
    for lb, tm in ((24, 2.0), (36, 1.5)):
        oos, log = walk(tf, lb, tm)
        rep = C.report(oos.to_dict("records"), label=f"WF+{name} lb{lb} t{tm}")
        print(C.fmt(rep)); print("    risc 0,5%:", monthly_pct(oos, 0.5) if len(oos) else None, flush=True)
        for r_ in (1.0, 1.5):
            print(f"    risc {r_}%:", monthly_pct(oos, r_), flush=True)
