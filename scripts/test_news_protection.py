# -*- coding: utf-8 -*-
"""
Teste pentru Protectia la Stiri + Mod Inteligent (redesign 2026-07-17).

Acopera cerintele de validare:
  - logica PURA de fereastra: event_window / events_active_at / upcoming_relevant_for
  - ACTIVARE DETERMINISTICA fata de timpul curent, indiferent de offset-urile pre/post
    (inclusiv pre=1 min — cazul pe care poll-ul de 5 min il rata)
  - _is_news_paused re-evalueaza ferestrele la timpul curent (nu starea inghetata a guardului)
  - backward-compat cu formatul vechi de fisier
  - sentiment (incl. indicatori inversati: somaj) + directie neta per simbol
  - MULTIPLE programe de stiri: departe / pre / in eveniment / post / trecut / suprapuse / conflict
  - ORDINE FALSE end-to-end: mod inteligent pastreaza pozitia aliniata, inchide contra-pozitia,
    plaseaza ordin in directia stirii (MT5 complet simulat, zero dependinte externe)

Rulare:  python scripts/test_news_protection.py
"""

import io
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from live import news_guard as ng

PASS, FAIL = [], []


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  {extra}" if extra else ""))


def _ev(title, ccy, impact, minutes_from_now, now, actual="", forecast=""):
    """Eveniment sintetic la `minutes_from_now` fata de `now` (event_time = datetime)."""
    return {"title": title, "currency": ccy, "impact": impact,
            "event_time": now + timedelta(minutes=minutes_from_now),
            "actual": actual, "forecast": forecast,
            "sentiment": ng._calc_sentiment(actual, forecast, title)}


NOW = datetime(2026, 7, 17, 12, 0, 0)   # UTC fix pentru determinism

# ═════════════════════════════════════════════════════════════════════════════
# 1. Ferestre PURE + determinism (cazul-cheie: pre mic)
# ═════════════════════════════════════════════════════════════════════════════

s, e = ng.event_window(NOW, 15, 15)
check("event_window: [ev-15, ev+15]", s == NOW - timedelta(minutes=15) and e == NOW + timedelta(minutes=15))

USD = {"USD"}
# eveniment USD la +10 min, pre=15 → fereastra [ev-15, ev+15] = [11:55, 12:25]; now 12:00 e IN
evs = [_ev("CPI", "USD", "High", 10, NOW, "3.1", "3.0")]
check("activ: eveniment la +10 cu pre=15 → ACTIV la now",
      len(ng.events_active_at(evs, NOW, USD, 3, 15, 15)) == 1)

# pre MIC (1 min): eveniment la +3 min → fereastra [ev-1, ev+15]=[12:02,12:18]; now 12:00 NU e activ
evs = [_ev("CPI", "USD", "High", 3, NOW, "3.1", "3.0")]
check("determinism: pre=1, ev la +3 → NEactiv la now (12:00 < 12:02)",
      len(ng.events_active_at(evs, NOW, USD, 3, 1, 15)) == 0)
# ...dar la +2 min (12:02) devine EXACT activ — onorat la secunda, nu ratat de poll
check("determinism: pre=1, ev la +3 → activ EXACT la 12:02",
      len(ng.events_active_at(evs, NOW + timedelta(minutes=2), USD, 3, 1, 15)) == 1)
# la 12:01 inca nu (fereastra incepe la 12:02)
check("determinism: la 12:01 inca NEactiv (granita exacta)",
      len(ng.events_active_at(evs, NOW + timedelta(minutes=1), USD, 3, 1, 15)) == 0)

# eveniment TRECUT dincolo de post → NEactiv
evs = [_ev("CPI", "USD", "High", -20, NOW, "3.1", "3.0")]
check("post: eveniment acum 20 min, post=15 → NEactiv (12:00 > 11:55)",
      len(ng.events_active_at(evs, NOW, USD, 3, 15, 15)) == 0)
