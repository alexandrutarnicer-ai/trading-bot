"""Configurarea Noisy Engine — `noisy_engine/config.json` (hot-reload la fiecare iteratie).

Valorile implicite vin din research (docs/NOISY_ENGINE_RESEARCH.md): USDJPY, M5, mean reversion la
EMA20 ± 2×ATR14, SL 1,5×ATR, tinta = EMA20, stop de timp 20 de bare, doar in fereastra lichida.
Toate limitele sunt OPTIONALE (enabled true/false). Implicit SHADOW (trade-uri virtuale, zero ordine);
EXECUTIE = ordine reale doar pe DEMO sau pe REAL deblocat explicit in Settings → Trading LIVE.
"""
from __future__ import annotations

import copy
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG_PATH = os.path.join(ROOT, "noisy_engine", "config.json")
DATA_DIR = os.path.join(ROOT, "data", "noisy_engine")

MODES = ("shadow", "execute")  # shadow = virtual (implicit); execute = ordine reale (DEMO, sau REAL deblocat in Trading LIVE)
TIMEFRAMES = {"M1": 1, "M5": 5}  # minute pe bara; M1 = implicit (decizia userului: multe trade-uri / ora)
MAGIC = 990001                 # rezervat pentru ordinele reale viitoare

DEFAULTS: dict = {
    "mode": "shadow",
    "symbol": "USDJPY",
    # M1 = implicit: scopul e FRECVENTA (mai multe trade-uri / ora), nu profitul — decizia userului
    # 2026-11-01. Research: pe M1 rezultatul e ~0 dupa costuri (USDJPY −0,01R/trade la spread 0,1 pip,
    # puternic negativ cu comision Raw). M5 ramane optiune (~3–4/zi, +0,08R in backtest).
    "timeframe": "M1",
    "poll_seconds": 5,
    "notify_telegram": True,
    "notify_trades": False,          # pe M1 ar fi zeci de mesaje / zi; pornire / blocari / buget se trimit mereu
    # la Stop / Emergency Stop / buget epuizat in EXECUTIE: "close" = inchide pozitiile Noisy (recomandat:
    # tinerea medie e de minute, nesupravegheate contrazic ideea de engine controlat) | "keep" = raman cu SL/TP
    "on_stop": "close",
    # fereastra in care are voie sa INTRE (ora RO): unul sau mai multe INTERVALE (ex. 10:00–13:00 si 16:00–22:00)
    # in zilele bifate. Un interval poate trece peste miezul noptii (22:00–02:00 = ziua in care INCEPE). Pozitiile
    # deschise se termina dupa regulile lor (stop de timp); nicio intrare care ar ramane deschisa peste miezul noptii.
    # `start` / `end` = primul interval (compatibilitate cu cititorii vechi); sursa de adevar = `intervals`.
    "window": {"intervals": [{"start": "10:00", "end": "20:00"}], "days": [0, 1, 2, 3, 4], "start": "10:00", "end": "20:00"},
    "strategy": {
        "ema": 20, "atr": 14,
        "dev_atr": 2.0,               # intrare cand inchiderea e la > 2×ATR de EMA20 (contra miscarii)
        "sl_atr": 1.5,                # SL = 1,5×ATR de la intrare
        "time_stop_bars": 20,         # iesire la inchidere dupa 20 de bare (M1 = 20 min) daca nu a atins SL/TP
        # pauza dupa iesire: OPRITA implicit — in backtest (12 luni USDJPY) pauza 3/6 bare scadea
        # expectancy de la +0,070R la +0,059R (test ≈ 0): mean reversion reintra des pe acelasi dezechilibru
        "cooldown_bars": 0,
        "cooldown_after_sl_bars": 0,
        "max_flips_per_hour": 3,      # > 3 schimbari de directie intr-o ora → fara intrari pana la ora urmatoare
        "trend_filter": False,        # OPTIONAL: nu intra cand piata e in trend (efficiency ratio)
        "er_bars": 20, "er_trend": 0.35,
        # spread_floor / spread_max = DERIVATE (unitati de pret) din sectiunea `spread` de mai jos, prin
        # resolve_spread (engine + backtest). Valorile de aici sunt doar rezerva cand nu se cunoaste `point`.
        "spread_floor": 0.001,
        "spread_max": 0.0,
        "min_atr_over_cost": 5.0,     # ATR ≥ 5× costul dus-intors (pe M1; M5 testat cu 15), altfel miscarea e prea mica
        "slip_frac": 0.25,            # slippage presupus: 25% din spread la intrare si la iesire
        "comm_price": 0.0,            # comision in unitati de pret (0 = contul actual)
        # R:R configurabil: 0 = tinta = revenirea la EMA20 (testat, implicit; ~1,6R in medie);
        # > 0 = tinta fixa la tp_rr × risc (ex. 2.0 = 2R). Backtest 12 luni: tintele fixe NU au ajutat.
        "tp_rr": 0.0,
    },
    # Break-Even — ACEEASI regula si aceiasi parametri ca in Custom Engine (engine/simulator.py), procente
    # din distanta intrare → tinta. Faza 1: pretul atinge trigger% si se intoarce → SL la lock1%.
    # Faza 2 (optionala): retragere in zona lock1–zone%, din nou trigger% si intoarcere → SL la lock2%.
    # OPRIT implicit — backtest 12 luni: nu a crescut profitul (vezi docs/NOISY_ENGINE_RESEARCH.md).
    "break_even": {"enabled": False, "trigger_pct": 80, "lock1_pct": 30,
                   "phase2_enabled": True, "phase2_zone_pct": 40, "lock2_pct": 50},
    # Profil PER TIMEFRAME: la comutarea M1 ⇄ M5 limitele si filtrul cost/ATR se schimba singure (valorile
    # testate pe fiecare). `limits` / `strategy.min_atr_over_cost` de mai jos = profilul timeframe-ului ACTIV.
    "tf_profiles": {
        "M1": {"limits": {"max_trades_day": {"enabled": True, "value": 60},
                          "max_losses_day": {"enabled": True, "value": 25},
                          "max_consec_losses": {"enabled": True, "value": 8}},
               "min_atr_over_cost": 5.0},
        "M5": {"limits": {"max_trades_day": {"enabled": True, "value": 6},
                          "max_losses_day": {"enabled": True, "value": 4},
                          "max_consec_losses": {"enabled": True, "value": 3}},
               "min_atr_over_cost": 15.0},
    },
    # SPREAD — in POINTS MT5 (coloana „Spread” din Market Watch; USDJPY: 1 point = 0,001 = 0,1 pips).
    # Doua valori DISTINCTE (inainte, `spread_floor` facea tot: cost + limita + filtrul cost/ATR):
    #   tipic  = costul presupus al unui trade (intra si in filtrul „ATR ≥ N × cost”)
    #            auto   = mediana spread-ului LIVE masurat de engine din tick-urile MT5 (inghetata pe zi,
    #                     la prima iteratie din fereastra — recalcularea zilei ramane identica)
    #            manual = manual_points
    #   maxim  = spread-ul LIVE peste care semnalul e respins: auto = max_mult × tipic; manual = max_points
    # Atentie: istoricul MT5 (barele) are spread-ul BRUT, fara markup-ul contului Standard (USDJPY 1 vs 9
    # points live) — de aceea tipicul vine din tick-urile live, nu din bare.
    "spread": {"mode": "auto", "manual_points": 9.0, "max_mode": "auto", "max_mult": 1.5, "max_points": 15.0},
    "news": {"enabled": True, "pre_min": 5, "post_min": 15},   # stiri High pe valutele pietei
    # limitele ACTIVE (toate OPTIONALE, resetate zilnic, ora RO) — derivate din tf_profiles[timeframe].
    # M1: ~25–30 trade-uri / zi (limitele taie doar zilele extreme, DD −130R → −117R); M5: 6 / 4 / 3.
    "limits": {
        "max_trades_day": {"enabled": True, "value": 60},
        "max_losses_day": {"enabled": True, "value": 25},
        "max_consec_losses": {"enabled": True, "value": 8},
    },
    # buget IZOLAT: P&L-ul trade-urilor Noisy (realizat + flotant), NU equity-ul contului
    "budget": {"capital": 40.0, "min_remaining": 30.0},
    "sizing": {"risk_pct": 0.01},                            # risc per trade, % din bugetul engine-ului
}


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def hm_to_min(s: str) -> int:
    h, m = str(s).split(":")
    return int(h) * 60 + int(m)


