"""
live_runner.py — Faza 1, Pasul 2
Bucla de semnale live — mod OBSERVE (ZERO executie, ZERO ordine).

Ce face:
  - Se trezeste la fiecare inchidere M15 (:00/:15/:30/:45) + 5s tampon.
  - Preia ultima bara M15 INCHISA (df.iloc[-2] din prepare_symbol).
  - Ruleaza EXACT aceleasi functii ca backtestul:
      prepare_symbol → detect_setup → count_optional → reward_R
      Aritmetica entry/sl/tp/lots identica cu engine/portfolio.py:178-198.
  - Logheaza structurat (CSV in data/live_signals/) si in consola.
  - NU plaseaza niciun ordin. NU foloseste SQLite sau persistenta.
  - Verifica obligatoriu ca e cont DEMO la pornire.

Rulare: python live_runner.py
Oprire: Ctrl+C

Punctul de extensie pentru Faza 2 (executie) este marcat cu
  # FASE 2: aici se va apela broker API
"""

import os
import sys
import csv
import json
import math
import time
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd
import MetaTrader5 as mt5

from adapters.mt5_source import Mt5DataSource
from strategy.preparation import prepare_symbol
from strategy.structure import detect_setup
from strategy.signals import pip_size, count_optional, reward_R
from strategy.costs import pip_value_usd

# ── Parametri (identici cu portfolio_backtest.py) ────────────────────────────

SYMBOLS         = ["EURUSD", "GBPUSD", "EURJPY"]   # perechi tranzactionate + loggate
SYMBOLS_RATE    = ["USDJPY"]                        # incarcate DOAR ca rata de conversie (nu se tranzactioneaza)
ONLY_LONG       = True                              # doar directia 1 (BUY); SELL ignorat
SKIP_MONDAY     = True
SKIP_HOURS      = (15, 16)
PULLBACK_WINDOW = 8
ATR_MAX_PIPS    = {"EURUSD": 7.5}
CORR_PAIRS      = {"EURUSD": "GBPUSD", "GBPUSD": "EURUSD"}

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config", "standard_profile.json")
LOG_DIR     = os.path.join(os.path.dirname(__file__), "data", "live_signals")

N_BARS        = 1000   # bare incarcate: suficient pt EMA200 M30 + buffer detect_setup
CYCLE_BUFFER  = 5      # secunde asteptare dupa marginea M15 (bara sigur inchisa la broker)


# ── Timing ───────────────────────────────────────────────────────────────────

def _seconds_to_next_m15() -> float:
    """Returneaza secundele pana la urmatoarea margine M15 in UTC."""
    now = datetime.now(timezone.utc)
    elapsed = (now.minute * 60 + now.second + now.microsecond / 1_000_000) % (15 * 60)
    return (15 * 60) - elapsed


# ── Scanare bara ─────────────────────────────────────────────────────────────

