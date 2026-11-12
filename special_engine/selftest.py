"""Special Engine — selftest (offline; MT5 simulat pe istoricul din data/research_*; fara date → sectiunile sar).
Rulare: python -m special_engine.selftest"""
from __future__ import annotations

import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from types import SimpleNamespace

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from special_engine import data as D  # noqa: E402
from special_engine import engine as E  # noqa: E402
import api.audit_log as _AL  # noqa: E402
_AL.AUDIT_FILE = os.path.join(tempfile.mkdtemp(), "audit.jsonl")    # testele nu scriu in jurnalul de audit real
from special_engine.config import COSTS, NOISE_MARKETS, ORB_MARKETS, sanitize  # noqa: E402
from special_engine.strategies import nr_flag  # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  OK   {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name} {str(detail)[:300]}")


def load_hist(sym):
    for p in (os.path.join(ROOT, "data", "research_daily", f"{sym}_M5_server.csv"),
              os.path.join(ROOT, "data", "research_special", f"{sym}_M5.csv")):
        if os.path.exists(p):
            return pd.read_csv(p, parse_dates=["time"])
    return None


POINT = {"DE40": 0.01, "USTEC": 0.01, "US500": 0.01, "XAUUSD": 0.01, "JP225": 0.01}   # MT5 ICMarketsEU (symbol_info.point)


def t_config_and_safety():
    print("1. siguranta: mod per piata (implicit SHADOW), ordine DOAR in executor.py")
    check("mod global vechi „execute” ignorat — fara piete Live = shadow", sanitize({"mode": "execute"})["mode"] == "shadow")
    c = sanitize({"markets": {"JP225": {"mode": "live"}, "USTEC": {"mode": "pause", "paused_at": "2026-11-12T10:00:00+00:00"},
                              "NOPE": {"mode": "live"}}})
    check("moduri per piata: JP225 Live, USTEC Pauza, simbol necunoscut ignorat; rezumat = execute",
          c["markets"]["JP225"]["mode"] == "live" and c["markets"]["USTEC"]["mode"] == "pause" and "NOPE" not in c["markets"]
          and c["mode"] == "execute", c["markets"])
    from special_engine.config import market_mode
    check("piata noua (ex. aleasa de selectia trimestriala) = SHADOW", market_mode(c, "DE40") == "shadow")
    check("risc implicit 1% / trade, risc total deschis 2%, max 2 pozitii, marja 80%",
          (sanitize(None)["risk_pct"], sanitize(None)["max_open_risk_pct"], sanitize(None)["max_positions"],
           sanitize(None)["max_margin_pct"]) == (0.01, 0.02, 2, 80.0))
    check("config corupt → implicit (A: 36 luni, t 1,5, NR4; B: USTEC)",
          sanitize("x")["strategy_a"]["lookback_months"] == 36 and sanitize(None)["strategy_b"]["symbol"] == "USTEC")
    pkg = os.path.join(ROOT, "special_engine")
    bad = [f for f in os.listdir(pkg) if f.endswith(".py") and f not in ("selftest.py", "executor.py")
           and re.search(r"order_send|TRADE_ACTION_DEAL|TRADE_ACTION_PENDING|TRADE_ACTION_SLTP", open(os.path.join(pkg, f), encoding="utf-8").read())]
    check("order_send / TRADE_ACTION DOAR in special_engine/executor.py", not bad, bad)


