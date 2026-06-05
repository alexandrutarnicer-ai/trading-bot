"""
Motor de backtest v1 - strategie pullback in trend (buy/sell stop)
==================================================================
Citeste config.json, incarca CSV-urile M30 (trend) si M15 (intrare) pentru
fiecare pereche, simuleaza strategia cu costuri si dimensionare de pozitie,
si afiseaza statisticile: nr. tranzactii, rata de castig, expectancy (R),
randament total si drawdown maxim.

ATENTIE v1:
  - Functioneaza pe perechi cotate in USD (EURUSD, GBPUSD). GBPJPY se adauga ulterior.
  - Detectia de structura (HH/HL) e o interpretare; o calibram dupa ce comparam
    setup-urile detectate cu un chart real.
  - Costurile (spread) sunt MODELATE, nu din date - vezi SPREAD_PIPS mai jos.

Cerinte:  pip install pandas numpy
Rulare:   python backtest/backtest.py
Structura asteptata:
  trading-bot/
    config/standard_profile.json
    data/EURUSD_M15.csv, EURUSD_M30.csv, GBPUSD_M15.csv, GBPUSD_M30.csv
    backtest/backtest.py   <- acest fisier
"""

import os
import json
import numpy as np
import pandas as pd

# ---- cai (relative la radacina proiectului) -------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
# radacina = folderul care contine 'config' (merge fie ca backtest.py e direct
# in trading-bot/, fie intr-un subfolder trading-bot/backtest/)
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


# ---- indicatori -----------------------------------------------------------
def ema(s, period):
    return s.ewm(span=period, adjust=False).mean()

