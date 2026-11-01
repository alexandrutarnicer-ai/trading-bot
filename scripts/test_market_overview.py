"""
Teste offline pentru api/market_overview.build (Piete active pe Dashboard, toate engine-urile).

Scenariile QA din cerinta Dashboard-ului global:
  Custom 1 piata · Custom mai multe piete (S1/S2) · AI pe alta piata · Daily pe alta piata ·
  Noisy pe o singura piata · aceeasi piata pe toate 4 engine-urile · starile (oprit / blocat /
  observatie / in afara programului / in pozitie) · statistici MT5 pe engine · piete doar cu istoric.
Rulare: python scripts/test_market_overview.py
"""
from __future__ import annotations

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from api import market_overview as M  # noqa: E402

FAIL = 0


def check(name, cond, info=None):
    global FAIL
    print(("  OK  " if cond else "  FAIL ") + name + ("" if cond or info is None else f"  -> {info}"))
    if not cond:
        FAIL += 1


MON = datetime(2026, 11, 2, 12, 0)      # luni 12:00
SAT = datetime(2026, 10, 31, 12, 0)     # sambata


def sess(i, sym, **kw):
    s = {"id": f"S{i}", "session_key": f"session{i}", "symbol": sym, "direction": "BOTH", "tf": "M15",
         "execute": True, "session_start": 0, "session_end": 24, "skip_weekdays": [], "skip_hours": [],
         "friday_close_enabled": True, "running": True, "paused": False, "news_paused": False}
    s.update(kw)
    return s


def base(**kw):
    inp = {"custom": {"running": True, "sessions": []}, "ai": {"running": False, "markets": []},
           "daily": {"running": False, "markets": []}, "noisy": {}, "trades": [], "positions": [], "pending": []}
    inp.update(kw)
    return inp


def mk(d, sym):
    return next((m for m in d["markets"] if m["symbol"] == sym), None)


def tr(sym, src, net, day="2026-11-02"):
    return {"symbol": sym, "source": src, "profit": net, "commission": 0.0, "swap": 0.0,
            "close_time": datetime.fromisoformat(day + "T10:00:00")}


print("1. Custom — o piata / mai multe piete (S1, S2)")
d = M.build(base(custom={"running": True, "sessions": [sess(1, "EURUSD")]}), MON)
check("o piata Custom → un card activ", len(d["markets"]) == 1 and mk(d, "EURUSD")["status"] == "active")
d = M.build(base(custom={"running": True, "sessions": [sess(1, "EURUSD"), sess(2, "AUDJPY", direction="LONG")]}), MON)
check("S1 + S2 → doua carduri, fara S1/S2 ca titlu (piata e titlul)", {m["symbol"] for m in d["markets"]} == {"EURUSD", "AUDJPY"}
      and mk(d, "AUDJPY")["engines"][0]["ref"] == "S2")
check("directia pietei din sesiune", mk(d, "AUDJPY")["direction"] == "LONG")

print("2. AI / Daily / Noisy pe alte piete")
d = M.build(base(custom={"running": True, "sessions": [sess(1, "EURUSD")]},
                 ai={"running": True, "mode": "demo", "markets": ["CHFJPY"]},
                 daily={"running": True, "mode": "shadow", "markets": [{"symbol": "US500", "enabled": True}],
                        "status_markets": [{"symbol": "US500", "phase": "waiting_entry"}]},
                 noisy={"running": True, "mode": "shadow", "symbol": "USDJPY", "timeframe": "M1", "state": "running"}), MON)
check("4 piete distincte", {m["symbol"] for m in d["markets"]} == {"EURUSD", "CHFJPY", "US500", "USDJPY"})
check("AI pe CHFJPY = activ", mk(d, "CHFJPY")["engines"][0]["status"] == "active")
check("Daily shadow in fereastra = observatie (nu activ)", mk(d, "US500")["engines"][0]["status"] == "observe"
      and "shadow" in mk(d, "US500")["engines"][0]["reason"])
check("Noisy shadow = observatie, o singura piata", mk(d, "USDJPY")["engines"][0]["status"] == "observe"
      and sum(1 for m in d["markets"] for e in m["engines"] if e["engine"] == "noisy") == 1)

