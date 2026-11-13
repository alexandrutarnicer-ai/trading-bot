"""
Teste offline: API-ul Special Engine (moduri per piata, setari proprii, audit, watchdog, atribuire MT5, lifecycle).
Config / date in director temporar; fara MT5, fara Telegram, fara procese pornite.
    python scripts/test_special_api.py
"""
from __future__ import annotations

import os
import sys
import tempfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import special_engine.config as C  # noqa: E402

TMP = tempfile.mkdtemp()
C.CFG_PATH = os.path.join(TMP, "config.json")
from api.routers import special_engine as R  # noqa: E402
import api.audit_log as AL  # noqa: E402
import api.telegram as TG  # noqa: E402

AL.AUDIT_FILE = os.path.join(TMP, "audit.jsonl")
R.DESIRED_FILE = os.path.join(TMP, "desired_running.json")
R.PID_FILE = os.path.join(TMP, "special_engine.pid")
R.STATUS_FILE = os.path.join(TMP, "status.json")
R.SELECTION_FILE = os.path.join(TMP, "selection.json")
SENT: list[str] = []
TG.send_message = lambda t: SENT.append(t)
R._tg = lambda t: SENT.append(t)
FAIL = 0


def check(name, cond, info=None):
    global FAIL
    print(("  OK  " if cond else "  FAIL ") + name + ("" if cond or info is None else f"  -> {info}"))
    if not cond:
        FAIL += 1


def refused(fn, *a, code=400):
    try:
        fn(*a)
    except R.HTTPException as e:
        return e.status_code == code
    return False


print("1. Moduri per piata (Live / Shadow / Pauza)")
r = R.special_market_mode("JP225", {"mode": "live"})
cfg = C.load_config()
check("JP225 → LIVE; USTEC rămâne SHADOW (independent); rezumat = execute",
      r["changed"] and C.market_mode(cfg, "JP225") == "live" and C.market_mode(cfg, "USTEC") == "shadow"
      and cfg["mode"] == "execute", cfg["markets"])
r = R.special_market_mode("USTEC", {"mode": "pause"})
cfg = C.load_config()
check("USTEC → PAUZĂ (cu momentul pauzei); JP225 rămâne LIVE", C.market_mode(cfg, "USTEC") == "pause"
      and cfg["markets"]["USTEC"]["paused_at"] and C.market_mode(cfg, "JP225") == "live", cfg["markets"])
check("mod repetat → fără schimbare", R.special_market_mode("JP225", {"mode": "live"})["changed"] is False)
check("piață necunoscută → 400", refused(R.special_market_mode, "NOPE", {"mode": "live"}))
check("mod invalid → 400", refused(R.special_market_mode, "JP225", {"mode": "turbo"}))
check("Telegram + audit la fiecare schimbare de mod", sum("Special Engine —" in t for t in SENT) == 2
      and [a["after"] for a in AL.read() if a["action"] == "mode"] == ["pause", "live"], SENT)
R.special_market_mode("JP225", {"mode": "shadow"})
check("JP225 înapoi pe SHADOW → rezumat shadow", C.load_config()["mode"] == "shadow")

print("2. Setarile proprii (capital / risc / limite) — validate, auditate, fara efect asupra Setarilor Globale")
from live import global_guard as GG  # noqa: E402
g_before = GG.load_settings()
out = R.special_config({"risk_pct": 0.5, "max_open_risk_pct": 0.5, "max_positions": 99, "max_margin_pct": 5,
                        "capital": {"capital_sync_mt5": False, "capital_usd": 150, "fraction": 2}})
check("valorile în afara limitelor sunt plafonate (risc ≤ 2%, risc total ≤ 10%, poziții ≤ 10, marjă ≥ 10%, fracție ≤ 100%)",
      (out["risk_pct"], out["max_open_risk_pct"], out["max_positions"], out["max_margin_pct"], out["capital"]["fraction"])
      == (0.02, 0.10, 10, 10.0, 1.0), out)
check("capital fix 150 $ salvat", out["capital"] == {"capital_sync_mt5": False, "capital_usd": 150.0, "fraction": 1.0})
check("modificările apar în audit", any(a["action"] == "config" and "risc / trade" in a["detail"] for a in AL.read()))
check("Setările Globale NU sunt atinse", GG.load_settings() == g_before)
check("modurile piețelor păstrate după salvarea setărilor", C.market_mode(C.load_config(), "USTEC") == "pause")

print("3. Stop din UI = oprire voita (watchdog-ul nu reporneste); status fara engine pornit")
open(R.DESIRED_FILE, "w").write("{}")
open(R.PID_FILE, "w").write(str(os.getpid()))
R.subprocess.run = lambda *a, **k: None          # niciun proces real oprit
R.special_stop()
check("Stop: desired_running.json șters (înainte de kill) + audit", not os.path.exists(R.DESIRED_FILE)
      and any(a["action"] == "stop" for a in AL.read()))
if os.path.exists(R.PID_FILE):
    os.remove(R.PID_FILE)
st = R.special_status()
check("status cu engine oprit: piețele + modurile lor (din configurație)", st["running"] is False
      and st["markets"].get("USTEC") == "pause", st.get("markets"))

print("4. Atribuire MT5 + Engine Lifecycle + live_guard")
from api import mt5_pool  # noqa: E402
check("magic 660001 → sursa „special”", mt5_pool.classify_trade(660001, "X-JP225-11120")["source"] == "special"
      and mt5_pool._classify_source(660001, "X-JP225-11120") == "special")
check("celelalte magic-uri neschimbate", mt5_pool.classify_trade(880001, "D-DE40-1112")["source"] == "daily"
      and mt5_pool.classify_trade(770015, "AI-1")["source"] == "ai")
from api import engine_lifecycle as EL  # noqa: E402
check("Special Engine în Engine Lifecycle (fără autostart propriu — watchdog-ul API)",
      "special" in EL.ENGINES and EL.ENGINES["special"]["task"] is None)
import live_guard  # noqa: E402
check("„special_engine” în componentele Trading LIVE (implicit BLOCAT pe cont real)",
      "special_engine" in live_guard.COMPONENTS)
from special_engine.config import MAGIC  # noqa: E402
check("MAGIC Special = mt5_pool.SPECIAL_MAGIC", MAGIC == mt5_pool.SPECIAL_MAGIC == 660001)

print(f"\n{'TOATE TESTELE AU TRECUT' if not FAIL else f'{FAIL} TESTE ESUATE'}")
sys.exit(1 if FAIL else 0)
