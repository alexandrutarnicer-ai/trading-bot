"""
telegram_bridge.ai_fast — nivelul "ai ..." (raspuns rapid, ~5-30s).

Reutilizeaza EXACT registrul de surse al motorului (ai_engine.providers +
ai_engine.config) — aceleasi chei, aceeasi sanatate, acelasi failover. Injecteaza
un context compact (scorecard + pozitii + erori recente) si cere un raspuns in
proza (nu JSON) de la prima sursa sanatoasa.

Nu atinge MT5, nu scrie in ledger, nu porneste consiliul motorului. Doar un apel
LLM de tip chat cu context — consuma din quota surselor tale AI (asta e scopul).
"""

from __future__ import annotations

import json

from . import status as st


_SYSTEM = (
    "Esti asistentul unui bot de trading algoritmic (forex/indici/cripto pe MT5 "
    "DEMO). Raspunzi SCURT si la obiect, in romana, pentru un mesaj de telefon. "
    "Ai context live despre bot si motorul AI mai jos. Daca ceva nu se poate sti "
    "din context, spune clar ca nu ai datele — NU inventa cifre. Nu da sfaturi "
    "financiare personalizate; explica mecanic ce face sistemul."
)


def _context(cfg: dict) -> str:
    _, ai = st.ai_running()
    mt5 = st.mt5_snapshot(cfg)
    orders = st.orders_snapshot(cfg)
    ctx = {
        "motor_ai": {
            "running": ai.get("running"),
            "markets": ai.get("markets"),
            "scorecard": ai.get("scorecard"),
            "scorecard_by_symbol": ai.get("scorecard_by_symbol"),
            "role_assignments": ai.get("role_assignments"),
            "providers_health": {k: v.get("status") for k, v in (ai.get("providers") or {}).items()},
            "last_errors": ai.get("last_errors"),
        },
        "cont_mt5": {
            "connected": mt5.get("connected"),
            "is_demo": mt5.get("is_demo"),
            "equity": mt5.get("equity"),
            "algo_trading_enabled": mt5.get("algo_trading_enabled"),
        },
        "pozitii_deschise": [
            {"symbol": p.get("symbol"), "type": p.get("type") or p.get("direction"),
             "profit": p.get("profit", p.get("pnl")), "source": p.get("source")}
            for p in (orders.get("positions") or [])[:15]
        ],
        "pending": len(orders.get("pending") or []),
    }
    return json.dumps(ctx, ensure_ascii=False, default=str)


def answer(cfg: dict, question: str) -> tuple[str, str | None]:
    """
    Returneaza (text_raspuns, nume_sursa). nume_sursa=None daca nicio sursa AI nu
    a raspuns (apelantul aplica fallback / mesaj onest).
    """
    try:
        from ai_engine.config import load_config, load_keys
        from ai_engine.providers import ProviderRegistry, ProviderError
    except Exception as e:
        return (f"(nu pot incarca sursele AI: {e})", None)

    try:
        acfg = load_config()
        reg = ProviderRegistry(acfg.get("providers", {}), load_keys())
    except Exception as e:
        return (f"(nu pot construi registrul de surse: {e})", None)

    user = (f"CONTEXT LIVE (JSON):\n{_context(cfg)}\n\n"
            f"INTREBARE: {question.strip()}")

    # Ordinea: sursele sanatoase in ordinea din registru; ollama (safety-net) ultimul.
    order = reg.usable_sources()
    order.sort(key=lambda n: n == reg.DEFAULT)   # default (ollama) la coada
    if not order:
        return ("(nicio sursa AI sanatoasa acum)", None)

    last = ""
    for name in order:
        inst = reg._instances.get(name)
        if inst is None:
            continue
        try:
            txt = inst.chat(_SYSTEM, user)
            reg.report_success(name)
            return (txt.strip(), name)
        except ProviderError as e:
            reg.report_failure(name, e)
            last = str(e)
            continue
        except Exception as e:
            last = str(e)
            continue
    return (f"(toate sursele AI au esuat: {last[:200]})", None)
