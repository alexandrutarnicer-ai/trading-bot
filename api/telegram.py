"""
Helper Telegram pentru API — citeste credentialele din data/telegram_config.json
cu fallback pe variabile de mediu (TELEGRAM_TOKEN, TELEGRAM_CHAT_ID).
"""

import json
import os
import urllib.request
import urllib.error

from api.config import DATA_DIR

TG_FILE = os.path.join(DATA_DIR, "telegram_config.json")


def _load_credentials() -> tuple[str, str]:
    try:
        with open(TG_FILE, encoding="utf-8") as f:
            cfg = json.load(f)
        token   = cfg.get("token", "").strip()
        chat_id = cfg.get("chat_id", "").strip()
        if token and chat_id:
            return token, chat_id
    except Exception:
        pass
    # Fallback pe env variables (folosite de run_all.py)
    return (
        os.environ.get("TELEGRAM_TOKEN", "").strip(),
        os.environ.get("TELEGRAM_CHAT_ID", "").strip(),
    )


def send_message(text: str, parse_mode: str = "HTML") -> bool:
    # Logheaza in notification store (independent de Telegram)
    try:
        from api.notifications import log_notification
        log_notification(text)
    except Exception:
        pass

    token, chat_id = _load_credentials()
    if not token or not chat_id:
        return False
    try:
        payload = json.dumps({
            "chat_id":    chat_id,
            "text":       text,
            "parse_mode": parse_mode,
        }).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=5)
        return True
    except Exception:
        return False
