"""
QA: rotatia jurnalelor Custom / AI (log_utils) + stergerea copiilor vechi de sync
(scripts/sync_branch.prune_backups). Offline, pe fisiere temporare.
    python scripts/test_log_rotation.py
"""
import logging
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import log_utils  # noqa: E402
from scripts import sync_branch as SB  # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name} {detail}")


TMP = tempfile.mkdtemp()
print("1. Rotatie la prag, se pastreaza N copii")
path = os.path.join(TMP, "generator.log")
lg = logging.getLogger("t_rot")
lg.setLevel(logging.INFO)
h = log_utils.rotating_handler(path, max_bytes=2_000, backups=3)
lg.addHandler(h)
for i in range(400):
    lg.info("linie %04d %s", i, "x" * 40)
files = sorted(f for f in os.listdir(TMP) if f.startswith("generator.log"))
check("fisierul curent + exact 3 copii", files == ["generator.log", "generator.log.1", "generator.log.2", "generator.log.3"], files)
check("fiecare fisier sub prag (+ o linie)", all(os.path.getsize(os.path.join(TMP, f)) <= 2_100 for f in files),
      [os.path.getsize(os.path.join(TMP, f)) for f in files])
check("ultima linie e in fisierul curent", "linie 0399" in open(path, encoding="utf-8").read())

print("2. Fisier tinut deschis de alt proces (redenumire refuzata) -> fara eroare, fara linii pierdute")
orig = os.rename
errors = []
h.handleError = lambda rec: errors.append(rec)
os.rename = lambda *a, **k: (_ for _ in ()).throw(PermissionError("in use"))
log_utils.os = os                       # acelasi modul
import logging.handlers as LH  # noqa: E402
_rot = LH.os.rename
LH.os.rename = os.rename
try:
    for i in range(50):
        lg.info("blocat %02d %s", i, "y" * 40)
finally:
    LH.os.rename = _rot
    os.rename = orig
check("nicio eroare de logging", not errors, len(errors))
check("liniile scrise in continuare (rotatia amanata)", "blocat 49" in open(path, encoding="utf-8").read())
lg.info("dupa deblocare")
check("dupa deblocare rotatia isi reia cursul", os.path.exists(path + ".1") and "dupa deblocare" in open(path, encoding="utf-8").read())
h.close()
lg.removeHandler(h)

print("3. Copii de siguranta sync: >30 zile sterse, restul pastrate")
SB.ROOT = TMP
base = os.path.join(TMP, "data", "_sync_backup")
now = datetime(2026, 11, 1, 12, 0)
for d in (now - timedelta(days=45), now - timedelta(days=30, hours=1), now - timedelta(days=29), now - timedelta(days=1)):
    os.makedirs(os.path.join(base, d.strftime("%Y%m%d-%H%M%S"), "data"), exist_ok=True)
os.makedirs(os.path.join(base, "manual_ceva"), exist_ok=True)
n = SB.prune_backups(now=now)
left = sorted(os.listdir(base))
check("2 foldere vechi sterse", n == 2, n)
check("cele recente + folderul cu nume necunoscut raman", left == sorted([(now - timedelta(days=29)).strftime("%Y%m%d-%H%M%S"),
      (now - timedelta(days=1)).strftime("%Y%m%d-%H%M%S"), "manual_ceva"]), left)
shutil.rmtree(base)
check("fara folder de backup -> nimic, fara eroare", SB.prune_backups(now=now) == 0)

shutil.rmtree(TMP, ignore_errors=True)
print(f"\nREZULTAT: {PASS} PASS / {FAIL} FAIL")
sys.exit(1 if FAIL else 0)