def _fmt_hm(mins: int) -> str:
    return f"{mins // 60 % 24:02d}:{mins % 60:02d}"


def _segments(a: int, b: int) -> list[tuple[int, int]]:
    """Intervalul [a, b) in minute pe [0, 1440); peste miezul noptii (a > b) → doua bucati."""
    return [(a, b)] if a < b else [(a, 1440), (0, b)]


def validate_intervals(intervals) -> list[str]:
    """Erorile unei liste de intervale (pentru API — userul afla de ce nu se salveaza). [] = valida."""
    errs: list[str] = []
    if not isinstance(intervals, list) or not intervals:
        return ["cel puțin un interval orar este obligatoriu"]
    segs = []
    for n, it in enumerate(intervals, 1):
        try:
            a, b = hm_to_min(it["start"]), hm_to_min(it["end"])
        except Exception:
            errs.append(f"intervalul {n}: oră invalidă (format HH:MM)")
            continue
        if not (0 <= a < 1440 and 0 <= b < 1440):
            errs.append(f"intervalul {n}: oră în afara 00:00–23:59")
            continue
        if a == b:
            errs.append(f"intervalul {n}: început = sfârșit ({it['start']}) — durată zero")
            continue
        segs += [(x, y, n) for x, y in _segments(a, b)]
    for i, (a1, b1, n1) in enumerate(segs):
        for a2, b2, n2 in segs[i + 1:]:
            if n1 != n2 and a1 < b2 and a2 < b1:
                errs.append(f"intervalele {n1} și {n2} se suprapun")
    return sorted(set(errs))


