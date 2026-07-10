"""
ai_engine.selftest — verificari de integritate fara MT5.

Ruleaza:  python -m ai_engine.selftest

Acopera:
  1. Ledger: schema + round-trip decizie → outcome → scorecard
  2. Triggers: heartbeat, regime flip, cooldown
  3. Rails: validate_decision respinge geometrie proasta, RR mic, SL departe
  4. Council LIVE pe Ollama: briefing sintetic → decizie JSON valida
     (testul real ca modelul local poate juca rolurile)
"""

from __future__ import annotations

import os
import tempfile

from ai_engine.config import load_config
from ai_engine.ledger import Ledger
from ai_engine import triggers, council
from ai_engine.executor import validate_decision
from ai_engine.providers import (ProviderError, ProviderRegistry, BaseProvider,
                                 make_provider)


def _assert(cond, msg):
    print(f"  {'OK ' if cond else 'FAIL'} — {msg}")
    if not cond:
        raise AssertionError(msg)


def _fake_snapshot(**over) -> dict:
    s = {
        "symbol": "EURUSD", "bar_time": "2026-07-08 12:00:00", "price": 1.0850,
        "trend_m30": 1, "trend_d1": 1, "adx_d1_gt25": 1, "weekly_up": 1,
        "rsi": 55.0, "ema_align": "bullish", "atr": 0.0009, "atr_pctile": 40.0,
        "swing_highs": [1.0870, 1.0885, 1.0900], "swing_lows": [1.0800, 1.0815, 1.0830],
        "high_20": 1.0880, "low_20": 1.0820,
        "ret_1h_pct": 0.05, "ret_4h_pct": 0.2, "ret_1d_pct": 0.4,
        "weekday": 2, "hour": 12, "news": [],
    }
    s.update(over)
    return s


def test_ledger():
    print("[1] ledger round-trip")
    path = os.path.join(tempfile.mkdtemp(), "test_ledger.db")
    led = Ledger(path)
    sid = led.add_snapshot("EURUSD", {"price": 1.085})
    cid = led.add_council("EURUSD", "heartbeat", sid, {"technical": {"bias": "long"}}, 12.3)
    did = led.add_decision("EURUSD", cid, {
        "action": "OPEN_LONG", "order_type": "stop", "entry": 1.086, "sl": 1.083,
        "tp": 1.092, "risk_pct": 0.005, "confidence": 70, "rationale": "test"},
        "placed", "test", ticket=12345)
    _assert(len(led.open_decisions()) == 1, "decizia plasata apare ca deschisa")
    led.add_outcome(did, "EURUSD", "TP", 1.092, 2.0, 10.0)
    _assert(len(led.open_decisions()) == 0, "outcome inchide decizia")
    sc = led.scorecard()
    _assert(sc["closed_trades"] == 1 and sc["total_R"] == 2.0, f"scorecard corect: {sc}")
    _assert(led.last_council_ts("EURUSD") is not None, "last_council_ts")
    led.close()


def test_triggers(cfg):
    print("[2] triggers")
    s1 = _fake_snapshot()
    _assert(triggers.evaluate(s1, None, None, False, cfg) == "heartbeat",
            "primul contact -> heartbeat")
    s2 = _fake_snapshot(trend_m30=-1)
    t = triggers.evaluate(s2, s1, None, False, cfg)
    _assert(t is not None and t.startswith("regime_flip"), f"flip M30 -> {t}")
    from datetime import datetime
    recent = datetime.now().isoformat(timespec="seconds")
    _assert(triggers.evaluate(s1, s1, recent, False, cfg) is None,
            "cooldown blocheaza consiliu imediat dupa altul")
    s3 = _fake_snapshot(news=[{"title": "NFP", "currency": "USD", "impact": "High",
                               "in_min": 30, "forecast": "", "actual": ""}])
    _assert(triggers.evaluate(s3, s1, None, False, cfg).startswith("news_window"),
            "stire High in 30min -> news_window")


