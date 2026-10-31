"""
Diagnostic „botul nu face trade-uri" — STRICT READ-ONLY (nu plaseaza, nu modifica nimic).

Ruleaza pe masina pe care ruleaza botul (MT5 deschis):
    python scripts/diagnose_no_trades.py

Verifica, in ordinea cauzelor frecvente: fus orar + offset server, cont MT5 /
AutoTrading, deblocarea LIVE (cont real), profil activ + sesiuni pe executie,
pauze, Setari Globale, filtrul AI in mod Strict fara surse AI, procesul botului,
semnalele si blocajele din ultimele 7 zile, tranzactiile MT5 din ultimele 7 zile.
"""
import glob
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
DATA = os.path.join(ROOT, "data")
PROBLEMS: list[str] = []


def ok(msg):    print(f"  ✓ {msg}")
def info(msg):  print(f"  · {msg}")
def bad(msg):   print(f"  ✗ {msg}"); PROBLEMS.append(msg)
def warn(msg):  print(f"  ! {msg}")


def jload(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def section(t):
    print(f"\n[{t}]")


# 1. Fus orar --------------------------------------------------------------
section("1. Fus orar")
try:
    from tz_helper import get_configured_tz_name
    tz = get_configured_tz_name()
    ZoneInfo(tz)
    ok(f"fus configurat: {tz} (ora locala {datetime.now(ZoneInfo(tz)):%H:%M})")
    info(f"ora sistemului Windows: {datetime.now():%H:%M}")
    if tz != "Europe/Bucharest":
        warn("Orele de sesiune / skip_hours din profil sunt calibrate pe ora ROMANIEI; cu alt "
             "fus se aplica pe ora locala (decalaj 1h fata de backtest). Nu opreste trade-urile.")
except Exception as e:
    bad(f"fusul orar nu poate fi citit ({e}) — lipseste pachetul tzdata? `pip install tzdata`")

# 2. MT5 -------------------------------------------------------------------
section("2. MT5")
mt5 = None
try:
    import MetaTrader5 as mt5
    if not mt5.initialize():
        bad(f"MT5 nu se initializeaza: {mt5.last_error()} — terminalul e deschis si logat?")
        mt5 = None
except ImportError:
    bad("pachetul MetaTrader5 nu e instalat")
acc = None
if mt5:
    acc = mt5.account_info()
    term = mt5.terminal_info()
    if acc is None:
        bad("niciun cont logat in MT5")
    else:
        is_demo = acc.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO
        ok(f"cont {acc.login} @ {acc.server} — {'DEMO' if is_demo else 'REAL'} · equity {acc.equity:.2f} {acc.currency}")
    if term is not None:
        (ok if term.connected else bad)(f"terminal conectat la broker: {term.connected}")
        (ok if term.trade_allowed else bad)(
            f"AutoTrading (butonul Algo Trading din MT5): {'PORNIT' if term.trade_allowed else 'OPRIT — ordinele sunt refuzate'}")
    # offset server
    for sym in ("BTCUSD", "EURUSD"):
        r = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M1, 0, 1)
        if r is not None and len(r):
            srv = datetime.fromtimestamp(int(r[0]["time"]), tz=timezone.utc).replace(tzinfo=None)
            off = round((srv - datetime.now(timezone.utc).replace(tzinfo=None)).total_seconds() / 3600)
            if abs(off) <= 4:
                info(f"ora serverului broker ≈ UTC{off:+d} (din {sym})")
                break

# 3. Deblocare LIVE --------------------------------------------------------
section("3. Trading LIVE (cont real)")
flags = jload(os.path.join(DATA, "live_trading.json"), {})
info(f"data/live_trading.json: {flags or 'LIPSA (= totul blocat pe conturi reale)'}")
if acc is not None and mt5 and acc.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO and not flags.get("bot"):
    bad("contul e REAL dar botul NU e deblocat → sesiunile refuza conectarea (zero ordine). "
        "Activeaza „Trading LIVE → Bot” in Settings, apoi reporneste botul.")

# 4. Profil + sesiuni ------------------------------------------------------
section("4. Profil activ")
rt = jload(os.path.join(DATA, "active_profile_runtime.json"))
sessions = []
if not rt:
    bad("data/active_profile_runtime.json lipseste → sesiunile ruleaza pe parametrii din script. "
        "Porneste botul din UI o data.")
    rt = jload(os.path.join(DATA, "profiles", "standard.json"))
    if rt:
        info("verificarile urmatoare folosesc data/profiles/standard.json")
if rt:
    sessions = rt.get("sessions", [])
    ex = [s for s in sessions if s.get("execute_trades")]
    (ok if ex else bad)(f"profil „{rt.get('name')}”: {len(sessions)} sesiuni, {len(ex)} pe EXECUTIE "
                        f"({', '.join(s['id'] for s in ex) or 'niciuna — toate pe observatie'})")
paused = jload(os.path.join(DATA, "paused_sessions.json"), [])
if paused:
    warn(f"sesiuni pe pauza: {', '.join(paused)}")
