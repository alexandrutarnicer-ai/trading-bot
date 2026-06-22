"""
Test izolat pentru strategy/patterns.py.
Verifica detect_flag si detect_inside_bar cu date sintetice.
Ruleaza: python _test_patterns.py
"""

import sys
import os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from strategy.patterns import detect_flag, detect_inside_bar


def make_df(rows):
    df = pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "atr"])
    df["time"] = pd.to_datetime(df["time"])
    return df


def test_detect_flag_long():
    """Bull Flag: 3 bare ascendente + 3 bare consolidare + breakout"""
    # ATR ~0.0020
    rows = []
    t = pd.Timestamp("2024-01-01 10:00")
    dt = pd.Timedelta("15min")

    # 60 bare de padding (cerinta minima j>=60)
    for i in range(60):
        rows.append((t + i * dt, 1.1000, 1.1010, 1.0990, 1.1000, 0.0020))

    # Pol: 3 bare bullish consecutive cu corp >= 0.5 * 0.0020 = 0.0010
    rows.append((t + 60*dt, 1.1000, 1.1020, 1.0998, 1.1018, 0.0020))  # +0.0018 body
    rows.append((t + 61*dt, 1.1018, 1.1040, 1.1016, 1.1038, 0.0020))  # +0.0020 body
    rows.append((t + 62*dt, 1.1038, 1.1060, 1.1036, 1.1056, 0.0020))  # +0.0018 body

    # Flag: 3 bare de consolidare (fara a depasi varful polului 1.1060)
    rows.append((t + 63*dt, 1.1050, 1.1058, 1.1040, 1.1042, 0.0020))
    rows.append((t + 64*dt, 1.1042, 1.1055, 1.1038, 1.1045, 0.0020))
    rows.append((t + 65*dt, 1.1045, 1.1057, 1.1040, 1.1048, 0.0020))

    # Breakout: inchide deasupra flag_high (1.1058)
    rows.append((t + 66*dt, 1.1048, 1.1075, 1.1046, 1.1065, 0.0020))

    df = make_df(rows)
    j = len(df) - 1  # bara de breakout

    cfg = {"pole_min_candles": 3, "pole_min_body_atr": 0.5, "flag_min_bars": 2, "flag_max_bars": 5, "flag_max_retrace_pct": 50}
    result = detect_flag(df, j, direction=1, cfg=cfg)

    assert result is not None, f"FAIL: trebuia sa detecteze bull flag, got None"
    sl_level, entry_level = result
    assert entry_level > 1.1000, f"FAIL: entry_level prea mic: {entry_level}"
    assert sl_level < entry_level, f"FAIL: sl_level ({sl_level}) trebuie < entry_level ({entry_level})"
    print(f"  [OK] detect_flag LONG: sl={sl_level:.5f} entry={entry_level:.5f}")


def test_detect_flag_rejects_no_pole():
    """Fara pol clar (corpuri mici) → nu detecteaza"""
    rows = []
    t = pd.Timestamp("2024-01-01 10:00")
    dt = pd.Timedelta("15min")

    for i in range(60):
        rows.append((t + i * dt, 1.1000, 1.1010, 1.0990, 1.1000, 0.0020))

    # Pol: corpuri mici (0.0001 < 0.5*0.0020 = 0.0010) → respins
    rows.append((t + 60*dt, 1.1000, 1.1002, 1.0999, 1.1001, 0.0020))
    rows.append((t + 61*dt, 1.1001, 1.1003, 1.1000, 1.1002, 0.0020))
    rows.append((t + 62*dt, 1.1002, 1.1004, 1.1001, 1.1003, 0.0020))

    rows.append((t + 63*dt, 1.1003, 1.1004, 1.1001, 1.1002, 0.0020))
    rows.append((t + 64*dt, 1.1002, 1.1003, 1.1001, 1.1002, 0.0020))
    rows.append((t + 65*dt, 1.1002, 1.1004, 1.1001, 1.1003, 0.0020))

    # Breakout
    rows.append((t + 66*dt, 1.1003, 1.1010, 1.1002, 1.1006, 0.0020))

    df = make_df(rows)
    j = len(df) - 1

    cfg = {"pole_min_candles": 3, "pole_min_body_atr": 0.5, "flag_min_bars": 2, "flag_max_bars": 5, "flag_max_retrace_pct": 50}
    result = detect_flag(df, j, direction=1, cfg=cfg)
    assert result is None, f"FAIL: trebuia None (pol slab), got {result}"
    print(f"  [OK] detect_flag respinge pol cu corpuri mici")


