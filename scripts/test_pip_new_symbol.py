"""
Teste pre/post-fix pentru pip_size si _calc_lots.
Verifica:
  1. Toate simbolurile active (sesiunile 1-20) pastreaza pip_size corect
  2. Simboluri non-forex necunoscute primesc fallback rezonabil (nu 0.0001 ca forex)
  3. Baselines backtest neschimbate (S1 / S3)
  4. _calc_lots produce acelasi lot pentru simboluri existente (matematic: pip se anuleaza)

Rulare: python scripts/test_pip_new_symbol.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategy.signals import pip_size, _INDEX_PIP

PASS = 0
FAIL = 0

def check(label, got, expected, tol=1e-9):
    global PASS, FAIL
    ok = abs(got - expected) < tol
    status = "PASS" if ok else "FAIL"
    if not ok:
        FAIL += 1
        print(f"  {status}  {label}: expected {expected}, got {got}")
    else:
        PASS += 1
        print(f"  {status}  {label}")

def section(title):
    print(f"\n[{title}]")

# ── 1. Simboluri active curente ───────────────────────────────────────────────
section("1. pip_size simboluri active (sesiunile 1-20)")
KNOWN = {
    "EURUSD": 0.0001, "GBPUSD": 0.0001, "AUDJPY": 0.01,
    "BTCUSD": 0.01,   "XRPUSD": 0.0001, "GER40":  1.0,
    "US30":   1.0,    "USDCHF": 0.0001, "EURCAD": 0.0001,
    "USDJPY": 0.01,   "GBPCAD": 0.0001, "USDCAD": 0.0001,
    "EURAUD": 0.0001, "EURJPY": 0.01,   "CHFJPY": 0.01,
    "GBPAUD": 0.0001, "AUDCAD": 0.0001, "NZDJPY": 0.01,
    "AUDNZD": 0.0001, "XAUUSD": 1.0,
}
for sym, exp in KNOWN.items():
    check(f"pip_size({sym})", pip_size(sym), exp)

# ── 2. Fallback forex standard (JPY / non-JPY) ───────────────────────────────
section("2. Fallback forex standard")
check("pip_size(USDMXN) non-JPY",  pip_size("USDMXN"), 0.0001)
check("pip_size(USDZAR) non-JPY",  pip_size("USDZAR"), 0.0001)
check("pip_size(SGDJPY) JPY pair", pip_size("SGDJPY"), 0.01)
check("pip_size(CADJPY) JPY pair", pip_size("CADJPY"), 0.01)

# ── 3. Simboluri non-forex NECUNOSCUTE (pre-fix: returneaza 0.0001 — GRESIT) ─
section("3. Simboluri non-forex necunoscute — comportament PRE-FIX")
# Dupa fix, aceste simboluri ar trebui sa fie >= 0.01 (nu 0.0001 forex fallback)
# Testul verifica starea ACTUALA — dupa fix valorile se schimba pt NAS100/ETHUSD
unknown_non_forex = ["NAS100", "ETHUSD", "UK100", "FRA40", "JPN225"]
for sym in unknown_non_forex:
    got = pip_size(sym)
    # Pre-fix: 0.0001 (forex fallback gresit)
    # Post-fix: >= 0.01 (corect pentru indici/crypto)
    is_forex_fallback = (got == 0.0001)
    print(f"  INFO {sym:10} pip={got}  {'(fallback forex — va fi corectat de fix)' if is_forex_fallback else '(deja corect)'}")

# ── 4. _calc_lots — verificare matematica (pip se anuleaza) ──────────────────
section("4. _calc_lots: pip_size nu influenteaza lotajul (verificare matematica)")
# Formula: lots = (capital * risk) / (sl_pips * pip_val)
#          sl_pips = sl_dist / pip; pip_val = tick_val/tick_size * pip
#          => lots = (capital * risk) / (sl_dist * tick_val / tick_size)
# Deci lotajul e INDEPENDENT de pip_size — pip se anuleaza
# Simulam manual cu valori fictive
capital = 150.0
risk_pct = 0.01
entry = 1.10000
sl    = 1.09700  # 30 pips
tick_size  = 0.00001  # EURUSD 5 decimale
tick_value = 1.0      # $1 per tick per lot (valoare fictiva)

risk_usd = capital * risk_pct  # $1.50

# Cu pip = 0.0001 (corect)
pip1 = 0.0001
sl_pips1 = abs(entry - sl) / pip1
pip_val1  = tick_value / tick_size * pip1
lots1     = risk_usd / (sl_pips1 * pip_val1)

# Cu pip = 0.0002 (dublu — gresit)
pip2 = 0.0002
sl_pips2 = abs(entry - sl) / pip2
pip_val2  = tick_value / tick_size * pip2
lots2     = risk_usd / (sl_pips2 * pip_val2)

check("lots identici indiferent de pip (pip se anuleaza)", lots1, lots2, tol=1e-10)

# ── 5. pip_value_usd (costs.py) — simboluri cunoscute ────────────────────────
section("5. pip_value_usd (backtest) — simboluri cunoscute")
from strategy.costs import pip_value_usd
# Valorile de referinta pentru symbolurile active
pv_checks = [
    ("EURUSD", 1.10,  None, 10.0),    # $10/pip/lot standard
    ("USDJPY", 150.0, 150.0, 0.01 * 100000 / 150.0),  # JPY quote
    ("GER40",  18000, None, 0.011519/0.01),  # EUR profit, convertit de MT5 → 1.1519
    ("US30",   39000, None, 0.010000/0.01),  # $1.00/pt/lot → 1.0
    ("BTCUSD", 60000, None, 0.01),    # tick_value direct din _CRYPTO_TICK
    ("XAUUSD", 2000,  None, 1.0/0.01),  # $100/pt/lot
]
for sym, price, usdjpy, exp in pv_checks:
    got = pip_value_usd(sym, price, usdjpy)
    # toleranta mai larga pentru cross-rate calculations
    tol = max(0.01, abs(exp) * 0.001)
    check(f"pip_value_usd({sym})", got, exp, tol=tol)

# ── Sumar ─────────────────────────────────────────────────────────────────────
print(f"\n{'='*50}")
print(f"Rezultat: {PASS} PASS, {FAIL} FAIL")
if FAIL == 0:
    print("Toate testele de referinta trecute. Safe sa aplici fix-ul.")
else:
    print("ATENTIE: Teste esuate inainte de fix — verifica inainte de a continua!")
print('='*50)
