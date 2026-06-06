"""
compare_live_vs_backtest.py  --  Faza 1, Pasul 3
=================================================
Dovedim ca live_runner detecteaza ACELEASI setup-uri ca backtestul,
bara cu bara, pe aceleasi date.

Sursa de bare pentru re-detectie: MT5 (nu CSV)
  - CSV-ul din data/ acopera perioada istorica, nu perioada live curenta.
  - live_runner foloseste Mt5DataSource; re-detectia trebuie sa foloseasca
    aceleasi bare pentru a verifica fidelitatea.
  - Barele M15 inchise sunt imutabile: OHLC-ul de la T este identic la T+n.

Compara la nivel de DETECTIE DE SETUP, nu tranzactii executate.
live_runner in OBSERVE nu are stare de pozitii -- comparatia e bara cu bara.

Configuratie aliniata la baseline-ul oficial:
  - Perechi:  EURUSD, GBPUSD, EURJPY  (ONLY_LONG=True)
  - ATR cap:  {"EURUSD": 7.5}  (fara cap pe EURJPY)
  - USDJPY:   incarcat separat ca rata de conversie (nu tranzactionat, nu logat)
  - Filtre:   skip_monday, skip_hours (15,16), sesiune 10-18 ora RO
  - Lookahead fix: detect_setup cu swing_n=3 default (look = df.iloc[a:j-2])

Nota lookahead:
  Fixul de lookahead (look = df.iloc[a:j-2]) garanteaza ca swing-urile
  folosite la bara j au fereastra de confirmare incheiata la j-1 sau mai
  devreme — adica folosesc EXCLUSIV bare deja inchise la momentul live.
  Barele inchise sunt imutabile, deci re-detectia produce ACELASI rezultat.
  Nepotrivirile din cauza mark_swings sunt imposibile cu fixul activ.

Rulare:
  python scripts/compare_live_vs_backtest.py
  python scripts/compare_live_vs_backtest.py --log-dir data/live_signals
  python scripts/compare_live_vs_backtest.py --all-logs   # toate sesiunile
"""

import os
import sys
import json
import math
import glob
import argparse

import numpy as np
import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from adapters.mt5_source import Mt5DataSource
from strategy.preparation import prepare_symbol
from strategy.structure import detect_setup
from strategy.signals import pip_size, count_optional, reward_R
from strategy.costs import pip_value_usd

# ── Constante identice cu live_runner.py ────────────────────────────────────

SYMBOLS         = ["EURUSD", "GBPUSD", "EURJPY"]   # perechi tranzactionate
SYMBOLS_RATE    = ["USDJPY"]                        # rata de conversie, nu tranzactionat
ONLY_LONG       = True
SKIP_MONDAY     = True
SKIP_HOURS      = (15, 16)
PULLBACK_WINDOW = 8
ATR_MAX_PIPS    = {"EURUSD": 7.5}                  # fara cap pe EURJPY

CONFIG_PATH = os.path.join(_ROOT, "config", "standard_profile.json")
LOG_DIR     = os.path.join(_ROOT, "data", "live_signals")
N_BARS      = 2000

# Toleranta sub-pip pentru entry/sl/tp
TOL_PRICE = 1e-7


# ── Incarcare log live ───────────────────────────────────────────────────────

def load_live_log(log_dir: str, all_logs: bool = False) -> pd.DataFrame:
    """
    Implicit: citeste DOAR cel mai recent signals_*.csv (o sesiune).
    Cu --all-logs: uneste toate sesiunile si deduplicheaza pe (bar_time, symbol).
    """
    files = sorted(glob.glob(os.path.join(log_dir, "signals_*.csv")))
    if not files:
        raise FileNotFoundError(
            f"Nu am gasit fisiere signals_*.csv in {log_dir}\n"
            "Ruleaza live_runner.py cel putin un ciclu inainte de comparatie."
        )

    to_load = files if all_logs else [files[-1]]
    print(f"    Fisier(e) citite: {[os.path.basename(f) for f in to_load]}")

    frames = []
    for f in to_load:
        df = pd.read_csv(f)
        df["_source_file"] = os.path.basename(f)
        frames.append(df)

    live = pd.concat(frames, ignore_index=True)
    live["bar_time"]   = pd.to_datetime(live["bar_time"])
    live["cycle_time"] = pd.to_datetime(live["cycle_time"])
    live["setup"] = (
        live["setup"].astype(str).str.strip().str.lower()
        .map({"true": True, "false": False, "1": True, "0": False})
        .fillna(False)
    )

    live = live.sort_values("cycle_time").drop_duplicates(
        subset=["bar_time", "symbol"], keep="first"
    ).reset_index(drop=True)

    # Filtreaza doar perechile valide din configuratia actuala
    live = live[live["symbol"].isin(SYMBOLS)].reset_index(drop=True)

    return live


