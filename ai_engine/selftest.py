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
from ai_engine.providers import make_provider


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


def test_council_live(cfg):
    print("[4] consiliu LIVE pe Ollama (poate dura ~1-2 min)")
    provider = make_provider(cfg)
    if not provider.available():
        print("  SKIP — Ollama/modelul indisponibil")
        return
    from ai_engine.perception import render_text
    briefing = render_text(_fake_snapshot())
    desk = {"open_positions": 0, "daily_r": 0.0, "open_pos_desc": "none"}
    decision, transcript, dur = council.convene(provider, briefing, desk, cfg)
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
    test_council_live(cfg)
    print("\nToate verificarile AI Engine au trecut.")


if __name__ == "__main__":
    main()
