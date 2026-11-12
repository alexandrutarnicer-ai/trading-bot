"""Daily Engine — logica ORB (Opening Range Breakout), PURA si deterministica.

`evaluate_day` primeste barele M5 INCHISE ale zilei curente din fereastra pietei (ora locala a
bursei) si intoarce starea zilei. Se recalculeaza de la zero la fiecare iteratie a motorului ->
restart-safe, fara stare ascunsa. Logica e IDENTICA cu backtestul de cercetare
(`scripts/research_daily/orb_m5.py::run`) — verificat de `daily_engine.selftest`.

Reguli:
  - OR (opening range) = primele `or_minutes` minute dupa deschidere
  - entry "dir": directia OR-ului (close ultima bara OR vs open prima bara), intrare la open-ul
    barei urmatoare; "brk": ordine stop pe ambele margini, primul nivel atins (gap -> open-ul barei)
  - SL = marginea opusa a OR-ului; TP = rr*R (None = fara TP, tinut pana la ultima bara)
  - cost: jumatate de spread la intrare + la iesire, slippage pe ordinele stop, comision
  - zi sarita: fara bara exact la deschidere, OR plat, lumanare OR doji (dir), ambele margini
    in aceeasi bara (brk), fara breakout pana la final (brk), risc < 2x cost, zi incompleta
"""
from __future__ import annotations

import numpy as np

PHASES = ("waiting_open", "forming_or", "waiting_entry", "in_position", "closed", "skipped")


# ── Profit Lock (OPTIONAL, oprit implicit) ─────────────────────────────────────────────────────────────────────
PLOCK_MIN_TRIGGER = 3.0


def plock_cfg(p) -> dict | None:
    """{enabled, trigger_R, lock_R} valid sau None (oprit / invalid). trigger >= 3R, 0 <= lock < trigger."""
    if not isinstance(p, dict) or not p.get("enabled"):
        return None
    try:
        tr, lk = float(p.get("trigger_R")), float(p.get("lock_R"))
    except (TypeError, ValueError):
        return None
    if not (tr >= PLOCK_MIN_TRIGGER and 0 <= lk < tr):
        return None
    return {"trigger_R": tr, "lock_R": lk}


def _walk(o, h, l, c, spr, *, i0, n, side, entry, sl, tp, rr, risk, slip, skip_entry_bar, plock):
    """Iesirea unui trade de la bara i0: SL / TP / (Profit Lock) / None = inca deschis.
    Fara Profit Lock = EXACT bucla initiala. Cu Profit Lock: dupa ce varful atinge trigger_R, SL-ul trece la
    lock_R de la bara URMATOARE (ordinea reala din bara nu se cunoaste → conservator); o bara care deschide
    dincolo de SL-ul blocat se umple la open. Pe bara de intrare a unui breakout varful NU conteaza."""
    pl = plock_cfg(plock)
    cur_sl, locked = sl, False
    for j in range(i0, n):
        hit_sl = (l[j] <= cur_sl) if side == 1 else (h[j] >= cur_sl)
        if skip_entry_bar and j == i0:
            if hit_sl:
                return -1.0 - (slip + spr[j] / 2) / risk, "SL", j, float(sl - side * slip), locked
            continue
        hit_tp = tp is not None and ((h[j] >= tp) if side == 1 else (l[j] <= tp))
        if hit_sl:
            if locked:
                px = min(o[j], cur_sl) if side == 1 else max(o[j], cur_sl)
                px = float(px - side * slip)
                return float(side * (px - entry) / risk - (spr[j] / 2) / risk), "LOCK", j, px, locked
            return -1.0 - (slip + spr[j] / 2) / risk, "SL", j, float(sl - side * slip), locked
        if hit_tp:
            return rr - (spr[j] / 2) / risk, "TP", j, float(tp), locked
        if pl and not locked:
            peak = ((h[j] - entry) if side == 1 else (entry - l[j])) / risk
            if peak >= pl["trigger_R"] - 1e-12:
                locked, cur_sl = True, entry + side * pl["lock_R"] * risk
    return None, None, None, None, (locked, cur_sl)


