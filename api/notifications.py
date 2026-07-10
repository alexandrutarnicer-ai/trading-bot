"""
Notification store — scrie si citeste din data/notifications.json (JSONL format).
JSONL (un JSON per linie) permite append din mai multe procese fara lock inter-process.

Problema anterioara: JSON array cu read-modify-write race: 20 sesiuni scriau simultan
la startup → fiecare citea versiunea veche, adauga intrarea sa, suprascria → alte intrari pierdute.

Solutie: log_notification() face append la o singura linie (fara read). Operatiile
de modificare (mark_read, delete, clear) sunt exclusiv din procesul API (threading.Lock suficient).
"""

import json
import os
import re
import uuid
from datetime import datetime
from threading import Lock

from api.config import DATA_DIR

NOTIFICATIONS_FILE = os.path.join(DATA_DIR, "notifications.json")
MAX_NOTIFICATIONS = 500

# Lock pentru operatii read-modify-write din procesul API (nu protejeaza inter-process)
_lock = Lock()


def _categorize(text: str) -> str:
    """Detecteaza categoria dupa continutul textului."""
    t = text.lower()
    # Doar respingerile filtrului si sanatatea surselor AI — mesajele de ordine
    # care contin sufixul "Filtru AI: aprobat" raman in categoria "order".
    if any(x in t for x in ["filtru ai: respins", "ai filter rejected", "sursa ai"]):
        return "ai"
    if any(x in t for x in ["activat #", "buy_stop", "sell_stop", "ordin activat", "ordin plasat"]):
        return "order"
    if any(x in t for x in ["semnal", "signal", "setup", "detectat"]):
        return "signal"
    if any(x in t for x in ["stire", "news", "protectie", "pauza automata", "news_paused", "auto-pauza"]):
        return "news"
    if any(x in t for x in ["pauza", "⏸", "reluata", "▶️", "resume", "pause"]):
        return "session"
    if any(x in t for x in ["pornit", "oprit", "start", "stop", "bot trading", "watchdog"]):
        return "bot"
    if any(x in t for x in ["tp", "sl", "inchis", "profit", "loss", "closed", "vineri"]):
        return "trade"
    return "system"


def _strip_html(text: str) -> str:
    """Elimina taguri HTML simple (bold, italic) din textul Telegram."""
    return re.sub(r"<[^>]+>", "", text).strip()


def _read_all_entries() -> list[dict]:
    """
    Citeste toate notificarile din fisier.
    Suporta JSONL (nou, un JSON per linie) si JSON array (legacy, pentru migrare).
    Linii invalide (scrise partial in caz de crash) sunt ignorate silentios.
    """
    if not os.path.exists(NOTIFICATIONS_FILE):
        return []
    try:
        with open(NOTIFICATIONS_FILE, encoding="utf-8", errors="replace") as f:
            content = f.read().strip()
        if not content:
            return []
        # Detecteaza format: JSON array legacy (incepe cu '[') sau JSONL
        if content.startswith("["):
            try:
                return json.loads(content)
            except Exception:
                return []
        entries = []
        for line in content.splitlines():
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except Exception:
                    pass  # linie partiala sau corupta — ignora
        return entries
    except Exception:
        return []


def _rewrite_entries(entries: list[dict]) -> None:
    """Rescrie fisierul ca JSONL. Apelat NUMAI cu _lock tinut (din procesul API)."""
    with open(NOTIFICATIONS_FILE, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False, separators=(",", ":")) + "\n")


def migrate_to_jsonl() -> None:
    """
    Migrare one-time: fisier JSON array legacy → JSONL.
    Apelata la startup API (api/main.py) si inline din log_notification ca fallback.
    Dupa migrare, append-ul JSONL e safe cross-process.
    """
    with _lock:
        if not os.path.exists(NOTIFICATIONS_FILE):
            return
        try:
            with open(NOTIFICATIONS_FILE, "rb") as f:
                first = f.read(1)
            if first == b"[":
                entries = _read_all_entries()
                _rewrite_entries(entries)
        except Exception:
            pass


def log_notification(text: str) -> None:
    """
    Adauga o notificare. Safe cross-process: append o singura linie JSONL.
    Nu necesita lock inter-process — OS garanteaza ca write-ul mic e atomic pe NTFS.
    Apelat din signal_generator.py (procese separate) si api/telegram.py (procesul API).
    """
    entry = {
        "id":         str(uuid.uuid4())[:8],
        "time":       datetime.now().isoformat(timespec="seconds"),
        "text":       text,
        "text_plain": _strip_html(text),
        "category":   _categorize(text),
        "read":       False,
    }
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        # Migrare inline: daca fisierul e in format JSON array legacy, converteste la JSONL
        if os.path.exists(NOTIFICATIONS_FILE):
            try:
                with open(NOTIFICATIONS_FILE, "rb") as _f:
                    _first = _f.read(1)
                if _first == b"[":
                    migrate_to_jsonl()
            except Exception:
                pass
        line = json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n"
        with open(NOTIFICATIONS_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


def read_notifications(limit: int = 100, offset: int = 0) -> list[dict]:
    """Citeste notificarile, cele mai noi primele. Trimeste la MAX daca depasit."""
    with _lock:
        entries = _read_all_entries()
        # Trim daca depasit MAX (fisierul creste prin append — trim la citire)
        if len(entries) > MAX_NOTIFICATIONS:
            entries = entries[-MAX_NOTIFICATIONS:]
            _rewrite_entries(entries)
    entries_rev = list(reversed(entries))
    return entries_rev[offset: offset + limit]


def mark_all_read() -> None:
    with _lock:
        entries = _read_all_entries()
        for n in entries:
            n["read"] = True
        _rewrite_entries(entries)


def delete_notification(nid: str) -> bool:
    with _lock:
        entries = _read_all_entries()
        original_len = len(entries)
        entries = [n for n in entries if n.get("id") != nid]
        if len(entries) == original_len:
            return False
        _rewrite_entries(entries)
        return True


def clear_all() -> None:
    with _lock:
        try:
            with open(NOTIFICATIONS_FILE, "w", encoding="utf-8") as f:
                pass  # fisier gol
        except Exception:
            pass


def unread_count() -> int:
    try:
        entries = _read_all_entries()
        return sum(1 for n in entries if not n.get("read", True))
    except Exception:
        return 0
