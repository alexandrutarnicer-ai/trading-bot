"""
Motor de backtest v1 - strategie pullback in trend (buy/sell stop)
==================================================================
Citeste config.json, incarca CSV-urile M30 (trend) si M15 (intrare) pentru
fiecare pereche, simuleaza strategia cu costuri si dimensionare de pozitie,
si afiseaza statisticile: nr. tranzactii, rata de castig, expectancy (R),
randament total si drawdown maxim.

Cerinte:  pip install pandas numpy
Rulare:   python backtest.py
"""

import os
import json
import numpy as np
import pandas as pd

from strategy.indicators import ema, rsi, atr
from strategy.structure import mark_swings, detect_setup
from strategy.signals import pip_size, count_optional, reward_R

# ---- cai (relative la radacina proiectului) -------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
if os.path.isdir(os.path.join(_HERE, "config")):
    ROOT = _HERE
elif os.path.isdir(os.path.join(os.path.dirname(_HERE), "config")):
    ROOT = os.path.dirname(_HERE)
else:
    ROOT = _HERE
CONFIG    = os.path.join(ROOT, "config", "standard_profile.json")
DATA_DIR  = os.path.join(ROOT, "data")

# ---- presupuneri de cost (pips) - calibrabile -----------------------------
SPREAD_PIPS = {"EURUSD": 0.5, "GBPUSD": 0.8}   # conservator; raw e mai mic
PIP_VALUE_PER_LOT_USD = 10.0                   # pt perechi cotate in USD, 1 lot
SYMBOLS_V1 = ["EURUSD", "GBPUSD"]


# ---- incarcare + pregatire date -------------------------------------------
def load_symbol(symbol, cfg):
    m15 = pd.read_csv(os.path.join(DATA_DIR, f"{symbol}_M15.csv"), parse_dates=["time"])
    m30 = pd.read_csv(os.path.join(DATA_DIR, f"{symbol}_M30.csv"), parse_dates=["time"])

    # trend pe M30
    m30["ema_trend"] = ema(m30["close"], cfg["trend_filter"]["ema_trend_period"])
    m30["trend"] = np.where(m30["close"] > m30["ema_trend"], 1,
                    np.where(m30["close"] < m30["ema_trend"], -1, 0))

    # indicatori pe M15
    per = cfg["optional_criteria"]["ema_alignment"]["periods"]   # [8,20,50]
    m15["ema_fast"]   = ema(m15["close"], per[0])
    m15["ema_mid"]    = ema(m15["close"], per[1])
    m15["ema_slow"]   = ema(m15["close"], per[2])
    m15["rsi"]        = rsi(m15["close"], cfg["optional_criteria"]["rsi"]["period"])
    m15["atr"]        = atr(m15, 14)
    m15 = mark_swings(m15, cfg["structure"]["swing_lookback_N"])

    # aliniaza trendul M30 la fiecare bara M15 (ultimul M30 inchis)
    m15 = pd.merge_asof(m15.sort_values("time"),
                        m30[["time", "trend"]].sort_values("time"),
                        on="time", direction="backward")
    return m15.reset_index(drop=True)   # index = pozitie (0..n-1)


