# -*- coding: utf-8 -*-
"""
Teste pentru Filtrul AI Pre-Trade (ai_engine/trade_filter.py + integrarea in
live/signal_generator.py + api/ai_filter_log.py).

Rulare:
    python scripts/test_ai_filter.py               # unit tests (fara Ollama/MT5)
    python scripts/test_ai_filter.py --live        # + un consiliu REAL pe Ollama

Unit testele folosesc surse AI simulate (FakeRegistry) — zero dependinte externe.
"""

import io
import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from ai_engine import trade_filter as tf
from ai_engine.providers import ProviderError

PASS, FAIL = [], []


def check(name: str, cond: bool, extra: str = ""):
    (PASS if cond else FAIL).append(name)
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  {extra}" if extra else ""))


class _Log:
    """Logger minimal pentru teste."""
    def info(self, *a, **k): pass
    def warning(self, *a, **k): pass
    def debug(self, *a, **k): pass
    def error(self, *a, **k): pass


# ═════════════════════════════════════════════════════════════════════════════
# 1. Niveluri si praguri
# ═════════════════════════════════════════════════════════════════════════════

check("praguri: permissive=50", tf.FILTER_LEVELS["permissive"] == 50)
check("praguri: balanced=70",   tf.FILTER_LEVELS["balanced"] == 70)
check("praguri: strict=85",     tf.FILTER_LEVELS["strict"] == 85)
check("normalize: valid",       tf.normalize_level("strict") == "strict")
check("normalize: case+spatii", tf.normalize_level("  Balanced ") == "balanced")
check("normalize: invalid→default", tf.normalize_level("mega") == "balanced")
check("normalize: None→default",    tf.normalize_level(None) == "balanced")

# ═════════════════════════════════════════════════════════════════════════════
# 2. _verdict — regulile aplicate in cod
# ═════════════════════════════════════════════════════════════════════════════

def _verdict(head, risk, level="balanced"):
    v = tf.TradeFilter._verdict(head, risk)
    thr = tf.FILTER_LEVELS[tf.normalize_level(level)]
    # replicam gate-ul de prag exact ca evaluate(): _verdict da approve raw,
    # dar pragul e aplicat... — NU: pragul e aplicat in _verdict? Verificam.
    return v

# NOTA: pragul e responsabilitatea evaluate()? Verificam contractul real:
# _verdict primeste doar head+risk — pragul trebuie aplicat de apelant sau in
# _verdict? In implementare, evaluate() construieste base cu threshold si
# _verdict decide approved FARA prag... — testam intai comportamentul real.
_v = tf.TradeFilter._verdict({"approve": True, "confidence": 80, "reason": "ok"},
                             {"veto": False, "veto_code": None})
check("_verdict: approve+80 → approved", _v["approved"] is True and _v["confidence"] == 80)

_v = tf.TradeFilter._verdict({"approve": False, "confidence": 75, "reason": "bad structure"},
                             {"veto": False})
check("_verdict: head reject → rejected", _v["approved"] is False)

_v = tf.TradeFilter._verdict({"approve": True, "confidence": 95, "reason": "great"},
                             {"veto": True, "veto_code": "NEWS_IMMINENT"})
check("_verdict: veto valid bate head-ul", _v["approved"] is False and "VETO" in _v["reason"])

_v = tf.TradeFilter._verdict({"approve": True, "confidence": 80, "reason": "fine"},
                             {"veto": True, "veto_code": "MIXED_SIGNALS"})
check("_verdict: veto necalificat NU respinge",
      _v["approved"] is True and "prudenta" in _v["reason"].lower())

_v = tf.TradeFilter._verdict({"approve": "true", "confidence": "82", "reason": "str types"},
                             {"veto": "false"})
check("_verdict: tipuri string tolerate", _v["approved"] is True and _v["confidence"] == 82)

_v = tf.TradeFilter._verdict({"approve": True, "confidence": 250, "reason": "clamp"},
                             {"veto": False})
check("_verdict: confidence clamp la 100", _v["confidence"] == 100)

_v = tf.TradeFilter._verdict({"approve": True, "confidence": None, "reason": "none conf"},
                             {"veto": False})
