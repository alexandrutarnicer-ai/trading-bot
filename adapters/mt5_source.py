class Mt5DataSource:
    """
    Adaptor pentru MetaTrader 5 — sursa de date live (implementare viitoare).
    Respecta acelasi contract ca CsvDataSource: load_bars() → DataFrame OHLC brut.
    Indicatorii se calculeaza in strategy/preparation.py, identic cu backtestul.
    """

    def __init__(self, login: int = None, server: str = None, password: str = None):
        self._login    = login
        self._server   = server
        self._password = password

    def load_bars(self, symbol: str, timeframe: str):
        raise NotImplementedError(
            "Mt5DataSource nu este inca implementat. "
            "Foloseste CsvDataSource pentru backtest."
        )