def normalize_intervals(intervals) -> list[dict]:
    """Varianta TOLERANTA (la incarcare): ignora intervalele invalide, uneste suprapunerile, sorteaza dupa
    inceput; lista goala → 10:00–20:00 (implicitul testat). Intervalele peste miezul noptii raman intregi."""
    out: list[tuple[int, int]] = []
    for it in intervals if isinstance(intervals, list) else []:
        try:
            a, b = hm_to_min(it["start"]) % 1440, hm_to_min(it["end"]) % 1440
        except Exception:
            continue
        if a != b:
            out.append((a, b))
    if not out:
        return [{"start": "10:00", "end": "20:00"}]
    # uneste suprapunerile (pe minute, inclusiv peste miezul noptii)
    cover = [False] * 1440
    for a, b in out:
        for x, y in _segments(a, b):
            for m in range(x, y):
                cover[m] = True
    if all(cover):
        return [{"start": "00:00", "end": "23:59"}]          # toata ziua (00:00–00:00 ar fi durata zero)
    starts = [m for m in range(1440) if cover[m] and not cover[m - 1]]
    res = []
    for a in starts:
        b = a
        while cover[b % 1440]:
            b += 1
        res.append((a, b % 1440))
    res.sort()
    return [{"start": _fmt_hm(a), "end": _fmt_hm(b)} for a, b in res]


def in_intervals(t, w: dict) -> bool:
    """t (datetime RO) e intr-unul din intervalele ferestrei, intr-o zi bifata. Pentru un interval peste miezul
    noptii, partea de dupa 00:00 apartine zilei in care a INCEPUT intervalul."""
    m = t.hour * 60 + t.minute
    wd = t.weekday()
    days = w["days"]
    for it in w.get("intervals") or [{"start": w["start"], "end": w["end"]}]:
        a, b = hm_to_min(it["start"]), hm_to_min(it["end"])
        if a < b:
            if a <= m < b and wd in days:
                return True
        else:
            if (m >= a and wd in days) or (m < b and (wd - 1) % 7 in days):
                return True
    return False


def intervals_label(w: dict) -> str:
    return ", ".join(f"{it['start']}–{it['end']}" for it in w.get("intervals") or [])


def _num(v, lo, hi, default):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


