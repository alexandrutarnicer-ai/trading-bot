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

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

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
    TRADE_ACTION_DEAL, TRADE_ACTION_PENDING, TRADE_ACTION_REMOVE = 1, 5, 8
    ORDER_TYPE_BUY, ORDER_TYPE_SELL, ORDER_TYPE_BUY_STOP, ORDER_TYPE_SELL_STOP = 0, 1, 4, 5
    ORDER_TIME_GTC, TRADE_RETCODE_DONE, TRADE_RETCODE_PLACED, POSITION_TYPE_BUY = 0, 10009, 10008, 0
    trade_mode = 0          # 0 = DEMO, 2 = REAL

    def __init__(self, rates, offset_h):
        self.rates, self.offset_h, self.now = rates, offset_h, None
        self.sent, self.positions, self.orders, self._tk = [], [], [], 100

    def positions_get(self, symbol=None): return [p for p in self.positions if symbol in (None, p.symbol)]
    def orders_get(self, symbol=None): return [o for o in self.orders if symbol in (None, o.symbol)]

    def order_send(self, req):
        self.sent.append(dict(req))
        self._tk += 1
        if req["action"] == self.TRADE_ACTION_DEAL and "position" in req:
            self.positions = [p for p in self.positions if p.ticket != req["position"]]
        elif req["action"] == self.TRADE_ACTION_DEAL:
            self.positions.append(SimpleNamespace(ticket=self._tk, symbol=req["symbol"], magic=req["magic"],
                                                  comment=req["comment"], volume=req["volume"],
                                                  type=0 if req["type"] == self.ORDER_TYPE_BUY else 1))
        elif req["action"] == self.TRADE_ACTION_PENDING:
            self.orders.append(SimpleNamespace(ticket=self._tk, symbol=req["symbol"], magic=req["magic"],
                                               comment=req["comment"], type=req["type"], price_open=req["price"]))
        elif req["action"] == self.TRADE_ACTION_REMOVE:
            self.orders = [o for o in self.orders if o.ticket != req["order"]]
        return SimpleNamespace(retcode=10009, order=self._tk)

    def initialize(self): return True
    def shutdown(self): pass
    def last_error(self): return (0, "ok")
    def account_info(self): return SimpleNamespace(login=1, server="Fake", trade_mode=self.trade_mode, equity=206.0, currency="USD")
    def symbol_select(self, s, f): return True
    def symbol_info(self, s): return SimpleNamespace(point=0.01, volume_min=0.1, volume_step=0.1, volume_max=100.0,
                                                     trade_tick_size=0.01, trade_tick_value=0.01, digits=2, filling_mode=2)
    def symbol_info_tick(self, s):
        px = getattr(self, "px", 6031.0)
        return SimpleNamespace(time=int(self.now.timestamp()) + self.offset_h * 3600, ask=px + 0.25, bid=px - 0.25)
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
    print("5. Ordinele reale sunt izolate")
    d = os.path.dirname(os.path.abspath(__file__))
    bad = []
    for fn in os.listdir(d):
        if fn.endswith(".py") and fn not in ("selftest.py", "executor.py"):
            src = open(os.path.join(d, fn), encoding="utf-8").read()
            if "order_send" in src or "order_check" in src:
                bad.append(fn)
    check("order_send DOAR in daily_engine/executor.py", not bad, bad)


def _exec_day(mode, trade_mode=0, live=False, arm_late=False, market="US500", extra=None):
    """O zi prin motor cu MT5 simulat; intoarce (fake, status final)."""
    tmp = tempfile.mkdtemp()
    for name in ("STATUS_FILE", "STATE_FILE", "TRADES_FILE"):
        setattr(E, name, os.path.join(tmp, os.path.basename(getattr(E, name))))
    E._notify = lambda cfg, text: None
    import live_guard
    live_guard.live_allowed = lambda comp: live
    m = {**next(x for x in DEFAULTS["markets"] if x["symbol"] == market), **(extra or {})}
    cfg = {"mode": mode, "poll_seconds": 15, "notify_telegram": True, "markets": [m],
           "sizing": {"capital_sync_mt5": True, "capital_usd": None, "fraction": 1.0, "risk_pct": 0.01}}
    E.load_config = lambda: cfg
    tz = ZoneInfo(m["tz"])
    open_loc = datetime(2026, 11, 3, *map(int, m["open"].split(":")), tzinfo=tz)
    n = (hm_to_min(m["last_bar"]) - hm_to_min(m["open"])) // 5 + 1
    rates = _fake_rates(open_loc, n, 7 if market == "US500" else 7, lambda i: (6000 + i, 6001.5 + i, 5999.5 + i, 6001 + i))
    fake = _FakeMt5(rates, 7)
    fake.trade_mode = trade_mode
    eng = E.DailyEngine(mt5_module=fake)
    eng.connect()
    or_m = m["or_minutes"]
    steps = (-10, or_m - 4, or_m + 1, 120, 300, hm_to_min(m["last_bar"]) - hm_to_min(m["open"]) + 6)
    st = None
    for i, mins in enumerate(steps):
        if arm_late and i < 2:
            continue                         # modul pornit DUPA formarea intervalului
        fake.now = (open_loc + timedelta(minutes=mins)).astimezone(timezone.utc)
        # in interval / imediat dupa: pretul sta intre margini (ordinele stop au sens)
        fake.px = 6000.5 if mins <= or_m + 1 and m["entry"] == "breakout" else 6000 + max(0, mins) / 5 + 1
        st = eng.iteration(fake.now)
    return fake, st


