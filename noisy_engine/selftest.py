"""
QA Noisy Engine — offline (MT5 simulat; partea de echivalenta foloseste MT5 doar CITIRE daca e pornit).
NU trimite Telegram, NU plaseaza ordine.
    python -m noisy_engine.selftest
"""
from __future__ import annotations

import copy
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from noisy_engine import config as C  # noqa: E402
from noisy_engine import strategy as S  # noqa: E402
from noisy_engine import engine as E  # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}  {detail}")


def raw(cfg):
    c = copy.deepcopy(cfg)
    c["strategy"].update(cooldown_bars=0, cooldown_after_sl_bars=0, max_flips_per_hour=0, trend_filter=False,
                         spread_max_mult=0, spread_max=0, min_atr_over_cost=0)
    for k in c["limits"]:
        c["limits"][k]["enabled"] = False
    return c


def make_bars(closes, start=datetime(2026, 11, 2, 9, 0), spread=0.001, wiggle=0.004):
    t = [start + timedelta(minutes=5 * i) for i in range(len(closes))]
    c = np.asarray(closes, float)
    o = np.r_[c[0], c[:-1]]
    return pd.DataFrame({"t": t, "open": o, "high": np.maximum(o, c) + wiggle, "low": np.minimum(o, c) - wiggle,
                         "close": c, "spread": spread})


CFG = C.sanitize({})
DAY = date(2026, 11, 2)

print("1. Configurare")
check("implicit: USDJPY, shadow, fereastra 10-20 RO", CFG["symbol"] == "USDJPY" and CFG["mode"] == "shadow"
      and CFG["window"] == {"start": "10:00", "end": "20:00", "days": [0, 1, 2, 3, 4]})
check("moduri: shadow (implicit) / execute; mod necunoscut → shadow",
      CFG["mode"] == "shadow" and C.sanitize({"mode": "execute"})["mode"] == "execute"
      and C.sanitize({"mode": "live!"})["mode"] == "shadow")
check("M1 implicit; la oprire: inchide pozitiile (implicit)", CFG["timeframe"] == "M1" and CFG["on_stop"] == "close")
check("limite optionale cu enabled/value", all(set(v) == {"enabled", "value"} for v in CFG["limits"].values()))
check("pragul bugetului nu poate depasi capitalul", C.sanitize({"budget": {"capital": 20, "min_remaining": 50}})["budget"]["min_remaining"] == 20)

print("2. Strategie: semnal, intrare la bara urmatoare, iesiri")
base = [150.0] * 40
drop = base + [149.80]                      # inchidere mult sub EMA → LONG
b = make_bars(drop + [149.82] + [150.0] * 3)
r = S.run_day(b, DAY, raw(CFG))
check("semnal LONG dupa caderea brusca", len(r["trades"]) >= 1 and r["trades"][0]["dir"] == "LONG", r["trades"][:1])
tr = r["trades"][0] if r["trades"] else {}
check("intrare la DESCHIDEREA barei urmatoare (fara lookahead)", tr.get("entry") == float(b.open[41]), (tr.get("entry"), b.open[41]))
check("tinta = revenirea la EMA → iesire TP", tr.get("reason") == "TP", tr.get("reason"))
r2 = S.run_day(make_bars(drop), DAY, raw(CFG))
check("semnal pe ultima bara inchisa → pending (asteapta bara urmatoare)", r2["pending"] and r2["pending"]["dir"] == "LONG" and not r2["trades"])
fall = make_bars(drop + [149.80, 149.60, 149.40, 149.20])
r3 = S.run_day(fall, DAY, raw(CFG))
check("continuarea caderii → SL", r3["trades"] and r3["trades"][0]["reason"] == "SL" and r3["trades"][0]["R"] < 0, r3["trades"][:1])
flat = make_bars(drop + [149.80] * 30, wiggle=0.0001)
r4 = S.run_day(flat, DAY, raw(CFG))
check("fara SL/TP in 20 de bare → iesire la timp", r4["trades"] and r4["trades"][0]["reason"] == "timp", r4["trades"][:1])
check("cost inclus: R net < R brut", tr and tr["R"] < tr["gross_R"])
check("spread_floor: spread-ul barei 0 → costul tot >= spread-ul real",
      S.run_day(make_bars(drop + [149.82] + [150.0] * 3, spread=0.0), DAY, raw(CFG))["trades"][0]["cost"] >= 0.001)