check("_verdict: confidence None → 0", _v["confidence"] == 0)

# ═════════════════════════════════════════════════════════════════════════════
# 3. evaluate() cu registry simulat — praguri end-to-end
# ═════════════════════════════════════════════════════════════════════════════

SIG = {
    "signal_id": "S1-EURUSD-SIG0042", "symbol": "EURUSD", "direction": 1,
    "dir_str": "LONG", "entry": 1.0850, "sl": 1.0820, "tp": 1.0955,
    "r_ratio": 3.5, "n_optional": 2, "rsi": 55.0, "atr_pips": 8.2,
    "signal_type": "pullback",
}
SESSION_CFG = {"entry_tf": "M15", "trend_tf": "M30", "expire_bars": 4,
               "session_id": "S1-EURUSD", "session_key": "session1"}
BRIEFING = "MARKET BRIEFING — EURUSD @ 1.0845 (Wednesday, 14:00). Trend M30: UP. RSI 55."


class FakeRegistry:
    """Simuleaza ProviderRegistry.call_role cu raspunsuri canned per rol."""
    def __init__(self, head_conf=80, head_approve=True, veto=False, veto_code=None,
                 fail_role=None):
        self.head_conf, self.head_approve = head_conf, head_approve
        self.veto, self.veto_code = veto, veto_code
        self.fail_role = fail_role
        self.calls = []

    def call_role(self, role, assignments, system, user, required):
        self.calls.append(role)
        if role == self.fail_role:
            raise ProviderError("sursa simulata picata", kind="network")
        views = {
            "technical": {"alignment": "supports", "confidence": 75,
                          "reasoning": "Structure aligns with M30 trend."},
            "macro":     {"timing_quality": "good", "event_risk": "none",
                          "confidence": 70, "reasoning": "London session, no events."},
            "risk":      {"veto": self.veto, "veto_code": self.veto_code,
                          "concerns": [], "notes": "Within limits."},
            "head_trader": {"approve": self.head_approve, "confidence": self.head_conf,
                            "reason": "Desk consensus supports the signal."},
        }
        return views[role], {"provider": "fake", "latency_s": 0.01}


def _make_filter(registry) -> tf.TradeFilter:
    f = tf.TradeFilter()
    # ocolim _refresh (nu vrem load_config real + registry real in unit tests)
    f._refresh = lambda: None
    f._registry = registry
    f._cfg = {"role_assignments": {}}
    return f


# aprobat: conf 80 >= balanced 70
f = _make_filter(FakeRegistry(head_conf=80))
v = f.evaluate(SIG, BRIEFING, "balanced", SESSION_CFG, _Log())
check("evaluate: 80 @ balanced(70) → APROBAT", v["approved"] is True and v["error"] is None,
      f"conf={v['confidence']}")
check("evaluate: toate 4 rolurile consultate", len(v["transcript"]) == 4)
check("evaluate: threshold in verdict", v["threshold"] == 70 and v["level"] == "balanced")

# respins: conf 60 < balanced 70
f = _make_filter(FakeRegistry(head_conf=60))
v = f.evaluate(SIG, BRIEFING, "balanced", SESSION_CFG, _Log())
check("evaluate: 60 @ balanced(70) → RESPINS (sub prag)", v["approved"] is False,
      f"reason={v['reason'][:60]}")

# permisiv: conf 60 >= 50
f = _make_filter(FakeRegistry(head_conf=60))
v = f.evaluate(SIG, BRIEFING, "permissive", SESSION_CFG, _Log())
check("evaluate: 60 @ permissive(50) → APROBAT", v["approved"] is True)

# strict: 84 < 85 respins, 86 aprobat
f = _make_filter(FakeRegistry(head_conf=84))
v = f.evaluate(SIG, BRIEFING, "strict", SESSION_CFG, _Log())
check("evaluate: 84 @ strict(85) → RESPINS", v["approved"] is False)
f = _make_filter(FakeRegistry(head_conf=86))
v = f.evaluate(SIG, BRIEFING, "strict", SESSION_CFG, _Log())
check("evaluate: 86 @ strict(85) → APROBAT", v["approved"] is True)

