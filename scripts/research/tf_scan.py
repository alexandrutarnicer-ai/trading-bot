"""
TF Scan — Research timeframe-uri mai mari: M30, H1, D1
=======================================================
Testeaza strategia pullback-in-trend pe entry TF mai mari decat M15,
pentru piete existente + noi (USDJPY, UK100, US500, US30).

Combinatii TF testate per simbol:
  M30+H1  : entry=M30, trend=H1   (simboluri cu H1 disponibil)
  M30+M30 : entry=M30, trend=M30  (simboluri fara H1: UK100, US30, XAUUSD)
  H1+D1   : entry=H1,  trend=D1   (simboluri cu H1+D1)
  D1+D1   : entry=D1,  trend=D1   (simboluri cu D1; stretch, putine semnale)

Date disponibile:
  H1+D1: EURUSD GBPUSD EURGBP AUDUSD NZDUSD USDCAD USDCHF USDJPY
         EURJPY AUDJPY CADJPY CHFJPY GBPJPY NZDJPY GER40 US500
  M30 only: UK100 US30 US2000 XAUUSD

Criterii viabilitate (identice S1/S2/S3):
  Exp(test) > 0  +  p_test < 0.10
  Spread/SL median < 25%
  DD max > -60%
  Frecventa >= 0.3 T/sapt (relaxat pentru TF mari)

Nota costuri: spread, comision si swap identice cu live (nu simulate mai mic).
  Spread = realist broker; comision $7/lot RT; swap = costuri overnight per noapte.

Rulare: python scripts/research/tf_scan.py
"""

import os, sys, copy, json, math, time as _time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
import pandas as pd
from scipy import stats as _stats

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)

from backtest import CONFIG, DATA_DIR
from adapters.csv_source import CsvDataSource
from strategy.preparation import prepare_symbol_tf
from strategy.signals import pip_size
from strategy.costs import pip_value_usd
from engine.portfolio import run_portfolio


# ============================================================================
# CATALOG INSTRUMENTE
# ============================================================================
# sess_long  = sesiune larga (default)
# sess_tight = sesiune mai stransa (alternativa)
# has_h1     = True daca exista H1 si D1 CSV in data/

