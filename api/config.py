"""
Configuratie centrala API — cai, definitii sesiuni.
Citit de toate routerele, nu importa din live/ sau backtest.py direct.
"""

import os

ROOT     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
PID_FILE = os.path.join(DATA_DIR, "run_all.pid")

SESSIONS = [
    {
        "id":        "session1",
        "label":     "S1 — FX Long",
        "markets":   ["EURUSD", "GBPUSD", "EURJPY"],
        "direction": "LONG",
        "tf":        "M15",
        "hours":     "10–18h UTC",
        "validated": True,
        "execute":   True,
        "capital_pct": 12.5,
    },
    {
        "id":        "session2",
        "label":     "S2 — FX Both",
        "markets":   ["EURUSD", "GBPUSD", "EURJPY", "USDJPY", "AUDJPY", "NZDJPY"],
        "direction": "BOTH",
        "tf":        "M15",
        "hours":     "02–18h UTC",
        "validated": True,
        "execute":   True,
        "capital_pct": 12.5,
    },
    {
        "id":        "session3",
        "label":     "S3 — BTC",
        "markets":   ["BTCUSD"],
        "direction": "BOTH",
        "tf":        "M15",
        "hours":     "00–09h + 15–18h UTC",
        "validated": True,
        "execute":   True,
        "capital_pct": 62.5,
    },
    {
        "id":        "session4",
        "label":     "S4 — GER40 + US30",
        "markets":   ["GER40", "US30"],
        "direction": "LONG",
        "tf":        "M15",
        "hours":     "09–21h UTC",
        "validated": False,
        "execute":   True,
        "capital_pct": 12.5,
    },
    {
        "id":        "session5",
        "label":     "S5 — GER40 + USDCHF H1",
        "markets":   ["GER40", "USDCHF"],
        "direction": "BOTH",
        "tf":        "H1",
        "hours":     "07–17h UTC",
        "validated": False,
        "execute":   True,
        "capital_pct": 0,
    },
    {
        "id":        "session6",
        "label":     "S6 — US30 Long",
        "markets":   ["US30"],
        "direction": "LONG",
        "tf":        "M15",
        "hours":     "13–21h UTC",
        "validated": False,
        "execute":   True,
        "capital_pct": 12.5,
    },
]

SESSION_MAP = {s["id"]: s for s in SESSIONS}