print("3. Filtre si limite")
c = raw(CFG)
c["window"]["start"], c["window"]["end"] = "18:00", "20:00"
check("in afara ferestrei → fara intrari", not S.run_day(b, DAY, c)["trades"])
blocks = [(datetime(2026, 11, 2, 12, 0), datetime(2026, 11, 2, 13, 0))]
check("in fereastra de stiri → fara intrari", not S.run_day(b, DAY, raw(CFG), news_blocks=blocks)["trades"])
vt = b.t[40].isoformat()
check("semnal respins global (vetoed) → acel semnal nu devine trade",
      all(x["signal_t"] != vt for x in S.run_day(b, DAY, raw(CFG), vetoed={vt})["trades"])
      and any(x["signal_t"] == vt for x in S.run_day(b, DAY, raw(CFG))["trades"]))
check("blocare externa (buget / pauza) → fara intrari", not S.run_day(b, DAY, raw(CFG), no_new_entries=True)["trades"])
# zi cu multe semnale pierzatoare
seq = base[:]
for _ in range(8):
    seq += [seq[-1] - 0.25, seq[-1] - 0.45, seq[-1] - 0.65, seq[-1] - 0.85] + [seq[-1] - 0.85] * 2
many = make_bars(seq)
c = raw(CFG)
c["limits"]["max_consec_losses"] = {"enabled": True, "value": 2}
r5 = S.run_day(many, DAY, c)
check("serie de 2 pierderi → blocat restul zilei", r5["lock"] == "loss_streak" and r5["counters"]["consec_losses"] == 2, (r5["lock"], r5["counters"]))
c = raw(CFG)
c["limits"]["max_trades_day"] = {"enabled": True, "value": 1}
check("max 1 trade / zi", len(S.run_day(many, DAY, c)["trades"]) == 1)
check("limite oprite → mai multe trade-uri", len(S.run_day(many, DAY, raw(CFG))["trades"]) > 2)
c = raw(CFG)
c["strategy"]["cooldown_bars"] = c["strategy"]["cooldown_after_sl_bars"] = 50
check("cooldown dupa iesire → urmatoarea intrare amanata", len(S.run_day(many, DAY, c)["trades"]) < len(S.run_day(many, DAY, raw(CFG))["trades"]))

print("3b. Break-Even IDENTIC cu Custom Engine (engine/simulator.py) + R:R configurabil + profile M1/M5")
from engine.simulator import simulate_trade  # noqa: E402
rng = np.random.default_rng(3)
mism = 0
checked = 0
for trial in range(400):
    n = 60
    steps = rng.normal(0, 0.03, n).cumsum()
    c_ = 150 + steps
    o_ = np.r_[150.0, c_[:-1]]
    h_ = np.maximum(o_, c_) + rng.uniform(0, 0.03, n)
    l_ = np.minimum(o_, c_) - rng.uniform(0, 0.03, n)
    bars_ = pd.DataFrame({"t": [datetime(2026, 11, 2, 11, 0) + timedelta(minutes=i) for i in range(n)],
                          "open": o_, "high": h_, "low": l_, "close": c_, "spread": 0.0})
    d = 1 if trial % 2 == 0 else -1
    entry, risk, tpd = o_[1], 0.05, 0.08 + 0.04 * (trial % 3)
    sl, tp = entry - d * risk, entry + d * tpd
    p2 = {"enabled": True, "trigger_pct": 80, "lock1_pct": 30, "phase2_enabled": trial % 4 != 3,
          "phase2_zone_pct": 40, "lock2_pct": 50}
    ref = simulate_trade(bars_[["open", "high", "low", "close"]].assign(time=bars_.t), 1,
                         {"dir": d, "entry": entry, "sl": sl, "tp": tp, "lots": 1, "R": 1, "risk_usd": 1, "time": None},
                         0.0, 0.01, 1.0, 0.0, "USDJPY",
                         be_cfg={"enabled": True, "trigger_pct": 80, "lock1_pct": 30, "lock2_pct": 50,
                                 "phase2_zone_pct": 40, "phase2_enabled": p2["phase2_enabled"]})
    if ref["outcome"] == "timeout":
        continue
    # aceeasi pozitie prin noisy run_day (semnal fortat pe bara 0, intrare la open[1])
    cfg_be = raw(CFG)
    cfg_be["break_even"] = p2
    cfg_be["strategy"]["time_stop_bars"] = 500
    pos_ = {"id": "x", "dir": d, "sig_i": 0, "entry_i": 1, "signal_t": "", "entry_t": "", "entry": entry, "sl": sl, "sl0": sl,
            "tp": tp, "risk": risk, "cost": 0.0,
            "be_lv": {k: entry + d * tpd * p2[f] / 100.0 for k, f in (("trig", "trigger_pct"), ("lock1", "lock1_pct"),
                                                                      ("zone", "phase2_zone_pct"), ("lock2", "lock2_pct"))},
            "be_phase": 0}
    out = S.simulate_exit(bars_, pos_, cfg_be)
    checked += 1
    exp = {"loss": "SL", "win": "TP", "be_lock": "be_lock", "be_lock2": "be_lock2"}[ref["outcome"]]
    ref_px = {"SL": sl, "TP": tp}.get(exp)
    if out["reason"] != exp or out["bar"] != ref["exit_j"] or (ref_px is not None and abs(out["exit"] - ref_px) > 1e-9):
        mism += 1
