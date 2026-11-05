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
        "token_masked":   masked if token else "",
        "chat_id":        cfg.get("chat_id", ""),
        "configured":     bool(token and cfg.get("chat_id")),
        "important_only": bool(cfg.get("important_only", False)),
    }


@router.put("/telegram")
def save_telegram(body: dict):
    token   = (body.get("token")   or "").strip()
    chat_id = (body.get("chat_id") or "").strip()
    if not token or not chat_id:
        raise HTTPException(400, "token si chat_id sunt necesare")
    os.makedirs(DATA_DIR, exist_ok=True)
    # Pastreaza campurile existente (ex: important_only) — nu suprascrie tot fisierul.
    cfg = _load()
    cfg["token"]   = token
    cfg["chat_id"] = chat_id
    with open(TG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    return {"ok": True}


@router.put("/telegram/important-only")
def set_important_only(body: dict):
    """
    Comuta modul liniste: cand e activ, se trimit pe Telegram DOAR notificarile
    importante (trading + conexiune + lifecycle bot). Restul (sanatatea surselor
    AI, pauze manuale, mesaje de sistem) raman doar in tab-ul Notificari.
    Body: {enabled: bool}. Efect imediat (fara restart) — bot/motor citesc flag-ul
    la fiecare notificare.
    """
    if "enabled" not in body:
        raise HTTPException(400, "enabled: true/false obligatoriu")
    enabled = bool(body.get("enabled"))
    os.makedirs(DATA_DIR, exist_ok=True)
    cfg = _load()
    cfg["important_only"] = enabled
    with open(TG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    return {"ok": True, "important_only": enabled}


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
    Componente valide: "bot", "ai_engine", "daily_engine", "noisy_engine". Trimite Telegram la fiecare schimbare
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
            name = {"bot": "Custom Engine (sesiunile pe reguli)", "ai_engine": "AI Engine",
                    "daily_engine": "Daily Engine", "noisy_engine": "Noisy Engine"}.get(component, component)
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


# ─── Setari Globale — punct unic de control pentru Bot Engine + AI Engine ────
# data/global_settings.json (sincronizat prin git). Toate sectiunile OPRITE
# implicit. Regula: „cea mai stricta castiga" peste setarile per sesiune/piata.
# Hot-reload: ambele engine-uri il recitesc la fiecare bara (fara restart).

@router.get("/global")
def get_global_settings():
    from live import global_guard
    return global_guard.load_settings()


@router.put("/global")
def put_global_settings(body: dict):
    from live import global_guard
    before = global_guard.load_settings()
    merged = {**before, **{k: {**before.get(k, {}), **v} for k, v in (body or {}).items()
                           if isinstance(v, dict) and k in global_guard.DEFAULTS}}
    saved = global_guard.save_settings(merged)
    changes = [f"{sec}.{k}: {before[sec][k]} → {saved[sec][k]}"
               for sec in saved for k in saved[sec] if before[sec].get(k) != saved[sec][k]]
    if changes:
        try:
            from api.telegram import send_message
            import threading
            text = ("⚙️ <b>Setări Globale modificate</b>\n" + "\n".join(changes[:20]) +
                    "\n<i>Se aplică de la următoarea bară (Bot + AI), fără restart.</i>")
            threading.Thread(target=send_message, args=(text,), daemon=True).start()
        except Exception:
            pass
    return saved


# ── Special Take Profit Mode (profit_lock.py) — Global → Engine, eligibilitate ─────────────────────────────
# Global: sectiunea `special_tp` din Setari Globale (PUT /settings/global). Engine: `special_tp` la nivelul
# profilului Custom (data/profiles/standard.json + profilul runtime, recitit de sesiuni la fiecare bara).

_STP_PROFILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                            "data", "profiles", "standard.json")
_STP_RUNTIME = os.path.join(os.path.dirname(_STP_PROFILE), "..", "active_profile_runtime.json")

# Rezumatul backtestului (scripts/research_tp/, docs/SPECIAL_TP_RESEARCH.md) — afisat langa comutator
SPECIAL_TP_RESEARCH = [
    {"engine": "Custom", "market": "EURUSD (S1)", "current": -0.008, "special": +0.014, "dd_current": -60.1, "dd_special": -45.0},
    {"engine": "Custom", "market": "GBPUSD (S15)", "current": -0.050, "special": -0.030, "dd_current": -45.7, "dd_special": -47.4},
    {"engine": "Daily", "market": "DE40 Frankfurt", "current": +0.084, "special": +0.039, "dd_current": -64.3, "dd_special": -39.0},
    {"engine": "Daily", "market": "GBPUSD Londra", "current": +0.069, "special": +0.015, "dd_current": -141.3, "dd_special": -82.8},
    {"engine": "Noisy", "market": "US500 M1", "current": -0.096, "special": -0.090, "dd_current": -402.5, "dd_special": -383.5},
]


def _stp_engine_cfg() -> dict:
    try:
        with open(_STP_PROFILE, encoding="utf-8") as f:
            return (json.load(f) or {}).get("special_tp") or {}
    except Exception:
        return {}


@router.get("/special-tp")
def get_special_tp():
    import profit_lock
    from live import global_guard
    g = global_guard.load_settings().get("special_tp")
    eng = {"custom": profit_lock.sanitize(_stp_engine_cfg())}
    return {"global": g, "engine_cfg": eng,
            "effective": {e: {k: v for k, v in profit_lock.effective(g, eng.get(e), e).items()}
                          for e in ("custom", "ai", "daily", "noisy")},
            "eligible": profit_lock.ELIGIBLE, "not_eligible": profit_lock.NOT_ELIGIBLE,
            "research": SPECIAL_TP_RESEARCH}


@router.put("/special-tp/engine")
def put_special_tp_engine(body: dict):
    """Setarea per engine (folosita DOAR cand Global e oprit). Doar engine-urile eligibile."""
    import profit_lock
    engine = (body or {}).get("engine", "custom")
    if engine not in profit_lock.ELIGIBLE:
        raise HTTPException(400, f"{engine}: {profit_lock.NOT_ELIGIBLE.get(engine, 'neeligibil')}")
    cfg = profit_lock.sanitize((body or {}).get("cfg"))
    before = profit_lock.sanitize(_stp_engine_cfg())
    for path in (_STP_PROFILE, os.path.normpath(_STP_RUNTIME)):
        try:
            with open(path, encoding="utf-8") as f:
                prof = json.load(f)
        except FileNotFoundError:
            continue
        prof["special_tp"] = cfg
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(prof, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    if before != cfg:
        try:
            from api.telegram import send_message
            import threading
            txt = (f"🎯 <b>Special TP — Custom Engine {'PORNIT' if cfg['enabled'] else 'oprit'}</b>\n"
                   f"extensie +{cfg['tp_extension_R']:g}R · SL la {cfg['sl_offset_R']:g}R sub prag · pas {cfg['step_R']:g}R "
                   f"({cfg['mode']})\n<i>Se aplică pozițiilor deschise de la următoarea bară (fără restart).</i>")
            threading.Thread(target=send_message, args=(txt,), daemon=True).start()
        except Exception:
            pass
    return get_special_tp()
