"""
Special Take Profit Mode — backtest comparativ pe engine-urile existente (2026-11-05). DOAR backtest.

Intrari = EXACT engine-ul respectiv; se schimba DOAR gestionarea iesirii (profit_lock.simulate_path, aceeasi functie
ca in live):
  Custom : profilul standard ca acum (S15 GBPUSD, S1 EURUSD — M15+M30, break-even-ul configurat, TP 2R), semnale din
           engine.portfolio.run_portfolio; iesiri pe M1 (minut cu minut), vineri 20:00 inchis; filtrul AI nu se simuleaza
  Daily  : config curent (GBPUSD Londra 5 min breakout, DE40 Frankfurt 5 min breakout), fara TP = actual; M5, final de zi
  Noisy  : config curent (US500 M1, TP 2R, stop de timp 20 bare), ultimul an din MT5
Costuri: Custom = spread live + 25% slippage + swap pe nopti; Daily = spread bara / 2 + slip + markup (ca engine-ul);
Noisy = costul calculat de engine. Aceleasi costuri pentru toate variantele aceluiasi trade.
Ordinea pe bara = conservatoare (gap → SL → TP → abia apoi treptele, aplicate de la bara urmatoare).
Selectia variantei: pe TRAIN (primele 70% din trade-urile fiecarei piete, in timp), raport pe TEST (ultimele 30%).
Rezultat: data/research_tp/tp_modes.json + tp_modes.log
"""
import copy
import json
import os
import sys
import time

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts", "research_pair"))
sys.path.insert(0, os.path.join(ROOT, "scripts", "research_special"))
OUT = os.path.join(ROOT, "data", "research_tp")
os.makedirs(OUT, exist_ok=True)

import profit_lock as PL                                             # noqa: E402

RR = 2.0


def variants() -> dict:
    v = {"current": None}
    for e in (0.10, 0.15, 0.20):
        for s in (0.5, 1.0):
            for o in (0.10, 0.25, 0.50):
                v[f"special e{e:.2f} s{s:g} o{o:.2f}"] = {"enabled": True, "mode": "special", "tp_extension_R": e,
                                                           "step_R": s, "sl_offset_R": o}
    for k in (1.0, 2.0, 3.0):
        v[f"alt atr_trail k{k:g}"] = {"enabled": True, "mode": "atr_trail", "atr_mult": k, "sl_offset_R": 0.10,
                                      "tp_extension_R": 0.10, "step_R": 0.5}
    v["alt lock_from_1R s0.5 o0.5"] = {"enabled": True, "mode": "special", "tp_extension_R": 0.0, "step_R": 0.5,
                                       "sl_offset_R": 0.5, "_activate": 1.0}
    return v


def run_variant(trades, path_of, cfg, be=None, sequence=True):
    """trades: [{key, t0 (np.datetime64), i0, end, side, entry, risk, atr_R, cost_R, slot}] → rezultate pe varianta.
    `sequence`: o pozitie odata pe slot (ca engine-ul) — o iesire mai tarzie blocheaza urmatoarea intrare."""
    out, busy = [], {}
    act = (cfg or {}).get("_activate", RR)
    for t in trades:
        if sequence and t["t0"] < busy.get(t["slot"], np.datetime64("1970-01-01")):
            continue
        o, h, l, c, times = path_of(t)
        r = PL.simulate_path(o, h, l, c, side=t["side"], entry=t["entry"], risk=t["risk"], sl_R=-1.0, tp_R=RR,
                             rr=act, cfg=cfg, start=t["i0"], end=t["end"], atr_R=t.get("atr_R"), be=be)
        busy[t["slot"]] = times[r["exit_i"]]
        net = r["R"] - t["cost_R"] - t.get("swap_R_per_night", 0.0) * max(
            0, int((times[r["exit_i"]] - t["t0"]) / np.timedelta64(1, "D")))
        out.append({"t": t["t0"], "R": float(net), "gross": float(r["R"]), "why": r["why"], "peak": float(r["peak_R"]),
                    "stage": r["stage"]})
    return out


