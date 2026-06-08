"""
Optimizare Session 2 — test comprehensiv
==========================================
Baza: ALL BOTH PW=6, 6 piete (3 EUR + 3 JPY), sesiuni separate, M15 proxy.

Teste:
  A  — SKIP_MONDAY: True vs False pe combo actual
  B  — Piete noi: EURGBP (European), AUDUSD/CADJPY/CHFJPY (Asian)
  C  — Portofolii combinate 7-9 piete cu cele mai bune adausuri
  D  — Variatie PW pe portofoliile extinse
  E  — M5 backtest (daca datele M5 sunt disponibile)

Rulare: python session2_optimize.py
"""

import json, copy, contextlib, io, time, os
import numpy as np, pandas as pd

from backtest import CONFIG, DATA_DIR
from adapters.csv_source import CsvDataSource
from strategy.preparation import prepare_symbol, prepare_symbol_tf
from engine.portfolio import run_portfolio

# ---- configuratii sesiuni ---------------------------------------------------

EUR_SESS   = (10, 18)
ASIAN_SESS = (2, 10)

CORE_EUR   = ["EURUSD", "GBPUSD", "EURJPY"]
CORE_ASIAN = ["USDJPY", "AUDJPY", "NZDJPY"]
NEW_EUR    = ["EURGBP"]
NEW_ASIAN  = ["AUDUSD", "CADJPY", "CHFJPY"]

SPREAD_PIPS = {
    "EURUSD": 0.5, "GBPUSD": 0.8, "EURJPY": 1.5,
    "USDJPY": 0.5, "AUDJPY": 1.5, "NZDJPY": 1.5,
    "EURGBP": 0.5, "AUDUSD": 0.8, "CADJPY": 1.5, "CHFJPY": 1.5,
    "USDCAD": 0.8, "GBPJPY": 2.0,
}

BASE_PARAMS = {
    "spread_pips":           SPREAD_PIPS,
    "leverage":              30,
    "start_balance":         1000,
    "expire_bars":           4,
    "pullback_window":       6,
    "depth_range":           None,
    "skip_monday":           True,
    "skip_hours":            (15, 16),
    "atr_max_pips":          {"EURUSD": 7.5},
    "max_day_consec_losses": 3,
    "corr_pairs":            {"EURUSD": "GBPUSD", "GBPUSD": "EURUSD",
                              "AUDUSD": "NZDJPY"},
    "only_long":             False,
    "max_pos_per_symbol":    1,
    "symbol_sessions":       {},
    "symbol_skip_hours":     {},
}

def _sessions(eur_syms, asian_syms):
    s = {x: EUR_SESS for x in eur_syms}
    s.update({x: ASIAN_SESS for x in asian_syms})
    return s


# ---- helpers ----------------------------------------------------------------

@contextlib.contextmanager
def _quiet():
    with contextlib.redirect_stdout(io.StringIO()): yield


def _run(data, cfg, label, params):
    t0 = time.time()
    try:
        with _quiet():
            trades, equity, balance, _, _, _, split_time = run_portfolio(data, cfg, params)
    except Exception as e:
        return {"label": label, "trades": 0, "exp": 0.0, "test_exp": 0.0,
                "test_n": 0, "trades_wk": 0.0, "dd": 0.0,
                "elapsed": time.time()-t0, "error": str(e)}

    elapsed = time.time() - t0
    if not trades:
        return {"label": label, "trades": 0, "exp": 0.0, "test_exp": 0.0,
                "test_n": 0, "trades_wk": 0.0, "dd": 0.0, "elapsed": elapsed}

    df = pd.DataFrame(trades)
    df["R"]       = df["pnl_usd"] / df["risk_usd"]
    df["entry_t"] = pd.to_datetime(df["time"])
    wr  = (df["outcome"] == "win").sum() / len(df) * 100
    exp = df["R"].mean()

    eqdf = pd.DataFrame(equity).sort_values("time")
    b    = eqdf["balance"].values
    dd   = ((b - np.maximum.accumulate(b)) / np.maximum.accumulate(b)).min() * 100

    test_df  = df[df["entry_t"] >= split_time]
    test_exp = test_df["R"].mean() if len(test_df) else 0.0

    span = (df["entry_t"].max() - df["entry_t"].min()).days
    trades_wk = len(df) / max(span / 7, 1)

    return {"label": label, "trades": len(df), "wr": wr, "exp": exp, "dd": dd,
            "test_exp": test_exp, "test_n": len(test_df), "trades_wk": trades_wk,
            "elapsed": elapsed}


