"""
telegram_bridge.status — citeste starea sistemului FARA a-l atinge.

Surse (toate read-only, zero efecte secundare, zero a doua conexiune MT5):
  - data/ai/status.json        → motor AI (running, equity, scorecard, per-piata)
  - data/run_all.pid + verificare proces → bot pe reguli sus/jos (fallback la API)
  - API local /api/*           → status bot, MT5, ordine (pool cache-uit deja)

Daca API-ul e jos, degradeaza elegant pe fisiere. Nimic aici nu blocheaza si nu
scrie in starea live.
"""

from __future__ import annotations

import json
import os
import urllib.request

from . import config

ROOT = config.ROOT
AI_STATUS = os.path.join(config.DATA_DIR, "ai", "status.json")
AI_PID    = os.path.join(config.DATA_DIR, "ai", "ai_engine.pid")
BOT_PID   = os.path.join(config.DATA_DIR, "run_all.pid")


def _read_json(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _pid_alive(pid: int) -> bool:
    """Windows: proces viu (STILL_ACTIVE=259) — acelasi criteriu ca api/routers."""
    try:
        import ctypes
        PROCESS_QUERY = 0x1000
        k = ctypes.windll.kernel32
        h = k.OpenProcess(PROCESS_QUERY, False, pid)
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = k.GetExitCodeProcess(h, ctypes.byref(code))
        k.CloseHandle(h)
        return bool(ok) and code.value == 259
    except Exception:
        # non-Windows / eroare → presupune viu daca pid file exista (fail-open info)
        return True


def api_get(cfg: dict, path: str) -> dict | None:
    try:
        url = cfg["api_base"].rstrip("/") + path
        with urllib.request.urlopen(url, timeout=cfg.get("api_timeout_s", 6)) as r:
            return json.loads(r.read())
    except Exception:
        return None


def _pid_from(path: str) -> int | None:
    try:
        with open(path, encoding="utf-8") as f:
            return int(f.read().strip())
    except Exception:
        return None


def bot_running(cfg: dict) -> tuple[bool, dict]:
    """(running, detalii). Prefera API-ul; fallback la pid file."""
    d = api_get(cfg, "/bot/status")
    if d is not None:
        return bool(d.get("running")), d
    pid = _pid_from(BOT_PID)
    return (bool(pid and _pid_alive(pid)), {"pid": pid, "source": "pid_file"})


def ai_running() -> tuple[bool, dict]:
    st = _read_json(AI_STATUS)
    pid = st.get("pid") or _pid_from(AI_PID)
    alive = bool(pid and _pid_alive(pid)) and bool(st.get("running"))
    return alive, st


def mt5_snapshot(cfg: dict) -> dict:
    return api_get(cfg, "/mt5/status") or {}


def orders_snapshot(cfg: dict) -> dict:
    return api_get(cfg, "/mt5/orders") or {}