def rsi(s, period=14):
    delta = s.diff()
    up = delta.clip(lower=0).ewm(alpha=1/period, adjust=False).mean()
    down = (-delta.clip(upper=0)).ewm(alpha=1/period, adjust=False).mean()
    rs = up / down.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def atr(df, period=14):
    """Average True Range pe `period` bare (in unitati de pret)."""
    h, l, c = df["high"], df["low"], df["close"]
    prev_c = c.shift(1)
    tr = pd.concat([(h - l), (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, adjust=False).mean()


# ---- swings (fractali simpli) ---------------------------------------------
def mark_swings(df, N):
    """Adauga coloane swing_high / swing_low (bool), confirmate dupa N bare."""
    high, low = df["high"].values, df["low"].values
    n = len(df)
    sh = np.zeros(n, dtype=bool)
    sl = np.zeros(n, dtype=bool)
    for i in range(N, n - N):
        window_h = high[i-N:i+N+1]
        window_l = low[i-N:i+N+1]
        if high[i] == window_h.max() and (window_h.argmax() == N):
            sh[i] = True
        if low[i] == window_l.min() and (window_l.argmin() == N):
            sl[i] = True
    df["swing_high"] = sh
    df["swing_low"] = sl
    return df


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


# ---- helperi ---------------------------------------------------------------
def pip_size(symbol):
    return 0.01 if "JPY" in symbol else 0.0001

def count_optional(row, direction, cfg):
    """Cate criterii optionale sunt indeplinite (RSI, aliniere EMA)."""
    c = 0
    o = cfg["optional_criteria"]
    if o["rsi"]["enabled"]:
        r = row["rsi"]
        if direction == 1 and o["rsi"]["buy_min"] <= r <= o["rsi"]["buy_max"]:
            c += 1
        elif direction == -1 and o["rsi"]["sell_min"] <= r <= o["rsi"]["sell_max"]:
            c += 1
    if o["ema_alignment"]["enabled"]:
        if direction == 1 and row["ema_fast"] > row["ema_mid"] > row["ema_slow"]:
            c += 1
        elif direction == -1 and row["ema_fast"] < row["ema_mid"] < row["ema_slow"]:
            c += 1
    return c

def reward_R(n_optional, cfg):
    rl = cfg["reward_ladder"]
    if n_optional >= 2: return rl["rr_if_5_criteria"]
    if n_optional == 1: return rl["rr_if_4_criteria"]
    return rl["rr_if_3_criteria"]


# ---- detectarea setup-ului la o bara de confirmare ------------------------
def detect_setup(df, j, direction, window=8, depth_range=None):
    """
    Setup STRICT de pullback in trend, la bara de confirmare j.
    Bullish: al 2-lea HH crescator -> pullback la un HL nou (ultima structura,
    recenta) -> bara j este PRIMA care inchide peste maximul barei de pullback.
    Bearish: oglinda. Conditii suplimentare fata de versiunea veche:
      - pullback-ul trebuie sa fie ultima structura formata (dupa ultimul HH/LL)
      - recent: la cel mult `window` bare in urma fata de j
      - "prima inchidere" peste/sub nivel (nu re-declanseaza pe fiecare bara)
    """
    a = max(0, j - 150)
    look = df.iloc[a:j]
    sh = look.index[look["swing_high"]].tolist()   # pozitii swing high
    sl = look.index[look["swing_low"]].tolist()     # pozitii swing low
    if len(sh) < 2 or len(sl) < 2:
        return None
    hi = df["high"]; lo = df["low"]; cl = df["close"]

    if direction == 1:
        pl = sl[-1]                       # pullback low = ultimul swing low
        if pl <= sh[-1]:                  # trebuie sa fie DUPA ultimul HH (structura proaspata)
            return None
        if j - pl > window:               # trebuie sa fie recent
            return None
        if not (hi.iloc[sh[-1]] > hi.iloc[sh[-2]]):   # al 2-lea HH crescator
            return None
        if not (lo.iloc[pl] > lo.iloc[sl[-2]]):       # HL: ramane peste low-ul anterior
            return None
        lvl = hi.iloc[pl]                 # maximul barei de pullback
        if cl.iloc[j] > lvl and cl.iloc[j-1] <= lvl:  # PRIMA inchidere peste nivel
            depth = hi.iloc[sh[-1]] - lo.iloc[pl]     # adancime pullback (HH - PL)
            return (lo.iloc[pl], depth)   # extremul pullback (pentru SL) si adancimea
    else:
        ph = sh[-1]                       # pullback high = ultimul swing high
        if ph <= sl[-1]:
            return None
        if j - ph > window:
            return None
        if not (lo.iloc[sl[-1]] < lo.iloc[sl[-2]]):   # al 2-lea LL descrescator
            return None
        if not (hi.iloc[ph] < hi.iloc[sh[-2]]):       # LH: ramane sub high-ul anterior
            return None
        lvl = lo.iloc[ph]
        if cl.iloc[j] < lvl and cl.iloc[j-1] >= lvl:  # PRIMA inchidere sub nivel
            depth = hi.iloc[ph] - lo.iloc[sl[-1]]     # adancime pullback (PH - LL)
            return (hi.iloc[ph], depth)   # extremul pullback (pentru SL) si adancimea
    return None


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
                    # simulam rezultatul in barele urmatoare
                    res = simulate_trade(df, j, pending, spread, pip,
                                         PIP_VALUE_PER_LOT_USD, comm, symbol)
                    balance += res["pnl_usd"]
                    equity_curve.append(balance)
                    equity_timeline.append({"time": res["exit_time"], "balance": round(balance, 2)})
                    trades.append(res)
                    trades_today += 1
                    consec_losses = consec_losses + 1 if res["pnl_usd"] < 0 else 0
                    busy_until = res["exit_j"]   # blocheaza intrari noi pana la inchidere
                    pending = None
            continue

        # 2) guardrails + sesiune pentru a arma ceva nou
        if not in_session or trades_today >= max_trades or consec_losses >= max_losses:
            continue
        if row["trend"] == 0 or pd.isna(row["trend"]):
            continue

        direction = int(row["trend"])
        ext = detect_setup(df, j, direction)
        if ext is None:
            continue
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

        # dimensionare pozitie: 1.5% daca toate criteriile optionale sunt bifate, altfel 1%
        rp = risk_pct_all if n_opt >= 2 else risk_pct
        risk_usd = balance * rp
        sl_pips = risk_dist / pip
        lots = risk_usd / (sl_pips * PIP_VALUE_PER_LOT_USD)
        lots = np.floor(lots / 0.01) * 0.01     # pas de 0.01
        if lots < 0.01:
            continue                             # capitalul nu permite -> skip

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

    # expectancy CORECT: R per tranzactie = pnl / riscul efectiv asumat la intrare
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
        print("  ROOT   :", ROOT)
        print("  In ROOT:", os.listdir(ROOT) if os.path.isdir(ROOT) else "(nu exista)")
        cfgdir = os.path.join(ROOT, "config")
        if os.path.isdir(cfgdir):
            print("  In config/:", os.listdir(cfgdir))
        else:
            print("  Folderul config/ NU exista la radacina.")
        print("\n  Solutie: creeaza folderul 'config' langa backtest.py si pune in el")
        print("  fisierul cu numele exact 'standard_profile.json'.")
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