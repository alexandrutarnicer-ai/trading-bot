"""
Candidat F — ORB intraday pe deschiderea fiecarei burse (logica Daily Engine: daily_engine.strategy.evaluate_day_multi,
identica cu engine-ul live). Fara nopti → fara swap. Costuri: spread-ul barei + slip = 25% din spread-ul LIVE +
comm = markup-ul contului (spread live − mediana spread-ului din bare, ~0 pe indici).

Disciplina anti-overfitting:
  - grila mica: interval 5 / 15 / 30 min × mod breakout / direction  (6 variante pe piata)
  - varianta se ALEGE doar pe primii 70% din zile (train) dupa expectancy; se raporteaza separat pe ultimii 30% (test)
  - portofoliul final = doar pietele a caror varianta aleasa pe train e pozitiva SI pe test
Rezultat: data/research_special/intraday_orb.json + orb_trades.csv
"""
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import common as C  # noqa: E402
from daily_engine.strategy import evaluate_day_multi  # noqa: E402
from daily_engine.config import ENTRY_MODES, hm_to_min  # noqa: E402
from daily_engine.market_tools import server_to_exchange  # noqa: E402

MARKETS = [  # simbol, bursa (tz, deschidere, ultima bara)
    ("DE40", "Europe/Berlin", "09:00", "17:25"),
    ("STOXX50", "Europe/Berlin", "09:00", "17:25"),
    ("UK100", "Europe/London", "08:00", "16:25"),
    ("US500", "America/New_York", "09:30", "15:55"),
    ("USTEC", "America/New_York", "09:30", "15:55"),
    ("US30", "America/New_York", "09:30", "15:55"),
    ("XAUUSD", "America/New_York", "08:20", "16:55"),
    ("JP225", "Asia/Tokyo", "09:00", "14:55"),
    ("AUS200", "Australia/Sydney", "10:00", "15:55"),
    ("GBPUSD", "Europe/London", "08:00", "14:25"),
]
GRID = [(o, e) for o in (5, 15, 30) for e in ("breakout", "direction")]


def load_m5(sym):
    p = os.path.join(C.ROOT, "data", "research_daily", f"{sym}_M5_server.csv")
    if sym in ("DE40", "US500", "GBPUSD") and os.path.exists(p):
        d = pd.read_csv(p, parse_dates=["time"])
    else:
        d = C.fetch(sym, "M5", 400000)
    return d


def prep(d, tz, op, lb):
    loc = server_to_exchange(d["time"], tz)
    d = d.assign(loc=loc).dropna(subset=["loc"])
    d = d[d["loc"].dt.weekday < 5].copy()
    om, lbm = hm_to_min(op), hm_to_min(lb)
    d["mins"] = d["loc"].dt.hour * 60 + d["loc"].dt.minute
    d = d[(d.mins >= om) & (d.mins <= lbm)]
    d["day"] = d["loc"].dt.normalize().dt.tz_localize(None)
    return d, om


def run_market(sym, tz, op, lb, slip, comm, point):
    d, om = prep(load_m5(sym), tz, op, lb)
    groups = [(day, g) for day, g in d.groupby("day", sort=True) if g.mins.iloc[0] == om and len(g) >= 12]
    out = {}
    for orm, ent in GRID:
        rows = []
        n_or = orm // 5
        for day, g in groups:
            if g.high.iloc[:n_or].max() - g.low.iloc[:n_or].min() <= 0:
                continue
            r = evaluate_day_multi(g.open, g.high, g.low, g.close, g.spread.to_numpy(float) * point, g.mins,
                                   open_min=om, or_minutes=orm, mode=ENTRY_MODES[ent], rr=None, slip=slip, comm=comm,
                                   day_complete=True, reentry=None)
            for t in r["trades"]:
                et = day + pd.Timedelta(minutes=int(t["entry_min"]))
                rows.append({"sym": sym, "entry_t": et, "exit_t": et, "R": float(t["R"]), "var": f"{orm}/{ent}"})
        out[(orm, ent)] = rows
    return out


def main():
    m = C.mt5()
    results, chosen_rows, table, all_variants = {}, [], [], []
    for sym, tz, op, lb in MARKETS:
        m.symbol_select(sym, True)
        info, tick = m.symbol_info(sym), m.symbol_info_tick(sym)
        point = float(info.point)
        bars = load_m5(sym)
        hist = float(np.median(bars["spread"].to_numpy(float)[-20000:])) * point
        live = float(tick.ask - tick.bid)
        slip, comm = max(point, 0.25 * live), max(0.0, round((live - hist) / point) * point)
        allv = run_market(sym, tz, op, lb, slip, comm, point)
        # alegere pe TRAIN (primele 70% din zile)
        days = sorted({r["entry_t"].normalize() for rows in allv.values() for r in rows})
        cut = days[int(0.7 * len(days))]
        best, best_tr = None, -9
        for k, rows in allv.items():
            tr = [r["R"] for r in rows if r["entry_t"] < cut]
            if len(tr) >= 50 and np.mean(tr) > best_tr:
                best, best_tr = k, float(np.mean(tr))
        info_v = {}
        for k, rows in allv.items():
            tr = [r["R"] for r in rows if r["entry_t"] < cut]
            te = [r["R"] for r in rows if r["entry_t"] >= cut]
            info_v[f"{k[0]}/{k[1]}"] = {"n": len(rows), "train": round(float(np.mean(tr)), 3) if tr else None,
                                        "test": round(float(np.mean(te)), 3) if te else None}
        for k_, rows_ in allv.items():
            all_variants.extend(rows_)
        rows = allv[best]
        te = [r["R"] for r in rows if r["entry_t"] >= cut]
        rep = C.report(rows, label=f"F orb {sym} {best[0]}/{best[1]}")
        rep["select_train"] = round(best_tr, 3)
        rep["select_test"] = round(float(np.mean(te)), 3)
        rep["grid"] = info_v
        rep["costs"] = {"slip": slip, "comm": comm, "spread_live": live, "spread_hist": hist}
        results[sym] = rep
        print(C.fmt(rep), f"| ales pe train {best_tr:+.3f} → test {np.mean(te):+.3f} | slip {slip:g} comm {comm:g}",
              flush=True)
        print("    grila:", {k: (v["train"], v["test"]) for k, v in info_v.items()}, flush=True)
        if best_tr > 0 and np.mean(te) > 0:
            chosen_rows += rows
        table += rows
    port = C.report(chosen_rows, label="F orb PORTOFOLIU (train>0 si test>0)")
    print(C.fmt(port))
    results["_portfolio"] = port
    results["_portfolio_markets"] = sorted({r["sym"] for r in chosen_rows})
    json.dump(results, open(os.path.join(C.OUT, "intraday_orb.json"), "w"), indent=1, default=str)
    pd.DataFrame(table).to_csv(os.path.join(C.OUT, "orb_trades.csv"), index=False)
    pd.DataFrame(all_variants).to_csv(os.path.join(C.OUT, "orb_trades_all.csv"), index=False)


if __name__ == "__main__":
    main()
