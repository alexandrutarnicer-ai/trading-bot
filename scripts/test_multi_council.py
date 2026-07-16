# -*- coding: utf-8 -*-
"""
Teste pentru Multi-Council Consensus + rolurile AI suplimentare (Quant, Devil).

Acopera cerintele de validare:
  - consensus.combine (media efectiva + veto absolut) + resolve_sources
  - providers.call_role_pinned (fara failover)
  - scenarii cu 1 / 2 / 3 consilii
  - esec de consiliu (fault tolerance) + surse duplicate
  - orchestratorul motorului autonom (primar + revizori)
  - backward-compat: un consiliu == comportamentul de dinainte de feature
  - rolurile optionale se activeaza doar cand sunt cerute

Rulare:  python scripts/test_multi_council.py           (fara Ollama/MT5)

Foloseste surse AI simulate — zero dependinte externe.
"""

import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from ai_engine import consensus, trade_filter as tf, orchestrator
from ai_engine.consensus import CouncilOpinion, combine, resolve_sources
from ai_engine.providers import ProviderRegistry, ProviderError
from ai_engine.config import load_config

PASS, FAIL = [], []


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  {extra}" if extra else ""))


class _Log:
    def info(self, *a, **k): pass
    def warning(self, *a, **k): pass
    def error(self, *a, **k): pass
    def debug(self, *a, **k): pass


# ═════════════════════════════════════════════════════════════════════════════
# 1. consensus.combine — strategia (media efectiva + veto absolut)
# ═════════════════════════════════════════════════════════════════════════════

def _op(source, approved=True, confidence=80, hard_veto=None, error=None):
    return CouncilOpinion(source=source, approved=approved, confidence=confidence,
                          hard_veto=hard_veto, error=error)

# un singur consiliu = regula de dinainte de feature
v = combine([_op("a", True, 80)], 70)
check("combine: 1 consiliu aproba 80@70 → APROBAT", v.approved and v.consensus_confidence == 80)
v = combine([_op("a", True, 60)], 70)
check("combine: 1 consiliu 60@70 → RESPINS", not v.approved and v.consensus_confidence == 60)
v = combine([_op("a", False, 90)], 70)
check("combine: 1 consiliu respinge (effective=0) → RESPINS", not v.approved and v.consensus_confidence == 0)

# doua consilii — media
v = combine([_op("a", True, 80), _op("b", True, 60)], 70)
check("combine: 2 consilii 80+60=media 70@70 → APROBAT", v.approved and v.consensus_confidence == 70,
      f"mean={v.consensus_confidence}")
v = combine([_op("a", True, 80), _op("b", True, 50)], 70)
check("combine: 2 consilii media 65@70 → RESPINS", not v.approved and v.consensus_confidence == 65)

# dizidenta: un consiliu care respinge aduce 0 la medie
v = combine([_op("a", True, 90), _op("b", False, 88)], 70)
check("combine: dizidenta (90 + effective 0) media 45 → RESPINS", not v.approved and v.consensus_confidence == 45)

# trei consilii
v = combine([_op("a", True, 80), _op("b", True, 70), _op("c", True, 75)], 70)
check("combine: 3 consilii media 75@70 → APROBAT", v.approved and v.consensus_confidence == 75)
check("combine: n_participating/n_approving corecte", v.n_participating == 3 and v.n_approving == 3)

# veto absolut — orice consiliu cu veto hard respinge, indiferent de medie
v = combine([_op("a", True, 95), _op("b", True, 95, hard_veto="NEWS_IMMINENT")], 70)
check("combine: veto absolut bate media mare → RESPINS", not v.approved and v.veto_code == "NEWS_IMMINENT")

# fault tolerance: consiliile esuate nu se numara
v = combine([_op("a", True, 80), _op("b", error="picat", confidence=None)], 70)
check("combine: consiliu esuat ignorat, decide restul → APROBAT",
      v.approved and v.n_participating == 1 and v.consensus_confidence == 80)

# toate esuate → all_failed (apelantul decide fail-open/safe)
v = combine([_op("a", error="x", confidence=None), _op("b", error="y", confidence=None)], 70)
check("combine: toate esuate → all_failed", v.all_failed and not v.approved and v.n_participating == 0)

