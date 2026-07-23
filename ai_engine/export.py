"""
Export al trade-urilor AI ÎNCHISE din ledger (data/ai/ledger.db) intr-un CSV
git-trackable (data/ai/ai_outcomes.csv) — pentru urmarire + transfer PC↔laptop pe
branch (alex-pc-laptop).

Reguli:
  • DOAR trade-uri ÎNCHISE real: status IN ('TP','SL','closed'). Ordinele
    'expired'/'cancelled' (plasate dar niciodata activate) NU sunt trade-uri.
  • outcome-ul FINAL per decizie (ultimul outcome): result_r + pnl_usd actualizate.
  • conexiune READ-ONLY pe DB → sigur si cu motorul pornit (SQLite = cititori concurenti).

Folosit de: `scripts/export_ai_outcomes.py` (CLI) si de motorul AI dupa fiecare
actualizare de outcome (auto-refresh, fail-safe).
"""

import csv
import os
import sqlite3

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH  = os.path.join(ROOT, "data", "ai", "ledger.db")
OUT_PATH = os.path.join(ROOT, "data", "ai", "ai_outcomes.csv")

# Coloane exportate, in ordine — identitate trade + outcome final.
COLS = [
    "decision_id", "symbol", "action", "order_type",
    "entry", "sl", "tp", "risk_pct", "confidence", "ticket",
    "decision_ts", "status", "exit_price", "result_r", "pnl_usd", "outcome_ts",
]

# Ultimul outcome per decizie (MAX id) + doar statusuri de trade real inchis.
QUERY = """
SELECT d.id AS decision_id, d.symbol, d.action, d.order_type,
       d.entry, d.sl, d.tp, d.risk_pct, d.confidence, d.ticket, d.ts AS decision_ts,
       o.status, o.exit_price, o.result_r, o.pnl_usd, o.ts AS outcome_ts
FROM outcomes o
JOIN decisions d ON d.id = o.decision_id
WHERE o.id IN (SELECT MAX(id) FROM outcomes GROUP BY decision_id)
  AND o.status IN ('TP', 'SL', 'closed')
ORDER BY o.ts
"""


def closed_rows(db_path: str = DB_PATH) -> list[dict]:
    """Randurile trade-urilor AI inchise (read-only). [] daca DB lipseste."""
    if not os.path.exists(db_path):
        return []
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        cur = con.execute(QUERY)
        names = [c[0] for c in cur.description]
        return [dict(zip(names, r)) for r in cur.fetchall()]
    finally:
        con.close()


def export_closed_outcomes(db_path: str = DB_PATH, out_path: str = OUT_PATH) -> int:
    """
    Scrie CSV-ul cu trade-urile AI inchise. Returneaza numarul de randuri.
    Fail-safe: DB lipsa → CSV cu doar antet (0 randuri). Scriere atomica (tmp+rename)
    ca sa nu lase un fisier partial daca procesul e intrerupt in scriere.
    """
    rows = closed_rows(db_path)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    tmp = out_path + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, out_path)
    return len(rows)
