"""
Citirea jurnalelor Filtrului AI Pre-Trade (data/live_signals/<sesiune>/ai_filter.jsonl),
cu cache pe (mtime, size) — acelasi pattern ca api/csv_cache.py.

Folosit de API pentru:
  - badge-ul BOT-AI din Ordine Active (/mt5/orders) — match pe comment MT5
    (sig_id trunchiat la 16 caractere de ICMarketsEU)
  - coloanele AI din Rapoarte/Tranzactii si din outcomes (/sessions/*)

Jurnalele sunt scrise de live/signal_generator.py (append JSONL, un verdict
per semnal evaluat). Fisiere mici (verdicte doar pentru sesiunile cu filtrul
activat) — parcurgerea completa e ieftina si exacta.
"""

import json
import os
import threading

from api.config import DATA_DIR

_LOCK = threading.Lock()
_file_cache: dict[str, tuple] = {}    # path -> (mtime_ns, size, [entries])


def _read_jsonl_cached(path: str) -> list[dict]:
    try:
        st = os.stat(path)
    except OSError:
        return []
    key = (st.st_mtime_ns, st.st_size)
    with _LOCK:
        hit = _file_cache.get(path)
        if hit is not None and (hit[0], hit[1]) == key:
            return hit[2]
    entries: list[dict] = []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                    # pastram doar campurile de join (transcriptul ramane pe disk)
                    entries.append({
                        "sig_id":     str(e.get("sig_id", "")),
                        "approved":   e.get("approved"),
                        "confidence": e.get("confidence"),
                        "threshold":  e.get("threshold"),
                        "level":      e.get("level"),
                        "reason":     str(e.get("reason", ""))[:300],
                        "error":      e.get("error"),
                    })
                except Exception:
                    pass   # linie partiala (crash la scriere) — ignora
    except Exception:
        entries = []
    with _LOCK:
        _file_cache[path] = (key[0], key[1], entries)
    return entries


def get_verdicts() -> tuple[dict, dict]:
    """
    Verdictele din toate sesiunile: (by_sig_id, by_prefix16).
    by_prefix16 mapeaza sig_id[:16] → verdict (comment-ul MT5 e trunchiat la 16).
    Ultimul verdict per sig_id castiga (re-evaluari sunt teoretic imposibile,
    dar jurnalul e append-only).
    """
    base = os.path.join(DATA_DIR, "live_signals")
    by_id: dict[str, dict] = {}
    by_16: dict[str, dict] = {}
    if not os.path.isdir(base):
        return by_id, by_16
    for name in os.listdir(base):
        path = os.path.join(base, name, "ai_filter.jsonl")
        if not os.path.isfile(path):
            continue
        for e in _read_jsonl_cached(path):
            sid = e["sig_id"]
            if sid:
                by_id[sid] = e
                by_16[sid[:16]] = e
    return by_id, by_16