INSTRUMENTS = [
    # ── FOREX EU / USD ── London + NY overlap ─────────────────────────────────
    dict(symbol="EURUSD",  cat="FOREX_EU",    label="EUR/USD",       spread=0.5,
         sess=(7, 17), skip_mon=True,  bal=1000, has_h1=True,
         note="London+NY 07-17h UTC"),
    dict(symbol="GBPUSD",  cat="FOREX_EU",    label="GBP/USD",       spread=0.8,
         sess=(7, 17), skip_mon=True,  bal=1000, has_h1=True,
         note="London+NY 07-17h UTC"),
    dict(symbol="EURGBP",  cat="FOREX_EU",    label="EUR/GBP",       spread=0.7,
         sess=(7, 17), skip_mon=True,  bal=1000, has_h1=True,
         note="London+NY 07-17h UTC"),
    dict(symbol="AUDUSD",  cat="FOREX_EU",    label="AUD/USD",       spread=1.0,
         sess=(0, 24), skip_mon=False, bal=1000, has_h1=True,
         note="Sesiune completa"),
    dict(symbol="NZDUSD",  cat="FOREX_EU",    label="NZD/USD",       spread=1.2,
         sess=(0, 24), skip_mon=False, bal=1000, has_h1=True,
         note="Sesiune completa"),
    dict(symbol="USDCAD",  cat="FOREX_EU",    label="USD/CAD",       spread=1.2,
         sess=(7, 17), skip_mon=True,  bal=1000, has_h1=True,
         note="London+NY 07-17h UTC"),
    dict(symbol="USDCHF",  cat="FOREX_EU",    label="USD/CHF",       spread=1.2,
         sess=(7, 17), skip_mon=True,  bal=1000, has_h1=True,
         note="London+NY 07-17h UTC"),
    # ── FOREX JPY ── Tokyo + early London ─────────────────────────────────────
    dict(symbol="USDJPY",  cat="FOREX_JPY",   label="USD/JPY",       spread=0.7,
         sess=(0, 10), skip_mon=True,  bal=1000, has_h1=True,
         note="Tokyo 00-10h UTC"),
    dict(symbol="EURJPY",  cat="FOREX_JPY",   label="EUR/JPY",       spread=1.2,
         sess=(0, 10), skip_mon=True,  bal=1000, has_h1=True,
         note="Tokyo 00-10h UTC"),
    dict(symbol="AUDJPY",  cat="FOREX_JPY",   label="AUD/JPY",       spread=1.5,
         sess=(0, 10), skip_mon=False, bal=1000, has_h1=True,
         note="Tokyo 00-10h UTC"),
    dict(symbol="CADJPY",  cat="FOREX_JPY",   label="CAD/JPY",       spread=1.5,
         sess=(0, 10), skip_mon=False, bal=1000, has_h1=True,
         note="Tokyo 00-10h UTC"),
    dict(symbol="CHFJPY",  cat="FOREX_JPY",   label="CHF/JPY",       spread=1.5,
         sess=(0, 10), skip_mon=False, bal=1000, has_h1=True,
         note="Tokyo 00-10h UTC"),
    dict(symbol="GBPJPY",  cat="FOREX_JPY",   label="GBP/JPY",       spread=2.0,
         sess=(7, 17), skip_mon=True,  bal=1000, has_h1=True,
         note="London+NY 07-17h UTC"),
    dict(symbol="NZDJPY",  cat="FOREX_JPY",   label="NZD/JPY",       spread=1.5,
         sess=(0, 10), skip_mon=False, bal=1000, has_h1=True,
         note="Tokyo 00-10h UTC"),
    # ── INDICI EU ─────────────────────────────────────────────────────────────
    dict(symbol="GER40",   cat="INDICES_EU",  label="DAX   (GER40)", spread=1.5,
         sess=(7, 16), skip_mon=False, bal=1000, has_h1=True,
         note="Piata EU cash 07-16h UTC"),
    dict(symbol="UK100",   cat="INDICES_EU",  label="FTSE  (UK100)", spread=2.0,
         sess=(7, 16), skip_mon=False, bal=1000, has_h1=False,
         note="Piata UK cash 07-16h UTC | M30 only"),
    # ── INDICI US ─────────────────────────────────────────────────────────────
    dict(symbol="US500",   cat="INDICES_US",  label="S&P500 (US500)",spread=0.5,
         sess=(13, 21), skip_mon=False, bal=1000, has_h1=True,
         note="NYSE 13-21h UTC"),
    dict(symbol="US30",    cat="INDICES_US",  label="Dow   (US30)",  spread=3.0,
         sess=(13, 21), skip_mon=False, bal=1000, has_h1=False,
         note="NYSE 13-21h UTC | M30 only"),
    dict(symbol="US2000",  cat="INDICES_US",  label="Russ. (US2000)",spread=0.5,
         sess=(13, 21), skip_mon=False, bal=1000, has_h1=False,
         note="NYSE 13-21h UTC | M30 only"),
    # ── MARFURI ───────────────────────────────────────────────────────────────
    dict(symbol="XAUUSD",  cat="COMMODITIES", label="Gold  (XAUUSD)",spread=0.25,
         sess=(7, 17), skip_mon=False, bal=1000, has_h1=False,
         note="London+NY 07-17h UTC | M30 only"),
]


# ============================================================================
# HELPERS STATISTICI
# ============================================================================

def ttest_one_sided(arr):
    """H0: mean<=0. Returneaza p-value one-sided (dreapta)."""
    a = np.asarray(arr, float)
    n = len(a)
    if n < 10:
        return None
    s = a.std(ddof=1)
    if s < 1e-12:
        return None
    t = a.mean() / (s / math.sqrt(n))
    return round(float(1 - _stats.t.cdf(t, df=n - 1)), 4)


def sig_label(p):
    if p is None:  return ""
    if p < 0.01:   return "***"
    if p < 0.05:   return "**"
    if p < 0.10:   return "*"
    return ""


def maxdd(equity_list):
    eq = np.asarray([e["balance"] for e in equity_list], float)
    if len(eq) < 2:
        return 0.0
    pk = np.maximum.accumulate(eq)
    dd = ((eq - pk) / np.where(pk > 0, pk, 1)).min() * 100
    return round(float(dd), 1)


