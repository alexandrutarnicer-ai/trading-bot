"""
Test aliniere sesiuni — verifica ca scripturile, profilul si api/config sunt 1:1.
Scripturile sunt descoperite dinamic (live/session<N>_*.py). Profilul e sursa de adevar la
runtime pentru parametri (account_fraction, flag-uri) — vezi CLAUDE.md.

Ruleaza: python scripts/test_sessions_alignment.py
Rezultat asteptat: toate testele PASS
"""

import os, sys, json, importlib.util

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

PASS = 0
FAIL = 0

def ok(msg):
    global PASS
    PASS += 1
    print(f"  PASS  {msg}")

def fail(msg):
    global FAIL
    FAIL += 1
    print(f"  FAIL  {msg}")

def check(cond, msg):
    ok(msg) if cond else fail(msg)


print("\n=== 1. Import toate scripturile session*.py ===")
SCRIPT_CONFIGS = {}
live_dir = os.path.join(ROOT, "live")
import glob, re
_scripts = {}
for path in glob.glob(os.path.join(live_dir, "session*_*.py")):
    m = re.match(r"session(\d+)_", os.path.basename(path))
    if m:
        _scripts[int(m.group(1))] = path
N_SESSIONS = max(_scripts) if _scripts else 0
for i in range(1, N_SESSIONS + 1):
    found = _scripts.get(i)
    if found is None:
        fail(f"S{i}: fisier script nu exista")
        continue
    try:
        spec = importlib.util.spec_from_file_location(f"session{i}", found)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        cfg = mod.SESSION_CONFIG
        SCRIPT_CONFIGS[f"session{i}"] = (cfg, os.path.basename(found))
        ok(f"S{i} ({os.path.basename(found)}): import OK | markets={cfg.get('markets')} key={cfg.get('session_key')}")
    except Exception as e:
        fail(f"S{i} ({os.path.basename(found)}): import EROARE — {e}")


print(f"\n=== 2. Verifica standard.json are {N_SESSIONS} sesiuni cu session_key corecti ===")
profile_path = os.path.join(ROOT, "data", "profiles", "standard.json")
try:
    with open(profile_path, encoding="utf-8") as f:
        profile = json.load(f)
    sessions_p = profile.get("sessions", [])
    check(len(sessions_p) == N_SESSIONS, f"standard.json are {len(sessions_p)} sesiuni (asteptat {N_SESSIONS})")
    profile_keys = {s["session_key"] for s in sessions_p}
    expected_keys = {f"session{i}" for i in range(1, N_SESSIONS + 1)}
    missing = expected_keys - profile_keys
    check(not missing, f"session_key-uri prezente in profil: {sorted(profile_keys)} | lipsa: {sorted(missing)}")
except Exception as e:
    fail(f"standard.json eroare citire: {e}")
    sessions_p = []


print(f"\n=== 3. Verifica api/config.py are {N_SESSIONS} sesiuni ===")
try:
    from api.config import SESSIONS, SESSION_MAP
    check(len(SESSIONS) == N_SESSIONS, f"api/config.py are {len(SESSIONS)} sesiuni (asteptat {N_SESSIONS})")
    api_ids = {s["id"] for s in SESSIONS}
    expected_ids = {f"session{i}" for i in range(1, N_SESSIONS + 1)}
    missing_api = expected_ids - api_ids
    check(not missing_api, f"sesiuni lipsa din api/config: {sorted(missing_api)}")
    ok("SESSION_MAP functional")
except Exception as e:
    fail(f"api/config import eroare: {e}")
    SESSIONS = []


print("\n=== 4. Aliniere script <-> profil <-> api/config per sesiune ===")
profile_map = {s["session_key"]: s for s in sessions_p}
api_config_map = {s["id"]: s for s in SESSIONS}