# head reject
f = _make_filter(FakeRegistry(head_conf=88, head_approve=False))
v = f.evaluate(SIG, BRIEFING, "balanced", SESSION_CFG, _Log())
check("evaluate: head reject → RESPINS chiar cu conf mare", v["approved"] is False)

# veto valid
f = _make_filter(FakeRegistry(head_conf=90, veto=True, veto_code="WEEKEND_GAP"))
v = f.evaluate(SIG, BRIEFING, "balanced", SESSION_CFG, _Log())
check("evaluate: veto WEEKEND_GAP → RESPINS", v["approved"] is False and v["veto_code"] == "WEEKEND_GAP")

# veto necalificat
f = _make_filter(FakeRegistry(head_conf=80, veto=True, veto_code="I_AM_SCARED"))
v = f.evaluate(SIG, BRIEFING, "balanced", SESSION_CFG, _Log())
check("evaluate: veto necalificat → APROBAT (anti-paralizie)", v["approved"] is True)

# nivel invalid → default balanced
f = _make_filter(FakeRegistry(head_conf=75))
v = f.evaluate(SIG, BRIEFING, "SUPER_STRICT_9000", SESSION_CFG, _Log())
check("evaluate: nivel invalid → default balanced", v["level"] == "balanced" and v["approved"] is True)

# ═════════════════════════════════════════════════════════════════════════════
# 4. FAIL-OPEN — erori AI nu opresc niciodata botul
# ═════════════════════════════════════════════════════════════════════════════

f = _make_filter(FakeRegistry(fail_role="technical"))
v = f.evaluate(SIG, BRIEFING, "strict", SESSION_CFG, _Log())
check("fail-open: ProviderError → APROBAT + error setat",
      v["approved"] is True and v["error"] is not None and v["confidence"] is None)

class _BoomRegistry:
    def call_role(self, *a, **k):
        raise RuntimeError("crash neasteptat")
f = _make_filter(_BoomRegistry())
v = f.evaluate(SIG, BRIEFING, "balanced", SESSION_CFG, _Log())
check("fail-open: exceptie generica → APROBAT + error", v["approved"] is True and "crash" in v["error"])

# buget de timp: fortam TIME_BUDGET_S negativ → primul rol declanseaza fail-open
_old_budget = tf.TIME_BUDGET_S
tf.TIME_BUDGET_S = -1
f = _make_filter(FakeRegistry())
v = f.evaluate(SIG, BRIEFING, "balanced", SESSION_CFG, _Log())
tf.TIME_BUDGET_S = _old_budget
check("fail-open: buget de timp depasit → APROBAT + error 'buget'",
      v["approved"] is True and "buget" in (v["error"] or ""))

# eroare in _refresh (config corupt etc.) → fail-open
f = tf.TradeFilter()
f._refresh = lambda: (_ for _ in ()).throw(RuntimeError("config corupt"))
v = f.evaluate(SIG, BRIEFING, "balanced", SESSION_CFG, _Log())
check("fail-open: eroare la refresh config → APROBAT", v["approved"] is True)

# ═════════════════════════════════════════════════════════════════════════════
# 5. describe_trade + log_verdict + api.ai_filter_log
# ═════════════════════════════════════════════════════════════════════════════

desc = tf.describe_trade(SIG, SESSION_CFG)
check("describe_trade: campuri cheie",
      all(s in desc for s in ["EURUSD", "LONG", "1.085", "3.5R", "pullback", "M15+M30"]))