def _hdr(title):
    print(f"\n{'='*105}")
    print(f"  {title}")
    print("="*105)
    print(f"  {'Label':<52} {'Tot':>5} {'WR':>6} {'Exp':>7} {'TestR':>7} "
          f"{'TN':>5} {'T/wk':>6} {'DD':>7}")
    print(f"  {'-'*103}")


def _row(r):
    if r.get("error"):
        print(f"  {r['label']:<52}  ERR: {r['error'][:40]}"); return
    if r["trades"] == 0:
        print(f"  {r['label']:<52}  0 trades"); return
    print(f"  {r['label']:<52} {r['trades']:>5} {r['wr']:>5.1f}%"
          f" {r['exp']:>+7.3f} {r['test_exp']:>+7.3f} {r['test_n']:>5}"
          f" {r['trades_wk']:>5.1f}/w {r['dd']:>+6.1f}%")


def _best(lst, min_tn=20):
    v = [r for r in lst if r.get("test_n", 0) >= min_tn and r["trades"] > 0 and not r.get("error")]
    return max(v, key=lambda r: r["test_exp"]) if v else None


# ---- main -------------------------------------------------------------------

def main():
    with open(CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)
    cfg_sym = copy.deepcopy(cfg)
    cfg_sym["optional_criteria"]["rsi"]["sell_max"] = 60

    src = CsvDataSource(DATA_DIR)

    print("Incarc date M15 (toate perechile)...")
    all_m15 = {}
    for s in CORE_EUR + CORE_ASIAN + NEW_EUR + NEW_ASIAN + ["GBPJPY", "USDCAD"]:
        try:
            all_m15[s] = prepare_symbol(src, s, cfg)
            print(f"  {s}: {len(all_m15[s])} bare M15")
        except FileNotFoundError:
            print(f"  {s}: LIPSESTE M15")

    # Incearca M5 pentru piete noi (daca s-a terminat descarcarea)
    all_m5 = {}
    print("\nIncarc date M5 (daca disponibile)...")
    for s in CORE_EUR + ["USDJPY"] + NEW_EUR + NEW_ASIAN + ["AUDJPY", "NZDJPY"]:
        try:
            all_m5[s] = prepare_symbol_tf(src, s, cfg, "M5", "M15")
            print(f"  {s}: {len(all_m5[s])} bare M5")
        except FileNotFoundError:
            print(f"  {s}: M5 nu e inca disponibil")

    results_all = []

    # =========================================================================
    # REFERINTA: ALL BOTH PW=6 cu SKIP_MONDAY=True (din asian_session_test)
    # =========================================================================
    _hdr("REF — Baseline Session 2: 6 piete BOTH PW=6, SKIP_MONDAY=True")
    ref_syms = CORE_EUR + CORE_ASIAN
    ref_data = {s: all_m15[s] for s in ref_syms if s in all_m15}
    ref_sess = _sessions(CORE_EUR, CORE_ASIAN)
    r_ref = _run(ref_data, cfg_sym, "REF 6mkt BOTH PW=6 skip_mon=T",
                 {**BASE_PARAMS, "pullback_window": 6, "symbol_sessions": ref_sess})
    _row(r_ref)
    results_all.append(r_ref)

    # =========================================================================
    # A — SKIP_MONDAY: True vs False
    # =========================================================================
    _hdr("A — SKIP_MONDAY: impactul lunii pe combo actual (6 piete, BOTH, PW=4/6)")
    sec_a = []
    for pw in [4, 6]:
        for skip_mon, sm_str in [(True, "T"), (False, "F")]:
            r = _run(ref_data, cfg_sym, f"A 6mkt BOTH PW={pw} skip_mon={sm_str}",
                     {**BASE_PARAMS, "pullback_window": pw,
                      "skip_monday": skip_mon, "symbol_sessions": ref_sess})
            _row(r)
            sec_a.append(r); results_all.append(r)
    b = _best(sec_a)
    if b: print(f"\n  >>> BEST A: {b['label']}  testR={b['test_exp']:+.3f}  {b['trades_wk']:.1f}/wk")

    # =========================================================================
    # B — Piete noi, individual, cu sesiunile corecte
    # =========================================================================
    _hdr("B — Piete noi INDIVIDUAL cu sesiunile corecte, BOTH, PW=6")
    sec_b = []
    new_candidates = [
        ("EURGBP", EUR_SESS),
        ("AUDUSD", ASIAN_SESS),
        ("CADJPY", ASIAN_SESS),
        ("CHFJPY", ASIAN_SESS),
        ("GBPJPY", EUR_SESS),
        ("USDCAD", EUR_SESS),
    ]
    for sym, sess in new_candidates:
        if sym not in all_m15: continue
        r = _run({sym: all_m15[sym]}, cfg_sym, f"B {sym} BOTH PW=6 sess={sess[0]}-{sess[1]}h",
                 {**BASE_PARAMS, "pullback_window": 6,
                  "symbol_sessions": {sym: sess}, "corr_pairs": {}})
        _row(r)
        sec_b.append(r); results_all.append(r)
    b = _best(sec_b, min_tn=10)
    if b: print(f"\n  >>> BEST B: {b['label']}  testR={b['test_exp']:+.3f}  {b['trades_wk']:.1f}/wk")

    # Selectam candidatii cu test_exp > 0
    good_new = [r["label"].split()[1] for r in sec_b
                if r.get("test_exp", -99) > 0 and r.get("test_n", 0) >= 8]
    print(f"\n  Candidati cu edge > 0: {good_new}")

    # =========================================================================
    # C — Portofolii combinate 7-9 piete
    # =========================================================================
    _hdr("C — CORE 6 piete + adaugare individuala a fiecarui candidat, BOTH PW=6")
    sec_c = []
    # Baseline: core 6 piete
    _row(r_ref)
    sec_c.append(r_ref)

    for sym, sess in new_candidates:
        if sym not in all_m15: continue
        syms_ext = [s for s in ref_syms if s in all_m15] + [sym]
        data_ext = {s: all_m15[s] for s in syms_ext}
        sess_ext = {**ref_sess, sym: sess}
        r = _run(data_ext, cfg_sym, f"C 6+{sym} BOTH PW=6",
                 {**BASE_PARAMS, "pullback_window": 6, "symbol_sessions": sess_ext})
        _row(r)
        sec_c.append(r); results_all.append(r)

    # Top 2 noi simultan
    top2 = good_new[:2]
    if len(top2) == 2:
        syms_ext = [s for s in ref_syms if s in all_m15] + top2
        data_ext = {s: all_m15[s] for s in syms_ext}
        sess_ext = dict(ref_sess)
        for sym in top2:
            sess_ext[sym] = next(s for n, s in new_candidates if n == sym)
        r = _run(data_ext, cfg_sym, f"C 6+{'+'.join(top2)} BOTH PW=6",
                 {**BASE_PARAMS, "pullback_window": 6, "symbol_sessions": sess_ext})
        _row(r)
        sec_c.append(r); results_all.append(r)

    b = _best(sec_c)
    if b: print(f"\n  >>> BEST C: {b['label']}  testR={b['test_exp']:+.3f}  {b['trades_wk']:.1f}/wk")

    # =========================================================================
    # D — PW variatie pe cel mai bun portofoliu extins
    # =========================================================================
    best_c = _best(sec_c)
    if best_c and "+" in best_c["label"] and best_c != r_ref:
        added_syms = best_c["label"].split("6+")[1].split(" ")[0].split("+")
        syms_best = [s for s in ref_syms if s in all_m15] + added_syms
        data_best = {s: all_m15[s] for s in syms_best if s in all_m15}
        sess_best = dict(ref_sess)
        for sym in added_syms:
            sess_best[sym] = next((s for n, s in new_candidates if n == sym), EUR_SESS)

        _hdr(f"D — PW variatie pe {best_c['label'][:40]}, BOTH, SKIP_MONDAY=T/F")
        sec_d = []
        for pw in [4, 5, 6, 7, 8]:
            for skip_mon, sm_str in [(True, "T"), (False, "F")]:
                r = _run(data_best, cfg_sym,
                         f"D PW={pw} skip_mon={sm_str}",
                         {**BASE_PARAMS, "pullback_window": pw,
                          "skip_monday": skip_mon, "symbol_sessions": sess_best})
                _row(r)
                sec_d.append(r); results_all.append(r)
        b = _best(sec_d)
        if b: print(f"\n  >>> BEST D: {b['label']}  testR={b['test_exp']:+.3f}  {b['trades_wk']:.1f}/wk  DD={b['dd']:+.1f}%")

    # =========================================================================
    # E — M5 backtest pe piete noi (daca date disponibile)
    # =========================================================================
    m5_new = [s for s in NEW_EUR + NEW_ASIAN if s in all_m5]
    if m5_new:
        _hdr("E — M5 backtest piete noi (confirmare), BOTH PW=6")
        for sym in m5_new:
            sess_sym = next((s for n, s in new_candidates if n == sym), EUR_SESS)
            r = _run({sym: all_m5[sym]}, cfg_sym, f"E M5 {sym} BOTH PW=6",
                     {**BASE_PARAMS, "pullback_window": 6,
                      "expire_bars": 12, "symbol_sessions": {sym: sess_sym},
                      "corr_pairs": {}})
            _row(r)
            results_all.append(r)

    # =========================================================================
    # SUMAR FINAL
    # =========================================================================
    print(f"\n\n{'='*105}")
    print("  SUMAR FINAL — sortate dupa trades/saptamana (test_exp > 0)")
    print("="*105)
    print(f"  {'Label':<52} {'Tot':>5} {'WR':>6} {'Exp':>7} {'TestR':>7} "
          f"{'TN':>5} {'T/wk':>6} {'DD':>7}")
    print(f"  {'-'*103}")
    valid = sorted([r for r in results_all if r.get("test_exp", -99) > 0 and
                    r.get("test_n", 0) >= 15 and not r.get("error")],
                   key=lambda r: r["trades_wk"], reverse=True)
    for r in valid[:15]:
        _row(r)

    print(f"\n  TARGET: 5+ trades/saptamana cu test_exp > +0.10R si DD < 60%")
    candidates = [r for r in valid if r["trades_wk"] >= 3.0 and r["test_exp"] >= 0.10
                  and r["dd"] >= -60]
    if candidates:
        print(f"\n  >>> OPTIUNI CARE INDEPLINESC CRITERIILE (>3/wk, >+0.10R, DD>-60%):")
        for r in candidates:
            print(f"      {r['label']:<52}  {r['trades_wk']:.1f}/wk  testR={r['test_exp']:+.3f}  DD={r['dd']:+.1f}%")
    else:
        best_v = max(valid, key=lambda r: r["trades_wk"]) if valid else None
        if best_v:
            print(f"\n  Cel mai apropiat: {best_v['label']}")
            print(f"  {best_v['trades_wk']:.1f}/wk  testR={best_v['test_exp']:+.3f}  DD={best_v['dd']:+.1f}%")

    total = sum(r["elapsed"] for r in results_all)
    print(f"\n  Total timp: {total:.0f}s ({total/60:.1f} min)")


if __name__ == "__main__":
    main()