# ── Re-detectie ──────────────────────────────────────────────────────────────

def _redetect_bar(df: pd.DataFrame, bar_time: pd.Timestamp,
                  symbol: str, cfg: dict,
                  balance: float, usdjpy_close: float) -> dict:
    """
    Re-ruleaza exact aceleasi filtre si detect_setup ca live_runner._scan().
    Aliniata la baseline-ul oficial: ONLY_LONG=True, ATR cap doar EURUSD.
    """
    mask = df["time"] == bar_time
    if not mask.any():
        return {"found": False, "bar_time": bar_time, "symbol": symbol,
                "setup": None, "skip_reason": "bara_absenta_in_MT5"}

    j   = int(df.index[mask][0])
    row = df.iloc[j]
    t   = row["time"]
    pip = pip_size(symbol)
    sh  = cfg["session"]["start_hour"]
    eh  = cfg["session"]["end_hour"]

    in_session = (sh <= t.hour < eh)

    base = dict(found=True, bar_time=t, symbol=symbol,
                in_session=in_session, setup=False, direction="NONE",
                entry=None, sl=None, tp=None, lots=None,
                R=None, n_opt=None, atr_pips=None, skip_reason="")

    if SKIP_MONDAY and t.weekday() == 0:
        return {**base, "skip_reason": "skip_monday"}
    if t.hour in SKIP_HOURS:
        return {**base, "skip_reason": f"skip_hour_{t.hour}"}
    if not in_session:
        return {**base, "skip_reason": "out_of_session"}

    trend = row.get("trend", 0)
    if pd.isna(trend) or trend == 0:
        return {**base, "skip_reason": "no_trend"}

    atr_val  = row.get("atr", float("nan"))
    atr_pips = round(atr_val / pip, 1) if not pd.isna(atr_val) else None
    cap = ATR_MAX_PIPS.get(symbol)
    if cap and atr_pips is not None and atr_pips > cap:
        return {**base, "skip_reason": "atr_cap", "atr_pips": atr_pips}

    direction = int(trend)
    if ONLY_LONG and direction == -1:
        return {**base, "skip_reason": "only_long", "atr_pips": atr_pips}

    found = detect_setup(df, j, direction, window=PULLBACK_WINDOW)
    if found is None:
        return {**base, "skip_reason": "no_setup", "atr_pips": atr_pips}

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

    rp_base_v = cfg["account"]["risk_per_trade_pct"] / 100.0
    rp_all_v  = cfg["account"].get("risk_per_trade_pct_all_criteria",
                                   cfg["account"]["risk_per_trade_pct"]) / 100.0
    rp = rp_all_v if n_opt >= 2 else rp_base_v

    pv      = pip_value_usd(symbol, entry, usdjpy_close)
    sl_pips = risk_dist / pip
    lots    = (balance * rp) / (sl_pips * pv) if sl_pips > 0 and pv > 0 else 0.0
    lots    = math.floor(lots / 0.01) * 0.01

    return dict(
        found=True, bar_time=t, symbol=symbol,
        in_session=True, skip_reason="",
        setup=True, direction="BUY" if direction == 1 else "SELL",
        entry=round(entry, 5), sl=round(sl, 5), tp=round(tp, 5),
        lots=round(lots, 2), R=R, n_opt=n_opt, atr_pips=atr_pips,
    )


# ── Comparatie rand cu rand ───────────────────────────────────────────────────