# per_council raportat pentru fiecare consiliu (vizibilitate)
v = combine([_op("a", True, 80), _op("b", True, 60)], 70)
check("combine: per_council are cate o intrare per consiliu", len(v.per_council) == 2
      and v.per_council[0]["effective"] == 80 and v.per_council[1]["effective"] == 60)

# ═════════════════════════════════════════════════════════════════════════════
# 2. resolve_sources — deduplicare + validare distincte
# ═════════════════════════════════════════════════════════════════════════════

s, d = resolve_sources("ollama", "claude", "gemini")
check("resolve: 3 distincte pastrate", s == ["ollama", "claude", "gemini"] and d == [])
s, d = resolve_sources("ollama", "claude", "ollama")
check("resolve: duplicat eliminat + raportat", s == ["ollama", "claude"] and d == ["ollama"])
s, d = resolve_sources("ollama", None, None)
check("resolve: None-uri ignorate", s == ["ollama"] and d == [])
s, d = resolve_sources(None, None, None)
check("resolve: toate None → gol", s == [] and d == [])

# ═════════════════════════════════════════════════════════════════════════════
# 3. providers.call_role_pinned — fara failover
# ═════════════════════════════════════════════════════════════════════════════

class _FakeProv:
    def __init__(self, name, fail=None, answer=None):
        self.name, self.fail = name, fail
        self.answer = answer or {"bias": "long", "confidence": 70}
        self.calls = 0
    def chat_json(self, system, user, required, retries=2):
        self.calls += 1
        if self.fail:
            raise ProviderError(f"{self.name} fail", kind=self.fail)
        return dict(self.answer)


def _reg(specs):
    cfg = {n: {"enabled": True, "type": "ollama", "model": "x"} for n in specs}
    r = ProviderRegistry(cfg, {})
    for n in specs:
        r._instances[n] = _FakeProv(n, fail=specs[n])
    return r

r = _reg({"gemini": None, "ollama": None})
obj, meta = r.call_role_pinned("gemini", "s", "u", ["bias"])
check("call_role_pinned: ruleaza EXACT sursa ceruta", meta["provider"] == "gemini" and meta.get("pinned"))
check("call_role_pinned: NU face failover pe alta sursa", r._instances["ollama"].calls == 0)

r = _reg({"gemini": "network", "ollama": None})
try:
    r.call_role_pinned("gemini", "s", "u", ["bias"])
    check("call_role_pinned: sursa picata ridica ProviderError", False)
except ProviderError:
    check("call_role_pinned: sursa picata ridica ProviderError (fara failover)", True)
    check("call_role_pinned: nu a atins ollama", r._instances["ollama"].calls == 0)

try:
    r.call_role_pinned("inexistent", "s", "u", ["bias"])
    check("call_role_pinned: sursa necunoscuta ridica", False)
except ProviderError:
    check("call_role_pinned: sursa necunoscuta ridica ProviderError", True)

check("usable_sources: listeaza surse sanatoase", set(_reg({"a": None, "b": None}).usable_sources()) == {"a", "b"})

# ═════════════════════════════════════════════════════════════════════════════
# 4. Registru fals multi-sursa (dispatch pe cheile 'required')
# ═════════════════════════════════════════════════════════════════════════════

