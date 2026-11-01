"""
QA: raspunsurile Gemini taiate (MAX_TOKENS) nu mai produc WAIT — failover RAPID pe Ollama.
Offline: HTTP-ul Gemini si Ollama sunt SIMULATE (fara retea, fara chei reale, fara Telegram).
    python scripts/test_gemini_truncation.py
"""
import os
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai_engine import providers as P  # noqa: E402
from ai_engine.providers import GeminiProvider, ProviderError, ProviderRegistry  # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}  {detail}")


ProviderRegistry._notify = staticmethod(lambda text: None)      # niciun Telegram real
SENT = []


def fake_http(url, payload, headers, timeout, name):
    SENT.append(payload)
    return RESP["value"]


RESP = {"value": None}
P._http_json = fake_http

print("1. Configurarea „gandirii” pe model")
check("2.5-flash -> gandire oprita (0)", P._gemini_thinking_config("gemini-2.5-flash") == {"thinkingBudget": 0})
check("2.5-flash-lite -> 0", P._gemini_thinking_config("gemini-2.5-flash-lite") == {"thinkingBudget": 0})
check("2.5-pro -> minimul permis (128)", P._gemini_thinking_config("gemini-2.5-pro") == {"thinkingBudget": 128})
check("2.0-flash -> campul nu se trimite", P._gemini_thinking_config("gemini-2.0-flash") is None)

g = GeminiProvider("gemini", "gemini-2.5-flash", api_key="k")
RESP["value"] = {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": '{"a": 1}'}]}}]}
check("raspuns complet -> text intors", g.chat("s", "u") == '{"a": 1}')
gc = SENT[-1]["generationConfig"]
check("cererea are thinkingBudget 0 + limita 8192", gc.get("thinkingConfig") == {"thinkingBudget": 0}
      and gc.get("maxOutputTokens") == 8192, gc)

print("2. Raspuns taiat -> eroare imediata, fara cele 3 reincercari JSON pe Gemini")
RESP["value"] = {"candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": [{"text": '{"decision": "OP'}]}}]}
n0 = len(SENT)
try:
    g.chat_json("s", "u", ["decision"])
    check("MAX_TOKENS ridica ProviderError", False)
except ProviderError as e:
    check("MAX_TOKENS -> ProviderError kind=truncated", e.kind == "truncated", e.kind)
check("un singur apel (nu 3 reincercari pe aceeasi sursa)", len(SENT) - n0 == 1, len(SENT) - n0)
RESP["value"] = {"candidates": [{"finishReason": "MAX_TOKENS"}]}
try:
    g.chat("s", "u")
    check("MAX_TOKENS fara text -> truncated", False)
except ProviderError as e:
    check("MAX_TOKENS fara niciun text -> truncated", e.kind == "truncated", e.kind)

print("3. Head Trader pe Gemini taiat -> trece pe Ollama in aceeasi decizie")


class FakeOllama(P.BaseProvider):
    name = "ollama"

    def __init__(self):
        self.calls = 0

    def chat(self, system, user, json_mode=False):
        self.calls += 1
        return '{"decision": "WAIT", "confidence": 55}'


reg = ProviderRegistry({})
reg._instances = {"gemini": g, "ollama": FakeOllama()}
reg.health = {n: {"status": "healthy", "reason": "", "retry_at": 0.0, "fails": 0} for n in reg._instances}
RESP["value"] = {"candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": [{"text": '{"deci'}]}}]}
t0 = time.time()
obj, meta = reg.call_role("head_trader", {"head_trader": "gemini"}, "s", "u", ["decision"])
check("rolul a primit raspunsul de la Ollama", meta["provider"] == "ollama" and obj["decision"] == "WAIT", meta)
check("meta: fallback_from = gemini", meta.get("fallback_from") == "gemini", meta)
check("failover rapid (fara asteptari)", time.time() - t0 < 1.0, time.time() - t0)
h = reg.health["gemini"]
check("Gemini pus in pauza scurta (~5 min), nu dezactivat",
      h["status"] == "paused" and 250 <= h["retry_at"] - time.time() <= 310, h)
obj, meta = reg.call_role("head_trader", {"head_trader": "gemini"}, "s", "u", ["decision"])
check("urmatoarea decizie merge direct pe Ollama (Gemini sarit cat e in pauza)",
      meta["provider"] == "ollama", meta)

print("4. Quota epuizata (tokenii contului) -> tot failover pe Ollama")
reg.health["gemini"] = {"status": "healthy", "reason": "", "retry_at": 0.0, "fails": 0}


def quota_http(url, payload, headers, timeout, name):
    raise ProviderError("gemini: quota epuizata", kind="quota")


P._http_json = quota_http
obj, meta = reg.call_role("head_trader", {"head_trader": "gemini"}, "s", "u", ["decision"])
check("quota -> raspuns de la Ollama", meta["provider"] == "ollama", meta)
check("quota -> Gemini in pauza lunga (6h)", reg.health["gemini"]["retry_at"] - time.time() > 5 * 3600)

print(f"\nREZULTAT: {PASS} PASS / {FAIL} FAIL")
sys.exit(1 if FAIL else 0)