with tempfile.TemporaryDirectory() as td:
    verdict = {"level": "balanced", "threshold": 70, "approved": True,
               "confidence": 82, "reason": "ok", "veto": False, "veto_code": None,
               "error": None, "duration_s": 12.3,
               "transcript": {"technical": {"alignment": "supports"}}}
    tf.log_verdict(td, SIG, verdict)
    tf.log_verdict(td, {**SIG, "signal_id": "S1-EURUSD-SIG0043"},
                   {**verdict, "approved": False, "confidence": 40})
    path = os.path.join(td, "ai_filter.jsonl")
    lines = open(path, encoding="utf-8").read().strip().splitlines()
    check("log_verdict: 2 linii JSONL", len(lines) == 2)
    e0 = json.loads(lines[0])
    check("log_verdict: campuri complete",
          e0["sig_id"] == "S1-EURUSD-SIG0042" and e0["confidence"] == 82
          and e0["transcript"]["technical"]["alignment"] == "supports")

    # api.ai_filter_log citeste si construieste maparile (patch DATA_DIR-like base)
    from api import ai_filter_log as afl
    entries = afl._read_jsonl_cached(path)
    check("ai_filter_log: parseaza jsonl", len(entries) == 2 and entries[1]["approved"] is False)
    # cache identity la a doua citire
    check("ai_filter_log: cache pe mtime", afl._read_jsonl_cached(path) is entries)
    # prefix16: sig_id-ul complet are 18 caractere → cheia e primele 16
    sid = "S1-EURUSD-SIG0042"
    check("prefix16: cheia de join corecta", sid[:16] == "S1-EURUSD-SIG004"
          and len(sid[:16]) == 16)

# ═════════════════════════════════════════════════════════════════════════════
# 6. Integrarea in signal_generator
# ═════════════════════════════════════════════════════════════════════════════

from live import signal_generator as sg

# _ai_note — sufixe dinamice
check("_ai_note: fara filtru → gol", sg._ai_note({"entry": 1.0}) == "")
check("_ai_note: None → gol", sg._ai_note(None) == "")
note = sg._ai_note({"ai_filter": {"approved": True, "confidence": 82, "threshold": 70}})
check("_ai_note: aprobat cu scor", "82%" in note and "70%" in note and "aprobat" in note)
note = sg._ai_note({"ai_filter": {"approved": True, "confidence": None,
                                  "threshold": 70, "error": "ollama down"}})
check("_ai_note: fail-open → 'indisponibil'", "indisponibil" in note)
check("_ai_note: pending vechi (fara cheia ai_filter) → gol",
      sg._ai_note({"direction": 1, "entry": 1.1}) == "")

# _ai_pending_entry — rezumat fara transcript
pe = sg._ai_pending_entry({"approved": True, "confidence": 82, "threshold": 70,
                           "level": "balanced", "error": None,
                           "transcript": {"big": "data"}})
check("_ai_pending_entry: slim, fara transcript",
      pe["confidence"] == 82 and "transcript" not in pe)
check("_ai_pending_entry: None → None", sg._ai_pending_entry(None) is None)

# _html_esc
check("_html_esc", sg._html_esc("<b>a&b</b>") == "&lt;b&gt;a&amp;b&lt;/b&gt;")

# _ai_filter_check: dezactivat → None (niciun apel AI)
r = sg._ai_filter_check(SIG, {"ai_filter_enabled": False}, None, _Log())
check("_ai_filter_check: dezactivat → None", r is None)
r = sg._ai_filter_check(SIG, {}, None, _Log())
check("_ai_filter_check: lipsa cheie (sesiuni vechi) → None", r is None)

# _ai_filter_check: activat, cu TradeFilter stub → verdict + jsonl scris
with tempfile.TemporaryDirectory() as td:
    class _StubFilter:
        def evaluate(self, sig, briefing, level, session_cfg=None, log=None):
            return {"approved": False, "confidence": 41, "threshold": 70,
                    "level": level, "reason": "stub reject", "veto": False,
                    "veto_code": None, "error": None, "duration_s": 0.1,
                    "transcript": {}}
    _old = sg._AI_FILTER
    sg._AI_FILTER = _StubFilter()
    try:
        cfg = {"ai_filter_enabled": True, "ai_filter_level": "balanced",
               "output_dir": td, **SESSION_CFG}
        r = sg._ai_filter_check(SIG, cfg, None, _Log())   # src=None → briefing fallback
        check("_ai_filter_check: verdict stub returnat", r is not None and r["approved"] is False)
        jl = os.path.join(td, "ai_filter.jsonl")
        check("_ai_filter_check: jurnal jsonl scris", os.path.isfile(jl))
        entry = json.loads(open(jl, encoding="utf-8").readline())
        check("_ai_filter_check: jurnal contine verdictul", entry["confidence"] == 41
              and entry["approved"] is False)
    finally:
        sg._AI_FILTER = _old

