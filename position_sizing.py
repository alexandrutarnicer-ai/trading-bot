"""
Position Sizing COMUN — o singura implementare pentru Custom Engine, AI Engine si Daily Engine.

Lantul (identic pe toate engine-urile):

    capital de baza   = equity MT5 (sync, implicit)  |  capital fix alocat, plafonat la equity
    capital alocat    = capital de baza × fractie (0..1)
    risc tinta (bani) = capital alocat × risc% per trade
    lot brut          = risc tinta / (distanta SL × valoarea unei unitati de pret pe 1 lot)
    lot final         = lot brut aliniat la broker: floor la volume_step (cu epsilon),
                        minim volume_min, maxim volume_max
    risc real (bani)  = lot final × distanta SL × valoarea unei unitati de pret pe 1 lot

Valoarea unei unitati de pret pe 1 lot = trade_tick_value / trade_tick_size din MT5 — deja in
MONEDA CONTULUI (MT5 face conversia), deci formula e corecta pentru orice simbol / cont.

Functiile sunt PURE: primesc obiectul `symbol_info` (sau orice obiect cu aceleasi campuri),
nu ating MT5. Testate de scripts/test_position_sizing.py.

Inainte (2026-10-31) logica era copiata in live/signal_generator.py si ai_engine/executor.py cu
diferente: rotunjire fara epsilon (0.5 putea deveni 0.49), fara plafon volume_max in modul
dinamic, iar botul calcula pe un capital fix de $1000 cand equity-ul MT5 nu se putea citi.
"""
from __future__ import annotations

import math

EPS = 1e-9


def _step(info) -> float:
    s = float(getattr(info, "volume_step", 0) or 0)
    return s if s > 0 else 0.01


def _decimals(step: float) -> int:
    """Zecimalele pasului de volum (0.01 -> 2, 0.1 -> 1, 1 -> 0, 100 -> 0)."""
    if step >= 1:
        return 0
    return max(0, min(8, round(-math.log10(step)))) if step > 0 else 2


def snap_volume(info, lots: float) -> float:
    """Aliniaza un volum la broker: floor la volume_step (epsilon anti-float), clamp la
    [volume_min, volume_max]. Nu creste niciodata expunerea peste cerere, cu exceptia lotului
    minim (sub el ordinul nu exista)."""
    step = _step(info)
    vmin = float(getattr(info, "volume_min", 0) or 0)
    vmax = float(getattr(info, "volume_max", 0) or 0)
    snapped = math.floor(float(lots) / step + EPS) * step
    snapped = max(vmin, snapped)
    if vmax > 0:
        snapped = min(snapped, vmax)
    return round(snapped, _decimals(step))


def value_per_price_unit(info) -> float | None:
    """Bani (moneda contului) per 1.0 unitate de pret per 1 lot. None daca MT5 nu da tick-ul."""
    ts = float(getattr(info, "trade_tick_size", 0) or 0)
    tv = float(getattr(info, "trade_tick_value", 0) or 0)
    if ts <= 0 or tv <= 0:
        return None
    return tv / ts


def capital_base(sync: bool, capital_fixed: float | None, equity: float | None) -> float:
    """sync=True: equity-ul real MT5 (0 daca indisponibil). sync=False: capitalul fix alocat,
    PLAFONAT la equity cand equity e disponibil (protectie la typo)."""
    eq = float(equity) if equity else 0.0
    if sync:
        return eq
    try:
        cap = float(capital_fixed or 0.0)
    except (TypeError, ValueError):
        cap = 0.0
    return min(cap, eq) if eq > 0 else cap


def clamp_fraction(fraction) -> float:
    """Fractia din capital alocata: 0..1 (valori invalide -> 0 = fara alocare)."""
    try:
        f = float(fraction)
    except (TypeError, ValueError):
        return 0.0
    if math.isnan(f) or f <= 0:
        return 0.0
    return min(1.0, f)


