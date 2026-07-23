"""
CLI: exporta trade-urile AI ÎNCHISE din ledger intr-un CSV git-trackable
(data/ai/ai_outcomes.csv) — pentru urmarire + transfer PC↔laptop pe branch.

Logica reala e in `ai_engine/export.py` (partajata cu motorul, care re-exporta
automat dupa fiecare actualizare de outcome).

Utilizare:
    python scripts/export_ai_outcomes.py           # scrie CSV-ul
    python scripts/export_ai_outcomes.py --print    # + afiseaza randurile

Transfer intre masini:
    git add data/ai/ai_outcomes.csv && git commit -m "ai outcomes" && git push
    (pe cealalta masina: git pull)
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai_engine.export import export_closed_outcomes, closed_rows, OUT_PATH, ROOT


def main() -> int:
    n = export_closed_outcomes()
    print(f"[export-ai] {n} trade-uri AI inchise -> {os.path.relpath(OUT_PATH, ROOT)}")
    if "--print" in sys.argv:
        for r in closed_rows():
            print(f"  #{r['decision_id']} {r['symbol']:8} {r['status']:4} "
                  f"R={r['result_r']} pnl={r['pnl_usd']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
