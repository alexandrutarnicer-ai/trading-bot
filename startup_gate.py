"""Pornire automata CONDITIONATA de dependente (23.11.2026) — rulat de task-ul Windows la login, in locul .bat-urilor cu
`ping` (care inghetau la boot: incidentul AI Engine 18.07 / recurent).

    python -m startup_gate --engine daily|ai|app [--min-delay 60] [--max-wait 1200]

Pasii: (1) intarziere minima dupa login (Windows / retea / MT5 apuca sa porneasca); (2) asteapta dependentele, cu
reincercari tot mai rare (15 s → 60 s) pana la `max_wait`: internet, MT5 (terminal pornit + conectat la broker + cont
autentificat — initialize() porneste si terminalul daca e oprit), Ollama pentru AI (pornit automat o data daca nu
raspunde), configuratia engine-ului citibila; (3) engine-ul deja pornit → nimic (fara dubluri); (4) pornire prin
ACEEASI functie ca butonul din Dashboard (watchdog-urile / desired_running raman valabile) + verificare ca procesul
traieste; (5) notificare: succes cu ce s-a verificat SAU incident critic „nu a pornit” (engine-ul ramane OPRIT —
stare sigura; nimic nu porneste doar pentru ca a expirat intarzierea).

Engine-urile isi refac singure starea la pornire din MT5 (pozitii / ordine proprii dupa magic + comment; Daily arma ziua
doar inainte de formarea intervalului; piete pe Pauza raman pe Pauza). Noisy NU are autostart (refuzat explicit).
Setari: data/autostart_config.json {"<engine>": {"min_delay_s": .., "max_wait_s": ..}}.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
import urllib.request
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
DATA = os.path.join(ROOT, "data")
CONFIG_FILE = os.path.join(DATA, "autostart_config.json")

ENGINES: dict[str, dict] = {
    "daily": {"label": "Daily Engine", "mt5": True, "ollama": False, "log": os.path.join(DATA, "daily_engine", "autostart.log"),
              "min_delay_s": 60, "max_wait_s": 1200},
    "ai":    {"label": "AI Engine", "mt5": True, "ollama": True, "log": os.path.join(DATA, "ai", "autostart.log"),
              "min_delay_s": 75, "max_wait_s": 1500},
    "app":   {"label": "Aplicația (API + monitorizare)", "mt5": False, "ollama": False,
              "log": os.path.join(DATA, "app_autostart.log"), "min_delay_s": 20, "max_wait_s": 600},
}
try:                                   # Special Engine (DOAR alex-live) — acelasi mecanism
    import special_engine  # noqa: F401
    ENGINES["special"] = {"label": "Special Engine", "mt5": True, "ollama": False,
                          "log": os.path.join(DATA, "special_engine", "autostart.log"), "min_delay_s": 60, "max_wait_s": 1200}
except Exception:
    pass
REFUSED = {"noisy": "Noisy Engine NU are autostart (pornire doar manuală, cu confirmare)"}
_sleep = time.sleep          # teste: inlocuit


def _cfg(eid: str) -> dict:
    e = dict(ENGINES[eid])
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            e.update({k: v for k, v in (json.load(f).get(eid) or {}).items() if k in ("min_delay_s", "max_wait_s")})
    except Exception:
        pass
    return e


def _log(e: dict, msg: str) -> None:
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line, flush=True)
    try:
        os.makedirs(os.path.dirname(e["log"]), exist_ok=True)
        with open(e["log"], "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


# ── dependente ──────────────────────────────────────────────────────────────────────────────────────────────────────
def check_internet() -> tuple[bool, str]:
    for host in ("1.1.1.1", "8.8.8.8"):
        try:
            with socket.create_connection((host, 443), timeout=4):
                return True, "internet"
        except OSError:
            continue
    return False, "internet indisponibil"


def check_mt5() -> tuple[bool, str]:
    try:
        import MetaTrader5 as mt5
    except Exception as ex:  # noqa: BLE001
        return False, f"MetaTrader5 indisponibil: {ex}"
    try:
        if not mt5.initialize():
            return False, f"MT5 nu pornește / nu răspunde ({mt5.last_error()})"
        ti, acc = mt5.terminal_info(), mt5.account_info()
        if ti is None or acc is None:
            return False, "MT5 pornit, dar contul nu e autentificat"
        if not getattr(ti, "connected", True):
            return False, f"MT5 neconectat la serverul brokerului ({acc.server})"
        return True, f"MT5 cont #{acc.login} conectat ({'DEMO' if acc.trade_mode == 0 else 'REAL'})"
    except Exception as ex:  # noqa: BLE001
        return False, f"MT5: {ex}"
    finally:
        try:
            mt5.shutdown()
        except Exception:
            pass


def check_ollama() -> tuple[bool, str]:
    try:
        from ai_engine.config import load_config
        url = (load_config().get("providers", {}).get("ollama") or {}).get("base_url") or "http://127.0.0.1:11434"
    except Exception:
        url = "http://127.0.0.1:11434"
    try:
        with urllib.request.urlopen(f"{url}/api/tags", timeout=5) as r:
            n = len(json.loads(r.read()).get("models", []))
            return (True, f"Ollama ({n} modele)") if n else (False, "Ollama pornit, dar fără modele")
    except Exception as ex:  # noqa: BLE001
        return False, f"Ollama nu răspunde ({type(ex).__name__})"


def check_config(eid: str) -> tuple[bool, str]:
    try:
        if eid == "daily":
            from daily_engine.config import load_config
            load_config()
        elif eid == "ai":
            from ai_engine.config import load_config
            load_config()
        elif eid == "special":
            from special_engine.config import load_config
            load_config()
        return True, "configurație validă"
    except Exception as ex:  # noqa: BLE001
        return False, f"configurație invalidă: {ex}"


def running(eid: str) -> int | None:
    from api.health_monitor import _pid_alive, _read_pid
    if eid == "app":
        try:
            with urllib.request.urlopen("http://127.0.0.1:8000/api/health", timeout=3):
                return -1
        except Exception:
            return None
    pid_file = {"daily": os.path.join(DATA, "daily_engine", "daily_engine.pid"), "ai": os.path.join(DATA, "ai", "ai_engine.pid"),
                "special": os.path.join(DATA, "special_engine", "special_engine.pid")}[eid]
    pid = _read_pid(pid_file)
    return pid if pid and _pid_alive(pid) else None


def launch(eid: str) -> None:
    if eid == "daily":
        from api.routers.daily_engine import daily_start
        daily_start()
    elif eid == "ai":
        from api.routers.ai_engine import ai_start
        ai_start()
    elif eid == "special":
        from api.routers.special_engine import special_start
        special_start()
    elif eid == "app":
        import subprocess
        subprocess.Popen([sys.executable, "-m", "uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", "8000"], cwd=ROOT,
                         creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                         stdout=open(os.path.join(DATA, "app_stdout.log"), "a"), stderr=subprocess.STDOUT, close_fds=True)


# ── fluxul ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def run(eid: str, min_delay: float | None = None, max_wait: float | None = None) -> int:
    import incidents
    if eid in REFUSED:
        print(REFUSED[eid])
        return 2
    if eid not in ENGINES:
        print(f"engine necunoscut: {eid} (cunoscute: {', '.join(ENGINES)})")
        return 2
    e = _cfg(eid)
    min_delay = e["min_delay_s"] if min_delay is None else min_delay
    max_wait = e["max_wait_s"] if max_wait is None else max_wait
    _log(e, f"===== autostart {e['label']} — întârziere minimă {min_delay}s, așteptare dependențe max {max_wait}s =====")
    _sleep(min_delay)
    if running(eid):
        _log(e, "rulează deja — nimic de făcut (fără dublură)")
        return 0
    t0, wait, ollama_started, last = time.time(), 15.0, False, ""
    while True:
        checks: list[tuple[bool, str]] = []
        if e["mt5"]:
            checks.append(check_internet())
            checks.append(check_mt5())
        if e["ollama"]:
            ok, why = check_ollama()
            if not ok and not ollama_started and time.time() - t0 > 30:
                from api.health_monitor import start_ollama
                ollama_started = start_ollama()
                why += " — am pornit Ollama" if ollama_started else ""
            checks.append((ok, why))
        if eid != "app":
            checks.append(check_config(eid))
        bad = [w for ok, w in checks if not ok]
        if not bad:
            break
        msg = "; ".join(bad)
        if msg != last:
            _log(e, f"aștept: {msg}")
            last = msg
        if time.time() - t0 >= max_wait:
            _log(e, f"RENUNȚ după {int(max_wait // 60)} min — {msg}. Engine-ul rămâne OPRIT (stare sigură).")
            incidents.report(f"autostart:{eid}", f"{e['label']} NU a pornit automat după restart",
                             f"Dependențe nevalidate după {int(max_wait // 60)} min: {msg}.\nEngine-ul a rămas OPRIT (stare "
                             "sigură). Pornește-l din Dashboard după ce rezolvi problema.", "critical", "autostart")
            return 1
        _sleep(wait)
        wait = min(60.0, wait * 1.5)
    ok_txt = [w for _, w in checks]
    if running(eid):
        _log(e, "pornit între timp de altcineva — nimic de făcut")
        return 0
    try:
        launch(eid)
    except Exception as ex:  # noqa: BLE001
        _log(e, f"pornirea a eșuat: {ex}")
        incidents.report(f"autostart:{eid}", f"{e['label']} NU a pornit automat", f"Eroare la pornire: {ex}", "critical",
                         "autostart")
        return 1
    for _ in range(12):
        _sleep(2)
        if running(eid):
            break
    if not running(eid):
        _log(e, "procesul nu a rămas pornit")
        incidents.report(f"autostart:{eid}", f"{e['label']} NU a rămas pornit după autostart",
                         f"Dependențe OK ({'; '.join(ok_txt)}), dar procesul s-a oprit. Vezi jurnalul engine-ului.",
                         "critical", "autostart")
        return 1
    _log(e, "PORNIT — " + "; ".join(ok_txt))
    incidents.resolve(f"autostart:{eid}", checks=ok_txt)
    incidents.event(f"autostart_ok:{eid}", f"▶️ <b>{e['label']} pornit automat</b> (după login / restart)\nVerificat: "
                    + ("; ".join(ok_txt) or "—") + ".\nPozițiile și ordinele sunt re-citite din MT5 de engine; piețele pe Pauză "
                    "rămân pe Pauză.", "info", dedup_min=10)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", required=True)
    ap.add_argument("--min-delay", type=float)
    ap.add_argument("--max-wait", type=float)
    a = ap.parse_args()
    return run(a.engine, a.min_delay, a.max_wait)


if __name__ == "__main__":
    sys.exit(main())