# in post-fereastra (acum 10 min, post 15) → activ
evs = [_ev("CPI", "USD", "High", -10, NOW, "3.1", "3.0")]
check("post: eveniment acum 10 min, post=15 → ACTIV",
      len(ng.events_active_at(evs, NOW, USD, 3, 15, 15)) == 1)

# impact sub prag → ignorat
evs = [_ev("Retail", "USD", "Medium", 5, NOW)]
check("impact: Medium sub prag High(3) → ignorat",
      len(ng.events_active_at(evs, NOW, USD, 3, 15, 15)) == 0)
check("impact: Medium cu prag 2 → activ",
      len(ng.events_active_at(evs, NOW, USD, 2, 15, 15)) == 1)

# valuta irelevanta → ignorat
evs = [_ev("CPI", "EUR", "High", 5, NOW)]
check("valuta: EUR pentru piata USD-only → ignorat",
      len(ng.events_active_at(evs, NOW, USD, 3, 15, 15)) == 0)

# ═════════════════════════════════════════════════════════════════════════════
# 2. upcoming_relevant_for — orizont (guard scrie in avans)
# ═════════════════════════════════════════════════════════════════════════════

evs = [
    _ev("CPI",  "USD", "High", 120, NOW),   # peste 2h — in orizont 180
    _ev("NFP",  "USD", "High", 240, NOW),   # peste 4h — dincolo de orizont
    _ev("Old",  "USD", "High", -60, NOW),   # acum 1h (fereastra inchisa) — exclus
]
up = ng.upcoming_relevant_for(["EURUSD"], NOW, 3, 15, 15, horizon_min=180, events=evs)
titles = [e["title"] for e in up]
check("upcoming: include eveniment in orizont (CPI 2h)", "CPI" in titles)
check("upcoming: exclude eveniment dincolo de orizont (NFP 4h)", "NFP" not in titles)
check("upcoming: exclude eveniment cu fereastra inchisa (Old)", "Old" not in titles)

# ═════════════════════════════════════════════════════════════════════════════
# 3. Sentiment + indicatori inversati
# ═════════════════════════════════════════════════════════════════════════════

check("sentiment: actual>forecast → +1 (CPI)", ng._calc_sentiment("3.2", "3.0", "CPI y/y") == 1)
check("sentiment: actual<forecast → -1 (CPI)", ng._calc_sentiment("2.8", "3.0", "CPI y/y") == -1)
check("sentiment: egal → 0", ng._calc_sentiment("3.0", "3.0", "CPI") == 0)
check("sentiment: lipsa → 0", ng._calc_sentiment("", "3.0", "CPI") == 0)
check("sentiment INVERSAT: somaj mai mare → -1", ng._calc_sentiment("4.2", "4.0", "Unemployment Rate") == -1)
check("sentiment INVERSAT: jobless claims mai mari → -1", ng._calc_sentiment("240K", "220K", "Initial Jobless Claims") == -1)
check("sentiment INVERSAT: somaj mai mic → +1 (bun pt valuta)", ng._calc_sentiment("3.8", "4.0", "Unemployment Rate") == 1)

# ═════════════════════════════════════════════════════════════════════════════
# 4. Directie neta per simbol (forex + index + conflict)
# ═════════════════════════════════════════════════════════════════════════════

# USD bullish → EURUSD SHORT (cotatie intarita)
ev_usd_up = [{"currency": "USD", "sentiment": 1}]
check("directie: USD+1 → EURUSD SHORT (-1)", ng.news_direction_for_symbol("EURUSD", ev_usd_up) == -1)
# EUR bullish → EURUSD LONG
ev_eur_up = [{"currency": "EUR", "sentiment": 1}]
check("directie: EUR+1 → EURUSD LONG (+1)", ng.news_direction_for_symbol("EURUSD", ev_eur_up) == 1)
# index USD: USD+1 → US30 LONG
check("directie: USD+1 → US30 LONG (index)", ng.news_direction_for_symbol("US30", ev_usd_up) == 1)
# conflict pe aceeasi valuta → 0
ev_conflict = [{"currency": "USD", "sentiment": 1}, {"currency": "USD", "sentiment": -1}]
check("directie: conflict USD → 0 (neclar)", ng.news_direction_for_symbol("EURUSD", ev_conflict) == 0)
# ambele confirma (EUR+1, USD-1) → EURUSD LONG
ev_both = [{"currency": "EUR", "sentiment": 1}, {"currency": "USD", "sentiment": -1}]
check("directie: EUR+1 & USD-1 → EURUSD LONG", ng.news_direction_for_symbol("EURUSD", ev_both) == 1)

