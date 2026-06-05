"""
Verificare aliniere MT5 <-> CSV
---------------------------------
Ce face scriptul:
  1. Se conecteaza la MT5, verifica ca e cont DEMO.
  2. Trage barele recente din MT5 pentru EURUSD, GBPUSD, USDJPY (M15 + M30).
  3. Incarca CSV-urile existente din data/ pentru aceeasi pereche/timeframe.
  4. Gaseste perioada de suprapunere si compara bara cu bara:
       - se potrivesc OHLC?
       - se potrivesc timestamp-urile?
  5. Test definitiv de timezone: compara bara recenta cu ora UTC curenta
     pentru a determina in ce fus orar sunt timestamp-urile MT5.
  6. Verifica corectitudinea filtrelor skip_monday si skip_hours_15_16.

Inainte sa rulezi:
  - MT5 desktop deschis si logat pe contul DEMO.
  - pip install MetaTrader5 pandas

Rulare: python scripts/verifica_aliniere_mt5.py
"""

import sys
import os
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from adapters.mt5_source import Mt5DataSource

DATA_DIR  = os.path.join(os.path.dirname(__file__), "..", "data")
SIMBOLURI = ["EURUSD", "GBPUSD", "USDJPY"]
TIMEFRAMES = ["M15", "M30"]

TOL_PIPS = {
    "EURUSD": 0.00002,
    "GBPUSD": 0.00002,
    "USDJPY": 0.002,
}


def _load_csv(symbol: str, tf: str) -> pd.DataFrame:
    path = os.path.join(DATA_DIR, f"{symbol}_{tf}.csv")
    if not os.path.exists(path):
        return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["time"])
    return df.set_index("time").sort_index()


def _compare(mt5_df: pd.DataFrame, csv_df: pd.DataFrame, symbol: str) -> dict:
    common_idx = mt5_df.index.intersection(csv_df.index)
    if len(common_idx) == 0:
        return {"common": 0}

    tol = TOL_PIPS.get(symbol, 0.00002)
    results = {"common": len(common_idx), "mismatches": []}

    for col in ["open", "high", "low", "close"]:
        diff = (mt5_df.loc[common_idx, col] - csv_df.loc[common_idx, col]).abs()
        bad  = diff[diff > tol]
        if len(bad) > 0:
            results["mismatches"].append({
                "col": col,
                "count": len(bad),
                "max_diff": bad.max(),
                "example_time": bad.index[0],
            })

    return results


