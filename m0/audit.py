"""
m0.audit — auditul statistic al celor 20 de sesiuni (Milestone 0).

Pentru fiecare sesiune din profil ruleaza backtestul pe TOATA istoria CSV,
apoi aplica bateria din m0.stats si clasifica sesiunea in:

  KEEP     — edge distinct de zgomot SI stabil in timp SI robust la cautare
  OBSERVE  — semnal ambiguu; ruleaza-l pe execute_trades=False si mai strange date
  DEMOTE   — edge indistinct de norocul de cautare; pune pe pauza / opreste
  INSUFF   — prea putine trade-uri ca sa concluzionezi

Iesire:
  - data/m0_audit.csv           (o linie per sesiune, toate metricile)
  - docs/M0_RESULTS.md          (raport citibil, clasament + detaliu)
  - stdout                      (rezumat)

Rulare:
  python -m m0.audit                     # toate sesiunile
  python -m m0.audit --sessions S1,S3    # doar unele
  python -m m0.audit --quick             # bootstrap redus (test rapid)
"""

from __future__ import annotations

import os
import sys
import json
import time
import argparse

import numpy as np
import pandas as pd

from backtest import DATA_DIR, ROOT
from m0.session_runner import run_profile_session, _load_base_cfg
from m0.robustness import evaluate_trades

PROFILE_PATH = os.path.join(DATA_DIR, "profiles", "standard.json")
OUT_CSV      = os.path.join(DATA_DIR, "m0_audit.csv")
OUT_MD       = os.path.join(ROOT, "docs", "M0_RESULTS.md")


def audit_session(session_cfg: dict, base_cfg: dict, n_boot: int, folds: int) -> dict:
    sid   = session_cfg.get("id", "?")
    label = session_cfg.get("label", sid)
    markets = session_cfg.get("markets", [])
    t0 = time.time()
    df, meta = run_profile_session(session_cfg, base_cfg=base_cfg)
    dt = time.time() - t0

    row = {
        "id": sid, "label": label, "markets": ",".join(markets),
        "direction": session_cfg.get("direction", ""),
        "entry_tf": session_cfg.get("entry_tf", ""),
        "execute_trades": session_cfg.get("execute_trades", True),
        "n": 0, "expectancy": float("nan"), "std_R": float("nan"),
        "win_rate": float("nan"), "profit_factor": float("nan"),
        "max_dd_R": float("nan"), "total_R": float("nan"),
        "sharpe": float("nan"),
        "boot_ci_low": float("nan"), "boot_ci_high": float("nan"),
        "prob_positive": float("nan"),
        "psr_vs_zero": float("nan"), "breakeven_trials": 0,
        "frac_positive": float("nan"), "trend_rho": float("nan"),
        "trend_p": float("nan"), "fold_exp": "",
        "train_exp": float("nan"), "test_exp": float("nan"),
        "train_n": 0, "test_n": 0,
        "data_from": meta.get("data_from_actual"),
        "data_to": meta.get("data_to_actual"),
        "skipped_markets": ",".join(meta.get("skipped_markets", [])),
        "runtime_s": round(dt, 1),
        "verdict": "INSUFF", "notes": "",
    }

    if df.empty:
        row["notes"] = "niciun trade / date lipsa"
        return row

    # Bateria completa via modulul comun (aceeasi implementare ca API-ul).
    m = evaluate_trades(df, split_time=meta.get("split_time"), n_boot=n_boot, folds=folds)
    row.update({k: m[k] for k in (
        "n", "expectancy", "std_R", "win_rate", "profit_factor", "max_dd_R",
        "total_R", "sharpe", "boot_ci_low", "boot_ci_high", "prob_positive",
        "psr_vs_zero", "breakeven_trials", "frac_positive", "trend_rho",
        "trend_p", "train_exp", "test_exp", "train_n", "test_n",
    )})
    row["fold_exp"] = " ".join(f"{e:+.2f}" for e in m["fold_exp"])
    row["verdict"]  = m["verdict"]
    row["notes"]    = "; ".join(m["notes"])
    return row


