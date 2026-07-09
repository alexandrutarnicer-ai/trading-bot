"""
m0.selftest — verificari rapide de integritate pentru M0.

Ruleaza:  python -m m0.selftest

Acopera:
  1. Runner-ul reproduce baseline-ul documentat (284 trade-uri).   [validate_runner]
  2. evaluate_trades + to_result_payload produc un payload JSON-safe (fara NaN)
     si verdicte corecte pe serii sintetice (KEEP pozitiv, DEMOTE negativ,
     INSUFF sub prag).
  3. Wiring-ul din API se importa fara erori (m0.robustness e legat corect).

Nu necesita MT5. Foloseste serii sintetice ca sa fie rapid (fara backtest lung).
"""

from __future__ import annotations

import json
import numpy as np
import pandas as pd

from m0.robustness import evaluate_trades, to_result_payload, MIN_TRADES


def _synthetic(mean: float, n: int, seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    R = rng.normal(mean, 1.0, n)
    times = pd.date_range("2020-01-01", periods=n, freq="8h")
    outcome = np.where(R > 0, "win", "loss")
    return pd.DataFrame({"R": R, "outcome": outcome, "entry_t": times})


def _assert(cond, msg):
    print(f"  {'OK ' if cond else 'FAIL'} — {msg}")
    if not cond:
        raise AssertionError(msg)


def test_json_safe_and_verdicts():
    print("[2] payload JSON-safe + verdicte pe serii sintetice")
    # KEEP: edge clar pozitiv, mult date
    m = evaluate_trades(_synthetic(0.30, 400), split_time=None, n_boot=1000)
    p = m and to_result_payload(m)
    s = json.dumps(p)  # arunca daca payload nu e serializabil
    _assert("NaN" not in s and "Infinity" not in s, "payload nu contine NaN/Infinity")
    _assert(m["verdict"] == "KEEP", f"serie +0.30R -> KEEP (a dat {m['verdict']})")

    # DEMOTE: edge negativ
    m2 = evaluate_trades(_synthetic(-0.20, 400), split_time=None, n_boot=1000)
    _assert(m2["verdict"] == "DEMOTE", f"serie -0.20R -> DEMOTE (a dat {m2['verdict']})")

    # INSUFF: sub pragul minim de trade-uri
    m3 = evaluate_trades(_synthetic(0.30, MIN_TRADES - 1), split_time=None, n_boot=500)
    _assert(m3["verdict"] == "INSUFF", f"<{MIN_TRADES} trade-uri -> INSUFF (a dat {m3['verdict']})")

    # gol -> INSUFF, payload valid
    m4 = evaluate_trades(pd.DataFrame(), n_boot=100)
    _ = json.dumps(to_result_payload(m4))
    _assert(m4["verdict"] == "INSUFF", "DataFrame gol -> INSUFF")


def test_api_wiring():
    print("[3] wiring API se importa fara erori")
    import api.routers.backtest as bt   # noqa: F401
    _assert(hasattr(bt, "evaluate_trades") and hasattr(bt, "to_result_payload"),
            "api.routers.backtest a importat evaluate_trades + to_result_payload")


def main():
    print("[1] runner reproduce baseline-ul documentat")
    from m0.validate_runner import validate_portfolio_baseline
    _assert(validate_portfolio_baseline(), "284 trade-uri baseline")
    test_json_safe_and_verdicts()
    test_api_wiring()
    print("\nToate verificarile M0 au trecut.")


if __name__ == "__main__":
    main()
