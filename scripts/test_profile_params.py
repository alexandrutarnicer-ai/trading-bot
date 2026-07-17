"""
Test: verifica ca parametrii din profilul activ se aplica corect in sesiunile live.

Ruleaza din radacina proiectului:
    python scripts/test_profile_params.py

Ce testeaza:
1. _apply_profile_overrides() aplica RSI thresholds, R-ladder, pullback_window, session hours
2. Parametrii hardcodati raman neschimbati cand nu exista fisier de profil activ
3. Fiecare sesiune (session1-session6) isi gaseste config-ul corect din profil
4. count_optional() si reward_R() folosesc valorile din profil
"""

import os, sys, json, tempfile, copy, shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest import DATA_DIR, CONFIG

RUNTIME_FILE = os.path.join(DATA_DIR, "active_profile_runtime.json")

# Importam functiile de testat
from live.signal_generator import _apply_profile_overrides
from strategy.signals import count_optional, reward_R


# ---------------------------------------------------------------------------
# Utilitare
# ---------------------------------------------------------------------------

def _load_base_cfg():
    with open(CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)
    cfg["optional_criteria"]["rsi"]["sell_max"] = 60
    return cfg


def _load_profile():
    profile_path = os.path.join(DATA_DIR, "profiles", "standard.json")
    with open(profile_path, encoding="utf-8") as f:
        return json.load(f)


def _write_runtime(profile: dict):
    with open(RUNTIME_FILE, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2)


def _remove_runtime():
    if os.path.exists(RUNTIME_FILE):
        os.remove(RUNTIME_FILE)


class MockLog:
    def info(self, msg): pass
    def warning(self, msg): print(f"  WARN: {msg}")


log = MockLog()

PASS = 0
FAIL = 0


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {msg}")
    else:
        FAIL += 1
        print(f"  FAIL  {msg}")


# ---------------------------------------------------------------------------
# Test 1: fara fisier runtime — parametri raman hardcodati
# ---------------------------------------------------------------------------
print("\n[Test 1] Fara profil activ — parametri hardcodati neschimbati")
_remove_runtime()

session_cfg = {
    "session_key": "session1",
    "pullback_window": 8,
    "session_start": 10,
    "session_end": 18,
    "only_long": True,
    "execute_trades": True,
}
cfg = _load_base_cfg()
_apply_profile_overrides(session_cfg, cfg, log)

check(session_cfg["pullback_window"] == 8, "pullback_window neschimbat fara profil")
check(session_cfg["session_start"] == 10, "session_start neschimbat fara profil")
check(cfg["optional_criteria"]["rsi"]["buy_min"] == 40, "rsi.buy_min neschimbat fara profil")
check(cfg["reward_ladder"]["rr_if_3_criteria"] == 2.5, "r_base neschimbat fara profil")

# ---------------------------------------------------------------------------
# Test 2: cu profil standard — parametrii se aplica corect
# ---------------------------------------------------------------------------
print("\n[Test 2] Cu profil standard — parametrii se aplica")
profile = _load_profile()
_write_runtime(profile)