check("Break-Even Noisy = Custom pe 400 trasee aleatoare (aceeasi iesire, aceeasi bara)", checked > 100 and mism == 0, (checked, mism))
c_rr = raw(CFG)
c_rr["strategy"]["tp_rr"] = 2.0
tr_rr = S.run_day(b, DAY, c_rr)["trades"]
check("R:R fix 2R → tinta = 2 × riscul", tr_rr and abs(abs(tr_rr[0]["tp"] - tr_rr[0]["entry"]) / tr_rr[0]["risk"] - 2.0) < 1e-6,
      tr_rr[:1])
m1, m5 = C.sanitize({"timeframe": "M1"}), C.sanitize({"timeframe": "M5"})
check("comutare M1 ⇄ M5: limitele si filtrul cost/ATR ale profilului", m1["limits"]["max_trades_day"]["value"] == 60
      and m5["limits"]["max_trades_day"]["value"] == 6 and m1["strategy"]["min_atr_over_cost"] == 5
      and m5["strategy"]["min_atr_over_cost"] == 15)
check("Break-Even OPRIT implicit, parametrii Custom (80/30/40/50, faza 2)", CFG["break_even"] == {
    "enabled": False, "trigger_pct": 80, "lock1_pct": 30, "phase2_enabled": True, "phase2_zone_pct": 40, "lock2_pct": 50})
fb = E.friday_block(datetime(2026, 10, 30, 19, 0), {"friday_close": {"enabled": True, "hour": 18}})
check("inchiderea de vineri (Setari Globale) → interval blocat in ora RO",
      fb is not None and fb[0].weekday() == 4 and not S.run_day(make_bars(drop + [149.82] + [150.0] * 3, start=datetime(2026, 10, 30, 18, 0)),
                                                                  date(2026, 10, 30), raw(CFG), news_blocks=[fb])["trades"])

print("4. Determinism / fara lookahead")
full = S.run_day(many, DAY, CFG)
part = S.run_day(many.iloc[:120], DAY, CFG)
check("recalcularea e identica (restart-safe)", S.run_day(many, DAY, CFG)["trades"] == full["trades"])
done = [t for t in part["trades"]]
check("barele viitoare nu schimba trade-urile deja inchise", full["trades"][:len(done)] == done)

print("5. Engine cu MT5 SIMULAT (shadow)")
tmp = tempfile.mkdtemp()
for k in ("STATUS_FILE", "STATE_FILE", "CONTROL_FILE", "TRADES_FILE"):
    setattr(E, k, os.path.join(tmp, os.path.basename(getattr(E, k))))
E._notify = lambda cfg, text: None                      # niciun Telegram real
srv = 3 * 3600
now = datetime(2026, 11, 2, 14, 0, tzinfo=timezone.utc)   # 16:00 RO
seq_t = [now - timedelta(minutes=5 * (len(drop) + 6 - i)) for i in range(len(drop) + 6)]
closes = drop + [149.82] + [150.0] * 5
o = np.r_[closes[0], closes[:-1]]
rates = np.array([(int(t.timestamp()) + srv, o[i], max(o[i], closes[i]) + .004, min(o[i], closes[i]) - .004, closes[i], 10, 0, 0)
                  for i, t in enumerate(seq_t)],
                 dtype=[("time", "i8"), ("open", "f8"), ("high", "f8"), ("low", "f8"), ("close", "f8"),
                        ("tick_volume", "i8"), ("spread", "i4"), ("real_volume", "i8")])