def metrics(rows) -> dict:
    if not rows:
        return {"n": 0}
    R = np.array([r["R"] for r in rows])
    pk = np.array([r["peak"] for r in rows])
    wins, losses = R[R > 0], R[R < 0]
    eq = np.cumsum(R)
    dd = float((eq - np.maximum.accumulate(eq)).min())
    streak = mx = 0
    for x in R:
        streak = streak + 1 if x < 0 else 0
        mx = max(mx, streak)
    cut = int(0.7 * len(R))
    lock = [r for r in rows if r["why"] in ("LOCK",)]
    return {"n": int(len(R)), "net_R": round(float(R.sum()), 1), "exp_R": round(float(R.mean()), 4),
            "win_rate": round(float((R > 0).mean() * 100), 1),
            "pf": round(float(wins.sum() / -losses.sum()), 3) if len(losses) and losses.sum() < 0 else None,
            "avg_win": round(float(wins.mean()), 3) if len(wins) else None,
            "avg_loss": round(float(losses.mean()), 3) if len(losses) else None,
            "max_dd_R": round(dd, 1), "max_consec_losses": int(mx),
            "train_exp": round(float(R[:cut].mean()), 4), "test_exp": round(float(R[cut:].mean()), 4),
            "reach": {f">={k}R": round(float((pk >= k - 1e-9).mean() * 100), 1) for k in (1, 2, 2.5, 3, 4, 5)},
            "exits": pd.Series([r["why"] for r in rows]).value_counts().to_dict(),
            "R_dist": {"p10": round(float(np.percentile(R, 10)), 2), "p50": round(float(np.percentile(R, 50)), 2),
                       "p90": round(float(np.percentile(R, 90)), 2), "max": round(float(R.max()), 2)},
            "giveback_R_on_locks": round(float(np.mean([r["peak"] - r["gross"] for r in lock])), 3) if lock else None}


# ── Custom ────────────────────────────────────────────────────────────────────────────────────────────────────

def custom_trades(sig: str):
    import pair_hedge as H
    import engine.portfolio as P
    import common as SC
    from adapters.csv_source import CsvDataSource
    from strategy.preparation import prepare_symbol_tf
    from m0.session_runner import _apply_session_to_cfg, _build_params, _load_base_cfg
    prof = json.load(open(os.path.join(ROOT, "data", "profiles", "standard.json"), encoding="utf-8"))
    s = copy.deepcopy(next(x for x in prof["sessions"] if x["session_key"] == H.SESSION_OF[sig]))
    cfg = _apply_session_to_cfg(_load_base_cfg(), s)
    df = prepare_symbol_tf(CsvDataSource(H.DATA), sig, cfg, s["entry_tf"], s["trend_tf"])
    params = _build_params(s, {sig: df}, 1e9)
    params["spread_pips"] = {sig: H.SPREAD_PIPS[sig]}
    fills, orig = [], P.simulate_trade

    def spy(d, j, p, *a, **k):
        res = orig(d, j, p, *a, **k)
        fills.append({"bar_time": d.iloc[j]["time"], "dir": int(p["dir"]), "entry": float(p["entry"]),
                      "sl": float(p["sl"]), "type": p.get("signal_type", "pullback"),
                      "atr": float(d.iloc[j - 1]["atr"]) if j > 0 else None})
        return res
    P.simulate_trade = spy
    try:
        P.run_portfolio({sig: df}, cfg, params, verbose=False)
    finally:
        P.simulate_trade = orig
    m = H.load_m1()
    a = m[sig]
    sp = SC.spec(sig)
    out = []
    for f in sorted(fills, key=lambda x: x["bar_time"]):
        ti, fill = H.find_trigger(m, sig, f["dir"], f["entry"], pd.Timestamp(f["bar_time"]), 15)
        t0 = m["time"][ti]
        dl = np.datetime64(H.friday_deadline(pd.Timestamp(t0)))
        if t0 >= dl:
            continue
        end = int(np.searchsorted(m["time"], dl)) + 1
        risk = abs(f["entry"] - f["sl"])
        swap = (sp["swap_long"] if f["dir"] == 1 else sp["swap_short"]) / risk
        out.append({"t0": t0, "i0": ti + 1, "end": min(end, len(m["time"])), "side": f["dir"], "entry": fill,
                    "risk": risk, "atr_R": (f["atr"] / risk) if f["atr"] else None, "slot": f["type"],
                    # spread FIX (masurat ziua, contul Standard) — nu cel live de la ora rularii (noaptea e mai mare)
                    "cost_R": H.SPREAD_PIPS[sig] * H.PIP * 1.25 / risk, "swap_R_per_night": swap})
    be = {"enabled": s.get("break_even_enabled", False), "phase2_enabled": s.get("be_phase2_enabled", True),
          "trigger_pct": s.get("be_trigger_pct", 80), "lock1_pct": s.get("be_lock1_pct", 30),
          "lock2_pct": s.get("be_lock2_pct", 50), "phase2_zone_pct": s.get("be_phase2_zone_pct", 40)}
    path = (a["open"], a["high"], a["low"], a["close"], m["time"])
    return out, (lambda t: path), be, s


