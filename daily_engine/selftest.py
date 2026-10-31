"""Selftest Daily Engine — `python -m daily_engine.selftest` (offline, fara MT5).

1. strategie pe scenarii sintetice (long/short, SL, EOD, zile sarite, faze intermediare)
2. ECHIVALENTA cu backtestul de cercetare pe tot istoricul M5 (daca data/research_daily/ exista)
3. conversia ora server -> ora bursei, inclusiv saptamana cu decalaj DST SUA/RO
4. o zi completa prin motor cu MT5 simulat (trade inregistrat o singura data, notificari o data)
5. modulul nu contine niciun apel de plasare ordine
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from daily_engine import engine as E          # noqa: E402
from daily_engine.config import DEFAULTS, ENTRY_MODES, hm_to_min  # noqa: E402
from daily_engine.strategy import evaluate_day  # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  OK   {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name} {detail}")


def _ev(bars, mode="dir", or_minutes=10, rr=None, done=True, slip=0.0, comm=0.0, open_min=570):
    o, h, l, c = (np.array([b[i] for b in bars], float) for i in range(4))
    mins = open_min + 5 * np.arange(len(bars))
    return evaluate_day(o, h, l, c, np.zeros(len(bars)), mins, open_min=open_min, or_minutes=or_minutes,
                        mode=mode, rr=rr, slip=slip, comm=comm, day_complete=done)


def t_strategy():
    print("1. Strategie (scenarii sintetice)")
    # OR 10 min = 2 bare; urcare -> LONG; intrare la open-ul barei 3; ziua inchide mai sus
    up = [(100, 102, 99, 101), (101, 103, 100, 102.5)] + [(102.5, 104, 102, 103.5)] * 6
    r = _ev(up)
    check("dir long: EOD castigator", r["phase"] == "closed" and r["side"] == 1 and r["reason"] == "EOD" and r["R"] > 0, r)
    check("dir long: SL = minimul intervalului", r["sl"] == 99)
    dn = [(100, 101, 98, 99), (99, 99.5, 97, 97.5)] + [(97.5, 98, 96, 96.5)] * 6
    r = _ev(dn)
    check("dir short", r["side"] == -1 and r["sl"] == 101 and r["R"] > 0, r)
    sl = [(100, 102, 99, 101), (101, 103, 100, 102.5), (102.5, 102.6, 98, 98.5)] + [(98.5, 99, 98, 98.5)] * 5
    r = _ev(sl)
    check("dir: SL atins -> -1R", r["reason"] == "SL" and abs(r["R"] + 1) < 1e-9, r)
    doji = [(100, 102, 99, 101), (101, 103, 99, 100)] + [(100, 101, 99, 100)] * 6
    check("dir: doji -> sarit", _ev(doji)["phase"] == "skipped")
    # breakout: OR = 1 bara (5 min), ambele margini in aceeasi bara -> sarit
    both = [(100, 101, 99, 100), (100, 102, 98, 100)] + [(100, 100.5, 99.5, 100)] * 6
    check("brk: ambele margini aceeasi bara -> sarit", _ev(both, "brk", 5)["phase"] == "skipped")
    brk = [(100, 101, 99, 100), (100, 100.8, 99.5, 100.5), (100.5, 102, 100.4, 101.8)] + [(101.8, 103, 101.5, 102.8)] * 5
    r = _ev(brk, "brk", 5)
    check("brk long la marginea de sus", r["side"] == 1 and r["entry"] == 101 and r["R"] > 0, r)
    gap = [(100, 101, 99, 100), (101.5, 102, 101.2, 101.8)] + [(101.8, 102, 101.5, 101.9)] * 6
    check("brk: gap peste nivel -> umplere la open", _ev(gap, "brk", 5)["entry"] == 101.5)
    nob = [(100, 101, 99, 100)] + [(100, 100.5, 99.5, 100)] * 7
    check("brk: fara breakout, zi incheiata -> sarit", _ev(nob, "brk", 5)["phase"] == "skipped")
    check("brk: fara breakout, zi in curs -> astept", _ev(nob, "brk", 5, done=False)["phase"] == "waiting_entry")
    check("faza: interval in formare", _ev(up[:1])["phase"] == "forming_or")
    check("faza: astept bara de intrare", _ev(up[:2])["phase"] == "waiting_entry")
    r = _ev(up[:4], done=False)
    check("faza: pozitie deschisa (R deschis)", r["phase"] == "in_position" and "open_R" in r, r)
    check("TP 2R", _ev([(100, 101, 99, 100.8), (100.8, 101, 100, 100.9), (101, 106, 100.5, 105)] + [(105, 105, 104, 104.5)] * 5,
                       rr=2.0)["reason"] == "TP")
    check("risc < 2x cost -> sarit", _ev(up, comm=5.0)["phase"] == "skipped")
    late = evaluate_day([1], [2], [0], [1], [0], [600], open_min=570, or_minutes=5, mode="dir",
                        rr=None, slip=0, comm=0, day_complete=False)
    check("fara bara la deschidere -> sarit", late["phase"] == "skipped", late)


def t_equivalence():
    print("2. Echivalenta cu backtestul de cercetare (istoric M5)")
    sys.path.insert(0, os.path.join(ROOT, "scripts", "research_daily"))
    try:
        import orb_m5 as O
    except Exception as e:
        print(f"  SKIP (scripturile de cercetare indisponibile: {e})")
        return
    for m in DEFAULTS["markets"]:
        sym = m["symbol"]
        if not os.path.isfile(os.path.join(ROOT, f"data/research_daily/{sym}_M5_server.csv")):
            print(f"  SKIP {sym} (fara date M5 locale)")
            continue
        om, cm = hm_to_min(m["open"]), hm_to_min(m["last_bar"])
        d = O.load(sym, m["tz"], om, cm)
        mode = ENTRY_MODES[m["entry"]]
        O.SPEC[sym]["slip"], O.SPEC[sym]["comm"] = m["slip"], m["comm"]
        ref = O.run(d, sym, m["or_minutes"], mode, m["rr"])
        ref_map = dict(zip(ref.entry_t, ref.R))
        point = O.SPEC[sym]["point"]
        mine = {}
        for day, g in d.groupby("day", sort=True):
            st = evaluate_day(g.open, g.high, g.low, g.close, g.spread * point, g.mins, open_min=om,
                              or_minutes=m["or_minutes"], mode=mode, rr=m["rr"], slip=m["slip"],
                              comm=m["comm"], day_complete=True)
            if st["phase"] == "closed":
                mine[day] = st["R"]
        same_days = set(mine) == set(ref_map)
        diff = max((abs(mine[k] - ref_map[k]) for k in mine if k in ref_map), default=0.0)
        check(f"{sym}: aceleasi {len(ref_map)} zile tranzactionate", same_days,
              f"motor {len(mine)} vs backtest {len(ref_map)}")
        check(f"{sym}: R identic pe fiecare trade (dif max {diff:.2e})", diff < 1e-9)
        if mine:
            print(f"       {sym}: {len(mine)} trade-uri, medie {np.mean(list(mine.values())):+.4f}R")


def _fake_rates(day_ny: datetime, n_bars: int, offset_h: int, pattern):
    """Bare M5 in 'ora serverului' (epoch al orei serverului) incepand cu day_ny (aware NY)."""
    rows = []
    for i in range(n_bars):
        start_utc = day_ny + timedelta(minutes=5 * i)
        o, h, l, c = pattern(i)
        rows.append((int(start_utc.timestamp()) + offset_h * 3600, o, h, l, c, 100, 2, 0))
    return np.array(rows, dtype=[("time", "i8"), ("open", "f8"), ("high", "f8"), ("low", "f8"),
                                 ("close", "f8"), ("tick_volume", "i8"), ("spread", "i4"), ("real_volume", "i8")])


def t_time():
    print("3. Ora server -> ora bursei (DST)")
    m = next(x for x in DEFAULTS["markets"] if x["symbol"] == "US500")
    ny = ZoneInfo("America/New_York")
    # 10 martie 2026: SUA deja pe ora de vara, Romania inca nu -> Wall Street deschide la 15:30 RO
    open_ny = datetime(2026, 3, 10, 9, 30, tzinfo=ny)
    w_open, _ = E.window_times(m, open_ny.date())
    check("decalaj DST: deschidere 15:30 RO", w_open.astimezone(E.RO).strftime("%H:%M") == "15:30")
    w_open2, w_end2 = E.window_times(m, datetime(2026, 11, 3).date())
    check("normal: deschidere 16:30 RO, sfarsit 23:00 RO",
          (w_open2.astimezone(E.RO).strftime("%H:%M"), w_end2.astimezone(E.RO).strftime("%H:%M")) == ("16:30", "23:00"))
    g = next(x for x in DEFAULTS["markets"] if x["symbol"] == "GBPUSD")
    gw = E.window_times(g, datetime(2026, 11, 3).date())
    check("GBPUSD: 10:00–16:30 RO", tuple(x.astimezone(E.RO).strftime("%H:%M") for x in gw) == ("10:00", "16:30"))
    rates = _fake_rates(open_ny - timedelta(minutes=30), 20, 7, lambda i: (1, 2, 0, 1))
    now = (open_ny + timedelta(minutes=42)).astimezone(timezone.utc)
    b = E.bars_today(rates, 7 * 3600, m, now)
    check("bars_today: incepe exact la 09:30 NY, doar bare inchise",
          len(b) == 8 and int(b.mins.iloc[0]) == 570 and int(b.mins.iloc[-1]) == 605, (len(b), list(b.mins)))


class _FakeMt5:
    TIMEFRAME_M5 = 5

    def __init__(self, rates, offset_h):
        self.rates, self.offset_h, self.now = rates, offset_h, None

    def initialize(self): return True
    def shutdown(self): pass
    def last_error(self): return (0, "ok")
    def account_info(self): return SimpleNamespace(login=1, server="Fake", trade_mode=0, equity=206.0, currency="USD")
    def symbol_select(self, s, f): return True
    def symbol_info(self, s): return SimpleNamespace(point=0.01, volume_min=0.1, volume_step=0.1, volume_max=100.0,
                                                     trade_tick_size=0.01, trade_tick_value=0.01)
    def symbol_info_tick(self, s): return SimpleNamespace(time=int(self.now.timestamp()) + self.offset_h * 3600)
    def copy_rates_from_pos(self, s, tf, a, n): return self.rates


def t_engine():
    print("4. O zi prin motor (MT5 simulat)")
    tmp = tempfile.mkdtemp()
    for name in ("STATUS_FILE", "STATE_FILE", "TRADES_FILE"):
        setattr(E, name, os.path.join(tmp, os.path.basename(getattr(E, name))))
    sent = []
    E._notify = lambda cfg, text: sent.append(text)
    cfg = {"mode": "shadow", "poll_seconds": 15, "notify_telegram": True,
           "markets": [m for m in DEFAULTS["markets"] if m["symbol"] == "US500"]}
    E.load_config = lambda: cfg
    ny = ZoneInfo("America/New_York")
    open_ny = datetime(2026, 11, 3, 9, 30, tzinfo=ny)
    # urcare constanta: interval 30 min urca -> LONG, ziua inchide sus -> R > 0
    rates = _fake_rates(open_ny, 78, 7, lambda i: (6000 + i, 6001.5 + i, 5999.5 + i, 6001 + i))
    fake = _FakeMt5(rates, 7)
    eng = E.DailyEngine(mt5_module=fake)
    eng.connect()
    phases = []
    for minutes in (10, 40, 200, 385, 395):
        fake.now = (open_ny + timedelta(minutes=minutes)).astimezone(timezone.utc)
        st = eng.iteration(fake.now)
        phases.append(st["markets"][0]["phase"])
    check("faze: interval -> pozitie -> inchis",
          phases == ["forming_or", "in_position", "in_position", "in_position", "closed"], phases)
    trades = E.load_trades()
    check("un singur trade inregistrat", len(trades) == 1 and trades[0]["side"] == "LONG" and trades[0]["R"] > 0, trades)
    tr0 = trades[0] if trades else {}
    # 1% din $206 = $2.06 la SL 6.51 puncte ($1/punct/lot) -> 0.316 -> floor la pas 0.1 = 0.3 loturi
    check("dimensionare comuna pe trade-ul virtual (0.3 loturi, risc $1.95)",
          tr0.get("lots") == 0.3 and abs(tr0.get("risk_money", 0) - 1.953) < 1e-3
          and abs(tr0.get("pnl_money_est", 0) - tr0["R"] * tr0["risk_money"]) < 1e-3, tr0)
    eng.iteration(fake.now)
    check("re-iteratie: fara dublura", len(E.load_trades()) == 1)
    check("notificari: intrare + inchidere, o singura data", len(sent) == 2, len(sent))
    eng2 = E.DailyEngine(mt5_module=fake)          # restart: starea zilei se reconstruieste
    eng2.connect()
    eng2.iteration(fake.now)
    check("restart: fara dublura / fara notificari noi", len(E.load_trades()) == 1 and len(sent) == 2)
    sc = eng2.iteration(fake.now)["scorecard"]
    check("scorecard", sc["trades"] == 1 and sc["wins"] == 1 and sc["by_symbol"]["US500"]["trades"] == 1, sc)


def t_no_orders():
    print("5. Zero ordine reale")
    d = os.path.dirname(os.path.abspath(__file__))
    bad = []
    for fn in os.listdir(d):
        if fn.endswith(".py") and fn != "selftest.py":
            src = open(os.path.join(d, fn), encoding="utf-8").read()
            if "order_send" in src or "order_check" in src:
                bad.append(fn)
    check("niciun apel order_send/order_check in daily_engine/", not bad, bad)


if __name__ == "__main__":
    t_strategy()
    t_equivalence()
    t_time()
    t_engine()
    t_no_orders()
    print(f"\n{PASS} OK, {FAIL} FAIL")
    sys.exit(1 if FAIL else 0)
