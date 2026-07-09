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
    "\nROLE: Senior Technical Analyst on an intraday desk (15-minute execution "
    "timeframe). You analyze market structure: trend, momentum, support/resistance "
    "from swing levels, volatility state, and price location within the range. "
    "You do NOT consider news — that is a colleague's job.\n"
    "STANCE POLICY (important):\n"
    "- Your PRIMARY direction signal is the M30 trend and current price action; "
    "higher timeframes (D1/Weekly) adjust CONFIDENCE, they do not force neutrality. "
    "Intraday desks trade M30 moves against the daily trend all the time — with "
    "reduced confidence, not with paralysis.\n"
    "- Price pressing the edge of the 20-bar range WITH an M30 trend behind it is a "
    "directional setup (breakout continuation), not a neutral condition.\n"
    "- 'neutral' is reserved for genuine chop: no M30 trend AND price mid-range. "
    "If you output neutral, say what specific price level would change your mind."
)
_TECH_USER = (
    "{briefing}\n\n"
    "COUNCIL CONVENED BECAUSE: {trigger} — address this directly: does it offer a "
    "tradeable setup, in which direction, and where are entry/stop levels?\n\n"
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
    "\nROLE: Risk Manager. You manage EXPOSURE, you do not re-do technical analysis "
    "— the analysts own the directional call. Your veto exists ONLY for hard risk "
    "conditions. You may veto ONLY with one of these codes:\n"
    "- NEWS_IMMINENT: high-impact event within 45 minutes on this market's currencies\n"
    "- DAILY_STOP: realized R today is at or beyond -2R (approaching the daily stop)\n"
    "- MAX_POSITIONS: open positions already at the maximum\n"
    "- EXTREME_VOL: ATR percentile above 95 (disorderly market)\n"
    "- WEEKEND_GAP: Friday after 20:00 local for FX (weekend gap risk)\n"
    "- BAD_GEOMETRY: no structural level exists for a sane stop-loss\n"
    "Anything else (mixed timeframes, neutral RSI, price near resistance, personal "
    "doubt) is NOT a veto — express it by lowering max_risk_pct to 0.0025. "
    "A veto without one of these codes will be ignored by the desk's systems."
)
_RISK_USER = (
    "{briefing}\n\n"
    "TECHNICAL ANALYST: {tech_view}\n"
    "MACRO ANALYST: {macro_view}\n"
    "DESK STATE: open AI positions: {open_positions} of max {max_positions}; "
    "realized today: {daily_r:+.1f}R (daily stop at -{max_daily_loss}R).\n\n"
    "Respond ONLY with JSON:\n"
    '{{"veto": true|false, "veto_code": "NEWS_IMMINENT"|"DAILY_STOP"|"MAX_POSITIONS"'
    '|"EXTREME_VOL"|"WEEKEND_GAP"|"BAD_GEOMETRY"|null, '
    '"max_risk_pct": 0.0025|0.005|0.01, "notes": "1-3 sentences"}}'
)

