"""
live/news_guard.py — Protectie automata la stiri economice
==========================================================
Thread daemon pornit de run_all.py. Poll-eaza calendar la fiecare 5 min.
Scrie sesiunile afectate in data/news_auto_paused.json.
signal_generator.py citeste fisierul la fiecare bara si sare generarea
de semnale noi daca sesiunea e prezenta.

Surse calendar (in ordinea prioritatii):
  1. ForexFactory JSON (nfs.faireconomy.media) — primar, fara API key
  2. MT5 built-in calendar — backup, fara API key, necesita MT5 conectat
  3. Finnhub API — optional, necessita data/finnhub_config.json cu api_key

Configurare per sesiune (in profil):
  news_protection_enabled: bool  (default false)
  news_impact_level: int         (1=toate, 2=Medium+, 3=High only — default 3)
  news_pre_minutes: int          (minute inainte de eveniment — default 15)
  news_post_minutes: int         (minute dupa eveniment — default 15)
"""

import json
import logging
import os
import re
import threading
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Optional

ROOT             = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR         = os.path.join(ROOT, "data")
NEWS_PAUSED_FILE = os.path.join(DATA_DIR, "news_auto_paused.json")
FINNHUB_CFG_FILE = os.path.join(DATA_DIR, "finnhub_config.json")

POLL_INTERVAL = 300   # secunde intre iteratii
CACHE_TTL     = 270   # secunde TTL cache (expire inainte de urmatorul poll)

FF_URLS = [
    "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
    "https://nfs.faireconomy.media/ff_calendar_nextweek.json",
]

# Valutele afectate de fiecare simbol tranzactionat
SYMBOL_CURRENCIES: dict[str, list[str]] = {
    "EURUSD":  ["EUR", "USD"],
    "GBPUSD":  ["GBP", "USD"],
    "EURJPY":  ["EUR", "JPY"],
    "GBPJPY":  ["GBP", "JPY"],
    "USDJPY":  ["USD", "JPY"],
    "AUDJPY":  ["AUD", "JPY"],
    "NZDJPY":  ["NZD", "JPY"],
    "CADJPY":  ["CAD", "JPY"],
    "AUDUSD":  ["AUD", "USD"],
    "NZDUSD":  ["NZD", "USD"],
    "USDCAD":  ["USD", "CAD"],
    "USDCHF":  ["USD", "CHF"],
    "EURGBP":  ["EUR", "GBP"],
    "EURCHF":  ["EUR", "CHF"],
    "EURAUD":  ["EUR", "AUD"],
    "EURCAD":  ["EUR", "CAD"],
    "CHFJPY":  ["CHF", "JPY"],
    "GBPCAD":  ["GBP", "CAD"],
    "GBPAUD":  ["GBP", "AUD"],
    "AUDCAD":  ["AUD", "CAD"],
    "AUDNZD":  ["AUD", "NZD"],
    "NZDCAD":  ["NZD", "CAD"],
    "XRPUSD":  ["USD"],
    "BTCUSD":  ["USD"],
    "BTCUSDT": ["USD"],
    "ETHUSD":  ["USD"],
    "XAUUSD":  ["USD"],
    "XAGUSD":  ["USD"],
    # Indici — valuta tarii de origine
    "GER40":   ["EUR"],
    "DE30":    ["EUR"],
    "GER30":   ["EUR"],
    "US30":    ["USD"],
    "US500":   ["USD"],
    "SP500":   ["USD"],
    "NAS100":  ["USD"],
    "UK100":   ["GBP"],
    "FRA40":   ["EUR"],
    "JPN225":  ["JPY"],
}

# FF foloseste codul valutei direct (USD, EUR, ...) dar uneori tara (US -> USD)
FF_COUNTRY_FIX: dict[str, str] = {
    "USD": "USD", "EUR": "EUR", "GBP": "GBP", "JPY": "JPY",
    "AUD": "AUD", "NZD": "NZD", "CAD": "CAD", "CHF": "CHF",
    "CNY": "CNY", "CNH": "CNY",
}

