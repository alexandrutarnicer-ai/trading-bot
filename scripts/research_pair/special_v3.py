"""
Special Engine v3 — relatia GBP / EUR folosita ca INFORMATIE, nu ca hedge (hedge-ul a anulat castigul, vezi
docs/PAIR_HEDGE_RESEARCH.md). Semnalele = exact Custom Engine (pair_hedge.gen_fills); un singur picior (piata de semnal),
SL −1R / TP 2R, vineri 20:00, o pozitie odata, simulare M1 (pair_hedge.sim mode="solo").

  base     — semnalul singur (referinta)
  confirm  — semnal pe X doar daca trendul celeilalte piete (close vs EMA200 pe TF-ul de trend) e in ACEEASI directie
  relstr   — semnal pe X doar daca X a fost mai puternic decat cealalta pe ultimele N bare de intrare
             (randament X − randament Y, in directia semnalului, > 0)
  relstr_x — ca relstr, dar cerut si sa fie peste mediana absoluta (forta relativa clara)
Rulare: python scripts/research_pair/special_v3.py
"""
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pair_hedge as H  # noqa: E402
from adapters.csv_source import CsvDataSource  # noqa: E402
from strategy.indicators import ema  # noqa: E402
from m0.robustness import evaluate_trades  # noqa: E402

N_RS = 20


def feats(sig, etf, ttf):
    src = CsvDataSource(H.DATA)
    oth = H.OTHER[sig]
    tr_o = src.load_bars(oth, ttf)
    tr_o["trend"] = np.sign(tr_o["close"] - ema(tr_o["close"], 200))
    en_s, en_o = src.load_bars(sig, etf), src.load_bars(oth, etf)
    rs = pd.merge_asof(en_s[["time", "close"]], en_o[["time", "close"]], on="time", suffixes=("_s", "_o"))
    rs["rs"] = np.log(rs["close_s"]).diff(N_RS) - np.log(rs["close_o"]).diff(N_RS)
    # valori cunoscute la deschiderea barei de umplere = bara anterioara (shift 1)
    t_o = pd.Series(tr_o["trend"].shift(1).values, index=tr_o["time"])
    r_s = pd.Series(rs["rs"].shift(1).values, index=rs["time"])
    return t_o, r_s


def main():
    m = H.load_m1()
    res = {}
    for sig in ("GBPUSD", "EURUSD"):
        for etf, ttf in H.TFS[1:]:              # M15+M30 si M30+H1 (M1+M5 negativ pe tot, dominat de costuri)
            key = f"{sig}_{etf}+{ttf}"
            fills, _ = H.gen_fills(sig, etf, ttf)
            t_o, r_s = feats(sig, etf, ttf)
            for f in fills:
                bt = pd.Timestamp(f["bar_time"])
                f["oth_trend"] = t_o.asof(bt)
                f["rs"] = r_s.asof(bt) * f["dir"]
            med = float(np.nanmedian(np.abs([f["rs"] for f in fills])))
            sets = {"base": fills,
                    "confirm": [f for f in fills if f["oth_trend"] == f["dir"]],
                    "relstr": [f for f in fills if f["rs"] > 0],
                    "relstr_x": [f for f in fills if f["rs"] > med]}
            res[key] = {}
            for name, fs in sets.items():
                rows = H.sim(m, fs, sig, lambda t: 1.0, H.TF_MIN[etf], "solo")
                s = H.summarize(rows)
                res[key][name] = s
                print(f"{key} {name:8} n={s.get('n')} /sapt={s.get('per_week')} exp={s.get('exp_R')} "
                      f"tot={s.get('total_R')} DD={s.get('max_dd_R')} train={s.get('train_exp')} "
                      f"test={s.get('test_exp')} folds+={s.get('frac_folds_pos')} {s.get('verdict')}", flush=True)
    json.dump(res, open(os.path.join(H.DATA, "special_v3.json"), "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
