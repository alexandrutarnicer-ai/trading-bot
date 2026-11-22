"""Diagnosticul calitatii deciziilor consiliului AI Engine, pe ledger-ul REAL (doar citire).

1. de ce sunt respinse deciziile (rails) — geometrie, RR, SL, expunere;
2. directia trade-ului fata de trendul M30 / D1 si regim → rezultat;
3. bias-ul analistului tehnic (Ollama) contra trendului — cat de des si ce face head-ul;
4. calibrarea increderii (confidence → R);
5. cine a decis (sursa head-ului) → rezultat.

    python scripts/research_ai/ai_decision_quality.py
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB = os.path.join(ROOT, "data", "ai", "ledger.db")


def main():
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    d = pd.read_sql("""select d.id, d.ts, d.symbol, d.action, d.order_type, d.entry, d.sl, d.tp, d.confidence,
                              d.exec_status, d.exec_detail, co.trigger, co.transcript, co.snapshot_id
                       from decisions d left join councils co on co.id = d.council_id""", c)
    o = pd.read_sql("select decision_id, status, result_r from outcomes", c).drop_duplicates("decision_id", keep="last")
    d = d.merge(o, left_on="id", right_on="decision_id", how="left")
    snaps = {r[0]: json.loads(r[1]) for r in c.execute("select id, data from snapshots")}
    def sget(sid, k):
        s = snaps.get(int(sid)) if sid == sid and sid is not None else None
        return s.get(k) if isinstance(s, dict) else None
    for k in ("trend_m30", "trend_d1", "regime", "efficiency", "atr", "price"):
        d[k] = [sget(s, k) for s in d.snapshot_id]
    tr = [json.loads(t) if isinstance(t, str) else {} for t in d.transcript]
    d["pruned"] = [bool(t.get("_pruned")) for t in tr]
    d["tech_bias"] = [(t.get("technical") or {}).get("bias") if isinstance(t.get("technical"), dict) else None for t in tr]
    d["tech_conf"] = [(t.get("technical") or {}).get("confidence") if isinstance(t.get("technical"), dict) else None for t in tr]
    d["macro_bias"] = [(t.get("macro") or {}).get("bias") if isinstance(t.get("macro"), dict) else None for t in tr]
    d["head_src"] = [(t.get("head_trader") or {}).get("_provider") if isinstance(t.get("head_trader"), dict) else None for t in tr]
    d["tech_src"] = [(t.get("technical") or {}).get("_provider") if isinstance(t.get("technical"), dict) else None for t in tr]
    d["side"] = d.action.map({"OPEN_LONG": 1, "OPEN_SHORT": -1})
    closed = d[d.status.isin(["TP", "SL", "closed"])].copy()
    print(f"Decizii: {len(d)} · OPEN: {d.side.notna().sum()} · plasate {int((d.exec_status == 'placed').sum())} · "
          f"respinse {int((d.exec_status == 'rejected').sum())} · trade-uri inchise {len(closed)} ({closed.result_r.sum():+.1f}R)")

    print("\n1. DE CE SUNT RESPINSE (rails) — top motive")
    rej = d[d.exec_status == "rejected"].exec_detail.fillna("")
    def norm(x):
        x = re.sub(r"[0-9]+(\.[0-9]+)?", "#", x)
        return x[:70]
    print(rej.map(norm).value_counts().head(12).to_string())

    print("\n2. DIRECTIA fata de trend → rezultat (trade-uri inchise)")
    closed["vs_d1"] = (closed.side == closed.trend_d1).map({True: "cu D1", False: "CONTRA D1"})
    closed["vs_m30"] = (closed.side == closed.trend_m30).map({True: "cu M30", False: "CONTRA M30"})
    for col in ("vs_d1", "vs_m30", "regime"):
        print(closed.groupby(col).result_r.agg(n="count", total="sum", medie="mean", wr=lambda r: (r > 0).mean()).round(3).to_string(), "\n")
    both = closed[(closed.side == closed.trend_d1) & (closed.side == closed.trend_m30)]
    print(f"  cu AMBELE trenduri: n={len(both)} total={both.result_r.sum():+.2f}R medie={both.result_r.mean():+.3f}")
    rest = closed.drop(both.index)
    print(f"  restul:             n={len(rest)} total={rest.result_r.sum():+.2f}R medie={rest.result_r.mean():+.3f}")

    print("\n3. ANALISTUL TEHNIC (transcripturi necompactate) — bias fata de trendul D1")
    full = d[~d.pruned & d.tech_bias.isin(["long", "short"]) & d.trend_d1.notna()].copy()
    full["tb"] = full.tech_bias.map({"long": 1, "short": -1})
    full["tech_vs_d1"] = (full.tb == full.trend_d1).map({True: "cu D1", False: "CONTRA D1"})
    print(full.groupby(["tech_vs_d1", "regime"]).size().unstack(fill_value=0).to_string())
    print(f"  tehnic contra D1: {(full.tech_vs_d1 == 'CONTRA D1').mean():.0%} din {len(full)} consilii necompactate")
    gx = full[full.side.notna()]
    print(f"  cand s-a deschis: head a urmat tehnicul in {(gx.side == gx.tb).mean():.0%} din cazuri")
    cl = gx[gx.status.isin(['TP', 'SL', 'closed'])]
    print(cl.groupby("tech_vs_d1").result_r.agg(n="count", total="sum", medie="mean").round(3).to_string())

    print("\n4. CALIBRAREA INCREDERII (trade-uri inchise)")
    closed["conf_b"] = pd.cut(closed.confidence, [0, 60, 70, 80, 101], right=False)
    print(closed.groupby("conf_b", observed=True).result_r.agg(n="count", total="sum", medie="mean").round(3).to_string())

    print("\n5. SURSA head-ului / tehnicului → rezultat")
    print(closed.groupby("head_src", dropna=False).result_r.agg(n="count", total="sum", medie="mean").round(3).to_string())
    print(closed.groupby("tech_src", dropna=False).result_r.agg(n="count", total="sum", medie="mean").round(3).to_string())

    print("\n6. SL / RR propuse (trade-uri inchise)")
    closed["sl_atr"] = (closed.entry - closed.sl).abs() / closed.atr
    closed["rr"] = (closed.tp - closed.entry).abs() / (closed.entry - closed.sl).abs()
    closed["sl_b"] = pd.cut(closed.sl_atr, [0, 1.5, 3, 5, 100])
    print(closed.groupby("sl_b", observed=True).result_r.agg(n="count", total="sum", medie="mean").round(3).to_string())
    print(f"  RR median {closed.rr.median():.2f} · TP atins {(closed.status == 'TP').mean():.0%} · SL {(closed.status == 'SL').mean():.0%}")
    closed.drop(columns=["transcript"]).to_csv(os.path.join(ROOT, "data", "research_ai_decisions_closed.csv"), index=False)


if __name__ == "__main__":
    sys.exit(main())
