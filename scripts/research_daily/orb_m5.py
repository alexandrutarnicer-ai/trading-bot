"""Daily Engine — Faza 1: validare ORB pe M5 (istoric MT5 complet), costuri reale bara-cu-bara.

Date: data/research_daily/<SYM>_M5_server.csv (ora serverului ICMarkets = ora New York + 7h, verificat).
Reguli (pre-inregistrate, grila mica pentru a limita cautarea):
  - OR = primele {5,15,30} minute dupa 09:30 NY (cash open)
  - mod "brk": ordine stop pe ambele margini (OCO); "dir": directia lumanarii OR, intrare la open-ul urmator
  - iesire: TP {2R, 3R} sau inchidere fortata 15:55 NY (EOD); SL = marginea opusa a OR
  - cost: spread-ul real al barei la intrare + la iesire + slippage pe ordinele stop; comision pe FX
  - gap peste nivel -> umplere la open-ul barei (nu la nivel); SL+TP in aceeasi bara -> SL
  - zile in care riscul < 2x cost sunt sarite (ca in replicarea independenta)
Iesire: tabel + verdict M0 (bootstrap, Deflated Sharpe / N*, 8 fold-uri) per configuratie.

Rulare: python scripts/research_daily/orb_m5.py [US500 EURUSD ...] [--news]
"""
import sys, itertools, json
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from m0.robustness import evaluate_trades  # noqa: E402

SPEC = {  # point, slippage (pret) per ordin stop, comision round-trip (pret), lot minim -> $/unitate pret
    "US500":  dict(point=0.01,    slip=0.10,    comm=0.0,     usd_per_unit_minlot=0.1),
    "EURUSD": dict(point=0.00001, slip=0.00002, comm=0.00007, usd_per_unit_minlot=1000.0),
    "USDJPY": dict(point=0.001,   slip=0.002,   comm=0.007,   usd_per_unit_minlot=6.35),
    "GBPUSD": dict(point=0.00001, slip=0.00002, comm=0.00007, usd_per_unit_minlot=1000.0),
    # GBPAUD: cotat in AUD; comision $7/lot ~ 0.00011 AUD; 0.01 lot = 1000 AUD/unitate ~ $640
    "GBPAUD": dict(point=0.00001, slip=0.00003, comm=0.00011, usd_per_unit_minlot=640.0),
}
SPLIT = pd.Timestamp("2022-01-01")


def load(sym, tz="America/New_York", open_min=570, close_min=955):
    """Bare M5 in ora locala a bursei `tz`, intre open_min si close_min (minute de la miezul noptii).
    Implicit: New York 09:30 .. 15:55."""
    d = pd.read_csv(ROOT / f"data/research_daily/{sym}_M5_server.csv", parse_dates=["time"])
    ny = d.time - pd.Timedelta(hours=7)                # server = NY + 7h
    if tz != "America/New_York":
        ny = (ny.dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT")
                .dt.tz_convert(tz).dt.tz_localize(None))
    d["ny"] = ny                                       # ora locala a bursei (numele istoric ramas "ny")
    d = d.dropna(subset=["ny"])
    d = d[d.ny.dt.weekday < 5]
    d["day"] = d.ny.dt.normalize()
    d["mins"] = d.ny.dt.hour * 60 + d.ny.dt.minute
    d = d[(d.mins >= open_min) & (d.mins <= close_min)]
    d.attrs["open_min"] = open_min
    return d


def news_days():
    """Zile cu NFP (prima vineri din luna), FOMC si CPI aproximate — filtru optional."""
    p = ROOT / "data/research_daily/news_days.json"
    return set(pd.to_datetime(json.loads(p.read_text())).normalize()) if p.exists() else set()


