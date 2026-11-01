"""
Update pentru branch-ul vlad-live — aduce codul nou FARA sa piarda configurarile locale.

Folosit de update-vlad-live.bat (dublu-click). Pasii:
  1. verificari: branch vlad-live, git instalat, Custom Engine oprit (celelalte: doar avertisment)
  2. fetch origin; tinta = origin/vlad-live sau origin/main — cel mai nou dintre ele (main poate
     primi codul inaintea vlad-live; amandoua contin doar cod, fara date)
  3. modificarile LOCALE (configurari editate din UI: profil, Setari Globale, config AI / Daily /
     Noisy, fus orar…) → git stash; fisierele locale NEURMARITE pe care update-ul le-ar suprascrie
     → mutate in data/_update_backup/<data-ora>/ (nimic nu se sterge)
  4. update: fast-forward; daca vlad-live are commit-uri proprii → merge (la conflict: abort +
     restaurare, nimic schimbat)
  5. reaplica modificarile locale; la conflict pastreaza versiunea LOCALA (a lui Vlad) si listeaza
     fisierele; modificarile raman necomise, ca inainte
  6. pip / npm doar daca requirements.txt / frontend/package.json s-au schimbat
Iesire 0 = ok / deja la zi, 1 = oprit cu mesaj (nimic pierdut).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRANCH = "vlad-live"
STASH_MSG = "vlad-update-auto-stash"


def git(*args: str, check: bool = False, cwd: str | None = None) -> subprocess.CompletedProcess:
    r = subprocess.run(["git", *args], cwd=cwd or ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip() or r.stdout.strip()}")
    return r


def out(*args: str, cwd: str | None = None) -> str:
    return git(*args, cwd=cwd).stdout.strip()


def say(msg: str = "") -> None:
    print(msg, flush=True)


def pid_alive(pid_file: str) -> bool:
    try:
        pid = int(open(pid_file, encoding="utf-8").read().strip())
    except Exception:
        return False
    if os.name == "nt":
        import ctypes
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not h:
            return False
        code = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(h)
        return code.value == 259
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def is_ancestor(a: str, b: str, cwd: str | None = None) -> bool:
    return git("merge-base", "--is-ancestor", a, b, cwd=cwd).returncode == 0


def pick_target(cwd: str | None = None) -> str | None:
    """origin/vlad-live sau origin/main — cel care il contine pe celalalt (cel mai nou)."""
    have = [r for r in ("origin/" + BRANCH, "origin/main") if git("rev-parse", "--verify", "-q", r, cwd=cwd).returncode == 0]
    if not have:
        return None
    if len(have) == 1:
        return have[0]
    vl, mn = have
    if is_ancestor(vl, mn, cwd):
        return mn
    return vl


def untracked_collisions(target: str, cwd: str | None = None) -> list[str]:
    """Fisiere locale NEURMARITE care exista in tinta (update-ul le-ar suprascrie / ar esua)."""
    untracked = set(filter(None, out("ls-files", "--others", "--exclude-standard", cwd=cwd).splitlines()))
    if not untracked:
        return []
    incoming = set(filter(None, out("ls-tree", "-r", "--name-only", target, cwd=cwd).splitlines()))
    return sorted(untracked & incoming)


def backup_files(paths: list[str], root: str) -> str:
    dest = os.path.join(root, "data", "_update_backup", datetime.now().strftime("%Y%m%d-%H%M%S"))
    for p in paths:
        src = os.path.join(root, p)
        dst = os.path.join(dest, p)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(src, dst)
    return dest


def run(root: str = ROOT, check_engines: bool = True, install_deps: bool = True) -> int:
    cwd = root
    say("=" * 60)
    say("  Update vlad-live (codul nou, configurarile tale raman)")
    say("=" * 60)
    if git("--version", cwd=cwd).returncode != 0:
        say(" [!] Git nu este instalat sau nu e in PATH.")
        return 1
    branch = out("branch", "--show-current", cwd=cwd)
    if branch != BRANCH:
        say(f" [!] Scriptul e doar pentru {BRANCH}. Branch curent: {branch or '(detached)'}")
        say("     alex-live: foloseste sync_data.bat · main: update_bot.bat")
        return 1
    if git("diff", "--name-only", "--diff-filter=U", cwd=cwd).stdout.strip():
        say(" [!] Exista un merge / conflict neterminat. Rezolva-l intai (git status).")
        return 1

    if check_engines:
        if pid_alive(os.path.join(root, "data", "run_all.pid")):
            say(" [!] Custom Engine ruleaza. Opreste-l din Dashboard (Stop) si ruleaza din nou update-ul.")
            say("     Pozitiile deschise din MT5 nu sunt afectate de oprire.")
            return 1
        others = [n for n, f in (("AI Engine", "data/ai/ai_engine.pid"), ("Daily Engine", "data/daily_engine/daily_engine.pid"),
                                 ("Noisy Engine", "data/noisy_engine/noisy_engine.pid")) if pid_alive(os.path.join(root, f))]
        if others:
            say(f" [i] Ruleaza: {', '.join(others)} — dupa update fa Stop + Start din Dashboard ca sa ia codul nou.")

    old = out("rev-parse", "HEAD", cwd=cwd)
    say(" [1/5] Descarc update-urile (git fetch) ...")
    f = git("fetch", "origin", cwd=cwd)
    if f.returncode != 0:
        say(f" [!] Fetch esuat — verifica internetul.\n     {f.stderr.strip()}")
        return 1
    target = pick_target(cwd)
    if not target:
        say(" [!] Nu gasesc origin/vlad-live sau origin/main.")
        return 1
    if is_ancestor(target, "HEAD", cwd):
        say(f"\n Deja la zi ({target} e inclus). Nimic de facut.")
        return 0

    # 2. pune deoparte configurarile locale + fisierele neurmarite care s-ar suprascrie
    stashed = False
    tracked_dirty = bool(out("status", "--porcelain", "--untracked-files=no", cwd=cwd))
    if tracked_dirty:
        say(" [2/5] Salvez configurarile tale locale (git stash) ...")
        r = git("stash", "push", "-m", STASH_MSG, cwd=cwd)
        if r.returncode != 0:
            say(f" [!] Nu am putut salva modificarile locale: {r.stderr.strip()}")
            return 1
        stashed = True
    else:
        say(" [2/5] Nicio configurare locala modificata.")
    coll = untracked_collisions(target, cwd)
    backup_dir = backup_files(coll, root) if coll else None
    if coll:
        say(f"      {len(coll)} fisier(e) locale neurmarite mutate in {os.path.relpath(backup_dir, root)} "
            f"(update-ul aduce fisiere cu acelasi nume): {', '.join(coll[:5])}{' …' if len(coll) > 5 else ''}")

    def restore() -> None:
        if stashed:
            git("stash", "pop", cwd=cwd)

    # 3. update
    say(f" [3/5] Aplic update-ul din {target} ...")
    if is_ancestor("HEAD", target, cwd):
        r = git("merge", "--ff-only", target, cwd=cwd)
    else:
        say("      vlad-live are commit-uri proprii — fac merge.")
        r = git("merge", "--no-edit", target, cwd=cwd)
    if r.returncode != 0:
        git("merge", "--abort", cwd=cwd)
        restore()
        say(" [!] Update-ul nu s-a putut aplica automat (conflict intre commit-urile tale si cele noi).")
        say("     Nimic nu s-a schimbat; configurarile tale sunt la loc.")
        say(f"     Detalii: {(r.stdout + r.stderr).strip()[:400]}")
        return 1

    # 4. reaplica configurarile; la conflict pastreaza versiunea LOCALA
    kept_local: list[str] = []
    if stashed:
        say(" [4/5] Reaplic configurarile tale ...")
        p = git("stash", "pop", cwd=cwd)
        conflicts = [x for x in out("diff", "--name-only", "--diff-filter=U", cwd=cwd).splitlines() if x]
        if conflicts:
            for c in conflicts:
                git("checkout", "--theirs", "--", c, cwd=cwd)     # theirs = stash = versiunea lui Vlad
                git("add", "--", c, cwd=cwd)
                kept_local.append(c)
            git("reset", "-q", cwd=cwd)                            # inapoi la modificari necomise, ca inainte
            git("stash", "drop", cwd=cwd)                          # pop cu conflict NU sterge stash-ul
        elif p.returncode != 0:
            say(f" [!] Reaplicarea a esuat: {(p.stdout + p.stderr).strip()[:400]}")
            say("     Configurarile tale sunt in siguranta in git stash (git stash list / git stash pop).")
            return 1
    else:
        say(" [4/5] Nimic de reaplicat.")

    # 5. dependente
    changed = set(out("diff", "--name-only", old, "HEAD", cwd=cwd).splitlines())
    if install_deps:
        if "requirements.txt" in changed:
            say(" [5/5] requirements.txt modificat — actualizez dependentele Python ...")
            subprocess.run([sys.executable, "-m", "pip", "install", "-r", os.path.join(root, "requirements.txt"), "--quiet"])
        if "frontend/package.json" in changed:
            say("       frontend/package.json modificat — npm install ...")
            subprocess.run("npm install --silent", shell=True, cwd=os.path.join(root, "frontend"))
        if not ({"requirements.txt", "frontend/package.json"} & changed):
            say(" [5/5] Dependentele nu s-au schimbat.")

    say("\n" + "=" * 60)
    say("  Update finalizat!")
    say("=" * 60)
    say(out("log", "--oneline", f"{old}..HEAD", cwd=cwd) or "(nimic)")
    if stashed:
        say("\n Configurarile tale locale au fost pastrate.")
    if kept_local:
        say(" La aceste fisiere ai si tu modificari si update-ul le-a schimbat — am PASTRAT versiunea ta:")
        for c in kept_local:
            say(f"   - {c}")
    if backup_dir:
        say(f" Copii ale fisierelor tale neurmarite: {os.path.relpath(backup_dir, root)}")
    say("\n IMPORTANT: codul nou se incarca doar dupa repornire — inchide si redeschide start_ui.bat,")
    say(" apoi Stop + Start pe engine-urile care rulau.")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(run())