# Finnhub: country code -> currency
FINNHUB_COUNTRY_CCY: dict[str, str] = {
    "US": "USD", "EU": "EUR", "GB": "GBP", "JP": "JPY",
    "AU": "AUD", "NZ": "NZD", "CA": "CAD", "CH": "CHF",
    "DE": "EUR", "FR": "EUR", "IT": "EUR", "ES": "EUR",
    "CN": "CNY",
}

IMPACT_RANK = {"High": 3, "Medium": 2, "Low": 1, "Non-Economic": 0, "Holiday": 0}

log = logging.getLogger("news_guard")


# ─── Sentimentul stirilor ─────────────────────────────────────────────────────

def _parse_number(s: str) -> float | None:
    """Parses strings like '216K', '-0.3%', '2.5B', '1.23' → float."""
    if not s:
        return None
    s = s.strip().replace(",", "").lstrip("+")
    try:
        if s.endswith("K"):
            return float(s[:-1]) * 1e3
        if s.endswith("M"):
            return float(s[:-1]) * 1e6
        if s.endswith("B"):
            return float(s[:-1]) * 1e9
        if s.endswith("%"):
            return float(s[:-1])
        return float(s)
    except (ValueError, TypeError):
        return None


def _calc_sentiment(actual_str: str, forecast_str: str) -> int:
    """
    +1 daca actual > forecast (valuta reportoare intarita),
    -1 daca actual < forecast, 0 daca necunoscut sau egal.
    Simplificat — nu tine cont de indicatori inversati (ex: somaj).
    """
    actual   = _parse_number(actual_str or "")
    forecast = _parse_number(forecast_str or "")
    if actual is None or forecast is None:
        return 0
    if actual > forecast:
        return 1
    if actual < forecast:
        return -1
    return 0


def news_direction_for_symbol(symbol: str, events: list[dict]) -> int:
    """
    Calculeaza directia neta a tranzactionarii pentru un simbol pe baza
    evenimentelor de stiri cu sentiment. Returneaza +1 (LONG), -1 (SHORT), 0 (neclar).

    Reguli forex:
      valuta_baza bullish (+1) → LONG perechea
      valuta_cotatie bullish (+1) → SHORT perechea
    Reguli indici/crypto (o singura valuta):
      valuta bullish (+1) → LONG indexul
    """
    sym = symbol.upper()
    currencies = SYMBOL_CURRENCIES.get(sym, [])
    if not currencies:
        return 0

    # Acumuleaza sentiment per valuta din evenimentele active
    currency_sentiment: dict[str, int] = {}
    for ev in events:
        ccy  = ev.get("currency", "")
        sent = ev.get("sentiment", 0)
        if ccy and sent != 0:
            # Daca exista conflicte (mai multi indicatori): anuleaza
            if ccy in currency_sentiment and currency_sentiment[ccy] != sent:
                currency_sentiment[ccy] = 0  # conflict → neclar
            else:
                currency_sentiment[ccy] = sent

    if len(currencies) == 1:
        # Index sau crypto (o singura valuta asociata)
        return currency_sentiment.get(currencies[0], 0)

    # Pereche forex: base = sym[:3], quote = sym[3:]
    base  = sym[:3]
    quote = sym[3:]
    s_base  = currency_sentiment.get(base,  0)
    s_quote = currency_sentiment.get(quote, 0)

    if s_base != 0 and s_quote == 0:
        return s_base        # baza intarita → LONG perechea
    if s_quote != 0 and s_base == 0:
        return -s_quote      # cotatie intarita → SHORT perechea
    if s_base != 0 and s_quote != 0 and s_base != -s_quote:
        return 0             # semnale contradictorii
    if s_base != 0:
        return s_base        # ambele confirma (ex: EUR+1 si USD-1 → LONG EURUSD)
    return 0


# ─── Cache ────────────────────────────────────────────────────────────────────

_lock:          threading.Lock = threading.Lock()
_cached:        list[dict]     = []
_cache_time:    Optional[datetime] = None


def _snapshot() -> list[dict]:
    with _lock:
        return list(_cached)


# ─── Parsare data ─────────────────────────────────────────────────────────────

