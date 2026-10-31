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
    "model":        "qwen3:1.7b",
    "model_opts":   {"temperature": 0.3, "num_ctx": 4096},

    # ── Registru deschis de surse AI (vezi docs/PLAN_SURSE_AI_MULTI_PROVIDER.md)
    # Tipuri: ollama | anthropic | gemini | openai_compatible.
    # "ollama" e sursa DEFAULT/safety-net: mereu prezenta, nu poate fi
    # dezactivata sau stearsa. Cheile API NU stau aici — vezi data/ai/providers.json.
    "providers": {
        "ollama": {"enabled": True,  "type": "ollama",
                   "model": "qwen3:1.7b", "url": "http://localhost:11434"},
        # Sursele suportate (2026-10-31): DOAR ollama (local) + gemini (cloud).
        # Celelalte (claude/chatgpt/groq/mistral/...) au fost eliminate: indisponibile,
        # rate-limit cronic (mistral 429) sau neplatite. Tipurile de adaptor raman in
        # providers.py (o sursa noua se poate adauga din UI), dar nu exista sabloane.
        "gemini": {"enabled": False, "type": "gemini",
                   "model": "gemini-2.5-flash"},
    },
    # Ce sursa joaca fiecare rol din consiliu. Se pot imparti oricum;
    # schimbarile din UI se aplica la urmatorul consiliu (fara restart).
    "role_assignments": {
        "technical":       "ollama",
        "macro":           "ollama",
        "risk":            "ollama",
        "head_trader":     "ollama",
    },

    # ── Roluri suplimentare de consiliu (Feature: Additional AI Roles) ──
    # Dezactivate by default → consiliul e EXACT cel de dinainte (4 roluri).

    # ── Semnal de regim trend/chop in briefing (Feature: Regime Awareness) ──
    # True → briefing-ul include eficienta de trend (Kaufman ER) + eticheta CHOPPY/
    # TRENDING/NEUTRAL, iar consiliul o considera (evita breakout-uri in chop). False
    # → briefing IDENTIC cu versiunea de dinainte. Hot-reload per iteratie.
    "regime_aware":                  True,

    # ── Consiliu multiplu (Feature: Multi-Council Consensus) ──
    # Motorul autonom: consiliul PRIMAR construieste trade-ul; daca sunt configurate
    # surse secundare/tertiare, acele consilii REVIZUIESC trade-ul propus si executia
    # e gate-uita de consens. Toate None → un singur consiliu (comportamentul de azi).
    "council_primary_source":   None,   # None = distribuit pe roluri (role_assignments)
    "council_secondary_source": None,   # sursa consiliului 2 (optional, distincta)
    "council_tertiary_source":  None,   # sursa consiliului 3 (optional, distincta)
    "consensus_threshold":      70,     # media increderilor >= prag → executa

    # Cadenta: perceptia ruleaza la fiecare bara M15; consiliul doar pe trigger.
    "bar_minutes":            15,
    "heartbeat_hours":        24,   # minim un consiliu per piata pe zi
    "council_cooldown_min":   120,  # minim intre doua consilii pe aceeasi piata
    "position_review_hours":  4,    # review pozitie deschisa
    # Trigger-e DEZACTIVATE (nu mai convoaca consiliul). [] = toate active (ca inainte).
    # Valori: regime_flip, breakout_tension, vol_spike, news_window, position_review,
    # heartbeat. Motivatie (2026-10-31, ledger real 89 trade-uri): breakout_tension =
    # 76% din consilii si -0.24R/trade; regime_flip singurul pozitiv (+0.40R, n=12).
    "disabled_triggers":      [],

    # Executie. mode: "demo" = ordine reale pe cont DEMO; "shadow" = doar log.
    "mode":            "demo",
    "magic":           770015,      # namespace MT5 al motorului AI
    "comment_prefix":  "AI",

    # ── Capitalul motorului AI (baza de sizing) ──
    # sync ON (default) = equity-ul REAL din MT5 la fiecare ordin (ca pana acum).
    # sync OFF = capitalul FIX alocat AI-ului (capital_usd) — restul contului nu
    # participa la sizing; daca depaseste equity-ul real, se foloseste equity-ul
    # (nu poti aloca mai mult decat exista). Per piata se aplica in continuare
    # market_overrides.capital_fraction peste aceasta baza.
    "capital_sync_mt5":   True,
    "capital_usd":        1000.0,

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

    # ── Config PER PIATA (market_overrides) — toate campurile OPTIONALE ──
    # O piata fara override se comporta EXACT ca pana acum. Campuri per simbol:
    #   capital_fraction   (0.05-1.0, default 1.0) — fractia din equity folosita ca
    #                      baza de sizing pe piata (risc $ = equity*fraction*risk_pct)
    #   risk_pct           (cap per trade pe piata; clamp la risk_pct_max global)
    #   max_rr             (1-10; TP peste e LIMITAT la max_rr; consiliul e informat)
    #   max_daily_loss_R   (stop zilnic PE PIATA, separat de stopul global -3R)
    #   max_trades_per_day (anti-overtrading: max ordine plasate/zi pe piata)
    #   fixed_lots         (0.01-100; volum FIX per ordin pe piata — inlocuieste
    #                      sizing-ul dinamic pe risc; None = sizing dinamic, ca acum)
    #   isolated           (true = piata "in observatie": rezultatele ei NU intra in
    #                      scorecard-ul principal; raman vizibile per piata)
    "market_overrides": {},
}