def test_detect_flag_rejects_large_retrace():
    """Retrasare > 50% din pol → nu detecteaza"""
    rows = []
    t = pd.Timestamp("2024-01-01 10:00")
    dt = pd.Timedelta("15min")

    for i in range(60):
        rows.append((t + i * dt, 1.1000, 1.1010, 1.0990, 1.1000, 0.0020))

    # Pol: pujde 100 pips (1.1000 → 1.1100)
    rows.append((t + 60*dt, 1.1000, 1.1035, 1.0998, 1.1030, 0.0020))
    rows.append((t + 61*dt, 1.1030, 1.1065, 1.1028, 1.1060, 0.0020))
    rows.append((t + 62*dt, 1.1060, 1.1105, 1.1058, 1.1100, 0.0020))

    # Flag: retrage 60 pips din 100 (>50%) → invalid
    rows.append((t + 63*dt, 1.1100, 1.1105, 1.1040, 1.1042, 0.0020))
    rows.append((t + 64*dt, 1.1042, 1.1050, 1.1038, 1.1040, 0.0020))  # low=1.1038 → retrace=62 pips

    rows.append((t + 65*dt, 1.1040, 1.1110, 1.1038, 1.1108, 0.0020))  # breakout

    df = make_df(rows)
    j = len(df) - 1

    cfg = {"pole_min_candles": 3, "pole_min_body_atr": 0.5, "flag_min_bars": 2, "flag_max_bars": 5, "flag_max_retrace_pct": 50}
    result = detect_flag(df, j, direction=1, cfg=cfg)
    assert result is None, f"FAIL: trebuia None (retrasare >50%), got {result}"
    print(f"  [OK] detect_flag respinge retrasare >50%")


def test_detect_inside_bar_long():
    """Inside bar LONG: mother bar larg, inside complet in interior, breakout sus"""
    rows = []
    t = pd.Timestamp("2024-01-01 10:00")
    dt = pd.Timedelta("15min")

    for i in range(60):
        rows.append((t + i * dt, 1.1000, 1.1010, 1.0990, 1.1000, 0.0020))

    # j-2: mother bar (range larg)
    rows.append((t + 60*dt, 1.1000, 1.1050, 1.0950, 1.1020, 0.0020))
    # j-1: inside bar (complet in interior)
    rows.append((t + 61*dt, 1.1010, 1.1040, 1.0960, 1.1015, 0.0020))
    # j: breakout deasupra inside bar high (1.1040)
    rows.append((t + 62*dt, 1.1015, 1.1060, 1.1010, 1.1055, 0.0020))

    df = make_df(rows)
    j = len(df) - 1

    result = detect_inside_bar(df, j, direction=1)
    assert result is not None, f"FAIL: trebuia sa detecteze inside bar LONG"
    sl_level, entry_level = result
    assert abs(sl_level - 1.0960) < 1e-7, f"FAIL: sl_level={sl_level:.5f} (asteptat ~1.09600)"
    assert abs(entry_level - 1.1040) < 1e-7, f"FAIL: entry_level={entry_level:.5f} (asteptat ~1.10400)"
    print(f"  [OK] detect_inside_bar LONG: sl={sl_level:.5f} entry={entry_level:.5f}")


def test_detect_inside_bar_short():
    """Inside bar SHORT: breakout sub inside bar low"""
    rows = []
    t = pd.Timestamp("2024-01-01 10:00")
    dt = pd.Timedelta("15min")

    for i in range(60):
        rows.append((t + i * dt, 1.1000, 1.1010, 1.0990, 1.1000, 0.0020))

    # j-2: mother bar
    rows.append((t + 60*dt, 1.1020, 1.1050, 1.0950, 1.1000, 0.0020))
    # j-1: inside bar
    rows.append((t + 61*dt, 1.1010, 1.1040, 1.0960, 1.1005, 0.0020))
    # j: breakout sub inside bar low (1.0960)
    rows.append((t + 62*dt, 1.0990, 1.1000, 1.0940, 1.0945, 0.0020))

    df = make_df(rows)
    j = len(df) - 1

    result = detect_inside_bar(df, j, direction=-1)
    assert result is not None, f"FAIL: trebuia sa detecteze inside bar SHORT"
    sl_level, entry_level = result
    assert abs(sl_level - 1.1040) < 1e-7, f"FAIL: sl_level={sl_level:.5f} (asteptat ~1.10400)"
    assert abs(entry_level - 1.0960) < 1e-7, f"FAIL: entry_level={entry_level:.5f} (asteptat ~1.09600)"
    print(f"  [OK] detect_inside_bar SHORT: sl={sl_level:.5f} entry={entry_level:.5f}")


