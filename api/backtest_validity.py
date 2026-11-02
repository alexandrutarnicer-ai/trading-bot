"""
Validarea unui rezultat de backtest (Custom Engine) — ce poate face cifrele NEREALISTE, afisat in Audit langa verdictul
M0. Functie PURA (nu schimba nimic din simulare / baseline-uri), testata in scripts/test_backtest_validity.py.

Provenienta (analiza Backtest vs Live, 2026-11-02):
  - XRPUSD: contractul s-a schimbat la broker (1 lot = 1 XRP, lot minim 100, pas 1) → R-uri imposibile (−26R, −7445R)
    pana la fix-ul din strategy/costs.py (LOT_SPECS / comision / swap / levier per simbol). Garda ramane: orice simbol nou cu
    un contract nereprezentat produce |R| mult peste tinta maxima → INVALID, nu „slab”.
  - CSV-urile de backtest erau din iunie–august: perioada recenta (cea care se compara cu live-ul) lipsea.
  - Contul Standard ICMarkets: spread-ul live pe FX include un markup (~0,8 pip) peste spread-ul brut din istoricul MT5.
  - Backtestul NU simuleaza: Filtrul AI pre-trade (116 din 179 de trade-uri „ratate” de live in perioada 27.07–01.11),
    Setarile Globale (capital, circuit breaker de cont, risc maxim), protectia la stiri, pauzele / oprirea engine-ului.
"""
from __future__ import annotations

from datetime import date

MAX_PLAUSIBLE_R = 8.0          # tinta maxima configurabila e 5,5R; +costuri / swap / gap-uri raman sub ~7R
STALE_DAYS = 14
_FX_Q = {"USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD"}

NOT_SIMULATED = [
    "Filtrul AI pre-trade (în live respinge o parte din semnale)",
    "Setările Globale (protecția capitalului, circuit breaker pe cont, risc maxim pe trade)",
    "Protecția la știri (pauză / închidere la știri)",
    "Pauzele manuale, oprirea engine-ului, AutoTrading oprit",
    "Slippage-ul real la executarea ordinelor stop",
]


def _is_fx(sym: str) -> bool:
    return len(sym) == 6 and sym[:3] in _FX_Q and sym[3:] in _FX_Q


def backtest_validity(R: list[float], markets: list[str], data_to: str | None, today: date | None = None) -> dict:
    """R = lista R-urilor trade-urilor; data_to = ultima zi din date (YYYY-MM-DD). Intoarce
    {"valid": bool, "warnings": [..], "not_simulated": [..]} — warnings = text pentru UI, in ordinea gravitatii."""
    today = today or date.today()
    warnings: list[str] = []
    bad = [r for r in R if r is not None and (r != r or abs(r) > MAX_PLAUSIBLE_R)]   # r != r → NaN
    valid = not bad
    if bad:
        worst = min((r for r in bad if r == r), default=float("nan"))
        warnings.append(f"REZULTAT INVALID: {len(bad)} trade-uri cu |R| > {MAX_PLAUSIBLE_R:g} (cel mai rău {worst:.1f}R) — "
                        "contractul pieței (lot / tick) nu e reprezentat corect în backtest (ex. XRPUSD după schimbarea "
                        "contractului la broker). Nu folosi aceste cifre.")
    if data_to:
        try:
            age = (today - date.fromisoformat(str(data_to)[:10])).days
            if age > STALE_DAYS:
                warnings.append(f"Datele se opresc la {str(data_to)[:10]} (acum {age} zile) — perioada recentă lipsește; "
                                "descarcă date noi din MT5 înainte să compari cu rezultatele live.")
        except ValueError:
            pass
    fx = [m for m in markets if _is_fx(m)]
    if fx:
        warnings.append("Costuri FX: spread-ul presupus e cel brut; pe contul Standard spread-ul live are un markup (~0,8 pip) — "
                        "pe SL-uri scurte (M15) rezultatul real poate fi puțin mai slab.")
    return {"valid": valid, "warnings": warnings, "not_simulated": NOT_SIMULATED}