def _role_view(required, cfg, source):
    keys = set(required)
    if "alignment" in keys:                         # technical (review)
        return {"alignment": "supports", "confidence": 75, "reasoning": "ok"}
    if "bias" in keys and "event_risk" in keys:     # macro (autonom)
        return {"bias": "long", "confidence": 68, "event_risk": "none", "reasoning": "ok"}
    if "bias" in keys:                              # technical (autonom)
        return {"bias": "long", "confidence": 72, "reasoning": "ok"}
    if "timing_quality" in keys:                    # macro (review)
        return {"timing_quality": "good", "event_risk": "none", "confidence": 70, "reasoning": "ok"}
    if "assessment" in keys:                        # quant
        return {"assessment": "favorable", "confidence": 72, "est_win_prob": 55, "reasoning": "ev+"}
    if "strongest_objection" in keys:               # devil's advocate
        return {"strongest_objection": "x", "failure_mode": "y", "severity": "low", "reasoning": "z"}
    if "max_risk_pct" in keys:                       # risk (autonom)
        return {"veto": cfg.get("veto", False), "veto_code": cfg.get("veto_code"),
                "max_risk_pct": 0.005, "notes": "n"}
    if "veto" in keys:                              # risk (review)
        return {"veto": cfg.get("veto", False), "veto_code": cfg.get("veto_code"),
                "concerns": [], "notes": "n"}
    if "action" in keys:                            # head (autonom) — produce trade
        return {"action": cfg.get("action", "OPEN_LONG"), "order_type": "stop",
                "entry": 1.0860, "sl": 1.0830, "tp": 1.0950, "risk_pct": 0.005,
                "confidence": cfg.get("conf", 80), "rationale": f"primary {source}"}
    if "approve" in keys:                           # head (review)
        return {"approve": cfg.get("approve", True), "confidence": cfg.get("conf", 80),
                "reason": f"desk {source}"}
    return {}


class MultiFakeRegistry:
    DEFAULT = "ollama"
    def __init__(self, sources):        # {name: {conf, approve, veto, veto_code, action, fail}}
        self.sources = sources
        self.calls = []
    def call_role(self, role, assignments, system, user, required):
        src = (assignments or {}).get("head_trader") or self.DEFAULT
        return self._answer(src, required)
    def call_role_pinned(self, source, system, user, required):
        return self._answer(source, required)
    def _answer(self, source, required):
        cfg = self.sources.get(source)
        if cfg is None:
            raise ProviderError(f"{source} necunoscut", kind="network")
        if cfg.get("fail"):
            raise ProviderError(f"{source} picat", kind=cfg.get("fail_kind", "network"))
        self.calls.append((source, tuple(required)))
        return _role_view(required, cfg, source), {"provider": source, "latency_s": 0.01}


def _make_filter(registry, cfg=None):
    f = tf.TradeFilter()
    f._refresh = lambda: None
    f._registry = registry
    f._cfg = cfg or {"role_assignments": {}}
    return f


SIG = {"signal_id": "S1-EURUSD-SIG0001", "symbol": "EURUSD", "direction": 1,
       "dir_str": "LONG", "entry": 1.0850, "sl": 1.0820, "tp": 1.0955,
       "r_ratio": 3.5, "n_optional": 2, "rsi": 55.0, "atr_pips": 8.2,
       "signal_type": "pullback"}
BRIEF = "MARKET BRIEFING EURUSD @ 1.0845. Trend M30 UP. RSI 55."


# ═════════════════════════════════════════════════════════════════════════════
# 5. evaluate — 1 / 2 / 3 consilii end-to-end
# ═════════════════════════════════════════════════════════════════════════════

# UN consiliu (fara secondary/tertiary) → distribuit pe roluri, comportament identic
reg = MultiFakeRegistry({"ollama": {"conf": 80, "approve": True}})
f = _make_filter(reg)
v = f.evaluate(SIG, BRIEF, "balanced", {}, _Log())
check("1 consiliu: 80@70 APROBAT + n_councils=1", v["approved"] and v["n_councils"] == 1)
check("1 consiliu: confidence = head (backward compat)", v["confidence"] == 80)
check("1 consiliu: consensus prezent, sources=[ollama-ish]", v["consensus"] is not None and len(v["sources"]) == 1)

# DOUA consilii, ambele mari → APROBAT (media)
reg = MultiFakeRegistry({"ollama": {"conf": 80, "approve": True},
                         "claude": {"conf": 70, "approve": True}})
scfg = {"ai_filter_primary_source": "ollama", "ai_filter_secondary_source": "claude"}
f = _make_filter(reg)
v = f.evaluate(SIG, BRIEF, "balanced", scfg, _Log())
check("2 consilii: media 75@70 → APROBAT", v["approved"] and v["confidence"] == 75, f"conf={v['confidence']}")
check("2 consilii: n_councils=2 + 2 surse", v["n_councils"] == 2 and len(v["councils"]) == 2)
check("2 consilii: surse distincte in verdict", set(v["sources"]) == {"ollama", "claude"})