_HEAD_SYS = _PREAMBLE + (
    "\nROLE: Head Trader. You make the final call after hearing your desk.\n"
    "DECISION RULE:\n"
    "- OPEN in the Technical Analyst's direction when their confidence is >= 55 and "
    "the Macro Analyst does not flag high event risk against it. That is the normal "
    "outcome of a desk convened on a real trigger.\n"
    "- Higher-timeframe conflict or moderate doubts reduce SIZE (use the Risk "
    "Manager's max_risk_pct, or 0.0025), they do not force WAIT.\n"
    "- Prefer order_type 'stop': a pending order placed beyond the breakout level in "
    "the trade direction. The market must reach it to trigger — an untriggered stop "
    "order costs NOTHING and expires. This is confirmation by price, so you do not "
    "need certainty before placing it.\n"
    "- Every trade needs entry, stop-loss and take-profit. SL goes beyond a real "
    "structural level (swing / range edge from the briefing), not an arbitrary "
    "distance. Risk/reward must be >= {min_rr}.\n"
    "- If the Risk Manager vetoed WITH a valid code, the action MUST be WAIT (or "
    "CLOSE when reviewing a position that should be exited).\n"
    "- WAIT is correct only when: no directional bias at all, valid risk veto, or no "
    "structural level exists for the stop."
)
_HEAD_USER = (
    "{briefing}\n\n"
    "COUNCIL CONVENED BECAUSE: {trigger}\n"
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


def convene(registry, briefing: str, desk_state: dict, cfg: dict) -> tuple[dict, dict, float]:
    """
    Ruleaza consiliul complet. `registry` este ProviderRegistry — fiecare rol
    isi ia sursa din cfg["role_assignments"], cu failover automat (vezi
    providers.ProviderRegistry.call_role). Returneaza (decision, transcript,
    duration_s). Orice ProviderError (toate sursele picate) → decizie WAIT.
    """
    t0 = time.time()
    assignments = cfg.get("role_assignments", {})
    transcript: dict = {}

    def _ask(role: str, system: str, user: str, required: list[str]) -> dict:
        view, meta = registry.call_role(role, assignments, system, user, required)
        # metadata de audit in transcript (prefix _ → nu intra in prompturi)
        view["_provider"]  = meta["provider"]
        view["_latency_s"] = meta["latency_s"]
        if "fallback_from" in meta:
            view["_fallback_from"] = meta["fallback_from"]
        transcript[role] = view
        return view

    trigger = desk_state.get("trigger", "scheduled review")
    try:
        tech = _ask("technical", _TECH_SYS,
                    _TECH_USER.format(briefing=briefing, trigger=trigger),
                    ["bias", "confidence", "reasoning"])

        macro = _ask("macro", _MACRO_SYS,
                     _MACRO_USER.format(briefing=briefing, tech_view=_short(tech)),
                     ["bias", "confidence", "event_risk", "reasoning"])

        risk = _ask("risk", _RISK_SYS,
                    _RISK_USER.format(
                        briefing=briefing, tech_view=_short(tech), macro_view=_short(macro),
                        open_positions=desk_state.get("open_positions", 0),
                        max_positions=cfg["max_open_positions"],
                        daily_r=desk_state.get("daily_r", 0.0),
                        max_daily_loss=cfg["max_daily_loss_R"]),
                    ["veto", "max_risk_pct", "notes"])

        head = _ask("head_trader", _HEAD_SYS.format(min_rr=cfg["min_rr"]),
                    _HEAD_USER.format(
                        briefing=briefing, trigger=trigger,
                        tech_view=_short(tech), macro_view=_short(macro),
                        risk_view=_short(risk),
                        open_pos_desc=desk_state.get("open_pos_desc", "none")),
                    ["action", "confidence", "rationale"])

        decision = _sanitize(head, risk, cfg)
    except ProviderError as e:
        decision = {"action": "WAIT", "order_type": None, "entry": None, "sl": None,
                    "tp": None, "risk_pct": None, "confidence": 0,
                    "rationale": f"Consiliu esuat (LLM): {e}"}
        transcript["error"] = str(e)
    return decision, transcript, time.time() - t0


def _short(view: dict) -> str:
    """Rezumat compact al unui rol pentru prompt-ul urmatorului (fara metadata _*)."""
    return str({k: v for k, v in view.items()
                if k != "reasoning" and not k.startswith("_")}) + \
           f" reasoning: {view.get('reasoning', view.get('notes', ''))}"


# Codurile de veto pe care sistemul le onoreaza. Orice veto FARA un cod din
# lista e tratat ca prudenta (risc redus la minim), nu ca blocaj — altfel un
# model pesimist cu veto nelimitat duce la paralizie totala (29/29 veto-uri
# observate pe 2026-07-08/09, toate cu motive de analiza tehnica, nu de risc).
VALID_VETO_CODES = {"NEWS_IMMINENT", "DAILY_STOP", "MAX_POSITIONS",
                    "EXTREME_VOL", "WEEKEND_GAP", "BAD_GEOMETRY"}
MIN_RISK_PCT = 0.0025


def _veto_flag(v) -> bool:
    """Bool robust: modelele pot returna si 'true'/'false' ca string."""
    if isinstance(v, bool):
        return v
    return isinstance(v, str) and v.strip().lower() in ("true", "yes", "da", "1")


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

    # Veto-ul e onorat DOAR cu un cod valid de risc (aplicat in cod, nu de model).
    veto      = _veto_flag(risk.get("veto"))
    veto_code = str(risk.get("veto_code") or "").strip().upper()
    veto_valid = veto and veto_code in VALID_VETO_CODES
    veto_soft  = veto and not veto_valid   # prudenta necalificata -> risc minim

    if veto_valid and d["action"] in ("OPEN_LONG", "OPEN_SHORT"):
        d["action"] = "WAIT"
        d["rationale"] = f"[VETO Risk Manager: {veto_code}] " + d["rationale"]

    if d["action"] in ("OPEN_LONG", "OPEN_SHORT"):
        # risc: min(cerut, permis de risk manager, rail-ul hard din config)
        allowed = _num(risk.get("max_risk_pct")) or cfg["risk_pct_default"]
        want    = d["risk_pct"] or cfg["risk_pct_default"]
        d["risk_pct"] = min(want, allowed, cfg["risk_pct_max"])
        if veto_soft:
            d["risk_pct"] = MIN_RISK_PCT
            d["rationale"] = "[Prudenta Risk Manager -> risc redus la minim] " + d["rationale"]
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
