"""
profit_lock — Special Take Profit Mode: serviciu COMUN, PUR (nu atinge MT5), folosit identic de backtest si de engine-uri.

Ideea (userului, 2026-11-05): nu inchide trade-ul la TP-ul initial, ci blocheaza profitul in trepte si lasa trendul sa
continue. Exemplu RR 1:2, extensie +0,10R, offset 0,10R, pas 0,50R:
    initial              SL −1R      TP 2,10R
    pretul atinge 2,0R   SL 1,90R    TP 2,60R
    pretul atinge 2,5R   SL 2,40R    TP 3,10R
    pretul atinge 3,0R   SL 2,90R    TP 3,60R   … (pragul L = rr + k × pas; SL = L − offset; TP = L + pas + extensie)

Consecinta matematica (verificata in backtest): pragul urmator (L + pas) e MEREU sub TP (L + pas + extensie), deci un
pret continuu trece intai prin prag si muta TP-ul mai departe → TP-ul nu se atinge decat printr-un GAP. Extensia
(0,10 / 0,15 / 0,20R) conteaza doar la gap-uri; mecanismul real = trailing in trepte de la rr.

Moduri:
  special    — treptele de mai sus
  atr_trail  — alternativa echipei: de la rr, SL = max(rr − offset, varf − atr_mult × ATR) (ATR in R la intrare)
Toate valorile in R sunt fata de riscul INITIAL (|entry − SL initial|). SL-ul e MONOTON (nu coboara niciodata).
Teste: python scripts/test_profit_lock.py
"""
from __future__ import annotations

import math

MODES = ("special", "atr_trail")
DEFAULTS = {"enabled": False, "mode": "special", "tp_extension_R": 0.10, "sl_offset_R": 0.10, "step_R": 0.50,
            "atr_mult": 2.0}
LIMITS = {"tp_extension_R": (0.0, 1.0), "sl_offset_R": (0.0, 1.0), "step_R": (0.1, 3.0), "atr_mult": (0.5, 5.0)}
_EPS = 1e-9


def sanitize(cfg: dict | None) -> dict:
    """Config sigur: lipsa / corupt → DEFAULTS (oprit). Valorile in afara limitelor → clamp."""
    out = dict(DEFAULTS)
    if not isinstance(cfg, dict):
        return out
    out["enabled"] = bool(cfg.get("enabled", False))
    if cfg.get("mode") in MODES:
        out["mode"] = cfg["mode"]
    for k, (lo, hi) in LIMITS.items():
        try:
            v = float(cfg.get(k, DEFAULTS[k]))
            if math.isfinite(v):
                out[k] = min(hi, max(lo, v))
        except (TypeError, ValueError):
            pass
    return out


def initial_tp_R(rr: float, cfg: dict) -> float:
    """TP-ul initial (R): rr + extensie cand modul e activ."""
    c = sanitize(cfg)
    return float(rr) + (c["tp_extension_R"] if c["enabled"] else 0.0)


def stage(rr: float, peak_R: float, cfg: dict) -> int:
    """Treapta atinsa: 0 = inca neactivat (varful < rr), 1 = rr atins, 2 = rr + pas, ..."""
    c = sanitize(cfg)
    if not c["enabled"] or peak_R + _EPS < rr:
        return 0
    return int(math.floor((peak_R - rr) / c["step_R"] + _EPS)) + 1


def levels(rr: float, peak_R: float, cfg: dict, atr_R: float | None = None) -> dict | None:
    """Nivelurile protejate (R) dupa varful favorabil `peak_R`; None = mecanism neactivat (SL / TP initiale raman)."""
    c = sanitize(cfg)
    k = stage(rr, peak_R, c)
    if k == 0:
        return None
    L = rr + (k - 1) * c["step_R"]
    if c["mode"] == "atr_trail":
        sl = rr - c["sl_offset_R"]
        if atr_R and atr_R > 0:
            sl = max(sl, peak_R - c["atr_mult"] * atr_R)
        return {"stage": k, "sl_R": sl, "tp_R": None, "threshold_R": L}
    return {"stage": k, "sl_R": L - c["sl_offset_R"], "tp_R": L + c["step_R"] + c["tp_extension_R"], "threshold_R": L}


def r_to_price(entry: float, side: int, risk: float, R: float) -> float:
    """R → pret: BUY (side 1) deasupra intrarii pentru R > 0, SELL (side −1) dedesubt."""
    return float(entry + side * R * risk)


def price_to_R(entry: float, side: int, risk: float, price: float) -> float:
    return float((price - entry) * side / risk) if risk else 0.0


def round_to_tick(price: float, tick: float, side: int, kind: str) -> float:
    """Rotunjire la tick in directia SIGURA (departe de piata): BUY → SL in jos, TP in sus; SELL → SL in sus, TP in jos.
    Rotunjirea nu muta niciodata SL-ul mai aproape de pret decat nivelul calculat (distanta minima a brokerului)."""
    if not tick or tick <= 0:
        return float(price)
    q = price / tick
    if kind == "sl":
        q = math.floor(q + _EPS) if side == 1 else math.ceil(q - _EPS)
    else:
        q = math.ceil(q - _EPS) if side == 1 else math.floor(q + _EPS)
    return round(q * tick, 10)