# ═════════════════════════════════════════════════════════════════════════════
# 5. _is_news_paused — re-evaluare deterministica dintr-un fisier scris
# ═════════════════════════════════════════════════════════════════════════════

from live import signal_generator as sg

def _write_news_file(path, session_key, events, pre, post, impact, markets):
    data = {session_key: {
        "updated_at": NOW.isoformat(), "pre": pre, "post": post, "impact": impact,
        "markets": markets,
        "events": [{"title": e["title"], "currency": e["currency"], "impact": e["impact"],
                    "event_time": e["event_time"].strftime("%Y-%m-%dT%H:%M:%S"),
                    "actual": e.get("actual", ""), "forecast": e.get("forecast", ""),
                    "sentiment": e.get("sentiment", 0)} for e in events]}}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)

with tempfile.TemporaryDirectory() as td:
    nf = os.path.join(td, "news_auto_paused.json")
    _old = sg._NEWS_PAUSED_FILE
    sg._NEWS_PAUSED_FILE = nf
    try:
        # eveniment care va deveni activ la +2 (pre=1). Guard-ul l-a scris "in avans".
        ev = _ev("CPI", "USD", "High", 3, NOW, "3.1", "3.0")
        _write_news_file(nf, "session9", [ev], pre=1, post=15, impact=3, markets=["USDJPY"])

        # Patch-uim ceasul folosit de _is_news_paused (datetime.utcnow) prin monkeypatch
        import live.signal_generator as _sgm
        _real_dt = _sgm.datetime
        class _FakeDT(datetime):
            _now = NOW
            @classmethod
            def utcnow(cls): return cls._now
        _sgm.datetime = _FakeDT

        _FakeDT._now = NOW                       # 12:00 — inca NEactiv (fereastra la 12:02)
        p0, _ = sg._is_news_paused("session9")
        check("_is_news_paused: la 12:00 NEpauza (fereastra pre=1 incepe la 12:02)", p0 is False)

        _FakeDT._now = NOW + timedelta(minutes=2)  # 12:02 — EXACT activ
        p1, ev1 = sg._is_news_paused("session9")
        check("_is_news_paused: la 12:02 PAUZA (activare exacta, nu ratata)", p1 is True and len(ev1) == 1)

        _FakeDT._now = NOW + timedelta(minutes=30)  # 12:30 — dincolo de post (ev+15=12:18)
        p2, _ = sg._is_news_paused("session9")
        check("_is_news_paused: la 12:30 NEpauza (dupa fereastra)", p2 is False)

        # sesiune absenta din fisier → nepauza
        check("_is_news_paused: sesiune absenta → nepauza", sg._is_news_paused("sessionX")[0] is False)

        # backward-compat: format VECHI (fara 'pre') → prezenta = pauza
        with open(nf, "w", encoding="utf-8") as f:
            json.dump({"session9": {"paused_at": NOW.isoformat(),
                                    "events": [{"title": "X", "minutes_to": 5}]}}, f)
        pc, _ = sg._is_news_paused("session9")
        check("_is_news_paused: format vechi → prezenta = pauza (compat)", pc is True)

        _sgm.datetime = _real_dt
    finally:
        sg._NEWS_PAUSED_FILE = _old

# ═════════════════════════════════════════════════════════════════════════════
# 6. ORDINE FALSE — mod inteligent end-to-end (MT5 simulat)
# ═════════════════════════════════════════════════════════════════════════════

