"""
run_all.py — Lansator + monitor toate sesiunile
================================================
Porneste S1–S6 simultan si afiseaza status la fiecare 5 minute.
Fiecare sesiune ruleaza independent si scrie in propriul log.
Ctrl+C opreste toate sesiunile simultan.

Sesiuni active:
  S1  FX Long  EURUSD/GBPUSD/EURJPY  M15  10-18h  validated
  S2  JPY Both  USDJPY/AUDJPY/NZDJPY  M15  02-10h  validated  (EUR pairs -> S1)
  S3  BTC Both                       M15  00-09h+15-18h  validated
  S4  GER40    LONG                  M15  09-14h  demo
  S5  GER40+USDCHF  LONG             H1   07-17h  demo
  S6  US30     LONG                  M15  13-21h  demo

Rulare:  python live/run_all.py
Loguri:  data/live_signals/sessionX/generator.log
"""

import os
import sys
import csv
import json
import time
import signal
import subprocess
import urllib.request
from datetime import datetime, date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from backtest import DATA_DIR
from live.news_guard import start_guard, clear_all as news_clear_all

PID_FILE = os.path.join(DATA_DIR, "run_all.pid")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SESSIONS = [
    dict(
        id="S1",
        label="S1  FX Long  (EUR/GBP/JPY)",
        script=os.path.join(ROOT, "live", "session1_m15_long.py"),
        sig_dir=os.path.join(DATA_DIR, "live_signals", "session1"),
        hours="10-18h UTC",
        validated=True,
    ),
    dict(
        id="S2",
        label="S2  JPY Both  (3 perechi)",
        script=os.path.join(ROOT, "live", "session2_m5_both.py"),
        sig_dir=os.path.join(DATA_DIR, "live_signals", "session2"),
        hours="02-18h UTC",
        validated=True,
    ),
    dict(
        id="S3",
        label="S3  BTC Both",
        script=os.path.join(ROOT, "live", "session3_btc_both.py"),
        sig_dir=os.path.join(DATA_DIR, "live_signals", "session3"),
        hours="00-09h + 15-18h UTC",
        validated=True,
    ),
    dict(
        id="S4",
        label="S4  GER40",
        script=os.path.join(ROOT, "live", "session4_obs.py"),
        sig_dir=os.path.join(DATA_DIR, "live_signals", "session4"),
        hours="09-14h UTC",
        validated=True,
    ),
    dict(
        id="S5",
        label="S5  GER40+USDCHF H1",
        script=os.path.join(ROOT, "live", "session5_ger40_h1.py"),
        sig_dir=os.path.join(DATA_DIR, "live_signals", "session5"),
        hours="07-17h UTC",
        validated=True,
    ),
    dict(
        id="S6",
        label="S6  US30 M15 Long",
        script=os.path.join(ROOT, "live", "session6_us30_m15.py"),
        sig_dir=os.path.join(DATA_DIR, "live_signals", "session6"),
        hours="13-21h UTC",
        validated=True,
    ),
]

STATUS_INTERVAL = 300   # afiseaza status la fiecare 5 minute

RUNTIME_PROFILE = os.path.join(DATA_DIR, "active_profile_runtime.json")


def _load_news_guard_configs() -> list[dict]:
    """
    Citeste profilul activ si returneaza sesiunile cu news_protection_enabled=True.
    Fara profil activ (bot pornit direct din CLI) returneaza lista goala.
    """
    if not os.path.exists(RUNTIME_PROFILE):
        return []
    try:
        with open(RUNTIME_PROFILE, encoding="utf-8") as f:
            profile = json.load(f)
        configs = []
        for s in profile.get("sessions", []):
            if not s.get("news_protection_enabled", False):
                continue
            configs.append({
                "session_key":           s.get("session_key", ""),
                "markets":               s.get("markets", []),
                "news_protection_enabled": True,
                "news_impact_level":     s.get("news_impact_level", 3),
                "news_pre_minutes":      s.get("news_pre_minutes", 15),
                "news_post_minutes":     s.get("news_post_minutes", 15),
            })
        return configs
    except Exception as e:
        print(f"  [!] News Guard: eroare citire profil — {e}")
        return []


