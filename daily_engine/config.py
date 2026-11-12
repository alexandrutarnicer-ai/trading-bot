"""Config Daily Engine — `daily_engine/config.json` (auto-creat), hot-reload la fiecare iteratie.

Piete alese pe baza cercetarii din docs/DAILY_ENGINE_PLAN.md (sect. 8):
  - GBPUSD dimineata, deschiderea Londrei 08:00 (10:00 RO), OR 5 min, breakout, pana la 14:25 Londra
  - US500 dupa-amiaza, deschiderea New York 09:30 (16:30 RO), OR 30 min, directie, pana la 15:55 NY
Orele sunt in ORA LOCALA A BURSEI (DST-corect). `last_bar` = inceputul ultimei bare M5 din fereastra
(pozitia se inchide la sfarsitul ei: 14:30 Londra / 16:00 NY).
"""
from __future__ import annotations

import copy
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG_PATH = os.path.join(ROOT, "daily_engine", "config.json")
DATA_DIR = os.path.join(ROOT, "data", "daily_engine")

MODES = ("shadow", "execute")  # compat: modul GLOBAL = rezumat ("execute" daca macar o piata e Live)
# Modul PER PIATA (2026-11-12): live = ordine reale (DEMO, sau REAL deblocat in Trading LIVE) / shadow = virtual;
# pauza = campul `paused` (daily_engine/pause.py). Modul afisat: "pause" daca paused, altfel exec_mode.
MARKET_EXEC_MODES = ("live", "shadow")
PLOCK_DEFAULT = {"enabled": False, "trigger_R": 4.5, "lock_R": 4.0}
MARGIN_DEFAULT_PCT = 80.0      # marja TOTALA folosita dupa ordin <= X% din equity (toate engine-urile)
ENTRY_MODES = {"breakout": "brk", "direction": "dir"}
MAGIC = 880001               # rezervat pentru ordinele reale viitoare (api/mt5_pool.DAILY_MAGIC)

DEFAULTS: dict = {
    "mode": "shadow",
    "poll_seconds": 15,
    "notify_telegram": True,
    # Dimensionare — ACEEASI logica pe toate engine-urile (position_sizing): baza = equity MT5
    # (sau capital fix plafonat), × fractie, × risc%. In SHADOW se calculeaza doar lotul pe care
    # l-ar fi plasat (estimare in bani a trade-ului virtual), fara ordin.
    "sizing": {"capital_sync_mt5": True, "capital_usd": None, "fraction": 1.0, "risk_pct": 0.01,
               "max_margin_pct": MARGIN_DEFAULT_PCT},
    "markets": [
        {"symbol": "GBPUSD", "enabled": True, "label": "Dimineata — deschiderea Londrei",
         "tz": "Europe/London", "open": "08:00", "last_bar": "14:25",
         "or_minutes": 5, "entry": "breakout", "rr": None,
         "slip": 0.00002, "comm": 0.00007, "role": "observatie", "reentry": None,
         "preset": "london", "costs_mode": "manual"},
        {"symbol": "US500", "enabled": True, "label": "Dupa-amiaza — deschiderea New York",
         "tz": "America/New_York", "open": "09:30", "last_bar": "15:55",
         "or_minutes": 30, "entry": "direction", "rr": None,
         "slip": 0.10, "comm": 0.0, "role": "principal", "reentry": None,
         "preset": "new_york", "costs_mode": "manual"},
    ],
}


# Re-intrari in fereastra „fierbinte” (per piata, OPTIONAL — None / enabled=false = un trade pe zi, ca pana acum)
REENTRY_LIMITS = {"window_min": (15, 240, 60), "max_trades": (2, 10, 3), "max_consec_losses": (0, 10, 2),
                  "cooldown_bars": (1, 12, 1)}


def sanitize_reentry(r) -> dict:
    out = {"enabled": False, **{k: d for k, (_lo, _hi, d) in REENTRY_LIMITS.items()}}
    if isinstance(r, dict):
        out["enabled"] = bool(r.get("enabled", False))
        for k, (lo, hi, d) in REENTRY_LIMITS.items():
            try:
                out[k] = int(max(lo, min(hi, int(r.get(k, d)))))
            except (TypeError, ValueError):
                out[k] = d
    return out


def sanitize_rr(v) -> float | None:
    """R:R fix (TP = rr × risc). None / 0 = fara TP (implicit — pozitia ramane pana la SL sau final de fereastra)."""
    try:
        v = float(v) if v not in (None, "", False) else 0.0
    except (TypeError, ValueError):
        return None
    return round(max(0.5, min(10.0, v)), 2) if v > 0 else None