def test_rails(cfg):
    print("[3] rails executor.validate_decision")
    snap = _fake_snapshot()
    good = {"action": "OPEN_LONG", "order_type": "stop", "entry": 1.0862,
            "sl": 1.0832, "tp": 1.0922, "risk_pct": 0.005}
    _assert(validate_decision(good, snap, cfg, 0, 0.0) is None, "decizie valida trece")
    bad_geo = dict(good, sl=1.0900)
    _assert(validate_decision(bad_geo, snap, cfg, 0, 0.0) is not None,
            "SL peste entry la LONG -> respins")
    bad_rr = dict(good, tp=1.0870)
    _assert(validate_decision(bad_rr, snap, cfg, 0, 0.0) is not None,
            "RR sub minim -> respins")
    far_sl = dict(good, sl=1.0700)
    _assert(validate_decision(far_sl, snap, cfg, 0, 0.0) is not None,
            "SL la >5xATR -> respins")
    _assert(validate_decision(good, snap, cfg, cfg["max_open_positions"], 0.0) is not None,
            "max pozitii -> respins")
    _assert(validate_decision(good, snap, cfg, 0, -cfg["max_daily_loss_R"]) is not None,
            "stop zilnic -> respins")
    bad_stop = dict(good, entry=1.0840)
    _assert(validate_decision(bad_stop, snap, cfg, 0, 0.0) is not None,
            "BUY_STOP sub pret -> respins")


class _FakeProvider(BaseProvider):
    """Sursa falsa pentru testele de failover — raspunde sau esueaza la comanda."""
    def __init__(self, name, fail_kind=None, answer=None):
        self.name, self.fail_kind = name, fail_kind
        self.answer, self.calls = answer or {"bias": "long", "confidence": 70}, 0

    def chat_json(self, system, user, required_keys, retries=2):
        self.calls += 1
        if self.fail_kind:
            raise ProviderError(f"{self.name}: fail simulat", kind=self.fail_kind)
        return dict(self.answer)


def _fake_registry(specs: dict) -> ProviderRegistry:
    """Registru cu surse false: specs = {nume: fail_kind|None}."""
    cfg = {n: {"enabled": True, "type": "ollama", "model": "x"} for n in specs}
    reg = ProviderRegistry(cfg, {})
    for n, kind in specs.items():
        reg._instances[n] = _FakeProvider(n, fail_kind=kind)
    return reg


