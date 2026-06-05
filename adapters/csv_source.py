import os
import pandas as pd


class CsvDataSource:
    """Incarca bare OHLC brute din fisiere CSV locale (backtest)."""

    def __init__(self, data_dir: str):
        self._data_dir = data_dir

    def load_bars(self, symbol: str, timeframe: str) -> pd.DataFrame:
        path = os.path.join(self._data_dir, f"{symbol}_{timeframe}.csv")
        return pd.read_csv(path, parse_dates=["time"])
