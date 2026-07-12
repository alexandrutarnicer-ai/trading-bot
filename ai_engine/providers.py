"""
ai_engine.providers — surse AI configurabile + failover automat.

Arhitectura (docs/PLAN_SURSE_AI_MULTI_PROVIDER.md):
  - 4 tipuri de adaptor cu interfata comuna `chat_json(system, user, required_keys)`:
      OllamaProvider            — local, gratuit, safety-net-ul default
      AnthropicProvider         — Claude, prin SDK-ul oficial `anthropic`
      GeminiProvider            — Google Gemini (are free tier cu quota zilnica)
      OpenAICompatProvider      — OpenAI/ChatGPT, Groq, DeepSeek, Mistral, xAI,
                                  OpenRouter, LM Studio... (base_url configurabil)
  - Erorile sunt CLASIFICATE (quota / rate_limit / auth / network / bad_response)
    si alimenteaza starea de sanatate per sursa, cu pauze diferite:
      quota epuizata → 6h   rate limit → 60s (sau retry-after)
      retea/server   → 2min cheie invalida → DEZACTIVAT pana la retest manual
  - ProviderRegistry ruteaza fiecare rol de consiliu: sursa asignata → urmatoarea
    sursa enabled+sanatoasa → default (ollama) → daca totul pica, ProviderError
    (consiliul decide WAIT — fail-safe existent). Revenirea e automata (lazy):
    la expirarea pauzei, urmatorul apel incearca din nou sursa originala.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request

# Pauze per tip de eroare (secunde)
_COOLDOWNS = {
    "quota":        6 * 3600,   # tokenii/creditele nu revin repede
    "rate_limit":   60,
    "network":      120,
    "bad_response": 120,
    # backend defect (Ollama fara runner) — persistent, necesita interventie umana;
    # pauza mai lunga ca sa nu intram in loop strans de retry, dar tot 'paused'
    # (nu 'disabled') ca sa se auto-repare in ≤5 min dupa ce utilizatorul repara Ollama.
    "server_error": 300,
}

# Semnaturi de backend Ollama defect: serverul raspunde la /api/tags (200) dar da
# 500 la /api/chat pentru ca runner-ul 'llama-server' lipseste / nu porneste. NU e
# un blip de retea — e o instalare corupta/partiala (update intrerupt) sau binarul
# a fost pus in carantina de antivirus. Il tratam distinct ca sa dam un mesaj
# ACTIONABIL, nu un "network" generic care se retry-uieste la nesfarsit.
_OLLAMA_BACKEND_BROKEN_SIGNS = (
    "llama-server", "binary not found", "error starting", "failed to start",
    "no compatible", "cmake",
)


def is_ollama_backend_broken(msg: str) -> bool:
    low = (msg or "").lower()
    return any(s in low for s in _OLLAMA_BACKEND_BROKEN_SIGNS)


class ProviderError(RuntimeError):
    """Eroare de sursa AI, cu clasificare pentru failover."""

    def __init__(self, message: str, kind: str = "network",
                 retry_after_s: float | None = None):
        super().__init__(message)
        # quota | rate_limit | auth | network | bad_response | server_error
        self.kind = kind
        self.retry_after_s = retry_after_s  # din header Retry-After, daca exista


def _extract_json(text: str) -> dict:
    """Extrage primul obiect JSON din text (tolerant la ``` fences)."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\s*|\s*```$", "", text, flags=re.IGNORECASE)
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not m:
            raise ValueError("niciun obiect JSON in raspuns")
        return json.loads(m.group(0))


# ── Baza comuna ──────────────────────────────────────────────────────────────

class BaseProvider:
    name = "?"
    needs_key = False

    def chat(self, system: str, user: str, json_mode: bool = False) -> str:
        raise NotImplementedError

    def chat_json(self, system: str, user: str, required_keys: list[str],
                  retries: int = 2) -> dict:
        """Chat cu output JSON validat pe chei obligatorii, retry cu feedback."""
        last_err = ""
        for _ in range(retries + 1):
            prompt = user if not last_err else (
                user + f"\n\nATENTIE: raspunsul anterior a fost invalid ({last_err}). "
                       "Raspunde DOAR cu obiectul JSON cerut, nimic altceva.")
            raw = self.chat(system, prompt, json_mode=True)
            try:
                obj = _extract_json(raw)
                missing = [k for k in required_keys if k not in obj]
                if missing:
                    raise ValueError(f"chei lipsa: {missing}")
                return obj
            except Exception as e:
                last_err = str(e)
        raise ProviderError(f"JSON invalid dupa {retries + 1} incercari: {last_err}",
                            kind="bad_response")

    def test(self) -> dict:
        """Testul de contract: reachable → auth → JSON valid. Pentru butonul Testeaza."""
        t0 = time.time()
        try:
            obj = self.chat_json(
                "You are a trading analyst. Reply only with JSON.",
                'Given: price 1.0850, trend UP, RSI 55. Reply JSON: '
                '{"bias": "long"|"short"|"neutral", "confidence": 0-100}',
                required_keys=["bias", "confidence"], retries=1)
            return {"ok": True, "latency_s": round(time.time() - t0, 1),
                    "detail": f"bias={obj.get('bias')}", "kind": None}
        except ProviderError as e:
            return {"ok": False, "latency_s": round(time.time() - t0, 1),
                    "detail": str(e)[:300], "kind": e.kind}
        except Exception as e:
            return {"ok": False, "latency_s": round(time.time() - t0, 1),
                    "detail": f"{type(e).__name__}: {e}"[:300], "kind": "network"}


def _http_json(url: str, payload: dict, headers: dict, timeout: int,
               provider_name: str) -> dict:
    """POST JSON cu clasificarea erorilor HTTP comuna adaptorilor pe urllib."""
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode(errors="replace")[:400]
        except Exception:
            pass
        low = body.lower()
        if e.code in (401, 403):
            raise ProviderError(f"{provider_name}: cheie invalida/neautorizat "
                                f"(HTTP {e.code}) {body[:120]}", kind="auth") from e
        if e.code == 429 or e.code == 402:
            quota_markers = ("insufficient_quota", "quota", "billing", "credit",
                             "resource_exhausted", "exceeded your current")
            kind = "quota" if (e.code == 402 or any(m in low for m in quota_markers)) \
                   else "rate_limit"
            retry_after = None
            try:
                ra = e.headers.get("Retry-After")
                retry_after = float(ra) if ra else None
            except Exception:
                pass
            raise ProviderError(f"{provider_name}: {('quota epuizata' if kind == 'quota' else 'rate limit')} "
                                f"(HTTP {e.code}) {body[:120]}",
                                kind=kind, retry_after_s=retry_after) from e
        raise ProviderError(f"{provider_name}: HTTP {e.code} {body[:160]}",
                            kind="network") from e
    except Exception as e:
        raise ProviderError(f"{provider_name}: {type(e).__name__}: {e}",
                            kind="network") from e


# ── Adaptori ─────────────────────────────────────────────────────────────────

class OllamaProvider(BaseProvider):
    needs_key = False

    def __init__(self, name: str, model: str, url: str = "http://localhost:11434",
                 opts: dict | None = None, timeout: int = 300, **_):
        self.name, self.model = name, model
        self.url = url.rstrip("/")
        self.opts = opts or {"temperature": 0.3, "num_ctx": 8192}
        self.timeout = timeout

    def available(self) -> bool:
        """Reachability ieftina: serverul raspunde SI modelul e instalat.

        ATENTIE: NU garanteaza ca inferenta merge — o instalare Ollama corupta
        (runner llama-server lipsa) trece de aici dar da 500 la /api/chat. Pentru
        garantia reala foloseste probe(). available() ramane cheap (fara inferenta)
        pentru ca e apelata des; probe() e apelata la pornire / in doctor."""
        try:
            req = urllib.request.Request(f"{self.url}/api/tags")
            with urllib.request.urlopen(req, timeout=5) as r:
                tags = json.loads(r.read())
            names = [m.get("name", "") for m in tags.get("models", [])]
            return any(n.startswith(self.model.split(":")[0]) for n in names)
        except Exception:
            return False

    def _broken_backend_error(self, detail: str) -> ProviderError:
        return ProviderError(
            f"{self.name}: backend Ollama DEFECT — runner-ul 'llama-server' lipseste "
            "sau nu porneste. Instalare Ollama corupta/partiala (update intrerupt) "
            "sau binarul a fost pus in carantina de antivirus. Reinstaleaza/actualizeaza "
            "Ollama de pe ollama.com/download si reporneste-l. Diagnostic: "
            "python -m ai_engine.doctor. Detaliu: " + str(detail)[:150],
            kind="server_error")

    def chat(self, system: str, user: str, json_mode: bool = False) -> str:
        payload = {
            "model": self.model, "stream": False,
            # fara chain-of-thought vizibil (qwen3 etc.) — 10-15x mai rapid
            "think": False, "options": self.opts,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
        }
        if json_mode:
            payload["format"] = "json"
        try:
            out = _http_json(f"{self.url}/api/chat", payload, {}, self.timeout, self.name)
        except ProviderError as e:
            # 500 "llama-server binary not found" ajunge aici clasificat drept
            # 'network'; il reclasificam ca 'server_error' cu mesaj actionabil.
            if is_ollama_backend_broken(str(e)):
                raise self._broken_backend_error(e) from e
            raise
        # Unele versiuni Ollama raporteaza esecul runner-ului ca 200 + {"error": ...}
        # in loc de 500 — il prindem si aici (altfel ar aparea drept "raspuns gol").
        if isinstance(out, dict) and out.get("error"):
            err_msg = str(out["error"])
            if is_ollama_backend_broken(err_msg):
                raise self._broken_backend_error(err_msg)
            raise ProviderError(f"{self.name}: {err_msg[:200]}", kind="server_error")
        content = (out.get("message") or {}).get("content", "")
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
        if not content:
            raise ProviderError(f"{self.name}: raspuns gol de la model", kind="bad_response")
        return content

    def probe(self) -> tuple[bool, str]:
        """
        Verificare PROFUNDA: nu doar ca serverul raspunde (/api/tags) ci ca poate
        RULA inferenta (/api/chat). Instalarile Ollama corupte trec de available()
        dar dau 500 la inferenta — de aceea available() singur e un fals-pozitiv la
        pornire. Returneaza (ok, detaliu_actionabil). Costul: un singur apel mic
        (o data, la pornire / in doctor); pe un model deja incarcat e ~1-3s.
        """
        if not self.available():
            return False, (f"serverul Ollama nu raspunde la {self.url} sau modelul "
                           f"'{self.model}' nu e instalat. Porneste Ollama si ruleaza: "
                           f"ollama pull {self.model}")
        try:
            self.chat("You reply with exactly one word.", "Reply with: ok")
            return True, ""
        except ProviderError as e:
            return False, str(e)[:280]


class AnthropicProvider(BaseProvider):
    """Claude, prin SDK-ul oficial `anthropic` (pip install anthropic)."""
    needs_key = True

    def __init__(self, name: str, model: str, api_key: str = "",
                 timeout: int = 120, **_):
        self.name, self.model, self.api_key = name, model, api_key
        self.timeout = timeout
        self._client = None

    def _cl(self):
        if self._client is None:
            try:
                import anthropic
            except ImportError as e:
                raise ProviderError(f"{self.name}: SDK-ul 'anthropic' nu e instalat "
                                    "(pip install anthropic)", kind="network") from e
            if not self.api_key:
                raise ProviderError(f"{self.name}: cheie API lipsa", kind="auth")
            self._client = anthropic.Anthropic(api_key=self.api_key,
                                               timeout=self.timeout, max_retries=0)
        return self._client

    def chat(self, system: str, user: str, json_mode: bool = False) -> str:
        import anthropic
        try:
            resp = self._cl().messages.create(
                model=self.model, max_tokens=2000, system=system,
                messages=[{"role": "user", "content": user}])
        except anthropic.AuthenticationError as e:
            raise ProviderError(f"{self.name}: cheie invalida (401)", kind="auth") from e
        except anthropic.PermissionDeniedError as e:
            raise ProviderError(f"{self.name}: acces refuzat (403)", kind="auth") from e
        except anthropic.RateLimitError as e:
            low = str(e).lower()
            kind = "quota" if ("credit" in low or "billing" in low or "quota" in low) \
                   else "rate_limit"
            ra = None
            try:
                ra = float(e.response.headers.get("retry-after", "") or 0) or None
            except Exception:
                pass
            raise ProviderError(f"{self.name}: {kind} (429)", kind=kind,
                                retry_after_s=ra) from e
        except anthropic.APIStatusError as e:
            k = "quota" if e.status_code == 402 else "network"
            raise ProviderError(f"{self.name}: HTTP {e.status_code} {e.message}"[:200],
                                kind=k) from e
        except anthropic.APIConnectionError as e:
            raise ProviderError(f"{self.name}: conexiune esuata: {e}", kind="network") from e

        text = next((b.text for b in resp.content if b.type == "text"), "")
        if resp.stop_reason == "refusal" or not text:
            raise ProviderError(f"{self.name}: raspuns gol/refuzat", kind="bad_response")
        return text


class GeminiProvider(BaseProvider):
    """Google Gemini (generativelanguage.googleapis.com). Free tier cu quota zilnica."""
    needs_key = True

    def __init__(self, name: str, model: str, api_key: str = "",
                 timeout: int = 120, **_):
        self.name, self.model, self.api_key = name, model, api_key
        self.timeout = timeout

    def chat(self, system: str, user: str, json_mode: bool = False) -> str:
        if not self.api_key:
            raise ProviderError(f"{self.name}: cheie API lipsa", kind="auth")
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{self.model}:generateContent")
        payload: dict = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 2000},
        }
        if json_mode:
            payload["generationConfig"]["responseMimeType"] = "application/json"
        out = _http_json(url, payload, {"x-goog-api-key": self.api_key},
                         self.timeout, self.name)
        try:
            parts = out["candidates"][0]["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts).strip()
        except (KeyError, IndexError):
            text = ""
        if not text:
            raise ProviderError(f"{self.name}: raspuns gol "
                                f"({json.dumps(out)[:160]})", kind="bad_response")
        return text


class OpenAICompatProvider(BaseProvider):
    """Orice API compatibil OpenAI: OpenAI, Groq, DeepSeek, Mistral, xAI, OpenRouter..."""
    needs_key = True

    def __init__(self, name: str, model: str, api_key: str = "",
                 base_url: str = "https://api.openai.com/v1", timeout: int = 120, **_):
        self.name, self.model, self.api_key = name, model, api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def chat(self, system: str, user: str, json_mode: bool = False) -> str:
        if not self.api_key:
            raise ProviderError(f"{self.name}: cheie API lipsa", kind="auth")
        payload: dict = {
            "model": self.model, "temperature": 0.3, "max_tokens": 2000,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        out = _http_json(f"{self.base_url}/chat/completions", payload,
                         {"Authorization": f"Bearer {self.api_key}"},
                         self.timeout, self.name)
        try:
            text = (out["choices"][0]["message"]["content"] or "").strip()
        except (KeyError, IndexError):
            text = ""
        if not text:
            raise ProviderError(f"{self.name}: raspuns gol", kind="bad_response")
        return text


_TYPES = {
    "ollama":            OllamaProvider,
    "anthropic":         AnthropicProvider,
    "gemini":            GeminiProvider,
    "openai_compatible": OpenAICompatProvider,
}


def build_provider(name: str, spec: dict, api_key: str = "") -> BaseProvider:
    """Construieste un adaptor dintr-o intrare de registru + cheia lui."""
    ptype = spec.get("type", "ollama")
    cls = _TYPES.get(ptype)
    if cls is None:
        raise ProviderError(f"tip de sursa necunoscut: {ptype}", kind="bad_response")
    return cls(name=name, model=spec.get("model", ""), api_key=api_key,
               url=spec.get("url", "http://localhost:11434"),
               base_url=spec.get("base_url", "https://api.openai.com/v1"),
               opts=spec.get("model_opts"))


# ── Registru + sanatate + failover ───────────────────────────────────────────

class ProviderRegistry:
    """
    Tine instantele surselor enabled + starea lor de sanatate si ruteaza
    apelurile de rol cu failover. Sursa default (ollama) e ultimul resort.
    """

    DEFAULT = "ollama"

    def __init__(self, providers_cfg: dict, keys: dict | None = None):
        self._instances: dict[str, BaseProvider] = {}
        self._specs: dict = {}
        self.health: dict[str, dict] = {}
        self.refresh(providers_cfg, keys or {})

    # -- lifecycle --

    def refresh(self, providers_cfg: dict, keys: dict) -> None:
        """Sincronizeaza cu config-ul; pastreaza sanatatea intrarilor neschimbate."""
        new_specs = {}
        for name, spec in (providers_cfg or {}).items():
            if not spec.get("enabled"):
                continue
            key = keys.get(name, "")
            sig = (spec.get("type"), spec.get("model"), spec.get("url"),
                   spec.get("base_url"), bool(key))
            new_specs[name] = sig
            if self._specs.get(name) != sig:
                self._instances[name] = build_provider(name, spec, key)
                self.health[name] = {"status": "healthy", "reason": "",
                                     "retry_at": 0.0, "fails": 0}
        for gone in set(self._instances) - set(new_specs):
            self._instances.pop(gone, None)
            self.health.pop(gone, None)
        self._specs = new_specs

    # -- sanatate --

    def _usable(self, name: str) -> bool:
        h = self.health.get(name)
        if not h or name not in self._instances:
            return False
        if h["status"] == "disabled_auth":
            return False
        if h["status"] == "paused":
            return time.time() >= h["retry_at"]   # lazy recovery: pauza a expirat
        return True

    def report_success(self, name: str) -> None:
        h = self.health.get(name)
        if h:
            recovered = h["status"] != "healthy"
            h.update({"status": "healthy", "reason": "", "retry_at": 0.0, "fails": 0})
            if recovered:
                self._notify(f"✅ Sursa AI «{name}» si-a revenit — rutare normala.")

    def report_failure(self, name: str, err: ProviderError) -> None:
        h = self.health.get(name)
        if not h:
            return
        h["fails"] = h.get("fails", 0) + 1
        if err.kind == "auth":
            h.update({"status": "disabled_auth", "reason": str(err)[:200],
                      "retry_at": 0.0})
            self._notify(f"🔑 Sursa AI «{name}» dezactivata: cheie invalida. "
                         "Repar-o din tab-ul AI Engine si apasa Testeaza.")
        else:
            wait = err.retry_after_s or _COOLDOWNS.get(err.kind, 120)
            first_pause = h["status"] == "healthy"
            h.update({"status": "paused", "reason": str(err)[:200],
                      "retry_at": time.time() + wait})
            if first_pause:
                if err.kind == "server_error" and name == self.DEFAULT:
                    # Ollama e safety-net-ul failover-ului: daca backend-ul lui e
                    # defect, e o problema de infrastructura (nu se auto-repara).
                    self._notify(
                        f"🛑 SAFETY-NET «{name}» DEFECT — {str(err)[:190]} "
                        "Motorul ramane fara plasa de failover pana repari Ollama.")
                elif err.kind == "server_error":
                    self._notify(f"🛑 Sursa AI «{name}» defecta (server) — {str(err)[:170]}")
                else:
                    mins = int(wait / 60)
                    self._notify(f"⚠ Sursa AI «{name}» in pauza ({err.kind}, ~{mins} min) — "
                                 f"rolurile ei trec temporar pe alta sursa.")

    @staticmethod
    def _notify(text: str) -> None:
        """Telegram best-effort, o data per tranzitie (apelat doar la schimbari)."""
        try:
            import threading
            from api.telegram import send_message
            threading.Thread(target=send_message, args=(f"🤖 {text}",),
                             daemon=True).start()
        except Exception:
            pass

    # -- rutare --

    def chain_for(self, assigned: str) -> list[str]:
        """Lantul de candidati pentru un rol: asignat → alte surse → default."""
        chain = []
        if assigned in self._instances:
            chain.append(assigned)
        for name in self._instances:
            if name not in chain and name != self.DEFAULT:
                chain.append(name)
        if self.DEFAULT in self._instances and self.DEFAULT not in chain:
            chain.append(self.DEFAULT)
        return chain

    def call_role(self, role: str, assignments: dict, system: str, user: str,
                  required_keys: list[str]) -> tuple[dict, dict]:
        """
        Executa un rol de consiliu cu failover. Returneaza (raspuns, meta):
        meta = {"provider", "latency_s", "fallback_from"?}.
        Ridica ProviderError doar daca TOATE sursele din lant esueaza.
        """
        assigned = assignments.get(role, self.DEFAULT)
        last_err: ProviderError | None = None
        for name in self.chain_for(assigned):
            if not self._usable(name):
                continue
            t0 = time.time()
            try:
                obj = self._instances[name].chat_json(system, user, required_keys)
            except ProviderError as e:
                self.report_failure(name, e)
                last_err = e
                continue
            self.report_success(name)
            meta = {"provider": name, "latency_s": round(time.time() - t0, 1)}
            if name != assigned:
                meta["fallback_from"] = assigned
            return obj, meta
        raise last_err or ProviderError("nicio sursa AI disponibila", kind="network")

    def call_role_pinned(self, source: str, system: str, user: str,
                         required_keys: list[str]) -> tuple[dict, dict]:
        """
        Executa un rol pe EXACT sursa `source`, FARA failover. Ridica ProviderError
        daca sursa e necunoscuta/indisponibila/esueaza.

        Folosit de consiliile multi-council: fiecare consiliu trebuie sa ramana pe
        propriul model — un failover pe alta sursa ar transforma consiliul intr-un
        duplicat al altui consiliu, distrugand independenta opiniilor. Daca sursa
        pinned pica, consiliul respectiv iese din joc (dropped), restul continua.
        """
        if source not in self._instances:
            raise ProviderError(f"sursa '{source}' nu exista in registru", kind="network")
        if not self._usable(source):
            h = self.health.get(source) or {}
            raise ProviderError(f"sursa '{source}' indisponibila ({h.get('status', '?')})",
                                kind="network")
        t0 = time.time()
        try:
            obj = self._instances[source].chat_json(system, user, required_keys)
        except ProviderError as e:
            self.report_failure(source, e)
            raise
        self.report_success(source)
        return obj, {"provider": source, "latency_s": round(time.time() - t0, 1),
                     "pinned": True}

    def usable_sources(self) -> list[str]:
        """Numele surselor enabled + sanatoase acum (pentru planificarea consiliilor)."""
        return [n for n in self._instances if self._usable(n)]

    # -- introspectie --

    def snapshot(self) -> dict:
        """Stare JSON-safe pentru status.json / UI."""
        out = {}
        now = time.time()
        for name, h in self.health.items():
            retry_in = max(0, int(h["retry_at"] - now)) if h["status"] == "paused" else 0
            out[name] = {"status": h["status"], "reason": h["reason"],
                         "retry_in_s": retry_in, "fails": h.get("fails", 0)}
        return out

    def default_available(self) -> bool:
        """Reachability ieftina a safety-net-ului (Ollama raspunde + model prezent)."""
        inst = self._instances.get(self.DEFAULT)
        return bool(inst and isinstance(inst, OllamaProvider) and inst.available())

    def default_probe(self) -> tuple[bool, str]:
        """
        Verificare PROFUNDA a safety-net-ului: poate rula inferenta, nu doar raspunde.
        Prinde cazul „reachable dar backend defect" (llama-server lipsa) pe care
        default_available() il rateaza. Returneaza (ok, detaliu_actionabil).
        """
        inst = self._instances.get(self.DEFAULT)
        if not (inst and isinstance(inst, OllamaProvider)):
            return False, "sursa default (ollama) nu e configurata in registru"
        return inst.probe()


# ── Compatibilitate (selftest / cod vechi) ───────────────────────────────────

def make_provider(cfg: dict):
    """Construieste sursa default (ollama) din config — pastrat pentru compat."""
    spec = (cfg.get("providers") or {}).get("ollama") or {
        "type": "ollama", "model": cfg.get("model", "qwen3:8b"),
        "url": cfg.get("ollama_url", "http://localhost:11434"),
    }
    return build_provider("ollama", spec)
