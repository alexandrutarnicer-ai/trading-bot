"""Profil orar (ora RO) pe ultimii ~3 ani: range mediu M15, volum tick, raport cost/range."""
import pandas as pd, numpy as np
D = r"C:\trading-bot\data"
# cost round-trip aproximativ (spread+comision) in unitati de pret — ICMarkets Raw, estimare conservatoare
COST = {"EURUSD": 0.00012, "GBPUSD": 0.00015, "USDJPY": 0.015, "XAUUSD": 0.35,
        "US30": 3.0, "US500": 0.6, "GER40": 2.0, "UK100": 1.5}
rows = []
for sym, cost in COST.items():
    d = pd.read_csv(f"{D}\\{sym}_M15.csv", parse_dates=["time"])
    d = d[d.time >= "2023-06-01"]
    d = d[d.time.dt.weekday < 5]
    d["rng"] = d.high - d.low
    d["h"] = d.time.dt.hour
    g = d.groupby("h").agg(rng=("rng", "mean"), vol=("tick_volume", "mean"))
    g["rng_rel"] = g.rng / g.rng.mean()
    g["cost_pct"] = cost / (g.rng * 4) * 100   # cost vs range orar (4 bare M15 ~ aprox. range orar)
    for h, r in g.iterrows():
        rows.append(dict(sym=sym, h=h, rng_rel=round(r.rng_rel, 2), vol_rel=round(r.vol / g.vol.mean(), 2),
                         cost_pct=round(r.cost_pct, 1)))
t = pd.DataFrame(rows)
p = t.pivot(index="h", columns="sym", values="rng_rel")
print("RANGE M15 relativ la media zilei (1.00 = medie), ora RO, iun 2023 - iun 2026\n")
print(p.to_string())
print("\nTOP 4 ore / piata (range):")
for s in COST:
    top = t[t.sym == s].nlargest(4, "rng_rel")
    print(f"  {s:7s}", ", ".join(f"{int(r.h):02d}h ({r.rng_rel}x, cost {r.cost_pct}%)" for _, r in top.iterrows()))
t.to_csv(r"C:\Users\alext\AppData\Local\Temp\claude\c--trading-bot\d3b1af9f-ad7b-4c8d-8ba0-3fb6876471db\scratchpad\hour_profile.csv", index=False)