def t_equivalence():
    print("2. echivalenta cu cercetarea (aceleasi functii, aceleasi date)")
    ro = os.path.join(ROOT, "data", "research_special", "orb_trades_all.csv")
    rn = os.path.join(ROOT, "data", "research_special", "noise_trades_all.csv")
    if not (os.path.exists(ro) and os.path.exists(rn)):
        print("  (sarit: fara datele de cercetare)")
        return
    ref_o = pd.read_csv(ro, parse_dates=["entry_t"])
    for sym in ("DE40", "XAUUSD"):
        d = load_hist(sym)
        if d is None:
            continue
        tz, op, last = ORB_MARKETS[sym]
        mine = pd.DataFrame(D.orb_history(d, sym, tz, op, last, *COSTS[sym], POINT[sym]))
        r = ref_o[ref_o.sym == sym]
        a = mine.groupby("comp").R.agg(["count", "sum"]).round(6)
        b = r.assign(comp="ORB:" + r.sym + ":" + r["var"]).groupby("comp").R.agg(["count", "sum"]).round(6)
        check(f"ORB {sym}: 6 variante identice (n, ΣR)", a.equals(b), a.join(b, rsuffix="_ref") if not a.equals(b) else "")
    ref_n = pd.read_csv(rn, parse_dates=["entry_t"])
    d = load_hist("USTEC")
    if d is not None:
        tz, op, cl = NOISE_MARKETS["USTEC"]
        mine = pd.DataFrame(D.noise_history(d, "USTEC", tz, op, cl, 1.75, POINT["USTEC"]))  # costul din rularea de cercetare
        r = ref_n[ref_n.sym == "USTEC"].reset_index(drop=True)
        same = len(mine) == len(r) and (mine.entry_t.values == r.entry_t.values).all() and np.allclose(mine.R, r.R, atol=1e-9)
        check(f"NOISE USTEC: {len(mine)} trade-uri identice (intrare + R)", same)


def t_selection():
    print("3. selectia trimestriala: fara look-ahead, reguli")
    rng = np.random.default_rng(3)
    rows = []
    for comp, mu in (("ORB:AAA:5/breakout", 0.3), ("ORB:AAA:15/direction", 0.25), ("ORB:BBB:5/breakout", 0.0),
                     ("NOISE:CCC", 0.2), ("ORB:DDD:5/breakout", 0.4)):
        for t in pd.date_range("2022-01-03", "2026-12-28", freq="2D"):
            rows.append({"comp": comp, "sym": comp.split(":")[1], "entry_t": t, "R": rng.normal(mu, 1.0)})
    df = pd.DataFrame(rows)
    a = sanitize(None)["strategy_a"]
    q = pd.Timestamp("2025-07-01")
    comps, tab = D.select(df, q, a)
    check("o singura componenta pe piata (AAA: cea cu t maxim)", sum(c.startswith("ORB:AAA") for c in comps) == 1, comps)
    check("componenta fara edge (BBB, media 0) exclusa", "ORB:BBB:5/breakout" not in comps, comps)
    df2 = df.copy()
    df2.loc[df2.entry_t >= q, "R"] = 99.0                     # viitorul „perfect” nu trebuie sa conteze
    check("trade-urile de dupa inceputul trimestrului NU influenteaza selectia", D.select(df2, q, a)[0] == comps)
    d1 = pd.DataFrame({"time": pd.date_range("2026-11-02", periods=5, freq="D"), "high": [10, 9, 8, 7.5, 9],
                       "low": [0, 1, 2, 3, 0]})
    check("NR4: range-ul de ieri (4,5) = minimul ultimelor 4 → True", nr_flag(d1, pd.Timestamp("2026-11-06"), 4) is True)
    check("NR4: zi dupa o zi larga → False", nr_flag(d1, pd.Timestamp("2026-11-07"), 4) is False)