def _to_utc(date_str: str) -> Optional[datetime]:
    """ISO 8601 string (cu sau fara offset) → UTC naive datetime."""
    if not date_str:
        return None
    try:
        s = date_str.strip().replace("Z", "+00:00")
        # normalizeaza -0500 → -05:00
        s = re.sub(r"([+-])(\d{2})(\d{2})$", r"\1\2:\3", s)
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except Exception:
        return None


# ─── Sursa 1: ForexFactory JSON ───────────────────────────────────────────────

def _fetch_forexfactory() -> list[dict]:
    """
    Descarca calendarul ForexFactory pentru saptamana curenta + urmatoarea.
    Fara API key. Endpoint neoficial dar stabil, folosit de mii de traderi.
    Returnate: eventi normalizati cu: title, currency, impact, event_time (UTC naive).
    """
    events: list[dict] = []
    for url in FF_URLS:
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; TradingBot/1.0)"}
            )
            with urllib.request.urlopen(req, timeout=15) as r:
                raw: list[dict] = json.loads(r.read())

            for ev in raw:
                ev_time  = _to_utc(ev.get("date", ""))
                currency = FF_COUNTRY_FIX.get(ev.get("country", "").upper(), "")
                if ev_time is None or not currency:
                    continue
                actual_s   = str(ev.get("actual",   "") or "").strip()
                forecast_s = str(ev.get("forecast", "") or "").strip()
                events.append({
                    "title":      ev.get("title", "Unknown"),
                    "currency":   currency,
                    "impact":     ev.get("impact", "Low"),
                    "event_time": ev_time,
                    "actual":     actual_s,
                    "forecast":   forecast_s,
                    "sentiment":  _calc_sentiment(actual_s, forecast_s),
                    "_source":    "ff",
                })
        except Exception as exc:
            log.warning(f"FF calendar ({url}): {exc}")

    return events


# ─── Sursa 2: MT5 built-in calendar ──────────────────────────────────────────

def _fetch_mt5() -> list[dict]:
    """
    Backup: calendarul economic built-in din MT5.
    Returneaza evenimentele HIGH importance programate in urmatoarele 24h.
    Avantaj: 0 dependente externe, merge offline daca MT5 e conectat la broker.
    """
    try:
        import MetaTrader5 as mt5

        now_utc   = datetime.utcnow()
        look_back = now_utc - timedelta(hours=2)
        look_fwd  = now_utc + timedelta(hours=24)

        defs = mt5.calendar_event_by_importance(3)  # 3 = HIGH
        if not defs:
            return []

        events: list[dict] = []
        seen:   set[str]   = set()

        for ev_def in defs:
            val = mt5.calendar_value_last_by_event_id(ev_def.id)
            if val is None:
                continue
            ev_time = datetime.utcfromtimestamp(val.time)
            if not (look_back <= ev_time <= look_fwd):
                continue
            key = f"{ev_def.id}:{val.time}"
            if key in seen:
                continue
            seen.add(key)

            currency = getattr(ev_def, "currency", "") or ""
            if not currency:
                continue
            events.append({
                "title":      ev_def.name,
                "currency":   currency.upper(),
                "impact":     "High",
                "event_time": ev_time,
                "_source":    "mt5",
            })

        return events

    except Exception as exc:
        log.debug(f"MT5 calendar: {exc}")
        return []


# ─── Sursa 3: Finnhub (optional) ─────────────────────────────────────────────

def _finnhub_key() -> str:
    try:
        with open(FINNHUB_CFG_FILE, encoding="utf-8") as f:
            return json.load(f).get("api_key", "")
    except Exception:
        return ""


