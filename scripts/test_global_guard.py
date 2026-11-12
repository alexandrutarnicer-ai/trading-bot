"""
Teste offline pentru live/global_guard.py (Setari Globale) + integrarea in
signal_generator / news_guard. Fara MT5 real (modul simulat), fara retea.

    python scripts/test_global_guard.py
"""
import os
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")   # consola Windows cp1252 nu afiseaza → / diacritice
except Exception:
    pass
import json
import copy
import tempfile
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from live import global_guard as gg

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}  {detail}")


def S(**over):
    s = copy.deepcopy(gg.DEFAULTS)
    for sec, vals in over.items():
        s[sec].update(vals)
    return gg.sanitize(s)


class Boom:
    """MT5 care pica la orice atingere — dovedeste ca globalul oprit nu interogheaza."""
    def __getattr__(self, name):
        raise AssertionError(f"MT5 atins: {name}")


class FakeMT5:
    TIMEFRAME_M15 = 15
    TIMEFRAME_M1 = 1

    def __init__(self, equity=200.0, balance=200.0, deals=(), positions=(), orders=(), extra=None):
        self._acc = NS(equity=equity, balance=balance)
        self._deals = list(deals)
        self._positions = list(positions)
        self._orders = list(orders)
        self._extra = extra or {}

    def account_info(self):
        return self._acc

    def history_deals_get(self, *a, position=None, **k):
        if position is not None:
            return self._extra.get(position, [])
        return self._deals

    def positions_get(self, symbol=None):
        return [p for p in self._positions if p.symbol == symbol]

    def orders_get(self, symbol=None):
        return [o for o in self._orders if o.symbol == symbol]


NOW = datetime(2026, 10, 30, 15, 0, 0)        # ora locala (naiva)


def ts(local_dt):
    """offset_h=0 in teste → epoch = ora locala citita ca UTC."""
    return int(local_dt.replace(tzinfo=timezone.utc).timestamp())


def trade(pid, net, minutes_ago, magic=0, comment="", symbol="EURUSD", entry_days_ago=0):
    t_in = NOW - timedelta(days=entry_days_ago, minutes=minutes_ago + 30)
    t_out = NOW - timedelta(minutes=minutes_ago)
    return [NS(type=0, entry=0, position_id=pid, symbol=symbol, magic=magic, comment=comment,
               commission=-0.1, swap=0.0, profit=0.0, time=ts(t_in)),
            NS(type=1, entry=1, position_id=pid, symbol=symbol, magic=magic, comment="[sl]",
               commission=-0.1, swap=0.0, profit=net + 0.2, time=ts(t_out))]


def hist(mt5):
    return gg.closed_today(mt5, now_local=NOW, offset_h=0, tz_name="Europe/Bucharest")


print("\n[1] Setari: default-uri, fisier lipsa/corupt, sanitizare")
d = gg.DEFAULTS
check("toate sectiunile OPRITE implicit", all(not v["enabled"] for v in d.values()))
check("filtru AI global DEZACTIVAT implicit", d["ai_filter"]["enabled"] is False)
check("pozitii simultane global DEZACTIVAT implicit", d["max_concurrent_per_market"]["enabled"] is False)
tmp = tempfile.mkdtemp()
check("fisier lipsa → default-uri", gg.load_settings(os.path.join(tmp, "x.json")) == gg.DEFAULTS)
bad = os.path.join(tmp, "bad.json")
open(bad, "w").write("{corupt")
check("fisier corupt → default-uri (totul oprit)", gg.load_settings(bad) == gg.DEFAULTS)
s = gg.sanitize({"friday_close": {"enabled": 1, "hour": 99}, "ai_filter": {"level": "xx"},
                 "news_protection": {"impact_level": 0}, "necunoscut": {"a": 1}})
check("clamp ora 0-23", s["friday_close"]["hour"] == 23)
check("nivel AI invalid → balanced", s["ai_filter"]["level"] == "balanced")
check("impact clamp 1-3", s["news_protection"]["impact_level"] == 1)
check("chei necunoscute ignorate", "necunoscut" not in s)
p = os.path.join(tmp, "g.json")
gg.save_settings({"circuit_breaker": {"enabled": True}}, p)
check("save → load round-trip", gg.load_settings(p)["circuit_breaker"]["enabled"] is True)

