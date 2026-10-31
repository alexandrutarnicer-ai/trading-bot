"""Test exploratoriu Opening Range Breakout (ORB) pe M15, la deschiderea bursei (ora locala a bursei,
DST-corect). NU e cod de productie — doar ca sa vedem daca ideea merita un engine.
Conservator: daca SL si TP sunt atinse in aceeasi bara -> SL. Cost round-trip scazut din fiecare trade."""
import pandas as pd, numpy as np, itertools, sys
D = r"C:\trading-bot\data"
COST = {"EURUSD": 0.00012, "GBPUSD": 0.00015, "USDJPY": 0.015, "XAUUSD": 0.35,
        "US30": 3.0, "US500": 0.6, "GER40": 2.0, "UK100": 1.5}
# (simbol, fus bursa, ora deschidere, ora inchidere fortata)
SETUPS = [
    ("US30",   "America/New_York", "09:30", "15:45"),
    ("US500",  "America/New_York", "09:30", "15:45"),
    ("XAUUSD", "America/New_York", "09:30", "15:45"),
    ("EURUSD", "America/New_York", "09:30", "15:45"),
    ("GBPUSD", "America/New_York", "09:30", "15:45"),
    ("USDJPY", "America/New_York", "09:30", "15:45"),
    ("GER40",  "Europe/Berlin",    "09:00", "17:15"),
    ("UK100",  "Europe/London",    "08:00", "16:15"),
    ("EURUSD", "Europe/London",    "08:00", "16:15"),
    ("GBPUSD", "Europe/London",    "08:00", "16:15"),
]
MIN_RISK_COST = 0  # fara filtru


def load(sym, tz):
    d = pd.read_csv(f"{D}\\{sym}_M15.csv", parse_dates=["time"])
    t = d.time.dt.tz_localize("Europe/Bucharest", ambiguous="NaT", nonexistent="NaT")
    d["lt"] = t.dt.tz_convert(tz)
    d = d.dropna(subset=["lt"])
    d["day"] = d["lt"].dt.date
    d["hm"] = d["lt"].dt.strftime("%H:%M")
    return d[d["lt"].dt.weekday < 5]


def run(d, sym, open_hm, close_hm, n_or, mode, rr):
    cost = COST[sym]
    out = []
    for day, g in d.groupby("day", sort=True):
        g = g[(g.hm >= open_hm) & (g.hm <= close_hm)]
        if len(g) < n_or + 4 or g.hm.iloc[0] != open_hm:
            continue
        orb = g.iloc[:n_or]
        hi, lo = orb.high.max(), orb.low.min()
        rest = g.iloc[n_or:]
        if hi - lo <= 0:
            continue
        if mode == "dir":   # directia lumanarii OR, intrare la open-ul barei urmatoare
            o, c = orb.open.iloc[0], orb.close.iloc[-1]
            if c == o:
                continue
            side = 1 if c > o else -1
            entry = rest.open.iloc[0]
            sl = lo if side == 1 else hi
            start = 0
        else:               # breakout: primul nivel atins (stop order)
            side = None
            for i, b in enumerate(rest.itertuples()):
                up, dn = b.high >= hi, b.low <= lo
                if up and dn:
                    side = None; break     # ambiguu -> sarim ziua
                if up: side, entry, sl, start = 1, hi, lo, i; break
                if dn: side, entry, sl, start = -1, lo, hi, i; break
            if side is None:
                continue
        risk = abs(entry - sl)
        if risk <= 0:
            continue
        tp = entry + side * rr * risk if rr else None
        res = None
        bars = rest.iloc[start:]
        for k, b in enumerate(bars.itertuples()):
            if mode == "brk" and k == 0:
                # in bara de intrare verificam doar SL (conservator)
                if (side == 1 and b.low <= sl) or (side == -1 and b.high >= sl):
                    res = -1.0; break
                continue
            hit_sl = b.low <= sl if side == 1 else b.high >= sl
            hit_tp = tp is not None and (b.high >= tp if side == 1 else b.low <= tp)
            if hit_sl:
                res = -1.0; break
            if hit_tp:
                res = rr; break
        if res is None:
            res = side * (bars.close.iloc[-1] - entry) / risk
        out.append((pd.Timestamp(day), res - cost / risk))
    return pd.DataFrame(out, columns=["day", "r"])


def summ(t):
    if len(t) < 30:
        return None
    t = t.sort_values("day")
    cut = t.day.iloc[int(len(t) * 0.7)]
    tr, te = t[t.day < cut], t[t.day >= cut]
    yrs = t.groupby(t.day.dt.year).r.sum()
    return dict(n=len(t), exp=t.r.mean(), win=(t.r > 0).mean(), train=tr.r.mean(), test=te.r.mean(),
                yrs_pos=f"{(yrs > 0).sum()}/{len(yrs)}", tstat=t.r.mean() / (t.r.std() / np.sqrt(len(t))))


rows = []
for sym, tz, oh, ch in SETUPS:
    d = load(sym, tz)
    for n_or, mode, rr in itertools.product([1, 2], ["dir", "brk"], [1.0, 2.0, 3.0, None]):
        s = summ(run(d, sym, oh, ch, n_or, mode, rr))
        if s:
            rows.append(dict(sym=sym, open=f"{tz.split('/')[1]} {oh}", orb=f"{15*n_or}m", mode=mode,
                             rr=rr or "EOD", **s))
    print(sym, tz, "gata", file=sys.stderr)
r = pd.DataFrame(rows)
r.to_csv(r"C:\Users\alext\AppData\Local\Temp\claude\c--trading-bot\d3b1af9f-ad7b-4c8d-8ba0-3fb6876471db\scratchpad\orb_results.csv", index=False)
pd.set_option("display.width", 200)
fmt = r.copy()
for c in ["exp", "train", "test", "tstat"]: fmt[c] = fmt[c].round(3)
fmt["win"] = (fmt.win * 100).round(0)
print(f"Configuratii testate: {len(r)}")
print("\nTOP 15 dupa min(train,test):")
fmt["robust"] = r[["train", "test"]].min(axis=1).round(3)
print(fmt.sort_values("robust", ascending=False).head(15).to_string(index=False))
print("\nCel mai bun per piata/deschidere:")
print(fmt.sort_values("robust", ascending=False).groupby(["sym", "open"]).head(1).to_string(index=False))
