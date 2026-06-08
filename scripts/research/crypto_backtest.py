"""
Backtest crypto individual — M15 entry + M30 trend, ambele directii, 24/7
==========================================================================
Testeaza 10 perechi crypto ca posibil diversificator de regim.

Per pereche:
  - trades, win rate, expectancy (global)
  - TRAIN / TEST 70/30 cu p-value (t-test one-sided H0: mean R <= 0)
  - expectancy per an (dependenta de regim bull/bear)
  - long vs short separat
  - drawdown max, swap total

CRITIC: crypto NU e forex — pip_size = tick_size real din MT5, pip_val = tick_value.
        Swap direction-aware (long vs short au rate diferite).
        Fara sesiune (24/7), fara plafon de trades.

Prerequizit: ruleaza mai intai  python scripts/descarca_crypto.py
Rulare:      python scripts/research/crypto_backtest.py
"""

import os
import sys
import copy
import json
import math
import numpy as np
import pandas as pd

# --- cale catre root (pentru import din backtest.py) --------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from backtest import CONFIG, DATA_DIR
from adapters.csv_source import CsvDataSource
from strategy.preparation import prepare_symbol
from strategy import signals as _sig
from strategy.structure import detect_setup
from strategy.signals import count_optional, reward_R, pip_size
from engine.simulator import simulate_trade

# ---- constante ---------------------------------------------------------------

SYMBOLS = [
    "BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "ADAUSD",
    "DOGEUSD", "LTCUSD", "BNBUSD", "AVAXUSD", "LINKUSD",
]

START_BALANCE   = 300
PULLBACK_WINDOW = 8
EXPIRE_BARS     = 4

CRYPTO_SPECS_FILE = os.path.join(DATA_DIR, "crypto_specs.json")

# MT5 foloseste 360 de zile/an pentru calculul dobanzii (mode 5).
# Unii brokeri folosesc 365 — verifica cu brokerul tau daca rezultatele sunt off.
SWAP_DAYS_PER_YEAR = 360


# ---- utilitare ---------------------------------------------------------------

def load_specs():
    if not os.path.exists(CRYPTO_SPECS_FILE):
        print(f"EROARE: {CRYPTO_SPECS_FILE} nu exista.")
        print("Ruleaza mai intai:  python scripts/descarca_crypto.py")
        return None
    with open(CRYPTO_SPECS_FILE, encoding="utf-8") as f:
        return json.load(f)


def nights_units(entry_time, exit_time):
    """Total swap units intre doua date: miercuri = 3, restul = 1."""
    e = pd.Timestamp(entry_time).normalize()
    x = pd.Timestamp(exit_time).normalize()
    nights = (x - e).days
    if nights <= 0:
        return 0
    units = 0
    d = e
    for _ in range(nights):
        d = d + pd.Timedelta(days=1)
        units += 3 if d.weekday() == 2 else 1
    return units


def crypto_swap_delta(spec, direction, entry_time, exit_time, lots, entry_price):
    """
    Delta PnL din swap (negativ = cost, pozitiv = credit).

    Gestioneaza modurile MT5:
      3, 4  — valoare fixa in USD per lot per noapte (raw din MT5, e.g. -50.0 $/lot/n)
      5     — SYMBOL_SWAP_MODE_INTEREST_OPEN: dobanda % anuala aplicata pe pretul de
              deschidere × contract_size × lots.
              Formula: notional × rate/100 / SWAP_DAYS_PER_YEAR × units
              unde notional = contract_size × entry_price × lots.
      altele — neiplementat, returneaza 0 (avertisment la prima pereche).

    swap_long / swap_short vin direct din MT5 symbol_info():
      mode 3/4: in USD/lot/noapte (negative = cost)
      mode 5:   in % anual (negative = cost, ex: -8.0 = 8% anual)
    """
    units = nights_units(entry_time, exit_time)
    if units == 0:
        return 0.0

    mode = spec.get("swap_mode", 3)
    rate = spec["swap_long"] if direction == 1 else spec["swap_short"]

    if rate == 0.0:
        return 0.0

    if mode in (3, 4):
        # Valoare fixa USD per lot per noapte — se aplica direct
        return units * rate * lots

    if mode == 5:
        # Dobanda anuala pe pretul de deschidere al pozitiei
        # swap_delta = contract_size × open_price × lots × (rate_pct/100) / 360 × units
        notional = spec["contract_size"] * entry_price * lots
        return units * notional * (rate / 100.0) / SWAP_DAYS_PER_YEAR

    # Mode 0 (points), 1 (base currency), 2 (% from current price) — neiplementat
    return 0.0


