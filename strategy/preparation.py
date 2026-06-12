import numpy as np
import pandas as pd

from strategy.indicators import ema, rsi, atr, adx
from strategy.structure import mark_swings


def prepare_symbol_tf(source, symbol: str, cfg: dict,
                      entry_tf: str = "M15", trend_tf: str = "M30") -> pd.DataFrame:
    """Like prepare_symbol but with configurable entry/trend timeframes."""
    entry_df = source.load_bars(symbol, entry_tf)
    trend_df = source.load_bars(symbol, trend_tf)
    return _enrich(entry_df, trend_df, cfg)


def prepare_symbol(source, symbol: str, cfg: dict) -> pd.DataFrame:
    """
    Incarca OHLC brut din `source` si calculeaza toti indicatorii necesari motorului.
    Returneaza un DataFrame M15 imbogatit, gata pentru engine/single sau engine/portfolio.

    Separarea este intentionata: adaptorul (source) livreaza doar bare brute,
    calculul indicatorilor se face o singura data, identic, indiferent de sursa.
    Adaugarea unui nou adaptor (MT5, broker API etc.) nu necesita nicio modificare aici.
    """
    m15 = source.load_bars(symbol, "M15")
    m30 = source.load_bars(symbol, "M30")
    return _enrich(m15, m30, cfg)


def _enrich(m15: pd.DataFrame, m30: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    # Normalizeaza precizia timestamp-urilor (MT5 poate returna <M8[s] sau <M8[us])
    m15["time"] = pd.to_datetime(m15["time"]).astype("datetime64[s]")
    m30["time"] = pd.to_datetime(m30["time"]).astype("datetime64[s]")

    # trend pe M30: EMA200, directie 1/-1/0
    m30["ema_trend"] = ema(m30["close"], cfg["trend_filter"]["ema_trend_period"])
    m30["trend"] = np.where(m30["close"] > m30["ema_trend"], 1,
                    np.where(m30["close"] < m30["ema_trend"], -1, 0))

    # indicatori pe M15
    per = cfg["optional_criteria"]["ema_alignment"]["periods"]   # [8, 20, 50]
    m15["ema_fast"] = ema(m15["close"], per[0])
    m15["ema_mid"]  = ema(m15["close"], per[1])
    m15["ema_slow"] = ema(m15["close"], per[2])
    m15["rsi"]      = rsi(m15["close"], cfg["optional_criteria"]["rsi"]["period"])
    m15["atr"]      = atr(m15, 14)
    m15 = mark_swings(m15, cfg["structure"]["swing_lookback_N"])

    # aliniaza trendul M30 la fiecare bara M15 (ultimul M30 inchis)
    m15 = pd.merge_asof(m15.sort_values("time"),
                        m30[["time", "trend"]].sort_values("time"),
                        on="time", direction="backward")

    # === Filtre de regim (calcul pe D1 si W1, fara look-ahead) ===
    # Toate semnalele sunt avansate cu 1 bara (zi/saptamana) pentru a evita look-ahead.
    # La bara M15 din ziua D, folosim valorile inchise ale zilei D-1.

    # D1 OHLC din M30 resampleat
    d1 = (m30.set_index("time")
             .resample("1D")
             .agg({"open": "first", "high": "max", "low": "min", "close": "last"})
             .dropna()
             .reset_index())
    d1["ema200_d1"]   = ema(d1["close"], 200)
    d1["daily_trend"] = np.where(d1["close"] > d1["ema200_d1"], 1, -1)  # pret vs EMA200
    d1["f3_slope"]    = np.where(d1["ema200_d1"].diff() > 0, 1, 0)      # EMA200 in crestere
    d1["adx_d1"]      = adx(d1, 14)
    d1["f2_adx"]      = np.where(d1["adx_d1"] > 25, 1, 0)               # ADX standard 25
    d1_sig = d1.copy()
    d1_sig["time"] = (d1_sig["time"] + pd.Timedelta(days=1)).astype("datetime64[s]")
    m15 = pd.merge_asof(m15.sort_values("time"),
                        d1_sig[["time", "daily_trend", "f2_adx", "f3_slope"]].sort_values("time"),
                        on="time", direction="backward")

    # W1 din M30 resampleat (saptamanal, sfarsit de saptamana = duminica implicit)
    w1 = (m30.set_index("time")
             .resample("W")["close"]
             .last()
             .dropna()
             .reset_index()
             .rename(columns={"close": "w1_close"}))
    w1["ema50_w1"]  = ema(w1["w1_close"], 50)
    w1["f1_weekly"] = np.where(w1["w1_close"] > w1["ema50_w1"], 1, 0)   # EMA50 saptamanal
    w1["time"]      = (w1["time"] + pd.Timedelta(weeks=1)).astype("datetime64[s]")
    m15 = pd.merge_asof(m15.sort_values("time"),
                        w1[["time", "f1_weekly"]].sort_values("time"),
                        on="time", direction="backward")

    # F4: F1 SI F3 combinate
    m15["f4_f1f3"] = ((m15["f1_weekly"] == 1) & (m15["f3_slope"] == 1)).astype(int)

    for col in ["daily_trend", "f1_weekly", "f2_adx", "f3_slope", "f4_f1f3"]:
        m15[col] = m15[col].fillna(0).astype(int)

    return m15.reset_index(drop=True)