class FakeMT5:
    TIMEFRAME_M5 = 5
    TIMEFRAME_M1 = 1

    def __init__(self):
        self.sent = []

    def initialize(self):
        return True

    def account_info(self):
        return SimpleNamespace(login=1, server="x", trade_mode=2, equity=206.0, currency="USD")

    def symbol_select(self, *a):
        return True

    def symbol_info_tick(self, s):
        return SimpleNamespace(time=int(now.timestamp()) + srv, bid=150.0, ask=150.001)

    def symbol_info(self, s):
        return SimpleNamespace(point=0.001, trade_tick_value=0.66, trade_tick_size=0.001, volume_min=0.01,
                               volume_step=0.01, volume_max=100.0)

    def copy_rates_from_pos(self, *a):
        return rates

    def order_send(self, *a, **k):                         # NU trebuie apelat niciodata
        self.sent.append(a)


fm = FakeMT5()
cfgfile = os.path.join(tmp, "config.json")
C.CFG_PATH = cfgfile
C.save_config(raw(CFG))
eng = E.NoisyEngine(fm, news_fetch=lambda: [], guard=lambda s: (True, ""))
st = eng.iteration(now)
check("iteratie fara erori, stare valida", st.get("state") in E.STATES, st.get("state"))
check("trade virtual inchis → trades.jsonl", len(E.load_trades()) >= 1, E.load_trades())
check("P&L virtual in $ din lotul minim", E.load_trades() and E.load_trades()[0]["lots"] == 0.01
      and E.load_trades()[0]["pnl_money"] is not None)
eng.iteration(now)
check("re-iteratia NU dubleaza trade-ul (restart-safe)", len(E.load_trades()) == len({t["id"] for t in E.load_trades()}))
check("ZERO ordine trimise in shadow", fm.sent == [])
# buget: prag sub P&L → lock
with open(E.TRADES_FILE, "a", encoding="utf-8") as f:            # o pierdere virtuala de 5$
    f.write(json.dumps({"id": "x-loss", "day": "2026-11-02", "exit_t": "2026-11-02T15:00:00", "R": -1.0,
                        "gross_R": -0.98, "pnl_money": -5.0, "bars": 3}) + "\n")
c = raw(CFG)
c["budget"] = {"capital": 40.0, "min_remaining": 38.0}
C.save_config(c)
st = eng.iteration(now)
check("bugetul atins → Stopped – Budget Limit", st["state"] == "budget_locked" and st["state_label"] == "Stopped – Budget Limit", st["state"])
eng.state["budget_lock"] = None
_write = E._write_json
_write(E.CONTROL_FILE, {"paused": True})
C.save_config(raw(CFG))
check("pauza din UI → Paused", eng.iteration(now)["state"] == "paused")
_write(E.CONTROL_FILE, {"paused": False})
shutil.rmtree(tmp, ignore_errors=True)

print("5b. Spread: unitati, auto / manual, maxim, diagnoza respingerilor (incident 2.11)")
info = C.resolve_spread(C.sanitize({}), 0.001, 9.0, 3)
check("USDJPY: 9 points = 0,009 pret = 0,9 pips (1 pip = 10 points)", info["typical_points"] == 9.0
      and abs(info["typical_price"] - 0.009) < 1e-12 and info["typical_pips"] == 0.9 and info["pip_points"] == 10, info)
check("maxim auto = 1,5 × tipic = 13,5 points", info["max_points"] == 13.5 and info["max_source"].startswith("auto"), info)
cm = C.sanitize({"spread": {"mode": "manual", "manual_points": 12, "max_mode": "manual", "max_points": 20}})
im = C.resolve_spread(cm, 0.001, 9.0, 3)
check("manual: valoarea userului (12) castiga peste auto (9); maxim manual 20 points",
      im["typical_points"] == 12 and im["source"] == "manual" and abs(cm["strategy"]["spread_max"] - 0.020) < 1e-12, im)
leg = C.sanitize({"strategy": {"spread_floor": 0.01, "spread_max_mult": 1.0}})
il = C.resolve_spread(leg, 0.001, 9.0, 3)
check("config VECHI (spread_floor 0,01 + 1,0×) → manual 10 points, maxim 10 points (comportament identic)",
      il["typical_points"] == 10.0 and il["max_points"] == 10.0 and leg["spread"]["mode"] == "manual", il)
