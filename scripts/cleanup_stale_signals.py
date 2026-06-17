"""
Curata semnalele stale din sesiunile live:
1. Marcheaza ca 'expirat' semnalele din signals.csv care nu au outcome si sunt mai vechi de 2 ore
2. Curata state.pkl — sterge intrari 'pending' pentru simboluri unde ultimul semnal s-a rezolvat deja
"""

import pickle
import sys
import os
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

SIGNALS_DIR = Path("data/live_signals")
CUTOFF_HOURS = 2  # semnal mai vechi de 2 ore pe M15 (expire_bars=4 = 1h) → sigur expirat

def cleanup_session(session_dir: Path, dry_run: bool = False) -> dict:
    name = session_dir.name
    signals_csv  = session_dir / "signals.csv"
    outcomes_csv = session_dir / "outcomes.csv"
    state_pkl    = session_dir / "state.pkl"

    result = {"session": name, "orphaned_marked": 0, "pending_cleaned": 0, "errors": []}

    if not signals_csv.exists():
        return result

    try:
        signals = pd.read_csv(signals_csv)
    except Exception as e:
        result["errors"].append(f"signals.csv read error: {e}")
        return result

    if outcomes_csv.exists():
        try:
            outcomes = pd.read_csv(outcomes_csv)
            resolved_ids = set(outcomes["signal_id"].dropna())
        except Exception:
            outcomes = None
            resolved_ids = set()
    else:
        outcomes = None
        resolved_ids = set()

    # 1. Gaseste semnale fara outcome, mai vechi de CUTOFF_HOURS
    cutoff = datetime.now() - timedelta(hours=CUTOFF_HOURS)
    orphaned = signals[~signals["signal_id"].isin(resolved_ids)].copy()
    orphaned["_time"] = pd.to_datetime(orphaned["time"])
    orphaned = orphaned[orphaned["_time"] < cutoff]

    if not orphaned.empty:
        print(f"  [{name}] {len(orphaned)} semnal(e) orfane - marcam expirat:")
        new_rows = []
        for _, row in orphaned.iterrows():
            print(f"    - {row['signal_id']} ({row['time']}) {row.get('symbol','')} {row.get('dir_str','')}")
            new_rows.append({
                "signal_id":   row["signal_id"],
                "time_check":  datetime.now().isoformat(),
                "symbol":      row.get("symbol", ""),
                "direction":   row.get("direction", 0),
                "status":      "expirat",
                "entry":       row.get("entry", 0),
                "sl":          row.get("sl", 0),
                "tp":          row.get("tp", 0),
                "r_ratio":     row.get("r_ratio", 0),
                "triggered_at": "",
                "exit_price":  "",
                "exit_time":   "",
                "result_r":    0.0,
            })
            resolved_ids.add(row["signal_id"])
            result["orphaned_marked"] += 1

        if not dry_run and new_rows:
            new_df = pd.DataFrame(new_rows)
            if outcomes is not None and not outcomes.empty:
                updated = pd.concat([outcomes, new_df], ignore_index=True)
            else:
                cols = ["signal_id","time_check","symbol","direction","status",
                        "entry","sl","tp","r_ratio","triggered_at",
                        "exit_price","exit_time","result_r"]
                updated = new_df[cols]
            updated.to_csv(outcomes_csv, index=False)
            print(f"    Salvat outcomes.csv cu {len(new_rows)} intrari noi")
    else:
        print(f"  [{name}] Niciun semnal orfan gasit")

    # 2. Curata state.pkl pending
    if state_pkl.exists():
        try:
            with open(state_pkl, "rb") as f:
                state = pickle.load(f)

            pending = state.get("pending", {})
            to_remove = []

            for symbol in list(pending.keys()):
                # Cel mai recent semnal pentru simbolul asta
                sym_signals = signals[signals.get("symbol", pd.Series()) == symbol] \
                    if "symbol" in signals.columns else signals
                sym_signals = signals[signals["symbol"] == symbol] if "symbol" in signals.columns else pd.DataFrame()

                if sym_signals.empty:
                    # Niciun semnal pentru simbol → pending e orfan
                    to_remove.append(symbol)
                    continue

                latest_sig_id = sym_signals.iloc[-1]["signal_id"]
                if latest_sig_id in resolved_ids:
                    # Cel mai recent semnal e rezolvat → pending e stale
                    to_remove.append(symbol)

            if to_remove:
                print(f"  [{name}] Sterg {len(to_remove)} intrari stale din pending: {to_remove}")
                if not dry_run:
                    for sym in to_remove:
                        del pending[sym]
                    state["pending"] = pending
                    with open(state_pkl, "wb") as f:
                        pickle.dump(state, f)
                    print(f"    state.pkl actualizat")
                result["pending_cleaned"] = len(to_remove)
            else:
                print(f"  [{name}] state.pkl pending OK — nimic de curatat")

        except Exception as e:
            result["errors"].append(f"state.pkl error: {e}")

    return result


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        print("=== DRY RUN — nu se scrie nimic ===\n")

    if not SIGNALS_DIR.exists():
        print(f"Director {SIGNALS_DIR} nu exista. Ruleaza din radacina proiectului.")
        sys.exit(1)

    total_orphaned = 0
    total_pending  = 0

    for session_dir in sorted(SIGNALS_DIR.iterdir()):
        if not session_dir.is_dir():
            continue
        r = cleanup_session(session_dir, dry_run=dry_run)
        total_orphaned += r["orphaned_marked"]
        total_pending  += r["pending_cleaned"]
        if r["errors"]:
            print(f"  ERORI in {r['session']}: {r['errors']}")

    print(f"\n=== REZUMAT ===")
    print(f"Semnale orfane marcate expirat: {total_orphaned}")
    print(f"Intrari pending curatate:       {total_pending}")
    if dry_run:
        print("(dry-run — nimic nu a fost scris)")
