"""
Test: export trade-uri AI inchise (ai_engine/export.py).

    python scripts/test_ai_export.py

Verifica:
1. Doar statusuri de trade real inchis (TP/SL/closed) — expired/cancelled EXCLUSE
2. Outcome-ul FINAL per decizie (ultimul, MAX id) cand exista mai multe
3. Coloanele + valorile (result_r/pnl_usd) corecte
4. DB lipsa → CSV cu doar antet (0 randuri), fara exceptie
"""

import csv
import os
import sqlite3
import sys
import tempfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai_engine.export import export_closed_outcomes, COLS

PASS = FAIL = 0


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  PASS  {msg}")
    else:
        FAIL += 1; print(f"  FAIL  {msg}")


def _make_db(path):
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE decisions (id INTEGER PRIMARY KEY, ts TEXT, symbol TEXT, council_id INT,
            action TEXT, order_type TEXT, entry REAL, sl REAL, tp REAL, risk_pct REAL,
            confidence INT, rationale TEXT, exec_status TEXT, exec_detail TEXT, ticket INT);
        CREATE TABLE outcomes (id INTEGER PRIMARY KEY, ts TEXT, decision_id INT, symbol TEXT,
            status TEXT, exit_price REAL, result_r REAL, pnl_usd REAL);
    """)
    def dec(i, sym, action="OPEN_LONG"):
        con.execute("INSERT INTO decisions (id,ts,symbol,action,order_type,entry,sl,tp,"
                    "risk_pct,confidence,ticket) VALUES (?,?,?,?,'stop',1.1,1.09,1.12,0.0025,70,?)",
                    (i, f"2026-07-21T0{i}:00:00", sym, action, 1000 + i))
    def out(oid, did, sym, status, r, pnl, ts):
        con.execute("INSERT INTO outcomes (id,ts,decision_id,symbol,status,exit_price,result_r,pnl_usd) "
                    "VALUES (?,?,?,?,?,1.11,?,?)", (oid, ts, did, sym, status, r, pnl))
    # 1 TP, 2 SL (inchise) ; 3 expired, 4 cancelled (NU trade-uri) ; 5 = doua outcomes (final castiga)
    for i, s in [(1,"EURUSD"),(2,"USDJPY"),(3,"GBPUSD"),(4,"AUDUSD"),(5,"USDCAD")]:
        dec(i, s)
    out(10, 1, "EURUSD", "TP",  2.0,  20.0, "2026-07-21T05:00:00")
    out(11, 2, "USDJPY", "SL", -1.0, -10.0, "2026-07-21T06:00:00")
    out(12, 3, "GBPUSD", "expired",   0.0, 0.0, "2026-07-21T07:00:00")
    out(13, 4, "AUDUSD", "cancelled", 0.0, 0.0, "2026-07-21T08:00:00")
    out(14, 5, "USDCAD", "SL", -0.5, -5.0, "2026-07-21T09:00:00")   # intermediar
    out(15, 5, "USDCAD", "TP",  3.0,  30.0, "2026-07-21T10:00:00")  # FINAL (id mai mare)
    con.commit(); con.close()


with tempfile.TemporaryDirectory() as td:
    db  = os.path.join(td, "ledger.db")
    out = os.path.join(td, "ai_outcomes.csv")

    print("\n[Test 1] DB lipsa → CSV cu antet, 0 randuri")
    n0 = export_closed_outcomes(db, out)
    check(n0 == 0, f"DB lipsa → 0 randuri [got {n0}]")
    check(os.path.exists(out), "CSV creat cu antet chiar si fara DB")
    check(list(csv.reader(open(out)))[0] == COLS, "antetul are toate coloanele")

    print("\n[Test 2] Export cu date")
    _make_db(db)
    n = export_closed_outcomes(db, out)
    rows = list(csv.DictReader(open(out, encoding="utf-8")))
    syms = {r["symbol"] for r in rows}
    statuses = {r["status"] for r in rows}
    check(n == 3, f"3 trade-uri inchise (1 TP + 1 SL + 1 final din decizia 5) [got {n}]")
    check(statuses <= {"TP", "SL", "closed"}, f"doar statusuri inchise [got {statuses}]")
    check("GBPUSD" not in syms, "expired EXCLUS")
    check("AUDUSD" not in syms, "cancelled EXCLUS")
    # decizia 5: outcome final (TP, +3.0) — nu intermediarul (SL, -0.5)
    usdcad = [r for r in rows if r["symbol"] == "USDCAD"]
    check(len(usdcad) == 1 and usdcad[0]["status"] == "TP" and usdcad[0]["result_r"] == "3.0",
          f"decizia cu 2 outcome-uri → FINAL (TP +3.0) [got {usdcad}]")
    eur = [r for r in rows if r["symbol"] == "EURUSD"][0]
    check(eur["result_r"] == "2.0" and eur["pnl_usd"] == "20.0", "valorile result_r/pnl_usd corecte")

print(f"\n{'='*56}\nREZULTAT: {PASS} PASS / {FAIL} FAIL\n{'='*56}")
sys.exit(1 if FAIL else 0)
