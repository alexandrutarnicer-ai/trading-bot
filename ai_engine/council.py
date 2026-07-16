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

# Buget de timp implicit pentru un consiliu complet (4 roluri). Peste asta,
# convocarea e abandonata cu WAIT ca sa nu blocheze bucla motorului la fiecare
# bara. Aliniat cu ai_engine.trade_filter.TIME_BUDGET_S. Suprascriere: config
# cheia "council_time_budget_s".
COUNCIL_TIME_BUDGET_S = 240

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
    "need certainty before placing it. Place the stop entry a few pips BEYOND the "
    "level (past the swing high/low or range edge), never exactly at the current "
    "price — an entry at market is invalid for a stop order.\n"
    "- CRITICAL STOP DIRECTION (a wrong-side entry is auto-rejected by the desk): "
    "OPEN_LONG uses a BUY_STOP placed strictly ABOVE the current price (you buy the "
    "upside breakout). OPEN_SHORT uses a SELL_STOP placed strictly BELOW the current "
    "price (you sell the downside breakdown). Never put a SELL_STOP above price or a "
    "BUY_STOP below price — that is a limit order, not a stop, and will be rejected.\n"
    "- The stop-loss distance should be reasonable: roughly 1-4x the ATR from the "
    "briefing. If the only sane structural stop is more than ~5x ATR away, the setup "
    "is not tradeable at acceptable risk — choose WAIT instead of a huge stop.\n"
    "- Every trade needs entry, stop-loss and take-profit. Build the geometry in "
    "this ORDER: (1) pick the entry, (2) place the STOP beyond a real structural "
    "level (swing / range edge from the briefing) — this fixes your risk distance R, "
    "(3) compute the TAKE-PROFIT from that risk distance: TP must be at least "
    "{min_rr}x R away from entry, and you should aim for about 2x R. Do NOT set TP at "
    "the nearest chart level (e.g. right at the resistance you are breaking) — that "
    "produces a reward smaller than the risk, which is an automatic reject. Reward "
    "must always exceed risk.\n"
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
    "{extra}"
    "OPEN POSITION ON THIS MARKET: {open_pos_desc}\n\n"
    "Make the final decision. Respond ONLY with JSON:\n"
    '{{"action": "OPEN_LONG"|"OPEN_SHORT"|"CLOSE"|"WAIT", '
    '"order_type": "market"|"stop"|null, '
    '"entry": number|null, "sl": number|null, "tp": number|null, '
    '"risk_pct": number|null, "confidence": 0-100, '
    '"rationale": "2-4 sentences summarizing the desk consensus"}}'
)

# ── Roluri OPTIONALE (dezactivate by default) ────────────────────────────────
# Se insereaza inaintea Head Trader-ului, care le vede in prompt. Cand ambele
# sunt oprite, secventa e EXACT cea de dinainte (4 roluri) si prompt-ul Head
# Trader e neschimbat (_format_extra intoarce "").

_QUANT_SYS = _PREAMBLE + (
    "\nROLE: Quantitative / Volatility Analyst. You do NOT call direction — the "
    "technical desk owns that. You pressure-test the NUMBERS behind the setup: is "
    "the reward/risk justified by a realistic win probability, is the stop distance "
    "sane relative to ATR and its percentile, is the expected value positive? A 3R "
    "target means little if the win probability is 20%. Flag setups whose geometry "
    "only works on optimistic assumptions.\n"
    "GUIDANCE: estimate an HONEST win probability from structure quality and "
    "volatility state; expected value is roughly win_prob*R - (1-win_prob). Favor "
    "positive-EV setups with stops that are neither absurdly tight (noise-stopped) "
    "nor absurdly wide (>4-5x ATR)."
)
_QUANT_USER = (
    "{briefing}\n\n"
    "TECHNICAL ANALYST: {tech_view}\n"
    "MACRO ANALYST: {macro_view}\n\n"
    "Assess the quantitative quality of a trade in the technical direction. "
    "Respond ONLY with JSON:\n"
    '{{"assessment": "favorable"|"marginal"|"unfavorable", "confidence": 0-100, '
    '"est_win_prob": 0-100|null, "reasoning": "2-4 sentences"}}'
)

