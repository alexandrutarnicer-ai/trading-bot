"""
Bot watchdog — ruleaza ca daemon thread in API.
Detecteaza cand botul moare neasteptat (PID mort dar profil activ inca) si
trimite notificare Telegram.
Verifica si protectia capitalului (capital_protection_enabled in profil).
"""

import os
import json
import ctypes
import threading
import time
from datetime import datetime

from api.config import DATA_DIR, PID_FILE
from api import telegram as tg

ACTIVE_PROFILE_FILE  = os.path.join(DATA_DIR, "active_profile.json")
RUN_LOG_FILE         = os.path.join(DATA_DIR, "bot_run_log.json")
PROFILES_DIR         = os.path.join(DATA_DIR, "profiles")
PAUSED_SESSIONS_FILE = os.path.join(DATA_DIR, "paused_sessions.json")
NEWS_AUTO_PAUSED_FILE = os.path.join(DATA_DIR, "news_auto_paused.json")

_CHECK_INTERVAL = 30   # secunde intre verificari

# Retine profile_id-urile pentru care protectia a fost deja activata in sesiunea curenta.
# Se reseteaza cand equity revine peste prag sau cand botul se reporneste.
_protection_triggered: set = set()


def _pid_alive(pid: int) -> bool:
    try:
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if h:
            exit_code = ctypes.c_ulong()
            ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(exit_code))
            ctypes.windll.kernel32.CloseHandle(h)
            return exit_code.value == STILL_ACTIVE
    except Exception:
        pass
    return False


def _read_pid() -> int | None:
    try:
        return int(open(PID_FILE).read().strip())
    except Exception:
        return None


def _read_active_profile() -> dict | None:
    try:
        with open(ACTIVE_PROFILE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _cleanup_and_log() -> None:
    # Sterge active_profile.json
    try:
        if os.path.exists(ACTIVE_PROFILE_FILE):
            os.remove(ACTIVE_PROFILE_FILE)
    except Exception:
        pass
    # Sterge PID file daca mai exista
    try:
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
    except Exception:
        pass
    # Reseteaza news_auto_paused.json — la crash, run_all.py nu apuca sa il curete
    try:
        with open(NEWS_AUTO_PAUSED_FILE, "w", encoding="utf-8") as f:
            f.write("{}")
    except Exception:
        pass
    # Actualizeaza run log cu last_stopped_at
    try:
        log: dict = {}
        if os.path.exists(RUN_LOG_FILE):
            with open(RUN_LOG_FILE, encoding="utf-8") as f:
                log = json.load(f)
        log["last_stopped_at"] = datetime.now().isoformat()
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(RUN_LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(log, f)
    except Exception:
        pass


def _get_mt5_equity() -> float | None:
    """Returneaza equity-ul contului MT5 sau None daca nu poate fi citit."""
    try:
        import MetaTrader5 as mt5
        if not mt5.initialize():
            return None
        info = mt5.account_info()
        eq = float(info.equity) if info else None
        mt5.shutdown()
        return eq
    except Exception:
        return None


def _check_capital_protection(ap: dict) -> None:
    """Verifica daca equity MT5 a scazut sub pragul de protectie. Daca da, pauzeaza sesiunile."""
    global _protection_triggered
    profile_id = ap.get("id")
    if not profile_id:
        return

    profile_path = os.path.join(PROFILES_DIR, f"{profile_id}.json")
    if not os.path.exists(profile_path):
        return

    try:
        with open(profile_path, encoding="utf-8") as f:
            profile = json.load(f)
    except Exception:
        return

    if not profile.get("capital_protection_enabled", False):
        _protection_triggered.discard(profile_id)
        return

    threshold_pct   = float(profile.get("capital_protection_threshold_pct", 70.0))
    start_balance   = float(profile.get("start_balance", 1000))
    threshold_value = start_balance * threshold_pct / 100.0

    equity = _get_mt5_equity()
    if equity is None:
        return

    if equity >= threshold_value:
        _protection_triggered.discard(profile_id)
        return

    if profile_id in _protection_triggered:
        return  # deja notificat si pauza activata

    _protection_triggered.add(profile_id)

    sessions_to_pause = [
        s.get("session_key", "")
        for s in profile.get("sessions", [])
        if s.get("execute_trades", False)
    ]
    if not sessions_to_pause:
        return

    try:
        paused = json.load(open(PAUSED_SESSIONS_FILE, encoding="utf-8")) if os.path.exists(PAUSED_SESSIONS_FILE) else []
    except Exception:
        paused = []

    paused_set    = set(paused)
    newly_paused  = [s for s in sessions_to_pause if s and s not in paused_set]
    if not newly_paused:
        return

    paused_set.update(newly_paused)
    os.makedirs(DATA_DIR, exist_ok=True)
    try:
        with open(PAUSED_SESSIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(sorted(paused_set), f)
    except Exception:
        return

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    msg = (
        f"<b>Protectie Capital Activata</b>  {now_str}\n"
        f"Equity MT5: <b>{equity:.2f} $</b> (limita: {threshold_value:.2f} $, "
        f"{threshold_pct:.0f}% din {start_balance:.2f} $)\n"
        f"Sesiuni puse pe pauza: {', '.join(newly_paused)}"
    )
    tg.send_message(msg)
    try:
        from api.notifications import log_notification
        log_notification(msg)
    except Exception:
        pass


def _watchdog_loop() -> None:
    while True:
        time.sleep(_CHECK_INTERVAL)
        try:
            ap = _read_active_profile()
            if ap is None:
                continue   # bot nu era pornit sau deja curatat

            pid = _read_pid()
            if pid is None or not _pid_alive(pid):
                # Botul era activ (active_profile.json exista) dar procesul e mort
                profile_name = ap.get("name") or "necunoscut"
                started_at   = ap.get("started_at", "")
                now_str      = datetime.now().strftime("%Y-%m-%d %H:%M")
                tg.send_message(
                    f"<b>Bot Trading oprit neasteptat!</b>  {now_str}\n"
                    f"Profil: {profile_name}\n"
                    f"Pornit la: {started_at[:16] if started_at else '?'}\n"
                    f"<i>Botul a cazut fara oprire manuala. Verifica logurile si reporneste.</i>"
                )
                _cleanup_and_log()
                continue  # nu mai verifica protectia daca botul e oprit

            # Bot activ — verifica protectia capitalului
            _check_capital_protection(ap)
        except Exception:
            pass   # watchdog-ul nu crapa niciodata


def start_watchdog() -> None:
    t = threading.Thread(target=_watchdog_loop, daemon=True, name="bot-watchdog")
    t.start()