def _scan(df: pd.DataFrame, j: int, symbol: str, cfg: dict,
          balance: float, usdjpy_close: float) -> dict:
    """
    Scaneaza bara INCHISA la index j din df.

    Refoloseste exact detect_setup / count_optional / reward_R din strategy/.
    Aritmetica entry/sl/tp/lots e identica cu engine/portfolio.py:178-198.
    NU plaseaza niciun ordin.

    Returneaza dict cu toate campurile necesare log-ului.
    """
    row = df.iloc[j]
    t   = row["time"]
    pip = pip_size(symbol)
    sh  = cfg["session"]["start_hour"]
    eh  = cfg["session"]["end_hour"]

    in_session = (sh <= t.hour < eh)

    base = {
        "bar_time":  t,
        "symbol":    symbol,
        "in_session": in_session,
        "setup":     False,
        "direction": "NONE",
        "entry": None, "sl": None, "tp": None,
        "lots":  None, "R":  None, "n_opt": None,
        "atr_pips": None, "skip_reason": "",
    }

    # Filtre — identice cu engine/portfolio.py:152-164
    if SKIP_MONDAY and t.weekday() == 0:
        return {**base, "skip_reason": "skip_monday"}
    if t.hour in SKIP_HOURS:
        return {**base, "skip_reason": f"skip_hour_{t.hour}"}
    if not in_session:
        return {**base, "skip_reason": "out_of_session"}

    trend = row.get("trend", 0)
    if pd.isna(trend) or trend == 0:
        return {**base, "skip_reason": "no_trend"}

    atr_val = row.get("atr", float("nan"))
    atr_pips = round(atr_val / pip, 1) if not pd.isna(atr_val) else None
    cap = ATR_MAX_PIPS.get(symbol)
    if cap and atr_pips is not None and atr_pips > cap:
        return {**base, "skip_reason": "atr_cap", "atr_pips": atr_pips}

    direction = int(trend)
    if ONLY_LONG and direction == -1:
        return {**base, "skip_reason": "only_long"}

    found = detect_setup(df, j, direction, window=PULLBACK_WINDOW)
    if found is None:
        return {**base, "skip_reason": "no_setup", "atr_pips": atr_pips}

    # Setup detectat — calculeaza ordinul (identic cu engine/portfolio.py:179-198)
    ext, _ = found
    buf = 2 * pip

    if direction == 1:
        entry = row["high"] + buf
        sl    = ext - buf
    else:
        entry = row["low"]  - buf
        sl    = ext + buf

    risk_dist = abs(entry - sl)
    if risk_dist <= 0:
        return {**base, "skip_reason": "zero_risk_dist", "atr_pips": atr_pips}

    n_opt = count_optional(row, direction, cfg)
    R     = reward_R(n_opt, cfg)
    tp    = entry + direction * risk_dist * R

    rp_base = cfg["account"]["risk_per_trade_pct"] / 100.0
    rp_all  = cfg["account"].get("risk_per_trade_pct_all_criteria",
                                 cfg["account"]["risk_per_trade_pct"]) / 100.0
    rp      = rp_all if n_opt >= 2 else rp_base

    pv      = pip_value_usd(symbol, entry, usdjpy_close)
    sl_pips = risk_dist / pip
    lots    = (balance * rp) / (sl_pips * pv) if sl_pips > 0 and pv > 0 else 0.0
    lots    = math.floor(lots / 0.01) * 0.01

    # FAZA 2: aici se va apela broker API (trimitere ordin Buy/Sell Stop)

    return {
        "bar_time":   t,
        "symbol":     symbol,
        "in_session": True,
        "skip_reason": "",
        "setup":      True,
        "direction":  "BUY" if direction == 1 else "SELL",
        "entry":      round(entry, 5),
        "sl":         round(sl,    5),
        "tp":         round(tp,    5),
        "lots":       round(lots,  2),
        "R":          R,
        "n_opt":      n_opt,
        "atr_pips":   atr_pips,
    }


# ── Corelatie EURUSD/GBPUSD ───────────────────────────────────────────────────

def _apply_corr_notes(results: list[dict]) -> None:
    """
    Daca EURUSD si GBPUSD au ambele setup in aceeasi directie in acelasi ciclu,
    marcheaza ambele cu corr_note (filtrul de corelatie ar fi blocat unul din ele).
    In OBSERVE nu blocam — doar notam, ca sa fie vizibil in log.
    """
    by_sym = {r["symbol"]: r for r in results}
    eu, gb = by_sym.get("EURUSD"), by_sym.get("GBPUSD")
    if eu and gb and eu["setup"] and gb["setup"] and eu["direction"] == gb["direction"]:
        eu["corr_note"] = f"corr_conflict:{eu['direction']}"
        gb["corr_note"] = f"corr_conflict:{eu['direction']}"


# ── Log CSV ───────────────────────────────────────────────────────────────────

_LOG_FIELDS = [
    "cycle_time", "bar_time", "symbol",
    "in_session", "skip_reason",
    "setup", "direction",
    "entry", "sl", "tp", "lots", "R", "n_opt",
    "atr_pips", "corr_note",
]


def _open_log(start_dt: datetime) -> tuple:
    os.makedirs(LOG_DIR, exist_ok=True)
    fname = os.path.join(LOG_DIR, f"signals_{start_dt.strftime('%Y%m%d_%H%M%S')}.csv")
    fh = open(fname, "w", newline="", encoding="utf-8")
    writer = csv.DictWriter(fh, fieldnames=_LOG_FIELDS, extrasaction="ignore")
    writer.writeheader()
    return fh, writer, fname


# ── Output consola ────────────────────────────────────────────────────────────

