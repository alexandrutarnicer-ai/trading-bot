import numpy as np
import pandas as pd

from strategy.indicators import ema, rsi, atr
from strategy.structure import mark_swings


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
    return m15.reset_index(drop=True)
