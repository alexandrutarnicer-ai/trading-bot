"""
Daily Engine — DE40 dimineata (Frankfurt): ORA DE INCHIDERE a trade-ului (2026-11-24). DOAR backtest, doar citire.

Intrebarea: trade-ul de la deschiderea Frankfurt (09:00 Berlin = 10:00 RO) sta deschis pana la 17:30 Berlin (18:30 RO),
adica si in prima ora dupa deschiderea New York (15:30 Berlin = 16:30 RO). Ar fi mai bine sa-l inchidem mai devreme
(15:00 / 15:30 / 16:00 RO)?

Metoda: ACEEASI functie ca engine-ul (strategy.evaluate_day_multi) + ACEEASI admitere a sesiunilor
(strategy.admit_session_trades: max trade-uri / zi, fara doua pozitii simultan), configuratia curenta DE40 din
daily_engine/config.json (interval 5 min, breakout, fara TP, costuri, sesiunea NY, max 2 / zi). Se schimba DOAR
ultima bara a sesiunii Frankfurt (inchidere la finalul ei). Tot istoricul M5 din data/research_daily/DE40_M5_server.csv.
Doua variante: A = doar sesiunea Frankfurt; B = Frankfurt + New York (configuratia reala: o inchidere mai devreme
elibereaza piata pentru trade-ul de la NY).
    python scripts/research_daily/de40_exit_time.py
Rezultat: data/research_daily/de40_exit_time.json + tabele pe ecran.
"""
from __future__ import annotations

import copy
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from daily_engine.config import ENTRY_MODES, hm_to_min, load_config  # noqa: E402
from daily_engine.market_tools import market_sessions, server_to_exchange  # noqa: E402
from daily_engine.strategy import admit_session_trades, evaluate_day_multi  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from m5_data import read_m5  # noqa: E402

DATA = os.path.join(ROOT, "data", "research_daily")
POINT = 0.01
# ultima bara M5 (ora Berlin) → inchidere la FINALUL ei; RO = Berlin + 1h (ambele urmeaza DST-ul UE)
EXITS = ["12:55", "13:25", "13:55", "14:25", "14:55", "15:25", "15:55", "16:25", "16:55", "17:25"]


def _close_label(last_bar: str) -> str:
    m = hm_to_min(last_bar) + 5
    return f"{m // 60:02d}:{m % 60:02d}"


def _ro_label(last_bar: str) -> str:
    m = hm_to_min(last_bar) + 5 + 60
    return f"{m // 60:02d}:{m % 60:02d}"


def load_bars() -> pd.DataFrame:
    # CSV-ul are bare ZILNICE in 2013-2015 si ORARE in 2016 (M5 din 27.03.2017) → doar zilele M5 reale (m5_data.py)
    return read_m5(os.path.join(DATA, "DE40_M5_server.csv"))


def run(d0: pd.DataFrame, m: dict) -> list[dict]:
    """Copie a market_tools.backtest_rates, cu sesiunea / motivul iesirii / ziua pastrate pe fiecare trade."""
    by_day: dict = {}
    for ses in market_sessions(m):
        loc = server_to_exchange(d0["time"], ses["tz"])
        d = d0.assign(loc=loc).dropna(subset=["loc"])
        d = d[d["loc"].dt.weekday < 5]
        om, lb = hm_to_min(ses["open"]), hm_to_min(ses["last_bar"])
        d = d.assign(mins=d["loc"].dt.hour * 60 + d["loc"].dt.minute)
        d = d[(d.mins >= om) & (d.mins <= lb)]
        d = d.assign(day=d["loc"].dt.normalize())
        n_or = ses["or_minutes"] // 5
        tzinfo = ZoneInfo(ses["tz"])
        for day, g in d.groupby("day", sort=True):
            if g.mins.iloc[0] != om or len(g) < n_or + 6 or g.high.iloc[:n_or].max() - g.low.iloc[:n_or].min() <= 0:
                continue
            r = evaluate_day_multi(g.open, g.high, g.low, g.close, g.spread.to_numpy(float) * POINT, g.mins, open_min=om,
                                   or_minutes=ses["or_minutes"], mode=ENTRY_MODES[ses["entry"]], rr=ses.get("rr"),
                                   slip=ses["slip"], comm=ses["comm"], day_complete=True, reentry=ses.get("reentry"),
                                   plock=ses.get("profit_lock"))
            base = datetime(day.year, day.month, day.day, tzinfo=tzinfo)
            dk = day.date()
            by_day.setdefault(dk, []).append(
                {"key": ses["_session"], "st": r,
                 "to_utc": (lambda mins, _b=base: (_b + timedelta(minutes=int(mins))).astimezone(timezone.utc))})
    max_tr = int(m.get("max_trades_per_day") or 1)
    rows = []
    for dk in sorted(by_day):
        comb = admit_session_trades(by_day[dk], max_tr)
        for item in by_day[dk]:
            for t in comb[item["key"]]["st"]["trades"]:
                rows.append({"day": dk, "session": item["key"], "R": float(t["R"]), "reason": t["reason"],
                             "entry_t": item["to_utc"](int(t["entry_min"]))})
    rows.sort(key=lambda x: x["entry_t"])
    return rows


