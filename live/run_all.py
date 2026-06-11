"""
run_all.py — Lansator + monitor toate sesiunile
================================================
Porneste S1+S2+S3+S4 simultan si afiseaza status la fiecare 5 minute.
Fiecare sesiune ruleaza independent si scrie in propriul log.
Ctrl+C opreste toate sesiunile simultan.

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
        label="S2  FX Both  (6 perechi)",
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
        label="S4  GER40+US30",
        script=os.path.join(ROOT, "live", "session4_obs.py"),
        sig_dir=os.path.join(DATA_DIR, "live_signals", "session4"),
        hours="09-21h UTC",
        validated=True,
    ),
    dict(
        id="S5",
        label="S5  GER40+USDCHF H1  [OBS]",
        script=os.path.join(ROOT, "live", "session5_ger40_h1.py"),
        sig_dir=os.path.join(DATA_DIR, "live_signals", "session5"),
        hours="07-16h UTC",
        validated=False,
    ),
]

STATUS_INTERVAL = 300   # afiseaza status la fiecare 5 minute


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
            )
            sp_list.append((s, proc))
            tag = "" if s["validated"] else "  [OBSERVARE]"
            print(f"  [+] {s['id']} pornit  PID={proc.pid:<7}  {s['hours']}{tag}")
        except Exception as e:
            print(f"  [!] {s['id']}: eroare pornire — {e}")

    if not sp_list:
        print("  Nicio sesiune pornita. Iesire.")
        return

    n = len(sp_list)
    print(f"\n  {n} sesiune{'a' if n==1 else 'i'} pornite. "
          f"Status la fiecare {STATUS_INTERVAL // 60} min. Ctrl+C pentru oprire.\n")

    lines = "\n".join(
        f"  • {s['label']}  ({s['hours']})"
        + ("  [obs]" if not s["validated"] else "")
        for s, _ in sp_list
    )
    _send_telegram(
        f"<b>Trading Bot pornit</b>  {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        f"{n} sesiuni active:\n{lines}"
    )

    # Handler Ctrl+C — opreste toate procesele copil
    def _stop_all(sig=None, frame=None):
        print("\n\n  Oprire sesiuni...")
        for _, proc in sp_list:
            if proc.poll() is None:
                proc.terminate()
        for _, proc in sp_list:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        print("  Toate sesiunile oprite.\n")
        sys.exit(0)

    signal.signal(signal.SIGINT,  _stop_all)
    signal.signal(signal.SIGTERM, _stop_all)

    # Status initial + loop
    _print_status(sp_list)

    while True:
        time.sleep(STATUS_INTERVAL)
        _print_status(sp_list)


if __name__ == "__main__":
    main()