# DOUA consilii, unul respinge → media sub prag → RESPINS
reg = MultiFakeRegistry({"ollama": {"conf": 90, "approve": True},
                         "claude": {"conf": 30, "approve": False}})
f = _make_filter(reg)
v = f.evaluate(SIG, BRIEF, "balanced", scfg, _Log())
check("2 consilii: unul respinge → media 45 → RESPINS", not v["approved"], f"conf={v['confidence']}")

# TREI consilii
reg = MultiFakeRegistry({"ollama": {"conf": 80, "approve": True},
                         "claude": {"conf": 74, "approve": True},
                         "gemini": {"conf": 71, "approve": True}})
scfg3 = {"ai_filter_primary_source": "ollama", "ai_filter_secondary_source": "claude",
         "ai_filter_tertiary_source": "gemini"}
f = _make_filter(reg)
v = f.evaluate(SIG, BRIEF, "balanced", scfg3, _Log())
check("3 consilii: media 75@70 → APROBAT", v["approved"] and v["confidence"] == 75)
check("3 consilii: n_councils=3", v["n_councils"] == 3 and len(v["sources"]) == 3)

# ═════════════════════════════════════════════════════════════════════════════
# 6. Fault tolerance + duplicate + veto in multi-council
# ═════════════════════════════════════════════════════════════════════════════

# un consiliu optional pica → continua cu restul (nu blocheaza trading-ul)
reg = MultiFakeRegistry({"ollama": {"conf": 80, "approve": True},
                         "claude": {"fail": True}})
f = _make_filter(reg)
v = f.evaluate(SIG, BRIEF, "balanced", scfg, _Log())
check("fault: consiliu secundar picat → decide primarul (APROBAT)",
      v["approved"] and v["n_councils"] == 1 and v["error"] is None)

# TOATE consiliile pica → fail-open (trade permis)
reg = MultiFakeRegistry({"ollama": {"fail": True}, "claude": {"fail": True}})
f = _make_filter(reg)
v = f.evaluate(SIG, BRIEF, "balanced", scfg, _Log())
check("fault: toate consiliile picate → fail-open (APROBAT + error)",
      v["approved"] and v["error"] is not None and v["confidence"] is None)

# surse duplicate configurate → deduplicare (nu se ruleaza aceeasi sursa de doua ori)
reg = MultiFakeRegistry({"ollama": {"conf": 80, "approve": True}})
dup = {"ai_filter_primary_source": "ollama", "ai_filter_secondary_source": "ollama"}
f = _make_filter(reg)
v = f.evaluate(SIG, BRIEF, "balanced", dup, _Log())
check("duplicat: aceeasi sursa de doua ori → un singur consiliu", v["n_councils"] == 1)

# veto valid de la un consiliu → RESPINS chiar cu media mare
reg = MultiFakeRegistry({"ollama": {"conf": 95, "approve": True},
                         "claude": {"conf": 95, "approve": True, "veto": True,
                                    "veto_code": "WEEKEND_GAP"}})
f = _make_filter(reg)
v = f.evaluate(SIG, BRIEF, "balanced", scfg, _Log())
check("veto: un consiliu veta WEEKEND_GAP → RESPINS", not v["approved"] and v["veto_code"] == "WEEKEND_GAP")

# ═════════════════════════════════════════════════════════════════════════════
# 7. Roluri optionale (Quant + Devil) — activate doar la cerere
# ═════════════════════════════════════════════════════════════════════════════

reg = MultiFakeRegistry({"ollama": {"conf": 80, "approve": True}})
f = _make_filter(reg)
v = f.evaluate(SIG, BRIEF, "balanced", {}, _Log())
check("roluri: default → doar 4 roluri in transcript", len(v["transcript"]) == 4)

f = _make_filter(reg)
v = f.evaluate(SIG, BRIEF, "balanced",
               {"ai_role_quant_enabled": True, "ai_role_devils_advocate_enabled": True}, _Log())
check("roluri: activate → 6 roluri (quant + devils_advocate adaugate)",
      len(v["transcript"]) == 6 and "quant" in v["transcript"] and "devils_advocate" in v["transcript"])

