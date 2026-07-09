"""
ai_engine.providers — abstractie peste furnizorul de LLM.

V1: Ollama local (gratuit, nelimitat). Interfata e minima intentionat —
`chat(system, user) -> str` si `chat_json(system, user, schema_hint) -> dict` —
astfel incat un upgrade ulterior la Claude API sa fie o clasa noua + o linie
in config, fara nicio schimbare in council.py.
"""

from __future__ import annotations

import json
import re
import urllib.request


class ProviderError(RuntimeError):
    pass


class OllamaProvider:
    def __init__(self, url: str, model: str, opts: dict | None = None,
                 timeout: int = 300):
        self.url     = url.rstrip("/")
        self.model   = model
        self.opts    = opts or {}
        self.timeout = timeout

    def _post(self, payload: dict) -> dict:
        req = urllib.request.Request(
            f"{self.url}/api/chat",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read())
        except Exception as e:
            raise ProviderError(f"Ollama indisponibil ({self.url}): {e}") from e

    def available(self) -> bool:
        try:
            req = urllib.request.Request(f"{self.url}/api/tags")
            with urllib.request.urlopen(req, timeout=5) as r:
                tags = json.loads(r.read())
            names = [m.get("name", "") for m in tags.get("models", [])]
            return any(n.startswith(self.model.split(":")[0]) for n in names)
        except Exception:
            return False

    def chat(self, system: str, user: str, json_mode: bool = False) -> str:
        payload = {
            "model":    self.model,
            "stream":   False,
            # Fara chain-of-thought vizibil (qwen3 etc.) — 10-15x mai rapid,
            # iar rolurile noastre cer oricum rationament scurt, structurat.
            "think":    False,
            "options":  self.opts,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
        }
        if json_mode:
            payload["format"] = "json"
        out = self._post(payload)
        content = (out.get("message") or {}).get("content", "")
        # Modele cu reasoning (qwen3 etc.) pot emite <think>...</think> — il scoatem.
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
        if not content:
            raise ProviderError("Raspuns gol de la model")
        return content

    def chat_json(self, system: str, user: str, required_keys: list[str],
                  retries: int = 2) -> dict:
        """Chat cu output JSON validat pe chei obligatorii, cu retry si feedback."""
        last_err = ""
        for attempt in range(retries + 1):
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
        raise ProviderError(f"JSON invalid dupa {retries + 1} incercari: {last_err}")


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


def make_provider(cfg: dict):
    if cfg.get("provider", "ollama") == "ollama":
        return OllamaProvider(cfg["ollama_url"], cfg["model"], cfg.get("model_opts"))
    raise ProviderError(f"Provider necunoscut: {cfg.get('provider')}")
