"""
Validarea DURA a candidatului pentru Special Engine (inainte de implementare), 2026-11-05.

Candidati (din cercetarea din 04.11, docs/SPECIAL_ENGINE_RESEARCH.md):
  A = portofoliu intraday ADAPTIV walk-forward (ORB 10 piete × 6 variante + NOISE 8 piete), doar in zilele NR4
  B = „Beat the Market” (noise area) pe USTEC, parametrii din lucrare, FARA nicio selectie (pre-inregistrat)
Verificari:
  1. look-ahead in selectia trimestriala: selectia trimestrului q foloseste DOAR trade-uri cu intrare < q (asertie)
  2. sensibilitate: lookback {24, 30, 36, 42} × t_min {1.25, 1.5, 1.75, 2.0} × filtru {NR4, NR5, NR7, fara}
  3. stres costuri: −0,03 / −0,05 / −0,10 R / trade
  4. regimuri: pe ani si pe tercile de volatilitate (ATR D1 US500)
  5. Monte Carlo (bootstrap pe luni, 10 000 traiectorii, 12 luni) la 0,5% risc: P(an negativ), P(DD > 20%)
  6. benchmark: ORB pe TOATE componentele fara selectie (media naiva) + noise pe toate pietele
Rezultat: data/research_special/validate_special.json + .log
"""
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import common as C  # noqa: E402
from walkforward import load, monthly_pct  # noqa: E402


def nr_flags(syms, n):
    out = {}
    for s in syms:
        d = C.fetch(s, "D1", 3000).copy()
        d["rng"] = d.high - d.low
        d["flag"] = (d.rng <= d.rng.rolling(n).min()).shift(1) if n else True
        d["day"] = d.time.dt.normalize()
        out[s] = d.set_index("day")["flag"]
    return out


def attach(t, flags):
    t = t.copy()
    t["day"] = t.entry_t.dt.normalize()
    parts = []
    for s, g in t.groupby("sym"):
        f = flags[s].reindex(g["day"]).to_numpy() if s in flags else np.ones(len(g), bool)
        parts.append(g.assign(flag=f))
    return pd.concat(parts)


def walk_checked(t, lookback, t_min, min_n=150, min_mean=0.05, max_comp=6):
    """walkforward.walk + ASERTIE anti look-ahead: fiecare trimestru vede doar trade-uri intrate inainte de inceputul lui."""
    q0 = (t.entry_t.min() + pd.DateOffset(months=lookback)).to_period("Q").start_time
    picked, log = [], []
    for qs in pd.date_range(q0, t.entry_t.max(), freq="QS"):
        qe = qs + pd.DateOffset(months=3)
        hist = t[(t.entry_t >= qs - pd.DateOffset(months=lookback)) & (t.entry_t < qs)]
        assert hist.entry_t.max() < qs if len(hist) else True, "LOOK-AHEAD in selectie"
        g = hist.groupby("comp")["R"].agg(["count", "mean", "std"])
        g = g[g["count"] >= min_n]
        g["t"] = g["mean"] / (g["std"] / np.sqrt(g["count"]))
        g = g[(g["t"] >= t_min) & (g["mean"] >= min_mean)].sort_values("t", ascending=False)
        g["sym"] = [c.split(":")[1] for c in g.index]
        sel = g.drop_duplicates("sym").head(max_comp)
        log.append({"q": str(qs.date()), "comp": list(sel.index)})
        if len(sel):
            picked.append(t[(t.entry_t >= qs) & (t.entry_t < qe) & t.comp.isin(sel.index)])
    return (pd.concat(picked) if picked else t.iloc[0:0]), log


def summary(df, label):
    r = C.report(df.to_dict("records"), label=label)
    m5 = monthly_pct(df, 0.5) if len(df) else {}
    return {k: r.get(k) for k in ("n", "per_month", "exp_R", "win_rate", "max_dd_R", "train", "test", "folds_pos",
                                  "p_edge", "verdict", "pct_months_pos", "by_year")} | {"at_0.5pct": m5}