def print_swap_example(specs_all):
    """
    Afiseaza swap per trade pentru BTC pe scenarii concrete — sanity check
    al formulei inainte de backtest.
    """
    sym = "BTCUSD"
    if sym not in specs_all:
        return
    spec   = specs_all[sym]
    mode   = spec.get("swap_mode", 3)
    rate_l = spec["swap_long"]
    rate_s = spec["swap_short"]
    cs     = spec["contract_size"]

    entry_price = 60_000.0   # exemplu ilustrativ
    lots        = 0.01        # lot minim tipic BTC
    risk_usd    = 3.0         # 1% din $300

    def calc(rate, units):
        if mode in (3, 4):
            return units * rate * lots
        if mode == 5:
            return units * cs * entry_price * lots * (rate / 100.0) / SWAP_DAYS_PER_YEAR
        return 0.0

    print(f"\n  === EXEMPLU SWAP {sym} (mode {mode}) ===")
    print(f"  Parametri: entry=${entry_price:,.0f}  lots={lots}  "
          f"swap_long={rate_l}%  swap_short={rate_s}%"
          if mode == 5 else
          f"  Parametri: entry=${entry_price:,.0f}  lots={lots}  "
          f"swap_long={rate_l}$/lot/n  swap_short={rate_s}$/lot/n")
    print(f"  {'Scenariu':<35} {'LONG cost ($)':>14} {'% risc':>8} {'SHORT cost ($)':>15} {'% risc':>8}")
    print(f"  {'-'*82}")

    for units, label in [
        (1, "1 noapte, fara miercuri"),
        (2, "2 nopti, fara miercuri"),
        (4, "2 nopti, CU miercuri (4 units)"),
        (3, "Miercuri singura (3 units)"),
    ]:
        cost_l = -calc(rate_l, units)
        cost_s = -calc(rate_s, units)
        pct_l  = cost_l / risk_usd * 100 if risk_usd else float("nan")
        pct_s  = cost_s / risk_usd * 100 if risk_usd else float("nan")
        print(f"  {label:<35} {cost_l:>14.4f} {pct_l:>7.1f}% {cost_s:>15.4f} {pct_s:>7.1f}%")

    print(f"  (risc de referinta: ${risk_usd} = 1% din ${START_BALANCE})\n")


def p_value_positive(R_values):
    """
    P-valoare one-sided H0: mean(R) <= 0, H1: mean(R) > 0.
    Foloseste aproximarea normala pentru t-statistic (valida pt n >= 30).
    Returneaza (t_stat, p_value) sau (None, None) daca n < 10.
    """
    n = len(R_values)
    if n < 10:
        return None, None
    arr = np.asarray(R_values, dtype=float)
    m = arr.mean()
    s = arr.std(ddof=1)
    if s < 1e-12:
        return None, None
    t_stat = m / (s / math.sqrt(n))
    p = 0.5 * math.erfc(t_stat / math.sqrt(2))   # P(Z > t), approximare normala
    return round(t_stat, 3), round(p, 4)


# ---- bucla de backtest crypto ------------------------------------------------

