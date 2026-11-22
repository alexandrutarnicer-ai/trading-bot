"""Reluarea consiliului AI pe snapshot-urile REALE ale unor trade-uri inchise, cu o varianta de surse (ex. analistul
tehnic + macro pe Gemini in loc de Ollama) — fara ordine, fara scriere in ledger. Compara cu decizia de atunci.

    python scripts/research_ai/ai_council_replay.py [--n 20] [--roles technical=gemini,macro=gemini]
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sqlite3
import sys
import time

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--roles", default="technical=gemini,macro=gemini")
    ap.add_argument("--sleep", type=float, default=0.0, help="pauza intre consilii (limita de cereri / minut Gemini)")
    ap.add_argument("--out", default="research_ai_council_replay.csv")
    a = ap.parse_args()
    from ai_engine import orchestrator, perception
    from ai_engine.config import load_config, load_keys
    from ai_engine.providers import ProviderRegistry
    cfg = copy.deepcopy(load_config())
    for kv in a.roles.split(","):
        k, v = kv.split("=")
        cfg["role_assignments"][k.strip()] = v.strip()
    registry = ProviderRegistry(cfg["providers"], load_keys())
    d = pd.read_csv(os.path.join(ROOT, "data", "research_ai_decisions_closed.csv"))
    c = sqlite3.connect(f"file:{os.path.join(ROOT, 'data', 'ai', 'ledger.db')}?mode=ro", uri=True)
    ch = d[d.regime == "CHOPPY"].sort_values("ts").tail(a.n // 2)
    ot = d[d.regime.isin(["NEUTRAL", "TRENDING"])].sort_values("ts").tail(a.n - len(ch))
    rows = []
    for _, r in pd.concat([ch, ot]).iterrows():
        snap = json.loads(c.execute("select data from snapshots where id=?", (int(r.snapshot_id),)).fetchone()[0])
        briefing = perception.render_text(snap, regime_aware=cfg.get("regime_aware", True))
        desk = {"open_positions": 0, "committed": 0, "daily_r": 0.0, "trigger": r.trigger, "open_pos_desc": "none"}
        t0 = time.time()
        try:
            dec, bundle, _ = orchestrator.decide(registry, r.symbol, snap, briefing, desk, cfg)
        except Exception as e:  # noqa: BLE001
            dec, bundle = {"action": "ERR", "rationale": str(e)}, {}
        tech = (bundle.get("primary") or {}).get("technical") or {}
        side_new = {"OPEN_LONG": 1, "OPEN_SHORT": -1}.get(dec.get("action"), 0)
        rows.append({"ts": r.ts, "symbol": r.symbol, "regime": r.regime, "orig_side": int(r.side), "orig_R": r.result_r,
                     "orig_tech_src": r.tech_src, "new_action": dec.get("action"), "new_conf": dec.get("confidence"),
                     "new_tech_bias": tech.get("bias"), "new_tech_src": tech.get("_provider"),
                     "same_trade": side_new == int(r.side), "rationale": (dec.get("rationale") or "")[:300]})
        print(f"{r.ts[:16]} {r.symbol:7} {r.regime:8} atunci {'LONG' if r.side == 1 else 'SHORT'} {r.result_r:+.2f}R "
              f"→ acum {dec.get('action')} ({dec.get('confidence')}) tehnic {tech.get('bias')}/{tech.get('_provider')} "
              f"[{time.time() - t0:.0f}s]")
        time.sleep(a.sleep)
    x = pd.DataFrame(rows)
    kept = x[x.same_trade]
    print(f"\nreplay {len(x)} snapshot-uri ({a.roles}): acelasi trade pastrat {len(kept)} ({kept.orig_R.sum():+.2f}R) · "
          f"evitat {len(x) - len(kept)} ({x[~x.same_trade].orig_R.sum():+.2f}R) · original total {x.orig_R.sum():+.2f}R")
    for reg in ("CHOPPY", "NEUTRAL", "TRENDING"):
        s = x[x.regime == reg]
        if len(s):
            print(f"  {reg}: {len(s)} · pastrate {int(s.same_trade.sum())} ({s[s.same_trade].orig_R.sum():+.2f}R) din {s.orig_R.sum():+.2f}R")
    print(f"  analistul tehnic a rulat pe: {x.new_tech_src.value_counts().to_dict()}")
    x.to_csv(os.path.join(ROOT, "data", a.out), index=False)


if __name__ == "__main__":
    main()
