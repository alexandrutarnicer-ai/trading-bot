_INDEX_PIP = {
    "US500": 1.0, "US100": 1.0, "US30": 1.0, "US2000": 1.0,
    "GER40": 1.0, "UK100": 1.0, "JPN225": 1.0,
    "FRA40": 1.0, "AUS200": 1.0,
    "XAUUSD": 1.0,   # 1 punct = $1 price move, pip_val=$100/lot
    "BTCUSD": 0.01, "ETHUSD": 0.01,  # tick_size real (nu 1.0 ca indicii)
}


def pip_size(symbol):
    if symbol in _INDEX_PIP:
        return _INDEX_PIP[symbol]
    return 0.01 if "JPY" in symbol else 0.0001


def count_optional(row, direction, cfg):
    """Cate criterii optionale sunt indeplinite (RSI, aliniere EMA, corp lumanare)."""
    c = 0
    o = cfg["optional_criteria"]

    if o["rsi"]["enabled"]:
        r = row["rsi"]
        if direction == 1 and o["rsi"]["buy_min"] <= r <= o["rsi"]["buy_max"]:
            c += 1
        elif direction == -1 and o["rsi"]["sell_min"] <= r <= o["rsi"]["sell_max"]:
            c += 1

    if o["ema_alignment"]["enabled"]:
        if direction == 1 and row["ema_fast"] > row["ema_mid"] > row["ema_slow"]:
            c += 1
        elif direction == -1 and row["ema_fast"] < row["ema_mid"] < row["ema_slow"]:
            c += 1

    # Criteriu 3: corp lumânare — bara de intrare are body > min_atr_ratio * ATR
    # in directia trade-ului. Dezactivat implicit, nu afecteaza baselines.
    bs = o.get("body_strength", {})
    if bs.get("enabled", False):
        min_ratio = bs.get("min_atr_ratio", 0.15)
        if direction == 1:
            body = row["close"] - row["open"]
        else:
            body = row["open"] - row["close"]
        if body > min_ratio * row["atr"]:
            c += 1

    return c


def reward_R(n_optional, cfg):
    rl = cfg["reward_ladder"]
    # Praguri configurabile (default: 1/2/3) — backward-compatible cu configuri vechi.
    t_mid = rl.get("threshold_mid", 1)
    t_top = rl.get("threshold_top", 2)
    t_max = rl.get("threshold_max", 3)
    if "rr_if_6_criteria" in rl and n_optional >= t_max:
        return rl["rr_if_6_criteria"]
    if n_optional >= t_top:
        return rl["rr_if_5_criteria"]
    if n_optional >= t_mid:
        return rl["rr_if_4_criteria"]
    return rl["rr_if_3_criteria"]