for key in ["session1", "session2", "session3", "session4", "session5", "session6"]:
    session_cfg = {
        "session_key": key,
        "pullback_window": 99,   # valoare falsa — trebuie sa fie suprascris
        "session_start": 99,
        "session_end": 99,
        "only_long": None,
        "execute_trades": None,
    }
    cfg = _load_base_cfg()
    _apply_profile_overrides(session_cfg, cfg, log)

    ps = next(s for s in profile["sessions"] if s["session_key"] == key)

    check(session_cfg["pullback_window"] == ps["pullback_window"],
          f"{key}: pullback_window = {session_cfg['pullback_window']} (asteptat {ps['pullback_window']})")
    check(session_cfg["session_start"] == ps["session_start"],
          f"{key}: session_start = {session_cfg['session_start']} (asteptat {ps['session_start']})")
    check(session_cfg["session_end"] == ps["session_end"],
          f"{key}: session_end = {session_cfg['session_end']} (asteptat {ps['session_end']})")
    check(session_cfg["execute_trades"] == ps["execute_trades"],
          f"{key}: execute_trades = {session_cfg['execute_trades']} (asteptat {ps['execute_trades']})")

    exp_only_long = ps["direction"] == "LONG"
    check(session_cfg["only_long"] == exp_only_long,
          f"{key}: only_long = {session_cfg['only_long']} (asteptat {exp_only_long})")

    check(cfg["optional_criteria"]["rsi"]["enabled"] == ps["rsi_enabled"],
          f"{key}: rsi.enabled = {cfg['optional_criteria']['rsi']['enabled']} (asteptat {ps['rsi_enabled']})")
    check(cfg["optional_criteria"]["rsi"]["buy_min"] == ps["rsi_buy_min"],
          f"{key}: rsi.buy_min = {cfg['optional_criteria']['rsi']['buy_min']} (asteptat {ps['rsi_buy_min']})")
    check(cfg["reward_ladder"]["rr_if_3_criteria"] == ps["r_base"],
          f"{key}: r_base = {cfg['reward_ladder']['rr_if_3_criteria']} (asteptat {ps['r_base']})")
    check(cfg["reward_ladder"]["rr_if_4_criteria"] == ps["r_mid"],
          f"{key}: r_mid = {cfg['reward_ladder']['rr_if_4_criteria']} (asteptat {ps['r_mid']})")
    check(cfg["reward_ladder"]["threshold_mid"] == ps["r_mid_threshold"],
          f"{key}: threshold_mid = {cfg['reward_ladder']['threshold_mid']} (asteptat {ps['r_mid_threshold']})")

# ---------------------------------------------------------------------------
# Test 3: reward_R() cu parametri modificati din profil
# ---------------------------------------------------------------------------
print("\n[Test 3] reward_R() cu parametri din profil")
_write_runtime(profile)

session_cfg = {"session_key": "session1", "pullback_window": 0, "session_start": 0,
               "session_end": 0, "only_long": True, "execute_trades": True}
cfg = _load_base_cfg()
_apply_profile_overrides(session_cfg, cfg, log)

r0 = reward_R(0, cfg)   # 0 criterii optionale -> r_base
r1 = reward_R(1, cfg)   # 1 criteriu -> r_mid
r2 = reward_R(2, cfg)   # 2 criterii -> r_top
r3 = reward_R(3, cfg)   # 3 criterii -> r_max

ps1 = next(s for s in profile["sessions"] if s["session_key"] == "session1")
check(r0 == ps1["r_base"], f"reward_R(0) = {r0} (asteptat {ps1['r_base']})")
check(r1 == ps1["r_mid"],  f"reward_R(1) = {r1} (asteptat {ps1['r_mid']})")
check(r2 == ps1["r_top"],  f"reward_R(2) = {r2} (asteptat {ps1['r_top']})")
check(r3 == ps1["r_max"],  f"reward_R(3) = {r3} (asteptat {ps1['r_max']})")

# ---------------------------------------------------------------------------
# Test 4: profil cu valori modificate (simuleaza un profil customizat)
# ---------------------------------------------------------------------------
print("\n[Test 4] Profil customizat — valori modificate")
custom = copy.deepcopy(profile)
s1 = next(s for s in custom["sessions"] if s["session_key"] == "session1")
s1["rsi_buy_min"] = 45
s1["rsi_buy_max"] = 70
s1["r_base"] = 2.0
s1["r_mid"] = 3.0
s1["r_top"] = 4.0
s1["pullback_window"] = 6
s1["execute_trades"] = False

_write_runtime(custom)

session_cfg = {"session_key": "session1", "pullback_window": 8, "session_start": 10,
               "session_end": 18, "only_long": True, "execute_trades": True}
cfg = _load_base_cfg()
_apply_profile_overrides(session_cfg, cfg, log)

check(session_cfg["pullback_window"] == 6,    "PW customizat aplicat (6)")
check(session_cfg["execute_trades"] is False,  "execute_trades customizat aplicat (False)")
check(cfg["optional_criteria"]["rsi"]["buy_min"] == 45, "rsi.buy_min customizat (45)")
check(cfg["optional_criteria"]["rsi"]["buy_max"] == 70, "rsi.buy_max customizat (70)")
check(reward_R(0, cfg) == 2.0, f"r_base customizat = {reward_R(0, cfg)} (asteptat 2.0)")
check(reward_R(1, cfg) == 3.0, f"r_mid customizat = {reward_R(1, cfg)} (asteptat 3.0)")