def run_crypto(df, symbol, spec, cfg, only_long=False, only_short=False,
               spread_override=None, skip_hours=None, skip_weekdays=None):
    """
    Bucla de backtest pentru o pereche crypto.
    Diferente fata de engine/single.py:
      - pip = tick_size real (nu 1.0 — necesar pentru perechi cu pret mic: XRP, DOGE)
      - pip_val = tick_value_usd (USD per tick per lot)
      - swap direction-aware inclus per trade
      - fara filtre de sesiune (24/7) — controlat prin skip_hours/skip_weekdays
      - fara circuit breaker per zi (plafon scos)
    only_long      : exclude short-urile
    only_short     : exclude long-urile
    spread_override: suprascrie spec['spread_price'] (util pt test cu spread real)
    skip_hours     : set() de ore UTC de ignorat (e.g. {10,11,12,13,14,19,20,21,22,23})
    skip_weekdays  : set() de zile (0=Lun, 5=Sam, 6=Dum)
    """
    pip     = spec["tick_size"]       # increment minim de pret
    pip_val = spec["tick_value_usd"]  # USD per tick per lot
    spread  = spread_override if spread_override is not None else spec["spread_price"]
    buf     = 2 * pip                 # buffer intrare/SL (2 tick-uri)
    comm    = 0.0                     # crypto CFD: spread-only

    risk_pct     = cfg["account"]["risk_per_trade_pct"] / 100.0
    risk_pct_all = cfg["account"].get("risk_per_trade_pct_all_criteria",
                                      cfg["account"]["risk_per_trade_pct"]) / 100.0

    balance      = START_BALANCE
    equity_curve = [balance]
    equity_tl    = []
    trades       = []

    day            = None
    pending        = None
    busy_until     = -1
    skipped_minlot = 0   # trades sarite: lots<0.01 (capital insuficient pt min lot)

    for j in range(60, len(df)):
        row = df.iloc[j]
        t   = row["time"]

        if day != t.date():
            day     = t.date()
            pending = None

        if j <= busy_until:
            continue

        if pending is not None:
            d    = pending["dir"]
            inv  = (d == 1  and row["low"]  < pending["invalidate"]) or \
                   (d == -1 and row["high"] > pending["invalidate"])
            exp  = j - pending["armed_at"] > EXPIRE_BARS
            if inv or exp:
                pending = None
            else:
                trig = (d == 1  and row["high"] >= pending["entry"]) or \
                       (d == -1 and row["low"]  <= pending["entry"])
                if trig:
                    res = simulate_trade(df, j, pending, spread, pip,
                                         pip_val, comm, symbol)
                    sw_delta       = crypto_swap_delta(spec, d,
                                                       res["time"], res["exit_time"],
                                                       res["lots"],
                                                       res["entry"])   # <-- fix mode 5
                    res["swap"]      = round(-sw_delta, 4)   # pozitiv = cost platit
                    res["pnl_usd"]   = round(res["pnl_usd"] + sw_delta, 2)
                    res["direction"] = d
                    balance         += res["pnl_usd"]

                    # Protectie cont: stop la margin call simulat
                    if balance <= 0:
                        balance = 0.0
                        equity_curve.append(balance)
                        equity_tl.append({"time": res["exit_time"], "balance": 0.0})
                        trades.append(res)
                        return trades, equity_curve, equity_tl, skipped_minlot

                    equity_curve.append(balance)
                    equity_tl.append({"time": res["exit_time"],
                                      "balance": round(balance, 2)})
                    trades.append(res)
                    busy_until = res["exit_j"]
                    pending    = None
            continue

        if row["trend"] == 0 or pd.isna(row["trend"]):
            continue

        # Filtre de sesiune (optionale)
        if skip_hours    and t.hour     in skip_hours:
            continue
        if skip_weekdays and t.weekday() in skip_weekdays:
            continue

        direction = int(row["trend"])
        if only_long  and direction == -1:
            continue
        if only_short and direction ==  1:
            continue
        found = detect_setup(df, j, direction, window=PULLBACK_WINDOW)
        if found is None:
            continue
        ext, _ = found

        if direction == 1:
            entry = row["high"] + buf
            sl    = ext - buf
        else:
            entry = row["low"]  - buf
            sl    = ext + buf

        risk_dist = abs(entry - sl)
        if risk_dist <= 0:
            continue

        n_opt    = count_optional(row, direction, cfg)
        R        = reward_R(n_opt, cfg)
        tp       = entry + direction * risk_dist * R
        rp       = risk_pct_all if n_opt >= 2 else risk_pct
        risk_usd = balance * rp
        sl_pips  = risk_dist / pip           # distanta SL in tick-uri
        lots     = risk_usd / (sl_pips * pip_val)
        lots     = math.floor(lots / 0.01) * 0.01
        if lots < 0.01:
            skipped_minlot += 1
            continue

        pending = {
            "dir": direction, "entry": entry, "sl": sl, "tp": tp,
            "lots": lots, "R": R, "invalidate": ext, "armed_at": j,
            "time": t, "risk_usd": risk_usd,
        }

    return trades, equity_curve, equity_tl, skipped_minlot


# ---- statistici per pereche --------------------------------------------------

