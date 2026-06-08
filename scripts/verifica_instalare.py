"""
Verificare instalare — trading bot pullback-in-trend
======================================================
Ruleaza INAINTE de prima pornire a sesiunilor live.
Verifica Python, pachete, MT5, date, si configuratia.

Rulare: python scripts/verifica_instalare.py
"""

import sys
import os

OK   = "  [OK]"
FAIL = "  [EROARE]"
WARN = "  [ATENTIE]"

errors   = []
warnings = []


def check(label, ok, detail="", fatal=True):
    if ok:
        print(f"{OK}  {label}" + (f" — {detail}" if detail else ""))
    else:
        marker = FAIL if fatal else WARN
        print(f"{marker}  {label}" + (f" — {detail}" if detail else ""))
        (errors if fatal else warnings).append(label)


# =============================================================================
print("\n=== 1. PYTHON ===")

ver = sys.version_info
check("Python versiune", ver >= (3, 11),
      f"gasit {ver.major}.{ver.minor}.{ver.micro} (necesar >=3.11)")

check("Sistem operare Windows", sys.platform == "win32",
      f"gasit {sys.platform} — MetaTrader5 necesita Windows", fatal=True)

# =============================================================================
print("\n=== 2. PACHETE PYTHON ===")

for pkg, min_ver in [("pandas", "2.0"), ("numpy", "1.26"), ("MetaTrader5", "5.0")]:
    try:
        mod = __import__(pkg.lower().replace("metatrader5", "MetaTrader5"))
        v = getattr(mod, "__version__", "?")
        check(f"pachet {pkg}", True, f"v{v}")
    except ImportError:
        check(f"pachet {pkg}", False,
              f"lipseste — ruleaza: pip install {pkg}")

try:
    from zoneinfo import ZoneInfo
    ZoneInfo("Europe/Bucharest")
    check("zoneinfo Europe/Bucharest", True)
except Exception as e:
    check("zoneinfo Europe/Bucharest", False, str(e))

# =============================================================================
print("\n=== 3. STRUCTURA PROIECT ===")

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

dirs_needed = [
    "strategy", "engine", "adapters", "live", "config", "scripts", "docs"
]
for d in dirs_needed:
    check(f"director {d}/", os.path.isdir(os.path.join(root, d)))

files_needed = [
    "config/standard_profile.json",
    "adapters/mt5_source.py",
    "live/signal_generator.py",
    "live/session1_m15_long.py",
    "live/session2_m5_both.py",
    "portfolio_backtest.py",
    "session2_backtest.py",
]
for f in files_needed:
    check(f"fisier {f}", os.path.isfile(os.path.join(root, f)))

# =============================================================================
print("\n=== 4. DATE ISTORICE (M15 + M30) ===")

data_dir = os.path.join(root, "data")
required_data = [
    ("EURUSD_M15.csv", "EURUSD_M30.csv"),
    ("GBPUSD_M15.csv", "GBPUSD_M30.csv"),
    ("EURJPY_M15.csv", "EURJPY_M30.csv"),
    ("USDJPY_M15.csv", "USDJPY_M30.csv"),
    ("AUDJPY_M15.csv",),
    ("NZDJPY_M15.csv",),
]

if not os.path.isdir(data_dir):
    check("director data/", False,
          "lipseste — va fi creat la prima descarcare")
else:
    import pandas as pd
    for group in required_data:
        for fname in group:
            fpath = os.path.join(data_dir, fname)
            if os.path.isfile(fpath):
                try:
                    df = pd.read_csv(fpath, nrows=5)
                    size = os.path.getsize(fpath) // 1024
                    check(f"data/{fname}", True, f"{size} KB")
                except Exception as e:
                    check(f"data/{fname}", False, f"corupt: {e}")
            else:
                check(f"data/{fname}", False,
                      "lipseste — ruleaza: python scripts/descarca_date.py",
                      fatal=False)

# =============================================================================
print("\n=== 5. CONEXIUNE MT5 ===")

try:
    import MetaTrader5 as mt5
    if mt5.initialize():
        acc = mt5.account_info()
        if acc:
            is_demo = acc.trade_mode == 0
            check("MT5 conectat", True,
                  f"cont {acc.login} @ {acc.server}")
            check("Cont DEMO (nu LIVE)", is_demo,
                  "ATENTIE: sesiunile ruleaza DOAR pe demo" if not is_demo else "")
        else:
            check("MT5 cont info", False, "nu s-a putut citi contul")
        mt5.shutdown()
    else:
        check("MT5 initialize()", False,
              "MT5 nu e deschis sau nu esti logat — deschide MT5 si logheaza-te pe demo")
except Exception as e:
    check("MT5 import/connect", False, str(e))

# =============================================================================
print("\n=== 6. IMPORT MODULE PROIECT ===")

sys.path.insert(0, root)
modules = [
    ("backtest", "CONFIG, DATA_DIR"),
    ("adapters.csv_source", "CsvDataSource"),
    ("adapters.mt5_source", "Mt5DataSource"),
    ("strategy.preparation", "prepare_symbol"),
    ("strategy.structure", "detect_setup"),
    ("engine.portfolio", "run_portfolio"),
    ("live.signal_generator", "run_generator"),
]
for mod_name, symbols in modules:
    try:
        mod = __import__(mod_name, fromlist=symbols.split(", "))
        for sym in symbols.split(", "):
            getattr(mod, sym.strip())
        check(f"import {mod_name}", True)
    except Exception as e:
        check(f"import {mod_name}", False, str(e))

# =============================================================================
print("\n=== 7. TEST RAPID BACKTEST ===")

try:
    import json, contextlib, io
    from adapters.csv_source import CsvDataSource
    from strategy.preparation import prepare_symbol
    from engine.portfolio import run_portfolio

    cfg_path = os.path.join(root, "config", "standard_profile.json")
    with open(cfg_path, encoding="utf-8") as f:
        cfg = json.load(f)

    src = CsvDataSource(data_dir)
    data = {}
    for sym in ["EURUSD"]:
        try:
            data[sym] = prepare_symbol(src, sym, cfg)
        except FileNotFoundError:
            pass

    if data:
        params = {
            "spread_pips": {"EURUSD": 0.5}, "leverage": 30,
            "start_balance": 300, "expire_bars": 4, "pullback_window": 8,
            "depth_range": None, "skip_monday": True, "skip_hours": (15, 16),
            "atr_max_pips": {"EURUSD": 7.5}, "max_day_consec_losses": 3,
            "corr_pairs": {}, "only_long": True, "max_pos_per_symbol": 1,
            "symbol_sessions": {}, "symbol_skip_hours": {},
        }
        with contextlib.redirect_stdout(io.StringIO()):
            trades, *_ = run_portfolio(data, cfg, params)
        check("Backtest smoke test EURUSD", len(trades) > 0,
              f"{len(trades)} trades simulate")
    else:
        check("Backtest smoke test", False,
              "EURUSD_M15.csv lipseste — ruleaza descarca_date.py mai intai",
              fatal=False)
except Exception as e:
    check("Backtest smoke test", False, str(e))

# =============================================================================
print("\n" + "="*55)
if errors:
    print(f"  REZULTAT: {len(errors)} ERORI — botul NU poate porni")
    print(f"\n  Erori de rezolvat:")
    for e in errors:
        print(f"    - {e}")
elif warnings:
    print(f"  REZULTAT: OK cu {len(warnings)} avertismente")
    print(f"  Botul poate porni, dar verifica avertismentele de mai sus.")
else:
    print("  REZULTAT: TOTUL OK — botul este pregatit de rulare")
print("="*55 + "\n")
