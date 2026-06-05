def simulate_trade(df, j, p, spread, pip, pip_val, comm, symbol):
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

    end = min(j + 400, len(df))
    for k in range(j, end):
        bar = df.iloc[k]
        hit_sl = (d == 1 and bar["low"] <= p["sl"]) or (d == -1 and bar["high"] >= p["sl"])
        hit_tp = (d == 1 and bar["high"] >= p["tp"]) or (d == -1 and bar["low"] <= p["tp"])
        if hit_sl:               # conservator: daca ambele in aceeasi bara, SL primul
            return make(p["sl"], "loss", k)
        if hit_tp:
            return make(p["tp"], "win", k)
    # nu a atins nici SL nici TP in fereastra -> inchis la ultimul close
    return make(df.iloc[end - 1]["close"], "timeout", end - 1)
