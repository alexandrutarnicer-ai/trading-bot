#!/usr/bin/env python3
"""
Reseteaza datele live ale Standard Profile la o stare curata (zero semnale, zero outcome-uri).

Util cand vrei sa pornesti de la zero sau sa mostenesti profilul standard fara
istoricul de tranzactii al altcuiva.

Ce face:
  - Reseteaza signals.csv si outcomes.csv la header gol (pastreaza coloanele)
  - Sterge state.pkl (stare pendinga, tickete MT5, friday_close_date)
  - Sterge generator.log
  - Reseteaza paused_sessions.json la []

Cu --all reseteaza si:
  - backtest_history.json
  - backtest_jobs.json
  - download_jobs.json

Usage:
    python scripts/clear_standard_data.py
    python scripts/clear_standard_data.py --all
    python scripts/clear_standard_data.py --yes        # fara confirmare interactiva
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

LIVE_DIR     = os.path.join(ROOT, "data", "live_signals")
PAUSED_FILE  = os.path.join(ROOT, "data", "paused_sessions.json")
BT_HISTORY   = os.path.join(ROOT, "data", "backtest_history.json")
BT_JOBS      = os.path.join(ROOT, "data", "backtest_jobs.json")
DL_JOBS      = os.path.join(ROOT, "data", "download_jobs.json")

SIGNALS_HEADER  = (
    "signal_id,time,symbol,direction,dir_str,"
    "entry,sl,tp,r_ratio,atr_pips,n_optional,rsi\n"
)
OUTCOMES_HEADER = (
    "signal_id,time_check,symbol,direction,status,"
    "entry,sl,tp,r_ratio,triggered_at,exit_price,exit_time,result_r\n"
)


def _reset_csv(path: str, header: str) -> str:
    if os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(header)
        return "resetat"
    return "absent"


def _delete(path: str) -> str:
    if os.path.exists(path):
        os.remove(path)
        return "sters"
    return "absent"


def _write_json(path: str, value) -> str:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(value, f)
    return "resetat"


def clear_session(session_dir: str, name: str):
    ops = [
        ("signals.csv",   _reset_csv(os.path.join(session_dir, "signals.csv"),  SIGNALS_HEADER)),
        ("outcomes.csv",  _reset_csv(os.path.join(session_dir, "outcomes.csv"), OUTCOMES_HEADER)),
        ("state.pkl",     _delete(os.path.join(session_dir, "state.pkl"))),
        ("generator.log", _delete(os.path.join(session_dir, "generator.log"))),
    ]
    parts = [f"{f}:{s}" for f, s in ops if s != "absent"]
    status = ", ".join(parts) if parts else "nimic de resetat"
    print(f"  [{name}] {status}")


def main():
    parser = argparse.ArgumentParser(
        description="Reseteaza datele live Standard Profile la stare curata."
    )
    parser.add_argument("--all", action="store_true",
                        help="Reseteaza si backtest_history, backtest_jobs, download_jobs")
    parser.add_argument("--yes", "-y", action="store_true",
                        help="Sari confirmarea interactiva")
    args = parser.parse_args()

    print("=" * 60)
    print("  CLEAR STANDARD PROFILE DATA")
    print("=" * 60)

    if not os.path.isdir(LIVE_DIR):
        print(f"\n[EROARE] {LIVE_DIR} nu exista.")
        print("Porneste botul cel putin o data pentru a initializa sesiunile.")
        sys.exit(1)

    sessions = sorted(
        d for d in os.listdir(LIVE_DIR)
        if os.path.isdir(os.path.join(LIVE_DIR, d))
    )
    if not sessions:
        print("\nNu exista sesiuni live de resetat.")
        sys.exit(0)

    print(f"\nSesiuni detectate: {', '.join(sessions)}")
    if args.all:
        print("Optiuni extra: backtest_history.json, backtest_jobs.json, download_jobs.json")

    if not args.yes:
        print()
        ans = input("Continui? Datele live vor fi sterse definitiv [da/nu]: ").strip().lower()
        if ans not in ("da", "d", "yes", "y"):
            print("Anulat.")
            sys.exit(0)

    print("\nResetare sesiuni live:")
    for session in sessions:
        clear_session(os.path.join(LIVE_DIR, session), session)

    print(f"  [global] paused_sessions.json: {_write_json(PAUSED_FILE, [])}")

    if args.all:
        print("\nResetare date optionale:")
        for path, label in [
            (BT_HISTORY, "backtest_history.json"),
            (BT_JOBS,    "backtest_jobs.json"),
            (DL_JOBS,    "download_jobs.json"),
        ]:
            print(f"  {label}: {_write_json(path, [])}")

    print("\nGata. Poti porni botul cu date curate.")


if __name__ == "__main__":
    main()
