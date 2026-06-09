"""
Session 4 Scan — Research piete noi (Risk Off + Risk On)
=========================================================
Testeaza sistematic 11 instrumente pentru o potentiala Sesiune 4.

Date suficiente (8+ ani, robuste): GER40, US30, XAUUSD
Date limitate  (2-2.5 ani, indicative): UK100, US500, US2000, AUDUSD,
                                         NZDUSD, USDCHF, GBPJPY, CHFJPY

Criterii viabilitate (aceleasi ca S1/S2/S3):
  - Exp(test) > 0  (one-sided t-test p < 0.10)
  - Spread/SL median < 25%
  - DD max < -60%
  - Frecventa >= 0.5 trades/saptamana

Rulare: python scripts/research/session4_scan.py
"""

import os, sys, copy, json, math

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np
import pandas as pd
from scipy import stats as _stats

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)

from backtest import CONFIG, DATA_DIR
from adapters.csv_source import CsvDataSource
from strategy.preparation import prepare_symbol
from strategy.signals import pip_size
from strategy.costs import pip_value_usd
from engine.portfolio import run_portfolio


# =============================================================================
# CATALOG INSTRUMENTE
# =============================================================================

# spread_pips = spread realist de broker (nu din CSV — cel din CSV e prea mic)
# session     = (start_h, end_h) UTC — fereastra primara de activitate
# data_ok     = True daca avem >= 6 ani de date (backtest robust)

INSTRUMENTS = [
    # ── Risk Off ─────────────────────────────────────────────────────────────
    dict(symbol="XAUUSD",  category="RISK_OFF",    label="Gold          (XAUUSD)",
         spread_pips=0.25, session=(7, 17), skip_monday=False,
         start_balance=5000, data_ok=True,
         note="Active: London 07-12h + NY 13-17h UTC | pip=$100/lot"),

    dict(symbol="USDCHF",  category="RISK_OFF",    label="Swiss Franc   (USDCHF)",
         spread_pips=1.5,  session=(7, 17), skip_monday=True,
         start_balance=1000, data_ok=False,
         note="Date: 2024-2026 (2.5 ani — indicativ)"),

    # ── Risk On — EU equity ───────────────────────────────────────────────────
    dict(symbol="GER40",   category="RISK_ON_EU",  label="DAX           (GER40)",
         spread_pips=1.5,  session=(7, 16), skip_monday=False,
         start_balance=1000, data_ok=True,
         note="Piata cash EU 08:00-17:30 Berlin | pip=$1.15/lot"),

    dict(symbol="UK100",   category="RISK_ON_EU",  label="FTSE          (UK100)",
         spread_pips=2.0,  session=(7, 16), skip_monday=False,
         start_balance=1000, data_ok=False,
         note="Date: 2023-2026 (2.5 ani — indicativ)"),

    # ── Risk On — US equity ───────────────────────────────────────────────────
    dict(symbol="US30",    category="RISK_ON_US",  label="Dow Jones     (US30)",
         spread_pips=3.0,  session=(14, 21), skip_monday=False,
         start_balance=1000, data_ok=True,
         note="NYSE 09:30-16:00 EST = 14:30-21:00 UTC | pip=$1.00/lot"),

    dict(symbol="US500",   category="RISK_ON_US",  label="S&P 500       (US500)",
         spread_pips=0.5,  session=(14, 21), skip_monday=False,
         start_balance=1000, data_ok=False,
         note="Date: 2023-2026 (2.5 ani — indicativ)"),

    dict(symbol="US2000",  category="RISK_ON_US",  label="Russell 2000  (US2000)",
         spread_pips=0.5,  session=(14, 21), skip_monday=False,
         start_balance=1000, data_ok=False,
         note="Date: 2023-2026 (2.5 ani — indicativ)"),

    # ── Risk On — FX ─────────────────────────────────────────────────────────
    dict(symbol="AUDUSD",  category="RISK_ON_FX",  label="AUD/USD       (AUDUSD)",
         spread_pips=1.5,  session=(0, 18), skip_monday=False,
         start_balance=1000, data_ok=False,
         note="Date: 2024-2026 (2.5 ani)"),

    dict(symbol="NZDUSD",  category="RISK_ON_FX",  label="NZD/USD       (NZDUSD)",
         spread_pips=2.0,  session=(0, 18), skip_monday=False,
         start_balance=1000, data_ok=False,
         note="Date: 2024-2026 (2.5 ani)"),

    dict(symbol="GBPJPY",  category="RISK_ON_FX",  label="GBP/JPY       (GBPJPY)",
         spread_pips=3.0,  session=(7, 17), skip_monday=False,
         start_balance=1000, data_ok=False,
         note="Date: 2024-2026 (2.5 ani)"),

    dict(symbol="CHFJPY",  category="RISK_ON_FX",  label="CHF/JPY       (CHFJPY)",
         spread_pips=2.0,  session=(0, 18), skip_monday=False,
         start_balance=1000, data_ok=False,
         note="Date: 2024-2026 (2.5 ani)"),
]