def test_failover():
    print("[4] failover intre surse (mock)")
    # 1. sursa asignata cade cu quota → ruleaza pe default (ollama)
    reg = _fake_registry({"gemini": "quota", "ollama": None})
    obj, meta = reg.call_role("technical", {"technical": "gemini"}, "s", "u", ["bias"])
    _assert(meta["provider"] == "ollama" and meta["fallback_from"] == "gemini",
            f"quota pe gemini -> fallback pe ollama ({meta})")
    _assert(reg.health["gemini"]["status"] == "paused"
            and reg.health["gemini"]["retry_at"] > 0,
            "gemini marcat in pauza cu retry_at setat")
    # 2. cat timp e in pauza, nu mai e apelat deloc
    calls_before = reg._instances["gemini"].calls
    reg.call_role("technical", {"technical": "gemini"}, "s", "u", ["bias"])
    _assert(reg._instances["gemini"].calls == calls_before,
            "sursa in pauza e sarita (nu se mai apeleaza)")
    # 3. revenire lazy: expira pauza → sursa e incercata din nou si isi revine
    reg.health["gemini"]["retry_at"] = 0
    reg._instances["gemini"].fail_kind = None
    obj, meta = reg.call_role("technical", {"technical": "gemini"}, "s", "u", ["bias"])
    _assert(meta["provider"] == "gemini" and reg.health["gemini"]["status"] == "healthy",
            "dupa expirarea pauzei sursa revine automat pe rolul ei")
    # 4. cheie invalida → disabled_auth, fara auto-retry nici dupa timp
    reg2 = _fake_registry({"claude": "auth", "ollama": None})
    _, meta = reg2.call_role("risk", {"risk": "claude"}, "s", "u", ["bias"])
    _assert(reg2.health["claude"]["status"] == "disabled_auth",
            "401 -> sursa dezactivata (necesita interventie umana)")
    reg2.health["claude"]["retry_at"] = 0
    calls = reg2._instances["claude"].calls
    reg2.call_role("risk", {"risk": "claude"}, "s", "u", ["bias"])
    _assert(reg2._instances["claude"].calls == calls,
            "disabled_auth NU se reincearca automat")
    # 5. toate sursele picate → ProviderError (consiliul va decide WAIT)
    reg3 = _fake_registry({"ollama": "network"})
    try:
        reg3.call_role("macro", {"macro": "ollama"}, "s", "u", ["bias"])
        _assert(False, "toate picate ar fi trebuit sa ridice ProviderError")
    except ProviderError:
        _assert(True, "toate sursele picate -> ProviderError -> WAIT (fail-safe)")
    # 6. consiliu complet pe registru mixt: risk pe sursa cazuta → fallback, decizie valida
    reg4 = _fake_registry({"claude": "rate_limit", "ollama": None})
    reg4._instances["ollama"].answer = {
        "bias": "neutral", "confidence": 50, "reasoning": "t", "event_risk": "low",
        "veto": True, "max_risk_pct": 0.005, "notes": "n",
        "action": "WAIT", "rationale": "test"}
    cfg_mix = load_config()
    cfg_mix["role_assignments"] = {"technical": "ollama", "macro": "ollama",
                                   "risk": "claude", "head_trader": "ollama"}
    decision, transcript, _ = council.convene(reg4, "briefing",
                                              {"open_positions": 0, "daily_r": 0.0,
                                               "open_pos_desc": "none"}, cfg_mix)
    _assert(decision["action"] == "WAIT" and
            transcript["risk"].get("_fallback_from") == "claude",
            "consiliu mixt: rolul risk a cazut pe fallback si e marcat in transcript")


def test_veto_semantics(cfg):
    print("[5] semantica veto (cod-enforced, anti-paralizie)")
    head_open = {"action": "OPEN_LONG", "order_type": "stop", "entry": 1.086,
                 "sl": 1.083, "tp": 1.092, "risk_pct": 0.005,
                 "confidence": 70, "rationale": "setup valid"}
    # 1. veto cu cod VALID -> WAIT (blocaj legitim)
    d = council._sanitize(dict(head_open),
                          {"veto": True, "veto_code": "NEWS_IMMINENT",
                           "max_risk_pct": 0.005}, cfg)
    _assert(d["action"] == "WAIT" and "NEWS_IMMINENT" in d["rationale"],
            "veto cu cod valid -> WAIT")
    # 2. veto FARA cod (prudenta generica) -> trade-ul trece cu risc minim
    d = council._sanitize(dict(head_open),
                          {"veto": True, "veto_code": None,
                           "max_risk_pct": 0.005}, cfg)
    _assert(d["action"] == "OPEN_LONG" and d["risk_pct"] == council.MIN_RISK_PCT,
            f"veto necalificat -> OPEN cu risc minim ({d['risk_pct']})")
    # 3. veto cu cod inventat -> tot prudenta, nu blocaj
    d = council._sanitize(dict(head_open),
                          {"veto": True, "veto_code": "RSI_NEUTRAL",
                           "max_risk_pct": 0.01}, cfg)
    _assert(d["action"] == "OPEN_LONG", "cod de veto inventat -> nu blocheaza")
    # 4. veto ca string 'false' -> nu e veto deloc (robustete parsing)
    d = council._sanitize(dict(head_open),
                          {"veto": "false", "veto_code": None,
                           "max_risk_pct": 0.005}, cfg)
    _assert(d["action"] == "OPEN_LONG" and d["risk_pct"] == 0.005,
            "veto='false' (string) -> nu veteaza, risc normal")