def compute_spread_sl(trades, symbol, spread_pips_val):
    pip = pip_size(symbol)
    ratios = []
    for tr in trades:
        sl_pips = abs(tr["entry"] - tr["sl"]) / pip
        if sl_pips > 0:
            ratios.append(spread_pips_val / sl_pips * 100)
    return round(float(np.median(ratios)), 1) if ratios else float("nan")


# ============================================================================
# RUN O COMBINATIE
# ============================================================================

def run_one(sym, entry_tf, trend_tf, session, skip_mon, spread, bal, pw,
            expire, cfg_base, source):
    """
    Ruleaza backtestul pentru sym cu entry_tf/trend_tf dati.
    Returneaza dict cu statistici, sau None daca datele lipsesc.
    """
    cfg = copy.deepcopy(cfg_base)
    cfg["account"]["starting_balance"]            = bal
    cfg["session"]["start_hour"]                  = 0
    cfg["session"]["end_hour"]                    = 24
    cfg["risk_management"]["max_trades_per_day"]  = 5
    cfg["risk_management"]["max_consecutive_losses"] = 9999
    cfg["optional_criteria"]["rsi"]["sell_max"]   = 60   # simetric BOTH

    try:
        df = prepare_symbol_tf(source, sym, cfg, entry_tf=entry_tf, trend_tf=trend_tf)
    except FileNotFoundError:
        return None
    except Exception as e:
        print(f"    PREP EROARE {sym} {entry_tf}+{trend_tf}: {e}")
        return None

    params = {
        "spread_pips":            {sym: spread},
        "leverage":               30,
        "start_balance":          bal,
        "expire_bars":            expire,
        "pullback_window":        pw,
        "depth_range":            None,
        "skip_monday":            skip_mon,
        "skip_hours":             (),
        "atr_max_pips":           {},
        "max_day_consec_losses":  3,
        "corr_pairs":             {},
        "only_long":              False,
        "max_pos_per_symbol":     1,
        "symbol_sessions":        {sym: session},
        "symbol_skip_hours":      {},
    }

    try:
        trades, equity, balance, _, _, halted, split_time = \
            run_portfolio({sym: df}, cfg, params)
    except Exception as e:
        print(f"    RUN EROARE {sym}: {e}")
        return None

    if not trades:
        return {"symbol": sym, "n": 0, "exp_all": 0.0, "exp_train": 0.0,
                "exp_test": 0.0, "wr": 0.0, "p_train": None, "p_test": None,
                "dd": 0.0, "freq": 0.0, "sp_sl": float("nan"),
                "bal": bal, "bal0": bal, "ret_pct": 0.0,
                "n_train": 0, "n_test": 0, "split_time": split_time,
                "halted": halted}

    tdf = pd.DataFrame(trades)
    tdf["R"]       = tdf["pnl_usd"] / tdf["risk_usd"]
    tdf["entry_t"] = pd.to_datetime(tdf["time"])

    span_days = (tdf["entry_t"].max() - tdf["entry_t"].min()).days
    freq_wk   = len(tdf) / max(span_days / 7, 1)

    train = tdf[tdf["entry_t"] <  split_time]
    test  = tdf[tdf["entry_t"] >= split_time]

    dd       = maxdd(equity)
    p_train  = ttest_one_sided(train["R"].values) if len(train) >= 10 else None
    p_test   = ttest_one_sided(test["R"].values)  if len(test)  >= 10 else None
    sp_sl    = compute_spread_sl(trades, sym, spread)
    wins     = (tdf["outcome"] == "win").sum()

    return {
        "symbol":    sym,
        "n":         len(tdf),
        "n_train":   len(train),
        "n_test":    len(test),
        "exp_all":   round(tdf["R"].mean(), 4),
        "exp_train": round(train["R"].mean(), 4) if len(train) else 0.0,
        "exp_test":  round(test["R"].mean(),  4) if len(test)  else 0.0,
        "wr":        round(wins / len(tdf) * 100, 1),
        "p_train":   p_train,
        "p_test":    p_test,
        "dd":        dd,
        "freq":      round(freq_wk, 1),
        "sp_sl":     sp_sl,
        "bal":       round(balance, 0),
        "bal0":      bal,
        "ret_pct":   round((balance - bal) / bal * 100, 1),
        "split_time": split_time,
        "halted":    halted,
    }


# ============================================================================
# HELPERS AFISARE
# ============================================================================

