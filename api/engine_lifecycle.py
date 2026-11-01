"""
Engine Lifecycle — management COMUN pentru toate engine-urile (Custom / AI / Daily).

Un singur contract pentru UI: status real, start/stop cu VERIFICARE, autostart Windows.
Nu rescrie mecanismele existente — DELEGA la ele (bot.py / ai_engine.py / daily_engine.py),
care raman sursa de adevar si sunt deja testate in productie:

  GET  /engines                          — status real al tuturor engine-urilor (+ autostart)
  POST /engines/{id}/start               — porneste si VERIFICA ca procesul traieste (max ~12s)
  POST /engines/{id}/stop                — opreste si verifica
  GET  /engines/{id}/autostart           — task-ul Windows exista?
  POST /engines/{id}/autostart/enable    — scriptul de setup al engine-ului (UAC)
  POST /engines/{id}/autostart/disable   — scriptul de remove al engine-ului (UAC)

Running = PID viu (GetExitCodeProcess), niciodata doar un fisier de stare — UI-ul nu poate
spune "Running" pentru un engine oprit. Un start care nu prinde viata intoarce eroare cu
ultimele linii din jurnalul engine-ului.
"""
from __future__ import annotations

import os
import subprocess
import time

from fastapi import APIRouter, HTTPException

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")

ENGINES: dict[str, dict] = {
    "custom": {"label": "Custom Engine", "task": "TradingBot-RunAll",
               "setup": ["setup_autostart.ps1"], "remove": ["remove_autostart.ps1"],
               "log": os.path.join(ROOT, "data", "live_signals", "session1", "generator.log")},
    "ai":     {"label": "AI Engine", "task": "TradingBot-AIEngine",
               "setup": ["setup_autostart_ai.ps1"], "remove": ["remove_autostart_ai.ps1"],
               "log": os.path.join(ROOT, "data", "ai", "engine.log")},
    "daily":  {"label": "Daily Engine", "task": "TradingBot-DailyEngine",
               "setup": ["setup_autostart_engine.ps1", "-Engine", "daily"],
               "remove": ["remove_autostart_engine.ps1", "-Engine", "daily"],
               "log": os.path.join(ROOT, "data", "daily_engine", "engine.log")},
}

router = APIRouter(prefix="/engines", tags=["engines"])

_autostart_cache: dict = {"ts": 0.0, "data": {}}
_AUTOSTART_TTL = 30.0


def _engine(eid: str) -> dict:
    if eid not in ENGINES:
        raise HTTPException(404, f"Engine necunoscut: {eid}")
    return ENGINES[eid]


# ── delegare catre routerele existente ───────────────────────────────────────

def _status(eid: str) -> dict:
    if eid == "custom":
        from api.routers import bot
        s = bot.bot_status()
        return {"running": bool(s.running), "pid": s.pid,
                "detail": f"{s.sessions_active}/{s.sessions_total} sesiuni active"
                          + (f" · {s.sessions_paused} pe pauză" if s.sessions_paused else ""),
                "mode": "live" if s.running else None}
    if eid == "ai":
        from api.routers import ai_engine
        s = ai_engine.ai_status()
        # oprit -> status.json poate fi vechi; pietele vin din configuratia curenta
        mk = (s.get("markets") or []) if s.get("running") else ai_engine.load_config().get("markets", [])
        demo = s.get("account_is_demo")
        mode = s.get("mode")
        return {"running": bool(s.get("running")), "pid": s.get("pid"),
                "detail": f"{len(mk)} piețe" + (f" · {mode}" if mode else "")
                          + (" · CONT REAL" if demo is False else ""),
                "mode": mode}
    from api.routers import daily_engine
    s = daily_engine.daily_status()
    mk = [m.get("symbol") for m in (s.get("markets") or []) if m.get("symbol")]
    return {"running": bool(s.get("running")), "pid": s.get("pid"),
            "detail": (", ".join(mk) if mk else "GBPUSD, US500") + (" · EXECUȚIE" + ("" if (s.get("execution") or {}).get("active") else " (blocată)")
                                                                     if s.get("mode") == "execute" else " · shadow"),
            "mode": s.get("mode", "shadow")}


def _do_start(eid: str) -> None:
    if eid == "custom":
        from api.routers import bot
        # pagina lucreaza mereu pe profilul "standard" (selectorul de profil a fost eliminat)
        bot.start_bot({"profile_id": "standard", "profile_name": "Standard"})
    elif eid == "ai":
        from api.routers import ai_engine
        ai_engine.ai_start()
    else:
        from api.routers import daily_engine
        daily_engine.daily_start()


def _do_stop(eid: str) -> None:
    if eid == "custom":
        from api.routers import bot
        bot.stop_bot()
    elif eid == "ai":
        from api.routers import ai_engine
        ai_engine.ai_stop()
    else:
        from api.routers import daily_engine
        daily_engine.daily_stop()


