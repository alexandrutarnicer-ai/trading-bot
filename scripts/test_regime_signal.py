# -*- coding: utf-8 -*-
"""
Teste pentru semnalul de regim trend/chop (Feature: Regime Awareness, 2026-08-08).

Verifica:
  - _efficiency_ratio (Kaufman ER) + _regime_label (praguri)
  - render_text: linia de regim apare cu regime_aware=True, ABSENTA (briefing identic)
    cu regime_aware=False sau cand efficiency lipseste
  - restul briefing-ului e byte-identic indiferent de flag (nu se strica structura)

Rulare:  python scripts/test_regime_signal.py   (offline, fara MT5/Ollama)
"""
import io, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import ai_engine.perception as P

_p = _f = 0
def check(c, m):
    global _p, _f
    if c: _p += 1; print(f"  OK  {m}")
    else: _f += 1; print(f"  XX  {m}")


def _snap(efficiency=0.05, regime="CHOPPY", pctile=8.0):
    """Snapshot minimal cu toate cheile pe care le foloseste render_text."""
    return {
        "symbol": "EURUSD", "price": 1.1000, "weekday": 2, "hour": 15,
        "bar_time": "2026-08-05 15:00:00", "trend_m30": 1, "trend_d1": 1,
        "weekly_up": 1, "adx_d1_gt25": 0, "ema_align": "bullish", "rsi": 55.0,
        "atr": 0.0008, "atr_pctile": 40.0, "swing_highs": [1.102], "swing_lows": [1.098],
        "high_20": 1.1015, "low_20": 1.0985, "ret_1h_pct": 0.1, "ret_4h_pct": 0.2,
        "ret_1d_pct": -0.3, "news": [],
        "efficiency": efficiency, "efficiency_pctile": pctile, "regime": regime,
    }


def test_efficiency_ratio():
    print("[1] _efficiency_ratio + _regime_label")
    check(abs(P._efficiency_ratio([1, 2, 3, 4, 5]) - 1.0) < 1e-9, "trend curat -> ER=1.0")
    check(P._efficiency_ratio([1, 2, 1, 2, 1, 2]) < 0.3, "oscilatie -> ER mic")
    check(P._efficiency_ratio([5, 5, 5]) is None, "drum nul -> None")
    check(P._efficiency_ratio([1]) is None, "prea putine puncte -> None")
    check(P._regime_label(0.05) == "CHOPPY", "0.05 -> CHOPPY")
    check(P._regime_label(0.15) == "NEUTRAL", "0.15 (prag) -> NEUTRAL")
    check(P._regime_label(0.34) == "NEUTRAL", "0.34 -> NEUTRAL")
    check(P._regime_label(0.35) == "TRENDING", "0.35 (prag) -> TRENDING")
    check(P._regime_label(None) == "unknown", "None -> unknown")


def test_render_gating():
    print("[2] render_text — linia de regim gate-uita + restul identic")
    s = _snap(efficiency=0.05, regime="CHOPPY")
    on  = P.render_text(s, regime_aware=True)
    off = P.render_text(s, regime_aware=False)
    check("Trend efficiency" in on, "regime_aware=True -> linia de regim prezenta")
    check("CHOPPY" in on, "eticheta CHOPPY prezenta in briefing")
    check("Trend efficiency" not in off, "regime_aware=False -> fara linie de regim")
    # restul liniilor: OFF trebuie sa fie ON fara linia de regim (byte-identic)
    on_wo = "\n".join(l for l in on.split("\n") if "Trend efficiency" not in l)
    check(off == on_wo, "OFF == ON minus linia de regim (restul briefing-ului neschimbat)")


def test_missing_efficiency_graceful():
    print("[3] Fallback: efficiency lipsa/None -> fara linie, fara eroare")
    s = _snap(); s["efficiency"] = None
    out = P.render_text(s, regime_aware=True)
    check("Trend efficiency" not in out, "efficiency=None -> nicio linie de regim (grace)")
    # briefing vechi (fara cheile de regim deloc) nu crapa
    s2 = _snap(); [s2.pop(k) for k in ("efficiency", "efficiency_pctile", "regime")]
    out2 = P.render_text(s2, regime_aware=True)
    check("MARKET BRIEFING" in out2 and "Trend efficiency" not in out2,
          "snapshot fara chei de regim -> render_text OK (backward-compat)")


def test_trending_label():
    print("[4] Etichete corecte in briefing pt TRENDING")
    on = P.render_text(_snap(efficiency=0.55, regime="TRENDING", pctile=88.0), regime_aware=True)
    check("TRENDING" in on and "0.55" in on, "regime TRENDING randat cu valoarea")


def main():
    print("=" * 60)
    print("TESTE — semnal regim trend/chop (Regime Awareness)")
    print("=" * 60)
    test_efficiency_ratio()
    test_render_gating()
    test_missing_efficiency_graceful()
    test_trending_label()
    print("=" * 60)
    print(f"REZULTAT: {_p} OK, {_f} esuate")
    print("=" * 60)
    sys.exit(1 if _f else 0)


if __name__ == "__main__":
    main()
