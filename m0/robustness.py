"""
m0.robustness — evaluare de robustete pentru o serie de trade-uri + verdict.

SURSA UNICA DE ADEVAR pentru bateria M0. Atat auditul CLI (m0.audit) cat si
worker-ul de backtest din API (api/routers/backtest.py) apeleaza evaluate_trades
+ classify de aici, ca sa nu existe niciodata doua implementari care sa divergeze.

Input: DataFrame de trade-uri cu coloanele R (pnl_usd/risk_usd), outcome, entry_t.
Output: dict plat cu toate metricile + verdict + note. Vezi docs/M0_METHOD.md.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from m0 import stats as S

MIN_TRADES = 30   # sub acest prag nu concluzionam

# Praguri de verdict — vezi docs/M0_METHOD.md. Verdictul se sprijina pe metrici
# cu date complete (bootstrap P(edge>0) + consistenta pe fold-uri). N* e caveat.
KEEP_PROB   = 0.95
KEEP_FOLD   = 0.60
DEMOTE_PROB = 0.75
SMALL_N_STAR = 10   # sub asta, adauga nota de sensibilitate la cautare


def classify(m: dict) -> tuple[str, list[str]]:
    """Reguli mecanice de verdict pe dict-ul de metrici. Returneaza (verdict, note)."""
    notes: list[str] = []
    n = m["n"]
    if n < MIN_TRADES:
        return "INSUFF", [f"doar {n} trade-uri (<{MIN_TRADES})"]

    exp, ppos, fpos, be = m["expectancy"], m["prob_positive"], m["frac_positive"], m["breakeven_trials"]
    keep   = (exp > 0 and ppos >= KEEP_PROB and fpos >= KEEP_FOLD)
    demote = (exp <= 0 or ppos < DEMOTE_PROB)
    verdict = "KEEP" if keep else ("DEMOTE" if demote else "OBSERVE")

    if np.isfinite(m["train_exp"]) and np.isfinite(m["test_exp"]) \
            and m["train_exp"] < 0 <= m["test_exp"]:
        notes.append("train negativ / test pozitiv (posibil regim recent)")
    if np.isfinite(m["trend_rho"]) and m["trend_rho"] > 0.6 and m["trend_p"] < 0.10:
        notes.append("edge in crestere in timp (dependenta de regim)")
    if np.isfinite(m["trend_rho"]) and m["trend_rho"] < -0.6 and m["trend_p"] < 0.10:
        notes.append("edge in scadere in timp (posibil decay)")
    if verdict in ("KEEP", "OBSERVE") and be < SMALL_N_STAR:
        notes.append(f"Sharpe/trade mic — N*={be} trial-uri il explica (sensibil la cautare)")

    return verdict, notes


def evaluate_trades(df: pd.DataFrame,
                    split_time=None,
                    n_boot: int = 2000,
                    folds: int = 8) -> dict:
    """
    Calculeaza intreaga baterie M0 pe o serie de trade-uri si returneaza un dict
    plat, gata de serializat (toate valorile sunt tipuri Python native / float).

    df trebuie sa aiba coloanele: R, outcome, entry_t (datetime intrare).
    Daca df e gol -> dict cu n=0 si verdict INSUFF.
    """
    empty = {
        "n": 0, "expectancy": float("nan"), "std_R": float("nan"),
        "win_rate": float("nan"), "profit_factor": float("nan"),
        "max_dd_R": float("nan"), "total_R": float("nan"), "sharpe": float("nan"),
        "boot_ci_low": float("nan"), "boot_ci_high": float("nan"),
        "prob_positive": float("nan"), "psr_vs_zero": float("nan"),
        "breakeven_trials": 0, "frac_positive": float("nan"),
        "trend_rho": float("nan"), "trend_p": float("nan"), "fold_exp": [],
        "train_exp": float("nan"), "test_exp": float("nan"),
        "train_n": 0, "test_n": 0, "verdict": "INSUFF", "notes": ["niciun trade"],
    }
    if df is None or df.empty:
        return empty

    R = df["R"].to_numpy(dtype=float)
    b  = S.basic_stats(df)
    sh = S.sharpe_stats(R)
    bo = S.stationary_bootstrap_ci(R, n_boot=n_boot)
    de = S.deflated_breakeven_trials(sh["sharpe"], sh["T"], sh["skew"], sh["kurt"])
    fo = S.fold_consistency(df["entry_t"], R, k=folds)
    tt = S.train_test_split_stats(df, split_time)

    m = {
        "n": b["n"], "expectancy": b["expectancy"], "std_R": b["std_R"],
        "win_rate": b["win_rate"], "profit_factor": b["profit_factor"],
        "max_dd_R": b["max_dd_R"], "total_R": b["total_R"], "sharpe": sh["sharpe"],
        "boot_ci_low": bo["ci_low"], "boot_ci_high": bo["ci_high"],
        "prob_positive": bo["prob_positive"], "psr_vs_zero": de["psr_vs_zero"],
        "breakeven_trials": de["breakeven_trials"], "frac_positive": fo["frac_positive"],
        "trend_rho": fo["trend_rho"], "trend_p": fo["trend_p"], "fold_exp": fo["fold_exp"],
        "train_exp": tt["train_exp"], "test_exp": tt["test_exp"],
        "train_n": tt["train_n"], "test_n": tt["test_n"],
    }
    verdict, notes = classify(m)
    m["verdict"] = verdict
    m["notes"]   = notes
    return m


def to_result_payload(m: dict) -> dict:
    """
    Subset compact, JSON-safe (fara NaN), pentru rezultatul de backtest din API.
    Frontend-ul citeste exact aceste chei (types.ts::RobustnessResult).
    """
    def _f(x, nd=3):
        if x is None or (isinstance(x, float) and not np.isfinite(x)):
            return None
        return round(float(x), nd)

    return {
        "verdict":          m["verdict"],
        "notes":            m.get("notes", []),
        "prob_positive":    _f(m["prob_positive"], 3),
        "ci_low":           _f(m["boot_ci_low"], 3),
        "ci_high":          _f(m["boot_ci_high"], 3),
        "frac_positive":    _f(m["frac_positive"], 3),
        "breakeven_trials": int(m["breakeven_trials"]),
        "psr_vs_zero":      _f(m["psr_vs_zero"], 3),
        "sharpe":           _f(m["sharpe"], 3),
        "trend_rho":        _f(m["trend_rho"], 2),
        "fold_exp":         [None if not np.isfinite(e) else round(float(e), 3)
                             for e in m.get("fold_exp", [])],
        "n":                int(m["n"]),
    }