def test_tp_repair(cfg):
    print("[6] reparare geometrie TP (RR sub minim -> target R)")
    from ai_engine import executor
    # Cazul REAL #32 XRPUSD: entry 1.0997, sl 1.0961 (risk 0.0036), tp 1.1009
    # (reward 0.0012) -> RR 0.33, respins de executor. Dupa reparare trebuie sa treaca.
    head = {"action": "OPEN_LONG", "order_type": "stop", "entry": 1.0997,
            "sl": 1.0961, "tp": 1.1009, "risk_pct": 0.005, "confidence": 72,
            "rationale": "breakout"}
    d = council._sanitize(dict(head), {"veto": False, "max_risk_pct": 0.005}, cfg)
    risk_dist = abs(d["entry"] - d["sl"])
    new_rr = (d["tp"] - d["entry"]) / risk_dist
    _assert(abs(new_rr - cfg["target_rr"]) < 1e-6,
            f"TP reparat la {cfg['target_rr']}R (RR nou = {new_rr:.2f})")
    _assert("recalculat" in d["rationale"], "reparatia e notata in rationale")
    # acum trece de rail-ul din executor (care respinsese #32 pe RR).
    # pret sub entry -> BUY_STOP valid deasupra pretului curent.
    snap = {"symbol": "XRPUSD", "price": 1.0990, "atr": 0.01}
    reason = executor.validate_decision(d, snap, cfg, n_open=0, daily_r=0.0)
    _assert(reason is None, f"dupa reparare rail-ul accepta (motiv={reason})")

    # SHORT: TP prea aproape sub entry -> reparat pe partea corecta
    hs = {"action": "OPEN_SHORT", "order_type": "stop", "entry": 1.0961,
          "sl": 1.0997, "tp": 1.0955, "risk_pct": 0.005, "confidence": 70, "rationale": "x"}
    ds = council._sanitize(dict(hs), {"veto": False, "max_risk_pct": 0.005}, cfg)
    _assert(ds["tp"] < ds["entry"] and (ds["entry"] - ds["tp"]) / abs(ds["entry"] - ds["sl"])
            >= cfg["min_rr"], "SHORT: TP reparat sub entry cu RR valid")
    # TP deja bun (>= min_rr) -> NU se atinge (respectam modelul)
    hg = {"action": "OPEN_LONG", "order_type": "stop", "entry": 1.10,
          "sl": 1.097, "tp": 1.109, "risk_pct": 0.005, "confidence": 70, "rationale": "x"}
    dg = council._sanitize(dict(hg), {"veto": False, "max_risk_pct": 0.005}, cfg)
    _assert(dg["tp"] == 1.109 and "recalculat" not in dg["rationale"],
            "TP deja valid ramane neschimbat")
    # SL degenerat (entry==sl) -> nu reparam, executorul respinge geometria
    hb = {"action": "OPEN_LONG", "order_type": "stop", "entry": 1.10,
          "sl": 1.10, "tp": 1.105, "risk_pct": 0.005, "confidence": 70, "rationale": "x"}
    db = council._sanitize(dict(hb), {"veto": False, "max_risk_pct": 0.005}, cfg)
    _assert(db["tp"] == 1.105, "SL degenerat: TP neschimbat (executorul va respinge)")