def evaluate_day(o, h, l, c, spr, mins, *, open_min: int, or_minutes: int, mode: str,
                 rr: float | None, slip: float, comm: float, day_complete: bool, plock: dict | None = None) -> dict:
    """o/h/l/c/spr/mins: secvente (spread deja in unitati de pret, mins = minute locale de la
    miezul noptii pentru inceputul barei). Intoarce dict cu `phase` + detalii."""
    o, h, l, c, spr, mins = (np.asarray(x, dtype=float) for x in (o, h, l, c, spr, mins))
    n_or = max(1, or_minutes // 5)
    n = len(o)
    if n == 0:
        return {"phase": "waiting_open"}
    if int(mins[0]) != open_min:
        return {"phase": "skipped", "reason": "fara bara la ora de deschidere"}
    if n < n_or:
        return {"phase": "forming_or", "bars": n, "bars_needed": n_or}

    hi, lo = float(h[:n_or].max()), float(l[:n_or].min())
    base = {"or_hi": hi, "or_lo": lo}
    if hi - lo <= 0:
        return {**base, "phase": "skipped", "reason": "interval de deschidere plat"}

    if mode == "dir":
        if c[n_or - 1] == o[0]:
            return {**base, "phase": "skipped", "reason": "interval fara directie (doji)"}
        if n < n_or + 1:
            return {**base, "phase": "waiting_entry"}
        side = 1 if c[n_or - 1] > o[0] else -1
        i0 = n_or
        entry = float(o[i0] + side * spr[i0] / 2)
        sl = lo if side == 1 else hi
    elif mode == "brk":
        side = None
        for i in range(n_or, n):
            up, dn = h[i] >= hi, l[i] <= lo
            if up and dn:
                return {**base, "phase": "skipped", "reason": "ambele margini atinse in aceeasi bara"}
            if up or dn:
                side = 1 if up else -1
                lvl = hi if up else lo
                fill = max(lvl, o[i]) if up else min(lvl, o[i])      # gap peste nivel -> open
                entry = float(fill + side * (slip + spr[i] / 2))
                sl, i0 = (lo if up else hi), i
                break
        if side is None:
            if day_complete:
                return {**base, "phase": "skipped", "reason": "fara breakout pana la inchidere"}
            return {**base, "phase": "waiting_entry"}
    else:
        raise ValueError(f"mod de intrare necunoscut: {mode}")

    risk = abs(entry - sl)
    cost_rt = float(spr[i0] + slip + comm)
    if risk <= 0 or risk < 2 * cost_rt:
        return {**base, "phase": "skipped", "side": side,
                "reason": f"risc {risk:.5g} < 2x cost {cost_rt:.5g}"}
    tp = entry + side * rr * risk if rr else None
    pos = {**base, "side": side, "entry": entry, "sl": float(sl), "tp": tp, "risk": risk,
           "entry_bar": int(i0), "entry_min": int(mins[i0])}

    res, reason, j_exit, exit_px, lk = _walk(o, h, l, c, spr, i0=i0, n=n, side=side, entry=entry, sl=sl, tp=tp,
                                             rr=rr, risk=risk, slip=slip, skip_entry_bar=(mode == "brk"),
                                             plock=plock)
    if res is None:
        locked, cur_sl = lk
        if not day_complete:
            return {**pos, "phase": "in_position", "last": float(c[-1]),
                    "open_R": float(side * (c[-1] - entry) / risk),
                    "sl_now": float(cur_sl), "locked": locked}
        res, reason, j_exit = float((side * (c[-1] - entry) - spr[-1] / 2) / risk), "EOD", n - 1
        exit_px = float(c[j_exit])

    if day_complete and n < n_or + 6:                 # oglinda filtrului din backtest
        return {**base, "phase": "skipped", "reason": "zi incompleta (prea putine bare)"}

    res -= comm / risk
    return {**pos, "phase": "closed", "R": float(res), "reason": reason,
            "exit": exit_px, "exit_min": int(mins[j_exit])}


# ── Re-intrari in fereastra „fierbinte” (OPTIONAL, oprit implicit) ──────────────────────────────────────────
REENTRY_DEFAULTS = {"enabled": False, "window_min": 60, "max_trades": 3, "max_consec_losses": 2, "cooldown_bars": 1}


def evaluate_day_multi(o, h, l, c, spr, mins, *, open_min: int, or_minutes: int, mode: str, rr: float | None,
                       slip: float, comm: float, day_complete: bool, reentry: dict | None = None,
                       plock: dict | None = None) -> dict:
    """Ziua cu RE-INTRARI optionale, peste `evaluate_day` (neatinsa — echivalenta cu backtestul ramane).

    reentry = {enabled, window_min, max_trades, max_consec_losses, cooldown_bars}. Oprit (implicit) → EXACT
    rezultatul lui evaluate_day (+ lista `trades`). Pornit: dupa ce trade-ul curent se INCHIDE (SL / TP), de la
    `cooldown_bars` lumanari dupa iesire se cauta o noua rupere a ACELUIASI interval de deschidere (oricare margine;
    pret deja dincolo de margine → intrare la open-ul barei, ca la ordinele stop). Intrarea e permisa doar daca bara
    ei incepe in primele `window_min` minute de la deschidere; o singura pozitie odata; maxim `max_trades` / zi;
    stop dupa `max_consec_losses` pierderi LA RAND (0 = fara). Aceeasi regula ca cercetarea
    scripts/research_daily/orb_reentry.py (verificat in selftest pe tot istoricul).
    Intoarce: campurile trade-ului CURENT (sau ultimului) + trades (inchise), k (index trade curent), phase,
    reentry_stop (motivul pentru care nu mai urmeaza alte intrari)."""
    first = evaluate_day(o, h, l, c, spr, mins, open_min=open_min, or_minutes=or_minutes, mode=mode, rr=rr,
                         slip=slip, comm=comm, day_complete=day_complete, plock=plock)
    re = {**REENTRY_DEFAULTS, **(reentry or {})}
    if not re["enabled"] or first["phase"] != "closed":
        return {**first, "k": 0, "trades": [{**first, "k": 0}] if first["phase"] == "closed" else []}
    o, h, l, c, spr, mins = (np.asarray(x, dtype=float) for x in (o, h, l, c, spr, mins))
    n = len(o)
    hi, lo = first["or_hi"], first["or_lo"]
    trades = [{**first, "k": 0}]
    consec = 1 if first["R"] < 0 else 0
    j_exit = int(np.nonzero(mins == first["exit_min"])[0][-1])
    w_end = open_min + int(re["window_min"])
    last = trades[-1]

    def done(why: str, phase: str = "closed") -> dict:
        return {**last, "phase": phase, "k": len(trades) - 1, "trades": trades, "reentry_stop": why}

    while True:
        if last.get("reason") == "EOD":
            return done("pozitia a ramas pana la final de fereastra")
        if len(trades) >= int(re["max_trades"]):
            return done(f"maxim {re['max_trades']} trade-uri / zi")
        if re["max_consec_losses"] and consec >= int(re["max_consec_losses"]):
            return done(f"{consec} pierderi la rand")
        side = None
        for i in range(j_exit + max(1, int(re["cooldown_bars"])), n):
            if mins[i] >= w_end:
                return done(f"fereastra de re-intrare ({re['window_min']} min) s-a terminat")
            up, dn = h[i] >= hi, l[i] <= lo
            if up and dn:
                return done("ambele margini atinse in aceeasi bara")
            if up or dn:
                side = 1 if up else -1
                lvl = hi if up else lo
                fill = max(lvl, o[i]) if up else min(lvl, o[i])
                entry = float(fill + side * (slip + spr[i] / 2))
                sl, i0 = (lo if up else hi), i
                break
        if side is None:
            if day_complete or (n and mins[n - 1] + 5 >= w_end):
                return done("fara o noua rupere in fereastra")
            return {**last, "phase": "waiting_entry", "k": len(trades), "trades": trades, "reentry_wait": True}
        risk = abs(entry - sl)
        cost_rt = float(spr[i0] + slip + comm)
        if risk <= 0 or risk < 2 * cost_rt:
            return done(f"re-intrare: risc {risk:.5g} < 2x cost {cost_rt:.5g}")
        tp = entry + side * rr * risk if rr else None
        pos = {"or_hi": hi, "or_lo": lo, "side": side, "entry": entry, "sl": float(sl), "tp": tp, "risk": risk,
               "entry_bar": int(i0), "entry_min": int(mins[i0]), "k": len(trades)}
        res, reason, j, exit_px, lk = _walk(o, h, l, c, spr, i0=i0, n=n, side=side, entry=entry, sl=sl, tp=tp,
                                            rr=rr, risk=risk, slip=slip, skip_entry_bar=True, plock=plock)
        if res is None:
            locked, cur_sl = lk
            if not day_complete:
                return {**pos, "phase": "in_position", "trades": trades, "last": float(c[-1]),
                        "open_R": float(side * (c[-1] - entry) / risk), "sl_now": float(cur_sl), "locked": locked}
            j = n - 1
            res, reason = float((side * (c[-1] - entry) - spr[-1] / 2) / risk), "EOD"
            exit_px = float(c[j])
        res -= comm / risk
        last = {**pos, "phase": "closed", "R": float(res), "reason": reason, "exit": exit_px, "exit_min": int(mins[j])}
        trades.append(last)
        consec = consec + 1 if res < 0 else 0
        j_exit = j
