"""
QA: reziliența la probleme de conexiune MT5 (audit 2026-11-01). MT5 SIMULAT — fără terminal, ordine, Telegram.
  • terminal MT5 închis / repornit → IPC pierdut → reconectare automată (Custom: Mt5DataSource, Daily, Noisy)
  • terminal deschis dar deconectat de la broker → Daily / Noisy: stare de eroare vizibilă, nimic pe date înghețate
    python scripts/test_mt5_reconnect.py
"""
import os
import sys
import tempfile
from datetime import datetime, timezone
from types import SimpleNamespace

import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}  {detail}")


RATES = np.array([(1_790_000_000 + 900 * i, 1.1, 1.2, 1.0, 1.15, 10, 1, 0) for i in range(50)],
                 dtype=[("time", "i8"), ("open", "f8"), ("high", "f8"), ("low", "f8"), ("close", "f8"),
                        ("tick_volume", "i8"), ("spread", "i4"), ("real_volume", "i8")])


class Term:
    """Terminal simulat: alive (IPC), connected (broker); initialize() reface IPC-ul daca terminalul e pornit."""
    ACCOUNT_TRADE_MODE_DEMO = 0
    TIMEFRAME_M15, TIMEFRAME_M1, TIMEFRAME_M5, TIMEFRAME_M30, TIMEFRAME_H1, TIMEFRAME_D1 = 15, 1, 5, 30, 16385, 16408

    def __init__(self):
        self.running, self.ipc, self.broker, self.inits = True, False, True, 0

    def initialize(self, *a, **k):
        self.inits += 1
        self.ipc = self.running
        return self.running

    def shutdown(self):
        self.ipc = False

    def last_error(self):
        return (-10004, "No IPC connection") if not self.ipc else (1, "Success")

    def terminal_info(self):
        return SimpleNamespace(connected=self.broker, trade_allowed=True) if self.ipc else None

    def account_info(self):
        return SimpleNamespace(login=1, server="x", trade_mode=0, equity=100.0, currency="USD") if self.ipc else None

    def symbol_select(self, *a):
        return self.ipc

    def copy_rates_from_pos(self, *a):
        return RATES if self.ipc else None

    def symbol_info_tick(self, s):
        return SimpleNamespace(time=int(datetime.now(timezone.utc).timestamp()) + 7200, bid=1.1, ask=1.1001) if self.ipc else None

    def symbol_info(self, s):
        return SimpleNamespace(point=0.00001, digits=5, trade_tick_value=1.0, trade_tick_size=0.00001,
                               volume_min=0.01, volume_step=0.01, volume_max=100.0) if self.ipc else None

    def positions_get(self, **k):
        return []

    def orders_get(self, **k):
        return []


print("1. Custom Engine — Mt5DataSource")
from adapters import mt5_source as MS  # noqa: E402
T = Term()
_orig = MS.mt5
MS.mt5 = T
try:
    src = MS.Mt5DataSource(n_bars=50)
    df = src.load_bars("EURUSD", "M15")
    check("prima conectare + bare", len(df) == 50 and T.inits == 1)
    T.running, T.ipc = False, False          # terminalul se inchide
    try:
        src.load_bars("EURUSD", "M15")
        check("terminal inchis → eroare (bucla sesiunii reincearca)", False)
    except RuntimeError:
        check("terminal inchis → eroare (bucla sesiunii reincearca)", True)
    T.running = True                          # terminalul a repornit (IPC-ul vechi e mort)
    df = src.load_bars("EURUSD", "M15")
    check("terminal repornit → RECONECTARE automata + bare din nou", len(df) == 50 and T.inits >= 2, T.inits)
finally:
    MS.mt5 = _orig

print("2. Noisy Engine")
from noisy_engine import engine as NE  # noqa: E402
tmp = tempfile.mkdtemp()
for k in ("STATUS_FILE", "STATE_FILE", "CONTROL_FILE", "TRADES_FILE"):
    setattr(NE, k, os.path.join(tmp, "n_" + os.path.basename(getattr(NE, k))))
NE._notify = lambda c, t: None
T = Term()
eng = NE.NoisyEngine(T, news_fetch=lambda: [], guard=lambda s: (True, ""))
eng.connect()
check("conectat → iteratie normala", eng.iteration()["state"] != "error")
T.running, T.ipc = False, False
st = eng.iteration()
check("terminal inchis → stare Error cu motiv (nu date goale)", st["state"] == "error" and "IPC" in st["reason"], st.get("reason"))
T.running = True
st = eng.iteration()
check("terminal repornit → reconectat automat", st["state"] != "error" and T.ipc, st.get("reason"))
T.broker = False
st = eng.iteration()
check("deconectat de la broker → stare Error, iteratia sarita", st["state"] == "error" and "broker" in st["reason"], st.get("reason"))
T.broker = True
check("broker revenit → normal", eng.iteration()["state"] != "error")

print("3. Daily Engine")
from daily_engine import engine as DE  # noqa: E402
for k in ("STATUS_FILE", "STATE_FILE", "TRADES_FILE"):
    setattr(DE, k, os.path.join(tmp, "d_" + os.path.basename(getattr(DE, k))))
DE._notify = lambda c, t: None
T = Term()
de = DE.DailyEngine(T)
de.connect()
de.iteration()
T.running, T.ipc = False, False
st = de.iteration()
check("terminal inchis → executie oprita cu motiv", st["execution"]["active"] is False and "IPC" in st["execution"]["reason"])
T.running = True
st = de.iteration()
check("terminal repornit → reconectat, piete procesate din nou", T.ipc and isinstance(st.get("markets"), list) and st.get("markets"))
T.broker = False
st = de.iteration()
check("deconectat de la broker → iteratia sarita cu motiv", "broker" in st["execution"]["reason"])

print(f"\nREZULTAT: {PASS} PASS / {FAIL} FAIL")
sys.exit(1 if FAIL else 0)