# _apply_profile_overrides copiaza campurile ai_filter_*
with tempfile.TemporaryDirectory() as td:
    profile = {"name": "TestProfile", "sessions": [{
        "session_key": "sessionT", "ai_filter_enabled": True, "ai_filter_level": "strict",
    }]}
    with open(os.path.join(td, "active_profile_runtime.json"), "w", encoding="utf-8") as fh:
        json.dump(profile, fh)
    _old_dd = sg.DATA_DIR
    sg.DATA_DIR = td
    try:
        scfg = {"session_key": "sessionT"}
        strat_cfg = {"optional_criteria": {"rsi": {}}, "reward_ladder": {}}
        sg._apply_profile_overrides(scfg, strat_cfg, _Log())
        check("profil: ai_filter_enabled aplicat", scfg.get("ai_filter_enabled") is True)
        check("profil: ai_filter_level aplicat", scfg.get("ai_filter_level") == "strict")
        # sesiune fara campurile ai_* in profil → raman nesetate (default off)
        scfg2 = {"session_key": "sessionT"}
        profile["sessions"][0].pop("ai_filter_enabled")
        profile["sessions"][0].pop("ai_filter_level")
        with open(os.path.join(td, "active_profile_runtime.json"), "w", encoding="utf-8") as fh:
            json.dump(profile, fh)
        sg._apply_profile_overrides(scfg2, strat_cfg, _Log())
        check("profil: fara campuri ai_* → default off (backward compat)",
              "ai_filter_enabled" not in scfg2)
    finally:
        sg.DATA_DIR = _old_dd

# ai_reject NU e status inchis (nu intra in statistici)
from api.routers.sessions import _CLOSED_STATUSES as _CS_SESS
from api.routers.reports import _CLOSED_STATUSES as _CS_REP
check("ai_reject exclus din _CLOSED_STATUSES (sessions)", "ai_reject" not in _CS_SESS)
check("ai_reject exclus din _CLOSED_STATUSES (reports)", "ai_reject" not in _CS_REP)

# categorizarea notificarilor
from api.notifications import _categorize
check("categorize: respingere → ai", _categorize("⛔ Filtru AI: RESPINS — LONG EURUSD") == "ai")
check("categorize: ordin cu sufix AI ramane order",
      _categorize("Ordin plasat: LONG EURUSD ... Filtru AI: aprobat") == "order")

# ═════════════════════════════════════════════════════════════════════════════
# 7. Rutarea surselor: failover pe consiliul unic + fallback cand pinned pica
# ═════════════════════════════════════════════════════════════════════════════

from ai_engine.providers import ProviderRegistry


class _RoleProv:
    """Sursa falsa pentru ProviderRegistry REAL: raspunde per rol dupa chei."""
    def __init__(self, name, fail=None, head_conf=80, head_approve=True):
        self.name, self.fail = name, fail
        self.head_conf, self.head_approve = head_conf, head_approve
        self.calls = 0

    def chat_json(self, system, user, required, retries=2):
        self.calls += 1
        if self.fail:
            raise ProviderError(f"{self.name} picat", kind=self.fail)
        keys = set(required)
        if "alignment" in keys:
            return {"alignment": "supports", "confidence": 75, "reasoning": "ok"}
        if "timing_quality" in keys:
            return {"timing_quality": "good", "event_risk": "none", "confidence": 70,
                    "reasoning": "ok"}
        if "veto" in keys:
            return {"veto": False, "veto_code": None, "concerns": [], "notes": "n"}
        if "approve" in keys:
            return {"approve": self.head_approve, "confidence": self.head_conf,
                    "reason": f"desk {self.name}"}
        return {"assessment": "favorable", "confidence": 70, "reasoning": "q"}


def _real_reg(specs):
    """Registru REAL (cu failover) peste surse false. specs: {name: fail_kind|None}."""
    cfg = {n: {"enabled": True, "type": "ollama", "model": "x"} for n in specs}
    r = ProviderRegistry(cfg, {})
    for n, fail in specs.items():
        r._instances[n] = _RoleProv(n, fail=fail)
    return r


