"""
QA — curatarea saptamanala a datelor AI fara trade (api/data_cleanup.py).
Ruleaza pe COPII ale datelor (ledger real copiat in temp + jsonl sintetic) — nu atinge data/.

    python scripts/test_data_cleanup.py
"""
import json
import os
import shutil
import sqlite3
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")   # consola Windows cp1252 nu afiseaza → / diacritice
except Exception:
    pass
import tempfile
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from api import data_cleanup as DC
from ai_engine.ledger import Ledger

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}  {detail}")


tmp = tempfile.mkdtemp()
real = os.path.join(ROOT, "data", "ai", "ledger.db")
db = os.path.join(tmp, "ledger.db")
if os.path.exists(real):
    shutil.copy2(real, db)
else:
    Ledger(db).close()

print("\n[1] Ledger (copie a celui real)")
con = sqlite3.connect(db)
placed_before = con.execute("""select k.id, k.transcript, s.data from councils k
    join decisions d on d.council_id=k.id left join snapshots s on s.id=k.snapshot_id
    where d.exec_status='placed'""").fetchall()
counts_before = [con.execute(f"select count(*) from {t}").fetchone()[0]
                 for t in ("councils", "decisions", "outcomes", "snapshots")]
con.close()
L = Ledger(db); sc_before = L.scorecard(); sbs_before = L.scorecard_by_symbol(); L.close()

cutoff = DC._cutoff()
dry = DC.prune_ledger(db, cutoff, apply=False)
check("dry-run nu modifica nimic", DC.prune_ledger(db, cutoff, apply=False) == dry)
rep = DC.prune_ledger(db, cutoff, apply=True)
check("apply curata exact ce a raportat dry-run", rep == dry, (rep, dry))

con = sqlite3.connect(db)
placed_after = con.execute("""select k.id, k.transcript, s.data from councils k
    join decisions d on d.council_id=k.id left join snapshots s on s.id=k.snapshot_id
    where d.exec_status='placed'""").fetchall()
check("consiliile + snapshot-urile cu trade PLASAT raman INTEGRAL", placed_before == placed_after)
counts_after = [con.execute(f"select count(*) from {t}").fetchone()[0]
                for t in ("councils", "decisions", "outcomes", "snapshots")]
check("niciun rand sters (doar textul greu golit) — FK si UI intacte", counts_before == counts_after)
recent = con.execute("select count(*) from councils where ts >= ? and transcript = ?",
                     (cutoff, DC._PRUNED)).fetchone()[0]
check("analizele RECENTE (< 28 zile) neatinse", recent == 0, recent)
old_nt = con.execute("""select count(*) from councils k where k.ts < ? and k.transcript != ? and not exists
    (select 1 from decisions d where d.council_id=k.id and d.exec_status='placed')""",
                     (cutoff, DC._PRUNED)).fetchone()[0]
check("toate consiliile vechi fara trade au fost compactate", old_nt == 0, old_nt)
con.close()
L = Ledger(db)
check("scorecard identic inainte/dupa", L.scorecard() == sc_before)
check("scorecard per piata identic", L.scorecard_by_symbol() == sbs_before)
_con = sqlite3.connect(db); _sym = (_con.execute("select symbol from councils order by id desc limit 1").fetchone() or [None])[0]; _con.close()
check("cooldown-ul (last_council_ts) functioneaza dupa curatare", _sym is None or L.last_council_ts(_sym) is not None)
L.close()
check("idempotent: a doua rulare nu mai gaseste nimic", DC.prune_ledger(db, cutoff, apply=True)["councils"] == 0)