def size_by_risk(info, entry: float, sl: float, capital: float, risk_pct: float) -> dict:
    """Lot pentru un risc tinta. Intoarce detaliile complete ale calculului (pentru UI / log).
    lots == 0 -> NU se plaseaza (motivul in `reason`)."""
    out = {"lots": 0.0, "risk_money": None, "target_money": None, "raw_lots": None,
           "at_min_lot": False, "capped_max": False, "ratio": None, "reason": None}
    if info is None:
        out["reason"] = "specificatiile simbolului indisponibile (MT5)"
        return out
    vpu = value_per_price_unit(info)
    dist = abs(float(entry) - float(sl))
    if vpu is None:
        out["reason"] = "tick_size / tick_value indisponibile (MT5)"
        return out
    if dist <= 0:
        out["reason"] = "distanta SL zero"
        return out
    target = float(capital or 0.0) * float(risk_pct or 0.0)
    out["target_money"] = round(target, 4)
    if target <= 0:
        out["reason"] = "capital alocat 0 (equity MT5 indisponibil sau fractie 0)"
        return out
    raw = target / (dist * vpu)
    lots = snap_volume(info, raw)
    vmin = float(getattr(info, "volume_min", 0) or 0)
    vmax = float(getattr(info, "volume_max", 0) or 0)
    risk = lots * dist * vpu
    out.update(lots=lots, raw_lots=round(raw, 6), risk_money=round(risk, 4),
               at_min_lot=raw < vmin - EPS, capped_max=vmax > 0 and raw > vmax + EPS,
               ratio=round(risk / target, 3) if target > 0 else None)
    return out


def size_fixed(info, fixed_lots: float, entry: float, sl: float) -> dict:
    """Volum FIX aliniat la broker + riscul lui la SL."""
    out = {"lots": 0.0, "risk_money": None, "reason": None}
    if info is None:
        out["reason"] = "specificatiile simbolului indisponibile (MT5)"
        return out
    lots = snap_volume(info, fixed_lots)
    vpu = value_per_price_unit(info)
    dist = abs(float(entry) - float(sl))
    out["lots"] = lots
    if vpu is not None and dist > 0:
        out["risk_money"] = round(lots * dist * vpu, 4)
    return out


def fit_to_margin(info, lots: float, margin_need: float | None, free_margin: float | None,
                  cap_fraction: float) -> tuple[float, bool]:
    """Reduce volumul ca marja sa incapa sub cap_fraction × marja libera (marja ~liniara in
    volum). Intoarce (lots, redus?). Fara date de marja -> nemodificat (brokerul decide)."""
    if not margin_need or margin_need <= 0 or free_margin is None or lots <= 0:
        return lots, False
    cap = float(free_margin) * cap_fraction
    if cap <= 0 or margin_need <= cap:
        return lots, False
    per_lot = margin_need / lots
    fitted = snap_volume(info, cap / per_lot)
    return (fitted, True) if fitted < lots else (lots, False)


def apply_risk_cap(info, lots: float, entry: float, sl: float, equity: float | None,
                   max_risk_pct: float | None) -> tuple[float, str | None]:
    """Limita de risc pe trade (Setari Globale → risk_cap), ACEEASI pe toate engine-urile:
    daca riscul real al volumului depaseste max_risk_pct % din equity, volumul e redus pana
    incape; daca nici lotul minim nu incape → 0 (ordinul NU se plaseaza). Intoarce (lots, motiv).
    Fara limita / fara equity / fara date de tick → nemodificat (limita nu poate fi evaluata)."""
    if not max_risk_pct or max_risk_pct <= 0 or not equity or equity <= 0 or not lots or lots <= 0:
        return lots, None
    vpu = value_per_price_unit(info)
    dist = abs(float(entry) - float(sl))
    if vpu is None or dist <= 0:
        return lots, None
    cap_money = float(equity) * float(max_risk_pct) / 100.0
    risk = lots * dist * vpu
    if risk <= cap_money + EPS:
        return lots, None
    step = _step(info)
    fit = math.floor(cap_money / (dist * vpu) / step + EPS) * step
    vmin = float(getattr(info, "volume_min", 0) or 0)
    if fit < vmin - EPS:
        return 0.0, (f"risc {risk:.2f} = {100 * risk / equity:.2f}% din equity > limita {max_risk_pct:g}% "
                     f"(chiar si la lotul minim {vmin:g})")
    fit = round(fit, _decimals(step))
    return fit, f"volum redus {lots:g} → {fit:g} (riscul depasea {max_risk_pct:g}% din equity)"