def summarize(symbol, spec, trades, equity_curve, skipped_minlot=0):
    if not trades:
        print(f"\n  {symbol}: 0 tranzactii — lipsesc date sau strategie nu gaseste setup-uri")
        if skipped_minlot:
            print(f"  ({skipped_minlot} setup-uri sarite: lots < 0.01 — capital insuficient pt min lot)")
        return

    tdf = pd.DataFrame(trades)
    # Exclude tranzactii cu risk_usd invalid (0 sau negativ) inainte de R=pnl/risk
    n_invalid = (tdf["risk_usd"] <= 0).sum()
    if n_invalid:
        print(f"  AVERTISMENT: {n_invalid} trades cu risk_usd <= 0 excluse din statistici")
        tdf = tdf[tdf["risk_usd"] > 0].copy()
    if len(tdf) == 0:
        print(f"\n  {symbol}: toate tranzactiile au risk_usd invalid")
        return

    tdf["R"]       = tdf["pnl_usd"] / tdf["risk_usd"]
    tdf["entry_t"] = pd.to_datetime(tdf["time"])
    tdf["year"]    = tdf["entry_t"].dt.year

    n    = len(tdf)
    wins = (tdf["outcome"] == "win").sum()

    eq   = np.asarray(equity_curve, dtype=float)
    peak = np.maximum.accumulate(eq)
    dd   = ((eq - peak) / peak).min() * 100

    span_days = (tdf["entry_t"].max() - tdf["entry_t"].min()).days
    freq_wk   = n / max(span_days / 7, 1)

    swap_total_paid = tdf["swap"].sum()

    # Train / test 70/30 (split pe timp)
    split_t = tdf["entry_t"].quantile(0.70)
    train   = tdf[tdf["entry_t"] <  split_t]
    test    = tdf[tdf["entry_t"] >= split_t]

    t_stat, pval = p_value_positive(test["R"].values if len(test) >= 10 else [])

    # Long vs short
    long_t  = tdf[tdf["direction"] == 1]
    short_t = tdf[tdf["direction"] == -1]

    # Expectancy per an
    annual = tdf.groupby("year")["R"].agg(["mean", "count"])

    # --- afisare ---
    print(f"\n{'='*62}")
    print(f"  {symbol}  |  contract={spec['contract_size']:.0f}  "
          f"tick={spec['tick_size']}  pip_val=${spec['pip_val']:.4f}  "
          f"spread={spec['spread_price']:.5f}")
    print(f"  swap_L={spec['swap_long']:.4f}  swap_S={spec['swap_short']:.4f}  "
          f"swap_mode={spec['swap_mode']}")
    print(f"{'='*62}")

    ret = (equity_curve[-1] - START_BALANCE) / START_BALANCE * 100
    print(f"  Balanta: {START_BALANCE} -> {equity_curve[-1]:.2f} USD  ({ret:+.1f}%)")
    print(f"  Trades  : {n}  |  Win: {wins/n*100:.1f}%  |  Expectancy: {tdf['R'].mean():+.3f} R")
    print(f"  DD max  : {dd:.1f}%  |  Frecventa: {freq_wk:.1f} trades/sapt"
          f"  |  Swap platit: {swap_total_paid:.2f} USD")

    # Train / Test
    print(f"\n  --- TRAIN ({len(train)} trades) / TEST ({len(test)} trades) ---")
    for label, d_set in [("TRAIN", train), ("TEST ", test)]:
        if len(d_set) < 3:
            print(f"  {label}: prea putine trades ({len(d_set)})")
            continue
        w = (d_set["outcome"] == "win").sum()
        line = (f"  {label}: {len(d_set):4d} trades | win {w/len(d_set)*100:.1f}% "
                f"| expectancy {d_set['R'].mean():+.3f} R")
        if label == "TEST " and pval is not None:
            sig = "  *** SEMNIFICATIV ***" if pval < 0.05 else \
                  "  (* marginal)"         if pval < 0.10 else \
                  "  (nesemnificativ)"
            line += f"  |  t={t_stat:.2f}  p={pval:.4f}{sig}"
        elif label == "TEST " and len(test) < 10:
            line += "  |  (n<10, p-value indisponibil)"
        print(line)

    # Long vs Short
    print(f"\n  --- Directie ---")
    for label, ddf in [("LONG  (+1)", long_t), ("SHORT (-1)", short_t)]:
        if len(ddf) == 0:
            print(f"  {label}: 0 trades")
            continue
        w = (ddf["outcome"] == "win").sum()
        print(f"  {label}: {len(ddf):4d} trades | win {w/len(ddf)*100:.1f}% "
              f"| expectancy {ddf['R'].mean():+.3f} R")

    # Expectancy per an (bull vs bear)
    print(f"\n  --- Expectancy per an (dependenta de regim) ---")
    for yr, row_a in annual.iterrows():
        print(f"  {yr}: {int(row_a['count']):4d} trades | expectancy {row_a['mean']:+.3f} R")


