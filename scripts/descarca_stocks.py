"""
Descarca date CFD Stocks din MT5 -> CSV
---------------------------------------
IC Markets EU: simboluri de tip AAPL.US, MSFT.US, TSLA.US etc.
Ruleaza cu MT5 deschis si logat.

Rulare: python scripts/descarca_stocks.py
"""
import os
from datetime import datetime, timedelta
import MetaTrader5 as mt5
import pandas as pd

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

if not mt5.initialize():
    print("EROARE la initialize():", mt5.last_error())
    quit()

# Simboluri stock CFD — IC Markets EU foloseste sufixul .US pentru actiuni NYSE/NASDAQ
# Incearca ambele variante (cu si fara .US)
STOCKS = [
    "AAPL.US", "AAPL",
    "MSFT.US", "MSFT",
    "TSLA.US", "TSLA",
    "NVDA.US", "NVDA",
    "META.US", "META",
    "GOOGL.US", "GOOGL",
    "AMZN.US", "AMZN",
    "NFLX.US", "NFLX",
    "AMD.US",  "AMD",
    "BABA.US", "BABA",
]

TF_CONFIG = {
    "M15": (mt5.TIMEFRAME_M15, 50000),
    "M30": (mt5.TIMEFRAME_M30, 50000),
}

found = []
print("Caut simboluri disponibile...\n")

checked = set()
for sym in STOCKS:
    if sym in checked:
        continue
    checked.add(sym)

    if not mt5.symbol_select(sym, True):
        continue

    info = mt5.symbol_info(sym)
    if info is None:
        continue

    print(f"  {sym}: gasit  (spread={info.spread}, point={info.point})")
    found.append(sym)

if not found:
    print("\nNiciun simbol stock gasit. Verifica:")
    print("  1. MT5 este deschis si logat pe contul IC Markets")
    print("  2. Simbolurile stock sunt vizibile in Market Watch")
    print("  3. Incearca sa cauti manual 'AAPL' in MT5 Market Watch")
    mt5.shutdown()
    quit()

print(f"\nDescarc date pentru {len(found)} simboluri...")

for sym in found:
    sym_info = mt5.symbol_info(sym)
    if sym_info is None:
        continue

    for tf_name, (tf, n_bars) in TF_CONFIG.items():
        rates = mt5.copy_rates_from_pos(sym, tf, 0, n_bars)

        if rates is None or len(rates) == 0:
            to = datetime.now()
            frm = to - timedelta(days=365 * 5)
            rates = mt5.copy_rates_range(sym, tf, frm, to)

        if rates is None or len(rates) == 0:
            print(f"  {sym} {tf_name}: nu am date")
            continue

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df = df[["time", "open", "high", "low", "close", "tick_volume"]]
        df.rename(columns={"tick_volume": "volume"}, inplace=True)

        # Normalizeaza simbolul pentru filename (sterge .US din nume fisier)
        file_sym = sym.replace(".", "_").replace("_US", "")
        out = os.path.join(DATA_DIR, f"{file_sym}_{tf_name}.csv")
        df.to_csv(out, index=False)
        yrs = (df["time"].max() - df["time"].min()).days / 365.25
        print(f"  {sym} {tf_name}: {len(df):,} bare ({yrs:.1f} ani) -> {out}")

    # Salveaza spec-uri pentru engine
    specs_path = os.path.join(DATA_DIR, "stocks_specs.json")
    try:
        import json
        specs = json.load(open(specs_path)) if os.path.exists(specs_path) else {}
    except Exception:
        specs = {}

    # Normalizeaza simbolul
    file_sym = sym.replace(".", "_").replace("_US", "")
    tick_val_usd = sym_info.trade_tick_value  # deja in USD (MT5 converteste)
    specs[file_sym] = {
        "original_symbol": sym,
        "tick_size":        sym_info.trade_tick_size,
        "tick_value_usd":   round(float(tick_val_usd), 6),
        "contract_size":    sym_info.trade_contract_size,
        "spread_ticks":     sym_info.spread,
        "spread_price":     round(sym_info.spread * sym_info.trade_tick_size, 6),
        "currency_profit":  sym_info.currency_profit,
    }
    with open(specs_path, "w") as f:
        json.dump(specs, f, indent=2)
    print(f"  {file_sym}: spec salvat in stocks_specs.json")

mt5.shutdown()
print("\nGata. Ruleaza python scripts/research/stocks_backtest.py pentru backtest.")
