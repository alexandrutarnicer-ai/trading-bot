"""
Router API pentru AI Engine — motorul de trading autonom AI (ai_engine/).

Endpoints:
  GET  /ai/status      — running/pid/heartbeat + scorecard + erori recente
  POST /ai/start       — porneste `python -m ai_engine` ca proces detasat
  POST /ai/stop        — taskkill pe PID-ul motorului
  GET  /ai/decisions   — ultimele decizii (cu rationale)
  GET  /ai/council/{decision_id} — transcriptul complet al consiliului
  GET  /ai/outcomes    — rezultatele deciziilor executate
  GET  /ai/config      — configurarea curenta (piete, model, mode, risc)
  PUT  /ai/config      — actualizeaza pietele/mode (validate contra MT5)
  GET  /ai/logs        — ultimele N linii din engine.log

Cititul din ledger foloseste conexiuni SQLite proprii per-request (read-only),
ca sa nu tina lock pe DB-ul motorului.
"""

import os
import sys
import json
import sqlite3
import subprocess
import threading
import contextlib
from datetime import datetime

from fastapi import APIRouter, HTTPException, Body

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from ai_engine.config import CFG_PATH, AI_DATA, load_config, save_default_config

router = APIRouter(prefix="/ai", tags=["ai_engine"])

PID_FILE    = os.path.join(AI_DATA, "ai_engine.pid")
WD_PID_FILE = os.path.join(AI_DATA, "watchdog.pid")
STATUS_FILE = os.path.join(AI_DATA, "status.json")
LOG_FILE    = os.path.join(AI_DATA, "engine.log")
DB_FILE     = os.path.join(AI_DATA, "ledger.db")


def _pid_alive(pid: int) -> bool:
    """GetExitCodeProcess — identic cu bot.py (OpenProcess singur minte)."""
    try:
        import ctypes
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


def _read_pid() -> int | None:
    try:
        with open(PID_FILE) as f:
            return int(f.read().strip())
    except Exception:
        return None


def _db() -> sqlite3.Connection:
    if not os.path.isfile(DB_FILE):
        raise HTTPException(404, "Ledger-ul AI nu exista inca (motorul nu a rulat)")
    return sqlite3.connect(f"file:{DB_FILE}?mode=ro", uri=True)


# ── Status / Start / Stop ─────────────────────────────────────────────────────

@router.get("/status")
def ai_status():
    pid = _read_pid()
    running = pid is not None and _pid_alive(pid)
    status: dict = {}
    try:
        with open(STATUS_FILE, encoding="utf-8") as f:
            status = json.load(f)
    except Exception:
        pass
    # PID-ul e sursa de adevar pentru running (status.json poate fi stale la crash)
    status["running"] = running
    status["pid"] = pid if running else None
    if not running and status.get("scorecard") is None and os.path.isfile(DB_FILE):
        # scorecard disponibil si cu motorul oprit
        try:
            # Pietele izolate (market_overrides.isolated) sunt excluse — sincron cu
            # motorul (aceeasi functie: config.isolated_markets, derivat din overrides).
            from ai_engine.config import isolated_markets
            _iso = isolated_markets(load_config())
            _ex = f" AND symbol NOT IN ({','.join('?' * len(_iso))})" if _iso else ""
            with contextlib.closing(_db()) as con:   # inchidere garantata (fara leak)
                # Doar tranzactii activate si inchise real (TP/SL/closed) — ordinele
                # expirate/anulate nu s-au activat niciodata, deci nu sunt tranzactii.
                # Trebuie sa ramana sincronizat cu ledger.Ledger.scorecard().
                row = con.execute(
                    "SELECT COUNT(*), COALESCE(SUM(result_r),0), COALESCE(AVG(result_r),0), "
                    "SUM(CASE WHEN result_r>0 THEN 1 ELSE 0 END) FROM outcomes "
                    "WHERE status IN ('TP','SL','closed') AND result_r IS NOT NULL"
                    + _ex, _iso).fetchone()
                n, tot, avg, w = row
                n_dec = con.execute("SELECT COUNT(*) FROM decisions WHERE 1=1" + _ex, _iso).fetchone()[0]
                n_wait = con.execute("SELECT COUNT(*) FROM decisions WHERE action='WAIT'" + _ex, _iso).fetchone()[0]
                status["scorecard"] = {
                    "decisions": n_dec, "waits": n_wait, "closed_trades": n,
                    "total_R": round(tot, 2), "expectancy_R": round(avg, 3),
                    "win_rate": round(w / n, 3) if n else None}
        except Exception:
            pass   # DB corupt/absent → scorecard ramane None (nu 500-uim status-ul)
    return status