# ═════════════════════════════════════════════════════════════════════════════
# 8. Orchestratorul motorului autonom (primar + revizori)
# ═════════════════════════════════════════════════════════════════════════════

CFG = load_config()
# Izolare de config-ul utilizatorului: role_assignments din UI (ex: head_trader →
# gemini) ar ruta rolurile fake-registry-ului spre surse pe care nu le cunoaste →
# WAIT fals. Testele de aici verifica MECANICA orchestratorului, nu rutarea userului.
CFG["role_assignments"] = {}
SNAP = {"symbol": "EURUSD", "price": 1.0855, "atr": 0.0009}
DESK = {"open_positions": 0, "daily_r": 0.0, "open_pos_desc": "none", "trigger": "test"}

# fara surse secundare → un singur convene (backward compat: fara strat de consens)
cfg = dict(CFG); cfg["council_secondary_source"] = None; cfg["council_tertiary_source"] = None
reg = MultiFakeRegistry({"ollama": {"conf": 80, "action": "OPEN_LONG"}})
dec, bundle, dur = orchestrator.decide(reg, "EURUSD", SNAP, BRIEF, DESK, cfg)
check("orchestrator: fara revizori → OPEN + fara consens", dec["action"] == "OPEN_LONG"
      and bundle["consensus"] is None)

# primar OPEN + revizor care aproba puternic → consens APROBA, ramane OPEN
cfg = dict(CFG); cfg["council_primary_source"] = "ollama"
cfg["council_secondary_source"] = "claude"; cfg["council_tertiary_source"] = None
cfg["consensus_threshold"] = 70
reg = MultiFakeRegistry({"ollama": {"conf": 85, "action": "OPEN_LONG"},
                         "claude": {"conf": 80, "approve": True}})
dec, bundle, dur = orchestrator.decide(reg, "EURUSD", SNAP, BRIEF, DESK, cfg)
check("orchestrator: primar+revizor de acord → OPEN executabil",
      dec["action"] == "OPEN_LONG" and bundle["consensus"]["approved"], f"{dec['rationale'][:60]}")
check("orchestrator: consensul + revizorii sunt in bundle",
      bundle["consensus"]["n_participating"] == 2 and len(bundle["reviewers"]) == 1)

# primar OPEN dar revizor respinge tare → consens sub prag → WAIT
reg = MultiFakeRegistry({"ollama": {"conf": 85, "action": "OPEN_LONG"},
                         "claude": {"conf": 20, "approve": False}})
dec, bundle, dur = orchestrator.decide(reg, "EURUSD", SNAP, BRIEF, DESK, cfg)
check("orchestrator: revizor respinge → consens sub prag → WAIT",
      dec["action"] == "WAIT" and not bundle["consensus"]["approved"])

# revizor cu veto valid → WAIT indiferent de increderi
reg = MultiFakeRegistry({"ollama": {"conf": 90, "action": "OPEN_LONG"},
                         "claude": {"conf": 90, "approve": True, "veto": True,
                                    "veto_code": "NEWS_IMMINENT"}})
dec, bundle, dur = orchestrator.decide(reg, "EURUSD", SNAP, BRIEF, DESK, cfg)
check("orchestrator: veto revizor → WAIT", dec["action"] == "WAIT"
      and bundle["consensus"]["veto_code"] == "NEWS_IMMINENT")

# revizorii pica → decide singur primarul (nu blocam din cauza esecului lor)
reg = MultiFakeRegistry({"ollama": {"conf": 85, "action": "OPEN_LONG"},
                         "claude": {"fail": True}})
dec, bundle, dur = orchestrator.decide(reg, "EURUSD", SNAP, BRIEF, DESK, cfg)
check("orchestrator: revizori indisponibili → primarul decide (OPEN)",
      dec["action"] == "OPEN_LONG" and "revizori indisponibili" in dec["rationale"])

# primarul face WAIT → nu se mai cheama revizorii
reg = MultiFakeRegistry({"ollama": {"conf": 40, "action": "WAIT"},
                         "claude": {"conf": 80, "approve": True}})
dec, bundle, dur = orchestrator.decide(reg, "EURUSD", SNAP, BRIEF, DESK, cfg)
check("orchestrator: primar WAIT → fara revizuire", dec["action"] == "WAIT"
      and bundle["consensus"] is None)

