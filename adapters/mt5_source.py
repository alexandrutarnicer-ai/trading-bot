"""
Mt5DataSource — adaptor live pentru MetaTrader 5.

Respecta contractul DataSource: load_bars() -> DataFrame OHLC brut
cu coloanele: time, open, high, low, close, tick_volume, spread, real_volume

Conditie obligatorie: contul trebuie sa fie DEMO. La orice alt tip
de cont adaptorul refuza sa functioneze.

Timezone: MT5 returneaza timestamps in ora serverului broker (e.g., UTC+2
iarna sau UTC+3 vara pentru ICMarketsEU). Adaptorul detecteaza automat
offset-ul serverului si converteste explicit la fusul orar configurat
(implicit Europe/Bucharest, configurabil via data/timezone_config.json).
Rezultat: coloana 'time' e intotdeauna in ora configurata (naive, fara tzinfo),
indiferent de sezon sau schimbarile DST ale serverului.

Utilizare:
    with Mt5DataSource() as src:
        m15 = src.load_bars("EURUSD", "M15")
        m30 = src.load_bars("EURUSD", "M30")
"""

from datetime import datetime, timezone, timedelta

import MetaTrader5 as mt5
import pandas as pd

from tz_helper import get_configured_tz_name

_TF_MAP: dict[str, int] = {
    "M1":  mt5.TIMEFRAME_M1,
    "M5":  mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30,
    "H1":  mt5.TIMEFRAME_H1,
    "H4":  mt5.TIMEFRAME_H4,
    "D1":  mt5.TIMEFRAME_D1,
}

_COLUMNS = ["time", "open", "high", "low", "close", "tick_volume", "spread", "real_volume"]