# ---------------------------------------------------------------------------
# Test 5: skip_weekdays si skip_monday
# ---------------------------------------------------------------------------
print("\n[Test 5] skip_weekdays / skip_monday")
custom2 = copy.deepcopy(profile)
s3 = next(s for s in custom2["sessions"] if s["session_key"] == "session3")
s3["skip_weekdays"] = [5, 6]   # sambata + duminica off

_write_runtime(custom2)
session_cfg = {"session_key": "session3", "skip_weekdays": [], "skip_monday": False,
               "pullback_window": 8, "session_start": 0, "session_end": 24,
               "only_long": False, "execute_trades": True}
cfg = _load_base_cfg()
_apply_profile_overrides(session_cfg, cfg, log)

check(session_cfg["skip_weekdays"] == {5, 6}, f"skip_weekdays = {session_cfg['skip_weekdays']} (asteptat {{5,6}})")
check(session_cfg["skip_monday"] is False, "skip_monday False (5 si 6, nu 0)")

# luni in skip -> skip_monday True
s3["skip_weekdays"] = [0, 5]
_write_runtime(custom2)
session_cfg["skip_weekdays"] = []
session_cfg["skip_monday"] = False
_apply_profile_overrides(session_cfg, cfg, log)
check(session_cfg["skip_monday"] is True, "skip_monday True cand 0 e in skip_weekdays")

# ---------------------------------------------------------------------------
# Hot-reload execute_trades (2026-07-17) — toggle observatie<->live fara restart
# ---------------------------------------------------------------------------
from live.signal_generator import _runtime_execute_trades
import live.signal_generator as _sg

# Foloseste acelasi DATA_DIR ca helperul (sg.DATA_DIR) pentru fisierul runtime.
_rt_file = os.path.join(_sg.DATA_DIR, "active_profile_runtime.json")

def _write_rt_exec(mapping: dict):
    prof = {"name": "T", "sessions": [
        {"session_key": k, **({"execute_trades": v} if v is not None else {})}
        for k, v in mapping.items()]}
    with open(_rt_file, "w", encoding="utf-8") as f:
        json.dump(prof, f)
    _sg._RUNTIME_ET_CACHE = {"mtime": None, "map": {}}   # forteaza re-citire

_write_rt_exec({"session20": True, "session4": False, "session99": None})
check(_runtime_execute_trades("session20") is True, "hot-reload: session20 execute=True")
check(_runtime_execute_trades("session4") is False, "hot-reload: session4 execute=False (OBS)")
check(_runtime_execute_trades("session99") is None, "hot-reload: sesiune fara camp -> None (pastreaza valoarea)")
check(_runtime_execute_trades("sessionX") is None, "hot-reload: sesiune absenta -> None")

# toggle live->obs se reflecta dupa schimbarea fisierului (invalidare mtime)
import time as _time; _time.sleep(0.02)
_write_rt_exec({"session20": False})
check(_runtime_execute_trades("session20") is False, "hot-reload: toggle True->False preluat (mtime)")

# fisier lipsa -> None (nu forteaza o valoare; apelantul pastreaza starea curenta)
_remove_runtime()
if os.path.exists(_rt_file):
    os.remove(_rt_file)
_sg._RUNTIME_ET_CACHE = {"mtime": None, "map": {}}
check(_runtime_execute_trades("session20") is None, "hot-reload: fisier lipsa -> None (fail-safe)")

# ---------------------------------------------------------------------------
# Curatare + sumar
# ---------------------------------------------------------------------------
_remove_runtime()

print(f"\n{'='*50}")
print(f"Rezultat: {PASS} PASS, {FAIL} FAIL")
if FAIL == 0:
    print("Toti parametrii profilului functioneaza corect.")
else:
    print(f"ATENTIE: {FAIL} test(e) au esuat!")
print('='*50)
sys.exit(0 if FAIL == 0 else 1)
