"""
Teste pentru safe_io.write_json_atomic (incident 2026-11-02: PermissionError WinError 5 la status.json pica iteratia Noisy).
Include un test REAL pe Windows: fisierul tinut deschis de alt handle (ca API-ul care citeste status.json).
    python scripts/test_safe_io.py
"""
import json
import os
import shutil
import sys
import tempfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from safe_io import write_json_atomic  # noqa: E402

FAIL = 0


def check(name, cond, info=None):
    global FAIL
    print(("  OK  " if cond else "  FAIL ") + name + ("" if cond or info is None else f"  -> {info}"))
    if not cond:
        FAIL += 1


tmp = tempfile.mkdtemp()
p = os.path.join(tmp, "status.json")
calls = {"n": 0}


def flaky(src, dst, fails=3):
    calls["n"] += 1
    if calls["n"] <= fails:
        raise PermissionError(5, "Access is denied")
    os.replace(src, dst)


check("blocare scurta (3 refuzuri) → reincercat, scris", write_json_atomic(p, {"v": 1}, critical=False, delay_s=0.001, _replace=flaky)
      and json.load(open(p))["v"] == 1)
always = lambda s, d: (_ for _ in ()).throw(PermissionError(5, "Access is denied"))  # noqa: E731
check("blocare persistenta, fisier de AFISARE → False, fara exceptie, fisierul vechi intact",
      write_json_atomic(p, {"v": 2}, critical=False, retries=3, delay_s=0.001, _replace=always) is False and json.load(open(p))["v"] == 1)
try:
    write_json_atomic(p, {"v": 3}, critical=True, retries=2, delay_s=0.001, _replace=always)
    raised = False
except PermissionError:
    raised = True
check("fisier de STARE (critical) → exceptia ramane vizibila", raised)

if os.name == "nt":
    reader = open(p, encoding="utf-8")                  # alt handle deschis = exact ce face API-ul cand citeste status.json
    try:
        r = write_json_atomic(p, {"v": 4}, critical=False, retries=3, delay_s=0.01)
        check("Windows REAL: status.json deschis de alt handle → nu mai arunca (iteratia continua)", r in (True, False), r)
    finally:
        reader.close()
    check("dupa eliberare → scrierea reuseste", write_json_atomic(p, {"v": 5}, critical=False) and json.load(open(p))["v"] == 5)

import noisy_engine.engine as NE  # noqa: E402
import daily_engine.engine as DE  # noqa: E402
for name, mod in (("Noisy", NE), ("Daily", DE)):
    sp = os.path.join(tmp, f"{name}_status.json")
    os.makedirs(os.path.join(tmp, name), exist_ok=True)
    sp = os.path.join(tmp, name, "status.json")
    import safe_io  # noqa: E402
    orig = safe_io.os.replace
    safe_io.os.replace = always
    try:
        mod._write_json(sp, {"x": 1})
        ok = True
    except PermissionError:
        ok = False
    try:
        mod._write_json(os.path.join(tmp, name, "state.json"), {"x": 1})
        state_raises = False
    except PermissionError:
        state_raises = True
    safe_io.os.replace = orig
    check(f"{name}: status.json blocat → iteratia NU mai pica; state.json blocat → eroarea ramane vizibila", ok and state_raises)
shutil.rmtree(tmp, ignore_errors=True)
print(f"\n{'TOATE TESTELE AU TRECUT' if not FAIL else f'{FAIL} TESTE ESUATE'}")
sys.exit(1 if FAIL else 0)
