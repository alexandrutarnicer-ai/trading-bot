"""
GET    /api/settings/telegram       — citeste config Telegram (token mascat)
PUT    /api/settings/telegram       — salveaza token + chat_id
DELETE /api/settings/telegram       — sterge configuratia
POST   /api/settings/telegram/test  — trimite mesaj de test
GET    /api/settings/timezone       — citeste fusul orar activ
PUT    /api/settings/timezone       — schimba fusul orar (Romania / Germania)
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
TZ_FILE = os.path.join(DATA_DIR, "timezone_config.json")

_SUPPORTED_TZ: dict[str, str] = {
    "Europe/Bucharest": "România (EET/EEST, UTC+2/UTC+3)",
    "Europe/Berlin":    "Germania (CET/CEST, UTC+1/UTC+2)",
}


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


# ---------------------------------------------------------------------------
# Timezone
# ---------------------------------------------------------------------------

@router.get("/timezone")
def get_timezone():
    """Returneaza fusul orar activ si lista de fusuri suportate."""
    try:
        with open(TZ_FILE, encoding="utf-8") as f:
            tz = json.load(f).get("timezone", "Europe/Bucharest")
    except Exception:
        tz = "Europe/Bucharest"
    if tz not in _SUPPORTED_TZ:
        tz = "Europe/Bucharest"
    return {
        "timezone": tz,
        "label":    _SUPPORTED_TZ[tz],
        "supported": [{"tz": k, "label": v} for k, v in _SUPPORTED_TZ.items()],
    }


@router.put("/timezone")
def set_timezone(body: dict):
    """Schimba fusul orar activ. Efectul intra la bara urmatoare (max 15 min)."""
    tz = (body.get("timezone") or "").strip()
    if tz not in _SUPPORTED_TZ:
        raise HTTPException(400, f"Fus orar nesuportat: '{tz}'. Valori valide: {list(_SUPPORTED_TZ)}")
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(TZ_FILE, "w", encoding="utf-8") as f:
        json.dump({"timezone": tz}, f, ensure_ascii=False, indent=2)
    return {"ok": True, "timezone": tz, "label": _SUPPORTED_TZ[tz]}


# ─── Trading LIVE — deblocarea explicita a contului real, per componenta ─────
# Default: BLOCAT (demo-only). Flag-urile stau in data/live_trading.json
# (gitignored — deblocarea nu se propaga intre masini). Vezi live_guard.py.

@router.get("/live-trading")
def get_live_trading():
    """Starea deblocarii LIVE per componenta + tipul contului MT5 curent."""
    from live_guard import live_flags
    account = {"connected": False, "is_demo": None, "login": None, "server": None}
    try:
        from api import mt5_pool
        st = mt5_pool.get_status()
        if st.get("connected"):
            account = {"connected": True, "is_demo": st.get("is_demo"),
                       "login": st.get("account"), "server": st.get("server")}
    except Exception:
        pass
    return {"flags": live_flags(), "account": account}


@router.put("/live-trading")
def set_live_trading(body: dict):
    """
    Comuta deblocarea LIVE pentru o componenta: body {component, allowed}.
    Componente valide: "bot", "ai_engine". Trimite Telegram la fiecare schimbare
    (activarea tranzactionarii cu bani reali nu e niciodata tacuta).
    """
    from live_guard import set_live, COMPONENTS, live_flags
    component = str(body.get("component") or "").strip()
    if component not in COMPONENTS:
        raise HTTPException(400, f"component: una din {list(COMPONENTS)}")
    if "allowed" not in body:
        raise HTTPException(400, "allowed: true/false obligatoriu")
    allowed = bool(body.get("allowed"))
    before = live_flags().get(component)
    flags = set_live(component, allowed)
    if before != allowed:
        try:
            from api.telegram import send_message
            import threading
            name = "BOT (sesiunile pe reguli)" if component == "bot" else "AI Engine"
            text = (f"🔴 <b>Trading LIVE ACTIVAT — {name}</b>\n"
                    f"Componenta poate tranzacționa pe cont REAL pe această mașină. "
                    f"Se aplică la următoarea pornire/reconectare."
                    if allowed else
                    f"🟢 <b>Trading LIVE dezactivat — {name}</b>\n"
                    f"Componenta revine la DEMO-only (blocată pe conturi reale).")
            threading.Thread(target=send_message, args=(text,), daemon=True).start()
        except Exception:
            pass
    return {"ok": True, "flags": flags,
            "note": "Se aplica la urmatoarea conectare MT5 a componentei "
                    "(restart bot/motor daca ruleaza)."}
