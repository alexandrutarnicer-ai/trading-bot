"""
m0_session_optimizer — cauta parametri mai buni pentru sesiunile cu WR mic,
evaluati cu ACEEASI baterie M0 ca auditul, dar cu disciplina out-of-sample.

De ce exista: M0 clasifica multe sesiuni ca DEMOTE ("edge indistinct de norocul
de cautare"). Daca pur si simplu maximizezi expectancy pe toata istoria si alegi
cel mai bun config, fabrici EXACT falsul edge pe care M0 il semnaleaza. Disciplina:

  1. Enrich date O SINGURA DATA per simbol (invariant la parametrii cautati; cache
     in worker), apoi rulam grid-ul prin run_portfolio, in paralel pe core-uri.
  2. SELECTIA se face DOAR pe fereastra de TRAIN (primele 70% din trade-uri).
     Fereastra de TEST (ultimele 30%) ramane neatinsa -> estimare oneasta OOS.
  3. Un candidat e "PROPER" doar daca: verdict M0 == KEEP pe toata istoria
     SI train_exp > 0 SI test_exp > 0 SI fold+ >= 60%.
  4. Grid-ul e mic intentionat (32 configuratii): mai putina cautare = N* mai
     credibil. Raportam dimensiunea grid-ului per sesiune.

Rulare:
  python scripts/m0_session_optimizer.py                 # toate sesiunile tinta
  python scripts/m0_session_optimizer.py --sessions S13  # una singura
  python scripts/m0_session_optimizer.py --workers 12

Iesire:
  data/m0_opt_configs.csv   — o linie per (sesiune, config) cu metrici ieftine
  data/m0_opt_report.md     — top candidati validati per sesiune + verdict M0
"""

from __future__ import annotations

import os
import sys
import json
import copy
import time
import argparse
import itertools
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest import CONFIG, DATA_DIR
from adapters.csv_source import CsvDataSource
from strategy.preparation import prepare_symbol_tf
from engine.portfolio import run_portfolio
from m0.session_runner import _apply_session_to_cfg, _build_params, _default_start_balance
from m0.robustness import evaluate_trades

# Sesiuni tinta: DEMOTE (excluzand GOLD=S20, DE40=S4, US30=S6) + OBSERVE (push spre KEEP)
DEFAULT_TARGETS = ["S1", "S5", "S7", "S8", "S9", "S10", "S12", "S13", "S19",  # DEMOTE
                   "S2", "S15", "S16"]                                        # OBSERVE
EXCLUDED = {"S4", "S6", "S20"}  # GOLD / DE40 / US30 — cerute explicit sa NU fie atinse

MIN_TRADES = 40
TOP_K = 8
N_BOOT = 3000

OUT_CSV = os.path.join(DATA_DIR, "m0_opt_configs.csv")
OUT_MD  = os.path.join(DATA_DIR, "m0_opt_report.md")

REWARD_PRESETS = {
    "base": (2.5, 3.5, 4.5, 5.5),
    "high": (3.0, 4.0, 5.0, 6.0),
}


def build_grid(s: dict) -> list[dict]:
    """Grid coarse (32) pe knob-urile de expectancy/calitate. Flag/IB/news/ema
    raman la baseline-ul sesiunii (tunam sesiunea existenta, nu o alta strategie)."""
    bl_pw = s["pullback_window"]
    pw_opts = sorted({bl_pw, bl_pw + 2})
    be_opts = sorted({bool(s.get("break_even_enabled", False)), False})
    grid = []
    for direction, pw, rsi_on, rew, be_on in itertools.product(
            ["LONG", "BOTH"], pw_opts, [True, False], ["base", "high"], be_opts):
        grid.append({
            "direction": direction, "pullback_window": pw,
            "rsi_enabled": rsi_on, "reward": rew, "break_even_enabled": be_on,
        })
    return grid


def apply_override(s_base: dict, ov: dict | None) -> dict:
    s = copy.deepcopy(s_base)
    if ov is None:
        return s
    s["direction"] = ov["direction"]
    s["pullback_window"] = ov["pullback_window"]
    s["rsi_enabled"] = ov["rsi_enabled"]
    r = REWARD_PRESETS[ov["reward"]]
    s["r_base"], s["r_mid"], s["r_top"], s["r_max"] = r
    s["break_even_enabled"] = ov["break_even_enabled"]
    return s