def t_execution():
    print("6. Executie reala (MT5 simulat)")
    chk = lambda cond, name, d="": check(name, cond, d)   # ordinea (conditie, nume) din aceasta sectiune
    fake, st = _exec_day("shadow")
    chk(not fake.sent, "SHADOW: zero ordine trimise", fake.sent)
    fake, st = _exec_day("execute", trade_mode=2, live=False)
    chk(not fake.sent and "nedeblocat" in st["execution"]["reason"],
          "cont REAL nedeblocat: zero ordine + motiv vizibil", (fake.sent, st.get("execution")))
    fake, st = _exec_day("execute", trade_mode=0)
    deals = [r for r in fake.sent if r["action"] == fake.TRADE_ACTION_DEAL]
    entry = deals[0] if deals else {}
    chk(len(deals) == 2 and "position" not in entry and "position" in deals[1],
          "DEMO, US500: o intrare la piață + închiderea la finalul ferestrei", fake.sent)
    chk(entry.get("magic") == 880001 and entry.get("comment") == "D-US500-1103" and entry.get("sl") == 5999.5
          and entry.get("type") == fake.ORDER_TYPE_BUY, "magic 880001, comment D-, SL = marginea opusă, LONG", entry)
    # 1% din $206 = $2,06 / (6007,65 − 5999,5 = 8,15 pct × $1/pct/lot) = 0,25 → pas 0,1 → 0,2 loturi
    chk(entry.get("volume") == 0.2 and not fake.positions, "lot din dimensionarea comună (0,2); nicio poziție peste noapte",
          (entry.get("volume"), fake.positions))
    fake, st = _exec_day("execute", trade_mode=2, live=True)
    chk(any(r["action"] == fake.TRADE_ACTION_DEAL for r in fake.sent), "cont REAL deblocat: execută")
    fake, st = _exec_day("execute", trade_mode=0, arm_late=True)
    chk(not fake.sent, "modul pornit DUPĂ formarea intervalului: ziua rămâne shadow (zero ordine)", fake.sent)
    fake, st = _exec_day("execute", trade_mode=0, market="GBPUSD")
    pend = [r for r in fake.sent if r["action"] == fake.TRADE_ACTION_PENDING]
    chk(len(pend) == 2 and {r["type"] for r in pend} == {fake.ORDER_TYPE_BUY_STOP, fake.ORDER_TYPE_SELL_STOP},
          "GBPUSD: BUY_STOP + SELL_STOP pe marginile intervalului", pend)
    chk(not fake.orders and not fake.positions, "final de fereastră: ordinele rămase anulate", (fake.orders, fake.positions))
    # OCO: o margine umpluta -> cealalta anulata
    eng = E.DailyEngine(mt5_module=fake)
    fake.orders = [SimpleNamespace(ticket=1, symbol="GBPUSD", magic=880001, comment="D-GBPUSD-1104", type=5)]
    fake.positions = [SimpleNamespace(ticket=2, symbol="GBPUSD", magic=880001, comment="D-GBPUSD-1104", volume=0.01, type=0)]
    fake.sent = []
    m = next(x for x in DEFAULTS["markets"] if x["symbol"] == "GBPUSD")
    from datetime import date as _d
    eng._execute(m, _d(2026, 11, 4), {"phase": "in_position"}, None,
                 datetime(2026, 11, 4, 9, 0, tzinfo=ZoneInfo("Europe/London")),
                 datetime(2026, 11, 4, 14, 30, tzinfo=ZoneInfo("Europe/London")))
    chk([r["action"] for r in fake.sent] == [fake.TRADE_ACTION_REMOVE], "OCO: poziție deschisă → cealaltă margine anulată", fake.sent)
    # plasa de siguranta: pozitie Daily din alta zi -> inchisa
    fake.positions = [SimpleNamespace(ticket=3, symbol="US500", magic=880001, comment="D-US500-1101", volume=0.1, type=0)]
    fake.orders, fake.sent = [], []
    eng.cfg = E.load_config()
    eng.sweep_stale(datetime(2026, 11, 3, 15, 0, tzinfo=timezone.utc))
    chk(fake.sent and "position" in fake.sent[0] and not fake.positions, "poziție Daily din altă zi → închisă (niciodată overnight)", fake.sent)