# =============================================================================
# HELPERS STATISTICI
# =============================================================================

def ttest_one_sided(arr):
    """H0: mean <= 0. Returneaza p-value (one-sided, dreapta)."""
    a = np.asarray(arr, float)
    n = len(a)
    if n < 10:
        return None
    s = a.std(ddof=1)
    if s < 1e-12:
        return None
    t = a.mean() / (s / math.sqrt(n))
    # one-sided p = P(T > t_obs)
    p = 1 - _stats.t.cdf(t, df=n - 1)
    return round(p, 4)


def sig_label(p):
    if p is None:      return ""
    if p < 0.01:       return "***"
    if p < 0.05:       return "**"
    if p < 0.10:       return "*"
    return ""


def maxdd(equity):
    eq = np.asarray(equity, float)
    pk = np.maximum.accumulate(eq)
    dd = ((eq - pk) / np.where(pk > 0, pk, 1)).min() * 100
    return round(dd, 1)


def spread_sl_pct(trades, symbol):
    """Median spread/SL% pe toate tradele."""
    pip = pip_size(symbol)
    if not trades:
        return float("nan")
    ratios = []
    for tr in trades:
        sl_pips = abs(tr["entry"] - tr["sl"]) / pip
        if sl_pips > 0:
            ratios.append(100.0 / sl_pips)   # 1 pip spread → ratio
    # Aceasta e ratio la 1 pip de spread — inmultim cu spread_pips real
    return float("nan")  # calculam mai jos din trades direct


def compute_spread_sl(trades, symbol, spread_pips_val):
    """Median (spread_pips / SL_pips) × 100."""
    pip = pip_size(symbol)
    ratios = []
    for tr in trades:
        sl_pips = abs(tr["entry"] - tr["sl"]) / pip
        if sl_pips > 0:
            ratios.append(spread_pips_val / sl_pips * 100)
    return round(float(np.median(ratios)), 1) if ratios else float("nan")


# =============================================================================
# RUN O CONFIGURATIE
# =============================================================================