def stats(rows: list[dict]) -> dict:
    if not rows:
        return {"n": 0}
    R = np.array([r["R"] for r in rows])
    eq = np.cumsum(R)
    cut = int(0.7 * len(R))
    w, ls = R[R > 0], R[R < 0]
    last = max(r["day"] for r in rows)
    r12 = np.array([r["R"] for r in rows if (last - r["day"]).days <= 365])
    years = {}
    for r in rows:
        years.setdefault(r["day"].year, []).append(r["R"])
    return {"n": int(len(R)), "exp_R": round(float(R.mean()), 4), "net_R": round(float(R.sum()), 1),
            "win_rate": round(float((R > 0).mean() * 100), 1),
            "pf": round(float(w.sum() / -ls.sum()), 3) if ls.sum() < 0 else None,
            "max_dd_R": round(float((eq - np.maximum.accumulate(eq)).min()), 1),
            "train_R": round(float(R[:cut].mean()), 4), "test_R": round(float(R[cut:].mean()), 4),
            "last12_R": round(float(r12.mean()), 4) if len(r12) else None, "last12_n": int(len(r12)),
            "years_pos": f"{sum(1 for v in years.values() if np.mean(v) > 0)}/{len(years)}",
            "by_year": {y: round(float(np.mean(v)), 3) for y, v in sorted(years.items())},
            "period": f"{min(r['day'] for r in rows)} → {last}"}


def main():
    cfg = load_config()
    base = next(m for m in cfg["markets"] if m.get("symbol") == "DE40")
    d0 = load_bars()
    out = {"config": {k: base.get(k) for k in ("symbol", "preset", "sessions", "max_trades_per_day", "rr", "slip",
                                                 "comm", "or_minutes", "entry", "open", "last_bar")}, "variants": []}
    print(f"DE40 — configuratia curenta: sesiuni {base.get('sessions')}, max {base.get('max_trades_per_day')}/zi, "
          f"rr {base.get('rr')}, inchidere Frankfurt acum {_close_label(base['last_bar'])} Berlin "
          f"({_ro_label(base['last_bar'])} RO)\n")
    for lb in EXITS:
        row = {"last_bar": lb, "close_berlin": _close_label(lb), "close_ro": _ro_label(lb)}
        # A: doar Frankfurt
        ma = copy.deepcopy(base)
        ma["last_bar"] = lb
        ma["sessions"] = ["frankfurt"]
        ma["max_trades_per_day"] = 1 if not (ma.get("reentry") or {}).get("enabled") else ma["reentry"]["max_trades"]
        ra = run(d0, ma)
        row["A_frankfurt"] = stats(ra)
        row["A_eod_share"] = round(100 * sum(1 for r in ra if r["reason"] == "EOD") / max(1, len(ra)), 1)
        # B: configuratia reala (Frankfurt + New York, max 2/zi)
        mb = copy.deepcopy(base)
        mb["last_bar"] = lb
        rb = run(d0, mb)
        row["B_total"] = stats(rb)
        row["B_frankfurt"] = stats([r for r in rb if r["session"] == "frankfurt"])
        row["B_new_york"] = stats([r for r in rb if r["session"] == "new_york"])
        out["variants"].append(row)
        print(f"  gata {row['close_ro']} RO")

    cur = _close_label(base["last_bar"])
    print("\nA. DOAR trade-ul Frankfurt (dimineata), in functie de ora de inchidere")
    print(f"{'inchidere RO':>12} {'Berlin':>7} {'n':>5} {'R/trade':>8} {'R total':>8} {'WR%':>5} {'PF':>6} {'DD R':>7}"
          f" {'train':>7} {'test':>7} {'12 luni':>8} {'ani+':>5} {'EOD%':>5}")
    for v in out["variants"]:
        s = v["A_frankfurt"]
        mark = " ← acum" if v["close_berlin"] == cur else ""
        print(f"{v['close_ro']:>12} {v['close_berlin']:>7} {s['n']:>5} {s['exp_R']:>8.3f} {s['net_R']:>8.1f} "
              f"{s['win_rate']:>5.1f} {s['pf'] or 0:>6.2f} {s['max_dd_R']:>7.1f} {s['train_R']:>7.3f} {s['test_R']:>7.3f} "
              f"{s['last12_R'] or 0:>8.3f} {s['years_pos']:>5} {v['A_eod_share']:>5.1f}{mark}")
    print("\nB. Configuratia reala (Frankfurt + New York, max 2/zi, fara pozitii simultane)")
    print(f"{'inchidere RO':>12} {'n tot':>6} {'R/trade':>8} {'R total':>8} {'DD R':>7} {'test':>7} {'12 luni':>8}"
          f" | {'n FRA':>5} {'R FRA':>7} | {'n NY':>5} {'R NY':>7} {'R/tr NY':>8}")
    for v in out["variants"]:
        s, f, n = v["B_total"], v["B_frankfurt"], v["B_new_york"]
        mark = " ← acum" if v["close_berlin"] == cur else ""
        print(f"{v['close_ro']:>12} {s['n']:>6} {s['exp_R']:>8.3f} {s['net_R']:>8.1f} {s['max_dd_R']:>7.1f} "
              f"{s['test_R']:>7.3f} {s['last12_R'] or 0:>8.3f} | {f['n']:>5} {f['net_R']:>7.1f} | {n.get('n', 0):>5} "
              f"{n.get('net_R', 0):>7.1f} {n.get('exp_R', 0):>8.3f}{mark}")
    with open(os.path.join(DATA, "de40_exit_time.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, default=str)
    print(f"\nperioada: {out['variants'][0]['A_frankfurt']['period']}  →  data/research_daily/de40_exit_time.json")


if __name__ == "__main__":
    main()
