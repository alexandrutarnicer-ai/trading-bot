"""
m0.stats — bateria statistica pentru auditul de sesiuni.

Strategia e bazata pe reguli (fara parametri fitati pe date), deci riscul de
overfitting NU vine din fitare in-sample, ci din SELECTIA istorica (multe
configuratii testate, cea mai buna promovata). Bateria raspunde la doua
intrebari, cu unelte standard din literatura:

  1. "Edge-ul e distinct de zgomotul de esantion?"
     -> stationary block bootstrap pe seria de R -> interval de incredere si
        probabilitatea ca expectancy > 0.

  2. "Edge-ul supravietuieste corectiei pentru cat de mult am cautat?"
     -> Probabilistic Sharpe Ratio (Bailey & Lopez de Prado) + un prag de
        "trial-uri de breakeven" N*: daca ai testat mai mult de N* variante
        independente ca sa gasesti asta, e explicabil prin noroc de cautare.

  3. "Edge-ul e stabil in timp sau depinde de un singur regim?"
     -> consistenta pe fold-uri contigue + test de trend (Spearman) care
        prinde tiparul train-negativ / test-pozitiv.

Toate functiile primesc seria de R realizat (pnl_usd / risk_usd), ordonata
cronologic dupa timpul de intrare.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats as sps

_EULER_GAMMA = 0.5772156649015329


# ── 1. Stationary block bootstrap ────────────────────────────────────────────

def stationary_bootstrap_ci(R: np.ndarray,
                            n_boot: int = 5000,
                            block_mean: float = 10.0,
                            alpha: float = 0.05,
                            seed: int = 42) -> dict:
    """
    Politis-Romano stationary bootstrap pe seria de R.
    Pastreaza dependenta seriala (trade-urile se aduna in clustere de regim),
    deci intervalul de incredere pe expectancy e onest, nu prea ingust.

    Returneaza: mean, ci_low, ci_high (percentile alpha/2..1-alpha/2),
                prob_positive (fractia de medii bootstrap > 0).
    """
    R = np.asarray(R, dtype=float)
    T = len(R)
    if T < 2:
        return {"mean": float(R.mean()) if T else float("nan"),
                "ci_low": float("nan"), "ci_high": float("nan"),
                "prob_positive": float("nan"), "n": T}

    rng = np.random.default_rng(seed)
    p = 1.0 / max(block_mean, 1.0)          # prob. de a incepe un bloc nou

    # Vectorizat peste cele n_boot resample-uri: iteram pe pasii de timp (T),
    # nu pe resample-uri. La fiecare pas, pentru toate resample-urile deodata:
    # ori continuam blocul (i+1 mod T), ori restartam la o pozitie aleatoare.
    idx = np.empty((n_boot, T), dtype=np.int64)
    cur = rng.integers(0, T, size=n_boot)
    for t in range(T):
        idx[:, t] = cur
        restart = rng.random(n_boot) < p
        nxt = (cur + 1) % T
        nxt[restart] = rng.integers(0, T, size=int(restart.sum()))
        cur = nxt
    means = R[idx].mean(axis=1)

    return {
        "mean":          float(R.mean()),
        "ci_low":        float(np.quantile(means, alpha / 2)),
        "ci_high":       float(np.quantile(means, 1 - alpha / 2)),
        "prob_positive": float((means > 0).mean()),
        "n":             T,
    }


# ── 2. Sharpe / PSR / Deflated Sharpe ────────────────────────────────────────

def sharpe_stats(R: np.ndarray) -> dict:
    """Sharpe pe trade (mean/std), plus skew, kurtoza (ne-excess), T."""
    R = np.asarray(R, dtype=float)
    T = len(R)
    if T < 2 or R.std(ddof=1) == 0:
        return {"sharpe": float("nan"), "skew": float("nan"),
                "kurt": float("nan"), "T": T}
    sr = R.mean() / R.std(ddof=1)
    return {
        "sharpe": float(sr),
        "skew":   float(sps.skew(R, bias=False)),
        "kurt":   float(sps.kurtosis(R, fisher=False, bias=False)),  # ne-excess
        "T":      T,
    }


def probabilistic_sharpe_ratio(sr: float, T: int, skew: float, kurt: float,
                               sr_benchmark: float = 0.0) -> float:
    """
    PSR(sr_benchmark) = Prob(Sharpe adevarat > benchmark).
    Bailey & Lopez de Prado (2012). sr, sr_benchmark pe aceeasi scara (per trade).
    """
    if not np.isfinite(sr) or T < 2:
        return float("nan")
    denom = np.sqrt(max(1e-12, 1 - skew * sr + (kurt - 1) / 4.0 * sr ** 2))
    z = (sr - sr_benchmark) * np.sqrt(T - 1) / denom
    return float(sps.norm.cdf(z))


def _expected_max_sharpe(n_trials: int, var_trial_sr: float) -> float:
    """
    E[max Sharpe] peste n_trials strategii null (medie 0), fiecare cu
    dispersie var_trial_sr a Sharpe-ului estimat. Aproximarea din Deflated
    Sharpe Ratio (Bailey & Lopez de Prado 2014).
    """
    if n_trials < 2:
        return 0.0
    sigma = np.sqrt(max(var_trial_sr, 1e-12))
    z1 = sps.norm.ppf(1 - 1.0 / n_trials)
    z2 = sps.norm.ppf(1 - 1.0 / (n_trials * np.e))
    return sigma * ((1 - _EULER_GAMMA) * z1 + _EULER_GAMMA * z2)


def deflated_breakeven_trials(sr: float, T: int, skew: float, kurt: float,
                              var_trial_sr: float | None = None,
                              psr_threshold: float = 0.95,
                              max_trials: int = 100000) -> dict:
    """
    Cauta N* = numarul de trial-uri la care Deflated Sharpe Ratio scade sub prag.

    var_trial_sr = dispersia Sharpe-ului intre trial-uri. Fara datele de scan
    reale o estimam cu 1/T (dispersia de esantionare a unui Sharpe pe trade
    cand adevaratul SR=0). Interpretare N*:
      - N* mare  -> ar fi trebuit sute/mii de variante ca sa fie noroc -> solid
      - N* mic   -> chiar si o cautare modesta explica edge-ul -> fragil

    Returneaza: psr_vs_zero, breakeven_trials (N*), var_trial_sr folosit.
    """
    if not np.isfinite(sr) or T < 2:
        return {"psr_vs_zero": float("nan"), "breakeven_trials": 0,
                "var_trial_sr": float("nan")}
    if var_trial_sr is None:
        var_trial_sr = 1.0 / T

    psr0 = probabilistic_sharpe_ratio(sr, T, skew, kurt, 0.0)

    # DSR scade monoton cu N (benchmark-ul creste). Cautam primul N cu DSR<prag.
    lo, hi = 1, max_trials
    if probabilistic_sharpe_ratio(
            sr, T, skew, kurt, _expected_max_sharpe(hi, var_trial_sr)) >= psr_threshold:
        breakeven = max_trials  # ramane semnificativ chiar si la max_trials
    else:
        while lo < hi:
            mid = (lo + hi) // 2
            dsr = probabilistic_sharpe_ratio(
                sr, T, skew, kurt, _expected_max_sharpe(mid, var_trial_sr))
            if dsr >= psr_threshold:
                lo = mid + 1
            else:
                hi = mid
        breakeven = lo
    return {"psr_vs_zero": float(psr0), "breakeven_trials": int(breakeven),
            "var_trial_sr": float(var_trial_sr)}


# ── 3. Consistenta pe fold-uri ───────────────────────────────────────────────

def fold_consistency(entry_times: pd.Series, R: np.ndarray, k: int = 8) -> dict:
    """
    Imparte trade-urile in k fold-uri contigue (dupa timp, egale ca numar).
    Returneaza expectancy per fold, fractia de fold-uri pozitive si un test de
    trend (Spearman intre expectancy si ordinea fold-ului). Un trend puternic
    pozitiv + fold-uri timpurii negative = tiparul train-negativ/test-pozitiv
    (edge dependent de un regim recent, nu durabil).
    """
    R = np.asarray(R, dtype=float)
    T = len(R)
    order = np.argsort(np.asarray(entry_times.values))
    Rs = R[order]
    k = max(2, min(k, T))
    folds = np.array_split(Rs, k)
    fold_exp = [float(f.mean()) if len(f) else float("nan") for f in folds]
    valid = [e for e in fold_exp if np.isfinite(e)]
    frac_pos = float(np.mean([e > 0 for e in valid])) if valid else float("nan")

    if len(valid) >= 3:
        rho, pval = sps.spearmanr(np.arange(len(fold_exp)), fold_exp)
    else:
        rho, pval = float("nan"), float("nan")

    return {
        "k":            len(folds),
        "fold_exp":     [round(e, 3) for e in fold_exp],
        "frac_positive": frac_pos,
        "trend_rho":    float(rho),
        "trend_p":      float(pval),
    }


# ── 4. Descriptive de baza ───────────────────────────────────────────────────

def basic_stats(df: pd.DataFrame) -> dict:
    """Expectancy, win rate, profit factor, DD in R (pe echitatea trade-cu-trade)."""
    R = df["R"].to_numpy(dtype=float)
    T = len(R)
    wins   = df["outcome"].isin(["win", "be_lock", "be_lock2"]).to_numpy()
    n_win  = int(wins.sum())
    gross_win  = R[R > 0].sum()
    gross_loss = -R[R < 0].sum()
    pf = float(gross_win / gross_loss) if gross_loss > 0 else float("inf")
    eq = np.cumsum(R)
    peak = np.maximum.accumulate(eq)
    dd_R = float((eq - peak).min()) if T else 0.0
    return {
        "n":            T,
        "expectancy":   float(R.mean()) if T else float("nan"),
        "std_R":        float(R.std(ddof=1)) if T > 1 else float("nan"),
        "win_rate":     float(n_win / T) if T else float("nan"),
        "profit_factor": pf,
        "max_dd_R":     dd_R,
        "total_R":      float(R.sum()),
    }


def train_test_split_stats(df: pd.DataFrame, split_time) -> dict:
    """Reproduce split-ul 70/30 existent (train primele 70%, test ultimele 30%)."""
    if split_time is None or df.empty:
        return {"train_exp": float("nan"), "test_exp": float("nan"),
                "train_n": 0, "test_n": 0}
    split = pd.Timestamp(split_time)
    tr = df[df["entry_t"] < split]
    te = df[df["entry_t"] >= split]
    return {
        "train_exp": float(tr["R"].mean()) if len(tr) else float("nan"),
        "test_exp":  float(te["R"].mean()) if len(te) else float("nan"),
        "train_n":   int(len(tr)),
        "test_n":    int(len(te)),
    }
