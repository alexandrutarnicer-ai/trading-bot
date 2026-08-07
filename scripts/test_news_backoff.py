# -*- coding: utf-8 -*-
"""
Teste pentru robustetea sursei de stiri (news_guard) — fixuri 2026-08-06:
  - Backoff exponential la 429 pe ForexFactory (nu mai batem in usa cand suntem blocati)
  - Throttle nextweek.json (aducut rar -> mai putine cereri -> mai putine 429)
  - Keep last-good cache in _refresh cand TOATE sursele pica (protectia NU se opreste)
  - Keep last-good cache in perception._calendar la fetch gol

Rulare:
    python scripts/test_news_backoff.py     # offline, fara retea/MT5
"""

import io
import os
import sys
import urllib.error
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import live.news_guard as ng

_passed = _failed = 0


def check(cond, msg):
    global _passed, _failed
    if cond:
        _passed += 1; print(f"  OK  {msg}")
    else:
        _failed += 1; print(f"  XX  {msg}")


def _reset_ff():
    ng._ff_fails = 0
    ng._ff_backoff_until = None
    ng._nextweek_last = None


class _FakeResp:
    def __init__(self, data): self._d = data
    def read(self): return self._d
    def __enter__(self): return self
    def __exit__(self, *a): return False


def test_backoff_escalation():
    print("[1] Backoff exponential la 429 (escaladare + plafon + reset)")
    _reset_ff()
    t0 = datetime(2026, 8, 6, 12, 0, 0)
    check(ng._ff_should_skip(t0) is False, "initial: fara backoff")
    ng._ff_note_429(t0)
    # primul 429 -> BASE (600s)
    check(ng._ff_should_skip(t0 + timedelta(seconds=599)), "dupa 429#1: skip in fereastra (599s)")
    check(ng._ff_should_skip(t0 + timedelta(seconds=601)) is False, "dupa 429#1: expira la BASE (601s)")
    # al doilea 429 -> 1200s
    ng._ff_note_429(t0)
    check(ng._ff_should_skip(t0 + timedelta(seconds=1199)), "dupa 429#2: fereastra ~1200s")
    # escaladare pana la plafon
    for _ in range(6):
        ng._ff_note_429(t0)
    span = (ng._ff_backoff_until - t0).total_seconds()
    check(span <= ng.FF_BACKOFF_CAP_S, f"plafon respectat: {span:.0f}s <= {ng.FF_BACKOFF_CAP_S}s")
    # reset dupa succes
    ng._ff_note_ok()
    check(ng._ff_backoff_until is None and ng._ff_fails == 0, "note_ok reseteaza backoff-ul")


def test_fetch_skips_during_backoff():
    print("[2] _fetch_forexfactory sare peste FF cat timp e in backoff")
    _reset_ff()
    ng._ff_note_429()  # activeaza backoff acum
    calls = []
    orig = ng.urllib.request.urlopen
    ng.urllib.request.urlopen = lambda req, timeout=None: calls.append(req.full_url) or _FakeResp(b"[]")
    try:
        out = ng._fetch_forexfactory()
    finally:
        ng.urllib.request.urlopen = orig
    check(out == [] and calls == [], "in backoff: 0 cereri HTTP catre FF, returneaza []")


def test_429_activates_backoff():
    print("[3] Un 429 real activeaza backoff-ul")
    _reset_ff()
    orig = ng.urllib.request.urlopen
    def boom(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", {}, None)
    ng.urllib.request.urlopen = boom
    try:
        out = ng._fetch_forexfactory()
    finally:
        ng.urllib.request.urlopen = orig
    check(out == [], "429: returneaza [] (fara evenimente)")
    check(ng._ff_should_skip(), "429: backoff activ dupa")


def test_nextweek_throttle():
    print("[4] nextweek.json e adus rar (throttle)")
    _reset_ff()
    calls = []
    orig = ng.urllib.request.urlopen
    ng.urllib.request.urlopen = lambda req, timeout=None: calls.append(req.full_url) or _FakeResp(b"[]")
    try:
        ng._fetch_forexfactory()          # prima aducere: thisweek + nextweek
        first = list(calls); calls.clear()
        ng._fetch_forexfactory()          # imediat dupa: nextweek throttled
        second = list(calls)
    finally:
        ng.urllib.request.urlopen = orig
    check(any("nextweek" in u for u in first), "prima aducere include nextweek")
    check(any("thisweek" in u for u in second), "a doua aducere include thisweek")
    check(not any("nextweek" in u for u in second), "a doua aducere NU readuce nextweek (throttle)")


def test_refresh_keeps_last_good():
    print("[5] _refresh pastreaza cache-ul cand TOATE sursele pica (protectia nu se opreste)")
    # pre-seed cache cu un eveniment „bun"
    good = [{"title": "CPI m/m", "currency": "USD", "impact": "High",
             "event_time": datetime.utcnow() + timedelta(hours=1),
             "actual": "", "forecast": "3.0", "sentiment": 0, "_source": "ff"}]
    ng._cached = list(good)
    ng._cache_time = datetime.utcnow()
    saved = (ng._fetch_forexfactory, ng._fetch_mt5, ng._finnhub_key)
    ng._fetch_forexfactory = lambda: []      # FF gol (429/backoff)
    ng._fetch_mt5 = lambda: []               # MT5 dead
    ng._finnhub_key = lambda: ""             # fara finnhub
    try:
        ng._refresh()
        check(ng._cached == good, "cache pastrat identic cand toate sursele dau gol")
        # acum o sursa revine -> cache se actualizeaza
        newev = [{"title": "NFP", "currency": "USD", "impact": "High",
                  "event_time": datetime.utcnow() + timedelta(hours=2),
                  "actual": "", "forecast": "200K", "sentiment": 0, "_source": "ff"}]
        ng._fetch_forexfactory = lambda: list(newev)
        ng._refresh()
        check(len(ng._cached) == 1 and ng._cached[0]["title"] == "NFP",
              "cache se actualizeaza cand o sursa revine")
    finally:
        ng._fetch_forexfactory, ng._fetch_mt5, ng._finnhub_key = saved
        ng._cached = []; ng._cache_time = None


def test_perception_keeps_last_good():
    print("[6] perception._calendar pastreaza ultima lista buna la fetch gol")
    import ai_engine.perception as perc
    seed = [{"title": "ISM", "currency": "USD", "impact": "High",
             "event_time": datetime.utcnow(), "sentiment": 0}]
    perc._cal_cache = list(seed)
    perc._cal_time = None  # forteaza refresh
    orig = perc._fetch_forexfactory
    perc._fetch_forexfactory = lambda: []   # fetch gol (FF 429)
    try:
        out = perc._calendar()
        check(out == seed, "cache pastrat cand fetch-ul e gol")
    finally:
        perc._fetch_forexfactory = orig
        perc._cal_cache = []; perc._cal_time = None


def main():
    print("=" * 62)
    print("TESTE — robustete surse stiri (backoff 429 + keep-last-good)")
    print("=" * 62)
    test_backoff_escalation()
    test_fetch_skips_during_backoff()
    test_429_activates_backoff()
    test_nextweek_throttle()
    test_refresh_keeps_last_good()
    test_perception_keeps_last_good()
    print("=" * 62)
    print(f"REZULTAT: {_passed} OK, {_failed} esuate")
    print("=" * 62)
    sys.exit(1 if _failed else 0)


if __name__ == "__main__":
    main()