def sanitize_plock(p) -> dict:
    """Profit Lock per piata — OPRIT implicit. trigger >= 3R (fara plafon artificial; maxim tehnic 100R),
    0 <= lock < trigger. Valori invalide → corectate in limite (nu se activeaza niciodata singur)."""
    out = dict(PLOCK_DEFAULT)
    if isinstance(p, dict):
        out["enabled"] = bool(p.get("enabled", False))
        try:
            out["trigger_R"] = round(max(3.0, min(100.0, float(p.get("trigger_R", out["trigger_R"])))), 2)
        except (TypeError, ValueError):
            pass
        try:
            out["lock_R"] = round(float(p.get("lock_R", out["lock_R"])), 2)
        except (TypeError, ValueError):
            pass
        out["lock_R"] = round(max(0.0, min(out["trigger_R"] - 0.1, out["lock_R"])), 2)
    return out


def market_mode(m: dict) -> str:
    """Modul afisat al pietei: pause / live / shadow."""
    return "pause" if m.get("paused") else (m.get("exec_mode") if m.get("exec_mode") in MARKET_EXEC_MODES else "shadow")


def hm_to_min(s: str) -> int:
    hh, mm = s.split(":")
    return int(hh) * 60 + int(mm)


def _sanitize(cfg: dict) -> dict:
    out = copy.deepcopy(DEFAULTS)
    out.update({k: v for k, v in cfg.items() if k in DEFAULTS and k not in ("markets", "sizing")})
    sz = {**DEFAULTS["sizing"], **(cfg.get("sizing") or {})}
    try:
        sz["fraction"] = max(0.0, min(1.0, float(sz.get("fraction") or 0)))
        sz["risk_pct"] = max(0.0, min(0.02, float(sz.get("risk_pct") or 0)))
        sz["capital_sync_mt5"] = bool(sz.get("capital_sync_mt5", True))
        sz["max_margin_pct"] = max(10.0, min(95.0, float(sz.get("max_margin_pct") or MARGIN_DEFAULT_PCT)))
    except (TypeError, ValueError):
        sz = dict(DEFAULTS["sizing"])
    out["sizing"] = sz
    if out["mode"] not in MODES:
        out["mode"] = "shadow"
    legacy_mode = out["mode"]
    out["poll_seconds"] = max(5, min(120, int(out.get("poll_seconds") or 15)))
    mk = cfg.get("markets")
    if isinstance(mk, list) and mk:
        clean = []
        for m in mk:
            try:
                defaults = {d["symbol"]: d for d in DEFAULTS["markets"]}
                e = {**defaults.get(m.get("symbol"), {}), **m}
                if not e.get("symbol"):
                    continue
                hm_to_min(e["open"]), hm_to_min(e["last_bar"])
                if e.get("entry") not in ENTRY_MODES:
                    continue
                e["or_minutes"] = int(e.get("or_minutes") or 5)
                if e["or_minutes"] % 5 or not 5 <= e["or_minutes"] <= 120:
                    continue
                e["rr"] = sanitize_rr(e.get("rr"))
                e["reentry"] = sanitize_reentry(e.get("reentry"))
                e["slip"] = float(e.get("slip") or 0.0)
                e["comm"] = float(e.get("comm") or 0.0)
                e["enabled"] = bool(e.get("enabled", True))
                e["costs_mode"] = e.get("costs_mode") if e.get("costs_mode") in ("auto", "manual") else "manual"
                e["paused"] = bool(e.get("paused", False))          # pauza per piata (daily_engine/pause.py)
                e["paused_at"] = e.get("paused_at") if e["paused"] else None
                # modul per piata; config vechi (doar modul global) → acelasi mod pe fiecare piata (migrare fara efect)
                if e.get("exec_mode") not in MARKET_EXEC_MODES:
                    e["exec_mode"] = "live" if legacy_mode == "execute" else "shadow"
                e["mode"] = market_mode(e)
                e["profit_lock"] = sanitize_plock(e.get("profit_lock"))
                clean.append(e)
            except Exception:
                continue
        if clean:
            out["markets"] = clean
    for e in out["markets"]:                      # implicitele (fara „markets” in fisier) primesc aceleasi campuri
        e.setdefault("exec_mode", "live" if legacy_mode == "execute" else "shadow")
        e.setdefault("paused", False)
        e["mode"] = market_mode(e)
        e["profit_lock"] = sanitize_plock(e.get("profit_lock"))
    # modul GLOBAL = rezumat (compat cu cititorii vechi: dashboard, rapoarte, lifecycle)
    out["mode"] = "execute" if any(e["exec_mode"] == "live" for e in out["markets"]) else "shadow"
    return out


def load_config() -> dict:
    try:
        with open(CFG_PATH, encoding="utf-8") as f:
            return _sanitize(json.load(f))
    except Exception:
        return copy.deepcopy(DEFAULTS)


def save_default_config() -> None:
    if not os.path.isfile(CFG_PATH):
        with open(CFG_PATH, "w", encoding="utf-8") as f:
            json.dump(DEFAULTS, f, indent=2, ensure_ascii=False)