# Valorile implicite ale unui override — identice cu comportamentul fara override.
MARKET_OVERRIDE_DEFAULTS = {
    "capital_fraction":   1.0,    # tot equity-ul (ca pana acum)
    "risk_pct":           None,   # None = riscul decis de consiliu (clamp global)
    "max_rr":             None,   # None = fara plafon RR (ca pana acum)
    "max_daily_loss_R":   None,   # None = doar stopul global de zi
    "max_trades_per_day": None,   # None = fara limita per piata
    "fixed_lots":         None,   # None = sizing dinamic pe risc (ca pana acum)
    # Mod piata (2026-10-31, inlocuieste „isolated" care DOAR excludea din scorecard,
    # dar piata continua sa tranzactioneze — confuz): "active" = tranzactioneaza;
    # "observe" = consiliul analizeaza, deciziile se salveaza ca SHADOW, ZERO ordine
    # noi (inchiderea pozitiilor existente ramane permisa), excluse din scorecard.
    "mode":               "active",
}


def sanitize_market_overrides(raw: dict | None, risk_pct_max: float = 0.02) -> dict:
    """Curata + clamp-uieste override-urile per piata (folosit de load_config SI de API)."""
    out: dict = {}
    for sym, ov in (raw or {}).items():
        if not isinstance(ov, dict):
            continue
        clean: dict = {}
        try:
            if ov.get("capital_fraction") is not None:
                clean["capital_fraction"] = max(0.05, min(1.0, float(ov["capital_fraction"])))
            if ov.get("risk_pct") is not None:
                clean["risk_pct"] = max(0.0005, min(float(ov["risk_pct"]), float(risk_pct_max)))
            if ov.get("max_rr") is not None:
                clean["max_rr"] = max(1.0, min(10.0, float(ov["max_rr"])))
            if ov.get("max_daily_loss_R") is not None:
                clean["max_daily_loss_R"] = max(0.25, min(10.0, float(ov["max_daily_loss_R"])))
            if ov.get("max_trades_per_day") is not None:
                clean["max_trades_per_day"] = max(1, min(20, int(ov["max_trades_per_day"])))
            if ov.get("fixed_lots") is not None:
                clean["fixed_lots"] = round(max(0.01, min(100.0, float(ov["fixed_lots"]))), 2)
            # compat: vechiul isolated:true → mode observe (intentia „piata in observatie")
            mode = str(ov.get("mode") or ("observe" if ov.get("isolated") else "active")).lower()
            if mode == "observe":
                clean["mode"] = "observe"
        except (TypeError, ValueError):
            continue   # override corupt → ignorat (fail-safe: comportament default)
        if clean:
            out[str(sym).strip().upper()] = clean
    return out