# ── Daily ─────────────────────────────────────────────────────────────────────────────────────────────────────

def daily_trades(m: dict):
    from intraday_orb import load_m5, prep
    from daily_engine.strategy import evaluate_day
    from daily_engine.config import ENTRY_MODES, hm_to_min
    import common as SC
    d, om = prep(load_m5(m["symbol"]), m["tz"], m["open"], m["last_bar"])
    info = SC.mt5().symbol_info(m["symbol"])
    point = float(info.point)
    out, paths = [], {}
    for day, g in d.groupby("day", sort=True):
        if g.mins.iloc[0] != om or len(g) < m["or_minutes"] // 5 + 6:
            continue
        o, h, l, c = (g[k].to_numpy(float) for k in ("open", "high", "low", "close"))
        spr = g["spread"].to_numpy(float) * point
        r = evaluate_day(o, h, l, c, spr, g.mins.to_numpy(), open_min=om, or_minutes=m["or_minutes"],
                         mode=ENTRY_MODES[m["entry"]], rr=None, slip=m["slip"], comm=m["comm"], day_complete=True)
        if r.get("phase") != "closed":
            continue
        i0 = r["entry_bar"]
        side, entry, risk = r["side"], r["entry"], r["risk"]
        key = str(day.date())
        paths[key] = (o, h, l, c, g["loc"].dt.tz_localize(None).to_numpy())
        start = i0
        if m["entry"] == "breakout":
            # bara de intrare: doar SL (ca engine-ul) — treptele / TP de la bara urmatoare
            if (side == 1 and l[i0] <= r["sl"]) or (side == -1 and h[i0] >= r["sl"]):
                start = i0                       # simulate_path va prinde SL-ul pe bara i0
            else:
                start = i0 + 1
        if start >= len(o):
            continue
        rng = pd.Series(h - l).rolling(14, min_periods=1).mean().to_numpy()
        out.append({"t0": paths[key][4][i0], "i0": start, "end": len(o), "side": side, "entry": entry, "risk": risk,
                    "atr_R": float(rng[max(0, i0 - 1)] / risk), "slot": "day", "key": key,
                    "cost_R": (float(spr[i0]) / 2 + m["slip"] + m["comm"]) / risk})
    return out, (lambda t: paths[t["key"]])


# ── Noisy ─────────────────────────────────────────────────────────────────────────────────────────────────────

