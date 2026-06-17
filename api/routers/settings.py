"""
GET    /api/settings/telegram  — citeste config Telegram (token mascat)
PUT    /api/settings/telegram  — salveaza token + chat_id
DELETE /api/settings/telegram  — sterge configuratia
"""
import os
import json
from fastapi import APIRouter, HTTPException
from api.config import DATA_DIR

router = APIRouter(prefix="/settings", tags=["settings"])

TG_FILE = os.path.join(DATA_DIR, "telegram_config.json")


def _load() -> dict:
    if os.path.exists(TG_FILE):
        try:
            with open(TG_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"token": "", "chat_id": ""}


@router.get("/telegram")
def get_telegram():
    cfg   = _load()
    token = cfg.get("token", "")
    masked = (token[:8] + "..." + token[-4:]) if len(token) > 12 else ("*" * len(token))
    return {
        "token_masked": masked if token else "",
        "chat_id":      cfg.get("chat_id", ""),
        "configured":   bool(token and cfg.get("chat_id")),
    }


@router.put("/telegram")
def save_telegram(body: dict):
    token   = (body.get("token")   or "").strip()
    chat_id = (body.get("chat_id") or "").strip()
    if not token or not chat_id:
        raise HTTPException(400, "token si chat_id sunt necesare")
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(TG_FILE, "w", encoding="utf-8") as f:
        json.dump({"token": token, "chat_id": chat_id}, f, ensure_ascii=False, indent=2)
    return {"ok": True}


@router.delete("/telegram")
def clear_telegram():
    if os.path.exists(TG_FILE):
        os.remove(TG_FILE)
    return {"ok": True}