_DEVIL_SYS = _PREAMBLE + (
    "\nROLE: Devil's Advocate. Your ONLY job is to argue AGAINST the trade the desk "
    "is leaning toward — build the strongest bear case (if they lean long) or bull "
    "case (if they lean short), and run a PRE-MORTEM: assume the trade has already "
    "hit its stop, then explain what most likely killed it. You are not negative for "
    "its own sake; you exist to surface the blind spot the desk ignores because of "
    "confirmation bias. If, after genuinely trying, you find no serious objection, "
    "say so plainly (severity 'low')."
)
_DEVIL_USER = (
    "{briefing}\n\n"
    "TECHNICAL ANALYST: {tech_view}\n"
    "MACRO ANALYST: {macro_view}\n\n"
    "Argue against the desk's leaning direction and run the pre-mortem. "
    "Respond ONLY with JSON:\n"
    '{{"strongest_objection": "1-2 sentences", "failure_mode": "what most likely '
    'stops the trade out", "severity": "low"|"medium"|"high", '
    '"reasoning": "2-4 sentences"}}'
)


def _format_extra(views: dict) -> str:
    """
    Blocul optional cu rolurile suplimentare, pentru prompt-ul Head Trader. Gol
    cand niciun rol suplimentar nu e activ → prompt IDENTIC cu cel de dinainte.
    """
    if not views:
        return ""
    lines = ["ADDITIONAL SPECIALISTS (weigh their input; they inform, they do not "
             "override the desk):"]
    if "quant" in views:
        lines.append(f"  QUANT/VOLATILITY: {_short(views['quant'])}")
    if "devils_advocate" in views:
        lines.append(f"  DEVIL'S ADVOCATE: {_short(views['devils_advocate'])}")
    return "\n".join(lines) + "\n"


class DebateRunner:
    """
    Ruleaza rolurile unui consiliu secvential, cu buget de timp comun, adunand
    transcriptul. Ruteaza fiecare rol fie catre o sursa PINNED (fara failover —
    consiliile de consens raman independente, nu se prabusesc unele in altele),
    fie via `assignments` cu failover (un singur consiliu, comportamentul de
    dinainte de feature). Reutilizat de consiliul autonom (convene) SI de
    consiliul de revizie din trade_filter.
    """

    def __init__(self, registry, cfg: dict, source: str | None = None,
                 assignments: dict | None = None, deadline: float | None = None):
        self.registry = registry
        self.source = source
        self.assignments = assignments or {}
        self.transcript: dict = {}
        self.fallback_from: str | None = None
        self.t0 = time.time()
        budget = float(cfg.get("council_time_budget_s", COUNCIL_TIME_BUDGET_S))
        self.deadline = deadline if deadline is not None else self.t0 + budget

    def ask(self, role: str, system: str, user: str, required: list[str]) -> dict:
        # Buget verificat INTRE roluri: o sursa lenta nu poate bloca bucla peste o bara.
        if time.time() > self.deadline:
            raise ProviderError(
                f"buget de timp consiliu depasit (la rolul {role})", kind="network")
        if self.source is not None:
            view, meta = self.registry.call_role_pinned(self.source, system, user, required)
        else:
            view, meta = self.registry.call_role(role, self.assignments, system, user, required)
        # metadata de audit in transcript (prefix _ → nu intra in prompturi)
        view["_provider"]  = meta["provider"]
        view["_latency_s"] = meta["latency_s"]
        if meta.get("fallback_from"):
            view["_fallback_from"] = meta["fallback_from"]
            self.fallback_from = meta["fallback_from"]
        self.transcript[role] = view
        return view

    def elapsed(self) -> float:
        return time.time() - self.t0


