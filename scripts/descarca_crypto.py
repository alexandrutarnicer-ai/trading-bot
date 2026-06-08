"""
Descarca date crypto din MT5 + afiseaza specificatii reale per pereche.
=======================================================================
Pasul 1 din testul crypto: verifica specs si salveaza datele.

Outputuri:
  - data/BTCUSD_M15.csv, data/BTCUSD_M30.csv ... (una per pereche per TF)
  - data/crypto_specs.json                       (specs pentru backtest)

Rulare (din folderul trading-bot):  python scripts/descarca_crypto.py
"""

import os
import json
from datetime import datetime
import MetaTrader5 as mt5
import pandas as pd

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

SIMBOLURI = [
    "BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "ADAUSD",
    "DOGEUSD", "LTCUSD", "BNBUSD", "AVAXUSD", "LINKUSD",
]

TIMEFRAMES = {
    "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30,
}

# Cerere agresiva de bare — vrem maxim istoric (inclusiv 2021-2022 bear)
N_BARE_MAX = 200_000

if not mt5.initialize():
    print("EROARE la initialize():", mt5.last_error())
    quit()

print("=== SPECIFICATII CRYPTO REALE DIN MT5 ===\n")
print(f"  {'Simbol':<10} {'ctrct_sz':>9} {'tick_sz':>9} {'tick_val':>10} "
      f"{'pip_val':>10} {'spread$':>9} {'swap_L':>9} {'swap_S':>9} {'sw_mode':>8}")
print("  " + "-" * 95)

specs = {}

for sym in SIMBOLURI:
    if not mt5.symbol_select(sym, True):
        print(f"  {sym:<10}  *** NU EXISTA LA ACEST BROKER — simbolul lipseste ***")
        continue

    info = mt5.symbol_info(sym)
    if info is None:
        print(f"  {sym:<10}  *** symbol_info() None — sare peste ***")
        continue

    cs     = info.trade_contract_size   # unitati per lot (ex: 1 BTC, 1000 XRP)
    ts     = info.trade_tick_size       # increment minim de pret
    tv     = info.trade_tick_value      # USD per tick per lot (in account currency)
    sw_mode = info.swap_mode            # modul de calcul swap (0=pips, 1=base, 3=margin)
    sw_l   = info.swap_long             # raw din MT5 (negativ = platesti)
    sw_s   = info.swap_short
    sp_ticks = info.spread              # spread in ticks (integer)
    sp_price = sp_ticks * ts            # spread in unitati de pret
    pip_val_display = tv / ts if ts > 0 else 0.0

    print(f"  {sym:<10} {cs:>9.2f} {ts:>9.6f} {tv:>10.6f} "
          f"${pip_val_display:>9.4f} {sp_price:>9.4f} {sw_l:>9.4f} {sw_s:>9.4f} {sw_mode:>8}")

    specs[sym] = {
        "contract_size":   cs,
        "tick_size":       ts,
        "tick_value_usd":  tv,
        "pip_val":         pip_val_display,   # tv/ts — pentru afisare; in backtest: pip=ts, pip_val=tv
        "spread_price":    round(sp_price, 8),
        "spread_ticks":    sp_ticks,
        "swap_long":       sw_l,
        "swap_short":      sw_s,
        "swap_mode":       sw_mode,
    }

if not specs:
    print("\nNicio pereche gasita la acest broker. Verifica numele simbolurilor.")
    mt5.shutdown()
    quit()

# Salveaza specs pentru backtest
specs_path = os.path.join(DATA_DIR, "crypto_specs.json")
with open(specs_path, "w", encoding="utf-8") as f:
    json.dump(specs, f, indent=2)
print(f"\n  Specs salvate in: {specs_path}")

print("\n  NOTA swap_mode: 0=pips, 1=base_currency, 2=interest%, 3=margin_currency, 4=currency, 5=points")
print("  swap_long/swap_short: negativ = platesti, pozitiv = primesti\n")

# ---- Descarca date M15 + M30 --------------------------------------------------
print("=== DESCARCARE DATE (M15 + M30, maxim istoric) ===\n")

found_symbols = list(specs.keys())

for sym in found_symbols:
    print(f"  {sym}:")
    for tf_name, tf_code in TIMEFRAMES.items():
        rates = mt5.copy_rates_from_pos(sym, tf_code, 0, N_BARE_MAX)

        if rates is None or len(rates) == 0:
            # Fallback: interval explicit de la 2020 pana azi
            frm = datetime(2020, 1, 1)
            to  = datetime.now()
            rates = mt5.copy_rates_range(sym, tf_code, frm, to)

        if rates is None or len(rates) == 0:
            print(f"    {tf_name}: NU AM PRIMIT DATE -> {mt5.last_error()}")
            print(f"    (Deschide chart-ul {sym} {tf_name} in MT5 si deruleaza la stanga,")
            print(f"     apoi reruleaza scriptul)")
            continue

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")

        cale = os.path.join(DATA_DIR, f"{sym}_{tf_name}.csv")
        df.to_csv(cale, index=False)

        start = df["time"].min().strftime("%Y-%m-%d")
        end   = df["time"].max().strftime("%Y-%m-%d")
        print(f"    {tf_name}: {len(df):>7} bare  [{start} ... {end}]  -> {cale}")

    print()

mt5.shutdown()
print("=== GATA ===")
print("Pasul urmator: python scripts/research/crypto_backtest.py")
