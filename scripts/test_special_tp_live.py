"""Teste Special TP pe pozitiile REALE ale Custom Engine (live/signal_generator._special_tp_step) — MT5 simulat, offline.
NU atinge MT5 / contul real. Rulare: python scripts/test_special_tp_live.py"""
import os
import sys
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "live"))
import pandas as pd                       # noqa: E402
import profit_lock as PL                  # noqa: E402
import live.signal_generator as sg        # noqa: E402

OK = FAIL = 0


def check(name, cond, detail=""):
    global OK, FAIL
    if cond:
        OK += 1
        print(f"  OK   {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name} {detail}")


class FakeMt5:
    TRADE_ACTION_SLTP, TRADE_ACTION_DEAL, TRADE_RETCODE_DONE = 6, 1, 10009
    ORDER_TYPE_BUY, ORDER_TYPE_SELL = 0, 1
    ORDER_FILLING_IOC, ORDER_FILLING_FOK, ORDER_FILLING_RETURN, ORDER_TIME_GTC = 1, 0, 2, 0

    def __init__(self, pos, bid, ask, stops_level=0, reject=None):
        self.pos, self.bid, self.ask, self.stops_level, self.reject = pos, bid, ask, stops_level, reject
        self.sent, self.calls = [], 0

    def positions_get(self, symbol=None, ticket=None):
        self.calls += 1
        return [p for p in self.pos if (symbol is None or p.symbol == symbol) and (ticket is None or p.ticket == ticket)]

    def history_orders_get(self, ticket=None):
        self.calls += 1
        return []

    def symbol_info(self, s):
        self.calls += 1
        return SimpleNamespace(point=0.00001, trade_tick_size=0.00001, trade_stops_level=self.stops_level, trade_freeze_level=0)

    def symbol_info_tick(self, s):
        self.calls += 1
        return SimpleNamespace(bid=self.bid, ask=self.ask)

    def last_error(self):
        return (1, "ok")

    def order_send(self, req):
        self.calls += 1
        self.sent.append(req)
        if self.reject:
            return SimpleNamespace(retcode=self.reject, comment="Invalid stops")
        if req["action"] == self.TRADE_ACTION_SLTP:
            for p in self.pos:
                if p.ticket == req["position"]:
                    p.sl, p.tp = req["sl"], req["tp"]
        if req["action"] == self.TRADE_ACTION_DEAL:
            self.pos = [p for p in self.pos if p.ticket != req["position"]]
        return SimpleNamespace(retcode=self.TRADE_RETCODE_DONE, comment="done", price=req.get("price"))


class Log:
    def __init__(self):
        self.w, self.i = [], []

    def warning(self, m):
        self.w.append(m)

    def info(self, m):
        self.i.append(m)


ON = {"cfg": PL.sanitize({"enabled": True}), "source": "global", "eligible": True}
OFF = {"cfg": PL.sanitize(None), "source": "off", "eligible": True}
msgs = []
sg._send_telegram = lambda t: msgs.append(t)


def bars(highs_lows, t0="2026-11-04 10:00"):
    t = pd.date_range(t0, periods=len(highs_lows), freq="15min")
    return pd.DataFrame({"time": t, "high": [h for h, _ in highs_lows], "low": [l for _, l in highs_lows],
                         "open": [0] * len(t), "close": [0] * len(t)})


def sig(d=1):
    # entry 1.10000, SL 1.09900 (risc 10 pips), TP 2R
    return {"direction": d, "entry": 1.10000, "sl": 1.09900 if d == 1 else 1.10100,
            "tp": 1.10200 if d == 1 else 1.09800, "triggered": True, "triggered_at": pd.Timestamp("2026-11-04 10:00")}


print("1. oprit (implicit) = zero apeluri MT5")
sg._special_tp_effective = lambda: OFF
fx = FakeMt5([SimpleNamespace(ticket=7, symbol="EURUSD", sl=1.099, tp=1.102, type=0, volume=0.01)], 1.1020, 1.1021)
sg._mt5_exec = fx
r = sg._special_tp_step(sig(), "S1-X", "EURUSD", 1, bars([(1.1022, 1.1001), (1.1023, 1.1015), (1.2, 1.0)]), 7, Log())
check("oprit → None, nicio interogare MT5", r is None and fx.calls == 0 and not fx.sent, (r, fx.calls))
check("engine neeligibil (daily) → oprit chiar cu Global ON",
      PL.effective({"enabled": True}, None, "daily")["source"] == "not_eligible")
check("Global ON castiga peste engine", PL.effective({"enabled": True, "step_R": 1.0}, {"enabled": True, "step_R": 0.5}, "custom")["cfg"]["step_R"] == 1.0)
check("Global OFF + engine ON → setarea engine-ului", PL.effective({"enabled": False}, {"enabled": True}, "custom")["source"] == "engine")
check("ambele oprite → off", PL.effective(None, None, "custom")["source"] == "off")

