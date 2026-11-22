"""Incidente CENTRALE — un singur incident activ pe problema, notificari Telegram fara spam, recuperare confirmata,
persistent peste restart / crash (23.11.2026). Folosit de API (health monitor, watchdog), de autostart (startup_gate)
si de engine-uri (sursele AI). Pur Python; MT5 / Telegram nu sunt atinse la import.

Ciclul unui incident (cheie unica, ex. "mt5", "internet", "ollama", "engine:daily"):
  report(key, ...)   — problema e observata. Notificarea pleaca abia dupa `confirm_s` secunde de persistenta (un blip nu
                       trimite nimic); apoi REAMINTIRI rare cat timp persista (implicit 10 min, 30 min, apoi la 60 min,
                       maxim 6) — nu un mesaj la fiecare verificare.
  resolve(key, ...)  — problema a disparut, CONFIRMAT de apelant. Daca incidentul fusese notificat → mesaj de recuperare
                       cu durata + ce s-a verificat; daca era doar un blip (nenotificat) → nimic.
  event(key, ...)    — mesaj unic (restart aplicatie, sleep detectat, engine pornit automat), deduplicat pe fereastra.

Persistenta: data/incidents.json (activ + istoric + outbox), scris atomic sub un lock de fisier (mai multe procese).
Telegram indisponibil → mesajul ramane in OUTBOX si e retrimis la urmatorul apel (marcat „intarziat”, cu ora reala).
Incidentele sunt IMPORTANTE prin definitie → ocolesc modul liniste; raman si in tab-ul Notificari.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT, "data")
STATE_FILE = os.path.join(DATA_DIR, "incidents.json")
CONFIG_FILE = os.path.join(DATA_DIR, "incidents_config.json")
LOCK_FILE = STATE_FILE + ".lock"

DEFAULTS = {"reminders_min": [10, 30, 60], "max_reminders": 6, "event_dedup_min": 30, "outbox_max": 50,
            "history_max": 300}
SEV_ICON = {"critical": "🔴", "warning": "🟠", "info": "🔵"}

_send_override = None            # teste: functie(text) -> bool


# ── persistenta + lock ──────────────────────────────────────────────────────────────────────────────────────────────
class _Lock:
    def __init__(self, path: str, timeout: float = 5.0):
        self.path, self.timeout, self.fd = path, timeout, None

    def __enter__(self):
        end = time.time() + self.timeout
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        while True:
            try:
                self.fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                return self
            except FileExistsError:
                try:                                   # lock ramas de la un proces mort (> 30 s) → preluat
                    if time.time() - os.path.getmtime(self.path) > 30:
                        os.remove(self.path)
                        continue
                except OSError:
                    pass
                if time.time() > end:
                    return self                        # nu blocam niciodata apelantul: continuam fara lock
                time.sleep(0.05)

    def __exit__(self, *a):
        if self.fd is not None:
            try:
                os.close(self.fd)
                os.remove(self.path)
            except OSError:
                pass


def _cfg() -> dict:
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            return {**DEFAULTS, **json.load(f)}
    except Exception:
        return dict(DEFAULTS)


def _load() -> dict:
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            s = json.load(f)
        if isinstance(s, dict):
            s.setdefault("active", {})
            s.setdefault("history", [])
            s.setdefault("outbox", [])
            s.setdefault("events", {})
            return s
    except Exception:
        pass
    return {"active": {}, "history": [], "outbox": [], "events": {}}


def _save(s: dict) -> None:
    try:
        from safe_io import write_json_atomic
        write_json_atomic(STATE_FILE, s, critical=False)
    except Exception:
        try:
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(s, f, ensure_ascii=False, indent=1)
        except Exception:
            pass


# ── Telegram (direct, cu rezultat) ──────────────────────────────────────────────────────────────────────────────────
def _creds() -> tuple[str, str]:
    try:
        with open(os.path.join(DATA_DIR, "telegram_config.json"), encoding="utf-8") as f:
            c = json.load(f)
        if c.get("token") and c.get("chat_id"):
            return str(c["token"]).strip(), str(c["chat_id"]).strip()
    except Exception:
        pass
    return os.environ.get("TELEGRAM_TOKEN", "").strip(), os.environ.get("TELEGRAM_CHAT_ID", "").strip()


def _telegram(text: str) -> bool:
    if _send_override is not None:
        return bool(_send_override(text))
    token, chat = _creds()
    if not token or not chat:
        return False
    try:
        req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage",
                                     data=json.dumps({"chat_id": chat, "text": text, "parse_mode": "HTML"}).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.status == 200
    except Exception:
        return False


def _log_ui(text: str) -> None:
    try:
        from api.notifications import log_notification
        log_notification(text)
    except Exception:
        pass


def _deliver(s: dict, text: str, key: str) -> bool:
    """Trimite; la esec pune in outbox (cu ora reala). Intoarce True daca a plecat acum."""
    _log_ui(text)
    if _telegram(text):
        return True
    ob = s.setdefault("outbox", [])
    ob.append({"key": key, "text": text, "at": _now_iso()})
    del ob[:-_cfg()["outbox_max"]]
    s["outbox_next"] = time.time() + 60
    return False


def flush_outbox(s: dict | None = None) -> int:
    """Retrimite mesajele ramase (Telegram / internet indisponibil). Intoarce cate au plecat."""
    own = s is None
    if own:
        with _Lock(LOCK_FILE):
            s = _load()
            n = flush_outbox(s)
            _save(s)
            return n
    if not s.get("outbox") or time.time() < float(s.get("outbox_next", 0)):
        return 0                                        # cel mult o incercare / minut cat timp Telegram e indisponibil
    sent, keep = 0, []
    for m in s.get("outbox", []):
        txt = m["text"] + f"\n<i>(trimis întârziat — mesaj din {m['at'][:16].replace('T', ' ')})</i>"
        if _telegram(txt):
            sent += 1
        else:
            keep.append(m)
            break                                       # fara furtuna de cereri: oprim la primul esec
    s["outbox"] = keep + s.get("outbox", [])[sent + len(keep):]
    s["outbox_next"] = time.time() + 60 if keep else 0
    return sent


# ── API public ──────────────────────────────────────────────────────────────────────────────────────────────────────
def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _dur(sec: float) -> str:
    m = int(sec // 60)
    return f"{m // 60} h {m % 60} min" if m >= 60 else (f"{m} min" if m else f"{int(sec)} s")


def report(key: str, title: str, detail: str = "", severity: str = "warning", component: str = "",
           confirm_s: float = 0, reminders: bool = True, now: float | None = None) -> dict:
    """Problema e observata ACUM. Intoarce incidentul (cu `notified`)."""
    now = now or time.time()
    c = _cfg()
    with _Lock(LOCK_FILE):
        s = _load()
        if s.get("outbox"):
            flush_outbox(s)
        inc = s["active"].get(key)
        if inc is None:
            inc = {"key": key, "title": title, "component": component or key.split(":")[0], "severity": severity,
                   "first_seen": now, "first_seen_iso": _now_iso(), "notified": False, "reminders": 0, "last_sent": 0}
            s["active"][key] = inc
        inc.update(title=title, detail=detail, severity=severity, last_seen=now, reminders_on=reminders)
        icon = SEV_ICON.get(severity, "🟠")
        if not inc["notified"]:
            if now - inc["first_seen"] >= confirm_s:
                txt = f"{icon} <b>{title}</b>\n{detail}".rstrip()
                _deliver(s, txt, key)
                inc.update(notified=True, last_sent=now, notified_iso=_now_iso())
        elif reminders and inc["reminders"] < c["max_reminders"]:
            sched = c["reminders_min"]
            gap = sched[min(inc["reminders"], len(sched) - 1)] * 60
            if now - inc["last_sent"] >= gap:
                txt = (f"{icon} <b>Încă activ: {title}</b> — de {_dur(now - inc['first_seen'])}\n{detail}").rstrip()
                _deliver(s, txt, key)
                inc["reminders"] += 1
                inc["last_sent"] = now
        _save(s)
        return dict(inc)


def resolve(key: str, detail: str = "", checks: list[str] | None = None, now: float | None = None) -> bool:
    """Problema a disparut (CONFIRMAT de apelant). Intoarce True daca s-a trimis mesaj de recuperare."""
    now = now or time.time()
    with _Lock(LOCK_FILE):
        s = _load()
        inc = s["active"].pop(key, None)
        if inc is None:
            return False
        sent = False
        if inc.get("notified"):
            lines = [f"✅ <b>Rezolvat: {inc['title']}</b> — a durat {_dur(now - inc['first_seen'])} "
                     f"(de la {inc.get('first_seen_iso', '')[11:16]})"]
            if checks:
                lines.append("Verificat: " + " · ".join(checks))
            if detail:
                lines.append(detail)
            _deliver(s, "\n".join(lines), key)
            sent = True
        s["history"].append({**{k: v for k, v in inc.items() if k != "detail"}, "resolved": now,
                             "resolved_iso": _now_iso(), "duration_s": round(now - inc["first_seen"])})
        del s["history"][:-_cfg()["history_max"]]
        _save(s)
        return sent


def event(key: str, text: str, severity: str = "info", dedup_min: float | None = None, now: float | None = None) -> bool:
    """Mesaj unic (deduplicat pe fereastra). Intoarce True daca a fost trimis / pus in outbox."""
    now = now or time.time()
    win = (dedup_min if dedup_min is not None else _cfg()["event_dedup_min"]) * 60
    with _Lock(LOCK_FILE):
        s = _load()
        last = s["events"].get(key, 0)
        if now - last < win:
            return False
        s["events"][key] = now
        for k in [k for k, t in s["events"].items() if now - t > 7 * 86400]:
            s["events"].pop(k, None)
        _deliver(s, f"{SEV_ICON.get(severity, '🔵')} {text}", key)
        _save(s)
        return True


def active() -> dict:
    return _load()["active"]


def snapshot() -> dict:
    s = _load()
    return {"active": list(s["active"].values()), "history": s["history"][-50:], "outbox": len(s.get("outbox", []))}


def is_active(key: str) -> bool:
    return key in _load()["active"]