def _fetch_finnhub(api_key: str) -> list[dict]:
    """
    Optional: Finnhub economic calendar API.
    Tier gratuit: 60 req/min. Activat daca exista data/finnhub_config.json.
    Completeaza FF cu acoperire mai buna pentru unele piete emergente.
    """
    try:
        now_utc = datetime.utcnow()
        f_from  = (now_utc - timedelta(hours=2)).strftime("%Y-%m-%d")
        f_to    = (now_utc + timedelta(hours=24)).strftime("%Y-%m-%d")
        url     = (f"https://finnhub.io/api/v1/calendar/economic"
                   f"?from={f_from}&to={f_to}&token={api_key}")
        with urllib.request.urlopen(urllib.request.Request(url), timeout=10) as r:
            data = json.loads(r.read())

        events: list[dict] = []
        for ev in data.get("economicCalendar", []):
            impact_n = ev.get("impact", 1)
            impact_s = {3: "High", 2: "Medium", 1: "Low"}.get(impact_n, "Low")
            currency = FINNHUB_COUNTRY_CCY.get(ev.get("country", ""), "")
            ev_time  = _to_utc(ev.get("time", ""))
            if not currency or ev_time is None:
                continue
            events.append({
                "title":      ev.get("event", "Unknown"),
                "currency":   currency,
                "impact":     impact_s,
                "event_time": ev_time,
                "_source":    "finnhub",
            })
        return events

    except Exception as exc:
        log.warning(f"Finnhub calendar: {exc}")
        return []


# ─── Refresh cache ────────────────────────────────────────────────────────────

def _refresh() -> None:
    global _cached, _cache_time

    all_events: list[dict] = []

    # Sursa 1: ForexFactory (principala)
    ff = _fetch_forexfactory()
    if ff:
        all_events.extend(ff)
        log.info(f"[NEWS] FF: {len(ff)} evenimente")
    else:
        log.info("[NEWS] ForexFactory indisponibil — incerc MT5...")
        mt5_ev = _fetch_mt5()
        if mt5_ev:
            all_events.extend(mt5_ev)
            log.info(f"[NEWS] MT5 calendar: {len(mt5_ev)} HIGH in 24h")
        else:
            log.warning("[NEWS] Ambele surse primare indisponibile.")

    # Sursa 3: Finnhub (optional, suplimentar daca e configurat)
    fk = _finnhub_key()
    if fk:
        fh = _fetch_finnhub(fk)
        if fh:
            all_events.extend(fh)
            log.info(f"[NEWS] Finnhub: {len(fh)} evenimente")

    # Deduplicare pe (currency, title_prefix, ora)
    seen: set[str]      = set()
    unique: list[dict]  = []
    for ev in all_events:
        key = f"{ev['currency']}:{ev['title'][:25]}:{ev.get('event_time', '')}"
        if key not in seen:
            seen.add(key)
            unique.append(ev)

    with _lock:
        _cached     = unique
        _cache_time = datetime.utcnow()

    log.info(f"[NEWS] Cache actualizat: {len(unique)} evenimente unice")


def _needs_refresh() -> bool:
    with _lock:
        if _cache_time is None:
            return True
        return (datetime.utcnow() - _cache_time).total_seconds() > CACHE_TTL


# ─── Verificare protectie per sesiune ─────────────────────────────────────────

def active_events_for(
    markets:      list[str],
    impact_min:   int = 3,
    pre_minutes:  int = 15,
    post_minutes: int = 15,
) -> list[dict]:
    """
    Returneaza evenimentele active din fereastra de protectie pentru pietele date.
    Lista goala = nicio protectie necesara acum.
    """
    currencies: set[str] = set()
    for m in markets:
        currencies.update(SYMBOL_CURRENCIES.get(m.upper(), []))
    if not currencies:
        return []

    now_utc      = datetime.utcnow()
    window_start = now_utc - timedelta(minutes=post_minutes)
    window_end   = now_utc + timedelta(minutes=pre_minutes)

    active: list[dict] = []
    for ev in _snapshot():
        if IMPACT_RANK.get(ev.get("impact", "Low"), 0) < impact_min:
            continue
        if ev.get("currency") not in currencies:
            continue
        ev_time = ev.get("event_time")
        if not isinstance(ev_time, datetime):
            continue
        if window_start <= ev_time <= window_end:
            mins_to = round((ev_time - now_utc).total_seconds() / 60)
            active.append({
                "title":      ev["title"],
                "currency":   ev["currency"],
                "impact":     ev["impact"],
                "event_time": ev_time.strftime("%Y-%m-%dT%H:%M:%S"),
                "minutes_to": mins_to,
                "actual":     ev.get("actual",   ""),
                "forecast":   ev.get("forecast", ""),
                "sentiment":  ev.get("sentiment", 0),
            })

    return active