def run(d, sym, or_min, mode, rr):
    sp = SPEC[sym]
    out = []
    n_or = or_min // 5
    for day, g in d.groupby("day", sort=True):
        if g.mins.iloc[0] != d.attrs.get("open_min", 570) or len(g) < n_or + 6:
            continue
        o, h, l, c = (g[k].to_numpy() for k in ("open", "high", "low", "close"))
        spr = g.spread.to_numpy() * sp["point"]
        hi, lo = h[:n_or].max(), l[:n_or].min()
        if mode == "dir":
            if c[n_or - 1] == o[0]:
                continue
            side = 1 if c[n_or - 1] > o[0] else -1
            i0 = n_or
            entry = o[i0] + side * spr[i0] / 2
            sl = lo if side == 1 else hi
        else:
            side = None
            for i in range(n_or, len(o)):
                up, dn = h[i] >= hi, l[i] <= lo
                if up and dn:
                    break
                if up or dn:
                    side = 1 if up else -1
                    lvl = hi if up else lo
                    fill = max(lvl, o[i]) if up else min(lvl, o[i])   # gap -> open
                    entry = fill + side * (sp["slip"] + spr[i] / 2)
                    sl, i0 = (lo if up else hi), i
                    break
            if side is None:
                continue
        risk = abs(entry - sl)
        cost_rt = spr[i0] + sp["slip"] + sp["comm"]
        if risk <= 0 or risk < 2 * cost_rt:
            continue
        tp = entry + side * rr * risk if rr else None
        res, j_exit = None, len(o) - 1
        for j in range(i0, len(o)):
            hit_sl = (l[j] <= sl) if side == 1 else (h[j] >= sl)
            if mode == "brk" and j == i0:
                if hit_sl:
                    res, j_exit = -1.0 - (sp["slip"] + spr[j] / 2) / risk, j
                    break
                continue
            hit_tp = tp is not None and ((h[j] >= tp) if side == 1 else (l[j] <= tp))
            if hit_sl:
                res, j_exit = -1.0 - (sp["slip"] + spr[j] / 2) / risk, j; break
            if hit_tp:
                res, j_exit = rr - (spr[j] / 2) / risk, j; break
        if res is None:
            res = (side * (c[-1] - entry) - spr[-1] / 2) / risk
        res -= sp["comm"] / risk
        out.append(dict(entry_t=day, R=res, outcome="TP" if res > 0 else "SL",
                        risk_usd_minlot=risk * sp["usd_per_unit_minlot"], side=side))
    return pd.DataFrame(out)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    syms = args or ["US500", "EURUSD", "USDJPY"]
    use_news = "--news" in sys.argv
    nd = news_days() if use_news else set()
    rows, keep = [], {}
    for sym in syms:
        d = load(sym)
        if nd:
            d = d[~d.day.isin(nd)]
        for or_min, mode, rr in itertools.product([5, 15, 30], ["brk", "dir"], [2.0, 3.0, None]):
            t = run(d, sym, or_min, mode, rr)
            if len(t) < 30:
                continue
            m = evaluate_trades(t, split_time=SPLIT, n_boot=1000)
            yrs = t.groupby(t.entry_t.dt.year).R.sum()
            rows.append(dict(sym=sym, orb=f"{or_min}m", mode=mode, exit=f"{rr:g}R" if rr else "EOD",
                             n=m["n"], exp=m["expectancy"], train=m["train_exp"], test=m["test_exp"],
                             p_pos=m["prob_positive"], n_star=m["breakeven_trials"],
                             folds_pos=m["frac_positive"], yrs_pos=f"{(yrs > 0).sum()}/{len(yrs)}",
                             risk_minlot_med=t.risk_usd_minlot.median(), verdict=m["verdict"]))
            keep[(sym, or_min, mode, rr)] = t
        print(sym, "gata", file=sys.stderr, flush=True)
    r = pd.DataFrame(rows)
    out = ROOT / f"data/research_daily/orb_m5_results{'_news' if use_news else ''}.csv"
    r.to_csv(out, index=False)
    f = r.copy()
    for k in ("exp", "train", "test", "p_pos", "folds_pos"):
        f[k] = f[k].astype(float).round(3)
    f["risk_minlot_med"] = f.risk_minlot_med.round(2)
    pd.set_option("display.width", 220)
    print(f"Configuratii: {len(r)} ({len(syms)} piete x 18) | filtru stiri: {'DA' if use_news else 'NU'} | split {SPLIT.date()}")
    print(f.sort_values("exp", ascending=False).to_string(index=False))


if __name__ == "__main__":
    main()
