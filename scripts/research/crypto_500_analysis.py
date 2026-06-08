"""
Analiza completa crypto $500 — spread live MT5 + backtest individual + verdict
==============================================================================
Buget tinta: $500 (de preferat), max $700. Obiectiv: 1-3 piete crypto active.

Structura:
  1. Refresh spreads live din MT5 (crypto = 24/7, spread real acum)
  2. Backtest individual per pereche la $500, ambele directii, 24/7
  3. Analiza per pereche: spread/SL, train/test+p-value, long/short,
                          R-levels (pe target R), annual breakdown, swap
  4. Verdict final rankat cu recomandare de portofoliu

Nota R: tdf["R"] = target R (2.5/3.5/4.5) pastrat din pending.
        tdf["R_actual"] = pnl_usd / risk_usd (incluzand spread + swap).

Prerequizit: data deja descarcata (descarca_crypto.py rulat anterior).
Rulare: python scripts/research/crypto_500_analysis.py
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

# ---- configurare --------------------------------------------------------------

START_BALANCE     = 500
MIN_HISTORY_YEARS = 2.5   # minim pentru robustete (exclude SOL/XRP cu 2025+)

SYMBOLS_ALL = ["BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "ADAUSD", "LTCUSD", "BNBUSD"]
CRYPTO_SPECS_FILE = os.path.join(DATA_DIR, "crypto_specs.json")

# ---- STEP 1: Refresh spreads live din MT5 -----------------------------------

def refresh_spreads_mt5():
    print("=" * 65)
    print("STEP 1 -- Spreads live din MT5")
    print("=" * 65)

    try:
        import MetaTrader5 as mt5
    except ImportError:
        print("  MetaTrader5 nu e instalat -- folosesc specs existente")
        with open(CRYPTO_SPECS_FILE, encoding="utf-8") as f:
            return json.load(f)

    if not mt5.initialize():
        print(f"  MT5 initialize() esuat: {mt5.last_error()} -- folosesc specs existente")
        with open(CRYPTO_SPECS_FILE, encoding="utf-8") as f:
            return json.load(f)

    with open(CRYPTO_SPECS_FILE, encoding="utf-8") as f:
        specs = json.load(f)

    print(f"\n  {'Simbol':<10} {'ticks':>7} {'spread_price':>14}  delta")
    print(f"  {'-'*50}")

    for sym in list(specs.keys()):
        if not mt5.symbol_select(sym, True):
            print(f"  {sym:<10} *** simbol indisponibil")
            continue
        info = mt5.symbol_info(sym)
        if info is None:
            continue

        sp_ticks = info.spread
        sp_price = round(sp_ticks * info.trade_tick_size, 8)
        prev     = specs[sym]["spread_ticks"]
        delta    = f"  (era {prev} ticks)" if sp_ticks != prev else "  (neschimbat)"

        specs[sym]["spread_ticks"] = sp_ticks
        specs[sym]["spread_price"] = sp_price
        print(f"  {sym:<10} {sp_ticks:>7}  {sp_price:>14.7f}{delta}")

    mt5.shutdown()

    with open(CRYPTO_SPECS_FILE, "w", encoding="utf-8") as f:
        json.dump(specs, f, indent=2)
    print(f"\n  Specs actualizate: {CRYPTO_SPECS_FILE}\n")
    return specs


# ---- STEP 2: Backtest per pereche -------------------------------------------

def run_all_backtests(specs, cfg_base, source):
    print("=" * 65)
    print(f"STEP 2 -- Backtests la ${START_BALANCE} (1% risc = ${START_BALANCE*0.01:.0f}/trade)")
    print("=" * 65)

    cb.START_BALANCE = START_BALANCE

    cfg = copy.deepcopy(cfg_base)
    cfg["account"]["starting_balance"]               = START_BALANCE
    cfg["session"]["start_hour"]                     = 0
    cfg["session"]["end_hour"]                       = 24
    cfg["risk_management"]["max_trades_per_day"]     = 9999
    cfg["risk_management"]["max_consecutive_losses"] = 9999
    cfg["costs"]["commission_per_lot_round_turn_usd"] = 0.0
    cfg["optional_criteria"]["rsi"]["sell_max"]       = 60

    results = {}

    for sym in SYMBOLS_ALL:
        if sym not in specs:
            continue
        try:
            df = prepare_symbol(source, sym, cfg)
        except FileNotFoundError:
            print(f"  {sym}: date lipsesc -- skip")
            continue

        t_start = df["time"].min()
        t_end   = df["time"].max()
        years   = (t_end - t_start).days / 365.25

        trades, equity, _, skipped = cb.run_crypto(df, sym, specs[sym], cfg)
        n = len(trades)
        hist_flag = "  *** SCURT ***" if years < MIN_HISTORY_YEARS else ""
        print(f"  {sym:<10}: {n:>5} trades  ({skipped:>4} sarite)  "
              f"{t_start.date()} -> {t_end.date()}  [{years:.1f} ani]{hist_flag}")

        if n > 0:
            tdf = pd.DataFrame(trades)
            tdf = tdf[tdf["risk_usd"] > 0].copy()
            # R_target = tinta planificata (2.5/3.5/4.5) din pending dict
            tdf = tdf.rename(columns={"R": "R_target"})
            # R_actual = pnl real / risk (include spread + swap)
            tdf["R_actual"]        = tdf["pnl_usd"] / tdf["risk_usd"]
            tdf["entry_t"]         = pd.to_datetime(tdf["time"])
            tdf["year"]            = tdf["entry_t"].dt.year
            tdf["risk_dist_price"] = (tdf["entry"] - tdf["sl"]).abs()
            sp = specs[sym]["spread_price"]
            tdf["spread_over_sl"]  = sp / tdf["risk_dist_price"].replace(0, np.nan)
        else:
            tdf = pd.DataFrame()

        results[sym] = {
            "df":       tdf,
            "equity":   equity,
            "skipped":  skipped,
            "years":    round(years, 1),
            "t_start":  t_start.date(),
            "t_end":    t_end.date(),
            "spec":     specs[sym],
        }

    print()
    return results, cfg


# ---- helpers statistici -----------------------------------------------------

def p_val_one_sided(arr):
    """H0: mean(R) <= 0, H1 > 0. Returneaza (t, p) sau (None, None) daca n < 10."""
    n = len(arr)
    if n < 10:
        return None, None
    a = np.asarray(arr, dtype=float)
    s = a.std(ddof=1)
    if s < 1e-12:
        return None, None
    t = a.mean() / (s / math.sqrt(n))
    p = 0.5 * math.erfc(t / math.sqrt(2))
    return round(t, 3), round(p, 4)


def ci_95(arr):
    n = len(arr)
    if n < 2:
        return None, None
    a  = np.asarray(arr, dtype=float)
    m, s = a.mean(), a.std(ddof=1)
    se   = s / math.sqrt(n)
    _t   = {1: 12.71, 2: 4.30, 3: 3.18, 4: 2.78, 5: 2.57, 6: 2.45, 7: 2.36,
            8: 2.31, 9: 2.26, 10: 2.23, 15: 2.13, 20: 2.09, 30: 2.04,
            40: 2.02, 60: 2.00, 120: 1.98}
    tc = next((v for k, v in sorted(_t.items()) if n <= k), 1.96)
    return round(m - tc * se, 4), round(m + tc * se, 4)


def dd_pct(equity):
    eq   = np.asarray(equity, dtype=float)
    peak = np.maximum.accumulate(eq)
    dd   = ((eq - peak) / np.where(peak > 0, peak, 1)).min() * 100
    return round(float(dd), 1)


# ---- analiza detaliata per pereche ------------------------------------------

def analyze_pair(sym, res):
    spec   = res["spec"]
    tdf    = res["df"]
    equity = res["equity"]
    years  = res["years"]
    sp     = spec["spread_price"]
    sp_tk  = spec["spread_ticks"]

    print(f"\n{'='*65}")
    print(f"  {sym}  {res['t_start']} -> {res['t_end']}  ({years:.1f} ani)")
    print(f"  spread={sp_tk} ticks = {sp:.7f}"
          f"  tick={spec['tick_size']}  pip_val=${spec['pip_val']:.4f}"
          f"  cs={spec['contract_size']:.0f}")
    print(f"  swap_long={spec['swap_long']:.1f}%/an  "
          f"swap_short={spec['swap_short']:.1f}%/an  mode={spec['swap_mode']}")
    print(f"{'='*65}")

    if len(tdf) == 0:
        print(f"  0 tranzactii executate")
        if res["skipped"]:
            pct = res["skipped"] / max(res["skipped"], 1) * 100
            print(f"  {res['skipped']} setup-uri sarite (lots < 0.01 -- capital insuficient)")
        return {}

    n    = len(tdf)
    wins = (tdf["outcome"] == "win").sum()
    exp  = tdf["R_actual"].mean()
    freq = n / max((tdf["entry_t"].max() - tdf["entry_t"].min()).days / 7, 1)
    dd   = dd_pct(equity)
    ret  = (equity[-1] - START_BALANCE) / START_BALANCE * 100

    swap_total = tdf["swap"].sum() if "swap" in tdf else 0.0
    gross_pnl  = (tdf["pnl_usd"] - (tdf["swap"] if "swap" in tdf else 0)).sum()
    swap_pct   = swap_total / abs(gross_pnl) * 100 if abs(gross_pnl) > 0.01 else 0.0

    sp_sl_med  = tdf["spread_over_sl"].median() * 100
    sp_sl_p90  = tdf["spread_over_sl"].quantile(0.90) * 100

    print(f"  Balanta: ${START_BALANCE} -> ${equity[-1]:.2f}  ({ret:+.1f}%)")
    print(f"  Trades  : {n}  ({res['skipped']} sarite)  |  Win: {wins/n*100:.1f}%"
          f"  |  Expectancy: {exp:+.4f} R")
    print(f"  DD max  : {dd:.1f}%  |  Frecv: {freq:.1f} trades/sapt")
    print(f"  Swap    : ${swap_total:.2f} total ({swap_pct:.1f}% din PnL brut)")
    print(f"  Spread/SL: median {sp_sl_med:.1f}%  p90 {sp_sl_p90:.1f}%"
          + ("  <<< PREA MARE" if sp_sl_med > 30 else "  [OK]" if sp_sl_med < 15 else "  [MARGINAL]"))

    # ---- Train / Test 70/30 ----
    split_t = tdf["entry_t"].quantile(0.70)
    train   = tdf[tdf["entry_t"] <  split_t]
    test    = tdf[tdf["entry_t"] >= split_t]
    print(f"\n  -- TRAIN / TEST 70/30 --")
    test_exp  = None
    test_pval = None
    for label, dset in [("TRAIN", train), ("TEST ", test)]:
        if len(dset) < 3:
            print(f"  {label}: prea putine trades ({len(dset)})")
            continue
        w = (dset["outcome"] == "win").sum()
        t_s, pval = p_val_one_sided(dset["R_actual"].values)
        lo, hi    = ci_95(dset["R_actual"].values)
        sig = ""
        if pval is not None:
            sig = ("  *** SEMN ***" if pval < 0.05 else
                   "  (* marginal)" if pval < 0.10 else "")
        p_str  = f"  t={t_s:.2f}  p={pval:.4f}{sig}" if pval is not None else ""
        ci_str = f"  IC95:[{lo:.3f},{hi:.3f}]" if lo is not None else ""
        print(f"  {label}: {len(dset):4d} trades | win {w/len(dset)*100:.1f}%"
              f" | exp {dset['R_actual'].mean():+.4f} R{p_str}{ci_str}")
        if label == "TEST ":
            test_exp  = dset["R_actual"].mean()
            test_pval = pval

    # ---- Long vs Short ----
    print(f"\n  -- LONG vs SHORT --")
    for lbl, d_val in [("LONG  (+1)", 1), ("SHORT (-1)", -1)]:
        sub = tdf[tdf["direction"] == d_val] if "direction" in tdf else pd.DataFrame()
        if len(sub) == 0:
            continue
        w = (sub["outcome"] == "win").sum()
        t_s, pval = p_val_one_sided(sub["R_actual"].values)
        sig = ("  SEMN" if pval is not None and pval < 0.05 else
               "  marg" if pval is not None and pval < 0.10 else "")
        print(f"  {lbl}: {len(sub):4d} trades | win {w/len(sub)*100:.1f}%"
              f" | exp {sub['R_actual'].mean():+.4f} R"
              + (f"  p={pval:.4f}{sig}" if pval is not None else ""))

    # ---- Edge pe R target ----
    print(f"\n  -- Edge per R tinta (R_target = recompensa planificata) --")
    print(f"  {'R-tinta':>8} {'N':>6} {'Win%':>7} {'Exp R_actual':>13} {'Breakeven%':>12}")
    for rb in [2.5, 3.5, 4.5]:
        sub = tdf[tdf["R_target"] == rb]
        if len(sub) == 0:
            continue
        w  = (sub["outcome"] == "win").sum()
        wr = w / len(sub)
        be = 1 / (1 + rb) * 100
        exp_r = sub["R_actual"].mean()
        ok = "OK" if exp_r > 0 else "--"
        print(f"  {rb:>8.1f} {len(sub):>6} {wr*100:>7.1f}%"
              f" {exp_r:>+13.4f} R  (be={be:.1f}%)  {ok}")

    # ---- Annual ----
    print(f"\n  -- Expectancy per an (dependenta de regim bull/bear) --")
    ann = tdf.groupby("year").agg(
        trades=("R_actual", "count"),
        exp=("R_actual", "mean"),
        win=("outcome", lambda x: (x == "win").mean() * 100),
        swap=("swap", "sum") if "swap" in tdf.columns else ("R_actual", lambda x: 0),
    ).reset_index()
    for _, row in ann.iterrows():
        sign = "+" if row.exp >= 0 else " "
        print(f"  {int(row.year)}: {int(row.trades):4d} trades"
              f" | win {row.win:.1f}%"
              f" | exp {sign}{row.exp:.4f} R"
              f" | swap ${row.swap:.2f}")

    # ---- Min-lot la $500 vs $700 ----
    risk_5   = START_BALANCE * 0.01
    risk_7   = 700 * 0.01
    avg_sl   = tdf["risk_dist_price"].mean()
    pip      = spec["tick_size"]
    pip_val  = spec["tick_value_usd"]
    min_risk = 0.01 * (avg_sl / pip) * pip_val   # cost minim lot 0.01
    skip_500 = (tdf["risk_usd"] / ((tdf["risk_dist_price"] / pip) * pip_val) < 0.01).sum()
    print(f"\n  Min-lot $500: {res['skipped']} setup-uri sarite"
          f"  (SL mediu={avg_sl:.5f}, min risk={min_risk:.2f}$)")
    needed   = math.ceil(min_risk / 0.01 * 100)   # capital necesar pt lot minim la avg SL
    print(f"  Capital necesar pt. toate setup-urile: ~${needed}")

    return {
        "n":            n,
        "skipped":      res["skipped"],
        "win_pct":      round(wins / n * 100, 1),
        "exp_R":        round(exp, 4),
        "dd_pct":       dd,
        "freq_wk":      round(freq, 1),
        "swap_total":   round(swap_total, 2),
        "swap_pct_pnl": round(swap_pct, 1),
        "sp_sl_median": round(sp_sl_med, 1),
        "years":        years,
        "ret_pct":      round(ret, 1),
        "test_exp":     round(test_exp, 4) if test_exp is not None else None,
        "test_pval":    test_pval,
        "t_start":      res["t_start"],
    }


# ---- STEP 5: Verdict --------------------------------------------------------

def print_verdict(all_stats):
    print(f"\n{'='*75}")
    print(f"  TABEL REZUMATIV -- TOATE PERECHILE -- ${START_BALANCE}")
    print(f"{'='*75}")
    hdr = (f"  {'Simbol':<10} {'Ani':>5} {'N':>6} {'Skip':>5} {'Win%':>6} "
           f"{'Exp(all)':>9} {'Exp(test)':>10} {'p-val':>7} "
           f"{'DD%':>7} {'Sp/SL%':>7}")
    print(hdr)
    print(f"  {'-'*74}")

    ranked = sorted(
        [(s, d) for s, d in all_stats.items() if d],
        key=lambda x: (x[1].get("test_exp") or -9),
        reverse=True,
    )

    viable = []
    for sym, s in ranked:
        if not s or s.get("n", 0) == 0:
            print(f"  {sym:<10}  --- 0 trades ---")
            continue

        te  = f"{s['test_exp']:>+10.4f}" if s["test_exp"] is not None else "       N/A"
        pv  = f"{s['test_pval']:>7.4f}" if s["test_pval"] is not None else "    N/A"
        sig = (" ***" if s["test_pval"] is not None and s["test_pval"] < 0.05 else
               "  * " if s["test_pval"] is not None and s["test_pval"] < 0.10 else
               "    ")
        hist = " [SCURT]" if s["years"] < MIN_HISTORY_YEARS else ""

        print(f"  {sym:<10} {s['years']:>5.1f} {s['n']:>6} {s['skipped']:>5} "
              f"{s['win_pct']:>6.1f}% {s['exp_R']:>+9.4f}{te} {pv}{sig} "
              f"{s['dd_pct']:>7.1f}% {s['sp_sl_median']:>6.1f}%{hist}")

        passes = (
            s["test_exp"] is not None
            and s["test_exp"] > 0
            and s["sp_sl_median"] < 30
            and s["years"] >= MIN_HISTORY_YEARS
            and s["dd_pct"] > -85
        )
        if passes:
            viable.append((sym, s))

    # ---- VERDICT ----
    print(f"\n{'='*75}")
    print(f"  VERDICT FINAL -- crypto M15 la ${START_BALANCE}")
    print(f"{'='*75}")

    criteria = [
        "  (1) Exp(test) > 0  [edge confirmat pe date nevazute]",
        "  (2) Spread/SL median < 30%  [cost de executie gestionabil]",
        f"  (3) Istoric >= {MIN_HISTORY_YEARS} ani  [include bull + bear market]",
        "  (4) DD max < -85%  [supravietuieste pana la urmatorul trade]",
    ]
    print(f"\n  Criterii minime de viabilitate:")
    for c in criteria:
        print(c)

    if not viable:
        print(f"\n  CONCLUZIE: NICIO PERECHE NU TRECE TOATE CRITERIILE la ${START_BALANCE}.")

        print(f"\n  Diagnosticul pieselor-cheie:")
        for sym, s in ranked[:5]:
            if not s or s.get("n", 0) == 0:
                continue
            issues = []
            if s["sp_sl_median"] >= 30:
                issues.append(f"spread/SL {s['sp_sl_median']:.0f}% (prea mare)")
            if s["years"] < MIN_HISTORY_YEARS:
                issues.append(f"doar {s['years']:.1f} ani date")
            if s.get("test_exp") is not None and s["test_exp"] <= 0:
                issues.append(f"exp test {s['test_exp']:+.3f}R (negativ)")
            if s["dd_pct"] <= -85:
                issues.append(f"DD {s['dd_pct']:.0f}%")
            print(f"  {sym}: {' | '.join(issues) if issues else 'trece!'}")

        print(f"\n  DE CE CRYPTO CFD NU FUNCTIONEAZA LA {START_BALANCE}$ CU ACEST BROKER:")
        print(f"  1. Altcoins (ADA, XRP, DOGE): spread in ticks este enorm relativ la")
        print(f"     distantele de SL structurale ale setup-urilor M15 pullback.")
        print(f"     Median spread/SL > 50% => pierdere garantata pe termen lung.")
        print(f"  2. BTC: setupuri cu SL > $500 sunt sarite (lots < 0.01).")
        print(f"     La $500 cont, ~30-50% din setup-uri BTC sunt nefezabile.")
        print(f"  3. ETH/LTC: pret intermediar + spread rezonabil => cel mai bun candidat.")
        print(f"     VERIFICA dupa rezultate daca ETH sau LTC au expectancy > 0.")

        print(f"\n  ALTERNATIVA RECOMANDATA:")
        print(f"  1. Forex / indici (Session 1 + 2) -- edge confirmat, spread mic relativ la SL")
        print(f"  2. Daca vrei crypto: asteapta cont de minim $1000-1500 (BTC tranzactionabil)")
        print(f"     sau cauta broker cu spread <20 ticks pe BTC/ETH (ECN/prime broker)")
    else:
        print(f"\n  PIETE RECOMANDATE ({len(viable)} din {len(all_stats)}):")
        for i, (sym, s) in enumerate(viable[:3], 1):
            pv_str = (f"semnificativ (p={s['test_pval']:.3f})" if s["test_pval"] is not None and s["test_pval"] < 0.05 else
                      f"marginal (p={s['test_pval']:.3f})"      if s["test_pval"] is not None and s["test_pval"] < 0.10 else
                      f"p={s['test_pval']:.3f}"                 if s["test_pval"] is not None else "n/a")
            print(f"\n  {i}. {sym}")
            print(f"     Exp (test) : {s['test_exp']:+.4f} R  -- {pv_str}")
            print(f"     Exp (all)  : {s['exp_R']:+.4f} R  |  Win: {s['win_pct']:.1f}%")
            print(f"     DD max     : {s['dd_pct']:.1f}%")
            print(f"     Spread/SL  : {s['sp_sl_median']:.1f}% median")
            print(f"     Frecventa  : {s['freq_wk']:.1f} trades/saptamana")
            print(f"     Swap total : ${s['swap_total']:.2f} ({s['swap_pct_pnl']:.1f}% din PnL brut)")
            print(f"     Istoric    : {s['years']:.1f} ani ({s['t_start']} -- azi)")

        if len(viable) >= 2:
            print(f"\n  PORTOFOLIU SUGERAT ({min(len(viable),3)} piete simultan):")
            names = " + ".join(s for s, _ in viable[:3])
            print(f"  {names}")
            print(f"  Risk: 1% per trade | max 3 pozitii = max 3% risc total pe cont")
            print(f"  Atentie: crypto = corelat in bear market => DD real poate fi mai mare")
            print(f"  Recomandare: incepe cu 1 pereche 3 luni live, apoi adauga restul")


# ---- main -------------------------------------------------------------------

def main():
    print(f"\n{'='*65}")
    print(f"  ANALIZA CRYPTO COMPLETA -- ${START_BALANCE} capital -- 2026-06-08")
    print(f"{'='*65}\n")

    specs = refresh_spreads_mt5()

    for sym, sp in specs.items():
        _sig._INDEX_PIP[sym] = sp["tick_size"]

    with open(CONFIG, encoding="utf-8") as f:
        cfg_base = json.load(f)

    source = CsvDataSource(DATA_DIR)

    results, cfg = run_all_backtests(specs, cfg_base, source)

    print(f"\n{'='*65}")
    print(f"STEP 3+4 -- Analiza detaliata per pereche")
    print(f"{'='*65}")

    all_stats = {}
    for sym in SYMBOLS_ALL:
        if sym not in results:
            all_stats[sym] = {}
            continue
        res = results[sym]
        if len(res["df"]) == 0:
            all_stats[sym] = {
                "n": 0, "skipped": res["skipped"], "win_pct": 0.0, "exp_R": float("nan"),
                "dd_pct": 0.0, "freq_wk": 0.0, "swap_total": 0.0, "swap_pct_pnl": 0.0,
                "sp_sl_median": 999.0, "years": res["years"], "ret_pct": 0.0,
                "test_exp": None, "test_pval": None, "t_start": res["t_start"],
            }
            print(f"\n  {sym}: 0 trades executate  ({res['skipped']} sarite min-lot)")
            continue
        stats = analyze_pair(sym, res)
        all_stats[sym] = stats

        # Salveaza CSV trades per pereche
        out = os.path.join(DATA_DIR, f"crypto_trades_{sym}.csv")
        res["df"].to_csv(out, index=False)

    print_verdict(all_stats)

    print(f"\n{'='*65}")
    print(f"  Gata. CSV in data/crypto_trades_<SIMBOL>.csv")
    print(f"{'='*65}\n")


if __name__ == "__main__":
    main()
