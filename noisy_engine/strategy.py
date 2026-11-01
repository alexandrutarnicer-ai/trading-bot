"""Strategia Noisy Engine — FUNCTIE PURA, recalculata de la zero la fiecare iteratie (restart-safe).

`run_day(bars, day, params)` primeste barele M5 INCHISE (cu istoric anterior pentru indicatori) si
reconstruieste ziua: semnale, intrari, iesiri, limite. Aceeasi functie e folosita de engine (shadow)
si de backtest (scripts/research_noisy/noisy_backtest.py) — ce vezi in shadow e exact ce a testat
backtestul. Cu toate filtrele / limitele oprite reproduce strategia MR din research (selftest).

Regula (mean reversion, M5):
  semnal la INCHIDEREA barei i: close < EMA − dev×ATR → LONG ; close > EMA + dev×ATR → SHORT
  intrare la DESCHIDEREA barei i+1 (fara lookahead)
  SL = intrare ∓ sl_atr×ATR_i ; tinta = intrare ± |EMA_i − close_i| (sau ± tp_rr×risc, R:R fix) ; stop de timp: iesire la
  inchiderea barei i+time_stop daca nu s-a atins nimic. SL si tinta in aceeasi bara → SL (prudent).
  O singura pozitie odata; dupa iesire, pauza (cooldown).
  Break-Even OPTIONAL (cfg["break_even"]) = aceeasi regula ca Custom Engine (engine/simulator.py).
Costul: max(spread bara de intrare, spread median, spread_floor) + comision + 2×slip×spread median (unitati de pret).
spread_floor = spread-ul median masurat pe tick-uri (spread-ul barelor MT5 e minimul din bara).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

from noisy_engine.config import hm_to_min

SPREAD_MED_BARS = 288          # 24h de bare M5


def indicators(df: pd.DataFrame, p: dict) -> pd.DataFrame:
    """EMA / ATR / mediana spread-ului / efficiency ratio — identice cu scripts/research_noisy/edge_test.py."""
    o, h, l, c = (df[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc)))
    out = pd.DataFrame(index=df.index)
    out["ema"] = pd.Series(c).ewm(span=p["ema"], adjust=False).mean().to_numpy()
    out["atr"] = pd.Series(tr).rolling(p["atr"]).mean().to_numpy()
    sp = np.maximum(df["spread"].to_numpy(float), p.get("spread_floor", 0.0))
    out["spread_med"] = pd.Series(sp).rolling(SPREAD_MED_BARS, min_periods=12).median().to_numpy()
    n = p["er_bars"]
    path = pd.Series(np.abs(np.diff(c, prepend=c[0]))).rolling(n).sum().to_numpy()
    move = np.abs(c - np.r_[np.full(n, np.nan), c[:-n]]) if len(c) > n else np.full(len(c), np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        out["er"] = np.where(path > 0, move / path, np.nan)
    return out


def _in_window(t: datetime, w: dict) -> bool:
    if t.weekday() not in w["days"]:
        return False
    m = t.hour * 60 + t.minute
    s, e = hm_to_min(w["start"]), hm_to_min(w["end"])
    return s <= m < e if s <= e else (m >= s or m < e)


def _blocked(t: datetime, intervals) -> bool:
    return any(a <= t < b for a, b in intervals or ())


def step_exit(pos: dict, i: int, hi: float, lo: float, cl: float, time_stop_bars: int, be: dict):
    """Iesirea pozitiei pe bara i → (pret, motiv) sau (None, None). Muta SL-ul la break-even (pos e modificat).
    Break-Even IDENTIC cu Custom Engine (engine/simulator.py::simulate_trade): max o tranzitie de faza pe
    bara, apoi SL-ul (eventual mutat) verificat pe aceeasi bara, apoi tinta; plus stopul de timp Noisy."""
    d = pos["dir"]
    if be.get("enabled"):
        b80 = pos["be_lv"]["trig"]
        if d > 0:
            reached, reversed_, in_zone = hi >= b80, lo < b80, pos["be_lv"]["lock1"] < lo <= pos["be_lv"]["zone"]
        else:
            reached, reversed_, in_zone = lo <= b80, hi > b80, pos["be_lv"]["zone"] <= hi < pos["be_lv"]["lock1"]
        ph = pos["be_phase"]
        if ph == 0 and reached:
            pos["be_phase"] = 1
        elif ph == 1 and reversed_:
            pos["sl"], pos["be_phase"] = pos["be_lv"]["lock1"], 2
        elif ph == 2 and be["phase2_enabled"]:
            if in_zone:
                pos["be_in_zone"] = True
            if pos.get("be_in_zone") and reached:
                pos["be_phase"] = 3
        elif ph == 3 and reversed_ and be["phase2_enabled"]:
            pos["sl"], pos["be_phase"] = pos["be_lv"]["lock2"], 4
    if (d > 0 and lo <= pos["sl"]) or (d < 0 and hi >= pos["sl"]):
        ph = pos.get("be_phase", 0)
        return pos["sl"], ("be_lock2" if ph >= 4 else "be_lock" if ph >= 2 else "SL")
    if (d > 0 and hi >= pos["tp"]) or (d < 0 and lo <= pos["tp"]):
        return pos["tp"], "TP"
    if i >= pos["sig_i"] + time_stop_bars:
        return cl, "timp"
    return None, None


def simulate_exit(bars: pd.DataFrame, pos: dict, cfg: dict) -> dict | None:
    """O pozitie data, bara cu bara, pana la iesire (pentru teste: echivalenta cu Custom Engine)."""
    be = cfg.get("break_even") or {"enabled": False}
    h, l, c = (bars[k].to_numpy(float) for k in ("high", "low", "close"))
    for i in range(pos["entry_i"], len(bars)):
        px, why = step_exit(pos, i, h[i], l[i], c[i], cfg["strategy"]["time_stop_bars"], be)
        if px is not None:
            return {"exit": float(px), "reason": why, "bar": i}
    return None


def run_day(bars: pd.DataFrame, day: date, cfg: dict, *, news_blocks=None, vetoed=None,
            no_new_entries: bool = False) -> dict:
    """
    bars: DataFrame cu coloanele t (datetime RO, inceputul barei), open, high, low, close, spread
          (in unitati de pret) — DOAR bare inchise, sortate, cu istoric inainte de `day`.
    news_blocks: [(start, end)] (datetime RO) in care nu se intra (stiri).
    vetoed: set de momente de semnal (t al barei de semnal) respinse de protectiile globale la
            momentul lor — pastrate de engine ca recalcularea sa ramana identica.
    no_new_entries: blocare externa (buget epuizat / pauza) — fara intrari noi.
    Intoarce: trades (inchise azi), open (pozitia virtuala deschisa), pending (semnal care asteapta
    bara urmatoare), counters, lock (motivul blocarii zilei) si ultimele valori ale indicatorilor.
    """
    p, lim, w = cfg["strategy"], cfg["limits"], cfg["window"]
    be = cfg.get("break_even") or {"enabled": False}
    res = {"trades": [], "open": None, "pending": None, "lock": None, "last": None,
           "counters": {"trades": 0, "losses": 0, "consec_losses": 0, "flips_hour": 0}}
    if bars is None or len(bars) < max(p["atr"], p["ema"]) + 2:
        return res
    df = bars.reset_index(drop=True)
    ind = indicators(df, p)
    t = df["t"].tolist()
    o, h, l, c = (df[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    # spread-ul barei MT5 e MINIMUL din bara (0 pe ~88% din barele USDJPY) → prag = spread-ul median
    # masurat pe tick-uri (config spread_floor), altfel costul ar fi subestimat
    sp = np.maximum(df["spread"].to_numpy(float), p.get("spread_floor", 0.0))
    ema, atr, spm, er = (ind[k].to_numpy() for k in ("ema", "atr", "spread_med", "er"))
    idx = [i for i in range(len(df)) if t[i].date() == day]
    if not idx:
        return res
    vetoed = vetoed or set()
    pos = None
    next_ok = idx[0]
    losses = consec = 0
    flips: list[datetime] = []
    last_dir = 0

    def cost_at(i_entry: int, i_sig: int) -> float:
        med = spm[i_sig] if np.isfinite(spm[i_sig]) else sp[i_sig]
        return max(sp[i_entry], med) + p["comm_price"] + 2 * p["slip_frac"] * med

    for i in idx:
        res["last"] = {"t": t[i].isoformat(), "close": c[i], "ema": float(ema[i]), "atr": float(atr[i]) if np.isfinite(atr[i]) else None,
                       "dev_atr": float((c[i] - ema[i]) / atr[i]) if np.isfinite(atr[i]) and atr[i] > 0 else None,
                       "spread": float(sp[i]), "spread_med": float(spm[i]) if np.isfinite(spm[i]) else None,
                       "er": float(er[i]) if np.isfinite(er[i]) else None}
        # 1) pozitia deschisa: iesire pe bara i
        if pos is not None and i >= pos["entry_i"]:
            d = pos["dir"]
            exit_p, reason = step_exit(pos, i, h[i], l[i], c[i], p["time_stop_bars"], be)
            if exit_p is not None:
                gross = d * (exit_p - pos["entry"])
                net = gross - pos["cost"]
                tr_ = {"id": pos["id"], "dir": "LONG" if d > 0 else "SHORT", "signal_t": pos["signal_t"],
                       "entry_t": pos["entry_t"], "exit_t": t[i].isoformat(), "entry": pos["entry"], "exit": float(exit_p),
                       "sl": pos["sl0"], "sl_final": pos["sl"], "tp": pos["tp"], "risk": pos["risk"], "cost": pos["cost"], "reason": reason,
                       "gross_R": gross / pos["risk"], "R": net / pos["risk"], "bars": i - pos["entry_i"] + 1,
                       "be_phase": pos.get("be_phase", 0)}
                res["trades"].append(tr_)
                res["counters"]["trades"] += 1
                if tr_["R"] < 0:
                    losses += 1
                    consec += 1
                else:
                    consec = 0
                next_ok = i + 1 + (p["cooldown_after_sl_bars"] if reason == "SL" else p["cooldown_bars"])
                pos = None
            continue                                  # nicio intrare noua pe bara unei iesiri
        if pos is not None:
            continue
        # 2) limitele zilei
        if lim["max_trades_day"]["enabled"] and res["counters"]["trades"] >= lim["max_trades_day"]["value"]:
            res["lock"] = res["lock"] or "trade_limit"
            continue
        if lim["max_losses_day"]["enabled"] and losses >= lim["max_losses_day"]["value"]:
            res["lock"] = res["lock"] or "loss_limit"
            continue
        if lim["max_consec_losses"]["enabled"] and consec >= lim["max_consec_losses"]["value"]:
            res["lock"] = res["lock"] or "loss_streak"
            continue
        if i < next_ok or no_new_entries:
            continue
        # 3) filtre obligatorii
        if not (np.isfinite(atr[i]) and atr[i] > 0) or not _in_window(t[i], w):
            continue
        if _blocked(t[i], news_blocks):
            continue
        med = spm[i] if np.isfinite(spm[i]) else sp[i]
        if p["spread_max_mult"] > 0 and med > 0 and sp[i] > p["spread_max_mult"] * med:
            continue
        cost_est = med + p["comm_price"] + 2 * p["slip_frac"] * med
        if p["min_atr_over_cost"] > 0 and cost_est > 0 and atr[i] < p["min_atr_over_cost"] * cost_est:
            continue
        # 4) semnal
        d = 1 if c[i] < ema[i] - p["dev_atr"] * atr[i] else (-1 if c[i] > ema[i] + p["dev_atr"] * atr[i] else 0)
        if d == 0:
            continue
        if p["trend_filter"] and np.isfinite(er[i]) and er[i] >= p["er_trend"]:
            continue
        if p["max_flips_per_hour"] > 0:
            recent = [x for x in flips if x > t[i] - timedelta(hours=1)]
            if last_dir and d != last_dir and len(recent) >= p["max_flips_per_hour"]:
                continue
        if t[i].isoformat() in vetoed:
            continue
        if last_dir and d != last_dir:
            flips.append(t[i])
        last_dir = d
        if i + 1 >= len(df):                          # intrarea vine la deschiderea barei urmatoare
            res["pending"] = {"dir": "LONG" if d > 0 else "SHORT", "signal_t": t[i].isoformat(),
                              "close": c[i], "ema": float(ema[i]), "atr": float(atr[i])}
            continue
        e = o[i + 1]
        risk = p["sl_atr"] * atr[i]
        tp_dist = p["tp_rr"] * risk if p.get("tp_rr", 0) > 0 else abs(ema[i] - c[i]) + 1e-12
        pos = {"id": f"{t[i]:%Y%m%d-%H%M}", "dir": d, "sig_i": i, "entry_i": i + 1, "signal_t": t[i].isoformat(),
               "entry_t": t[i + 1].isoformat(), "entry": float(e), "sl": float(e - d * risk), "sl0": float(e - d * risk),
               "tp": float(e + d * tp_dist), "risk": float(risk), "cost": float(cost_at(i + 1, i))}
        if be["enabled"]:
            # nivelurile break-even = procente din distanta intrare → tinta (ca in Custom Engine)
            pos["be_lv"] = {k: float(e + d * tp_dist * be[f] / 100.0) for k, f in
                            (("trig", "trigger_pct"), ("lock1", "lock1_pct"), ("zone", "phase2_zone_pct"), ("lock2", "lock2_pct"))}
            pos["be_phase"] = 0
    res["counters"].update(losses=losses, consec_losses=consec,
                           flips_hour=len([x for x in flips if t[-1] - timedelta(hours=1) < x]))
    if pos is not None:
        d = pos["dir"]
        res["open"] = {**{k: v for k, v in pos.items() if k not in ("sig_i", "entry_i", "sl0", "be_lv")},
                       "sl": pos["sl0"], "sl_now": pos["sl"], "be_phase": pos.get("be_phase", 0),
                       "dir": "LONG" if d > 0 else "SHORT", "last": float(c[-1]),
                       "float_R": (d * (c[-1] - pos["entry"]) - pos["cost"]) / pos["risk"],
                       "bars_held": len(df) - pos["entry_i"]}
    return res
