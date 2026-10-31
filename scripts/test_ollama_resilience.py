"""
QA — rezilienta integrarii Ollama (server Ollama SIMULAT local, fara Ollama real/MT5).

    python scripts/test_ollama_resilience.py

Scenarii: disponibil · oprit (conexiune refuzata) · repornit (recovery fara restart) ·
conexiune inchisa in timpul cererii (RemoteDisconnected) · raspuns foarte lent ·
model care nu raspunde deloc · multe cereri succesive · buget de consiliu respectat
la apel · keep_alive trimis · eroarea de pornire curatata dupa recovery.
"""
import json
import os
import socket
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")   # consola Windows cp1252 nu afiseaza → / diacritice
except Exception:
    pass
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ai_engine import providers as P
from ai_engine.providers import OllamaProvider, ProviderRegistry, ProviderError
from ai_engine.council import DebateRunner

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}  {detail}")


MODE = {"mode": "ok", "delay": 0.0, "calls": 0, "drop_first": 0, "last_payload": None}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._send({"models": [{"name": "qwen3:1.7b"}]})

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        MODE["last_payload"] = json.loads(self.rfile.read(n) or b"{}")
        MODE["calls"] += 1
        if MODE["drop_first"] > 0:
            MODE["drop_first"] -= 1
            self.connection.shutdown(socket.SHUT_RDWR)   # RemoteDisconnected la client
            self.connection.close()
            return
        if MODE["mode"] == "hang":
            time.sleep(60)
            return
        if MODE["delay"]:
            time.sleep(MODE["delay"])
        self._send({"message": {"content": json.dumps({"bias": "long", "confidence": 60})}})


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


PORT = free_port()
URL = f"http://127.0.0.1:{PORT}"
srv = None


def start():
    global srv
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()


def stop():
    srv.shutdown()
    srv.server_close()


def reg():
    return ProviderRegistry({"ollama": {"enabled": True, "type": "ollama", "model": "qwen3:1.7b",
                                        "url": URL}})


P.ProviderRegistry._notify = staticmethod(lambda text: None)   # fara Telegram in teste

print("\n[1] Ollama disponibil")
start()
r = reg()
obj, meta = r.call_role("technical", {}, "s", "u", ["bias"])
check("raspuns valid", obj.get("bias") == "long")
check("keep_alive=30m trimis (modelul ramane in RAM pe CPU)", MODE["last_payload"].get("keep_alive") == "30m")
check("last_ok setat la succes", r.health["ollama"].get("last_ok"))

print("\n[2] Conexiune inchisa in timpul cererii (RemoteDisconnected)")
MODE.update(calls=0, drop_first=1)
obj, _ = r.call_role("technical", {}, "s", "u", ["bias"])
check("o deconectare → reincercare automata reusita", obj.get("bias") == "long" and MODE["calls"] == 2,
      MODE["calls"])
check("sursa ramane sanatoasa", r.health["ollama"]["status"] == "healthy")
MODE.update(calls=0, drop_first=5)
try:
    r.call_role("technical", {}, "s", "u", ["bias"])
    check("deconectari repetate → eroare", False)
except ProviderError as e:
    check("deconectari repetate → eroare cu CAUZA clara", "a inchis conexiunea" in str(e), str(e))
    check("pauza scurta (30s) pentru Ollama local, nu 120s",
          25 <= r.health["ollama"]["retry_at"] - time.time() <= 31, r.health["ollama"])
MODE["drop_first"] = 0

print("\n[3] Ollama oprit → repornit (recovery fara restart de motor)")
stop()
r = reg()
t0 = time.time()
try:
    r.call_role("technical", {}, "s", "u", ["bias"])
    check("oprit → eroare", False)
except ProviderError as e:
    check("oprit → eroare 'nu ruleaza (conexiune refuzata)'", "nu ruleaza" in str(e), str(e))
    check("esec rapid (nu blocheaza)", time.time() - t0 < 6, time.time() - t0)
check("in pauza → apelurile urmatoare nu mai lovesc serverul", not r._usable("ollama"))
start()
r.health["ollama"]["retry_at"] = time.time() - 1          # pauza de 30s expirata
obj, _ = r.call_role("technical", {}, "s", "u", ["bias"])
check("repornit → se reconecteaza singur, fara restart", obj.get("bias") == "long")
check("revenit la healthy", r.health["ollama"]["status"] == "healthy")

print("\n[4] Raspuns foarte lent / model care nu raspunde — bugetul consiliului respectat")
MODE.update(mode="ok", delay=8)
r = reg()
t0 = time.time()
try:
    r.call_role("technical", {}, "s", "u", ["bias"], deadline=time.time() + 4)
    check("lent peste buget → eroare", False)
except ProviderError as e:
    took = time.time() - t0
    check("lent peste buget → oprit la termen (~4s, nu 180s)", took < 6, took)
    check("clasificat 'budget'", e.kind == "budget", e.kind)
    check("sursa NU e pusa pe pauza (nu e vina ei)", r.health["ollama"]["status"] == "healthy")
MODE.update(mode="hang", delay=0)
t0 = time.time()
try:
    DebateRunner(r, {"council_time_budget_s": 5}).ask("technical", "s", "u", ["bias"])
    check("model blocat → eroare", False)
except ProviderError as e:
    check("model care nu raspunde → consiliul se opreste la buget (5s)", time.time() - t0 < 7,
          time.time() - t0)
MODE.update(mode="ok", delay=1)
obj, _ = r.call_role("technical", {}, "s", "u", ["bias"], deadline=time.time() + 30)
check("lent DAR in buget → raspuns", obj.get("bias") == "long")
MODE["delay"] = 0

print("\n[5] Multe cereri succesive")
MODE["calls"] = 0
ok = 0
for _ in range(30):
    o, _ = r.call_role("technical", {}, "s", "u", ["bias"])
    ok += o.get("bias") == "long"
check("30/30 cereri succesive OK", ok == 30, ok)
res = []
def worker():
    o, _ = r.call_role("technical", {}, "s", "u", ["bias"], deadline=time.time() + 20)
    res.append(o.get("bias"))
ths = [threading.Thread(target=worker) for _ in range(5)]
[t.start() for t in ths]; [t.join() for t in ths]
check("5 cereri concurente (thread-uri diferite, deadline per thread) OK", res.count("long") == 5, res)

print("\n[6] Pornire: probe cu asteptare + curatarea erorii vechi")
import ai_engine.engine as E
stop()
r = reg()
waits = []
def later():
    time.sleep(1.5); start()
threading.Thread(target=later).start()
orig_sleep = E.time.sleep
ok, detail = E._probe_ollama_with_wait(r, waits=(1, 1, 1, 1))
check("Ollama porneste in timpul asteptarii → probe OK (nu mai raporteaza DEFECT)", ok, detail)
E._last_errors[:] = [{"ts": "2026-10-25T14:47:20", "where": "ollama_probe", "error": "RemoteDisconnected"}]
E._clear_recovered_errors(r)
check("eroarea veche de pornire dispare din „Erori recente” dupa recovery", E._last_errors == [])
stop()
r = reg()
t0 = time.time()
ok, detail = E._probe_ollama_with_wait(r, waits=(0.2, 0.2))
check("Ollama oprit de tot → probe esueaza dupa asteptare (motorul continua degradat)", not ok, detail)

print(f"\n{'=' * 60}\nREZULTAT: {PASS} PASS / {FAIL} FAIL")
sys.stdout.flush()
os._exit(1 if FAIL else 0)