print("\n[2] ai_filter.jsonl (sintetic)")
d = os.path.join(tmp, "live_signals", "session9"); os.makedirs(d)
old = (datetime.now() - timedelta(days=40)).isoformat()
new = datetime.now().isoformat()
rows = [
    {"sig_id": "A", "time": old, "approved": False, "confidence": 30, "reason": "slab", "transcript": {"technical": {"x": "y" * 500}}},
    {"sig_id": "B", "time": old, "approved": True, "confidence": 80, "reason": "ok", "transcript": {"technical": {"x": "y" * 500}}},
    {"sig_id": "C", "time": new, "approved": False, "confidence": 20, "reason": "recent", "transcript": {"technical": {"x": "y" * 500}}},
    {"sig_id": "D", "time": old, "approved": False, "councils": [{"source": "ollama", "transcript": {"a": "b" * 300}}], "transcript": {}},
]
open(os.path.join(d, "ai_filter.jsonl"), "w", encoding="utf-8").write("\n".join(json.dumps(r) for r in rows) + "\n")
r = DC.prune_ai_filter_logs(tmp, DC._cutoff(), apply=True)
out = {json.loads(l)["sig_id"]: json.loads(l) for l in open(os.path.join(d, "ai_filter.jsonl"), encoding="utf-8")}
check("respins vechi → transcript golit, verdictul ramane", out["A"]["transcript"] == {} and out["A"]["reason"] == "slab" and out["A"]["_pruned"])
check("APROBAT (a dus la trade) → integral", out["B"]["transcript"] != {})
check("respins RECENT → integral", out["C"]["transcript"] != {})
check("multi-council: transcriptul din councils[] golit, sursa pastrata",
      "transcript" not in out["D"]["councils"][0] and out["D"]["councils"][0]["source"] == "ollama")
check("raport: 2 verdicte compactate", r["verdicts"] == 2, r)

print("\n[3] Programare: luni de la 12:00, o data pe saptamana")
DC.MARKER = os.path.join(tmp, "marker.json")
mon = datetime(2026, 11, 2, 12, 5)
check("luni 11:59 → nu", not DC.due(mon.replace(hour=11, minute=59)))
check("luni 12:05, fara marcaj → da", DC.due(mon))
json.dump({"last_run": mon.isoformat()}, open(DC.MARKER, "w"))
check("luni 15:00 dupa rulare → nu (o data)", not DC.due(mon.replace(hour=15)))
check("marti → nu", not DC.due(mon + timedelta(days=1)))
check("lunea urmatoare → da", DC.due(mon + timedelta(days=7)))
check("API pornit luni 18:00 (catch-up) → da",
      DC.due(datetime(2026, 11, 9, 18, 0)))

print("\n[4] Sincronizare PC <-> laptop: fiecare masina compacteaza doar datele engine-urilor ei")
calls = []
_pl, _pf = DC.prune_ledger, DC.prune_ai_filter_logs
DC.prune_ledger = lambda **k: calls.append("ledger") or {"councils": 5, "snapshots": 5, "bytes": 10}
DC.prune_ai_filter_logs = lambda **k: calls.append("filter") or {"verdicts": 3, "bytes": 10, "files": 1}
r = DC.run_cleanup(apply=False, local_only=True, engines={"ai": False, "bot": False})
check("masina fara engine-uri (doar UI) → nu atinge ledger.db / ai_filter.jsonl (fisiere sincronizate)",
      calls == [] and r["ledger"]["councils"] == 0 and r["ai_filter"]["verdicts"] == 0, (calls, r))
calls.clear()
r = DC.run_cleanup(apply=False, local_only=True, engines={"ai": True, "bot": False})
check("doar AI Engine aici → doar ledger-ul", calls == ["ledger"], calls)
calls.clear()
r = DC.run_cleanup(apply=False)
check("rulare manuala (CLI) → tot, ca inainte", calls == ["ledger", "filter"], calls)
DC.prune_ledger, DC.prune_ai_filter_logs = _pl, _pf
check("PID inexistent → engine-ul NU ruleaza aici", not DC._engine_running_here(os.path.join(tmp, "nu_exista.pid")))
open(os.path.join(tmp, "self.pid"), "w").write(str(os.getpid()))
check("PID viu → ruleaza aici", DC._engine_running_here(os.path.join(tmp, "self.pid")))

print(f"\n{'=' * 60}\nREZULTAT: {PASS} PASS / {FAIL} FAIL")
sys.exit(1 if FAIL else 0)
