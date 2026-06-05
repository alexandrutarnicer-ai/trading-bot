import numpy as np
import pandas as pd

from engine.simulator import simulate_trade
from strategy.signals import pip_size, count_optional, reward_R
from strategy.structure import detect_setup
from strategy.costs import swap_cost, pip_value_usd, notional_usd


def run_portfolio(data, cfg, params):
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
    skip_hours         = params["skip_hours"]
    atr_max_pips       = params["atr_max_pips"]
    max_day_consec_losses = params["max_day_consec_losses"]
    corr_pairs         = params["corr_pairs"]

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
    print(f"  total evenimente: {len(events)}")
    print(f"  split train/test la: {split_time.date()}\n  rulez...")

    balance    = start_balance
    equity     = [{"time": events[0][0], "balance": balance}]
    trades     = []

    pending     = {s: None  for s in data}
    busy_until  = {s: -1    for s in data}
    day_state   = {s: None  for s in data}
    trades_today = {s: 0    for s in data}
    consec      = {s: 0     for s in data}
    open_margin = {s: 0.0   for s in data}
    active_dir  = {s: None  for s in data}
    open_trades = []

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

        if open_trades:
            still = []
            for (xt, xs, pnl) in open_trades:
                if xt <= t:
                    balance += pnl
                    equity.append({"time": xt, "balance": round(balance, 2)})
                    consec[xs]  = consec[xs] + 1 if pnl < 0 else 0
                    gconsec     = gconsec + 1 if pnl < 0 else 0
                    if gconsec >= max_day_consec_losses and not ghalt:
                        ghalt = True; halted_days += 1
                    open_margin[xs] = 0.0
                    active_dir[xs]  = None
                    open_now -= 1
                else:
                    still.append((xt, xs, pnl))
            open_trades = still

        df  = data[s]
        row = df.iloc[jj]

        if day_state[s] != t.date():
            day_state[s]   = t.date()
            trades_today[s] = 0
            consec[s]      = 0
            pending[s]     = None

        if jj <= busy_until[s]:
            continue

        pip = pip_size(s)

        if pending[s] is not None:
            p = pending[s]; d = p["dir"]
            if (d == 1 and row["low"] < p["invalidate"]) or \
               (d == -1 and row["high"] > p["invalidate"]):
                pending[s] = None
            elif jj - p["armed_at"] > expire_bars:
                pending[s] = None
            else:
                trig = (d == 1 and row["high"] >= p["entry"]) or \
                       (d == -1 and row["low"]  <= p["entry"])
                if trig:
                    margin = notional_usd(s, p["entry"], p["lots"]) / leverage
                    used   = sum(open_margin.values())
                    if balance - used < margin:
                        skipped_margin += 1
                        pending[s] = None
                        continue
                    pv  = p["pv"]
                    spr = spread_pips.get(s, 1.0) * pip
                    res = simulate_trade(df, jj, p, spr, pip, pv, comm, s)
                    sc  = swap_cost(s, res["time"], res["exit_time"], p["lots"])
                    res["swap"]     = round(sc, 3)
                    res["pnl_usd"]  = round(res["pnl_usd"] - sc, 2)
                    res["atr_pips"] = p["atr_pips"]
                    open_trades.append((pd.Timestamp(res["exit_time"]), s, res["pnl_usd"]))
                    open_margin[s]  = margin
                    active_dir[s]   = d
                    busy_until[s]   = res["exit_j"]
                    trades_today[s] += 1
                    trades.append(res)
                    open_now += 1
                    max_concurrent = max(max_concurrent, open_now)
                    pending[s] = None
            continue

        if ghalt:
            continue
        if not (sh <= t.hour < eh):
            continue
        if skip_monday and t.weekday() == 0:
            continue
        if t.hour in skip_hours:
            continue
        if trades_today[s] >= max_trades or consec[s] >= max_losses:
            continue
        if row["trend"] == 0 or pd.isna(row["trend"]):
            continue
        cap = atr_max_pips.get(s)
        if cap and row["atr"] / pip > cap:
            continue

        direction = int(row["trend"])

        corr = corr_pairs.get(s)
        if corr and corr in data:
            corr_dir = pending[corr]["dir"] if pending[corr] is not None else active_dir[corr]
            if corr_dir == direction:
                continue

        found = detect_setup(df, jj, direction, window=pullback_window, depth_range=depth_range)
        if found is None:
            continue
        ext, _ = found

        buf = 2 * pip
        if direction == 1:
            entry = row["high"] + buf; sl = ext - buf
        else:
            entry = row["low"] - buf; sl = ext + buf
        risk_dist = abs(entry - sl)
        if risk_dist <= 0:
            continue

        n_opt = count_optional(row, direction, cfg)
        R     = reward_R(n_opt, cfg)
        tp    = entry + direction * risk_dist * R

        rp       = rp_all if n_opt >= 2 else rp_base
        risk_usd = balance * rp
        pv       = pip_value_usd(s, entry, usdjpy_at(t))
        sl_pips  = risk_dist / pip
        lots     = risk_usd / (sl_pips * pv)
        lots     = np.floor(lots / 0.01) * 0.01
        if lots < 0.01:
            continue

        pending[s] = {"dir": direction, "entry": entry, "sl": sl, "tp": tp,
                      "lots": lots, "R": R, "invalidate": ext, "armed_at": jj,
                      "time": t, "risk_usd": risk_usd, "pv": pv,
                      "atr_pips": round(row["atr"] / pip, 1)}

    for (xt, xs, pnl) in open_trades:
        balance += pnl
        equity.append({"time": xt, "balance": round(balance, 2)})

    return trades, equity, balance, max_concurrent, skipped_margin, halted_days, split_time
