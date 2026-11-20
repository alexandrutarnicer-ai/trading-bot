"""Reluare LIVE a unei zile prin Daily Engine REAL (executie pornita), pe barele M5 REALE din MT5 — fara niciun ordin.

Verifica intregul lant de executie cu configuratia CURENTA (daily_engine/config.json) inainte de Live: armarea zilei,
politica de risc (Market Risk Override), lotul, marja, ordinele stop OCO / ordinul la piata, SL-ul, inchiderea la final
de fereastra si limita de trade-uri / zi pe piata.

Izolare (verificata la pornire): `order_send` NU ajunge la broker — un registru simulat il primeste (umple ordinele stop
pe barele reale, aplica SL-ul, inchiderile); contul, specificatiile si marja vin din MT5 REAL (doar citire); starea,
jurnalul, statusul, notificarile si auditul merg intr-un director temporar; Trading LIVE e considerat deblocat DOAR in
acest proces (fisierul nu e atins); o piata e trecuta pe Live doar in copia din memorie a configuratiei.

    python scripts/research_daily/daily_live_replay.py [--day 2026-11-19] [--symbol DE40]
"""
from __future__ import annotations

import argparse
import copy
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
RO = ZoneInfo("Europe/Bucharest")
NY = ZoneInfo("America/New_York")


class Book:
    """Registrul simulat al brokerului: pozitii + ordine pending ale replay-ului."""

    def __init__(self):
        self.pos, self.ords, self.deals, self.sent = [], [], [], []
        self.ticket = 900000

    def nt(self):
        self.ticket += 1
        return self.ticket


