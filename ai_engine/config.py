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

    # Model LLM local (Ollama). Schimbabil fara cod.
    "provider":     "ollama",
    "ollama_url":   "http://localhost:11434",
    "model":        "qwen3:8b",
    "model_opts":   {"temperature": 0.3, "num_ctx": 8192},

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
    "min_rr":             1.0,     # TP/SL minim acceptat
    "max_sl_atr_mult":    5.0,     # SL nu poate fi mai departe de 5*ATR
    "decision_valid_bars": 8,      # ordinele stop neactivate expira dupa N bare
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
    os.makedirs(AI_DATA, exist_ok=True)
    return cfg


def save_default_config() -> None:
    """Scrie config.json cu defaults daca nu exista (prima rulare)."""
    if not os.path.isfile(CFG_PATH):
        with open(CFG_PATH, "w", encoding="utf-8") as f:
            json.dump(DEFAULTS, f, indent=2, ensure_ascii=False)
