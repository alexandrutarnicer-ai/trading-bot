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


def evaluate_day(o, h, l, c, spr, mins, *, open_min: int, or_minutes: int, mode: str,
                 rr: float | None, slip: float, comm: float, day_complete: bool) -> dict:
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

    res, reason, j_exit = None, None, None
    for j in range(i0, n):
        hit_sl = (l[j] <= sl) if side == 1 else (h[j] >= sl)
        if mode == "brk" and j == i0:
            if hit_sl:                       # bara de intrare: doar SL (conservator)
                res, reason, j_exit = -1.0 - (slip + spr[j] / 2) / risk, "SL", j
                break
            continue
        hit_tp = tp is not None and ((h[j] >= tp) if side == 1 else (l[j] <= tp))
        if hit_sl:
            res, reason, j_exit = -1.0 - (slip + spr[j] / 2) / risk, "SL", j
            break
        if hit_tp:
            res, reason, j_exit = rr - (spr[j] / 2) / risk, "TP", j
            break

    if res is None:
        if not day_complete:
            return {**pos, "phase": "in_position", "last": float(c[-1]),
                    "open_R": float(side * (c[-1] - entry) / risk)}
        res, reason, j_exit = float((side * (c[-1] - entry) - spr[-1] / 2) / risk), "EOD", n - 1

    if day_complete and n < n_or + 6:                 # oglinda filtrului din backtest
        return {**base, "phase": "skipped", "reason": "zi incompleta (prea putine bare)"}

    res -= comm / risk
    if reason == "SL":
        exit_px = float(sl - side * slip)
    elif reason == "TP":
        exit_px = float(tp)
    else:
        exit_px = float(c[j_exit])
    return {**pos, "phase": "closed", "R": float(res), "reason": reason,
            "exit": exit_px, "exit_min": int(mins[j_exit])}