def improves(side: int, current_sl: float | None, new_sl: float) -> bool:
    """SL-ul nou e STRICT mai protector (monoton): BUY → mai sus, SELL → mai jos."""
    if current_sl is None or current_sl == 0:
        return True
    return new_sl > current_sl + _EPS if side == 1 else new_sl < current_sl - _EPS


def broker_check(side: int, new_sl: float, bid: float, ask: float, point: float,
                 stops_level: int = 0, freeze_level: int = 0) -> tuple[bool, str]:
    """Modificarea SL e acceptabila de broker? SL-ul unui BUY trebuie sa fie sub BID cu cel putin stops_level points;
    al unui SELL peste ASK. freeze_level: pretul prea aproape de SL-ul curent → MT5 refuza orice modificare."""
    gap = max(int(stops_level or 0), int(freeze_level or 0)) * float(point or 0)
    if side == 1:
        if new_sl >= bid - gap - _EPS:
            return False, f"SL {new_sl:g} prea aproape de BID {bid:g} (min {gap:g})"
    else:
        if new_sl <= ask + gap + _EPS:
            return False, f"SL {new_sl:g} prea aproape de ASK {ask:g} (min {gap:g})"
    return True, ""


def plan_modification(*, side: int, entry: float, risk: float, rr: float, peak_price: float, current_sl: float,
                      current_tp: float | None, cfg: dict, bid: float, ask: float, point: float, tick: float,
                      stops_level: int = 0, freeze_level: int = 0, atr_R: float | None = None) -> dict:
    """Decizia pentru o pozitie LIVE: ce SL / TP trebuie trimise (sau nimic). Pura; apelantul trimite TRADE_ACTION_SLTP
    doar daca `action == "modify"`; `action == "close"` = nivelul blocat a fost deja depasit inapoi (inchidere la
    piata). Niciodata un SL mai putin protector decat cel curent (restart / eroare → nimic)."""
    c = sanitize(cfg)
    if not c["enabled"] or not risk or risk <= 0:
        return {"action": "none", "reason": "oprit"}
    peak_R = price_to_R(entry, side, risk, peak_price)
    lv = levels(rr, peak_R, c, atr_R)
    if lv is None:
        return {"action": "none", "reason": f"neactivat (vârf {peak_R:.2f}R < {rr:g}R)", "peak_R": peak_R}
    new_sl = round_to_tick(r_to_price(entry, side, risk, lv["sl_R"]), tick, side, "sl")
    if not improves(side, current_sl, new_sl):
        return {"action": "none", "reason": "SL deja la nivel / mai protector", "stage": lv["stage"], "peak_R": peak_R}
    # pretul a trecut deja inapoi de nivelul blocat (intre doua verificari) → stop-ul ar fi fost lovit: inchide la piata
    if (side == 1 and bid <= new_sl) or (side == -1 and ask >= new_sl):
        return {"action": "close", "reason": f"prețul a revenit sub nivelul blocat {lv['sl_R']:.2f}R",
                "stage": lv["stage"], "sl_R": lv["sl_R"], "peak_R": peak_R}
    ok, why = broker_check(side, new_sl, bid, ask, point, stops_level, freeze_level)
    if not ok:
        return {"action": "none", "reason": f"amânat: {why}", "stage": lv["stage"], "peak_R": peak_R}
    new_tp = None
    if lv["tp_R"] is not None:
        new_tp = round_to_tick(r_to_price(entry, side, risk, lv["tp_R"]), tick, side, "tp")
        if current_tp and ((side == 1 and new_tp < current_tp) or (side == -1 and new_tp > current_tp)):
            new_tp = current_tp                     # TP-ul nu se apropie niciodata de pret
    elif current_tp:
        new_tp = None                               # atr_trail: fara TP fix dupa activare (trailing pur)
    return {"action": "modify", "sl": new_sl, "tp": new_tp, "stage": lv["stage"], "sl_R": lv["sl_R"],
            "tp_R": lv["tp_R"], "peak_R": peak_R}


# ── simulare pe bare (backtest) — aceleasi niveluri ca in live ─────────────────────────────────────────────────

