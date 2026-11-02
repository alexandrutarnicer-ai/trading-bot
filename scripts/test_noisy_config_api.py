"""
Teste offline pentru configurarea Noisy Engine prin API (api/routers/noisy_engine.py) + comutarea pietei in engine.
MT5 simulat (market_info inlocuit), config intr-un director temporar, fara Telegram.
    python scripts/test_noisy_config_api.py
"""
from __future__ import annotations

import os
import sys
import tempfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import noisy_engine.config as C  # noqa: E402

TMP = tempfile.mkdtemp()
C.CFG_PATH = os.path.join(TMP, "config.json")
from api.routers import noisy_engine as R  # noqa: E402
from noisy_engine import engine as E  # noqa: E402

FAIL = 0
SENT: list[str] = []
R._tg = lambda t: SENT.append(t)


def check(name, cond, info=None):
    global FAIL
    print(("  OK  " if cond else "  FAIL ") + name + ("" if cond or info is None else f"  -> {info}"))
    if not cond:
        FAIL += 1


MARKETS = {"USDJPY": dict(point=0.001, digits=3, spread_live_points=9.0, tradable=True),
           "US500": dict(point=0.01, digits=2, spread_live_points=50.0, tradable=True),
           "OLD.NAS": dict(point=0.01, digits=2, spread_live_points=3.0, tradable=False)}


def fake_info(sym):
    m = MARKETS.get(str(sym).upper())
    return {"ok": False, "detail": f"simbolul {sym} nu există în contul MT5 curent"} if m is None else {"ok": True, "symbol": sym, **m}


R.market_info = fake_info
STATUS = {}
R._read = lambda path, default: STATUS if path == R.STATUS_FILE else default
R._read_pid = lambda: 1234 if STATUS.get("_running") else None
R._pid_alive = lambda pid: True


def err(fn):
    try:
        fn()
    except Exception as e:
        return getattr(e, "status_code", None), getattr(e, "detail", str(e))
    return None, None


print("1. Piata (Edit Market)")
C.save_config({})
code, det = err(lambda: R.noisy_config_save({"symbol": "NOPE"}))
check("piata inexistenta in MT5 → 400 cu motivul", code == 400 and "nu există" in det, (code, det))
code, det = err(lambda: R.noisy_config_save({"symbol": "OLD.NAS"}))
check("piata netranzactionabila → 400", code == 400 and "tranzacționabil" in det, (code, det))
check("config neschimbat dupa refuz", C.load_config()["symbol"] == "USDJPY")
STATUS.update(_running=True, open={"dir": "LONG"})
code, det = err(lambda: R.noisy_config_save({"symbol": "US500"}))
check("pozitie VIRTUALA deschisa (engine pornit) → 409", code == 409, (code, det))
STATUS.update(open=None, real_positions=[{"ticket": 1}])
check("pozitie REALA deschisa → 409", err(lambda: R.noisy_config_save({"symbol": "US500"}))[0] == 409)
STATUS.clear()
C.save_config({"spread": {"mode": "manual", "manual_points": 10, "max_mode": "manual", "max_points": 10}})
SENT.clear()
out = R.noisy_config_save({"symbol": "us500"})
check("schimbare valida → salvata (simbol normalizat la majuscule)", out["symbol"] == "US500" and C.load_config()["symbol"] == "US500")
check("spread manual al pietei vechi → trecut pe AUTO + notificare in raspuns",
      out["spread"]["mode"] == "auto" and out["spread"]["max_mode"] == "auto" and "AUTO" in (out.get("_notice") or ""), out.get("_notice"))
check("Telegram: piata schimbata, cu avertismentul 'netestata'", any("piața schimbată" in t and "USDJPY → US500" in t for t in SENT), SENT)
SENT.clear()
out = R.noisy_config_save({"symbol": "US500", "budget": {"capital": 50}})
check("salvare fara schimbare de piata → fara notificare de piata", not any("piața schimbată" in t for t in SENT) and "_notice" not in out)

print("2. Ferestre si spread prin API")
code, det = err(lambda: R.noisy_config_save({"window": {"intervals": []}}))
check("niciun interval → 400", code == 400 and "cel puțin" in det, det)
out = R.noisy_config_save({"window": {"intervals": [{"start": "16:00", "end": "22:00"}, {"start": "10:00", "end": "13:00"}]}})
check("doua intervale valide → salvate sortate", out["window"]["intervals"][0]["start"] == "10:00" and len(out["window"]["intervals"]) == 2)
out = R.noisy_config_save({"spread": {"mode": "manual", "manual_points": 40, "max_mode": "manual", "max_points": 60}})
check("spread manual salvat in points", out["spread"]["manual_points"] == 40 and out["spread"]["max_points"] == 60)
st = R.noisy_status()
check("status cu engine oprit: spread rezolvat cu point-ul pietei (US500: 40 points = 0,40)",
      st.get("spread", {}).get("typical_price") == 0.4 and st["spread"]["pip_points"] == 1, st.get("spread"))
check("status.config nu e alterat de rezolvare (fara valori derivate salvate)", st["config"]["spread"]["manual_points"] == 40)

print("3. Engine: comutarea pietei — starea per semnal arhivata / restaurata")
for k in ("STATUS_FILE", "STATE_FILE", "CONTROL_FILE", "TRADES_FILE"):
    setattr(E, k, os.path.join(TMP, os.path.basename(getattr(E, k))))
E._notify = lambda cfg, text: None


class M:
    def initialize(self):
        return True


eng = E.NoisyEngine(M())
eng.state.update(symbol="USDJPY", recorded=["20261102-1023"], checked=["2026-11-02T10:22:00"],
                 vetoed={"2026-11-02": ["2026-11-02T10:22:00"]}, placed=[])
eng._switch_symbol("US500")
check("pe US500 starea USDJPY nu se mai vede (ID-uri pe timestamp ar fi coliziune)",
      eng.state["recorded"] == [] and eng.state["vetoed"] == {} and eng.state["symbol"] == "US500")
eng.state["recorded"].append("20261102-1500")
eng._switch_symbol("USDJPY")
check("revenire pe USDJPY in aceeasi zi → starea restaurata (fara trade-uri dublate)",
      eng.state["recorded"] == ["20261102-1023"] and eng.state["vetoed"] == {"2026-11-02": ["2026-11-02T10:22:00"]})
check("… iar starea US500 e pastrata in arhiva", eng.state["per_symbol"]["US500"]["recorded"] == ["20261102-1500"])
check("stiri: valutele pietei din harta comuna (US500 → USD, GER40 → EUR, USDJPY → USD+JPY)",
      E.symbol_currencies("US500") == {"USD"} and E.symbol_currencies("GER40") == {"EUR"}
      and E.symbol_currencies("USDJPY") == {"USD", "JPY"}, (E.symbol_currencies("US500"), E.symbol_currencies("GER40")))

print(f"\n{'TOATE TESTELE AU TRECUT' if not FAIL else f'{FAIL} TESTE ESUATE'}")
sys.exit(1 if FAIL else 0)
