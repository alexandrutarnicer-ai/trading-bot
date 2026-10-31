"""
global_guard — punct UNIC de control GLOBAL pentru Bot Engine + AI Engine.

Setarile globale (data/global_settings.json, hot-reload pe mtime) se aplica PESTE
setarile per sesiune / per piata dupa regula „cea mai stricta castiga": globalul e
un minim de siguranta; o sesiune poate fi mai stricta, niciodata mai permisiva.

TOATE sectiunile sunt DEZACTIVATE implicit → fara fisier (sau fisier corupt)
comportamentul ambelor engine-uri e identic cu inainte.

Componente:
  - capital_protection   — equity < prag% din start_balance → niciun ordin nou (Bot+AI)
  - circuit_breaker      — N pierderi CONSECUTIVE azi pe tot contul (sau pierdere
                           zilnica ≥ X% din balanta de la inceputul zilei) → stop pana maine
  - friday_close         — inchidere de vineri pentru TOATE pietele non-cripto
  - news_protection      — fereastra de stiri globala (Bot + AI)
  - max_concurrent_per_market — pozitii+pending pe simbol, pe TOT contul (toate engine-urile)
  - ai_filter            — filtrul AI pre-trade global (DOAR Custom/Bot Engine)

Plus circuit breaker-ul PER SESIUNE (campul `circuit_breaker` din profil, care
exista in UI si in backtest dar NU era aplicat in live): aceeasi semantica ca
engine/portfolio.py — N pierderi consecutive in aceeasi zi → sesiunea nu mai
deschide nimic pana a doua zi; un castig reseteaza contorul.

Functiile de decizie sunt PURE (modulul MetaTrader5 e injectat) → testabile offline.
"""
from __future__ import annotations

import copy
import json
import os
import re
import threading
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(_ROOT, "data")
SETTINGS_FILE = os.path.join(DATA_DIR, "global_settings.json")
PROFILE_FILE = os.path.join(DATA_DIR, "profiles", "standard.json")

AI_MAGIC = 770015
_BOT_COMMENT_RE = re.compile(r"^S(\d+)-")
_SMART_NEWS_RE = re.compile(r"^SN\d+$")

FILTER_RANK = {"permissive": 0, "balanced": 1, "strict": 2}

DEFAULTS: dict = {
    "capital_protection": {"enabled": False, "threshold_pct": 70.0, "start_balance": None},
    "circuit_breaker": {"enabled": False, "max_consecutive_losses": 3, "max_daily_loss_pct": 0.0},
    "friday_close": {"enabled": False, "hour": 20, "exclude_crypto": True},
    "news_protection": {"enabled": False, "impact_level": 3, "pre_minutes": 15, "post_minutes": 15},
    "max_concurrent_per_market": {"enabled": False, "max": 1},
    "ai_filter": {"enabled": False, "level": "balanced", "strict": False},
}

_CRYPTO_PREFIXES = ("BTC", "ETH", "XRP", "LTC", "SOL", "ADA", "DOGE", "DOT", "BNB", "AVAX",
                    "LINK", "BCH", "XLM", "TRX", "MATIC")

_lock = threading.Lock()
_cache: dict = {"mtime": None, "settings": copy.deepcopy(DEFAULTS)}


# ── Setari ──────────────────────────────────────────────────────────────────

def _num(v, lo, hi, default, cast=float):
    try:
        return max(lo, min(hi, cast(v)))
    except (TypeError, ValueError):
        return default


def sanitize(raw: dict | None) -> dict:
    """Completeaza cu default-uri + clamp. Chei necunoscute sunt ignorate."""
    raw = raw if isinstance(raw, dict) else {}
    out = copy.deepcopy(DEFAULTS)
    for sec, dflt in DEFAULTS.items():
        src = raw.get(sec)
        if isinstance(src, dict):
            for k in dflt:
                if k in src:
                    out[sec][k] = src[k]
    cp, cb, fc = out["capital_protection"], out["circuit_breaker"], out["friday_close"]
    np_, mc, af = out["news_protection"], out["max_concurrent_per_market"], out["ai_filter"]
    for sec in out.values():
        sec["enabled"] = bool(sec["enabled"])
    cp["threshold_pct"] = _num(cp["threshold_pct"], 1.0, 99.0, 70.0)
    cp["start_balance"] = (None if cp["start_balance"] in (None, "", 0)
                           else _num(cp["start_balance"], 1.0, 1e9, None))
    cb["max_consecutive_losses"] = _num(cb["max_consecutive_losses"], 1, 50, 3, int)
    cb["max_daily_loss_pct"] = _num(cb["max_daily_loss_pct"], 0.0, 100.0, 0.0)
    fc["hour"] = _num(fc["hour"], 0, 23, 20, int)
    fc["exclude_crypto"] = bool(fc["exclude_crypto"])
    np_["impact_level"] = _num(np_["impact_level"], 1, 3, 3, int)
    np_["pre_minutes"] = _num(np_["pre_minutes"], 0, 720, 15, int)
    np_["post_minutes"] = _num(np_["post_minutes"], 0, 720, 15, int)
    mc["max"] = _num(mc["max"], 1, 20, 1, int)
    if af["level"] not in FILTER_RANK:
        af["level"] = "balanced"
    af["strict"] = bool(af["strict"])
    return out