# ── Worker (proces separat) ───────────────────────────────────────────────────
_W = {}  # globals per worker: base_cfg, src, cache


def _worker_init(config_path: str, data_dir: str):
    with open(config_path, encoding="utf-8") as f:
        _W["base_cfg"] = json.load(f)
    _W["src"] = CsvDataSource(data_dir)
    _W["cache"] = {}


def _get_data(markets, entry_tf, trend_tf):
    data = {}
    for sym in markets:
        key = (sym, entry_tf, trend_tf)
        if key not in _W["cache"]:
            try:
                df = prepare_symbol_tf(_W["src"], sym, _W["base_cfg"], entry_tf, trend_tf)
                _W["cache"][key] = df if (df is not None and len(df) > 100) else None
            except Exception:
                _W["cache"][key] = None
        if _W["cache"][key] is not None:
            data[sym] = _W["cache"][key]
    return data


def _eval_task(task: dict) -> dict:
    """Ruleaza un config si returneaza metrici ieftine + seria de trade-uri compacta."""
    s_base = task["s"]
    ov = task["ov"]
    s_cfg = apply_override(s_base, ov)
    markets = s_base["markets"]
    start_balance = _default_start_balance(markets)
    data = _get_data(markets, s_base["entry_tf"], s_base["trend_tf"])
    out = {"id": s_base["id"], "label": s_base["label"], "ov": ov, "n": 0}
    if not data:
        out["error"] = "no data"
        return out

    cfg = _apply_session_to_cfg(_W["base_cfg"], s_cfg)
    params = _build_params(s_cfg, data, start_balance)
    trades, *_rest = run_portfolio(data, cfg, params, verbose=False)
    split_time = _rest[-1]
    if not trades:
        return out

    df_t = pd.DataFrame(trades)
    R = (df_t["pnl_usd"] / df_t["risk_usd"]).to_numpy(dtype=float)
    entry_t = pd.to_datetime(df_t["time"])
    order = np.argsort(entry_t.values)
    R = R[order]
    entry_t = entry_t.iloc[order].reset_index(drop=True)
    outcome = df_t["outcome"].to_numpy()[order]

    n = len(R)
    gross_win = R[R > 0].sum()
    gross_loss = -R[R < 0].sum()
    pf = float(gross_win / gross_loss) if gross_loss > 0 else float("inf")
    wins = int(pd.Series(outcome).isin(["win", "be_lock", "be_lock2"]).sum())
    tr_exp = te_exp = float("nan")
    tr_n = te_n = 0
    if split_time is not None:
        split = pd.Timestamp(split_time)
        mask_tr = entry_t < split
        tr_n = int(mask_tr.sum()); te_n = int((~mask_tr).sum())
        if tr_n:
            tr_exp = float(R[mask_tr.to_numpy()].mean())
        if te_n:
            te_exp = float(R[(~mask_tr).to_numpy()].mean())

    out.update({
        "n": n, "exp": float(R.mean()), "total_R": float(R.sum()),
        "win_rate": float(wins / n), "profit_factor": pf,
        "train_exp": tr_exp, "test_exp": te_exp, "train_n": tr_n, "test_n": te_n,
    })
    if n >= MIN_TRADES:  # doar candidatii posibili duc seria (economie de pickle)
        out["series"] = {
            "R": R.tolist(),
            "outcome": [str(x) for x in outcome],
            "entry_t": [t.isoformat() for t in entry_t],
            "split": None if split_time is None else pd.Timestamp(split_time).isoformat(),
        }
    return out


def _full_eval(series: dict) -> dict:
    df = pd.DataFrame({
        "R": series["R"], "outcome": series["outcome"],
        "entry_t": pd.to_datetime(series["entry_t"]),
    })
    split = pd.Timestamp(series["split"]) if series["split"] else None
    return evaluate_trades(df, split_time=split, n_boot=N_BOOT)


def fmt_cfg(ov) -> str:
    if ov is None:
        return "baseline"
    return (f"dir={ov['direction']} pw={ov['pullback_window']} "
            f"rsi={'on' if ov['rsi_enabled'] else 'off'} "
            f"rew={ov['reward']} be={'on' if ov['break_even_enabled'] else 'off'}")


