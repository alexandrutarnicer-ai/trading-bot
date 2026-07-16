"""
ai_engine.trade_filter — Filtrul AI Pre-Trade pentru botul pe reguli.

Validarea FINALA a unui semnal generat de bot, inainte ca ordinul sa fie trimis
in MT5. Reutilizeaza integral infrastructura motorului AI:

  - ProviderRegistry + role_assignments din ai_engine/config.json + data/ai/providers.json
    (aceleasi surse AI ca motorul; hot-reload la fiecare evaluare — schimbarile
    facute din UI se aplica imediat, fara restart de bot)
  - perception.build_snapshot / render_text — acelasi briefing numeric de piata
  - consiliul de 4 roluri (Technical / Macro / Risk / Head Trader), cu prompturi
    specifice de REVIZIE: trade-ul e deja complet format de motorul pe reguli
    (entry/SL/TP/R fixe) — consiliul NU proiecteaza trade-ul, doar il aproba/respinge.

Diferente fata de consiliul motorului autonom (council.py):
  - intrebarea e "aprobati acest trade?" (approve + confidence), nu "ce facem?"
  - veto-ul Risk Manager e onorat DOAR cu cod valid (acelasi anti-paralizie
    ca in council._sanitize); veto necalificat NU respinge, e doar notat.
  - FAIL-OPEN: orice eroare (LLM cazut, JSON invalid, timeout de buget) →
    approved=True cu `error` setat. Edge-ul principal e al botului pe reguli;
    filtrul e un strat suplimentar care nu are voie sa opreasca botul cand
    infrastructura AI e indisponibila. (Motorul autonom face invers — WAIT —
    pentru ca acolo AI-ul E strategia.)

Praguri de incredere (validate contra distributiei reale de confidence a
modelelor mici — vezi docs/AI_TRADE_FILTER.md):
  permissive 50 · balanced 70 · strict 85
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime

from ai_engine.config import load_config, load_keys
from ai_engine.providers import ProviderRegistry, ProviderError
from ai_engine.council import (_PREAMBLE, _short, VALID_VETO_CODES,
                               DebateRunner, _format_extra)
from ai_engine.consensus import CouncilOpinion, combine, resolve_sources

# ── Praguri de incredere ─────────────────────────────────────────────────────
# permissive: blocheaza doar setup-urile pe care consiliul le considera slabe
# balanced:   pragul "normal" — peste nivelul 55 pe care motorul autonom il
#             trateaza ca actionabil, dar sub zona de super-incredere
# strict:     doar setup-urile cu conviction reala. NU 90+: modelele isi
#             raporteaza rar incredere >85 pe date ambigue (paralizie garantata).
FILTER_LEVELS: dict[str, int] = {"permissive": 50, "balanced": 70, "strict": 85}
DEFAULT_LEVEL = "balanced"

# Buget total de timp pentru consiliu (verificat INTRE roluri). Depasit → fail-open.
TIME_BUDGET_S = 240

# Codurile de veto relevante pentru un trade deja format (subset din council):
# DAILY_STOP / MAX_POSITIONS lipsesc — limitele de expunere ale botului pe
# reguli sunt gestionate de bot insusi (circuit breaker, max_concurrent).
_FILTER_VETO_CODES = {"NEWS_IMMINENT", "EXTREME_VOL", "WEEKEND_GAP", "BAD_GEOMETRY"} \
                     & VALID_VETO_CODES


# ── Prompturi (aceleasi 4 roluri ca motorul, misiune de REVIZIE) ─────────────

_TECH_SYS = _PREAMBLE + (
    "\nROLE: Senior Technical Analyst reviewing a SYSTEMATIC trade signal. A "
    "rule-based engine (pullback-in-trend on M15/M30, validated on 8 years of "
    "backtests) proposes a trade with FIXED entry, stop-loss and take-profit. "
    "You do NOT redesign the trade — you assess whether current market structure "
    "supports it: trend alignment, momentum, location vs swing levels and range, "
    "stop placement sanity. The engine has a real statistical edge; your job is "
    "to catch the minority of signals fired into hostile conditions (chop, "
    "exhausted moves, price pressed into major resistance for a long, etc.)."
)
_TECH_USER = (
    "{briefing}\n\n"
    "PROPOSED TRADE (fixed, from the rule engine):\n{trade}\n\n"
    "Assess whether market structure supports this trade. Respond ONLY with JSON:\n"
    '{{"alignment": "supports"|"against"|"mixed", "confidence": 0-100, '
    '"reasoning": "2-4 sentences"}}'
)

_MACRO_SYS = _PREAMBLE + (
    "\nROLE: Macro & News Analyst reviewing a systematic trade signal. Assess "
    "TIMING quality: upcoming economic events for this market's currencies, day "
    "of week, and trading session (Romania local time: London opens ~10:00, NY "
    "~15:00). The entry is a pending stop order — it may trigger within the next "
    "few hours. Flag event risk explicitly; trading minutes before high-impact "
    "news is usually gambling."
)
_MACRO_USER = (
    "{briefing}\n\n"
    "PROPOSED TRADE:\n{trade}\n\n"
    "TECHNICAL ANALYST'S REVIEW (for context): {tech_view}\n\n"
    "Assess the timing/macro quality of taking this trade now. Respond ONLY with JSON:\n"
    '{{"timing_quality": "good"|"neutral"|"poor", "event_risk": "none"|"low"|"high", '
    '"confidence": 0-100, "reasoning": "2-4 sentences"}}'
)

_RISK_SYS = _PREAMBLE + (
    "\nROLE: Risk Manager reviewing a systematic trade signal. You manage "
    "EXPOSURE conditions, you do not re-do the analysis. Your veto exists ONLY "
    "for hard risk conditions. You may veto ONLY with one of these codes:\n"
    "- NEWS_IMMINENT: high-impact event within 45 minutes on this market's currencies\n"
    "- EXTREME_VOL: ATR percentile above 95 (disorderly market)\n"
    "- WEEKEND_GAP: Friday after 20:00 local for FX (weekend gap risk)\n"
    "- BAD_GEOMETRY: the stop-loss sits at no structural level, or reward < risk\n"
    "Anything else (mixed signals, neutral RSI, personal doubt) is NOT a veto — "
    "voice it as a concern. A veto without one of these codes will be ignored "
    "by the desk's systems. Note: the rule engine already enforces position "
    "limits and a daily circuit breaker — those are not your concern here."
)
_RISK_USER = (
    "{briefing}\n\n"
    "PROPOSED TRADE:\n{trade}\n\n"
    "TECHNICAL ANALYST: {tech_view}\n"
    "MACRO ANALYST: {macro_view}\n\n"
    "Respond ONLY with JSON:\n"
    '{{"veto": true|false, "veto_code": "NEWS_IMMINENT"|"EXTREME_VOL"|"WEEKEND_GAP"'
    '|"BAD_GEOMETRY"|null, "concerns": ["..."], "notes": "1-3 sentences"}}'
)

_HEAD_SYS = _PREAMBLE + (
    "\nROLE: Head Trader making the final APPROVE/REJECT call on a systematic "
    "trade signal, after hearing your desk.\n"
    "DECISION RULE:\n"
    "- The rule engine has a validated statistical edge; the DEFAULT for a "
    "clean signal in a supportive market is APPROVE. You reject the minority "
    "of signals fired into clearly hostile conditions.\n"
    "- APPROVE when the Technical Analyst finds structure supportive (or mixed "
    "with good reasons) and the Macro Analyst sees no high event risk against it.\n"
    "- REJECT when structure clearly opposes the trade, timing is poor with "
    "high event risk, or the Risk Manager raised a coded veto.\n"
    "- Your `confidence` (0-100) expresses how convinced you are that TAKING "
    "this trade now is right. It gates execution: the desk only executes above "
    "a configured threshold. Be honest, not diplomatic: a mediocre setup "
    "deserves 40-60, a clean aligned setup 70-85, an exceptional one 85+.\n"
    "- Doubt lowers confidence; it does not flip approve to reject on its own."
)
_HEAD_USER = (
    "{briefing}\n\n"
    "PROPOSED TRADE:\n{trade}\n\n"
    "TECHNICAL ANALYST: {tech_view}\n"
    "MACRO ANALYST: {macro_view}\n"
    "RISK MANAGER: {risk_view}\n"
    "{extra}\n"
    "Make the final call. Respond ONLY with JSON:\n"
    '{{"approve": true|false, "confidence": 0-100, '
    '"reason": "2-3 sentences summarizing the desk consensus"}}'
)

# ── Roluri OPTIONALE de revizie (dezactivate by default) ─────────────────────
# Gate-uite prin cfg["role_quant_enabled"] / cfg["role_devils_advocate_enabled"]
# (mapate din session_cfg ai_role_*). Cand ambele sunt oprite, consiliul de
# revizie e EXACT cel de dinainte (4 roluri).

_QUANT_SYS = _PREAMBLE + (
    "\nROLE: Quantitative / Volatility Analyst reviewing a SYSTEMATIC trade signal "
    "with FIXED entry, stop and take-profit. You do NOT redesign it. You judge the "
    "NUMBERS: is the fixed reward/risk justified by a realistic win probability, is "
    "the stop sane vs ATR and its percentile, is expected value positive? EV is "
    "roughly win_prob*RR - (1-win_prob). Flag signals whose geometry only pays off "
    "on optimistic assumptions; endorse those with a positive, robust edge."
)
_QUANT_USER = (
    "{briefing}\n\n"
    "PROPOSED TRADE:\n{trade}\n\n"
    "TECHNICAL ANALYST: {tech_view}\n"
    "MACRO ANALYST: {macro_view}\n\n"
    "Assess the quantitative quality of taking this fixed trade. Respond ONLY with JSON:\n"
    '{{"assessment": "favorable"|"marginal"|"unfavorable", "confidence": 0-100, '
    '"est_win_prob": 0-100|null, "reasoning": "2-4 sentences"}}'
)

_DEVIL_SYS = _PREAMBLE + (
    "\nROLE: Devil's Advocate reviewing a SYSTEMATIC trade signal. Your ONLY job is "
    "to argue AGAINST taking this specific trade now and run a PRE-MORTEM: assume it "
    "already hit its stop, then explain what most likely killed it. The rule engine "
    "has a real edge, so do not reject on principle — but surface the blind spot the "
    "desk may be ignoring. If you find no serious objection, say so (severity 'low')."
)
_DEVIL_USER = (
    "{briefing}\n\n"
    "PROPOSED TRADE:\n{trade}\n\n"
    "TECHNICAL ANALYST: {tech_view}\n"
    "MACRO ANALYST: {macro_view}\n\n"
    "Argue against taking this trade and run the pre-mortem. Respond ONLY with JSON:\n"
    '{{"strongest_objection": "1-2 sentences", "failure_mode": "what most likely '
    'stops it out", "severity": "low"|"medium"|"high", "reasoning": "2-4 sentences"}}'
)


# ── Helpers de veto / consiliu de revizie reutilizabile ──────────────────────

def _flag(v) -> bool:
    """Bool robust: modelele pot returna 'true'/'false' ca string."""
    if isinstance(v, bool):
        return v
    return isinstance(v, str) and v.strip().lower() in ("true", "yes", "da", "1")


def _hard_veto(risk: dict) -> str | None:
    """Codul de veto DOAR daca e valid pentru filtru — altfel None (prudenta necalificata)."""
    code = str(risk.get("veto_code") or "").strip().upper()
    return code if (_flag(risk.get("veto")) and code in _FILTER_VETO_CODES) else None


def _rep_source(runner: DebateRunner, assignments: dict | None) -> str:
    """Eticheta sursei pentru un consiliu distribuit pe roluri (source=None)."""
    ht = runner.transcript.get("head_trader", {})
    return ht.get("_provider") or (assignments or {}).get("head_trader") or "roluri"


def run_review_council(registry, briefing: str, trade_desc: str, cfg: dict,
                       source: str | None = None, assignments: dict | None = None,
                       deadline: float | None = None, log=None) -> CouncilOpinion:
    """
    Ruleaza consiliul de revizie (4-6 roluri) pe un trade DEJA format si intoarce
    o CouncilOpinion (approved/confidence/hard_veto/transcript). Pinned pe `source`
    (consens, fara failover) sau via `assignments` (un singur consiliu, cu failover).
    Nu ridica: orice ProviderError → opinion cu `error` setat (consiliul iese din joc).
    """
    t0 = time.time()
    src_label = source or "roluri"
    try:
        runner = DebateRunner(registry, cfg, source=source,
                              assignments=assignments or {}, deadline=deadline)
        tech = runner.ask("technical", _TECH_SYS,
                          _TECH_USER.format(briefing=briefing, trade=trade_desc),
                          ["alignment", "confidence", "reasoning"])
        macro = runner.ask("macro", _MACRO_SYS,
                           _MACRO_USER.format(briefing=briefing, trade=trade_desc,
                                              tech_view=_short(tech)),
                           ["timing_quality", "event_risk", "confidence", "reasoning"])
        risk = runner.ask("risk", _RISK_SYS,
                          _RISK_USER.format(briefing=briefing, trade=trade_desc,
                                            tech_view=_short(tech), macro_view=_short(macro)),
                          ["veto", "notes"])
        extra_views: dict = {}
        if cfg.get("role_quant_enabled"):
            extra_views["quant"] = runner.ask(
                "quant", _QUANT_SYS,
                _QUANT_USER.format(briefing=briefing, trade=trade_desc,
                                   tech_view=_short(tech), macro_view=_short(macro)),
                ["assessment", "confidence", "reasoning"])
        if cfg.get("role_devils_advocate_enabled"):
            extra_views["devils_advocate"] = runner.ask(
                "devils_advocate", _DEVIL_SYS,
                _DEVIL_USER.format(briefing=briefing, trade=trade_desc,
                                   tech_view=_short(tech), macro_view=_short(macro)),
                ["strongest_objection", "severity", "reasoning"])
        head = runner.ask("head_trader", _HEAD_SYS,
                          _HEAD_USER.format(briefing=briefing, trade=trade_desc,
                                            tech_view=_short(tech), macro_view=_short(macro),
                                            risk_view=_short(risk),
                                            extra=_format_extra(extra_views)),
                          ["approve", "confidence", "reason"])
        v = TradeFilter._verdict(head, risk)
        return CouncilOpinion(
            source=(source or _rep_source(runner, assignments)),
            approved=v["approved"], confidence=v["confidence"],
            hard_veto=_hard_veto(risk), reason=v["reason"],
            transcript=runner.transcript, duration_s=round(time.time() - t0, 1),
            fallback_from=runner.fallback_from)
    except ProviderError as e:
        if log:
            log.warning(f"  [AI-FILTER] consiliul «{src_label}» indisponibil ({e})")
        return CouncilOpinion(source=src_label, approved=False, confidence=None,
                              error=str(e)[:300], transcript={},
                              duration_s=round(time.time() - t0, 1))


def review_trade(registry, briefing: str, sig: dict, cfg: dict,
                 source: str | None = None, session_cfg: dict | None = None,
                 deadline: float | None = None, log=None) -> CouncilOpinion:
    """
    Wrapper subtire peste run_review_council pentru orchestratorul motorului
    autonom: revizuieste un trade descris de `sig` (dict cu symbol/direction/
    entry/sl/tp/r_ratio/dir_str) pe o sursa data. Foloseste describe_trade.
    """
    trade_desc = describe_trade(sig, session_cfg)
    return run_review_council(registry, briefing, trade_desc, cfg, source=source,
                              assignments=cfg.get("role_assignments"),
                              deadline=deadline, log=log)


def describe_trade(sig: dict, session_cfg: dict | None = None) -> str:
    """Descrierea compacta a trade-ului propus, pentru prompturi."""
    scfg = session_cfg or {}
    risk = abs(sig["entry"] - sig["sl"])
    lines = [
        f"  symbol: {sig['symbol']}  direction: {sig.get('dir_str', 'LONG' if sig['direction'] == 1 else 'SHORT')}",
        f"  entry (pending stop order): {sig['entry']}  stop-loss: {sig['sl']}  take-profit: {sig['tp']}",
        f"  risk distance: {risk:.5f}  reward/risk: {sig.get('r_ratio', '?')}R",
        f"  signal type: {sig.get('signal_type', 'pullback')} on "
        f"{scfg.get('entry_tf', 'M15')}+{scfg.get('trend_tf', 'M30')}",
    ]
    if sig.get("n_optional") is not None:
        lines.append(f"  optional criteria satisfied: {sig['n_optional']} "
                     "(RSI band / EMA alignment / D1 ADX)")
    if sig.get("rsi") is not None:
        lines.append(f"  RSI at signal bar: {sig['rsi']}")
    if sig.get("atr_pips") is not None:
        lines.append(f"  ATR at signal bar: {sig['atr_pips']} pips")
    exp = scfg.get("expire_bars")
    if exp:
        lines.append(f"  order expires if not triggered within {exp} bars")
    return "\n".join(lines)


def build_briefing(src, symbol: str) -> str:
    """
    Briefing-ul numeric de piata — reutilizeaza perception (aceiasi ochi ca
    motorul AI: indicatori din strategy.preparation._enrich + calendar
    ForexFactory cu cache 10 min). Import lazy: perception trage news_guard etc.
    """
    from ai_engine import perception
    old_n = getattr(src, "_n_bars", 2000)
    try:
        src._n_bars = 2000   # warm-up suficient pt EMA200 M30 + weekly (ca motorul)
        snap = perception.build_snapshot(src, symbol)
        return perception.render_text(snap)
    finally:
        src._n_bars = old_n


def normalize_level(level) -> str:
    lv = str(level or DEFAULT_LEVEL).strip().lower()
    return lv if lv in FILTER_LEVELS else DEFAULT_LEVEL


class TradeFilter:
    """
    Consiliul de revizie pre-trade. Tine un ProviderRegistry propriu (procesul
    sesiunii live), sincronizat la FIECARE evaluare cu ai_engine/config.json +
    data/ai/providers.json — mostenirea automata a configuratiei motorului AI.
    """

    def __init__(self):
        self._registry: ProviderRegistry | None = None
        self._cfg: dict = {}

    def _refresh(self) -> None:
        self._cfg = load_config()
        keys = load_keys()
        if self._registry is None:
            self._registry = ProviderRegistry(self._cfg["providers"], keys)
        else:
            self._registry.refresh(self._cfg["providers"], keys)

    @staticmethod
    def _plan_councils(session_cfg: dict, assignments: dict, registry) -> list[str | None]:
        """
        Sursele consiliilor din config-ul sesiunii. Fara secondary/tertiary → un
        singur consiliu (sentinel `None` = distribuit pe roluri, EXACT ca inainte).
        Cu secondary/tertiary → consilii pinned pe surse DISTINCTE (primary default
        pe sursa Head Trader-ului). Feature: Multi-Council Consensus.
        """
        sc = session_cfg or {}
        primary = sc.get("ai_filter_primary_source") or None
        sec = sc.get("ai_filter_secondary_source") or None
        ter = sc.get("ai_filter_tertiary_source") or None
        if not (sec or ter):
            return [primary]   # [None] = un consiliu distribuit pe roluri (backward compat)
        p = primary or (assignments or {}).get("head_trader") or registry.DEFAULT
        sources, _dups = resolve_sources(p, sec, ter)
        return sources or [None]

    def evaluate(self, sig: dict, briefing: str, level: str,
                 session_cfg: dict | None = None, log=None) -> dict:
        """
        Ruleaza pana la 3 consilii AI de revizie pe un semnal si combina verdictele
        prin CONSENS (media increderilor efective + veto absolut — vezi consensus.py).
        NU ridica niciodata — orice esec total intoarce approved=True (fail-open).

        Un singur consiliu (default) → comportament IDENTIC cu cel de dinainte de
        feature: effective = confidence daca aproba altfel 0; aprobat ⟺ >= prag.

        Returneaza (campuri de dinainte + campuri noi additive):
          {approved, confidence, threshold, level, reason, veto, veto_code, error,
           duration_s, transcript, consensus_confidence, n_councils, sources,
           councils, consensus}
        """
        lv = normalize_level(level)
        threshold = FILTER_LEVELS[lv]
        t0 = time.time()
        base = {"level": lv, "threshold": threshold, "veto": False,
                "veto_code": None, "error": None, "transcript": {},
                "consensus_confidence": None, "n_councils": 0, "sources": [],
                "councils": [], "consensus": None}

        try:
            self._refresh()
            registry = self._registry
            cfg = dict(self._cfg)
            # Rolurile optionale se activeaza per sesiune (mostenesc global daca lipsesc).
            cfg["role_quant_enabled"] = bool((session_cfg or {}).get(
                "ai_role_quant_enabled", cfg.get("role_quant_enabled", False)))
            cfg["role_devils_advocate_enabled"] = bool((session_cfg or {}).get(
                "ai_role_devils_advocate_enabled", cfg.get("role_devils_advocate_enabled", False)))
            assignments = cfg.get("role_assignments", {})
            trade_desc = describe_trade(sig, session_cfg)

            council_sources = self._plan_councils(session_cfg or {}, assignments, registry)
            opinions: list[CouncilOpinion] = []
            if len(council_sources) == 1 and council_sources[0]:
                # UN singur consiliu cu sursa PREFERATA: rulam cu FAILOVER, nu
                # pinned — sursa aleasa → celelalte surse sanatoase → ollama.
                # (Pinned exista doar pentru independenta opiniilor in modul
                # multi-council; cu un singur consiliu, un blip la sursa aleasa
                # nu are voie sa scoata filtrul din joc — cerinta: filtrul
                # consuma toate sursele AI si abia apoi cade pe fail-open.)
                pref = {role: council_sources[0] for role in
                        ("technical", "macro", "risk", "quant",
                         "devils_advocate", "head_trader")}
                opinions = [run_review_council(
                    registry, briefing, trade_desc, cfg, source=None,
                    assignments=pref, deadline=t0 + TIME_BUDGET_S, log=log)]
            else:
                # Buget PER consiliu (nu comun): un consiliu lent nu mai consuma
                # bugetul urmatoarelor — consiliile 2/3 nu mai picau doar pentru
                # ca primul a fost lent (esec observat cu rolurile optionale active).
                opinions = [
                    run_review_council(registry, briefing, trade_desc, cfg, source=src,
                                       assignments=assignments,
                                       deadline=time.time() + TIME_BUDGET_S, log=log)
                    for src in council_sources
                ]

            verdict = combine(opinions, threshold)
            if verdict.all_failed and any(council_sources):
                # Toate consiliile pinned au picat → INAINTE de fail-open, o ultima
                # incercare cu failover complet pe roluri (orice sursa sanatoasa →
                # ollama). Abia daca si asta pica, filtrul devine fail-open.
                if log:
                    log.warning("  [AI-FILTER] toate consiliile pinned au picat — "
                                "incerc consiliul de rezerva cu failover (→ ollama)")
                fb = run_review_council(registry, briefing, trade_desc, cfg, source=None,
                                        assignments=assignments,
                                        deadline=time.time() + TIME_BUDGET_S, log=log)
                opinions.append(fb)
                verdict = combine(opinions, threshold)
            dur = round(time.time() - t0, 1)

            if verdict.all_failed:
                err = next((o.error for o in opinions if o.error), "consiliu indisponibil")
                if log:
                    log.warning(f"  [AI-FILTER] toate consiliile indisponibile ({err}) "
                                "— fail-open, trade permis")
                return {**base, "approved": True, "confidence": None,
                        "reason": "Filtru AI indisponibil — trade permis (fail-open).",
                        "error": err[:300], "duration_s": dur,
                        "councils": verdict.per_council, "consensus": verdict.to_dict()}

            # Consiliul "primar" pentru motiv/transcript = primul care a PARTICIPAT
            # (cu fallback-ul de rezerva, opinions[0] poate fi un consiliu picat).
            primary_op = next((o for o in opinions if o.participated), opinions[0])
            single = verdict.n_participating <= 1
            if verdict.consensus_confidence is None:
                # veto absolut → nu exista o medie de consens
                confidence = primary_op.confidence if single else None
            elif single:
                confidence = primary_op.confidence   # backward compat: increderea head-ului
            else:
                confidence = int(round(verdict.consensus_confidence))
            reason = self._compose_reason(verdict, primary_op, threshold, lv, single)
            # transcriptul principal ramane cel al consiliului primar (compat UI);
            # opiniile per consiliu sunt in `councils`.
            transcript = primary_op.transcript
            return {**base,
                    "approved":  verdict.approved,
                    "confidence": confidence,
                    "reason":    reason,
                    "veto":      bool(verdict.veto_code),
                    "veto_code": verdict.veto_code,
                    "consensus_confidence": verdict.consensus_confidence,
                    "n_councils": verdict.n_participating,
                    "sources":   verdict.sources,
                    "councils":  verdict.per_council,
                    "consensus": verdict.to_dict(),
                    "duration_s": dur,
                    "transcript": transcript}

        except ProviderError as e:
            if log:
                log.warning(f"  [AI-FILTER] indisponibil ({e}) — fail-open, trade permis")
            return {**base, "approved": True, "confidence": None,
                    "reason": "Filtru AI indisponibil — trade permis (fail-open).",
                    "error": str(e)[:300],
                    "duration_s": round(time.time() - t0, 1)}
        except Exception as e:
            if log:
                log.warning(f"  [AI-FILTER] eroare neasteptata ({type(e).__name__}: {e}) "
                            "— fail-open, trade permis")
            return {**base, "approved": True, "confidence": None,
                    "reason": "Eroare interna filtru AI — trade permis (fail-open).",
                    "error": f"{type(e).__name__}: {e}"[:300],
                    "duration_s": round(time.time() - t0, 1)}

    @staticmethod
    def _compose_reason(verdict, primary_op, threshold: int, lv: str, single: bool) -> str:
        """Motivul afisat — reproduce mesajele de dinainte de feature pt 1 consiliu."""
        if verdict.veto_code:
            return primary_op.reason          # deja "[VETO ...] ..." din _verdict
        if single:
            if (not verdict.approved and primary_op.approved
                    and (primary_op.confidence or 0) < threshold):
                return (f"Încredere {primary_op.confidence}% sub pragul {threshold}% "
                        f"(nivel {lv}). {primary_op.reason}")
            return primary_op.reason
        # multi-council: motivul de consens + rezumatul consiliului primar
        return verdict.reason + (f" {primary_op.reason}" if primary_op.reason else "")

    @staticmethod
    def _verdict(head: dict, risk: dict) -> dict:
        """
        Regulile aplicate IN COD (LLM-ul propune, codul dispune):
          1. veto Risk Manager cu cod VALID → respins, indiferent de head trader
          2. head trader approve=false → respins (motivul lui)
          3. approve=true dar confidence < prag → respins ("sub prag")
          4. altfel → aprobat
        Veto necalificat (fara cod valid) NU respinge — doar apare in motiv.

        NOTA: aceasta functie decide approve la nivel de UN consiliu (fara pragul
        de incredere — pragul se aplica pe media de consens in `evaluate`).
        """
        try:
            confidence = max(0, min(100, int(float(head.get("confidence", 0) or 0))))
        except (TypeError, ValueError):
            confidence = 0
        approve = _flag(head.get("approve"))
        reason  = str(head.get("reason", ""))[:1000]

        veto      = _flag(risk.get("veto"))
        veto_code = str(risk.get("veto_code") or "").strip().upper()
        veto_valid = veto and veto_code in _FILTER_VETO_CODES

        out = {"confidence": confidence, "reason": reason,
               "veto": bool(veto), "veto_code": veto_code or None}

        if veto_valid:
            out["approved"] = False
            out["reason"] = f"[VETO Risk Manager: {veto_code}] {reason}"
        elif not approve:
            out["approved"] = False
        elif veto and not veto_valid:
            # prudenta necalificata: notata, nu blocanta (anti-paralizie)
            out["approved"] = True
            out["reason"] = f"{reason} [Nota: prudenta Risk Manager, fara cod valid]"
        else:
            out["approved"] = True
        return out


# ── Jurnal per sesiune (data/live_signals/<sesiune>/ai_filter.jsonl) ─────────

def log_verdict(output_dir: str, sig: dict, verdict: dict) -> None:
    """
    Scrie verdictul in jurnalul JSONL al sesiunii — append atomic, un JSON per
    linie (acelasi pattern ca notifications). Citit de API pentru badge-ul
    BOT-AI din Ordine Active si pentru coloanele AI din Rapoarte. Best-effort:
    esecul jurnalului nu afecteaza niciodata fluxul de tranzactionare.
    """
    try:
        entry = {
            "sig_id":      sig["signal_id"],
            "time":        datetime.now().isoformat(timespec="seconds"),
            "symbol":      sig["symbol"],
            "direction":   sig["direction"],
            "dir_str":     sig.get("dir_str", ""),
            "entry":       sig["entry"], "sl": sig["sl"], "tp": sig["tp"],
            "r_ratio":     sig.get("r_ratio"),
            "signal_type": sig.get("signal_type", "pullback"),
            "level":       verdict.get("level"),
            "threshold":   verdict.get("threshold"),
            "approved":    verdict.get("approved"),
            "confidence":  verdict.get("confidence"),
            "reason":      verdict.get("reason"),
            "veto":        verdict.get("veto"),
            "veto_code":   verdict.get("veto_code"),
            "error":       verdict.get("error"),
            "duration_s":  verdict.get("duration_s"),
            # Multi-Council Consensus (additive — gol/None cand e un singur consiliu)
            "consensus_confidence": verdict.get("consensus_confidence"),
            "n_councils":  verdict.get("n_councils"),
            "sources":     verdict.get("sources") or [],
            "councils":    verdict.get("councils") or [],
            "transcript":  verdict.get("transcript") or {},
        }
        os.makedirs(output_dir, exist_ok=True)
        path = os.path.join(output_dir, "ai_filter.jsonl")
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str,
                               separators=(",", ":")) + "\n")
    except Exception:
        pass
