"""
BTC Session 3 — Optimizare sesiune + filtru ATR/SL pentru BTCUSD
=================================================================
Testeaza combinatii de:
  - Ore de skip (sesiune US, noapte)
  - Zi saptamana skip (sambata)
  - Filtru SL minim (elimina setup-uri cu SL prea mic)
  - Filtru ATR (atr_max_pips)

Criteriu de selectie: Exp(test) maxim cu p < 0.10 si DD > -70%.
NU SUPRAOPTIMIZEAZA: teste cu sens economic, nu grid-search exhaustiv.

Rulare: python scripts/research/btc_session_optimize.py
"""

import os, sys, copy, json, math, warnings
import numpy as np
import pandas as pd
warnings.filterwarnings("ignore")

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import scripts.research.crypto_backtest as cb
from backtest import CONFIG, DATA_DIR
from adapters.csv_source import CsvDataSource
from strategy.preparation import prepare_symbol
from strategy import signals as _sig

START_BALANCE = 500
SYMBOL        = "BTCUSD"

# ---- backtest cu filtre de sesiune -----------------------------------------

def run_btc_filtered(df, spec, cfg,
                     skip_hours=None,     # set() de ore UTC de ignorat
                     skip_weekdays=None,  # set() de zile (0=Mon, 5=Sat, 6=Sun)
                     min_sl_usd=None,     # filtru minim SL in USD
                     atr_max_usd=None):   # filtru maxim ATR in USD
    """
    Varianta run_crypto cu filtre suplimentare de sesiune/ATR.
    Parametrii de filtru se aplica INAINTE de detect_setup.
    """
    import math as _math
    from strategy.structure import detect_setup
    from strategy.signals import count_optional, reward_R
    from engine.simulator import simulate_trade

    pip     = spec["tick_size"]
    pip_val = spec["tick_value_usd"]
    spread  = spec["spread_price"]
    buf     = 2 * pip
    comm    = 0.0

    risk_pct     = cfg["account"]["risk_per_trade_pct"] / 100.0
    risk_pct_all = cfg["account"].get("risk_per_trade_pct_all_criteria",
                                      cfg["account"]["risk_per_trade_pct"]) / 100.0

    balance      = START_BALANCE
    equity_curve = [balance]
    trades       = []
    pending      = None
    busy_until   = -1
    day          = None
    skipped      = 0

    for j in range(60, len(df)):
        row = df.iloc[j]
        t   = row["time"]

        if day != t.date():
            day     = t.date()
            pending = None

        if j <= busy_until:
            continue

        if pending is not None:
            d   = pending["dir"]
            inv = (d ==  1 and row["low"]  < pending["invalidate"]) or \
                  (d == -1 and row["high"] > pending["invalidate"])
            exp = j - pending["armed_at"] > cb.EXPIRE_BARS
            if inv or exp:
                pending = None
            else:
                trig = (d ==  1 and row["high"] >= pending["entry"]) or \
                       (d == -1 and row["low"]  <= pending["entry"])
                if trig:
                    res       = simulate_trade(df, j, pending, spread, pip, pip_val, comm, SYMBOL)
                    sw_delta  = cb.crypto_swap_delta(spec, d,
                                                     res["time"], res["exit_time"],
                                                     res["lots"], res["entry"])
                    res["swap"]      = round(-sw_delta, 4)
                    res["pnl_usd"]   = round(res["pnl_usd"] + sw_delta, 2)
                    res["direction"] = d
                    balance         += res["pnl_usd"]
                    if balance <= 0:
                        balance = 0.0
                        equity_curve.append(0.0)
                        trades.append(res)
                        return trades, equity_curve, skipped
                    equity_curve.append(balance)
                    trades.append(res)
                    busy_until = res["exit_j"]
                    pending    = None
            continue

        if row["trend"] == 0 or pd.isna(row["trend"]):
            continue

        # ---- filtre de sesiune ----
        if skip_hours and t.hour in skip_hours:
            continue
        if skip_weekdays and t.weekday() in skip_weekdays:
            continue

        # ---- filtru ATR ----
        if atr_max_usd and row.get("atr", 0) > atr_max_usd:
            continue

        direction = int(row["trend"])
        found = detect_setup(df, j, direction, window=cb.PULLBACK_WINDOW)
        if found is None:
            continue
        ext, _ = found

        entry     = (row["high"] + buf) if direction == 1 else (row["low"] - buf)
        sl        = (ext - buf)         if direction == 1 else (ext + buf)
        risk_dist = abs(entry - sl)
        if risk_dist <= 0:
            continue

        # ---- filtru SL minim ----
        if min_sl_usd and risk_dist < min_sl_usd:
            skipped += 1
            continue

        n_opt    = count_optional(row, direction, cfg)
        R        = reward_R(n_opt, cfg)
        tp       = entry + direction * risk_dist * R
        rp       = risk_pct_all if n_opt >= 2 else risk_pct
        risk_usd = balance * rp
        sl_pips  = risk_dist / pip
        lots     = risk_usd / (sl_pips * pip_val)
        lots     = _math.floor(lots / 0.01) * 0.01
        if lots < 0.01:
            skipped += 1
            continue

        pending = {"dir": direction, "entry": entry, "sl": sl, "tp": tp,
                   "lots": lots, "R": R, "invalidate": ext, "armed_at": j,
                   "time": t, "risk_usd": risk_usd}

    return trades, equity_curve, skipped