def t_reentry():
    print("7. Re-intrari in prima ora + R:R (optionale)")
    from daily_engine.strategy import evaluate_day_multi
    from daily_engine.config import sanitize_reentry, sanitize_rr, _sanitize
    # GBPUSD-like, OR 5 min la 08:00: interval 0.9990–1.0010
    bars = [(1.0000, 1.0010, 0.9990, 1.0000),      # 08:00 OR
            (1.0005, 1.0015, 1.0001, 1.0012),      # 08:05 rupere sus -> LONG 1.0010
            (1.0012, 1.0013, 0.9985, 0.9987),      # 08:10 SL long (pierdere 1)
            (0.9986, 0.9988, 0.9980, 0.9982),      # 08:15 pret sub margine -> SHORT la open 0.9986
            (0.9983, 1.0012, 0.9982, 1.0011),      # 08:20 SL short (pierdere 2)
            (1.0011, 1.0020, 1.0008, 1.0018)] + [(1.0018, 1.0019, 1.0017, 1.0018)] * 10   # 08:25 rupere sus din nou
    o, h, l, c = (np.array([b[i] for b in bars], float) for i in range(4))
    mins = 480 + 5 * np.arange(len(bars))
    kw = dict(open_min=480, or_minutes=5, mode="brk", rr=None, slip=0.0, comm=0.0, day_complete=True)
    z = np.zeros(len(bars))
    base = evaluate_day(o, h, l, c, z, mins, **kw)
    off = evaluate_day_multi(o, h, l, c, z, mins, **kw)
    check("oprit (implicit) -> identic cu evaluate_day, un singur trade",
          {k: v for k, v in off.items() if k not in ("trades", "k")} == base and len(off["trades"]) == 1)
    on = evaluate_day_multi(o, h, l, c, z, mins, **kw, reentry={"enabled": True, "window_min": 60, "max_trades": 3,
                                                               "max_consec_losses": 2, "cooldown_bars": 1})
    tr = on["trades"]
    check("re-intrare dupa SL: al doilea trade SHORT la open-ul barei urmatoare (pret deja sub margine)",
          len(tr) >= 2 and tr[1]["side"] == -1 and abs(tr[1]["entry"] - 0.9986) < 1e-9 and tr[1]["k"] == 1, tr[:2])
    check("2 pierderi la rand -> STOP (a treia rupere de la 08:25 nu se mai ia)",
          len(tr) == 2 and "2 pierderi" in on.get("reentry_stop", ""), (len(tr), on.get("reentry_stop")))
    no_stop = evaluate_day_multi(o, h, l, c, z, mins, **kw, reentry={"enabled": True, "max_consec_losses": 0, "max_trades": 3})
    check("fara stop pe pierderi -> al treilea trade (max 3 / zi)", len(no_stop["trades"]) == 3, len(no_stop["trades"]))
    short_win = evaluate_day_multi(o, h, l, c, z, mins, **kw, reentry={"enabled": True, "window_min": 15})
    check("fereastra de re-intrare 15 min: rupere la 08:15 -> nu se mai ia", len(short_win["trades"]) == 1
          and "fereastra" in short_win.get("reentry_stop", ""), short_win.get("reentry_stop"))
    cool = evaluate_day_multi(o, h, l, c, z, mins, **kw, reentry={"enabled": True, "cooldown_bars": 2, "max_consec_losses": 0})
    check("pauza de 2 lumanari: bara imediat urmatoare iesirii (08:15) e sarita; la 08:20 ambele margini -> stop",
          len(cool["trades"]) == 1 and "ambele margini" in cool.get("reentry_stop", ""), cool.get("reentry_stop"))
    live = evaluate_day_multi(o[:4], h[:4], l[:4], c[:4], z[:4], mins[:4], **{**kw, "day_complete": False},
                              reentry={"enabled": True})
    check("in timpul zilei: re-intrarea deschisa = in_position, k = 1", live["phase"] == "in_position" and live["k"] == 1, live)
    # R:R: TP 1R pe primul trade, apoi re-intrare (continuare) pe aceeasi directie
    bars_tp = [(1.0000, 1.0010, 0.9990, 1.0000), (1.0005, 1.0015, 1.0001, 1.0012),
               (1.0012, 1.0031, 1.0011, 1.0029), (1.0029, 1.0030, 1.0025, 1.0027)] + [(1.0027, 1.0028, 1.0026, 1.0027)] * 8
    o2, h2, l2, c2 = (np.array([b[i] for b in bars_tp], float) for i in range(4))
    m2 = 480 + 5 * np.arange(len(bars_tp))
    z2 = np.zeros(len(bars_tp))
    rr1 = evaluate_day_multi(o2, h2, l2, c2, z2, m2, **{**kw, "rr": 1.0}, reentry={"enabled": True})
    check("R:R 1R -> primul trade iese pe TP (+1R), apoi re-intrare in aceeasi directie",
          rr1["trades"][0]["reason"] == "TP" and abs(rr1["trades"][0]["R"] - 1.0) < 1e-9 and len(rr1["trades"]) >= 2
          and rr1["trades"][1]["side"] == 1, [(t["reason"], round(t["R"], 3)) for t in rr1["trades"]])
    check("config: re-intrari limitate (fereastra 15-240, max 2-10, pierderi 0-10, pauza 1-12)",
          sanitize_reentry({"enabled": 1, "window_min": 5, "max_trades": 50, "max_consec_losses": -1, "cooldown_bars": 0})
          == {"enabled": True, "window_min": 15, "max_trades": 10, "max_consec_losses": 0, "cooldown_bars": 1})
    check("config: R:R None / 0 = fara TP; 3 acceptat; limitat 0,5-10",
          sanitize_rr(None) is None and sanitize_rr(0) is None and sanitize_rr("3") == 3.0 and sanitize_rr(99) == 10.0)
    check("config implicit: re-intrari OPRITE, fara TP pe ambele piete",
          all(not m["reentry"]["enabled"] and m["rr"] is None for m in _sanitize({"markets": DEFAULTS["markets"]})["markets"]))

    # motorul in SHADOW: doua trade-uri in jurnal, notificari o data, restart fara dubluri
    tmp = tempfile.mkdtemp()
    for name in ("STATUS_FILE", "STATE_FILE", "TRADES_FILE"):
        setattr(E, name, os.path.join(tmp, os.path.basename(getattr(E, name))))
    sent = []
    E._notify = lambda cfg, text: sent.append(text)
    g = {**next(x for x in DEFAULTS["markets"] if x["symbol"] == "GBPUSD"),
         "reentry": {"enabled": True, "window_min": 60, "max_trades": 3, "max_consec_losses": 2, "cooldown_bars": 1}}
    cfg = {"mode": "shadow", "poll_seconds": 15, "notify_telegram": True, "markets": [g]}
    E.load_config = lambda: cfg
    lon = ZoneInfo("Europe/London")
    open_l = datetime(2026, 11, 3, 8, 0, tzinfo=lon)
    n = (hm_to_min(g["last_bar"]) - hm_to_min(g["open"])) // 5 + 1
    rates = _fake_rates(open_l, n, 7, lambda i: bars[i] if i < len(bars) else bars[-1])
    fx_info = lambda sym: SimpleNamespace(point=0.00001, volume_min=0.01, volume_step=0.01, volume_max=100.0,
                                          trade_tick_size=0.00001, trade_tick_value=1.0, digits=5, filling_mode=2)
    fake = _FakeMt5(rates, 7)
    fake.symbol_info = fx_info
    eng = E.DailyEngine(mt5_module=fake)
    eng.connect()
    st = None
    for mn in (6, 16, 31, n * 5 + 6):
        fake.now = (open_l + timedelta(minutes=mn)).astimezone(timezone.utc)
        st = eng.iteration(fake.now)
    tj = E.load_trades()
    check("SHADOW: doua trade-uri in jurnal (k 0 si 1), al doilea SHORT",
          [t.get("k") for t in tj] == [0, 1] and tj[1]["side"] == "SHORT", tj)
    check("notificari: intrare + inchidere pentru fiecare trade, cu #1 / #2", len(sent) == 4 and "#2" in sent[2], len(sent))
    eng2 = E.DailyEngine(mt5_module=fake)
    eng2.connect()
    eng2.iteration(fake.now)
    check("restart: fara dubluri in jurnal / notificari", len(E.load_trades()) == 2 and len(sent) == 4)
    mk = st["markets"][0]
    check("status: trade-uri azi = 2 + configurarea pietei", mk.get("trades_today") == 2 and mk["reentry"]["enabled"], mk.get("trades_today"))

    # EXECUTIE: TP real cand R:R e setat; re-intrare reala doar cu semnal proaspat si fara pozitie
    fake_x, _ = _exec_day("execute", trade_mode=0, extra={"rr": 2.0})
    entry = next((r for r in fake_x.sent if r["action"] == fake_x.TRADE_ACTION_DEAL and "position" not in r), {})
    check("EXECUTIE cu R:R 2: ordinul real are TP = intrare + 2 x risc",
          entry.get("tp") and abs((entry["tp"] - entry["price"]) / (entry["price"] - entry["sl"]) - 2.0) < 0.01, entry)
    fake_n, _ = _exec_day("execute", trade_mode=0)
    entry_n = next((r for r in fake_n.sent if r["action"] == fake_n.TRADE_ACTION_DEAL and "position" not in r), {})
    check("EXECUTIE fara R:R: fara TP (ca pana acum)", "tp" not in entry_n, entry_n)
    import pandas as _pd
    import live_guard
    live_guard.live_allowed = lambda comp: True
    cfg["mode"] = "execute"
    from datetime import date as _d
    d0 = _d(2026, 11, 3)
    w_end = datetime(2026, 11, 3, 14, 30, tzinfo=lon)
    st_k = {"phase": "in_position", "k": 1, "side": -1, "sl": 1.0010, "entry": 0.9986, "entry_min": 495,
            "or_hi": 1.0010, "or_lo": 0.9990}

    def fresh_engine():
        fx = _FakeMt5(rates, 7)
        fx.symbol_info = fx_info
        fx.symbol_info_tick = lambda sym: SimpleNamespace(time=int(fx.now.timestamp()) + 7 * 3600, ask=0.99856, bid=0.99850)
        fx.now, fx.px = datetime(2026, 11, 3, 8, 21, tzinfo=lon).astimezone(timezone.utc), 0.9985
        ex = E.DailyEngine(mt5_module=fx)
        ex.cfg = cfg
        ex.state.setdefault("events", {})[f"{d0}|GBPUSD|armed"] = True
        return fx, ex

    fx, ex = fresh_engine()
    b = _pd.DataFrame({"mins": [480, 485, 490, 495]})
    ex._execute(g, d0, st_k, b, datetime(2026, 11, 3, 8, 21, tzinfo=lon), w_end)
    re_ord = [r for r in fx.sent if r["action"] == fx.TRADE_ACTION_DEAL]
    check("EXECUTIE re-intrare: ordin la piata SHORT, comment D-GBPUSD-11031, SL = marginea opusa",
          len(re_ord) == 1 and re_ord[0]["comment"] == "D-GBPUSD-11031" and re_ord[0]["type"] == fx.ORDER_TYPE_SELL
          and abs(re_ord[0]["sl"] - 1.001) < 1e-9, re_ord)
    ex._execute(g, d0, st_k, b, datetime(2026, 11, 3, 8, 22, tzinfo=lon), w_end)
    check("... o singura data (re-iteratia nu dubleaza; pozitia deschisa blocheaza alta intrare)",
          len([r for r in fx.sent if r["action"] == fx.TRADE_ACTION_DEAL]) == 1)
    fx2, ex2 = fresh_engine()
    b_late = _pd.DataFrame({"mins": [480, 485, 490, 495, 500, 505, 510]})
    ex2._execute(g, d0, st_k, b_late, datetime(2026, 11, 3, 8, 36, tzinfo=lon), w_end)
    check("semnal de re-intrare VECHI (restart tarziu) -> niciun ordin", not fx2.sent, fx2.sent)
    cfg["mode"] = "shadow"


