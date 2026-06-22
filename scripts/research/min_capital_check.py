"""
Calculeaza capitalul minim necesar per piata la 1% risk, bazat pe:
  - lot minim broker (din MT5)
  - ATR mediu M15 (din CSV local, ultimele 1000 bare)
  - pip_value per lot (din MT5 symbol_info)

Ruleaza: python scripts/research/min_capital_check.py
"""

import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pandas as pd
import numpy as np

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")

# Piete viabile din scan
VIABLE = [
    "EURUSD", "GER40", "BTCUSD", "XRPUSD", "US30",
    "USDCHF", "AUDJPY", "EURCAD", "USDJPY", "GBPCAD",
    "USDCAD", "EURAUD", "EURJPY", "CHFJPY", "GBPUSD",
    "GBPAUD", "AUDCAD", "NZDJPY", "AUDNZD", "XAUUSD",
]

# pip_size per simbol (fallback daca MT5 nu e disponibil)
PIP_SIZE_FALLBACK = {
    "EURUSD": 0.0001, "GBPUSD": 0.0001, "USDCHF": 0.0001,
    "USDCAD": 0.0001, "AUDUSD": 0.0001, "NZDUSD": 0.0001,
    "EURAUD": 0.0001, "EURCAD": 0.0001, "EURGBP": 0.0001,
    "EURNZD": 0.0001, "GBPAUD": 0.0001, "GBPCAD": 0.0001,
    "GBPNZD": 0.0001, "AUDNZD": 0.0001, "AUDCAD": 0.0001,
    "USDJPY": 0.01,   "EURJPY": 0.01,   "GBPJPY": 0.01,
    "AUDJPY": 0.01,   "NZDJPY": 0.01,   "CADJPY": 0.01,
    "CHFJPY": 0.01,
    "GER40": 1.0,  "US30": 1.0,  "US500": 1.0, "UK100": 1.0,
    "XAUUSD": 0.01, "XAGUSD": 0.01,
    "BTCUSD": 1.0, "ETHUSD": 1.0, "XRPUSD": 0.001,
    "SOLUSD": 0.01,
}

def get_atr_from_csv(symbol, n_bars=1000):
    """Calculeaza ATR mediu M15 din ultimele n_bars bare CSV."""
    csv_path = os.path.join(DATA_DIR, f"{symbol}_M15.csv")
    if not os.path.exists(csv_path):
        # Incearca H1 pentru simboluri fara M15
        csv_path = os.path.join(DATA_DIR, f"{symbol}_H1.csv")
        if not os.path.exists(csv_path):
            return None
    try:
        # Citim ultimele n_bars + 1 (pentru shift) din CSV (newest la sfarsit)
        df = pd.read_csv(csv_path)
        df.columns = [c.lower() for c in df.columns]
        df = df.tail(n_bars + 1).reset_index(drop=True)
        if len(df) < 20:
            return None
        # True Range
        df["tr"] = np.maximum(
            df["high"] - df["low"],
            np.maximum(
                abs(df["high"] - df["close"].shift(1)),
                abs(df["low"]  - df["close"].shift(1))
            )
        )
        atr = df["tr"].iloc[1:].mean()   # skip primul rand (shift NaN)
        price = df["close"].iloc[-1]
        return float(atr), float(price)
    except Exception as e:
        return None

def get_mt5_specs(symbol):
    """Returneaza specs din MT5: volume_min, tick_size, tick_value, pip_value_per_lot."""
    if not MT5_AVAILABLE:
        return None

    info = mt5.symbol_info(symbol)
    if info is None:
        # Incearca alias-uri comune
        aliases = {
            "GER40": ["DE40", "GER40", "DAX40", "GER40.cash"],
            "US30":  ["US30", "DJ30", "DJIA", "US30.cash"],
            "US500": ["US500", "SP500", "SPX500"],
            "UK100": ["UK100", "FTSE100", "UK100.cash"],
            "XRPUSD": ["XRPUSD", "XRP/USD"],
            "BTCUSD": ["BTCUSD", "BTC/USD"],
        }
        for alias in aliases.get(symbol, []):
            info = mt5.symbol_info(alias)
            if info is not None:
                break
    if info is None:
        return None

    pip_size = PIP_SIZE_FALLBACK.get(symbol, 0.0001)

    tick_size  = info.trade_tick_size
    tick_value = info.trade_tick_value   # USD per tick per 1 lot
    vol_min    = info.volume_min
    vol_step   = info.volume_step
    contract   = info.trade_contract_size

    if tick_size > 0:
        pip_value_per_lot = (tick_value / tick_size) * pip_size
    else:
        pip_value_per_lot = 0

    return {
        "vol_min":   vol_min,
        "vol_step":  vol_step,
        "contract":  contract,
        "tick_size": tick_size,
        "tick_value":tick_value,
        "pip_value_per_lot": pip_value_per_lot,
        "pip_size":  pip_size,
    }

