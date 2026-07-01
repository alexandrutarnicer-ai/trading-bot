"""
Configuratie centrala API — cai, definitii sesiuni.
Citit de toate routerele, nu importa din live/ sau backtest.py direct.

20 sesiuni individuale (una piata per sesiune) — scan complet 2026-06.
"""

import os

ROOT     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
PID_FILE = os.path.join(DATA_DIR, "run_all.pid")

SESSIONS = [
    {
        "id":          "session1",
        "label":       "S1 — EURUSD M15 LONG",
        "markets":     ["EURUSD"],
        "direction":   "LONG",
        "tf":          "M15+M30",
        "hours":       "0–24h",
        "validated":   True,
        "execute":     True,
        "capital_pct": 7.0,
        "score":       3.84,
    },
    {
        "id":          "session2",
        "label":       "S2 — AUDJPY M15 BOTH+BE",
        "markets":     ["AUDJPY"],
        "direction":   "BOTH",
        "tf":          "M15+M30",
        "hours":       "0–24h",
        "validated":   True,
        "execute":     True,
        "capital_pct": 7.0,
        "score":       2.05,
    },
    {
        "id":          "session3",
        "label":       "S3 — BTCUSD M15 BOTH+IB",
        "markets":     ["BTCUSD"],
        "direction":   "BOTH",
        "tf":          "M15+M30",
        "hours":       "00–09h + 15–18h UTC",
        "validated":   True,
        "execute":     True,
        "capital_pct": 37.0,
        "score":       None,
    },
    {
        "id":          "session4",
        "label":       "S4 — GER40 M15 LONG+Flag",
        "markets":     ["GER40"],
        "direction":   "LONG",
        "tf":          "M15+M30",
        "hours":       "09–17h UTC",
        "validated":   True,
        "execute":     False,
        "capital_pct": 50.0,
        "score":       3.31,
    },
    {
        "id":          "session5",
        "label":       "S5 — USDCHF H1 BOTH",
        "markets":     ["USDCHF"],
        "direction":   "BOTH",
        "tf":          "H1+D1",
        "hours":       "0–24h",
        "validated":   True,
        "execute":     True,
        "capital_pct": 8.0,
        "score":       2.37,
    },
    {
        "id":          "session6",
        "label":       "S6 — US30 M15 BOTH",
        "markets":     ["US30"],
        "direction":   "BOTH",
        "tf":          "M15+M30",
        "hours":       "15–22h UTC",
        "validated":   True,
        "execute":     False,
        "capital_pct": 57.0,
        "score":       2.71,
    },
    {
        "id":          "session7",
        "label":       "S7 — XRPUSD M15 BOTH+IB",
        "markets":     ["XRPUSD"],
        "direction":   "BOTH",
        "tf":          "M15+M30",
        "hours":       "0–24h",
        "validated":   True,
        "execute":     True,
        "capital_pct": 10.0,
        "score":       3.07,
    },
    {
        "id":          "session8",
        "label":       "S8 — EURCAD H1 LONG+Flag",
        "markets":     ["EURCAD"],
        "direction":   "LONG",
        "tf":          "H1+D1",
        "hours":       "0–24h",
        "validated":   True,
        "execute":     True,
        "capital_pct": 7.0,
        "score":       1.96,
    },
    {
        "id":          "session9",
        "label":       "S9 — USDJPY M15 LONG",
        "markets":     ["USDJPY"],
        "direction":   "LONG",
        "tf":          "M15+M30",
        "hours":       "0–24h",
        "validated":   True,
        "execute":     True,
        "capital_pct": 5.0,
        "score":       1.38,
    },
    {
        "id":          "session10",
        "label":       "S10 — GBPCAD H1 LONG+Flag",
        "markets":     ["GBPCAD"],
        "direction":   "LONG",
        "tf":          "H1+D1",
        "hours":       "0–24h",
        "validated":   True,
        "execute":     True,
        "capital_pct": 8.0,
        "score":       1.19,
    },
    {
        "id":          "session11",
        "label":       "S11 — USDCAD M15 LONG+IB",
        "markets":     ["USDCAD"],
        "direction":   "LONG",
        "tf":          "M15+M30",
        "hours":       "0–24h",
        "validated":   True,
        "execute":     True,
        "capital_pct": 6.0,
        "score":       1.07,
    },
    {
        "id":          "session12",
        "label":       "S12 — EURAUD H1 LONG",
        "markets":     ["EURAUD"],
        "direction":   "LONG",
        "tf":          "H1+D1",
        "hours":       "0–24h",
        "validated":   True,
        "execute":     True,
        "capital_pct": 8.0,
        "score":       1.06,
    },
    {
        "id":          "session13",
        "label":       "S13 — EURJPY M15 LONG",
        "markets":     ["EURJPY"],
        "direction":   "LONG",
        "tf":          "M15+M30",
        "hours":       "0–24h",
        "validated":   True,
        "execute":     True,
        "capital_pct": 6.0,
        "score":       0.74,
    },
    {
        "id":          "session14",
        "label":       "S14 — CHFJPY H1 LONG all",
        "markets":     ["CHFJPY"],
        "direction":   "LONG",
        "tf":          "H1+D1",
        "hours":       "0–24h",
        "validated":   True,
        "execute":     True,
        "capital_pct": 9.0,
        "score":       0.67,
    },
    {
        "id":          "session15",
        "label":       "S15 — GBPUSD M15 LONG",
        "markets":     ["GBPUSD"],
        "direction":   "LONG",
        "tf":          "M15+M30",
        "hours":       "0–24h",
        "validated":   True,
        "execute":     True,
        "capital_pct": 8.0,
        "score":       0.49,
    },
    {
        "id":          "session16",
        "label":       "S16 — GBPAUD H1 BOTH+BE",
        "markets":     ["GBPAUD"],
        "direction":   "BOTH",
        "tf":          "H1+D1",
        "hours":       "0–24h",
        "validated":   True,
        "execute":     True,
        "capital_pct": 9.0,
        "score":       0.35,
    },
    {
        "id":          "session17",
        "label":       "S17 — AUDCAD H1 LONG+IB",
        "markets":     ["AUDCAD"],
        "direction":   "LONG",
        "tf":          "H1+D1",
        "hours":       "0–24h",
        "validated":   True,
        "execute":     True,
        "capital_pct": 7.0,
        "score":       0.12,
    },
    {
        "id":          "session18",
        "label":       "S18 — NZDJPY H1 BOTH+IB",
        "markets":     ["NZDJPY"],
        "direction":   "BOTH",
        "tf":          "H1+D1",
        "hours":       "0–24h",
        "validated":   True,
        "execute":     True,
        "capital_pct": 7.0,
        "score":       0.01,
    },
    {
        "id":          "session19",
        "label":       "S19 — AUDNZD M15 BOTH",
        "markets":     ["AUDNZD"],
        "direction":   "BOTH",
        "tf":          "M15+M30",
        "hours":       "0–24h",
        "validated":   False,
        "execute":     True,
        "capital_pct": 5.0,
        "score":       None,
    },
    {
        "id":          "session20",
        "label":       "S20 — XAUUSD M15 BOTH",
        "markets":     ["XAUUSD"],
        "direction":   "BOTH",
        "tf":          "M15+M30",
        "hours":       "0–24h",
        "validated":   False,
        "execute":     True,
        "capital_pct": 10.0,
        "score":       None,
    },
]

SESSION_MAP = {s["id"]: s for s in SESSIONS}


def get_profile_execute_map() -> dict[str, bool]:
    """
    Returns {session_key: execute_trades} from the active profile.
    Falls back to static SESSIONS execute field when profile is unavailable.
    Call this at request time (not at import) to pick up profile changes made via UI.
    """
    import json  # local import — avoids circular issues at module load
    fallback = {s["id"]: s["execute"] for s in SESSIONS}
    try:
        active_file = os.path.join(DATA_DIR, "active_profile.json")
        profile_id  = "standard"
        if os.path.exists(active_file):
            with open(active_file, encoding="utf-8") as fh:
                profile_id = json.load(fh).get("id", "standard")
        pfile = os.path.join(DATA_DIR, "profiles", f"{profile_id}.json")
        if not os.path.exists(pfile):
            return fallback
        with open(pfile, encoding="utf-8") as fh:
            profile = json.load(fh)
        return {s["session_key"]: bool(s.get("execute_trades", True))
                for s in profile.get("sessions", [])}
    except Exception:
        return fallback