def _make_filter_real(registry):
    f = tf.TradeFilter()
    f._refresh = lambda: None
    f._registry = registry
    f._cfg = {"role_assignments": {}}
    return f


# consiliu UNIC cu sursa preferata picata → failover pe alta sursa → aprobat
reg = _real_reg({"groq": "network", "ollama": None})
f = _make_filter_real(reg)
v = f.evaluate(SIG, BRIEFING, "balanced",
               {"ai_filter_primary_source": "groq"}, _Log())
check("failover: sursa primara picata → consumat restul → ollama (nu fail-open)",
      v["approved"] is True and v["error"] is None and v["n_councils"] == 1,
      f"sources={v['sources']}")
check("failover: sursa reala folosita raportata (ollama)", v["sources"] == ["ollama"])

# consiliu UNIC cu sursa preferata sanatoasa → sursa aleasa e consumata prima
reg = _real_reg({"groq": None, "ollama": None})
f = _make_filter_real(reg)
v = f.evaluate(SIG, BRIEFING, "balanced",
               {"ai_filter_primary_source": "groq"}, _Log())
check("failover: sursa preferata sanatoasa → folosita ea",
      v["approved"] is True and v["sources"] == ["groq"]
      and reg._instances["ollama"].calls == 0)

# MULTI-council: TOATE sursele pinned pica → consiliul de rezerva cu failover
# (→ ollama) decide, NU fail-open
reg = _real_reg({"a": "network", "b": "network", "ollama": None})
f = _make_filter_real(reg)
v = f.evaluate(SIG, BRIEFING, "balanced",
               {"ai_filter_primary_source": "a", "ai_filter_secondary_source": "b"}, _Log())
check("fallback: toate consiliile pinned picate → consiliul de rezerva (ollama) decide",
      v["approved"] is True and v["error"] is None and v["n_councils"] == 1,
      f"sources={v['sources']} err={v['error']}")

# ... si abia cand pica si rezerva → fail-open (plasa finala)
reg = _real_reg({"a": "network", "b": "network", "ollama": "network"})
f = _make_filter_real(reg)
v = f.evaluate(SIG, BRIEFING, "balanced",
               {"ai_filter_primary_source": "a", "ai_filter_secondary_source": "b"}, _Log())
check("fallback: si rezerva picata → fail-open (trade permis + error)",
      v["approved"] is True and v["error"] is not None)

# _plan_councils: fara secondary → [primary]; cu secondary → surse distincte
pc = tf.TradeFilter._plan_councils({}, {}, None)
check("_plan_councils: default → [None] (distribuit pe roluri)", pc == [None])
pc = tf.TradeFilter._plan_councils({"ai_filter_primary_source": "groq"}, {}, None)
check("_plan_councils: doar primary → [groq]", pc == ["groq"])

# ═════════════════════════════════════════════════════════════════════════════
# 8. Mod STRICT (fail-closed) — AI indisponibil → ordinul NU se plaseaza
# ═════════════════════════════════════════════════════════════════════════════

_V_OK     = {"approved": True,  "confidence": 80, "error": None}
_V_FAIL   = {"approved": True,  "confidence": None, "error": "nicio sursa AI"}
_V_REJECT = {"approved": False, "confidence": 40, "error": None}

check("strict: OFF + fail-open → NU blocheaza (comportament vechi)",
      sg._ai_strict_blocked({}, _V_FAIL) is False)
check("strict: ON + verdict valid aprobat → NU blocheaza",
      sg._ai_strict_blocked({"ai_filter_strict": True}, _V_OK) is False)
check("strict: ON + AI indisponibil (fail-open) → BLOCHEAZA",
      sg._ai_strict_blocked({"ai_filter_strict": True}, _V_FAIL) is True)
check("strict: ON + respins normal → nu e treaba strict-ului (respins oricum)",
      sg._ai_strict_blocked({"ai_filter_strict": True}, _V_REJECT) is False)
