"""
Cache pentru citirea CSV-urilor de semnale/outcomes, invalidat automat prin
(mtime, size). Fisierele se schimba doar cand botul scrie (o data la ~15 min
sau la evenimente de trade), deci cache-ul pe (mtime_ns, size) e EXACT — nu
exista staleness. Elimina re-citirea + re-parsarea a ~40 CSV-uri la fiecare
poll `GET /sessions` (la 15s).

Nu copiaza DataFrame-ul returnat: apelantii din api/ fac fie boolean-indexing
(care produce un frame nou), fie `.copy()` explicit inainte de orice mutatie.
Frame-ul cache-uit nu e mutat niciodata in loc.
"""

import os
import threading

import pandas as pd

_LOCK = threading.Lock()
_cache: dict[str, tuple] = {}   # path -> (mtime_ns, size, DataFrame)


def read_csv_cached(path: str, **read_kwargs) -> pd.DataFrame:
    """Citeste un CSV cu cache pe (mtime, size). Frame gol daca lipseste/eroare."""
    try:
        st = os.stat(path)
    except OSError:
        return pd.DataFrame()
    mtime_ns, size = st.st_mtime_ns, st.st_size

    with _LOCK:
        hit = _cache.get(path)
        if hit is not None and hit[0] == mtime_ns and hit[1] == size:
            return hit[2]

    # Citirea (disk + parse) se face in afara lock-ului.
    try:
        df = pd.read_csv(path, **read_kwargs)
    except Exception:
        df = pd.DataFrame()

    with _LOCK:
        _cache[path] = (mtime_ns, size, df)
    return df