check("indice (digits 2): 1 pip = 1 point", C.resolve_spread(C.sanitize({}), 0.01, 50, 2)["pip_points"] == 1)
check("fara point (simbol necunoscut) → valorile de rezerva, fara exceptie",
      "rezerva" in C.resolve_spread(C.sanitize({}), None, None, None)["source"].replace("ă", "a"))
# incidentul: tipic 10 points pe M1 → filtrul cost/ATR respinge TOT, acum vizibil cu cifrele
bars_m1 = make_bars(drop + [149.82] + [150.0] * 3, spread=0.001)
cfg_inc = raw(CFG)
cfg_inc["strategy"]["min_atr_over_cost"] = 5.0
cfg_inc["strategy"]["spread_floor"] = 0.010
r_inc = S.run_day(bars_m1, DAY, cfg_inc)
check("spread tipic 0,010 + cost/ATR ≥ 5 → niciun trade (cauza „nu mai plaseaza trade-uri”)", not r_inc["trades"], r_inc["trades"][:1])
rj = [x for x in r_inc["rejected"] if x["reason"] == "cost_atr"]
check("… si respingerea e RAPORTATA: motiv cost_atr + ATR / cost / prag in detaliu",
      rj and "ATR" in rj[0]["detail"] and "cost" in rj[0]["detail"] and r_inc["reject_counts"].get("cost_atr"), r_inc["rejected"][:2])
cfg_ok = raw(CFG)
cfg_ok["strategy"]["min_atr_over_cost"] = 5.0
check("acelasi semnal cu spread 0,001 → trade (filtrul nu blocheaza cand costul e mic)", S.run_day(bars_m1, DAY, cfg_ok)["trades"])
cfg_sp = raw(CFG)
cfg_sp["strategy"]["spread_floor"], cfg_sp["strategy"]["spread_max"] = 0.010, 0.005
r_sp = S.run_day(bars_m1, DAY, cfg_sp)
check("spread tipic peste maxim → respins cu motivul 'spread'", not r_sp["trades"] and r_sp["reject_counts"].get("spread"), r_sp["reject_counts"])
check("diagnoza nu schimba trade-urile (aceleasi cu / fara filtre care nu se declanseaza)",
      [t["id"] for t in S.run_day(b, DAY, raw(CFG))["trades"]] == [t["id"] for t in r["trades"]])

tmp = tempfile.mkdtemp()
for k in ("STATUS_FILE", "STATE_FILE", "CONTROL_FILE", "TRADES_FILE"):
    setattr(E, k, os.path.join(tmp, os.path.basename(getattr(E, k))))
C.CFG_PATH = os.path.join(tmp, "config.json")


class SpreadMT5(FakeMT5):
    def __init__(self, spread):
        super().__init__()
        self.spread = spread

    def symbol_info_tick(self, s):
        return SimpleNamespace(time=int(now.timestamp()) + srv, bid=150.0, ask=150.0 + self.spread)

    def symbol_info(self, s):
        return SimpleNamespace(point=0.001, digits=3, trade_tick_value=0.66, trade_tick_size=0.001, volume_min=0.01,
                               volume_step=0.01, volume_max=100.0)


rates_pend = rates[:len(drop)]                         # ultima bara inchisa = semnalul → pending
fm2 = SpreadMT5(0.020)                                  # spread live 20 points
fm2.copy_rates_from_pos = lambda *a: rates_pend
_c2 = {**raw(CFG), "spread": {"mode": "manual", "manual_points": 9, "max_mode": "manual", "max_points": 15}}
_c2["tf_profiles"] = copy.deepcopy(CFG["tf_profiles"])
_c2["tf_profiles"]["M1"]["min_atr_over_cost"] = 0          # izoleaza verificarea spread-ului LIVE
C.save_config(_c2)
eng2 = E.NoisyEngine(fm2, news_fetch=lambda: [], guard=lambda s: (True, ""))
st2 = eng2.iteration(now)
check("status.spread: tipic manual 9 points, maxim 15 points, live 20 points", st2["spread"]["typical_points"] == 9
      and st2["spread"]["max_points"] == 15 and st2["spread"]["live_points"] == 20.0, st2.get("spread"))
check("spread LIVE peste maxim → semnal respins, motivul in points (nu 'blocat global')",
      "SPREAD live" in (st2.get("reason") or "") and "20.0 points" in st2["reason"] and "15.0 points" in st2["reason"], st2.get("reason"))