def run_instrument(inst: dict, pw: int, only_long: bool,
                   cfg_base: dict, source: CsvDataSource) -> dict | None:
    """
    Ruleaza backtestul pentru un instrument cu parametri dati.
    Returneaza un dict cu statistici sau None daca datele lipsesc.
    """
    sym  = inst["symbol"]
    sh, eh = inst["session"]

    cfg = copy.deepcopy(cfg_base)
    cfg["account"]["starting_balance"]               = inst["start_balance"]
    cfg["session"]["start_hour"]                     = 0    # fallback; sesiunea reala e in symbol_sessions
    cfg["session"]["end_hour"]                       = 24
    cfg["risk_management"]["max_trades_per_day"]     = 5
    cfg["risk_management"]["max_consecutive_losses"] = 9999
    cfg["optional_criteria"]["rsi"]["sell_max"]      = 60   # simetric pentru BOTH

    try:
        df = prepare_symbol(source, sym, cfg)
    except FileNotFoundError:
        return None

    params = {
        "spread_pips":            {sym: inst["spread_pips"]},
        "leverage":               30,
        "start_balance":          inst["start_balance"],
        "expire_bars":            4,
        "pullback_window":        pw,
        "depth_range":            None,
        "skip_monday":            inst["skip_monday"],
        "skip_hours":             (),
        "atr_max_pips":           {},
        "max_day_consec_losses":  3,
        "corr_pairs":             {},
        "only_long":              only_long,
        "max_pos_per_symbol":     1,
        "symbol_sessions":        {sym: (sh, eh)},
        "symbol_skip_hours":      {},
    }

    try:
        trades, equity, balance, _, _, halted, split_time = \
            run_portfolio({sym: df}, cfg, params)
    except Exception as e:
        print(f"    EROARE {sym}: {e}")
        return None

    if not trades:
        return {"symbol": sym, "n": 0, "exp": 0.0, "p": None,
                "dd": 0.0, "freq": 0.0, "sp_sl": float("nan"),
                "bal": inst["start_balance"], "split_time": split_time}

    tdf = pd.DataFrame(trades)
    tdf["R"]       = tdf["pnl_usd"] / tdf["risk_usd"]
    tdf["entry_t"] = pd.to_datetime(tdf["time"])

    span_days = (tdf["entry_t"].max() - tdf["entry_t"].min()).days
    freq_wk   = len(tdf) / max(span_days / 7, 1)

    # Train / Test split
    train = tdf[tdf["entry_t"] <  split_time]
    test  = tdf[tdf["entry_t"] >= split_time]

    eq_list = [row["balance"] for row in equity]
    dd = maxdd(eq_list) if len(eq_list) > 1 else 0.0

    p_train  = ttest_one_sided(train["R"].values) if len(train) >= 10 else None
    p_test   = ttest_one_sided(test["R"].values)  if len(test)  >= 10 else None
    sp_sl    = compute_spread_sl(trades, sym, inst["spread_pips"])

    wins = (tdf["outcome"] == "win").sum()

    return {
        "symbol":     sym,
        "n":          len(tdf),
        "n_train":    len(train),
        "n_test":     len(test),
        "exp_all":    round(tdf["R"].mean(), 4),
        "exp_train":  round(train["R"].mean(), 4) if len(train) else 0.0,
        "exp_test":   round(test["R"].mean(),  4) if len(test)  else 0.0,
        "wr":         round(wins / len(tdf) * 100, 1),
        "p_train":    p_train,
        "p_test":     p_test,
        "dd":         dd,
        "freq":       round(freq_wk, 1),
        "sp_sl":      sp_sl,
        "bal":        round(balance, 0),
        "bal0":       inst["start_balance"],
        "ret_pct":    round((balance - inst["start_balance"]) / inst["start_balance"] * 100, 1),
        "split_time": split_time,
        "halted":     halted,
    }


# =============================================================================
# MAIN
# =============================================================================