print("2. BUY: treapta 1 la 2,2R (bare inchise), fara dubluri, restart")
sg._special_tp_effective = lambda: ON
pos = SimpleNamespace(ticket=7, symbol="EURUSD", sl=1.09900, tp=1.10200, type=0, volume=0.03)
fx = FakeMt5([pos], 1.10215, 1.10216)
sg._mt5_exec = fx
log = Log()
p = sig()
df = bars([(1.10050, 1.09980), (1.10220, 1.10100), (1.30000, 1.0)])   # ultima = bara IN FORMARE (ignorata)
r = sg._special_tp_step(p, "S1-X", "EURUSD", 1, df, 7, log)
check("SLTP trimis: SL 1.10190 (+1,9R), TP 1.10260 (+2,6R)", r and r["action"] == "modify" and fx.sent and
      fx.sent[-1]["sl"] == 1.1019 and fx.sent[-1]["tp"] == 1.1026, (r, fx.sent))
check("varful = doar barele INCHISE (bara in formare la 1.3 ignorata)", r and abs(r["peak_R"] - 2.2) < 1e-6, r)
check("stare + notificare", p.get("stp_stage") == 1 and len(msgs) == 1)
n = len(fx.sent)
sg._special_tp_step(p, "S1-X", "EURUSD", 1, df, 7, log)
check("re-iteratie: nicio modificare duplicata", len(fx.sent) == n)
p2 = sig()                                                # „restart”: stare goala, SL real deja la nivel
sg._special_tp_step(p2, "S1-X", "EURUSD", 1, df, 7, log)
check("restart: SL real deja blocat → nimic trimis", len(fx.sent) == n)
pos.sl = 1.10195                                          # SL mutat manual mai sus
sg._special_tp_step(sig(), "S1-X", "EURUSD", 1, df, 7, log)
check("SL manual mai protector → nu e coborat", len(fx.sent) == n and pos.sl == 1.10195)

print("3. SELL + treapta 2")
pos = SimpleNamespace(ticket=8, symbol="EURUSD", sl=1.10100, tp=1.09800, type=1, volume=0.01)
fx = FakeMt5([pos], 1.09748, 1.09749)
sg._mt5_exec = fx
r = sg._special_tp_step(sig(-1), "S1-Y", "EURUSD", -1, bars([(1.1005, 1.0990), (1.0985, 1.09745), (1.0, 1.0)]), 8, Log())
check("SELL la 2,55R → SL 1.09760 (+2,4R), TP 1.09690", r["action"] == "modify" and fx.sent[-1]["sl"] == 1.0976
      and fx.sent[-1]["tp"] == 1.0969, (r, fx.sent))

print("4. respingeri / siguranta")
pos = SimpleNamespace(ticket=9, symbol="EURUSD", sl=1.09900, tp=1.10200, type=0, volume=0.01)
fx = FakeMt5([pos], 1.10215, 1.10216, reject=10016)
sg._mt5_exec = fx
log, p = Log(), sig()
df = bars([(1.10220, 1.10100), (1.0, 1.0)])
sg._special_tp_step(p, "S1-Z", "EURUSD", 1, df, 9, log)
sg._special_tp_step(p, "S1-Z", "EURUSD", 1, df, 9, log)
check("respins de broker: SL real neschimbat, stare neschimbata", pos.sl == 1.099 and "stp_stage" not in p)
check("... avertisment o singura data (fara spam), reincercat la bara urmatoare", len(log.w) == 1 and len(fx.sent) == 2, log.w)
fx = FakeMt5([SimpleNamespace(ticket=10, symbol="EURUSD", sl=1.099, tp=1.102, type=0, volume=0.01)], 1.10195, 1.10196,
             stops_level=10)
sg._mt5_exec = fx
r = sg._special_tp_step(sig(), "S1-W", "EURUSD", 1, df, 10, Log())
check("prea aproape de pret (stops_level 10) → amanat, nimic trimis", r["action"] == "none" and not fx.sent, r)
fx = FakeMt5([SimpleNamespace(ticket=11, symbol="EURUSD", sl=1.099, tp=1.102, type=0, volume=0.04)], 1.10150, 1.10151)
sg._mt5_exec = fx
r = sg._special_tp_step(sig(), "S1-V", "EURUSD", 1, df, 11, Log())
deal = [x for x in fx.sent if x["action"] == fx.TRADE_ACTION_DEAL]
check("pretul a revenit sub nivelul blocat → inchidere la piata, volumul REAL (0,04)", r["action"] == "close"
      and deal and deal[0]["volume"] == 0.04 and deal[0]["type"] == fx.ORDER_TYPE_SELL, fx.sent)
fx = FakeMt5([], 1.1021, 1.1022)
sg._mt5_exec = fx
check("pozitie inchisa manual / lipsa → nimic", sg._special_tp_step(sig(), "S1-U", "EURUSD", 1, df, 12, Log()) is None
      and not fx.sent)
check("fara TP (semnal fara tp) → nimic", sg._special_tp_step({**sig(), "tp": None}, "S1-T", "EURUSD", 1, df, 12, Log()) is None)
check("neactivat (triggered False) → nimic", sg._special_tp_step({**sig(), "triggered": False}, "S1-T", "EURUSD", 1, df, 12, Log()) is None)

print(f"\n{OK} OK, {FAIL} FAIL")
sys.exit(1 if FAIL else 0)
