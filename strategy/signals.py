_INDEX_PIP = {
    "US500": 1.0, "US100": 1.0, "US30": 1.0, "US2000": 1.0,
    "GER40": 1.0, "UK100": 1.0, "JPN225": 1.0,
    "FRA40": 1.0, "AUS200": 1.0,
    "XAUUSD": 1.0,   # 1 punct = $1 price move, pip_val=$100/lot
}


def pip_size(symbol):
    if symbol in _INDEX_PIP:
        return _INDEX_PIP[symbol]
    return 0.01 if "JPY" in symbol else 0.0001


def count_optional(row, direction, cfg):
    """Cate criterii optionale sunt indeplinite (RSI, aliniere EMA)."""
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
    return c


def reward_R(n_optional, cfg):
    rl = cfg["reward_ladder"]
    if n_optional >= 2: return rl["rr_if_5_criteria"]
    if n_optional == 1: return rl["rr_if_4_criteria"]
    return rl["rr_if_3_criteria"]
