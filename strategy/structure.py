import numpy as np


def mark_swings(df, N):
    """Adauga coloane swing_high / swing_low (bool), confirmate dupa N bare."""
    high, low = df["high"].values, df["low"].values
    n = len(df)
    sh = np.zeros(n, dtype=bool)
    sl = np.zeros(n, dtype=bool)
    for i in range(N, n - N):
        window_h = high[i-N:i+N+1]
        window_l = low[i-N:i+N+1]
        if high[i] == window_h.max() and (window_h.argmax() == N):
            sh[i] = True
        if low[i] == window_l.min() and (window_l.argmin() == N):
            sl[i] = True
    df["swing_high"] = sh
    df["swing_low"] = sl
    return df


def detect_setup(df, j, direction, window=8, depth_range=None):
    """
    Setup STRICT de pullback in trend, la bara de confirmare j.
    Bullish: al 2-lea HH crescator -> pullback la un HL nou (ultima structura,
    recenta) -> bara j este PRIMA care inchide peste maximul barei de pullback.
    Bearish: oglinda. Conditii suplimentare fata de versiunea veche:
      - pullback-ul trebuie sa fie ultima structura formata (dupa ultimul HH/LL)
      - recent: la cel mult `window` bare in urma fata de j
      - "prima inchidere" peste/sub nivel (nu re-declanseaza pe fiecare bara)

    Returneaza (extremul_pullback, adancime) sau None.
    """
    a = max(0, j - 150)
    look = df.iloc[a:j]
    sh = look.index[look["swing_high"]].tolist()   # pozitii swing high
    sl = look.index[look["swing_low"]].tolist()     # pozitii swing low
    if len(sh) < 2 or len(sl) < 2:
        return None
    hi = df["high"]; lo = df["low"]; cl = df["close"]

    if direction == 1:
        pl = sl[-1]                       # pullback low = ultimul swing low
        if pl <= sh[-1]:                  # trebuie sa fie DUPA ultimul HH (structura proaspata)
            return None
        if j - pl > window:               # trebuie sa fie recent
            return None
        if not (hi.iloc[sh[-1]] > hi.iloc[sh[-2]]):   # al 2-lea HH crescator
            return None
        if not (lo.iloc[pl] > lo.iloc[sl[-2]]):       # HL: ramane peste low-ul anterior
            return None
        lvl = hi.iloc[pl]                 # maximul barei de pullback
        if cl.iloc[j] > lvl and cl.iloc[j-1] <= lvl:  # PRIMA inchidere peste nivel
            depth = hi.iloc[sh[-1]] - lo.iloc[pl]     # adancime pullback (HH - PL)
            return (lo.iloc[pl], depth)   # extremul pullback (pentru SL) si adancimea
    else:
        ph = sh[-1]                       # pullback high = ultimul swing high
        if ph <= sl[-1]:
            return None
        if j - ph > window:
            return None
        if not (lo.iloc[sl[-1]] < lo.iloc[sl[-2]]):   # al 2-lea LL descrescator
            return None
        if not (hi.iloc[ph] < hi.iloc[sh[-2]]):       # LH: ramane sub high-ul anterior
            return None
        lvl = lo.iloc[ph]
        if cl.iloc[j] < lvl and cl.iloc[j-1] >= lvl:  # PRIMA inchidere sub nivel
            depth = hi.iloc[ph] - lo.iloc[sl[-1]]     # adancime pullback (PH - LL)
            return (hi.iloc[ph], depth)   # extremul pullback (pentru SL) si adancimea
    return None