def test_stop_bracket(cfg):
    print("[7] sanitizare ordin STOP vs pret live (fix 10015)")
    from ai_engine.executor import adjust_stop_bracket
    dg = 5
    # Cazul REAL #40/#41: BUY_STOP la 0.5 pip peste snapshot, dar pretul LIVE a urcat
    # peste entry -> breakout deja atins -> skip curat (nu mai da 10015 'failed').
    e, s, t, skip = adjust_stop_bracket(1.34152, 1.33946, 1.34564,
                                        ref=1.34160, long_=True, buf=0.00010, digits=dg)
    _assert(skip is not None and e is None,
            "BUY_STOP sub pretul live -> skip curat (fara 10015)")
    # entry pe partea corecta dar prea aproape (< buf) -> muta tot bracket-ul, R pastrat
    e, s, t, skip = adjust_stop_bracket(1.34152, 1.33946, 1.34564,
                                        ref=1.34148, long_=True, buf=0.00010, digits=dg)
    _assert(skip is None and abs((e - 1.34148) - 0.00010) < 1e-9,
            f"entry prea aproape -> mutat la ref+buf ({e})")
    rr_before = (1.34564 - 1.34152) / (1.34152 - 1.33946)
    rr_after = (t - e) / (e - s)
    _assert(abs(rr_before - rr_after) < 1e-6, "geometria R pastrata dupa mutare")
    # entry comfortabil deasupra pietei -> neschimbat
    e, s, t, skip = adjust_stop_bracket(1.3450, 1.3420, 1.3510,
                                        ref=1.3430, long_=True, buf=0.00010, digits=dg)
    _assert(skip is None and e == 1.3450, "entry valid ramane neschimbat")
    # SELL_STOP simetric: pretul live a cazut la/sub nivelul de intrare -> skip
    # (SELL_STOP e valid sub piata; devine invalid cand bid <= entry, adica entry >= ref)
    e, s, t, skip = adjust_stop_bracket(1.3432, 1.3460, 1.3372,
                                        ref=1.3430, long_=False, buf=0.00010, digits=dg)
    _assert(skip is not None, "SELL_STOP: pretul a atins deja intrarea -> skip curat")
    # SELL_STOP valid (entry sub piata, cu distanta) -> neschimbat
    e, s, t, skip = adjust_stop_bracket(1.3420, 1.3450, 1.3360,
                                        ref=1.3430, long_=False, buf=0.00010, digits=dg)
    _assert(skip is None and e == 1.3420, "SELL_STOP valid sub piata ramane neschimbat")


def test_council_live(cfg):
    print("[8] consiliu LIVE pe Ollama (poate dura ~1-2 min)")
    provider = make_provider(cfg)
    if not provider.available():
        print("  SKIP — Ollama/modelul indisponibil")
        return
    registry = ProviderRegistry(cfg["providers"], {})
    from ai_engine.perception import render_text
    briefing = render_text(_fake_snapshot())
    desk = {"open_positions": 0, "daily_r": 0.0, "open_pos_desc": "none"}
    decision, transcript, dur = council.convene(registry, briefing, desk, cfg)
    _assert("error" not in transcript,
            f"consiliul a rulat fara eroare ({dur:.0f}s)")
    _assert(decision["action"] in ("OPEN_LONG", "OPEN_SHORT", "CLOSE", "WAIT"),
            f"actiune valida: {decision['action']}")
    _assert(all(k in transcript for k in ("technical", "macro", "risk", "head_trader")),
            "toate cele 4 roluri au raspuns")
    if decision["action"].startswith("OPEN"):
        _assert(decision["sl"] is not None and decision["tp"] is not None,
                "decizie OPEN are SL si TP")
        _assert(decision["risk_pct"] <= cfg["risk_pct_max"],
                f"risc {decision['risk_pct']} sub rail {cfg['risk_pct_max']}")
    print(f"  DECIZIE: {decision['action']} conf={decision['confidence']}% "
          f"— {decision['rationale'][:120]}")


def main():
    cfg = load_config()
    test_ledger()
    test_triggers(cfg)
    test_rails(cfg)
    test_failover()
    test_veto_semantics(cfg)
    test_tp_repair(cfg)
    test_stop_bracket(cfg)
    test_council_live(cfg)
    print("\nToate verificarile AI Engine au trecut.")


if __name__ == "__main__":
    main()
