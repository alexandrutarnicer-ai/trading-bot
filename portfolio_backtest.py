"""
Motor de backtest DE PORTOFOLIU
================================
Ruleaza toate perechile pe UN SINGUR CONT comun, in ordine cronologica:
  - o singura pozitie per pereche, dar mai multe perechi simultan
  - balanta si marja sunt comune
  - P&L-ul fiecarei tranzactii se deconteaza la INCHIDERE (exit), in ordinea timpului
  - verificare de marja: daca nu sunt fonduri libere, tranzactia e ratata (ca in realitate)
  - valoarea pipului calculata corect per pereche (USDJPY/USDCAD au USD ca baza)

Cerinte:  pip install pandas numpy
Rulare:   python portfolio_backtest.py
"""

import os
import json
import numpy as np
import pandas as pd

from backtest import load_symbol, simulate_trade, CONFIG
from strategy.structure import detect_setup
from strategy.signals import pip_size, count_optional, reward_R
from strategy.costs import swap_cost, pip_value_usd, notional_usd

# ---- parametri portofoliu --------------------------------------------------
SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY"]
SPREAD_PIPS = {"EURUSD": 0.5, "GBPUSD": 0.8, "USDJPY": 0.7}
START_BALANCE = 1000      # balanta simulata (schimb-o ca sa testezi alte praguri)
LEVERAGE = 30             # 1:30 (entitate UE)
EXPIRE_BARS = 4
DEPTH_RANGE = None        # filtru adancime pullback (Fibonacci); None = dezactivat
PULLBACK_WINDOW = 8       # max bare M15 intre swing si bara de confirmare (1 bara = 15 min)
SKIP_MONDAY = True        # nu intra lunea (deschidere slaba dupa weekend)
SKIP_HOURS = (15, 16)     # nu intra intre 15:00-16:49 RO (gol Londra->NY)
ATR_MAX_PIPS = {"EURUSD": 7.5}   # nu intra pe EURUSD daca ATR > prag (volatilitate mare = haos)
MAX_DAY_CONSEC_LOSSES = 3       # circuit breaker: 3 pierderi consecutive pe cont => stop pe ziua aia
CORR_PAIRS = {"EURUSD": "GBPUSD", "GBPUSD": "EURUSD"}  # nu intra pe amandoua in aceeasi directie