logtxt = "\n".join(eng2.state["events"])
check("respingerea are cheie de eveniment unica (o singura notificare)", any(k.startswith("veto-") for k in eng2.state["events"]))
# auto: inghetat pe zi la prima iteratie din fereastra; repornirea foloseste aceeasi valoare
os.remove(E.STATE_FILE)
fm3 = SpreadMT5(0.009)
fm3.copy_rates_from_pos = lambda *a: rates
C.save_config(raw(CFG))
eng3 = E.NoisyEngine(fm3, news_fetch=lambda: [], guard=lambda s: (True, ""))
s3 = eng3.iteration(now)
ref = eng3.state.get("spread_ref")
check("auto: spread tipic = tick-ul live (9 points), inghetat pentru azi", ref and ref["points"] == 9.0 and s3["spread"]["source"].startswith("auto"), ref)
fm3.spread = 0.030                                      # spread-ul se largeste in timpul zilei
eng3b = E.NoisyEngine(fm3, news_fetch=lambda: [], guard=lambda s: (True, ""))   # „restart”
s3b = eng3b.iteration(now)
check("restart / spread largit in timpul zilei → tipicul de azi ramane 9 (recalcularea zilei identica)",
      s3b["spread"]["typical_points"] == 9.0, s3b["spread"])
shutil.rmtree(tmp, ignore_errors=True)

print("6. Siguranta codului")
src = "".join(open(os.path.join(ROOT, "noisy_engine", f), encoding="utf-8").read()
              for f in os.listdir(os.path.join(ROOT, "noisy_engine")) if f.endswith(".py") and f != "selftest.py")
srcs = {f: open(os.path.join(ROOT, "noisy_engine", f), encoding="utf-8").read()
        for f in os.listdir(os.path.join(ROOT, "noisy_engine")) if f.endswith(".py") and f != "selftest.py"}
check("order_send DOAR in executor.py", [f for f, s in srcs.items() if re.search(r"\.order_send\s*\(", s)] == ["executor.py"],
      [f for f, s in srcs.items() if re.search(r"\.order_send\s*\(", s)])

print("6b. EXECUTIE cu MT5 SIMULAT (demo / real nedeblocat / stop de timp / buget)")
tmp = tempfile.mkdtemp()
for k in ("STATUS_FILE", "STATE_FILE", "CONTROL_FILE", "TRADES_FILE"):
    setattr(E, k, os.path.join(tmp, os.path.basename(getattr(E, k))))
C.CFG_PATH = os.path.join(tmp, "config.json")
from noisy_engine import executor as X  # noqa: E402


class ExecMT5(FakeMT5):
    TRADE_ACTION_DEAL, ORDER_TYPE_BUY, ORDER_TYPE_SELL, ORDER_TIME_GTC, TRADE_ACTION_SLTP = 1, 0, 1, 0, 6
    TRADE_RETCODE_DONE, POSITION_TYPE_BUY = 10009, 0

    def __init__(self, demo=True, tick_time=None):
        super().__init__()
        self.demo, self.positions, self.deals = demo, [], []
        self.tick_time = tick_time or int(now.timestamp()) + srv

    def account_info(self):
        return SimpleNamespace(login=1, server="x", trade_mode=0 if self.demo else 2, equity=206.0, currency="USD")

    def symbol_info(self, s):
        return SimpleNamespace(point=0.001, digits=3, trade_tick_value=0.66, trade_tick_size=0.001, volume_min=0.01,
                               volume_step=0.01, volume_max=100.0, filling_mode=2)

    def symbol_info_tick(self, s):
        return SimpleNamespace(time=self.tick_time, bid=150.0, ask=150.001)

    def positions_get(self, **kw):
        return list(self.positions)

    def history_deals_get(self, a, b):
        return list(self.deals)

    def order_send(self, req):
        self.sent.append(req)
        if req.get("action") == self.TRADE_ACTION_SLTP:
            for p_ in self.positions:
                if p_.ticket == req["position"]:
                    p_.sl = req["sl"]
            return SimpleNamespace(retcode=10009, comment="done")
        if "position" in req:
            self.positions = [p for p in self.positions if p.ticket != req["position"]]
        else:
            self.positions.append(SimpleNamespace(ticket=100 + len(self.sent), magic=req["magic"], symbol=req["symbol"],
                                                  type=req["type"], volume=req["volume"], price_open=req["price"],
                                                  sl=req["sl"], tp=req["tp"], profit=0.0, swap=0.0, time=self.tick_time,
                                                  comment=req["comment"]))
        return SimpleNamespace(retcode=10009, comment="done")