def sanitize(cfg: dict) -> dict:
    c = _merge(DEFAULTS, cfg)
    c["mode"] = c["mode"] if c["mode"] in MODES else "shadow"
    c["symbol"] = str(c.get("symbol") or "USDJPY").upper()
    c["timeframe"] = c["timeframe"] if c.get("timeframe") in TIMEFRAMES else "M1"
    c["on_stop"] = c["on_stop"] if c.get("on_stop") in ("close", "keep") else "close"
    c["notify_trades"] = bool(c.get("notify_trades", False))
    c["poll_seconds"] = int(_num(c["poll_seconds"], 2, 120, 5))
    w = c["window"]
    raw_w = (cfg or {}).get("window") or {}
    if "intervals" not in raw_w and ("start" in raw_w or "end" in raw_w):        # config vechi: un singur interval
        w["intervals"] = [{"start": raw_w.get("start", "10:00"), "end": raw_w.get("end", "20:00")}]
    w["intervals"] = normalize_intervals(w.get("intervals"))
    w["start"], w["end"] = w["intervals"][0]["start"], w["intervals"][0]["end"]
    w["days"] = sorted({int(x) for x in w.get("days", []) if str(x).isdigit() and 0 <= int(x) <= 6}) or [0, 1, 2, 3, 4]
    s, d = c["strategy"], DEFAULTS["strategy"]
    s["ema"] = int(_num(s["ema"], 5, 200, 20))
    s["atr"] = int(_num(s["atr"], 5, 100, 14))
    s["dev_atr"] = _num(s["dev_atr"], 0.5, 6, d["dev_atr"])
    s["sl_atr"] = _num(s["sl_atr"], 0.3, 6, d["sl_atr"])
    s["time_stop_bars"] = int(_num(s["time_stop_bars"], 2, 200, 20))
    s["cooldown_bars"] = int(_num(s["cooldown_bars"], 0, 100, 0))
    s["cooldown_after_sl_bars"] = int(_num(s["cooldown_after_sl_bars"], 0, 200, 0))
    s["max_flips_per_hour"] = int(_num(s["max_flips_per_hour"], 0, 50, 3))
    s["trend_filter"] = bool(s["trend_filter"])
    s["er_bars"] = int(_num(s["er_bars"], 5, 200, 20))
    s["er_trend"] = _num(s["er_trend"], 0.05, 1, 0.35)
    s["spread_floor"] = _num(s.get("spread_floor"), 0, 1e6, 0.001)
    s["spread_max"] = _num(s.get("spread_max"), 0, 1e6, 0.0)
    legacy = (cfg or {}).get("strategy") or {}
    sp = c["spread"]
    if "spread" not in (cfg or {}) and ("spread_floor" in legacy or "spread_max_mult" in legacy):
        # config vechi (spread_floor in PRET + multiplicator) → mod manual, aceleasi valori; convertit in
        # points la prima rezolvare (cand `point` e cunoscut) — comportament identic cu inainte
        sp.update(mode="manual", manual_points=None, legacy_floor_price=_num(legacy.get("spread_floor"), 0, 1e6, 0.001),
                  max_mode="auto", max_mult=_num(legacy.get("spread_max_mult"), 0, 20, 1.5))
    s.pop("spread_max_mult", None)                      # inlocuit de spread.max_* (rezolvat in strategy.spread_max)
    sp["mode"] = sp.get("mode") if sp.get("mode") in ("auto", "manual") else "auto"
    sp["max_mode"] = sp.get("max_mode") if sp.get("max_mode") in ("auto", "manual") else "auto"
    sp["manual_points"] = None if sp.get("manual_points") is None else _num(sp["manual_points"], 0, 1e6, 9.0)
    sp["max_mult"] = _num(sp.get("max_mult"), 0, 20, 1.5)
    sp["max_points"] = _num(sp.get("max_points"), 0, 1e7, 15.0)
    s["min_atr_over_cost"] = _num(s["min_atr_over_cost"], 0, 200, 5)
    s["slip_frac"] = _num(s["slip_frac"], 0, 5, 0.25)
    s["comm_price"] = _num(s["comm_price"], 0, 1e6, 0.0)
    s["tp_rr"] = _num(s.get("tp_rr"), 0, 20, 0.0)
    for k in ("be_trigger_R", "be_lock_R"):          # chei vechi (prototip) — inlocuite de break_even
        s.pop(k, None)
    be = c["break_even"]
    be["enabled"] = bool(be.get("enabled", False))
    be["phase2_enabled"] = bool(be.get("phase2_enabled", True))
    be["trigger_pct"] = _num(be.get("trigger_pct"), 50, 99, 80)          # aceleasi limite ca in Custom Engine
    be["lock1_pct"] = _num(be.get("lock1_pct"), 5, 60, 30)
    be["phase2_zone_pct"] = _num(be.get("phase2_zone_pct"), 20, 70, 40)
    be["lock2_pct"] = _num(be.get("lock2_pct"), 30, 80, 50)
    n = c["news"]
    n["enabled"] = bool(n["enabled"])
    n["pre_min"] = int(_num(n["pre_min"], 0, 240, 5))
    n["post_min"] = int(_num(n["post_min"], 0, 240, 15))
    # profilele per timeframe; config vechi (doar `limits`, fara profile) → devine profilul timeframe-ului lui
    profs = c["tf_profiles"]
    if "limits" in (cfg or {}) and "tf_profiles" not in (cfg or {}):
        profs[c["timeframe"]]["limits"] = _merge(profs[c["timeframe"]]["limits"], cfg["limits"])
    for tf, pr in profs.items():
        for k in ("max_trades_day", "max_losses_day", "max_consec_losses"):
            lim = pr["limits"].get(k) or {}
            pr["limits"][k] = {"enabled": bool(lim.get("enabled", True)), "value": int(_num(lim.get("value"), 1, 1000, 1))}
        pr["min_atr_over_cost"] = _num(pr.get("min_atr_over_cost"), 0, 200, 5 if tf == "M1" else 15)
    act = profs[c["timeframe"]]
    c["limits"] = copy.deepcopy(act["limits"])
    s["min_atr_over_cost"] = act["min_atr_over_cost"]
    b = c["budget"]
    b["capital"] = _num(b["capital"], 1, 1e6, 40.0)
    b["min_remaining"] = _num(b["min_remaining"], 0, b["capital"], min(30.0, b["capital"]))
    c["sizing"]["risk_pct"] = _num(c["sizing"].get("risk_pct"), 0.0005, 0.05, 0.01)
    return c