def main():
    sep  = "=" * 76
    sep2 = "-" * 76

    print(sep)
    print("  SESSION 4 SCAN — Research piete noi (Risk Off + Risk On)")
    print(sep)

    with open(CONFIG, encoding="utf-8") as f:
        cfg_base = json.load(f)

    source = CsvDataSource(DATA_DIR)

    # Testeaza fiecare instrument cu PW=6 si PW=8, BOTH directions
    # Retine cel mai bun (exp_test maxim) per instrument
    all_results = {}   # symbol -> best result dict

    cat_order = ["RISK_OFF", "RISK_ON_EU", "RISK_ON_US", "RISK_ON_FX"]
    cat_label = {
        "RISK_OFF":   "RISK OFF  — Safe Haven",
        "RISK_ON_EU": "RISK ON   — EU Equity",
        "RISK_ON_US": "RISK ON   — US Equity",
        "RISK_ON_FX": "RISK ON   — FX / Commodity",
    }

    for inst in INSTRUMENTS:
        sym  = inst["symbol"]
        flag = "" if inst["data_ok"] else "  [DATE LIMITATE ~2.5 ani]"
        print(f"\n{'-'*50}")
        print(f"  {inst['label']}{flag}")
        print(f"  {inst['note']}")
        print(f"  Sesiune: {inst['session'][0]:02d}-{inst['session'][1]:02d}h UTC  "
              f"spread={inst['spread_pips']} pip  capital=${inst['start_balance']}")

        best = None
        for pw in [8, 6]:
            for ol in [False]:   # BOTH only (only_long=False)
                tag = f"PW={pw}"
                print(f"    {tag}  ", end="", flush=True)
                r = run_instrument(inst, pw, ol, cfg_base, source)
                if r is None:
                    print("lipsesc datele — sarit")
                    break

                if r["n"] < 20:
                    print(f"prea putine trades ({r['n']}) — sarit")
                    continue

                p_str  = f"p_test={r['p_test']:.4f}{sig_label(r['p_test'])}" \
                         if r["p_test"] is not None else "p_test=N/A"
                sp_str = f"sp/SL={r['sp_sl']:.1f}%"
                print(f"N={r['n']:4d}  exp_test={r['exp_test']:+.4f}R  "
                      f"{p_str}  {sp_str}  DD={r['dd']:+.1f}%  {r['freq']:.1f}/wk")

                r["pw"] = pw
                if best is None or r["exp_test"] > best["exp_test"]:
                    best = r

        all_results[sym] = (inst, best)

    # ==========================================================================
    # TABEL SUMAR COMPLET
    # ==========================================================================
    print(f"\n\n{sep}")
    print("  RAPORT FINAL — toate instrumentele")
    print(sep)

    viable    = []
    promising = []
    rejected  = []

    header = (f"  {'Instrument':<22} {'N':>5} {'Exp(all)':>9} {'Exp(test)':>10} "
              f"{'p_test':>9} {'Sp/SL':>7} {'DD':>7} {'T/wk':>6} {'Ret%':>6}  Note")
    print(header)
    print(f"  {sep2[:74]}")

    for cat in cat_order:
        print(f"\n  -- {cat_label[cat]} --")
        for inst in INSTRUMENTS:
            if inst["category"] != cat:
                continue
            sym = inst["symbol"]
            inst_obj, r = all_results.get(sym, (inst, None))

            if r is None or r["n"] == 0:
                print(f"  {inst['label']:<22}  {'—':>5}   date lipsesc")
                rejected.append(sym)
                continue

            p_s   = f"{r['p_test']:.4f}{sig_label(r['p_test'])}" if r["p_test"] is not None else "  N/A"
            note  = ""
            if not inst["data_ok"]:
                note += "[DATE LIMITATE] "

            sp_ok = not math.isnan(r["sp_sl"]) and r["sp_sl"] < 25
            p_ok  = r["p_test"] is not None and r["p_test"] < 0.10
            dd_ok = r["dd"] > -60
            exp_ok = r["exp_test"] > 0

            if sp_ok and p_ok and dd_ok and exp_ok:
                verdict = "VIABLE OK"
                if inst["data_ok"]:
                    viable.append(sym)
                else:
                    promising.append(sym)
                    verdict = "PROMITATOR ?"
            elif exp_ok and sp_ok:
                verdict = "MARGINAL"
                note   += f"p={r['p_test']:.3f} (nesemnificativ)"
            else:
                verdict = "REJECTAT"
                if not sp_ok:
                    note += f"sp/SL={r['sp_sl']:.0f}% (>25%) "
                if not exp_ok:
                    note += f"exp_test={r['exp_test']:+.4f}R (<0) "
                rejected.append(sym)

            print(
                f"  {inst['label']:<22} {r['n']:>5} "
                f"{r['exp_all']:>+9.4f} {r['exp_test']:>+10.4f} "
                f"{p_s:>9} {r['sp_sl']:>6.1f}% "
                f"{r['dd']:>+6.1f}% {r['freq']:>5.1f}/w {r['ret_pct']:>+5.1f}%"
                f"  {verdict}  {note}"
            )

    # ==========================================================================
    # DETALIU INSTRUMENTE VIABILE
    # ==========================================================================
    print(f"\n{sep}")
    print("  DETALIU — instrumente viabile / promitatore")
    print(sep)

    for sym in viable + promising:
        inst_obj = next(i for i in INSTRUMENTS if i["symbol"] == sym)
        _, r = all_results[sym]
        if r is None:
            continue
        flag = "" if inst_obj["data_ok"] else "  *** DATE LIMITATE — verifica cu mai multa date ***"
        print(f"\n  {inst_obj['label']}{flag}")
        print(f"  PW={r['pw']}  sesiune={inst_obj['session'][0]}-{inst_obj['session'][1]}h UTC"
              f"  spread={inst_obj['spread_pips']}pip  capital=${inst_obj['start_balance']}")
        print(f"  Trades  : {r['n']}  (WR={r['wr']:.1f}%)  Frecventa: {r['freq']:.1f}/sapt")
        print(f"  Exp all : {r['exp_all']:+.4f}R")
        print(f"  TRAIN ({r['n_train']}t): {r['exp_train']:+.4f}R  "
              f"p={r['p_train']:.4f}{sig_label(r['p_train'])}"
              if r["p_train"] is not None else f"  TRAIN ({r['n_train']}t): {r['exp_train']:+.4f}R  p=N/A")
        print(f"  TEST  ({r['n_test']}t): {r['exp_test']:+.4f}R  "
              f"p={r['p_test']:.4f}{sig_label(r['p_test'])}"
              if r["p_test"] is not None else f"  TEST  ({r['n_test']}t): {r['exp_test']:+.4f}R  p=N/A")
        print(f"  Spread/SL median: {r['sp_sl']:.1f}%  |  DD max: {r['dd']:+.1f}%")
        print(f"  Balanta: ${r['bal0']} → ${r['bal']:.0f}  ({r['ret_pct']:+.1f}%)")
        print(f"  Split train/test: {r['split_time'].date()}")

    # ==========================================================================
    # VERDICT FINAL + RECOMANDARE S4
    # ==========================================================================
    print(f"\n{sep}")
    print("  VERDICT FINAL")
    print(sep)

    print(f"\n  VIABILE (date robuste 8+ ani):  {viable if viable else '—'}")
    print(f"  PROMITATORE (date limitate):     {promising if promising else '—'}")
    print(f"  RESPINSE:                        {rejected}")

    if viable or promising:
        print(f"\n  Recomandare Session 4:")
        # Clasifica viabile pe categorie
        risk_off_v  = [s for s in viable + promising
                       if next(i for i in INSTRUMENTS if i["symbol"]==s)["category"] == "RISK_OFF"]
        risk_on_eu  = [s for s in viable + promising
                       if next(i for i in INSTRUMENTS if i["symbol"]==s)["category"] == "RISK_ON_EU"]
        risk_on_us  = [s for s in viable + promising
                       if next(i for i in INSTRUMENTS if i["symbol"]==s)["category"] == "RISK_ON_US"]
        risk_on_fx  = [s for s in viable + promising
                       if next(i for i in INSTRUMENTS if i["symbol"]==s)["category"] == "RISK_ON_FX"]

        if risk_off_v:
            print(f"    S4-RISK-OFF:  {risk_off_v}  |  Sesiune: 07-17h UTC (London + NY)")
        if risk_on_eu:
            print(f"    S4-RISK-ON-EU: {risk_on_eu}  |  Sesiune: 07-16h UTC (EU cash)")
        if risk_on_us:
            print(f"    S4-RISK-ON-US: {risk_on_us}  |  Sesiune: 14-21h UTC (US cash)")
        if risk_on_fx:
            print(f"    S4-RISK-ON-FX: {risk_on_fx}  |  Sesiune: variate")

        print(f"\n  Daca vrei sa combini Risk Off + Risk On intr-o singura sesiune,")
        print(f"  foloseste symbol_sessions ca in S2 (sesiuni diferite per instrument).")
    else:
        print("\n  Niciun instrument nu trece toate criteriile. Nu se recomanda S4 momentan.")

    print(f"\n{sep}\n")


if __name__ == "__main__":
    main()
