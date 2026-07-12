"""
ai_engine.orchestrator — consens multi-council pentru MOTORUL AUTONOM.

Modelul e asimetric (spre deosebire de filtrul pe reguli, unde toate consiliile
sunt egale): consiliul PRIMAR construieste efectiv trade-ul (directie + geometrie,
via council.convene). Daca sunt configurate surse secundare/tertiare, acele
consilii REVIZUIESC trade-ul propus (aceleasi prompturi de revizie ca filtrul,
via trade_filter.review_trade) si emit fiecare o incredere. Executia e apoi
gate-uita de CONSENS (media increderilor efective + veto absolut, consensus.py).

Backward compatible: fara surse secundare/tertiare → un singur apel convene, EXACT
ca inainte (fara strat de consens). Fault-tolerant: daca revizorii pica, decide
singur consiliul primar (esecul unui consiliu optional nu blocheaza niciodata).
"""

from __future__ import annotations

import time

from ai_engine import council


def _rr(entry, sl, tp) -> float | None:
    try:
        risk = abs(float(entry) - float(sl))
        return round(abs(float(tp) - float(entry)) / risk, 2) if risk > 0 else None
    except (TypeError, ValueError):
        return None


def decide(registry, symbol: str, snap: dict, briefing: str, desk_state: dict,
           cfg: dict) -> tuple[dict, dict, float]:
    """
    Returneaza (decision, bundle, duration_s). `bundle` contine transcriptul
    consiliului primar + (daca e cazul) opiniile revizorilor si verdictul de
    consens — pentru ledger/UI. Nu ridica: erorile de sursa devin WAIT (fail-safe).
    """
    primary_src = cfg.get("council_primary_source") or None
    sec = cfg.get("council_secondary_source") or None
    ter = cfg.get("council_tertiary_source") or None
    multi = bool(sec or ter)

    decision, transcript, dur = council.convene(
        registry, briefing, desk_state, cfg,
        source=(primary_src if multi else None))
    bundle: dict = {"primary": transcript, "consensus": None, "reviewers": []}

    # Fara consiliu multiplu, sau primarul n-a propus o deschidere → nimic de revizuit.
    if not multi or decision["action"] not in ("OPEN_LONG", "OPEN_SHORT"):
        return decision, bundle, dur

    # Import lazy — evita ciclul la incarcare (trade_filter importa din council).
    from ai_engine.trade_filter import review_trade
    from ai_engine.consensus import CouncilOpinion, combine, resolve_sources

    entry = decision.get("entry")
    if entry is None:                      # ordin market → foloseste pretul curent
        entry = snap.get("price")
    sig = {
        "symbol":     symbol,
        "direction":  1 if decision["action"] == "OPEN_LONG" else -1,
        "dir_str":    "LONG" if decision["action"] == "OPEN_LONG" else "SHORT",
        "entry":      entry, "sl": decision.get("sl"), "tp": decision.get("tp"),
        "r_ratio":    _rr(entry, decision.get("sl"), decision.get("tp")),
        "signal_type": "ai-primary",
        "atr_pips":   snap.get("atr"),
    }

    primary_label = primary_src or "roluri"
    primary_op = CouncilOpinion(
        source=primary_label, approved=True,
        confidence=int(decision.get("confidence") or 0), hard_veto=None,
        reason=decision.get("rationale", "")[:300], transcript=transcript, duration_s=dur)
    opinions = [primary_op]

    reviewer_sources, _dups = resolve_sources(sec, ter)
    reviewer_sources = [s for s in reviewer_sources if s != primary_src]  # nu duplica primarul
    deadline = time.time() + council.COUNCIL_TIME_BUDGET_S
    for src in reviewer_sources:
        opinions.append(review_trade(registry, briefing, sig, cfg,
                                     source=src, deadline=deadline))

    threshold = int(cfg.get("consensus_threshold", 70))
    verdict = combine(opinions, threshold)
    bundle["consensus"] = verdict.to_dict()
    bundle["reviewers"] = verdict.per_council[1:]

    reviewer_participated = any(o.participated for o in opinions[1:])
    if not reviewer_participated:
        # Revizorii indisponibili → decide singur primarul (nu blocam din cauza lor).
        decision["rationale"] = ("[Consens: revizori indisponibili — decide consiliul "
                                 "primar] " + decision.get("rationale", ""))[:2000]
        return decision, bundle, dur

    if not verdict.approved:
        decision = {
            "action": "WAIT", "order_type": None, "entry": None, "sl": None, "tp": None,
            "risk_pct": None,
            "confidence": (int(round(verdict.consensus_confidence))
                           if verdict.consensus_confidence is not None else 0),
            "rationale": (f"[Consens respins] {verdict.reason} | Primar propunea: "
                          f"{primary_op.reason}")[:2000],
        }
    else:
        cc = verdict.consensus_confidence
        decision["rationale"] = (
            f"[Consens {verdict.n_participating} consilii: {cc:.0f}% >= {threshold}% · "
            f"{', '.join(verdict.sources)}] " + decision.get("rationale", ""))[:2000]
    return decision, bundle, dur
