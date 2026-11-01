"""
Curatarea saptamanala a datelor AI fara trade (luni, de la 12:00 — din scheduler-ul API).

REGULA (decizie Trader + BA, 2026-10-31):
  • Tot ce tine de un trade PLASAT ramane INTEGRAL (decizie, consiliu, transcript,
    snapshot, outcome, verdict filtru AI aprobat).
  • Pentru analizele care NU au produs un trade si sunt MAI VECHI de RETENTION_DAYS,
    se sterge doar PARTEA GREA (textul): transcriptul consiliului, snapshot-ul de
    piata, transcriptul verdictului filtrului AI respins. Randul compact ramane
    (cand, ce piata, ce trigger, ce a decis, de ce — o propozitie).

DE CE nu stergem tot ce n-a dus la trade: randurile compacte sunt singura sursa
pentru evaluarea AI (ex. 2026-10-31: trigger-ul breakout = 76% din consilii si
-0.24R; rolurile Quant/Devil scadeau aprobarea 12%→4-6%; contrafactualul semnalelor
respinse de filtru). Si mai multe componente DEPIND de ele: cooldown-ul consiliului
(ultimele consilii), dedup-ul semnalelor (signals.csv), contorul de ID-uri al
semnalelor (citit din signals.csv la restart — stergerea ar putea REFOLOSI ID-uri,
deci asocieri gresite cu ordine MT5 vechi), recuperarea dupa restart (outcomes.csv,
10 zile). De aceea signals.csv / outcomes.csv NU se ating (0.1 MB in 3 luni).

Rulare manuala:  python -m api.data_cleanup [--apply]   (implicit dry-run)
"""
from __future__ import annotations

import glob
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(_ROOT, "data")
LEDGER = os.path.join(DATA_DIR, "ai", "ledger.db")
MARKER = os.path.join(DATA_DIR, "ai", "cleanup_last_run.json")
RETENTION_DAYS = 28
_PRUNED = '{"_pruned": true}'


def _cutoff(now: datetime | None = None, days: int = RETENTION_DAYS) -> str:
    return ((now or datetime.now()) - timedelta(days=days)).isoformat(timespec="seconds")


def prune_ledger(db_path: str = LEDGER, cutoff: str | None = None, apply: bool = False) -> dict:
    """Golesc transcripturile + snapshot-urile consiliilor FARA ordin plasat, mai vechi de cutoff."""
    cutoff = cutoff or _cutoff()
    out = {"councils": 0, "snapshots": 0, "bytes": 0}
    if not os.path.exists(db_path):
        return out
    con = sqlite3.connect(db_path, timeout=30)
    try:
        # consilii fara NICIO decizie plasata (placed) — inclusiv cele fara decizie
        q_c = ("FROM councils k WHERE k.ts < ? AND k.transcript != ? AND NOT EXISTS ("
               "SELECT 1 FROM decisions d WHERE d.council_id = k.id AND d.exec_status = 'placed')")
        n, b = con.execute(f"SELECT COUNT(*), COALESCE(SUM(LENGTH(k.transcript)),0) {q_c}",
                           (cutoff, _PRUNED)).fetchone()
        # snapshot-uri folosite DOAR de astfel de consilii (niciun consiliu cu trade nu le refera)
        q_s = ("FROM snapshots s WHERE s.ts < ? AND s.data != ? AND NOT EXISTS ("
               "SELECT 1 FROM councils k JOIN decisions d ON d.council_id = k.id "
               "WHERE k.snapshot_id = s.id AND d.exec_status = 'placed')")
        ns, bs = con.execute(f"SELECT COUNT(*), COALESCE(SUM(LENGTH(s.data)),0) {q_s}",
                             (cutoff, _PRUNED)).fetchone()
        out.update(councils=int(n), snapshots=int(ns), bytes=int(b) + int(bs))
        if apply and (n or ns):
            with con:
                con.execute(f"UPDATE councils SET transcript = ? WHERE id IN (SELECT k.id {q_c})",
                            (_PRUNED, cutoff, _PRUNED))
                con.execute(f"UPDATE snapshots SET data = ? WHERE id IN (SELECT s.id {q_s})",
                            (_PRUNED, cutoff, _PRUNED))
    finally:
        con.close()
    return out


