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
import urllib.request
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

# ---------------------------------------------------------------------------
# Telegram — citit din variabile de mediu (setate o singura data in Windows)
# ---------------------------------------------------------------------------
_TG_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
_TG_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


def _get_tg_creds() -> tuple[str, str]:
    """Env vars > data/telegram_config.json (configurat din UI)."""
    token, chat_id = _TG_TOKEN, _TG_CHAT_ID
    if not token or not chat_id:
        cfg_path = os.path.join(DATA_DIR, "telegram_config.json")
        if os.path.exists(cfg_path):
            try:
                with open(cfg_path, encoding="utf-8") as _f:
                    _cfg = json.load(_f)
                token   = token   or _cfg.get("token", "")
                chat_id = chat_id or _cfg.get("chat_id", "")
            except Exception:
                pass
    return token, chat_id


def _send_telegram(text: str) -> None:
    """Trimite mesaj Telegram. Non-blocking, esecul e ignorat silentios."""
    token, chat_id = _get_tg_creds()
    if not token or not chat_id:
        return
    try:
        payload = json.dumps({
            "chat_id":    chat_id,
            "text":       text,
            "parse_mode": "HTML",
        }).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass


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

    Return:
      int  (ticket) — ordin plasat cu succes
      None           — pret deja depasit la aceasta bara; semnal PASTRAT in pending,
                       incearca bara urmatoare (pretul poate reveni la entry)
      False          — eroare MT5 reala; semnal SCOS din pending
    """
    if _mt5_exec is None:
        log.warning("  [EXEC] MetaTrader5 indisponibil.")
        return False

    symbol    = sig["symbol"]
    direction = sig["direction"]

    # Daca pretul a depasit deja entry, nu plasam BUY_STOP/SELL_STOP acum.
    # Returnam None (nu False) — semnalul ramane in pending si va fi incercat
    # la bara urmatoare sau va expira normal dupa expire_bars.
    tick = _mt5_exec.symbol_info_tick(symbol)
    if tick is not None:
        if direction == 1 and tick.ask >= sig["entry"]:
            log.info(f"  [EXEC] {sig['signal_id']}: BUY_STOP amanat "
                     f"(Ask {tick.ask:.5f} >= entry {sig['entry']:.5f}) — retry bara urm.")
            return None
        if direction == -1 and tick.bid <= sig["entry"]:
            log.info(f"  [EXEC] {sig['signal_id']}: SELL_STOP amanat "
                     f"(Bid {tick.bid:.5f} <= entry {sig['entry']:.5f}) — retry bara urm.")
            return None

    order_type = (_mt5_exec.ORDER_TYPE_BUY_STOP
                  if direction == 1 else _mt5_exec.ORDER_TYPE_SELL_STOP)

    # Incearca toate modurile de umplere in ordine (bitmask-ul brokerului poate fi incorect).
    # RETURN primul — cel mai permisiv pentru ordine pending.
    sym_info = _mt5_exec.symbol_info(symbol)
    fm       = sym_info.filling_mode if sym_info else 0
    fill_modes = [
        _mt5_exec.ORDER_FILLING_RETURN,   # 2 — partial fill ok
        _mt5_exec.ORDER_FILLING_FOK,      # 0 — fill or kill
        _mt5_exec.ORDER_FILLING_IOC,      # 1 — immediate or cancel
    ]

    request = {
        "action":    _mt5_exec.TRADE_ACTION_PENDING,
        "symbol":    symbol,
        "volume":    lots,
        "type":      order_type,
        "price":     sig["entry"],
        "sl":        sig["sl"],
        "tp":        sig["tp"],
        "type_time": _mt5_exec.ORDER_TIME_GTC,
        "comment":   sig["signal_id"][:31],
    }

    all_none = True  # True daca niciun order_send nu a returnat macar un retcode
    for filling in fill_modes:
        request["type_filling"] = filling
        result = _mt5_exec.order_send(request)
        if result is None:
            err = _mt5_exec.last_error()
            log.warning(f"  [EXEC] {sig['signal_id']}: filling={filling} → result None "
                        f"(last_error={err})")
            continue
        all_none = False
        if result.retcode == _mt5_exec.TRADE_RETCODE_DONE:
            dir_str = "LONG" if direction == 1 else "SHORT"
            log.info(f"  [EXEC] *** ORDIN: {sig['signal_id']} {symbol} {dir_str} "
                     f"{lots}lot @ {sig['entry']:.5f}  "
                     f"SL={sig['sl']:.5f}  TP={sig['tp']:.5f}  "
                     f"ticket=#{result.order}")
            return result.order
        log.warning(f"  [EXEC] {sig['signal_id']}: filling={filling} → "
                    f"retcode={result.retcode} ({result.comment})")
        if result.retcode in (10026, 10027):
            # AutoTrading dezactivat (server sau client) — setare temporara, retry bara urm.
            log.warning(f"  [EXEC] {sig['signal_id']}: AutoTrading dezactivat — retry bara urm.")
            return None
        if result.retcode != 10030:   # alta eroare (pret, volum, etc) — nu are sens sa incercam alt fill
            return False

    # Ultima sansa: fara type_filling (lasa MT5 sa aleaga implicit)
    request.pop("type_filling", None)
    result = _mt5_exec.order_send(request)
    if result is not None:
        all_none = False
        log.warning(f"  [EXEC] {sig['signal_id']}: fara filling → "
                    f"retcode={result.retcode} ({result.comment})")
        if result.retcode == _mt5_exec.TRADE_RETCODE_DONE:
            dir_str = "LONG" if direction == 1 else "SHORT"
            log.info(f"  [EXEC] *** ORDIN (no-fill): {sig['signal_id']} {symbol} {dir_str} "
                     f"{lots}lot @ {sig['entry']:.5f}  ticket=#{result.order}")
            return result.order
    else:
        err = _mt5_exec.last_error()
        log.warning(f"  [EXEC] {sig['signal_id']}: fara filling → result None "
                    f"(last_error={err})")

    if all_none:
        # Toate order_send au returnat None — probabil eroare tranzitorie de conexiune MT5.
        # Pastram semnalul in pending si reincercam la bara urmatoare.
        log.warning(f"  [EXEC] {sig['signal_id']}: toate order_send → None "
                    f"(conexiune MT5?) — retry bara urm.")
        return None

    log.warning(f"  [EXEC] {sig['signal_id']}: niciun mod de umplere acceptat "
                f"(filling_mode={fm}, incercate={fill_modes} + fara filling).")
    return False


def _notify_signal(sig: dict, session_id: str) -> None:
    """
    Notificare Windows Toast + Telegram + terminal bell la detectarea unui semnal nou.
    Non-blocking. Esecul notificarii nu opreste sesiunea.
    """
    # Bell in terminal
    sys.stdout.write("\a")
    sys.stdout.flush()

    sym = sig["symbol"]
    fmt = ".2f" if sig["entry"] > 100 else ".5f"
    entry = format(sig["entry"], fmt)
    tp    = format(sig["tp"],    fmt)
    sl    = format(sig["sl"],    fmt)

    title = f"Signal {sig['dir_str']} {sym}"
    body  = f"{session_id} | entry {entry}  SL {sl}  TP {tp}  ({sig['r_ratio']:.1f}R)"

    # Telegram
    _send_telegram(
        f"<b>{title}</b>\n"
        f"Entry: <code>{entry}</code>\n"
        f"SL:    <code>{sl}</code>\n"
        f"TP:    <code>{tp}</code>\n"
        f"R/R:   {sig['r_ratio']:.1f}R\n"
        f"<i>{session_id}</i>"
    )

    # Windows Toast
    try:
        t = title.replace("'", "`'")
        b = body.replace("'",  "`'")
        ps = (
            "[Windows.UI.Notifications.ToastNotificationManager,"
            "Windows,ContentType=WindowsRuntime]|Out-Null;"
            "$xml=[Windows.UI.Notifications.ToastNotificationManager]::"
            "GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02);"
            f"$xml.GetElementsByTagName('text')[0].AppendChild($xml.CreateTextNode('{t}'))|Out-Null;"
            f"$xml.GetElementsByTagName('text')[1].AppendChild($xml.CreateTextNode('{b}'))|Out-Null;"
            "$toast=[Windows.UI.Notifications.ToastNotification]::new($xml);"
            "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('TradingBot').Show($toast)"
        )
        subprocess.Popen(
            ["powershell", "-WindowStyle", "Hidden", "-NonInteractive", "-Command", ps],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


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

    # Task 7: limite de pozitii simultane per simbol
    max_concurrent    = session_cfg.get("max_concurrent_per_market", 1)
    min_bars_between  = session_cfg.get("min_bars_between_trades", 0)
    tf_minutes = {"M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240}.get(
        session_cfg.get("entry_tf", "M15"), 15)

    # Sesiunea pentru acest simbol specific
    sym_sessions = session_cfg.get("symbol_sessions", {})
    s_start, s_end = sym_sessions.get(symbol,
                     (session_cfg["session_start"], session_cfg["session_end"]))
    skip_hours    = session_cfg.get("skip_hours", ())
    skip_monday   = session_cfg.get("skip_monday", True)
    skip_weekdays = set(session_cfg.get("skip_weekdays", []))

    n = len(df)
    # Offset 1 = bara curent deschisa (incompleta) — ignorata intentionat.
    # Semnalele se detecteaza doar pe bare INCHISE (offset 2 si 3).
    # Altfel, aceeasi bara poate fi detectata de doua ori: odata ca partiala
    # la offset=1, si din nou ca bara inchisa la offset=2 in iteratia urmatoare.
    for offset in range(3, 1, -1):
        j = n - offset
        if j < 60:
            continue

        row = df.iloc[j]
        t   = pd.Timestamp(row["time"])

        # Task 7: verifica limita de pozitii simultane (pending + triggerate)
        pending_for_sym = state["pending"].get(symbol, {})
        if len(pending_for_sym) >= max_concurrent:
            continue

        # Task 7: verifica distanta minima intre semnale (in bare)
        if min_bars_between > 0 and pending_for_sym:
            last_armed = max(
                (pd.Timestamp(p.get("armed_at", pd.Timestamp.min))
                 for p in pending_for_sym.values()),
                default=pd.Timestamp.min,
            )
            bars_since = (t - last_armed).total_seconds() / (tf_minutes * 60)
            if bars_since < min_bars_between:
                continue

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
# MT5 position reconciliation
# ---------------------------------------------------------------------------

def _check_mt5_position_closed(ticket: int, p: dict, log) -> dict | None:
    """
    Verifica daca pozitia MT5 cu ticket-ul dat a fost inchisa.

    Returns:
      dict cu status/result_r/exit_price/exit_time  — pozitia e inchisa
      None                                           — inca deschisa / pending / neconcludent
    """
    if _mt5_exec is None:
        return None

    # Ordin inca pending (netriggerat)
    if _mt5_exec.orders_get(ticket=ticket):
        return None

    # Pozitie deschisa (triggerat, in curs)
    if _mt5_exec.positions_get(ticket=ticket):
        return None

    # Nu e nici pending nici deschisa — cautam in history deals
    # In netting mode ticket pozitie == ticket ordin; in hedging mode pot diferi
    deals = _mt5_exec.history_deals_get(position=ticket)
    if not deals:
        hist_orders = _mt5_exec.history_orders_get(ticket=ticket)
        if hist_orders:
            order = hist_orders[0]
            # ORDER_STATE: CANCELED=2, REJECTED=5, EXPIRED=6  (FILLED=4 nu e orfan)
            if order.state in (2, 5, 6):
                log.warning(
                    f"  [MT5] Ordin #{ticket} anulat/respins in MT5 "
                    f"(state={order.state}) — scos din tracking fara outcome"
                )
                return {"__no_outcome__": True}
            # Hedging mode: position_id poate diferi de order ticket (ordin executat)
            pos_id = getattr(order, "position_id", None)
            if pos_id and pos_id != ticket:
                # Pozitia inca deschisa in hedging mode
                if _mt5_exec.positions_get(ticket=pos_id):
                    return None
                deals = _mt5_exec.history_deals_get(position=pos_id)
                if deals:
                    log.info(
                        f"  [MT5] Hedging mode: ordin #{ticket} → pozitie #{pos_id}"
                    )
    if not deals:
        return None

    close_deal = next(
        (deal for deal in deals if deal.entry == _mt5_exec.DEAL_ENTRY_OUT),
        None,
    )
    if close_deal is None:
        return None

    exit_price = close_deal.price
    exit_time  = datetime.fromtimestamp(close_deal.time)
    d          = p["direction"]
    risk_dist  = abs(p["entry"] - p["sl"])

    if risk_dist <= 0:
        result_r, status = 0.0, "SL"
    else:
        result_r = round((exit_price - p["entry"]) * d / risk_dist, 3)
        status   = "TP" if result_r > 0 else "SL"

    log.info(
        f"  [MT5] Pozitie #{ticket} inchisa: "
        f"exit={exit_price}  result={result_r:+.3f}R  [{status}]"
    )
    return {
        "status":       status,
        "result_r":     result_r,
        "exit_price":   exit_price,
        "exit_time":    exit_time,
        "triggered_at": p.get("triggered_at", exit_time),
    }


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
                     expire_bars: int = 4, bar_minutes: int = 15,
                     session_id: str = "", execute_trades: bool = False,
                     session_cfg: dict = None):
    if symbol not in state["pending"]:
        return

    _be_cfg = None
    _be_on  = False
    if session_cfg is not None:
        _be_cfg = {
            "enabled":         session_cfg.get("break_even_enabled", False),
            "trigger_pct":     session_cfg.get("be_trigger_pct",    80),
            "lock1_pct":       session_cfg.get("be_lock1_pct",      30),
            "lock2_pct":       session_cfg.get("be_lock2_pct",      50),
            "phase2_zone_pct": session_cfg.get("be_phase2_zone_pct", 40),
        }
        _be_on = _be_cfg["enabled"]

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
                    rows_to_remove.append(sig_id)
                    _ticket = state.get("mt5_tickets", {}).get(sig_id)
                    if _ticket and _mt5_exec is not None:
                        _r = _mt5_exec.order_send({
                            "action": _mt5_exec.TRADE_ACTION_REMOVE,
                            "order":  _ticket,
                        })
                        if _r and _r.retcode == _mt5_exec.TRADE_RETCODE_DONE:
                            log.info(f"  [EXEC] {sig_id}: ordin MT5 #{_ticket} anulat (expirat)")
                        else:
                            log.warning(f"  [EXEC] {sig_id}: anulare MT5 #{_ticket} esuata "
                                        f"({_mt5_exec.last_error()}) — poate deja inchis/triggerat")
                        state["mt5_tickets"].pop(sig_id, None)
                        # Ordin plasat in MT5 si expirat -> scriem in outcomes
                        outcome_rows.append({**p, "signal_id": sig_id,
                                             "symbol": symbol,
                                             "status": "expirat", "result_r": 0.0,
                                             "exit_time": current_bar_t,
                                             "time_check": datetime.now()})
                        _send_telegram(
                            f"<b>EXPIRAT: {symbol}</b>\n"
                            f"Ordinul nu a fost triggerat (>{expire_bars} bare)\n"
                            f"<i>{session_id} | {sig_id}</i>"
                        )
                    else:
                        # Fara ordin MT5 — pastram doar in signals.csv, nu in outcomes
                        log.info(f"  EXPIRAT (fara ordin MT5): {sig_id} {symbol} "
                                 f"— pastrat ca semnal, nu in outcomes")
                    log.info(f"  EXPIRAT: {sig_id} {symbol} (>{expire_bars} bare fara trigger)")
                    continue

            for _, bar in df_post.iterrows():
                inv  = (d == 1 and bar["low"]  < p["sl"]) or \
                       (d == -1 and bar["high"] > p["sl"])
                trig = (d == 1 and bar["high"] >= p["entry"]) or \
                       (d == -1 and bar["low"]  <= p["entry"])
                if inv:
                    rows_to_remove.append(sig_id)
                    _ticket = state.get("mt5_tickets", {}).get(sig_id)
                    if _ticket and _mt5_exec is not None:
                        _r = _mt5_exec.order_send({
                            "action": _mt5_exec.TRADE_ACTION_REMOVE,
                            "order":  _ticket,
                        })
                        if _r and _r.retcode == _mt5_exec.TRADE_RETCODE_DONE:
                            log.info(f"  [EXEC] {sig_id}: ordin MT5 #{_ticket} anulat (invalidat)")
                        else:
                            log.warning(f"  [EXEC] {sig_id}: anulare MT5 #{_ticket} esuata "
                                        f"({_mt5_exec.last_error()}) — poate deja inchis/triggerat")
                        state["mt5_tickets"].pop(sig_id, None)
                        # Ordin plasat in MT5 si invalidat -> scriem in outcomes
                        outcome_rows.append({**p, "signal_id": sig_id,
                                             "symbol": symbol,
                                             "status": "invalidat", "result_r": 0.0,
                                             "time_check": datetime.now()})
                    else:
                        # Fara ordin MT5 — pastram doar in signals.csv, nu in outcomes
                        log.info(f"  INVALIDAT (fara ordin MT5): {sig_id} {symbol} "
                                 f"— pastrat ca semnal, nu in outcomes")
                    break
                if trig:
                    if execute_trades and sig_id not in state.get("mt5_tickets", {}):
                        # Pretul a trecut de entry, dar nu exista (inca) un ordin MT5
                        # real pentru acest semnal — plasarea a fost amanata/in retry.
                        # Nu marcam triggered sintetic (ar decupla tracking-ul de MT5);
                        # asteptam fie un ticket real, fie expirarea naturala.
                        continue
                    p["triggered"]    = True
                    p["triggered_at"] = bar["time"]
                    log.info(f"  TRIGGERAT: {sig_id} {symbol} "
                             f"{'LONG' if d==1 else 'SHORT'} @ {p['entry']:.5f}")
                    break

        if p.get("triggered") and sig_id not in rows_to_remove:
            _ticket  = state.get("mt5_tickets", {}).get(sig_id)
            fmt      = ".2f" if p["entry"] > 100 else ".5f"
            dir_str  = "LONG" if d == 1 else "SHORT"

            if _ticket and _mt5_exec is not None and execute_trades:
                # Tracking bazat pe MT5 real — exit price = pretul efectiv al brokerului
                mt5_res = _check_mt5_position_closed(_ticket, p, log)
                if mt5_res is not None:
                    rows_to_remove.append(sig_id)
                    state.get("mt5_tickets", {}).pop(sig_id, None)
                    if mt5_res.get("__no_outcome__"):
                        # Ordin anulat/respins in MT5 fara executie — nu scriem in outcomes
                        log.info(f"  [MT5] {sig_id} scos din tracking (anulat/respins fara executie)")
                        continue
                    outcome_rows.append({**p, "signal_id": sig_id, "symbol": symbol,
                                         **mt5_res, "time_check": datetime.now()})
                    if mt5_res["status"] == "TP":
                        log.info(f"  PROFIT (MT5): {sig_id} TP +{mt5_res['result_r']:.3f}R")
                        _send_telegram(
                            f"<b>PROFIT +{mt5_res['result_r']:.2f}R: {dir_str} {symbol}</b>\n"
                            f"Entry {format(p['entry'], fmt)} → "
                            f"{format(mt5_res['exit_price'], fmt)} (exit real MT5)\n"
                            f"<i>{session_id} | {sig_id}</i>"
                        )
                    else:
                        log.info(f"  PIERDERE (MT5): {sig_id} SL {mt5_res['result_r']:.3f}R")
                        _send_telegram(
                            f"<b>PIERDERE {mt5_res['result_r']:.2f}R: {dir_str} {symbol}</b>\n"
                            f"Entry {format(p['entry'], fmt)} → "
                            f"{format(mt5_res['exit_price'], fmt)} (exit real MT5)\n"
                            f"<i>{session_id} | {sig_id}</i>"
                        )
                # else: pozitia inca deschisa sau pending — verificam la urmatoarea bara
                if _be_on and p.get("triggered") and len(df) >= 2:
                    _bar_be = df.iloc[-2]
                    _be_last = p.get("be_last_t")
                    if _be_last is None or pd.Timestamp(_bar_be["time"]) > pd.Timestamp(_be_last):
                        _bep = p.get("be_phase", 0)
                        _tpd = abs(p["tp"] - p["entry"])
                        _be80 = p["entry"] + d * _tpd * (_be_cfg["trigger_pct"]    / 100)
                        _be30 = p["entry"] + d * _tpd * (_be_cfg["lock1_pct"]      / 100)
                        _be40 = p["entry"] + d * _tpd * (_be_cfg["phase2_zone_pct"] / 100)
                        _be50 = p["entry"] + d * _tpd * (_be_cfg["lock2_pct"]      / 100)
                        _b = _bar_be
                        if d == 1:
                            _r80 = _b["high"] >= _be80; _rev = _b["low"] < _be80
                            _inz = _be30 < _b["low"] <= _be40
                        else:
                            _r80 = _b["low"] <= _be80;  _rev = _b["high"] > _be80
                            _inz = _be40 <= _b["high"] < _be30
                        _nsl = None; _pname = None
                        if _bep == 0 and _r80: _bep = 1
                        if _bep == 1 and _rev: _bep = 2; _nsl = _be30; _pname = "phase1"
                        if _bep == 2:
                            if _inz: p["be_in_zone"] = True
                            if p.get("be_in_zone") and _r80: _bep = 3
                        if _bep == 3 and _rev: _bep = 4; _nsl = _be50; _pname = "phase2"
                        if _nsl is not None and _mt5_exec is not None:
                            _pos_mt5 = None
                            for _po in (_mt5_exec.positions_get(symbol=symbol) or []):
                                if _po.ticket == _ticket: _pos_mt5 = _po; break
                            if _pos_mt5 is None:
                                _ho = _mt5_exec.history_orders_get(ticket=_ticket)
                                if _ho:
                                    _pid2 = getattr(_ho[0], "position_id", None)
                                    if _pid2:
                                        _pp2 = _mt5_exec.positions_get(ticket=_pid2)
                                        if _pp2: _pos_mt5 = _pp2[0]
                            if _pos_mt5:
                                _slr = _mt5_exec.order_send({"action": _mt5_exec.TRADE_ACTION_SLTP,
                                    "symbol": symbol, "position": _pos_mt5.ticket,
                                    "sl": _nsl, "tp": p["tp"]})
                                if _slr and _slr.retcode == _mt5_exec.TRADE_RETCODE_DONE:
                                    p["be_phase"] = _bep; p["be_current_sl"] = _nsl
                                    _lbl = "Faza 1" if _pname == "phase1" else "Faza 2"
                                    _pct = _be_cfg["lock1_pct"] if _pname == "phase1" else _be_cfg["lock2_pct"]
                                    log.info(f"  [BE] {sig_id} {_lbl}: SL → {format(_nsl, fmt)}")
                                    _send_telegram(
                                        f"<b>Break-Even {_lbl}: {dir_str} {symbol}</b>\n"
                                        f"SL mutat la <code>{format(_nsl, fmt)}</code> (+{_pct}% TP)\n"
                                        f"<i>{session_id} | {sig_id}</i>"
                                    )
                                else:
                                    log.warning(f"  [BE] {sig_id}: SLTP esuat")
                        p["be_phase"]  = _bep
                        p["be_last_t"] = _bar_be["time"]
                continue  # nu facem bar-based tracking cand avem ticket MT5

            # Bar-based tracking pentru sesiuni fara executie (execute_trades=False / OBS)
            df_aft = df[df["time"] > p.get("triggered_at")]
            if _be_on:
                _bep = 0; _be_inz = False; _be_csl = p["sl"]
                _tpd  = abs(p["tp"] - p["entry"])
                _be80 = p["entry"] + d * _tpd * (_be_cfg["trigger_pct"]    / 100)
                _be30 = p["entry"] + d * _tpd * (_be_cfg["lock1_pct"]      / 100)
                _be40 = p["entry"] + d * _tpd * (_be_cfg["phase2_zone_pct"] / 100)
                _be50 = p["entry"] + d * _tpd * (_be_cfg["lock2_pct"]      / 100)
                _notif = p.get("be_notified_phases", set())
                _new_n: set = set()
                for _, bar in df_aft.iterrows():
                    if d == 1:
                        _r80 = bar["high"] >= _be80; _rev80 = bar["low"] < _be80
                        _inz = _be30 < bar["low"] <= _be40
                    else:
                        _r80 = bar["low"] <= _be80;  _rev80 = bar["high"] > _be80
                        _inz = _be40 <= bar["high"] < _be30
                    if _bep == 0 and _r80:  _bep = 1
                    if _bep == 1 and _rev80: _bep = 2; _be_csl = _be30; _new_n.add(2)
                    if _bep == 2:
                        if _inz: _be_inz = True
                        if _be_inz and _r80: _bep = 3
                    if _bep == 3 and _rev80: _bep = 4; _be_csl = _be50; _new_n.add(4)
                    _sl_hit = (d == 1 and bar["low"] <= _be_csl) or (d == -1 and bar["high"] >= _be_csl)
                    _tp_hit = (d == 1 and bar["high"] >= p["tp"]) or (d == -1 and bar["low"] <= p["tp"])
                    if _sl_hit:
                        if _bep >= 4:   _oc = "be_lock2"; _rr = round((_be_csl - p["entry"]) * d / abs(p["entry"] - p["sl"]), 3)
                        elif _bep >= 2: _oc = "be_lock";  _rr = round((_be_csl - p["entry"]) * d / abs(p["entry"] - p["sl"]), 3)
                        else:           _oc = "SL";       _rr = -1.0
                        outcome_rows.append({**p, "signal_id": sig_id, "symbol": symbol,
                                             "status": _oc, "result_r": _rr,
                                             "exit_price": _be_csl, "exit_time": bar["time"],
                                             "time_check": datetime.now()})
                        rows_to_remove.append(sig_id)
                        if _oc == "SL":
                            log.info(f"  PIERDERE: {sig_id} SL -1.0R")
                            _send_telegram(
                                f"<b>PIERDERE -1R: {dir_str} {symbol}</b>\n"
                                f"Entry {format(p['entry'], fmt)} → SL {format(p['sl'], fmt)}\n"
                                f"<i>{session_id} | {sig_id}</i>"
                            )
                        else:
                            _lbl = "Faza 1" if _oc == "be_lock" else "Faza 2"
                            log.info(f"  [BE {_lbl}] {sig_id} +{_rr:.3f}R")
                            _send_telegram(
                                f"<b>Break-Even {_lbl}: {dir_str} {symbol}</b>\n"
                                f"Ieșire la +{_rr:.2f}R\n"
                                f"<i>{session_id} | {sig_id}</i>"
                            )
                        break
                    if _tp_hit:
                        outcome_rows.append({**p, "signal_id": sig_id, "symbol": symbol,
                                             "status": "TP", "result_r": p["r_ratio"],
                                             "exit_price": p["tp"], "exit_time": bar["time"],
                                             "time_check": datetime.now()})
                        rows_to_remove.append(sig_id)
                        log.info(f"  PROFIT: {sig_id} TP +{p['r_ratio']:.1f}R")
                        _send_telegram(
                            f"<b>PROFIT +{p['r_ratio']:.1f}R: {dir_str} {symbol}</b>\n"
                            f"Entry {format(p['entry'], fmt)} → TP {format(p['tp'], fmt)}\n"
                            f"<i>{session_id} | {sig_id}</i>"
                        )
                        break
                if sig_id not in rows_to_remove:
                    p["be_phase"] = _bep; p["be_in_zone"] = _be_inz; p["be_current_sl"] = _be_csl
                _new_un = _new_n - _notif
                if _new_un:
                    p.setdefault("be_notified_phases", set()).update(_new_un)
                    for _nph in sorted(_new_un):
                        if _nph == 2:
                            _send_telegram(
                                f"<b>Break-Even Faza 1 (OBS): {dir_str} {symbol}</b>\n"
                                f"SL virtual la +{_be_cfg['lock1_pct']}% din TP\n"
                                f"<i>{session_id} | {sig_id}</i>"
                            )
                        elif _nph == 4:
                            _send_telegram(
                                f"<b>Break-Even Faza 2 (OBS): {dir_str} {symbol}</b>\n"
                                f"SL virtual la +{_be_cfg['lock2_pct']}% din TP\n"
                                f"<i>{session_id} | {sig_id}</i>"
                            )
            else:
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
                        _send_telegram(
                            f"<b>PIERDERE -1R: {dir_str} {symbol}</b>\n"
                            f"Entry {format(p['entry'], fmt)} → SL {format(p['sl'], fmt)}\n"
                            f"<i>{session_id} | {sig_id}</i>"
                        )
                        break
                    if tp_hit:
                        outcome_rows.append({**p, "signal_id": sig_id,
                                             "symbol": symbol, "status": "TP",
                                             "result_r": p["r_ratio"], "exit_price": p["tp"],
                                             "exit_time": bar["time"],
                                             "time_check": datetime.now()})
                        rows_to_remove.append(sig_id)
                        log.info(f"  PROFIT: {sig_id} TP +{p['r_ratio']:.1f}R")
                        _send_telegram(
                            f"<b>PROFIT +{p['r_ratio']:.1f}R: {dir_str} {symbol}</b>\n"
                            f"Entry {format(p['entry'], fmt)} → TP {format(p['tp'], fmt)}\n"
                            f"<i>{session_id} | {sig_id}</i>"
                        )
                        break

    if outcome_rows:
        # Evita duplicate daca doua instante ruleaza simultan pe acelasi fisier
        existing_ids: set = set()
        if os.path.exists(outcomes_file):
            try:
                existing_ids = set(pd.read_csv(outcomes_file, usecols=["signal_id"])["signal_id"].dropna())
            except Exception:
                pass
        new_rows = [r for r in outcome_rows if r.get("signal_id") not in existing_ids]
        if new_rows:
            pd.DataFrame(new_rows).reindex(columns=_OUTCOMES_COLS).to_csv(
                outcomes_file, mode="a", header=False, index=False)

    for sig_id in rows_to_remove:
        state["pending"][symbol].pop(sig_id, None)


# ---------------------------------------------------------------------------
# Reconciliere tickets MT5 la pornire
# ---------------------------------------------------------------------------

def _reconcile_mt5_tickets(state: dict, log) -> None:
    """
    Verifica toate ticket-urile din state["mt5_tickets"] la pornire.
    Sterge orfanele (anulate, respinse sau inexistente in MT5).
    Semnalele corespunzatoare raman in pending — vor expira natural.
    Nu scrie nimic in outcomes.csv (ordinele nu s-au executat niciodata).
    """
    if _mt5_exec is None or not state.get("mt5_tickets"):
        return

    to_remove = []
    for sig_id, ticket in list(state["mt5_tickets"].items()):
        # Inca pending (netriggerat) → ok
        if _mt5_exec.orders_get(ticket=ticket):
            continue
        # Pozitie deschisa (triggerat, in curs) → ok
        if _mt5_exec.positions_get(ticket=ticket):
            continue
        # Pozitie inchisa cu deals → va fi procesata normal la urmatoarea bara
        deals = _mt5_exec.history_deals_get(position=ticket)
        if deals:
            continue
        # Ordin anulat/respins in MT5 (ORDER_STATE: CANCELED=2, REJECTED=4, EXPIRED=6)
        hist_orders = _mt5_exec.history_orders_get(ticket=ticket)
        if hist_orders:
            order = hist_orders[0]
            if order.state in (2, 4, 6):
                log.warning(
                    f"  [RECONCIL] {sig_id} ticket #{ticket} anulat/respins "
                    f"(state={order.state}) — scos din tracking"
                )
                to_remove.append(sig_id)
                continue
        # Nu gasit nicaieri — ticket orfan (plasare esuata sau state corupt)
        log.warning(
            f"  [RECONCIL] {sig_id} ticket #{ticket} negasit in MT5 (orfan) — scos din tracking"
        )
        to_remove.append(sig_id)

    for sig_id in to_remove:
        state["mt5_tickets"].pop(sig_id, None)

    if to_remove:
        log.info(f"  [RECONCIL] Curatate {len(to_remove)} ticket(e) orfane; "
                 f"semnalele raman in pending si vor expira natural.")


# ---------------------------------------------------------------------------
# Pauza sesiune (manuala + automata din protectie stiri)
# ---------------------------------------------------------------------------

_PAUSED_FILE      = os.path.join(DATA_DIR, "paused_sessions.json")
_NEWS_PAUSED_FILE = os.path.join(DATA_DIR, "news_auto_paused.json")


def _is_paused(session_key: str) -> bool:
    """Verifica daca sesiunea e in pauza manuala (data/paused_sessions.json)."""
    try:
        if os.path.exists(_PAUSED_FILE):
            with open(_PAUSED_FILE, encoding="utf-8") as f:
                return session_key in json.load(f)
    except Exception:
        pass
    return False


def _is_news_paused(session_key: str) -> tuple[bool, list]:
    """
    Verifica daca sesiunea e pe pauza automata din protectie la stiri.
    Returneaza (paused: bool, events: list) din data/news_auto_paused.json.
    """
    try:
        if os.path.exists(_NEWS_PAUSED_FILE):
            with open(_NEWS_PAUSED_FILE, encoding="utf-8") as f:
                data = json.load(f)
            if session_key in data:
                return True, data[session_key].get("events", [])
    except Exception:
        pass
    return False, []


# ---------------------------------------------------------------------------
# Vineri close — inchide pozitii triggerate la ora configurata
# ---------------------------------------------------------------------------

def _friday_close_check(
    state: dict,
    outcomes_file: str,
    log,
    session_id: str = "",
    execute_trades: bool = False,
    friday_close_enabled: bool = True,
    friday_close_hour: int = 20,
) -> None:
    """
    Vineri la ora configurata, inchide toate pozitiile triggerate deschise.
    Executa o singura data per saptamana (evita re-rulari la fiecare bara).
    """
    if not friday_close_enabled:
        return

    now = datetime.now()
    if now.weekday() != 4:   # 4 = Friday
        return
    if now.hour < friday_close_hour:
        return

    today_str = now.strftime("%Y-%m-%d")
    if state.get("friday_close_date") == today_str:
        return   # deja executat in aceasta zi

    state["friday_close_date"] = today_str
    log.info(f"  [VINERI] Ora {now.strftime('%H:%M')} >= {friday_close_hour}:00 — inchid pozitii deschise.")

    outcome_rows   = []
    sigs_to_remove = []   # list of (symbol, sig_id)

    # 1. Anuleaza ordinele pending (neactivate) — ramase ca GTC in MT5
    for symbol, pending in list(state["pending"].items()):
        for sig_id, p in list(pending.items()):
            if p.get("triggered"):
                continue  # pozitiile triggerate sunt tratate mai jos

            ticket  = state.get("mt5_tickets", {}).get(sig_id)
            fmt     = ".2f" if p.get("entry", 0) > 100 else ".5f"
            dir_str = "LONG" if p.get("direction", 1) == 1 else "SHORT"

            if ticket and _mt5_exec is not None and execute_trades:
                r = _mt5_exec.order_send({
                    "action": _mt5_exec.TRADE_ACTION_REMOVE,
                    "order":  ticket,
                })
                if r and r.retcode == _mt5_exec.TRADE_RETCODE_DONE:
                    outcome_rows.append({
                        **p,
                        "signal_id":    sig_id,
                        "symbol":       symbol,
                        "status":       "vineri_cancel",
                        "result_r":     0.0,
                        "exit_price":   None,
                        "exit_time":    now,
                        "triggered_at": None,
                        "time_check":   now,
                    })
                    state.get("mt5_tickets", {}).pop(sig_id, None)
                    sigs_to_remove.append((symbol, sig_id))
                    log.info(
                        f"  [VINERI] {sig_id} {symbol} {dir_str} pending anulat "
                        f"(entry={format(p['entry'], fmt[1:])})"
                    )
                else:
                    retcode = r.retcode if r else "None"
                    log.warning(f"  [VINERI] {sig_id}: anulare pending esuata retcode={retcode}")
            elif not execute_trades:
                sigs_to_remove.append((symbol, sig_id))
                log.info(f"  [VINERI] {sig_id} {symbol} pending scos din state (OBS, vineri_cancel)")

    # 2. Inchide pozitiile triggerate (open)
    for symbol, pending in list(state["pending"].items()):
        for sig_id, p in list(pending.items()):
            if not p.get("triggered"):
                continue

            d       = p["direction"]
            fmt     = ".2f" if p["entry"] > 100 else ".5f"
            dir_str = "LONG" if d == 1 else "SHORT"

            ticket = state.get("mt5_tickets", {}).get(sig_id)

            if ticket and _mt5_exec is not None and execute_trades:
                positions = _mt5_exec.positions_get(ticket=ticket)
                if not positions:
                    continue   # deja inchisa altundeva

                pos  = positions[0]
                tick = _mt5_exec.symbol_info_tick(symbol)
                if tick is None:
                    log.warning(f"  [VINERI] {sig_id}: nu pot obtine tick pentru {symbol}")
                    continue

                close_price = tick.bid if d == 1 else tick.ask
                close_type  = (_mt5_exec.ORDER_TYPE_SELL
                               if d == 1 else _mt5_exec.ORDER_TYPE_BUY)

                close_req = {
                    "action":       _mt5_exec.TRADE_ACTION_DEAL,
                    "symbol":       symbol,
                    "volume":       pos.volume,
                    "type":         close_type,
                    "position":     ticket,
                    "price":        close_price,
                    "comment":      "vineri_close",
                    "type_time":    _mt5_exec.ORDER_TIME_GTC,
                    "type_filling": _mt5_exec.ORDER_FILLING_IOC,
                }
                result = _mt5_exec.order_send(close_req)
                if result and result.retcode == _mt5_exec.TRADE_RETCODE_DONE:
                    exit_price = result.price
                    risk_dist  = abs(p["entry"] - p["sl"])
                    result_r   = (round((exit_price - p["entry"]) * d / risk_dist, 3)
                                  if risk_dist > 0 else 0.0)
                    outcome_rows.append({
                        **p,
                        "signal_id":    sig_id,
                        "symbol":       symbol,
                        "status":       "vineri_close",
                        "result_r":     result_r,
                        "exit_price":   exit_price,
                        "exit_time":    now,
                        "triggered_at": p.get("triggered_at", now),
                        "time_check":   now,
                    })
                    state.get("mt5_tickets", {}).pop(sig_id, None)
                    sigs_to_remove.append((symbol, sig_id))
                    log.info(
                        f"  [VINERI] {sig_id} {symbol} {dir_str} inchis: "
                        f"exit={exit_price:{fmt[1:]}}  result={result_r:+.3f}R"
                    )
                    _send_telegram(
                        f"<b>Vineri close: {dir_str} {symbol}</b>\n"
                        f"Entry {format(p['entry'], fmt)} → {format(exit_price, fmt)}\n"
                        f"Result: {result_r:+.2f}R\n"
                        f"<i>{session_id}</i>"
                    )
                else:
                    retcode = result.retcode if result else "None"
                    log.warning(f"  [VINERI] {sig_id}: inchidere esuata retcode={retcode}")

            elif not execute_trades:
                # OBS mode — scoatem din pending fara outcome real
                sigs_to_remove.append((symbol, sig_id))
                log.info(f"  [VINERI] {sig_id} {symbol} scos din pending (OBS, vineri_close)")

    if outcome_rows:
        existing_ids: set = set()
        if os.path.exists(outcomes_file):
            try:
                existing_ids = set(
                    pd.read_csv(outcomes_file, usecols=["signal_id"])["signal_id"].dropna()
                )
            except Exception:
                pass
        new_rows = [r for r in outcome_rows if r.get("signal_id") not in existing_ids]
        if new_rows:
            pd.DataFrame(new_rows).reindex(columns=_OUTCOMES_COLS).to_csv(
                outcomes_file, mode="a", header=False, index=False)

    for symbol, sig_id in sigs_to_remove:
        state["pending"].get(symbol, {}).pop(sig_id, None)


def _news_close_check(
    state: dict,
    outcomes_file: str,
    log,
    session_id: str = "",
    execute_trades: bool = False,
) -> None:
    """
    La prima iteratie de pauza de stiri (tranzitia False → True):
    - anuleaza ordinele pending neactivate (TRADE_ACTION_REMOVE)
    - inchide la piata pozitiile triggerate deschise (TRADE_ACTION_DEAL)
    Apelat o singura data per tranzitie, din bucla principala.
    """
    total = sum(len(v) for v in state["pending"].values())
    if total == 0:
        log.info("  [STIRI] Nicio pozitie/ordin activ — nimic de inchis.")
        return

    outcome_rows   = []
    sigs_to_remove = []
    now = datetime.now()

    for symbol, pending in list(state["pending"].items()):
        for sig_id, p in list(pending.items()):
            d         = p["direction"]
            fmt       = ".2f" if p["entry"] > 100 else ".5f"
            dir_str   = "LONG" if d == 1 else "SHORT"
            ticket    = state.get("mt5_tickets", {}).get(sig_id)
            triggered = p.get("triggered", False)

            if not execute_trades:
                sigs_to_remove.append((symbol, sig_id))
                log.info(f"  [STIRI] {sig_id} {symbol} scos din pending (OBS, news_close)")
                continue

            if not ticket or _mt5_exec is None:
                sigs_to_remove.append((symbol, sig_id))
                log.info(f"  [STIRI] {sig_id} {symbol}: fara ticket MT5 — scos din pending")
                continue

            if triggered:
                positions = _mt5_exec.positions_get(ticket=ticket)
                if not positions:
                    state.get("mt5_tickets", {}).pop(sig_id, None)
                    sigs_to_remove.append((symbol, sig_id))
                    continue

                pos  = positions[0]
                tick = _mt5_exec.symbol_info_tick(symbol)
                if tick is None:
                    log.warning(f"  [STIRI] {sig_id}: nu pot obtine tick pentru {symbol}")
                    continue

                close_price = tick.bid if d == 1 else tick.ask
                close_type  = (_mt5_exec.ORDER_TYPE_SELL if d == 1 else _mt5_exec.ORDER_TYPE_BUY)
                result = _mt5_exec.order_send({
                    "action":       _mt5_exec.TRADE_ACTION_DEAL,
                    "symbol":       symbol,
                    "volume":       pos.volume,
                    "type":         close_type,
                    "position":     ticket,
                    "price":        close_price,
                    "comment":      "news_close",
                    "type_time":    _mt5_exec.ORDER_TIME_GTC,
                    "type_filling": _mt5_exec.ORDER_FILLING_IOC,
                })
                if result and result.retcode == _mt5_exec.TRADE_RETCODE_DONE:
                    exit_price = result.price
                    risk_dist  = abs(p["entry"] - p["sl"])
                    result_r   = (round((exit_price - p["entry"]) * d / risk_dist, 3)
                                  if risk_dist > 0 else 0.0)
                    outcome_rows.append({
                        **p,
                        "signal_id":    sig_id,
                        "symbol":       symbol,
                        "status":       "news_close",
                        "result_r":     result_r,
                        "exit_price":   exit_price,
                        "exit_time":    now,
                        "triggered_at": p.get("triggered_at", now),
                        "time_check":   now,
                    })
                    state.get("mt5_tickets", {}).pop(sig_id, None)
                    sigs_to_remove.append((symbol, sig_id))
                    log.info(
                        f"  [STIRI] {sig_id} {symbol} {dir_str} inchis la stire: "
                        f"exit={exit_price:{fmt[1:]}}  result={result_r:+.3f}R"
                    )
                    _send_telegram(
                        f"⚡ <b>Inchis la știre: {dir_str} {symbol}</b>\n"
                        f"Entry {format(p['entry'], fmt)} → {format(exit_price, fmt)}\n"
                        f"Result: {result_r:+.2f}R\n"
                        f"<i>{session_id}</i>"
                    )
                else:
                    retcode = result.retcode if result else "None"
                    log.warning(f"  [STIRI] {sig_id}: inchidere pozitie esuata retcode={retcode}")

            else:
                # Ordin pending neactivat — anuleaza din MT5
                r = _mt5_exec.order_send({
                    "action": _mt5_exec.TRADE_ACTION_REMOVE,
                    "order":  ticket,
                })
                if r and r.retcode == _mt5_exec.TRADE_RETCODE_DONE:
                    log.info(f"  [STIRI] {sig_id} {symbol}: ordin #{ticket} anulat la stire")
                else:
                    log.warning(
                        f"  [STIRI] {sig_id}: anulare #{ticket} esuata "
                        f"({_mt5_exec.last_error()})"
                    )
                state.get("mt5_tickets", {}).pop(sig_id, None)
                outcome_rows.append({
                    **p,
                    "signal_id":  sig_id,
                    "symbol":     symbol,
                    "status":     "news_cancel",
                    "result_r":   0.0,
                    "exit_time":  now,
                    "time_check": now,
                })
                sigs_to_remove.append((symbol, sig_id))

    if outcome_rows:
        existing_ids: set = set()
        if os.path.exists(outcomes_file):
            try:
                existing_ids = set(
                    pd.read_csv(outcomes_file, usecols=["signal_id"])["signal_id"].dropna()
                )
            except Exception:
                pass
        new_rows = [r for r in outcome_rows if r.get("signal_id") not in existing_ids]
        if new_rows:
            pd.DataFrame(new_rows).reindex(columns=_OUTCOMES_COLS).to_csv(
                outcomes_file, mode="a", header=False, index=False)

    for symbol, sig_id in sigs_to_remove:
        state["pending"].get(symbol, {}).pop(sig_id, None)


# ---------------------------------------------------------------------------
# Aplicare parametri profil activ
# ---------------------------------------------------------------------------

def _apply_profile_overrides(session_cfg: dict, cfg: dict, log) -> None:
    """
    Daca botul a fost pornit din UI cu un profil, aplica parametrii profilului
    peste session_cfg (ore, PW, execute) si cfg (RSI, EMA, R-ladder).
    Fara fisier de profil activ → no-op (valorile hardcodate raman).
    """
    runtime_file = os.path.join(DATA_DIR, "active_profile_runtime.json")
    if not os.path.exists(runtime_file):
        return
    try:
        with open(runtime_file, encoding="utf-8") as f:
            profile = json.load(f)
    except Exception as e:
        log.warning(f"  [PROFIL] Nu pot citi {runtime_file}: {e}")
        return

    key = session_cfg.get("session_key")
    if not key:
        return

    ps = next((s for s in profile.get("sessions", []) if s.get("session_key") == key), None)
    if ps is None:
        log.info(f"  [PROFIL] Sesiunea '{key}' nu e in profil — parametri hardcodati.")
        return

    # --- parametri sesiune (session_cfg) ---
    for field in ("pullback_window", "session_start", "session_end",
                  "expire_bars", "execute_trades", "account_fraction", "risk_pct",
                  "risk_base", "risk_mid", "risk_top", "risk_max",
                  "r_mid_threshold", "r_top_threshold", "r_max_threshold",
                  # Task 7: pozitii simultane per piata
                  "max_concurrent_per_market", "min_bars_between_trades",
                  "break_even_enabled", "be_trigger_pct", "be_lock1_pct",
                  "be_lock2_pct", "be_phase2_zone_pct"):
        if field in ps:
            session_cfg[field] = ps[field]

    if "skip_hours" in ps:
        session_cfg["skip_hours"] = tuple(ps["skip_hours"])
    if "skip_weekdays" in ps:
        skip_wd = set(ps["skip_weekdays"])
        session_cfg["skip_weekdays"] = skip_wd
        # compatibilitate skip_monday
        session_cfg["skip_monday"] = 0 in skip_wd

    if "direction" in ps:
        session_cfg["only_long"] = ps["direction"] == "LONG"

    if "friday_close_enabled" in ps:
        session_cfg["friday_close_enabled"] = ps["friday_close_enabled"]
    if "friday_close_hour" in ps:
        session_cfg["friday_close_hour"] = ps["friday_close_hour"]

    for news_field in ("news_protection_enabled", "news_impact_level",
                       "news_pre_minutes", "news_post_minutes"):
        if news_field in ps:
            session_cfg[news_field] = ps[news_field]

    # --- parametri strategie (cfg) ---
    if ps.get("rsi_enabled") is not None:
        cfg["optional_criteria"]["rsi"]["enabled"] = ps["rsi_enabled"]
    for rsi_key in ("buy_min", "buy_max", "sell_min", "sell_max"):
        prof_key = f"rsi_{rsi_key}"
        if prof_key in ps:
            cfg["optional_criteria"]["rsi"][rsi_key] = ps[prof_key]

    if ps.get("ema_alignment_enabled") is not None:
        cfg["optional_criteria"]["ema_alignment"]["enabled"] = ps["ema_alignment_enabled"]

    if ps.get("body_strength_enabled") is not None:
        cfg["optional_criteria"].setdefault("body_strength", {})
        cfg["optional_criteria"]["body_strength"]["enabled"] = ps["body_strength_enabled"]
    if "body_strength_min_atr_ratio" in ps:
        cfg["optional_criteria"].setdefault("body_strength", {})
        cfg["optional_criteria"]["body_strength"]["min_atr_ratio"] = ps["body_strength_min_atr_ratio"]

    rl = cfg["reward_ladder"]
    if "r_base" in ps: rl["rr_if_3_criteria"] = ps["r_base"]
    if "r_mid"  in ps: rl["rr_if_4_criteria"] = ps["r_mid"]
    if "r_top"  in ps: rl["rr_if_5_criteria"] = ps["r_top"]
    if "r_max"  in ps: rl["rr_if_6_criteria"] = ps["r_max"]
    if "r_mid_threshold" in ps: rl["threshold_mid"] = ps["r_mid_threshold"]
    if "r_top_threshold" in ps: rl["threshold_top"] = ps["r_top_threshold"]
    if "r_max_threshold" in ps: rl["threshold_max"] = ps["r_max_threshold"]

    log.info(f"  [PROFIL] Profil '{profile.get('name', '?')}' aplicat pe {key}.")


def _pick_risk_pct(n_optional: int, session_cfg: dict) -> float:
    """
    Selecteaza risk% in functie de numarul de criterii optionale satisfacute.
    Daca risk_base/mid/top/max nu sunt in session_cfg, foloseste risk_pct flat.
    """
    t_mid = session_cfg.get("r_mid_threshold", 1)
    t_top = session_cfg.get("r_top_threshold", 2)
    t_max = session_cfg.get("r_max_threshold", 3)
    base  = session_cfg.get("risk_base", session_cfg.get("risk_pct", 0.01))
    if n_optional >= t_max and "risk_max" in session_cfg:
        return session_cfg["risk_max"]
    if n_optional >= t_top and "risk_top" in session_cfg:
        return session_cfg["risk_top"]
    if n_optional >= t_mid and "risk_mid" in session_cfg:
        return session_cfg["risk_mid"]
    return base


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
    lock_file    = os.path.join(out_dir, "session.lock")

    os.makedirs(out_dir, exist_ok=True)

    # Previne doua instante ale aceleiasi sesiuni sa ruleze simultan
    # IMPORTANT: OpenProcess singur returneaza True pentru procese moarte recent
    # (kernel object raman viu cateva secunde dupa taskkill).
    # GetExitCodeProcess(STILL_ACTIVE=259) este verificarea corecta.
    def _pid_alive(pid: int) -> bool:
        try:
            import ctypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            STILL_ACTIVE = 259
            h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if h:
                exit_code = ctypes.c_ulong()
                ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(exit_code))
                ctypes.windll.kernel32.CloseHandle(h)
                return exit_code.value == STILL_ACTIVE
        except Exception:
            pass
        return False

    if os.path.exists(lock_file):
        try:
            existing_pid = int(open(lock_file).read().strip())
            if _pid_alive(existing_pid):
                print(f"[{session_cfg['session_id']}] EROARE: deja rulaza (PID {existing_pid}). "
                      f"Opreste instanta existenta inainte de a relansa. Iesire.")
                sys.exit(1)
        except (ValueError, OSError):
            pass  # lock corupt sau PID mort — suprascriem

    with open(lock_file, "w") as f:
        f.write(str(os.getpid()))

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

    # Incarca stare (cu fallback la coruptie — ex: reboot in mijlocul scrierii)
    _empty_state = {"pending": {}, "signal_counter": 0, "last_checked": {}}
    try:
        state = pickle.load(open(state_file, "rb")) if os.path.exists(state_file) else _empty_state
    except Exception as _e:
        log.warning(f"state.pkl corupt ({_e}) — resetat la stare goala.")
        state = _empty_state
    state.setdefault("mt5_tickets", {})   # ticket MT5 per signal_id

    # Sincronizeaza signal_counter cu ce e deja in signals.csv
    # (previne reutilizarea ID-urilor dupa restart cu state.pkl fresh)
    if os.path.exists(signals_file):
        try:
            import re as _re
            _existing = pd.read_csv(signals_file, usecols=["signal_id"])["signal_id"].dropna()
            _max_n = max(
                (int(m.group(1)) for sid in _existing
                 if (m := _re.search(r"SIG(\d+)$", str(sid)))),
                default=0,
            )
            if _max_n > state["signal_counter"]:
                state["signal_counter"] = _max_n
                log.info(f"  signal_counter sincronizat la {_max_n} din signals.csv")
        except Exception:
            pass

    with open(CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)
    cfg["optional_criteria"]["rsi"]["sell_max"] = 60  # RSI simetric pentru SELL

    # Aplica parametrii din profilul activ (daca botul a fost pornit din UI)
    _apply_profile_overrides(session_cfg, cfg, log)

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

    # Reconciliere tickets la pornire — curata orfanele din state
    _reconcile_mt5_tickets(state, log)

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
    _was_news_paused = False   # pentru detectia tranzitiei False → True

    # Notificare la orice oprire (manuala, crash, SIGTERM/kill Windows)
    import signal as _signal
    _stop_reason = ["necunoscut"]

    def _handle_sigterm(signum, frame):
        _stop_reason[0] = "SIGTERM (kill / restart Windows)"
        raise SystemExit(0)

    try:
        _signal.signal(_signal.SIGTERM, _handle_sigterm)
        _signal.signal(_signal.SIGBREAK, _handle_sigterm)   # Ctrl+Break Windows
    except (OSError, AttributeError):
        pass

    def _send_stop_notification(reason: str) -> None:
        icon = "🛑" if reason == "manual" else "⚠️"
        _send_telegram(
            f"{icon} <b>Bot oprit: {session_cfg['session_id']}</b>\n"
            f"Motiv: {reason}\n"
            f"<i>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</i>"
        )

    try:
      while True:
        try:
            iteration += 1
            log.info(f"--- {session_cfg['session_id']} iter {iteration} "
                     f"@ {datetime.now().strftime('%H:%M:%S')} ---")

            session_key    = session_cfg.get("session_key", "")
            manual_paused  = _is_paused(session_key)
            news_paused, news_events = _is_news_paused(session_key)
            session_paused = manual_paused or news_paused

            if manual_paused:
                log.info("  [PAUZA] Sesiune in pauza manuala — semnal checking dezactivat. "
                         "Pozitiile deschise sunt in continuare monitorizate.")
            elif news_paused:
                top = news_events[0] if news_events else {}
                log.info(f"  [STIRI] Pauza automata — {top.get('title','?')} "
                         f"({top.get('currency','?')}, {top.get('impact','?')}, "
                         f"{top.get('minutes_to','?')} min)")

            # La prima iteratie de pauza de stiri, inchide imediat ordine/pozitii active
            if news_paused and not _was_news_paused:
                log.info("  [STIRI] Tranzitie → pauza: inchid ordine/pozitii active.")
                _news_close_check(
                    state=state,
                    outcomes_file=outcomes_file,
                    log=log,
                    session_id=session_cfg.get("session_id", ""),
                    execute_trades=session_cfg.get("execute_trades", False),
                )
                with open(state_file, "wb") as f:
                    pickle.dump(state, f)
            _was_news_paused = news_paused

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
                                bar_minutes=session_cfg["bar_minutes"],
                                session_id=session_cfg.get("session_id", ""),
                                execute_trades=session_cfg.get("execute_trades", False),
                                session_cfg=session_cfg)

                if session_paused:
                    continue  # skip signal detection si plasare ordine noi

                sigs = _check_signals(df, symbol, cfg, state, session_cfg)
                for sig in sigs:
                    # Evita duplicate in signals.csv (doua instante simultane)
                    _sig_exists = False
                    try:
                        _ex = pd.read_csv(signals_file, usecols=["signal_id"])["signal_id"].dropna()
                        _sig_exists = sig["signal_id"] in _ex.values
                    except Exception:
                        pass
                    if not _sig_exists:
                        pd.DataFrame([sig]).to_csv(signals_file, mode="a",
                                                   header=False, index=False)
                    state["pending"].setdefault(symbol, {})[sig["signal_id"]] = {
                        "direction":  sig["direction"],
                        "entry":      sig["entry"],
                        "sl":         sig["sl"],
                        "tp":         sig["tp"],
                        "r_ratio":    sig["r_ratio"],
                        "n_optional": sig.get("n_optional", 0),
                        "armed_at":   sig["time"],
                        "triggered":  False,
                        "be_phase":           0,
                        "be_current_sl":      sig["sl"],
                        "be_in_zone":         False,
                        "be_notified_phases": set(),
                        "be_last_t":          None,
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
                        risk_pct = _pick_risk_pct(sig.get("n_optional", 0), session_cfg)
                        lots   = _calc_lots(sig["symbol"], sig["entry"], sig["sl"],
                                            capital, risk_pct)
                        ticket = _place_order(sig, lots,
                                              session_cfg.get("expire_bars", 4),
                                              session_cfg["bar_minutes"], log)
                        if ticket:
                            # Ordin plasat cu succes
                            state["mt5_tickets"][sig["signal_id"]] = ticket
                            fmt = ".2f" if sig["entry"] > 100 else ".5f"
                            _send_telegram(
                                f"<b>Ordin plasat: {sig['dir_str']} {sig['symbol']}</b>\n"
                                f"Entry: <code>{format(sig['entry'], fmt)}</code>  "
                                f"SL: <code>{format(sig['sl'], fmt)}</code>  "
                                f"TP: <code>{format(sig['tp'], fmt)}</code>\n"
                                f"Lot: {lots}  Ticket: #{ticket}\n"
                                f"<i>{session_cfg['session_id']}</i>"
                            )
                        elif ticket is None:
                            # Pret depasit la aceasta bara — semnal pastrat in pending,
                            # va fi incercat la urmatoarea bara M15 sau va expira normal.
                            log.info(f"  {sig['signal_id']}: pret depasit acum — retry bara urm.")
                        else:
                            # ticket is False — eroare MT5 reala, scoate din pending
                            state["pending"][symbol].pop(sig["signal_id"], None)
                            log.info(f"  {sig['signal_id']}: scos din pending (eroare MT5)")
                            fmt = ".2f" if sig["entry"] > 100 else ".5f"
                            _send_telegram(
                                f"⚠️ <b>Ordin NEEXECUTAT: {sig['dir_str']} {sig['symbol']}</b>\n"
                                f"Entry: <code>{format(sig['entry'], fmt)}</code>  "
                                f"SL: <code>{format(sig['sl'], fmt)}</code>  "
                                f"TP: <code>{format(sig['tp'], fmt)}</code>\n"
                                f"Eroare plasare — verificati log pentru retcode\n"
                                f"<i>{session_cfg['session_id']} | {sig['signal_id']}</i>"
                            )

                    new_sigs += 1

                # Retry plasare pentru semnale pending fara ticket MT5 inca
                # (order_send a returnat None la bara precedenta — eroare tranzitorie)
                if not session_paused and session_cfg.get("execute_trades", False):
                    frac    = session_cfg.get("account_fraction")
                    capital = session_cfg.get("session_capital", 1000)
                    if frac and _mt5_exec is not None:
                        _ai = _mt5_exec.account_info()
                        if _ai:
                            capital = _ai.equity * frac

                    for _sid, _p in list(state["pending"].get(symbol, {}).items()):
                        if _sid in state.get("mt5_tickets", {}):
                            continue  # ordin deja plasat in MT5
                        if _p.get("triggered"):
                            continue  # deja triggerat
                        # Reconstituie sig dict minimal pentru _place_order
                        _sig_retry = {
                            "symbol":    symbol,
                            "signal_id": _sid,
                            "direction": _p["direction"],
                            "entry":     _p["entry"],
                            "sl":        _p["sl"],
                            "tp":        _p["tp"],
                        }
                        _risk_pct = _pick_risk_pct(_p.get("n_optional", 0), session_cfg)
                        _lots = _calc_lots(symbol, _p["entry"], _p["sl"], capital, _risk_pct)
                        log.info(f"  [RETRY] {_sid}: incerc plasare ordin (bara precedenta → None)")
                        _ticket = _place_order(_sig_retry, _lots,
                                               session_cfg.get("expire_bars", 4),
                                               session_cfg["bar_minutes"], log)
                        if _ticket:
                            state["mt5_tickets"][_sid] = _ticket
                            dir_str = "LONG" if _p["direction"] == 1 else "SHORT"
                            fmt = ".2f" if _p["entry"] > 100 else ".5f"
                            _send_telegram(
                                f"<b>Ordin plasat (retry): {dir_str} {symbol}</b>\n"
                                f"Entry: <code>{format(_p['entry'], fmt)}</code>  "
                                f"SL: <code>{format(_p['sl'], fmt)}</code>  "
                                f"TP: <code>{format(_p['tp'], fmt)}</code>\n"
                                f"Lot: {_lots}  Ticket: #{_ticket}\n"
                                f"<i>{session_cfg['session_id']}</i>"
                            )
                        elif _ticket is False:
                            state["pending"][symbol].pop(_sid, None)
                            log.info(f"  {_sid}: scos din pending la retry (eroare MT5 reala)")

                if len(df) > 2:
                    state["last_checked"][symbol] = pd.Timestamp(df.iloc[-2]["time"])

            # Vineri close — inchide pozitii triggerate la ora configurata
            _friday_close_check(
                state=state,
                outcomes_file=outcomes_file,
                log=log,
                session_id=session_cfg.get("session_id", ""),
                execute_trades=session_cfg.get("execute_trades", False),
                friday_close_enabled=session_cfg.get("friday_close_enabled", True),
                friday_close_hour=session_cfg.get("friday_close_hour", 20),
            )

            pending_n = sum(len(v) for v in state["pending"].values())
            if new_sigs == 0:
                log.info(f"  Niciun semnal nou. Pendinge: {pending_n}")

            with open(state_file, "wb") as f:
                pickle.dump(state, f)

            _sleep_to_next_bar(bar_min, log)

        except KeyboardInterrupt:
            _stop_reason[0] = "manual"
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
    finally:
        _send_stop_notification(_stop_reason[0])
        try:
            if os.path.exists(lock_file):
                os.remove(lock_file)
        except OSError:
            pass