class Mt5DataSource:
    """
    Sursa de date live din MT5 (cont DEMO obligatoriu by default).

    n_bars: cate bare se incarca la fiecare apel load_bars().
            2000 bare M15 = ~500 ore = ~83 zile de tranzactionare,
            suficient pentru warm-up EMA200 pe M30.

    component: identitatea consumatorului pentru deblocarea LIVE ("bot" /
            "ai_engine"). None (default) = strict DEMO, indiferent de flag-uri —
            scripturile de research si orice cod care nu se declara explicit
            raman blocate pe conturi reale. Cu component setat, conectarea la un
            cont REAL e permisa DOAR daca utilizatorul a deblocat explicit acea
            componenta in data/live_trading.json (UI: Profil → Trading LIVE);
            la prima conectare live se trimite Telegram + log (live_guard).
    """

    def __init__(self, n_bars: int = 2000, component: str | None = None):
        self._n_bars = n_bars
        self.component = component
        self._connected = False
        # Offset-ul serverului fata de UTC, detectat la primul load_bars().
        # None = nu a fost detectat inca.
        self._server_offset_h: int | None = None

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
            # Cont REAL: permis DOAR daca componenta e declarata si deblocata
            # explicit de utilizator pe aceasta masina (data/live_trading.json).
            allowed = False
            if self.component:
                try:
                    from live_guard import live_allowed, notify_live_connection
                    allowed = live_allowed(self.component)
                except Exception:
                    allowed = False   # fail-safe: orice eroare = blocat
            if not allowed:
                mt5.shutdown()
                raise RuntimeError(
                    f"BLOCAT — contul {acc.login} pe serverul '{acc.server}' "
                    f"NU este cont DEMO (trade_mode={acc.trade_mode}). "
                    "Pentru tranzactionare pe cont REAL, deblocheaza explicit "
                    "componenta din UI (Profil → Trading LIVE) sau in "
                    "data/live_trading.json. Scripturile de research raman "
                    "DEMO-only prin design."
                )
            notify_live_connection(self.component, acc.login, acc.server)

        self._connected = True
        return acc

    def disconnect(self) -> None:
        if self._connected:
            mt5.shutdown()
            self._connected = False
            # Reset offset: orice reconectare re-detecteaza fusul serverului.
            # Asta acopera cazul (rar) in care botul ruleaza prin o schimbare DST.
            self._server_offset_h = None

    def __enter__(self) -> "Mt5DataSource":
        self.connect()
        return self

    def __exit__(self, *_) -> None:
        self.disconnect()

    # ------------------------------------------------------------------
    # Detecție timezone server
    # ------------------------------------------------------------------

    def _detect_server_offset_h(self, symbol: str) -> int:
        """
        Detecteaza programatic offset-ul fusului orar al serverului MT5
        fata de UTC, fara a face nicio presupunere despre broker.

        Metoda: bara M15 la pozitia 0 (in formare) a fost deschisa recent
        (0–15 min). Timestamp-ul ei (interpretat ca si cum ar fi UTC) minus
        ora UTC reala a sistemului da offset-ul serverului.

        Returneaza un intreg in ore (tipic 2 sau 3 pentru brokeri EU).
        Returneaza 0 daca piata e inchisa sau detectia nu e concludenta —
        in acel caz timestamps raman in server time (passthrough fara
        conversie, acceptabil deoarece server time ≈ ora RO in practica).
        """
        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)

        # pos=1 = ultima bara INCHISA (nu bara in formare de la pos=0).
        # O bara inchisa are open_time fix si deterministic: a fost deschisa
        # cu exact 1–2 perioade in urma, ceea ce da un diff stabil fata de now_utc.
        # Toleranta ±30 min este mai larga decat orice incertitudine reala:
        #   - bara M15 inchisa: deschisa acum 15–30 min → diff = offset ± 30 min ✓
        #   - bara M1 inchisa:  deschisa acum  1–2 min → diff = offset ±  2 min ✓
        for tf_candidate in (mt5.TIMEFRAME_M15, mt5.TIMEFRAME_M1):
            rates = mt5.copy_rates_from_pos(symbol, tf_candidate, 1, 1)
            if rates is None or len(rates) == 0:
                continue

            bar_naive = datetime.fromtimestamp(rates[0]["time"], tz=timezone.utc).replace(tzinfo=None)
            diff_s = (bar_naive - now_utc).total_seconds()

            # Candidati in ordinea probabilitatii pentru brokeri forex EU.
            # 0 acopera cazul (rar) in care timestamps sunt UTC curat.
            for candidate in (3, 2, 1, 0):
                if abs(diff_s - candidate * 3600) < 1800:  # ±30 min
                    return candidate

        # Bara prea veche (piata inchisa de mai mult de 3.5 ore: weekend sau
        # sesiune nocturna extinsa). Nu convertim — server time ≈ ora RO oricum.
        # Offsetul va fi re-detectat la urmatorul apel load_bars() din sesiune.
        return 0

    def server_offset_h(self, symbol: str = "EURUSD") -> int:
        """Returneaza offset-ul serverului (il detecteaza daca nu e inca cunoscut)."""
        if not self._connected:
            self.connect()
        if self._server_offset_h is None:
            self._server_offset_h = self._detect_server_offset_h(symbol)
        return self._server_offset_h

    # ------------------------------------------------------------------
    # DataSource contract
    # ------------------------------------------------------------------

    def load_bars(self, symbol: str, timeframe: str) -> pd.DataFrame:
        """
        Incarca ultimele self._n_bars bare OHLC din MT5 pentru symbol/timeframe.

        Returneaza DataFrame cu coloanele: time, open, high, low, close,
        tick_volume, spread, real_volume.

        Coloana 'time' este datetime64 timezone-naive in ora Romaniei
        (Europe/Bucharest), conversia fiind facuta explicit via zoneinfo.
        Asta asigura ca filtrele skip_monday, skip_hours_15-16 si sesiunea
        10-18 opereaza intotdeauna pe ora reala a Romaniei, indiferent de
        sezon sau schimbarile DST ale serverului broker.
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
        # Pasul 1: epoch MT5 → server time (naive, fara tzinfo)
        df["time"] = pd.to_datetime(df["time"], unit="s")

        # Pasul 2: detecteaza offset-ul serverului o singura data per sesiune
        if self._server_offset_h is None:
            self._server_offset_h = self._detect_server_offset_h(symbol)

        # Pasul 3: server time → UTC → fusul orar configurat (naive)
        # Daca offset=0 (nedetectat sau server real UTC), sarim conversia.
        if self._server_offset_h != 0:
            df["time"] = (
                (df["time"] - pd.Timedelta(hours=self._server_offset_h))
                .dt.tz_localize("UTC")
                .dt.tz_convert(get_configured_tz_name())
                .dt.tz_localize(None)
            )

        return df[_COLUMNS].copy()

    # ------------------------------------------------------------------
    # Info
    # ------------------------------------------------------------------

    def account_info(self) -> mt5.AccountInfo:
        if not self._connected:
            self.connect()
        return mt5.account_info()