def simulate_path(o, h, l, c, *, side: int, entry: float, risk: float, sl_R: float, tp_R: float | None, rr: float,
                  cfg: dict | None, start: int, end: int, atr_R: float | None = None, be: dict | None = None,
                  update_mask=None) -> dict:
    """Pozitia de la bara `start` pana la `end` (exclusiv; la `end` − 1 se inchide la close = iesire fortata: final de
    zi / vineri / stop de timp). `update_mask[i]` (optional) = treptele se recalculeaza DOAR la barele marcate (ex.
    inchiderea barei M15 cand engine-ul live verifica pe M15), SL-ul curent fiind lovit oricand. Ordinea pe bara (CONSERVATOR): gap la deschidere → SL curent → TP curent → abia apoi
    se actualizeaza treptele din extremul barei (noul SL se aplica de la bara urmatoare). Intoarce R brut (fara costuri),
    motivul, bara de iesire, varful favorabil si treapta maxima. `be` = break-even Custom (engine/simulator), optional."""
    c_ = sanitize(cfg) if cfg else dict(DEFAULTS)
    on = c_["enabled"]
    tp = None if tp_R is None else tp_R + (c_["tp_extension_R"] if on else 0.0)
    sl = sl_R
    peak = 0.0
    st_max = 0
    be_ph = 0
    be_zone = False

    def R(px):
        return (px - entry) * side / risk

    for i in range(start, end):
        ro, rh, rl = R(o[i]), R(h[i] if side == 1 else l[i]), R(l[i] if side == 1 else h[i])
        if ro <= sl:                                  # gap la deschidere peste SL-ul de DINAINTE de bara
            return {"R": ro, "why": "SL_gap", "exit_i": i, "peak_R": peak, "stage": st_max}
        if tp is not None and ro >= tp:
            return {"R": ro, "why": "TP_gap", "exit_i": i, "peak_R": max(peak, ro), "stage": st_max}
        # break-even Custom (o tranzitie / bara, inainte de SL — identic engine/simulator.py)
        if be and be.get("enabled") and tp is not None:
            trig, lock1, zone, lock2 = (tp * be[k] / 100.0 for k in ("trigger_pct", "lock1_pct", "phase2_zone_pct", "lock2_pct"))
            reached, reversed_, in_zone = rh >= trig, rl < trig, lock1 < rl <= zone
            if be_ph == 0 and reached:
                be_ph = 1
            elif be_ph == 1 and reversed_:
                sl, be_ph = max(sl, lock1), 2
            elif be_ph == 2 and be.get("phase2_enabled", True):
                if in_zone:
                    be_zone = True
                if be_zone and reached:
                    be_ph = 3
            elif be_ph == 3 and reversed_ and be.get("phase2_enabled", True):
                sl, be_ph = max(sl, lock2), 4
        if rl <= sl:
            why = "SL" if sl < 0 else ("BE" if st_max == 0 else "LOCK")
            return {"R": sl, "why": why, "exit_i": i, "peak_R": peak, "stage": st_max}
        if tp is not None and rh >= tp and not on:
            return {"R": tp, "why": "TP", "exit_i": i, "peak_R": max(peak, rh), "stage": st_max}
        peak = max(peak, rh)
        if on and (update_mask is None or update_mask[i]):
            lv = levels(rr, peak, c_, atr_R)
            if lv is not None:
                st_max = max(st_max, lv["stage"])
                sl = max(sl, lv["sl_R"])
                tp = lv["tp_R"]                       # None la atr_trail
                if tp is not None and peak >= tp:     # doar teoretic (prag < TP); pastrat pentru siguranta
                    return {"R": tp, "why": "TP", "exit_i": i, "peak_R": peak, "stage": st_max}
            elif tp is not None and rh >= tp:          # TP initial (rr + extensie) atins fara sa treaca de rr: imposibil
                return {"R": tp, "why": "TP", "exit_i": i, "peak_R": peak, "stage": st_max}
    last = end - 1
    return {"R": R(c[last]), "why": "FORCED", "exit_i": last, "peak_R": peak, "stage": st_max}


# ── Configurare: Global → Engine, eligibilitate (decizia din backtest, docs/SPECIAL_TP_RESEARCH.md) ───────────

ELIGIBLE = {
    "custom": "validat în backtest: TP fix 2R; mai bun pe train ȘI test pe GBPUSD + EURUSD (actualizare la bara M15)",
}
NOT_ELIGIBLE = {
    "daily": "exclus: varianta actuală (fără TP, închidere la final de zi) e de 2–5× mai bună decât orice blocare în trepte",
    "noisy": "exclus: stopul de timp (20 bare) face efectul neglijabil, iar sistemul e negativ în backtest",
    "ai": "exclus: netestat — TP-ul îl alege consiliul AI, cu propriile rails",
}


def effective(global_cfg: dict | None, engine_cfg: dict | None, engine: str) -> dict:
    """Configuratia ACTIVA pentru un engine: Global (daca e pornit) castiga; altfel setarea engine-ului; engine-urile
    neeligibile raman mereu oprite (motivul e afisat). Intoarce {cfg, source: global|engine|off|not_eligible, reason}."""
    off = sanitize(None)
    if engine not in ELIGIBLE:
        return {"cfg": off, "source": "not_eligible", "eligible": False, "reason": NOT_ELIGIBLE.get(engine, "neeligibil")}
    g = sanitize(global_cfg)
    if g["enabled"]:
        return {"cfg": g, "source": "global", "eligible": True, "reason": "pornit din Setări Globale (setarea engine-ului e ignorată)"}
    e = sanitize(engine_cfg)
    if e["enabled"]:
        return {"cfg": e, "source": "engine", "eligible": True, "reason": "pornit din setările engine-ului"}
    return {"cfg": off, "source": "off", "eligible": True, "reason": "oprit (nici global, nici pe engine)"}
