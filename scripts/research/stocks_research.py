"""
Session 5 Research — Stocks + XAUUSD + US500 + FX volatil
==========================================================
Testeaza sistematic cu acelasi API ca session4_scan.py:
  - XAUUSD (Gold) — date 8+ ani, netestata ca sesiune principala
  - US500  (S&P 500) — date disponibile
  - GBPJPY, EURGBP, CADJPY — FX volatil netestata
  - Stocks: AAPL / MSFT / TSLA / NVDA (daca date disponibile in /data)

Grid: PW 4/6/8/10 × LONG/BOTH × skipMon/allDays × sesiuni multiple

Rulare: python scripts/research/stocks_research.py
"""

import os, sys, json, copy, contextlib, io
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
from strategy.signals import pip_size, _INDEX_PIP
from strategy.costs import _INDEX_TICK
from engine.portfolio import run_portfolio

# ─── pip overrides pentru simboluri noi ──────────────────────────────────────
_OVERRIDES = {
    "XAUUSD":   0.01,
    "US500":    0.01,
    "AAPL":     0.01,  "AAPL.US": 0.01,
    "MSFT":     0.01,  "MSFT.US": 0.01,
    "TSLA":     0.01,  "TSLA.US": 0.01,
    "NVDA":     0.01,  "NVDA.US": 0.01,
    "META":     0.01,  "META.US": 0.01,
    "GOOGL":    0.01,  "GOOGL.US":0.01,
    "AMZN":     0.01,  "AMZN.US": 0.01,
    "NFLX":     0.01,  "NFLX.US": 0.01,
}
for sym, pip in _OVERRIDES.items():
    _INDEX_PIP[sym] = pip

# ─── CATALOG ─────────────────────────────────────────────────────────────────

INSTRUMENTS = [
    # ── Gold ─────────────────────────────────────────────────────────────────
    dict(symbol="XAUUSD", label="Gold (XAUUSD)",
         spread_pips=0.3, start_balance=1000, skip_monday=False,
         sessions=[(7, 20), (8, 17), (13, 20)],
         note="London+NY | pip=$0.01"),

    # ── US indices ────────────────────────────────────────────────────────────
    dict(symbol="US500", label="S&P 500 (US500)",
         spread_pips=0.4, start_balance=1000, skip_monday=False,
         sessions=[(13, 21), (14, 21), (13, 20)],
         note="NYSE hours UTC"),

    # ── FX volatil ────────────────────────────────────────────────────────────
    dict(symbol="GBPJPY", label="GBP/JPY (GBPJPY)",
         spread_pips=2.0, start_balance=1000, skip_monday=True,
         sessions=[(7, 17), (0, 10), (7, 16)],
         note="London+Tokyo"),

    dict(symbol="CADJPY", label="CAD/JPY (CADJPY)",
         spread_pips=1.5, start_balance=1000, skip_monday=True,
         sessions=[(0, 10), (7, 17), (13, 21)],
         note="Tokyo+London"),

    dict(symbol="EURGBP", label="EUR/GBP (EURGBP)",
         spread_pips=1.0, start_balance=1000, skip_monday=True,
         sessions=[(7, 17), (8, 16), (6, 16)],
         note="Sesiune europeana"),

    # ── Stocks (daca exista in /data) ─────────────────────────────────────────
    dict(symbol="AAPL",    label="Apple (AAPL)",
         spread_pips=4.0, start_balance=1000, skip_monday=False,
         sessions=[(14, 21)], note="NYSE CFD"),
    dict(symbol="AAPL.US", label="Apple (AAPL.US)",
         spread_pips=4.0, start_balance=1000, skip_monday=False,
         sessions=[(14, 21)], note="NYSE CFD"),
    dict(symbol="MSFT",    label="Microsoft (MSFT)",
         spread_pips=4.0, start_balance=1000, skip_monday=False,
         sessions=[(14, 21)], note="NYSE CFD"),
    dict(symbol="MSFT.US", label="Microsoft (MSFT.US)",
         spread_pips=4.0, start_balance=1000, skip_monday=False,
         sessions=[(14, 21)], note="NYSE CFD"),
    dict(symbol="TSLA",    label="Tesla (TSLA)",
         spread_pips=6.0, start_balance=1000, skip_monday=False,
         sessions=[(14, 21)], note="NYSE CFD | spread mare"),
    dict(symbol="TSLA.US", label="Tesla (TSLA.US)",
         spread_pips=6.0, start_balance=1000, skip_monday=False,
         sessions=[(14, 21)], note="NYSE CFD | spread mare"),
    dict(symbol="NVDA",    label="Nvidia (NVDA)",
         spread_pips=6.0, start_balance=1000, skip_monday=False,
         sessions=[(14, 21)], note="NYSE CFD"),
    dict(symbol="NVDA.US", label="Nvidia (NVDA.US)",
         spread_pips=6.0, start_balance=1000, skip_monday=False,
         sessions=[(14, 21)], note="NYSE CFD"),
]

