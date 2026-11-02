"""
Setup UNIC al aplicatiei (partea Python) - apelat de setup.bat dupa ce Python / Node.js / Git exista.
Idempotent: se poate rula oricand din nou (nu suprascrie nicio configurare, profil sau date existente).

  py scripts\\setup_app.py               # interactiv (intreaba doar de AI Engine / Ollama)
  py scripts\\setup_app.py --with-ai     # + Ollama + modelul AI Engine (fara intrebari)
  py scripts\\setup_app.py --no-ai       # fara AI Engine
  py scripts\\setup_app.py --check       # doar verifica (nu instaleaza nimic)

Pasi: 1) versiuni Python / Node / Git  2) dependente Python  3) dependente frontend  4) directoare + configurari
implicite  5) configurari existente valide (JSON)  6) MetaTrader 5 (doar CITIRE)  7) AI Engine (optional)
8) verificare finala (importuri, frontend, porturi) -> sumar: GATA / ce lipseste si cum se repara.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import socket
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
try:                                     # consola Windows (cp1252): nimic nu are voie sa opreasca setup-ul
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass
PY_MIN = (3, 10)
# Vite 8 cere Node ^20.19 sau >=22.12 (frontend/node_modules/vite/package.json -> engines)
NODE_OK = lambda v: (v[0] == 20 and v[1] >= 19) or (v[0] == 22 and v[1] >= 12) or v[0] >= 23  # noqa: E731
NODE_MIN_TXT = "20.19 sau 22.12+"

RESULTS: list[tuple[str, str, str]] = []          # (pas, stare OK/WARN/FAIL, detaliu)


def say(msg: str = "") -> None:
    print(msg, flush=True)


def result(step: str, state: str, detail: str = "") -> None:
    RESULTS.append((step, state, detail))
    icon = {"OK": "[OK]  ", "WARN": "[ATENTIE]", "FAIL": "[EROARE]"}[state]
    say(f"  {icon} {step}" + (f" - {detail}" if detail else ""))


def run(cmd, cwd=None, shell=False, quiet=False) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, cwd=cwd or ROOT, shell=shell, capture_output=quiet, text=True)
        return r.returncode, ((r.stdout or "") + (r.stderr or "")) if quiet else ""
    except FileNotFoundError as e:
        return 127, str(e)


def parse_version(text: str) -> tuple[int, ...] | None:
    import re
    m = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", text or "")
    return tuple(int(x) for x in m.groups() if x is not None) if m else None


# ── 1. Versiuni ───────────────────────────────────────────────────────────────

def check_versions() -> bool:
    say("\n[1/8] Versiuni Python / Node.js / Git")
    ok = True
    if sys.version_info[:2] >= PY_MIN:
        result("Python", "OK", sys.version.split()[0])
    else:
        result("Python", "FAIL", f"{sys.version.split()[0]} - necesar >= {PY_MIN[0]}.{PY_MIN[1]} (setup.bat il instaleaza)")
        ok = False
    code, out = run("node --version", shell=True, quiet=True)
    v = parse_version(out) if code == 0 else None
    if v and NODE_OK(v):
        result("Node.js", "OK", out.strip())
    elif v:
        result("Node.js", "FAIL", f"{out.strip()} - Vite cere {NODE_MIN_TXT}: winget upgrade OpenJS.NodeJS.LTS")
        ok = False
    else:
        result("Node.js", "FAIL", "negasit - ruleaza setup.bat (il instaleaza)")
        ok = False
    code, out = run("git --version", shell=True, quiet=True)
    result("Git", "OK" if code == 0 else "WARN", out.strip() if code == 0 else "negasit (necesar doar pentru update-uri)")
    return ok


# ── 2-3. Dependente ───────────────────────────────────────────────────────────

def missing_python_deps() -> list[str]:
    import importlib.util
    names = {"pandas": "pandas", "numpy": "numpy", "MetaTrader5": "MetaTrader5", "fastapi": "fastapi",
             "uvicorn": "uvicorn", "pydantic": "pydantic", "scipy": "scipy", "dotenv": "python-dotenv", "tzdata": "tzdata"}
    return [pkg for mod, pkg in names.items() if importlib.util.find_spec(mod) is None]


def install_python(check_only: bool) -> bool:
    say("\n[2/8] Dependente Python (requirements.txt)")
    if not check_only:
        run([sys.executable, "-m", "pip", "install", "--upgrade", "pip", "--quiet"])
        code, out = run([sys.executable, "-m", "pip", "install", "-r", os.path.join(ROOT, "requirements.txt"), "--quiet"], quiet=True)
        if code != 0:
            result("pip install", "FAIL", (out or "").strip().splitlines()[-1:][0] if out else f"cod {code}")
            return False
    miss = missing_python_deps()
    if miss:
        result("Pachete Python", "FAIL", "lipsesc: " + ", ".join(miss) + " - ruleaza setup.bat din nou")
        return False
    result("Pachete Python", "OK", "toate pachetele din requirements.txt")
    return True


def install_frontend(check_only: bool) -> bool:
    say("\n[3/8] Dependente frontend (npm)")
    fe = os.path.join(ROOT, "frontend")
    if not check_only:
        # npm = npm.cmd pe Windows -> shell=True obligatoriu
        code, out = run("npm install --no-fund --no-audit", cwd=fe, shell=True, quiet=True)
        if code != 0:
            tail = "\n".join((out or "").strip().splitlines()[-3:])
            result("npm install", "FAIL", tail or f"cod {code}")
            return False
    vite = os.path.join(fe, "node_modules", "vite", "package.json")
    if not os.path.isfile(vite):
        result("Frontend", "FAIL", "node_modules lipsa - ruleaza setup.bat")
        return False
    result("Frontend", "OK", "node_modules instalat")
    return True


# ── 4-5. Directoare, configurari ─────────────────────────────────────────────

def data_dirs(root: str = ROOT) -> list[str]:
    n = len(glob.glob(os.path.join(root, "live", "session*_*.py"))) or 22
    dirs = [os.path.join(root, "data", d) for d in ("profiles", "ai", "daily_engine", "noisy_engine", "research_daily")]
    dirs += [os.path.join(root, "data", "live_signals", f"session{i}") for i in range(1, n + 1)]
    return dirs


def prepare_files(check_only: bool, root: str = ROOT) -> bool:
    """Directoarele de date + configurarile implicite care LIPSESC. Nimic existent nu e suprascris."""
    say("\n[4/8] Directoare + configurari implicite (nimic existent nu e suprascris)")
    made = 0
    for d in data_dirs(root):
        if not os.path.isdir(d):
            made += 1
            if not check_only:
                os.makedirs(d, exist_ok=True)
    result("Directoare de date", "OK" if made == 0 or not check_only else "WARN",
           f"{made} create" if made and not check_only else (f"{made} lipsesc" if made else "toate exista"))
    prof = os.path.join(root, "data", "profiles", "standard.json")
    if os.path.isfile(prof):
        result("Profil Custom Engine (standard)", "OK", "exista")
    else:
        # vine din git (e urmarit pe toate branch-urile); config/standard_profile.json e formatul LEGACY, nu cel din UI
        result("Profil Custom Engine (standard)", "WARN",
               "lipseste data/profiles/standard.json (ar trebui sa vina din git: git checkout -- data/profiles/standard.json)")
    # configurarile engine-urilor: AI / Daily vin din git, Noisy se creeaza la prima pornire (fara fisiere noi aici)
    return True


CONFIG_FILES = ("data/profiles/standard.json", "data/global_settings.json", "ai_engine/config.json",
                "daily_engine/config.json", "noisy_engine/config.json", "data/telegram_config.json",
                "data/live_trading.json", "data/reports_config.json", "data/ai/providers.json")


def validate_configs(root: str = ROOT) -> bool:
    say("\n[5/8] Configurari existente (JSON valid)")
    bad = []
    for rel in CONFIG_FILES:
        p = os.path.join(root, rel)
        if not os.path.isfile(p):
            continue
        try:
            with open(p, encoding="utf-8") as f:
                json.load(f)
        except Exception as e:
            bad.append(f"{rel} ({type(e).__name__})")
    if bad:
        result("Configurari", "FAIL", "fisiere corupte: " + "; ".join(bad) + " - repara-le sau sterge-le (se recreeaza implicit)")
        return False
    result("Configurari", "OK", "toate fisierele de configurare existente se pot citi")
    return True


# ── 6. MetaTrader 5 (doar citire) ────────────────────────────────────────────

def check_mt5() -> None:
    say("\n[6/8] MetaTrader 5 (doar citire: nicio conexiune de tranzactionare)")
    paths = [r"C:\Program Files\MetaTrader 5\terminal64.exe"] + glob.glob(r"C:\Program Files\*\terminal64.exe")
    installed = any(os.path.isfile(p) for p in paths)
    try:
        import MetaTrader5 as mt5
    except Exception:
        result("MT5", "WARN", "pachetul MetaTrader5 lipseste")
        return
    if not mt5.initialize():
        result("MT5", "WARN", ("instalat, dar " if installed else "nu l-am gasit / ") +
               "nu raspunde: deschide MetaTrader 5, logheaza-te, activeaza Algo Trading. "
               "Aplicatia porneste si fara el (dashboard-ul arata MT5 deconectat).")
        return
    try:
        a, t = mt5.account_info(), mt5.terminal_info()
        if a is None:
            result("MT5", "WARN", "terminal pornit, dar niciun cont logat")
        else:
            demo = getattr(a, "trade_mode", None) == 0
            result("MT5", "OK", f"cont {a.login} pe {a.server} ({'DEMO' if demo else 'REAL - engine-urile refuza contul real pana la deblocarea din Settings -> Trading LIVE'})"
                   + ("" if getattr(t, "trade_allowed", True) else " | ATENTIE: Algo Trading OPRIT in MT5"))
    finally:
        mt5.shutdown()


# ── 7. AI Engine (optional) ──────────────────────────────────────────────────

def ollama_exe() -> str | None:
    for p in (os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe"), shutil.which("ollama") or ""):
        if p and os.path.isfile(p):
            return p
    return None


def ai_model() -> str:
    try:
        with open(os.path.join(ROOT, "ai_engine", "config.json"), encoding="utf-8") as f:
            return json.load(f).get("model") or "qwen3:8b"
    except Exception:
        return "qwen3:8b"


def setup_ai(mode: str, check_only: bool) -> None:
    say("\n[7/8] AI Engine (optional: Ollama + model local)")
    exe = ollama_exe()
    if mode == "ask" and not check_only:
        ans = input(f"  Instalez / verific Ollama + modelul {ai_model()} pentru AI Engine? (~5 GB) [d/N]: ").strip().lower()
        mode = "yes" if ans in ("d", "da", "y", "yes") else "no"
    if mode == "no" or (check_only and not exe):
        result("AI Engine", "OK", "Ollama instalat" if exe else "sarit (optional - ruleaza setup.bat --with-ai mai tarziu)")
        return
    if not exe and not check_only:
        say("  Instalez Ollama via winget...")
        code, _ = run("winget install --id Ollama.Ollama -e --silent --accept-package-agreements --accept-source-agreements", shell=True)
        exe = ollama_exe()
    if not exe:
        result("Ollama", "WARN", "nu s-a putut instala - descarca de pe https://ollama.com/download, apoi setup.bat --with-ai")
        return
    result("Ollama", "OK", exe)
    model = ai_model()
    code, out = run([exe, "list"], quiet=True)
    if code != 0:
        subprocess.Popen([exe, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        import time
        time.sleep(5)
        code, out = run([exe, "list"], quiet=True)
    if model.split(":")[0] in (out or "") and model in (out or ""):
        result(f"Model {model}", "OK", "descarcat")
    elif check_only:
        result(f"Model {model}", "WARN", f"lipseste - {exe} pull {model}")
    else:
        say(f"  Descarc modelul {model} (~5 GB, 5-20 min)...")
        code, _ = run([exe, "pull", model])
        result(f"Model {model}", "OK" if code == 0 else "WARN", "descarcat" if code == 0 else f"esuat - {exe} pull {model}")


# ── 8. Verificare finala ─────────────────────────────────────────────────────

def port_state(port: int) -> str:
    with socket.socket() as s:
        s.settimeout(0.5)
        return "ocupat" if s.connect_ex(("127.0.0.1", port)) == 0 else "liber"


def final_check() -> bool:
    say("\n[8/8] Verificare finala")
    code, out = run([sys.executable, "-c", "import api.main, ai_engine.engine, daily_engine.engine, noisy_engine.engine, "
                     "live.signal_generator, m0.robustness; print('ok')"], quiet=True)
    if code == 0 and "ok" in out:
        result("Module aplicatie (API + engine-uri)", "OK", "se incarca fara erori")
        ok = True
    else:
        result("Module aplicatie (API + engine-uri)", "FAIL", (out or "").strip().splitlines()[-1] if out else f"cod {code}")
        ok = False
    for port, name in ((8000, "API"), (5173, "Dashboard")):
        st = port_state(port)
        result(f"Port {port} ({name})", "OK", st + (" (probabil aplicatia deja pornita - start_ui.bat o reporneste)" if st == "ocupat" else ""))
    return ok


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--with-ai", action="store_true")
    ap.add_argument("--no-ai", action="store_true")
    ap.add_argument("--check", action="store_true", help="doar verifica, nu instaleaza nimic")
    a = ap.parse_args(argv)
    say("=" * 64)
    say("  No Trading - setup " + ("(doar verificare)" if a.check else "(prima instalare / reparare)"))
    say(f"  Folder: {ROOT}")
    say("=" * 64)
    required = [check_versions()]
    if required[0]:
        required.append(install_python(a.check))
        required.append(install_frontend(a.check))
    prepare_files(a.check)
    required.append(validate_configs())
    check_mt5()
    setup_ai("yes" if a.with_ai else "no" if a.no_ai else "ask", a.check)
    required.append(final_check())
    say("\n" + "=" * 64)
    fails = [r for r in RESULTS if r[1] == "FAIL"]
    warns = [r for r in RESULTS if r[1] == "WARN"]
    if all(required) and not fails:
        say("  GATA - aplicatia e pregatita.")
        say("  Pornire:   dublu-click start_ui.bat   (API + dashboard + browser la http://localhost:5173)")
        say("  Oprire:    stop_ui.bat (sau inchide ferestrele TradingBotAPI / TradingBotUI)")
        say("  Restart:   start_ui.bat din nou (opreste singur instanta veche)")
        say("  Engine-urile (Custom / AI / Daily / Noisy) se pornesc din Dashboard.")
        if warns:
            say(f"  De verificat ({len(warns)}): " + "; ".join(f"{s}: {d}" for s, _, d in warns))
        say("=" * 64)
        return 0
    say("  SETUP INCOMPLET - de reparat:")
    for s, _, d in fails:
        say(f"   - {s}: {d}")
    say("  Dupa reparare ruleaza din nou setup.bat (e sigur de rulat de mai multe ori).")
    say("=" * 64)
    return 1


if __name__ == "__main__":
    sys.exit(main())