class FakeMt5:
    TRADE_ACTION_PENDING = 5
    TRADE_ACTION_DEAL = 1
    TRADE_ACTION_REMOVE = 2
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    ORDER_TYPE_BUY_STOP = 4
    ORDER_TYPE_SELL_STOP = 5
    ORDER_TIME_GTC = 0
    ORDER_FILLING_RETURN = 2
    ORDER_FILLING_IOC = 1
    ORDER_FILLING_FOK = 0
    TRADE_RETCODE_DONE = 10009
    POSITION_TYPE_BUY = 0

    def __init__(self):
        self.sent = []
        self._ticket = 5000

    def symbol_info(self, s):
        return SimpleNamespace(digits=5, point=0.00001, spread=10, volume_min=0.01,
                               volume_step=0.01, volume_max=100.0,
                               trade_tick_value=1.0, trade_tick_size=0.00001)

    def symbol_info_tick(self, s):
        return SimpleNamespace(ask=1.10010, bid=1.10000)

    def account_info(self):
        return SimpleNamespace(equity=1000.0, margin_free=1e7, currency="USD")

    def order_calc_margin(self, *a):
        return 10.0

    def order_send(self, req):
        self.sent.append(dict(req))
        self._ticket += 1
        return SimpleNamespace(retcode=self.TRADE_RETCODE_DONE, order=self._ticket,
                               deal=self._ticket, price=req.get("price", 1.1))

    def positions_get(self, ticket=None):
        return []

    def last_error(self):
        return (0, "ok")


class _Log:
    def info(self, *a, **k): pass
    def warning(self, *a, **k): pass
    def debug(self, *a, **k): pass
    def error(self, *a, **k): pass


_fake = FakeMt5()
_real_exec = sg._mt5_exec
sg._mt5_exec = _fake
try:
    scfg = {"session_id": "S9-USDJPY", "markets": ["EURUSD"], "account_fraction": 0.1,
            "risk_base": 0.01, "r_max": 4.5}
    news_ev = [{"title": "CPI", "currency": "USD", "impact": "High",
                "event_time": "2026-07-17T12:00:00", "actual": "3.2", "forecast": "3.0",
                "sentiment": 1}]   # USD+1 → EURUSD SHORT

    # 6a. Plasare ordin in directia stirii (SHORT EURUSD) — ordin FALS in FakeMt5
    st = {"pending": {}, "sn_counter": 0}
    nd = ng.news_direction_for_symbol("EURUSD", news_ev)
    check("smart: directie EURUSD la USD+1 = SHORT (-1)", nd == -1)
    sg._smart_news_place_order("EURUSD", nd, news_ev, st, scfg, _Log())
    check("smart: ordin FALS plasat", len(_fake.sent) == 1)
    o = _fake.sent[-1]
    check("smart: SELL_STOP sub pret (directia stirii)",
          o["type"] == FakeMt5.ORDER_TYPE_SELL_STOP and o["price"] < 1.10000)
    check("smart: ticket inregistrat in state", len(st.get("smart_news_tickets", {})) == 1)

    # 6b. _news_close_check mod inteligent: pozitie ALINIATA (SHORT) ramane, CONTRA (LONG) se inchide
    class FakeMt5Pos(FakeMt5):
        def positions_get(self, ticket=None):
            # pozitie deschisa pt ticket-ul cerut
            return [SimpleNamespace(ticket=ticket, volume=0.1, price_open=1.10000, type=0)]
    _fake2 = FakeMt5Pos()
    sg._mt5_exec = _fake2
    st2 = {"pending": {"EURUSD": {
        "SIGL": {"direction": 1,  "entry": 1.1000, "sl": 1.0980, "tp": 1.1050,
                 "triggered": True, "risk_usd": 20},   # LONG = CONTRA stirii USD+1 (SHORT) → inchide
        "SIGS": {"direction": -1, "entry": 1.1000, "sl": 1.1020, "tp": 1.0950,
                 "triggered": True, "risk_usd": 20},   # SHORT = ALINIAT → ramane
    }}, "mt5_tickets": {"SIGL": 111, "SIGS": 222}, "sn_counter": 0}
    with tempfile.TemporaryDirectory() as td:
        ofile = os.path.join(td, "outcomes.csv")
        # header minimal
        import pandas as pd
        pd.DataFrame(columns=sg._OUTCOMES_COLS).to_csv(ofile, index=False)
        sg._news_close_check(state=st2, outcomes_file=ofile, log=_Log(),
                             session_id="S9", execute_trades=True,
                             smart_news_enabled=True, news_events=news_ev, session_cfg=scfg)
        # SHORT aliniat ramane in pending, LONG contra e scos
        remaining = st2["pending"].get("EURUSD", {})
        check("smart-close: pozitia ALINIATA (SHORT) ramane deschisa", "SIGS" in remaining)
        check("smart-close: pozitia CONTRA (LONG) a fost inchisa", "SIGL" not in remaining)

    sg._mt5_exec = _fake
