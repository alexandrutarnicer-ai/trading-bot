"""Daily Engine — R:R (2R / 3R / 4R) + RE-INTRARI in prima ora + alte intervale de deschidere (cercetare, 2026-11-03).

Foloseste EXACT functia engine-ului (`daily_engine.strategy.evaluate_day_multi`, verificata identica cu orb_m5 /
orb_reentry), costurile reale din orb_m5.SPEC (spread-ul barei + slippage + comision) si verdictul M0.

Grila: piata (Londra GBPUSD breakout · New York US500 directie · Frankfurt DE40 breakout / directie) ×
       intervalul de deschidere OR (5 / 15 / 30 / 60 min — „timeframe-ul” strategiei; barele raman M5) ×
       tinta (fara TP = actual / 2R / 3R / 4R) × re-intrari (oprit / pornit: prima ora, max 3 / zi, stop la 2 pierderi
       la rand, o lumanare pauza dupa iesire).
Rulare: python scripts/research_daily/orb_rr_reentry.py   (date: data/research_daily/<SYM>_M5_server.csv)
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import orb_m5 as O  # noqa: E402
from daily_engine.strategy import evaluate_day_multi  # noqa: E402
from m0.robustness import evaluate_trades  # noqa: E402

O.SPEC.setdefault("DE40", dict(point=0.01, slip=0.20, comm=0.0, usd_per_unit_minlot=0.112))
MARKETS = [  # (eticheta, simbol, tz, deschidere, ultima bara, mod actual)
    ("Londra GBPUSD", "GBPUSD", "Europe/London", 480, 865, "brk"),
    ("New York US500", "US500", "America/New_York", 570, 955, "dir"),
    ("Frankfurt DE40", "DE40", "Europe/Berlin", 540, 1045, "brk"),
    ("Frankfurt DE40", "DE40", "Europe/Berlin", 540, 1045, "dir"),
]
RE_ON = {"enabled": True, "window_min": 60, "max_trades": 3, "max_consec_losses": 2, "cooldown_bars": 1}


def run(d, sym, om, or_min, mode, rr, reentry):
    sp = O.SPEC[sym]
    n_or = or_min // 5
    rows = []
    for day, g in d.groupby("day", sort=True):
        if g.mins.iloc[0] != om or len(g) < n_or + 6:
            continue
        if g.high.iloc[:n_or].max() - g.low.iloc[:n_or].min() <= 0:
            continue
        r = evaluate_day_multi(g.open, g.high, g.low, g.close, g.spread.to_numpy() * sp["point"], g.mins, open_min=om,
                               or_minutes=or_min, mode=mode, rr=rr, slip=sp["slip"], comm=sp["comm"], day_complete=True,
                               reentry=reentry)
        rows += [dict(day=day, entry_t=day + pd.Timedelta(minutes=int(t["entry_min"])), R=t["R"], k=t["k"]) for t in r["trades"]]
    return pd.DataFrame(rows)


def summary(t, days_total):
    if t.empty:
        return dict(n=0)
    m = evaluate_trades(t[["entry_t", "R"]].assign(outcome=np.where(t.R > 0, "TP", "SL")), split_time=O.SPLIT, n_boot=500)
    eq = t.R.cumsum()
    return dict(n=len(t), pe_sapt=round(len(t) / days_total * 5, 1), exp=round(m["expectancy"], 3),
                wr=round(100 * (t.R > 0).mean()), tot=round(t.R.sum(), 1), dd=round(float((eq - eq.cummax()).min()), 1),
                train=round(m["train_exp"], 3), test=round(m["test_exp"], 3), verdict=m["verdict"])


def main():
    pd.set_option("display.width", 250)
    pd.set_option("display.max_rows", 500)
    out = []
    for label, sym, tz, om, cm, mode in MARKETS:
        d = O.load(sym, tz, om, cm)
        days_total = d.day.nunique()
        for or_min in (5, 15, 30, 60):
            for rr in (None, 2.0, 3.0, 4.0):
                for re_on in (False, True):
                    t = run(d, sym, om, or_min, mode, rr, RE_ON if re_on else None)
                    out.append(dict(piata=label, mod=mode, OR=or_min, tinta="fara TP" if rr is None else f"{rr:g}R",
                                    reintrari="DA" if re_on else "-", **summary(t, days_total)))
            print(f"{label} {mode} OR {or_min} gata", flush=True)
    df = pd.DataFrame(out)
    print(df.to_string(index=False))
    df.to_csv(ROOT / "data/research_daily/orb_rr_reentry.csv", index=False)


if __name__ == "__main__":
    main()