def t_pause():
    print("8. Pauză per piață (fără intrări noi; pozițiile deschise rămân gestionate)")
    from daily_engine.pause import apply_pause, pause_cut_min
    from daily_engine.config import _sanitize
    from datetime import date as _d
    ber = {"tz": "Europe/Berlin"}
    check("activă → fără tăietură", pause_cut_min({**ber, "paused": False}, _d(2026, 11, 3)) is None)
    check("pauză azi 10:07 Berlin → minutul 607",
          pause_cut_min({**ber, "paused": True, "paused_at": "2026-11-03T09:07:00+00:00"}, _d(2026, 11, 3)) == 607)
    check("pauză de ieri → toată ziua (0)",
          pause_cut_min({**ber, "paused": True, "paused_at": "2026-11-02T15:00:00+00:00"}, _d(2026, 11, 3)) == 0)
    check("pauză fără moment valid → toată ziua", pause_cut_min({**ber, "paused": True, "paused_at": "x"}, _d(2026, 11, 3)) == 0)
    pos = {"phase": "in_position", "entry_min": 600, "side": 1, "entry": 1.0, "sl": 0.9, "trades": []}
    check("poziție intrată ÎNAINTE de pauză → rămâne (gestionată)", apply_pause(pos, 607)["phase"] == "in_position")
    check("poziție intrată DUPĂ pauză → dispare", apply_pause({**pos, "entry_min": 610}, 607)["phase"] == "paused")
    check("așteaptă intrarea → pauză", apply_pause({"phase": "waiting_entry", "trades": []}, 0)["phase"] == "paused")
    st = {"phase": "closed", "entry_min": 640, "trades": [{"entry_min": 600, "R": 1}, {"entry_min": 640, "R": -1}]}
    out = apply_pause(st, 620)
    check("re-intrări: doar trade-urile dinaintea pauzei rămân", [t["R"] for t in out["trades"]] == [1] and out["phase"] == "paused")
    check("neatins când nu e pauză", apply_pause(pos, None) is pos)
    m0 = DEFAULTS["markets"][0]
    cl = _sanitize({"markets": [{**m0, "paused": True, "paused_at": "2026-11-03T09:07:00+00:00"}]})["markets"][0]
    check("config: pauza persistă (sanitize)", cl["paused"] is True and cl["paused_at"].startswith("2026-11-03"))
    cl2 = _sanitize({"markets": [{**m0, "paused": False, "paused_at": "2026-11-03T09:07:00+00:00"}]})["markets"][0]
    check("config: reluată → fără moment de pauză", cl2["paused"] is False and cl2["paused_at"] is None)
    check("config veche (fără câmp) → activă", _sanitize({"markets": [m0]})["markets"][0]["paused"] is False)

    old = "2026-11-02T00:00:00+00:00"
    fake, st = _exec_day("shadow", extra={"paused": True, "paused_at": old})
    mk = (st.get("markets") or [{}])[0]
    with open(E.TRADES_FILE, "a+", encoding="utf-8") as f:
        f.seek(0)
        n_tr = len([x for x in f.read().splitlines() if x.strip()])
    check("SHADOW pe pauză: nicio intrare virtuală, faza „paused”", n_tr == 0 and mk.get("phase") == "paused"
          and mk.get("paused") is True, (n_tr, mk.get("phase")))
    fake, st = _exec_day("execute", trade_mode=0, extra={"paused": True, "paused_at": old})
    check("EXECUȚIE (DEMO) pe pauză: zero ordine", not fake.sent, fake.sent)
    fake, st = _exec_day("execute", trade_mode=0)
    check("... aceeași zi fără pauză: execută (control)", any(r["action"] == fake.TRADE_ACTION_DEAL for r in fake.sent))
    # pauza pusa cu ordinele stop GBPUSD deja plasate → anulate; pozitia deschisa ramane pana la final de fereastra
    eng = E.DailyEngine(mt5_module=fake)
    lon = ZoneInfo("Europe/London")
    g = {**next(x for x in DEFAULTS["markets"] if x["symbol"] == "GBPUSD"), "paused": True, "paused_at": old}
    fake.orders = [SimpleNamespace(ticket=11, symbol="GBPUSD", magic=880001, comment="D-GBPUSD-1104", type=4),
                   SimpleNamespace(ticket=12, symbol="GBPUSD", magic=880001, comment="D-GBPUSD-1104", type=5)]
    fake.positions, fake.sent = [], []
    w_end = datetime(2026, 11, 4, 14, 30, tzinfo=lon)
    eng._execute(g, _d(2026, 11, 4), {"phase": "paused"}, None, datetime(2026, 11, 4, 8, 20, tzinfo=lon), w_end)
    check("pauză cu ordinele stop plasate → ambele anulate, niciun ordin nou",
          [r["action"] for r in fake.sent] == [fake.TRADE_ACTION_REMOVE] * 2, fake.sent)
    fake.orders, fake.sent = [], []
    fake.positions = [SimpleNamespace(ticket=13, symbol="GBPUSD", magic=880001, comment="D-GBPUSD-1104", volume=0.01, type=0)]
    eng._execute(g, _d(2026, 11, 4), {"phase": "in_position"}, None, datetime(2026, 11, 4, 9, 0, tzinfo=lon), w_end)
    check("poziție deschisă + pauză → NU e închisă în fereastră", not fake.sent and fake.positions, fake.sent)
    eng._execute(g, _d(2026, 11, 4), {"phase": "in_position"}, None, datetime(2026, 11, 4, 14, 31, tzinfo=lon), w_end)
    check("... dar se închide la finalul ferestrei (regula existentă)", fake.sent and "position" in fake.sent[0], fake.sent)