def verdict(r, min_freq=0.3):
    if r is None or r["n"] < 20:
        return "INSUF"
    sp_ok  = not math.isnan(r["sp_sl"]) and r["sp_sl"] < 25
    p_ok   = r["p_test"] is not None and r["p_test"] < 0.10
    dd_ok  = r["dd"] > -60
    exp_ok = r["exp_test"] > 0
    frq_ok = r["freq"] >= min_freq
    if sp_ok and p_ok and dd_ok and exp_ok and frq_ok:
        return "VIABLE"
    elif exp_ok and sp_ok and frq_ok:
        return "MARGINAL"
    else:
        return "REJECTAT"


def print_row(label, tf_tag, r, inst):
    if r is None:
        print(f"  {label:<22} {tf_tag:<10}   — date lipsa")
        return
    if r["n"] < 5:
        print(f"  {label:<22} {tf_tag:<10}   prea putine trades ({r['n']})")
        return
    p_s = (f"{r['p_test']:.4f}{sig_label(r['p_test'])}"
           if r["p_test"] is not None else "  N/A")
    verd = verdict(r)
    sp_s = f"{r['sp_sl']:.1f}%" if not math.isnan(r["sp_sl"]) else "  N/A"
    print(
        f"  {label:<22} {tf_tag:<10} {r['n']:>5} "
        f"{r['exp_all']:>+9.4f} {r['exp_test']:>+10.4f} "
        f"{p_s:>9} {sp_s:>7} "
        f"{r['dd']:>+7.1f}% {r['freq']:>5.1f}/w {r['ret_pct']:>+6.1f}%"
        f"  {verd}"
    )


# ============================================================================
# MAIN
# ============================================================================