def convene(registry, briefing: str, desk_state: dict, cfg: dict,
            source: str | None = None) -> tuple[dict, dict, float]:
    """
    Ruleaza consiliul complet si returneaza (decision, transcript, duration_s).

    `source=None` (implicit): fiecare rol isi ia sursa din cfg["role_assignments"]
    cu failover automat — IDENTIC cu comportamentul de dinainte de feature.
    `source="nume"`: TOATE rolurile ruleaza pinned pe acea sursa, fara failover —
    folosit de consensul multi-council ca sa fie o opinie independenta.

    Rolurile Quant / Devil's Advocate ruleaza doar daca cfg["role_quant_enabled"] /
    cfg["role_devils_advocate_enabled"] sunt True (ambele False by default).

    Orice ProviderError (sursa picata / buget depasit) → decizie WAIT (fail-safe).
    """
    runner = DebateRunner(registry, cfg, source=source,
                          assignments=cfg.get("role_assignments", {}))
    transcript = runner.transcript
    trigger = desk_state.get("trigger", "scheduled review")
    try:
        tech = runner.ask("technical", _TECH_SYS,
                          _TECH_USER.format(briefing=briefing, trigger=trigger),
                          ["bias", "confidence", "reasoning"])

        macro = runner.ask("macro", _MACRO_SYS,
                           _MACRO_USER.format(briefing=briefing, tech_view=_short(tech)),
                           ["bias", "confidence", "event_risk", "reasoning"])

        risk = runner.ask("risk", _RISK_SYS,
                          _RISK_USER.format(
                              briefing=briefing, tech_view=_short(tech), macro_view=_short(macro),
                              open_positions=desk_state.get("open_positions", 0),
                              max_positions=cfg["max_open_positions"],
                              daily_r=desk_state.get("daily_r", 0.0),
                              max_daily_loss=cfg["max_daily_loss_R"]),
                          ["veto", "max_risk_pct", "notes"])

        extra_views: dict = {}
        if cfg.get("role_quant_enabled"):
            extra_views["quant"] = runner.ask(
                "quant", _QUANT_SYS,
                _QUANT_USER.format(briefing=briefing, tech_view=_short(tech),
                                   macro_view=_short(macro)),
                ["assessment", "confidence", "reasoning"])
        if cfg.get("role_devils_advocate_enabled"):
            extra_views["devils_advocate"] = runner.ask(
                "devils_advocate", _DEVIL_SYS,
                _DEVIL_USER.format(briefing=briefing, tech_view=_short(tech),
                                   macro_view=_short(macro)),
                ["strongest_objection", "severity", "reasoning"])

        head = runner.ask("head_trader", _HEAD_SYS.format(min_rr=cfg["min_rr"]),
                          _HEAD_USER.format(
                              briefing=briefing, trigger=trigger,
                              tech_view=_short(tech), macro_view=_short(macro),
                              risk_view=_short(risk), extra=_format_extra(extra_views),
                              open_pos_desc=desk_state.get("open_pos_desc", "none")),
                          ["action", "confidence", "rationale"])

        decision = _sanitize(head, risk, cfg)
        # Increderea DECIZIEI = media membrilor consiliului (nu doar head trader).
        # Head-ul raporteaza sistematic mai sus decat media desk-ului; ordinele se
        # gate-uiesc pe media membrilor contra consensus_threshold (orchestrator).
        avg = council_confidence(transcript)
        if avg is not None:
            decision["head_confidence"] = decision["confidence"]
            decision["confidence"] = avg
    except ProviderError as e:
        decision = {"action": "WAIT", "order_type": None, "entry": None, "sl": None,
                    "tp": None, "risk_pct": None, "confidence": 0,
                    "rationale": f"Consiliu esuat (LLM): {e}"}
        transcript["error"] = str(e)
    return decision, transcript, runner.elapsed()


def _short(view: dict) -> str:
    """Rezumat compact al unui rol pentru prompt-ul urmatorului (fara metadata _*)."""
    return str({k: v for k, v in view.items()
                if k != "reasoning" and not k.startswith("_")}) + \
           f" reasoning: {view.get('reasoning', view.get('notes', ''))}"


# Rolurile care raporteaza un camp numeric "confidence" (Risk Manager si Avocatul
# Diavolului nu au — ei se exprima prin veto/severity, nu prin incredere).
_CONFIDENCE_ROLES = ("technical", "macro", "quant", "head_trader")