check("strict: ON dar filtru dezactivat (verdict None) → NU blocheaza",
      sg._ai_strict_blocked({"ai_filter_strict": True}, None) is False)

# _ai_reject_cause — mesaj de respingere ne-inducand in eroare (incident AUDNZD S19:
# head approve=false, confidence 90, prag 85 → parea contradictie). consensus_confidence
# (increderea EFECTIVA) e sursa de adevar, nu `confidence` (convingerea head-ului in NU).
_c_headno = sg._ai_reject_cause(
    {"confidence": 90, "threshold": 85, "veto": False, "consensus_confidence": 0.0})
check("cauza: head NU (conf 90, consens 0) → NU pomeneste pragul, zice decizie NU",
      "NU" in _c_headno and "90%" in _c_headno and "prag" not in _c_headno.lower(), _c_headno)
check("cauza: incredere sub prag (consens 72) → compara cu pragul",
      "72%" in sg._ai_reject_cause({"confidence": 72, "threshold": 85,
                                    "consensus_confidence": 72.0, "veto": False})
      and "85%" in sg._ai_reject_cause({"confidence": 72, "threshold": 85,
                                        "consensus_confidence": 72.0, "veto": False}))
check("cauza: veto cu cod → mesaj de veto",
      "Veto" in sg._ai_reject_cause({"veto": True, "veto_code": "EXTREME_VOL",
                                     "consensus_confidence": 0.0, "confidence": 60, "threshold": 85}))
check("cauza: head NU fara confidence → mesaj generic, fara procent inselator",
      "%" not in sg._ai_reject_cause({"confidence": None, "threshold": 85,
                                      "consensus_confidence": 0.0, "veto": False}))

# profilele copiaza si ai_filter_strict in sesiunea live
with tempfile.TemporaryDirectory() as td:
    profile = {"name": "T", "sessions": [{
        "session_key": "sessionT", "ai_filter_enabled": True, "ai_filter_strict": True,
    }]}
    with open(os.path.join(td, "active_profile_runtime.json"), "w", encoding="utf-8") as fh:
        json.dump(profile, fh)
    _old_dd = sg.DATA_DIR
    sg.DATA_DIR = td
    try:
        scfg = {"session_key": "sessionT"}
        sg._apply_profile_overrides(scfg, {"optional_criteria": {"rsi": {}},
                                           "reward_ladder": {}}, _Log())
        check("profil: ai_filter_strict aplicat in sesiunea live",
              scfg.get("ai_filter_strict") is True)
    finally:
        sg.DATA_DIR = _old_dd

# ═════════════════════════════════════════════════════════════════════════════
# 9. Optional: consiliu REAL pe Ollama (--live)
# ═════════════════════════════════════════════════════════════════════════════

if "--live" in sys.argv:
    print("\n── Consiliu REAL pe sursele AI configurate (poate dura 30-120s) ──")
    t0 = time.time()
    real = tf.TradeFilter()
    v = real.evaluate(SIG, BRIEFING + "\nEMA 8/20/50 alignment: bullish | ATR percentile: 42%",
                      "balanced", SESSION_CFG, _Log())
    dur = time.time() - t0
    print(f"    verdict: approved={v['approved']} conf={v['confidence']} "
          f"veto={v['veto_code']} err={v['error']} in {dur:.0f}s")
    print(f"    reason: {v['reason'][:200]}")
    check("LIVE: evaluare completa fara crash", isinstance(v, dict) and "approved" in v)
    check("LIVE: confidence valid sau fail-open",
          v["error"] is not None or (isinstance(v["confidence"], int) and 0 <= v["confidence"] <= 100))
    check("LIVE: 4 roluri in transcript (sau eroare)",
          v["error"] is not None or len(v["transcript"]) == 4)

# ═════════════════════════════════════════════════════════════════════════════

print("\n" + "═" * 60)
print(f"REZULTAT: {len(PASS)} PASS / {len(FAIL)} FAIL din {len(PASS) + len(FAIL)}")
if FAIL:
    print("ESUATE:", FAIL)
    sys.exit(1)
print("TOATE TESTELE AU TRECUT ✓")
