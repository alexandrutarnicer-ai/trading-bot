"""Jurnal de AUDIT comun pentru actiunile administrative pe engine-uri (2026-11-12).

Un rand JSON pe actiune in `data/audit_log.jsonl` (append-only, sincronizat ca restul datelor): cine / ce /
pe ce piata / de la ce la ce. Folosit de Daily + Special Engine (schimbari de mod Live / Shadow / Pauza,
configurare, pornire / oprire, ordine respinse sau blocate). Scrierea NU are voie sa strice actiunea:
orice eroare e ignorata. Citire: `read(limit, engine)` (cele mai noi primele) → GET /reports/audit-log.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIT_FILE = os.path.join(ROOT, "data", "audit_log.jsonl")
_LOCK = threading.Lock()


def record(engine: str, action: str, detail: str = "", *, market: str | None = None, before=None, after=None,
           source: str = "ui") -> None:
    row = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "engine": engine, "action": action,
           "market": market, "before": before, "after": after, "detail": detail, "source": source}
    try:
        with _LOCK:
            os.makedirs(os.path.dirname(AUDIT_FILE), exist_ok=True)
            with open(AUDIT_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


def read(limit: int = 300, engine: str | None = None) -> list[dict]:
    out = []
    try:
        with open(AUDIT_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if engine and r.get("engine") != engine:
                    continue
                out.append(r)
    except FileNotFoundError:
        return []
    return out[::-1][:max(1, min(limit, 5000))]