def t_modes_plock():
    print("9. Moduri per piață (Live / Shadow / Pauză), Profit Lock, limita de marjă")
    from datetime import date as _d
    from daily_engine.config import _sanitize, sanitize_plock
    # --- configurare: migrare + independenta + Profit Lock oprit implicit
    old = _sanitize({"mode": "execute", "markets": [dict(x) for x in DEFAULTS["markets"]]})
    check("migrare: modul global vechi „execute” → fiecare piață Live (fără efect asupra comportamentului)",
          [x["exec_mode"] for x in old["markets"]] == ["live", "live"] and old["mode"] == "execute", old["markets"])
    mk = [dict(x) for x in DEFAULTS["markets"]]
    mk[0].update(exec_mode="live")
    mk[1].update(exec_mode="shadow", paused=True)
    c = _sanitize({"mode": "shadow", "markets": mk})
    check("moduri INDEPENDENTE: piața 1 Live, piața 2 Pauză; global = rezumat",
          [x["mode"] for x in c["markets"]] == ["live", "pause"] and c["mode"] == "execute", [x["mode"] for x in c["markets"]])
    check("Profit Lock OPRIT implicit pe toate piețele", all(not x["profit_lock"]["enabled"] for x in c["markets"]))
    check("Profit Lock: trigger sub 3R → 3R; lock >= trigger → trigger − 0,1",
          sanitize_plock({"enabled": True, "trigger_R": 2, "lock_R": 5}) == {"enabled": True, "trigger_R": 3.0, "lock_R": 2.9})
    # --- strategie: urcare la ~5R apoi intoarcere la SL
    bars = [(100, 101, 99, 100.5), (100.5, 101, 99.5, 100.8),       # OR 10 min: 99..101 → LONG
            (100.8, 103, 100.7, 102.9), (102.9, 106, 102.8, 105.8),   # varf 106 = (106-100.8)/1.8 = 2,9R
            (105.8, 110.5, 105.5, 110), (110, 110.2, 98, 98.5)] + [(98.5, 99, 98, 98.5)] * 4
    base = _ev(bars)
    pl = {"enabled": True, "trigger_R": 4.5, "lock_R": 4.0}
    o, h, l, cc = (np.array([b[i] for b in bars], float) for i in range(4))
    mins = 570 + 5 * np.arange(len(bars))
    lk = evaluate_day(o, h, l, cc, np.zeros(len(bars)), mins, open_min=570, or_minutes=10, mode="dir", rr=None,
                      slip=0.0, comm=0.0, day_complete=True, plock=pl)
    check("fără Profit Lock: întoarcerea închide pe SL (−1R)", base["reason"] == "SL" and abs(base["R"] + 1) < 1e-9, base)
    check("cu Profit Lock 4,5R → 4R: ieșire LOCK la +4R", lk["reason"] == "LOCK" and abs(lk["R"] - 4.0) < 1e-9, lk)
    lk_off = evaluate_day(o, h, l, cc, np.zeros(len(bars)), mins, open_min=570, or_minutes=10, mode="dir", rr=None,
                          slip=0.0, comm=0.0, day_complete=True, plock={**pl, "enabled": False})
    check("Profit Lock oprit = rezultat IDENTIC cu strategia actuală", lk_off == base)
    part = evaluate_day(o[:5], h[:5], l[:5], cc[:5], np.zeros(5), mins[:5], open_min=570, or_minutes=10, mode="dir",
                        rr=None, slip=0.0, comm=0.0, day_complete=False, plock=pl)
    check("în poziție după prag: locked + sl_now = intrare + 4R (pentru SL-ul real)",
          part["phase"] == "in_position" and part["locked"] and abs(part["sl_now"] - (100.8 + 4 * 1.8)) < 1e-9, part)
    # --- executie: modul pietei castiga (Shadow pe piata = zero ordine chiar daca global era „execute”)
    fake, st = _exec_day("execute", trade_mode=0, extra={"exec_mode": "shadow"})
    check("piața pe SHADOW: zero ordine reale (DEMO, modul global ignorat)", not fake.sent
          and "SHADOW" in st["markets"][0]["execution"]["reason"], (fake.sent, st["markets"][0].get("execution")))
    fake, st = _exec_day("shadow", trade_mode=0, extra={"exec_mode": "live"})
    check("piața pe LIVE (DEMO): ordin real + închidere la final", sum(r["action"] == fake.TRADE_ACTION_DEAL
                                                                     for r in fake.sent) == 2, fake.sent)
    fake, st = _exec_day("shadow", trade_mode=2, live=False, extra={"exec_mode": "live"})
    check("piața pe LIVE + cont REAL nedeblocat: zero ordine", not fake.sent, fake.sent)
    # --- Profit Lock pe pozitia REALA
    fake.TRADE_ACTION_SLTP = 6
    _send0 = fake.order_send

    def _send_sltp(req):                     # brokerul simulat aplica SL-ul nou (ca MT5 real)
        r = _send0(req)
        if req["action"] == 6:
            for p_ in fake.positions:
                if p_.ticket == req["position"]:
                    p_.sl = req["sl"]
        return r
    fake.order_send = _send_sltp
    eng = E.DailyEngine(mt5_module=fake)
    us = {**next(x for x in DEFAULTS["markets"] if x["symbol"] == "US500"), "exec_mode": "live",
          "profit_lock": pl}
    ny = ZoneInfo("America/New_York")
    fake.orders, fake.sent = [], []
    fake.positions = [SimpleNamespace(ticket=21, symbol="US500", magic=880001, comment="D-US500-1104", volume=0.1,
                                      type=0, sl=6000.0, tp=0.0)]
    stp = {"phase": "in_position", "locked": True, "sl_now": 6036.0}
    w_end = datetime(2026, 11, 4, 16, 0, tzinfo=ny)
    eng._execute(us, _d(2026, 11, 4), stp, None, datetime(2026, 11, 4, 12, 0, tzinfo=ny), w_end)
    check("Profit Lock: SL-ul REAL mutat o dată (TRADE_ACTION_SLTP la intrare + 4R)",
          len(fake.sent) == 1 and fake.sent[0]["action"] == 6 and fake.sent[0]["sl"] == 6036.0, fake.sent)
    fake.sent = []
    eng._execute(us, _d(2026, 11, 4), stp, None, datetime(2026, 11, 4, 12, 5, tzinfo=ny), w_end)
    check("... re-iterația nu trimite din nou", not fake.sent, fake.sent)
    fake.positions[0].sl, fake.sent = 6040.0, []
    eng2 = E.DailyEngine(mt5_module=fake)
    eng2._execute(us, _d(2026, 11, 4), stp, None, datetime(2026, 11, 4, 12, 10, tzinfo=ny), w_end)
    check("SL real deja mai protector (manual / restart) → nu e coborât", not fake.sent, fake.sent)
    fake.positions[0].sl, fake.sent = 6000.0, []
    eng3 = E.DailyEngine(mt5_module=fake)
    eng3._execute({**us, "paused": True}, _d(2026, 11, 4), stp, None, datetime(2026, 11, 4, 12, 15, tzinfo=ny), w_end)
    check("piață pe PAUZĂ: Profit Lock gestionează în continuare poziția existentă",
          len(fake.sent) == 1 and fake.sent[0]["action"] == 6, fake.sent)
    # --- inchiderea de vineri GLOBALA (Setari Globale): pozitia Daily inchisa la ora de vineri, nimic nou
    from live import global_guard as GG
    _ls = GG.load_settings
    GG.load_settings = lambda path=None: GG.sanitize({"friday_close": {"enabled": True, "hour": 20}})
    fake.positions = [SimpleNamespace(ticket=31, symbol="US500", magic=880001, comment="D-US500-1113", volume=0.1,
                                      type=0, sl=6000.0, tp=0.0)]
    fake.sent = []
    eng5 = E.DailyEngine(mt5_module=fake)
    fri_ny = datetime(2026, 11, 13, 13, 30, tzinfo=ny)              # vineri 20:30 RO (fus aplicatie RO)
    eng5._execute({**us, "profit_lock": None}, _d(2026, 11, 13), {"phase": "in_position"}, None, fri_ny,
                  datetime(2026, 11, 13, 16, 0, tzinfo=ny))
    check("vineri după ora globală de închidere: poziția Daily închisă (fără să aștepte finalul ferestrei)",
          fake.sent and fake.sent[0]["action"] == fake.TRADE_ACTION_DEAL and "position" in fake.sent[0], fake.sent)
    GG.load_settings = _ls
    # --- limita de marja (toate engine-urile)
    acc = SimpleNamespace(login=1, server="Fake", trade_mode=0, equity=200.0, margin=40.0, currency="USD")
    fake.account_info = lambda: acc
    fake.order_calc_margin = lambda t, s_, lots, px: 147.6 * lots / 0.1
    eng4 = E.DailyEngine(mt5_module=fake)
    eng4.cfg = {"sizing": {"max_margin_pct": 80}, "markets": []}
    lots, why = eng4._margin_ok("DE40", 1, 0.1, 24000.0)
    check("marjă: 40 $ folosiți + 147,6 $ > 80% din 200 $ → ordinul NU se plasează (motiv vizibil)",
          lots == 0 and "marjă insuficientă" in (why or ""), (lots, why))
    acc.margin = 0.0
    lots, why = eng4._margin_ok("DE40", 1, 0.2, 24000.0)
    check("marjă: 0,2 loturi (295 $) > 160 $ → redus la 0,1", abs(lots - 0.1) < 1e-9 and "redus" in (why or ""), (lots, why))


if __name__ == "__main__":
    t_strategy()
    t_equivalence()
    t_time()
    t_engine()
    t_no_orders()
    t_execution()
    t_reentry()
    t_pause()
    t_modes_plock()
    print(f"\n{PASS} OK, {FAIL} FAIL")
    sys.exit(1 if FAIL else 0)