def _log_tail(eid: str, n: int = 8) -> list[str]:
    try:
        with open(ENGINES[eid]["log"], encoding="utf-8", errors="replace") as f:
            return [ln.rstrip() for ln in f.readlines()[-n:]]
    except Exception:
        return []


def _wait_for(eid: str, running: bool, timeout_s: float) -> dict:
    deadline = time.time() + timeout_s
    st = _status(eid)
    while st["running"] != running and time.time() < deadline:
        time.sleep(0.75)
        st = _status(eid)
    return st


# ── autostart (o singura interogare PowerShell pentru toate task-urile, cache 30s) ───────

def _autostart_all(force: bool = False) -> dict[str, bool]:
    if not force and time.time() - _autostart_cache["ts"] < _AUTOSTART_TTL:
        return _autostart_cache["data"]
    names = ",".join(f"'{e['task']}'" for e in ENGINES.values())
    cmd = (f"@({names}) | ForEach-Object {{ if (Get-ScheduledTask -TaskName $_ -ErrorAction "
           f"SilentlyContinue) {{ \"$_=1\" }} else {{ \"$_=0\" }} }}")
    data = {}
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd],
                           capture_output=True, text=True, timeout=15)
        found = dict(line.strip().split("=", 1) for line in r.stdout.splitlines() if "=" in line)
        data = {eid: found.get(e["task"]) == "1" for eid, e in ENGINES.items()}
    except Exception:
        data = {eid: None for eid in ENGINES}
    _autostart_cache.update(ts=time.time(), data=data)
    return data


def _run_elevated(script_args: list[str]) -> None:
    script = os.path.join(SCRIPTS, script_args[0])
    if not os.path.exists(script):
        raise HTTPException(404, f"scripts/{script_args[0]} nu a fost gasit")
    extra = " ".join(script_args[1:])
    subprocess.Popen([
        "powershell", "-Command",
        f"Start-Process powershell -Verb RunAs -ArgumentList "
        f"'-NoExit -ExecutionPolicy Bypass -File \"{script}\" {extra}'"])
    _autostart_cache["ts"] = 0.0          # urmatorul status reinterogheaza Task Scheduler


# ── endpoints ────────────────────────────────────────────────────────────────

@router.get("")
def engines_status():
    auto = _autostart_all()
    out = []
    for eid, e in ENGINES.items():
        try:
            st = _status(eid)
            err = None
        except Exception as ex:                 # un engine stricat nu blocheaza restul
            st, err = {"running": False, "pid": None, "detail": "", "mode": None}, str(ex)
        out.append({"id": eid, "label": e["label"], **st, "autostart": auto.get(eid), "error": err})
    return out


@router.post("/{eid}/start")
def engine_start(eid: str):
    _engine(eid)
    if _status(eid)["running"]:
        raise HTTPException(409, f"{ENGINES[eid]['label']} rulează deja")
    import device_owner
    other = device_owner.other_device_running()
    if other:      # engine-urile sunt preluate de celalalt dispozitiv -> ordine duble pe acelasi cont
        raise HTTPException(409, f"Engine-urile rulează pe {other}. Ca să le muți aici: pe {other} "
                                 f"schimb_dispozitiv.bat → Predau, apoi aici → Preiau.")
    _do_start(eid)
    st = _wait_for(eid, True, 12.0)
    if not st["running"]:
        tail = _log_tail(eid)
        raise HTTPException(500, {"message": f"{ENGINES[eid]['label']} nu a pornit (procesul nu e viu "
                                             f"după 12s). Vezi jurnalul.", "log_tail": tail})
    return {"ok": True, **st}


@router.post("/{eid}/stop")
def engine_stop(eid: str):
    _engine(eid)
    if not _status(eid)["running"]:
        raise HTTPException(409, f"{ENGINES[eid]['label']} nu rulează")
    _do_stop(eid)
    st = _wait_for(eid, False, 8.0)
    if st["running"]:
        raise HTTPException(500, f"{ENGINES[eid]['label']} încă rulează după oprire (PID {st['pid']})")
    return {"ok": True, **st}


@router.get("/{eid}/autostart")
def engine_autostart_status(eid: str):
    _engine(eid)
    return {"enabled": _autostart_all(force=True).get(eid)}


@router.post("/{eid}/autostart/enable")
def engine_autostart_enable(eid: str):
    _run_elevated(_engine(eid)["setup"])
    return {"started": True, "note": "Confirmă fereastra UAC; statusul se actualizează în ~30s"}


@router.post("/{eid}/autostart/disable")
def engine_autostart_disable(eid: str):
    _run_elevated(_engine(eid)["remove"])
    return {"started": True, "note": "Confirmă fereastra UAC; statusul se actualizează în ~30s"}
