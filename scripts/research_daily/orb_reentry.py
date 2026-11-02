"""Daily Engine — RE-INTRARE in prima ora dupa deschidere (cercetare, 2026-11-02).

Intrebarea userului: in prima ora a punctelor „fierbinti” (deschiderea Londrei / New York), daca trade-ul
zilei s-a inchis (SL) sau a fost invalidat, sa mai poata intra alte trade-uri?

Baza = EXACT regulile Daily Engine (configuratia live) si simularea din orb_m5.run:
  GBPUSD  Londra 08:00, OR 5 min, „brk” (stop pe ambele margini), SL = marginea opusa, fara TP, iesire 14:25 London
  US500   New York 09:30, OR 30 min, „dir” (directia OR-ului, intrare 10:00), SL = marginea opusa, iesire 15:55 NY
Re-intrare: dupa o iesire pe SL, de la bara URMATOARE se cauta o noua rupere a ACELUIASI OR (oricare margine —
dupa un SL pe long, pretul e deja sub marginea de jos → intrare short la open-ul barei, ca in live: „pret deja
dincolo de margine → piata”), cu aceleasi costuri (spread real al barei + slippage + comision). Intrarea noua e
permisa doar daca bara ei incepe in primele W minute de la deschidere; maximum K trade-uri / zi; o pozitie odata.
„Invalidat” (ambele margini atinse in aceeasi bara → ziua abandonata in baza): varianta „cont” continua cautarea
in fereastra W in loc sa abandoneze ziua.
Fara grila mare: W ∈ {60 (cerut), 30, 90, 120 — doar sensibilitate}, K ∈ {2, 3}.
Verificare: K=1 reproduce orb_m5.run trade cu trade (altfel scriptul se opreste).

Rulare: python scripts/research_daily/orb_reentry.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import orb_m5 as O  # noqa: E402
from m0.robustness import evaluate_trades  # noqa: E402

MARKETS = [  # (simbol, tz, open_min, close_min, or_min, mode) — = daily_engine/config.json
    ("GBPUSD", "Europe/London", 480, 865, 5, "brk"),
    ("US500", "America/New_York", 570, 955, 30, "dir"),
]


def sim_day(o, h, l, c, spr, mins, *, open_min, n_or, mode, slip, comm, max_trades, window, cont_double):
    """Trade-urile unei zile. max_trades=1 & cont_double=False = orb_m5.run (verificat)."""
    n = len(o)
    hi, lo = h[:n_or].max(), l[:n_or].min()
    out, start, k = [], n_or, 0
    while k < max_trades:
        if k == 0 and mode == "dir":
            if c[n_or - 1] == o[0]:
                return out
            side = 1 if c[n_or - 1] > o[0] else -1
            i0 = n_or
            entry = o[i0] + side * spr[i0] / 2
            sl = lo if side == 1 else hi
            stop_fill = False
        else:
            side = None
            for i in range(start, n):
                if k > 0 and mins[i] >= open_min + window:
                    return out                              # re-intrare doar in primele W minute
                up, dn = h[i] >= hi, l[i] <= lo
                if up and dn:
                    if cont_double and mins[i] < open_min + window:
                        continue                            # „invalidat” → continua cautarea in fereastra
                    return out
                if up or dn:
                    side = 1 if up else -1
                    lvl = hi if up else lo
                    fill = max(lvl, o[i]) if up else min(lvl, o[i])
                    entry = fill + side * (slip + spr[i] / 2)
                    sl, i0 = (lo if up else hi), i
                    break
            if side is None:
                return out
            stop_fill = True
        risk = abs(entry - sl)
        cost_rt = spr[i0] + slip + comm
        if risk <= 0 or risk < 2 * cost_rt:
            return out
        res, j_exit, why = None, n - 1, "EOD"
        for j in range(i0, n):
            hit_sl = (l[j] <= sl) if side == 1 else (h[j] >= sl)
            if stop_fill and j == i0:
                if hit_sl:
                    res, j_exit, why = -1.0 - (slip + spr[j] / 2) / risk, j, "SL"
                    break
                continue
            if hit_sl:
                res, j_exit, why = -1.0 - (slip + spr[j] / 2) / risk, j, "SL"
                break
        if res is None:
            res = (side * (c[-1] - entry) - spr[-1] / 2) / risk
        res -= comm / risk
        out.append(dict(k=k, side=side, R=float(res), why=why, entry_min=int(mins[i0]), exit_min=int(mins[j_exit])))
        k += 1
        if why != "SL" or j_exit + 1 >= n:
            return out
        start = j_exit + 1
    return out


def run(d, sym, open_min, or_min, mode, max_trades=1, window=60, cont_double=False):
    sp = O.SPEC[sym]
    n_or = or_min // 5
    rows = []
    for day, g in d.groupby("day", sort=True):
        if g.mins.iloc[0] != open_min or len(g) < n_or + 6:
            continue
        o, h, l, c = (g[k].to_numpy() for k in ("open", "high", "low", "close"))
        spr = g.spread.to_numpy() * sp["point"]
        mins = g.mins.to_numpy()
        if h[:n_or].max() - l[:n_or].min() <= 0:
            continue
        for t in sim_day(o, h, l, c, spr, mins, open_min=open_min, n_or=n_or, mode=mode, slip=sp["slip"],
                         comm=sp["comm"], max_trades=max_trades, window=window, cont_double=cont_double):
            rows.append(dict(day=day, entry_t=day + pd.Timedelta(minutes=t["entry_min"]), **t))
    return pd.DataFrame(rows)


def max_dd(r: pd.Series) -> float:
    eq = r.cumsum()
    return float((eq - eq.cummax()).min()) if len(eq) else 0.0


def summary(t: pd.DataFrame, label: str) -> dict:
    if t.empty:
        return dict(var=label, n=0)
    m = evaluate_trades(t[["entry_t", "R"]].assign(outcome=np.where(t.R > 0, "TP", "SL")), split_time=O.SPLIT, n_boot=1000)
    yrs = t.groupby(t.day.dt.year).R.sum()
    days = t.day.nunique()
    return dict(var=label, n=len(t), days=days, exp=round(m["expectancy"], 3), tot=round(t.R.sum(), 1),
                per_day=round(t.R.sum() / max(days, 1), 3), train=round(m["train_exp"], 3), test=round(m["test_exp"], 3),
                dd=round(max_dd(t.R), 1), p_pos=round(m["prob_positive"], 2), folds=round(m["frac_positive"], 2),
                yrs=f"{(yrs > 0).sum()}/{len(yrs)}", verdict=m["verdict"])


def main():
    pd.set_option("display.width", 240)
    pd.set_option("display.max_columns", 30)
    for sym, tz, om, cm, or_min, mode in MARKETS:
        d = O.load(sym, tz, om, cm)
        # 1. verificare: K=1 = backtestul existent, trade cu trade
        ref = O.run(d, sym, or_min, mode, None)
        base = run(d, sym, om, or_min, mode, max_trades=1)
        same = len(ref) == len(base) and np.allclose(ref.R.to_numpy(), base.R.to_numpy(), atol=1e-12)
        print(f"\n=== {sym} ({tz} {om // 60:02d}:{om % 60:02d}, OR {or_min} min, {mode}) — verificare baza: "
              f"{'IDENTIC cu orb_m5.run' if same else 'DIFERIT!'} ({len(ref)} vs {len(base)} trade-uri)")
        if not same:
            sys.exit(1)
        rows = [summary(base, "BAZA 1/zi")]
        extra_rows = []
        for w in (60, 30, 90, 120):
            for kmax in (2, 3):
                for cont in (False, True):
                    lab = f"W{w} K{kmax}{' +inval' if cont else ''}"
                    t = run(d, sym, om, or_min, mode, max_trades=kmax, window=w, cont_double=cont)
                    rows.append(summary(t, lab))
                    ex = t[t.k > 0]
                    s = summary(ex, f"doar extra {lab}")
                    # zilele „invalidate” recuperate (k=0 gasit dupa o bara dubla) — fac parte din extra
                    if cont:
                        bkeys = set(zip(base.day, base.entry_min))
                        rec = t[(t.k == 0) & ~pd.Series(list(zip(t.day, t.entry_min)), index=t.index).isin(bkeys)]
                        s["inval_recuperate"] = len(rec)
                        s["inval_exp"] = round(rec.R.mean(), 3) if len(rec) else None
                    extra_rows.append(s)
        print(pd.DataFrame(rows).to_string(index=False))
        print("\n  Trade-urile IN PLUS (a 2-a / a 3-a intrare din zi) — luate separat:")
        print(pd.DataFrame(extra_rows).to_string(index=False))


if __name__ == "__main__":
    main()
