"""
Candidati pe bare D1 (MT5, 2015 → azi). Semnal la INCHIDEREA zilei t, intrare la DESCHIDEREA zilei t+1 (fara lookahead),
costuri: spread live + 25% slippage + swap pe fiecare noapte (common.trade_R).

  A  rsi2      — mean reversion long-only (Connors): close > SMA200, RSI(2) < 10 → cumpara; iesire close > SMA5,
                 max 10 zile, stop de urgenta 2,5×ATR. R = 2,5×ATR.
  B  tom       — turn of the month: intrare la deschiderea ultimei zile de tranzactionare a lunii, iesire la inchiderea
                 zilei 3 din luna noua, stop 2×ATR. R = 2×ATR.
  C  donchian  — trend following: rupere 55 zile → intrare; iesire la rupere 20 zile opusa; stop initial 2×ATR(20).
  E  eurgbp_mr — Special Engine v2 (pairs trading GBP/EUR = EURGBP): z = (close − SMA20) / STD20; z < −2 long, z > 2 short,
                 iesire z trece de 0, max 15 zile, stop 1×ATR peste extrem (R = 2×ATR).
"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

INDICES = ["US500", "US30", "USTEC", "DE40", "UK100", "STOXX50", "AUS200"]
TREND_U = ["US500", "US30", "USTEC", "DE40", "UK100", "STOXX50", "AUS200", "XAUUSD", "XAGUSD", "XTIUSD",
           "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD", "EURGBP", "EURJPY", "GBPJPY",
           "AUDJPY"]


def ind(df):
    df = df.copy()
    c = df["close"]
    df["sma200"] = c.rolling(200).mean()
    df["sma5"] = c.rolling(5).mean()
    df["sma20"] = c.rolling(20).mean()
    df["std20"] = c.rolling(20).std()
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / 2, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / 2, adjust=False).mean()
    df["rsi2"] = 100 - 100 / (1 + up / dn.replace(0, np.nan))
    tr = pd.concat([df["high"] - df["low"], (df["high"] - c.shift()).abs(), (df["low"] - c.shift()).abs()], axis=1).max(axis=1)
    df["atr"] = tr.ewm(alpha=1 / 14, adjust=False).mean()
    df["atr20"] = tr.rolling(20).mean()
    df["hh55"] = df["high"].rolling(55).max()
    df["ll55"] = df["low"].rolling(55).min()
    df["hh20"] = df["high"].rolling(20).max()
    df["ll20"] = df["low"].rolling(20).min()
    return df


def rsi2(sym, df):
    rows, i, n = [], 201, len(df)
    while i < n - 1:
        r = df.iloc[i]
        if r["close"] > r["sma200"] and r["rsi2"] < 10:
            e_i = i + 1
            entry = df["open"].iat[e_i]
            risk = 2.5 * r["atr"]
            stop = entry - risk
            x_i, exit_ = None, None
            for k in range(e_i, min(n, e_i + 11)):
                if df["low"].iat[k] <= stop:
                    x_i, exit_ = k, min(stop, df["open"].iat[k]); break
                if df["close"].iat[k] > df["sma5"].iat[k] or k == e_i + 9:
                    if k + 1 < n:
                        x_i, exit_ = k + 1, df["open"].iat[k + 1]
                    else:
                        x_i, exit_ = k, df["close"].iat[k]
                    break
            if x_i is None:
                break
            t_in, t_out = df["time"].iat[e_i], df["time"].iat[x_i]
            rows.append({"sym": sym, "entry_t": t_in, "exit_t": t_out, "d": 1,
                         "R": C.trade_R(sym, 1, entry, exit_, risk, t_in, t_out)})
            i = x_i
        i += 1
    return rows


def tom(sym, df):
    rows = []
    df = df.copy()
    df["ym"] = df["time"].dt.to_period("M")
    last_idx = df.groupby("ym").tail(1).index        # ultima zi de tranzactionare a fiecarei luni
    for li in last_idx:
        if li < 30 or li + 3 >= len(df):
            continue
        entry = df["open"].iat[li]
        risk = 2.0 * df["atr"].iat[li - 1]
        stop = entry - risk
        x_i, exit_ = li + 3, df["close"].iat[li + 3]
        for k in range(li, li + 4):
            if df["low"].iat[k] <= stop:
                x_i, exit_ = k, min(stop, df["open"].iat[k]); break
        t_in, t_out = df["time"].iat[li], df["time"].iat[x_i]
        rows.append({"sym": sym, "entry_t": t_in, "exit_t": t_out, "d": 1,
                     "R": C.trade_R(sym, 1, entry, exit_, risk, t_in, t_out)})
    return rows


def donchian(sym, df, n_in=55, n_out=20):
    rows, i, n = [], 60, len(df)
    hh, ll = df["high"].rolling(n_in).max().shift(1), df["low"].rolling(n_in).min().shift(1)
    xh, xl = df["high"].rolling(n_out).max().shift(1), df["low"].rolling(n_out).min().shift(1)
    while i < n - 1:
        c = df["close"].iat[i]
        d = 1 if c > hh.iat[i] else (-1 if c < ll.iat[i] else 0)
        if d:
            e_i = i + 1
            entry = df["open"].iat[e_i]
            risk = 2.0 * df["atr20"].iat[i]
            stop = entry - d * risk
            x_i = exit_ = None
            for k in range(e_i, n):
                if (d == 1 and df["low"].iat[k] <= stop) or (d == -1 and df["high"].iat[k] >= stop):
                    o = df["open"].iat[k]
                    x_i, exit_ = k, (min(stop, o) if d == 1 else max(stop, o)); break
                ck = df["close"].iat[k]
                if (d == 1 and ck < xl.iat[k]) or (d == -1 and ck > xh.iat[k]):
                    x_i, exit_ = (k + 1, df["open"].iat[k + 1]) if k + 1 < n else (k, ck); break
            if x_i is None:
                x_i, exit_ = n - 1, df["close"].iat[n - 1]
            t_in, t_out = df["time"].iat[e_i], df["time"].iat[x_i]
            rows.append({"sym": sym, "entry_t": t_in, "exit_t": t_out, "d": d,
                         "R": C.trade_R(sym, d, entry, exit_, risk, t_in, t_out)})
            i = x_i
        i += 1
    return rows


def zmr(sym, df, z_in=2.0, max_days=15):
    rows, i, n = [], 25, len(df)
    z = (df["close"] - df["sma20"]) / df["std20"]
    while i < n - 1:
        zi = z.iat[i]
        d = 1 if zi < -z_in else (-1 if zi > z_in else 0)
        if d:
            e_i = i + 1
            entry = df["open"].iat[e_i]
            risk = 2.0 * df["atr"].iat[i]
            stop = entry - d * risk
            x_i = exit_ = None
            for k in range(e_i, min(n, e_i + max_days)):
                if (d == 1 and df["low"].iat[k] <= stop) or (d == -1 and df["high"].iat[k] >= stop):
                    o = df["open"].iat[k]
                    x_i, exit_ = k, (min(stop, o) if d == 1 else max(stop, o)); break
                if (d == 1 and z.iat[k] >= 0) or (d == -1 and z.iat[k] <= 0) or k == e_i + max_days - 1:
                    x_i, exit_ = (k + 1, df["open"].iat[k + 1]) if k + 1 < n else (k, df["close"].iat[k]); break
            if x_i is None:
                break
            t_in, t_out = df["time"].iat[e_i], df["time"].iat[x_i]
            rows.append({"sym": sym, "entry_t": t_in, "exit_t": t_out, "d": d,
                         "R": C.trade_R(sym, d, entry, exit_, risk, t_in, t_out)})
            i = x_i
        i += 1
    return rows


def main():
    data = {s: ind(C.fetch(s, "D1", 3000)) for s in set(INDICES + TREND_U)}
    out = {}
    def run(label, rows):
        r = C.report(rows, label=label)
        out[label] = r
        print(C.fmt(r), flush=True)
        return r

    print("── A. RSI(2) mean reversion, long-only, indici")
    allA = []
    for s in INDICES:
        rows = rsi2(s, data[s]); allA += rows; run(f"A rsi2 {s}", rows)
    run("A rsi2 PORTOFOLIU indici", allA)
    print("── B. Turn of the month, indici")
    allB = []
    for s in INDICES:
        rows = tom(s, data[s]); allB += rows; run(f"B tom {s}", rows)
    run("B tom PORTOFOLIU indici", allB)
    print("── C. Donchian 55/20 trend following")
    allC = []
    for s in TREND_U:
        rows = donchian(s, data[s]); allC += rows; run(f"C donch {s}", rows)
    run("C donch PORTOFOLIU 21 piete", allC)
    print("── E. Special v2: EURGBP mean reversion (z-score D1)")
    for zin in (1.5, 2.0, 2.5):
        run(f"E eurgbp z{zin}", zmr("EURGBP", data["EURGBP"], zin))
    json.dump(out, open(os.path.join(C.OUT, "daily_candidates.json"), "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
