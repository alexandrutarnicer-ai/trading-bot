"""
Portofoliul ORB construit CINSTIT din orb_trades.csv (varianta per piata aleasa DOAR pe train, intraday_orb.py):
  - perioada comuna tuturor pietelor (fara luni in care exista doar o piata)
  - P_train: pietele cu train > 0 (selectie fara sa ne uitam la test)
  - stres: costuri duble (+1 × costul mediu estimat per trade inca o data)
  - risc pe trade, luni pozitive, luni >= 2%, cea mai slaba luna, DD % — pe randamente lunare NECOMPUSE
  - corelatia lunara intre piete
"""
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import common as C  # noqa: E402

res = json.load(open(os.path.join(C.OUT, "intraday_orb.json")))
t = pd.read_csv(os.path.join(C.OUT, "orb_trades.csv"), parse_dates=["entry_t", "exit_t"])
start = t.groupby("sym")["entry_t"].min().max()
t = t[t.entry_t >= start]
print("perioada comuna de la", start.date(), "→", t.entry_t.max().date())
train_pos = [s for s, r in res.items() if not s.startswith("_") and r.get("select_train", -1) > 0]
print("piete cu train > 0:", train_pos)


def monthly(df, risk):
    m = df.groupby(df.exit_t.dt.to_period("M"))["R"].sum()
    m = m.reindex(pd.period_range(m.index.min(), m.index.max(), freq="M"), fill_value=0) * risk
    eq = m.cumsum()
    return {"luna_medie_%": round(m.mean(), 2), "luni_poz_%": round((m > 0).mean() * 100, 1),
            "luni_>=2%_%": round((m >= 2).mean() * 100, 1), "luni_2-5%_%": round(((m >= 2) & (m <= 5)).mean() * 100, 1),
            "cea_mai_slaba_%": round(m.min(), 1), "DD_max_%": round(float((eq - eq.cummax()).min()), 1),
            "luni": len(m), "ani_poz": f"{int((m.groupby(m.index.year).sum() > 0).sum())}/{m.index.year.nunique()}"}


out = {}
for name, syms in (("toate_train_pozitiv", train_pos),
                   ("fara_GBPUSD_US30_AUS200", [s for s in train_pos if s not in ("GBPUSD", "US30", "AUS200")]),
                   ("indici_US_doar_USTEC", [s for s in train_pos if s not in ("US500", "US30")])):
    d = t[t.sym.isin(syms)].copy()
    rep = C.report(d.to_dict("records"), label=f"P {name}")
    print(C.fmt(rep))
    # stres: costuri duble — costul mediu per trade in R ~ (spread+slip)/risc; aproximat cu 2× diferenta dintre
    # rezultatul cu costuri si fara: nu avem R brut, deci scadem inca o data costul estimat = 0.05R / trade (indici)
    d2 = d.assign(R=d.R - 0.05)
    rep2 = C.report(d2.to_dict("records"), label=f"P {name} STRES −0,05R/trade")
    print(C.fmt(rep2))
    per = {}
    for risk in (0.25, 0.5, 0.75, 1.0):
        per[risk] = monthly(d, risk)
        print(f"   risc {risk}%/trade:", per[risk])
    out[name] = {"syms": syms, "report": rep, "stress": rep2, "by_risk": per,
                 "by_year": rep.get("by_year")}
    mm = d.pivot_table(index=d.exit_t.dt.to_period("M"), columns="sym", values="R", aggfunc="sum").fillna(0)
    print("   corelatie lunara medie intre piete:", round(float(mm.corr().values[np.triu_indices(len(mm.columns), 1)].mean()), 2))
    print("   pe ani (R):", rep.get("by_year"))
json.dump(out, open(os.path.join(C.OUT, "orb_portfolio.json"), "w"), indent=1, default=str)
