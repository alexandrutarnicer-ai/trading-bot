"""
setup.py — Instalare automata trading bot pe masina noua
=========================================================
Ruleaza o singura data dupa `git clone`.

Automatizeaza:
  1. Verifica Python >= 3.10
  2. Verifica Node.js >= 18
  3. pip install -r requirements.txt
  4. npm install (frontend React)
  5. Creeaza directoarele necesare + data/profiles/standard.json
  6. Descarca date istorice din MT5 (necesita MT5 pornit + logat)
  7. Configureaza autostart Windows (Task Scheduler)

Necesita interventie manuala INAINTE:
  - Python 3.10+ instalat si adaugat in PATH
  - Node.js 18+ instalat (https://nodejs.org/)
  - MT5 instalat, deschis si logat pe contul demo
  - git clone <repo> facut deja
"""

import os
import sys
import json
import shutil
import subprocess
from pathlib import Path

ROOT     = Path(__file__).parent.resolve()
PYTHON   = sys.executable
REQS     = ROOT / "requirements.txt"
FRONTEND = ROOT / "frontend"
DATA     = ROOT / "data"
PROFILES = DATA / "profiles"

SEP  = "=" * 60
sep2 = "-" * 60

DATA_DIRS = [
    DATA / "live_signals" / "session1",
    DATA / "live_signals" / "session2",
    DATA / "live_signals" / "session3",
    DATA / "live_signals" / "session4",
    DATA / "live_signals" / "session5",
    DATA / "live_signals" / "session6",
    PROFILES,
]


def hdr(title: str) -> None:
    print(f"\n{SEP}\n  {title}\n{SEP}")


def ok(msg: str)  -> None: print(f"  [OK]  {msg}")
def err(msg: str) -> None: print(f"  [!!]  {msg}")
def info(msg: str)-> None: print(f"  [--]  {msg}")


# ─── 1. Python version ────────────────────────────────────────────────────────

def check_python() -> bool:
    hdr("1. Verifica Python")
    v = sys.version_info
    info(f"Python {v.major}.{v.minor}.{v.micro}  ({PYTHON})")
    if v < (3, 10):
        err("Necesita Python >= 3.10. Instaleaza o versiune mai noua.")
        err("Descarca de la: https://www.python.org/downloads/")
        err("Bifeaza 'Add Python to PATH' la instalare.")
        return False
    ok("Versiune Python OK")
    return True


# ─── 2. Node.js version ───────────────────────────────────────────────────────

def check_nodejs() -> bool:
    hdr("2. Verifica Node.js")
    try:
        r = subprocess.run(["node", "--version"], capture_output=True, text=True, timeout=10)
        ver = r.stdout.strip()
        if r.returncode == 0 and ver.startswith("v"):
            major = int(ver.lstrip("v").split(".")[0])
            if major >= 18:
                ok(f"Node.js {ver}")
                return True
            else:
                err(f"Node.js {ver} gasit, dar necesar >= v18.")
        else:
            err("Node.js nu a raspuns corect.")
    except FileNotFoundError:
        err("Node.js nu a fost gasit in PATH.")
    except Exception as e:
        err(f"Eroare la verificare Node.js: {e}")
    err("Descarca de la: https://nodejs.org/ (versiunea LTS)")
    err("Dupa instalare, reporneste terminalul si ruleaza din nou setup.py")
    return False


# ─── 3. pip install ───────────────────────────────────────────────────────────

def install_python_deps() -> bool:
    hdr("3. Instaleaza dependente Python (pip)")
    if not REQS.exists():
        err(f"Lipseste {REQS}")
        return False
    info(f"Ruleaza: pip install -r {REQS.name} --upgrade")
    r = subprocess.run(
        [PYTHON, "-m", "pip", "install", "-r", str(REQS), "--quiet", "--upgrade"],
        capture_output=True, text=True,
        shell=False,
    )
    if r.returncode != 0:
        err("pip install a esuat:")
        print(r.stderr[-800:])
        return False
    ok("Toate dependentele Python instalate")
    return True


# ─── 4. npm install ───────────────────────────────────────────────────────────

def install_frontend_deps() -> bool:
    hdr("4. Instaleaza dependente frontend (npm install)")
    if not FRONTEND.exists():
        err(f"Directorul frontend/ nu exista la {FRONTEND}")
        return False
    info("Ruleaza: npm install in frontend/")
    # shell=True necesar pe Windows: npm este npm.cmd, gasit doar daca CMD rezolva extensiile
    r = subprocess.run(
        "npm install",
        cwd=str(FRONTEND),
        capture_output=True, text=True,
        shell=True,
    )
    if r.returncode != 0:
        err("npm install a esuat:")
        print(r.stderr[-800:])
        return False
    ok("Dependente frontend instalate")
    return True


# ─── 5. Directoare + profil standard ─────────────────────────────────────────

