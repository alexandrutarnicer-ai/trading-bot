"""
Sincronizare PC <-> laptop pe branch-ul de date (alex-live) — UN singur script, aceeasi comanda
pe ambele dispozitive (dublu-click: sync_data.bat sau pull_data.bat).

    python scripts/sync_branch.py

Pasi: (1) pune deoparte datele acestui dispozitiv, (2) aduce codul + datele celuilalt,
(3) trimite tot pe GitHub. Nu porneste / opreste nimic — cine ruleaza engine-urile decide userul.

Ce date TRIMITE acest dispozitiv: ale fiecarui engine care a RULAT AICI recent (jurnalul lui scris
in ultimele RECENT_DAYS zile, sau procesul viu) — astfel dispozitivul care doar analizeaza nu urca
niciodata copii vechi peste datele reale ale celuilalt:
  • Custom Engine → live_signals/session*/{signals,outcomes}.csv + ai_filter.jsonl, paused_sessions.json
  • AI Engine     → ai/ledger.db (copie CONSISTENTA prin backup SQLite, sigura si cu motorul pornit) + ai_outcomes.csv
  • Daily Engine  → daily_engine/{trades.jsonl,state.json}
  • mereu: configurarile modificate din UI (Setari Globale, profil, config AI / Daily)
NU se sincronizeaza: state.pkl / loguri / PID-uri / cheile API / deblocarea LIVE (per dispozitiv;
pozitiile deschise se reconciliaza din MT5).

Cand vin date de pe celalalt dispozitiv, copiile LOCALE care s-ar suprascrie se MUTA in
data/_sync_backup/<data-ora>/ — nu se sterge nimic. Modificari locale de COD in conflict → oprire cu mesaj.
"""
from __future__ import annotations

import glob
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

RECENT_DAYS = 3
LEDGER_REL = "data/ai/ledger.db"
# engine → (jurnale = dovada ca a rulat aici, PID-uri, fisierele lui de date)
ENGINES = {
    "Custom Engine": (["data/live_signals/session*/generator.log"], ["data/run_all.pid"],
                      ["data/live_signals/session*/signals.csv", "data/live_signals/session*/outcomes.csv",
                       "data/live_signals/session*/ai_filter.jsonl", "data/paused_sessions.json"]),
    "AI Engine":     (["data/ai/engine.log"], ["data/ai/ai_engine.pid"], ["data/ai/ai_outcomes.csv"]),
    "Daily Engine":  (["data/daily_engine/engine.log"], ["data/daily_engine/daily_engine.pid"],
                      ["data/daily_engine/trades.jsonl", "data/daily_engine/state.json"]),
}
CONFIG_FILES = ["data/global_settings.json", "data/profiles/standard.json",
                "ai_engine/config.json", "daily_engine/config.json"]
PROTECTED_BRANCHES = ("main", "vlad-live")


class Stop(Exception):
    pass


def say(msg: str = "", kind: str = "") -> None:
    print({"ok": "[OK] ", "warn": "[!]  ", "err": "[EROARE] ", "step": ">> "}.get(kind, "") + msg, flush=True)


