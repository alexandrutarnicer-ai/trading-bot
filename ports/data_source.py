from typing import Protocol
import pandas as pd


class DataSource(Protocol):
    """
    Contract minimal pentru orice sursa de date OHLC.
    Implementarile (CSV, MT5, altele) nu trebuie sa mosteneasca explicit —
    duck-typing structural (typing.Protocol) e suficient.

    Contractul: returneaza un DataFrame cu coloanele
        time (datetime64), open, high, low, close
    fara indicatori calculati — acestia sunt responsabilitatea strategy/.
    """

    def load_bars(self, symbol: str, timeframe: str) -> pd.DataFrame:
        """Incarca bare OHLC brute pentru perechea si timeframe-ul dat."""
        ...