class FakeMt5:
    TIMEFRAME_M5, TIMEFRAME_D1 = 5, 16408

    def __init__(self, m5: dict, d1: dict):
        self.m5, self.d1, self.now_server = m5, d1, None
        self.sent = []

    def initialize(self):
        return True

    def symbol_select(self, s, on):
        return s in self.m5

    def symbol_info(self, s):
        return SimpleNamespace(point=POINT[s])

    def account_info(self):
        return SimpleNamespace(equity=1000.0)

    def copy_rates_from_pos(self, s, tf, start, n):
        src = self.m5[s] if tf == self.TIMEFRAME_M5 else self.d1[s]
        x = src[src.time <= self.now_server].tail(n)
        arr = np.zeros(len(x), dtype=[("time", "i8"), ("open", "f8"), ("high", "f8"), ("low", "f8"), ("close", "f8"),
                                      ("tick_volume", "i8"), ("spread", "i8")])
        arr["time"] = ((x.time - pd.Timestamp("1970-01-01")) // pd.Timedelta(seconds=1)).to_numpy()
        for k in ("open", "high", "low", "close", "tick_volume", "spread"):
            arr[k] = x[k].to_numpy()
        return arr

    def order_send(self, req):                     # nu trebuie apelat niciodata
        self.sent.append(req)


def t_live_equals_backtest():
    print("4. engine-ul LIVE reluat pe zile istorice = backtestul (MT5 simulat)")
    d = load_hist("USTEC")
    if d is None:
        print("  (sarit: fara istoric USTEC)")
        return
    d1 = d.set_index("time").resample("1D").agg({"open": "first", "high": "max", "low": "min", "close": "last",
                                                "tick_volume": "sum", "spread": "max"}).dropna().reset_index()
    tmp = tempfile.mkdtemp()
    for n in ("STATUS_FILE", "STATE_FILE", "TRADES_FILE", "SELECTION_FILE"):
        setattr(E, n, os.path.join(tmp, os.path.basename(getattr(E, n))))
    E._notify = lambda *a, **k: None
    E.load_config = lambda: {**sanitize(None), "notify_telegram": False}
    fake = FakeMt5({"USTEC": d}, {"USTEC": d1})
    eng = E.SpecialEngine(mt5_module=fake)
    eng.selection = {"quarter": "x", "components": []}
    eng.ensure_selection = lambda now: None
    tz, op, cl = NOISE_MARKETS["USTEC"]
    ref = pd.DataFrame(D.noise_history(d, "USTEC", tz, op, cl, sum(COSTS["USTEC"]), POINT["USTEC"]))
    ref["day"] = ref.entry_t.dt.normalize()
    days = sorted(ref.day.unique())[-25:]
    bad = 0
    for dd in days:
        day = pd.Timestamp(dd)
        # ora 16:10 NY = sesiune incheiata; server = NY + 7h
        now_ny = day + pd.Timedelta(hours=16, minutes=10)
        fake.now_server = now_ny + pd.Timedelta(hours=7)
        now_utc = now_ny.tz_localize("America/New_York").tz_convert("UTC").to_pydatetime()
        st = eng.iteration(now_utc)
        live = [c for c in st["components"] if c["strategy"] == "B"][0]
        want = ref[ref.day == day]
        if live.get("trades_today") != len(want) or abs((live.get("R_today") or 0) - round(want.R.sum(), 3)) > 1e-6:
            bad += 1
    check(f"B pe ultimele {len(days)} zile cu trade-uri: aceleasi trade-uri si R ca backtestul", bad == 0, f"{bad} zile diferite")
    n1 = len(E.load_trades())
    eng.iteration(now_utc)
    eng2 = E.SpecialEngine(mt5_module=fake)          # „restart”
    eng2.selection, eng2.ensure_selection = eng.selection, (lambda now: None)
    eng2.iteration(now_utc)
    check("restart / re-iteratie: fara dubluri in jurnal", len(E.load_trades()) == n1, (n1, len(E.load_trades())))
    check("zero ordine trimise", not fake.sent)
    # bara IN FORMARE ignorata: la 10:02 NY nu exista inca bara inchisa 10:00 → fara intrare la 10:00
    day = pd.Timestamp(days[-1])
    fake.now_server = day + pd.Timedelta(hours=10, minutes=2) + pd.Timedelta(hours=7)
    eng3 = E.SpecialEngine(mt5_module=fake)
    b = eng3._today_bars("USTEC", tz, op, cl, False, (day + pd.Timedelta(hours=10, minutes=2)).tz_localize(tz).tz_convert("UTC").to_pydatetime())
    check("doar bare INCHISE (ultima bara = 09:55 la ora 10:02)", len(b) and int(b.mins.iloc[-1]) == 9 * 60 + 55,
          b.mins.tail(2).tolist() if len(b) else "gol")


def t_display_times():
    """annotate_trade: ora bursei + fusul aplicatiei, observat live / reconstituit (doar afisare)."""
    from special_engine.engine import annotate_trade
    real = {"day": "2026-11-05", "strategy": "B", "comp": "NOISE:USTEC", "symbol": "USTEC", "entry_t": "2026-11-05 09:55:00",
            "exit_t": "2026-11-05 15:55:00", "d": -1, "why": "EOD", "R": 10.1, "logged_at": "2026-11-05T21:51:15+00:00"}
    a = annotate_trade(real, "Europe/Bucharest")
    check("NOISE USTEC 05.11: intrare 10:00 NY = 17:00 RO, iesire 16:00 NY = 23:00 RO (decizie la inchiderea lumanarii)",
          (a["entry_exch"], a["exit_exch"], a["entry_app"], a["exit_app"]) == ("10:00", "16:00", "2026-11-05 17:00",
                                                                              "2026-11-05 23:00"), a)
    check("... inregistrat la 23:51 RO dupa inchidere → RECONSTITUIT (nu live)", a["live"] is False and "reconstituit" in a["live_note"], a)
    check("... fus Germania: 16:00 / 22:00 DE", annotate_trade(real, "Europe/Berlin")["entry_app"].endswith("16:00"))
    live = {**real, "logged_at": "2026-11-05T21:03:00+00:00", "seen_since": "2026-11-05T13:00:00+00:00"}
    check("inregistrat la 3 min dupa iesire, engine pornit inainte de intrare → ✓ live", annotate_trade(live)["live"] is True)
    part = {**live, "seen_since": "2026-11-05T16:00:00+00:00"}
    b = annotate_trade(part)
    check("engine pornit DUPA intrare → partial (nu live)", b["live"] is False and b["live_note"].startswith("parțial"), b)
    orb = {"comp": "ORB:JP225:5/direction", "symbol": "JP225", "entry_t": "2026-11-06 09:05:00", "exit_t": "2026-11-06 14:55:00",
           "why": "EOD", "day": "2026-11-06"}
    c = annotate_trade(orb)
    check("ORB JP225: intrare 09:05 Tokyo (open-ul lumanarii) = 02:05 RO, EOD la 15:00 Tokyo = 08:00 RO; fara logged_at → live necunoscut",
          (c["entry_exch"], c["exit_exch"], c["entry_app"], c["exit_app"], c["live"]) ==
          ("09:05", "15:00", "2026-11-06 02:05", "2026-11-06 08:00", None), c)
    check("ORB iesire pe SL = in lumanare (fara +5 min)", annotate_trade({**orb, "why": "SL"})["exit_exch"] == "14:55")
    check("trade stricat → returnat neschimbat (afisarea nu pica)", annotate_trade({"comp": "X"}) == {"comp": "X"})


class TradeMt5(FakeMt5):
    """MT5 simulat CU ordine (pozitii, ordine, cont DEMO / REAL) — pentru executia reala."""
    TRADE_ACTION_DEAL, TRADE_ACTION_PENDING, TRADE_ACTION_REMOVE = 1, 5, 8
    ORDER_TYPE_BUY, ORDER_TYPE_SELL, ORDER_TYPE_BUY_STOP, ORDER_TYPE_SELL_STOP = 0, 1, 4, 5
    ORDER_TIME_GTC, TRADE_RETCODE_DONE, TRADE_RETCODE_PLACED, POSITION_TYPE_BUY = 0, 10009, 10008, 0

    def __init__(self, m5, d1, trade_mode=0, equity=10000.0, margin_per_lot=100.0):
        super().__init__(m5, d1)
        self.trade_mode, self.equity, self.mpl = trade_mode, equity, margin_per_lot
        self.positions, self.orders, self._tk, self.margin = [], [], 500, 0.0

    def symbol_info(self, s):
        return SimpleNamespace(point=POINT[s], digits=2, volume_min=0.1, volume_step=0.1, volume_max=100.0,
                               trade_tick_size=0.01, trade_tick_value=0.01, filling_mode=2)

    def account_info(self):
        return SimpleNamespace(equity=self.equity, balance=self.equity, margin=self.margin, trade_mode=self.trade_mode,
                               currency="USD", login=1, server="Fake")

    def symbol_info_tick(self, s):
        x = self.m5[s][self.m5[s].time <= self.now_server].tail(1)
        px = float(x.close.iat[0])
        return SimpleNamespace(ask=px + 0.5, bid=px - 0.5, time=0)

    def order_calc_margin(self, t, s, lots, px):
        return self.mpl * lots / 0.1

    def positions_get(self, symbol=None):
        return [p for p in self.positions if symbol in (None, p.symbol)]

    def orders_get(self, symbol=None):
        return [o for o in self.orders if symbol in (None, o.symbol)]

    def order_send(self, req):
        self.sent.append(dict(req))
        self._tk += 1
        if req["action"] == self.TRADE_ACTION_DEAL and "position" in req:
            self.positions = [p for p in self.positions if p.ticket != req["position"]]
        elif req["action"] == self.TRADE_ACTION_DEAL:
            self.positions.append(SimpleNamespace(ticket=self._tk, symbol=req["symbol"], magic=req["magic"],
                                                  comment=req["comment"], volume=req["volume"], price_open=req["price"],
                                                  sl=req["sl"], type=0 if req["type"] == self.ORDER_TYPE_BUY else 1))
        elif req["action"] == self.TRADE_ACTION_PENDING:
            self.orders.append(SimpleNamespace(ticket=self._tk, symbol=req["symbol"], magic=req["magic"],
                                               comment=req["comment"], type=req["type"]))
        elif req["action"] == self.TRADE_ACTION_REMOVE:
            self.orders = [o for o in self.orders if o.ticket != req["order"]]
        return SimpleNamespace(retcode=10009, order=self._tk)


def t_execution():
    print("5. EXECUTIE reala per piata (MT5 simulat; zero ordine reale in teste)")
    d = load_hist("USTEC")
    if d is None:
        print("  (sarit: fara istoric USTEC)")
        return
    d1 = d.set_index("time").resample("1D").agg({"open": "first", "high": "max", "low": "min", "close": "last",
                                                "tick_volume": "sum", "spread": "max"}).dropna().reset_index()
    import live_guard
    from live import global_guard as GG
    GG_defaults = GG.sanitize(None)
    GG.load_settings = lambda path=None: GG_defaults            # Setarile Globale OPRITE (izolare de fisierul real)
    tz, op, cl = NOISE_MARKETS["USTEC"]
    ref = pd.DataFrame(D.noise_history(d, "USTEC", tz, op, cl, sum(COSTS["USTEC"]), POINT["USTEC"]))
    ref["day"] = ref.entry_t.dt.normalize()
    day = pd.Timestamp(sorted(ref.day.unique())[-3])
    want = ref[ref.day == day]

    def run_day(mode, trade_mode=0, live=False, equity=10000.0, start_min=0, cfg_extra=None, mpl=100.0, notes=None):
        tmp = tempfile.mkdtemp()
        for n in ("STATUS_FILE", "STATE_FILE", "TRADES_FILE", "SELECTION_FILE"):
            setattr(E, n, os.path.join(tmp, os.path.basename(getattr(E, n))))
        E._notify = lambda cfg, text, force=False: (notes.append(text) if notes is not None else None)
        cfg = {**sanitize({"markets": {"USTEC": {"mode": mode, "paused_at": "2000-01-01T00:00:00+00:00"}}}),
               "notify_telegram": False, **(cfg_extra or {})}
        E.load_config = lambda: cfg
        live_guard.live_allowed = lambda comp: live
        fake = TradeMt5({"USTEC": d}, {"USTEC": d1}, trade_mode=trade_mode, equity=equity, margin_per_lot=mpl)
        eng = E.SpecialEngine(mt5_module=fake)
        eng.selection = {"quarter": "x", "components": []}
        eng.ensure_selection = lambda now: None
        for mins in range(start_min, 6 * 60 + 45, 5):
            now_ny = day + pd.Timedelta(hours=9, minutes=30 + mins + 1)
            fake.now_server = now_ny + pd.Timedelta(hours=7)
            eng.iteration(now_ny.tz_localize("America/New_York").tz_convert("UTC").to_pydatetime())
        return fake, eng

    fake, _ = run_day("shadow")
    check("piata pe SHADOW: zero ordine reale (shadow-ul ruleaza normal)", not fake.sent, fake.sent[:2])
    fake, _ = run_day("live", trade_mode=2, live=False)
    check("piata pe LIVE + cont REAL nedeblocat: zero ordine", not fake.sent, fake.sent[:2])
    notes = []
    fake, eng = run_day("live", trade_mode=0, notes=notes)
    deals = [r for r in fake.sent if r["action"] == fake.TRADE_ACTION_DEAL]
    entries = [r for r in deals if "position" not in r]
    check(f"piata pe LIVE (DEMO): cate un ordin real pe fiecare trade virtual ({len(want)}) + toate inchise",
          len(entries) == len(want) and len(deals) == 2 * len(want) and not fake.positions, (len(entries), len(want), fake.positions))
    e0 = entries[0] if entries else {}
    check("ordin: magic 660001, comment X-USTEC-MMDD0, SL atasat pe partea corecta",
          e0.get("magic") == 660001 and str(e0.get("comment", "")).startswith(f"X-USTEC-{day:%m%d}0")
          and ((e0.get("type") == 0 and e0["sl"] < e0["price"]) or (e0.get("type") == 1 and e0["sl"] > e0["price"])), e0)
    check("... notificare pentru fiecare ordin real (si cu Telegram-ul de rutina oprit)", any("ORDINE REALE" in t for t in notes))
    trades = E.load_trades()
    check("trade-urile cu ordin real marcate mode=execute (rapoartele nu le numara de doua ori)",
          trades and all(t.get("mode") == "execute" for t in trades), [t.get("mode") for t in trades])
    fake, _ = run_day("pause")
    check("piata pe PAUZA: zero ordine si zero trade-uri virtuale noi", not fake.sent and not E.load_trades(), fake.sent[:1])
    fake, _ = run_day("live", trade_mode=0, start_min=6 * 60 + 25)
    check("restart TARZIU (dupa semnal): niciun ordin vechi plasat", not [r for r in fake.sent if "position" not in r], fake.sent[:1])
    fake, _ = run_day("live", trade_mode=0, equity=1000.0)
    check("cont mic: riscul la lotul minim > riscul total permis (2%) → ordinul NU se plaseaza",
          not [r for r in fake.sent if "position" not in r], fake.sent[:1])
    fake, _ = run_day("live", trade_mode=0, mpl=9000.0)
    check("marja insuficienta (lotul minim > 80% din equity) → ordinul NU se plaseaza",
          not [r for r in fake.sent if "position" not in r], fake.sent[:1])
    fake, _ = run_day("live", trade_mode=0, cfg_extra={"max_positions": 1})
    check("max 1 pozitie: tot plaseaza (o singura pozitie odata pe zi)", [r for r in fake.sent if "position" not in r])
    # pozitie ramasa din alta zi → inchisa (niciodata peste noapte)
    fake2 = TradeMt5({"USTEC": d}, {"USTEC": d1})
    fake2.positions = [SimpleNamespace(ticket=1, symbol="USTEC", magic=660001, comment="X-USTEC-01010", volume=0.1,
                                       price_open=1.0, sl=0.5, type=0)]
    fake2.now_server = day + pd.Timedelta(hours=17)
    eng2 = E.SpecialEngine(mt5_module=fake2)
    eng2.sweep_stale((day + pd.Timedelta(hours=10)).tz_localize("America/New_York").tz_convert("UTC").to_pydatetime())
    check("pozitie Special din alta zi → inchisa la urmatoarea iteratie", not fake2.positions and fake2.sent, fake2.sent)
    fake3 = TradeMt5({"USTEC": d}, {"USTEC": d1})
    fake3.positions = [SimpleNamespace(ticket=2, symbol="USTEC", magic=770015, comment="AI-1", volume=0.1,
                                       price_open=1.0, sl=0.5, type=0)]
    E.SpecialEngine(mt5_module=fake3).sweep_stale(datetime.now(timezone.utc))
    check("pozitiile ALTOR engine-uri (alt magic) nu sunt atinse", fake3.positions and not fake3.sent)
    # ORB pe JP225 (strategia A): ordin la PIATA la formarea intervalului, SL = marginea opusa, inchis la final
    dj = load_hist("JP225")
    if dj is not None:
        dj1 = dj.set_index("time").resample("1D").agg({"open": "first", "high": "max", "low": "min", "close": "last",
                                                      "tick_volume": "sum", "spread": "max"}).dropna().reset_index()
        tzj, opj, endj = ORB_MARKETS["JP225"]
        refj = pd.DataFrame(D.orb_history(dj, "JP225", tzj, opj, endj, *COSTS["JP225"], POINT["JP225"]))
        refj = refj[refj.comp == "ORB:JP225:5/direction"]
        dayj = pd.Timestamp(refj.entry_t.iloc[-5]).normalize()
        tmp = tempfile.mkdtemp()
        for n in ("STATUS_FILE", "STATE_FILE", "TRADES_FILE", "SELECTION_FILE"):
            setattr(E, n, os.path.join(tmp, os.path.basename(getattr(E, n))))
        base = sanitize({"markets": {"JP225": {"mode": "live"}}, "strategy_a": {"nr_filter": 0},
                         "strategy_b": {"enabled": False}})
        E.load_config = lambda: base
        live_guard.live_allowed = lambda comp: False
        fj = TradeMt5({"JP225": dj}, {"JP225": dj1}, trade_mode=0, equity=10000.0)
        ej = E.SpecialEngine(mt5_module=fj)
        ej.selection = {"quarter": "x", "components": ["ORB:JP225:5/direction"]}
        ej.ensure_selection = lambda now: None
        for mins in range(-10, 6 * 60 + 15, 5):
            now_t = dayj + pd.Timedelta(hours=9, minutes=mins + 1)          # Tokyo; server = NY + 7h
            now_u = now_t.tz_localize("Asia/Tokyo").tz_convert("UTC")
            fj.now_server = now_u.tz_convert("America/New_York").tz_localize(None) + pd.Timedelta(hours=7)
            ej.iteration(now_u.to_pydatetime())
        ent = [r for r in fj.sent if r["action"] == fj.TRADE_ACTION_DEAL and "position" not in r]
        rj = refj[pd.to_datetime(refj.entry_t).dt.normalize() == dayj].iloc[0]
        check("JP225 ORB direcție (LIVE, DEMO): un ordin la piață cu SL atașat, închis la final de sesiune",
              len(ent) == 1 and not fj.positions and ent[0]["comment"].startswith(f"X-JP225-{dayj:%m%d}0")
              and ent[0]["sl"] and ((ent[0]["type"] == 0 and ent[0]["sl"] < ent[0]["price"]) or
                                    (ent[0]["type"] == 1 and ent[0]["sl"] > ent[0]["price"])), (ent, fj.positions))
        trj = E.load_trades()
        check("... trade-ul virtual = backtestul (același R) și marcat execute",
              len(trj) == 1 and abs(trj[0]["R"] - rj.R) < 1e-9 and trj[0]["mode"] == "execute", (trj, rj.R))
    # inchiderea de vineri globala
    GG2 = GG.sanitize({"friday_close": {"enabled": True, "hour": 20}})
    ok, why = GG.friday_close_now("USTEC", datetime(2026, 11, 13, 19, 0, tzinfo=timezone.utc), settings=GG2)
    check("inchiderea de vineri globala: vineri 21:00 RO → activa (Special inchide + nu deschide)", ok and "vineri" in why, why)
    check("... cripto exceptat", not GG.friday_close_now("BTCUSD", datetime(2026, 11, 13, 19, 0, tzinfo=timezone.utc), settings=GG2)[0])


if __name__ == "__main__":
    t_config_and_safety()
    t_display_times()
    t_equivalence()
    t_selection()
    t_live_equals_backtest()
    t_execution()
    print(f"\n{PASS} OK, {FAIL} FAIL")
    sys.exit(1 if FAIL else 0)
