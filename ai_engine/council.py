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

# ── Prompturile motorului AUTONOM (revizuite 23.11.2026 — docs/AI_ENGINE_DECISION_QUALITY.md) ──────────────────
# Diagnostic (ledger real, 103 trade-uri, −28R): prompturile vechi IMPINGEAU spre tranzactie („OPEN cand tehnicul are
# >= 55 — rezultatul normal”, „conflictul cu D1 reduce doar marimea, nu forteaza WAIT”, „un stop nu costa nimic, nu ai
# nevoie de certitudine”) → inclinatie LONG (oct: 401 LONG / 2 SHORT), intrari in regim CHOPPY (63% din pierdere),
# geometrie gresita (297 de respingeri). Acum: WAIT implicit, citirea contextului in ordine fixa, factori pentru /
# contra / lipsa, simetrie long / short, increderea construita explicit (nu o probabilitate), stirile DOAR din briefing.
# Riscul (lot, SL minim, limite, protectii) ramane in COD — LLM-ul nu-l decide. _PREAMBLE (vechi) ramane pentru
# filtrul pre-trade al Custom Engine (pragurile lui sunt calibrate pe el).
_ENGINE_PREAMBLE = (
    "You are part of a disciplined intraday trading desk (DEMO / research). Rules for every role:\n"
    "1. Use ONLY the briefing data. Never invent prices, levels, news or events; if something is missing, say so.\n"
    "2. NO TRADE is the default. A trade needs several INDEPENDENT confirmations (trend, structure, momentum, regime) "
    "and no serious contradiction. One indicator alone is never enough.\n"
    "3. Judge LONG and SHORT by exactly the same standard — a downtrend is as tradeable as an uptrend.\n"
    "4. You do not size positions or change limits: a deterministic risk system (lot size, minimum stop distance, "
    "daily stop, capital protection) runs after you and cannot be overridden.\n"
    "5. Confidence is NOT a win probability — it scores setup quality: start at 50, +10 for each independent "
    "confirmation, -10 for each contradiction or important missing information. Above 80 ONLY when M30 trend, D1 "
    "trend and regime all agree with the direction and nothing important is missing (the desk trades only above 80)."
)

_TECH_SYS = _ENGINE_PREAMBLE + (
    "\nROLE: Technical Analyst (15-minute execution). Work in this order:\n"
    "(a) TREND: M30 and D1 direction — agree or conflict?\n"
    "(b) REGIME: the efficiency line (TRENDING / NEUTRAL / CHOPPY).\n"
    "(c) LOCATION: where price sits in the 20-bar range (ATR distances are given).\n"
    "(d) MOMENTUM: RSI, EMA alignment, returns.\n"
    "(e) SETUP: direction, and the level that would invalidate it.\n"
    "DIRECTION RULES:\n"
    "- The bias follows the M30 trend. A bias against M30 needs an explicit structural reason; against BOTH M30 and "
    "D1 → neutral.\n"
    "- CHOPPY regime → neutral (range-edge breakouts in chop usually fail).\n"
    "- Price already more than 1 ATR beyond the range edge in the trade direction = late entry → neutral.\n"
    "- You do NOT consider news — a colleague does."
)
_TECH_USER = (
    "{briefing}\n\n"
    "COUNCIL CONVENED BECAUSE: {trigger}\n\n"
    "Give your technical read. Respond ONLY with JSON:\n"
    '{{"trend_read": "M30 up/down/flat, D1 up/down — agree/conflict", "regime": "TRENDING|NEUTRAL|CHOPPY", '
    '"bias": "short"|"neutral"|"long", "confidence": 0-100, '
    '"for": ["confirmations"], "against": ["contradictions"], "missing": ["unknown information"], '
    '"key_support": number|null, "key_resistance": number|null, "invalidation": number|null, '
    '"reasoning": "2-3 sentences"}}'
)

