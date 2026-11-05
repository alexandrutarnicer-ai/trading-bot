"""Custom live verifica pozitiile la inchiderea barei M15 (nu minut cu minut): treptele recalculate doar la :14/:29/:44/:59,
SL-ul brokerului lovit oricand (M1). Variantele relevante, aceleasi intrari ca tp_modes.py."""
import os, sys, json
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tp_modes as T
import profit_lock as PL
V = {"current": None,
     "special e0.10 s0.5 o0.10 (userul)": {"enabled": True, "mode": "special", "tp_extension_R": .1, "step_R": .5, "sl_offset_R": .1},
     "special e0.10 s1 o0.50": {"enabled": True, "mode": "special", "tp_extension_R": .1, "step_R": 1.0, "sl_offset_R": .5},
     "alt atr_trail k3": {"enabled": True, "mode": "atr_trail", "atr_mult": 3.0, "sl_offset_R": .1, "tp_extension_R": .1, "step_R": .5}}
out = {}
for sig in ("GBPUSD", "EURUSD"):
    trades, path_of, be, s = T.custom_trades(sig)
    o, h, l, c, tt = path_of(None)
    minute = (tt.astype("datetime64[m]").astype(np.int64)) % 15
    mask = minute == 14
    out[sig] = {}
    for name, cfg in V.items():
        rows, busy = [], {}
        for t in trades:
            if t["t0"] < busy.get(t["slot"], np.datetime64("1970-01-01")):
                continue
            r = PL.simulate_path(o, h, l, c, side=t["side"], entry=t["entry"], risk=t["risk"], sl_R=-1.0, tp_R=2.0,
                                 rr=2.0, cfg=cfg, start=t["i0"], end=t["end"], atr_R=t["atr_R"], be=be, update_mask=mask)
            busy[t["slot"]] = tt[r["exit_i"]]
            nights = max(0, int((tt[r["exit_i"]] - t["t0"]) / np.timedelta64(1, "D")))
            rows.append({"t": t["t0"], "R": r["R"] - t["cost_R"] - t["swap_R_per_night"] * nights, "gross": r["R"],
                         "why": r["why"], "peak": r["peak_R"], "stage": r["stage"]})
        mt = T.metrics(rows)
        out[sig][name] = mt
        print(f"{sig} M15-update {name:34} n={mt['n']} exp={mt['exp_R']:+.4f} train={mt['train_exp']:+.4f} test={mt['test_exp']:+.4f} DD={mt['max_dd_R']} PF={mt['pf']}", flush=True)
json.dump(out, open(os.path.join(T.OUT, "tp_granularity.json"), "w"), indent=1, default=str)