print("3. Aceeasi piata pe toate 4 engine-urile")
d = M.build(base(custom={"running": True, "sessions": [sess(15, "GBPUSD")]},
                 ai={"running": True, "mode": "demo", "markets": ["GBPUSD"]},
                 daily={"running": True, "mode": "execute", "markets": [{"symbol": "GBPUSD", "enabled": True}],
                        "status_markets": [{"symbol": "GBPUSD", "phase": "in_position"}]},
                 noisy={"running": True, "mode": "execute", "symbol": "GBPUSD", "timeframe": "M5", "state": "outside_window",
                        "reason": "intră doar 10:00–20:00"},
                 positions=[{"symbol": "GBPUSD", "source": "daily"}],
                 trades=[tr("GBPUSD", "bot", 5), tr("GBPUSD", "ai", -2), tr("GBPUSD", "daily", 3),
                         tr("GBPUSD", "noisy", -1), tr("GBPUSD", "manual", 4)]), MON)
g = mk(d, "GBPUSD")
check("un singur card cu 4 engine-uri in ordinea Custom/AI/Daily/Noisy", len(d["markets"]) == 1
      and g["engine_ids"] == ["custom", "ai", "daily", "noisy"])
check("starea agregata = cea mai 'vie' (in pozitie, din Daily)", g["status"] == "in_position")
check("fiecare engine pastreaza starea proprie", [e["status"] for e in g["engines"]] == ["active", "active", "in_position", "idle"],
      [e["status"] for e in g["engines"]])
check("statistici pe engine din MT5 (bot 5, ai -2, daily 3, noisy -1)",
      [g["stats_by_engine"][x]["net"] for x in ("custom", "ai", "daily", "noisy")] == [5, -2, 3, -1])
check("total piata = toate sursele (inclusiv manual 4) = 9", g["stats"]["net"] == 9 and g["stats_other"]["net"] == 4)
check("win rate piata 3/5 = 60% (aceeasi definitie ca /mt5/stats)", g["stats"]["win_rate"] == 60.0)

print("4. Stari: oprit / pauza / stiri / observatie / ore / Setari Globale / limite")
d = M.build(base(custom={"running": False, "sessions": [sess(1, "EURUSD")]}), MON)
check("Custom Engine oprit → oprit", mk(d, "EURUSD")["status"] == "stopped")
d = M.build(base(custom={"running": True, "sessions": [sess(1, "EURUSD", paused=True)]}), MON)
check("sesiune pe pauza → blocat 'pauză manuală'", mk(d, "EURUSD")["engines"][0]["reason"] == "pauză manuală")
d = M.build(base(custom={"running": True, "sessions": [sess(1, "EURUSD", news_paused=True)]}), MON)
check("stiri → blocat", mk(d, "EURUSD")["status"] == "blocked" and "știri" in mk(d, "EURUSD")["engines"][0]["reason"])
d = M.build(base(custom={"running": True, "sessions": [sess(4, "GER40", execute=False)]}), MON)
check("execute_trades=False → observatie", mk(d, "GER40")["status"] == "observe")
d = M.build(base(custom={"running": True, "sessions": [sess(1, "EURUSD", session_start=14, session_end=18)]}), MON)
check("in afara orelor → in afara programului", mk(d, "EURUSD")["status"] == "idle" and "14–18" in mk(d, "EURUSD")["engines"][0]["reason"])
d = M.build(base(custom={"running": True, "sessions": [sess(1, "EURUSD"), sess(3, "BTCUSD")]}), SAT)
check("weekend: FX in afara programului, cripto activ", mk(d, "EURUSD")["status"] == "idle" and mk(d, "BTCUSD")["status"] == "active")
d = M.build(base(custom={"running": True, "sessions": [sess(1, "EURUSD")]}, global_block="Circuit breaker global: 3 pierderi"), MON)
check("Setari Globale → blocat cu motivul global", mk(d, "EURUSD")["engines"][0]["reason"].startswith("Circuit breaker"))
d = M.build(base(ai={"running": True, "mode": "demo", "markets": ["CHFJPY", "GBPUSD"], "modes": {"GBPUSD": "observe"},
                     "market_status": {"CHFJPY": {"can_open": False, "reason": "limita zilnica 2/2"}}}), MON)