# ── Raport ───────────────────────────────────────────────────────────────────

_VERDICT_ORDER = {"KEEP": 0, "OBSERVE": 1, "DEMOTE": 2, "INSUFF": 3}
_VERDICT_ICON  = {"KEEP": "🟢 KEEP", "OBSERVE": "🟡 OBSERVE",
                  "DEMOTE": "🔴 DEMOTE", "INSUFF": "⚪ INSUFF"}


def _fmt(x, nd=2, pct=False):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "—"
    if pct:
        return f"{x*100:.0f}%"
    return f"{x:.{nd}f}"


def write_markdown(rows: list[dict], path: str) -> None:
    rows_sorted = sorted(rows, key=lambda r: (_VERDICT_ORDER[r["verdict"]],
                                              -(r["expectancy"] if np.isfinite(r["expectancy"]) else -9)))
    counts = {v: sum(1 for r in rows if r["verdict"] == v) for v in _VERDICT_ORDER}
    lines = []
    lines.append("# M0 — Rezultate audit statistic sesiuni\n")
    lines.append(f"*Generat: {time.strftime('%Y-%m-%d %H:%M')} · "
                 f"{len(rows)} sesiuni · backtest pe toata istoria CSV*\n")
    lines.append("Metoda: vezi [M0_METHOD.md](M0_METHOD.md). Verdictele sunt reguli "
                 "mecanice pe metricile de mai jos, nu opinii — pragurile sunt in "
                 "`m0/audit.py::classify`.\n")
    lines.append(f"**Sumar:** 🟢 {counts['KEEP']} keep · 🟡 {counts['OBSERVE']} observe · "
                 f"🔴 {counts['DEMOTE']} demote · ⚪ {counts['INSUFF']} insuficient\n")

    lines.append("## Clasament\n")
    lines.append("| Verdict | Sesiune | Piata | Dir | N | Exp (R) | P(edge>0) | "
                 "Fold+ | N* trials | Train/Test | Note |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for r in rows_sorted:
        tt = f"{_fmt(r['train_exp'])}/{_fmt(r['test_exp'])}"
        be = "∞" if r["breakeven_trials"] >= 100000 else str(r["breakeven_trials"])
        lines.append(
            f"| {_VERDICT_ICON[r['verdict']]} | {r['id']} {r['label']} | {r['markets']} | "
            f"{r['direction']} | {r['n']} | {_fmt(r['expectancy'],3)} | "
            f"{_fmt(r['prob_positive'],pct=True)} | {_fmt(r['frac_positive'],pct=True)} | "
            f"{be} | {tt} | {r['notes']} |")
    lines.append("")

    lines.append("## Coloane\n")
    lines.append("- **N** — numar de trade-uri in backtest (dimensiunea esantionului).")
    lines.append("- **Exp (R)** — expectancy: castig mediu per trade in multipli de risc.")
    lines.append("- **P(edge>0)** — increderea (bootstrap) ca expectancy adevarat > 0. "
                 "≥95% = edge distinct de zgomot.")
    lines.append("- **Fold+** — fractia din cele 8 sub-perioade in care sesiunea a fost "
                 "pozitiva. Aproape de 100% = stabil in timp.")
    lines.append("- **N\\* trials** — de cate variante independente ai fi avut nevoie ca "
                 "edge-ul sa fie explicat prin noroc de cautare. Mic = fragil.")
    lines.append("- **Train/Test** — expectancy pe primele 70% / ultimele 30% (split-ul existent).\n")

    lines.append("## Detaliu per sesiune\n")
    for r in rows_sorted:
        lines.append(f"### {_VERDICT_ICON[r['verdict']]} — {r['id']} {r['label']} "
                     f"({r['markets']}, {r['direction']})\n")
        if r["n"] == 0:
            lines.append(f"- {r['notes']}\n")
            continue
        lines.append(f"- Trade-uri: **{r['n']}** · win rate {_fmt(r['win_rate'],pct=True)} · "
                     f"profit factor {_fmt(r['profit_factor'])} · perioada {r['data_from']} → {r['data_to']}")
        lines.append(f"- Expectancy: **{_fmt(r['expectancy'],3)}R** "
                     f"(bootstrap 95% CI: {_fmt(r['boot_ci_low'],3)} … {_fmt(r['boot_ci_high'],3)}R) · "
                     f"Sharpe/trade {_fmt(r['sharpe'])}")
        lines.append(f"- P(edge>0) = **{_fmt(r['prob_positive'],pct=True)}** · "
                     f"PSR vs 0 = {_fmt(r['psr_vs_zero'],pct=True)} · "
                     f"breakeven trials N* = **{('∞' if r['breakeven_trials']>=100000 else r['breakeven_trials'])}**")
        lines.append(f"- Stabilitate: {_fmt(r['frac_positive'],pct=True)} din fold-uri pozitive · "
                     f"trend {_fmt(r['trend_rho'])} (p={_fmt(r['trend_p'])}) · fold exp: `{r['fold_exp']}`")
        lines.append(f"- Train/Test: {_fmt(r['train_exp'],3)}R ({r['train_n']}t) / "
                     f"{_fmt(r['test_exp'],3)}R ({r['test_n']}t) · max DD {_fmt(r['max_dd_R'],1)}R")
        if r["notes"]:
            lines.append(f"- ⚠ {r['notes']}")
        lines.append("")

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main():
    ap = argparse.ArgumentParser(description="M0 — audit statistic sesiuni")
    ap.add_argument("--sessions", default="", help="lista id-uri (ex: S1,S3); gol = toate")
    ap.add_argument("--profile", default=PROFILE_PATH)
    ap.add_argument("--quick", action="store_true", help="bootstrap redus (test rapid)")
    ap.add_argument("--folds", type=int, default=8)
    args = ap.parse_args()

    n_boot = 1000 if args.quick else 5000
    with open(args.profile, encoding="utf-8") as f:
        profile = json.load(f)
    sessions = profile["sessions"]
    if args.sessions:
        want = {x.strip().upper() for x in args.sessions.split(",")}
        sessions = [s for s in sessions if s.get("id", "").upper() in want]

    base_cfg = _load_base_cfg()
    print(f"M0 audit — {len(sessions)} sesiuni · bootstrap={n_boot} · folds={args.folds}\n")
    rows = []
    for i, s in enumerate(sessions, 1):
        sid = s.get("id", "?")
        print(f"[{i}/{len(sessions)}] {sid} {s.get('label','')} "
              f"({','.join(s.get('markets',[]))}) ... ", end="", flush=True)
        try:
            row = audit_session(s, base_cfg, n_boot, args.folds)
        except Exception as e:
            print(f"EROARE: {type(e).__name__}: {e}")
            continue
        rows.append(row)
        print(f"{row['verdict']:8s} n={row['n']:4d} exp={_fmt(row['expectancy'],3):>7} "
              f"P>0={_fmt(row['prob_positive'],pct=True):>4} N*={row['breakeven_trials']} "
              f"({row['runtime_s']}s)")

    if not rows:
        print("Nicio sesiune auditata.")
        return

    pd.DataFrame(rows).to_csv(OUT_CSV, index=False)
    write_markdown(rows, OUT_MD)
    counts = {v: sum(1 for r in rows if r["verdict"] == v) for v in _VERDICT_ORDER}
    print(f"\nSumar: KEEP {counts['KEEP']} · OBSERVE {counts['OBSERVE']} · "
          f"DEMOTE {counts['DEMOTE']} · INSUFF {counts['INSUFF']}")
    print(f"Scris: {OUT_CSV}")
    print(f"Scris: {OUT_MD}")


if __name__ == "__main__":
    main()