def noisy_trades():
    from datetime import datetime, timezone
    import MetaTrader5 as mt5
    from noisy_engine.config import load_config
    from noisy_engine.engine import rates_to_bars
    sys.path.insert(0, os.path.join(ROOT, "scripts", "research_noisy"))
    from noisy_backtest import backtest
    assert mt5.initialize()
    cfg = load_config()
    sym = cfg["symbol"]
    mt5.symbol_select(sym, True)
    rates = mt5.copy_rates_range(sym, mt5.TIMEFRAME_M1, datetime(2025, 11, 3, tzinfo=timezone.utc),
                                 datetime(2026, 11, 4, tzinfo=timezone.utc))
    bars = rates_to_bars(rates, None, mt5.symbol_info(sym).point, tf_min=1)
    trades = backtest(cfg, bars)
    tt = bars["t"].to_numpy()
    o, h, l, c = (bars[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    atr = pd.Series(h - l).rolling(14, min_periods=1).mean().to_numpy()
    ts = cfg["strategy"]["time_stop_bars"]
    out = []
    for t in trades:
        i0 = int(np.searchsorted(tt, np.datetime64(pd.Timestamp(t["entry_t"]).tz_localize(None))))
        if i0 >= len(tt):
            continue
        side = 1 if t["dir"] == "LONG" else -1
        out.append({"t0": tt[i0], "i0": i0, "end": min(len(tt), i0 + ts + 1), "side": side, "entry": t["entry"],
                    "risk": t["risk"], "atr_R": float(atr[max(0, i0 - 1)] / t["risk"]), "slot": "n",
                    "cost_R": t["cost"] / t["risk"]})
    return out, (lambda t: (o, h, l, c, tt)), cfg


def main():
    t0 = time.time()
    V = variants()
    res = {}
    jobs = []
    for sig in ("GBPUSD", "EURUSD"):
        trades, path_of, be, s = custom_trades(sig)
        jobs.append((f"Custom {sig} ({s['id']} {s['entry_tf']}+{s['trend_tf']})", trades, path_of, be))
        print(f"Custom {sig}: {len(trades)} intrari ({time.time() - t0:.0f}s)", flush=True)
    from daily_engine.config import load_config as dcfg
    for mk in dcfg()["markets"]:
        trades, path_of = daily_trades(mk)
        jobs.append((f"Daily {mk['symbol']} ({mk['tz'].split('/')[-1]} {mk['or_minutes']}m {mk['entry']})",
                     trades, path_of, None))
        print(f"Daily {mk['symbol']}: {len(trades)} intrari ({time.time() - t0:.0f}s)", flush=True)
    trades, path_of, ncfg = noisy_trades()
    jobs.append((f"Noisy {ncfg['symbol']} ({ncfg['timeframe']}, TP {ncfg['strategy']['tp_rr']:g}R, stop "
                 f"{ncfg['strategy']['time_stop_bars']} bare)", trades, path_of, None))
    print(f"Noisy: {len(trades)} intrari ({time.time() - t0:.0f}s)", flush=True)
    for name, trades, path_of, be in jobs:
        res[name] = {}
        daily = name.startswith("Daily")
        for vname, vc in V.items():
            if vname == "current":
                cfgv = None
                if daily:          # actual Daily = fara TP (inchidere la final de zi)
                    rows = []
                    busy = {}
                    for t in trades:
                        o, h, l, c, tt = path_of(t)
                        r = PL.simulate_path(o, h, l, c, side=t["side"], entry=t["entry"], risk=t["risk"], sl_R=-1.0,
                                             tp_R=None, rr=RR, cfg=None, start=t["i0"], end=t["end"])
                        rows.append({"t": t["t0"], "R": r["R"] - t["cost_R"], "gross": r["R"], "why": r["why"],
                                     "peak": r["peak_R"], "stage": 0})
                    res[name]["current"] = metrics(rows)
                    res[name]["standard 2R"] = metrics(run_variant(trades, path_of, None, be))
                    continue
            else:
                cfgv = vc
            res[name][vname] = metrics(run_variant(trades, path_of, cfgv, be))
        cur = res[name]["current"]
        print(f"\n== {name}: actual n={cur['n']} exp={cur['exp_R']} netR={cur['net_R']} DD={cur['max_dd_R']} "
              f"PF={cur['pf']}", flush=True)
        for vname, mt in res[name].items():
            if vname != "current":
                print(f"   {vname:28} n={mt['n']} exp={mt['exp_R']:+.4f} netR={mt['net_R']} PF={mt['pf']} "
                      f"DD={mt['max_dd_R']} WR={mt['win_rate']} train={mt['train_exp']:+.4f} test={mt['test_exp']:+.4f} "
                      f"≥3R={mt['reach']['>=3R']}%", flush=True)
    json.dump(res, open(os.path.join(OUT, "tp_modes.json"), "w"), indent=1, default=str)
    print(f"gata in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