def market_cfg(cfg: dict, symbol: str) -> dict:
    """Config-ul REZOLVAT al unei piete: DEFAULTS + override-ul ei (daca exista).
    `_has_overrides` = piata are cel putin un camp configurat explicit.
    O piata NOUA (fara override) primeste pure default-uri = comportament global."""
    ov = (cfg.get("market_overrides") or {}).get(symbol) or {}
    m = dict(MARKET_OVERRIDE_DEFAULTS)
    m.update(ov)
    if m.get("isolated") and "mode" not in ov:      # config vechi nesanitizat
        m["mode"] = "observe"
    m["isolated"] = m["mode"] == "observe"
    # doar LIMITELE conteaza pentru briefing (modul nu se comunica consiliului)
    m["_has_overrides"] = bool(set(ov) - {"mode", "isolated"})
    return m


def isolated_markets(cfg: dict) -> list[str]:
    """
    Pietele marcate `isolated` in market_overrides — derivate din OVERRIDE-URI,
    nu din lista `markets`: o piata izolata SCOASA din urmarire ramane izolata,
    ca istoricul ei sa nu reintre pe tacute in scorecard-ul principal. (Config-ul
    ei ramane salvat si e re-aplicat automat daca piata e re-adaugata.)
    """
    return sorted(s for s, ov in (cfg.get("market_overrides") or {}).items()
                  if isinstance(ov, dict) and (ov.get("mode") == "observe" or ov.get("isolated")))


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
    cfg["max_open_positions"] = max(1, min(int(cfg["max_open_positions"]), 6))
    # Capitalul AI: sync bool robust + clamp pe capitalul fix (corupt → defaults).
    cfg["capital_sync_mt5"] = bool(cfg.get("capital_sync_mt5", True))
    try:
        cfg["capital_usd"] = max(10.0, min(1_000_000.0, float(cfg.get("capital_usd", 1000.0))))
    except (TypeError, ValueError):
        cfg["capital_usd"] = 1000.0
    # Pragul de consens: clamp in banda utila (sub 50 = fara sens, peste 90 = paralizie).
    try:
        cfg["consensus_threshold"] = max(50, min(90, int(cfg.get("consensus_threshold", 70))))
    except (TypeError, ValueError):
        cfg["consensus_threshold"] = 70
    _TRIG = {"regime_flip", "breakout_tension", "vol_spike", "news_window",
             "position_review", "heartbeat"}
    dt = cfg.get("disabled_triggers")
    cfg["disabled_triggers"] = sorted({str(x) for x in dt if str(x) in _TRIG})         if isinstance(dt, (list, tuple)) else []
    # Override-uri per piata: curatate + clamp-uite (corupt → ignorat, default-uri raman)
    cfg["market_overrides"] = sanitize_market_overrides(
        cfg.get("market_overrides"), cfg["risk_pct_max"])

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

    # Consilii multiple ELIMINATE (2026-10-31; rolurile Quant/Devil la fel): un singur
    # consiliu (sursa primara → failover → Ollama). Fortat indiferent de config.json.
    cfg["council_secondary_source"] = None
    cfg["council_tertiary_source"] = None

    # surse de consiliu multiplu: doar surse existente si enabled (altfel None)
    for key in ("council_primary_source", "council_secondary_source",
                "council_tertiary_source"):
        src = cfg.get(key)
        if src is not None and not (isinstance(provs.get(src), dict)
                                    and provs[src].get("enabled")):
            cfg[key] = None

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