def pip_points(digits: int | None) -> int:
    """Points intr-un pip: FX cu 3 / 5 zecimale → 10 (USDJPY 0,01 = 10 points); altfel 1 (indici, cripto)."""
    return 10 if digits in (3, 5) else 1


def resolve_spread(cfg: dict, point: float | None, auto_points: float | None = None, digits: int | None = None) -> dict:
    """Rezolva sectiunea `spread` (points) → strategy.spread_floor / spread_max (PRET) — in loc. Intoarce ce se
    afiseaza: valorile in points / pips / pret si SURSA fiecareia (auto MT5 / manual / rezerva)."""
    sp, s = cfg["spread"], cfg["strategy"]
    if not point:
        return {"mode": sp["mode"], "source": "point necunoscut — valorile de rezerva", "typical_price": s["spread_floor"],
                "max_price": s["spread_max"]}
    if sp["mode"] == "manual":
        pts = sp.get("manual_points")
        if pts is None and sp.get("legacy_floor_price") is not None:
            pts = round(sp["legacy_floor_price"] / point, 3)
        src = "manual"
    else:
        pts, src = auto_points, "auto (MT5 live)"
    if pts is None or pts <= 0:
        pts, src = (s["spread_floor"] / point if s["spread_floor"] else None), "rezervă (încă fără tick-uri MT5)"
    typical = (pts or 0.0) * point
    if sp["max_mode"] == "manual":
        max_pts, max_src = sp["max_points"], "manual"
    else:
        max_pts, max_src = sp["max_mult"] * (pts or 0.0), f"auto ({sp['max_mult']:g}× tipic)"
    s["spread_floor"] = typical
    s["spread_max"] = max_pts * point
    pp = pip_points(digits)
    return {"mode": sp["mode"], "max_mode": sp["max_mode"], "source": src, "max_source": max_src, "point": point,
            "digits": digits, "pip_points": pp, "typical_points": round(pts or 0.0, 2), "typical_price": round(typical, 8),
            "typical_pips": round((pts or 0.0) / pp, 3), "max_points": round(max_pts, 2), "max_price": round(max_pts * point, 8),
            "max_pips": round(max_pts / pp, 3)}


def load_config() -> dict:
    try:
        with open(CFG_PATH, encoding="utf-8") as f:
            return sanitize(json.load(f))
    except Exception:
        return sanitize({})


def save_config(cfg: dict) -> dict:
    clean = sanitize(cfg)
    with open(CFG_PATH, "w", encoding="utf-8") as f:
        json.dump(clean, f, indent=2, ensure_ascii=False)
    return clean


def save_default_config() -> None:
    if not os.path.exists(CFG_PATH):
        save_config({})