print("\n[2] „Cea mai stricta castiga\" — campuri efective sesiune")
bases = [
    {},
    {"friday_close_enabled": True, "friday_close_hour": 20},
    {"friday_close_enabled": False, "news_protection_enabled": True, "news_impact_level": 2,
     "news_pre_minutes": 30, "news_post_minutes": 10, "ai_filter_enabled": True,
     "ai_filter_level": "strict", "ai_filter_strict": True},
]
check("global oprit → valori sesiune IDENTICE (3 cazuri)",
      all(gg.effective_session_fields(b, ["EURUSD"], gg.DEFAULTS) == b for b in bases))
e = gg.effective_session_fields({"friday_close_enabled": True, "friday_close_hour": 20}, ["EURUSD"],
                                S(friday_close={"enabled": True, "hour": 18}))
check("vineri: global 18 + sesiune 20 → 18", e["friday_close_hour"] == 18 and e["friday_close_enabled"])
e = gg.effective_session_fields({"friday_close_enabled": True, "friday_close_hour": 16}, ["EURUSD"],
                                S(friday_close={"enabled": True, "hour": 18}))
check("vineri: sesiune mai stricta (16) ramane 16", e["friday_close_hour"] == 16)
e = gg.effective_session_fields({"friday_close_enabled": False}, ["EURUSD"],
                                S(friday_close={"enabled": True, "hour": 19}))
check("vineri: sesiune oprita → activata la ora globala", e["friday_close_enabled"] and e["friday_close_hour"] == 19)
e = gg.effective_session_fields({"friday_close_enabled": False}, ["BTCUSD"],
                                S(friday_close={"enabled": True, "hour": 19}))
check("vineri: cripto exceptat (exclude_crypto)", e["friday_close_enabled"] is False)
e = gg.effective_session_fields({"friday_close_enabled": False}, ["BTCUSD"],
                                S(friday_close={"enabled": True, "hour": 19, "exclude_crypto": False}))
check("vineri: cripto inclus daca exclude_crypto=False", e["friday_close_enabled"] is True)
e = gg.effective_session_fields(bases[2], ["EURUSD"],
                                S(news_protection={"enabled": True, "impact_level": 3,
                                                   "pre_minutes": 15, "post_minutes": 45}))
check("stiri: impact min(3,2)=2, pre max(15,30)=30, post max(45,10)=45",
      (e["news_impact_level"], e["news_pre_minutes"], e["news_post_minutes"]) == (2, 30, 45))
e = gg.effective_session_fields({}, ["EURUSD"], S(news_protection={"enabled": True, "impact_level": 2}))
check("stiri: sesiune fara protectie → valorile globale", e["news_protection_enabled"] and e["news_impact_level"] == 2)
e = gg.effective_session_fields({"ai_filter_enabled": True, "ai_filter_level": "permissive"}, [],
                                S(ai_filter={"enabled": True, "level": "balanced"}))
check("AI: permissive vs global balanced → balanced", e["ai_filter_level"] == "balanced")
e = gg.effective_session_fields(bases[2], [], S(ai_filter={"enabled": True, "level": "balanced"}))
check("AI: sesiune strict ramane strict + Strict pastrat", e["ai_filter_level"] == "strict" and e["ai_filter_strict"])
e = gg.effective_session_fields({}, [], S(ai_filter={"enabled": True, "level": "permissive", "strict": True}))
check("AI: sesiune oprita → activat cu nivelul global", e["ai_filter_enabled"] and e["ai_filter_strict"])
check("AI weekend: global oprit → config AI (22)", gg.effective_ai_weekend({}, "EURUSD", gg.DEFAULTS) == (True, 22))
check("AI weekend: global 20 → 20",
      gg.effective_ai_weekend({}, "EURUSD", S(friday_close={"enabled": True, "hour": 20})) == (True, 20))
check("AI weekend: cripto exceptat",
      gg.effective_ai_weekend({}, "XRPUSD", S(friday_close={"enabled": True, "hour": 20})) == (True, 22))

print("\n[3] Istoricul zilei (MT5) + atribuire")
deals = (trade(1, -1.0, 200, comment="S5-USDCHF-SIG3") + trade(2, 2.0, 100, magic=770015, comment="AI-9")
         + trade(3, -0.5, 50, comment="manual") + trade(4, -3.0, 60 * 24 + 60, comment="S5-X"))