def _analyze_timezone(mt5_raw_df: pd.DataFrame, symbol: str) -> None:
    """
    Determina empiric fusul orar al timestamp-urilor returnate de MT5.

    Testul definitiv: bara M15 la pozitia 1 (ultima bara completa) a fost
    deschisa cu cel mult 15 minute inainte de acum (in orice fus orar real).
    Convertim epoch-ul brut cu utcfromtimestamp (= UTC) si comparam cu
    utcnow(). Diferenta spune daca barele sunt UTC sau UTC+2/+3.
    """
    if mt5_raw_df.empty:
        return

    # Bara M15 la pozitia 1 = ultima bara completa (0 e bara curenta, inca in formare)
    rates_last = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 1, 1)
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)

    print(f"\n  ======= ANALIZA TIMEZONE (test definitiv) =======")

    if rates_last is not None and len(rates_last) > 0:
        bar_epoch = rates_last[0]["time"]

        # Conversia standard (la fel ca in adaptorul si in scriptul de descarcare)
        bar_naive  = datetime.utcfromtimestamp(bar_epoch)   # echivalent pd.to_datetime(unit='s')
        bar_pandas = pd.to_datetime(bar_epoch, unit="s")    # cum face Mt5DataSource

        diff_min = (bar_naive - now_utc).total_seconds() / 60

        print(f"    Ora UTC curenta (sistem):              {now_utc.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"    Ultima bara M15 completa (epoch->UTC): {bar_naive.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"    Aceeasi bara via pd.to_datetime:       {bar_pandas}")
        print(f"    Diferenta bar_naive - now_utc:         {diff_min:+.0f} minute")
        print()

        if -30 <= diff_min <= 15:
            tz_label = "UTC"
            tz_note  = (
                "Filtrele 10-18h, skip 15-16h actioneaza pe ora UTC.\n"
                "    Ora 10:00 UTC = 13:00 Romania vara (EEST) / 12:00 iarna (EET).\n"
                "    Filtrele NU sunt in ora Romaniei — sunt in UTC."
            )
        elif 100 <= diff_min <= 140:
            tz_label = "UTC+2 (EET — ora Romaniei iarna)"
            tz_note  = (
                "Filtrele actioneaza pe ora Romaniei in sezon de iarna.\n"
                "    Vara (EEST=UTC+3) exista o deviere de 1h fata de Romania."
            )
        elif 145 <= diff_min <= 200:
            tz_label = "UTC+3 (EEST / ICMarkets server time)"
            tz_note  = (
                "Filtrele actioneaza pe ora Romaniei vara (EEST=UTC+3).\n"
                "    ICMarkets mentine UTC+3 tot anul, deci skip 15-16h\n"
                "    si sesiunea 10-18h sunt corecte in ora Romaniei vara."
            )
        else:
            tz_label = f"NECUNOSCUT (diff={diff_min:.0f}min)"
            tz_note  = (
                "Offset neasteptat. Posibil: piata e inchisa, simbolul\n"
                "    nu e disponibil sau conexiunea e instabila."
            )

        print(f"    CONCLUZIE TIMEZONE: {tz_label}")
        print(f"    {tz_note}")

    else:
        now_utc_str = now_utc.strftime("%H:%M")
        print(f"    [!] Nu am putut trage bara recenta. Ora UTC acum: {now_utc_str}")
        print(f"    Verifica: MT5 e conectat? simbolul are date disponibile?")

    # -- Ora curenta in cele 3 timezone-uri (referinta vizuala) ---------------
    ro_eest = now_utc + timedelta(hours=3)
    ro_eet  = now_utc + timedelta(hours=2)
    print(
        f"\n  Referinta: "
        f"UTC={now_utc.strftime('%H:%M')}  "
        f"RO-EEST(+3)={ro_eest.strftime('%H:%M')}  "
        f"RO-EET(+2)={ro_eet.strftime('%H:%M')}"
    )

    # -- Distributia orelor in ultimele 500 bare ------------------------------
    sample_hours = mt5_raw_df["time"].dt.hour.value_counts().sort_index()
    print(f"\n  Distributia orelor in ultimele {len(mt5_raw_df)} bare M15 (naive):")
    print(f"  (daca e UTC: sesiunea 10-18 in DataFrame = 12-20 ora RO vara)")
    print(f"  (daca e UTC+3: sesiunea 10-18 in DataFrame = sesiunea reala RO)")
    for h, cnt in sample_hours.items():
        bar = "#" * min(cnt // 5, 30)
        print(f"    {h:02d}:xx  {cnt:4d}  {bar}")

    # -- Verificare skip_monday -----------------------------------------------
    weekdays = mt5_raw_df["time"].dt.dayofweek.value_counts().sort_index()
    day_names = {0: "Lun(0-skip)", 1: "Mar(1)", 2: "Mie(2)",
                 3: "Joi(3)", 4: "Vin(4)", 5: "Sam(5)", 6: "Dum(6)"}
    print(f"\n  Bare per zi (weekday=0 e Luni, skip_monday se aplica pe weekday==0):")
    for d, cnt in weekdays.items():
        print(f"    {day_names.get(d, '?'):<14}  {cnt:4d} bare")


def main():
    print("=" * 62)
    print("Verificare aliniere MT5 <-> CSV")
    print("=" * 62)

    src = Mt5DataSource(n_bars=500)

    try:
        acc = src.connect()
    except RuntimeError as e:
        print(f"\nEROARE: {e}")
        sys.exit(1)

    demo_label = "DEMO OK" if acc.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO else f"trade_mode={acc.trade_mode}"
    print(f"\nConectat la MT5:")
    print(f"  Login:   {acc.login}  |  Server: {acc.server}")
    print(f"  Tip:     {demo_label}  |  Valuta: {acc.currency}  |  Balanta: {acc.balance}")

    timezone_done = False

    for symbol in SIMBOLURI:
        print(f"\n{'=' * 62}")
        print(f"  Simbol: {symbol}")

        for tf in TIMEFRAMES:
            print(f"\n  -- {tf} --")

            try:
                mt5_raw = src.load_bars(symbol, tf)
            except RuntimeError as e:
                print(f"    [!] Eroare MT5: {e}")
                continue

            mt5_idx = mt5_raw.set_index("time").sort_index()
            print(
                f"    MT5: {len(mt5_idx)} bare  "
                f"| {mt5_idx.index.min()}  ->  {mt5_idx.index.max()}"
            )

            csv_df = _load_csv(symbol, tf)
            if csv_df.empty:
                print(f"    CSV: lipseste fisierul {symbol}_{tf}.csv")
                continue

            print(
                f"    CSV: {len(csv_df)} bare  "
                f"| {csv_df.index.min()}  ->  {csv_df.index.max()}"
            )

            result = _compare(mt5_idx, csv_df, symbol)
            n_common = result["common"]

            if n_common == 0:
                print("    Suprapunere: ZERO bare comune.")
                print("    Cauza posibila: MT5 returneaza 500 bare recente, CSV acopera alta perioada.")
                print("    Solutie: ruleaza cu n_bars mai mare sau verifica histericul MT5.")
            else:
                print(f"    Bare comune: {n_common}")
                mismatches = result.get("mismatches", [])
                if not mismatches:
                    print("    OHLC: MATCH PERFECT - toate valorile se potrivesc.")
                else:
                    print("    OHLC: DIFERENTE DETECTATE:")
                    for m in mismatches:
                        print(
                            f"      col '{m['col']}': {m['count']} bare, "
                            f"max_diff={m['max_diff']:.6f}, ex: {m['example_time']}"
                        )

        # Analiza timezone o singura data (dupa primul simbol)
        if not timezone_done:
            try:
                first_m15 = src.load_bars(symbol, "M15")
                _analyze_timezone(first_m15, symbol)
                timezone_done = True
            except RuntimeError as e:
                print(f"  [!] Analiza timezone esuat: {e}")

    # -- Concluzie finala pentru filtre ---------------------------------------
    print(f"\n{'=' * 62}")
    print("Concluzie pentru filtrele skip_monday / skip_hours_15-16:")
    print()
    print("  engine/portfolio.py aplica:")
    print("    t.weekday() == 0       -> skip Luni")
    print("    t.hour in skip_hours   -> skip 15 si 16")
    print("    sh <= t.hour < eh      -> sesiunea 10-18")
    print()
    print("  unde 't' = bara.time din DataFrame (naive, fara tzinfo).")
    print()
    print("  Interpretarea CORECTA depinde de timezone-ul confirmat mai sus.")
    print("  Daca e UTC+3 (ICMarkets server) = ora Romaniei vara: filtrele OK.")
    print("  Daca e UTC: filtrele sunt decalate cu 2-3h fata de ora Romaniei.")

    src.disconnect()
    print("\nGata.")


if __name__ == "__main__":
    main()