def load_settings(path: str | None = None) -> dict:
    """Setarile globale (cache pe mtime). Lipsa/corupt → DEFAULTS (totul oprit)."""
    path = path or SETTINGS_FILE
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return copy.deepcopy(DEFAULTS)
    with _lock:
        if _cache["mtime"] == (path, mtime):
            return copy.deepcopy(_cache["settings"])
        try:
            with open(path, encoding="utf-8") as f:
                s = sanitize(json.load(f))
        except Exception:
            s = copy.deepcopy(DEFAULTS)
        _cache["mtime"], _cache["settings"] = (path, mtime), s
        return copy.deepcopy(s)


def save_settings(new: dict, path: str | None = None) -> dict:
    path = path or SETTINGS_FILE
    s = sanitize(new)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)
    return s


def is_crypto(symbol: str) -> bool:
    return str(symbol).upper().startswith(_CRYPTO_PREFIXES)


# ── „Cea mai stricta castiga" — campuri efective per sesiune (Bot Engine) ─────

GLOBAL_SESSION_FIELDS = (
    "friday_close_enabled", "friday_close_hour",
    "news_protection_enabled", "news_impact_level", "news_pre_minutes", "news_post_minutes",
    "ai_filter_enabled", "ai_filter_level", "ai_filter_strict",
)


def effective_session_fields(base: dict, markets: list | None = None,
                             settings: dict | None = None) -> dict:
    """
    PUR. `base` = valorile sesiunii (din script + profil), DOAR cheile din
    GLOBAL_SESSION_FIELDS. Intoarce valorile efective dupa aplicarea globalului.
    Global oprit pe o sectiune → valorile sesiunii neschimbate (byte-identic).
    """
    s = settings if settings is not None else load_settings()
    out = {k: base.get(k) for k in GLOBAL_SESSION_FIELDS if k in base}
    markets = markets or []

    fc = s["friday_close"]
    if fc["enabled"] and not (fc["exclude_crypto"] and markets and all(is_crypto(m) for m in markets)):
        sess_on = bool(base.get("friday_close_enabled", True))
        sess_h = int(base.get("friday_close_hour", 20))
        out["friday_close_enabled"] = True
        out["friday_close_hour"] = min(fc["hour"], sess_h) if sess_on else fc["hour"]

    np_ = s["news_protection"]
    if np_["enabled"]:
        if base.get("news_protection_enabled", False):
            out["news_impact_level"] = min(np_["impact_level"], int(base.get("news_impact_level", 3)))
            out["news_pre_minutes"] = max(np_["pre_minutes"], int(base.get("news_pre_minutes", 15)))
            out["news_post_minutes"] = max(np_["post_minutes"], int(base.get("news_post_minutes", 15)))
        else:
            out["news_impact_level"] = np_["impact_level"]
            out["news_pre_minutes"] = np_["pre_minutes"]
            out["news_post_minutes"] = np_["post_minutes"]
        out["news_protection_enabled"] = True

    af = s["ai_filter"]
    if af["enabled"]:
        if base.get("ai_filter_enabled", False):
            lvl = base.get("ai_filter_level", "balanced")
            if FILTER_RANK.get(af["level"], 1) > FILTER_RANK.get(lvl, 1):
                lvl = af["level"]
            out["ai_filter_level"] = lvl
            out["ai_filter_strict"] = bool(base.get("ai_filter_strict", False)) or af["strict"]
        else:
            out["ai_filter_level"] = af["level"]
            out["ai_filter_strict"] = af["strict"]
        out["ai_filter_enabled"] = True
    return out