# ─── news_auto_paused.json ────────────────────────────────────────────────────

def _load_state() -> dict:
    try:
        with open(NEWS_PAUSED_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(NEWS_PAUSED_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def clear_all() -> None:
    """Sterge fisierul de pauza news — apelat la oprire bot."""
    try:
        if os.path.exists(NEWS_PAUSED_FILE):
            os.remove(NEWS_PAUSED_FILE)
            log.info("[NEWS] news_auto_paused.json sters la oprire.")
    except Exception:
        pass


# ─── Guard loop ───────────────────────────────────────────────────────────────

def run_guard(session_configs: list[dict], send_telegram=None) -> None:
    """
    Loop principal. Ruleaza ca thread daemon.

    session_configs: lista de dicts cu:
      session_key, markets, news_protection_enabled,
      news_impact_level, news_pre_minutes, news_post_minutes
    send_telegram: callable(html_str) pentru notificari Telegram — optional
    """
    active_count = sum(1 for s in session_configs if s.get("news_protection_enabled"))
    log.info(f"[NEWS GUARD] Pornit — {active_count}/{len(session_configs)} sesiuni cu protectie activa")

    # Reset stare veche la startup. Fara asta, un restart dupa crash lasa sesiunile
    # blocate pe o stire expirata. Primul poll (max 5 min) repopuleaza daca e nevoie.
    try:
        _save_state({})
    except Exception:
        pass

    _notified: dict[str, str] = {}  # session_key -> cheie eveniment notificat

    while True:
        try:
            if _needs_refresh():
                _refresh()
        except Exception as exc:
            log.error(f"[NEWS GUARD] Refresh esuat: {exc}")

        try:
            state   = _load_state()
            changed = False

            for scfg in session_configs:
                sk = scfg.get("session_key", "")
                if not sk:
                    continue

                if not scfg.get("news_protection_enabled", False):
                    if sk in state:
                        del state[sk]
                        changed = True
                    continue

                active = active_events_for(
                    markets      = scfg.get("markets", []),
                    impact_min   = scfg.get("news_impact_level", 3),
                    pre_minutes  = scfg.get("news_pre_minutes", 15),
                    post_minutes = scfg.get("news_post_minutes", 15),
                )

                if active:
                    was_paused = sk in state
                    state[sk]  = {
                        "paused_at": datetime.utcnow().isoformat(),
                        "events":    active,
                    }
                    changed = True

                    if not was_paused and send_telegram:
                        top    = active[0]
                        mins   = top["minutes_to"]
                        timing = (f"in {mins} min" if mins >= 0 else f"acum {abs(mins)} min in urma")
                        nkey   = f"{top['title'][:30]}:{top['event_time'][:13]}"
                        if _notified.get(sk) != nkey:
                            _notified[sk] = nkey
                            try:
                                send_telegram(
                                    f"⚠️ <b>Protectie stiri — {sk.upper()} suspendat</b>\n"
                                    f"Eveniment: <b>{top['title']}</b>\n"
                                    f"Valuta: {top['currency']} | Impact: {top['impact']}\n"
                                    f"Programat: {timing}\n"
                                    f"Semnale noi suspendate temporar."
                                )
                            except Exception:
                                pass
                else:
                    if sk in state:
                        del state[sk]
                        changed = True
                        if _notified.pop(sk, None) and send_telegram:
                            try:
                                send_telegram(
                                    f"✅ <b>Protectie stiri — {sk.upper()} reluata</b>\n"
                                    f"Fereastra evenimentului a trecut."
                                )
                            except Exception:
                                pass

            if changed:
                _save_state(state)

        except Exception as exc:
            log.error(f"[NEWS GUARD] Iteratie esuata: {exc}")

        time.sleep(POLL_INTERVAL)


def start_guard(session_configs: list[dict], send_telegram=None) -> threading.Thread:
    """Porneste guardul ca thread daemon si returneaza thread-ul."""
    t = threading.Thread(
        target=run_guard,
        args=(session_configs, send_telegram),
        daemon=True,
        name="NewsGuard",
    )
    t.start()
    return t