PW_VALUES  = [4, 6, 8, 10]
DIRECTIONS = [("LONG", True), ("BOTH", False)]

# ─── HELPERS ─────────────────────────────────────────────────────────────────

def ttest_one_sided(rs):
    if len(rs) < 10:
        return None
    _, p2 = _stats.ttest_1samp(rs, 0)
    return p2 / 2

def sig_label(p):
    if p is None: return ""
    if p < 0.01:  return "***"
    if p < 0.05:  return "**"
    if p < 0.10:  return "*"
    return ""

def maxdd(equity_list):
    eq = np.asarray([e["balance"] for e in equity_list], float)
    if len(eq) < 2: return 0.0
    pk = np.maximum.accumulate(eq)
    return float(((eq - pk) / np.where(pk > 0, pk, 1)).min() * 100)


def run_one(sym, inst, pw, only_long, skip_monday, session,
            cfg_base, source):
    cfg = copy.deepcopy(cfg_base)
    cfg["account"]["starting_balance"]           = inst["start_balance"]
    cfg["session"]["start_hour"]                 = 0
    cfg["session"]["end_hour"]                   = 24
    cfg["risk_management"]["max_consecutive_losses"] = 9999

    try:
        df = prepare_symbol(source, sym, cfg)
    except (FileNotFoundError, KeyError):
        return None
    if df is None or len(df) < 300:
        return None

    params = {
        "spread_pips":           {sym: inst["spread_pips"]},
        "leverage":              30,
        "start_balance":         inst["start_balance"],
        "expire_bars":           4,
        "pullback_window":       pw,
        "depth_range":           None,
        "skip_monday":           skip_monday,
        "skip_hours":            (),
        "atr_max_pips":          {},
        "max_day_consec_losses": 3,
        "corr_pairs":            {},
        "only_long":             only_long,
        "max_pos_per_symbol":    1,
        "symbol_sessions":       {sym: session},
        "symbol_skip_hours":     {},
    }

    try:
        with contextlib.redirect_stdout(io.StringIO()):
            trades, equity, balance, _, _, halted, split_time = \
                run_portfolio({sym: df}, cfg, params)
    except Exception:
        return None

    if not trades:
        return None

    tdf = pd.DataFrame(trades)
    tdf["R"]  = tdf["pnl_usd"] / tdf["risk_usd"]
    tdf["et"] = pd.to_datetime(tdf["time"])

    train = tdf[tdf["et"] <  split_time]
    test  = tdf[tdf["et"] >= split_time]

    freq = len(tdf) / max((tdf["et"].max() - tdf["et"].min()).days / 7, 1)
    dd   = maxdd(equity)

    return dict(
        n=len(tdf), n_train=len(train), n_test=len(test),
        exp_all=tdf["R"].mean(),
        exp_train=train["R"].mean() if len(train) >= 5 else float("nan"),
        exp_test=test["R"].mean()   if len(test)  >= 5 else float("nan"),
        p_train=ttest_one_sided(train["R"].values),
        p_test=ttest_one_sided(test["R"].values),
        freq=freq, dd=dd, balance=balance,
        split_time=split_time,
    )


# ─── MAIN ────────────────────────────────────────────────────────────────────