def main():
    SEP  = "=" * 90
    SEP2 = "-" * 90

    print(SEP)
    print("  TF SCAN — Research M30 / H1 / D1 Entry Timeframes")
    print("  Piete: Forex (EU+JPY), Indici (EU+US), Marfuri")
    print("  Costuri: spread realist broker + comision $7/lot RT + swap overnight")
    print(SEP)

    with open(CONFIG, encoding="utf-8") as f:
        cfg_base = json.load(f)

    source = CsvDataSource(DATA_DIR)

    # --------------------------------------------------------
    # Configuratii TF de testat
    # (label, entry_tf, trend_tf, expire_bars, pw_list, require_h1)
    # --------------------------------------------------------
    TF_CFGS = [
        ("M30+H1",  "M30", "H1",  4, [6, 8], True),   # simboluri cu H1
        ("M30+M30", "M30", "M30", 4, [6, 8], False),   # fallback fara H1
        ("H1+D1",   "H1",  "D1",  4, [6, 8], True),
        ("D1+D1",   "D1",  "D1",  2, [4, 6], True),
    ]

    all_results = {}   # symbol -> {tf_label -> best_result}
    t_start = _time.time()

    for inst in INSTRUMENTS:
        sym   = inst["symbol"]
        label = inst["label"]
        print(f"\n{'-'*60}")
        print(f"  {label}  [{inst['cat']}]  spread={inst['spread']}pip  "
              f"sess={inst['sess']}h UTC  skip_mon={inst['skip_mon']}")
        print(f"  {inst['note']}")

        sym_results = {}

        for (tf_label, entry_tf, trend_tf, expire, pw_list, req_h1) in TF_CFGS:
            # M30+H1 si H1+D1 si D1+D1 → numai pentru simboluri cu H1
            if req_h1 and not inst["has_h1"]:
                continue
            # M30+M30 → numai pentru simboluri fara H1
            if not req_h1 and inst["has_h1"]:
                continue

            # pentru D1, sesiunea trebuie sa fie (0,24) (bare daily la 00:00)
            sess = (0, 24) if entry_tf == "D1" else inst["sess"]
            skip = False   if entry_tf == "D1" else inst["skip_mon"]

            best = None
            for pw in pw_list:
                print(f"    {tf_label}  PW={pw}  ", end="", flush=True)
                r = run_one(sym, entry_tf, trend_tf, sess, skip,
                            inst["spread"], inst["bal"], pw, expire, cfg_base, source)
                if r is None:
                    print("date lipsa — sarit")
                    break
                if r["n"] < 5:
                    print(f"N={r['n']} prea mic — sarit")
                    continue

                p_s = (f"p_test={r['p_test']:.4f}{sig_label(r['p_test'])}"
                       if r["p_test"] is not None else "p_test=N/A")
                sp_s = f"sp/SL={r['sp_sl']:.1f}%" if not math.isnan(r["sp_sl"]) else "sp/SL=N/A"
                print(f"N={r['n']:4d}  exp_test={r['exp_test']:+.4f}R  "
                      f"{p_s}  {sp_s}  DD={r['dd']:+.1f}%  {r['freq']:.1f}/wk")

                r["pw"]       = pw
                r["tf_label"] = tf_label
                if best is None or r["exp_test"] > best["exp_test"]:
                    best = r

            sym_results[tf_label] = best

        all_results[sym] = (inst, sym_results)

    elapsed = _time.time() - t_start
    print(f"\n\nScan complet in {elapsed/60:.1f} minute.")

    # ==========================================================================
    # TABEL SUMAR PER TIMEFRAME
    # ==========================================================================
    header = (f"  {'Simbol':<22} {'TF Combo':<10} {'N':>5} {'Exp(all)':>9} "
              f"{'Exp(test)':>10} {'p_test':>9} {'Sp/SL':>7} {'DD':>8} "
              f"{'T/wk':>6} {'Ret%':>6}  Verdict")

    for tf_label in ["M30+H1", "M30+M30", "H1+D1", "D1+D1"]:
        # gaseste daca exista rezultate pentru acest TF
        has_any = any(
            tf_label in sym_res
            for _, sym_res in all_results.values()
            if sym_res
        )
        if not has_any:
            continue

        print(f"\n\n{SEP}")
        print(f"  RAPORT {tf_label} — toate simbolurile")
        print(SEP)
        print(header)
        print(f"  {SEP2[:88]}")

        cat_order = ["FOREX_EU", "FOREX_JPY", "INDICES_EU", "INDICES_US", "COMMODITIES"]
        cat_labels = {
            "FOREX_EU":    "FOREX — London / NY",
            "FOREX_JPY":   "FOREX — Tokyo / JPY",
            "INDICES_EU":  "INDICI — Europa",
            "INDICES_US":  "INDICI — SUA",
            "COMMODITIES": "MARFURI",
        }

        for cat in cat_order:
            printed_header = False
            for inst in INSTRUMENTS:
                if inst["cat"] != cat:
                    continue
                sym = inst["symbol"]
                sym_res = all_results.get(sym, (inst, {}))[1]
                r = sym_res.get(tf_label)
                if r is None and tf_label not in sym_res:
                    continue
                if not printed_header:
                    print(f"\n  -- {cat_labels[cat]} --")
                    printed_header = True
                print_row(inst["label"], tf_label, r, inst)

    # ==========================================================================
    # RAPORT CONSOLIDAT — TOP REZULTATE
    # ==========================================================================
    print(f"\n\n{SEP}")
    print("  RAPORT CONSOLIDAT — Cele mai bune rezultate per simbol (toate TF)")
    print(SEP)

    viable    = []
    marginal  = []
    rejected  = []

    print(header)
    print(f"  {SEP2[:88]}")

    cat_order = ["FOREX_EU", "FOREX_JPY", "INDICES_EU", "INDICES_US", "COMMODITIES"]
    cat_labels = {
        "FOREX_EU":    "FOREX — London / NY",
        "FOREX_JPY":   "FOREX — Tokyo / JPY",
        "INDICES_EU":  "INDICI — Europa",
        "INDICES_US":  "INDICI — SUA",
        "COMMODITIES": "MARFURI",
    }

    for cat in cat_order:
        print(f"\n  -- {cat_labels[cat]} --")
        for inst in INSTRUMENTS:
            if inst["cat"] != cat:
                continue
            sym     = inst["symbol"]
            sym_res = all_results.get(sym, (inst, {}))[1]

            # alege cel mai bun TF per simbol (maxim exp_test)
            best_r  = None
            for tf_label, r in sym_res.items():
                if r is None or r["n"] < 20:
                    continue
                if best_r is None or r["exp_test"] > best_r["exp_test"]:
                    best_r = r

            print_row(inst["label"], best_r["tf_label"] if best_r else "—", best_r, inst)

            if best_r is not None:
                v = verdict(best_r)
                if v == "VIABLE":
                    viable.append((sym, best_r))
                elif v == "MARGINAL":
                    marginal.append((sym, best_r))
                else:
                    rejected.append(sym)
            else:
                rejected.append(sym)

    # ==========================================================================
    # DETALIU VIABILE
    # ==========================================================================
    print(f"\n\n{SEP}")
    print("  DETALIU — Instrumente VIABLE (trec toate criteriile)")
    print(SEP)

    if not viable:
        print("  Niciun instrument nu trece toate criteriile.")
    else:
        for sym, r in viable:
            inst = next(i for i in INSTRUMENTS if i["symbol"] == sym)
            print(f"\n  {inst['label']}  [TF={r['tf_label']}  PW={r['pw']}]")
            print(f"  Sesiune: {inst['sess']}h UTC  spread={inst['spread']}pip  "
                  f"capital=${inst['bal']}")
            print(f"  Trades : {r['n']} total  "
                  f"(train={r['n_train']}, test={r['n_test']})  "
                  f"WR={r['wr']:.1f}%  Freq={r['freq']:.1f}/sapt")
            print(f"  Exp all: {r['exp_all']:+.4f}R")
            if r['p_train'] is not None:
                print(f"  TRAIN ({r['n_train']}t): {r['exp_train']:+.4f}R  "
                      f"p={r['p_train']:.4f}{sig_label(r['p_train'])}")
            else:
                print(f"  TRAIN ({r['n_train']}t): {r['exp_train']:+.4f}R  p=N/A")
            if r['p_test'] is not None:
                print(f"  TEST  ({r['n_test']}t): {r['exp_test']:+.4f}R  "
                      f"p={r['p_test']:.4f}{sig_label(r['p_test'])}")
            else:
                print(f"  TEST  ({r['n_test']}t): {r['exp_test']:+.4f}R  p=N/A")
            print(f"  Spread/SL: {r['sp_sl']:.1f}%  |  DD max: {r['dd']:+.1f}%")
            print(f"  Balanta: ${r['bal0']} → ${r['bal']:.0f}  ({r['ret_pct']:+.1f}%)")
            print(f"  Split train/test: {r['split_time'].date()}")

    # ==========================================================================
    # DETALIU MARGINAL
    # ==========================================================================
    if marginal:
        print(f"\n\n{SEP}")
        print("  DETALIU — Instrumente MARGINALE (exp_test>0 dar p>=0.10)")
        print(SEP)
        for sym, r in marginal:
            inst = next(i for i in INSTRUMENTS if i["symbol"] == sym)
            p_s = (f"p={r['p_test']:.4f}{sig_label(r['p_test'])}"
                   if r["p_test"] is not None else "p=N/A")
            print(f"  {inst['label']:<22} [TF={r['tf_label']}  PW={r['pw']}]  "
                  f"N={r['n']}  exp_test={r['exp_test']:+.4f}R  {p_s}  "
                  f"DD={r['dd']:+.1f}%  {r['freq']:.1f}/wk")

    # ==========================================================================
    # VERDICT FINAL
    # ==========================================================================
    print(f"\n\n{SEP}")
    print("  VERDICT FINAL")
    print(SEP)
    viable_syms   = [s for s, _ in viable]
    marginal_syms = [s for s, _ in marginal]

    print(f"\n  VIABLE    ({len(viable_syms)}):   {viable_syms if viable_syms else '—'}")
    print(f"  MARGINALE ({len(marginal_syms)}):  {marginal_syms if marginal_syms else '—'}")
    print(f"  RESPINSE  ({len(rejected)}):  {rejected}")

    # Grupat pe TF pentru recomandari de sesiune paralela
    if viable_syms or marginal_syms:
        all_good = [(s, r) for s, r in viable] + [(s, r) for s, r in marginal]
        by_tf = {}
        for s, r in all_good:
            tf = r["tf_label"]
            by_tf.setdefault(tf, []).append(s)

        print(f"\n  Recomandare sesiuni paralele (adaugat peste M15 existente):")
        for tf, syms in sorted(by_tf.items()):
            sess_info = {}
            for sym in syms:
                inst = next(i for i in INSTRUMENTS if i["symbol"] == sym)
                sess_info.setdefault(str(inst["sess"]), []).append(sym)
            for sess, s_list in sess_info.items():
                print(f"    [{tf}] {sess}h UTC: {s_list}")

    print(f"\n{SEP}\n")


if __name__ == "__main__":
    main()