for key, (cfg, script_name) in SCRIPT_CONFIGS.items():
    sid = cfg.get("session_key", "")
    markets_script = cfg.get("markets", [])

    # Verifica session_key consistent
    check(sid == key, f"{script_name}: session_key='{sid}' (asteptat '{key}')")

    # Verifica piata unica in script
    check(len(markets_script) == 1, f"{script_name}: {len(markets_script)} piete (asteptat 1) — {markets_script}")

    # Verifica profil are sesiunea
    p = profile_map.get(key)
    if p:
        markets_profile = p.get("markets", [])
        check(
            markets_script == markets_profile,
            f"{script_name}: piata script={markets_script} == profil={markets_profile}"
        )
        # account_fraction: NU se compara cu default-ul din script — la pornire
        # _apply_profile_overrides il suprascrie cu valoarea din profil (sursa de adevar).
        frac_p = p.get("account_fraction", 0)
        check(0 < frac_p <= 1, f"{script_name}: account_fraction profil={frac_p:.2f} in (0, 1]")
    else:
        fail(f"{script_name}: {key} lipsa din profil")

    # Verifica api/config are sesiunea
    a = api_config_map.get(key)
    if a:
        markets_api = a.get("markets", [])
        check(
            markets_script == markets_api,
            f"{script_name}: piata script={markets_script} == api={markets_api}"
        )
    else:
        fail(f"{script_name}: {key} lipsa din api/config")


print("\n=== 5. Verifica flag-uri aliniate intre script si profil ===")
FLAG_SESSIONS_EXPECTED = {
    "session4": ("flag_enabled", True),
    "session7": ("flag_enabled", True),
    "session8": ("flag_enabled", True),
    "session10": ("flag_enabled", True),
    "session14": ("flag_enabled", True),
}
IB_SESSIONS_EXPECTED = {
    "session3": ("inside_bar_enabled", True),
    "session7": ("inside_bar_enabled", True),
    "session11": ("inside_bar_enabled", True),
    "session14": ("inside_bar_enabled", True),
    "session17": ("inside_bar_enabled", True),
    "session18": ("inside_bar_enabled", True),
}
BE_SESSIONS_EXPECTED = {
    "session2": ("break_even_enabled", True),
    "session14": ("break_even_enabled", True),
    "session16": ("break_even_enabled", True),
}

for key, (flag, expected_val) in {**FLAG_SESSIONS_EXPECTED, **IB_SESSIONS_EXPECTED, **BE_SESSIONS_EXPECTED}.items():
    cfg_script, script_name = SCRIPT_CONFIGS.get(key, ({}, "MISSING"))
    p = profile_map.get(key, {})
    script_val = cfg_script.get(flag, False)
    profile_val = p.get(flag, False)
    check(
        script_val == expected_val,
        f"{script_name}: {flag}={script_val} (asteptat {expected_val} in script)"
    )
    # profilul poate dezactiva o strategie (sursa de adevar la runtime) — doar informativ
    if profile_val != expected_val:
        print(f"  INFO  profil {key}: {flag}={profile_val} (default script {expected_val}) — se aplica profilul")


print("\n=== 6. Verifica execute_trades=False pentru S20 (XAUUSD) ===")
cfg20, name20 = SCRIPT_CONFIGS.get("session20", ({}, "MISSING"))
check(cfg20.get("execute_trades") == False, f"{name20}: execute_trades=False (XAUUSD obs only)")
p20 = profile_map.get("session20", {})
check(p20.get("execute_trades") == False, "profil S20: execute_trades=False")


print("\n=== 7. Verifica news_guard SYMBOL_CURRENCIES are toate pietele ===")
try:
    from live.news_guard import SYMBOL_CURRENCIES
    required = [
        "EURUSD", "AUDJPY", "BTCUSD", "GER40", "USDCHF", "US30",
        "XRPUSD", "EURCAD", "USDJPY", "GBPCAD", "USDCAD", "EURAUD",
        "EURJPY", "CHFJPY", "GBPUSD", "GBPAUD", "AUDCAD", "NZDJPY",
        "AUDNZD", "XAUUSD",
    ]
    for sym in required:
        check(sym in SYMBOL_CURRENCIES, f"news_guard: SYMBOL_CURRENCIES contine '{sym}'")
except Exception as e:
    fail(f"news_guard import eroare: {e}")


print("\n" + "=" * 55)
total = PASS + FAIL
print(f"REZULTAT: {PASS}/{total} PASS  |  {FAIL} FAIL")
if FAIL == 0:
    print(">>> TOATE TESTELE AU TRECUT <<<")
else:
    print(">>> ATENTIE: sunt erori de rezolvat! <<<")
print()
sys.exit(0 if FAIL == 0 else 1)