def main():
    if MT5_AVAILABLE:
        if not mt5.initialize():
            print("MT5 initialize() esuat. Asigura-te ca MT5 e deschis.")
            return
        print(f"MT5 conectat: {mt5.account_info().server}")
    else:
        print("MetaTrader5 nu e disponibil. Rulam cu date CSV only (fara specs broker).")

    print()
    print("=" * 110)
    print(f"{'Piata':<10} {'Lot min':>8} {'Lot step':>9} {'ATR M15':>10} {'ATR/pip':>9} {'pip$/lot':>9} "
          f"{'Risc min$':>10} {'Cap min$':>10} {'$alocat':>8} {'Multiplicator':>14}")
    print("-" * 110)

    ALLOCATION = {
        "EURUSD": 130, "GER40": 112, "BTCUSD": 109, "XRPUSD": 103, "US30": 91,
        "USDCHF": 80,  "AUDJPY": 69, "EURCAD": 66,  "USDJPY": 47,  "GBPCAD": 40,
        "USDCAD": 36,  "EURAUD": 36, "EURJPY": 25,  "CHFJPY": 23,  "GBPUSD": 16,
        "GBPAUD": 12,  "AUDCAD": 4,  "NZDJPY": 0,   "AUDNZD": 0,   "XAUUSD": 0,
    }

    results = []

    for sym in VIABLE:
        csv_result = get_atr_from_csv(sym)
        if csv_result is None:
            atr_abs = None
            price   = None
        else:
            atr_abs, price = csv_result

        specs = get_mt5_specs(sym) if MT5_AVAILABLE else None

        alloc = ALLOCATION.get(sym, 0)

        if specs is None:
            # Fara MT5, nu putem calcula risc minim
            results.append({
                "sym": sym, "vol_min": "N/A", "vol_step": "N/A",
                "atr_abs": atr_abs, "atr_pips": None,
                "pip_val": None, "min_risk": None, "min_cap": None,
                "alloc": alloc, "mult": None,
            })
            print(f"  {sym:<10} {'N/A':>8} {'N/A':>9} "
                  f"{f'{atr_abs:.4f}' if atr_abs else 'N/A':>10} {'N/A':>9} {'N/A':>9} "
                  f"{'N/A':>10} {'N/A':>10} {alloc:>7}$ {'N/A':>14}")
            continue

        pip_size = specs["pip_size"]
        atr_pips = atr_abs / pip_size if (atr_abs and pip_size > 0) else None
        pip_val  = specs["pip_value_per_lot"]
        vol_min  = specs["vol_min"]

        # Stop estimat = 1 ATR (pullback setup tipic)
        # Risc minim = vol_min loturi × atr_pips pips × pip_value_per_lot
        if atr_pips and pip_val > 0:
            min_risk = vol_min * atr_pips * pip_val
            min_cap  = min_risk / 0.01   # capital la 1% risk
        else:
            min_risk = None
            min_cap  = None

        mult = (min_risk / (alloc * 0.01)) if (min_risk and alloc > 0) else None

        results.append({
            "sym": sym, "vol_min": vol_min, "vol_step": specs["vol_step"],
            "atr_abs": atr_abs, "atr_pips": atr_pips,
            "pip_val": pip_val, "min_risk": min_risk, "min_cap": min_cap,
            "alloc": alloc, "mult": mult,
        })

        mult_str = f"{mult:.1f}x" if mult else "N/A"
        flag = " !!!" if (mult and mult > 2) else (" !" if (mult and mult > 1.5) else "")

        print(f"  {sym:<10} {vol_min:>8.3f} {specs['vol_step']:>9.4f} "
              f"{atr_abs:>10.4f} {atr_pips:>9.1f} {pip_val:>9.4f} "
              f"{min_risk:>9.2f}$ {min_cap:>9.0f}$ {alloc:>7}$ {mult_str:>10}{flag}")

    print("=" * 110)
    print()

    # Rezumat: piete cu probleme (multiplicator > 1.5x)
    problematic = [r for r in results if r["mult"] and r["mult"] > 1.5]
    ok          = [r for r in results if r["mult"] and r["mult"] <= 1.5]

    if problematic:
        print("PROBLEME (risc minim > 1.5x riscul intentionat la alocarea sugerata):")
        for r in sorted(problematic, key=lambda x: -x["mult"]):
            print(f"  {r['sym']:<10} lot_min={r['vol_min']:.3f} | risc_min=${r['min_risk']:.2f} "
                  f"vs intentionat=${r['alloc']*0.01:.2f} | cap_min_necesar=${r['min_cap']:.0f} "
                  f"(alocat ${r['alloc']}) | {r['mult']:.1f}x")

    print()
    print("OK (risc controlat la alocarea sugerata):")
    for r in sorted(ok, key=lambda x: x["mult"] or 0):
        if r["mult"]:
            print(f"  {r['sym']:<10} lot_min={r['vol_min']:.3f} | risc_min=${r['min_risk']:.2f} "
                  f"vs intentionat=${r['alloc']*0.01:.2f} | {r['mult']:.2f}x")

    print()
    print("NOTA: ATR = media ultimelor 1000 bare M15 (stop estimat = 1 ATR)")
    print("      'Multiplicator' = cat de mare e riscul real vs riscul intentionat la lot minim")
    print("      > 2x = problematic (risc real de 2+ ori mai mare decat intentionat)")

    if MT5_AVAILABLE:
        mt5.shutdown()

if __name__ == "__main__":
    main()
