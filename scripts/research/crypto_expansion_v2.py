"""
Crypto Expansion v2 — ETH/BNB/SOL/XRP vs 4 sesiuni
=====================================================
Obiectiv: gaseste 2-3 alternative la S3 BTC cu budget $300-500
Control:  BTCUSD cu sesiunea validata (ar trebui pozitiv ~+0.336R)

Diferenta critica vs run_portfolio:
  run_portfolio  pip_val = tick_value/tick_size = 0.01/0.01 = 1.0 (normalizat)
  run_crypto     pip_val = tick_value           = 0.01        (raw)
  → la run_portfolio: lots = risk×tick_size/sl_dist = 100x mai mic! 0 tranzactii BTC
  → TREBUIE sa folosim run_crypto pentru toate calculele crypto.

Simboluri: BTCUSD (control), ETHUSD, BNBUSD, SOLUSD, XRPUSD
Sesiuni:   4 variante via skip_hours
Grid:      PW [6,8] x BOTH/LONG = 4 combos × 4 sesiuni = 16/simbol
Total:     5 sym × 16 = 80 combos
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
import scripts.research.crypto_backtest as cb

# ── Simboluri si specs ──────────────────────────────────────────────────────
SPECS_FILE = os.path.join(DATA_DIR, "crypto_specs.json")
with open(SPECS_FILE, encoding="utf-8") as f:
    SPECS = json.load(f)

SYMBOLS = ["BTCUSD", "ETHUSD", "BNBUSD", "SOLUSD", "XRPUSD"]

# ── Sesiuni (convertite la skip_hours pentru run_crypto) ────────────────────
# Format: (label, skip_hours_set, skip_weekdays_set)
# Session windows → skip hours outside window
def _window_to_skip(start, end):
    """Orele din afara ferestrei [start, end) de sarit."""
    return set(range(0, start)) | set(range(end, 24))

SESSION_CONFIGS = [
    # BTC-validated: skip EU mid-day 10-14h + US prime seara 19-23h + Sambata
    ("btc_proven",
     {10,11,12,13,14,19,20,21,22,23},
     {5}),
    # Noapte: 00-08h UTC (Asia low-vol, BTC/ETH trending)
    ("night_00_08",
     _window_to_skip(0, 8),
     {5, 6}),
    # EU+NY overlap: 08-20h UTC (volum maxim crypto)
    ("eu_ny_08_20",
     _window_to_skip(8, 20),
     {5, 6}),
    # Baseline 24/7: fara filtre de timp (doar skip Sambata)
    ("full24_7",
     set(),
     {5}),
]

PW_LIST     = [6, 8]
DIRS        = [("BOTH", False, False), ("LONG", True, False)]
BALANCE     = 500  # $500 — identic cu config live Session 3


# ── Utilitare ───────────────────────────────────────────────────────────────

def ttest_os(rs):
    if len(rs) < 10:
        return None
    return _stats.ttest_1samp(rs, 0).pvalue / 2


def sig(p):
    if p is None: return ""
    if p < 0.01:  return "***"
    if p < 0.05:  return "**"
    if p < 0.10:  return "*"
    return ""


def maxdd(equity_curve):
    eq = np.array(equity_curve, float)
    if len(eq) < 2: return 0.0
    pk = np.maximum.accumulate(eq)
    return float(((eq - pk) / np.where(pk > 0, pk, 1)).min() * 100)


def run_one(sym, df, spec, sess_label, skip_hours, skip_weekdays,
            pw, only_long, only_short, cfg_base):
    """
    Ruleaza o combinatie cu run_crypto (corect pentru pip_val crypto).
    Returneaza dict cu statistici sau None.
    """
    # Seteaza globals in modulul crypto_backtest
    cb.START_BALANCE    = BALANCE
    cb.PULLBACK_WINDOW  = pw
    cb.EXPIRE_BARS      = 4

    cfg = copy.deepcopy(cfg_base)
    cfg["account"]["starting_balance"]               = BALANCE
    cfg["session"]["start_hour"]                     = 0
    cfg["session"]["end_hour"]                       = 24
    cfg["risk_management"]["max_trades_per_day"]     = 9999
    cfg["risk_management"]["max_consecutive_losses"] = 9999

    try:
        trades, equity_curve, equity_tl, skipped = cb.run_crypto(
            df, sym, spec, cfg,
            only_long     = only_long,
            only_short    = only_short,
            skip_hours    = skip_hours    or None,
            skip_weekdays = skip_weekdays or None,
        )
    except Exception:
        return None

    if not trades:
        return None

    tdf = pd.DataFrame(trades)
    tdf = tdf[tdf["risk_usd"] > 0].copy()
    if len(tdf) < 10:
        return None

    tdf["R"]  = tdf["pnl_usd"] / tdf["risk_usd"]
    tdf["et"] = pd.to_datetime(tdf["time"])

    # Train/test split la 70% din intervalul de timp
    t_min = tdf["et"].min()
    t_max = tdf["et"].max()
    span  = t_max - t_min
    split_time = t_min + span * 0.70

    train = tdf[tdf["et"] <  split_time]
    test  = tdf[tdf["et"] >= split_time]
    freq  = len(tdf) / max(span.days / 7, 1)

    return dict(
        n=len(tdf), n_tr=len(train), n_te=len(test),
        e_tr=train["R"].mean() if len(train) >= 5 else float("nan"),
        e_te=test["R"].mean()  if len(test)  >= 5 else float("nan"),
        p_tr=ttest_os(train["R"].values) if len(train) >= 10 else None,
        p_te=ttest_os(test["R"].values)  if len(test)  >= 10 else None,
        freq=freq, dd=maxdd(equity_curve),
        split=split_time.strftime("%Y-%m"),
        n_skip=skipped,
    )


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    banner = "=" * 82
    print(banner)
    print(f"  CRYPTO EXPANSION v2 — ETH / BNB / SOL / XRP  (BTC = control)")
    print(f"  balance=${BALANCE}  risk=1%  engine=run_crypto  spread=real_MT5")
    print(banner)

    with open(CONFIG, encoding="utf-8") as f:
        cfg_base = json.load(f)
    source = CsvDataSource(DATA_DIR)

    all_candidates = []

    for sym in SYMBOLS:
        f15 = os.path.join(DATA_DIR, f"{sym}_M15.csv")
        f30 = os.path.join(DATA_DIR, f"{sym}_M30.csv")
        if not os.path.exists(f15) or not os.path.exists(f30):
            print(f"\n  {sym}: date lipsa — SKIP")
            continue
        if sym not in SPECS:
            print(f"\n  {sym}: specs lipsa — SKIP")
            continue

        spec = SPECS[sym]

        try:
            t0   = pd.read_csv(f15, usecols=["time"], nrows=1)["time"].iloc[0]
            t1   = pd.read_csv(f15, usecols=["time"]).tail(1)["time"].iloc[0]
            rows = sum(1 for _ in open(f15)) - 1
            yrs  = (pd.Timestamp(t1) - pd.Timestamp(t0)).days / 365.25
        except Exception:
            yrs, rows = 0, 0

        spread_usd  = spec["spread_price"]
        pip_val_raw = spec["tick_value_usd"]
        tick_sz     = spec["tick_size"]

        print(f"\n{'─'*82}")
        print(f"  {sym}  ({yrs:.1f} ani, {rows:,} bare M15)")
        print(f"  tick_size={tick_sz}  pip_val={pip_val_raw}  spread=${spread_usd:.3f} ({spec['spread_ticks']} ticks)")
        print(f"{'─'*82}")

        # Inregistreaza pip override pentru prepare_symbol
        from strategy import signals as _sig
        _sig._INDEX_PIP[sym] = tick_sz

        # prepare_symbol O SINGURA DATA per simbol
        cfg_prep = copy.deepcopy(cfg_base)
        cfg_prep["account"]["starting_balance"] = BALANCE
        cfg_prep["session"]["start_hour"] = 0
        cfg_prep["session"]["end_hour"]   = 24
        cfg_prep["risk_management"]["max_consecutive_losses"] = 9999
        try:
            df_sym = prepare_symbol(source, sym, cfg_prep)
        except Exception as e:
            print(f"  {sym}: eroare prepare_symbol ({e}) — SKIP")
            continue
        if df_sym is None or len(df_sym) < 300:
            print(f"  {sym}: date insuficiente — SKIP")
            continue

        sym_best = None

        for sess_label, skip_hours, skip_weekdays in SESSION_CONFIGS:
            # Calculeaza fereastra activa pentru afisare
            active_h = sorted(set(range(24)) - skip_hours)
            if active_h:
                window_str = f"{active_h[0]:02d}-{active_h[-1]+1:02d}h"
            else:
                window_str = "00-24h"
            days_str = "Mon-Sun" if not skip_weekdays else (
                "Mon-Fri" if {5,6}.issubset(skip_weekdays) else "Mon-Sat"
            )
            print(f"\n  ── {sess_label} ({window_str}, {days_str})")

            for pw in PW_LIST:
                for dlbl, only_long, only_short in DIRS:
                    r = run_one(sym, df_sym, spec, sess_label,
                                skip_hours, skip_weekdays,
                                pw, only_long, only_short, cfg_base)

                    if r is None or r["n"] < 15:
                        print(f"    PW={pw} {dlbl:<4} | n<15 sau 0 tranzactii")
                        continue

                    p_s  = f"{r['p_te']:.3f}{sig(r['p_te'])}" if r["p_te"] else "  N/A"
                    e_s  = f"{r['e_te']:+.3f}" if not np.isnan(r["e_te"]) else "  N/A"
                    e_r  = f"{r['e_tr']:+.3f}" if not np.isnan(r["e_tr"]) else "  N/A"
                    skip_s = f" skip={r['n_skip']}" if r.get("n_skip") else ""

                    flag = ""
                    is_edge = (
                        r["p_te"] and r["p_te"] < 0.10
                        and not np.isnan(r["e_te"]) and r["e_te"] > 0
                        and r["freq"] >= 0.3
                    )
                    if is_edge:
                        flag = "  *** EDGE" if r["p_te"] < 0.05 else "  * edge"

                    print(f"    PW={pw} {dlbl:<4} | n={r['n']:4d} "
                          f"train={e_r}R test={e_s}R p={p_s} "
                          f"{r['freq']:.1f}/s DD={r['dd']:+.0f}%"
                          f" [{r['split']}]{skip_s}{flag}")

                    if is_edge:
                        all_candidates.append(dict(
                            sym=sym, sess=sess_label, pw=pw, dir=dlbl, **r
                        ))

                    e_te_v = r["e_te"] if not np.isnan(r["e_te"]) else float("-inf")
                    if sym_best is None or e_te_v > (
                        sym_best["e_te"] if not np.isnan(sym_best["e_te"]) else float("-inf")
                    ):
                        sym_best = dict(sess=sess_label, pw=pw, dir=dlbl, **r)

        if sym_best and not np.isnan(sym_best.get("e_te", float("nan"))):
            p_s = (f"{sym_best['p_te']:.3f}{sig(sym_best['p_te'])}"
                   if sym_best["p_te"] else "N/A")
            print(f"\n  >> {sym} CEL MAI BUN: {sym_best['sess']} PW={sym_best['pw']} "
                  f"{sym_best['dir']} | test={sym_best['e_te']:+.3f}R "
                  f"p={p_s} {sym_best['freq']:.1f}/s DD={sym_best['dd']:+.0f}%")

    # ── Sumar final ─────────────────────────────────────────────────────────
    print("\n" + "=" * 82)
    print("  SUMAR FINAL — Crypto cu edge confirmat (p<0.10, exp>0, >=0.3/s)")
    print("=" * 82)

    if not all_candidates:
        print("  Niciun instrument cu edge confirmat.")
    else:
        all_candidates.sort(key=lambda x: (x["e_te"] if not np.isnan(x["e_te"]) else -999), reverse=True)
        print(f"  {'Sym':<8} {'Sesiune':<15} {'PW':>3} {'Dir':<5} {'Train':>8} "
              f"{'Test':>8} {'p':>8} {'Freq':>5} {'DD':>6}")
        print("  " + "-" * 74)
        for c in all_candidates:
            p_s  = f"{c['p_te']:.3f}{sig(c['p_te'])}"
            e_tr = f"{c['e_tr']:>+8.3f}R" if not np.isnan(c.get("e_tr", float("nan"))) else "     N/A"
            print(f"  {c['sym']:<8} {c['sess']:<15} PW={c['pw']:2d} {c['dir']:<5} "
                  f"{e_tr} {c['e_te']:>+8.3f}R {p_s:>8} {c['freq']:>4.1f}/s {c['dd']:>+5.0f}%")

    print()
    print("  Recomandari pentru buget $300-500 (bazate pe vol_min MT5):")
    print("  - ETH: vol_min=0.01 @ $1,628  → risc $5-30/tranzactie (10-6% din $500)")
    print("  - BNB: vol_min=0.01 @ $586    → risc $1-5/tranzactie   (2-1% din $500)")
    print("  - SOL: vol_min=1.0  @ $63     → risc $1-3/tranzactie   (live: MT5 forced)")
    print("  - XRP: vol_min=100  @ $1.10   → risc $2-5/tranzactie   (live: MT5 forced)")


if __name__ == "__main__":
    main()
