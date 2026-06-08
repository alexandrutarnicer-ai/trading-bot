import numpy as np
import pandas as pd


def ema(s, period):
    return s.ewm(span=period, adjust=False).mean()


def rsi(s, period=14):
    delta = s.diff()
    up = delta.clip(lower=0).ewm(alpha=1/period, adjust=False).mean()
    down = (-delta.clip(upper=0)).ewm(alpha=1/period, adjust=False).mean()
    rs = up / down.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def atr(df, period=14):
    h, l, c = df["high"], df["low"], df["close"]
    prev_c = c.shift(1)
    tr = pd.concat([(h - l), (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, adjust=False).mean()


def adx(df, period=14):
    """Wilder ADX pe DataFrame cu coloane high, low, close."""
    h, l, c = df["high"], df["low"], df["close"]
    pc, ph, pl = c.shift(1), h.shift(1), l.shift(1)
    tr = pd.concat([(h - l), (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    up, down = h - ph, pl - l
    dm_p = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=df.index)
    dm_m = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=df.index)
    alpha = 1.0 / period
    tr_s  = tr.ewm(alpha=alpha, adjust=False).mean()
    dmp_s = dm_p.ewm(alpha=alpha, adjust=False).mean()
    dmm_s = dm_m.ewm(alpha=alpha, adjust=False).mean()
    di_p  = 100 * dmp_s / tr_s.replace(0, np.nan)
    di_m  = 100 * dmm_s / tr_s.replace(0, np.nan)
    dx    = 100 * (di_p - di_m).abs() / (di_p + di_m).replace(0, np.nan)
    return dx.ewm(alpha=alpha, adjust=False).mean()
