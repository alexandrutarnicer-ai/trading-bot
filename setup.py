"""
setup.py — Instalare automata trading bot pe masina noua
=========================================================
Ruleaza o singura data dupa `git clone`.

Automatizeaza:
  1. Verifica Python >= 3.10
  2. pip install -r requirements.txt
  3. Creeaza directoarele necesare (data/, live_signals/, etc.)
  4. Configureaza .env (cere token/chat_id daca lipsesc)
  5. Testeaza conexiunea Telegram
  6. Descarca date istorice din MT5 (necesita MT5 pornit + logat)
  7. Adauga bot la Windows autostart (Task Scheduler, la login)

Necesita interventie manuala INAINTE:
  - Python 3.10+ instalat
  - MT5 instalat, deschis si logat pe contul demo
  - git clone <repo> facut deja
"""

import os
import sys
import json
import time
import shutil
import subprocess
import urllib.request
from pathlib import Path

ROOT    = Path(__file__).parent.resolve()
PYTHON  = sys.executable
BAT     = ROOT / "live" / "start_bot.bat"
ENV_FILE = ROOT / ".env"
REQS    = ROOT / "requirements.txt"

SEP  = "=" * 60
sep2 = "-" * 60

DATA_DIRS = [
    ROOT / "data",
    ROOT / "data" / "live_signals" / "session1",
    ROOT / "data" / "live_signals" / "session2",
    ROOT / "data" / "live_signals" / "session3",
    ROOT / "data" / "live_signals" / "session4",
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
        return False
    ok("Versiune Python OK")
    return True


# ─── 2. pip install ───────────────────────────────────────────────────────────

def install_deps() -> bool:
    hdr("2. Instaleaza dependente (pip)")
    if not REQS.exists():
        err(f"Lipseste {REQS}")
        return False
    info(f"Ruleaza: pip install -r {REQS.name}")
    r = subprocess.run(
        [PYTHON, "-m", "pip", "install", "-r", str(REQS), "--quiet"],
        capture_output=True, text=True
    )
    if r.returncode != 0:
        err("pip install a esuat:")
        print(r.stderr[-800:])
        return False
    ok("Toate dependentele instalate")
    return True


# ─── 3. Directoare ────────────────────────────────────────────────────────────

def create_dirs() -> None:
    hdr("3. Creeaza directoare")
    for d in DATA_DIRS:
        d.mkdir(parents=True, exist_ok=True)
        ok(str(d.relative_to(ROOT)))


# ─── 4. .env ─────────────────────────────────────────────────────────────────

def setup_env() -> bool:
    hdr("4. Configureaza .env (Telegram)")

    if ENV_FILE.exists():
        tok, cid = _read_env()
        if tok and cid:
            ok(f".env exista si are TOKEN + CHAT_ID={cid}")
            return True
        info(".env exista dar lipsesc valorile — il completez.")

    # Citeste din registry Windows (daca sunt deja setate pe aceasta masina)
    tok = _reg_env("TELEGRAM_TOKEN")
    cid = _reg_env("TELEGRAM_CHAT_ID")

    if tok and cid:
        info("Gasit in registry Windows — copiez in .env.")
    else:
        print()
        print("  Introdu credentialele Telegram.")
        print("  (Gasesti TOKEN-ul la @BotFather, CHAT_ID la @userinfobot)")
        print()
        if not tok:
            tok = input("  TELEGRAM_TOKEN  : ").strip()
        if not cid:
            cid = input("  TELEGRAM_CHAT_ID: ").strip()

    if not tok or not cid:
        err("Credentialele lipsesc — sari peste Telegram.")
        return False

    ENV_FILE.write_text(
        "# Telegram bot credentials\n"
        "# NU commitati acest fisier in git!\n"
        f"TELEGRAM_TOKEN={tok}\n"
        f"TELEGRAM_CHAT_ID={cid}\n",
        encoding="utf-8",
    )
    ok(f".env creat la {ENV_FILE}")
    return True


def _read_env():
    tok = cid = ""
    if not ENV_FILE.exists():
        return tok, cid
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("TELEGRAM_TOKEN="):
            tok = line.split("=", 1)[1]
        elif line.startswith("TELEGRAM_CHAT_ID="):
            cid = line.split("=", 1)[1]
    return tok, cid


def _reg_env(name: str) -> str:
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment")
        v, _ = winreg.QueryValueEx(k, name)
        return v
    except Exception:
        return ""


# ─── 5. Test Telegram ─────────────────────────────────────────────────────────

def test_telegram() -> bool:
    hdr("5. Testeaza Telegram")
    tok, cid = _read_env()
    if not tok or not cid:
        info("Credentialele lipsesc din .env — skip.")
        return False
    try:
        payload = json.dumps({
            "chat_id": cid,
            "text": "<b>Trading Bot — setup nou</b>\nInstalare reusita pe aceasta masina!",
            "parse_mode": "HTML",
        }).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{tok}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
        ok(f"Telegram OK — message_id={data['result']['message_id']}")
        return True
    except urllib.request.HTTPError as e:
        err(f"Telegram HTTP {e.code}: {e.read().decode()[:200]}")
    except Exception as e:
        err(f"Telegram eroare retea: {e}")
    return False


# ─── 6. Descarca date MT5 ─────────────────────────────────────────────────────

def download_data() -> bool:
    hdr("6. Descarca date istorice din MT5")
    print("  Necesita MT5 deschis si logat.")
    print("  Apasa ENTER pentru a incepe sau 'skip' pentru a sari: ", end="")
    ans = input().strip().lower()
    if ans == "skip":
        info("Sarit. Ruleaza manual: python scripts/descarca_date.py")
        return True

    scripts = [
        ("scripts/descarca_date.py",          "Forex + indici (M15/M30/H1/D1)"),
        ("scripts/descarca_crypto.py",         "Crypto BTC/ETH/BNB/SOL/XRP (M15/M30)"),
        ("scripts/descarca_date_istorice.py",  "Date istorice suplimentare"),
    ]

    ok_count = 0
    for rel, label in scripts:
        script = ROOT / rel
        if not script.exists():
            info(f"  Lipseste {rel} — skip")
            continue
        info(f"  Ruleaza {rel}  ({label})...")
        r = subprocess.run([PYTHON, str(script)], cwd=str(ROOT), timeout=300)
        if r.returncode == 0:
            ok(label)
            ok_count += 1
        else:
            err(f"{label} — eroare (exit {r.returncode})")

    return ok_count > 0


# ─── 7. Windows autostart (Task Scheduler) ───────────────────────────────────

def setup_autostart() -> bool:
    hdr("7. Windows autostart (Task Scheduler)")

    if not BAT.exists():
        err(f"Lipseste {BAT}")
        return False

    task_name = "TradingBot_Autostart"

    # Sterge task existent daca exista
    subprocess.run(
        ["schtasks", "/delete", "/tn", task_name, "/f"],
        capture_output=True
    )

    # Creeaza task nou: ruleaza start_bot.bat la logon
    r = subprocess.run([
        "schtasks", "/create",
        "/tn",      task_name,
        "/tr",      f'"{BAT}"',
        "/sc",      "ONLOGON",
        "/delay",   "0001:00",   # delay 1 minut dupa logon
        "/rl",      "HIGHEST",
        "/f",
    ], capture_output=True, text=True)

    if r.returncode != 0:
        err(f"schtasks eroare: {r.stderr.strip()[:200]}")
        info("Alternativa manuala: Task Scheduler > Creare task > La logon > start_bot.bat")
        return False

    ok(f"Task '{task_name}' creat — pornire automata la logon")
    return True


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print(SEP)
    print("  TRADING BOT — Setup masina noua")
    print(f"  Director: {ROOT}")
    print(SEP)

    results = {}

    results["python"]    = check_python()
    if not results["python"]:
        print("\n  Oprire: Python incompatibil.")
        sys.exit(1)

    results["deps"]      = install_deps()
    create_dirs()
    results["env"]       = setup_env()
    results["telegram"]  = test_telegram()
    results["data"]      = download_data()
    results["autostart"] = setup_autostart()

    # Sumar final
    hdr("SUMAR")
    checks = [
        ("Python 3.10+",           results["python"]),
        ("Dependente pip",         results["deps"]),
        (".env Telegram",          results["env"]),
        ("Test Telegram",          results["telegram"]),
        ("Date MT5 descarcate",    results["data"]),
        ("Windows autostart",      results["autostart"]),
    ]
    all_ok = True
    for label, passed in checks:
        icon = "OK " if passed else "!! "
        print(f"  [{icon}] {label}")
        if not passed:
            all_ok = False

    print()
    if all_ok:
        print("  Setup complet! Porneste botul cu: live\\start_bot.bat")
    else:
        print("  Setup partial. Verifica erorile de mai sus.")
        print("  Dupa rezolvare poti rula din nou setup.py — sare peste ce e deja facut.")
    print(SEP)


if __name__ == "__main__":
    main()
