"""
ai_engine.config — configurare motor AI.

Config-ul editabil de utilizator sta in ai_engine/config.json. Valorile de
mai jos sunt DEFAULTS + rails hard care nu pot fi depasite din JSON (clamp).
"""

import os
import json

ROOT     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG_PATH = os.path.join(ROOT, "ai_engine", "config.json")
AI_DATA  = os.path.join(ROOT, "data", "ai")

DEFAULTS: dict = {
    # Pietele urmarite. Alese pentru cont ~$1000 la levier 1:30 (verificat pe
    # specs reale ICMarketsEU 2026-07-08): risc la lot minim $2-4 (0.2-0.4%),
    # marja $33-45/pozitie. XAUUSD/BTCUSD/US30 NU incap la $1000: risc lot minim
    # $12-16 sau marja $260-310/pozitie — se pot adauga cand contul creste.
    "markets": ["EURUSD", "USDJPY", "GBPUSD", "AUDUSD", "USDCAD"],

    # Model LLM local (Ollama) — chei legacy, pastrate pentru compatibilitate.
    # Sursa de adevar noua este registrul "providers" de mai jos.
    "provider":     "ollama",
    "ollama_url":   "http://localhost:11434",
    "model":        "qwen3:8b",
    "model_opts":   {"temperature": 0.3, "num_ctx": 8192},

    # ── Registru deschis de surse AI (vezi docs/PLAN_SURSE_AI_MULTI_PROVIDER.md)
    # Tipuri: ollama | anthropic | gemini | openai_compatible.
    # "ollama" e sursa DEFAULT/safety-net: mereu prezenta, nu poate fi
    # dezactivata sau stearsa. Cheile API NU stau aici — vezi data/ai/providers.json.
    "providers": {
        "ollama": {"enabled": True,  "type": "ollama",
                   "model": "qwen3:8b", "url": "http://localhost:11434"},
        "claude": {"enabled": False, "type": "anthropic",
                   "model": "claude-haiku-4-5"},
        "gemini": {"enabled": False, "type": "gemini",
                   "model": "gemini-2.5-flash"},
        "chatgpt": {"enabled": False, "type": "openai_compatible",
                    "model": "gpt-4o-mini",
                    "base_url": "https://api.openai.com/v1"},
    },
    # Ce sursa joaca fiecare rol din consiliu. Se pot imparti oricum;
    # schimbarile din UI se aplica la urmatorul consiliu (fara restart).
    "role_assignments": {
        "technical":   "ollama",
        "macro":       "ollama",
        "risk":        "ollama",
        "head_trader": "ollama",
    },

    # Cadenta: perceptia ruleaza la fiecare bara M15; consiliul doar pe trigger.
    "bar_minutes":            15,
    "heartbeat_hours":        24,   # minim un consiliu per piata pe zi
    "council_cooldown_min":   120,  # minim intre doua consilii pe aceeasi piata
    "position_review_hours":  4,    # review pozitie deschisa

    # Executie. mode: "demo" = ordine reale pe cont DEMO; "shadow" = doar log.
    "mode":            "demo",
    "magic":           770015,      # namespace MT5 al motorului AI
    "comment_prefix":  "AI",

    # Rails de risc HARD (clamp peste orice decide consiliul).
    "risk_pct_default":   0.005,   # 0.5% din equity per trade
    "risk_pct_max":       0.01,    # consiliul nu poate cere mai mult de 1%
    "max_open_positions": 3,       # total pozitii AI simultane
    "max_daily_loss_R":   3.0,     # stop pe zi: dupa -3R cumulat, nu mai deschide
    "min_rr":             1.0,     # TP/SL minim acceptat (rail hard)
    "target_rr":          2.0,     # tinta cand reparam un TP prea aproape (>= min_rr)
    "max_sl_atr_mult":    5.0,     # SL nu poate fi mai departe de 5*ATR
    "decision_valid_bars": 8,      # ordinele stop neactivate expira dupa N bare

    # Inchidere weekend (piete FX/indici) — cripto (XRP/BTC...) e exceptat, ruleaza non-stop.
    "weekend_close_enabled": True, # Vineri: inchide pozitiile + anuleaza pending; nu deschide Sam/Dum
    "weekend_close_hour":    22,   # Vineri, ora RO (Europe/Bucharest), de la care FX e "inchis"
}


def load_config() -> dict:
    """DEFAULTS + override din config.json, cu clamp pe rails."""
    cfg = dict(DEFAULTS)
    if os.path.isfile(CFG_PATH):
        try:
            with open(CFG_PATH, encoding="utf-8") as f:
                user = json.load(f)
            cfg.update({k: v for k, v in user.items() if k in DEFAULTS})
        except Exception:
            pass
    # Rails: orice ar scrie utilizatorul/consiliul, limitele hard raman.
    cfg["risk_pct_max"]       = min(float(cfg["risk_pct_max"]), 0.02)
    cfg["max_open_positions"] = min(int(cfg["max_open_positions"]), 6)

    # ── Normalizare registru surse ──
    provs = dict(cfg.get("providers") or {})
    # ollama = safety net: exista mereu, enabled mereu; url/model din legacy daca lipsesc
    ol = dict(provs.get("ollama") or {})
    ol["type"]    = "ollama"
    ol["enabled"] = True
    ol.setdefault("model", cfg.get("model", "qwen3:8b"))
    ol.setdefault("url",   cfg.get("ollama_url", "http://localhost:11434"))
    provs["ollama"] = ol
    cfg["providers"] = provs

    # asignari de rol: doar surse existente; fallback pe ollama
    ra = dict(cfg.get("role_assignments") or {})
    for role in ("technical", "macro", "risk", "head_trader"):
        if ra.get(role) not in provs:
            ra[role] = "ollama"
    cfg["role_assignments"] = ra

    os.makedirs(AI_DATA, exist_ok=True)
    return cfg


# ── Chei API (local, gitignored — data/* e ignorat) ─────────────────────────

KEYS_PATH = os.path.join(AI_DATA, "providers.json")


def load_keys() -> dict:
    """{nume_sursa: api_key}. Fisier local, niciodata comis in git."""
    try:
        with open(KEYS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_key(name: str, api_key: str) -> None:
    os.makedirs(AI_DATA, exist_ok=True)
    keys = load_keys()
    if api_key:
        keys[name] = api_key
    else:
        keys.pop(name, None)
    with open(KEYS_PATH, "w", encoding="utf-8") as f:
        json.dump(keys, f, indent=2)


def save_default_config() -> None:
    """Scrie config.json cu defaults daca nu exista (prima rulare)."""
    if not os.path.isfile(CFG_PATH):
        with open(CFG_PATH, "w", encoding="utf-8") as f:
            json.dump(DEFAULTS, f, indent=2, ensure_ascii=False)
