"""
QA: schimbarea dispozitivului PC <-> laptop (scripts/device_switch.py + device_owner.py).
Offline — doua clone git TEMPORARE + un remote local; engine-uri simulate; NU trimite Telegram,
NU atinge repo-ul real, MT5 sau engine-urile reale.
    python scripts/test_device_switch.py
"""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import device_owner as DO  # noqa: E402
from scripts import device_switch as DS  # noqa: E402

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


TMP = tempfile.mkdtemp()
REMOTE = os.path.join(TMP, "remote.git")
LAPTOP = os.path.join(TMP, "laptop")
PC = os.path.join(TMP, "pc")
subprocess.run(["git", "init", "-q", "--bare", "-b", "alex-live", REMOTE], check=True)
subprocess.run(["git", "clone", "-q", REMOTE, LAPTOP], check=True)
for d in (LAPTOP,):
    sh(d, "config", "user.name", "t"); sh(d, "config", "user.email", "t@t"); sh(d, "checkout", "-q", "-b", "alex-live")


def wr(root, rel, text):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w", encoding="utf-8", newline="\n").write(text)


def rd(root, rel):
    return open(os.path.join(root, rel), encoding="utf-8").read()


# repo initial: cod + date ignorate (ca alex-live: data/* in .gitignore, datele force-add)
wr(LAPTOP, ".gitignore", "data/*\n*.csv\n")
wr(LAPTOP, "api/x.py", "v = 1\n")
wr(LAPTOP, "ai_engine/config.json", '{"markets": ["GBPUSD"]}\n')
wr(LAPTOP, "data/live_signals/session1/outcomes.csv", "id\nS1\n")
sh(LAPTOP, "add", "-A"); sh(LAPTOP, "add", "-f", "data/live_signals/session1/outcomes.csv")
sh(LAPTOP, "commit", "-q", "-m", "init"); sh(LAPTOP, "push", "-q", "-u", "origin", "alex-live")
subprocess.run(["git", "clone", "-q", "-b", "alex-live", REMOTE, PC], check=True)
sh(PC, "config", "user.name", "t"); sh(PC, "config", "user.email", "t@t")

# engine-uri simulate per dispozitiv
ENG = {"LAPTOP": {"custom", "ai"}, "PC": set()}
CALLS = []


def use(dev):
    root = LAPTOP if dev == "LAPTOP" else PC
    os.environ["COMPUTERNAME"] = dev
    DS.ROOT = root
    DO.OWNER_FILE = os.path.join(root, "data", "device_owner.json")
    DS.running_engines = lambda: [e for e in DS.ORDER if e in ENG[dev]]

    def stop(eids):
        CALLS.append((dev, "stop", tuple(eids)))
        ENG[dev].difference_update(eids)

    def start(eids):
        CALLS.append((dev, "start", tuple(eids)))
        ENG[dev].update(eids)
        return []
    DS.stop_engines, DS.start_engines = stop, start
    return root


DS.notify = lambda text: CALLS.append(("telegram", text))     # NICIODATA Telegram real in teste
os.environ["DEVICE_SWITCH_YES"] = "1"


def run(dev, fn, *a):
    use(dev)
    try:
        fn(*a)
        return None
    except DS.Stop as e:
        return str(e)


print("1. Laptopul ruleaza engine-urile si scrie date (inclusiv ledger AI deschis, in WAL)")
use("LAPTOP")
wr(LAPTOP, "data/live_signals/session1/outcomes.csv", "id\nS1\nS2\n")
wr(LAPTOP, "data/live_signals/session22/signals.csv", "id\nSOFI1\n")          # sesiune nesincronizata pana acum
db = os.path.join(LAPTOP, "data", "ai", "ledger.db")
os.makedirs(os.path.dirname(db), exist_ok=True)
con = sqlite3.connect(db)
con.execute("PRAGMA journal_mode=WAL"); con.execute("CREATE TABLE d (x)"); con.execute("INSERT INTO d VALUES (1),(2),(3)")
con.commit()                                       # conexiunea ramane deschisa (motorul ruleaza)
wr(LAPTOP, "data/daily_engine/trades.jsonl", '{"symbol": "US500"}\n')

print("2. PC: copie VECHE session22 (neurmarita) + date scrise local de UI")
wr(PC, "data/live_signals/session22/signals.csv", "id\nVECHI\n")
wr(PC, "data/live_signals/session1/outcomes.csv", "id\nS1\nLOCAL_PC\n")

print("3. Laptop -> PREDAU")
err = run("LAPTOP", DS.cmd_predau)
con.close()
check("predare fara eroare", err is None, err)
check("engine-urile laptopului oprite", ("LAPTOP", "stop", ("custom", "ai")) in CALLS and not ENG["LAPTOP"])
ro = json.loads(sh(REMOTE, "show", "alex-live:data/device_owner.json"))
check("pe GitHub: LAPTOP · released · [custom, ai]", ro["owner"] == "LAPTOP" and ro["state"] == "released"
      and ro["engines"] == ["custom", "ai"], ro)
files = sh(REMOTE, "ls-tree", "-r", "--name-only", "alex-live").splitlines()
check("datele trimise: outcomes + session22 + ledger + trades Daily",
      {"data/live_signals/session1/outcomes.csv", "data/live_signals/session22/signals.csv",
       "data/ai/ledger.db", "data/daily_engine/trades.jsonl"} <= set(files), files)

