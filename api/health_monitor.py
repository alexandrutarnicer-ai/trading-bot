"""Monitorizarea CENTRALA a sanatatii aplicatiei (23.11.2026) — thread in procesul API, la 30 s.

Componente: internet, MT5 (terminal + broker + cont), Ollama (doar daca AI Engine ruleaza), Gemini (daca e activat),
engine-uri (oprite neasteptat / blocate — heartbeat vechi), disc, baza de date AI, Telegram (outbox), plus evenimente:
aplicatia a pornit dupa o oprire NECURATA (crash / pana de curent / kill), Windows a repornit, sistemul a dormit (Sleep /
Hibernate — engine-urile nu au rulat), Windows e setat sa intre in Sleep cu engine-uri Live pornite.

Stari: healthy / degraded / unavailable / recovering / failed. Problemele reale devin INCIDENTE (incidents.py): un singur
incident activ pe problema, confirmat inainte de prima notificare, reamintiri rare, recuperare confirmata cu durata.
O componenta indisponibila NU opreste engine-urile care nu depind de ea (monitorul doar observa si notifica; singurele
actiuni automate sunt pornirea Ollama — limitata — si, separat, repornirile din api/watchdog.py).
Monitorul NU plaseaza / inchide ordine si nu schimba configurari.
"""
from __future__ import annotations

import ctypes
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import threading
import time
import urllib.request
from datetime import datetime, timedelta, timezone

import incidents

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
HEARTBEAT_FILE = os.path.join(DATA, "app_heartbeat.json")
INTERVAL_S = 30
_state: dict = {"components": {}, "started": None, "boot_time": None, "startup_event": None, "last_loop": None}
_lock = threading.Lock()
_ollama_starts: list[float] = []
_last_power_check = {"t": 0.0, "result": None}


# ── utilitare ───────────────────────────────────────────────────────────────────────────────────────────────────────
def _pid_alive(pid) -> bool:
    try:
        pid = int(pid)
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(h)
        return bool(ok) and code.value == 259
    except Exception:
        return False


def _read_pid(path) -> int | None:
    try:
        with open(path, encoding="utf-8") as f:
            return int(f.read().strip().split()[0])
    except Exception:
        return None


