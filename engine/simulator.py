def simulate_trade(df, j, p, spread, pip, pip_val, comm, symbol, be_cfg=None):
    """Parcurge barele de la j inainte; intoarce primul exit (SL sau TP)."""
    d = p["dir"]
    entry = p["entry"] + d * spread          # platim spread la intrare

    def make(exit_price, outcome, k):
        pnl_price = (exit_price - entry) * d
        pnl_usd = (pnl_price / pip) * pip_val * p["lots"] - comm * p["lots"]
        return {"symbol": symbol, "time": p["time"], "exit_time": df.iloc[k]["time"],
                "dir": d, "lots": p["lots"], "R": p["R"],
                "entry": round(p["entry"], 5), "sl": round(p["sl"], 5),
                "tp": round(p["tp"], 5), "risk_usd": round(p["risk_usd"], 2),
                "outcome": outcome, "pnl_usd": round(pnl_usd, 2), "exit_j": k}

    # Break-even config
    be_enabled = bool(be_cfg and be_cfg.get("enabled", False))
    if be_enabled:
        tp_dist    = abs(p["tp"] - p["entry"])
        trig_pct   = be_cfg.get("trigger_pct",    80) / 100
        lock1_pct  = be_cfg.get("lock1_pct",      30) / 100
        lock2_pct  = be_cfg.get("lock2_pct",      50) / 100
        zone_pct   = be_cfg.get("phase2_zone_pct", 40) / 100
        be_80      = p["entry"] + d * tp_dist * trig_pct
        be_30      = p["entry"] + d * tp_dist * lock1_pct
        be_40      = p["entry"] + d * tp_dist * zone_pct
        be_50      = p["entry"] + d * tp_dist * lock2_pct
        be_phase   = 0
        be_in_zone = False
        current_sl = p["sl"]
    else:
        current_sl = p["sl"]

    end = min(j + 400, len(df))
    for k in range(j, end):
        bar = df.iloc[k]

        if not be_enabled:
            hit_sl = (d == 1 and bar["low"] <= p["sl"]) or (d == -1 and bar["high"] >= p["sl"])
            hit_tp = (d == 1 and bar["high"] >= p["tp"]) or (d == -1 and bar["low"] <= p["tp"])
            if hit_sl:
                return make(p["sl"], "loss", k)
            if hit_tp:
                return make(p["tp"], "win", k)
            continue

        if d == 1:
            hit_tp      = bar["high"] >= p["tp"]
            reached_80  = bar["high"] >= be_80
            reversed_80 = bar["low"]  <  be_80
            in_zone     = be_30 < bar["low"] <= be_40
        else:
            hit_tp      = bar["low"]  <= p["tp"]
            reached_80  = bar["low"]  <= be_80
            reversed_80 = bar["high"] >  be_80
            in_zone     = be_40 <= bar["high"] < be_30

        # elif: max o tranzitie de faza per bara (previne skip de faze pe lumânari volatile)
        if be_phase == 0 and reached_80:
            be_phase = 1
        elif be_phase == 1 and reversed_80:
            current_sl = be_30; be_phase = 2
        elif be_phase == 2:
            if in_zone:
                be_in_zone = True
            if be_in_zone and reached_80:
                be_phase = 3
        elif be_phase == 3 and reversed_80:
            current_sl = be_50; be_phase = 4

        # hit_sl dupa tranzitii: verifica current_sl actualizat pe aceeasi bara
        hit_sl = (d == 1 and bar["low"] <= current_sl) or (d == -1 and bar["high"] >= current_sl)

        if hit_sl:
            if be_phase >= 4:
                return make(current_sl, "be_lock2", k)
            elif be_phase >= 2:
                return make(current_sl, "be_lock", k)
            else:
                return make(current_sl, "loss", k)
        if hit_tp:
            return make(p["tp"], "win", k)

    return make(df.iloc[end - 1]["close"], "timeout", end - 1)