def _compare(live_row: pd.Series, redet: dict, pip: float) -> list[str]:
    """
    Returneaza lista de discrepante (goala = potrivire perfecta).
    Compara: setup da/nu, direction, entry/sl/tp (toleranta sub-pip), R, n_opt.
    Lots exclus: depinde de balanta la momentul ciclului live.
    """
    issues = []
    l_setup = bool(live_row["setup"])
    r_setup = bool(redet["setup"])

    if l_setup != r_setup:
        issues.append(
            f"SETUP live={l_setup}({live_row.get('skip_reason','')}) "
            f"redet={r_setup}({redet.get('skip_reason','')})"
        )
        return issues

    if not l_setup:
        return issues  # ambele: no-setup, acord

    if str(live_row.get("direction", "")) != str(redet.get("direction", "")):
        issues.append(
            f"direction live={live_row['direction']} redet={redet['direction']}"
        )

    for field in ("entry", "sl", "tp"):
        lv = live_row.get(field)
        rv = redet.get(field)
        try:
            lv, rv = float(lv), float(rv)
        except (TypeError, ValueError):
            issues.append(f"{field} neparsabil live={lv} redet={rv}")
            continue
        if abs(lv - rv) > TOL_PRICE:
            issues.append(
                f"{field} live={lv:.5f} redet={rv:.5f} "
                f"diff={abs(lv-rv)/pip:.4f}pips"
            )

    try:
        if live_row.get("R") is not None and redet.get("R") is not None:
            if float(live_row["R"]) != float(redet["R"]):
                issues.append(f"R live={live_row['R']} redet={redet['R']}")
    except (TypeError, ValueError):
        pass

    try:
        if live_row.get("n_opt") is not None and redet.get("n_opt") is not None:
            if int(float(live_row["n_opt"])) != int(float(redet["n_opt"])):
                issues.append(f"n_opt live={live_row['n_opt']} redet={redet['n_opt']}")
    except (TypeError, ValueError):
        pass

    return issues


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Compara detectia live_runner cu re-detectia pe aceleasi bare"
    )
    parser.add_argument("--log-dir", default=LOG_DIR,
                        help=f"Director cu signals_*.csv (implicit: {LOG_DIR})")
    parser.add_argument("--all-logs", action="store_true",
                        help="Uneste toate sesiunile din log-dir (implicit: doar cel mai recent)")
    args = parser.parse_args()

    sep = "=" * 68

    print(sep)
    print("  compare_live_vs_backtest.py  --  Faza 1, Pasul 3")
    print("  Sursa bare re-detectie : MT5")
    print("  Motiv                  : CSV historic nu acopera perioada live;")
    print("                           Mt5DataSource livreaza aceleasi bare")
    print("                           ca live_runner (barele M15 inchise sunt imutabile).")
    print(f"  Config                 : ONLY_LONG={ONLY_LONG} | ATR={ATR_MAX_PIPS}")
    print(f"  Perechi                : {SYMBOLS}")
    print(f"  Rata USDJPY            : din {SYMBOLS_RATE} (incarcat separat, nu logat)")
    print(sep)

    # ── 1. Citeste log live ──────────────────────────────────────────────
    print(f"\n[1] Citesc log din: {args.log_dir}")
    live = load_live_log(args.log_dir, all_logs=args.all_logs)

    t_min = live["bar_time"].min()
    t_max = live["bar_time"].max()
    n_setup_live = int(live["setup"].sum())
    print(f"    {len(live)} randuri dupa deduplicare  |  simboluri: {sorted(live['symbol'].unique())}")
    print(f"    Fereastra bar_time: {t_min}  ->  {t_max}")
    print(f"    Setup-uri in log: {n_setup_live}  |  fara setup: {len(live)-n_setup_live}")

    # ── 2. Conectare MT5 si preparare date ───────────────────────────────
    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)

    print(f"\n[2] Conectez la MT5 ...")
    src = Mt5DataSource(n_bars=N_BARS)
    try:
        acc = src.connect()
    except RuntimeError as e:
        print(f"    EROARE: {e}")
        sys.exit(1)

    balance = acc.balance
    print(f"    Login: {acc.login}  |  Server: {acc.server}  |  DEMO OK")
    print(f"    Balanta: {balance} {acc.currency}  (lots re-detectate pot diferi)")

    # Perechi de tranzactionat
    symbols_in_log = sorted(live["symbol"].unique())
    prepared: dict[str, pd.DataFrame] = {}
    for sym in symbols_in_log:
        try:
            prepared[sym] = prepare_symbol(src, sym, cfg)
            df_ = prepared[sym]
            print(f"    {sym}: {len(df_)} bare  "
                  f"({df_['time'].min().strftime('%Y-%m-%d')} -> "
                  f"{df_['time'].max().strftime('%Y-%m-%d')})")
        except Exception as e:
            print(f"    [!] {sym}: eroare prepare_symbol -- {e}")

    # USDJPY ca rata de conversie (separat, nu tranzactionat)
    usdjpy_close = 150.0
    for sym in SYMBOLS_RATE:
        try:
            uj_df = prepare_symbol(src, sym, cfg)
            if len(uj_df) >= 2:
                usdjpy_close = float(uj_df["close"].iloc[-2])
                print(f"    USDJPY (rata): {usdjpy_close:.4f}  (bara inchisa)")
        except Exception as e:
            print(f"    [!] USDJPY rata: eroare -- {e} (fallback 150.0)")

    src.disconnect()

    # ── 3. Re-detectie bara cu bara ──────────────────────────────────────
    print(f"\n[3] Re-detectie ({len(live)} randuri) ...")

    redet_rows = []
    for sym in symbols_in_log:
        df = prepared.get(sym)
        if df is None:
            continue
        for bt in live.loc[live["symbol"] == sym, "bar_time"].unique():
            r = _redetect_bar(df, pd.Timestamp(bt), sym, cfg, balance, usdjpy_close)
            redet_rows.append(r)

    redet_df = pd.DataFrame(redet_rows)
    n_absent = int((redet_df["found"] == False).sum())
    if n_absent:
        print(f"    [!] {n_absent} bara/bare absente in MT5 (weekend/sarbatoare):")
        for _, row in redet_df[redet_df["found"] == False].iterrows():
            print(f"        {row['bar_time']}  {row['symbol']}")

    # ── 4. Aliniere pe intersectia de bare ───────────────────────────────
    print(f"\n[4] Aliniere pe (bar_time, symbol) ...")

    def _key(r):
        return (str(r["bar_time"]), r["symbol"])

    live_keys   = set(live.apply(_key, axis=1))
    redet_found = redet_df[redet_df["found"] == True].copy()
    redet_keys  = set(redet_found.apply(_key, axis=1))
    common_keys = live_keys & redet_keys

    live_c  = live[live.apply(_key, axis=1).isin(common_keys)].copy()
    redet_c = redet_found[redet_found.apply(_key, axis=1).isin(common_keys)].copy()
    redet_c = redet_c.rename(columns={
        c: f"r_{c}" for c in redet_c.columns if c not in ("bar_time", "symbol")
    })

    merged = pd.merge(live_c, redet_c, on=["bar_time", "symbol"], how="inner")

    n_match = 0; n_mismatch = 0; mismatches = []
    for _, row in merged.iterrows():
        sym = row["symbol"]
        pip = pip_size(sym)
        redet_dict = {
            "found": True,
            "setup": row["r_setup"],
            "direction": row.get("r_direction", "NONE"),
            "entry": row.get("r_entry"), "sl": row.get("r_sl"), "tp": row.get("r_tp"),
            "R": row.get("r_R"), "n_opt": row.get("r_n_opt"),
            "skip_reason": row.get("r_skip_reason", ""),
        }
        issues = _compare(row, redet_dict, pip)
        if issues:
            n_mismatch += 1
            mismatches.append({"bar_time": row["bar_time"], "symbol": sym,
                                "issues": issues,
                                "l_lots": row.get("lots"), "r_lots": row.get("r_lots")})
        else:
            n_match += 1

    # ── 5. Raport final ───────────────────────────────────────────────────
    n_setup_redet = int(redet_c["r_setup"].sum()) if "r_setup" in redet_c.columns else 0
    fidelity = n_match / len(common_keys) * 100 if common_keys else 0.0

    print()
    print(sep)
    print("  RAPORT COMPARATIE  --  LIVE vs RE-DETECTIE")
    print(sep)
    print(f"  Randuri log live (dupa dedup)  : {len(live)}")
    print(f"  Bare comune (intersectie)      : {len(common_keys)}")
    if live_keys - redet_keys:
        print(f"  Bare doar in live (absente MT5): {len(live_keys - redet_keys)}")
    if redet_keys - live_keys:
        print(f"  Bare noi in MT5 (post-sesiune) : {len(redet_keys - live_keys)}")
    print(f"  Setup-uri log live             : {n_setup_live}")
    print(f"  Setup-uri re-detectate         : {n_setup_redet}")
    print(f"  Potriviri exacte               : {n_match}")
    print(f"  Nepotriviri                    : {n_mismatch}")
    print(f"  Fidelitate                     : {fidelity:.1f}%  ({n_match}/{len(common_keys)})")

    if mismatches:
        print(f"\n  LISTA NEPOTRIVIRI ({len(mismatches)}):")
        print("  " + "-" * 64)
        for m in mismatches:
            lots_note = ""
            if m["l_lots"] is not None and m["r_lots"] is not None:
                lots_note = f"  [lots live={m['l_lots']} redet={m['r_lots']}]"
            for issue in m["issues"]:
                print(f"  {m['bar_time']}  {m['symbol']:6s}  {issue}{lots_note}")
    else:
        print("\n  Toate barele comune se potrivesc perfect.")

    print(sep)
    print("""
  NOTE:
  - Lots exclus din fidelitate: depind de balanta la ciclul live.
  - Nepotriviri din mark_swings: IMPOSIBILE cu fixul de lookahead activ.
    Swing-ul cel mai recent folosit (k=j-3) are fereastra [j-6:j-1] --
    toate bare inchise la momentul live, imutabile la re-detectie.
  - Daca log-ul are doar bare out_of_session, ruleaza live_runner in
    sesiune (10:00-18:00 ora RO) pentru a acumula setup-uri reale.
  - Foloseste --all-logs pentru a compara toate sesiunile acumulate.
""")


if __name__ == "__main__":
    main()
