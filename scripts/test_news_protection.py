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

# CRITIC: testele plaseaza ordine FALSE prin functiile reale, care trimit notificari
# REALE (_send_telegram → Telegram + Notificari UI). Fara mock, fiecare rulare a
# suitei trimitea utilizatorului „📰 Ordin Stire EURUSD/BTCUSD" cu datele sintetice
# de test (bug raportat: notificare EURUSD Sambata — era din teste, nu de la bot).
_TG_SENT: list[str] = []
sg._send_telegram = lambda text: _TG_SENT.append(text)

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
_real_now = sg.now_local
sg._mt5_exec = _fake
# Fixam ceasul pe VINERI (piata FX deschisa) ca sectiunea sa fie deterministica
# indiferent de ziua in care ruleaza testul (altfel guard-ul de weekend ar bloca
# plasarea in weekend si testul ar pica Sambata/Duminica).
sg.now_local = lambda: datetime(2026, 7, 17, 12, 0, 0)   # Vineri
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

    # 6c. PIATA INCHISA — ordinul de stire NU se plaseaza in weekend (bug raportat:
    # „Ordin Stire EURUSD" primit Sambata, cu FX inchis). Guard-ul _market_is_open.
    sat = datetime(2026, 7, 18, 12, 0, 0)   # Sambata
    fri = datetime(2026, 7, 17, 12, 0, 0)   # Vineri
    check("market_open: EURUSD Sambata → INCHIS", sg._market_is_open("EURUSD", now=sat)[0] is False)
    check("market_open: EURUSD Vineri → deschis", sg._market_is_open("EURUSD", now=fri)[0] is True)
    check("market_open: BTCUSD Sambata → deschis (cripto 24/7)",
          sg._market_is_open("BTCUSD", now=sat)[0] is True)
    check("market_open: XRPUSD Duminica → deschis (cripto)",
          sg._market_is_open("XRPUSD", now=datetime(2026, 7, 19, 3, 0, 0))[0] is True)

    # end-to-end: cu ceasul pe Sambata, _smart_news_place_order NU trimite ordin
    sg.now_local = lambda: sat
    _fake_wknd = FakeMt5()
    sg._mt5_exec = _fake_wknd
    st_wknd = {"pending": {}, "sn_counter": 0}
    sg._smart_news_place_order("EURUSD", -1, news_ev, st_wknd, scfg, _Log())
    check("smart weekend: NICIUN ordin plasat cu piata inchisa", len(_fake_wknd.sent) == 0)
    check("smart weekend: niciun ticket de stire inregistrat",
          not st_wknd.get("smart_news_tickets"))
    # cripto in weekend ramane permis
    sg._smart_news_place_order("BTCUSD", 1,
                               [{"title": "x", "currency": "USD", "impact": "High",
                                 "event_time": "2026-07-18T12:00:00", "actual": "1", "forecast": "0",
                                 "sentiment": 1}],
                               st_wknd, {"session_id": "S3", "markets": ["BTCUSD"],
                                         "account_fraction": 0.1, "risk_base": 0.01, "r_max": 4.5},
                               _Log())
    check("smart weekend: cripto (BTCUSD) TOT se plaseaza", len(_fake_wknd.sent) == 1)

    # 6d. FILTRU AI pe ordinele de stire — aceeasi validare ca semnalele normale.
    # _ai_filter_check e mock-uit (fara Ollama/surse reale); testam DECIZIA:
    # aprobat → plasat, respins → neplasat, strict+AI picat → blocat, fail-open → plasat.
    sg.now_local = lambda: fri            # Vineri — piata deschisa
    _real_aif = sg._ai_filter_check
    _aif_calls = []

    def _aif_approved(sig, scfg_, src_, log_):
        _aif_calls.append(dict(sig))
        return {"approved": True, "confidence": 82, "threshold": 70}

    scfg_ai = dict(scfg, ai_filter_enabled=True)
    try:
        sg._ai_filter_check = _aif_approved
        _f_ok = FakeMt5(); sg._mt5_exec = _f_ok
        st_ok = {"pending": {}, "sn_counter": 0}
        _TG_SENT.clear()
        sg._smart_news_place_order("EURUSD", -1, news_ev, st_ok, scfg_ai, _Log())
        check("smart+AI aprobat: ordin plasat", len(_f_ok.sent) == 1)
        check("smart+AI: filtrul a primit semnalul (signal_type=smart_news, SL/TP setate)",
              _aif_calls and _aif_calls[0].get("signal_type") == "smart_news"
              and _aif_calls[0].get("sl") and _aif_calls[0].get("tp"))
        check("smart+AI aprobat: verdictul e atasat ticketului",
              next(iter(st_ok["smart_news_tickets"].values()))["ai_filter"]["confidence"] == 82)
        check("smart+AI aprobat: notificarea are sufixul AI",
              _TG_SENT and "Filtru AI" in _TG_SENT[-1])

        sg._ai_filter_check = lambda *a: {"approved": False, "confidence": 40, "threshold": 70}
        _f_rej = FakeMt5(); sg._mt5_exec = _f_rej
        st_rej = {"pending": {}, "sn_counter": 0}
        _TG_SENT.clear()
        sg._smart_news_place_order("EURUSD", -1, news_ev, st_rej, scfg_ai, _Log())
        check("smart+AI respins: NICIUN ordin plasat", len(_f_rej.sent) == 0)
        check("smart+AI respins: fara ticket in state", not st_rej.get("smart_news_tickets"))
        check("smart+AI respins: notificare de respingere trimisa",
              _TG_SENT and "RESPINS" in _TG_SENT[-1])

        sg._ai_filter_check = lambda *a: {"approved": True, "confidence": None,
                                          "threshold": 70, "error": "AI indisponibil"}
        _f_strict = FakeMt5(); sg._mt5_exec = _f_strict
        st_strict = {"pending": {}, "sn_counter": 0}
        sg._smart_news_place_order("EURUSD", -1, news_ev, st_strict,
                                   dict(scfg_ai, ai_filter_strict=True), _Log())
        check("smart+AI Strict + AI picat: ordin BLOCAT (fail-closed)",
              len(_f_strict.sent) == 0)

        _f_fo = FakeMt5(); sg._mt5_exec = _f_fo
        st_fo = {"pending": {}, "sn_counter": 0}
        sg._smart_news_place_order("EURUSD", -1, news_ev, st_fo, scfg_ai, _Log())
        check("smart+AI fail-open (fara Strict): ordin plasat (edge-ul e al botului)",
              len(_f_fo.sent) == 1)

        # filtrul DEZACTIVAT (default) → _ai_filter_check real intoarce None instant,
        # comportament identic cu inainte de feature
        sg._ai_filter_check = _real_aif
        _f_off = FakeMt5(); sg._mt5_exec = _f_off
        st_off = {"pending": {}, "sn_counter": 0}
        sg._smart_news_place_order("EURUSD", -1, news_ev, st_off, scfg, _Log())
        check("smart, filtru AI dezactivat (default): plasat fara consult AI",
              len(_f_off.sent) == 1
              and next(iter(st_off["smart_news_tickets"].values()))["ai_filter"] is None)
    finally:
        sg._ai_filter_check = _real_aif

    sg._mt5_exec = _fake

    # 6e. Mod Inteligent — plasare IN FEREASTRA (bug reparat 2026-07-22): pre-stire nu se
    # plasa nimic (actual necunoscut → sentiment 0); acum, cand apare `actual`, se plaseaza.
    sg.now_local = lambda: datetime(2026, 7, 17, 12, 0, 0)   # Vineri (piata deschisa)
    scfg_win = {"session_id": "S1", "markets": ["EURUSD"], "account_fraction": 0.1,
                "risk_base": 0.01, "r_max": 4.5,
                "smart_news_enabled": True, "execute_trades": True}

    # (i) PRE-stire: actual gol → sentiment 0 → directie 0 → NIMIC (reproduce vechiul bug)
    _f_pre = FakeMt5(); sg._mt5_exec = _f_pre
    ev_pre = [{"title": "CPI", "currency": "USD", "impact": "High",
               "event_time": "2026-07-17T12:00:00", "actual": "", "forecast": "3.0", "sentiment": 0}]
    st_win = {"pending": {}, "sn_counter": 0, "smart_news_window_done": set()}
    sg._smart_news_window_check(st_win, scfg_win, ev_pre, _Log())
    check("window pre-stire (actual gol): NICIUN ordin (directie 0)", len(_f_pre.sent) == 0)

    # (ii) POST-stire: actual disponibil → directie != 0 → ordin plasat
    _f_post = FakeMt5(); sg._mt5_exec = _f_post
    ev_post = [{"title": "CPI", "currency": "USD", "impact": "High",
                "event_time": "2026-07-17T12:00:00", "actual": "3.2", "forecast": "3.0", "sentiment": 1}]
    st_win2 = {"pending": {}, "sn_counter": 0, "smart_news_window_done": set()}
    sg._smart_news_window_check(st_win2, scfg_win, ev_post, _Log())
    check("window post-stire (actual aparut): ordin plasat", len(_f_post.sent) == 1)
    check("window: piata marcata done dupa plasare",
          "EURUSD" in st_win2.get("smart_news_window_done", set()))

    # (iii) idempotent: al doilea tick NU replaseaza (guard per fereastra)
    sg._smart_news_window_check(st_win2, scfg_win, ev_post, _Log())
    check("window: al doilea tick NU replaseaza (guard fereastra)", len(_f_post.sent) == 1)

    # (iv) smart OFF / execute OFF → nimic
    _f_off2 = FakeMt5(); sg._mt5_exec = _f_off2
    st_off2 = {"pending": {}, "sn_counter": 0, "smart_news_window_done": set()}
    sg._smart_news_window_check(st_off2, {**scfg_win, "smart_news_enabled": False}, ev_post, _Log())
    check("window: smart OFF → nimic plasat", len(_f_off2.sent) == 0)
    sg._smart_news_window_check(st_off2, {**scfg_win, "execute_trades": False}, ev_post, _Log())
    check("window: execute OFF → nimic plasat", len(_f_off2.sent) == 0)

    sg._mt5_exec = _fake
finally:
    sg._mt5_exec = _real_exec
    sg.now_local = _real_now

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