_MACRO_SYS = _ENGINE_PREAMBLE + (
    "\nROLE: Macro & News Analyst. Use ONLY the economic-calendar lines of the briefing.\n"
    "- If the briefing says the calendar is UNAVAILABLE, event risk is unknown: say so and set event_risk \"unknown\" "
    "— never assume there is no news.\n"
    "- A high-impact event for this symbol's currencies within 60 minutes (CPI, NFP, FOMC / Fed speakers incl. Powell, "
    "central-bank decisions, GDP) → event_risk \"high\".\n"
    "- Session context (Romania time): London ~10:00, New York ~15:30; Friday evening and late session = thin liquidity.\n"
    "- Your bias is only a note on the technical view (agree / disagree and why), never a new technical analysis."
)
_MACRO_USER = (
    "{briefing}\n\n"
    "TECHNICAL ANALYST'S VIEW (for context): {tech_view}\n\n"
    "Give your macro/session read. Respond ONLY with JSON:\n"
    '{{"bias": "short"|"neutral"|"long", "confidence": 0-100, '
    '"event_risk": "none"|"low"|"high"|"unknown", "warnings": ["..."], '
    '"reasoning": "2-3 sentences"}}'
)

_RISK_SYS = _ENGINE_PREAMBLE + (
    "\nROLE: Risk Manager. You manage EXPOSURE, not direction. Veto ONLY with one of these codes:\n"
    "- NEWS_IMMINENT: high-impact event within 45 minutes on this market's currencies\n"
    "- DAILY_STOP: realized R today is at or beyond -2R\n"
    "- MAX_POSITIONS: open positions already at the maximum\n"
    "- EXTREME_VOL: ATR percentile above 95 (disorderly market)\n"
    "- WEEKEND_GAP: Friday after 20:00 local for FX\n"
    "- BAD_GEOMETRY: no structural level exists for a sane stop-loss\n"
    "A veto without one of these codes is ignored by the desk's systems. Size DOWN (max_risk_pct 0.0025) when: the "
    "regime is CHOPPY or NEUTRAL, event risk is unknown, the trend timeframes conflict, or the setup is late."
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

_HEAD_SYS = _ENGINE_PREAMBLE + (
    "\nROLE: Head Trader — the final call, strict JSON.\n"
    "OPEN only when ALL of these hold — otherwise WAIT (WAIT is the default and costs nothing):\n"
    "1. The Technical Analyst's bias is long or short with confidence >= 60, and its 'for' list is stronger than its "
    "'against' list.\n"
    "2. The regime is not CHOPPY and the entry is not late (price not more than 1 ATR beyond the range edge).\n"
    "3. The Macro Analyst does not flag high event risk; unknown event risk → only with a strong setup.\n"
    "4. No valid Risk Manager veto.\n"
    "ORDER GEOMETRY — use the briefing's reference levels, do not invent new ones:\n"
    "- order_type 'stop'. OPEN_LONG = BUY_STOP strictly ABOVE the current price (at or above the LONG reference "
    "entry). OPEN_SHORT = SELL_STOP strictly BELOW the current price (at or below the SHORT reference entry).\n"
    "- Stop-loss beyond the structural level AND at least the briefing's minimum stop-loss distance from the entry.\n"
    "- Take-profit = entry ± 2 × |entry − stop-loss| (at least {min_rr} × the risk distance).\n"
    "- If a sane stop-loss would be more than 5 × ATR away → WAIT.\n"
    "Your confidence = your judgment of setup quality after weighing for / against / missing (not a win probability)."
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
        # Termenul limita ajunge pana la cererea HTTP (timeout = timpul ramas).
        if self.source is not None:
            view, meta = self.registry.call_role_pinned(self.source, system, user, required,
                                                        deadline=self.deadline)
        else:
            view, meta = self.registry.call_role(role, self.assignments, system, user, required,
                                                 deadline=self.deadline)
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

        # Rolurile Quant / Avocatul Diavolului au fost ELIMINATE (2026-10-31): pe 356
        # verdicte reale au scazut aprobarea de la 12% la 4-6% fara dovada ca trade-urile
        # respinse in plus erau mai proaste, + latenta. Prompt Head Trader neschimbat.
        extra_views: dict = {}

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