def mc(df, risk=0.5, n=10000, months=12, seed=1):
    m = df.groupby(df.exit_t.dt.to_period("M"))["R"].sum()
    m = m.reindex(pd.period_range(m.index.min(), m.index.max(), freq="M"), fill_value=0).to_numpy() * risk
    rng = np.random.default_rng(seed)
    paths = rng.choice(m, size=(n, months), replace=True)
    eq = paths.cumsum(axis=1)
    dd = (eq - np.maximum.accumulate(np.maximum(eq, 0), axis=1)).min(axis=1)
    return {"p_year_negative": round(float((eq[:, -1] < 0).mean() * 100), 1),
            "median_year_pct": round(float(np.median(eq[:, -1])), 1),
            "p5_year_pct": round(float(np.percentile(eq[:, -1], 5)), 1),
            "p_dd_gt_20pct": round(float((dd < -20).mean() * 100), 1),
            "p_dd_gt_10pct": round(float((dd < -10).mean() * 100), 1),
            "p_month_2_5pct": round(float(((m >= 2) & (m <= 5)).mean() * 100), 1),
            "p_month_ge_2pct": round(float((m >= 2).mean() * 100), 1)}


def main():
    t = load()
    syms = sorted(t.sym.unique())
    out, lines = {}, []

    def say(s):
        print(s, flush=True)
        lines.append(s)

    flags = {n: nr_flags(syms, n) for n in (4, 5, 7)}
    say("── 2. sensibilitate (A = walk-forward, componente ORB + NOISE)")
    grid = {}
    for filt in (4, 5, 7, 0):
        tf = attach(t, flags[filt]) if filt else t.assign(flag=True)
        tf = tf[tf.flag == True]                                     # noqa: E712
        for lb in (24, 30, 36, 42):
            for tm in (1.25, 1.5, 1.75, 2.0):
                oos, _ = walk_checked(tf, lb, tm, min_n=60 if filt else 150)
                key = f"NR{filt or '-'} lb{lb} t{tm}"
                if len(oos) < 30:
                    grid[key] = {"n": len(oos)}
                    continue
                s = summary(oos, key)
                grid[key] = s
                say(f"  {key:18} n={s['n']:5} exp={s['exp_R']:+.3f} test={s['test']:+.3f} DD={s['max_dd_R']} "
                    f"luni+={s['pct_months_pos']}% {s['verdict']} | 0,5%: {s['at_0.5pct'].get('luna_medie')}%/luna DD {s['at_0.5pct'].get('DD_max')}%")
    out["grid"] = grid
    pos = [v for v in grid.values() if v.get("n", 0) >= 30]
    say(f"  → configuratii pozitive: {sum(1 for v in pos if v['exp_R'] > 0)}/{len(pos)}; cu test > 0: "
        f"{sum(1 for v in pos if (v['test'] or -1) > 0)}/{len(pos)}; KEEP: {sum(1 for v in pos if v['verdict'] == 'KEEP')}")
    for filt in (4, 5, 7, 0):
        vs = [v for k, v in grid.items() if k.startswith(f"NR{filt or '-'} ") and v.get("n", 0) >= 30]
        if vs:
            say(f"  filtru NR{filt or '-'}: exp median {np.median([v['exp_R'] for v in vs]):+.3f}, test median "
                f"{np.median([v['test'] for v in vs]):+.3f}, %/luna median la 0,5% {np.median([v['at_0.5pct']['luna_medie'] for v in vs]):.2f}")

    # candidatul ales anterior + varianta „centrala” a grilei
    tf4 = attach(t, flags[4])
    tf4 = tf4[tf4.flag == True]                                      # noqa: E712
    A, logA = walk_checked(tf4, 36, 1.5, min_n=60)
    say("── 1. look-ahead: asertia a trecut pe toate trimestrele (nicio exceptie)")
    say("── 3. stres costuri (A = NR4 lb36 t1.5)")
    out["A"] = summary(A, "A")
    for c in (0.0, 0.03, 0.05, 0.10):
        s = summary(A.assign(R=A.R - c), f"A −{c}")
        out[f"A_cost_{c}"] = s
        say(f"  −{c:.2f}R/trade: exp={s['exp_R']:+.3f} test={s['test']:+.3f} {s['verdict']} | 0,5%: {s['at_0.5pct']['luna_medie']}%/luna, DD {s['at_0.5pct']['DD_max']}%")
    say("── B. noise area USTEC (fara selectie) + combinat A+B")
    B = t[t.comp == "NOISE:USTEC"]
    out["B"] = summary(B, "B")
    AB = pd.concat([A, B[B.entry_t >= A.entry_t.min()]])
    out["AB"] = summary(AB, "A+B")
    for k in ("A", "B", "AB"):
        s = out[k]
        say(f"  {k:3} n={s['n']} {s['per_month']}/luna exp={s['exp_R']:+.3f} train={s['train']:+.3f} test={s['test']:+.3f} "
            f"DD={s['max_dd_R']}R {s['verdict']} luni+={s['pct_months_pos']}% | 0,5%: {s['at_0.5pct']}")
    say("── 4. regimuri de volatilitate (ATR D1 US500, tercile)")
    d = C.fetch("US500", "D1", 3000).copy()
    tr = pd.concat([d.high - d.low, (d.high - d.close.shift()).abs(), (d.low - d.close.shift()).abs()], axis=1).max(axis=1)
    d["atrp"] = (tr.rolling(20).mean() / d.close).shift(1)
    d["day"] = d.time.dt.normalize()
    q = d["atrp"].quantile([1 / 3, 2 / 3]).to_numpy()
    reg = pd.cut(d.set_index("day")["atrp"], [-1, q[0], q[1], 9], labels=["vol scazuta", "vol medie", "vol mare"])
    for k, df in (("A", A), ("B", B), ("AB", AB)):
        rr = df.assign(reg=reg.reindex(df.entry_t.dt.normalize()).to_numpy()).groupby("reg", observed=True)["R"].agg(["count", "mean"])
        out[f"regime_{k}"] = {str(i): [int(r["count"]), round(float(r["mean"]), 3)] for i, r in rr.iterrows()}
        say(f"  {k}: {out[f'regime_{k}']}")
    say("── 5. Monte Carlo 12 luni la 0,5% risc / trade (bootstrap pe luni)")
    for k, df in (("A", A), ("B", B), ("AB", AB)):
        out[f"mc_{k}"] = mc(df)
        say(f"  {k}: {out[f'mc_{k}']}")
    out["mc_AB_1pct"] = mc(AB, risk=1.0)
    say(f"  AB la 1%: {out['mc_AB_1pct']}")
    say("── 6. benchmark")
    naive = t[t.comp.str.startswith("ORB") & (t.entry_t >= A.entry_t.min())]
    out["bench_orb_all"] = summary(naive, "toate ORB")
    say(f"  ORB toate componentele fara selectie: exp={out['bench_orb_all']['exp_R']:+.3f} {out['bench_orb_all']['verdict']}")
    nz = t[t.comp.str.startswith("NOISE") & (t.entry_t >= A.entry_t.min())]
    out["bench_noise_all"] = summary(nz, "toate NOISE")
    say(f"  NOISE toate pietele: exp={out['bench_noise_all']['exp_R']:+.3f} {out['bench_noise_all']['verdict']}")
    out["selection_log_A"] = logA
    json.dump(out, open(os.path.join(C.OUT, "validate_special.json"), "w"), indent=1, default=str)
    open(os.path.join(C.OUT, "validate_special.log"), "w", encoding="utf-8").write("\n".join(lines))


if __name__ == "__main__":
    main()
