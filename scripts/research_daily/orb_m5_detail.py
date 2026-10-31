"""Detaliu US500: rezultate pe ani, sensibilitate la slippage, efectul zilelor cu stiri (NFP/CPI/FOMC aprox.)."""
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
import orb_m5 as O

d = O.load("US500")
base_slip = O.SPEC["US500"]["slip"]
for or_min, mode, rr in [(5, "brk", None), (30, "brk", 3.0), (30, "dir", None)]:
    tag = f"OR {or_min}m {mode} {'EOD' if rr is None else f'{rr:g}R'}"
    O.SPEC["US500"]["slip"] = base_slip
    t = O.run(d, "US500", or_min, mode, rr)
    y = t.groupby(t.entry_t.dt.year).R.agg(["count", "mean", "sum"]).round(3)
    print(f"\n=== {tag}: n={len(t)} exp={t.R.mean():+.3f}  (prima zi {t.entry_t.min().date()})")
    print("pe ani (mean R):", {int(k): v for k, v in y["mean"].items()})
    # stiri: prima vineri (NFP) + zilele 10-15 (fereastra CPI) — aproximare grosiera
    dd = t.entry_t
    nfp = (dd.dt.weekday == 4) & (dd.dt.day <= 7)
    cpi = dd.dt.day.between(10, 15)
    print(f"  NFP-vineri: n={nfp.sum()} exp={t.R[nfp].mean():+.3f} | ferestre CPI: n={cpi.sum()} exp={t.R[cpi].mean():+.3f} | restul: exp={t.R[~nfp & ~cpi].mean():+.3f}")
    print(f"  long: exp={t.R[t.side==1].mean():+.3f} (n={(t.side==1).sum()}) | short: exp={t.R[t.side==-1].mean():+.3f} (n={(t.side==-1).sum()})")
    for mult in (2, 4):
        O.SPEC["US500"]["slip"] = base_slip * mult
        t2 = O.run(d, "US500", or_min, mode, rr)
        print(f"  slippage x{mult} ({base_slip*mult:.2f} pct/ordin): exp={t2.R.mean():+.3f}")
O.SPEC["US500"]["slip"] = base_slip
