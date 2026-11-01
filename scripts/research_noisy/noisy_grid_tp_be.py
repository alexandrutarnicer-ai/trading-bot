"""
Noisy Engine — efectul unei tinte mai mari (TP fix in R) si al break-even-ului, pe barele REALE (12 luni),
cu exact functia engine-ului (run_day). Doar citire MT5.

    python scripts/research_noisy/noisy_grid_tp_be.py M1      (sau M5)  -> data/research_noisy/grid_tp_be_<TF>.json
"""
from __future__ import annotations

import copy
import json
import os
import sys

import numpy as np
import MetaTrader5 as mt5

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

import noisy_backtest as B  # noqa: E402
from noisy_engine.config import load_config  # noqa: E402
from noisy_engine.engine import rates_to_bars  # noqa: E402

TPS = [("EMA (acum)", 0.0), ("1,5R", 1.5), ("2R", 2.0), ("3R", 3.0)]
BES = [("fara BE", 0.0, 0.0), ("BE la +0,5R", 0.5, 0.0), ("BE la +1R", 1.0, 0.0), ("BE +1R → +0,2R", 1.0, 0.2)]


def main() -> None:
    tf = sys.argv[1] if len(sys.argv) > 1 else "M1"
    assert mt5.initialize()
    base = load_config()
    base["timeframe"] = tf
    if tf == "M5":                                   # valorile testate pe M5
        base["strategy"]["min_atr_over_cost"] = 15
        for k, v in (("max_trades_day", 6), ("max_losses_day", 4), ("max_consec_losses", 3)):
            base["limits"][k] = {"enabled": True, "value": v}
    rates = mt5.copy_rates_range(base["symbol"], getattr(mt5, f"TIMEFRAME_{tf}"), B.START, B.END)
    bars = rates_to_bars(rates, None, mt5.symbol_info(base["symbol"]).point)
    out = []
    for tp_name, tp in TPS:
        for be_name, trig, lock in BES:
            if tp and trig and trig >= tp:
                continue                             # BE dupa tinta = fara sens
            c = copy.deepcopy(base)
            c["strategy"].update(tp_rr=tp, be_trigger_R=trig, be_lock_R=lock)
            tr = B.backtest(c, bars)
            s = B.stats(tr)
            reasons = {}
            for x in tr:
                reasons[x["reason"]] = reasons.get(x["reason"], 0) + 1
            r = np.array([x["R"] for x in tr])
            row = {"tp": tp_name, "be": be_name, "trades": s["trades"], "per_day": s.get("per_day_active"),
                   "win_rate": s["win_rate"], "expectancy_R": s["expectancy_R"], "max_dd_R": s["max_dd_R"],
                   "test_R": s.get("test_R"), "t_stat": s.get("t_stat"),
                   "avg_win": round(float(r[r > 0].mean()), 2) if (r > 0).any() else None,
                   "avg_loss": round(float(r[r < 0].mean()), 2) if (r < 0).any() else None,
                   "exits": {k: round(v / len(tr) * 100) for k, v in reasons.items()}}
            out.append(row)
            print(f"{tf} | TP {tp_name:10s} | {be_name:15s} | {row['trades']:5d} tr | WR {row['win_rate'] * 100:4.1f}% | "
                  f"{row['expectancy_R']:+.3f}R | DD {row['max_dd_R']:7.1f}R | test {row['test_R']:+.3f} | "
                  f"castig {row['avg_win']} / pierdere {row['avg_loss']} | iesiri {row['exits']}", flush=True)
    json.dump(out, open(os.path.join(B.OUT, f"grid_tp_be_{tf}.json"), "w", encoding="utf-8"), indent=1)


if __name__ == "__main__":
    main()
