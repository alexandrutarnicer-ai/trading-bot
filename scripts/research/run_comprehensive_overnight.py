"""
Launcher — Scan Comprehensive (Gold M15 + EUR/GBP crosses)
===========================================================
Ruleaza scan_comprehensive.py si salveaza rezultatele.

Rulare: python scripts/research/run_comprehensive_overnight.py
"""

import os
import sys
import subprocess
import time
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HERE = os.path.join(ROOT, "scripts", "research")
OUT  = os.path.join(HERE, "rezultate_comprehensive.txt")
SCAN = os.path.join(HERE, "scan_comprehensive.py")

SEP = "=" * 70

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

if __name__ == "__main__":
    print(SEP)
    print("  SCAN COMPREHENSIVE — Gold M15 + EUR/GBP crosses + sesiuni noi")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Output: {OUT}")
    print(SEP)

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(f"Scan Comprehensive — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    t0  = time.time()
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    result = subprocess.run(
        [sys.executable, SCAN],
        capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        env=env,
    )

    elapsed = time.time() - t0
    output  = result.stdout + (("\n--- STDERR ---\n" + result.stderr) if result.stderr.strip() else "")

    print(output)
    print(f"\n  Durata: {elapsed/60:.1f} minute  |  returncode={result.returncode}")

    with open(OUT, "a", encoding="utf-8") as f:
        f.write(output)
        f.write(f"\nDurata totala: {elapsed/60:.1f} min\n")

    print(f"\n{SEP}")
    print(f"  GATA. Rezultate in: {OUT}")
    print(f"  {datetime.now().strftime('%H:%M:%S')}")
    print(SEP)