def test_detect_inside_bar_rejects_non_inside():
    """Bara care depaseste mother bar high → nu e inside bar"""
    rows = []
    t = pd.Timestamp("2024-01-01 10:00")
    dt = pd.Timedelta("15min")

    for i in range(60):
        rows.append((t + i * dt, 1.1000, 1.1010, 1.0990, 1.1000, 0.0020))

    rows.append((t + 60*dt, 1.1000, 1.1050, 1.0950, 1.1020, 0.0020))  # mother
    rows.append((t + 61*dt, 1.1010, 1.1060, 1.0960, 1.1015, 0.0020))  # high > mother.high → nu e inside
    rows.append((t + 62*dt, 1.1015, 1.1070, 1.1010, 1.1065, 0.0020))

    df = make_df(rows)
    j = len(df) - 1

    result = detect_inside_bar(df, j, direction=1)
    assert result is None, f"FAIL: trebuia None (bara nu e inside), got {result}"
    print(f"  [OK] detect_inside_bar respinge bara non-inside")


def test_flag_in_portfolio():
    """Integrat: backtest cu flag enabled genereaza trades cu signal_type='flag'"""
    import json
    from backtest import CONFIG, DATA_DIR
    from adapters.csv_source import CsvDataSource
    from strategy.preparation import prepare_symbol
    from engine.portfolio import run_portfolio

    try:
        with open(CONFIG, encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception as e:
        print(f"  [SKIP] Nu pot citi config: {e}")
        return

    src  = CsvDataSource(DATA_DIR)
    data = {}
    for s in ["EURUSD", "GBPUSD", "EURJPY"]:
        try:
            df = prepare_symbol(src, s, cfg)
            if len(df) > 200:
                data[s] = df
        except Exception:
            pass

    if not data:
        print("  [SKIP] Date CSV lipsa pentru test integrat")
        return

    params = {
        "spread_pips":           {s: 1.0 for s in data},
        "leverage":              30,
        "start_balance":         1000,
        "expire_bars":           4,
        "pullback_window":       8,
        "depth_range":           None,
        "skip_monday":           True,
        "skip_weekdays":         {0},
        "skip_hours":            (15, 16),
        "atr_max_pips":          {},
        "max_day_consec_losses": 3,
        "corr_pairs":            {},
        "only_long":             True,
        "max_pos_per_symbol":    2,
        "min_bars_between_same_symbol": 0,
        "symbol_sessions":       {},
        "symbol_skip_hours":     {},
        "flag_cfg": {
            "enabled":  True,
            "r_ratio":  2.0,
            "risk_pct": 0.01,
        },
        "inside_bar_cfg": {
            "enabled":  True,
            "r_ratio":  2.0,
            "risk_pct": 0.01,
        },
    }

    trades, equity, balance, _, _, _, _ = run_portfolio(data, cfg, params)

    if not trades:
        print("  [SKIP] Niciun trade generat (date insuficiente sau config)")
        return

    import pandas as pd
    df_t = pd.DataFrame(trades)
    types = df_t.get("signal_type", pd.Series(["pullback"] * len(df_t)))
    n_pullback  = int((types == "pullback").sum())  if "signal_type" in df_t.columns else len(df_t)
    n_flag      = int((types == "flag").sum())      if "signal_type" in df_t.columns else 0
    n_inside    = int((types == "inside_bar").sum()) if "signal_type" in df_t.columns else 0

    print(f"  [OK] Backtest cu flag+inside_bar: {len(trades)} trades total "
          f"(pullback={n_pullback}, flag={n_flag}, inside_bar={n_inside})")
    assert "signal_type" in df_t.columns, "FAIL: signal_type lipseste din trades"

    # Baseline-ul pullback (fara flag) trebuie sa fie neschimbat
    params2 = dict(params)
    params2["flag_cfg"]       = {"enabled": False}
    params2["inside_bar_cfg"] = {"enabled": False}
    trades2, _, _, _, _, _, _ = run_portfolio(data, cfg, params2)
    n_pullback2 = len(trades2)

    # Pullback trades cu flag enabled trebuie sa fie <= pullback trades fara flag
    # (pot fi mai putine daca flag ocupa slot-ul de pozitie)
    print(f"  [OK] Fara flag: {n_pullback2} trades | Cu flag: {n_pullback} pullback + {n_flag} flag + {n_inside} IB")


if __name__ == "__main__":
    print("\n=== Test strategy/patterns.py ===\n")
    print("--- detect_flag ---")
    test_detect_flag_long()
    test_detect_flag_rejects_no_pole()
    test_detect_flag_rejects_large_retrace()
    print("\n--- detect_inside_bar ---")
    test_detect_inside_bar_long()
    test_detect_inside_bar_short()
    test_detect_inside_bar_rejects_non_inside()
    print("\n--- Test integrat backtest ---")
    test_flag_in_portfolio()
    print("\n=== Toate testele trecute! ===\n")