mt = FakeMT5(deals=deals)
h = hist(mt)
check("doar azi (ieri exclus)", len(h) == 3, h)
check("ordine cronologica", [x["net"] for x in h] == [-1.0, 2.0, -0.5], h)
check("atribuire bot/ai/manual", [x["source"] for x in h] == ["bot", "ai", "manual"])
check("sesiune din comment", h[0]["session_id"] == "session5")
old = trade(7, -2.0, 30, comment="S9-USDJPY-IB001")
mt = FakeMT5(deals=[old[1]], extra={7: [old[0]]})
h = hist(mt)
check("intrare mai veche decat fereastra → cerere position=", h and h[0]["session_id"] == "session9", h)
check("serie pierderi: [-,+,-] → 1", gg.consecutive_losses([{"net": -1}, {"net": 1}, {"net": -1}]) == 1)
check("serie pierderi: [-,-,-] → 3", gg.consecutive_losses([{"net": -1}] * 3) == 3)

print("\n[4] check_open — decizia unica")
check("totul oprit → permis FARA nicio interogare MT5",
      gg.check_open(Boom(), "bot", "EURUSD", "session1", 0, gg.DEFAULTS) == (True, ""))
check("AI, totul oprit → permis fara MT5", gg.check_open(Boom(), "ai", "EURUSD", settings=gg.DEFAULTS)[0])
cps = S(capital_protection={"enabled": True, "threshold_pct": 70, "start_balance": 200})
check("capital: equity 150 < 140? nu → permis", gg.check_open(FakeMT5(equity=150), "bot", "X", settings=cps)[0])
ok, why = gg.check_open(FakeMT5(equity=130), "ai", "X", settings=cps)
check("capital: equity 130 < 140 → BLOCAT (si AI)", not ok and "PROTECTIE CAPITAL" in why, why)
cbs = S(circuit_breaker={"enabled": True, "max_consecutive_losses": 3})
three = [{"net": -1, "source": "ai", "session_id": None}] * 3
ok, why = gg.check_open(FakeMT5(), "bot", "X", settings=cbs, trades_today=three)
check("CB global: 3 pierderi (oricare engine) → BLOCAT", not ok and "GLOBAL" in why, why)
tt2 = [{"net": -6.0, "source": "bot", "session_id": None}, {"net": 0.5, "source": "ai", "session_id": None}]
check("CB global: pierdere 5.5$ (2.75%) < 5% → permis",
      gg.check_open(FakeMT5(balance=194.5), "ai", "X", settings=S(circuit_breaker={"enabled": True,
                    "max_consecutive_losses": 50, "max_daily_loss_pct": 5}), trades_today=tt2)[0])
check("CB global: castig la final reseteaza",
      gg.check_open(FakeMT5(), "bot", "X", settings=cbs,
                    trades_today=three + [{"net": 1, "source": "bot", "session_id": None}])[0])
dls = S(circuit_breaker={"enabled": True, "max_consecutive_losses": 50, "max_daily_loss_pct": 5})
tt = [{"net": -12.0, "source": "bot", "session_id": "session1"}, {"net": 0.5, "source": "ai", "session_id": None}]
ok, why = gg.check_open(FakeMT5(balance=188.5), "ai", "X", settings=dls, trades_today=tt)
check("CB global: pierdere zilnica 11.5$ (5.75%) ≥ 5% din 200$ → BLOCAT", not ok, why)
sess = [{"net": -1, "source": "bot", "session_id": "session3"}] * 2 + \
       [{"net": -1, "source": "ai", "session_id": None}] * 5
check("CB sesiune: 2 pierderi proprii < 3 → permis (pierderile AI nu conteaza)",
      gg.check_open(FakeMT5(), "bot", "X", "session3", 3, gg.DEFAULTS, trades_today=sess)[0])
ok, why = gg.check_open(FakeMT5(), "bot", "X", "session3", 2, gg.DEFAULTS, trades_today=sess)
check("CB sesiune: 2 pierderi proprii ≥ 2 → BLOCAT", not ok and "session3" in why, why)
check("CB sesiune 0 (oprit) → fara MT5", gg.check_open(Boom(), "bot", "X", "session3", 0, gg.DEFAULTS)[0])
mcs = S(max_concurrent_per_market={"enabled": True, "max": 2})
mt = FakeMT5(positions=[NS(symbol="EURUSD")], orders=[NS(symbol="EURUSD"), NS(symbol="GBPUSD")])
ok, why = gg.check_open(mt, "bot", "EURUSD", settings=mcs)
check("simultane: 1 pozitie + 1 pending pe EURUSD ≥ 2 → BLOCAT (toate engine-urile)", not ok, why)
check("simultane: GBPUSD 1 < 2 → permis", gg.check_open(mt, "ai", "GBPUSD", settings=mcs)[0])