# ---- backtest pentru o pereche --------------------------------------------
def backtest_symbol(symbol, cfg):
    df = load_symbol(symbol, cfg)
    pip = pip_size(symbol)
    buf = 2 * pip                              # buffer 2 pips
    spread = SPREAD_PIPS.get(symbol, 1.0) * pip
    comm = cfg["costs"]["commission_per_lot_round_turn_usd"]
    risk_pct = cfg["account"]["risk_per_trade_pct"] / 100.0
    risk_pct_all = cfg["account"].get("risk_per_trade_pct_all_criteria",
                                      cfg["account"]["risk_per_trade_pct"]) / 100.0
    sh, eh = cfg["session"]["start_hour"], cfg["session"]["end_hour"]
    max_trades = cfg["risk_management"]["max_trades_per_day"]
    max_losses = cfg["risk_management"]["max_consecutive_losses"]
    expire_bars = 4

    balance = cfg["account"]["starting_balance"]
    equity_curve = [balance]
    equity_timeline = []
    trades = []
    setups_detected = 0

    day = None
    trades_today = 0
    consec_losses = 0
    pending = None     # ordin armat in asteptare
    busy_until = -1    # indexul barei pana la care o pozitie e inca deschisa

    n = len(df)
    for j in range(60, n):
        row = df.iloc[j]
        t = row["time"]

        # reset zilnic
        if day != t.date():
            day = t.date()
            trades_today = 0
            consec_losses = 0
            pending = None   # anulam pending neatins peste noapte/sesiune

        # o singura pozitie per pereche: cat timp una e deschisa, nu armam/intram nimic
        if j <= busy_until:
            continue

        in_session = (sh <= t.hour < eh)

        # 1) daca avem ordin pending, verificam trigger / invalidare / expirare
        if pending:
            d = pending["dir"]
            # invalidare structurala
            if (d == 1 and row["low"] < pending["invalidate"]) or \
               (d == -1 and row["high"] > pending["invalidate"]):
                pending = None
            elif j - pending["armed_at"] > expire_bars:
                pending = None
            else:
                triggered = (d == 1 and row["high"] >= pending["entry"]) or \
                            (d == -1 and row["low"]  <= pending["entry"])
                if triggered:
                    res = simulate_trade(df, j, pending, spread, pip,
                                         PIP_VALUE_PER_LOT_USD, comm, symbol)
                    balance += res["pnl_usd"]
                    equity_curve.append(balance)
                    equity_timeline.append({"time": res["exit_time"], "balance": round(balance, 2)})
                    trades.append(res)
                    trades_today += 1
                    consec_losses = consec_losses + 1 if res["pnl_usd"] < 0 else 0
                    busy_until = res["exit_j"]
                    pending = None
            continue

        # 2) guardrails + sesiune pentru a arma ceva nou
        if not in_session or trades_today >= max_trades or consec_losses >= max_losses:
            continue
        if row["trend"] == 0 or pd.isna(row["trend"]):
            continue

        direction = int(row["trend"])
        found = detect_setup(df, j, direction)
        if found is None:
            continue
        ext, _ = found
        setups_detected += 1

        # construim ordinul stop
        if direction == 1:
            entry = row["high"] + buf
            sl = ext - buf
        else:
            entry = row["low"] - buf
            sl = ext + buf
        risk_dist = abs(entry - sl)
        if risk_dist <= 0:
            continue

        n_opt = count_optional(row, direction, cfg)
        R = reward_R(n_opt, cfg)
        tp = entry + direction * risk_dist * R

        rp = risk_pct_all if n_opt >= 2 else risk_pct
        risk_usd = balance * rp
        sl_pips = risk_dist / pip
        lots = risk_usd / (sl_pips * PIP_VALUE_PER_LOT_USD)
        lots = np.floor(lots / 0.01) * 0.01     # pas de 0.01
        if lots < 0.01:
            continue

        pending = {"dir": direction, "entry": entry, "sl": sl, "tp": tp,
                   "lots": lots, "R": R, "invalidate": ext, "armed_at": j,
                   "time": t, "risk_usd": risk_usd}

    return summarize(symbol, trades, equity_curve, equity_timeline, setups_detected)