check("AI: can_open=False → blocat cu motivul engine-ului", mk(d, "CHFJPY")["engines"][0]["reason"] == "limita zilnica 2/2")
check("AI: piata in Observatie → observatie", mk(d, "GBPUSD")["status"] == "observe")
d = M.build(base(ai={"running": True, "mode": "demo", "markets": ["CHFJPY"]}), SAT)
check("AI weekend FX → in afara programului", mk(d, "CHFJPY")["status"] == "idle")
d = M.build(base(noisy={"running": True, "mode": "shadow", "symbol": "USDJPY", "state": "budget_locked",
                        "state_label": "Stopped – Budget Limit"}), MON)
check("Noisy budget lock → blocat", mk(d, "USDJPY")["status"] == "blocked" and "Budget" in mk(d, "USDJPY")["engines"][0]["reason"])
d = M.build(base(custom={"running": True, "sessions": [sess(9, "USDJPY")]}, positions=[{"symbol": "USDJPY", "source": "bot"}]), MON)
check("pozitie reala Custom → in pozitie", mk(d, "USDJPY")["status"] == "in_position" and mk(d, "USDJPY")["positions"] == 1)
d = M.build(base(daily={"running": True, "mode": "shadow", "markets": [{"symbol": "GBPUSD", "enabled": False}]}), MON)
check("piata Daily dezactivata → oprit", mk(d, "GBPUSD")["status"] == "stopped")

print("5. Fara hardcodare: piete doar cu istoric, MT5 indisponibil, semnale + virtuale")
d = M.build(base(custom={"running": True, "sessions": [sess(1, "EURUSD")]}, trades=[tr("AUDUSD", "ai", 2), tr("EURUSD", "bot", 1)]), MON)
check("AUDUSD (tranzactii AI, nu mai e configurata) → 'doar istoric', nu card",
      mk(d, "AUDUSD") is None and d["history_only"][0]["symbol"] == "AUDUSD" and d["history_only"][0]["sources"] == {"ai": 1})
d = M.build(base(custom={"running": True, "sessions": [sess(1, "EURUSD")]}, trades=None), MON)
check("MT5 indisponibil → statistici None (nu zero inventat)", mk(d, "EURUSD")["stats"] is None and d["mt5_connected"] is False)
d = M.build(base(noisy={"running": True, "mode": "shadow", "symbol": "USDJPY", "state": "running"},
                 signals_today={("USDJPY", "noisy"): 4}, virtual_today={("USDJPY", "noisy"): {"n": 4, "R": -0.5}}), MON)
e = mk(d, "USDJPY")["engines"][0]
check("Noisy: semnale azi + trade-uri virtuale separate (R, nu bani)", e["signals_today"] == 4 and e["virtual_today"] == {"trades": 4, "R": -0.5})
check("niciun simbol hardcodat in modul (piete doar din configuratii)",
      not any(s in open(M.__file__, encoding="utf-8").read() for s in ('"EURUSD"', '"GBPUSD"', '"USDJPY"', '"US500"')))

print("6. Zi azi / ieri in fusul aplicatiei")
d = M.build(base(custom={"running": True, "sessions": [sess(1, "EURUSD")]},
                 trades=[tr("EURUSD", "bot", 2, "2026-11-02"), tr("EURUSD", "bot", -1, "2026-11-01"), tr("EURUSD", "bot", 7, "2026-10-20")]), MON)
s = mk(d, "EURUSD")["stats"]
check("P&L azi 2, ieri -1, total 8", (s["pnl_today"], s["pnl_yesterday"], s["pnl"]) == (2, -1, 8), s)
tc = dict(tr("EURUSD", "bot", 5), commission=-0.5, swap=-0.2)
s2 = M._stats([tc], "2026-11-02", "2026-11-01")
check("P&L brut 5, costuri -0.7, net 4.3 (ca _perf)", (s2["pnl"], s2["costs"], s2["net"]) == (5, -0.7, 4.3), s2)

print(f"\n{'TOATE TESTELE AU TRECUT' if not FAIL else f'{FAIL} TESTE ESUATE'}")
sys.exit(1 if FAIL else 0)
