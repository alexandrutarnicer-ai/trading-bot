"""
ai_engine.watchdog — repornire automata a motorului AI daca moare.

Rulare (detasat):  python -m ai_engine.watchdog

La fiecare 5 min verifica PID-ul motorului; daca e mort → il reporneste
(max 5 restarturi per rulare de watchdog — protectie la crash-loop).
Log: data/ai/watchdog.log. PID propriu: data/ai/watchdog.pid (anti-duplicat).
Oprire intentionata a motorului: opreste INTAI watchdog-ul (taskkill pe
watchdog.pid sau din UI — butonul Stop opreste ambele daca watchdog-ul ruleaza).
"""

from __future__ import annotations

import os
import sys
import time
import ctypes
import subprocess
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ai_engine.config import AI_DATA

PID_FILE      = os.path.join(AI_DATA, "ai_engine.pid")
WD_PID_FILE   = os.path.join(AI_DATA, "watchdog.pid")
LOG_FILE      = os.path.join(AI_DATA, "watchdog.log")
CHECK_S       = 300
MAX_RESTARTS  = 5


def _log(msg: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')} {msg}"
    print(line)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def _pid_alive(pid: int) -> bool:
    try:
        STILL_ACTIVE = 259
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(h)
        return bool(ok) and code.value == STILL_ACTIVE
    except Exception:
        return False


def _engine_alive() -> bool:
    try:
        with open(PID_FILE) as f:
            return _pid_alive(int(f.read().strip()))
    except (OSError, ValueError):
        return False


def _notify(text: str) -> None:
    try:
        from api.telegram import send_message
        send_message(text)
    except Exception:
        pass


def main() -> None:
    # anti-duplicat: daca alt watchdog ruleaza, iesim
    try:
        with open(WD_PID_FILE) as f:
            old = int(f.read().strip())
        if _pid_alive(old):
            _log(f"alt watchdog activ (PID {old}) — ies")
            return
    except (OSError, ValueError):
        pass
    with open(WD_PID_FILE, "w") as f:
        f.write(str(os.getpid()))

    _log(f"watchdog pornit (PID {os.getpid()}), verificare la {CHECK_S}s")
    restarts = 0
    try:
        while True:
            time.sleep(CHECK_S)
            if _engine_alive():
                continue
            if restarts >= MAX_RESTARTS:
                _log(f"motorul e mort dar am atins limita de {MAX_RESTARTS} restarturi — ma opresc")
                _notify("🤖⚠ AI Engine a cazut repetat — watchdog-ul s-a oprit dupa "
                        f"{MAX_RESTARTS} restarturi. Verifica data/ai/engine.log!")
                return
            restarts += 1
            _log(f"motor mort — restart #{restarts}/{MAX_RESTARTS}")
            _notify(f"🤖 AI Engine cazut — watchdog restart #{restarts}/{MAX_RESTARTS}")
            subprocess.Popen(
                [sys.executable, "-m", "ai_engine"],
                cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True,
            )
            time.sleep(60)   # lasa-l sa porneasca inainte de urmatoarea verificare
    finally:
        try:
            os.remove(WD_PID_FILE)
        except OSError:
            pass


if __name__ == "__main__":
    main()