class Broken(FakeMT5):
    def account_info(self):
        raise RuntimeError("IPC")


ok, why = gg.check_open(Broken(), "bot", "X", settings=cps)
check("eroare MT5 → permis (fail-open) cu motiv notat", ok and "eroare" in why, why)

print("\n[5] Integrare signal_generator._apply_global_fields")
import logging
from live import signal_generator as sg
log = logging.getLogger("t")
orig_load = gg.load_settings
try:
    gg.load_settings = lambda path=None: copy.deepcopy(gg.DEFAULTS)
    cfg = {"session_key": "session1", "friday_close_hour": 20, "risk_pct": 0.01}
    before = dict(cfg)
    base = {k: cfg[k] for k in gg.GLOBAL_SESSION_FIELDS if k in cfg}
    sg._apply_global_fields(cfg, base, ["EURUSD"], log)
    check("global oprit → session_cfg neschimbat (chei lipsa raman lipsa)", cfg == before, cfg)
    gg.load_settings = lambda path=None: S(friday_close={"enabled": True, "hour": 18},
                                           ai_filter={"enabled": True})
    sg._apply_global_fields(cfg, base, ["EURUSD"], log)
    check("global pornit → aplicat", cfg["friday_close_hour"] == 18 and cfg["ai_filter_enabled"] is True)
    gg.load_settings = lambda path=None: copy.deepcopy(gg.DEFAULTS)
    sg._apply_global_fields(cfg, base, ["EURUSD"], log)
    check("global oprit din nou → revine EXACT la sesiune", cfg == before, cfg)

    print("\n[6] Integrare news_guard._effective_configs")
    from live import news_guard as ng
    confs = [{"session_key": "session1", "markets": ["EURUSD"], "news_protection_enabled": False,
              "news_impact_level": 3, "news_pre_minutes": 15, "news_post_minutes": 15}]
    check("global oprit → config sesiune identic", ng._effective_configs(confs) == confs)
    gg.load_settings = lambda path=None: S(news_protection={"enabled": True, "impact_level": 2,
                                                            "pre_minutes": 20})
    eff = ng._effective_configs(confs)[0]
    check("global pornit → protectie activa cu valorile globale",
          eff["news_protection_enabled"] and eff["news_impact_level"] == 2 and eff["news_pre_minutes"] == 20, eff)
    check("lista originala nemodificata", confs[0]["news_protection_enabled"] is False)
finally:
    gg.load_settings = orig_load

print("friday_close_now — inchiderea de vineri comuna (Daily / Special)")
_fc = gg.sanitize({"friday_close": {"enabled": True, "hour": 20}})
_tz_orig = gg._tz_name
gg._tz_name = lambda: "Europe/Bucharest"
try:
    check("vineri 19:59 RO -> nu", not gg.friday_close_now("DE40", datetime(2026, 11, 13, 17, 59, tzinfo=timezone.utc), settings=_fc)[0])
    check("vineri 20:00 RO -> da", gg.friday_close_now("DE40", datetime(2026, 11, 13, 18, 0, tzinfo=timezone.utc), settings=_fc)[0])
    check("joi 21:00 RO -> nu", not gg.friday_close_now("DE40", datetime(2026, 11, 12, 19, 0, tzinfo=timezone.utc), settings=_fc)[0])
    check("cripto exceptat", not gg.friday_close_now("BTCUSD", datetime(2026, 11, 13, 19, 0, tzinfo=timezone.utc), settings=_fc)[0])
    check("regula oprita -> nu", not gg.friday_close_now("DE40", datetime(2026, 11, 13, 19, 0, tzinfo=timezone.utc),
                                                         settings=gg.sanitize(None))[0])
finally:
    gg._tz_name = _tz_orig

print(f"\n{'=' * 60}\nREZULTAT: {PASS} PASS, {FAIL} FAIL")
sys.exit(1 if FAIL else 0)
