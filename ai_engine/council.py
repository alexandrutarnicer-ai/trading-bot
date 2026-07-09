"""
ai_engine.council — grupul de traderi AI.

Patru roluri, patru apeluri LLM secventiale (fiecare il vede pe cel dinainte —
o dezbatere reala, nu voturi izolate):

  1. TECHNICAL ANALYST — citeste briefing-ul numeric, da bias + niveluri
  2. MACRO/NEWS ANALYST — calendarul economic + contextul de sesiune, da bias + avertizari
  3. RISK MANAGER — provocatorul: cauta motive sa NU se tranzactioneze, poate veta
  4. HEAD TRADER — sintetizeaza si emite decizia finala, strict JSON

Iesire: (decision_dict, transcript_dict). Orice esec LLM → decizie WAIT
(fail-safe: motorul nu tranzactioneaza niciodata pe o dezbatere corupta).
"""

from __future__ import annotations

import time

from ai_engine.providers import ProviderError

_PREAMBLE = (
    "You are part of a professional trading desk making decisions on a DEMO account "
    "for research. Be rigorous, skeptical and concise. Base every statement ONLY on "
    "the data provided — never invent prices, news or facts. 'No trade' is always "
    "an acceptable, respectable conclusion."
)

_TECH_SYS = _PREAMBLE + (
    "\nROLE: Senior Technical Analyst. You analyze market structure: trend alignment "
    "across timeframes, momentum, support/resistance from swing levels, volatility "
    "state, and current price location within the recent range. You do NOT consider "
    "news — that is a colleague's job."
)
_TECH_USER = (
    "{briefing}\n\n"
    "Give your technical read. Respond ONLY with JSON:\n"
    '{{"bias": "long"|"short"|"neutral", "confidence": 0-100, '
    '"key_support": number|null, "key_resistance": number|null, '
    '"invalidation": number|null, "reasoning": "2-4 sentences"}}'
)

_MACRO_SYS = _PREAMBLE + (
    "\nROLE: Macro & News Analyst. You assess how upcoming economic events, the day "
    "of week, and the trading session (Asia/London/New York, given Romania local time: "
    "London opens ~10:00, NY ~15:00) affect this market right now. Flag event risk "
    "explicitly: trading minutes before high-impact news is usually gambling."
)
_MACRO_USER = (
    "{briefing}\n\n"
    "TECHNICAL ANALYST'S VIEW (for context): {tech_view}\n\n"
    "Give your macro/session read. Respond ONLY with JSON:\n"
    '{{"bias": "long"|"short"|"neutral", "confidence": 0-100, '
    '"event_risk": "none"|"low"|"high", "warnings": ["..."], '
    '"reasoning": "2-4 sentences"}}'
)

_RISK_SYS = _PREAMBLE + (
    "\nROLE: Risk Manager. You are the challenger. Your job is to find reasons NOT to "
    "trade: conflicting analyst views, event risk, abnormal volatility, weekend "
    "proximity (Friday evening), chop (no clear trend), or a setup with poor "
    "risk/reward geometry. You cannot be overruled on a veto."
)
_RISK_USER = (
    "{briefing}\n\n"
    "TECHNICAL ANALYST: {tech_view}\n"
    "MACRO ANALYST: {macro_view}\n"
    "DESK STATE: open AI positions: {open_positions} of max {max_positions}; "
    "realized today: {daily_r:+.1f}R (daily stop at -{max_daily_loss}R).\n\n"
    "Respond ONLY with JSON:\n"
    '{{"veto": true|false, "veto_reasons": ["..."], '
    '"max_risk_pct": 0.0025|0.005|0.01, "notes": "1-3 sentences"}}'
)

_HEAD_SYS = _PREAMBLE + (
    "\nROLE: Head Trader. You make the final call after hearing your desk. Rules you "
    "must respect:\n"
    "- If the Risk Manager vetoed, the action MUST be WAIT (or CLOSE if reviewing an "
    "open position that should be exited).\n"
    "- Only trade when technical and macro views agree or one is strongly convincing; "
    "disagreement means WAIT.\n"
    "- Every trade needs entry, stop-loss and take-profit. SL goes beyond a real "
    "structural level (swing), not an arbitrary distance. Risk/reward must be >= {min_rr}.\n"
    "- order_type 'stop' = pending order beyond current price in trade direction "
    "(breakout confirmation); 'market' = immediate entry.\n"
    "- risk_pct must not exceed what the Risk Manager allowed.\n"
    "- WAIT is a professional decision, not a failure."
)
_HEAD_USER = (
    "{briefing}\n\n"
    "TECHNICAL ANALYST: {tech_view}\n"
    "MACRO ANALYST: {macro_view}\n"
    "RISK MANAGER: {risk_view}\n"
    "OPEN POSITION ON THIS MARKET: {open_pos_desc}\n\n"
    "Make the final decision. Respond ONLY with JSON:\n"
    '{{"action": "OPEN_LONG"|"OPEN_SHORT"|"CLOSE"|"WAIT", '
    '"order_type": "market"|"stop"|null, '
    '"entry": number|null, "sl": number|null, "tp": number|null, '
    '"risk_pct": number|null, "confidence": 0-100, '
    '"rationale": "2-4 sentences summarizing the desk consensus"}}'
)


