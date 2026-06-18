"""
GET    /api/settings/telegram       — citeste config Telegram (token mascat)
PUT    /api/settings/telegram       — salveaza token + chat_id
DELETE /api/settings/telegram       — sterge configuratia
POST   /api/settings/telegram/test  — trimite mesaj de test
"""
import os
import json
import urllib.request
import urllib.error
from datetime import datetime
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


@router.post("/telegram/test")
def test_telegram():
    cfg     = _load()
    token   = cfg.get("token", "").strip()
    chat_id = cfg.get("chat_id", "").strip()
    if not token or not chat_id:
        raise HTTPException(400, "Telegram nu este configurat — salvează token-ul și Chat ID-ul mai întâi.")

    now  = datetime.now().strftime("%d %b %Y, %H:%M:%S")
    text = (
        "🤖 *Trading Bot — Test conexiune*\n\n"
        "✅ Notificările Telegram funcționează corect\\!\n\n"
        f"📅 Data: {now}"
    )

    url  = f"https://api.telegram.org/bot{token}/sendMessage"
    data = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "MarkdownV2"}).encode()
    req  = urllib.request.Request(url, data=data,
                                  headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
        if not result.get("ok"):
            raise HTTPException(502, f"Telegram API error: {result.get('description', 'unknown')}")
        return {"ok": True}
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        try:
            detail = json.loads(body).get("description", body)
        except Exception:
            detail = body
        raise HTTPException(502, f"Telegram API error: {detail}")
    except urllib.error.URLError as e:
        raise HTTPException(502, f"Conexiune eșuată: {e.reason}")