def run_portfolio(cfg):
    # parametri din config
    rp_base = cfg["account"]["risk_per_trade_pct"] / 100.0
    rp_all = cfg["account"].get("risk_per_trade_pct_all_criteria",
                                cfg["account"]["risk_per_trade_pct"]) / 100.0
    comm = cfg["costs"]["commission_per_lot_round_turn_usd"]
    sh, eh = cfg["session"]["start_hour"], cfg["session"]["end_hour"]
    max_trades = cfg["risk_management"]["max_trades_per_day"]
    max_losses = cfg["risk_management"]["max_consecutive_losses"]

    # incarca toate perechile
    data = {}
    for s in SYMBOLS:
        try:
            data[s] = load_symbol(s, cfg)
            print(f"  {s}: {len(data[s])} bare M15")
        except FileNotFoundError:
            print(f"  {s}: LIPSESC datele (M15/M30) - sare peste")
    if not data:
        print("Nu am date pentru nicio pereche.")
        return

    # pentru cross-uri JPY (ex GBPJPY) ne trebuie cursul USDJPY ca sa convertim in USD
    ujdf = data.get("USDJPY")
    uj_times = ujdf["time"].values if ujdf is not None else None
    uj_close = ujdf["close"].values if ujdf is not None else None

    def usdjpy_at(ts):
        if uj_times is None:
            return 150.0
        i = np.searchsorted(uj_times, np.datetime64(ts), side="right") - 1
        return float(uj_close[max(0, min(i, len(uj_close) - 1))])

    # lista de evenimente (timp, simbol, pozitie_bara), sortata cronologic
    events = []
    for s, df in data.items():
        times = df["time"].values
        for jj in range(60, len(df)):
            events.append((times[jj], s, jj))
    events.sort(key=lambda e: e[0])
    split_time = pd.Timestamp(events[int(0.7 * len(events))][0])   # 70% train / 30% test
    print(f"  total evenimente: {len(events)}")
    print(f"  split train/test la: {split_time.date()}\n  rulez...")

    balance = START_BALANCE
    equity = [{"time": events[0][0], "balance": balance}]
    trades = []

    pending = {s: None for s in data}
    busy_until = {s: -1 for s in data}
    day_state = {s: None for s in data}
    trades_today = {s: 0 for s in data}
    consec = {s: 0 for s in data}
    open_margin = {s: 0.0 for s in data}      # marja blocata de pozitia deschisa
    active_dir = {s: None for s in data}     # directia pozitiei active (pentru filtrul de corelatie)
    open_trades = []                          # (exit_time, symbol, pnl)

    open_now = 0
    max_concurrent = 0
    skipped_margin = 0
    gday = None           # ziua curenta (circuit breaker la nivel de cont)
    gconsec = 0           # pierderi consecutive azi (tot contul)
    ghalt = False         # oprit pentru restul zilei?
    halted_days = 0       # cate zile am fost opriti (statistica)

    for (t, s, jj) in events:
        t = pd.Timestamp(t)

        # circuit breaker: reset la schimbarea zilei
        if t.date() != gday:
            gday = t.date(); gconsec = 0; ghalt = False

        # 1) deconteaza tranzactiile inchise pana la timpul curent
        if open_trades:
            still = []
            for (xt, xs, pnl) in open_trades:
                if xt <= t:
                    balance += pnl
                    equity.append({"time": xt, "balance": round(balance, 2)})
                    consec[xs] = consec[xs] + 1 if pnl < 0 else 0
                    gconsec = gconsec + 1 if pnl < 0 else 0
                    if gconsec >= MAX_DAY_CONSEC_LOSSES and not ghalt:
                        ghalt = True; halted_days += 1
                    open_margin[xs] = 0.0
                    active_dir[xs] = None
                    open_now -= 1
                else:
                    still.append((xt, xs, pnl))
            open_trades = still

        df = data[s]
        row = df.iloc[jj]

        # reset zilnic per simbol
        if day_state[s] != t.date():
            day_state[s] = t.date()
            trades_today[s] = 0
            consec[s] = 0
            pending[s] = None

        # o singura pozitie per pereche
        if jj <= busy_until[s]:
            continue

        pip = pip_size(s)

        # 2) ordin pending: trigger / invalidare / expirare
        if pending[s] is not None:
            p = pending[s]; d = p["dir"]
            if (d == 1 and row["low"] < p["invalidate"]) or \
               (d == -1 and row["high"] > p["invalidate"]):
                pending[s] = None
            elif jj - p["armed_at"] > EXPIRE_BARS:
                pending[s] = None
            else:
                trig = (d == 1 and row["high"] >= p["entry"]) or \
                       (d == -1 and row["low"] <= p["entry"])
                if trig:
                    margin = notional_usd(s, p["entry"], p["lots"]) / LEVERAGE
                    used = sum(open_margin.values())
                    if balance - used < margin:
                        skipped_margin += 1
                        pending[s] = None
                        continue
                    pv = p["pv"]
                    spr = SPREAD_PIPS.get(s, 1.0) * pip
                    res = simulate_trade(df, jj, p, spr, pip, pv, comm, s)
                    sc = swap_cost(s, res["time"], res["exit_time"], p["lots"])
                    res["swap"] = round(sc, 3)
                    res["pnl_usd"] = round(res["pnl_usd"] - sc, 2)
                    res["atr_pips"] = p["atr_pips"]
                    open_trades.append((pd.Timestamp(res["exit_time"]), s, res["pnl_usd"]))
                    open_margin[s] = margin
                    active_dir[s] = d
                    busy_until[s] = res["exit_j"]
                    trades_today[s] += 1
                    trades.append(res)
                    open_now += 1
                    max_concurrent = max(max_concurrent, open_now)
                    pending[s] = None
            continue

        # 3) conditii pentru a arma ceva nou
        if ghalt:
            continue
        if not (sh <= t.hour < eh):
            continue
        if SKIP_MONDAY and t.weekday() == 0:
            continue
        if t.hour in SKIP_HOURS:
            continue
        if trades_today[s] >= max_trades or consec[s] >= max_losses:
            continue
        if row["trend"] == 0 or pd.isna(row["trend"]):
            continue
        cap = ATR_MAX_PIPS.get(s)
        if cap and row["atr"] / pip > cap:
            continue

        direction = int(row["trend"])

        # filtru corelatie: EURUSD si GBPUSD nu intra in aceeasi directie simultan
        corr = CORR_PAIRS.get(s)
        if corr and corr in data:
            corr_dir = pending[corr]["dir"] if pending[corr] is not None else active_dir[corr]
            if corr_dir == direction:
                continue

        found = detect_setup(df, jj, direction, window=PULLBACK_WINDOW, depth_range=DEPTH_RANGE)
        if found is None:
            continue
        ext, _ = found

        buf = 2 * pip
        if direction == 1:
            entry = row["high"] + buf; sl = ext - buf
        else:
            entry = row["low"] - buf; sl = ext + buf
        risk_dist = abs(entry - sl)
        if risk_dist <= 0:
            continue

        n_opt = count_optional(row, direction, cfg)
        R = reward_R(n_opt, cfg)
        tp = entry + direction * risk_dist * R

        rp = rp_all if n_opt >= 2 else rp_base
        risk_usd = balance * rp
        pv = pip_value_usd(s, entry, usdjpy_at(t))
        sl_pips = risk_dist / pip
        lots = risk_usd / (sl_pips * pv)
        lots = np.floor(lots / 0.01) * 0.01
        if lots < 0.01:
            continue

        pending[s] = {"dir": direction, "entry": entry, "sl": sl, "tp": tp,
                      "lots": lots, "R": R, "invalidate": ext, "armed_at": jj,
                      "time": t, "risk_usd": risk_usd, "pv": pv,
                      "atr_pips": round(row["atr"] / pip, 1)}

    # deconteaza ce a ramas deschis la final
    for (xt, xs, pnl) in open_trades:
        balance += pnl
        equity.append({"time": xt, "balance": round(balance, 2)})

    print(f"\n  Circuit breaker activat in {halted_days} zile (stop dupa {MAX_DAY_CONSEC_LOSSES} pierderi consecutive)")
    summarize(trades, equity, balance, max_concurrent, skipped_margin, split_time)


