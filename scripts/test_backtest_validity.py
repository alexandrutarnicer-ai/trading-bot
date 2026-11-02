"""
Teste offline pentru api/backtest_validity.py (validitatea unui rezultat de backtest, afisata in Audit).
    python scripts/test_backtest_validity.py
"""
import os
import sys
from datetime import date

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from api.backtest_validity import MAX_PLAUSIBLE_R, backtest_validity  # noqa: E402

FAIL = 0


def check(name, cond, info=None):
    global FAIL
    print(("  OK  " if cond else "  FAIL ") + name + ("" if cond or info is None else f"  -> {info}"))
    if not cond:
        FAIL += 1


T = date(2026, 11, 2)
v = backtest_validity([2.0, -1.0, 1.8, -1.1], ["GBPUSD"], "2026-11-01", T)
check("R-uri normale + date proaspete → valid", v["valid"] and not any("INVALID" in w or "se opresc" in w for w in v["warnings"]), v)
check("FX → nota despre markup-ul contului Standard", any("Standard" in w for w in v["warnings"]))
v = backtest_validity([-1.0, -26.04, 2.0, float("nan")], ["XRPUSD"], "2026-11-01", T)
check("XRPUSD cu R −26 / NaN → INVALID, primul avertisment", not v["valid"] and v["warnings"][0].startswith("REZULTAT INVALID")
      and "2 trade-uri" in v["warnings"][0], v["warnings"][:1])
check("non-FX (cripto) → fara nota de markup FX", not any("Standard" in w for w in v["warnings"]))
check(f"prag |R| > {MAX_PLAUSIBLE_R:g}: 5,5R + costuri ramane valid", backtest_validity([5.5, 6.9, -1.3], ["US500"], "2026-11-01", T)["valid"])
v = backtest_validity([1.0], ["EURUSD"], "2026-06-05", T)
check("date vechi (iunie) → avertisment cu numarul de zile", any("2026-06-05" in w and "150 zile" in w for w in v["warnings"]), v["warnings"])
check("data invalida / lipsa → fara exceptie", backtest_validity([1.0], [], None, T)["valid"] and backtest_validity([1.0], [], "x", T)["valid"])
check("lista „nu se simuleaza” include Filtrul AI si Setarile Globale",
      any("Filtrul AI" in x for x in v["not_simulated"]) and any("Setările Globale" in x for x in v["not_simulated"]))

print(f"\n{'TOATE TESTELE AU TRECUT' if not FAIL else f'{FAIL} TESTE ESUATE'}")
sys.exit(1 if FAIL else 0)