def council_confidence(transcript: dict) -> int | None:
    """
    MEDIA increderilor MEMBRILOR consiliului (technical/macro/[quant]/head).

    Aceasta e valoarea pe care o gate-uieste pragul de consens ("bara" din UI):
    increderea afisata/stocata a unei decizii trebuie sa fie media calculata a
    fiecarui membru care raporteaza confidence, nu doar parerea Head Trader-ului
    (care e sistematic mai optimista decat media analiza+macro). None daca niciun
    rol nu a produs o incredere numerica (ex: consiliu esuat).
    """
    vals = []
    for role in _CONFIDENCE_ROLES:
        view = transcript.get(role)
        if isinstance(view, dict):
            c = _num(view.get("confidence"))
            if c is not None:
                vals.append(max(0.0, min(100.0, c)))
    return int(round(sum(vals) / len(vals))) if vals else None


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
        _repair_tp(d, cfg)
    else:
        d["order_type"] = None
    return d


def _price_decimals(*vals) -> int:
    """Numarul de zecimale al preturilor de intrare (pentru a rotunji TP la fel)."""
    dec = 0
    for v in vals:
        if v is None:
            continue
        s = f"{float(v):.10f}".rstrip("0")
        if "." in s:
            dec = max(dec, len(s.split(".")[1]))
    return min(dec, 6) if dec else 5


def _repair_tp(d: dict, cfg: dict) -> None:
    """
    Repara geometria TP daca RR e sub minim. Modelele mici pun uneori TP prea
    aproape (la un nivel de chart, ex. exact la rezistenta) -> reward < risk ->
    RR < 1 -> rail-ul din executor ar respinge tot setup-ul. Aici, cand SL e deja
    structural si valid, DUCEM TP la o tinta coerenta (target_rr) in loc sa
    aruncam trade-ul. Nu inventam nimic: directia si SL raman ce a decis consiliul,
    doar tinta de profit devine sanatoasa. Rail-ul RR>=min din executor ramane
    activ ca plasa de siguranta.
    """
    entry, sl, tp = d.get("entry"), d.get("sl"), d.get("tp")
    if entry is None or sl is None:
        return   # market fara entry explicit -> validat cu pretul live in executor
    direction = 1 if d["action"] == "OPEN_LONG" else -1
    risk_dist = abs(entry - sl)
    if risk_dist <= 0:
        return   # SL degenerat -> lasam executorul sa respinga (geometrie invalida)
    min_rr = float(cfg.get("min_rr", 1.0))
    cur_rr = ((tp - entry) * direction / risk_dist) if tp is not None else -1.0
    if cur_rr >= min_rr:
        return   # TP-ul modelului e deja OK — respectam alegerea lui
    target_rr = max(float(cfg.get("target_rr", 2.0)), min_rr)
    new_tp = round(entry + direction * risk_dist * target_rr,
                   _price_decimals(entry, sl))
    d["tp"] = new_tp
    d["rationale"] = (f"[TP recalculat la {target_rr:.1f}R "
                      f"(propus {cur_rr:.2f}R prea aproape)] ") + d["rationale"]


def clamp_tp_to_max_rr(d: dict, max_rr: float | None) -> bool:
    """
    Oglinda lui _repair_tp, pentru plafonul PER PIATA (market_overrides.max_rr):
    daca TP-ul propus depaseste max_rr, il ADUCEM la max_rr (directia si SL raman
    ale consiliului — doar tinta de profit e plafonata la politica pietei).
    Returneaza True daca a modificat TP-ul. max_rr=None → nimic (comportament vechi).
    """
    if max_rr is None or d.get("action") not in ("OPEN_LONG", "OPEN_SHORT"):
        return False
    entry, sl, tp = d.get("entry"), d.get("sl"), d.get("tp")
    if entry is None or sl is None or tp is None:
        return False
    direction = 1 if d["action"] == "OPEN_LONG" else -1
    risk_dist = abs(entry - sl)
    if risk_dist <= 0:
        return False
    cur_rr = (tp - entry) * direction / risk_dist
    if cur_rr <= float(max_rr):
        return False
    d["tp"] = round(entry + direction * risk_dist * float(max_rr),
                    _price_decimals(entry, sl))
    d["rationale"] = (f"[TP plafonat la {float(max_rr):.1f}R "
                      f"(limita pietei; propus {cur_rr:.2f}R)] ") + d.get("rationale", "")
    return True


def _num(x) -> float | None:
    try:
        v = float(x)
        return v if v == v else None   # NaN guard
    except (TypeError, ValueError):
        return None