def summarize(trades, equity, balance, max_concurrent, skipped_margin, split_time):
    if not trades:
        print("\nNicio tranzactie.")
        return
    df = pd.DataFrame(trades)
    df["R_realizat"] = df["pnl_usd"] / df["risk_usd"]
    df["entry_t"] = pd.to_datetime(df["time"])
    wins = (df["outcome"] == "win").sum()
    losses = (df["outcome"] == "loss").sum()

    eqdf = pd.DataFrame(equity).sort_values("time")
    b = eqdf["balance"].values
    peak = np.maximum.accumulate(b)
    dd = ((b - peak) / peak).min() * 100
    ret = (balance - START_BALANCE) / START_BALANCE * 100
    swap_total = df["swap"].sum() if "swap" in df else 0.0

    print("\n===== PORTOFOLIU (cont comun, swap inclus) =====")
    print(f"  Balanta: {START_BALANCE} -> {balance:.2f} USD   ({ret:+.1f}%)")
    print(f"  Tranzactii          : {len(df)}  (W:{wins} / L:{losses})")
    print(f"  Rata de castig      : {wins/len(df)*100:.1f}%")
    print(f"  Expectancy/trade    : {df['R_realizat'].mean():+.3f} R")
    print(f"  Drawdown maxim      : {dd:.1f}%")
    print(f"  Swap platit total   : {swap_total:.2f} USD")
    print(f"  Maxim pozitii simultane : {max_concurrent}")
    print(f"  Ratate (fonduri insuficiente): {skipped_margin}")

    print("\n  --- VALIDARE: train vs test nevazut ---")
    for name, d in [("TRAIN (primele 70%)", df[df["entry_t"] < split_time]),
                    ("TEST  (ultimele 30%, nevazut)", df[df["entry_t"] >= split_time])]:
        if len(d):
            w = (d["outcome"] == "win").sum()
            print(f"  {name}: {len(d):4d} trades | win {w/len(d)*100:.1f}% | "
                  f"expectancy {d['R_realizat'].mean():+.3f} R")

    print("\n  --- pe pereche ---")
    for s in df["symbol"].unique():
        sub = df[df["symbol"] == s]
        w = (sub["outcome"] == "win").sum()
        print(f"  {s}: {len(sub):4d} trades | win {w/len(sub)*100:.1f}% | "
              f"expectancy {sub['R_realizat'].mean():+.3f} R | pnl {sub['pnl_usd'].sum():+.1f} USD")

    from backtest import DATA_DIR
    df.to_csv(os.path.join(DATA_DIR, "portfolio_trades.csv"), index=False)
    eqdf.to_csv(os.path.join(DATA_DIR, "portfolio_equity.csv"), index=False)
    print(f"\n  Salvat: portfolio_trades.csv si portfolio_equity.csv in {DATA_DIR}")


def main():
    with open(CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)
    print(f"Backtest de portofoliu | balanta simulata {START_BALANCE} USD | levier 1:{LEVERAGE}")
    run_portfolio(cfg)


if __name__ == "__main__":
    main()
