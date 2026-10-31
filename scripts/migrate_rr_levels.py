"""
Migrare 2026-10-31: R:R pe 3 niveluri fixe per piata + Expire Bars comun = 4.

Pentru fiecare sesiune din mapare scrie nivelul ales in campurile EXISTENTE
(r_base/mid/top/max, inside_bar_r_ratio, flag_r_ratio = R; risc 1% pe toate
treptele si strategiile) + rr_level. Backtest, M0 si live folosesc deja aceste
campuri → zero cod nou de trading. expire_bars = 4 pe TOATE sesiunile.
Face backup al profilului si scrie diff-ul in data/session_changes_log.json.

    python scripts/migrate_rr_levels.py S5=2R S8=3R ...   (sau --file mapping.json)
"""
import json
import os
import shutil
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILE = os.path.join(ROOT, "data", "profiles", "standard.json")
LOG = os.path.join(ROOT, "data", "session_changes_log.json")
LEVELS = {"2R": ("short", 2.0), "3R": ("standard", 3.0), "4R": ("extended", 4.0)}
RISK = 0.01
EXPIRE = 4


def main(argv):
    if argv and argv[0] == "--file":
        mapping = json.load(open(argv[1], encoding="utf-8"))
    else:
        mapping = dict(a.split("=", 1) for a in argv)
    raw = open(PROFILE, encoding="utf-8").read()
    prof = json.loads(raw)
    backup = PROFILE + f".bak-{datetime.now():%Y%m%d-%H%M%S}"
    shutil.copy2(PROFILE, backup)
    log_sessions = []
    for s in prof["sessions"]:
        before = dict(s)
        if s["id"] in mapping:
            level, r = LEVELS[mapping[s["id"]]]
            s["rr_level"] = level
            for k in ("r_base", "r_mid", "r_top", "r_max", "inside_bar_r_ratio", "flag_r_ratio"):
                s[k] = r
            for k in ("risk_pct", "risk_base", "risk_mid", "risk_top", "risk_max",
                      "inside_bar_risk_pct", "flag_risk_pct"):
                s[k] = RISK
        s["expire_bars"] = EXPIRE
        ch = [{"field": k, "from": before.get(k), "to": s.get(k)}
              for k in s if before.get(k) != s.get(k)]
        if ch:
            log_sessions.append({"id": s["id"], "changes": ch})
            print(s["id"], ", ".join(f"{c['field']}: {c['from']}→{c['to']}" for c in ch))
    prof["updated_at"] = datetime.now().isoformat(timespec="seconds")
    open(PROFILE, "w", encoding="utf-8").write(json.dumps(prof, indent=2, ensure_ascii=False) + "\n")
    try:
        log = json.load(open(LOG, encoding="utf-8")) if os.path.exists(LOG) else []
    except Exception:
        log = []
    log.append({"profile_id": prof["id"], "profile_name": prof.get("name"),
                "time": prof["updated_at"], "sessions": log_sessions,
                "note": "migrare R:R 3 niveluri + expire 4 (scripts/migrate_rr_levels.py)"})
    json.dump(log[-500:], open(LOG, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(f"\nbackup: {backup}\n{len(log_sessions)} sesiuni modificate")


if __name__ == "__main__":
    main(sys.argv[1:])
