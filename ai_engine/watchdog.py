"""
ai_engine.watchdog — supervizorul motorului AI: il PORNESTE la boot si il
reporneste daca moare.

Rulare (detasat):  python -m ai_engine.watchdog

Redesign 2026-08-08 (bug: bat-ul de autostart ingheta pe pauzele `ping` la boot,
deci watchdog-ul — care era lansat DUPA acele pauze — nu pornea niciodata si
nimic nu repornea motorul). Acum bat-ul lanseaza DOAR watchdog-ul, imediat, fara
pauze lungi; asteptarea MT5/Ollama e MUTATA AICI, in Python (fiabil):

  FAZA BOOT (max BOOT_WINDOW_S): porneste motorul imediat si reincearca agresiv.
    engine.run() iese instant daca Ollama SAU MT5 nu sunt gata (nu are retry
    propriu) → lasand PID-ul stale (proces mort), deci detectam corect si
    reincercam pana "prinde". Aceste reincercari de boot NU consuma bugetul de
    crash-loop din steady-state.
  FAZA STEADY-STATE: verificare la CHECK_S; daca motorul moare → restart, max
    MAX_RESTARTS (protectie la crash-loop), cu notificare Telegram.

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

ROOT          = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PID_FILE      = os.path.join(AI_DATA, "ai_engine.pid")
WD_PID_FILE   = os.path.join(AI_DATA, "watchdog.pid")
LOG_FILE      = os.path.join(AI_DATA, "watchdog.log")

# Faza de boot: porneste motorul si asteapta MT5/Ollama prin retry.
BOOT_WINDOW_S = 900   # cat timp incercam agresiv sa pornim motorul dupa boot (15 min)
BOOT_RETRY_S  = 20    # pauza dupa o lansare, inainte de recheck (motorul isi scrie PID-ul devreme)
STICK_S       = 90    # cat trebuie sa ramana viu neintrerupt ca sa consideram boot reusit
                      # (> timpul pana intra in bucla: sonda Ollama ~35s + connect MT5)
STICK_POLL_S  = 10    # granularitatea verificarii de stabilitate (prinde crash-ul rapid)

# Faza steady-state: monitorizare normala + protectie la crash-loop.
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


def _engine_stable(stick_s: float = STICK_S, poll_s: float = STICK_POLL_S) -> bool:
    """True daca motorul ramane viu neintrerupt `stick_s` secunde.

    engine.run() scrie PID-ul devreme, apoi poate iesi (MT5/Ollama neready) dupa
    ~35-45s (dupa sonda Ollama, la connect MT5). Confirmarea ca a "prins" =
    ramane viu peste acest prag. Poll-ul scurt prinde un crash devreme, ca sa
    reincercam imediat, nu dupa tot intervalul.
    """
    deadline = time.time() + stick_s
    while time.time() < deadline:
        if not _engine_alive():
            return False
        time.sleep(poll_s)
    return _engine_alive()


def _start_engine() -> None:
    subprocess.Popen(
        [sys.executable, "-m", "ai_engine"],
        cwd=ROOT,
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True,
    )


def _notify(text: str) -> None:
    try:
        from api.telegram import send_message
        send_message(text)
    except Exception:
        pass


def _boot_phase() -> bool:
    """Porneste motorul la boot, reincercand pana "prinde" sau pana expira
    fereastra. Returneaza True daca motorul e viu si stabil la iesire."""
    deadline = time.time() + BOOT_WINDOW_S
    attempts = 0
    while True:
        if _engine_alive():
            if _engine_stable():
                _log(f"motor pornit si STABIL (dupa {attempts} incercari de boot)")
                return True
            _log("motorul a iesit devreme (MT5/Ollama neready?) — reincerc")
        if time.time() >= deadline:
            return _engine_alive()
        attempts += 1
        _log(f"boot: pornesc motorul (incercare #{attempts})")
        _start_engine()
        time.sleep(BOOT_RETRY_S)   # lasa-l sa isi scrie PID-ul inainte de recheck


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

    _log(f"watchdog pornit (PID {os.getpid()}); pornesc motorul (fereastra boot {BOOT_WINDOW_S}s)")
    try:
        # ── FAZA BOOT: porneste motorul + asteapta MT5/Ollama prin retry ──
        booted = _boot_phase()
        if not booted:
            _log(f"motorul NU a pornit in fereastra de boot ({BOOT_WINDOW_S}s) — "
                 f"continui monitorizarea la {CHECK_S}s")
            _notify("🤖⚠ AI Engine nu a pornit in "
                    f"{BOOT_WINDOW_S // 60} min dupa boot (MT5/Ollama neready?). "
                    "Watchdog-ul incearca in continuare. Verifica MT5 + data/ai/autostart.log.")

        # ── FAZA STEADY-STATE: monitorizare + protectie la crash-loop ──
        _log(f"monitorizare steady-state la {CHECK_S}s")
        restarts = 0
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
            _start_engine()
            time.sleep(60)   # lasa-l sa porneasca inainte de urmatoarea verificare
    finally:
        try:
            os.remove(WD_PID_FILE)
        except OSError:
            pass


if __name__ == "__main__":
    main()