def _read_wd_pid() -> int | None:
    try:
        with open(WD_PID_FILE) as f:
            return int(f.read().strip())
    except Exception:
        return None


@router.post("/start")
def ai_start():
    pid = _read_pid()
    if pid and _pid_alive(pid):
        raise HTTPException(409, f"AI Engine ruleaza deja (PID={pid})")
    save_default_config()
    _flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    proc = subprocess.Popen(
        [sys.executable, "-m", "ai_engine"], cwd=ROOT, creationflags=_flags,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
    # porneste si watchdog-ul (anti-crash overnight) — idempotent, iese daca exista
    wd = _read_wd_pid()
    if not (wd and _pid_alive(wd)):
        subprocess.Popen(
            [sys.executable, "-m", "ai_engine.watchdog"], cwd=ROOT, creationflags=_flags,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
    return {"ok": True, "pid": proc.pid,
            "note": "Motorul verifica singur DEMO + Ollama la pornire; vezi /ai/logs"}


@router.post("/stop")
def ai_stop():
    pid = _read_pid()
    if not pid or not _pid_alive(pid):
        raise HTTPException(409, "AI Engine nu ruleaza")
    # INTAI watchdog-ul — altfel reporneste motorul in ≤5 min dupa stop
    wd = _read_wd_pid()
    if wd and _pid_alive(wd):
        subprocess.run(["taskkill", "/F", "/PID", str(wd)], capture_output=True, text=True)
        try:
            os.remove(WD_PID_FILE)
        except OSError:
            pass
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                   capture_output=True, text=True)
    try:
        os.remove(PID_FILE)
    except OSError:
        pass
    # taskkill /F nu lasa procesul sa-si scrie status-ul de oprire — o facem noi
    try:
        st = {}
        if os.path.isfile(STATUS_FILE):
            with open(STATUS_FILE, encoding="utf-8") as f:
                st = json.load(f)
        st["running"] = False
        st["ts"] = datetime.now().isoformat(timespec="seconds")
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(st, f, ensure_ascii=False, indent=1)
    except Exception:
        pass

    def _notify():
        try:
            from api.telegram import send_message
            send_message("🤖 AI Engine <b>oprit</b> din dashboard.")
        except Exception:
            pass
    threading.Thread(target=_notify, daemon=True).start()
    return {"ok": True}


# ── Date din ledger ───────────────────────────────────────────────────────────

@router.get("/decisions")
def ai_decisions(limit: int = 30, symbol: str | None = None):
    cols = ["id", "ts", "symbol", "action", "order_type", "entry", "sl", "tp",
            "risk_pct", "confidence", "rationale", "exec_status", "exec_detail",
            "ticket", "council_id"]
    where, params = "", []
    if symbol:   # vizualizare SEPARATA per piata (market_overrides / izolare)
        where, params = " WHERE symbol=?", [symbol.strip().upper()]
    with contextlib.closing(_db()) as con:   # inchidere garantata (fara leak)
        rows = con.execute(
            "SELECT id, ts, symbol, action, order_type, entry, sl, tp, risk_pct, "
            "confidence, rationale, exec_status, exec_detail, ticket, council_id "
            f"FROM decisions{where} ORDER BY id DESC LIMIT ?",
            (*params, min(limit, 200))).fetchall()
        out = [dict(zip(cols, r)) for r in rows]
        # Outcome-urile pentru TOATE deciziile intr-o SINGURA interogare (nu N+1).
        if out:
            ids = [d["id"] for d in out]
            ph = ",".join("?" * len(ids))
            omap: dict = {}
            for r in con.execute(
                    "SELECT decision_id, status, exit_price, result_r, pnl_usd FROM outcomes "
                    f"WHERE decision_id IN ({ph}) ORDER BY id", ids):
                omap[r[0]] = r   # ORDER BY id asc → ultimul (cel mai recent) ramane
            for d in out:
                r = omap.get(d["id"])
                d["outcome"] = (dict(zip(["status", "exit_price", "result_r", "pnl_usd"], r[1:]))
                                if r else None)
    return out


@router.get("/council/{decision_id}")
def ai_council(decision_id: int):
    with contextlib.closing(_db()) as con:   # inchidere garantata (fara leak)
        row = con.execute(
            "SELECT c.id, c.ts, c.symbol, c.trigger, c.transcript, c.duration_s "
            "FROM councils c JOIN decisions d ON d.council_id = c.id WHERE d.id=?",
            (decision_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Consiliu negasit pentru decizia data")
    cid, ts, sym, trig, transcript, dur = row
    try:
        transcript = json.loads(transcript)
    except Exception:
        pass
    return {"council_id": cid, "ts": ts, "symbol": sym, "trigger": trig,
            "duration_s": dur, "transcript": transcript}


@router.get("/outcomes")
def ai_outcomes(limit: int = 50, symbol: str | None = None):
    where, params = "", []
    if symbol:   # vizualizare SEPARATA per piata
        where, params = " WHERE o.symbol=?", [symbol.strip().upper()]
    with contextlib.closing(_db()) as con:   # inchidere garantata (fara leak)
        rows = con.execute(
            "SELECT o.ts, o.symbol, o.status, o.exit_price, o.result_r, o.pnl_usd, "
            f"o.decision_id FROM outcomes o{where} ORDER BY o.id DESC LIMIT ?",
            (*params, min(limit, 200))).fetchall()
    cols = ["ts", "symbol", "status", "exit_price", "result_r", "pnl_usd", "decision_id"]
    return [dict(zip(cols, r)) for r in rows]


# ── Config ────────────────────────────────────────────────────────────────────

@router.get("/config")
def ai_get_config():
    return load_config()


@router.put("/config")
def ai_put_config(body: dict = Body(...)):
    """Actualizeaza doar campurile editabile din UI. Pietele se valideaza in MT5."""
    editable = {"markets", "mode", "model", "risk_pct_default",
                "heartbeat_hours", "council_cooldown_min",
                # Roluri optionale de consiliu (Additional AI Roles)
                "role_quant_enabled", "role_devils_advocate_enabled",
                # Consiliu multiplu (Multi-Council Consensus)
                "council_primary_source", "council_secondary_source",
                "council_tertiary_source", "consensus_threshold",
                # Config per piata (capital fraction, max RR, stop zilnic, overtrading, izolare)
                "market_overrides"}
    updates = {k: v for k, v in (body or {}).items() if k in editable}
    if not updates:
        raise HTTPException(400, "Niciun camp editabil in body")

    # Normalizeaza surse goale ("" din UI) → None fara a atinge cheile absente din body.
    _CSRC = ("council_primary_source", "council_secondary_source", "council_tertiary_source")
    for _key in _CSRC:
        if _key in updates and updates[_key] in ("", None):
            updates[_key] = None

    # Validare surse de consiliu: trebuie sa existe, sa fie enabled si DISTINCTE.
    # Validam pe config-ul REZULTAT (valori din body suprascrise peste cele curente).
    _cur = load_config()
    _provs = _cur["providers"]
    _eff = {_k: (updates[_k] if _k in updates else _cur.get(_k)) for _k in _CSRC}
    _srcs = [v for v in _eff.values() if v]
    for _val in _srcs:
        if not (isinstance(_provs.get(_val), dict) and _provs[_val].get("enabled")):
            raise HTTPException(400, f"Sursa consiliu '{_val}' nu exista sau e dezactivata")
    if len(set(_srcs)) != len(_srcs):
        raise HTTPException(400, "Consiliile trebuie sa foloseasca surse AI DISTINCTE "
                                 "(scopul e sa obtii opinii independente)")
    if (_eff["council_secondary_source"] or _eff["council_tertiary_source"]) \
            and len({n for n, s in _provs.items() if s.get("enabled")}) < 2:
        raise HTTPException(400, "Consiliu multiplu necesita cel putin 2 surse AI active")
    if "consensus_threshold" in updates:
        try:
            th = int(updates["consensus_threshold"])
        except (TypeError, ValueError):
            raise HTTPException(400, "consensus_threshold: numar intreg (50-90)")
        updates["consensus_threshold"] = max(50, min(90, th))

    if "market_overrides" in updates:
        from ai_engine.config import sanitize_market_overrides
        if not isinstance(updates["market_overrides"], dict):
            raise HTTPException(400, "market_overrides: obiect {SIMBOL: {campuri}}")
        # aceeasi curatare + clamp ca load_config — o singura sursa de adevar
        updates["market_overrides"] = sanitize_market_overrides(
            updates["market_overrides"], _cur["risk_pct_max"])

    if "markets" in updates:
        mkts = updates["markets"]
        if not isinstance(mkts, list) or not (1 <= len(mkts) <= 10):
            raise HTTPException(400, "markets: lista de 1-10 simboluri")
        mkts = [str(m).strip().upper() for m in mkts if str(m).strip()]
        # validare contra MT5 (daca terminalul e disponibil)
        invalid = []
        try:
            import MetaTrader5 as mt5
            if mt5.initialize():
                for m in mkts:
                    if not mt5.symbol_select(m, True):
                        invalid.append(m)
                mt5.shutdown()
        except Exception:
            pass   # MT5 inchis — acceptam, motorul valideaza la pornire
        if invalid:
            raise HTTPException(400, f"Simboluri inexistente in MT5: {', '.join(invalid)}")
        updates["markets"] = mkts

    if "mode" in updates and updates["mode"] not in ("demo", "shadow"):
        raise HTTPException(400, "mode: 'demo' sau 'shadow'")

    save_default_config()
    with open(CFG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    cfg.update(updates)
    with open(CFG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

    pid = _read_pid()
    restart_needed = pid is not None and _pid_alive(pid)
    return {"ok": True, "config": load_config(),
            "restart_needed": restart_needed,
            "note": "Motorul citeste config la pornire — restart necesar" if restart_needed else ""}


@router.get("/logs")
def ai_logs(lines: int = 100):
    if not os.path.isfile(LOG_FILE):
        return {"lines": []}
    try:
        with open(LOG_FILE, encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
        return {"lines": [ln.rstrip() for ln in all_lines[-min(lines, 500):]]}
    except Exception as e:
        raise HTTPException(500, f"Nu pot citi log-ul: {e}")


# ── Surse AI (multi-provider) — vezi docs/PLAN_SURSE_AI_MULTI_PROVIDER.md ────

_ROLES = ("technical", "macro", "risk", "quant", "devils_advocate", "head_trader")
_PROVIDER_TYPES = ("ollama", "anthropic", "gemini", "openai_compatible")


@router.get("/providers")
def ai_get_providers():
    """Registrul de surse (chei mascate: doar has_key), asignari, sanatate live."""
    from ai_engine.config import load_keys
    cfg = load_config()
    keys = load_keys()
    providers = {}
    for name, spec in cfg["providers"].items():
        providers[name] = {
            "type":     spec.get("type"),
            "model":    spec.get("model"),
            "enabled":  bool(spec.get("enabled")),
            "base_url": spec.get("base_url"),
            "url":      spec.get("url"),
            "has_key":  bool(keys.get(name)),
            "needs_key": spec.get("type") != "ollama",
            "is_default": name == "ollama",
        }
    health = {}
    try:
        with open(STATUS_FILE, encoding="utf-8") as f:
            health = json.load(f).get("providers") or {}
    except Exception:
        pass
    return {"providers": providers,
            "role_assignments": cfg["role_assignments"],
            "health": health, "default": "ollama"}


@router.put("/providers")
def ai_put_providers(body: dict = Body(...)):
    """
    Actualizeaza registrul: body poate contine
      providers: {name: {type, model, enabled, base_url?, url?, _delete?}}
      role_assignments: {technical|macro|risk|head_trader: name}
      keys: {name: "cheia-api"}  (stocate separat in data/ai/providers.json)
    Ollama nu poate fi dezactivata/stearsa (safety-net-ul failover-ului).
    """
    from ai_engine.config import load_keys, save_key
    save_default_config()
    with open(CFG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    provs = dict(cfg.get("providers") or load_config()["providers"])

    for name, upd in (body.get("providers") or {}).items():
        name = str(name).strip()
        if not name:
            continue
        if upd.get("_delete"):
            if name == "ollama":
                raise HTTPException(400, "Ollama e sursa default — nu poate fi stearsa")
            provs.pop(name, None)
            save_key(name, "")
            continue
        cur = dict(provs.get(name) or {})
        ptype = upd.get("type", cur.get("type", "openai_compatible"))
        if ptype not in _PROVIDER_TYPES:
            raise HTTPException(400, f"Tip necunoscut '{ptype}'. "
                                     f"Valide: {', '.join(_PROVIDER_TYPES)}")
        if name == "ollama" and upd.get("enabled") is False:
            raise HTTPException(400, "Ollama e safety-net-ul failover — nu se dezactiveaza")
        cur["type"] = ptype
        for field in ("model", "enabled", "base_url", "url"):
            if field in upd:
                cur[field] = upd[field]
        if not cur.get("model"):
            raise HTTPException(400, f"Sursa '{name}': model lipsa")
        provs[name] = cur

    ra = dict(cfg.get("role_assignments") or {})
    for role, target in (body.get("role_assignments") or {}).items():
        if role not in _ROLES:
            raise HTTPException(400, f"Rol necunoscut: {role}")
        if target not in provs or not provs[target].get("enabled", target == "ollama"):
            raise HTTPException(400, f"Rolul {role}: sursa '{target}' nu exista sau e dezactivata")
        ra[role] = target

    for name, key in (body.get("keys") or {}).items():
        save_key(str(name), str(key or ""))

    cfg["providers"] = provs
    if ra:
        cfg["role_assignments"] = ra
    with open(CFG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

    # Motorul reciteste config-ul la fiecare iteratie — NU necesita restart.
    return {"ok": True, "restart_needed": False, "note": "Se aplica la urmatorul consiliu"}


@router.post("/providers/test")
def ai_test_provider(body: dict = Body(...)):
    """Testul de contract pentru o sursa: reachable → auth → JSON valid + latenta."""
    from ai_engine.config import load_keys
    from ai_engine.providers import build_provider, ProviderError
    name = str(body.get("name") or "").strip()
    cfg = load_config()
    spec = cfg["providers"].get(name)
    if spec is None:
        raise HTTPException(404, f"Sursa '{name}' nu exista")
    try:
        prov = build_provider(name, spec, load_keys().get(name, ""))
    except ProviderError as e:
        return {"ok": False, "latency_s": 0, "detail": str(e), "kind": e.kind}
    return prov.test()


# ─── Autostart Windows (mirror al /bot/autostart/*) ───────────────────────────
# Task Scheduler: TradingBot-AIEngine (+ TradingBot-MT5 partajat). Scripturile
# scripts/setup_autostart_ai.ps1 / remove_autostart_ai.ps1 fac munca; aici doar
# le lansam cu elevare UAC, exact ca la bot.

@router.get("/autostart/status")
def ai_autostart_status():
    try:
        r = subprocess.run(
            ["powershell", "-Command",
             "if (Get-ScheduledTask -TaskName 'TradingBot-AIEngine' -ErrorAction SilentlyContinue) { 'true' } else { 'false' }"],
            capture_output=True, text=True, timeout=10
        )
        enabled = r.stdout.strip().lower() == "true"
    except Exception:
        enabled = False
    return {"enabled": enabled}


@router.post("/autostart/enable")
def ai_autostart_enable():
    script = os.path.join(ROOT, "scripts", "setup_autostart_ai.ps1")
    if not os.path.exists(script):
        raise HTTPException(404, "scripts/setup_autostart_ai.ps1 nu a fost gasit")
    subprocess.Popen([
        "powershell", "-Command",
        f'Start-Process powershell -Verb RunAs -ArgumentList \'-NoExit -ExecutionPolicy Bypass -File "{script}"\''
    ])
    return {"started": True}


@router.post("/autostart/disable")
def ai_autostart_disable():
    script = os.path.join(ROOT, "scripts", "remove_autostart_ai.ps1")
    if not os.path.exists(script):
        raise HTTPException(404, "scripts/remove_autostart_ai.ps1 nu a fost gasit")
    subprocess.Popen([
        "powershell", "-Command",
        f'Start-Process powershell -Verb RunAs -ArgumentList \'-NoExit -ExecutionPolicy Bypass -File "{script}"\''
    ])
    return {"started": True}