# ---- main --------------------------------------------------------------------

def main():
    specs_all = load_specs()
    if specs_all is None:
        return

    # Patch _INDEX_PIP: pip_size(symbol) = tick_size real (nu 1.0 pentru crypto cu pret mic)
    for sym, sp in specs_all.items():
        _sig._INDEX_PIP[sym] = sp["tick_size"]

    with open(CONFIG, encoding="utf-8") as f:
        cfg_base = json.load(f)

    cfg = copy.deepcopy(cfg_base)
    cfg["account"]["starting_balance"]            = START_BALANCE
    cfg["session"]["start_hour"]                  = 0    # 24/7
    cfg["session"]["end_hour"]                    = 24
    cfg["risk_management"]["max_trades_per_day"]   = 9999
    cfg["risk_management"]["max_consecutive_losses"] = 9999
    cfg["costs"]["commission_per_lot_round_turn_usd"] = 0.0
    # RSI simetric pentru SELL (ca in session2)
    cfg["optional_criteria"]["rsi"]["sell_max"] = 60

    source = CsvDataSource(DATA_DIR)

    print(f"\nBacktest crypto individual | {START_BALANCE} USD | BOTH directions | 24/7")
    print(f"Pullback window: {PULLBACK_WINDOW} | Expire bars: {EXPIRE_BARS}")
    print(f"Simboluri: {SYMBOLS}")

    # Sanity check swap inainte de orice backtest
    print_swap_example(specs_all)

    results_summary = []

    for symbol in SYMBOLS:
        if symbol not in specs_all:
            print(f"\n  {symbol}: specs lipsesc din crypto_specs.json — sare peste")
            continue

        spec = specs_all[symbol]

        try:
            df = prepare_symbol(source, symbol, cfg)
        except FileNotFoundError:
            print(f"\n  {symbol}: DATE LIPSA — ruleaza descarca_crypto.py mai intai")
            continue

        date_start = df["time"].min().strftime("%Y-%m-%d")
        date_end   = df["time"].max().strftime("%Y-%m-%d")
        print(f"  {symbol}: {len(df):>7} bare M15  [{date_start} ... {date_end}]", end="  ")

        trades, equity_curve, equity_tl, skipped = run_crypto(df, symbol, spec, cfg)
        print(f"-> {len(trades)} trades triggerate"
              + (f"  ({skipped} sarite: lots<0.01)" if skipped else ""))

        summarize(symbol, spec, trades, equity_curve, skipped)

        if trades:
            tdf = pd.DataFrame(trades)
            valid = tdf[tdf["risk_usd"] > 0].copy()
            if len(valid):
                valid["R"] = valid["pnl_usd"] / valid["risk_usd"]
                out = os.path.join(DATA_DIR, f"crypto_trades_{symbol}.csv")
                valid.to_csv(out, index=False)

            n    = len(tdf)
            wins = (tdf["outcome"] == "win").sum()
            eq   = np.asarray(equity_curve, dtype=float)
            peak = np.maximum.accumulate(eq)
            dd   = ((eq - peak) / peak).min() * 100
            exp  = valid["R"].mean() if len(valid) else float("nan")
            results_summary.append({
                "symbol":   symbol,
                "trades":   n,
                "skipped":  skipped,
                "win_pct":  round(wins / n * 100, 1),
                "exp_R":    round(exp, 3) if math.isfinite(exp) else float("nan"),
                "dd_pct":   round(dd, 1),
                "swap_usd": round(tdf["swap"].sum(), 1),
            })

    # ---- tabel rezumativ -----
    if results_summary:
        print(f"\n{'='*72}")
        print(f"  REZUMAT FINAL")
        print(f"  {'Simbol':<10} {'trades':>7} {'sarite':>7} {'win%':>6} {'exp R':>7} {'DD%':>7} {'swap$':>9}")
        print(f"  {'-'*65}")
        for r in results_summary:
            exp_str = f"{r['exp_R']:>+7.3f}" if math.isfinite(r["exp_R"]) else "    NaN"
            print(f"  {r['symbol']:<10} {r['trades']:>7} {r['skipped']:>7} {r['win_pct']:>6.1f}%"
                  f" {exp_str} {r['dd_pct']:>7.1f}% {r['swap_usd']:>9.1f}")

    print(f"\n{'='*62}")
    print(f"Gata. CSV salvate in data/crypto_trades_<SIMBOL>.csv")


if __name__ == "__main__":
    main()
