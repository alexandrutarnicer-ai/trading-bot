"""
Launcher — Download M15 AUDNZD/AUDCAD + Scan
"""
import os, sys, subprocess, time
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HERE = os.path.join(ROOT, "scripts", "research")
OUT  = os.path.join(HERE, "rezultate_audcross.txt")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def run_step(label, script):
    print(f"\n{'='*60}\n  {label}\n{'='*60}")
    env = os.environ.copy(); env["PYTHONIOENCODING"] = "utf-8"
    t0  = time.time()
    r   = subprocess.run([sys.executable, script], capture_output=True,
                         text=True, encoding="utf-8", errors="replace", env=env)
    out = r.stdout + (("\n--- STDERR ---\n" + r.stderr) if r.stderr.strip() else "")
    print(out)
    with open(OUT, "a", encoding="utf-8") as f:
        f.write(f"\n{'='*60}\n  {label}  {datetime.now():%Y-%m-%d %H:%M:%S}\n{'='*60}\n")
        f.write(out)
    return r.returncode == 0

if __name__ == "__main__":
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(f"AUDNZD+AUDCAD Scan — {datetime.now():%Y-%m-%d %H:%M:%S}\n")
    run_step("STEP 1 — Download M15 AUDNZD+AUDCAD", os.path.join(HERE, "descarca_audcross_m15.py"))
    run_step("STEP 2 — Scan M15+M30",               os.path.join(HERE, "scan_audcross.py"))
    print(f"\n  Rezultate: {OUT}")