def git(*args: str, check: bool = True) -> str:
    r = subprocess.run(["git", "-C", ROOT, *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        raise Stop(f"git {' '.join(args)} a esuat:\n{(r.stderr or r.stdout).strip()}")
    return r.stdout.strip()


def git_ok(*args: str) -> bool:
    return subprocess.run(["git", "-C", ROOT, *args], capture_output=True).returncode == 0


def _glob(pat: str) -> list[str]:
    return [os.path.relpath(p, ROOT).replace("\\", "/") for p in glob.glob(os.path.join(ROOT, pat))]


def _pid_alive(rel: str) -> bool:
    try:
        pid = int(open(os.path.join(ROOT, rel), encoding="utf-8").read().strip())
    except Exception:
        return False
    try:
        import ctypes
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not h:
            return False
        code = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(h)
        return code.value == 259
    except Exception:
        return False


def engines_here(now: float | None = None) -> dict[str, bool]:
    """Ce engine-uri au rulat pe ACEST dispozitiv recent (proces viu sau jurnal scris de curand)."""
    now = now or time.time()
    out = {}
    for name, (logs, pids, _) in ENGINES.items():
        mt = [os.path.getmtime(os.path.join(ROOT, f)) for pat in logs for f in _glob(pat)]
        out[name] = any(_pid_alive(p) for p in pids) or bool(mt and now - max(mt) < RECENT_DAYS * 86400)
    return out


# ── 1. datele acestui dispozitiv ─────────────────────────────────────────────

def _ledger_snapshot_to_index() -> bool:
    """Copie consistenta a ledger-ului (backup SQLite — sigur si cu motorul pornit) pusa direct in
    index sub data/ai/ledger.db; fisierul de lucru nu e atins."""
    src = os.path.join(ROOT, LEDGER_REL)
    if not os.path.exists(src):
        return False
    d = tempfile.mkdtemp()
    tmp = os.path.join(d, "ledger.db")
    con = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    dst = sqlite3.connect(tmp)
    try:
        con.backup(dst)
    finally:
        dst.close()
        con.close()
    sha = git("hash-object", "-w", "--no-filters", tmp)
    git("update-index", "--add", "--cacheinfo", f"100644,{sha},{LEDGER_REL}")
    shutil.rmtree(d, ignore_errors=True)
    return True


def commit_local(here: dict[str, bool]) -> bool:
    for name, (_, _, data) in ENGINES.items():
        if not here[name]:
            continue
        files = [f for pat in data for f in _glob(pat)]
        if files:
            git("add", "-f", "--", *files)
        if name == "AI Engine":
            _ledger_snapshot_to_index()
    cfg = [f for f in CONFIG_FILES if git("status", "--porcelain", "--", f)]
    if cfg:
        git("add", "--", *cfg)
    if git_ok("diff", "--cached", "--quiet"):
        return False
    host = os.environ.get("COMPUTERNAME", "?")
    git("commit", "-q", "-m", f"data sync ({host} {datetime.now():%Y-%m-%d %H:%M})")
    return True


# ── 2. ce vine de pe celalalt dispozitiv ─────────────────────────────────────

def _is_data(path: str) -> bool:
    return path.startswith("data/")


def prepare_incoming(br: str) -> int:
    """Copiile locale care s-ar suprascrie (neurmarite, sau date urmarite modificate local si
    necomise) se MUTA in data/_sync_backup/<data-ora>/. Cod local in conflict → oprire."""
    incoming = set(filter(None, git("diff", "--name-only", f"HEAD...origin/{br}").splitlines()))
    if not incoming:
        return 0
    modified = set(filter(None, git("diff", "--name-only", "HEAD").splitlines()))
    code = sorted(f for f in modified & incoming if not _is_data(f))
    if code:
        raise Stop("Ai modificari locale necomise in fisiere care vin si de pe celalalt dispozitiv:\n  "
                   + "\n  ".join(code) + "\nFa commit (sau anuleaza-le) si reia.")
    tracked = set(git("ls-files").splitlines())
    move = [f for f in incoming if os.path.exists(os.path.join(ROOT, f))
            and (f not in tracked or f in modified)]
    if not move:
        return 0
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    bdir = os.path.join(ROOT, "data", "_sync_backup", stamp)
    for f in sorted(move):
        src, dst = os.path.join(ROOT, f), os.path.join(bdir, f)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if f in tracked:
            shutil.copy2(src, dst)
            git("checkout", "--", f)
        else:
            shutil.move(src, dst)
    say(f"{len(move)} copii locale mutate deoparte in data/_sync_backup/{stamp}/", "warn")
    return len(move)


def merge_remote(br: str) -> None:
    if not git("rev-list", f"HEAD..origin/{br}"):
        return
    r = subprocess.run(["git", "-C", ROOT, "merge", "--no-edit", f"origin/{br}"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        git("merge", "--abort", check=False)
        raise Stop("Integrarea cu GitHub a dat conflict (merge anulat, nimic pierdut):\n"
                   + (r.stdout + r.stderr).strip())


# ── principal ────────────────────────────────────────────────────────────────

def sync() -> None:
    br = git("rev-parse", "--abbrev-ref", "HEAD")
    if br in PROTECTED_BRANCHES or br == "HEAD":
        raise Stop(f"Esti pe '{br}' — scriptul lucreaza doar pe branch-ul tau de date (alex-live).")
    here = engines_here()
    say("Engine-uri care au rulat aici recent: " + (", ".join(n for n, v in here.items() if v) or "niciunul")
        + " → " + ("le trimit datele" if any(here.values()) else "doar aduc datele"))
    if commit_local(here):
        say("Datele acestui dispozitiv puse deoparte (commit)", "ok")
    say("Aduc de pe GitHub ...", "step")
    git("fetch", "-q", "origin", br)
    old = git("rev-parse", "HEAD")
    prepare_incoming(br)
    merge_remote(br)
    new = git("rev-parse", "HEAD")
    if git("rev-list", f"origin/{br}..HEAD"):
        say("Trimit pe GitHub ...", "step")
        r = subprocess.run(["git", "-C", ROOT, "push", "origin", br], capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if r.returncode != 0:
            raise Stop("Push esuat (autentificare GitHub / retea):\n" + (r.stderr or r.stdout).strip())
    say("La zi cu GitHub (cod + date)", "ok")
    if old != new:
        changed = git("diff", "--name-only", old, new).splitlines()
        if any(not f.startswith("data/") and f.endswith((".py", ".ts", ".tsx")) for f in changed):
            say("A venit COD nou: reporneste dashboard-ul (start_ui.bat) si engine-urile care ruleaza, "
                "ca sa-l incarce.", "warn")


def main() -> int:
    try:
        sync()
        return 0
    except Stop as e:
        say(str(e), "err")
        return 1


if __name__ == "__main__":
    sys.exit(main())