def write_report(summaries: list[dict], path: str, grid_size: int):
    L = []
    L.append("# M0 — optimizare sesiuni cu WR mic (disciplina out-of-sample)\n")
    L.append(f"*Generat: {time.strftime('%Y-%m-%d %H:%M')} · grid = {grid_size} configuratii/sesiune*\n")
    L.append("Selectia candidatilor se face DOAR pe fereastra de train (primele 70%). "
             "Test (ultimele 30%) = holdout neatins. Un candidat e **PROPER** doar daca "
             "atinge KEEP pe toata istoria SI train>0 SI test>0 SI fold+>=60%.\n")
    L.append(f"**N\\*:** grid mic ({grid_size} configuratii) tocmai ca sa nu inflam riscul de "
             "noroc de cautare. Chiar si asa, un candidat cu N* mic ramane fragil.\n")

    L.append("## Sumar\n")
    L.append("| Sesiune | Piata | Baseline | Cel mai bun candidat (OOS) | PROPER? |")
    L.append("|---|---|---|---|---|")
    for s in summaries:
        if s.get("error"):
            L.append(f"| {s['id']} | — | eroare: {s['error']} | — | — |")
            continue
        bl = s["baseline"]
        bl_txt = f"{bl['verdict']} exp={bl.get('expectancy', float('nan')):+.3f}"
        cands = s["candidates"]
        proper = [c for c in cands if c["proper"]]
        if proper:
            c = proper[0]
            best_txt = (f"{c['m']['verdict']} exp={c['m']['expectancy']:+.3f} "
                        f"P>0={c['m']['prob_positive']:.0%} · {fmt_cfg(c['ov'])}")
            flag = "✅ DA"
        elif cands:
            c = cands[0]
            best_txt = (f"{c['m']['verdict']} exp={c['m']['expectancy']:+.3f} "
                        f"P>0={c['m']['prob_positive']:.0%} train={c['m']['train_exp']:+.2f}/test={c['m']['test_exp']:+.2f}")
            flag = "—"
        else:
            best_txt, flag = "niciun candidat valid", "—"
        L.append(f"| {s['id']} | {s['markets']} | {bl_txt} | {best_txt} | {flag} |")
    L.append("")

    L.append("## Detaliu per sesiune\n")
    for s in summaries:
        if s.get("error"):
            continue
        L.append(f"### {s['id']} — {s['label']} ({s['markets']})\n")
        bl = s["baseline"]
        L.append(f"- **Baseline:** {bl['verdict']} · exp={bl.get('expectancy', float('nan')):+.3f}R · "
                 f"P>0={bl.get('prob_positive', float('nan')):.0%} · fold+={bl.get('frac_positive', float('nan')):.0%} · "
                 f"train={bl.get('train_exp', float('nan')):+.3f} / test={bl.get('test_exp', float('nan')):+.3f}")
        L.append(f"- {s['n_valid']} configuratii cu n>={MIN_TRADES}; validate top {len(s['candidates'])} (selectate pe train)\n")
        if not s["candidates"]:
            L.append("- Niciun candidat cu destule trade-uri.\n")
            continue
        L.append("| Config | Verdict | n | exp | P>0 | fold+ | N* | train | test | PROPER |")
        L.append("|---|---|---|---|---|---|---|---|---|---|")
        for c in s["candidates"]:
            m = c["m"]
            L.append(f"| {fmt_cfg(c['ov'])} | {m['verdict']} | {m['n']} | "
                     f"{m['expectancy']:+.3f} | {m['prob_positive']:.0%} | "
                     f"{m['frac_positive']:.0%} | {m['breakeven_trials']} | "
                     f"{m['train_exp']:+.3f} | {m['test_exp']:+.3f} | "
                     f"{'✅' if c['proper'] else ''} |")
        L.append("")

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))