# semnal pe ULTIMA bara inchisa → pending → ordin real la deschiderea barei curente
seq_p = [now - timedelta(minutes=(len(drop) - i)) for i in range(len(drop))]
c_p = list(drop)                                    # semnalul cade pe ultima bara INCHISA
o_p = np.r_[c_p[0], c_p[:-1]]
rates_p = np.array([(int(t.timestamp()) + srv, o_p[i], max(o_p[i], c_p[i]) + .004, min(o_p[i], c_p[i]) - .004, c_p[i], 10, 0, 0)
                    for i, t in enumerate(seq_p)], dtype=rates.dtype)
ExecMT5.copy_rates_from_pos = lambda self, *a: rates_p
exe = raw(CFG)
exe["mode"] = "execute"
C.save_config(exe)

m_sh = ExecMT5(demo=True)
C.save_config({**raw(CFG), "mode": "shadow"})
E.NoisyEngine(m_sh, news_fetch=lambda: [], guard=lambda s: (True, "")).iteration(now)
check("SHADOW (chiar pe demo) → zero ordine", m_sh.sent == [])

C.save_config(exe)
os.remove(E.STATE_FILE) if os.path.exists(E.STATE_FILE) else None
m_real = ExecMT5(demo=False)
X_live = E.NoisyEngine(m_real, news_fetch=lambda: [], guard=lambda s: (True, ""))
import live_guard as LG  # noqa: E402
_la = LG.live_allowed
LG.live_allowed = lambda comp: False
st_r = X_live.iteration(now)
check("cont REAL nedeblocat → zero ordine + motiv vizibil", m_real.sent == [] and "nedeblocat" in st_r["execution"]["reason"],
      (m_real.sent, st_r.get("execution")))
os.remove(E.STATE_FILE) if os.path.exists(E.STATE_FILE) else None
LG.live_allowed = lambda comp: comp == "noisy_engine"
m_real2 = ExecMT5(demo=False)
E.NoisyEngine(m_real2, news_fetch=lambda: [], guard=lambda s: (True, "")).iteration(now)
check("cont REAL deblocat (noisy_engine) → executa", len(m_real2.sent) == 1, m_real2.sent)
LG.live_allowed = _la

os.remove(E.STATE_FILE) if os.path.exists(E.STATE_FILE) else None
m = ExecMT5(demo=True)
eng_x = E.NoisyEngine(m, news_fetch=lambda: [], guard=lambda s: (True, ""))
st_x = eng_x.iteration(now)
req = m.sent[0] if m.sent else {}
check("DEMO + semnal nou → ordin la piata cu SL + tinta, magic Noisy", len(m.sent) == 1 and req.get("magic") == C.MAGIC
      and req.get("sl") and req.get("tp") and req["type"] == m.ORDER_TYPE_BUY and req["volume"] == 0.01, req)
check("comment N-<SIMBOL>-<HHMM> (≤16 caractere)", str(req.get("comment", "")).startswith("N-USDJPY-") and len(req["comment"]) <= 16)
check("status: executie activa + pozitia reala vizibila", st_x["execution"]["active"] and len(st_x["real_positions"]) == 1)
eng_x.iteration(now)
check("acelasi semnal NU e plasat de doua ori", len(m.sent) == 1, len(m.sent))
m.tick_time += (exe["strategy"]["time_stop_bars"] + 2) * 60
eng_x.iteration(now)
check("stop de timp → pozitia reala inchisa", len(m.sent) == 2 and "position" in m.sent[1] and not m.positions, m.sent)
# buget din MT5: pierdere reala → BUDGET LIMIT → inchide pozitiile (on_stop = close)
m.positions.append(SimpleNamespace(ticket=999, magic=C.MAGIC, symbol="USDJPY", type=0, volume=0.01, price_open=150.0,
                                   sl=149.9, tp=150.1, profit=-1.0, swap=0.0, time=m.tick_time, comment="N-USDJPY-x"))
m.deals = [SimpleNamespace(magic=C.MAGIC, profit=-12.0, commission=0.0, swap=0.0, fee=0.0),
           SimpleNamespace(magic=770015, profit=-500.0, commission=0.0, swap=0.0, fee=0.0)]
