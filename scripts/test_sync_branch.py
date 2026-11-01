"""
QA: sincronizarea PC <-> laptop (scripts/sync_branch.py). Offline — doua clone git TEMPORARE +
un remote local; NU atinge repo-ul real, MT5, engine-urile sau Telegram.
    python scripts/test_sync_branch.py
"""
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts import sync_branch as SB  # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name} {detail}")


def sh(cwd, *args):
    r = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def wr(root, rel, text, age_days=0.0):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w", encoding="utf-8", newline="\n").write(text)
    if age_days:
        t = time.time() - age_days * 86400
        os.utime(p, (t, t))


def rd(root, rel):
    return open(os.path.join(root, rel), encoding="utf-8").read()


TMP = tempfile.mkdtemp()
REMOTE, LAPTOP, PC = (os.path.join(TMP, n) for n in ("remote.git", "laptop", "pc"))
subprocess.run(["git", "init", "-q", "--bare", "-b", "alex-live", REMOTE], check=True)
subprocess.run(["git", "clone", "-q", REMOTE, LAPTOP], check=True)
sh(LAPTOP, "config", "user.name", "t"); sh(LAPTOP, "config", "user.email", "t@t")
sh(LAPTOP, "checkout", "-q", "-b", "alex-live")
wr(LAPTOP, ".gitignore", "data/*\n*.csv\n")
wr(LAPTOP, "api/x.py", "v = 1\n")
wr(LAPTOP, "data/live_signals/session1/outcomes.csv", "id\nS1\n")
sh(LAPTOP, "add", "-A"); sh(LAPTOP, "add", "-f", "data/live_signals/session1/outcomes.csv")
sh(LAPTOP, "commit", "-q", "-m", "init"); sh(LAPTOP, "push", "-q", "-u", "origin", "alex-live")
subprocess.run(["git", "clone", "-q", "-b", "alex-live", REMOTE, PC], check=True)
sh(PC, "config", "user.name", "t"); sh(PC, "config", "user.email", "t@t")


def run(root):
    SB.ROOT = root
    try:
        SB.sync()
        return None
    except SB.Stop as e:
        return str(e)


print("1. Laptopul ruleaza Custom + AI (jurnale recente, ledger deschis in WAL)")
wr(LAPTOP, "data/live_signals/session1/generator.log", "iter\n")
wr(LAPTOP, "data/ai/engine.log", "iter\n")
wr(LAPTOP, "data/live_signals/session1/outcomes.csv", "id\nS1\nS2\n")
wr(LAPTOP, "data/live_signals/session22/signals.csv", "id\nSOFI1\n")
db = os.path.join(LAPTOP, "data", "ai", "ledger.db")
con = sqlite3.connect(db)
con.execute("PRAGMA journal_mode=WAL"); con.execute("CREATE TABLE d (x)"); con.execute("INSERT INTO d VALUES (1),(2),(3)")
con.commit()
SB.ROOT = LAPTOP
here = SB.engines_here()
check("laptop: Custom + AI detectate ca rulate aici, Daily nu",
      here["Custom Engine"] and here["AI Engine"] and not here["Daily Engine"], here)
err = run(LAPTOP)
con.close()
check("laptop: sync fara eroare", err is None, err)
files = set(sh(REMOTE, "ls-tree", "-r", "--name-only", "alex-live").splitlines())
check("pe GitHub: outcomes + session22 + ledger", {"data/live_signals/session1/outcomes.csv",
      "data/live_signals/session22/signals.csv", "data/ai/ledger.db"} <= files, files)
check("jurnalele / PID-urile NU se urca", not any(f.endswith((".log", ".pid")) for f in files), files)

