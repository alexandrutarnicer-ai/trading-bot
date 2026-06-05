import numpy as np
import pandas as pd

from engine.simulator import simulate_trade
from strategy.signals import pip_size, count_optional, reward_R
from strategy.structure import detect_setup


def run_symbol(df, symbol, cfg, spread_pips, pip_val_per_lot):
    """
    Bucla de backtest pentru o singura pereche pe un DataFrame pre-incarcat.
    Returneaza (trades, equity_curve, equity_timeline, setups_detected).
    """
    pip = pip_size(symbol)
    buf = 2 * pip
    spread = spread_pips.get(symbol, 1.0) * pip
    comm = cfg["costs"]["commission_per_lot_round_turn_usd"]
    risk_pct = cfg["account"]["risk_per_trade_pct"] / 100.0
    risk_pct_all = cfg["account"].get("risk_per_trade_pct_all_criteria",
                                      cfg["account"]["risk_per_trade_pct"]) / 100.0
    sh, eh = cfg["session"]["start_hour"], cfg["session"]["end_hour"]
    max_trades = cfg["risk_management"]["max_trades_per_day"]
    max_losses = cfg["risk_management"]["max_consecutive_losses"]
    expire_bars = 4

    balance = cfg["account"]["starting_balance"]
    equity_curve = [balance]
    equity_timeline = []
    trades = []
    setups_detected = 0

    day = None
    trades_today = 0
    consec_losses = 0
    pending = None
    busy_until = -1

    n = len(df)
    for j in range(60, n):
        row = df.iloc[j]
        t = row["time"]

        if day != t.date():
            day = t.date()
            trades_today = 0
            consec_losses = 0
            pending = None

        if j <= busy_until:
            continue

        in_session = (sh <= t.hour < eh)

        if pending:
            d = pending["dir"]
            if (d == 1 and row["low"] < pending["invalidate"]) or \
               (d == -1 and row["high"] > pending["invalidate"]):
                pending = None
            elif j - pending["armed_at"] > expire_bars:
                pending = None
            else:
                triggered = (d == 1 and row["high"] >= pending["entry"]) or \
                            (d == -1 and row["low"]  <= pending["entry"])
                if triggered:
                    res = simulate_trade(df, j, pending, spread, pip,
                                         pip_val_per_lot, comm, symbol)
                    balance += res["pnl_usd"]
                    equity_curve.append(balance)
                    equity_timeline.append({"time": res["exit_time"], "balance": round(balance, 2)})
                    trades.append(res)
                    trades_today += 1
                    consec_losses = consec_losses + 1 if res["pnl_usd"] < 0 else 0
                    busy_until = res["exit_j"]
                    pending = None
            continue

        if not in_session or trades_today >= max_trades or consec_losses >= max_losses:
            continue
        if row["trend"] == 0 or pd.isna(row["trend"]):
            continue

        direction = int(row["trend"])
        found = detect_setup(df, j, direction)
        if found is None:
            continue
        ext, _ = found
        setups_detected += 1

        if direction == 1:
            entry = row["high"] + buf
            sl = ext - buf
        else:
            entry = row["low"] - buf
            sl = ext + buf
        risk_dist = abs(entry - sl)
        if risk_dist <= 0:
            continue

        n_opt = count_optional(row, direction, cfg)
        R = reward_R(n_opt, cfg)
        tp = entry + direction * risk_dist * R

        rp = risk_pct_all if n_opt >= 2 else risk_pct
        risk_usd = balance * rp
        sl_pips = risk_dist / pip
        lots = risk_usd / (sl_pips * pip_val_per_lot)
        lots = np.floor(lots / 0.01) * 0.01
        if lots < 0.01:
            continue

        pending = {"dir": direction, "entry": entry, "sl": sl, "tp": tp,
                   "lots": lots, "R": R, "invalidate": ext, "armed_at": j,
                   "time": t, "risk_usd": risk_usd}

    return trades, equity_curve, equity_timeline, setups_detected