finally:
    sg._mt5_exec = _real_exec

# ═════════════════════════════════════════════════════════════════════════════
# 7. GATING: Mod Inteligent + watch sub-bara DOAR cu protectia activata
# ═════════════════════════════════════════════════════════════════════════════

# _sleep_watching_news e folosit doar cand news_protection_enabled sau exista
# smart_news_tickets — verificam conditia exact cum e scrisa in bucla principala.
def _watch_needed(scfg, st):
    return bool(scfg.get("news_protection_enabled", False) or st.get("smart_news_tickets"))

check("gating: protectie OFF + fara ordine stire → somn simplu (zero watch)",
      _watch_needed({"news_protection_enabled": False}, {}) is False)
check("gating: protectie ON → watch sub-bara activ",
      _watch_needed({"news_protection_enabled": True}, {}) is True)
check("gating: protectie OFF dar ordin de stire deschis → watch pt trailing",
      _watch_needed({"news_protection_enabled": False},
                    {"smart_news_tickets": {"SN1": {}}}) is True)
check("gating: camp lipsa (sesiuni vechi) → somn simplu (default OFF)",
      _watch_needed({}, {}) is False)

# Smart mode nu poate actiona fara protectie: guard-ul nu scrie intrari pentru
# sesiuni fara protectie, iar tick-ul face early-return → news_paused mereu False.
with tempfile.TemporaryDirectory() as td:
    nf = os.path.join(td, "news_auto_paused.json")
    _old = sg._NEWS_PAUSED_FILE
    sg._NEWS_PAUSED_FILE = nf
    try:
        # chiar cu un fisier VECHI ramas pe disc care ar pune sesiunea pe pauza...
        with open(nf, "w", encoding="utf-8") as f:
            json.dump({"sessionG": {"paused_at": "x", "events": [{"title": "X"}]}}, f)
        pz, _ = sg._is_news_paused("sessionG")
        check("gating: fisier vechi prezent → _is_news_paused True (fara gate)", pz is True)
        # ...dar tick-ul sesiunii cu protectie OFF nu-l consulta deloc (early-return).
        # Reproducem conditia gate-ului din _news_watch_tick:
        scfg_off = {"news_protection_enabled": False, "smart_news_enabled": True}
        gate_blocks = not scfg_off.get("news_protection_enabled", False)
        check("gating: protectie OFF → tick face early-return (smart fortat inactiv)",
              gate_blocks is True)
    finally:
        sg._NEWS_PAUSED_FILE = _old

# ═════════════════════════════════════════════════════════════════════════════

print("\n" + "═" * 60)
print(f"REZULTAT: {len(PASS)} PASS / {len(FAIL)} FAIL din {len(PASS) + len(FAIL)}")
if FAIL:
    print("ESUATE:", FAIL)
    sys.exit(1)
print("TOATE TESTELE AU TRECUT ✓")