def _print_cycle(cycle_utc: datetime, results: list[dict]) -> None:
    ts = cycle_utc.strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"\n[{ts}] Ciclu M15:")
    for r in results:
        bt = r["bar_time"]
        bar_str = bt.strftime("%H:%M") if hasattr(bt, "strftime") else str(bt)
        sym = r["symbol"]
        if r["setup"]:
            corr = f"  [{r['corr_note']}]" if r.get("corr_note") else ""
            print(
                f"  {sym:6s} {r['direction']:4s}  "
                f"bara={bar_str}  entry={r['entry']}  sl={r['sl']}  tp={r['tp']}"
                f"  lots={r['lots']}  R={r['R']}  n_opt={r['n_opt']}{corr}"
            )
        else:
            reason = r["skip_reason"] or "?"
            print(f"  {sym:6s} ---   bara={bar_str}  ({reason})")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    # Forteaza UTF-8 pe stdout/stderr (necesar pe Windows cu terminal cp1252)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)

    src = Mt5DataSource(n_bars=N_BARS)
    try:
        acc = src.connect()
    except RuntimeError as e:
        print(f"EROARE: {e}")
        sys.exit(1)

    start_dt = datetime.now(timezone.utc)
    fh, writer, log_path = _open_log(start_dt)

    print("=" * 62)
    print("  live_runner.py  --  mod OBSERVE (ZERO executie)")
    print(f"  Login:   {acc.login}  |  Server: {acc.server}  |  DEMO OK")
    print(f"  Balanta: {acc.balance} {acc.currency}")
    print(f"  Offset server: UTC+{src.server_offset_h()}")
    print(f"  Log:     {log_path}")
    print(f"  Sesiune: {cfg['session']['start_hour']:02d}:00-{cfg['session']['end_hour']:02d}:00 "
          f"| skip_luni={SKIP_MONDAY} | skip_ore={list(SKIP_HOURS)}")
    print(f"  Pullback window: {PULLBACK_WINDOW} | ATR cap: {ATR_MAX_PIPS}")
    print("=" * 62)

    try:
        while True:
            wait_s = _seconds_to_next_m15() + CYCLE_BUFFER
            wake_utc = datetime.now(timezone.utc) + timedelta(seconds=wait_s)
            print(f"\n  Dorm {wait_s:.0f}s -> ciclu la {wake_utc.strftime('%H:%M:%S')} UTC ...",
                  end="", flush=True)
            time.sleep(wait_s)
            print(" activ.")

            cycle_utc = datetime.now(timezone.utc)

            # Refresh balanta (cont demo poate fi reincarcata)
            acc_live = src.account_info()
            balance  = acc_live.balance if acc_live else acc.balance

            # ── Incarca si prepara datele ─────────────────────────────
            data: dict[str, pd.DataFrame] = {}
            for symbol in SYMBOLS:
                try:
                    data[symbol] = prepare_symbol(src, symbol, cfg)
                except Exception as e:
                    print(f"  [!] {symbol}: prepare_symbol eroare - {e}")

            # Incarca SYMBOLS_RATE (ex: USDJPY) DOAR pentru conversie pip value —
            # nu se tranzactioneaza, nu se logeaza, nu apar in results.
            rate_data: dict[str, pd.DataFrame] = {}
            for symbol in SYMBOLS_RATE:
                try:
                    rate_data[symbol] = prepare_symbol(src, symbol, cfg)
                except Exception as e:
                    print(f"  [!] {symbol} (rate): prepare_symbol eroare - {e}")

            # Cursul USDJPY pentru pip_value_usd pe cross-uri cu JPY (EURJPY etc.)
            uj = rate_data.get("USDJPY")
            usdjpy_close = float(uj["close"].iloc[-2]) if uj is not None and len(uj) >= 2 else 150.0

            # ── Scaneaza ultima bara INCHISA pt fiecare simbol ────────
            results: list[dict] = []
            for symbol in SYMBOLS:
                df = data.get(symbol)
                if df is None or len(df) < 2:
                    continue
                # df.iloc[-1] = bara in formare (pos=0 MT5)
                # df.iloc[-2] = ultima bara INCHISA (pos=1 MT5)
                r = _scan(df, len(df) - 2, symbol, cfg, balance, usdjpy_close)
                r.setdefault("corr_note", "")
                results.append(r)

            _apply_corr_notes(results)

            # ── Scrie log CSV ──────────────────────────────────────────
            cycle_str = cycle_utc.strftime("%Y-%m-%d %H:%M:%S")
            for r in results:
                writer.writerow({**r, "cycle_time": cycle_str})
            fh.flush()

            _print_cycle(cycle_utc, results)

    except KeyboardInterrupt:
        print("\n\n  Oprit (Ctrl+C).")
    finally:
        fh.close()
        src.disconnect()
        print(f"  Log final: {log_path}")


if __name__ == "__main__":
    main()
