"""
Teste pentru scripts/update_vlad_live.py — repository-uri git TEMPORARE (remote local + clona „Vlad”).
Offline. Rulare: python scripts/test_update_vlad_live.py
"""
from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts import update_vlad_live as U  # noqa: E402

FAIL = 0


def check(name, cond, info=None):
    global FAIL
    print(("  OK  " if cond else "  FAIL ") + name + ("" if cond or info is None else f"  -> {info}"))
    if not cond:
        FAIL += 1


def sh(cwd, *args):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"git {args}: {r.stderr}")
    return r.stdout.strip()


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def read(path):
    return open(path, encoding="utf-8").read()


def setup():
    base = tempfile.mkdtemp()
    remote = os.path.join(base, "remote.git")
    dev = os.path.join(base, "dev")
    vlad = os.path.join(base, "vlad")
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", remote], check=True)
    subprocess.run(["git", "clone", "-q", remote, dev], check=True, capture_output=True)
    for c in (dev,):
        sh(c, "config", "user.email", "t@t"); sh(c, "config", "user.name", "t")
    write(os.path.join(dev, "app.py"), "v1\n")
    write(os.path.join(dev, "config", "ai.json"), '{"markets": ["EURUSD"]}\n')
    write(os.path.join(dev, "config", "profile.json"), '{"risk": 1}\n')
    write(os.path.join(dev, ".gitignore"), "data/run_all.pid\n")
    sh(dev, "add", "-A"); sh(dev, "commit", "-qm", "v1")
    sh(dev, "push", "-q", "origin", "main")
    sh(dev, "checkout", "-qb", "vlad-live"); sh(dev, "push", "-q", "origin", "vlad-live")
    subprocess.run(["git", "clone", "-q", "-b", "vlad-live", remote, vlad], check=True, capture_output=True)
    sh(vlad, "config", "user.email", "v@v"); sh(vlad, "config", "user.name", "v")
    return base, dev, vlad


def upstream(dev, files: dict, msg="update", branches=("main", "vlad-live")):
    sh(dev, "checkout", "-q", branches[0])
    for p, t in files.items():
        write(os.path.join(dev, p), t)
    sh(dev, "add", "-A"); sh(dev, "commit", "-qm", msg)
    sh(dev, "push", "-q", "origin", branches[0])
    for b in branches[1:]:
        sh(dev, "checkout", "-q", b); sh(dev, "merge", "-q", "--ff-only", branches[0]); sh(dev, "push", "-q", "origin", b)


def run(vlad):
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = U.run(vlad, check_engines=True, install_deps=False)
    return rc, buf.getvalue()


print("1. Scenariul lui Vlad: configurari locale modificate (vechiul script refuza)")
base, dev, vlad = setup()
write(os.path.join(vlad, "config", "ai.json"), '{"markets": ["GER40", "EURUSD"]}\n')   # config local (UI)
write(os.path.join(vlad, "config", "profile.json"), '{"risk": 2}\n')                  # config local, neatins upstream
upstream(dev, {"app.py": "v2\n", "config/ai.json": '{"markets": ["EURUSD"], "new_field": 1}\n', "new_feature.py": "x\n"})
write(os.path.join(vlad, "new_feature.py"), "copia mea locala\n")                    # neurmarit, se ciocneste
rc, log = run(vlad)
check("update reusit (rc 0)", rc == 0, log)
check("codul nou a ajuns (app.py v2)", read(os.path.join(vlad, "app.py")) == "v2\n")
check("config modificat doar local pastrat (profile risk 2)", '"risk": 2' in read(os.path.join(vlad, "config", "profile.json")))
check("conflict pe config → pastrata versiunea LUI VLAD", "GER40" in read(os.path.join(vlad, "config", "ai.json")), read(os.path.join(vlad, "config", "ai.json")))
check("fisierele pastrate sunt listate in raport", "config/ai.json" in log)
st = subprocess.run(["git", "status", "--porcelain"], cwd=vlad, capture_output=True, text=True).stdout   # fara strip: " M" are spatiu
check("configurarile raman modificari NECOMISE (ca inainte), fara conflicte", "UU" not in st and " M config/ai.json" in st
      and " M config/profile.json" in st, st)
check("stash-ul a fost consumat (nu ramane gunoi)", sh(vlad, "stash", "list") == "")
bk = os.path.join(vlad, "data", "_update_backup")
check("fisierul neurmarit care se ciocnea → mutat in backup, nu sters",
      os.path.isdir(bk) and any("copia mea locala" in read(os.path.join(r, f)) for r, _, fs in os.walk(bk) for f in fs if f == "new_feature.py"))
check("versiunea noua a fisierului din update e la locul ei", read(os.path.join(vlad, "new_feature.py")) == "x\n")
check("vlad-live = ultimul commit din remote", sh(vlad, "rev-parse", "HEAD") == sh(dev, "rev-parse", "origin/vlad-live"))

print("2. Deja la zi / main mai nou decat vlad-live")
rc, log = run(vlad)
check("a doua rulare: deja la zi", rc == 0 and "Deja la zi" in log, log)
upstream(dev, {"app.py": "v3\n"}, branches=("main",))      # doar main a primit codul
rc, log = run(vlad)
check("main mai nou → luat din origin/main", rc == 0 and read(os.path.join(vlad, "app.py")) == "v3\n" and "origin/main" in log, log)

print("3. Siguranta")
sh(vlad, "checkout", "-qb", "alex-live")
rc, log = run(vlad)
check("pe alt branch refuza (alex-live)", rc == 1 and "doar pentru vlad-live" in log)
sh(vlad, "checkout", "-q", "vlad-live")
write(os.path.join(vlad, "data", "run_all.pid"), str(os.getpid()))
upstream(dev, {"app.py": "v4\n"})
rc, log = run(vlad)
check("Custom Engine pornit → refuza, nimic schimbat", rc == 1 and "Custom Engine ruleaza" in log and read(os.path.join(vlad, "app.py")) == "v3\n")
os.remove(os.path.join(vlad, "data", "run_all.pid"))
# commit local al lui Vlad + upstream pe acelasi fisier → conflict real de merge
write(os.path.join(vlad, "app.py"), "modificarea lui vlad\n")
sh(vlad, "commit", "-qam", "vlad local")
write(os.path.join(vlad, "config", "profile.json"), '{"risk": 3}\n')
rc, log = run(vlad)
check("conflict intre commit-ul lui Vlad si update → oprit curat", rc == 1 and "Nimic nu s-a schimbat" in log, log)
check("dupa abort: commit-ul lui Vlad intact + config local restaurat",
      read(os.path.join(vlad, "app.py")) == "modificarea lui vlad\n" and '"risk": 3' in read(os.path.join(vlad, "config", "profile.json"))
      and sh(vlad, "stash", "list") == "" and "UU" not in sh(vlad, "status", "--porcelain"))
# commit local care NU intra in conflict → merge automat
sh(vlad, "reset", "-q", "--hard", "origin/vlad-live~1")
write(os.path.join(vlad, "vlad_notes.txt"), "notite\n")
sh(vlad, "add", "vlad_notes.txt"); sh(vlad, "commit", "-qm", "notite")
rc, log = run(vlad)
check("commit local fara conflict → merge automat, ambele pastrate",
      rc == 0 and read(os.path.join(vlad, "app.py")) == "v4\n" and os.path.isfile(os.path.join(vlad, "vlad_notes.txt")), log)
shutil.rmtree(base, ignore_errors=True)

print(f"\n{'TOATE TESTELE AU TRECUT' if not FAIL else f'{FAIL} TESTE ESUATE'}")
sys.exit(1 if FAIL else 0)
