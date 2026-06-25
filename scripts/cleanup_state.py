"""
Curata state.pkl corupte si adauga outcomes "expirat" pentru semnale orfane.
Rulat DUPA oprirea botului (python scripts/cleanup_state.py).
"""

import pickle, glob, os, pandas as pd
from datetime import datetime

DATA_DIR = "data/live_signals"

# ── 1. Sterge intrari goale {symbol: {}} din state.pkl ─────────────────────────

ACTIVE_SESSIONS_WITH_MT5 = {
    # session: {simbol_valid_in_state}  — NU sterge acestea
    "session18": {"NZDJPY"},
    "session5":  {"USDCHF"},
    "session7":  {"XRPUSD"},
    "session20": {"XAUUSD"},
}

print("=== 1. Curatare state.pkl ===")
for pkl_path in sorted(glob.glob(f"{DATA_DIR}/*/state.pkl")):
    sess = os.path.basename(os.path.dirname(pkl_path))
    with open(pkl_path, "rb") as f:
        state = pickle.load(f)

    pending = state.get("pending", {})
    valid_keys = ACTIVE_SESSIONS_WITH_MT5.get(sess, set())
    to_remove = [k for k, v in pending.items() if isinstance(v, dict) and not v and k not in valid_keys]

    if to_remove:
        for k in to_remove:
            del pending[k]
        with open(pkl_path, "wb") as f:
            pickle.dump(state, f)
        print(f"  {sess}: sterse {to_remove}")
    else:
        print(f"  {sess}: ok (nimic de sters)")

# ── 2. Adauga outcome "expirat" pentru semnale orfane ──────────────────────────

# Semnale care sunt REALE si inca active (NU primesc "expirat")
ACTIVE_SIGNALS = {
    "S18-NZDJPY-H1-SIG0001",  # NZDJPY open in MT5
    "S5-H1D1-SIG0011",         # USDCHF open in MT5
    "S7-XRP-SIG0004",          # XRPUSD open in MT5
    "S7-XRP-IB0009",           # XRPUSD pending order in MT5
    "S20-XAUUSD-SIG0003",      # XAUUSD obs mode (execute_trades=False)
}

OUTCOMES_COLS = [
    "signal_id", "time_check", "symbol", "direction", "status",
    "entry", "sl", "tp", "r_ratio",
    "triggered_at", "exit_price", "exit_time", "result_r", "pnl_usd",
]

now_str = datetime.now().isoformat(timespec="seconds")

print()
print("=== 2. Adaugare outcome 'expirat' pentru semnale orfane ===")
for sig_path in sorted(glob.glob(f"{DATA_DIR}/session*/signals.csv")):
    sess = os.path.basename(os.path.dirname(sig_path))
    out_path = sig_path.replace("signals.csv", "outcomes.csv")

    df_s = pd.read_csv(sig_path)
    df_o = pd.read_csv(out_path) if os.path.exists(out_path) else pd.DataFrame(columns=OUTCOMES_COLS)

    orphans = set(df_s["signal_id"]) - set(df_o["signal_id"]) - ACTIVE_SIGNALS
    if not orphans:
        continue

    new_rows = []
    for sig_id in orphans:
        row = df_s[df_s["signal_id"] == sig_id].iloc[0]
        new_rows.append({
            "signal_id":    sig_id,
            "time_check":   now_str,
            "symbol":       row.get("symbol", ""),
            "direction":    row.get("direction", ""),
            "status":       "expirat",
            "entry":        row.get("entry", ""),
            "sl":           row.get("sl", ""),
            "tp":           row.get("tp", ""),
            "r_ratio":      row.get("r_ratio", ""),
            "triggered_at": "",
            "exit_price":   "",
            "exit_time":    "",
            "result_r":     0.0,
            "pnl_usd":      "",
        })
        print(f"  {sess}: {sig_id} → expirat")

    df_new = pd.DataFrame(new_rows, columns=OUTCOMES_COLS)
    df_o = pd.concat([df_o, df_new], ignore_index=True)
    df_o.to_csv(out_path, index=False)

print()
print("Done. Verifica Dashboard-ul — semnalele Pending false ar trebui sa dispara.")
