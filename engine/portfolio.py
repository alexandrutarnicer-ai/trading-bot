import numpy as np
import pandas as pd

from engine.simulator import simulate_trade
from strategy.signals import pip_size, count_optional, reward_R
from strategy.structure import detect_setup
from strategy.patterns import detect_flag, detect_inside_bar
from strategy.costs import swap_cost, pip_value_usd, notional_usd


def run_portfolio(data, cfg, params, verbose=True):
    """
    data   : {symbol: DataFrame} — pre-incarcat de catre entry-point
    params : dict cu setarile de portofoliu (spread, leverage, filtre etc.)
    Returneaza (trades, equity, balance, max_concurrent, skipped_margin,
                halted_days, split_time).
    """
    spread_pips        = params["spread_pips"]
    leverage           = params["leverage"]
    start_balance      = params["start_balance"]
    expire_bars        = params["expire_bars"]
    pullback_window    = params["pullback_window"]
    depth_range        = params["depth_range"]
    skip_monday        = params["skip_monday"]
    skip_weekdays      = params.get("skip_weekdays", set())
    if skip_monday:
        skip_weekdays = skip_weekdays | {0}
    skip_hours         = params["skip_hours"]
    atr_max_pips       = params["atr_max_pips"]
    max_day_consec_losses = params["max_day_consec_losses"]
    corr_pairs         = params["corr_pairs"]
    max_pos_per_symbol      = params.get("max_pos_per_symbol", 1)
    min_bars_between_symbol = params.get("min_bars_between_same_symbol", 0)
    be_cfg                  = params.get("be_cfg", None)
    flag_cfg                = params.get("flag_cfg", None)
    inside_bar_cfg          = params.get("inside_bar_cfg", None)
    symbol_sessions         = params.get("symbol_sessions", {})    # {symbol: (sh, eh)}
    symbol_skip_hours       = params.get("symbol_skip_hours", {})  # {symbol: tuple}

    rp_base = cfg["account"]["risk_per_trade_pct"] / 100.0
    rp_all  = cfg["account"].get("risk_per_trade_pct_all_criteria",
                                 cfg["account"]["risk_per_trade_pct"]) / 100.0
    comm     = cfg["costs"]["commission_per_lot_round_turn_usd"]
    sh, eh   = cfg["session"]["start_hour"], cfg["session"]["end_hour"]
    max_trades = cfg["risk_management"]["max_trades_per_day"]
    max_losses = cfg["risk_management"]["max_consecutive_losses"]

    ujdf     = data.get("USDJPY")
    uj_times = ujdf["time"].values if ujdf is not None else None
    uj_close = ujdf["close"].values if ujdf is not None else None

    def usdjpy_at(ts):
        if uj_times is None:
            return 150.0
        i = np.searchsorted(uj_times, np.datetime64(ts), side="right") - 1
        return float(uj_close[max(0, min(i, len(uj_close) - 1))])

    events = []
    for s, df in data.items():
        times = df["time"].values
        for jj in range(60, len(df)):
            events.append((times[jj], s, jj))
    events.sort(key=lambda e: e[0])
    split_time = pd.Timestamp(events[int(0.7 * len(events))][0])
    if verbose:
        print(f"  total evenimente: {len(events)}")
        print(f"  split train/test la: {split_time.date()}\n  rulez...")

    balance    = start_balance
    equity     = [{"time": events[0][0], "balance": balance}]
    trades     = []

    # pendings[s]: lista de ordine pending (pana la max_pos_per_symbol per simbol)
    # active_count[s]: total pozitii active per simbol (toate tipurile)
    # active_pb/fl/ib[s]: pozitii active per tip — slot independent per strategie
    # open_trades: (exit_time, symbol, pnl_usd, margin_reserved, signal_type)
    pendings         = {s: []   for s in data}
    active_count     = {s: 0    for s in data}
    active_pb        = {s: 0    for s in data}
    active_fl        = {s: 0    for s in data}
    active_ib        = {s: 0    for s in data}
    last_trigger_j   = {s: -9999 for s in data}
    day_state    = {s: None for s in data}
    trades_today = {s: 0    for s in data}
    consec       = {s: 0    for s in data}
    open_margin  = {s: 0.0  for s in data}
    active_dir   = {s: None for s in data}
    open_trades  = []

    open_now       = 0
    max_concurrent = 0
    skipped_margin = 0
    gday      = None
    gconsec   = 0
    ghalt     = False
    halted_days = 0

    for (t, s, jj) in events:
        t = pd.Timestamp(t)

        if t.date() != gday:
            gday = t.date(); gconsec = 0; ghalt = False

        # --- inchide tranzactii expirate ---
        if open_trades:
            still = []
            for (xt, xs, pnl, marg, st) in open_trades:
                if xt <= t:
                    balance += pnl
                    equity.append({"time": xt, "balance": round(balance, 2)})
                    consec[xs]  = consec[xs] + 1 if pnl < 0 else 0
                    gconsec     = gconsec + 1 if pnl < 0 else 0
                    if gconsec >= max_day_consec_losses and not ghalt:
                        ghalt = True; halted_days += 1
                    active_count[xs] -= 1
                    if st == "flag":       active_fl[xs] = max(0, active_fl[xs] - 1)
                    elif st == "inside_bar": active_ib[xs] = max(0, active_ib[xs] - 1)
                    else:                  active_pb[xs] = max(0, active_pb[xs] - 1)
                    open_margin[xs]   = max(0.0, open_margin[xs] - marg)
                    if active_count[xs] <= 0:
                        active_count[xs] = 0
                        active_dir[xs]   = None
                    open_now -= 1
                else:
                    still.append((xt, xs, pnl, marg, st))
            open_trades = still

        df  = data[s]
        row = df.iloc[jj]
        pip = pip_size(s)

        if day_state[s] != t.date():
            day_state[s]    = t.date()
            trades_today[s] = 0
            consec[s]       = 0
            pendings[s]     = []

        # --- proceseaza toate ordinele pending pentru acest simbol ---
        remaining = []
        for p in pendings[s]:
            d = p["dir"]
            if (d == 1 and row["low"] < p["invalidate"]) or \
               (d == -1 and row["high"] > p["invalidate"]):
                pass  # invalidat, se elimina
            elif jj - p["armed_at"] > expire_bars:
                pass  # expirat, se elimina
            else:
                trig = (d == 1 and row["high"] >= p["entry"]) or \
                       (d == -1 and row["low"]  <= p["entry"])
                if trig:
                    margin = notional_usd(s, p["entry"], p["lots"]) / leverage
                    used   = sum(open_margin.values())
                    if balance - used < margin:
                        skipped_margin += 1
                        # fonduri insuficiente — ordinul se elimina
                    else:
                        pv  = p["pv"]
                        spr = spread_pips.get(s, 1.0) * pip
                        res = simulate_trade(df, jj, p, spr, pip, pv, comm, s, be_cfg=be_cfg)
                        sc  = swap_cost(s, res["time"], res["exit_time"], p["lots"])
                        res["swap"]       = round(sc, 3)
                        res["pnl_usd"]    = round(res["pnl_usd"] - sc, 2)
                        res["atr_pips"]   = p["atr_pips"]
                        _st = p.get("signal_type", "pullback")
                        res["signal_type"] = _st
                        open_trades.append((pd.Timestamp(res["exit_time"]), s,
                                            res["pnl_usd"], margin, _st))
                        open_margin[s]    += margin
                        active_dir[s]      = d
                        active_count[s]   += 1
                        if _st == "flag":        active_fl[s] += 1
                        elif _st == "inside_bar": active_ib[s] += 1
                        else:                    active_pb[s] += 1
                        last_trigger_j[s]  = jj
                        trades_today[s]   += 1
                        trades.append(res)
                        open_now += 1
                        max_concurrent = max(max_concurrent, open_now)
                        # triggerat — nu se mai pune in remaining
                else:
                    remaining.append(p)
        pendings[s] = remaining

        if ghalt:
            continue
        sym_sh, sym_eh = symbol_sessions.get(s, (sh, eh))
        if not (sym_sh <= t.hour < sym_eh):
            continue
        if t.weekday() in skip_weekdays:
            continue
        eff_skip_hours = symbol_skip_hours.get(s, skip_hours)
        if t.hour in eff_skip_hours:
            continue
        if trades_today[s] >= max_trades or consec[s] >= max_losses:
            continue
        if row["trend"] == 0 or pd.isna(row["trend"]):
            continue
        cap = atr_max_pips.get(s)
        if cap and row["atr"] / pip > cap:
            continue

        direction = int(row["trend"])
        if params.get("only_long") and direction == -1:
            continue
        # Filtru de regim: coloana specificata trebuie sa fie 1 pentru a permite intrarea.
        # daily_regime_filter (legacy) = echivalent cu regime_filter_col="daily_trend"
        _rcol = params.get("regime_filter_col") or (
            "daily_trend" if params.get("daily_regime_filter") else None)
        if _rcol and int(row.get(_rcol, 0) or 0) != 1:
            continue

        corr = corr_pairs.get(s)
        if corr and corr in data:
            corr_dir = pendings[corr][0]["dir"] if pendings[corr] else active_dir[corr]
            if corr_dir == direction:
                continue

        buf = 2 * pip

        # Slot per tip: pullback respecta max_pos_per_symbol, flag si IB au slot independent
        pb_pending = sum(1 for p in pendings[s] if p.get("signal_type", "pullback") == "pullback")
        fl_pending = sum(1 for p in pendings[s] if p.get("signal_type") == "flag")
        ib_pending = sum(1 for p in pendings[s] if p.get("signal_type") == "inside_bar")

        # --- Pullback-in-trend (strategie principala) ---
        if active_pb[s] + pb_pending < max_pos_per_symbol:
          _delay_ok = not (active_pb[s] > 0 and min_bars_between_symbol > 0
                           and jj - last_trigger_j[s] < min_bars_between_symbol)
          if _delay_ok:
            found = detect_setup(df, jj, direction, window=pullback_window, depth_range=depth_range)
          else:
            found = None
        else:
          found = None
        if found is not None:
            ext, _ = found
            if direction == 1:
                entry = row["high"] + buf; sl = ext - buf
            else:
                entry = row["low"] - buf; sl = ext + buf
            risk_dist = abs(entry - sl)
            if risk_dist > 0:
                n_opt = count_optional(row, direction, cfg)
                R     = reward_R(n_opt, cfg)
                tp    = entry + direction * risk_dist * R
                rp    = rp_all if n_opt >= 2 else rp_base
                risk_usd = balance * rp
                pv    = pip_value_usd(s, entry, usdjpy_at(t))
                lots  = np.floor(risk_usd / ((risk_dist / pip) * pv) / 0.01) * 0.01
                if lots >= 0.01:
                    pendings[s].append({
                        "dir": direction, "entry": entry, "sl": sl, "tp": tp,
                        "lots": lots, "R": R, "invalidate": ext, "armed_at": jj,
                        "time": t, "risk_usd": risk_usd, "pv": pv,
                        "atr_pips": round(row["atr"] / pip, 1),
                        "signal_type": "pullback",
                    })

        # --- Flag pattern (optional, independent — slot propriu, nu depinde de pullback) ---
        if flag_cfg and flag_cfg.get("enabled") and active_fl[s] + fl_pending < 1:
            _fcfg = {
                "pole_min_candles":    flag_cfg.get("pole_min_candles",    3),
                "pole_min_body_atr":   flag_cfg.get("pole_min_body_atr",   0.5),
                "flag_min_bars":       flag_cfg.get("flag_min_bars",        2),
                "flag_max_bars":       flag_cfg.get("flag_max_bars",        5),
                "flag_max_retrace_pct": flag_cfg.get("flag_max_retrace_pct", 50),
            }
            f_res = detect_flag(df, jj, direction, _fcfg)
            if f_res is not None:
                sl_lv, _ = f_res
                # Entry la HIGH-ul barei de breakout + buf (ca la pullback),
                # nu la flag_high + buf care poate fi deja sub close-ul curent.
                if direction == 1:
                    f_entry = row["high"] + buf; f_sl = sl_lv - buf
                else:
                    f_entry = row["low"] - buf; f_sl = sl_lv + buf
                f_risk = abs(f_entry - f_sl)
                if f_risk > 0:
                    f_R   = float(flag_cfg.get("r_ratio",   2.0))
                    f_rp  = float(flag_cfg.get("risk_pct",  0.01))
                    f_tp  = f_entry + direction * f_risk * f_R
                    f_ru  = balance * f_rp
                    pv_f  = pip_value_usd(s, f_entry, usdjpy_at(t))
                    f_lot = np.floor(f_ru / ((f_risk / pip) * pv_f) / 0.01) * 0.01
                    if f_lot >= 0.01:
                        pendings[s].append({
                            "dir": direction, "entry": f_entry, "sl": f_sl, "tp": f_tp,
                            "lots": f_lot, "R": f_R, "invalidate": sl_lv,
                            "armed_at": jj, "time": t, "risk_usd": f_ru, "pv": pv_f,
                            "atr_pips": round(row["atr"] / pip, 1),
                            "signal_type": "flag",
                        })

        # --- Inside Bar Breakout (optional, independent — slot propriu, nu depinde de pullback) ---
        if inside_bar_cfg and inside_bar_cfg.get("enabled") and active_ib[s] + ib_pending < 1:
            ib_res = detect_inside_bar(df, jj, direction)
            if ib_res is not None:
                sl_lv, _ent_lv = ib_res
                # Entry la HIGH-ul barei de breakout + buf — BUY_STOP valid in MT5.
                if direction == 1:
                    ib_entry = row["high"] + buf; ib_sl = sl_lv - buf
                else:
                    ib_entry = row["low"] - buf; ib_sl = sl_lv + buf
                ib_risk = abs(ib_entry - ib_sl)
                if ib_risk > 0:
                    ib_R   = float(inside_bar_cfg.get("r_ratio",  2.0))
                    ib_rp  = float(inside_bar_cfg.get("risk_pct", 0.01))
                    ib_tp  = ib_entry + direction * ib_risk * ib_R
                    ib_ru  = balance * ib_rp
                    pv_ib  = pip_value_usd(s, ib_entry, usdjpy_at(t))
                    ib_lot = np.floor(ib_ru / ((ib_risk / pip) * pv_ib) / 0.01) * 0.01
                    if ib_lot >= 0.01:
                        pendings[s].append({
                            "dir": direction, "entry": ib_entry, "sl": ib_sl, "tp": ib_tp,
                            "lots": ib_lot, "R": ib_R, "invalidate": sl_lv,
                            "armed_at": jj, "time": t, "risk_usd": ib_ru, "pv": pv_ib,
                            "atr_pips": round(row["atr"] / pip, 1),
                            "signal_type": "inside_bar",
                        })

    for (xt, xs, pnl, marg, _st) in open_trades:
        balance += pnl
        equity.append({"time": xt, "balance": round(balance, 2)})

    return trades, equity, balance, max_concurrent, skipped_margin, halted_days, split_time
