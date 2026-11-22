"""Consultare a consiliului AI REAL (aceleasi surse, prompturi si rails ca motorul) pe piete CANDIDATE — fara niciun ordin,
fara scriere in ledger. Briefing-ul = exact cel pe care l-ar primi motorul (perception.build_snapshot + render_text).

    python scripts/research_ai/ai_council_consult.py XAGUSD JP225 STOXX50
Rezultat: data/research_ai_council_<data>.json + rezumat in consola.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)


class ReadOnlySrc:
    """Barele MT5 in ora aplicatiei (ca Mt5DataSource), FARA conexiunea „component” (cont real → doar citire directa)."""

    def __init__(self, mt5, n_bars: int = 2000):
        from zoneinfo import ZoneInfo
        self.mt5, self.n = mt5, n_bars
        self.ny, self.ro = ZoneInfo("America/New_York"), ZoneInfo("Europe/Bucharest")

    def load_bars(self, symbol: str, timeframe: str) -> pd.DataFrame:
        tf = {"M15": self.mt5.TIMEFRAME_M15, "M30": self.mt5.TIMEFRAME_M30, "H1": self.mt5.TIMEFRAME_H1,
              "H4": self.mt5.TIMEFRAME_H4, "D1": self.mt5.TIMEFRAME_D1}[timeframe]
        self.mt5.symbol_select(symbol, True)
        r = self.mt5.copy_rates_from_pos(symbol, tf, 0, self.n)
        d = pd.DataFrame(r)
        srv = pd.to_datetime(d["time"], unit="s")               # ora serverului ICMarkets = New York + 7h
        d["time"] = ((srv - pd.Timedelta(hours=7)).dt.tz_localize(self.ny, ambiguous="NaT", nonexistent="NaT")
                     .dt.tz_convert(self.ro).dt.tz_localize(None))
        d = d.dropna(subset=["time"])
        return d[["time", "open", "high", "low", "close", "tick_volume", "spread", "real_volume"]].reset_index(drop=True)


def main():
    syms = [s.upper() for s in sys.argv[1:]] or ["CHFJPY", "GBPUSD"]
    import MetaTrader5 as mt5
    if not mt5.initialize():
        sys.exit("MT5 indisponibil")
    from ai_engine import orchestrator, perception
    from ai_engine.config import load_config, load_keys
    from ai_engine.providers import ProviderRegistry
    cfg = load_config()
    registry = ProviderRegistry(cfg["providers"], load_keys())
    src = ReadOnlySrc(mt5)
    out = {"time": datetime.now().isoformat(timespec="seconds"), "results": {}}
    for sym in syms:
        t0 = time.time()
        try:
            snap = perception.build_snapshot(src, sym)
            briefing = perception.render_text(snap, regime_aware=cfg.get("regime_aware", True))
            desk = {"open_positions": 0, "committed": 0, "daily_r": 0.0, "trigger": "weekly_review (consultare, fara ordin)",
                    "open_pos_desc": "none"}
            decision, bundle, dur = orchestrator.decide(registry, sym, snap, briefing, desk, cfg)
            tr = bundle.get("primary") or {}
            res = {"action": decision.get("action"), "confidence": decision.get("confidence"),
                   "head_confidence": decision.get("head_confidence"), "entry": decision.get("entry"),
                   "sl": decision.get("sl"), "tp": decision.get("tp"), "rationale": decision.get("rationale"),
                   "regime": snap.get("regime"), "efficiency": snap.get("efficiency"), "trend_m30": snap.get("trend_m30"),
                   "trend_d1": snap.get("trend_d1"), "atr": snap.get("atr"), "price": snap.get("price"),
                   "roles": {r: {k: (v.get(k) if isinstance(v, dict) else None) for k in ("bias", "stance", "confidence", "veto",
                                                                                          "summary", "thesis", "reason", "_provider")}
                             for r, v in tr.items() if not r.startswith("_")},
                   "duration_s": round(dur, 1)}
        except Exception as e:  # noqa: BLE001
            res = {"error": f"{type(e).__name__}: {e}"}
        out["results"][sym] = res
        print(f"\n=== {sym} ({time.time() - t0:.0f}s) → {res.get('action')} conf {res.get('confidence')} · regim "
              f"{res.get('regime')} ER {res.get('efficiency')} · trend M30 {res.get('trend_m30')} D1 {res.get('trend_d1')}")
        print("   ", (res.get("rationale") or res.get("error") or "")[:500])
    path = os.path.join(ROOT, "data", f"research_ai_council_{datetime.now():%Y%m%d}.json")
    json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print("->", path)


if __name__ == "__main__":
    main()
