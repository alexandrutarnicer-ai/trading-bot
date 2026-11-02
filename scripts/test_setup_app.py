"""
Teste offline pentru setup-ul unic (scripts/setup_app.py + setup.bat / start_ui.bat / stop_ui.bat).
Nu instaleaza nimic: foloseste un director temporar si simulari.
    python scripts/test_setup_app.py
"""
from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tempfile
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts import setup_app as SA  # noqa: E402

ROOT = SA.ROOT
FAIL = 0


def check(name, cond, info=None):
    global FAIL
    print(("  OK  " if cond else "  FAIL ") + name + ("" if cond or info is None else f"  -> {info}"))
    if not cond:
        FAIL += 1


def quiet(fn, *a, **k):
    with redirect_stdout(io.StringIO()):
        return fn(*a, **k)


print("1. Versiuni")
check("Node 20.19 / 22.12 / 24 acceptate", all(SA.NODE_OK(v) for v in ((20, 19, 0), (22, 12, 0), (24, 1, 0))))
check("Node 18 / 20.18 / 22.11 refuzate (Vite 8 nu porneste pe ele)", not any(SA.NODE_OK(v) for v in ((18, 20, 0), (20, 18, 0), (22, 11, 0))))
check("parsare versiune: 'v22.16.0' / 'Python 3.12.4'", SA.parse_version("v22.16.0") == (22, 16, 0) and SA.parse_version("Python 3.12.4")[:2] == (3, 12))

print("2. Directoare + idempotenta (director temporar, ca un PC nou)")
tmp = tempfile.mkdtemp()
os.makedirs(os.path.join(tmp, "live"))
for i in range(1, 23):
    open(os.path.join(tmp, "live", f"session{i}_x.py"), "w").close()
SA.RESULTS.clear()
quiet(SA.prepare_files, True, tmp)
check("--check pe PC nou: raporteaza directoarele lipsa, NU le creeaza", not os.path.isdir(os.path.join(tmp, "data"))
      and any("lipsesc" in d for _, _, d in SA.RESULTS))
quiet(SA.prepare_files, False, tmp)
dirs = SA.data_dirs(tmp)
check("prima rulare: creeaza toate directoarele (22 sesiuni + engine-uri)", all(os.path.isdir(d) for d in dirs) and len(dirs) == 27, len(dirs))
check("profil standard lipsa → ATENTIE explicita (vine din git), nu un profil inventat",
      any(s.startswith("Profil") and st == "WARN" for s, st, _ in SA.RESULTS))
marker = os.path.join(tmp, "data", "live_signals", "session1", "signals.csv")
open(marker, "w").write("date existente")
quiet(SA.prepare_files, False, tmp)
check("setup repetat: datele existente raman neatinse", open(marker).read() == "date existente")

print("3. Configurari invalide")
os.makedirs(os.path.join(tmp, "ai_engine"))
with open(os.path.join(tmp, "ai_engine", "config.json"), "w") as f:
    f.write("{ stricat")
with open(os.path.join(tmp, "data", "global_settings.json"), "w") as f:
    json.dump({"ok": True}, f)
SA.RESULTS.clear()
check("JSON corupt → setup-ul ESUEAZA cu numele fisierului", quiet(SA.validate_configs, tmp) is False
      and "ai_engine/config.json" in SA.RESULTS[-1][2], SA.RESULTS[-1:])
os.remove(os.path.join(tmp, "ai_engine", "config.json"))
SA.RESULTS.clear()
check("fisierele lipsa nu sunt erori (se creeaza la prima pornire)", quiet(SA.validate_configs, tmp) is True)
shutil.rmtree(tmp, ignore_errors=True)

print("4. Dependenta lipsa → raportata clar")
import importlib.util as U  # noqa: E402
_fs = U.find_spec
U.find_spec = lambda name, *a, **k: None if name == "scipy" else _fs(name, *a, **k)
check("pachet Python lipsa detectat (scipy)", SA.missing_python_deps() == ["scipy"])
SA.RESULTS.clear()
check("… si setup-ul in --check esueaza cu instructiunea de reparare", quiet(SA.install_python, True) is False
      and "setup.bat" in SA.RESULTS[-1][2])
U.find_spec = _fs
_isfile = os.path.isfile
os.path.isfile = lambda p: False if p.endswith(os.path.join("vite", "package.json")) else _isfile(p)
SA.RESULTS.clear()
check("frontend neinstalat → esec explicit", quiet(SA.install_frontend, True) is False)
os.path.isfile = _isfile

print("5. Scripturile .bat (CMD: ASCII + CRLF obligatoriu) si fluxul documentat")
for name in ("setup.bat", "start_ui.bat", "stop_ui.bat", "setupFirst.bat", "setup_ai_engine.bat"):
    d = open(os.path.join(ROOT, name), "rb").read()
    lines = d.split(b"\n")
    check(f"{name}: ASCII, CRLF, fara caractere de control", all(c < 128 for c in d) and all(l.endswith(b"\r") for l in lines[:-1])
          and not any(b in d for b in (b"\x0b", b"\x0c", b"\x07", b"\x08")))
setup_bat = open(os.path.join(ROOT, "setup.bat"), encoding="ascii").read()
check("setup.bat: Python 3.10+, Node 20.19/22.12+, Git, apoi scripts\\setup_app.py cu optiunile",
      "3, 10" in setup_bat and "GEQ 12" in setup_bat and "GEQ 19" in setup_bat and "Git.Git" in setup_bat
      and 'setup_app.py" %*' in setup_bat)
check("scurtaturile vechi trimit la setup.bat (setupFirst, setup_ai_engine --with-ai)",
      "setup.bat" in open(os.path.join(ROOT, "setupFirst.bat")).read()
      and "--with-ai" in open(os.path.join(ROOT, "setup_ai_engine.bat")).read())
start = open(os.path.join(ROOT, "start_ui.bat"), encoding="ascii").read()
check("start_ui.bat refuza clar daca setup-ul n-a fost facut", r"frontend\node_modules\vite\package.json" in start and "setup.bat" in start)
check("duplicatele vechi eliminate (setupSecond.py, setup_instance.ps1, start_app.ps1)",
      not any(os.path.exists(os.path.join(ROOT, p)) for p in ("setupSecond.py", os.path.join("scripts", "setup_instance.ps1"), "start_app.ps1")))
req = open(os.path.join(ROOT, "requirements.txt")).read()
check("requirements.txt include tzdata (ZoneInfo pe Windows nu are baza de fusuri proprie)", "tzdata" in req)

print(f"\n{'TOATE TESTELE AU TRECUT' if not FAIL else f'{FAIL} TESTE ESUATE'}")
sys.exit(1 if FAIL else 0)
