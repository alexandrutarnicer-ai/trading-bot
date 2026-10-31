"""EURUSD la deschiderea europeana (M5, costuri reale, verdict M0).
Variante de start: Frankfurt 08:00 (Berlin) = 09:00 RO; Londra 08:00 (London) = 10:00 RO.
Iesire: TP 2R/3R, inchidere la 12:00 RO-echivalent (sfarsitul ferestrei dimineata) sau la 17:00 Londra."""
import sys, itertools
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
import orb_m5 as O
from m0.robustness import evaluate_trades

rows = []
for label, tz, om, closes in [("Frankfurt 08:00 (09:00 RO)", "Europe/Berlin", 480, {"11:55 RO": 655, "17:55 RO": 1015}),
                              ("Londra 08:00 (10:00 RO)", "Europe/London", 480, {"12:55 RO": 595, "18:55 RO": 955})]:
    for cname, cm in closes.items():
        d = O.load("EURUSD", tz, om, cm)
        for or_min, mode, rr in itertools.product([5, 15, 30], ["brk", "dir"], [2.0, 3.0, None]):
            t = O.run(d, "EURUSD", or_min, mode, rr)
            if len(t) < 30:
                continue
            m = evaluate_trades(t, split_time=O.SPLIT, n_boot=500)
            yrs = t.groupby(t.entry_t.dt.year).R.sum()
            rows.append(dict(start=label, close=cname, orb=f"{or_min}m", mode=mode, exit=f"{rr:g}R" if rr else "EOD",
                             n=m["n"], exp=round(m["expectancy"], 3), train=round(m["train_exp"], 3),
                             test=round(m["test_exp"], 3), folds=round(m["frac_positive"], 2),
                             yrs=f"{(yrs > 0).sum()}/{len(yrs)}", verdict=m["verdict"]))
r = pd.DataFrame(rows).sort_values("exp", ascending=False)
r.to_csv(O.ROOT / "data/research_daily/orb_m5_eurusd_eu.csv", index=False)
pd.set_option("display.width", 220)
print(f"Variante: {len(r)} | verdicte: {r.verdict.value_counts().to_dict()}")
print(r.head(12).to_string(index=False))
