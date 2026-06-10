"""
Generator de semnale live — engine generic
==========================================
Folosit de session1_m15_long.py si session2_m5_both.py.
Nu se ruleaza direct — ruleaza una dintre sesiuni.

Fiecare sesiune are config propriu (piete, TF, directie, sesiune, output).
Sesiunile sunt complet independente: capital separat, loguri separate.
"""

import os
import sys
import json
import time
import pickle
import logging
import subprocess
from datetime import datetime, timedelta

import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest import CONFIG, DATA_DIR
from adapters.mt5_source import Mt5DataSource
from strategy.preparation import _enrich
from strategy.structure import detect_setup
from strategy.signals import pip_size, count_optional, reward_R


# ---------------------------------------------------------------------------
# Notificari Windows
# ---------------------------------------------------------------------------

try:
    import MetaTrader5 as _mt5_exec
except ImportError:
    _mt5_exec = None


def _calc_lots(symbol: str, entry: float, sl: float,
               capital: float, risk_pct: float) -> float:
    """Calculeaza lotajul bazat pe capitalul virtual si riscul per trade."""
    if _mt5_exec is None:
        return 0.01
    info = _mt5_exec.symbol_info(symbol)
    if info is None:
        return 0.01
    pip     = pip_size(symbol)
    sl_pips = abs(entry - sl) / pip
    if sl_pips <= 0 or info.trade_tick_size <= 0:
        return info.volume_min
    pip_val = info.trade_tick_value / info.trade_tick_size * pip
    if pip_val <= 0:
        return info.volume_min
    raw  = (capital * risk_pct) / (sl_pips * pip_val)
    step = info.volume_step if info.volume_step > 0 else 0.01
    lot  = max(info.volume_min, (raw // step) * step)
    return round(lot, 2)


def _place_order(sig: dict, lots: float, expire_bars: int,
                 bar_minutes: int, log) -> int | None:
    """
    Plaseaza ordin pending BUY_STOP/SELL_STOP in MT5.
    Returneaza ticket-ul MT5 sau None la esec/respingere.
    """
    if _mt5_exec is None:
        log.warning("  [EXEC] MetaTrader5 indisponibil.")
        return None

    symbol    = sig["symbol"]
    direction = sig["direction"]

    # Verifica ca pretul nu a fost deja depasit (BUY_STOP must be > Ask)
    tick = _mt5_exec.symbol_info_tick(symbol)
    if tick is not None:
        if direction == 1 and tick.ask >= sig["entry"]:
            log.warning(f"  [EXEC] {sig['signal_id']}: BUY_STOP ignorat "
                        f"(Ask {tick.ask:.5f} >= entry {sig['entry']:.5f})")
            return None
        if direction == -1 and tick.bid <= sig["entry"]:
            log.warning(f"  [EXEC] {sig['signal_id']}: SELL_STOP ignorat "
                        f"(Bid {tick.bid:.5f} <= entry {sig['entry']:.5f})")
            return None

    order_type = (_mt5_exec.ORDER_TYPE_BUY_STOP
                  if direction == 1 else _mt5_exec.ORDER_TYPE_SELL_STOP)
    exp_time   = datetime.now() + timedelta(minutes=expire_bars * bar_minutes)

    request = {
        "action":    _mt5_exec.TRADE_ACTION_PENDING,
        "symbol":    symbol,
        "volume":    lots,
        "type":      order_type,
        "price":     sig["entry"],
        "sl":        sig["sl"],
        "tp":        sig["tp"],
        "expiration": exp_time,
        "type_time":  _mt5_exec.ORDER_TIME_SPECIFIED,
        "comment":    sig["signal_id"][:31],
    }

    # Incearca moduri de umplere in ordine (difera per broker)
    for filling in [_mt5_exec.ORDER_FILLING_RETURN,
                    _mt5_exec.ORDER_FILLING_IOC,
                    _mt5_exec.ORDER_FILLING_FOK]:
        request["type_filling"] = filling
        result = _mt5_exec.order_send(request)
        if result is None:
            continue
        if result.retcode == _mt5_exec.TRADE_RETCODE_DONE:
            dir_str = "LONG" if direction == 1 else "SHORT"
            log.info(f"  [EXEC] *** ORDIN: {sig['signal_id']} {symbol} {dir_str} "
                     f"{lots}lot @ {sig['entry']:.5f}  "
                     f"SL={sig['sl']:.5f}  TP={sig['tp']:.5f}  "
                     f"ticket=#{result.order}")
            return result.order
        if result.retcode != 10030:   # 10030 = INVALID_FILL — incearca urmatorul
            log.warning(f"  [EXEC] {sig['signal_id']}: RESPINS "
                        f"retcode={result.retcode} ({result.comment})")
            return None

    log.warning(f"  [EXEC] {sig['signal_id']}: niciun mod de umplere acceptat.")
    return None


def _notify_signal(sig: dict, session_id: str) -> None:
    """
    Notificare Windows Toast + terminal bell la detectarea unui semnal nou.
    Non-blocking (Popen). Esecul notificarii nu opreste sesiunea.
    """
    # Bell in terminal — face tab-ul/taskbar-ul VSCode sa clipeasca
    sys.stdout.write("\a")
    sys.stdout.flush()

    try:
        sym   = sig["symbol"]
        # Format pret: BTC/ETH cu 2 zecimale, FX cu 5
        fmt   = ".2f" if sig["entry"] > 100 else ".5f"
        entry = format(sig["entry"], fmt)
        tp    = format(sig["tp"],    fmt)
        sl    = format(sig["sl"],    fmt)

        title = f"Signal {sig['dir_str']} {sym}"
        body  = f"{session_id} | entry {entry}  SL {sl}  TP {tp}  ({sig['r_ratio']:.1f}R)"

        # Escape single quotes din valori (evita injectie in PS string)
        title = title.replace("'", "`'")
        body  = body.replace("'",  "`'")

        ps = (
            "[Windows.UI.Notifications.ToastNotificationManager,"
            "Windows,ContentType=WindowsRuntime]|Out-Null;"
            "$xml=[Windows.UI.Notifications.ToastNotificationManager]::"
            "GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02);"
            f"$xml.GetElementsByTagName('text')[0].AppendChild($xml.CreateTextNode('{title}'))|Out-Null;"
            f"$xml.GetElementsByTagName('text')[1].AppendChild($xml.CreateTextNode('{body}'))|Out-Null;"
            "$toast=[Windows.UI.Notifications.ToastNotification]::new($xml);"
            "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('TradingBot').Show($toast)"
        )
        subprocess.Popen(
            ["powershell", "-WindowStyle", "Hidden", "-NonInteractive", "-Command", ps],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass  # notificarea nu trebuie sa opreasca vreodata sesiunea


# ---------------------------------------------------------------------------
# Helpers timp
# ---------------------------------------------------------------------------

def _next_bar_close(bar_minutes: int) -> datetime:
    now = datetime.now()
    mod = now.minute % bar_minutes
    mins_to_next = bar_minutes - mod
    nxt = now + timedelta(minutes=mins_to_next)
    return nxt.replace(second=5, microsecond=0)


def _sleep_to_next_bar(bar_minutes: int, log):
    nxt = _next_bar_close(bar_minutes)
    wait = (nxt - datetime.now()).total_seconds()
    if wait > 0:
        log.info(f"  Urmatoarea bara {bar_minutes}min @ {nxt.strftime('%H:%M:%S')} — {wait:.0f}s")
        time.sleep(wait)


# ---------------------------------------------------------------------------
# Rezolutie simbol (pentru indici cu alias broker)
# ---------------------------------------------------------------------------

def _resolve_symbol(src: Mt5DataSource, name: str, fallbacks: dict,
                    entry_tf: str = "M15") -> str | None:
    candidates = fallbacks.get(name, [name])
    for c in candidates:
        try:
            df = src.load_bars(c, entry_tf)
            if df is not None and len(df) > 0:
                return c
        except Exception:
            pass
    return None


# ---------------------------------------------------------------------------
# Pregatire date live
# ---------------------------------------------------------------------------

def _prepare_live(src: Mt5DataSource, symbol: str, cfg: dict,
                  entry_tf: str, trend_tf: str,
                  n_bars_entry: int, n_bars_trend: int, log) -> pd.DataFrame | None:
    src._n_bars = n_bars_entry
    try:
        entry_df = src.load_bars(symbol, entry_tf)
    except Exception as e:
        log.warning(f"  {symbol}: eroare {entry_tf} — {e}")
        return None

    src._n_bars = n_bars_trend
    try:
        trend_df = src.load_bars(symbol, trend_tf)
    except Exception as e:
        log.warning(f"  {symbol}: eroare {trend_tf} — {e}")
        return None

    try:
        return _enrich(entry_df, trend_df, cfg)
    except Exception as e:
        log.warning(f"  {symbol}: eroare enrich — {e}")
        return None


# ---------------------------------------------------------------------------
# Verificare semnale noi
# ---------------------------------------------------------------------------

def _check_signals(df: pd.DataFrame, symbol: str, cfg: dict,
                   state: dict, session_cfg: dict) -> list[dict]:
    sigs = []
    pip    = pip_size(symbol)
    buf    = 2 * pip
    pw     = session_cfg["pullback_window"]
    only_long = session_cfg["only_long"]

    # Sesiunea pentru acest simbol specific
    sym_sessions = session_cfg.get("symbol_sessions", {})
    s_start, s_end = sym_sessions.get(symbol,
                     (session_cfg["session_start"], session_cfg["session_end"]))
    skip_hours    = session_cfg.get("skip_hours", ())
    skip_monday   = session_cfg.get("skip_monday", True)
    skip_weekdays = set(session_cfg.get("skip_weekdays", []))

    n = len(df)
    for offset in range(3, 0, -1):
        j = n - offset
        if j < 60:
            continue

        row = df.iloc[j]
        t   = pd.Timestamp(row["time"])

        if not (s_start <= t.hour < s_end):
            continue
        if skip_monday and t.weekday() == 0:
            continue
        if skip_weekdays and t.weekday() in skip_weekdays:
            continue
        if t.hour in skip_hours:
            continue

        last_t = state["last_checked"].get(symbol)
        if last_t is not None and t <= last_t:
            continue

        if row.get("trend", 0) == 0 or pd.isna(row.get("trend")):
            continue

        direction = int(row["trend"])
        if only_long and direction == -1:
            continue

        found = detect_setup(df, j, direction, window=pw)
        if found is None:
            continue

        ext, _ = found

        if direction == 1:
            entry = row["high"] + buf
            sl    = ext - buf
        else:
            entry = row["low"] - buf
            sl    = ext + buf

        risk_dist = abs(entry - sl)
        if risk_dist <= 0:
            continue

        n_opt = count_optional(row, direction, cfg)
        R     = reward_R(n_opt, cfg)
        tp    = entry + direction * risk_dist * R

        state["signal_counter"] += 1
        sig_id = f"{session_cfg['session_id']}-SIG{state['signal_counter']:04d}"

        sigs.append({
            "signal_id": sig_id,
            "time":      t,
            "symbol":    symbol,
            "direction": direction,
            "dir_str":   "LONG" if direction == 1 else "SHORT",
            "entry":     round(entry, 5),
            "sl":        round(sl, 5),
            "tp":        round(tp, 5),
            "r_ratio":   round(R, 1),
            "atr_pips":  round(row.get("atr", 0) / pip, 1),
            "n_optional": n_opt,
            "rsi":       round(row.get("rsi", 0), 1),
        })

    return sigs


# ---------------------------------------------------------------------------
# Update outcome-uri
# ---------------------------------------------------------------------------

_OUTCOMES_COLS = [
    "signal_id", "time_check", "symbol", "direction", "status",
    "entry", "sl", "tp", "r_ratio", "triggered_at",
    "exit_price", "exit_time", "result_r",
]


def _update_outcomes(df: pd.DataFrame, symbol: str,
                     state: dict, outcomes_file: str, log,
                     expire_bars: int = 4, bar_minutes: int = 15):
    if symbol not in state["pending"]:
        return

    rows_to_remove = []
    outcome_rows   = []
    expire_delta   = timedelta(minutes=expire_bars * bar_minutes)
    current_bar_t  = pd.Timestamp(df.iloc[-2]["time"]) if len(df) >= 2 else None

    for sig_id, p in list(state["pending"].get(symbol, {}).items()):
        df_post = df[df["time"] > p["armed_at"]]
        if df_post.empty:
            continue

        d = p["direction"]

        if not p.get("triggered"):
            # Expira dupa expire_bars bare fara trigger
            if current_bar_t is not None:
                armed = pd.Timestamp(p["armed_at"])
                if current_bar_t - armed > expire_delta:
                    outcome_rows.append({**p, "signal_id": sig_id,
                                         "symbol": symbol,
                                         "status": "expirat", "result_r": 0.0,
                                         "exit_time": current_bar_t,
                                         "time_check": datetime.now()})
                    rows_to_remove.append(sig_id)
                    log.info(f"  EXPIRAT: {sig_id} {symbol} (>{expire_bars} bare fara trigger)")
                    continue

            for _, bar in df_post.iterrows():
                inv  = (d == 1 and bar["low"]  < p["sl"]) or \
                       (d == -1 and bar["high"] > p["sl"])
                trig = (d == 1 and bar["high"] >= p["entry"]) or \
                       (d == -1 and bar["low"]  <= p["entry"])
                if inv:
                    outcome_rows.append({**p, "signal_id": sig_id,
                                         "symbol": symbol,
                                         "status": "invalidat", "result_r": 0.0,
                                         "time_check": datetime.now()})
                    rows_to_remove.append(sig_id)
                    break
                if trig:
                    p["triggered"]    = True
                    p["triggered_at"] = bar["time"]
                    log.info(f"  TRIGGERAT: {sig_id} {symbol} "
                             f"{'LONG' if d==1 else 'SHORT'} @ {p['entry']:.5f}")
                    break

        if p.get("triggered") and sig_id not in rows_to_remove:
            df_aft = df[df["time"] > p["triggered_at"]]
            for _, bar in df_aft.iterrows():
                sl_hit = (d == 1 and bar["low"]  <= p["sl"]) or \
                         (d == -1 and bar["high"] >= p["sl"])
                tp_hit = (d == 1 and bar["high"] >= p["tp"]) or \
                         (d == -1 and bar["low"]  <= p["tp"])
                if sl_hit:
                    outcome_rows.append({**p, "signal_id": sig_id,
                                         "symbol": symbol, "status": "SL",
                                         "result_r": -1.0, "exit_price": p["sl"],
                                         "exit_time": bar["time"],
                                         "time_check": datetime.now()})
                    rows_to_remove.append(sig_id)
                    log.info(f"  PIERDERE: {sig_id} SL -1.0R")
                    break
                if tp_hit:
                    outcome_rows.append({**p, "signal_id": sig_id,
                                         "symbol": symbol, "status": "TP",
                                         "result_r": p["r_ratio"], "exit_price": p["tp"],
                                         "exit_time": bar["time"],
                                         "time_check": datetime.now()})
                    rows_to_remove.append(sig_id)
                    log.info(f"  PROFIT: {sig_id} TP +{p['r_ratio']:.1f}R")
                    break

    if outcome_rows:
        pd.DataFrame(outcome_rows).reindex(columns=_OUTCOMES_COLS).to_csv(
            outcomes_file, mode="a", header=False, index=False)

    for sig_id in rows_to_remove:
        state["pending"][symbol].pop(sig_id, None)


# ---------------------------------------------------------------------------
# Engine principal
# ---------------------------------------------------------------------------

def run_generator(session_cfg: dict):
    """
    Ruleaza generatorul de semnale cu configuratia data.
    session_cfg: dict cu toti parametrii sesiunii (vezi session1/session2).
    """
    out_dir      = session_cfg["output_dir"]
    signals_file = os.path.join(out_dir, "signals.csv")
    outcomes_file = os.path.join(out_dir, "outcomes.csv")
    state_file   = os.path.join(out_dir, "state.pkl")
    log_file     = os.path.join(out_dir, "generator.log")

    os.makedirs(out_dir, exist_ok=True)

    # Logger per sesiune
    log = logging.getLogger(session_cfg["session_id"])
    log.setLevel(logging.INFO)
    if not log.handlers:
        fmt = logging.Formatter("%(asctime)s  %(message)s", "%Y-%m-%d %H:%M:%S")
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(fmt)
        log.addHandler(sh)
        log.addHandler(fh)

    # Init CSV-uri
    if not os.path.exists(signals_file):
        pd.DataFrame(columns=[
            "signal_id", "time", "symbol", "direction", "dir_str",
            "entry", "sl", "tp", "r_ratio", "atr_pips", "n_optional", "rsi",
        ]).to_csv(signals_file, index=False)
    if not os.path.exists(outcomes_file):
        pd.DataFrame(columns=[
            "signal_id", "time_check", "symbol", "direction", "status",
            "entry", "sl", "tp", "r_ratio", "triggered_at",
            "exit_price", "exit_time", "result_r",
        ]).to_csv(outcomes_file, index=False)

    # Incarca stare
    state = (pickle.load(open(state_file, "rb"))
             if os.path.exists(state_file)
             else {"pending": {}, "signal_counter": 0, "last_checked": {}})
    state.setdefault("mt5_tickets", {})   # ticket MT5 per signal_id

    with open(CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)
    cfg["optional_criteria"]["rsi"]["sell_max"] = 60  # RSI simetric pentru SELL

    log.info("=" * 65)
    log.info(f"  {session_cfg['session_id']} — {session_cfg['description']}")
    log.info(f"  Piete: {session_cfg['markets']}")
    log.info(f"  TF: {session_cfg['entry_tf']} (trend {session_cfg['trend_tf']}) | "
             f"PW={session_cfg['pullback_window']} | "
             f"{'BOTH' if not session_cfg['only_long'] else 'LONG'}")
    log.info(f"  Output: {out_dir}")
    log.info("=" * 65)

    src = Mt5DataSource(n_bars=session_cfg["n_bars_entry"])
    try:
        acc = src.connect()
        log.info(f"MT5: {acc.login} @ {acc.server} "
                 f"({'DEMO' if acc.trade_mode == 0 else 'LIVE'})")
    except Exception as e:
        log.error(f"MT5 nu e disponibil: {e}")
        return

    # Rezolva simbolurile
    fallbacks = session_cfg.get("symbol_fallbacks", {})
    resolved  = {}
    for m in session_cfg["markets"]:
        sym = _resolve_symbol(src, m, fallbacks, session_cfg["entry_tf"])
        if sym:
            resolved[m] = sym
        else:
            log.warning(f"  {m}: nu e disponibil — sarit")

    log.info(f"Simboluri active: {list(resolved.values())}")
    log.info("Pornit. Ctrl+C pentru oprire.\n")

    bar_min = session_cfg["bar_minutes"]
    iteration = 0

    while True:
        try:
            iteration += 1
            log.info(f"--- {session_cfg['session_id']} iter {iteration} "
                     f"@ {datetime.now().strftime('%H:%M:%S')} ---")

            new_sigs = 0
            for market, symbol in resolved.items():
                df = _prepare_live(
                    src, symbol, cfg,
                    session_cfg["entry_tf"], session_cfg["trend_tf"],
                    session_cfg["n_bars_entry"], session_cfg["n_bars_trend"], log,
                )
                if df is None or len(df) < 100:
                    continue

                _update_outcomes(df, symbol, state, outcomes_file, log,
                                expire_bars=session_cfg.get("expire_bars", 4),
                                bar_minutes=session_cfg["bar_minutes"])

                sigs = _check_signals(df, symbol, cfg, state, session_cfg)
                for sig in sigs:
                    pd.DataFrame([sig]).to_csv(signals_file, mode="a",
                                               header=False, index=False)
                    state["pending"].setdefault(symbol, {})[sig["signal_id"]] = {
                        "direction": sig["direction"],
                        "entry":     sig["entry"],
                        "sl":        sig["sl"],
                        "tp":        sig["tp"],
                        "r_ratio":   sig["r_ratio"],
                        "armed_at":  sig["time"],
                        "triggered": False,
                    }
                    log.info(
                        f"  *** SEMNAL: {sig['signal_id']} {symbol} {sig['dir_str']} "
                        f"entry={sig['entry']:.5f} sl={sig['sl']:.5f} tp={sig['tp']:.5f} "
                        f"({sig['r_ratio']:.1f}R) RSI={sig['rsi']:.0f}"
                    )
                    _notify_signal(sig, session_cfg["session_id"])

                    # Executie demo/live
                    if session_cfg.get("execute_trades", False):
                        # Sizing dinamic: daca e setat account_fraction, foloseste
                        # equity-ul real din MT5 × fractie, altfel session_capital fix.
                        frac = session_cfg.get("account_fraction")
                        if frac and _mt5_exec is not None:
                            _ai = _mt5_exec.account_info()
                            capital = (_ai.equity * frac) if _ai else session_cfg.get("session_capital", 1000)
                            log.debug(
                                "sizing dinamic: equity=%.2f frac=%.3f capital=%.2f",
                                _ai.equity if _ai else 0, frac, capital,
                            )
                        else:
                            capital = session_cfg.get("session_capital", 1000)
                        risk_pct = session_cfg.get("risk_pct", 0.01)
                        lots   = _calc_lots(sig["symbol"], sig["entry"], sig["sl"],
                                            capital, risk_pct)
                        ticket = _place_order(sig, lots,
                                              session_cfg.get("expire_bars", 4),
                                              session_cfg["bar_minutes"], log)
                        if ticket:
                            state["mt5_tickets"][sig["signal_id"]] = ticket

                    new_sigs += 1

                if len(df) > 2:
                    state["last_checked"][symbol] = pd.Timestamp(df.iloc[-2]["time"])

            pending_n = sum(len(v) for v in state["pending"].values())
            if new_sigs == 0:
                log.info(f"  Niciun semnal nou. Pendinge: {pending_n}")

            with open(state_file, "wb") as f:
                pickle.dump(state, f)

            _sleep_to_next_bar(bar_min, log)

        except KeyboardInterrupt:
            log.info("\nOprire manuala.")
            with open(state_file, "wb") as f:
                pickle.dump(state, f)
            src.disconnect()

            # Sumar
            try:
                df_s = pd.read_csv(signals_file)
                df_o = pd.read_csv(outcomes_file)
                closed = df_o[df_o["status"].isin(["TP", "SL"])] if len(df_o) else pd.DataFrame()
                log.info(f"\n=== SUMAR {session_cfg['session_id']} ===")
                log.info(f"  Semnale: {len(df_s)}")
                if len(closed):
                    wins = (closed["result_r"] > 0).sum()
                    log.info(f"  Inchise: {len(closed)}  W:{wins}/L:{len(closed)-wins}")
                    log.info(f"  WR: {wins/len(closed)*100:.1f}% | "
                             f"Exp: {closed['result_r'].mean():+.3f}R")
            except Exception:
                pass
            break

        except Exception as e:
            import traceback
            log.error(f"Eroare: {e}\n{traceback.format_exc()}")
            log.info("Reincerc in 60s...")
            time.sleep(60)