print("2. PC doar analizeaza: copie VECHE session22 + jurnale vechi (Custom a rulat aici acum o luna)")
wr(PC, "data/live_signals/session1/generator.log", "vechi\n", age_days=30)
wr(PC, "data/live_signals/session22/signals.csv", "id\nVECHI\n", age_days=60)
wr(PC, "data/live_signals/session21/signals.csv", "id\nCSCO_VECHI\n", age_days=60)
SB.ROOT = PC
check("PC: niciun engine recent", not any(SB.engines_here().values()))
err = run(PC)
check("PC: sync fara eroare", err is None, err)
check("PC a primit datele laptopului", rd(PC, "data/live_signals/session22/signals.csv") == "id\nSOFI1\n"
      and rd(PC, "data/live_signals/session1/outcomes.csv") == "id\nS1\nS2\n")
rows = sqlite3.connect(os.path.join(PC, "data", "ai", "ledger.db")).execute("SELECT COUNT(*) FROM d").fetchone()[0]
check("ledger AI complet pe PC (inclusiv ce era in WAL)", rows == 3, rows)
files = set(sh(REMOTE, "ls-tree", "-r", "--name-only", "alex-live").splitlines())
check("copiile vechi ale PC-ului NU au fost urcate (session21 absent pe GitHub)",
      "data/live_signals/session21/signals.csv" not in files)
bk = os.path.join(PC, "data", "_sync_backup")
check("copia veche session22 a PC-ului MUTATA deoparte, nu stearsa",
      any("session22" in r for r, _, fs in os.walk(bk) if fs))

print("3. Laptopul continua; PC-ul modifica o setare din UI")
wr(PC, "data/global_settings.json", '{"risk_cap": 2}\n')
sh(PC, "add", "-f", "data/global_settings.json"); sh(PC, "commit", "-qm", "setari"); sh(PC, "push", "-q")
wr(PC, "data/global_settings.json", '{"risk_cap": 3}\n')                   # schimbare din UI, necomisa
wr(LAPTOP, "data/live_signals/session1/outcomes.csv", "id\nS1\nS2\nS3\n")
err = run(PC)
check("PC: setarea modificata din UI se trimite", err is None and '"risk_cap": 3' in sh(REMOTE, "show", "alex-live:data/global_settings.json"), err)
err = run(LAPTOP)
check("laptop: trimite datele noi + primeste setarea", err is None and '"risk_cap": 3' in rd(LAPTOP, "data/global_settings.json"), err)
err = run(PC)
check("PC: primeste S3", err is None and rd(PC, "data/live_signals/session1/outcomes.csv").endswith("S3\n"), err)

print("4. Cod nou pe un dispozitiv, cod local necomis pe celalalt")
wr(PC, "api/x.py", "v = 2\n"); sh(PC, "commit", "-qam", "cod"); sh(PC, "push", "-q")
wr(LAPTOP, "api/x.py", "v = 99\n")
err = run(LAPTOP)
check("conflict de cod -> oprire, fisierul local neatins", err and "api/x.py" in err and rd(LAPTOP, "api/x.py") == "v = 99\n", err)
sh(LAPTOP, "checkout", "--", "api/x.py")
err = run(LAPTOP)
check("dupa anulare: codul nou ajunge", err is None and rd(LAPTOP, "api/x.py") == "v = 2\n", err)

print("5. Engine-urile mutate pe PC: datele PC-ului se trimit, laptopul le primeste")
wr(PC, "data/daily_engine/engine.log", "iter\n")
wr(PC, "data/daily_engine/trades.jsonl", '{"symbol": "US500"}\n')
err = run(PC)
check("PC: Daily a rulat aici -> trade-urile Daily trimise", err is None and "US500" in sh(REMOTE, "show", "alex-live:data/daily_engine/trades.jsonl"), err)
err = run(LAPTOP)
check("laptop: primeste trade-urile Daily", err is None and "US500" in rd(LAPTOP, "data/daily_engine/trades.jsonl"), err)

print("6. Refuza main / vlad-live")
sh(PC, "checkout", "-q", "-b", "main")
err = run(PC)
check("pe main -> refuzat", err and "main" in err, err)

shutil.rmtree(TMP, ignore_errors=True)
print(f"\nREZULTAT: {PASS} PASS / {FAIL} FAIL")
sys.exit(1 if FAIL else 0)
