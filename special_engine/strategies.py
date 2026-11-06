"""Special Engine — strategiile (functii PURE, fara MT5). Aceleasi functii in backtest, selectie si engine.

ORB   : daily_engine.strategy.evaluate_day (EXACT functia Daily Engine) pe deschiderea bursei; variantele = interval
        5 / 15 / 30 min × breakout / direction, fara TP, inchidere la final de sesiune.
NOISE : „Beat the Market” (Zarattini, Aziz, Barbon 2024, SFI WP 24-97), parametrii din lucrare: sigma(minut) = media
        pe 14 zile ANTERIOARE a |close(minut)/open(zi) − 1|; UB = max(open, close_ieri)·(1+sigma), LB = min(...)·(1−sigma);
        verificare la fiecare :00/:30 (de la deschidere + 30 min); LONG peste UB / SHORT sub LB; iesire cand pretul revine
        sub max(UB, VWAP) / peste min(LB, VWAP); totul inchis la final de sesiune. R = sigma × open la intrare.
        Copie fidela a scripts/research_special/noise_area.run — echivalenta verificata in special_engine.selftest.
NR    : ziua e „NR4” daca range-ul zilei D1 ANTERIOARE (inchise) e cel mai mic din ultimele 4 (Crabel 1990)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from daily_engine.config import ENTRY_MODES
from daily_engine.strategy import evaluate_day

NOISE_LOOKBACK = 14
ORB_VARIANTS = [(o, e) for o in (5, 15, 30) for e in ("breakout", "direction")]


def orb_day(o, h, l, c, spr, mins, *, open_min: int, or_minutes: int, entry: str, slip: float, comm: float,
            day_complete: bool) -> dict:
    return evaluate_day(o, h, l, c, spr, mins, open_min=open_min, or_minutes=or_minutes, mode=ENTRY_MODES[entry],
                        rr=None, slip=slip, comm=comm, day_complete=day_complete)


def noise_moves(o0: float, closes, mins, slots) -> np.ndarray:
    """|close/open − 1| pe minutul-zilei (sloturi de 5 min), ffill — randul unei zile in matricea sigma."""
    s = pd.Series(np.abs(np.asarray(closes, float) / o0 - 1), index=np.asarray(mins))
    return s.reindex(slots).ffill().to_numpy()


def noise_sigma(prev_moves: list) -> np.ndarray | None:
    """sigma pe sloturi din cele 14 zile ANTERIOARE (None daca nu sunt destule)."""
    if len(prev_moves) < NOISE_LOOKBACK:
        return None
    return np.nanmean(np.array(prev_moves[-NOISE_LOOKBACK:]), axis=0)


def noise_day(g: pd.DataFrame, *, sig: np.ndarray, slots: list, prev_close: float, om: int, cm: int, point: float,
              cost_px: float, day: pd.Timestamp, sym: str, day_complete: bool = True) -> dict:
    """O zi NOISE pe barele M5 (inchise) `g` [open, high, low, close, spread, tick_volume, mins].
    Intoarce {trades: [...], open: pozitia deschisa sau None}. Identic cu noise_area.run cand day_complete=True."""
    o = float(g["open"].iat[0])
    ubase, lbase = max(o, prev_close), min(o, prev_close)
    cl_ = g["close"].to_numpy(float)
    mins = g["mins"].to_numpy()
    vol = g["tick_volume"].astype(float).clip(lower=1).to_numpy()
    pv = (g["high"] + g["low"] + g["close"]).to_numpy(float) / 3
    vwap = np.cumsum(pv * vol) / np.cumsum(vol)
    spr = g["spread"].to_numpy(float) * point
    rows = []
    pos, ent, unit, t_in, ub_in = 0, 0.0, 0.0, None, None

    def close_pos(i, px, why):
        R = (px - ent) * pos / unit - (spr[i] + cost_px) / unit
        rows.append({"sym": sym, "entry_t": t_in, "exit_t": day + pd.Timedelta(minutes=int(mins[i])), "d": pos,
                     "R": float(R), "entry": ent, "exit": float(px), "unit": unit, "why": why})

    slot_idx = {m_: k for k, m_ in enumerate(slots)}
    for i in range(len(g)):
        m_ = mins[i] + 5
        if (m_ - om) % 30 != 0 or m_ - om < 30:
            continue
        si = slot_idx.get(mins[i])
        if si is None or np.isnan(sig[si]):
            continue
        ub, lb = ubase * (1 + sig[si]), lbase * (1 - sig[si])
        c = cl_[i]
        last = m_ >= cm
        if pos == 1 and (c < max(ub, vwap[i]) or last):
            close_pos(i, c, "EOD" if last and c >= max(ub, vwap[i]) else "trail")
            pos = 0
        elif pos == -1 and (c > min(lb, vwap[i]) or last):
            close_pos(i, c, "EOD" if last and c <= min(lb, vwap[i]) else "trail")
            pos = 0
        if pos == 0 and not last:
            nd = 1 if c > ub else (-1 if c < lb else 0)
            if nd:
                pos, ent, unit = nd, c, sig[si] * o
                t_in = day + pd.Timedelta(minutes=int(mins[i]))
    open_pos = None
    if pos:
        if day_complete:
            close_pos(len(g) - 1, cl_[-1], "EOD")
        else:
            open_pos = {"d": pos, "entry": ent, "unit": unit, "entry_t": t_in, "last": float(cl_[-1]),
                        "open_R": float((cl_[-1] - ent) * pos / unit)}
    return {"trades": rows, "open": open_pos, "ub": float(ubase * (1 + sig[0])) if len(sig) else None}


def nr_flag(d1: pd.DataFrame, day: pd.Timestamp, n: int = 4) -> bool | None:
    """NR-n pentru ziua `day` (ziua serverului): range-ul ultimei bare D1 INCHISE inainte de `day` e minimul ultimelor n."""
    prev = d1[d1["time"].dt.normalize() < day.normalize()].tail(n)
    if len(prev) < n:
        return None
    rng = (prev["high"] - prev["low"]).to_numpy()
    return bool(rng[-1] <= rng.min() + 1e-12)