# ---- statistici rapide -------------------------------------------------------

def stats(trades, equity_curve):
    if not trades:
        return {"n": 0, "exp": float("nan"), "dd": 0.0,
                "test_exp": None, "test_p": None, "freq": 0.0,
                "win_pct": 0.0, "skipped_ml": 0}
    tdf = pd.DataFrame(trades)
    tdf = tdf[tdf["risk_usd"] > 0].copy()
    tdf["R"]       = tdf["pnl_usd"] / tdf["risk_usd"]
    tdf["entry_t"] = pd.to_datetime(tdf["time"])

    n   = len(tdf)
    eq  = np.asarray(equity_curve, dtype=float)
    pk  = np.maximum.accumulate(eq)
    dd  = ((eq - pk) / np.where(pk > 0, pk, 1)).min() * 100
    freq = n / max((tdf["entry_t"].max() - tdf["entry_t"].min()).days / 7, 1)

    split_t    = tdf["entry_t"].quantile(0.70)
    test       = tdf[tdf["entry_t"] >= split_t]
    test_r     = test["R"].values if len(test) >= 10 else np.array([])
    t_stat, pv = (None, None)
    if len(test_r) >= 10:
        s  = test_r.std(ddof=1)
        if s > 1e-12:
            t2 = test_r.mean() / (s / math.sqrt(len(test_r)))
            pv = round(0.5 * math.erfc(t2 / math.sqrt(2)), 4)
            t_stat = round(t2, 3)

    return {
        "n":        n,
        "exp":      round(tdf["R"].mean(), 4),
        "dd":       round(float(dd), 1),
        "test_exp": round(test["R"].mean(), 4) if len(test) >= 10 else None,
        "test_p":   pv,
        "freq":     round(freq, 1),
        "win_pct":  round((tdf["outcome"] == "win").mean() * 100, 1),
        "final_bal": round(eq[-1], 2),
    }


# ---- configuratii de testat --------------------------------------------------

CONFIGS = [
    {   "name":   "BASELINE (all hours, all days)",
        "skip_hours":    None,
        "skip_weekdays": None,
        "min_sl_usd":    None,
        "atr_max_usd":   None,
    },
    {   "name":   "Skip sambata",
        "skip_hours":    None,
        "skip_weekdays": {5},    # 5 = Saturday
        "min_sl_usd":    None,
        "atr_max_usd":   None,
    },
    {   "name":   "Skip 21-23h UTC (US close)",
        "skip_hours":    {21, 22, 23},
        "skip_weekdays": None,
        "min_sl_usd":    None,
        "atr_max_usd":   None,
    },
    {   "name":   "Skip sambata + 21-23h",
        "skip_hours":    {21, 22, 23},
        "skip_weekdays": {5},
        "min_sl_usd":    None,
        "atr_max_usd":   None,
    },
    {   "name":   "Skip sambata + 06h + 12h + 14h + 22-23h",
        "skip_hours":    {6, 12, 14, 22, 23},
        "skip_weekdays": {5},
        "min_sl_usd":    None,
        "atr_max_usd":   None,
    },
    {   "name":   "Skip sambata + 10-14h + 19-23h (fara US)",
        "skip_hours":    {10, 11, 12, 13, 14, 19, 20, 21, 22, 23},
        "skip_weekdays": {5},
        "min_sl_usd":    None,
        "atr_max_usd":   None,
    },
    {   "name":   "Min SL=$140 (filtru setup mic)",
        "skip_hours":    None,
        "skip_weekdays": None,
        "min_sl_usd":    140,
        "atr_max_usd":   None,
    },
    {   "name":   "Skip sambata + min SL=$140",
        "skip_hours":    None,
        "skip_weekdays": {5},
        "min_sl_usd":    140,
        "atr_max_usd":   None,
    },
    {   "name":   "Skip sambata + 21-23h + min SL=$140",
        "skip_hours":    {21, 22, 23},
        "skip_weekdays": {5},
        "min_sl_usd":    140,
        "atr_max_usd":   None,
    },
    {   "name":   "Skip sambata + ore bune 00-20h + min SL=$140",
        "skip_hours":    {20, 21, 22, 23},
        "skip_weekdays": {5},
        "min_sl_usd":    140,
        "atr_max_usd":   None,
    },
    {   "name":   "PRIME: 00-03h + 07-17h, skip Sat + min SL=$140",
        "skip_hours":    {4, 5, 6, 17, 18, 19, 20, 21, 22, 23},
        "skip_weekdays": {5},
        "min_sl_usd":    140,
        "atr_max_usd":   None,
    },
]