def effective_ai_weekend(cfg: dict, symbol: str, settings: dict | None = None) -> tuple[bool, int]:
    """AI Engine: (weekend_close_enabled, ora) dupa aplicarea friday_close global."""
    s = settings if settings is not None else load_settings()
    on = bool(cfg.get("weekend_close_enabled", True))
    hour = int(cfg.get("weekend_close_hour", 22))
    fc = s["friday_close"]
    if fc["enabled"] and not (fc["exclude_crypto"] and is_crypto(symbol)):
        hour = min(hour, fc["hour"]) if on else fc["hour"]
        on = True
    return on, hour


# ── Istoricul zilei din MT5 (sursa unica) ───────────────────────────────────

def classify(magic: int, comment: str) -> tuple[str, str | None]:
    """(source, session_id) — aceeasi regula ca api/mt5_pool.classify_trade."""
    if int(magic or 0) == AI_MAGIC:
        return "ai", None
    c = str(comment or "")
    m = _BOT_COMMENT_RE.match(c)
    if m:
        return "bot", f"session{m.group(1)}"
    if _SMART_NEWS_RE.match(c):
        return "bot", None
    return "manual", None


def _detect_offset_h(mt5) -> int:
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    for tf in (mt5.TIMEFRAME_M15, mt5.TIMEFRAME_M1):
        rates = mt5.copy_rates_from_pos("EURUSD", tf, 1, 1)
        if rates is None or len(rates) == 0:
            continue
        bar = datetime.fromtimestamp(int(rates[0]["time"]), tz=timezone.utc).replace(tzinfo=None)
        diff = (bar - now_utc).total_seconds()
        for c in (3, 2, 1, 0):
            if abs(diff - c * 3600) < 1800:
                return c
    return 0


_offset: dict = {"until": None, "value": 0}


def _server_offset_h(mt5) -> int:
    now = datetime.utcnow()
    if _offset["until"] is None or now > _offset["until"]:
        try:
            _offset["value"] = _detect_offset_h(mt5)
        except Exception:
            pass
        _offset["until"] = now + timedelta(minutes=30)
    return _offset["value"]


def _tz_name() -> str:
    try:
        from tz_helper import get_configured_tz_name
        return get_configured_tz_name()
    except Exception:
        return "Europe/Bucharest"


def closed_today(mt5, now_local: datetime | None = None, offset_h: int | None = None,
                 tz_name: str | None = None) -> list[dict]:
    """
    Pozitiile INCHISE azi (ziua locala), sortate dupa ora inchiderii:
    [{close_time, net, symbol, source, session_id}]. net = profit+comision+swap.
    Atribuirea vine din deal-ul de INTRARE (magic/comment), ca in mt5_pool.
    """
    tz_name = tz_name or _tz_name()
    now_local = now_local or datetime.now(ZoneInfo(tz_name)).replace(tzinfo=None)
    off = _server_offset_h(mt5) if offset_h is None else offset_h
    # fereastra larga in ora serverului: pozitii deschise cu zile in urma, inchise azi
    deals = mt5.history_deals_get(now_local - timedelta(days=7), now_local + timedelta(days=1)) or []

    def _local(ts: int) -> datetime:
        server = datetime.utcfromtimestamp(int(ts))
        if off == 0:
            return server
        return ((server - timedelta(hours=off)).replace(tzinfo=timezone.utc)
                .astimezone(ZoneInfo(tz_name)).replace(tzinfo=None))

    pos: dict = {}
    for d in deals:
        if getattr(d, "type", None) not in (0, 1):
            continue
        p = pos.setdefault(d.position_id, {"net": 0.0, "close_time": None, "symbol": d.symbol,
                                           "magic": 0, "comment": "", "has_in": False})
        if getattr(d, "magic", 0):
            p["magic"] = int(d.magic)
        p["net"] += float(d.commission or 0) + float(d.swap or 0)
        if d.entry == 0:
            p["comment"] = str(getattr(d, "comment", "") or "")
            p["has_in"] = True
        else:
            p["net"] += float(d.profit or 0)
            t = _local(d.time)
            if p["close_time"] is None or t > p["close_time"]:
                p["close_time"] = t
    today = now_local.date()
    out = []
    for pid, p in pos.items():
        if p["close_time"] is None or p["close_time"].date() != today:
            continue
        if not p["has_in"]:
            try:   # intrarea e mai veche decat fereastra — o cerem explicit
                ins = [d for d in (mt5.history_deals_get(position=pid) or []) if d.entry == 0]
                if ins:
                    p["comment"] = str(getattr(ins[0], "comment", "") or "")
                    p["magic"] = int(getattr(ins[0], "magic", 0) or 0)
            except Exception:
                pass
        src, sess = classify(p["magic"], p["comment"])
        out.append({"close_time": p["close_time"], "net": round(p["net"], 2),
                    "symbol": p["symbol"], "source": src, "session_id": sess})
    out.sort(key=lambda x: x["close_time"])
    return out