def prune_ai_filter_logs(data_dir: str = DATA_DIR, cutoff: str | None = None,
                         apply: bool = False) -> dict:
    """In ai_filter.jsonl: verdictele RESPINSE mai vechi de cutoff pierd transcriptul
    (raman: piata, directie, nivel, aprobat/respins, incredere, motivul)."""
    cutoff = cutoff or _cutoff()
    out = {"verdicts": 0, "bytes": 0, "files": 0}
    for path in glob.glob(os.path.join(data_dir, "live_signals", "session*", "ai_filter.jsonl")):
        lines = open(path, encoding="utf-8", errors="ignore").read().splitlines()
        new, changed = [], 0
        for line in lines:
            try:
                v = json.loads(line)
            except Exception:
                new.append(line)
                continue
            heavy = v.get("transcript") or any((c or {}).get("transcript") for c in v.get("councils") or [])
            if (heavy and not v.get("approved", True) and str(v.get("time", "")) < cutoff):
                before = len(line)
                v["transcript"] = {}
                v["councils"] = [{k: x for k, x in (c or {}).items() if k != "transcript"}
                                 for c in v.get("councils") or []]
                v["_pruned"] = True
                line = json.dumps(v, ensure_ascii=False, default=str)
                out["bytes"] += before - len(line)
                changed += 1
            new.append(line)
        if changed:
            out["verdicts"] += changed
            out["files"] += 1
            if apply:
                tmp = path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    f.write("\n".join(new) + "\n")
                os.replace(tmp, path)
    return out


def _engine_running_here(pid_file: str) -> bool:
    """Engine-ul ruleaza pe ACEASTA masina (PID din fisier, proces viu)."""
    try:
        pid = int(open(pid_file, encoding="utf-8").read().strip())
    except Exception:
        return False
    try:
        from api.routers.bot import _pid_alive
        return _pid_alive(pid)
    except Exception:
        return False


def local_engines() -> dict:
    """Ce engine-uri ruleaza aici. ledger.db + ai_filter.jsonl sunt SINCRONIZATE prin git
    (alex-live, PC <-> laptop): daca masina care DOAR afiseaza (fara engine) le-ar compacta,
    fisierele urmarite s-ar modifica local → `git pull` refuza / un push ar suprascrie datele
    mai noi ale celeilalte masini. Deci fiecare masina compacteaza doar datele propriilor engine-uri."""
    return {"ai": _engine_running_here(os.path.join(DATA_DIR, "ai", "ai_engine.pid")),
            "bot": _engine_running_here(os.path.join(DATA_DIR, "run_all.pid"))}


_EMPTY_LEDGER = {"councils": 0, "snapshots": 0, "bytes": 0}
_EMPTY_FILTER = {"verdicts": 0, "bytes": 0, "files": 0}


def run_cleanup(apply: bool = True, now: datetime | None = None, local_only: bool = False,
                engines: dict | None = None) -> dict:
    """local_only (scheduler-ul API) = doar datele engine-urilor care ruleaza pe aceasta masina.
    Rularea manuala (CLI) ramane pe tot."""
    cutoff = _cutoff(now)
    eng = (engines if engines is not None else local_engines()) if local_only else {"ai": True, "bot": True}
    rep = {"cutoff": cutoff, "apply": apply, "engines": eng,
           "ledger": prune_ledger(cutoff=cutoff, apply=apply) if eng["ai"] else dict(_EMPTY_LEDGER),
           "ai_filter": prune_ai_filter_logs(cutoff=cutoff, apply=apply) if eng["bot"] else dict(_EMPTY_FILTER)}
    rep["freed_mb"] = round((rep["ledger"]["bytes"] + rep["ai_filter"]["bytes"]) / 1e6, 2)
    if apply:
        try:
            os.makedirs(os.path.dirname(MARKER), exist_ok=True)
            json.dump({"last_run": (now or datetime.now()).isoformat(timespec="seconds"), **rep},
                      open(MARKER, "w", encoding="utf-8"), indent=1)
        except Exception:
            pass
    return rep


def due(now: datetime | None = None) -> bool:
    """Luni de la 12:00, o singura data pe saptamana (catch-up daca API porneste mai tarziu luni)."""
    now = now or datetime.now()
    if now.weekday() != 0 or now.hour < 12:
        return False
    try:
        last = datetime.fromisoformat(json.load(open(MARKER, encoding="utf-8"))["last_run"])
    except Exception:
        return True
    return last.date() < now.date()


def summary_text(rep: dict) -> str:
    led, af = rep["ledger"], rep["ai_filter"]
    return (f"🧹 <b>Curățare date AI (fără trade, > {RETENTION_DAYS} zile)</b>\n"
            f"Consilii fără ordin: {led['councils']} transcripturi golite · snapshot-uri: {led['snapshots']}\n"
            f"Filtru AI: {af['verdicts']} verdicte respinse compactate ({af['files']} sesiuni)\n"
            f"Spațiu eliberat ~{rep['freed_mb']} MB. Trade-urile plasate și rândurile de statistică "
            f"rămân integral.")


if __name__ == "__main__":
    r = run_cleanup(apply="--apply" in sys.argv)
    print(json.dumps(r, indent=1))
