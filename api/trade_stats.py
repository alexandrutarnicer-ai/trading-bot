"""
Statistici pe grupuri de tranzactii inchise MT5 — SURSA UNICA pentru Top 5 Piete (Dashboard),
Rapoarte → Piete si Rapoarte → Comisioane+Swap (2026-11-06).

Inainte fiecare endpoint isi facea propria agregare, cu definitii diferite de restul
Dashboard-ului: Top 5 numara break-even-ul ca pierdere (losses = n − wins), win rate-ul era
wins / n (restul aplicatiei: wins / (wins + losses)), expectancy-ul impartea R-ul la TOATE
trade-urile (inclusiv cele fara SL, deci fara R) si clasamentul era DOAR dupa R — o piata cu
R negativ dar profit in $ (loturi diferite intre engine-uri) aparea sub una cu pierdere in $.

Definitii (aceleasi ca `mt5status._perf` / `/mt5/stats`):
  win = profit > 0, loss = profit < 0, break-even = 0 (nici una)
  win_rate = wins / (wins + losses)
  expectancy_r = total_r / trades_with_r (doar pozitiile cu SL → R rezolvabil)
  pnl_gross = profitul deal-urilor de iesire (spread-ul e DEJA inclus — e in pretul de executie)
  costs = comision + swap (taxe separate de pret), pnl_net = pnl_gross + costs
  spread_est = estimarea costului de spread (negativ), DOAR informativ: e deja in pnl_gross,
               nu se scade a doua oara. Calculat la spread-ul CURENT al simbolului × volum.

Functii pure — fara MT5, testate in scripts/test_reports_costs.py.
"""

from __future__ import annotations

from typing import Callable, Iterable


def summarize(trades: Iterable[dict], spread_per_lot: dict[str, float] | None = None) -> dict:
    """Statistici pentru un grup de tranzactii. `spread_per_lot` = {simbol: $ / lot (pozitiv)}."""
    trades = list(trades)
    spl = spread_per_lot or {}
    wins = losses = 0
    total_r = 0.0
    n_r = 0
    gross = comm = swap = 0.0
    spread = 0.0
    n_spread = 0
    for t in trades:
        p = float(t.get("profit") or 0.0)
        if p > 0:
            wins += 1
        elif p < 0:
            losses += 1
        gross += p
        comm += float(t.get("commission") or 0.0)
        swap += float(t.get("swap") or 0.0)
        r = t.get("result_r")
        if r is not None:
            total_r += float(r)
            n_r += 1
        per_lot = spl.get(t.get("symbol"))
        vol = t.get("volume")
        if per_lot is not None and vol:
            spread -= per_lot * float(vol)
            n_spread += 1
    n = len(trades)
    decided = wins + losses
    costs = comm + swap
    return {
        "trades": n,
        "wins": wins,
        "losses": losses,
        "breakeven": n - decided,
        "win_rate": round(100.0 * wins / decided, 1) if decided else 0.0,
        "trades_with_r": n_r,
        "total_r": round(total_r, 3),
        "expectancy_r": round(total_r / n_r, 3) if n_r else None,
        "pnl_gross": round(gross, 2),
        "commission": round(comm, 2),
        "swap": round(swap, 2),
        "costs": round(costs, 2),
        "pnl_net": round(gross + costs, 2),
        "cost_per_trade": round(costs / n, 3) if n else 0.0,
        # spread: None cand nu s-a putut estima pentru niciun trade (MT5 / simbol indisponibil)
        "spread_est": round(spread, 2) if n_spread else None,
        "spread_est_trades": n_spread,
    }


def group_by(trades: Iterable[dict], key: Callable[[dict], object],
             spread_per_lot: dict[str, float] | None = None) -> dict:
    """{cheie: summarize(grup)} — ordinea cheilor = ordinea primei aparitii."""
    groups: dict[object, list] = {}
    for t in trades:
        groups.setdefault(key(t), []).append(t)
    return {k: summarize(v, spread_per_lot) for k, v in groups.items()}


SORT_KEYS = {
    # cheie de sortare (descrescator); R-ul lipsa (piata fara SL) ajunge la coada
    "net":   lambda s: s["pnl_net"],
    "gross": lambda s: s["pnl_gross"],
    "r":     lambda s: s["total_r"] if s["trades_with_r"] else float("-inf"),
    "trades": lambda s: s["trades"],
    "costs": lambda s: -s["costs"],   # cele mai scumpe primele (costurile sunt negative)
}


def rank(stats: dict, sort: str = "net") -> list[tuple[object, dict]]:
    """Perechile (cheie, statistici) sortate descrescator dupa `sort` (implicit P&L net)."""
    fn = SORT_KEYS.get(sort, SORT_KEYS["net"])
    return sorted(stats.items(), key=lambda kv: fn(kv[1]), reverse=True)