def main():
    try:  # consola Windows e cp1252 — forteaza utf-8 ca sa nu pice pe emoji
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--sessions", default="")
    ap.add_argument("--workers", type=int, default=12)
    args = ap.parse_args()

    with open(os.path.join(DATA_DIR, "profiles", "standard.json"), encoding="utf-8") as f:
        profile = json.load(f)
    sessions = {s["id"]: s for s in profile["sessions"]}

    if args.sessions:
        targets = [x.strip().upper() for x in args.sessions.split(",")]
    else:
        targets = DEFAULT_TARGETS
    targets = [t for t in targets if t not in EXCLUDED and t in sessions]

    # Construieste task-urile: baseline (ov=None) + grid, pentru fiecare sesiune.
    tasks = []
    grids = {}
    for sid in targets:
        s = sessions[sid]
        grid = build_grid(s)
        grids[sid] = len(grid)
        tasks.append({"s": s, "ov": None})               # baseline
        for ov in grid:
            tasks.append({"s": s, "ov": ov})

    grid_size = grids[targets[0]] if targets else 0
    print(f"Optimizer M0 — {len(targets)} sesiuni, {len(tasks)} rulari "
          f"(grid {grid_size}/sesiune + baseline), {args.workers} workers\n")

    results_by_sid = {sid: [] for sid in targets}
    baseline_series = {sid: None for sid in targets}
    t0 = time.time()
    done = 0
    with ProcessPoolExecutor(max_workers=args.workers,
                             initializer=_worker_init, initargs=(CONFIG, DATA_DIR)) as ex:
        futs = {ex.submit(_eval_task, t): t for t in tasks}
        for fut in as_completed(futs):
            r = fut.result()
            done += 1
            sid = r["id"]
            if r["ov"] is None:
                baseline_series[sid] = r.get("series")
                baseline_series[sid + "_cheap"] = r
            else:
                results_by_sid[sid].append(r)
            if done % 25 == 0 or done == len(tasks):
                print(f"  {done}/{len(tasks)} rulari ({time.time()-t0:.0f}s)", flush=True)

    # Metrici ieftine -> CSV
    all_rows = []
    for sid in targets:
        for r in [baseline_series[sid + "_cheap"]] + results_by_sid[sid]:
            if r is None or r.get("n", 0) == 0:
                continue
            row = {"id": sid, "label": r["label"], "config": fmt_cfg(r["ov"]),
                   **{k: r.get(k) for k in ("n", "exp", "total_R", "win_rate",
                       "profit_factor", "train_exp", "test_exp", "train_n", "test_n")}}
            if r["ov"]:
                row.update(r["ov"])
            all_rows.append(row)
    pd.DataFrame(all_rows).to_csv(OUT_CSV, index=False)

    # Selectie OOS (pe train) + validare M0 completa
    summaries = []
    for sid in targets:
        s = sessions[sid]
        bl_series = baseline_series[sid]
        bl_full = _full_eval(bl_series) if bl_series else {"verdict": "INSUFF"}

        valid = [r for r in results_by_sid[sid]
                 if r.get("n", 0) >= MIN_TRADES and "series" in r
                 and np.isfinite(r.get("train_exp", float("nan")))]
        valid.sort(key=lambda r: r["train_exp"], reverse=True)
        cands = valid[:TOP_K]

        validated = []
        for r in cands:
            m_full = _full_eval(r["series"])
            proper = (m_full["verdict"] == "KEEP" and m_full["train_exp"] > 0
                      and m_full["test_exp"] > 0 and m_full["frac_positive"] >= 0.60)
            validated.append({"ov": r["ov"], "m": m_full, "proper": proper})
        validated.sort(key=lambda v: (v["proper"], v["m"]["prob_positive"]), reverse=True)

        summaries.append({
            "id": sid, "label": s["label"], "markets": ",".join(s["markets"]),
            "n_valid": len(valid), "baseline": bl_full, "candidates": validated,
        })

    write_report(summaries, OUT_MD, grid_size)

    print(f"\n=== Rezultate ({time.time()-t0:.0f}s total) ===")
    n_proper = 0
    for s in summaries:
        proper = [c for c in s["candidates"] if c["proper"]]
        if proper:
            n_proper += 1
            c = proper[0]
            print(f"  {s['id']:4s} {s['markets']:8s} baseline={s['baseline']['verdict']:7s} "
                  f"-> PROPER ✅ {c['m']['verdict']} exp={c['m']['expectancy']:+.3f} "
                  f"P>0={c['m']['prob_positive']:.0%} | {fmt_cfg(c['ov'])}")
        else:
            best = s["candidates"][0] if s["candidates"] else None
            b = (f"best={best['m']['verdict']} exp={best['m']['expectancy']:+.3f} "
                 f"P>0={best['m']['prob_positive']:.0%}" if best else "niciun candidat")
            print(f"  {s['id']:4s} {s['markets']:8s} baseline={s['baseline']['verdict']:7s} -> {b}")
    print(f"\nSesiuni cu candidat PROPER: {n_proper}/{len(summaries)}")
    print(f"Scris: {OUT_CSV}\nScris: {OUT_MD}")


if __name__ == "__main__":
    main()
