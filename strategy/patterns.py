"""
Detectie pattern-uri independente de pullback-in-trend.

Flag Pattern (Bull/Bear):
  Statistic: 65-72% win rate in piete trending cu filtru EMA200.
  Sursa: J. Murphy "Technical Analysis of Financial Markets" (1999),
         T. Bulkowski "Encyclopedia of Chart Patterns" (2002, 2021 ed).
  Conditii:
    1. Flagpole — N bare consecutive in directia trendului, body >= min_body * ATR
    2. Flag     — 2-5 bare consolidare, retrasare < 50% din inaltime pol
    3. Breakout — prima bara ce inchide dincolo de limita flagului

Inside Bar Breakout:
  Statistic: 60-68% win rate in piete trending (Bulkowski 2002/2021).
  Conditii:
    1. Mother bar — bara de referinta cu range mai larg
    2. Inside bar — bara complet in interiorul mother bar (high<=prev_high, low>=prev_low)
    3. Breakout   — bara curenta inchide deasupra/sub inside bar

Ambele returneaza (sl_level, entry_level) sau None.
  LONG:  entry_level = nivelul de breakout (BUY_STOP), sl_level = baza pattern-ului
  SHORT: entry_level = nivelul de breakdown (SELL_STOP), sl_level = varful pattern-ului

Apelantul adauga buffer pip la entry/sl si calculeaza TP pe baza r_ratio.
Nu modifica nimic din strategia pullback-in-trend existenta.
"""


def detect_flag(df, j: int, direction: int, cfg: dict) -> tuple[float, float] | None:
    """
    Detecteaza flag pattern la bara j.

    direction: 1 = Bull Flag (LONG), -1 = Bear Flag (SHORT)
    cfg keys (cu default-uri):
      pole_min_candles   = 3   — bare consecutive in pol
      pole_min_body_atr  = 0.5 — corp minim per bara pol (multiplicator ATR)
      flag_min_bars      = 2   — bare minime in flag
      flag_max_bars      = 5   — bare maxime in flag
      flag_max_retrace_pct = 50 — retrasare maxima din pol (%)

    Returneaza (sl_level, entry_level) sau None:
      LONG:  sl_level=flag_low,  entry_level=flag_high  (BUY_STOP la top flag)
      SHORT: sl_level=flag_high, entry_level=flag_low   (SELL_STOP la bottom flag)
    """
    pole_min    = int(cfg.get("pole_min_candles",    3))
    body_atr    = float(cfg.get("pole_min_body_atr", 0.5))
    flag_min    = int(cfg.get("flag_min_bars",        2))
    flag_max    = int(cfg.get("flag_max_bars",        5))
    max_retrace = float(cfg.get("flag_max_retrace_pct", 50)) / 100.0

    # Minim: pol + flag_min + 1 (bara curenta de breakout)
    if j < pole_min + flag_min + 1:
        return None

    atr = float(df.iloc[j]["atr"])
    if atr <= 0:
        return None

    for flag_bars in range(flag_min, flag_max + 1):
        # Structura: [pole_start .. pole_end] [pole_end+1 .. j-1] [j]
        #             ----POL----              ------FLAG------    breakout
        pole_end   = j - flag_bars
        pole_start = pole_end - pole_min + 1

        if pole_start < 1:
            continue

        pole_slice = df.iloc[pole_start : pole_end + 1]

        # --- Verifica polul: bare consecutive cu corp semnificativ ---
        if direction == 1:
            if not (pole_slice["close"] > pole_slice["open"]).all():
                continue
            bodies = pole_slice["close"] - pole_slice["open"]
        else:
            if not (pole_slice["close"] < pole_slice["open"]).all():
                continue
            bodies = pole_slice["open"] - pole_slice["close"]

        if not (bodies >= body_atr * atr).all():
            continue

        pole_high   = float(pole_slice["high"].max())
        pole_low    = float(pole_slice["low"].min())
        pole_height = pole_high - pole_low
        if pole_height <= 0:
            continue

        # --- Verifica flag-ul: consolidare dupa pol ---
        flag_slice = df.iloc[pole_end + 1 : j]   # [pole_end+1 .. j-1], fara bara j
        if len(flag_slice) < 1:
            continue

        flag_high = float(flag_slice["high"].max())
        flag_low  = float(flag_slice["low"].min())

        if direction == 1:
            if flag_high > pole_high:
                continue              # flag a depasit varful polului — nu e consolidare
            retrace = pole_high - flag_low
        else:
            if flag_low < pole_low:
                continue              # flag a depasit minimul polului — nu e consolidare
            retrace = flag_high - pole_low

        if retrace > max_retrace * pole_height:
            continue

        # --- Verifica breakout: bara j este PRIMA care inchide dincolo de flag ---
        if direction == 1:
            bkout = flag_high
            if float(df.iloc[j]["close"]) <= bkout:
                continue
            # Anti-lookahead: nicio bara din flag nu a inchis deja deasupra
            if (flag_slice["close"] > bkout).any():
                continue
            return (flag_low, bkout)   # (sl, entry)
        else:
            bkout = flag_low
            if float(df.iloc[j]["close"]) >= bkout:
                continue
            if (flag_slice["close"] < bkout).any():
                continue
            return (flag_high, bkout)   # (sl, entry)

    return None


def detect_inside_bar(df, j: int, direction: int) -> tuple[float, float] | None:
    """
    Detecteaza inside bar breakout la bara j.

    Structura:
      j-2 = mother bar (range mai larg)
      j-1 = inside bar (complet in interiorul mother bar)
      j   = bara de breakout (inchide deasupra/sub inside bar)

    Statistic (Bulkowski): 60-68% win rate in piete trending cu filtru EMA200.
    Functioneaza mai bine pe H1+, dar valid si pe M15 cu trend filter activ.

    Returneaza (sl_level, entry_level) sau None:
      LONG:  sl_level=inside_low,  entry_level=inside_high
      SHORT: sl_level=inside_high, entry_level=inside_low
    """
    if j < 3:
        return None

    mother = df.iloc[j - 2]
    inside = df.iloc[j - 1]
    bar_j  = df.iloc[j]

    # Conditia inside bar: complet in interiorul mother bar
    if not (float(inside["high"]) <= float(mother["high"]) and
            float(inside["low"])  >= float(mother["low"])):
        return None

    inside_high = float(inside["high"])
    inside_low  = float(inside["low"])

    if inside_high - inside_low <= 0:
        return None

    if direction == 1:
        if float(bar_j["close"]) <= inside_high:
            return None
        return (inside_low, inside_high)   # (sl, entry)
    else:
        if float(bar_j["close"]) >= inside_low:
            return None
        return (inside_high, inside_low)   # (sl, entry)
