"""
Mt5DataSource — adaptor live pentru MetaTrader 5.

Respecta contractul DataSource: load_bars() -> DataFrame OHLC brut
cu coloanele: time, open, high, low, close, tick_volume, spread, real_volume

Conditie obligatorie: contul trebuie sa fie DEMO. La orice alt tip
de cont adaptorul refuza sa functioneze.

Utilizare:
    with Mt5DataSource() as src:
        m15 = src.load_bars("EURUSD", "M15")
        m30 = src.load_bars("EURUSD", "M30")
"""

import MetaTrader5 as mt5
import pandas as pd

_TF_MAP: dict[str, int] = {
    "M1":  mt5.TIMEFRAME_M1,
    "M5":  mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30,
    "H1":  mt5.TIMEFRAME_H1,
    "H4":  mt5.TIMEFRAME_H4,
    "D1":  mt5.TIMEFRAME_D1,
}

# Coloanele returnate de MT5 copy_rates_* pe care le pastram, in ordinea CSV
_COLUMNS = ["time", "open", "high", "low", "close", "tick_volume", "spread", "real_volume"]


class Mt5DataSource:
    """
    Sursa de date live din MT5 (cont DEMO obligatoriu).

    n_bars: cate bare se incarca la fiecare apel load_bars().
            2000 bare M15 = ~500 ore = ~83 zile de tranzactionare,
            suficient pentru warm-up EMA200 pe M30.
    """

    def __init__(self, n_bars: int = 2000):
        self._n_bars = n_bars
        self._connected = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> mt5.AccountInfo:
        """
        Initializeaza conexiunea la terminalul MT5 si verifica ca e cont DEMO.
        Terminalul MT5 trebuie sa fie deschis si logat inainte de apel.
        """
        if self._connected:
            return mt5.account_info()

        if not mt5.initialize():
            raise RuntimeError(f"mt5.initialize() a esuat: {mt5.last_error()}")

        acc = mt5.account_info()
        if acc is None:
            mt5.shutdown()
            raise RuntimeError("Nu am putut citi info cont MT5 dupa initialize().")

        if acc.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO:
            mt5.shutdown()
            raise RuntimeError(
                f"BLOCAT — contul {acc.login} pe serverul '{acc.server}' "
                f"NU este cont DEMO (trade_mode={acc.trade_mode}). "
                "Conecteaza-te la un cont demo inainte de a folosi Mt5DataSource."
            )

        self._connected = True
        return acc

    def disconnect(self) -> None:
        if self._connected:
            mt5.shutdown()
            self._connected = False

    def __enter__(self) -> "Mt5DataSource":
        self.connect()
        return self

    def __exit__(self, *_) -> None:
        self.disconnect()

    # ------------------------------------------------------------------
    # DataSource contract
    # ------------------------------------------------------------------

    def load_bars(self, symbol: str, timeframe: str) -> pd.DataFrame:
        """
        Incarca ultimele self._n_bars bare OHLC din MT5 pentru symbol/timeframe.
        Returneaza DataFrame cu coloanele: time, open, high, low, close,
        tick_volume, spread, real_volume — identic cu formatul CSV.

        time este datetime64 timezone-naive, in ora serverului broker
        (ICMarkets: UTC+3 tot anul = identic cu ora Romaniei vara/EEST).
        """
        if not self._connected:
            self.connect()

        tf = _TF_MAP.get(timeframe)
        if tf is None:
            raise ValueError(
                f"Timeframe necunoscut: '{timeframe}'. "
                f"Valori acceptate: {sorted(_TF_MAP)}"
            )

        if not mt5.symbol_select(symbol, True):
            raise RuntimeError(
                f"Simbolul '{symbol}' nu este disponibil in MT5: {mt5.last_error()}"
            )

        rates = mt5.copy_rates_from_pos(symbol, tf, 0, self._n_bars)
        if rates is None or len(rates) == 0:
            raise RuntimeError(
                f"Nu am primit bare pentru {symbol} {timeframe}: {mt5.last_error()}"
            )

        df = pd.DataFrame(rates)
        # MT5 returneaza timestamps ca Unix epoch (secunde UTC).
        # Conversia la datetime naive le lasa fara tzinfo, ceea ce
        # corespunde cu formatul CSV existent.
        df["time"] = pd.to_datetime(df["time"], unit="s")
        return df[_COLUMNS].copy()

    # ------------------------------------------------------------------
    # Info (util pentru debugging / verificare)
    # ------------------------------------------------------------------

    def account_info(self) -> mt5.AccountInfo:
        if not self._connected:
            self.connect()
        return mt5.account_info()