print("4. PC -> PREIAU")
err = run("PC", DS.cmd_preiau)
check("preluare fara eroare", err is None, err)
check("datele laptopului au ajuns pe PC", rd(PC, "data/live_signals/session1/outcomes.csv") == "id\nS1\nS2\n"
      and rd(PC, "data/live_signals/session22/signals.csv") == "id\nSOFI1\n")
rows = sqlite3.connect(os.path.join(PC, "data", "ai", "ledger.db")).execute("SELECT COUNT(*) FROM d").fetchone()[0]
check("ledger AI complet (copie consistenta, inclusiv ce era in WAL)", rows == 3, rows)
bk = os.path.join(PC, "data", "_sync_backup")
bfiles = [os.path.relpath(os.path.join(r, f), bk).replace("\\", "/") for r, _, fs in os.walk(bk) for f in fs]
check("copiile locale ale PC-ului MUTATE deoparte (nu sterse)",
      any(f.endswith("session22/signals.csv") for f in bfiles) and any(f.endswith("session1/outcomes.csv") for f in bfiles), bfiles)
check("PC a pornit exact engine-urile predate", ("PC", "start", ("custom", "ai")) in CALLS and ENG["PC"] == {"custom", "ai"})
ro = json.loads(sh(REMOTE, "show", "alex-live:data/device_owner.json"))
check("pe GitHub: PC · running", ro["owner"] == "PC" and ro["state"] == "running", ro)

print("5. Plase de siguranta")
use("LAPTOP"); sh(LAPTOP, "pull", "-q")
check("laptop: UI-ul refuza pornirea (engine-urile ruleaza pe PC)", DO.other_device_running() == "PC")
check("laptop: NU trimite rapoartele", not DO.is_reporting_machine())
use("PC")
check("PC: poate porni / trimite rapoarte", DO.other_device_running() is None and DO.is_reporting_machine())
err = run("LAPTOP", DS.cmd_trimit)
check("laptop: TRIMIT refuzat (nu e proprietar)", err and "PC" in err, err)
err = run("LAPTOP", DS.cmd_predau)
check("laptop: PREDAU refuzat (n-are ce preda)", err and "PC" in err, err)
del os.environ["DEVICE_SWITCH_YES"]
_ask = DS.ask
DS.ask = lambda q, yes_default=True: False               # userul raspunde NU la avertisment
n_before = len([c for c in CALLS if c[0] == "LAPTOP" and c[1] == "start"])
err = run("LAPTOP", DS.cmd_preiau)
check("laptop: PREIAU fara predare de pe PC -> avertisment + anulat la NU", err and "anulat" in err.lower(), err)
check("... si nu porneste nimic", len([c for c in CALLS if c[0] == "LAPTOP" and c[1] == "start"]) == n_before)
DS.ask = _ask
os.environ["DEVICE_SWITCH_YES"] = "1"

print("6. PC (proprietar) TRIMIT cu engine-urile pornite; laptopul ACTUALIZEZ (doar analiza)")
wr(PC, "data/live_signals/session1/outcomes.csv", "id\nS1\nS2\nS3\n")
err = run("PC", DS.cmd_trimit)
check("PC trimite fara sa opreasca engine-urile", err is None and ENG["PC"] == {"custom", "ai"}, err)
err = run("LAPTOP", DS.cmd_actualizez)
check("laptop primeste datele noi", err is None and rd(LAPTOP, "data/live_signals/session1/outcomes.csv").endswith("S3\n"), err)
check("ACTUALIZEZ nu porneste engine-uri pe laptop", not ENG["LAPTOP"])
err = run("PC", DS.cmd_actualizez)
check("ACTUALIZEZ refuzat pe dispozitivul care ruleaza engine-urile", err and "TRIMIT" in err.upper(), err)

print("7. Modificari locale de COD nu se suprascriu niciodata")
wr(PC, "api/x.py", "v = 2\n"); sh(PC, "commit", "-qam", "cod pe PC"); sh(PC, "push", "-q", "origin", "alex-live")
wr(LAPTOP, "api/x.py", "v = 99  # necomis\n")
err = run("LAPTOP", DS.cmd_actualizez)
check("cod local necomis in conflict -> oprire cu mesaj, fisierul neatins",
      err and "api/x.py" in err and rd(LAPTOP, "api/x.py") == "v = 99  # necomis\n", err)

print("8. Ruta inapoi: PC PREDAU -> laptop PREIAU")
sh(LAPTOP, "checkout", "--", "api/x.py")
err = run("PC", DS.cmd_predau)
check("PC preda", err is None and not ENG["PC"], err)
err = run("LAPTOP", DS.cmd_preiau)
check("laptopul preia + porneste engine-urile", err is None and ENG["LAPTOP"] == {"custom", "ai"}, err)
check("codul PC-ului a ajuns pe laptop", rd(LAPTOP, "api/x.py") == "v = 2\n")
check("niciun mesaj Telegram real (doar simulat)", all(c[0] != "real" for c in CALLS))

print("9. device_owner fara fisier = comportamentul de dinainte")
DO.OWNER_FILE = os.path.join(TMP, "nu_exista.json")
check("fara fisier: nicio restrictie", DO.other_device_running() is None and DO.is_reporting_machine())

shutil.rmtree(TMP, ignore_errors=True)
print(f"\nREZULTAT: {PASS} PASS / {FAIL} FAIL")
sys.exit(1 if FAIL else 0)
