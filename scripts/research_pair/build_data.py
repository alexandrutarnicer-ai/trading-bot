"""Date pentru testul de perechi GBPUSD / EURUSD: M1 din data/<SYM>_M1.csv (din 2021) completat din MT5 (doar citire)
pana azi; M5 / M15 / M30 / H1 derivate din ACELASI M1 (grila serverului). Iesire: data/research_pair/ (gitignored)."""
import os, sys
from datetime import datetime, timezone
import pandas as pd
import MetaTrader5 as mt5

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "data", "research_pair")
os.makedirs(OUT, exist_ok=True)
assert mt5.initialize()
for sym in ("GBPUSD", "EURUSD"):
    old = pd.read_csv(os.path.join(ROOT, "data", f"{sym}_M1.csv"), parse_dates=["time"])
    start = old["time"].max() - pd.Timedelta(days=2)
    r = mt5.copy_rates_range(sym, mt5.TIMEFRAME_M1, start.to_pydatetime().replace(tzinfo=timezone.utc),
                             datetime.now(timezone.utc))
    new = pd.DataFrame(r)
    new["time"] = pd.to_datetime(new["time"], unit="s")          # ora serverului, ca CSV-urile
    m1 = pd.concat([old, new[old.columns]]).drop_duplicates("time", keep="last").sort_values("time").reset_index(drop=True)
    m1.to_csv(os.path.join(OUT, f"{sym}_M1.csv"), index=False)
    print(sym, "M1", len(m1), m1["time"].min(), "->", m1["time"].max(), "| din MT5:", len(new))
    s = m1.set_index("time")
    for tf, rule in (("M5", "5min"), ("M15", "15min"), ("M30", "30min"), ("H1", "1h")):
        g = s.resample(rule, label="left", closed="left").agg(
            {"open": "first", "high": "max", "low": "min", "close": "last", "tick_volume": "sum", "spread": "max",
             "real_volume": "sum"}).dropna(subset=["open"]).reset_index()
        g.to_csv(os.path.join(OUT, f"{sym}_{tf}.csv"), index=False)
        print("  ", tf, len(g))
