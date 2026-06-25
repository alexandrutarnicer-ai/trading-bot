"""
Notification store — scrie si citeste din data/notifications.json.
Folosit de api/telegram.py si live/signal_generator.py.
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

_lock = Lock()


def _categorize(text: str) -> str:
    """Detecteaza categoria dupa continutul textului."""
    t = text.lower()
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


def log_notification(text: str) -> None:
    """Adauga o notificare in fisierul JSON. Thread-safe."""
    entry = {
        "id":       str(uuid.uuid4())[:8],
        "time":     datetime.now().isoformat(timespec="seconds"),
        "text":     text,
        "text_plain": _strip_html(text),
        "category": _categorize(text),
        "read":     False,
    }
    with _lock:
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            notifications = []
            if os.path.exists(NOTIFICATIONS_FILE):
                try:
                    with open(NOTIFICATIONS_FILE, encoding="utf-8") as f:
                        notifications = json.load(f)
                except Exception:
                    notifications = []
            notifications.append(entry)
            # Pastreaza ultimele MAX_NOTIFICATIONS
            if len(notifications) > MAX_NOTIFICATIONS:
                notifications = notifications[-MAX_NOTIFICATIONS:]
            with open(NOTIFICATIONS_FILE, "w", encoding="utf-8") as f:
                json.dump(notifications, f, ensure_ascii=False, indent=None, separators=(",", ":"))
        except Exception:
            pass


def read_notifications(limit: int = 100, offset: int = 0) -> list[dict]:
    try:
        if not os.path.exists(NOTIFICATIONS_FILE):
            return []
        with open(NOTIFICATIONS_FILE, encoding="utf-8") as f:
            all_n = json.load(f)
        # Cele mai noi primele
        all_n = list(reversed(all_n))
        return all_n[offset: offset + limit]
    except Exception:
        return []


def mark_all_read() -> None:
    with _lock:
        try:
            if not os.path.exists(NOTIFICATIONS_FILE):
                return
            with open(NOTIFICATIONS_FILE, encoding="utf-8") as f:
                notifications = json.load(f)
            for n in notifications:
                n["read"] = True
            with open(NOTIFICATIONS_FILE, "w", encoding="utf-8") as f:
                json.dump(notifications, f, ensure_ascii=False, separators=(",", ":"))
        except Exception:
            pass


def delete_notification(nid: str) -> bool:
    with _lock:
        try:
            if not os.path.exists(NOTIFICATIONS_FILE):
                return False
            with open(NOTIFICATIONS_FILE, encoding="utf-8") as f:
                notifications = json.load(f)
            original_len = len(notifications)
            notifications = [n for n in notifications if n.get("id") != nid]
            if len(notifications) == original_len:
                return False
            with open(NOTIFICATIONS_FILE, "w", encoding="utf-8") as f:
                json.dump(notifications, f, ensure_ascii=False, separators=(",", ":"))
            return True
        except Exception:
            return False


def clear_all() -> None:
    with _lock:
        try:
            with open(NOTIFICATIONS_FILE, "w", encoding="utf-8") as f:
                json.dump([], f)
        except Exception:
            pass


def unread_count() -> int:
    try:
        if not os.path.exists(NOTIFICATIONS_FILE):
            return 0
        with open(NOTIFICATIONS_FILE, encoding="utf-8") as f:
            notifications = json.load(f)
        return sum(1 for n in notifications if not n.get("read", True))
    except Exception:
        return 0