gs = jload(os.path.join(DATA, "global_settings.json"), {}) or {}
on = [k for k, v in gs.items() if isinstance(v, dict) and v.get("enabled")]
info(f"Setari Globale active: {', '.join(on) or 'niciuna'}")

# 5. Filtru AI Strict ------------------------------------------------------
section("5. Filtru AI")
strict = [s["id"] for s in sessions if s.get("execute_trades") and s.get("ai_filter_enabled") and s.get("ai_filter_strict")]
if strict:
    provs = jload(os.path.join(DATA, "ai", "providers.json"), {}) or {}
    keys = [k for k, v in provs.items() if v]
    ollama_ok = False
    try:
        import urllib.request
        urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3)
        ollama_ok = True
    except Exception:
        pass
    info(f"sesiuni cu filtru AI + STRICT: {', '.join(strict)}")
    info(f"chei surse AI (data/ai/providers.json): {', '.join(keys) or 'niciuna'} · Ollama local: {'DA' if ollama_ok else 'NU'}")
    if not keys and not ollama_ok:
        bad("modul STRICT e activ dar NU exista nicio sursa AI functionala pe aceasta masina → "
            "FIECARE semnal e BLOCAT („Filtru AI STRICT: ordin BLOCAT”). Instaleaza Ollama / "
            "adauga chei AI, sau dezactiveaza Strict pe aceste sesiuni.")
else:
    ok("niciun filtru AI in mod Strict pe sesiunile de executie")

# 6. Procesul botului ------------------------------------------------------
section("6. Procesul botului")
pid_s = None
try:
    pid_s = open(os.path.join(DATA, "run_all.pid")).read().strip()
except OSError:
    pass
if not pid_s:
    bad("data/run_all.pid lipseste → botul nu ruleaza pe aceasta masina")
else:
    try:
        import ctypes
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(pid_s))
        code = ctypes.c_ulong()
        alive = bool(h) and ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code)) and code.value == 259
        (ok if alive else bad)(f"run_all PID {pid_s}: {'RULEAZA' if alive else 'MORT'}")
    except Exception:
        info(f"run_all PID {pid_s} (nu pot verifica)")

# 7. Semnale + blocaje 7 zile ---------------------------------------------
section("7. Ultimele 7 zile (jurnalul botului)")
import pandas as pd
since = datetime.now() - timedelta(days=7)
tot_sig, blocks = 0, {}
errors = []
for d in sorted(glob.glob(os.path.join(DATA, "live_signals", "session*"))):
    sk = os.path.basename(d)
    try:
        s = pd.read_csv(os.path.join(d, "signals.csv"), parse_dates=["time"])
        tot_sig += int((s["time"] >= since).sum())
    except Exception:
        pass
    try:
        o = pd.read_csv(os.path.join(d, "outcomes.csv"), parse_dates=["time_check"])
        o = o[o["time_check"] >= since]
        for st in ("ai_reject", "global_block"):
            n = int((o["status"] == st).sum())
            if n:
                blocks[st] = blocks.get(st, 0) + n
    except Exception:
        pass
    try:
        with open(os.path.join(d, "generator.log"), encoding="utf-8", errors="ignore") as f:
            tail = f.readlines()[-400:]
        for line in tail:
            if any(k in line for k in ("BLOCAT", "refuza", "RuntimeError", "NU este DEMO", "Traceback")):
                errors.append(f"{sk}: {line.strip()[:160]}")
    except OSError:
        pass
info(f"semnale detectate: {tot_sig} · respinse AI: {blocks.get('ai_reject', 0)} · blocate global: {blocks.get('global_block', 0)}")
if tot_sig == 0:
    warn("niciun semnal in 7 zile — normal doar daca botul n-a rulat sau piata a fost inchisa")
for e in errors[-8:]:
    warn(e)

# 8. MT5 7 zile -----------------------------------------------------------
section("8. Tranzactii MT5 (7 zile)")
if mt5:
    deals = mt5.history_deals_get(datetime.now() - timedelta(days=7), datetime.now() + timedelta(days=1)) or []
    ins = [d for d in deals if d.entry == 0 and d.type in (0, 1)]
    bot = sum(1 for d in ins if str(d.comment).startswith("S"))
    ai = sum(1 for d in ins if d.magic == 770015)
    info(f"pozitii deschise in 7 zile: {len(ins)} (bot {bot} · AI {ai} · altele {len(ins) - bot - ai})")
    orders = mt5.orders_get() or []
    info(f"ordine pending acum: {len(orders)}")
    mt5.shutdown()

print("\n" + "=" * 60)
if PROBLEMS:
    print("PROBLEME GASITE (in ordinea importantei):")
    for i, p in enumerate(PROBLEMS, 1):
        print(f"  {i}. {p}")
else:
    print("Nicio problema blocanta gasita. Daca tot nu apar trade-uri: frecventa normala e mica "
          "(cateva semnale/saptamana pe toate pietele) — verifica sectiunea 7.")