st_b = eng_x.iteration(now)
check("buget din MT5 = doar deal-urile Noisy (nu AI) + flotant", st_b["budget"]["source"] == "mt5"
      and st_b["budget"]["realized"] == -12.0 and st_b["budget"]["floating"] == -1.0, st_b["budget"])
check("BUDGET LIMIT in executie → pozitiile Noisy inchise", st_b["state"] == "budget_locked" and not m.positions, (st_b["state"], m.positions))
# break-even pe pozitia REALA: faza virtuala ≥ 2 → SL real mutat la lock1% din tinta, o singura data
eng_be = E.NoisyEngine(m, news_fetch=lambda: [], guard=lambda s: (True, ""))
m.positions = [SimpleNamespace(ticket=555, magic=C.MAGIC, symbol="USDJPY", type=0, volume=0.01, price_open=150.0,
                               sl=149.95, tp=150.10, profit=0.2, swap=0.0, time=m.tick_time, comment=X.tag("USDJPY", "2026-11-02T15:40:00"))]
cfg_x = C.load_config()
cfg_x["break_even"]["enabled"] = True
eng_be.cfg = cfg_x
n0 = len(m.sent)
eng_be._execute("USDJPY", None, {"open": {"signal_t": "2026-11-02T15:40:00", "be_phase": 2}}, False, 1)
sltp = [r for r in m.sent[n0:] if r.get("action") == m.TRADE_ACTION_SLTP]
check("break-even real: SL mutat la intrare + 30% din tinta (150.030), tinta neschimbata",
      len(sltp) == 1 and abs(sltp[0]["sl"] - 150.03) < 1e-9 and sltp[0]["tp"] == 150.10 and abs(m.positions[0].sl - 150.03) < 1e-9, sltp)
eng_be._execute("USDJPY", None, {"open": {"signal_t": "2026-11-02T15:40:00", "be_phase": 2}}, False, 1)
check("acelasi break-even NU e retrimis", len([r for r in m.sent[n0:] if r.get("action") == m.TRADE_ACTION_SLTP]) == 1)
eng_be._execute("USDJPY", None, {"open": {"signal_t": "2026-11-02T15:40:00", "be_phase": 4}}, False, 1)
check("faza 2 (break-even 2): SL → 50% din tinta", abs(m.positions[0].sl - 150.05) < 1e-9, m.positions[0].sl)
m.positions = []
cfg_x["break_even"]["enabled"] = False
cfg_x["strategy"]["tp_rr"] = 2.0
eng_be.cfg = cfg_x
n0 = len(m.sent)
eng_be._execute("USDJPY", {"dir": "LONG", "signal_t": "2026-11-02T16:00:00", "close": 149.9, "ema": 150.0, "atr": 0.02}, {}, False, 1)
req2 = m.sent[n0] if len(m.sent) > n0 else {}
check("R:R fix in executie: tinta = intrare + 2 × riscul", req2 and abs((req2["tp"] - req2["price"]) / (req2["price"] - req2["sl"]) - 2.0) < 0.05, req2)
shutil.rmtree(tmp, ignore_errors=True)
from api import engine_lifecycle as L  # noqa: E402
check("Noisy e in lifecycle FARA autostart", "noisy" in L.ENGINES and L.ENGINES["noisy"].get("task") is None)

print("7. Echivalenta cu studiul (MT5 doar citire, sarit daca MT5 nu e pornit)")
try:
    import MetaTrader5 as mt5
    ok = mt5.initialize()
except Exception:
    ok = False
if not ok:
    print("  SKIP  MT5 indisponibil")
else:
    sys.path.insert(0, os.path.join(ROOT, "scripts", "research_noisy"))
    import noisy_backtest as B
    r = mt5.copy_rates_range("USDJPY", mt5.TIMEFRAME_M5, B.START, B.END)
    bars = E.rates_to_bars(r, None, mt5.symbol_info("USDJPY").point)
    tr = B.backtest(raw(C.sanitize({})), bars)
    x = np.array([t["R"] for t in tr])
    check("fara filtre: ~1320 trade-uri, +0,07R (studiul: 1324, +0,069R)", 1290 <= len(x) <= 1350 and 0.05 <= x.mean() <= 0.09,
          (len(x), round(float(x.mean()), 3)))

print(f"\nREZULTAT: {PASS} PASS / {FAIL} FAIL")
sys.exit(1 if FAIL else 0)
