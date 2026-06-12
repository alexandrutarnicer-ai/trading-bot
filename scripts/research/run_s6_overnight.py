"""
Launcher noapte — Session 6 Research
=====================================
1. Descarca datele lipsa (H1 + H4 + M30 pentru 25 simboluri)
2. Ruleaza scanul complet Session 6 (23 piete, 3 TF combos, 4 PW, 2 directii)
3. Salveaza rezultatele in scripts/research/rezultate_s6.txt

Ruleaza independent de run_all.py — doar citeste fisiere CSV, nu atinge nimic live.

Rulare: python scripts/research/run_s6_overnight.py
"""

import os
import sys
import subprocess
import time
from datetime import datetime

ROOT   = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HERE   = os.path.join(ROOT, "scripts", "research")
OUT    = os.path.join(HERE, "rezultate_s6.txt")

DESCARCA = os.path.join(HERE, "descarca_s6.py")
SCAN     = os.path.join(HERE, "session6_scan.py")

SEP = "=" * 70

def run_step(label, script, output_file):
    print(f"\n{SEP}")
    print(f"  {label}")
    print(f"  Start: {datetime.now().strftime('%H:%M:%S')}")
    print(SEP)

    t0  = time.time()
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    result = subprocess.run(
        [sys.executable, script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )

    elapsed = time.time() - t0
    output  = result.stdout + (("\n--- STDERR ---\n" + result.stderr) if result.stderr.strip() else "")

    print(output)
    print(f"\n  Durata: {elapsed/60:.1f} minute  |  returncode={result.returncode}")

    if output_file:
        with open(output_file, "a", encoding="utf-8") as f:
            f.write(f"\n{'='*70}\n")
            f.write(f"  {label}  —  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"{'='*70}\n")
            f.write(output)
            f.write(f"\nDurata: {elapsed/60:.1f} min\n")

    return result.returncode == 0


if __name__ == "__main__":
    print(SEP)
    print("  SESSION 6 — RESEARCH OVERNIGHT")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Output: {OUT}")
    print(SEP)

    # Curata fisierul de output anterior
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(f"Session 6 Research — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # Step 1: Descarca date
    ok = run_step(
        "STEP 1/2 — Descarcare date H1 + H4 + M30",
        DESCARCA,
        OUT,
    )
    if not ok:
        print("\n  ATENTIE: Descarcarea a esuat partial — continuam oricum cu ce avem.")

    # Step 2: Scan
    run_step(
        "STEP 2/2 — Scan complet Session 6 (23 piete)",
        SCAN,
        OUT,
    )

    print(f"\n{SEP}")
    print(f"  GATA. Citeste rezultatele in:")
    print(f"  {OUT}")
    print(f"  {datetime.now().strftime('%H:%M:%S')}")
    print(SEP)