# ═════════════════════════════════════════════════════════════════════════════
# 9. Media membrilor consiliului + gate pe pragul de consens ("bara" din UI)
# ═════════════════════════════════════════════════════════════════════════════

from ai_engine import council as _council

# council_confidence = media rolurilor cu confidence (technical/macro/[quant]/head)
avg = _council.council_confidence({"technical": {"confidence": 72},
                                   "macro": {"confidence": 68},
                                   "head_trader": {"confidence": 80}})
check("council_confidence: media membrilor (72+68+80)/3 → 73", avg == 73, f"avg={avg}")
avg = _council.council_confidence({"technical": {"confidence": 72},
                                   "macro": {"confidence": 68},
                                   "quant": {"confidence": 60},
                                   "head_trader": {"confidence": 80}})
check("council_confidence: cu quant (72+68+60+80)/4 → 70", avg == 70, f"avg={avg}")
check("council_confidence: transcript gol → None", _council.council_confidence({}) is None)
check("council_confidence: valori string tolerate",
      _council.council_confidence({"technical": {"confidence": "80"},
                                   "head_trader": {"confidence": 60}}) == 70)
check("council_confidence: risk/devil (fara confidence) ignorati",
      _council.council_confidence({"risk": {"veto": False},
                                   "devils_advocate": {"severity": "low"},
                                   "head_trader": {"confidence": 90}}) == 90)

# convene: decizia poarta MEDIA membrilor, nu doar head-ul (fake: tech 72, macro 68)
cfg = dict(CFG); cfg["council_secondary_source"] = None; cfg["council_tertiary_source"] = None
reg = MultiFakeRegistry({"ollama": {"conf": 80, "action": "OPEN_LONG"}})
dec, bundle, dur = orchestrator.decide(reg, "EURUSD", SNAP, BRIEF, DESK, cfg)
check("media: decizia OPEN poarta media membrilor (73), nu head-ul (80)",
      dec["confidence"] == 73 and dec.get("head_confidence") == 80,
      f"conf={dec['confidence']} head={dec.get('head_confidence')}")

# gate consiliu unic: head 55 → media (72+68+55)/3 = 65 < prag 70 → WAIT
reg = MultiFakeRegistry({"ollama": {"conf": 55, "action": "OPEN_LONG"}})
dec, bundle, dur = orchestrator.decide(reg, "EURUSD", SNAP, BRIEF, DESK, cfg)
check("gate: consiliu unic sub prag (media 65 < 70) → WAIT, ordin blocat",
      dec["action"] == "WAIT" and "Sub pragul" in dec["rationale"],
      f"conf={dec['confidence']}")

# gate: prag configurabil — acelasi consiliu trece la prag 60
cfg_low = dict(cfg); cfg_low["consensus_threshold"] = 60
dec, bundle, dur = orchestrator.decide(reg, "EURUSD", SNAP, BRIEF, DESK, cfg_low)
check("gate: acelasi consiliu (media 65) la prag 60 → OPEN", dec["action"] == "OPEN_LONG")

# gate si cand revizorii pica: primar sub prag → WAIT (nu se strecoara pe fallback)
cfg_m = dict(CFG); cfg_m["council_primary_source"] = "ollama"
cfg_m["council_secondary_source"] = "claude"; cfg_m["consensus_threshold"] = 70
reg = MultiFakeRegistry({"ollama": {"conf": 55, "action": "OPEN_LONG"},
                         "claude": {"fail": True}})
dec, bundle, dur = orchestrator.decide(reg, "EURUSD", SNAP, BRIEF, DESK, cfg_m)
check("gate: revizori picati + primar sub prag → WAIT",
      dec["action"] == "WAIT" and "Sub pragul" in dec["rationale"])

# ═════════════════════════════════════════════════════════════════════════════

print("\n" + "═" * 60)
print(f"REZULTAT: {len(PASS)} PASS / {len(FAIL)} FAIL din {len(PASS) + len(FAIL)}")
if FAIL:
    print("ESUATE:", FAIL)
    sys.exit(1)
print("TOATE TESTELE AU TRECUT ✓")