def consecutive_losses(trades: list[dict]) -> int:
    """Seria curenta de pierderi (ca engine/portfolio: pierdere +1, altfel reset)."""
    n = 0
    for t in trades:
        n = n + 1 if t["net"] < 0 else 0
    return n


# ── Decizia unica: se poate deschide un ordin NOU? ─────────────────────────

def _profile_start_balance() -> float | None:
    try:
        with open(PROFILE_FILE, encoding="utf-8") as f:
            return float(json.load(f).get("start_balance"))
    except Exception:
        return None


def check_open(mt5, engine: str, symbol: str, session_key: str | None = None,
               session_cb: int = 0, settings: dict | None = None,
               trades_today: list | None = None) -> tuple[bool, str]:
    """
    (ok, motiv). Apelat de AMBELE engine-uri inainte de a plasa un ordin NOU.
    Nu inchide nimic — blocheaza doar expunerea noua. Erori MT5 → permis
    (fail-open: o eroare de citire nu blocheaza un engine care oricum nu poate
    plasa fara MT5; regulile existente per sesiune/piata raman active).
    engine: "bot" | "ai". session_cb: circuit breaker-ul sesiunii (0 = oprit).
    """
    s = settings if settings is not None else load_settings()
    try:
        cp = s["capital_protection"]
        if cp["enabled"]:
            acc = mt5.account_info()
            start = cp["start_balance"] or _profile_start_balance()
            if acc is not None and start:
                limit = start * cp["threshold_pct"] / 100.0
                if float(acc.equity) < limit:
                    return False, (f"PROTECTIE CAPITAL: equity {acc.equity:.2f}$ sub "
                                   f"{limit:.2f}$ ({cp['threshold_pct']:.0f}% din {start:.2f}$)")

        cb = s["circuit_breaker"]
        need_hist = cb["enabled"] or (engine == "bot" and session_cb and session_key)
        if need_hist:
            trades = trades_today if trades_today is not None else closed_today(mt5)
            if cb["enabled"]:
                n = consecutive_losses(trades)
                if n >= cb["max_consecutive_losses"]:
                    return False, (f"CIRCUIT BREAKER GLOBAL: {n} pierderi consecutive azi "
                                   f"pe cont (limita {cb['max_consecutive_losses']})")
                if cb["max_daily_loss_pct"] > 0:
                    acc = mt5.account_info()
                    day_net = sum(t["net"] for t in trades)
                    if acc is not None and day_net < 0:
                        start_day = float(acc.balance) - day_net
                        if start_day > 0 and -day_net / start_day * 100 >= cb["max_daily_loss_pct"]:
                            return False, (f"CIRCUIT BREAKER GLOBAL: pierdere azi {day_net:.2f}$ "
                                           f"(≥{cb['max_daily_loss_pct']:.1f}% din balanta zilei)")
            if engine == "bot" and session_cb and session_key:
                own = [t for t in trades if t["source"] == "bot" and t["session_id"] == session_key]
                n = consecutive_losses(own)
                if n >= int(session_cb):
                    return False, (f"CIRCUIT BREAKER {session_key}: {n} pierderi consecutive "
                                   f"azi (limita {int(session_cb)})")

        mc = s["max_concurrent_per_market"]
        if mc["enabled"]:
            n = len(mt5.positions_get(symbol=symbol) or ()) + len(mt5.orders_get(symbol=symbol) or ())
            if n >= mc["max"]:
                return False, (f"POZITII SIMULTANE GLOBAL: {n} pozitii/ordine pe {symbol} "
                               f"pe tot contul (max {mc['max']})")
    except Exception as e:   # fail-open
        return True, f"global_guard eroare (permis): {e}"
    return True, ""


def news_window_active(symbol: str, events: list[dict], now_utc: datetime | None = None,
                       settings: dict | None = None) -> list[dict]:
    """AI Engine: evenimentele active acum pentru `symbol` dupa news_protection GLOBAL."""
    s = settings if settings is not None else load_settings()
    np_ = s["news_protection"]
    if not np_["enabled"] or not events:
        return []
    from live.news_guard import events_active_at, market_currencies
    return events_active_at(events, now_utc or datetime.utcnow(), market_currencies([symbol]),
                            np_["impact_level"], np_["pre_minutes"], np_["post_minutes"])
