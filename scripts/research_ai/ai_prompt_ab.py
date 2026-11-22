"""A/B pe ACELEASI date: consiliul AI (prompturile din cod, la momentul rularii) pe snapshot-uri reale din ledger + rezultatul
SIMULAT al fiecarei decizii OPEN pe barele M5 reale (aceeasi simulare ca ai_guard_replay). Fara ordine, fara ledger.

Rulat o data INAINTE de schimbarea prompturilor (--tag old) si o data DUPA (--tag new) → acelasi esantion (seed fix).
Doar Ollama pe toate rolurile (implicit) — nu consuma cota Gemini, iar Ollama e acum sursa principala.
Cu --gates aplica si regulile deterministe noi (validate_decision) inainte de simulare.

    python scripts/research_ai/ai_prompt_ab.py --tag old --n 40
    python scripts/research_ai/ai_prompt_ab.py --tag new --n 40 --gates
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sqlite3
import sys
import time
from datetime import timedelta

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def sample(n: int, seed: int = 20261122) -> pd.DataFrame:
    c = sqlite3.connect(f"file:{os.path.join(ROOT, 'data', 'ai', 'ledger.db')}?mode=ro", uri=True)
    df = pd.read_sql("""select co.id, co.ts, co.symbol, co.trigger, co.snapshot_id, d.action orig_action
                        from councils co join snapshots s on s.id = co.snapshot_id
                        left join decisions d on d.council_id = co.id
                        where s.data not like '%_pruned%' and co.ts >= '2026-10-01'""", c)
    df = df.drop_duplicates("id")
    opens = df[df.orig_action.str.startswith("OPEN", na=False)]
    waits = df[~df.index.isin(opens.index)]
    k = min(len(opens), n // 2)
    return pd.concat([opens.sample(k, random_state=seed), waits.sample(n - k, random_state=seed)]).sort_values("ts")


def sim(b, side, entry, sl, tp, t0, market):
    w = b[(b.time >= t0) & (b.time <= t0 + timedelta(hours=72))]
    if w.empty or not sl or not entry:
        return None, "fara date"
    i0 = 0
    if not market:
        hit = np.where((w.high >= entry) if side == 1 else (w.low <= entry))[0]
        hit = hit[hit < 288]
        if not len(hit):
            return 0.0, "expirat"
        i0 = hit[0]
    risk = abs(entry - sl)
    if risk <= 0:
        return None, "geometrie"
    for k in range(i0, min(len(w), i0 + 576)):
        h, l = w.high.iat[k], w.low.iat[k]
        if (l <= sl) if side == 1 else (h >= sl):
            return -1.0, "SL"
        if tp and k > i0 and ((h >= tp) if side == 1 else (l <= tp)):
            return abs(tp - entry) / risk, "TP"
    return (w.close.iat[min(len(w), i0 + 576) - 1] - entry) * side / risk, "timp"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--roles", default="technical=ollama,macro=ollama,risk=ollama,head_trader=ollama")
    ap.add_argument("--gates", action="store_true")
    a = ap.parse_args()
    import MetaTrader5 as mt5
    mt5.initialize()
    from ai_engine import orchestrator, perception
    from ai_engine.config import load_config, load_keys
    from ai_engine.providers import ProviderRegistry
    cfg = copy.deepcopy(load_config())
    for kv in a.roles.split(","):
        k, v = kv.split("=")
        cfg["role_assignments"][k] = v
    registry = ProviderRegistry(cfg["providers"], load_keys())
    c = sqlite3.connect(f"file:{os.path.join(ROOT, 'data', 'ai', 'ledger.db')}?mode=ro", uri=True)
    bars, rows = {}, []
    for _, r in sample(a.n).iterrows():
        snap = json.loads(c.execute("select data from snapshots where id=?", (int(r.snapshot_id),)).fetchone()[0])
        briefing = perception.render_text(snap, regime_aware=cfg.get("regime_aware", True))
        desk = {"open_positions": 0, "committed": 0, "daily_r": 0.0, "trigger": r.trigger, "open_pos_desc": "none"}
        t0 = time.time()
        try:
            dec, bundle, _ = orchestrator.decide(registry, r.symbol, snap, briefing, desk, cfg)
        except Exception as e:  # noqa: BLE001
            dec, bundle = {"action": "ERR", "rationale": str(e)}, {}
        gate = ""
        if a.gates and str(dec.get("action", "")).startswith("OPEN"):
            from ai_engine import executor
            try:
                ok, why, dec2 = executor.apply_decision_gates(dec, snap, cfg)
                if not ok:
                    gate = why
                    dec = {**dec, "action": "WAIT"}
                else:
                    dec = dec2
            except AttributeError:
                pass
        side = {"OPEN_LONG": 1, "OPEN_SHORT": -1}.get(dec.get("action"), 0)
        R, st = (None, "")
        if side:
            if r.symbol not in bars:
                mt5.symbol_select(r.symbol, True)
                x = pd.DataFrame(mt5.copy_rates_from_pos(r.symbol, mt5.TIMEFRAME_M5, 0, 60000))
                x["time"] = pd.to_datetime(x.time, unit="s")
                bars[r.symbol] = x
            R, st = sim(bars[r.symbol], side, dec.get("entry"), dec.get("sl"), dec.get("tp"), pd.Timestamp(r.ts),
                        dec.get("order_type") == "market")
        tech = (bundle.get("primary") or {}).get("technical") or {}
        rows.append({"council_id": r.id, "ts": r.ts, "symbol": r.symbol, "regime": snap.get("regime"),
                     "trend_m30": snap.get("trend_m30"), "trend_d1": snap.get("trend_d1"), "orig": r.orig_action,
                     "action": dec.get("action"), "conf": dec.get("confidence"), "tech_bias": tech.get("bias"),
                     "gate": gate, "R": R, "sim": st, "secs": round(time.time() - t0, 1),
                     "rationale": (dec.get("rationale") or "")[:240]})
        print(f"{r.ts[:16]} {r.symbol:7} {str(snap.get('regime')):8} atunci {str(r.orig_action):10} → {dec.get('action'):10} "
              f"({dec.get('confidence')}) {gate[:40]} {'' if R is None else f'{R:+.2f}R {st}'} [{time.time() - t0:.0f}s]")
    x = pd.DataFrame(rows)
    out = os.path.join(ROOT, "data", f"research_ai_ab_{a.tag}.csv")
    x.to_csv(out, index=False)
    op = x[x.action.str.startswith("OPEN", na=False)]
    print(f"\n[{a.tag}] {len(x)} consilii · OPEN {len(op)} (LONG {int((op.action == 'OPEN_LONG').sum())} / SHORT "
          f"{int((op.action == 'OPEN_SHORT').sum())}) · R simulat {op.R.sum():+.2f} pe {op.R.notna().sum()} · "
          f"in CHOPPY: {int((op.regime == 'CHOPPY').sum())} · timp mediu {x.secs.mean():.0f}s · erori {int((x.action == 'ERR').sum())}")
    print("->", out)


if __name__ == "__main__":
    main()