def _kill_old_instance() -> None:
    """Ucide instanta run_all deja pornita, impreuna cu toate sesiunile copil."""
    if not os.path.exists(PID_FILE):
        return
    try:
        with open(PID_FILE) as f:
            old_pid = int(f.read().strip())
    except (ValueError, OSError):
        try:
            os.remove(PID_FILE)
        except OSError:
            pass
        return

    if old_pid == os.getpid():
        return

    print(f"\n  [!] Instanta anterioara detectata (PID={old_pid}). Inchid procesul si sesiunile...")
    result = subprocess.run(
        ["taskkill", "/F", "/T", "/PID", str(old_pid)],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        print(f"  [+] PID={old_pid} oprit cu succes. Astept 3s curatare...")
        _send_telegram(
            f"⚠️ <b>Trading Bot repornit</b>  {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
            f"Instanta anterioara (PID={old_pid}) a fost inchisa automat."
        )
        time.sleep(3)
    else:
        # Procesul nu mai era activ — PID file ramas din sesiune anterioara
        print(f"  [~] PID={old_pid} nu mai era activ (bot era deja oprit).")

    try:
        os.remove(PID_FILE)
    except OSError:
        pass


def _load_dotenv() -> None:
    """Incarca .env din radacina proiectului fara a suprascrie variabile deja setate."""
    env_path = os.path.join(ROOT, ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip())


_load_dotenv()

_TG_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
_TG_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


def _send_telegram(text: str) -> None:
    if not _TG_TOKEN or not _TG_CHAT_ID:
        return
    try:
        payload = json.dumps({
            "chat_id": _TG_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
        }).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{_TG_TOKEN}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sig_stats(sig_dir):
    """Returneaza (semnale_azi, ultima_ora, total_all_time)."""
    f = os.path.join(sig_dir, "signals.csv")
    if not os.path.exists(f):
        return 0, "-", 0
    today      = str(date.today())
    count_azi  = 0
    total      = 0
    last_ora   = "-"
    try:
        with open(f, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                total += 1
                t = row.get("time", "")
                if t.startswith(today):
                    count_azi += 1
                    last_ora = t[11:16]   # HH:MM
    except Exception:
        pass
    return count_azi, last_ora, total


def _print_status(sp_list):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sep = "=" * 74
    print(f"\n{sep}")
    print(f"  TRADING BOT  —  STATUS  |  {now}")
    print(sep)
    print(f"  {'Sesiune':<28} {'Status':<8} {'PID':>7}  {'Azi':>4}  {'Total':>6}  Ultima")
    print(f"  {'-'*70}")

    total_azi = 0
    for s, proc in sp_list:
        alive  = proc.poll() is None
        status = "ACTIV" if alive else "OPRIT"
        icon   = "+" if alive else "!"
        pid    = str(proc.pid) if alive else "—"
        azi, last, total = _sig_stats(s["sig_dir"])
        total_azi += azi
        obs_tag = " [obs]" if not s["validated"] else ""
        print(
            f"  [{icon}] {s['label']:<26} {status:<8} {pid:>7}"
            f"  {azi:>4}  {total:>6}  {last}{obs_tag}"
        )

    print(f"  {'-'*70}")
    print(f"  Total semnale azi: {total_azi}")
    print(f"  Loguri: data/live_signals/sessionX/generator.log")
    print(f"  Ctrl+C opreste toate")
    print(f"{sep}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    _kill_old_instance()

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))

    sep = "=" * 74
    print(sep)
    print("  TRADING BOT  —  LANSARE SESIUNI")
    print(sep)

    sp_list = []

    for s in SESSIONS:
        if not os.path.exists(s["script"]):
            print(f"  [!] {s['id']}: script negasit — {s['script']}")
            continue
        try:
            proc = subprocess.Popen(
                [sys.executable, s["script"]],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            sp_list.append((s, proc))
            tag = "" if s["validated"] else "  [OBSERVARE]"
            print(f"  [+] {s['id']} pornit  PID={proc.pid:<7}  {s['hours']}{tag}")
        except Exception as e:
            print(f"  [!] {s['id']}: eroare pornire — {e}")

    if not sp_list:
        print("  Nicio sesiune pornita. Iesire.")
        return

    # Porneste News Guard daca cel putin o sesiune are protectie activa
    guard_configs = _load_news_guard_configs()
    if guard_configs:
        start_guard(guard_configs, _send_telegram)
        print(f"  [+] News Guard pornit — {len(guard_configs)} sesiuni monitorizate")
    else:
        print("  [~] News Guard inactiv (nicio sesiune cu protectie la stiri configurata)")

    n = len(sp_list)
    print(f"\n  {n} sesiune{'a' if n==1 else 'i'} pornite. "
          f"Status la fiecare {STATUS_INTERVAL // 60} min. Ctrl+C pentru oprire.\n")

    # Cand e pornit din UI (bot.py seteaza BOT_API_START=1), API-ul trimite
    # deja mesajul de start cu profilul si sesiunile → nu mai trimitem al doilea.
    if not os.environ.get("BOT_API_START"):
        lines = "\n".join(
            f"  • {s['label']}  ({s['hours']})"
            + ("  [obs]" if not s["validated"] else "")
            for s, _ in sp_list
        )
        _send_telegram(
            f"<b>Trading Bot pornit</b>  {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
            f"{n} sesiuni active:\n{lines}"
        )

    # Handler Ctrl+C / SIGTERM / restart Windows — opreste toate procesele copil
    def _stop_all(sig=None, frame=None):
        motiv = "Oprire manuala (Ctrl+C)" if sig == signal.SIGINT else "SIGTERM / restart sistem"
        _send_telegram(
            f"⚠️ <b>Trading Bot oprit</b>  {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
            f"{motiv}"
        )
        print("\n\n  Oprire sesiuni...")
        for _, proc in sp_list:
            if proc.poll() is None:
                proc.terminate()
        for _, proc in sp_list:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        news_clear_all()   # sterge news_auto_paused.json la oprire
        print("  Toate sesiunile oprite.\n")
        try:
            os.remove(PID_FILE)
        except OSError:
            pass
        sys.exit(0)

    signal.signal(signal.SIGINT,  _stop_all)
    signal.signal(signal.SIGTERM, _stop_all)
    try:
        signal.signal(signal.SIGBREAK, _stop_all)   # Ctrl+Break / restart Windows
    except (OSError, AttributeError):
        pass

    # Status initial + loop
    _print_status(sp_list)

    while True:
        time.sleep(STATUS_INTERVAL)
        _print_status(sp_list)


if __name__ == "__main__":
    main()