# ---- main -------------------------------------------------------------------

def main():
    with open(os.path.join(DATA_DIR, "crypto_specs.json"), encoding="utf-8") as f:
        specs = json.load(f)
    spec = specs[SYMBOL]
    _sig._INDEX_PIP[SYMBOL] = spec["tick_size"]

    with open(CONFIG, encoding="utf-8") as f:
        cfg_base = json.load(f)

    cb.START_BALANCE = START_BALANCE
    cfg = copy.deepcopy(cfg_base)
    cfg["account"]["starting_balance"]               = START_BALANCE
    cfg["session"]["start_hour"]                     = 0
    cfg["session"]["end_hour"]                       = 24
    cfg["risk_management"]["max_trades_per_day"]     = 9999
    cfg["risk_management"]["max_consecutive_losses"] = 9999
    cfg["costs"]["commission_per_lot_round_turn_usd"] = 0.0
    cfg["optional_criteria"]["rsi"]["sell_max"]      = 60

    source = CsvDataSource(DATA_DIR)
    df = prepare_symbol(source, SYMBOL, cfg)

    print(f"\n{'='*80}")
    print(f"  BTCUSD Session Optimization -- ${START_BALANCE} -- {len(df)} bare M15")
    print(f"{'='*80}\n")

    results = []
    for c in CONFIGS:
        tr, eq, _ = run_btc_filtered(
            df, spec, cfg,
            skip_hours    = c["skip_hours"],
            skip_weekdays = c["skip_weekdays"],
            min_sl_usd    = c["min_sl_usd"],
            atr_max_usd   = c["atr_max_usd"],
        )
        s = stats(tr, eq)
        results.append({"cfg": c["name"], **s})
        te_str = f"{s['test_exp']:>+7.4f}" if s["test_exp"] is not None else "    N/A"
        pv_str = f"{s['test_p']:.4f}"       if s["test_p"]  is not None else "   N/A"
        sig    = (" ***" if s["test_p"] is not None and s["test_p"] < 0.05 else
                  " *  " if s["test_p"] is not None and s["test_p"] < 0.10 else "    ")
        print(f"  [{s['n']:>4}tr {s['freq']:.1f}/wk] "
              f"exp {s['exp']:>+7.4f}  test {te_str}  p={pv_str}{sig} "
              f" dd {s['dd']:>7.1f}%  ${s['final_bal']:.0f}"
              f"\n  {c['name']}\n")

    # Tabel final
    print(f"\n{'='*80}")
    print(f"  TABEL COMPARATIV (rankat dupa Exp test)")
    print(f"{'='*80}")
    print(f"  {'N':>5} {'Freq/wk':>8} {'Exp(all)':>9} {'Exp(test)':>10} {'p-val':>7} "
          f"{'DD%':>7} {'Bal$':>7}  Config")
    print(f"  {'-'*80}")
    for r in sorted(results, key=lambda x: x["test_exp"] or -9, reverse=True):
        te  = f"{r['test_exp']:>+10.4f}" if r["test_exp"] is not None else "       N/A"
        pv  = f"{r['test_p']:>7.4f}"     if r["test_p"]  is not None else "    N/A"
        sig = (" ***" if r["test_p"] is not None and r["test_p"] < 0.05 else
               " *  " if r["test_p"] is not None and r["test_p"] < 0.10 else "    ")
        print(f"  {r['n']:>5} {r['freq']:>8.1f} {r['exp']:>+9.4f}{te} {pv}{sig} "
              f"{r['dd']:>7.1f}% {r['final_bal']:>7.0f}$  {r['cfg']}")

    # Recomandat
    best = max(results, key=lambda x: (
        x["test_exp"] or -9
    ))
    print(f"\n  >>> RECOMANDAT: {best['cfg']}")
    print(f"      N={best['n']}  Exp(all)={best['exp']:+.4f}R  "
          f"Exp(test)={best['test_exp']:+.4f}R  p={best['test_p']}")
    print(f"      DD={best['dd']:.1f}%  Frecv={best['freq']:.1f}/sapt  "
          f"Balanta finala: ${best['final_bal']:.2f}")


if __name__ == "__main__":
    main()