def main():
    print("=" * 76)
    print("  SESSION 5 RESEARCH — Stocks + XAUUSD + US500 + FX volatil")
    print("=" * 76)

    with open(CONFIG, encoding="utf-8") as f:
        cfg_base = json.load(f)
    source = CsvDataSource(DATA_DIR)

    candidates = []   # configuratii cu edge (p_test < 0.10, exp_test > 0)
    skipped    = []

    for inst in INSTRUMENTS:
        sym = inst["symbol"]

        # verifica rapid daca datele exista
        f15 = os.path.join(DATA_DIR, f"{sym}_M15.csv")
        f30 = os.path.join(DATA_DIR, f"{sym}_M30.csv")
        if not os.path.exists(f15) or not os.path.exists(f30):
            skipped.append(sym)
            continue

        rows = sum(1 for _ in open(f15)) - 1
        try:
            t0 = pd.read_csv(f15, usecols=["time"], nrows=1)["time"].iloc[0]
            t1 = pd.read_csv(f15, usecols=["time"]).tail(1)["time"].iloc[0]
            yrs = (pd.Timestamp(t1) - pd.Timestamp(t0)).days / 365.25
        except Exception:
            yrs = 0

        print(f"\n{'─'*76}")
        print(f"  {inst['label']}  ({yrs:.1f} ani, {rows:,} bare M15)")
        print(f"  Sesiuni testate: {inst['sessions']}  spread={inst['spread_pips']}p")
        print(f"{'─'*76}")

        best = None

        for session in inst["sessions"]:
            for pw in PW_VALUES:
                for dir_lbl, only_long in DIRECTIONS:
                    for skip_mon in [True, False]:
                        r = run_one(sym, inst, pw, only_long, skip_mon,
                                    session, cfg_base, source)
                        if r is None or r["n"] < 15:
                            continue

                        p_t = r["p_test"]
                        e_t = r["exp_test"]
                        sm  = "skipMon" if skip_mon else "allDay"
                        flag = ""
                        if e_t is not None and not np.isnan(e_t) and e_t > 0:
                            if p_t and p_t < 0.05:
                                flag = "  *** EDGE BINE"
                            elif p_t and p_t < 0.10:
                                flag = "  * EDGE"

                        p_str = f"{p_t:.3f}{sig_label(p_t)}" if p_t else "  N/A"
                        e_str = f"{e_t:+.3f}" if (e_t and not np.isnan(e_t)) else "  N/A"
                        e_tr  = f"{r['exp_train']:+.3f}" if not np.isnan(r["exp_train"]) else "N/A"

                        print(
                            f"  {session[0]:02d}-{session[1]:02d}h "
                            f"PW={pw:2d} {dir_lbl:<4} {sm:<7} | "
                            f"n={r['n']:3d}({r['n_train']:3d}tr/{r['n_test']:3d}te) "
                            f"train={e_tr}R  test={e_str}R  "
                            f"p={p_str}  {r['freq']:.1f}/s  DD={r['dd']:.0f}%{flag}"
                        )

                        if (e_t and not np.isnan(e_t) and e_t > 0 and
                                p_t and p_t < 0.10 and r["freq"] >= 0.3):
                            candidates.append(dict(
                                symbol=sym, label=inst["label"],
                                session=session, pw=pw,
                                direction=dir_lbl, skip_monday=skip_mon,
                                **r
                            ))

                        if best is None or (
                            e_t and not np.isnan(e_t) and
                            (best["exp_test"] is None or
                             np.isnan(best["exp_test"]) or
                             e_t > best["exp_test"])
                        ):
                            best = dict(session=session, pw=pw, dir=dir_lbl,
                                        sm=skip_mon, **r)

        if best and best.get("exp_test") and not np.isnan(best["exp_test"]):
            sm = "skipMon" if best["sm"] else "allDay"
            e_te = best["exp_test"]
            p_te = best["p_test"]
            p_str = f"p={p_te:.3f}{sig_label(p_te)}" if p_te else "p=N/A"
            print(
                f"\n  >> CEL MAI BUN: {best['session'][0]:02d}-{best['session'][1]:02d}h "
                f"PW={best['pw']} {best['dir']} {sm} | "
                f"test={e_te:+.3f}R {p_str} {best['freq']:.1f}/s "
                f"DD={best['dd']:.0f}%"
            )

    # ── SUMAR ─────────────────────────────────────────────────────────────────
    print("\n" + "=" * 76)
    print("  SUMAR — Configuratii viabile (p_test < 0.10, exp_test > 0)")
    print("=" * 76)

    if skipped:
        print(f"  Fara date (skip): {', '.join(skipped)}")
        print()

    if not candidates:
        print("  Niciun instrument cu edge statistic confirmat.")
    else:
        candidates.sort(key=lambda x: x["exp_test"] if x["exp_test"] else -99,
                        reverse=True)
        print(f"  {'Instrument':<22} {'Config':<26} "
              f"{'Train':>7} {'Test':>7} {'p_test':>8} {'Freq':>6} {'DD':>6}")
        print("  " + "-" * 80)
        for r in candidates:
            sm  = "skipMon" if r["skip_monday"] else "allDay"
            cfg = f"{r['session'][0]:02d}-{r['session'][1]:02d}h PW={r['pw']} {r['direction']:<4} {sm}"
            et  = r["exp_test"]
            etr = r["exp_train"]
            pt  = r["p_test"]
            p_s = f"{pt:.3f}{sig_label(pt)}" if pt else "N/A"
            print(
                f"  {r['label']:<22} {cfg:<26} "
                f"{etr:>+7.3f}R {et:>+7.3f}R {p_s:>8} "
                f"{r['freq']:>5.1f}/s {r['dd']:>5.0f}%"
            )

    # ── NOTA FUTURES ─────────────────────────────────────────────────────────
    print("\n" + "=" * 76)
    print("  FUTURES la $800 — Evaluare")
    print("=" * 76)
    print("""
  ES (S&P 500 mini):  marja ~$500/contract, tick=$12.50 → risc/trade >> 1%
  NQ (Nasdaq mini):   marja ~$1000/contract → depaseste bugetul
  CL (Crude Oil):     marja ~$1000+ → nu e viabil

  Verdict: Futures NU sunt practice la $800.
  US500 CFD (avem deja date) este echivalentul S&P 500 fara constrangeri de marja.
  La $5000+ capital, futures merita revizitat.
    """)


if __name__ == "__main__":
    main()
