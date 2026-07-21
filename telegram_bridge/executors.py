"""
telegram_bridge.executors — cine executa cererile "claude ..." / "copilot ...".

Nivelul 2 (Claude, agent complet) cu lant de fallback:
  1. Claude Code CLI headless  (claude -p, cu tools reale in repo — citeste cod,
     ruleaza teste, face rapoarte). Read-only prin allowlist; scriere doar in
     modul confirmat (allow_writes).
  2. Claude API direct         (sursa 'claude' din registru) — degradat: raspunde
     din prompt + context injectat, FARA tools de repo. Folosit cand CLI-ul pica.
  3. Sursele AI existente       (ai_fast) — cerebras/mistral/ollama etc.
  4. Mesaj onest                — doar comenzi locale disponibile acum.

Fiecare raspuns spune clar pe ce nivel/sursa a fost generat.

SIGURANTA: modul CLI ruleaza cu --allowedTools restrictiv. In modul headless (-p),
orice tool care nu e in allowlist si cere permisiune e REFUZAT (nu exista TTY pentru
prompt) — deci read-only chiar inseamna read-only. Scrierea e gated de allow_writes
si de fluxul de confirmare in 2 pasi (vezi router.py).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field

from . import config


@dataclass
class RunResult:
    text: str
    level: str                       # "claude-cli" | "claude-api" | "ai-sources" | "local"
    source: str | None = None        # numele sursei concrete
    session_id: str | None = None    # doar pentru claude-cli (pentru --resume)
    cost_usd: float | None = None
    num_turns: int | None = None
    is_error: bool = False
    meta: dict = field(default_factory=dict)


# ── Claude Code CLI ───────────────────────────────────────────────────────────

def claude_binary(cfg: dict) -> str | None:
    b = cfg.get("claude_binary") or ""
    if b and (os.path.isfile(b) or shutil.which(b)):
        return b
    return shutil.which("claude")


def _build_cmd(cfg: dict, prompt: str, resume: str | None, mode: str) -> list[str]:
    """
    mode:
      "read"    — read-only (allowlist read-only, fara permission bypass)
      "plan"    — plan mode (produce un plan, NU executa modificari)
      "write"   — executa modificari (acceptEdits + write_tools)
    """
    binary = claude_binary(cfg)
    cmd = [binary, "-p", prompt, "--output-format", "json",
           "--add-dir", cfg.get("claude_cwd", config.ROOT)]
    if resume:
        cmd += ["--resume", resume]

    if mode == "plan":
        cmd += ["--permission-mode", "plan"]
        tools = cfg.get("claude_readonly_tools", [])
    elif mode == "write":
        cmd += ["--permission-mode", cfg.get("write_permission_mode", "acceptEdits")]
        tools = cfg.get("write_tools", [])
    else:  # read
        tools = cfg.get("claude_readonly_tools", [])

    # allowedTools LAST — forma nargs (fiecare tool = un argument separat).
    if tools:
        cmd += ["--allowedTools", *tools]
    return cmd


def _parse_cli_output(stdout: str) -> dict:
    """Extrage obiectul-rezultat din --output-format json (tolerant la zgomot)."""
    stdout = (stdout or "").strip()
    if not stdout:
        return {}
    # de obicei o singura linie JSON; uneori mai multe evenimente — luam ultimul obiect
    try:
        return json.loads(stdout)
    except Exception:
        pass
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                return json.loads(line)
            except Exception:
                continue
    return {"result": stdout}


def run_claude_cli(cfg: dict, prompt: str, resume: str | None = None,
                   mode: str = "read") -> RunResult | None:
    """Ruleaza Claude Code headless. None → CLI indisponibil (declanseaza fallback)."""
    binary = claude_binary(cfg)
    if not binary:
        return None
    cmd = _build_cmd(cfg, prompt, resume, mode)
    env = dict(os.environ)
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=cfg.get("claude_cwd", config.ROOT), env=env,
            timeout=cfg.get("claude_timeout_s", 600),
        )
    except subprocess.TimeoutExpired:
        return RunResult(text="⏱ Claude a depasit timpul alocat "
                              f"({cfg.get('claude_timeout_s', 600)}s). Incearca o cerere mai mica.",
                         level="claude-cli", is_error=True)
    except Exception as e:
        return RunResult(text=f"(nu am putut porni Claude CLI: {e})",
                         level="claude-cli", is_error=True)

    data = _parse_cli_output(proc.stdout)
    text = (data.get("result") or "").strip()
    if not text:
        # esec fara result → arata stderr scurt pentru diagnostic
        err = (proc.stderr or "").strip()[:500]
        text = f"(Claude nu a intors text; cod {proc.returncode})" + (f"\n{err}" if err else "")
        return RunResult(text=text, level="claude-cli", is_error=True,
                         session_id=data.get("session_id"))

    cost = data.get("total_cost_usd")
    max_chars = cfg.get("claude_max_output_chars", 12000)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n…(raspuns trunchiat)"
    return RunResult(
        text=text, level="claude-cli", source="claude-code",
        session_id=data.get("session_id"),
        cost_usd=(float(cost) if isinstance(cost, (int, float)) else None),
        num_turns=data.get("num_turns"),
        is_error=bool(data.get("is_error")),
    )


# ── Fallback: Claude API direct (fara tools de repo) ──────────────────────────

def run_claude_api(cfg: dict, prompt: str) -> RunResult | None:
    """Raspunde cu sursa 'claude' din registru + context injectat. None → indisponibil."""
    provider = cfg.get("fallback_claude_provider", "claude")
    try:
        from ai_engine.config import load_config, load_keys
        from ai_engine.providers import ProviderRegistry, ProviderError
        from .ai_fast import _context, _SYSTEM
    except Exception:
        return None
    try:
        acfg = load_config()
        provs = acfg.get("providers", {})
        if not (isinstance(provs.get(provider), dict) and provs[provider].get("enabled")):
            return None
        reg = ProviderRegistry(provs, load_keys())
        inst = reg._instances.get(provider)
        if inst is None or not reg._usable(provider):
            return None
        sysmsg = (_SYSTEM + " NOTA: raspunzi prin API direct, FARA acces la fisierele "
                  "repo-ului — poti doar analiza pe baza contextului de mai jos.")
        user = f"CONTEXT LIVE (JSON):\n{_context(cfg)}\n\nCERERE: {prompt.strip()}"
        txt = inst.chat(sysmsg, user)
        return RunResult(text=txt.strip(), level="claude-api", source=provider)
    except ProviderError:
        return None
    except Exception:
        return None


# ── Copilot (optional, pluggable) ─────────────────────────────────────────────

def copilot_binary(cfg: dict) -> list[str] | None:
    """Comanda de baza pentru Copilot: standalone `copilot` sau `gh copilot`."""
    b = cfg.get("copilot_binary") or ""
    if b and (os.path.isfile(b) or shutil.which(b)):
        return [b]
    if shutil.which("copilot"):
        return ["copilot"]
    if shutil.which("gh"):
        # verifica extensia copilot
        try:
            r = subprocess.run(["gh", "copilot", "--version"], capture_output=True,
                               text=True, timeout=15)
            if r.returncode == 0:
                return ["gh", "copilot"]
        except Exception:
            pass
    return None


def run_copilot(cfg: dict, prompt: str) -> RunResult | None:
    """
    Ruleaza GitHub Copilot CLI daca e instalat. Suporta doua forme:
      - standalone agentic:  copilot -p "<prompt>" --allow-all-tools? (NU — read-only)
      - gh copilot suggest/explain (non-agentic)
    None → Copilot indisponibil.
    """
    base = copilot_binary(cfg)
    if not base:
        return None
    try:
        if base == ["copilot"] or (len(base) == 1 and base[0].endswith("copilot")):
            # CLI agentic standalone, mod non-interactiv, read-only (fara --allow-all-tools)
            cmd = base + ["-p", prompt]
        else:
            # gh copilot: explica/sugereaza (non-agentic)
            cmd = base + ["explain", prompt]
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", cwd=cfg.get("claude_cwd", config.ROOT),
                              timeout=cfg.get("claude_timeout_s", 600))
        out = (proc.stdout or "").strip() or (proc.stderr or "").strip()
        return RunResult(text=out or "(Copilot nu a intors nimic)",
                         level="copilot", source="copilot",
                         is_error=proc.returncode != 0)
    except subprocess.TimeoutExpired:
        return RunResult(text="⏱ Copilot a depasit timpul alocat.", level="copilot",
                         is_error=True)
    except Exception as e:
        return RunResult(text=f"(Copilot a esuat: {e})", level="copilot", is_error=True)


# ── Editor de REZERVA (gratuit): Aider + Copilot-write ────────────────────────

# Prefix model Aider → (variabila de mediu asteptata de Aider, nume sursa in providers.json).
# Injectam cheia ta existenta ca Aider sa foloseasca modelele tale gratuite fara setup extra.
_AIDER_KEY_ENV = {
    "groq":       ("GROQ_API_KEY", "groq"),
    "gemini":     ("GEMINI_API_KEY", "gemini"),
    "openai":     ("OPENAI_API_KEY", "chatgpt"),
    "deepseek":   ("DEEPSEEK_API_KEY", "deepseek"),
    "openrouter": ("OPENROUTER_API_KEY", "openroute"),
    "anthropic":  ("ANTHROPIC_API_KEY", "claude"),
    "mistral":    ("MISTRAL_API_KEY", "mistral"),
}


def aider_binary(cfg: dict) -> str | None:
    import shutil as _sh
    b = cfg.get("aider_binary") or ""
    if b and (os.path.isfile(b) or _sh.which(b)):
        return b
    return _sh.which("aider")


def _aider_env(cfg: dict) -> dict:
    """Env pentru Aider, cu cheia AI injectata din providers.json dupa prefixul modelului."""
    env = dict(os.environ)
    model = (cfg.get("aider_model") or "").strip().lower()
    prefix = model.split("/", 1)[0] if "/" in model else ""
    ev = _AIDER_KEY_ENV.get(prefix)
    if ev and ev[0] not in env:
        try:
            from ai_engine.config import load_keys
            key = (load_keys() or {}).get(ev[1], "")
            if key:
                env[ev[0]] = key
        except Exception:
            pass
    return env


def run_aider(cfg: dict, prompt: str) -> RunResult | None:
    """
    Editor liber Aider (open-source, gratuit): editeaza fisierele + face commit.
    Foloseste modelul din `aider_model` (implicit un model gratuit prin cheia ta groq).
    None → aider neinstalat (fallback pe copilot / mesaj onest).
    """
    binary = aider_binary(cfg)
    if not binary:
        return None
    cmd = [binary, "--yes-always", "--no-check-update", "--no-stream", "--message", prompt]
    model = (cfg.get("aider_model") or "").strip()
    if model:
        cmd += ["--model", model]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=cfg.get("claude_cwd", config.ROOT), env=_aider_env(cfg),
            timeout=cfg.get("claude_timeout_s", 600))
    except subprocess.TimeoutExpired:
        return RunResult(text="⏱ Aider a depasit timpul alocat.", level="aider", is_error=True)
    except Exception as e:
        return RunResult(text=f"(nu am putut porni Aider: {e})", level="aider", is_error=True)
    text = (proc.stdout or "").strip() or (proc.stderr or "").strip() or f"(Aider a rulat, cod {proc.returncode})"
    max_chars = cfg.get("claude_max_output_chars", 12000)
    if len(text) > max_chars:
        text = "…(inceput trunchiat)\n" + text[-max_chars:]   # pastreaza coada (rezumat/commit)
    return RunResult(text=text, level="aider", source=f"aider·{model or 'default'}",
                     is_error=proc.returncode != 0)


def run_copilot_write(cfg: dict, prompt: str) -> RunResult | None:
    """Copilot CLI in mod agentic (poate edita). None → Copilot neinstalat."""
    base = copilot_binary(cfg)
    if not base:
        return None
    # Doar CLI-ul agentic standalone poate edita; `gh copilot` e doar suggest/explain.
    if not (base == ["copilot"] or (len(base) == 1 and base[0].endswith("copilot"))):
        return None
    try:
        proc = subprocess.run(base + ["-p", prompt], capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              cwd=cfg.get("claude_cwd", config.ROOT),
                              timeout=cfg.get("claude_timeout_s", 600))
        out = (proc.stdout or "").strip() or (proc.stderr or "").strip()
        return RunResult(text=out or "(Copilot nu a intors nimic)", level="copilot",
                         source="copilot-write", is_error=proc.returncode != 0)
    except subprocess.TimeoutExpired:
        return RunResult(text="⏱ Copilot a depasit timpul alocat.", level="copilot", is_error=True)
    except Exception as e:
        return RunResult(text=f"(Copilot a esuat: {e})", level="copilot", is_error=True)


def available_editors(cfg: dict) -> dict:
    """Ce editoare de scriere sunt disponibile ACUM (pentru /editors + fallback)."""
    cop = copilot_binary(cfg)
    cop_write = bool(cop and (cop == ["copilot"] or (len(cop) == 1 and cop[0].endswith("copilot"))))
    return {"claude": claude_binary(cfg) is not None,
            "aider":  aider_binary(cfg) is not None,
            "copilot": cop_write}


def reserve_editor_name(cfg: dict) -> str | None:
    """Numele primului editor de REZERVA disponibil (dupa Claude): aider → copilot."""
    if not cfg.get("editor_fallback_enabled", True):
        return None
    eds = available_editors(cfg)
    if eds["aider"]:
        return "aider"
    if eds["copilot"]:
        return "copilot"
    return None


def run_reserve_editor(cfg: dict, backend: str, prompt: str) -> RunResult:
    """Ruleaza editorul de rezerva ales (aider/copilot) pe cererea data."""
    fn = {"aider": run_aider, "copilot": run_copilot_write}.get(backend)
    res = fn(cfg, prompt) if fn else None
    if res is not None:
        return res
    return RunResult(
        text="⚠️ Editorul de rezerva nu mai e disponibil. Instaleaza Aider "
             "(pip install aider-chat) sau foloseste Claude.",
        level="local", is_error=True)


# ── Orchestrare "claude ..." cu fallback ──────────────────────────────────────

def handle_claude(cfg: dict, prompt: str, resume: str | None = None,
                  mode: str = "read") -> RunResult:
    """Lantul complet: CLI → Claude API → surse AI → mesaj onest."""
    # 1. Claude Code CLI
    res = run_claude_cli(cfg, prompt, resume=resume, mode=mode)
    if res is not None and not (res.is_error and not res.text.strip()):
        return res

    # de aici incolo, fallback-urile nu pot executa tools de repo → doar analiza
    reason = "Claude CLI indisponibil" if res is None else "Claude CLI a esuat"

    # 2. Claude API direct
    if cfg.get("fallback_claude_api", True):
        api = run_claude_api(cfg, prompt)
        if api is not None:
            api.meta["fallback_reason"] = reason
            return api

    # 3. Sursele AI existente
    if cfg.get("fallback_ai_sources", True):
        from .ai_fast import answer
        txt, src = answer(cfg, prompt)
        if src:
            return RunResult(text=txt, level="ai-sources", source=src,
                             meta={"fallback_reason": reason})

    # 4. Onest
    return RunResult(
        text=(f"⚠️ {reason} si niciun fallback nu a raspuns. "
              "Doar comenzile locale (/status, /raport, /piete) sunt disponibile acum."),
        level="local", is_error=True, meta={"fallback_reason": reason})