def create_dirs_and_profile() -> None:
    hdr("5. Creeaza directoare necesare")
    for d in DATA_DIRS:
        d.mkdir(parents=True, exist_ok=True)
        ok(str(d.relative_to(ROOT)))

    # Profil standard pentru UI — copiat din config/ sau creat minimal
    std_profile = PROFILES / "standard.json"
    if std_profile.exists():
        ok("data/profiles/standard.json exista deja")
        return

    # Incearca sa copieze din config/standard_profile.json (daca exista si are formatul UI)
    # Altfel creaza un profil minimal — sesiunile se configureaza din UI
    src = ROOT / "config" / "standard_profile.json"
    if src.exists():
        try:
            with open(src, encoding="utf-8") as f:
                cfg = json.load(f)
            # Daca are format profil UI (cu 'sessions' ca list de obiecte cu 'session_key')
            sessions = cfg.get("sessions", [])
            if sessions and isinstance(sessions[0], dict) and "session_key" in sessions[0]:
                shutil.copy2(src, std_profile)
                ok("data/profiles/standard.json copiat din config/")
                return
        except Exception:
            pass

    # Creeaza profil minimal — userul il completeaza din UI
    from datetime import datetime
    ts = datetime.now().isoformat(timespec="seconds")
    minimal = {
        "id": "standard",
        "name": "Standard Profile",
        "description": "Configuratia implicita",
        "start_balance": 1000,
        "sessions": [],
        "updated_at": ts,
    }
    with open(std_profile, "w", encoding="utf-8") as f:
        json.dump(minimal, f, indent=2, ensure_ascii=False)
    ok("data/profiles/standard.json creat (gol — configureaza sesiunile din UI)")
    info("NOTA: Telegram se configureaza din UI: Profile → sectiunea Telegram Settings")


# ─── 6. Descarca date MT5 ─────────────────────────────────────────────────────

def download_data() -> bool:
    hdr("6. Descarca date istorice din MT5")
    print("  Necesita MT5 deschis si logat.")
    print("  Apasa ENTER pentru a incepe sau scrie 'skip' pentru a sari: ", end="")
    ans = input().strip().lower()
    if ans == "skip":
        info("Sarit. Ruleaza manual: python scripts/descarca_date.py")
        return True

    scripts = [
        ("scripts/descarca_date.py",         "Forex + indici (M15/M30/H1/D1)"),
        ("scripts/descarca_crypto.py",        "Crypto BTC (M15/M30)"),
        ("scripts/descarca_date_istorice.py", "Date istorice suplimentare"),
    ]

    ok_count = 0
    for rel, label in scripts:
        script = ROOT / rel
        if not script.exists():
            info(f"Lipseste {rel} — skip")
            continue
        info(f"Ruleaza {rel}  ({label})...")
        try:
            r = subprocess.run([PYTHON, str(script)], cwd=str(ROOT), timeout=300)
            if r.returncode == 0:
                ok(label)
                ok_count += 1
            else:
                err(f"{label} — eroare (exit {r.returncode})")
        except subprocess.TimeoutExpired:
            err(f"{label} — timeout dupa 5 minute")

    return ok_count > 0


# ─── 7. Windows autostart (Task Scheduler) ───────────────────────────────────

def setup_autostart() -> bool:
    hdr("7. Windows autostart (Task Scheduler)")
    autostart_ps = ROOT / "scripts" / "setup_autostart.ps1"
    if not autostart_ps.exists():
        err(f"Lipseste {autostart_ps}")
        return False

    print("  Creeaza task-uri Windows pentru pornire automata la login.")
    print("  ATENTIE: necesita privilegii Administrator.")
    print("  Apasa ENTER pentru a continua sau scrie 'skip' pentru a sari: ", end="")
    ans = input().strip().lower()
    if ans == "skip":
        info("Sarit. Ruleaza manual (ca Administrator):")
        info(f"  Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass")
        info(f"  .\\scripts\\setup_autostart.ps1")
        return True

    r = subprocess.run([
        "powershell", "-ExecutionPolicy", "Bypass",
        "-File", str(autostart_ps)
    ], cwd=str(ROOT))

    if r.returncode == 0:
        ok("Autostart configurat (TradingBot-MT5 + TradingBot-RunAll)")
        return True
    else:
        err("setup_autostart.ps1 a esuat sau a fost anulat.")
        info("Incearca manual ca Administrator.")
        return False


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print(SEP)
    print("  TRADING BOT — Setup masina noua")
    print(f"  Director: {ROOT}")
    print(SEP)

    results = {}

    results["python"] = check_python()
    if not results["python"]:
        print("\n  Oprire: Python incompatibil.")
        sys.exit(1)

    results["nodejs"] = check_nodejs()
    if not results["nodejs"]:
        print("\n  ATENTIE: fara Node.js frontend-ul nu va porni.")
        print("  Continui oricum? (y/n): ", end="")
        if input().strip().lower() != "y":
            sys.exit(1)

    results["pip"]      = install_python_deps()
    results["npm"]      = install_frontend_deps()
    create_dirs_and_profile()
    results["data"]     = download_data()
    results["autostart"]= setup_autostart()

    # Sumar final
    hdr("SUMAR")
    checks = [
        ("Python 3.10+",        results["python"]),
        ("Node.js 18+",         results["nodejs"]),
        ("Dependente Python",   results["pip"]),
        ("Dependente frontend", results["npm"]),
        ("Date MT5",            results["data"]),
        ("Windows autostart",   results["autostart"]),
    ]
    all_ok = True
    for label, passed in checks:
        icon = "OK " if passed else "!! "
        col  = "" if passed else ""
        print(f"  [{icon}] {label}")
        if not passed:
            all_ok = False

    print()
    if all_ok:
        print("  Setup complet! Pasi urmatori:")
    else:
        print("  Setup partial. Verifica erorile de mai sus. Pasi urmatori:")
    print()
    print("  1. Deschide MetaTrader 5 si conecteaza-te pe cont demo")
    print("  2. Porneste aplicatia web:")
    print()
    print("     Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass")
    print("     .\\start_app.ps1")
    print()
    print("  3. Deschide http://localhost:5173")
    print("  4. In Profile → Telegram Settings configureaza token + chat ID")
    print("  5. Porneste botul din Dashboard (butonul Start)")
    print(SEP)


if __name__ == "__main__":
    main()
