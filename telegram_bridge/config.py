"""
telegram_bridge.config — configurarea puntii.

Model identic cu ai_engine.config: DEFAULTS in cod + override optional dintr-un
fisier JSON local (data/telegram_bridge.json, gitignored ca tot data/). Token-ul
si chat_id-ul NU stau aici — se citesc din data/telegram_config.json (aceleasi
credentiale ca restul sistemului). Whitelist-ul implicit = chat_id-ul tau.
"""

from __future__ import annotations

import json
import os

ROOT      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR  = os.path.join(ROOT, "data")
CFG_PATH  = os.path.join(DATA_DIR, "telegram_bridge.json")
STATE_PATH = os.path.join(DATA_DIR, "telegram_bridge_state.json")
TG_CFG    = os.path.join(DATA_DIR, "telegram_config.json")
LOG_PATH  = os.path.join(DATA_DIR, "telegram_bridge.log")

# Binarul Claude Code instalat de installer-ul nativ (nu e pe PATH-ul de sistem).
_DEFAULT_CLAUDE = os.path.join(os.path.expanduser("~"), ".local", "bin", "claude.exe")

# Tool-uri READ-ONLY permise "claude ..." — analiza/rapoarte fara sa atinga nimic.
# Bash e limitat la comenzi de citire/diagnostic (git read, teste, rapoarte AI).
# Orice tool care nu e aici (Edit/Write/NotebookEdit, order_send etc.) e refuzat
# automat in modul headless — deci nu poate modifica cod, config sau piata.
_READONLY_TOOLS = [
    "Read", "Grep", "Glob",
    "Bash(git log:*)", "Bash(git status:*)", "Bash(git diff:*)",
    "Bash(git show:*)", "Bash(git branch:*)",
    "Bash(python -m ai_engine.report:*)",
    "Bash(python -m ai_engine.doctor:*)",
    "Bash(python -m ai_engine.selftest:*)",
    "Bash(python -m m0.audit:*)",
    "Bash(python scripts/test_*:*)",
    "Bash(python scripts/analiza_*:*)",
    "Bash(type:*)", "Bash(dir:*)", "Bash(findstr:*)",
]

# Tool-uri pentru modul de SCRIERE (Faza 3, activat doar cu allow_writes=true).
# Permite editari + rularea testelor/scripturilor de restart, NU bypass total.
_WRITE_TOOLS = _READONLY_TOOLS + [
    "Edit", "Write",
    "Bash(python scripts/test_*:*)",
    "Bash(git add:*)", "Bash(git commit:*)",
]

DEFAULTS: dict = {
    "enabled": True,

    # Whitelist HARD. Gol → se foloseste chat_id-ul din data/telegram_config.json.
    # Orice alt expeditor e ignorat + o alerta (rate-limited) catre proprietar.
    "allowed_chat_ids": [],

    # Long-polling getUpdates. 50s = aproape instant, ~1 request/50s in repaus.
    "poll_timeout_s": 50,
    # La pornire / dupa downtime, mesajele mai vechi de atat NU se executa (dar
    # offset-ul avanseaza) — nu vrem sa ruleze comenzi "statute".
    "ignore_messages_older_than_s": 180,

    # Cuvintele cheie. Mesajele FARA keyword sunt ignorate (nimic accidental nu porneste).
    "kw_claude":        "claude",    # agentul complet (read-only default)
    "kw_claude_resume": "claude+",   # continua ultima conversatie claude
    "kw_claude_write":  "claude!",    # cere modificare (2 pasi, gated de allow_writes)
    "kw_ai":            "ai",         # raspuns rapid de la sursele AI existente
    "kw_confirm":       "CONFIRM",    # confirmarea pasului de scriere

    # Nivele active.
    "level_instant_enabled": True,   # /status /raport /piete /ajutor  (mereu on)
    "level_ai_enabled":      True,   # "ai ..."
    "level_claude_enabled":  True,   # "claude ..."

    # ── Claude Code CLI (headless) ──
    "claude_binary":     "",         # "" = auto-detect (~/.local/bin/claude.exe → PATH)
    "claude_cwd":        ROOT,
    "claude_timeout_s":  600,        # un task nu poate depasi 10 min
    "claude_readonly_tools": _READONLY_TOOLS,
    "claude_resume_window_s": 1800,  # reply la un raspuns mai vechi de atat → sesiune noua
    "claude_max_output_chars": 12000,  # taie raspunsuri uriase inainte de chunking

    # ── Modul de SCRIERE (Faza 3) — OFF by default (siguranta) ──
    "allow_writes":       False,
    "write_tools":        _WRITE_TOOLS,
    "write_permission_mode": "acceptEdits",   # accepta editari; NU bypass total
    "confirm_timeout_s":  300,        # ai 5 min sa raspunzi CONFIRM <cod>

    # ── Lant de fallback pentru "claude ..." ──
    "fallback_claude_api": True,      # CLI picat → Claude API direct (sursa 'claude')
    "fallback_ai_sources": True,      # apoi → sursele AI existente (cerebras/mistral/...)
    "announce_fallback":   True,      # spune mereu pe ce nivel/sursa a raspuns

    # Sursa preferata pentru raspunsurile Claude-API-directe (fallback).
    "fallback_claude_provider": "claude",

    # ── Copilot (optional, pluggable) ──
    # Daca ai instalat GitHub Copilot CLI ("copilot" sau "gh copilot"), il poti folosi
    # ca sursa de executie alternativa cu prefixul kw_copilot. Detectat automat.
    "copilot_enabled":  False,
    "kw_copilot":       "copilot",
    "copilot_binary":   "",          # "" = auto-detect (copilot → gh copilot)

    # Un singur task greu (claude/ai/copilot) simultan; restul primesc "ocupat".
    "single_task": True,

    # API local (reutilizeaza pool-ul MT5 cache-uit — fara a doua conexiune MT5).
    "api_base": "http://localhost:8000/api",
    "api_timeout_s": 6,
}


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    if os.path.isfile(CFG_PATH):
        try:
            with open(CFG_PATH, encoding="utf-8") as f:
                user = json.load(f)
            cfg.update({k: v for k, v in user.items() if k in DEFAULTS})
        except Exception:
            pass
    if not cfg.get("claude_binary"):
        cfg["claude_binary"] = _DEFAULT_CLAUDE if os.path.isfile(_DEFAULT_CLAUDE) else "claude"
    return cfg


def load_credentials() -> tuple[str, str]:
    """(token, chat_id) din data/telegram_config.json, fallback pe env."""
    try:
        with open(TG_CFG, encoding="utf-8") as f:
            c = json.load(f)
        tok, cid = c.get("token", "").strip(), str(c.get("chat_id", "")).strip()
        if tok and cid:
            return tok, cid
    except Exception:
        pass
    return (os.environ.get("TELEGRAM_TOKEN", "").strip(),
            os.environ.get("TELEGRAM_CHAT_ID", "").strip())


def allowed_ids(cfg: dict) -> set[str]:
    """Setul de chat_id-uri autorizate. Gol in config → chat_id-ul din credentiale."""
    ids = {str(x).strip() for x in (cfg.get("allowed_chat_ids") or []) if str(x).strip()}
    if not ids:
        _, cid = load_credentials()
        if cid:
            ids.add(cid)
    return ids


def save_default_config() -> None:
    """Scrie un config.json de exemplu daca nu exista (prima rulare)."""
    if not os.path.isfile(CFG_PATH):
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(CFG_PATH, "w", encoding="utf-8") as f:
            json.dump(DEFAULTS, f, indent=2, ensure_ascii=False)