def _read_json(path) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _age_s(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        t = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        if t.tzinfo is None:
            return (datetime.now() - t).total_seconds()
        return (datetime.now(timezone.utc) - t).total_seconds()
    except Exception:
        return None


def boot_time() -> datetime | None:
    try:
        up_ms = ctypes.windll.kernel32.GetTickCount64()
        return datetime.now() - timedelta(milliseconds=up_ms)
    except Exception:
        return None


def _set(name: str, status: str, detail: str = "", **extra) -> dict:
    with _lock:
        prev = _state["components"].get(name, {})
        since = prev.get("since") if prev.get("status") == status else datetime.now().isoformat(timespec="seconds")
        c = {"status": status, "detail": detail, "since": since, "checked": datetime.now().isoformat(timespec="seconds"),
             **extra}
        _state["components"][name] = c
        return c


# ── engine-uri (ce ar trebui sa ruleze) ─────────────────────────────────────────────────────────────────────────────
def engines_expected() -> dict:
    """{id: {"expected": bool, "running": bool, "heartbeat_age": s | None, "stale_after": s}} — fara interogari MT5."""
    out = {}
    ap = os.path.join(DATA, "active_profile.json")
    out["custom"] = {"expected": os.path.isfile(ap), "running": _pid_alive(_read_pid(os.path.join(DATA, "run_all.pid"))),
                     "heartbeat_age": None, "stale_after": None}
    try:
        lg = os.path.join(DATA, "live_signals", "session1", "generator.log")
        out["custom"]["heartbeat_age"] = time.time() - os.path.getmtime(lg)
        out["custom"]["stale_after"] = 3 * 3600          # sesiunile scriu la fiecare bara (M15 / H1); 3 h = blocaj clar
    except OSError:
        pass
    ai_pid_f = os.path.join(DATA, "ai", "ai_engine.pid")
    ai_st = _read_json(os.path.join(DATA, "ai", "status.json"))
    out["ai"] = {"expected": os.path.isfile(ai_pid_f), "running": _pid_alive(_read_pid(ai_pid_f)),
                 "heartbeat_age": _age_s(ai_st.get("ts")), "stale_after": 45 * 60}
    for eid, sub, hb_key, stale in (("daily", "daily_engine", "heartbeat", 5 * 60),
                                    ("special", "special_engine", "updated", 10 * 60)):
        d = os.path.join(DATA, sub)
        if eid == "special" and not os.path.isdir(os.path.join(ROOT, "special_engine")):
            continue
        st = _read_json(os.path.join(d, "status.json"))
        out[eid] = {"expected": os.path.isfile(os.path.join(d, "desired_running.json")),
                    "running": _pid_alive(_read_pid(os.path.join(d, f"{sub}.pid"))),
                    "heartbeat_age": _age_s(st.get(hb_key)), "stale_after": stale}
    return out


LABEL = {"custom": "Custom Engine", "ai": "AI Engine", "daily": "Daily Engine", "special": "Special Engine"}


# ── verificari ──────────────────────────────────────────────────────────────────────────────────────────────────────
def check_internet() -> dict:
    ok_ip = ok_dns = False
    for host in ("1.1.1.1", "8.8.8.8"):
        try:
            with socket.create_connection((host, 443), timeout=3):
                ok_ip = True
                break
        except OSError:
            continue
    try:
        socket.getaddrinfo("api.telegram.org", 443)
        ok_dns = True
    except OSError:
        pass
    if ok_ip and ok_dns:
        incidents.resolve("internet", checks=["conexiune TCP", "DNS"])
        return _set("internet", "healthy")
    detail = "fără conexiune la internet" if not ok_ip else "DNS nu răspunde (internetul pare activ)"
    incidents.report("internet", "Internet indisponibil", detail + "\nMT5 / Telegram / Gemini nu pot funcționa; engine-urile "
                     "nu pot plasa ordine noi. Pozițiile deschise rămân pe SL / TP la broker.", "critical", "internet",
                     confirm_s=90)
    return _set("internet", "unavailable" if not ok_ip else "degraded", detail)


def check_mt5(eng: dict) -> dict:
    """Terminal (IPC), conexiunea la broker si contul — prin pool-ul API (aceeasi conexiune, sub lock)."""
    try:
        from api import mt5_pool
        with mt5_pool._LOCK:
            mt5 = mt5_pool._ensure_mt5()
            ti, acc = mt5.terminal_info(), mt5.account_info()
            npos = len(mt5.positions_get() or ())
    except Exception as e:  # noqa: BLE001
        ti, acc, npos = None, None, None
        err = str(e)
    else:
        err = ""
    live = [LABEL[k] for k, v in eng.items() if v.get("running")]
    who = (" Engine-uri pornite: " + ", ".join(live) + ".") if live else ""
    if ti is None or acc is None:
        incidents.report("mt5:ipc_lost", "MT5 indisponibil (terminal închis / neautentificat)",
                         f"{err or 'terminalul nu răspunde'}.{who}\nOrdine noi imposibile; pozițiile rămân pe SL / TP la "
                         "broker. Engine-urile se reconectează singure când terminalul revine.",
                         "critical" if live else "warning", "mt5", confirm_s=300)
        return _set("mt5", "unavailable", err or "terminal indisponibil")
    incidents.resolve("mt5:ipc_lost", checks=[f"terminal", f"cont #{acc.login}", f"{npos} poziții citite"])
    if not getattr(ti, "connected", True):
        incidents.report("mt5:disconnected", "MT5: deconectat de la serverul brokerului",
                         f"Terminalul rulează, dar nu are conexiune cu {acc.server}.{who}\nDate înghețate — engine-urile "
                         "sar iterațiile până la reconectare.", "critical" if live else "warning", "mt5", confirm_s=300)
        return _set("mt5", "degraded", "deconectat de la broker")
    incidents.resolve("mt5:disconnected", checks=[f"server {acc.server}", f"cont #{acc.login}", f"{npos} poziții citite"])
    if not getattr(ti, "trade_allowed", True) and live:
        incidents.report("mt5:autotrading_off", "MT5: AutoTrading DEZACTIVAT",
                         "Ordinele nu pot fi plasate. Activează din toolbar-ul MT5 (Alt+A).", "warning", "mt5", confirm_s=60)
        return _set("mt5", "degraded", "AutoTrading dezactivat")
    incidents.resolve("mt5:autotrading_off", checks=["AutoTrading activ"])
    return _set("mt5", "healthy", f"cont #{acc.login} · {npos} poziții", positions=npos)


def _ollama_exe() -> str | None:
    for p in (shutil.which("ollama"), os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama.exe")):
        if p and os.path.isfile(p):
            return p
    return None


def start_ollama() -> bool:
    """Porneste `ollama serve` DETASAT — maxim 3 incercari / ora (fara bucla)."""
    now = time.time()
    _ollama_starts[:] = [t for t in _ollama_starts if now - t < 3600]
    exe = _ollama_exe()
    if not exe or len(_ollama_starts) >= 3:
        return False
    _ollama_starts.append(now)
    try:
        subprocess.Popen([exe, "serve"], creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
        return True
    except Exception:
        return False


def ollama_reachable(url: str = "http://127.0.0.1:11434", timeout: float = 3) -> tuple[bool, str]:
    try:
        with urllib.request.urlopen(f"{url}/api/tags", timeout=timeout) as r:
            models = [m.get("name") for m in json.loads(r.read()).get("models", [])]
            return True, ", ".join(models[:4])
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


def check_ai_sources(eng: dict) -> None:
    ai = eng.get("ai") or {}
    if not ai.get("running"):
        _set("ollama", "healthy" if ollama_reachable()[0] else "unavailable", "AI Engine oprit — doar informativ")
        incidents.resolve("ollama", checks=["AI Engine oprit"])
        return
    try:
        from ai_engine.config import load_config
        cfg = load_config()
        url = (cfg.get("providers", {}).get("ollama") or {}).get("base_url") or cfg.get("ollama_url") or "http://127.0.0.1:11434"
        model = (cfg.get("providers", {}).get("ollama") or {}).get("model", "")
    except Exception:
        url, model = "http://127.0.0.1:11434", ""
    ok, info = ollama_reachable(url)
    if ok and model and model not in info and info:
        incidents.report("ollama:model", f"Ollama: modelul {model} lipsește",
                         f"Modele disponibile: {info}. Consiliul trece pe sursele de rezervă / WAIT. Remediere: "
                         f"`ollama pull {model}`.", "warning", "ollama", confirm_s=60)
    else:
        incidents.resolve("ollama:model", checks=[f"model {model}"])
    if ok:
        incidents.resolve("ollama", checks=[f"Ollama răspunde ({info or 'fără modele listate'})"])
        _set("ollama", "healthy", info)
    else:
        started = start_ollama()
        incidents.report("ollama", "Ollama indisponibil — AI Engine nu poate convoca consiliul",
                         f"{info}\nAI Engine NU deschide trade-uri noi (decizia la erori = WAIT); pozițiile deschise rămân "
                         f"pe SL / TP la broker + închiderea de weekend.\n"
                         f"{'Am pornit Ollama automat (ollama serve) — verific la următoarea iterație.' if started else 'Pornire automată indisponibilă / limita de 3 / oră atinsă — pornește Ollama manual.'}",
                         "critical", "ollama", confirm_s=120)
        _set("ollama", "recovering" if started else "unavailable", info)
    prov = (_read_json(os.path.join(DATA, "ai", "status.json")).get("providers") or {})
    g = prov.get("gemini")
    if g:                                  # notificarea o face registrul surselor (incident ai_source:gemini) — aici doar starea
        if g.get("status") in ("paused", "disabled", "disabled_auth", "down"):
            _set("gemini", "degraded", (g.get("reason") or g.get("status"))[:120] + " — rolurile lui rulează pe Ollama")
        else:
            _set("gemini", "healthy")


def check_engines(eng: dict) -> None:
    for eid, e in eng.items():
        if not e.get("expected"):
            _set(f"engine:{eid}", "healthy" if not e.get("running") else "healthy", "oprit (normal)" if not e.get("running") else "pornit")
            incidents.resolve(f"stalled:{eid}", checks=["engine oprit din UI"])
            continue
        if not e.get("running"):
            # repornirea automata (Daily / Special) o face api/watchdog.py; AI isi are watchdog-ul propriu
            incidents.report(f"engine:{eid}", f"{LABEL[eid]} oprit neașteptat",
                             {"custom": "Fără repornire automată (poziții reale) — pornește-l din Dashboard după verificare.",
                              "ai": "Watchdog-ul AI îl repornește automat (max 5 / 5 min).",
                              "daily": "Watchdog-ul API îl repornește automat (max 3 / oră).",
                              "special": "Watchdog-ul API îl repornește automat (max 3 / oră)."}[eid],
                             "critical", "engine", confirm_s=90)
            _set(f"engine:{eid}", "failed", "proces oprit neașteptat")
            continue
        age, lim = e.get("heartbeat_age"), e.get("stale_after")
        if age is not None and lim and age > lim:
            incidents.report(f"stalled:{eid}", f"{LABEL[eid]} pare blocat",
                             f"Procesul rulează, dar nu a mai scris starea de {int(age // 60)} min (limita {lim // 60} min).",
                             "warning", "engine", confirm_s=0)
            _set(f"engine:{eid}", "degraded", f"heartbeat vechi de {int(age // 60)} min")
            continue
        incidents.resolve(f"stalled:{eid}", checks=["heartbeat proaspăt"])
        incidents.resolve(f"engine:{eid}", checks=["proces viu", "heartbeat proaspăt"], detail=f"{LABEL[eid]} rulează din nou.")
        _set(f"engine:{eid}", "healthy", "rulează")


def check_disk() -> dict:
    try:
        free_gb = shutil.disk_usage(ROOT).free / 1e9
    except Exception as e:  # noqa: BLE001
        return _set("disk", "degraded", str(e))
    if free_gb < 0.5:
        incidents.report("disk", "Spațiu pe disc aproape epuizat", f"{free_gb:.2f} GB liberi — stările / jurnalele nu se mai "
                         "pot scrie. Eliberează spațiu.", "critical", "disk")
        return _set("disk", "failed", f"{free_gb:.2f} GB liberi")
    if free_gb < 2:
        incidents.report("disk", "Spațiu pe disc redus", f"{free_gb:.1f} GB liberi.", "warning", "disk")
        return _set("disk", "degraded", f"{free_gb:.1f} GB liberi")
    incidents.resolve("disk", checks=[f"{free_gb:.0f} GB liberi"])
    return _set("disk", "healthy", f"{free_gb:.0f} GB liberi")


def check_db() -> dict:
    p = os.path.join(DATA, "ai", "ledger.db")
    if not os.path.isfile(p):
        return _set("database", "healthy", "ledger AI inexistent (AI neutilizat)")
    try:
        c = sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=3)
        c.execute("select count(*) from decisions").fetchone()
        c.close()
        incidents.resolve("database", checks=["ledger AI citibil"])
        return _set("database", "healthy", "ledger AI citibil")
    except Exception as e:  # noqa: BLE001
        incidents.report("database", "Baza de date AI indisponibilă", f"{e}\nAI Engine poate să nu-și poată salva deciziile.",
                         "critical", "database", confirm_s=120)
        return _set("database", "failed", str(e))


def check_telegram() -> dict:
    n = incidents.snapshot().get("outbox", 0)
    if n:
        incidents.flush_outbox()
        return _set("telegram", "degraded", f"{n} mesaje în așteptare (Telegram / internet indisponibil)")
    return _set("telegram", "healthy")


def _powercfg(sub: str, setting: str) -> int | None:
    try:
        r = subprocess.run(["powercfg", "/query", "SCHEME_CURRENT", sub, setting], capture_output=True, text=True, timeout=10,
                           creationflags=0x08000000)
        for line in r.stdout.splitlines():
            if "AC Power Setting Index" in line or "Index setare alimentare c.a." in line or "Current AC Power Setting Index" in line:
                return int(line.split(":")[-1].strip(), 16)
    except Exception:
        return None
    return None


def check_power(eng: dict) -> dict:
    """Doar CITIRE (nu schimba nimic): Sleep pe priza activ / inchiderea capacului = Sleep, cu engine-uri Live pornite."""
    now = time.time()
    if now - _last_power_check["t"] < 6 * 3600 and _last_power_check["result"] is not None:
        res = _last_power_check["result"]
    else:
        res = {"sleep_ac_s": _powercfg("SUB_SLEEP", "STANDBYIDLE"), "hibernate_ac_s": _powercfg("SUB_SLEEP", "HIBERNATEIDLE"),
               "lid_ac": _powercfg("SUB_BUTTONS", "LIDACTION")}
        _last_power_check.update(t=now, result=res)
    live = any(v.get("running") for v in eng.values())
    issues = []
    if res.get("sleep_ac_s"):
        issues.append(f"Sleep automat după {res['sleep_ac_s'] // 60} min (pe priză)")
    if res.get("hibernate_ac_s"):
        issues.append(f"Hibernare automată după {res['hibernate_ac_s'] // 60} min")
    if res.get("lid_ac") in (1, 2, 3):
        issues.append("închiderea capacului = " + {1: "Sleep", 2: "Hibernate", 3: "Shut down"}[res["lid_ac"]])
    if issues and live:
        incidents.event("power_settings", "⚠️ <b>Windows poate suspenda engine-urile Live</b>\n" + "; ".join(issues) +
                        ".\nÎn Sleep / Hibernate engine-urile NU rulează (pozițiile rămân doar pe SL / TP la broker). "
                        "Setările nu au fost modificate — vezi Ghidul („Sleep / StandBy”).", "warning", dedup_min=24 * 60)
        return _set("power", "degraded", "; ".join(issues), **res)
    return _set("power", "healthy", "fără Sleep automat" if not issues else "Sleep activ, dar niciun engine pornit", **res)


# ── pornire: oprire necurata / restart Windows / sleep ──────────────────────────────────────────────────────────────
def startup_checks() -> dict | None:
    """La pornirea API-ului: ultima rulare s-a incheiat curat? Windows a repornit intre timp?"""
    prev = _read_json(HEARTBEAT_FILE)
    bt = boot_time()
    _state["boot_time"] = bt.isoformat(timespec="seconds") if bt else None
    _state["started"] = datetime.now().isoformat(timespec="seconds")
    ev = None
    if prev.get("ts") and not prev.get("clean_shutdown"):
        last = datetime.fromisoformat(prev["ts"])
        down = int((datetime.now() - last).total_seconds() // 60)
        rebooted = bool(bt and bt > last)
        eng = engines_expected()
        want = [LABEL[k] for k, v in eng.items() if v.get("expected")]
        ev = {"last_seen": prev["ts"], "down_min": down, "rebooted": rebooted}
        incidents.event("app_unclean_restart",
                        f"🔄 <b>Aplicația a repornit după o oprire NECURATĂ</b>\nUltimul semn de viață: {prev['ts'][:16].replace('T', ' ')} "
                        f"(întrerupere ~{down} min){' · Windows a repornit la ' + bt.strftime('%H:%M') if rebooted else ''}.\n"
                        "Cauze posibile: crash, pană de curent, restart Windows, proces oprit forțat. Mesajul de oprire NU a "
                        "putut fi trimis la momentul respectiv.\n"
                        + (f"Engine-uri care ar trebui să ruleze: {', '.join(want)} — verific starea lor în următoarele minute."
                           if want else "Niciun engine nu era marcat pornit."), "warning", dedup_min=5)
    elif prev.get("clean_shutdown") and bt and prev.get("ts") and bt > datetime.fromisoformat(prev["ts"]):
        incidents.event("windows_restart", f"🔄 Windows a repornit (la {bt.strftime('%d.%m %H:%M')}); aplicația a pornit din nou.",
                        "info", dedup_min=5)
    _state["startup_event"] = ev
    _write_heartbeat(clean=False)
    return ev


def _write_heartbeat(clean: bool) -> None:
    try:
        from safe_io import write_json_atomic
        write_json_atomic(HEARTBEAT_FILE, {"ts": datetime.now().isoformat(timespec="seconds"), "pid": os.getpid(),
                                           "clean_shutdown": clean}, critical=False)
    except Exception:
        pass


def mark_clean_shutdown() -> None:
    _write_heartbeat(clean=True)


def run_once(now_wall: float | None = None) -> dict:
    eng = engines_expected()
    for fn in (check_internet, check_disk, check_db, check_telegram):
        try:
            fn()
        except Exception:
            pass
    for fn in (check_mt5, check_ai_sources, check_engines, check_power):
        try:
            fn(eng)
        except Exception:
            pass
    _write_heartbeat(clean=False)
    return status()


def sleep_check(gap_s: float) -> bool:
    """Ceasul (wall clock) a sarit peste intervalul monitorului → sistemul a dormit (Sleep / Hibernate / StandBy)."""
    if gap_s <= INTERVAL_S + 120:
        return False
    eng = engines_expected()
    live = [LABEL[k] for k, v in eng.items() if v.get("expected")]
    incidents.event("system_sleep",
                    f"😴 <b>Sistemul a fost suspendat ~{int(gap_s // 60)} min</b> (Sleep / Hibernate / StandBy) — "
                    f"până la {datetime.now().strftime('%H:%M')}.\n"
                    + (f"Engine-urile ({', '.join(live)}) NU au rulat în acest timp; pozițiile au fost protejate doar de "
                       "SL / TP la broker. Se reconectează automat — verifică pozițiile." if live else
                       "Niciun engine nu era pornit."), "warning", dedup_min=10)
    return True


def _loop() -> None:
    try:
        startup_checks()
    except Exception:
        pass
    last = time.time()
    while True:
        time.sleep(INTERVAL_S)
        now = time.time()
        gap = now - last
        last = now
        sleep_check(gap)
        try:
            run_once()
        except Exception:
            pass
        _state["last_loop"] = datetime.now().isoformat(timespec="seconds")


def start() -> None:
    threading.Thread(target=_loop, daemon=True, name="health-monitor").start()


def status() -> dict:
    with _lock:
        comps = dict(_state["components"])
    worst = "healthy"
    order = ["healthy", "recovering", "degraded", "unavailable", "failed"]
    for c in comps.values():
        if order.index(c.get("status", "healthy")) > order.index(worst):
            worst = c["status"]
    return {"overall": worst, "components": comps, "incidents": incidents.snapshot(), "started": _state["started"],
            "boot_time": _state["boot_time"], "startup_event": _state["startup_event"], "last_loop": _state["last_loop"]}
