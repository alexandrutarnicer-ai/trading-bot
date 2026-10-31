"""Comparatie Daily Engine: 4 piete x 2 ferestre (dimineata EU / dupa-amiaza NY), M5, costuri reale, verdict M0.
Dimineata: Frankfurt 08:00 Berlin (09:00 RO) si Londra 08:00 London (10:00 RO); inchidere fortata 16:25 RO
           (inainte de fereastra de dupa-amiaza, ca sa nu se suprapuna).
Dupa-amiaza: New York 09:30 (16:30 RO); inchidere fortata 15:55 NY (22:55 RO).
Grila identica pentru toate: OR {5,15,30} min x {brk, dir} x iesire {2R, 3R, EOD} = 18 variante / fereastra."""
import sys, itertools
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
import orb_m5 as O
from m0.robustness import evaluate_trades

WINDOWS = [  # eticheta, tz bursa, open (min local), close (min local)
    ("dim 09:00 RO (Frankfurt)", "Europe/Berlin", 480, 925),     # 08:00 .. 15:25 Berlin = 16:25 RO
    ("dim 10:00 RO (Londra)",    "Europe/London", 480, 865),     # 08:00 .. 14:25 London = 16:25 RO
    ("dupa-amiaza 16:30 RO (NY)", "America/New_York", 570, 955),
]
rows = []
for sym in ["US500", "EURUSD", "GBPUSD", "GBPAUD"]:
    for label, tz, om, cm in WINDOWS:
        d = O.load(sym, tz, om, cm)
        for or_min, mode, rr in itertools.product([5, 15, 30], ["brk", "dir"], [2.0, 3.0, None]):
            t = O.run(d, sym, or_min, mode, rr)
            if len(t) < 30:
                continue
            m = evaluate_trades(t, split_time=O.SPLIT, n_boot=500)
            yrs = t.groupby(t.entry_t.dt.year).R.sum()
            last2 = t[t.entry_t >= "2025-01-01"].R.mean()
            rows.append(dict(sym=sym, window=label, orb=f"{or_min}m", mode=mode, exit=f"{rr:g}R" if rr else "EOD",
                             n=m["n"], exp=m["expectancy"], train=m["train_exp"], test=m["test_exp"],
                             last2y=last2, folds=m["frac_positive"], p_pos=m["prob_positive"],
                             yrs=f"{(yrs > 0).sum()}/{len(yrs)}", risk_usd=t.risk_usd_minlot.median(),
                             verdict=m["verdict"]))
        print(sym, label, "gata", file=sys.stderr, flush=True)
r = pd.DataFrame(rows)
r.to_csv(O.ROOT / "data/research_daily/orb_compare.csv", index=False)
f = r.copy()
for k in ("exp", "train", "test", "last2y", "folds", "p_pos"):
    f[k] = f[k].astype(float).round(3)
f["risk_usd"] = f.risk_usd.round(2)
f["robust"] = f[["train", "test"]].min(axis=1)
pd.set_option("display.width", 240)
print(f"Variante totale: {len(r)}  | verdicte: {r.verdict.value_counts().to_dict()}\n")
print("=== Cea mai buna varianta per piata x fereastra (dupa min(train,test)) ===")
best = f.sort_values("robust", ascending=False).groupby(["sym", "window"]).head(1)
print(best.sort_values(["window", "robust"], ascending=[True, False]).to_string(index=False))
print("\n=== Numar variante KEEP/OBSERVE per piata x fereastra (din 18) ===")
print(pd.crosstab([r.sym, r.window], r.verdict).to_string())