def convene(provider, briefing: str, desk_state: dict, cfg: dict) -> tuple[dict, dict, float]:
    """
    Ruleaza consiliul complet. Returneaza (decision, transcript, duration_s).
    Orice ProviderError la orice pas → decizie WAIT cu motivul in rationale.
    """
    t0 = time.time()
    transcript: dict = {}
    try:
        tech = provider.chat_json(
            _TECH_SYS, _TECH_USER.format(briefing=briefing),
            required_keys=["bias", "confidence", "reasoning"])
        transcript["technical"] = tech

        macro = provider.chat_json(
            _MACRO_SYS, _MACRO_USER.format(briefing=briefing, tech_view=_short(tech)),
            required_keys=["bias", "confidence", "event_risk", "reasoning"])
        transcript["macro"] = macro

        risk = provider.chat_json(
            _RISK_SYS, _RISK_USER.format(
                briefing=briefing, tech_view=_short(tech), macro_view=_short(macro),
                open_positions=desk_state.get("open_positions", 0),
                max_positions=cfg["max_open_positions"],
                daily_r=desk_state.get("daily_r", 0.0),
                max_daily_loss=cfg["max_daily_loss_R"]),
            required_keys=["veto", "max_risk_pct", "notes"])
        transcript["risk"] = risk

        head = provider.chat_json(
            _HEAD_SYS.format(min_rr=cfg["min_rr"]),
            _HEAD_USER.format(
                briefing=briefing, tech_view=_short(tech), macro_view=_short(macro),
                risk_view=_short(risk),
                open_pos_desc=desk_state.get("open_pos_desc", "none")),
            required_keys=["action", "confidence", "rationale"])
        transcript["head_trader"] = head

        decision = _sanitize(head, risk, cfg)
    except ProviderError as e:
        decision = {"action": "WAIT", "order_type": None, "entry": None, "sl": None,
                    "tp": None, "risk_pct": None, "confidence": 0,
                    "rationale": f"Consiliu esuat (LLM): {e}"}
        transcript["error"] = str(e)
    return decision, transcript, time.time() - t0


def _short(view: dict) -> str:
    """Rezumat compact al unui rol pentru prompt-ul urmatorului."""
    return str({k: v for k, v in view.items() if k != "reasoning"}) + \
           f" reasoning: {view.get('reasoning', view.get('notes', ''))}"


def _sanitize(head: dict, risk: dict, cfg: dict) -> dict:
    """Normalizeaza + aplica regulile pe care LLM-ul nu are voie sa le incalce."""
    d = {
        "action":     str(head.get("action", "WAIT")).upper(),
        "order_type": head.get("order_type"),
        "entry":      _num(head.get("entry")),
        "sl":         _num(head.get("sl")),
        "tp":         _num(head.get("tp")),
        "risk_pct":   _num(head.get("risk_pct")),
        "confidence": int(head.get("confidence", 0) or 0),
        "rationale":  str(head.get("rationale", ""))[:2000],
    }
    if d["action"] not in ("OPEN_LONG", "OPEN_SHORT", "CLOSE", "WAIT"):
        d["action"] = "WAIT"

    # Veto-ul Risk Manager-ului e absolut pentru deschideri noi.
    if risk.get("veto") and d["action"] in ("OPEN_LONG", "OPEN_SHORT"):
        d["action"] = "WAIT"
        d["rationale"] = "[VETO Risk Manager] " + d["rationale"]

    if d["action"] in ("OPEN_LONG", "OPEN_SHORT"):
        # risc: min(cerut, permis de risk manager, rail-ul hard din config)
        allowed = _num(risk.get("max_risk_pct")) or cfg["risk_pct_default"]
        want    = d["risk_pct"] or cfg["risk_pct_default"]
        d["risk_pct"] = min(want, allowed, cfg["risk_pct_max"])
        if d["order_type"] not in ("market", "stop"):
            d["order_type"] = "market"
    else:
        d["order_type"] = None
    return d


def _num(x) -> float | None:
    try:
        v = float(x)
        return v if v == v else None   # NaN guard
    except (TypeError, ValueError):
        return None
