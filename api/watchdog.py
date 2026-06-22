"""
Bot watchdog — ruleaza ca daemon thread in API.
Detecteaza cand botul moare neasteptat (PID mort dar profil activ inca) si
trimite notificare Telegram.
"""

import os
import ctypes
import threading
import time
from datetime import datetime

from api.config import DATA_DIR, PID_FILE
from api import telegram as tg

ACTIVE_PROFILE_FILE = os.path.join(DATA_DIR, "active_profile.json")
RUN_LOG_FILE        = os.path.join(DATA_DIR, "bot_run_log.json")

_CHECK_INTERVAL = 30   # secunde intre verificari


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
    import json
    try:
        with open(ACTIVE_PROFILE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _cleanup_and_log() -> None:
    import json
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
    # Actualizeaza run log cu last_stopped_at
    try:
        log = {}
        if os.path.exists(RUN_LOG_FILE):
            with open(RUN_LOG_FILE, encoding="utf-8") as f:
                log = json.load(f)
        log["last_stopped_at"] = datetime.now().isoformat()
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(RUN_LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(log, f)
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
        except Exception:
            pass   # watchdog-ul nu crapa niciodata


def start_watchdog() -> None:
    t = threading.Thread(target=_watchdog_loop, daemon=True, name="bot-watchdog")
    t.start()
