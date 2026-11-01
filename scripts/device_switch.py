"""
Schimbarea dispozitivului (PC <-> laptop) pe branch-ul de date (alex-live) — un singur script.

    python scripts/device_switch.py predau       # PLECI: opreste engine-urile, trimite datele, preda
    python scripts/device_switch.py preiau       # AJUNGI: aduce datele, preia, porneste engine-urile
    python scripts/device_switch.py actualizez   # doar analiza: aduce datele, NU porneste nimic
    python scripts/device_switch.py trimit       # de pe dispozitivul care ruleaza: trimite datele, fara oprire
    python scripts/device_switch.py status       # cine detine engine-urile + ce ruleaza aici
    (dublu-click: schimb_dispozitiv.bat — meniu)

Reguli (decizia userului 2026-11-01): engine-urile ruleaza pe UN SINGUR dispozitiv odata; de obicei
laptopul, uneori PC-ul. `data/device_owner.json` (sincronizat) spune cine le detine.

Ce se sincronizeaza: semnalele / jurnalul Custom Engine (signals.csv, outcomes.csv, ai_filter.jsonl),
ledger-ul AI (ledger.db — copie CONSISTENTA prin backup SQLite, sigura si cu motorul pornit),
ai_outcomes.csv, trade-urile + starea Daily (trades.jsonl, state.json), pauzele sesiunilor si
configurarile modificate din UI (Setari Globale, profil, AI, Daily).
NU se sincronizeaza: state.pkl / loguri / PID-uri / cheile API / deblocarea LIVE (per dispozitiv;
pozitiile deschise se reconciliaza din MT5).

La preluare, fisierele locale care s-ar suprascrie (copii vechi, date scrise de UI pe dispozitivul
care doar analiza) se MUTA in data/_sync_backup/<data-ora>/ — nu se sterge nimic.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import device_owner as DO  # noqa: E402

LEDGER_REL = "data/ai/ledger.db"
DATA_GLOBS = [
    "data/live_signals/session*/signals.csv",
    "data/live_signals/session*/outcomes.csv",
    "data/live_signals/session*/ai_filter.jsonl",
    "data/ai/ai_outcomes.csv",
    "data/daily_engine/trades.jsonl",
    "data/daily_engine/state.json",
    "data/paused_sessions.json",
]
# configurari urmarite deja de git, modificabile din UI pe dispozitivul care ruleaza
CONFIG_FILES = ["data/global_settings.json", "data/profiles/standard.json",
                "ai_engine/config.json", "daily_engine/config.json"]
PROTECTED_BRANCHES = ("main", "vlad-live")
ORDER = ("custom", "ai", "daily")


class Stop(Exception):
    pass


# ── utilitare ────────────────────────────────────────────────────────────────

def say(msg: str = "", kind: str = "") -> None:
    prefix = {"ok": "[OK] ", "warn": "[!]  ", "err": "[EROARE] ", "step": ">> "}.get(kind, "")
    print(prefix + msg, flush=True)


def git(*args: str, check: bool = True) -> str:
    r = subprocess.run(["git", "-C", ROOT, *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        raise Stop(f"git {' '.join(args)} a esuat:\n{(r.stderr or r.stdout).strip()}")
    return r.stdout.strip()


def git_ok(*args: str) -> bool:
    return subprocess.run(["git", "-C", ROOT, *args], capture_output=True).returncode == 0


def branch() -> str:
    b = git("rev-parse", "--abbrev-ref", "HEAD")
    if b in PROTECTED_BRANCHES or b == "HEAD":
        raise Stop(f"Esti pe '{b}'. Scriptul lucreaza doar pe branch-ul tau de date (alex-live): "
                   f"git checkout alex-live")
    return b


def ask(question: str, yes_default: bool = True) -> bool:
    if os.environ.get("DEVICE_SWITCH_YES") == "1":
        return True
    try:
        a = input(f"{question} [{'D/n' if yes_default else 'd/N'}] ").strip().lower()
    except EOFError:
        return yes_default
    return yes_default if not a else a in ("d", "da", "y", "yes")


def remote_owner(br: str) -> dict | None:
    try:
        txt = git("show", f"origin/{br}:{DO.OWNER_REL}")
        d = json.loads(txt)
        return d if d.get("owner") else None
    except Exception:
        return None


def write_owner(state: str, engines: list[str]) -> dict:
    d = {"owner": DO.this_machine(), "state": state, "engines": engines,
         "time": datetime.now().isoformat(timespec="seconds")}
    os.makedirs(os.path.dirname(DO.OWNER_FILE), exist_ok=True)
    with open(DO.OWNER_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2)
    return d


def notify(text: str) -> None:
    try:
        from api import telegram
        telegram.send_message(text)
    except Exception:
        pass


# ── engine-uri (aceleasi functii ca butoanele din Dashboard) ─────────────────

def _lc():
    from api import engine_lifecycle
    return engine_lifecycle


def running_engines() -> list[str]:
    L = _lc()
    out = []
    for eid in ORDER:
        try:
            if L._status(eid)["running"]:
                out.append(eid)
        except Exception as e:
            say(f"{eid}: status indisponibil ({e})", "warn")
    return out


def stop_engines(eids: list[str]) -> None:
    L = _lc()
    for eid in eids:
        label = L.ENGINES[eid]["label"]
        say(f"Opresc {label} ...", "step")
        L._do_stop(eid)
        st = L._wait_for(eid, False, 20.0)
        if st["running"]:
            raise Stop(f"{label} inca ruleaza (PID {st['pid']}). Opreste-l din Dashboard si reia.")
        say(f"{label} oprit", "ok")


def start_engines(eids: list[str]) -> list[str]:
    L = _lc()
    failed = []
    for eid in eids:
        label = L.ENGINES[eid]["label"]
        if L._status(eid)["running"]:
            say(f"{label} ruleaza deja", "ok")
            continue
        say(f"Pornesc {label} ...", "step")
        try:
            L._do_start(eid)
            st = L._wait_for(eid, True, 20.0)
        except Exception as e:
            st = {"running": False}
            say(f"{label}: {e}", "err")
        if st.get("running"):
            say(f"{label} pornit (PID {st.get('pid')})", "ok")
        else:
            failed.append(label)
            for ln in L._log_tail(eid, 5):
                print("      " + ln)
    return failed


# ── date ─────────────────────────────────────────────────────────────────────

def _ledger_snapshot_to_index() -> bool:
    """Copie CONSISTENTA a ledger-ului (API-ul de backup SQLite, sigur si cu motorul pornit) pusa
    direct in index sub data/ai/ledger.db — fisierul de lucru nu e atins."""
    src = os.path.join(ROOT, LEDGER_REL)
    if not os.path.exists(src):
        return False
    tmp = os.path.join(tempfile.mkdtemp(), "ledger.db")
    con = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    dst = sqlite3.connect(tmp)
    try:
        con.backup(dst)
    finally:
        dst.close()
        con.close()
    sha = git("hash-object", "-w", "--no-filters", tmp)
    git("update-index", "--add", "--cacheinfo", f"100644,{sha},{LEDGER_REL}")
    shutil.rmtree(os.path.dirname(tmp), ignore_errors=True)
    return True


def stage_data() -> None:
    files = []
    for pat in DATA_GLOBS:
        files += [os.path.relpath(p, ROOT).replace("\\", "/") for p in glob.glob(os.path.join(ROOT, pat))]
    if files:
        git("add", "-f", "--", *files)
    changed_cfg = [f for f in CONFIG_FILES if git("status", "--porcelain", "--", f)]
    if changed_cfg:
        git("add", "--", *changed_cfg)
    _ledger_snapshot_to_index()
    if os.path.exists(DO.OWNER_FILE):
        git("add", "-f", "--", DO.OWNER_REL)


def commit_staged(message: str) -> bool:
    if git_ok("diff", "--cached", "--quiet"):
        return False
    git("commit", "-q", "-m", message)
    return True


def integrate_remote(br: str) -> None:
    """Aduce eventualele commit-uri de pe remote (cod / fix-uri) peste cele locale."""
    if not git("rev-list", f"HEAD..origin/{br}"):
        return
    r = subprocess.run(["git", "-C", ROOT, "merge", "--no-edit", f"origin/{br}"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        git("merge", "--abort", check=False)
        raise Stop("Integrarea cu remote a dat conflict:\n" + (r.stdout + r.stderr).strip()
                   + "\nNimic nu s-a pierdut (merge anulat). Rezolva manual sau cere ajutor.")


def push(br: str) -> None:
    say(f"Trimit pe origin/{br} ...", "step")
    r = subprocess.run(["git", "-C", ROOT, "push", "origin", br], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise Stop("Push esuat (autentificare GitHub sau retea):\n" + (r.stderr or r.stdout).strip())
    say("Trimis", "ok")


def _is_data(path: str) -> bool:
    return path.startswith("data/") or path == LEDGER_REL


def prepare_incoming(br: str) -> str | None:
    """Inainte de a aduce datele celuilalt dispozitiv: fisierele locale care s-ar suprascrie se MUTA
    in data/_sync_backup/<data-ora>/. Modificarile locale de COD nu se ating (oprire cu mesaj)."""
    # doar ce s-a schimbat PE REMOTE de la punctul comun (nu si commit-urile locale netrimise)
    incoming = set(filter(None, git("diff", "--name-only", f"HEAD...origin/{br}").splitlines()))
    if not incoming:
        return None
    modified = set(filter(None, git("diff", "--name-only", "HEAD").splitlines()))
    staged = set(filter(None, git("diff", "--name-only", "--cached").splitlines()))
    code_conflicts = sorted(f for f in (modified | staged) & incoming if not _is_data(f))
    if code_conflicts:
        raise Stop("Ai modificari locale necomise in fisiere care vin si de pe celalalt dispozitiv:\n  "
                   + "\n  ".join(code_conflicts) + "\nFa commit (sau anuleaza-le) si reia.")
    tracked = set(git("ls-files").splitlines())
    to_move = [f for f in incoming if os.path.exists(os.path.join(ROOT, f))
               and ((f not in tracked) or (f in modified and _is_data(f)))]
    if not to_move:
        return None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    bdir = os.path.join(ROOT, "data", "_sync_backup", stamp)
    for f in sorted(to_move):
        src = os.path.join(ROOT, f)
        dst = os.path.join(bdir, f)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if f in tracked:
            shutil.copy2(src, dst)
            git("checkout", "--", f)                 # revine la versiunea comisa; vine cea noua
        else:
            shutil.move(src, dst)
    say(f"{len(to_move)} fisiere locale mutate deoparte in data/_sync_backup/{stamp}/", "warn")
    return stamp


# ── comenzi ──────────────────────────────────────────────────────────────────

def cmd_status() -> None:
    br = branch()
    git("fetch", "-q", "origin", br, check=False)
    ro = remote_owner(br)
    say(f"Dispozitivul acesta: {DO.this_machine()} · branch {br}")
    say("Proprietar engine-uri (pe GitHub): " + (f"{ro['owner']} · {ro['state']} · {', '.join(ro.get('engines') or []) or '-'}"
                                                 f" · {ro.get('time', '')}" if ro else "neinregistrat"))
    say("Ruleaza aici: " + (", ".join(running_engines()) or "nimic"))
    behind = git("rev-list", "--count", f"HEAD..origin/{br}", check=False)
    ahead = git("rev-list", "--count", f"origin/{br}..HEAD", check=False)
    say(f"Fata de GitHub: {behind or 0} commit-uri de adus, {ahead or 0} de trimis")


def cmd_predau() -> None:
    br = branch()
    git("fetch", "-q", "origin", br)
    ro = remote_owner(br)
    if ro and ro.get("state") == "running" and str(ro["owner"]).upper() != DO.this_machine():
        raise Stop(f"Pe GitHub, engine-urile sunt preluate de {ro['owner']} — acest dispozitiv nu are ce preda.")
    running = running_engines()
    engines = running or ((ro or {}).get("engines") if ro and str(ro["owner"]).upper() == DO.this_machine() else []) or []
    say("Engine-uri de predat: " + (", ".join(engines) or "niciunul pornit"))
    if running:
        stop_engines(running)
    write_owner("released", engines)
    stage_data()
    committed = commit_staged(f"data sync: predare de pe {DO.this_machine()} ({datetime.now():%Y-%m-%d %H:%M})")
    integrate_remote(br)
    push(br)
    say(("Date trimise. " if committed else "Nicio data noua; ") + "Pe celalalt dispozitiv ruleaza: schimb_dispozitiv.bat -> Preiau", "ok")
    notify(f"🔁 <b>Predare</b> de pe {DO.this_machine()}: engine-uri oprite ({', '.join(engines) or '-'}), date trimise. "
           f"Urmeaza preluarea pe celalalt dispozitiv.")


def cmd_trimit() -> None:
    br = branch()
    git("fetch", "-q", "origin", br)
    ro = remote_owner(br)
    if ro and str(ro["owner"]).upper() != DO.this_machine() and ro.get("state") == "running":
        raise Stop(f"Engine-urile sunt pe {ro['owner']} — de acolo se trimit datele (acest dispozitiv doar analizeaza).")
    stage_data()
    if not commit_staged(f"data sync de pe {DO.this_machine()} ({datetime.now():%Y-%m-%d %H:%M})"):
        say("Nicio data noua de trimis", "ok")
    integrate_remote(br)
    if git("rev-list", f"origin/{br}..HEAD"):
        push(br)


def _pull(br: str) -> tuple[str, str]:
    old = git("rev-parse", "HEAD")
    prepare_incoming(br)
    integrate_remote(br)
    return old, git("rev-parse", "HEAD")


def _code_changed_hint(old: str, new: str) -> None:
    if old == new:
        return
    changed = git("diff", "--name-only", old, new).splitlines()
    if any(f.startswith(("api/", "frontend/", "live/", "strategy/", "engine/", "ai_engine/", "daily_engine/"))
           and not f.endswith(".json") for f in changed):
        say("A venit COD nou: reporneste dashboard-ul (inchide si redeschide start_ui.bat) ca API-ul sa-l incarce.", "warn")


def cmd_actualizez() -> None:
    br = branch()
    if running_engines():
        raise Stop("Pe acest dispozitiv ruleaza engine-uri — de aici se TRIMIT datele (optiunea Trimit), nu se aduc.")
    git("fetch", "-q", "origin", br)
    old, new = _pull(br)
    ro = remote_owner(br)
    say("Date aduse" + (f" (engine-urile: {ro['owner']} · {ro['state']})" if ro else ""), "ok")
    _code_changed_hint(old, new)


def cmd_preiau(start: bool = True) -> None:
    br = branch()
    git("fetch", "-q", "origin", br)
    ro = remote_owner(br)
    me = DO.this_machine()
    if ro and ro.get("state") == "running" and str(ro["owner"]).upper() != me:
        say(f"ATENTIE: {ro['owner']} NU a predat (engine-urile pot rula inca acolo, din {ro.get('time', '?')}).", "warn")
        say("Daca ruleaza pe ambele dispozitive = ordine DUBLE pe acelasi cont.", "warn")
        say(f"Ruleaza intai pe {ro['owner']}: schimb_dispozitiv.bat -> Predau.", "warn")
        if not ask("Continui DOAR daca esti sigur ca celalalt dispozitiv e oprit / engine-urile nu ruleaza acolo?",
                   yes_default=False):
            raise Stop("Preluare anulata — nimic nu s-a schimbat.")
    old, new = _pull(br)
    engines = list((ro or {}).get("engines") or [])
    write_owner("running", engines)
    git("add", "-f", "--", DO.OWNER_REL)
    commit_staged(f"preluare pe {me} ({datetime.now():%Y-%m-%d %H:%M})")
    push(br)
    say(f"Date aduse, engine-urile sunt acum pe {me}", "ok")
    _code_changed_hint(old, new)
    failed = []
    if start and engines:
        if ask(f"Pornesc engine-urile care rulau pe celalalt dispozitiv ({', '.join(engines)})?"):
            failed = start_engines(engines)
    elif start:
        say("Pe celalalt dispozitiv nu rula niciun engine — porneste-le din Dashboard cand vrei.")
    if failed:
        say("Nu au pornit: " + ", ".join(failed) + " — vezi jurnalul / porneste-le din Dashboard.", "err")
    notify(f"🔁 <b>Preluare</b> pe {me}: date aduse"
           + (f", engine-uri: {', '.join(e for e in engines)}" if engines else "")
           + (f" · ⚠️ NU au pornit: {', '.join(failed)}" if failed else ""))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["predau", "preiau", "actualizez", "trimit", "status"])
    ap.add_argument("--fara-pornire", action="store_true", help="preiau fara sa porneasca engine-urile")
    a = ap.parse_args()
    try:
        {"predau": cmd_predau, "trimit": cmd_trimit, "actualizez": cmd_actualizez, "status": cmd_status,
         "preiau": lambda: cmd_preiau(start=not a.fara_pornire)}[a.cmd]()
        return 0
    except Stop as e:
        say(str(e), "err")
        return 1


if __name__ == "__main__":
    sys.exit(main())
