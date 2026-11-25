"""
Citirea CSV-urilor de cercetare M5 (data/research_daily/<SIM>_M5_server.csv) — DOAR zilele cu bare M5 reale.

De ce (2026-11-24): MT5 a exportat la inceputul istoricului bare de alt timeframe sub acelasi fisier — DE40: bare
ZILNICE 2013-2015 si ORARE 2016 (M5 abia din 27.03.2017, dupa-amiaza); US500: zilnice 2012-2015, orare 2016. O zi cu
bare orare trecea filtrul de zi al backtestului (bara la ora de deschidere + destule bare), iar „intervalul de 5
minute” era de fapt o bara de o ora → trade-uri false (~290 pe DE40 Frankfurt), si doar cand fereastra era destul de
lunga (strica tocmai comparatiile intre ferestre). GBPUSD / EURUSD / USDJPY / GBPAUD sunt curate (rezultat identic).

Regula: (1) se scot TOATE barele pana la ultima bara a ultimei serii de alt timeframe (>= 4 pasi la rand de cel putin
55 min — o pauza normala a pietei pe M5 e un singur pas lung). Taietura e la nivel de BARA, nu de zi: in ziua de
tranzitie raman doar barele M5 (DE40 27.03.2017: bara de 09:00 Berlin era orara → ziua e sarita de backtest pentru ca
nu mai are bara de deschidere; US500 21.03.2017: doar dimineata serverului era orara, fereastra NY ramane intacta);
(2) din rest, o zi a serverului ramane doar daca pasul MEDIAN e de 5 minute.
Doar cercetare / selftest; engine-urile live si backtestul din UI citesc barele direct din MT5 (M5) si nu folosesc
acest modul.
"""
from __future__ import annotations

import pandas as pd

STEP_MIN = 5.0
_LONG_STEP_MIN = 55.0
_RUN = 4


def only_m5_days(d: pd.DataFrame, time_col: str = "time") -> pd.DataFrame:
    """Pastreaza doar zilele (dupa data serverului) cu bare M5 reale. Intoarce o copie (index resetat);
    `attrs["dropped_days"]` = cate zile au fost scoase."""
    if d is None or d.empty:
        return d
    t = pd.to_datetime(d[time_col]).reset_index(drop=True)
    day = t.dt.normalize()
    step = t.diff().dt.total_seconds().div(60)
    long_ = step.ge(_LONG_STEP_MIN)
    run = long_.groupby((~long_).cumsum()).cumsum()        # lungimea seriei curente de pasi lungi
    keep = pd.Series(True, index=t.index)
    if run.ge(_RUN).any():
        keep &= t.gt(t[run.ge(_RUN)].max())               # tot ce e pana la ultima bara de alt timeframe, inclusiv
    t2, day2 = t[keep], day[keep]
    in_day = t2.diff().dt.total_seconds().div(60).where(day2.eq(day2.shift()))
    med = in_day.groupby(day2).median()
    keep &= day.isin(med[med == STEP_MIN].index)
    out = d.reset_index(drop=True)[keep.to_numpy()].reset_index(drop=True)
    out.attrs["dropped_days"] = int(day.nunique() - day[keep].nunique())
    return out


def read_m5(path) -> pd.DataFrame:
    return only_m5_days(pd.read_csv(path, parse_dates=["time"]))
