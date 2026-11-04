"""
Candidat G — „Beat the Market” (Zarattini, Aziz, Barbon 2024, SFI WP 24-97): intraday momentum pe „noise area”.
Implementat cu parametrii DIN LUCRARE, fara optimizare (zero data snooping):
  - sigma(minut) = media pe ultimele 14 zile a |close(minut) / open(zi) − 1| la acelasi minut al zilei
  - UB = max(open, close_ieri) × (1 + sigma), LB = min(open, close_ieri) × (1 − sigma)
  - verificare la fiecare :00 / :30 (de la deschidere + 30 min pana la ultima jumatate de ora):
      close > UB → LONG, close < LB → SHORT (se poate intoarce)
      stop trailing: LONG iese daca close < max(UB, VWAP), SHORT daca close > min(LB, VWAP)
  - totul inchis la sfarsitul sesiunii (fara nopti → fara swap)
Unitatea R = sigma × open la intrare (latimea „zgomotului”); costuri: spread bara + 25% slip live + markup cont.
Piete: indici US (sesiunea NY) + DE40 (Xetra) + XAUUSD (NY) + JP225 (Tokyo).
"""
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import common as C  # noqa: E402
from intraday_orb import load_m5  # noqa: E402
from daily_engine.config import hm_to_min  # noqa: E402
from daily_engine.market_tools import server_to_exchange  # noqa: E402

MARKETS = [("US500", "America/New_York", "09:30", "16:00"), ("USTEC", "America/New_York", "09:30", "16:00"),
           ("US30", "America/New_York", "09:30", "16:00"), ("DE40", "Europe/Berlin", "09:00", "17:30"),
           ("XAUUSD", "America/New_York", "09:30", "16:00"), ("JP225", "Asia/Tokyo", "09:00", "15:00"),
           ("UK100", "Europe/London", "08:00", "16:30"), ("STOXX50", "Europe/Berlin", "09:00", "17:30")]
LOOKBACK = 14


def run(sym, tz, op, cl, cost_px, point):
    d = load_m5(sym)
    loc = server_to_exchange(d["time"], tz)
    d = d.assign(loc=loc).dropna(subset=["loc"])
    d = d[d["loc"].dt.weekday < 5].copy()
    om, cm = hm_to_min(op), hm_to_min(cl)
    d["mins"] = d["loc"].dt.hour * 60 + d["loc"].dt.minute
    d = d[(d.mins >= om) & (d.mins < cm)]
    d["day"] = d["loc"].dt.normalize().dt.tz_localize(None)
    d["vol"] = d["tick_volume"].astype(float).clip(lower=1)
    days = []
    for day, g in d.groupby("day", sort=True):
        if g.mins.iloc[0] != om or len(g) < (cm - om) // 5 * 0.9:
            continue
        days.append((day, g.reset_index(drop=True)))
    # matrice |close/open - 1| pe minut-al-zilei (pentru sigma)
    slots = list(range(om, cm, 5))
    mv = []
    for day, g in days:
        s = pd.Series(np.abs(g["close"].to_numpy() / g["open"].iat[0] - 1), index=g["mins"].to_numpy())
        mv.append(s.reindex(slots).ffill().to_numpy())
    mv = np.array(mv)
    rows, prev_close = [], None
    for k, (day, g) in enumerate(days):
        if k < LOOKBACK or prev_close is None:
            prev_close = g["close"].iat[-1]
            continue
        sig = np.nanmean(mv[k - LOOKBACK:k], axis=0)            # doar zilele ANTERIOARE
        o = g["open"].iat[0]
        ubase, lbase = max(o, prev_close), min(o, prev_close)
        cl_ = g["close"].to_numpy()
        mins = g["mins"].to_numpy()
        pv = (g["high"] + g["low"] + g["close"]).to_numpy() / 3
        vwap = np.cumsum(pv * g["vol"].to_numpy()) / np.cumsum(g["vol"].to_numpy())
        spr = g["spread"].to_numpy(float) * point
        pos, ent, unit, t_in = 0, 0.0, 0.0, None

        def close_pos(i, px):
            R = (px - ent) * pos / unit - (spr[i] + cost_px) / unit
            rows.append({"sym": sym, "entry_t": t_in, "exit_t": day + pd.Timedelta(minutes=int(mins[i])),
                         "d": pos, "R": float(R)})
        for i in range(len(g)):
            m_ = mins[i] + 5                                    # inchiderea barei de 5 min
            if (m_ - om) % 30 != 0 or m_ - om < 30:
                continue
            si = slots.index(mins[i]) if mins[i] in slots else None
            if si is None or np.isnan(sig[si]):
                continue
            ub, lb = ubase * (1 + sig[si]), lbase * (1 - sig[si])
            c = cl_[i]
            last = m_ >= cm
            if pos == 1 and (c < max(ub, vwap[i]) or last):
                close_pos(i, c); pos = 0
            elif pos == -1 and (c > min(lb, vwap[i]) or last):
                close_pos(i, c); pos = 0
            if pos == 0 and not last:
                nd = 1 if c > ub else (-1 if c < lb else 0)
                if nd:
                    pos, ent, unit = nd, c, sig[si] * o
                    t_in = day + pd.Timedelta(minutes=int(mins[i]))
        if pos:
            close_pos(len(g) - 1, cl_[-1])
        prev_close = g["close"].iat[-1]
    return rows


def main():
    m = C.mt5()
    out, allr, everything = {}, [], []
    for sym, tz, op, cl in MARKETS:
        m.symbol_select(sym, True)
        info, tick = m.symbol_info(sym), m.symbol_info_tick(sym)
        point = float(info.point)
        bars = load_m5(sym)
        hist = float(np.median(bars["spread"].to_numpy(float)[-20000:])) * point
        live = float(tick.ask - tick.bid)
        cost_px = max(point, 0.25 * live) + max(0.0, live - hist)
        rows = run(sym, tz, op, cl, cost_px, point)
        rep = C.report(rows, label=f"G noise {sym}")
        out[sym] = rep
        everything += rows
        allr += [r for r in rows if pd.Timestamp(r["entry_t"]) >= pd.Timestamp("2021-03-17")]
        print(C.fmt(rep), flush=True)
        print("    pe ani:", rep.get("by_year"), flush=True)
    rep = C.report(allr, label="G noise PORTOFOLIU (toate, din 2021-03)")
    out["_portfolio"] = rep
    print(C.fmt(rep))
    print("    pe ani:", rep.get("by_year"))
    json.dump(out, open(os.path.join(C.OUT, "noise_area.json"), "w"), indent=1, default=str)
    pd.DataFrame(allr).to_csv(os.path.join(C.OUT, "noise_trades.csv"), index=False)
    pd.DataFrame(everything).to_csv(os.path.join(C.OUT, "noise_trades_all.csv"), index=False)


if __name__ == "__main__":
    main()