class ReplayMt5:
    """MT5 real pentru cont / specificatii / marja; barele si tick-ul = momentul simulat; order_send = registrul."""

    def __init__(self, real, sym, bars, book):
        self.r, self.sym, self.bars, self.book, self.now_srv = real, sym, bars, book, None
        for k in dir(real):
            if k.isupper():
                setattr(self, k, getattr(real, k))

    # ── timp / date ──
    def set_now(self, now_utc):
        self.now_srv = (now_utc.astimezone(NY).replace(tzinfo=None) + timedelta(hours=7))
        self.ts = int(self.now_srv.replace(tzinfo=timezone.utc).timestamp())

    def _cur(self):
        b = self.bars[self.bars["time"] <= self.ts]
        return b.iloc[-1] if len(b) else None

    def copy_rates_from_pos(self, sym, tf, start, n):
        if sym != self.sym:                                            # celelalte piete: fara bare (doar piata reluata)
            return None
        b = self.bars[self.bars["time"] + 300 <= self.ts]             # doar bare INCHISE (+ engine-ul filtreaza oricum)
        return b.tail(n).to_records(index=False)

    def symbol_info_tick(self, sym):
        if sym != self.sym:
            return None
        c = self._cur()
        if c is None:
            return None
        sp = float(c["spread"]) * self.r.symbol_info(sym).point
        px = float(c["open"])
        return SimpleNamespace(time=self.ts, bid=px, ask=px + sp, last=px)

    def terminal_info(self):
        return SimpleNamespace(connected=True, trade_allowed=True)

    def __getattr__(self, k):                                          # cont, specificatii, marja: MT5 REAL
        if k in ("order_send", "order_check"):
            raise RuntimeError("BLOCAT: ordinele nu ies din replay")
        return getattr(self.r, k)

    def positions_get(self, **kw):
        return tuple(p for p in self.book.pos if not kw.get("symbol") or p.symbol == kw["symbol"])

    def orders_get(self, **kw):
        return tuple(o for o in self.book.ords if not kw.get("symbol") or o.symbol == kw["symbol"])

    def history_deals_get(self, *a, **kw):
        return tuple(self.book.deals)

    # ── ordinele (interceptate) ──
    def order_send(self, req):
        B = self.book
        B.sent.append(dict(req))
        a = req["action"]
        ok = SimpleNamespace(retcode=self.r.TRADE_RETCODE_DONE, order=0, price=req.get("price", 0.0), comment="replay")
        if a == self.r.TRADE_ACTION_DEAL and req.get("position"):                         # inchidere
            p = next((x for x in B.pos if x.ticket == req["position"]), None)
            if p:
                B.pos.remove(p)
                B.deals.append(("close", p.comment, req["price"], self.now_srv))
            return ok
        if a == self.r.TRADE_ACTION_DEAL:                                                  # deschidere la piata
            t = B.nt()
            buy = req["type"] == self.r.ORDER_TYPE_BUY
            B.pos.append(SimpleNamespace(ticket=t, symbol=req["symbol"], volume=req["volume"], magic=req["magic"],
                                         comment=req["comment"], price_open=req["price"], sl=req["sl"], tp=req.get("tp", 0.0),
                                         type=0 if buy else 1, time=self.ts, profit=0.0))
            ok.order = t
            return ok
        if a == self.r.TRADE_ACTION_PENDING:
            t = B.nt()
            B.ords.append(SimpleNamespace(ticket=t, symbol=req["symbol"], volume_initial=req["volume"], magic=req["magic"],
                                          comment=req["comment"], price_open=req["price"], sl=req["sl"], tp=req.get("tp", 0.0),
                                          type=req["type"]))
            ok.order = t
            return ok
        if a == self.r.TRADE_ACTION_REMOVE:
            B.ords = [o for o in B.ords if o.ticket != req["order"]]
            return ok
        if a == self.r.TRADE_ACTION_SLTP:
            for p in B.pos:
                if p.ticket == req["position"]:
                    p.sl = req["sl"]
            return ok
        return SimpleNamespace(retcode=10013, order=0, price=0.0, comment="necunoscut")

    def step_fills(self, bar):
        """Bara inchisa: ordinele stop atinse devin pozitii; SL-urile atinse inchid pozitia."""
        B = self.book
        for o in list(B.ords):
            buy = o.type == self.r.ORDER_TYPE_BUY_STOP
            if (buy and bar["high"] >= o.price_open) or (not buy and bar["low"] <= o.price_open):
                B.ords.remove(o)
                B.pos.append(SimpleNamespace(ticket=o.ticket, symbol=o.symbol, volume=o.volume_initial, magic=o.magic,
                                             comment=o.comment, price_open=o.price_open, sl=o.sl, tp=o.tp, type=0 if buy else 1,
                                             time=int(bar["time"]), profit=0.0))
                B.deals.append(("fill", o.comment, o.price_open, bar["time"]))
        for p in list(B.pos):
            if p.sl and ((p.type == 0 and bar["low"] <= p.sl) or (p.type == 1 and bar["high"] >= p.sl)):
                B.pos.remove(p)
                B.deals.append(("SL", p.comment, p.sl, bar["time"]))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", default="2026-11-19")
    ap.add_argument("--symbol", default="DE40")
    a = ap.parse_args()
    import MetaTrader5 as mt5
    import pandas as pd
    if not mt5.initialize():
        sys.exit("MT5 indisponibil")
    import daily_engine.engine as E
    from daily_engine.config import load_config, _sanitize
    import live_guard
    from api import audit_log
    tmp = tempfile.mkdtemp(prefix="daily_replay_")
    E.STATE_FILE, E.STATUS_FILE, E.TRADES_FILE = (os.path.join(tmp, f) for f in ("state.json", "status.json", "trades.jsonl"))
    audit_log.AUDIT_FILE = os.path.join(tmp, "audit.jsonl")
    notes = []
    E._notify = lambda cfg, text, *k, **kw: notes.append(text)
    try:
        import api.telegram as T
        T.send_message = lambda *k, **kw: notes.append(k[0] if k else "")
    except Exception:
        pass
    live_guard.live_allowed = lambda comp: True                      # DOAR in acest proces (fisierul nu e atins)
    cfg = copy.deepcopy(load_config())
    for m in cfg["markets"]:
        m["exec_mode"] = "live" if m["symbol"] == a.symbol else "shadow"
    cfg = _sanitize(cfg)
    E.load_config = lambda: copy.deepcopy(cfg)
    day = datetime.fromisoformat(a.day)
    r = mt5.copy_rates_range(a.symbol, mt5.TIMEFRAME_M5, day - timedelta(days=1), day + timedelta(days=1, hours=8))
    bars = pd.DataFrame(r)
    book = Book()
    fake = ReplayMt5(mt5, a.symbol, bars, book)
    # izolare: verificata INAINTE de orice
    try:
        fake.r.order_send  # noqa: B018 — exista in modulul real, dar instanta replay o suprascrie
        assert ReplayMt5.order_send is not None and fake.order_send.__func__ is ReplayMt5.order_send
    except AssertionError:
        sys.exit("izolarea order_send a esuat — nu rulez")
    eng = E.DailyEngine(mt5_module=fake)
    m = next(x for x in cfg["markets"] if x["symbol"] == a.symbol)
    print(f"Replay {a.symbol} {a.day} · config: sesiuni {m['sessions']} · max {m['max_trades_per_day']}/zi · re-intrări "
          f"{'DA' if m['reentry']['enabled'] else 'nu'} · risc {m.get('risk')} · cont {mt5.account_info().equity} $ (REAL, doar citire)")
    print(f"politica de risc: {eng.risk_policy(a.symbol)}")
    t = datetime(day.year, day.month, day.day, 8, 0, tzinfo=RO)
    end = datetime(day.year, day.month, day.day, 23, 59, tzinfo=RO)
    last_bar = None
    seen_sent = 0
    while t <= end:
        now = t.astimezone(timezone.utc)
        fake.set_now(now)
        closed = bars[bars["time"] + 300 <= fake.ts]
        if len(closed) and (last_bar is None or closed.iloc[-1]["time"] != last_bar):
            for _, b in closed[closed["time"] > (last_bar or 0)].iterrows():
                fake.step_fills(b)
            last_bar = closed.iloc[-1]["time"]
        eng.iteration(now_utc=now)
        for req in book.sent[seen_sent:]:
            kind = {mt5.TRADE_ACTION_DEAL: "DEAL", mt5.TRADE_ACTION_PENDING: "PENDING", mt5.TRADE_ACTION_REMOVE: "REMOVE",
                    mt5.TRADE_ACTION_SLTP: "SLTP"}.get(req["action"], req["action"])
            typ = {mt5.ORDER_TYPE_BUY: "BUY", mt5.ORDER_TYPE_SELL: "SELL", mt5.ORDER_TYPE_BUY_STOP: "BUY_STOP",
                   mt5.ORDER_TYPE_SELL_STOP: "SELL_STOP"}.get(req.get("type"), "")
            print(f"  {t:%H:%M} RO  order_send {kind:7} {typ:9} vol {req.get('volume', '')} preț {req.get('price', '')} "
                  f"SL {req.get('sl', '')} magic {req.get('magic', '')} '{req.get('comment', '')}'"
                  + (f" poz #{req['position']}" if req.get("position") else "") + (f" ord #{req['order']}" if req.get("order") else ""))
        seen_sent = len(book.sent)
        t += timedelta(minutes=1)
    print("Evenimente registru:", [(k, c, round(float(p), 2)) for k, c, p, *_ in book.deals])
    print("Poziții / ordine rămase:", len(book.pos), len(book.ords))
    sc = E.scorecard(E.load_trades())
    print("Trade-uri virtuale (jurnalul temporar):", [(x.get("session"), x.get("k"), x["side"], round(x["R"], 2), x.get("mode"),
                                                         x.get("lots")) for x in E.load_trades()])
    print("Notificări generate:", len(notes))
    for n in notes:
        if "EXECUȚIE" in n or "ordin" in n.lower() or "BLOC" in n:
            print("   •", n.replace("\n", " | ")[:220])
    print("director temporar:", tmp, "| scorecard:", sc.get("total_R"))


if __name__ == "__main__":
    main()