def simulate_trade(df, j, p, spread, pip, pip_val, comm, symbol):
    """Parcurge barele de la j inainte; intoarce primul exit (SL sau TP)."""
    d = p["dir"]
    entry = p["entry"] + d * spread          # platim spread la intrare

    def make(exit_price, outcome, k):
        pnl_price = (exit_price - entry) * d
        pnl_usd = (pnl_price / pip) * pip_val * p["lots"] - comm * p["lots"]
        return {"symbol": symbol, "time": p["time"], "exit_time": df.iloc[k]["time"],
                "dir": d, "lots": p["lots"], "R": p["R"],
                "entry": round(p["entry"], 5), "sl": round(p["sl"], 5),
                "tp": round(p["tp"], 5), "risk_usd": round(p["risk_usd"], 2),
                "outcome": outcome, "pnl_usd": round(pnl_usd, 2), "exit_j": k}

    end = min(j + 400, len(df))
    for k in range(j, end):
        bar = df.iloc[k]
        hit_sl = (d == 1 and bar["low"] <= p["sl"]) or (d == -1 and bar["high"] >= p["sl"])
        hit_tp = (d == 1 and bar["high"] >= p["tp"]) or (d == -1 and bar["low"] <= p["tp"])
        if hit_sl:               # conservator: daca ambele in aceeasi bara, SL primul
            return make(p["sl"], "loss", k)
        if hit_tp:
            return make(p["tp"], "win", k)
    # nu a atins nici SL nici TP in fereastra -> inchis la ultimul close
    return make(df.iloc[end - 1]["close"], "timeout", end - 1)


# ---- statistici ------------------------------------------------------------
def summarize(symbol, trades, equity, equity_timeline, setups):
    if not trades:
        print(f"\n=== {symbol} ===")
        print(f"  Setup-uri detectate: {setups} | Tranzactii: 0")
        return
    df = pd.DataFrame(trades)
    wins = (df["outcome"] == "win").sum()
    losses = (df["outcome"] == "loss").sum()
    wr = wins / len(df) * 100
    start, end = equity[0], equity[-1]
    ret = (end - start) / start * 100
    eq = np.array(equity)
    dd = ((eq - np.maximum.accumulate(eq)) / np.maximum.accumulate(eq)).min() * 100

    df["R_realizat"] = df["pnl_usd"] / df["risk_usd"]
    expectancy = df["R_realizat"].mean()
    avg_win = df.loc[df["outcome"] == "win", "R_realizat"].mean()
    avg_loss = df.loc[df["outcome"] == "loss", "R_realizat"].mean()

    print(f"\n=== {symbol} ===")
    print(f"  Setup-uri detectate : {setups}")
    print(f"  Tranzactii          : {len(df)}  (W:{wins} / L:{losses})")
    print(f"  Rata de castig      : {wr:.1f}%")
    print(f"  Expectancy/trade    : {expectancy:+.3f} R")
    print(f"  Castig mediu        : {avg_win:+.2f} R | Pierdere medie: {avg_loss:+.2f} R")
    print(f"  Balanta finala      : {end:.2f} USD  (start {start})")
    print(f"  Randament total     : {ret:+.1f}%")
    print(f"  Drawdown maxim      : {dd:.1f}%")

    out = os.path.join(DATA_DIR, f"trades_{symbol}.csv")
    df.to_csv(out, index=False)
    print(f"  Tranzactii salvate  : {out}")
    if equity_timeline:
        eqout = os.path.join(DATA_DIR, f"equity_{symbol}.csv")
        pd.DataFrame(equity_timeline).to_csv(eqout, index=False)
        print(f"  Curba de capital    : {eqout}")


# ---- main ------------------------------------------------------------------
def main():
    if not os.path.isfile(CONFIG):
        print("Nu gasesc fisierul de config.")
        print("  Astept :", CONFIG)
        return
    with open(CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)
    if not os.path.isdir(DATA_DIR):
        print("Atentie: folderul data/ nu exista la:", DATA_DIR)
    print("Backtest v1 - strategie pullback in trend")
    for sym in SYMBOLS_V1:
        try:
            backtest_symbol(sym, cfg)
        except FileNotFoundError as e:
            print(f"\n{sym}: lipseste fisierul de date -> {e}")
        except Exception as e:
            print(f"\n{sym}: eroare -> {type(e).__name__}: {e}")

if __name__ == "__main__":
    main()
