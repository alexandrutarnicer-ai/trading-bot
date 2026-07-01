"""
Generator de semnale live — engine generic
==========================================
Folosit de session1_m15_long.py si session2_m5_both.py.
Nu se ruleaza direct — ruleaza una dintre sesiuni.

Fiecare sesiune are config propriu (piete, TF, directie, sesiune, output).
Sesiunile sunt complet independente: capital separat, loguri separate.
"""

import os
import re
import sys
import json
import time
import pickle
import logging
import threading
import subprocess
import urllib.request
from datetime import datetime, timedelta
from tz_helper import now_local

import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest import CONFIG, DATA_DIR
from adapters.mt5_source import Mt5DataSource
from strategy.preparation import _enrich
from strategy.structure import detect_setup
from strategy.patterns import detect_flag, detect_inside_bar
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


class _NotificationHandler(logging.Handler):
    """
    Handler de logging care trimite automat mesajele WARNING/ERROR
    catre notification store din UI (api/notifications.py).
    Non-blocking — esecul nu afecteaza niciodata botul.

    Rate-limiting: acelasi mesaj (primele 80 caractere) se trimite max o data
    la 10 minute, prevenind flood-ul din WARNING-uri repetate la fiecare bara.
    """
    # Mesaje de ignora (spam frecvent, nu erori reale)
    _IGNORE = ("Niciun semnal nou", "Urmatoarea bara", "iter ", "Pornit.",
               "[DEDUP]", "[ORPHAN] Niciun")
    _COOLDOWN_SEC = 600   # 10 minute intre doua notificari cu acelasi prefix

    def __init__(self, session_id: str):
        super().__init__()
        self._session_id = session_id
        self._seen: dict[str, float] = {}   # prefix80 → timestamp ultima notificare

    def emit(self, record: logging.LogRecord) -> None:
        try:
            raw_msg = record.getMessage()
            if any(skip in raw_msg for skip in self._IGNORE):
                return
            # Rate-limiting pe primele 80 de caractere (ignora detalii variabile)
            key = raw_msg[:80]
            now = datetime.now().timestamp()
            last = self._seen.get(key, 0.0)
            if now - last < self._COOLDOWN_SEC:
                return
            self._seen[key] = now
            # Curata cache-ul periodic (max 200 intrari)
            if len(self._seen) > 200:
                oldest = sorted(self._seen.items(), key=lambda x: x[1])
                for k, _ in oldest[:50]:
                    self._seen.pop(k, None)
            from api.notifications import log_notification
            level_tag = "ERROR" if record.levelno >= logging.ERROR else "WARNING"
            log_notification(f"[{level_tag}][{self._session_id}] {raw_msg}")
        except Exception:
            pass


def _send_telegram(text: str) -> None:
    """Trimite mesaj Telegram in daemon thread — complet non-blocking pentru bot."""
    # Logheaza in notification store (independent de Telegram)
    try:
        from api.notifications import log_notification
        log_notification(text)
    except Exception:
        pass

    token, chat_id = _get_tg_creds()
    if not token or not chat_id:
        return

    def _do_send():
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
            urllib.request.urlopen(req, timeout=8)
        except Exception:
            pass

    threading.Thread(target=_do_send, daemon=True).start()


_MT5_HEALTH_ALERT_FILE = os.path.join("data", "mt5_health_alert.json")
_MT5_HEALTH_NOTIFIER   = "session1"  # singura sesiune care trimite Telegram
_MT5_HEALTH_MAX        = 2           # max 2 notificari per incident
_MT5_HEALTH_REPEAT_S   = 600         # a 2-a notificare dupa 10 min daca persista


def _check_mt5_health(log, session_key: str, expected_login: int) -> None:
    """
    Verifica sanatatea conexiunii MT5.

    DOAR session1 trimite Telegram — elimina race condition in care toate
    20 sesiunile trimiteau simultan (toate notificarile veneau odata).

    Per incident: max 2 notificari
      - prima: imediat la detectare
      - a doua: dupa 10 min daca problema persista (reminder final)
      - nimic dupa aceea pana la rezolvare + re-aparitie

    La rezolvare (reconnect, AutoTrading reactivat): 1 notificare de confirmare
    si resetare contor — urmatorul incident primeste din nou 2 notificari.
    """
    if _mt5_exec is None:
        return

    _can_notify = (session_key == _MT5_HEALTH_NOTIFIER)
    now = time.time()

    try:
        alerts = json.loads(open(_MT5_HEALTH_ALERT_FILE, encoding="utf-8").read())
    except Exception:
        alerts = {}

    changed = False

    def _entry(key: str) -> dict:
        e = alerts.get(key)
        return e if isinstance(e, dict) else {}

    def _should_alert(key: str) -> bool:
        if not _can_notify:
            return False
        e = _entry(key)
        count = e.get("count", 0)
        if count >= _MT5_HEALTH_MAX:
            return False                              # limita atinsa pentru acest incident
        if count == 0:
            return True                              # prima detectare — trimite imediat
        return now - e.get("last_sent", 0) > _MT5_HEALTH_REPEAT_S  # reminder dupa 10 min

    def _fire(key: str, text: str):
        nonlocal changed
        e     = _entry(key)
        count = e.get("count", 0) + 1
        alerts[key] = {"count": count, "last_sent": now}
        changed = True
        suffix = "\n<i>(reminder — problema persista)</i>" if count > 1 else ""
        log.warning(f"[MT5-HEALTH] {key} (#{count})")
        _send_telegram(text + suffix)

    def _resolve(key: str, text: str):
        """Trimite notificare de rezolvare si reseteaza contorul."""
        nonlocal changed
        if key not in alerts:
            return
        log.info(f"[MT5-HEALTH] {key} rezolvat")
        if _can_notify and _entry(key).get("count", 0) > 0:
            _send_telegram(text)
        del alerts[key]
        changed = True

    ti = _mt5_exec.terminal_info()
    if ti is None:
        log.warning("[MT5-HEALTH] terminal_info() = None — IPC pierdut")
        if _should_alert("ipc_lost"):
            _fire("ipc_lost",
                  "🔴 <b>MT5: Conexiune IPC pierduta</b>\n"
                  "terminal_info() = None. Verifica ca MT5 terminal este deschis.")
        if changed:
            _write_health_alerts(alerts)
        return

    # IPC recuperat — curata alerta IPC daca exista
    _resolve("ipc_lost",
             "✅ <b>MT5: Conexiune IPC restabilita</b>\nBotul reia monitorizarea normala.")

    # 1. Conexiune broker
    if not ti.connected:
        log.warning("[MT5-HEALTH] deconectat de la server broker")
        if _should_alert("disconnected"):
            _fire("disconnected",
                  "🔴 <b>MT5: Deconectat de la server broker</b>\n"
                  "MT5 nu are conexiune cu ICMarketsEU.\n"
                  "Verifica internetul sau statusul serverului broker.")
    else:
        _resolve("disconnected",
                 "✅ <b>MT5: Reconectat la server broker</b>\nBotul reia plasarea ordinelor.")

    # 2. AutoTrading
    if not ti.trade_allowed:
        log.warning("[MT5-HEALTH] AutoTrading dezactivat")
        if _should_alert("autotrading_off"):
            _fire("autotrading_off",
                  "⚠️ <b>MT5: AutoTrading DEZACTIVAT</b>\n"
                  "Ordinele nu pot fi plasate. Activeaza din toolbar MT5 (<code>Alt+A</code>).\n"
                  "Cauza frecventa: cont schimbat sau restart MT5.")
    else:
        _resolve("autotrading_off",
                 "✅ <b>MT5: AutoTrading reactivat</b>\nOrdinele pot fi plasate din nou.")

    # 3. Cont schimbat
    acc = _mt5_exec.account_info()
    if acc is None:
        log.warning("[MT5-HEALTH] account_info() = None")
        if _should_alert("account_null"):
            _fire("account_null",
                  "🔴 <b>MT5: account_info() = None</b>\n"
                  "Contul nu raspunde — posibil deautorizat sau schimbat.\n"
                  "Relogheaza-te in MT5 terminal.")
    elif expected_login > 0 and acc.login != expected_login:
        log.warning(f"[MT5-HEALTH] cont schimbat: {expected_login} -> {acc.login}")
        if _should_alert("account_changed"):
            _fire("account_changed",
                  f"🔴 <b>MT5: Cont schimbat!</b>\n"
                  f"Asteptat: <code>{expected_login}</code>\n"
                  f"Activ acum: <code>{acc.login}</code> @ {acc.server}\n"
                  "Relogheza-te in contul demo corect si reactiveza AutoTrading.")
    else:
        _resolve("account_null",
                 "✅ <b>MT5: Cont restaurat</b>\nAccount info disponibil din nou.")
        _resolve("account_changed",
                 f"✅ <b>MT5: Cont corect activ</b> (<code>{expected_login}</code>)")

    if changed:
        _write_health_alerts(alerts)


def _write_health_alerts(alerts: dict) -> None:
    try:
        with open(_MT5_HEALTH_ALERT_FILE, "w", encoding="utf-8") as _f:
            json.dump(alerts, _f)
    except Exception:
        pass


def _calc_lots(symbol: str, entry: float, sl: float,
               capital: float, risk_pct: float) -> tuple[float, float | None]:
    """Calculeaza lotajul si riscul real in USD pentru 1R.

    Returns:
        (lots, risk_usd) — risk_usd = lot × sl_pips × pip_val (USD efectiv per 1R)
                           risk_usd = None daca MT5 nedisponibil
    """
    if _mt5_exec is None:
        return 0.01, None
    info = _mt5_exec.symbol_info(symbol)
    if info is None:
        return 0.01, None
    pip     = pip_size(symbol)
    sl_pips = abs(entry - sl) / pip
    if sl_pips <= 0 or info.trade_tick_size <= 0:
        return info.volume_min, None
    pip_val = info.trade_tick_value / info.trade_tick_size * pip
    if pip_val <= 0:
        return info.volume_min, None
    raw  = (capital * risk_pct) / (sl_pips * pip_val)
    step = info.volume_step if info.volume_step > 0 else 0.01
    lot  = max(info.volume_min, (raw // step) * step)
    lot  = round(lot, 2)
    risk_usd = round(lot * sl_pips * pip_val, 4)
    return lot, risk_usd


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
    sym_info = _mt5_exec.symbol_info(symbol)

    if tick is not None:
        if direction == 1 and tick.ask >= sig["entry"]:
            log.info(f"  [EXEC] {sig['signal_id']}: BUY_STOP amanat "
                     f"(Ask {tick.ask:.5f} >= entry {sig['entry']:.5f}) — retry bara urm.")
            return None
        if direction == -1 and tick.bid <= sig["entry"]:
            log.info(f"  [EXEC] {sig['signal_id']}: SELL_STOP amanat "
                     f"(Bid {tick.bid:.5f} <= entry {sig['entry']:.5f}) — retry bara urm.")
            return None

        # Verifica distanta minima fata de pret (trade_stops_level).
        # Daca entry e prea aproape de pret curent, brokerul respinge ordinul (10006/10014).
        # Retry la bara urmatoare — pretul se va distanta natural de entry.
        if sym_info is not None and sym_info.trade_stops_level > 0:
            min_dist = sym_info.trade_stops_level * sym_info.point
            cur_price = tick.ask if direction == 1 else tick.bid
            dist = abs(cur_price - sig["entry"])
            if dist < min_dist:
                log.info(f"  [EXEC] {sig['signal_id']}: entry prea aproape de pret curent "
                         f"(dist={dist:.{sym_info.digits}f} < min={min_dist:.{sym_info.digits}f}) "
                         f"— retry bara urm.")
                return None

    order_type = (_mt5_exec.ORDER_TYPE_BUY_STOP
                  if direction == 1 else _mt5_exec.ORDER_TYPE_SELL_STOP)
    fm       = sym_info.filling_mode if sym_info else 0
    # MT5 filling_mode bitmask: bit 0 (1) = FOK suportat, bit 1 (2) = IOC suportat.
    # RETURN nu are bit propriu — e default pt Forex (fm=0).
    # Crypto/indici au de obicei fm!=0 → prioritizam modurile declarate de broker,
    # cu RETURN ca fallback (evitam retcode 10006/10030 din prima incercare).
    if fm == 0:
        fill_modes = [_mt5_exec.ORDER_FILLING_RETURN,
                      _mt5_exec.ORDER_FILLING_FOK,
                      _mt5_exec.ORDER_FILLING_IOC]
    else:
        bitmask_modes = []
        if fm & 1: bitmask_modes.append(_mt5_exec.ORDER_FILLING_FOK)
        if fm & 2: bitmask_modes.append(_mt5_exec.ORDER_FILLING_IOC)
        leftover = [m for m in [_mt5_exec.ORDER_FILLING_FOK, _mt5_exec.ORDER_FILLING_IOC]
                    if m not in bitmask_modes]
        fill_modes = bitmask_modes + [_mt5_exec.ORDER_FILLING_RETURN] + leftover

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

    all_none    = True   # True daca niciun order_send nu a returnat macar un retcode
    all_10006   = True   # True daca toate retcode-urile non-None au fost 10006
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
        if result.retcode != 10006:
            all_10006 = False
        if result.retcode in (10026, 10027):
            # AutoTrading dezactivat (server sau client) — setare temporara, retry bara urm.
            log.warning(f"  [EXEC] {sig['signal_id']}: AutoTrading dezactivat — retry bara urm.")
            return None
        if result.retcode in (10012, 10031):
            # 10012 = timeout (cerere trimisa, fara raspuns) — nu stim daca a ajuns pe server
            # 10031 = no connection with trade server — MT5 terminal deconectat temporar de la broker
            # Ambele sunt tranzitorii, nu probleme de filling — retry bara urm.
            log.warning(f"  [EXEC] {sig['signal_id']}: retcode={result.retcode} conexiune/timeout — retry bara urm.")
            return None
        if result.retcode not in (10030, 10006):
            # 10030 = invalid fill type, 10006 = reject generic (ICMarketsEU crypto returneaza
            # 10006 in loc de 10030 cand filling mode e incompatibil) — incercam alt filling.
            # Orice alt retcode (pret gresit, volum, etc) = eroare reala, iesim imediat.
            return False

    # Ultima sansa: fara type_filling (lasa MT5 sa aleaga implicit)
    request.pop("type_filling", None)
    result = _mt5_exec.order_send(request)
    if result is not None:
        all_none = False
        log.warning(f"  [EXEC] {sig['signal_id']}: fara filling → "
                    f"retcode={result.retcode} ({result.comment})")
        if result.retcode != 10006:
            all_10006 = False
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
        log.warning(f"  [EXEC] {sig['signal_id']}: toate order_send → None "
                    f"(conexiune MT5?) — retry bara urm.")
        return None

    if all_10006:
        # Toate incercarile au returnat 10006 — ICMarketsEU returneaza 10006 si pentru
        # piata temporar inchisa (crypto weekend/maintenance), nu doar 10018 ca standard.
        # Retinem semnalul si reincercam; va expira natural dupa expire_bars.
        log.warning(f"  [EXEC] {sig['signal_id']}: toate incercarile → 10006 "
                    f"(piata probabil inchisa temporar) — retry bara urm.")
        return None

    log.warning(f"  [EXEC] {sig['signal_id']}: niciun mod de umplere acceptat "
                f"(filling_mode={fm}, incercate={fill_modes} + fara filling).")
    return False


def _close_position_robust(symbol: str, volume: float, order_type,
                           position: int, price: float, comment: str, log):
    """
    Inchide o pozitie deschisa (TRADE_ACTION_DEAL) incercand mai multe moduri
    de filling: IOC → FOK → RETURN → fara filling.

    Returneaza result-ul MT5 (retcode verificat de apelant) sau None (conexiune pierduta).
    Continua cu alt filling doar la 10006/10030; orice alta eroare e returnata imediat.
    """
    if _mt5_exec is None:
        return None

    base_req = {
        "action":    _mt5_exec.TRADE_ACTION_DEAL,
        "symbol":    symbol,
        "volume":    volume,
        "type":      order_type,
        "position":  position,
        "price":     price,
        "comment":   comment,
        "type_time": _mt5_exec.ORDER_TIME_GTC,
    }
    for filling in [_mt5_exec.ORDER_FILLING_IOC,
                    _mt5_exec.ORDER_FILLING_FOK,
                    _mt5_exec.ORDER_FILLING_RETURN]:
        result = _mt5_exec.order_send({**base_req, "type_filling": filling})
        if result is None:
            continue
        if result.retcode == _mt5_exec.TRADE_RETCODE_DONE:
            return result
        if result.retcode in (10012, 10031):
            if log:
                log.warning(f"  [CLOSE] {comment} {symbol}: filling={filling} "
                            f"retcode={result.retcode} timeout/no-conn — incercam alt filling")
            continue
        if result.retcode not in (10030, 10006):
            if log:
                log.warning(f"  [CLOSE] {comment} {symbol}: filling={filling} "
                            f"retcode={result.retcode} — eroare reala, nu mai incercam")
            return result
        if log:
            log.warning(f"  [CLOSE] {comment} {symbol}: filling={filling} "
                        f"retcode={result.retcode} — incercam alt filling")
    # Ultima sansa: fara type_filling
    return _mt5_exec.order_send(base_req)


def _cancel_mt5_order(ticket: int, sig_id: str, reason: str, log) -> bool:
    """
    Anuleaza un ordin pending MT5 (TRADE_ACTION_REMOVE).
    Returneaza True daca ordinul a disparut (anulat sau deja disparut din MT5).
    Logheaza la INFO daca era deja disparut (nu e eroare), WARNING la esec real.
    """
    if _mt5_exec is None:
        return False
    _r = _mt5_exec.order_send({
        "action": _mt5_exec.TRADE_ACTION_REMOVE,
        "order":  ticket,
    })
    if _r and _r.retcode == _mt5_exec.TRADE_RETCODE_DONE:
        log.info(f"  [EXEC] {sig_id}: ordin MT5 #{ticket} anulat ({reason})")
        return True
    # Verifica daca ordinul mai exista in MT5
    still_open = _mt5_exec.orders_get(ticket=ticket)
    if not still_open:
        # Nu mai e in MT5 — triggerat sau deja anulat/expirat manual
        log.info(f"  [EXEC] {sig_id}: ordin MT5 #{ticket} deja disparut din MT5 ({reason}) — ok")
        return True
    # Ordinul inca exista dar nu l-am putut anula — eroare reala
    err = _mt5_exec.last_error()
    retcode = _r.retcode if _r else "None"
    log.warning(
        f"  [EXEC] {sig_id}: anulare MT5 #{ticket} ESUATA ({reason}) "
        f"retcode={retcode} last_error={err} — ordinul ramane deschis in MT5!"
    )
    return False


def _notify_signal(sig: dict, session_id: str, telegram: bool = True) -> None:
    """
    Notificare Windows Toast + Telegram + terminal bell la detectarea unui semnal nou.
    Non-blocking. Esecul notificarii nu opreste sesiunea.

    telegram=False cand execute_trades=True — Telegram-ul este trimis separat in
    "Ordin plasat" (cu ticket + lots), evitand doua notificari identice la distanta
    de secunde pentru acelasi eveniment.
    """
    # Bell in terminal
    sys.stdout.write("\a")
    sys.stdout.flush()

    sym = sig["symbol"]
    fmt = ".2f" if sig["entry"] > 100 else ".5f"
    entry = format(sig["entry"], fmt)
    tp    = format(sig["tp"],    fmt)
    sl    = format(sig["sl"],    fmt)

    sig_type = sig.get("signal_type", "pullback")
    if sig_type == "flag":
        type_label = "FLAG"
    elif sig_type == "inside_bar":
        type_label = "INSIDE BAR"
    else:
        type_label = "PULLBACK"

    title = f"[{type_label}] {sig['dir_str']} {sym}"
    body  = f"{session_id} | entry {entry}  SL {sl}  TP {tp}  ({sig['r_ratio']:.1f}R)"

    # Telegram — trimis doar pentru sesiuni obs (execute_trades=False).
    # Cand execute_trades=True, notificarea Telegram vine din "Ordin plasat" (cu ticket).
    if telegram:
        _send_telegram(
            f"<b>[{type_label}] {sig['dir_str']} {sym}</b>\n"
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
    now = now_local()
    mod = now.minute % bar_minutes
    mins_to_next = bar_minutes - mod
    nxt = now + timedelta(minutes=mins_to_next)
    return nxt.replace(second=5, microsecond=0)


def _sleep_to_next_bar(bar_minutes: int, log):
    nxt = _next_bar_close(bar_minutes)
    wait = (nxt - now_local()).total_seconds()
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
    # Daca inchiderea vineri e activa, skip automat Sambata (5) si Duminica (6)
    if session_cfg.get("friday_close_enabled", True):
        skip_weekdays |= {5, 6}

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

        pending_for_sym = state["pending"].get(symbol, {})
        # Slot per tip: pullback = limitat de max_concurrent; flag/IB = slot independent
        pb_pending_count = sum(1 for p in pending_for_sym.values()
                               if p.get("signal_type", "pullback") == "pullback")
        fl_pending_count = sum(1 for p in pending_for_sym.values()
                               if p.get("signal_type") == "flag")
        ib_pending_count = sum(1 for p in pending_for_sym.values()
                               if p.get("signal_type") == "inside_bar")

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

        # --- Pullback-in-trend ---
        _pb_found = None
        if pb_pending_count < max_concurrent:
            _delay_ok = True
            if min_bars_between > 0 and pending_for_sym:
                pb_only = {k: v for k, v in pending_for_sym.items()
                           if v.get("signal_type", "pullback") == "pullback"}
                if pb_only:
                    last_armed = max(
                        pd.Timestamp(p.get("armed_at", pd.Timestamp.min))
                        for p in pb_only.values()
                    )
                    bars_since = (t - last_armed).total_seconds() / (tf_minutes * 60)
                    if bars_since < min_bars_between:
                        _delay_ok = False
            if _delay_ok:
                _pb_found = detect_setup(df, j, direction, window=pw)
        found = _pb_found
        if found is not None:
            ext, _ = found
            if direction == 1:
                entry = row["high"] + buf
                sl    = ext - buf
            else:
                entry = row["low"] - buf
                sl    = ext + buf
            risk_dist = abs(entry - sl)
            if risk_dist > 0:
                n_opt  = count_optional(row, direction, cfg)
                R      = reward_R(n_opt, cfg)
                tp     = entry + direction * risk_dist * R
                state["signal_counter"] += 1
                sig_id = f"{session_cfg['session_id']}-SIG{state['signal_counter']:04d}"
                sigs.append({
                    "signal_id":  sig_id,
                    "time":       t,
                    "symbol":     symbol,
                    "direction":  direction,
                    "dir_str":    "LONG" if direction == 1 else "SHORT",
                    "entry":      round(entry, 5),
                    "sl":         round(sl, 5),
                    "tp":         round(tp, 5),
                    "r_ratio":    round(R, 1),
                    "atr_pips":   round(row.get("atr", 0) / pip, 1),
                    "n_optional": n_opt,
                    "rsi":        round(row.get("rsi", 0), 1),
                    "signal_type": "pullback",
                })

        # --- Flag Pattern (optional, independent — slot propriu) ---
        if session_cfg.get("flag_enabled", False) and fl_pending_count < 1:
            _fcfg = {
                "pole_min_candles":     session_cfg.get("flag_pole_min_candles",    3),
                "pole_min_body_atr":    session_cfg.get("flag_pole_min_body_atr",   0.5),
                "flag_min_bars":        session_cfg.get("flag_min_bars",             2),
                "flag_max_bars":        session_cfg.get("flag_max_bars",             5),
                "flag_max_retrace_pct": session_cfg.get("flag_max_retrace_pct",    50),
            }
            f_res = detect_flag(df, j, direction, _fcfg)
            if f_res is not None:
                sl_lv, _ = f_res
                # Entry la HIGH-ul barei de breakout + buf — BUY_STOP valid in MT5.
                if direction == 1:
                    f_entry = row["high"] + buf; f_sl = sl_lv - buf
                else:
                    f_entry = row["low"] - buf; f_sl = sl_lv + buf
                f_risk = abs(f_entry - f_sl)
                if f_risk > 0:
                    f_R  = float(session_cfg.get("flag_r_ratio", 2.0))
                    f_tp = f_entry + direction * f_risk * f_R
                    state["flag_signal_counter"] += 1
                    flg_id = f"{session_cfg['session_id']}-FLG{state['flag_signal_counter']:04d}"
                    sigs.append({
                        "signal_id":  flg_id,
                        "time":       t,
                        "symbol":     symbol,
                        "direction":  direction,
                        "dir_str":    "LONG" if direction == 1 else "SHORT",
                        "entry":      round(f_entry, 5),
                        "sl":         round(f_sl, 5),
                        "tp":         round(f_tp, 5),
                        "r_ratio":    round(f_R, 1),
                        "atr_pips":   round(row.get("atr", 0) / pip, 1),
                        "n_optional": 0,
                        "rsi":        round(row.get("rsi", 0), 1),
                        "signal_type": "flag",
                    })

        # --- Inside Bar Breakout (optional, independent — slot propriu) ---
        if session_cfg.get("inside_bar_enabled", False) and ib_pending_count < 1:
            ib_res = detect_inside_bar(df, j, direction)
            if ib_res is not None:
                sl_lv, _ = ib_res
                # Entry la HIGH-ul barei de breakout + buf — BUY_STOP valid in MT5.
                if direction == 1:
                    ib_entry = row["high"] + buf; ib_sl = sl_lv - buf
                else:
                    ib_entry = row["low"] - buf; ib_sl = sl_lv + buf
                ib_risk = abs(ib_entry - ib_sl)
                if ib_risk > 0:
                    ib_R  = float(session_cfg.get("inside_bar_r_ratio", 2.0))
                    ib_tp = ib_entry + direction * ib_risk * ib_R
                    state["ib_signal_counter"] += 1
                    ib_id = f"{session_cfg['session_id']}-IB{state['ib_signal_counter']:04d}"
                    sigs.append({
                        "signal_id":  ib_id,
                        "time":       t,
                        "symbol":     symbol,
                        "direction":  direction,
                        "dir_str":    "LONG" if direction == 1 else "SHORT",
                        "entry":      round(ib_entry, 5),
                        "sl":         round(ib_sl, 5),
                        "tp":         round(ib_tp, 5),
                        "r_ratio":    round(ib_R, 1),
                        "atr_pips":   round(row.get("atr", 0) / pip, 1),
                        "n_optional": 0,
                        "rsi":        round(row.get("rsi", 0), 1),
                        "signal_type": "inside_bar",
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

    entry_deal = next(
        (deal for deal in deals if deal.entry == 0),  # DEAL_ENTRY_IN = 0
        None,
    )
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

    pnl_usd        = round(float(close_deal.profit), 4)
    commission_usd = round(
        float(getattr(entry_deal, "commission", 0) or 0) +
        float(getattr(close_deal, "commission", 0) or 0),
        4,
    )
    swap_usd = round(float(getattr(close_deal, "swap", 0) or 0), 4)
    log.info(
        f"  [MT5] Pozitie #{ticket} inchisa: "
        f"exit={exit_price}  result={result_r:+.3f}R  pnl={pnl_usd:+.2f}USD  "
        f"comm={commission_usd:+.2f}  swap={swap_usd:+.2f}  [{status}]"
    )
    return {
        "status":         status,
        "result_r":       result_r,
        "exit_price":     exit_price,
        "exit_time":      exit_time,
        "triggered_at":   p.get("triggered_at", exit_time),
        "pnl_usd":        pnl_usd,
        "commission_usd": commission_usd,
        "swap_usd":       swap_usd,
    }


_SIGNALS_COLS = [
    "signal_id", "time", "symbol", "direction", "dir_str",
    "entry", "sl", "tp", "r_ratio", "atr_pips", "n_optional", "rsi",
]

# ---------------------------------------------------------------------------
# Update outcome-uri
# ---------------------------------------------------------------------------

_OUTCOMES_COLS = [
    "signal_id", "time_check", "symbol", "direction", "status",
    "entry", "sl", "tp", "r_ratio", "armed_at", "triggered_at",
    "exit_price", "exit_time", "result_r", "pnl_usd",
    "commission_usd", "swap_usd",
]


def _pnl(result_r: float, risk_usd: float | None) -> float | None:
    """Calculeaza pnl_usd din result_r si risk_usd stocat la plasare."""
    return round(result_r * risk_usd, 4) if risk_usd is not None else None


def _usd_str(pnl: float | None) -> str:
    """Formateaza pnl_usd pentru mesaje Telegram. Returneaza '' daca None."""
    if pnl is None:
        return ""
    sign = "+" if pnl >= 0 else ""
    return f" ({sign}{pnl:.2f} USD)"


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
            "phase2_enabled":  session_cfg.get("be_phase2_enabled",  True),
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
                        # VERIFICA INAINTE: pozitia poate fi triggerata si inchisa
                        # in lipsa botului (crash / restart). MT5 are prioritate.
                        _mt5_res = _check_mt5_position_closed(_ticket, p, log)
                        if _mt5_res and not _mt5_res.get("__no_outcome__"):
                            # Pozitie reala inchisa cu TP/SL — corectam in loc de "expirat"
                            log.warning(
                                f"  [RECOVER] {sig_id}: ar fi fost marcat 'expirat' dar "
                                f"pozitia MT5 #{_ticket} era INCHISA — corectez la "
                                f"{_mt5_res['status']} {_mt5_res['result_r']:+.3f}R"
                            )
                            _send_telegram(
                                f"<b>[RECOVER] {sig_id}</b>\n"
                                f"Pozitie recuperata: {_mt5_res['status']} "
                                f"{_mt5_res['result_r']:+.3f}R | "
                                f"{_mt5_res.get('pnl_usd', 0):+.2f} USD\n"
                                f"<i>{session_id} — pozitie inchisa in lipsa botului</i>"
                            )
                            outcome_rows.append({**p, "signal_id": sig_id,
                                                 "symbol": symbol,
                                                 **_mt5_res, "time_check": now_local()})
                        else:
                            # Ordin inca pending sau inexistent → anulare + expirat
                            _cancel_mt5_order(_ticket, sig_id, "expirat", log)
                            outcome_rows.append({**p, "signal_id": sig_id,
                                                 "symbol": symbol,
                                                 "status": "expirat", "result_r": 0.0,
                                                 "exit_time": current_bar_t,
                                                 "time_check": now_local(),
                                                 "pnl_usd": 0.0})
                            _send_telegram(
                                f"<b>EXPIRAT: {symbol}</b>\n"
                                f"Ordinul nu a fost triggerat (>{expire_bars} bare)\n"
                                f"<i>{session_id} | {sig_id}</i>"
                            )
                        state["mt5_tickets"].pop(sig_id, None)
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
                        # VERIFICA INAINTE: pozitia poate fi deja inchisa cu TP/SL real
                        _mt5_res = _check_mt5_position_closed(_ticket, p, log)
                        if _mt5_res and not _mt5_res.get("__no_outcome__"):
                            log.warning(
                                f"  [RECOVER] {sig_id}: bar invalideaza dar MT5 #{_ticket} "
                                f"era deja INCHIS — corectez la "
                                f"{_mt5_res['status']} {_mt5_res['result_r']:+.3f}R"
                            )
                            outcome_rows.append({**p, "signal_id": sig_id,
                                                 "symbol": symbol,
                                                 **_mt5_res, "time_check": now_local()})
                        else:
                            _cancel_mt5_order(_ticket, sig_id, "invalidat", log)
                            outcome_rows.append({**p, "signal_id": sig_id,
                                                 "symbol": symbol,
                                                 "status": "invalidat", "result_r": 0.0,
                                                 "time_check": now_local(),
                                                 "pnl_usd": 0.0})
                            _dir_str = "LONG" if d == 1 else "SHORT"
                            _send_telegram(
                                f"<b>INVALIDAT #{_ticket}: {_dir_str} {symbol}</b>\n"
                                f"Structura ruptă — ordinul anulat din MT5\n"
                                f"Entry {p['entry']} | SL {p['sl']} | {p.get('r_ratio', '?')}R\n"
                                f"<i>{session_id} | {sig_id}</i>"
                            )
                        state["mt5_tickets"].pop(sig_id, None)
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
                    # Notificare Telegram: ordin activat in MT5 (doar execute_trades=True)
                    if execute_trades:
                        _ticket = state.get("mt5_tickets", {}).get(sig_id)
                        _ticket_str = f" #{_ticket}" if _ticket else ""
                        _fmt = ".2f" if p["entry"] > 100 else ".5f"
                        _dir = "LONG" if d == 1 else "SHORT"
                        _send_telegram(
                            f"<b>ACTIVAT{_ticket_str}: {_dir} {symbol}</b>\n"
                            f"Entry {format(p['entry'], _fmt)} | "
                            f"SL {format(p['sl'], _fmt)} | "
                            f"TP {format(p['tp'], _fmt)} ({p['r_ratio']:.1f}R)\n"
                            f"<i>{session_id} | {sig_id}</i>"
                        )
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
                                         **mt5_res, "time_check": now_local()})
                    if mt5_res["status"] == "TP":
                        log.info(f"  PROFIT (MT5): {sig_id} TP +{mt5_res['result_r']:.3f}R")
                        _send_telegram(
                            f"<b>PROFIT +{mt5_res['result_r']:.2f}R: {dir_str} {symbol}</b>"
                            f"{_usd_str(mt5_res.get('pnl_usd'))}\n"
                            f"Entry {format(p['entry'], fmt)} → "
                            f"{format(mt5_res['exit_price'], fmt)} (exit real MT5)\n"
                            f"<i>{session_id} | {sig_id}</i>"
                        )
                    else:
                        log.info(f"  PIERDERE (MT5): {sig_id} SL {mt5_res['result_r']:.3f}R")
                        _send_telegram(
                            f"<b>PIERDERE {mt5_res['result_r']:.2f}R: {dir_str} {symbol}</b>"
                            f"{_usd_str(mt5_res.get('pnl_usd'))}\n"
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
                        _be_p2_on = _be_cfg.get("phase2_enabled", True)
                        if _bep == 0 and _r80: _bep = 1
                        if _bep == 1 and _rev: _bep = 2; _nsl = _be30; _pname = "phase1"
                        if _bep == 2 and _be_p2_on:
                            if _inz: p["be_in_zone"] = True
                            if p.get("be_in_zone") and _r80: _bep = 3
                        if _bep == 3 and _rev and _be_p2_on: _bep = 4; _nsl = _be50; _pname = "phase2"
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
                _be_p2_on_bb = _be_cfg.get("phase2_enabled", True)
                for _, bar in df_aft.iterrows():
                    if d == 1:
                        _r80 = bar["high"] >= _be80; _rev80 = bar["low"] < _be80
                        _inz = _be30 < bar["low"] <= _be40
                    else:
                        _r80 = bar["low"] <= _be80;  _rev80 = bar["high"] > _be80
                        _inz = _be40 <= bar["high"] < _be30
                    if _bep == 0 and _r80:  _bep = 1
                    if _bep == 1 and _rev80: _bep = 2; _be_csl = _be30; _new_n.add(2)
                    if _bep == 2 and _be_p2_on_bb:
                        if _inz: _be_inz = True
                        if _be_inz and _r80: _bep = 3
                    if _bep == 3 and _rev80 and _be_p2_on_bb: _bep = 4; _be_csl = _be50; _new_n.add(4)
                    _sl_hit = (d == 1 and bar["low"] <= _be_csl) or (d == -1 and bar["high"] >= _be_csl)
                    _tp_hit = (d == 1 and bar["high"] >= p["tp"]) or (d == -1 and bar["low"] <= p["tp"])
                    if _sl_hit:
                        if _bep >= 4:   _oc = "be_lock2"; _rr = round((_be_csl - p["entry"]) * d / abs(p["entry"] - p["sl"]), 3)
                        elif _bep >= 2: _oc = "be_lock";  _rr = round((_be_csl - p["entry"]) * d / abs(p["entry"] - p["sl"]), 3)
                        else:           _oc = "SL";       _rr = -1.0
                        outcome_rows.append({**p, "signal_id": sig_id, "symbol": symbol,
                                             "status": _oc, "result_r": _rr,
                                             "exit_price": _be_csl, "exit_time": bar["time"],
                                             "time_check": now_local(),
                                             "pnl_usd": _pnl(_rr, p.get("risk_usd"))})
                        rows_to_remove.append(sig_id)
                        if _oc == "SL":
                            _pnl_val = _pnl(_rr, p.get("risk_usd"))
                            log.info(f"  PIERDERE: {sig_id} SL -1.0R")
                            _send_telegram(
                                f"<b>PIERDERE -1R: {dir_str} {symbol}</b>"
                                f"{_usd_str(_pnl_val)}\n"
                                f"Entry {format(p['entry'], fmt)} → SL {format(p['sl'], fmt)}\n"
                                f"<i>{session_id} | {sig_id}</i>"
                            )
                        else:
                            _pnl_val = _pnl(_rr, p.get("risk_usd"))
                            _lbl = "Faza 1" if _oc == "be_lock" else "Faza 2"
                            log.info(f"  [BE {_lbl}] {sig_id} +{_rr:.3f}R")
                            _send_telegram(
                                f"<b>Break-Even {_lbl}: {dir_str} {symbol}</b>"
                                f"{_usd_str(_pnl_val)}\n"
                                f"Ieșire la +{_rr:.2f}R\n"
                                f"<i>{session_id} | {sig_id}</i>"
                            )
                        break
                    if _tp_hit:
                        outcome_rows.append({**p, "signal_id": sig_id, "symbol": symbol,
                                             "status": "TP", "result_r": p["r_ratio"],
                                             "exit_price": p["tp"], "exit_time": bar["time"],
                                             "time_check": now_local(),
                                             "pnl_usd": _pnl(p["r_ratio"], p.get("risk_usd"))})
                        rows_to_remove.append(sig_id)
                        _pnl_tp = _pnl(p["r_ratio"], p.get("risk_usd"))
                        log.info(f"  PROFIT: {sig_id} TP +{p['r_ratio']:.1f}R")
                        _send_telegram(
                            f"<b>PROFIT +{p['r_ratio']:.1f}R: {dir_str} {symbol}</b>"
                            f"{_usd_str(_pnl_tp)}\n"
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
                        _sl_pnl = _pnl(-1.0, p.get("risk_usd"))
                        outcome_rows.append({**p, "signal_id": sig_id,
                                             "symbol": symbol, "status": "SL",
                                             "result_r": -1.0, "exit_price": p["sl"],
                                             "exit_time": bar["time"],
                                             "time_check": now_local(),
                                             "pnl_usd": _sl_pnl})
                        rows_to_remove.append(sig_id)
                        log.info(f"  PIERDERE: {sig_id} SL -1.0R")
                        _send_telegram(
                            f"<b>PIERDERE -1R: {dir_str} {symbol}</b>"
                            f"{_usd_str(_sl_pnl)}\n"
                            f"Entry {format(p['entry'], fmt)} → SL {format(p['sl'], fmt)}\n"
                            f"<i>{session_id} | {sig_id}</i>"
                        )
                        break
                    if tp_hit:
                        _tp_pnl = _pnl(p["r_ratio"], p.get("risk_usd"))
                        outcome_rows.append({**p, "signal_id": sig_id,
                                             "symbol": symbol, "status": "TP",
                                             "result_r": p["r_ratio"], "exit_price": p["tp"],
                                             "exit_time": bar["time"],
                                             "time_check": now_local(),
                                             "pnl_usd": _tp_pnl})
                        rows_to_remove.append(sig_id)
                        log.info(f"  PROFIT: {sig_id} TP +{p['r_ratio']:.1f}R")
                        _send_telegram(
                            f"<b>PROFIT +{p['r_ratio']:.1f}R: {dir_str} {symbol}</b>"
                            f"{_usd_str(_tp_pnl)}\n"
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
        # Dedup si in interiorul batch-ului (ex: doua semnale cu acelasi sig_id trunchiat)
        seen_in_batch: set = set()
        new_rows = []
        for r in outcome_rows:
            sid = r.get("signal_id")
            if sid not in existing_ids and sid not in seen_in_batch:
                new_rows.append(r)
                seen_in_batch.add(sid)
        if new_rows:
            pd.DataFrame(new_rows).reindex(columns=_OUTCOMES_COLS).to_csv(
                outcomes_file, mode="a", header=False, index=False)

    for sig_id in rows_to_remove:
        state["pending"][symbol].pop(sig_id, None)


# ---------------------------------------------------------------------------
# Migrare format vechi pending la format nou (ruleaza o singura data la pornire)
# ---------------------------------------------------------------------------

def _migrate_pending_format(state: dict, session_cfg: dict, log) -> None:
    """
    Detecteaza si migraz semnalele in format vechi (flat) la formatul nou (nested).

    Format vechi (inainte de refactorizare multi-simbol):
        state["pending"] = { "S1-EURUSD-SIG0001": {entry, sl, tp, time, ...} }

    Format nou (curent):
        state["pending"] = { "EURUSD": { "S1-EURUSD-SIG0002": {entry, sl, tp, armed_at, ...} } }

    Semnele unui entry in format vechi:
      - cheia nu e un simbol (nu e all-caps simplu), ci un signal ID (contine '-' si 'SIG'/'IB'/'FLG')
      - valoarea e un dict cu campul 'entry' (semnalul efectiv)

    Semnele unui entry corrupt gol:
      - cheia e un simbol (all-caps, fara '-') iar valoarea e {} (dict gol)
    """
    pending = state.get("pending", {})
    all_symbols = {sym for mk in session_cfg.get("markets", []) for sym in [mk]}
    # Adauga si simbolurile din fallbacks
    for v in session_cfg.get("symbol_fallbacks", {}).values():
        if isinstance(v, list):
            all_symbols.update(v)
        else:
            all_symbols.add(v)

    migrated = 0
    removed_empty = 0

    for key in list(pending.keys()):
        value = pending[key]
        # Detecteaza intrari in format vechi: cheia contine '-' si valoarea are 'entry'
        if "-" in key and isinstance(value, dict) and "entry" in value:
            # Extrage simbolul din campul 'symbol' al semnalului sau din signal_id
            sym = value.get("symbol") or key.split("-")[1] if "-" in key else None
            if not sym:
                continue
            # Adauga campurile lipsa necesare de _update_outcomes
            if "armed_at" not in value or not value.get("armed_at"):
                # Fallback: "time" din semnal, sau epoch (semnal va expira imediat)
                value["armed_at"] = value.get("time") or "2000-01-01 00:00:00"
            value.setdefault("signal_type",        "pullback")
            value.setdefault("be_phase",           0)
            value.setdefault("be_current_sl",      value["sl"])
            value.setdefault("be_in_zone",         False)
            value.setdefault("be_notified_phases", set())
            value.setdefault("be_last_t",          None)
            # Muta la noua locatie: pending[symbol][sig_id]
            pending.pop(key)
            pending.setdefault(sym, {})[key] = value
            log.warning(
                f"  [MIGRATE] Semnal in format vechi detectat si migrat: "
                f"{key} -> pending[{sym}][{key}]"
            )
            migrated += 1

    # Sterge cheile goale de tip simbol (corrupt empty dicts)
    for key in list(pending.keys()):
        value = pending[key]
        is_symbol_like = (key == key.upper() and "-" not in key and len(key) >= 3)
        if is_symbol_like and isinstance(value, dict) and len(value) == 0:
            pending.pop(key)
            log.warning(f"  [MIGRATE] Cheie goala stearsa din pending: {key!r}")
            removed_empty += 1

    if migrated or removed_empty:
        log.info(
            f"  [MIGRATE] Migrare pending: {migrated} semnale migrate, "
            f"{removed_empty} chei goale sterse."
        )


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


def _recover_lost_outcomes(
    state: dict,
    session_cfg: dict,
    outcomes_file: str,
    log,
) -> None:
    """
    Startup: pentru semnale pending FARA ticket MT5 cunoscut, cauta in history MT5
    ordine cu comment = signal_id (plasate de bot in sesiunile anterioare).

    Scenariul acoperit: botul a plasat un ordin, l-a triggerat, pozitia s-a inchis
    (TP/SL), dar state.pkl a fost sters intre timp (crash / reset manual).
    Fara aceasta functie, semnalul ar fi marcat 'expirat 0R' la urmatoarea bara.

    MT5 are prioritate — daca MT5 zice SL, se scrie SL, indiferent de bare.
    """
    if _mt5_exec is None:
        return
    # Sesiunile de observatie (execute_trades=False) nu plaseaza ordine in MT5
    if not session_cfg.get("execute_trades", True):
        return

    pending = state.get("pending", {})
    mt5_tickets = state.get("mt5_tickets", {})

    sigs_without_ticket = [
        (sym, sig_id, sig)
        for sym, sym_sigs in pending.items()
        for sig_id, sig in sym_sigs.items()
        if sig_id not in mt5_tickets
    ]
    if not sigs_without_ticket:
        return

    log.info(f"  [RECOVER] Verificare {len(sigs_without_ticket)} semnale fara ticket MT5 in history...")
    dt_from = datetime.now() - timedelta(days=10)
    dt_to   = datetime.now()
    recovered = 0

    # Previne doua semnale diferite sa claim-uiasca acelasi ordin MT5
    # (ICMarketsEU trunchiaza la 16 chars → SIG0001/SIG0002 devin ambele "S13-EURJPY-SIG00")
    claimed_tickets: set[int] = set()

    for sym, sig_id, sig in sigs_without_ticket:
        hist_orders = _mt5_exec.history_orders_get(dt_from, dt_to, group=sym)
        if not hist_orders:
            continue

        # 1. Match exact pe comment (ideal — nu e trunchiat sau e acelasi ID)
        exact_matching = [o for o in hist_orders if o.comment == sig_id]
        if exact_matching:
            matching = [o for o in exact_matching if o.ticket not in claimed_tickets]
        else:
            # 2. Fallback prefix 16 chars (ICMarketsEU trunchiaza la 16 caractere)
            prefix_matching = [
                o for o in hist_orders
                if o.comment.rstrip() == sig_id[:16] and o.ticket not in claimed_tickets
            ]
            if len(prefix_matching) <= 1:
                matching = prefix_matching
            else:
                # Mai multe ordine cu acelasi prefix — disambiguare prin pret de intrare
                _entry = sig.get("entry")
                if _entry is not None:
                    try:
                        from strategy.signals import pip_size as _psz
                        _pip = _psz(sym)
                    except Exception:
                        _pip = 0.0001
                    price_matched = [
                        o for o in prefix_matching
                        if abs(o.price_open - _entry) < 5 * _pip
                    ]
                    if len(price_matched) == 1:
                        matching = price_matched
                        log.info(
                            f"  [RECOVER] {sig_id}: {len(prefix_matching)} ordine cu prefix "
                            f"'{sig_id[:16]}' — selectat #{price_matched[0].ticket} "
                            f"prin pret (|{price_matched[0].price_open:.5f}-{_entry:.5f}|<5pip)"
                        )
                    else:
                        matching = []
                        log.warning(
                            f"  [RECOVER] {sig_id}: {len(prefix_matching)} ordine cu prefix "
                            f"'{sig_id[:16]}' si {len(price_matched)} match-uri prin pret "
                            f"— skip, va fi recuperat de scan_mt5_history la urmatorul restart"
                        )
                else:
                    matching = []

        if not matching:
            continue

        # Cel mai recent ordin plasat cu comentariul potrivit
        order = sorted(matching, key=lambda o: o.time_setup)[-1]
        claimed_tickets.add(order.ticket)
        ticket = order.ticket
        pos_id = getattr(order, "position_id", ticket) or ticket

        # 1. Ordin inca pending (netriggerat)
        if _mt5_exec.orders_get(ticket=ticket):
            mt5_tickets[sig_id] = ticket
            log.info(f"  [RECOVER] {sig_id}: ordin #{ticket} inca pending → actualizat mt5_tickets")
            continue

        # 2. Pozitie inca deschisa (triggerat, in curs)
        if _mt5_exec.positions_get(ticket=pos_id):
            mt5_tickets[sig_id] = ticket
            sig["triggered"] = True
            if order.time_done:
                sig["triggered_at"] = datetime.fromtimestamp(order.time_done).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            log.info(f"  [RECOVER] {sig_id}: pozitie #{pos_id} deschisa → actualizat mt5_tickets+triggered")
            continue

        # 3. Pozitie inchisa — folosim _check_mt5_position_closed cu ticketul gasit
        mt5_res = _check_mt5_position_closed(ticket, sig, log)
        if mt5_res is None or mt5_res.get("__no_outcome__"):
            # Order anulat/respins fara executie — lasa sa expire natural
            continue

        # Verifica ca nu e deja in outcomes.csv
        if os.path.exists(outcomes_file):
            try:
                _ex = pd.read_csv(outcomes_file, usecols=["signal_id"])
                if sig_id in _ex["signal_id"].values:
                    pending.get(sym, {}).pop(sig_id, None)
                    continue
            except Exception:
                pass

        # Scrie outcome real in loc de "expirat"
        row = {
            **sig, "signal_id": sig_id, "symbol": sym,
            **mt5_res, "time_check": now_local(),
        }
        pd.DataFrame([row]).reindex(columns=_OUTCOMES_COLS).to_csv(
            outcomes_file, mode="a", header=False, index=False
        )

        pending.get(sym, {}).pop(sig_id, None)
        mt5_tickets.pop(sig_id, None)
        recovered += 1

        log.warning(
            f"  [RECOVER] {sig_id}: {mt5_res['status']} {mt5_res['result_r']:+.3f}R "
            f"{mt5_res.get('pnl_usd', 0):+.2f}USD recuperat din history MT5 "
            f"(pozitie inchisa in lipsa botului)"
        )
        _send_telegram(
            f"<b>[RECOVER] {sig_id}</b>\n"
            f"Pozitie recuperata din history MT5\n"
            f"Status: {mt5_res['status']} | {mt5_res['result_r']:+.3f}R | "
            f"{mt5_res.get('pnl_usd', 0):+.2f} USD\n"
            f"<i>{session_cfg.get('session_id', '?')} — pozitie inchisa in lipsa botului</i>"
        )

    if recovered > 0:
        log.warning(
            f"  [RECOVER] {recovered} outcome(uri) recuperate din history MT5 la startup"
        )


def _scan_mt5_history_for_missing_outcomes(
    state: dict,
    session_cfg: dict,
    outcomes_file: str,
    log,
) -> None:
    """
    Startup: scanare completa history MT5 (10 zile) pentru simbolurile sesiunii.
    Complementara cu _recover_lost_outcomes (care lucreaza doar cu semnale in pending).

    Acopera cazul stat complet gol (crash total, state.pkl sters manual):
    gaseste ORICE ordin/pozitie cu comment in formatul botului, a carui pozitie e
    INCHISA si NU apare inca in outcomes.csv → scrie outcome real + trimite [RECOVER].

    Deduplicare:
    - Verifica sig_id exact in existing_sig_ids
    - Verifica prefix (pentru comentarii trunchiate vs. sig_id full din _recover_lost_outcomes)
    - Skip daca ordinul e inca activ (tracked in mt5_tickets sau pending)
    """
    if _mt5_exec is None:
        return
    # Sesiunile de observatie (execute_trades=False) nu plaseaza ordine in MT5 — skip
    if not session_cfg.get("execute_trades", True):
        return

    markets    = session_cfg.get("markets", [])
    session_id = session_cfg.get("session_id", "?")
    if not markets:
        return

    # Citeste sig_id-urile existente (inclusiv cele scrise de _recover_lost_outcomes)
    existing_sig_ids: set[str] = set()
    # Deduplicare pe identitate pozitie: (symbol, pnl_rotunjit, exit_time[:19])
    # Previne scrieri duble cand mai multe ordine au acelasi comment trunchiat (ICMarketsEU 16 chars)
    existing_pos_keys: set[tuple] = set()
    if os.path.exists(outcomes_file):
        try:
            _df = pd.read_csv(outcomes_file)
            existing_sig_ids = set(_df["signal_id"].dropna().astype(str).tolist())
            for _, _r in _df.iterrows():
                try:
                    _pnl = _r.get("pnl_usd", "")
                    if _pnl != "" and str(_pnl) not in ("nan", ""):
                        # Includ si entry_price in cheie ca sa prind duplicate cu exit_time
                        # usor diferit (ex: vineri_close inregistrat de bot vs deal MT5)
                        _entry_r = _r.get("entry", "")
                        _entry_k = round(float(_entry_r), 5) if str(_entry_r) not in ("", "nan") else 0.0
                        existing_pos_keys.add((
                            str(_r.get("symbol", "")),
                            round(float(_pnl), 2),
                            str(_r.get("exit_time", ""))[:19],
                        ))
                        # Cheie alternativa fara exit_time, cu entry — prinde acelasi trade
                        # chiar daca exit_time difera intre bot record si MT5 deal record
                        existing_pos_keys.add((
                            str(_r.get("symbol", "")),
                            round(float(_pnl), 2),
                            _entry_k,
                        ))
                except Exception:
                    pass
        except Exception:
            pass

    seen_tickets: set[int] = set()  # dedup ordine in cadrul acestei rulari (unicitate per ticket MT5)

    # Ticketele deja trackuite (nu le procesam din nou)
    tracked_tickets: set[int] = set(state.get("mt5_tickets", {}).values())

    dt_from  = datetime.now() - timedelta(days=10)
    dt_to    = datetime.now()
    recovered = 0

    for symbol in markets:
        hist_orders = _mt5_exec.history_orders_get(dt_from, dt_to, group=symbol) or []

        for order in hist_orders:
            # Skip ordine neexecutate (anulate, respinse, expirate)
            if order.state in (2, 5, 6):
                continue

            comment = (getattr(order, "comment", "") or "").strip()
            if not _BOT_SIG_RE.match(comment):
                continue

            is_full = bool(_BOT_SIG_FULL_RE.match(comment))
            # sig_id provizoriu pentru verificarea tracked_tickets/existing_sig_ids;
            # poate fi corectat mai jos dupa obtinerea entry_price (matching in pending)
            sig_id  = comment if is_full else f"{comment}_{order.ticket}"

            # Skip daca ticketul e deja in tracking activ
            if order.ticket in tracked_tickets:
                continue

            # Skip daca sig_id deja in outcomes (verificare rapida pentru IDs complete)
            if is_full and sig_id in existing_sig_ids:
                continue

            # Obtine deals-urile pozitiei (necesar pentru pnl + exit_time → deduplicare)
            pos_id = getattr(order, "position_id", 0) or order.ticket
            deals  = _mt5_exec.history_deals_get(position=pos_id)
            if not deals:
                continue

            # DEAL_ENTRY_IN=0 (deschidere), DEAL_ENTRY_OUT=1 (inchidere)
            entry_deal = next((d for d in deals if d.entry == 0), None)
            close_deal = next((d for d in deals if d.entry == 1), None)

            if not close_deal:
                # Pozitie inca deschisa → orphan detection se ocupa
                continue

            entry_price    = float(entry_deal.price if entry_deal else order.price_open)
            exit_price     = float(close_deal.price)
            exit_time      = datetime.fromtimestamp(close_deal.time).strftime("%Y-%m-%d %H:%M:%S")
            pnl_usd        = round(float(close_deal.profit), 4)
            commission_usd = round(
                float(getattr(entry_deal, "commission", 0) or 0) +
                float(getattr(close_deal, "commission", 0) or 0),
                4,
            )
            swap_usd = round(float(getattr(close_deal, "swap", 0) or 0), 4)
            d_int    = 1 if order.type in (0, 2, 4) else -1
            sl_price = float(getattr(order, "sl", 0) or 0)
            tp_price = float(getattr(order, "tp", 0) or 0)

            # Pentru comentarii trunchiate (ICMarketsEU 16 chars): cauta semnalul real
            # Prioritate: 1. comment_map (stocat la plasare — sigur), 2. pending by price,
            # 3. signals.csv by price (fallback dupa crash cu state gol)
            if not is_full:
                _matched_sig = None
                # 1. comment_map — cea mai fiabila metoda, DAR numai daca sig_id-ul rezolvat
                # nu are deja un ticket activ in mt5_tickets. Daca are, inseamna ca ordinul
                # scanat din history este un alt ordin (acelasi prefix 16-char, alta tranzactie)
                # si nu trebuie asociat semnalului curent pending.
                _cm_match = state.get("comment_map", {}).get(comment)
                if _cm_match and _cm_match not in existing_sig_ids:
                    if _cm_match not in state.get("mt5_tickets", {}):
                        _matched_sig = _cm_match
                        log.info(
                            f"  [SCAN-RECOVER] Comentariu trunchiat '{comment}' → {_matched_sig} "
                            f"(via comment_map)"
                        )
                    else:
                        log.info(
                            f"  [SCAN-RECOVER] Comentariu trunchiat '{comment}' → comment_map "
                            f"arata spre {_cm_match} care are ticket activ — ordin vechi ignorat, "
                            f"se foloseste ID ticket-based"
                        )
                # 2. Pending by price
                if not _matched_sig:
                    _mt5_tickets = state.get("mt5_tickets", {})
                    try:
                        from strategy.signals import pip_size as _psz
                        _pip = _psz(symbol)
                    except Exception:
                        _pip = 0.0001
                    for _s_id, _s_sig in state.get("pending", {}).get(symbol, {}).items():
                        if _s_id in _mt5_tickets:
                            continue  # semnal activ — nu il revendicam
                        if (_s_sig.get("direction") == d_int and
                                abs(_s_sig.get("entry", 0) - entry_price) < 5 * _pip):
                            _matched_sig = _s_id
                            break
                # 3. Fallback signals.csv daca pending gol (crash cu state resetat)
                if not _matched_sig:
                    _signals_file = outcomes_file.replace("outcomes.csv", "signals.csv")
                    if os.path.exists(_signals_file):
                        try:
                            _sig_df = pd.read_csv(_signals_file)
                            _sig_sym = _sig_df[_sig_df["symbol"] == symbol] if not _sig_df.empty else pd.DataFrame()
                            for _, _srow in _sig_sym.iterrows():
                                _s_id = str(_srow.get("signal_id", ""))
                                if _s_id in existing_sig_ids:
                                    continue
                                if (int(_srow.get("direction", 0)) == d_int and
                                        abs(float(_srow.get("entry", 0)) - entry_price) < 5 * _pip):
                                    _matched_sig = _s_id
                                    break
                        except Exception:
                            pass
                if _matched_sig:
                    sig_id = _matched_sig
                    if not state.get("comment_map", {}).get(comment):
                        log.info(
                            f"  [SCAN-RECOVER] Comentariu trunchiat '{comment}' → {sig_id} "
                            f"(match prin pret {entry_price:.5f})"
                        )
                # else: pastram {comment}_{order.ticket} ca fallback unic

            # Dupa corectia sig_id: re-verifica ca nu e deja in outcomes
            if sig_id in existing_sig_ids:
                continue

            # Dedup in cadrul acestei rulari pe ticket unic (previne rescrierea aceluiasi ordin)
            if order.ticket in seen_tickets:
                continue
            # Dedup vs outcomes existente (pnl+exit_time sau pnl+entry — protectie dupa restart)
            pos_key = (symbol, round(pnl_usd, 2), exit_time[:19])
            pos_key_alt = (symbol, round(pnl_usd, 2), round(entry_price, 5))
            if pos_key in existing_pos_keys or pos_key_alt in existing_pos_keys:
                continue

            if sl_price and abs(entry_price - sl_price) > 1e-8:
                risk_dist = abs(entry_price - sl_price)
                result_r  = round((exit_price - entry_price) * d_int / risk_dist, 3)
                r_ratio   = round(abs(tp_price - entry_price) / risk_dist, 3) if (
                    tp_price and abs(tp_price - entry_price) > 1e-8
                ) else 0.0
            else:
                result_r = 0.0
                r_ratio  = 0.0

            status       = "TP" if result_r > 0 else "SL"
            t_done       = getattr(order, "time_done", 0) or 0
            triggered_at = datetime.fromtimestamp(
                t_done if t_done else order.time_setup
            ).strftime("%Y-%m-%d %H:%M:%S")

            row = {
                "signal_id":      sig_id,
                "time_check":     now_local(),
                "symbol":         symbol,
                "direction":      d_int,
                "status":         status,
                "entry":          entry_price,
                "sl":             sl_price,
                "tp":             tp_price,
                "r_ratio":        r_ratio,
                "triggered_at":   triggered_at,
                "exit_price":     exit_price,
                "exit_time":      exit_time,
                "result_r":       result_r,
                "pnl_usd":        pnl_usd,
                "commission_usd": commission_usd,
                "swap_usd":       swap_usd,
            }
            pd.DataFrame([row]).reindex(columns=_OUTCOMES_COLS).to_csv(
                outcomes_file, mode="a", header=False, index=False
            )
            existing_sig_ids.add(sig_id)
            existing_pos_keys.add(pos_key)
            seen_tickets.add(order.ticket)
            tracked_tickets.add(order.ticket)
            recovered += 1

            log.warning(
                f"  [SCAN-RECOVER] {sig_id}: {status} {result_r:+.3f}R "
                f"{pnl_usd:+.2f}USD recuperat din scanare history MT5"
            )
            _send_telegram(
                f"<b>[RECOVER] {sig_id}</b>\n"
                f"Pozitie recuperata din scanare history MT5 (bot offline)\n"
                f"Status: {status} | {result_r:+.3f}R | {pnl_usd:+.2f} USD\n"
                f"<i>{session_id}</i>"
            )

    if recovered:
        log.warning(
            f"  [SCAN-RECOVER] {recovered} outcome(uri) recuperate din scanare history MT5"
        )


# ICMarketsEU trunchiaza comentariile MT5 la 16 caractere.
# Ex: "S17-AUDCAD-H1-IB0001" (20 chars) → "S17-AUDCAD-H1-IB" (fara cifre finale).
# \d* in loc de \d+ pentru a prinde si comentariile trunchiate.
_BOT_SIG_RE = re.compile(r"^S\d+-[A-Z0-9]+-(?:[A-Z0-9]+-)?(?:SIG|IB|FLG)\d*", re.IGNORECASE)
# FULL = exact 4+ cifre la final (format :04d). Comentariile trunchiate (SIG00, IB000 etc.)
# au mai putine cifre si sunt tratate ca partial → primesc sufixul _{ticket} pentru unicitate.
_BOT_SIG_FULL_RE = re.compile(r"^S\d+-[A-Z0-9]+-(?:[A-Z0-9]+-)?(?:SIG|IB|FLG)\d{4,}$", re.IGNORECASE)


def _detect_orphan_mt5_orders(
    state: dict, markets: list, session_id: str, log,
    signals_file: str = "",
) -> None:
    """
    Detecteaza ordinele MT5 deschise (pending/pozitii) pentru simbolurile sesiunii
    care NU sunt in state["mt5_tickets"].

    - Daca comment-ul e in formatul botului (SigID): preia automat in state si trimite
      Telegram "[RECOVER] Pozitie preluata pentru monitorizare".
    - Altfel (ordine manuale): alerteaza userul sa verifice si inchida manual daca e cazul.

    Ruleaza o singura data la pornire, dupa _reconcile_mt5_tickets + _recover_lost_outcomes.
    """
    if _mt5_exec is None:
        return
    tracked_tickets = set(state.get("mt5_tickets", {}).values())

    # Cache signals.csv pentru fuzzy-match fallback (cand state["pending"] e gol dupa crash)
    _sig_cache: dict[str, list[tuple[str, int, float]]] = {}  # symbol -> [(sig_id, dir, entry)]
    if signals_file and os.path.exists(signals_file):
        try:
            _sig_df = pd.read_csv(signals_file)
            for _, _srow in _sig_df.iterrows():
                _sym = str(_srow.get("symbol", ""))
                _sig_cache.setdefault(_sym, []).append((
                    str(_srow.get("signal_id", "")),
                    int(_srow.get("direction", 0)),
                    float(_srow.get("entry", 0)),
                ))
        except Exception:
            pass
    unknown_orphans: list[tuple] = []
    recovered = 0

    for symbol in markets:
        # ── Ordine pending neactivate ──
        for order in (_mt5_exec.orders_get(symbol=symbol) or []):
            if order.ticket in tracked_tickets:
                continue
            comment = getattr(order, "comment", "") or ""
            if _BOT_SIG_RE.match(comment.strip()):
                c = comment.strip()
                if _BOT_SIG_FULL_RE.match(c):
                    sig_id = c
                else:
                    # Comentariu trunchiat — rezolva sig_id in ordinea prioritatii:
                    # 1. comment_map (stocat la plasare), 2. pending by price, 3. signals.csv
                    _matched = state.get("comment_map", {}).get(c)
                    if _matched:
                        log.info(
                            f"  [ORPHAN-RECOVER] Ordin #{order.ticket} comment '{c}' "
                            f"→ {_matched} (via comment_map)"
                        )
                    if not _matched:
                        try:
                            from strategy.signals import pip_size as _psz
                            _pip = _psz(symbol)
                        except Exception:
                            _pip = 0.0001
                        d_ord = 1 if order.type in (2, 4) else -1  # BUY_STOP=2, BUY_LIMIT=4
                        for _s_id, _s_sig in state.get("pending", {}).get(symbol, {}).items():
                            if (_s_sig.get("direction") == d_ord and
                                    abs(_s_sig.get("entry", 0) - order.price_open) < 5 * _pip):
                                _matched = _s_id
                                break
                    # Fallback: cauta in signals.csv daca pending e gol (state resetat la crash)
                    if not _matched:
                        _existing_tickets = set(state.get("mt5_tickets", {}).values())
                        for _s_id, _s_dir, _s_entry in _sig_cache.get(symbol, []):
                            if _s_id in state.get("mt5_tickets", {}):
                                continue
                            if (_s_dir == d_ord and
                                    abs(_s_entry - order.price_open) < 5 * _pip):
                                _matched = _s_id
                                break
                    sig_id = _matched if _matched else f"{c}_{order.ticket}"
                    if _matched:
                        log.info(
                            f"  [ORPHAN-RECOVER] Ordin #{order.ticket} comment trunchiat '{c}' "
                            f"→ {sig_id} (match prin pret {order.price_open:.5f})"
                        )
                state.setdefault("mt5_tickets", {})[sig_id] = order.ticket
                tracked_tickets.add(order.ticket)
                log.warning(
                    f"  [ORPHAN-RECOVER] Ordin pending #{order.ticket} ({sig_id}) "
                    f"preluat din MT5 — adaugat in tracking"
                )
                _send_telegram(
                    f"<b>[RECOVER] {sig_id}</b>\n"
                    f"Ordin pending #{order.ticket} preluat automat pentru monitorizare\n"
                    f"{symbol} @ {order.price_open:.5f}\n"
                    f"<i>{session_id} — state recuperat la startup</i>"
                )
                recovered += 1
            else:
                unknown_orphans.append((symbol, order.ticket, "pending", order.price_open, comment))

        # ── Pozitii deschise (triggerate) ──
        for pos in (_mt5_exec.positions_get(symbol=symbol) or []):
            if pos.ticket in tracked_tickets:
                continue
            comment = getattr(pos, "comment", "") or ""
            if _BOT_SIG_RE.match(comment.strip()):
                # Reconstruieste intrarea in pending din datele pozitiei MT5
                c = comment.strip()
                d = 1 if pos.type == 0 else -1  # 0=buy, 1=sell
                if _BOT_SIG_FULL_RE.match(c):
                    sig_id = c
                else:
                    # Comentariu trunchiat — rezolva sig_id: comment_map → pending → signals.csv
                    _matched = state.get("comment_map", {}).get(c)
                    if _matched:
                        log.info(
                            f"  [ORPHAN-RECOVER] Pozitie #{pos.ticket} comment '{c}' "
                            f"→ {_matched} (via comment_map)"
                        )
                    if not _matched:
                        try:
                            from strategy.signals import pip_size as _psz
                            _pip = _psz(symbol)
                        except Exception:
                            _pip = 0.0001
                        for _s_id, _s_sig in state.get("pending", {}).get(symbol, {}).items():
                            if (_s_sig.get("direction") == d and
                                    abs(_s_sig.get("entry", 0) - pos.price_open) < 10 * _pip):
                                _matched = _s_id
                                break
                    # Fallback: cauta in signals.csv daca pending e gol (state resetat la crash)
                    if not _matched:
                        for _s_id, _s_dir, _s_entry in _sig_cache.get(symbol, []):
                            if _s_id in state.get("mt5_tickets", {}):
                                continue
                            if (_s_dir == d and
                                    abs(_s_entry - pos.price_open) < 10 * _pip):
                                _matched = _s_id
                                break
                    sig_id = _matched if _matched else f"{c}_{pos.ticket}"
                    if _matched and not state.get("comment_map", {}).get(c):
                        log.info(
                            f"  [ORPHAN-RECOVER] Pozitie #{pos.ticket} comment trunchiat '{c}' "
                            f"→ {sig_id} (match prin pret {pos.price_open:.5f})"
                        )
                t_open = datetime.fromtimestamp(pos.time).strftime("%Y-%m-%d %H:%M:%S")
                # Actualizeaza semnalul existent in pending daca exista; altfel creaza unul nou
                existing_sig = state.get("pending", {}).get(symbol, {}).get(sig_id)
                if existing_sig is not None:
                    existing_sig["triggered"]    = True
                    existing_sig["triggered_at"] = t_open
                else:
                    reconstructed = {
                        "direction":     d,
                        "entry":         pos.price_open,
                        "sl":            pos.sl if pos.sl else pos.price_open * (1 - 0.005 * d),
                        "tp":            pos.tp if pos.tp else pos.price_open * (1 + 0.01 * d),
                        "r_ratio":       0.0,
                        "armed_at":      t_open,
                        "triggered":     True,
                        "triggered_at":  t_open,
                        "be_phase":      0,
                        "be_current_sl": pos.sl or 0,
                        "symbol":        symbol,
                        "risk_usd":      None,
                    }
                    state.setdefault("pending", {}).setdefault(symbol, {})[sig_id] = reconstructed
                state.setdefault("mt5_tickets", {})[sig_id] = pos.ticket
                tracked_tickets.add(pos.ticket)
                dir_str = "LONG" if d == 1 else "SHORT"
                log.warning(
                    f"  [ORPHAN-RECOVER] Pozitie #{pos.ticket} ({sig_id}) {dir_str} {symbol} "
                    f"@ {pos.price_open:.5f} preluata din MT5 — reconstruita in pending+tracking"
                )
                _send_telegram(
                    f"<b>[RECOVER] {sig_id}</b>\n"
                    f"Pozitie activa #{pos.ticket} preluata automat\n"
                    f"{dir_str} {symbol} @ {pos.price_open:.5f} | "
                    f"SL {pos.sl:.5f} | TP {pos.tp:.5f}\n"
                    f"<i>{session_id} — botul monitorizeaza acum aceasta pozitie</i>"
                )
                recovered += 1
            else:
                unknown_orphans.append((symbol, pos.ticket, "pozitie", pos.price_open, comment))

    if recovered:
        log.warning(f"  [ORPHAN-RECOVER] {recovered} ordine/pozitii preluate automat din MT5 la startup")

    if unknown_orphans:
        lines = "\n".join(
            f"  #{tkt} {sym} {kind} @ {price:.5f}"
            + (f" [{cmt}]" if cmt else "")
            for sym, tkt, kind, price, cmt in unknown_orphans
        )
        msg = (
            f"⚠️ <b>[{session_id}] Pozitii MT5 fara corespondent in bot</b>\n"
            f"Urmatoarele pozitii din MT5 nu pot fi identificate automat\n"
            f"(probabil deschise manual sau de alta sesiune):\n<pre>{lines}</pre>\n"
            f"Verifica in MT5 si inchide manual daca nu sunt ale botului."
        )
        log.warning(f"  [ORPHAN] {len(unknown_orphans)} pozitii MT5 neidentiabile: {unknown_orphans}")
        _send_telegram(msg)
    elif not recovered:
        log.info("  [ORPHAN] Nicio pozitie MT5 fara corespondent — state consistent cu MT5.")


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

    now = now_local()
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
                        "pnl_usd":      0.0,
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

                result = _close_position_robust(
                    symbol, pos.volume, close_type, ticket,
                    close_price, "vineri_close", log
                )
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
                        "pnl_usd":      _pnl(result_r, p.get("risk_usd")),
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
        seen_in_batch: set = set()
        new_rows = []
        for r in outcome_rows:
            sid = r.get("signal_id")
            if sid not in existing_ids and sid not in seen_in_batch:
                new_rows.append(r)
                seen_in_batch.add(sid)
        if new_rows:
            pd.DataFrame(new_rows).reindex(columns=_OUTCOMES_COLS).to_csv(
                outcomes_file, mode="a", header=False, index=False)

    for symbol, sig_id in sigs_to_remove:
        state["pending"].get(symbol, {}).pop(sig_id, None)


def _smart_news_place_order(
    symbol: str,
    direction: int,
    news_events: list,
    state: dict,
    session_cfg: dict,
    log,
) -> None:
    """
    Mod Inteligent: plaseaza un ordin STOP in directia stirii.
    direction: +1 = LONG (BUY_STOP), -1 = SHORT (SELL_STOP)
    Risk: 1.5 × risk_base din session_cfg.
    """
    if _mt5_exec is None:
        return
    if direction == 0:
        return

    tick = _mt5_exec.symbol_info_tick(symbol)
    info = _mt5_exec.symbol_info(symbol)
    if tick is None or info is None:
        return

    # Entry: la piata (usor dincolo de BID/ASK pentru STOP imediat)
    spread_pts = info.spread * info.point if info.point > 0 else 0
    if direction == 1:
        entry = round(tick.ask + info.point, info.digits)   # BUY_STOP deasupra ask
    else:
        entry = round(tick.bid - info.point, info.digits)   # SELL_STOP sub bid

    # SL: standard pip × atr sau fallback la 30 × point
    from strategy.signals import pip_size as _pip_size
    pip = _pip_size(symbol)
    sl_pips = 30.0  # fallback
    sl = entry - direction * sl_pips * pip

    # TP: r_max × SL distance
    r_max = session_cfg.get("r_max", session_cfg.get("risk_pct", 0.01) and 4.5)
    if not isinstance(r_max, (int, float)):
        r_max = 4.5
    tp = entry + direction * sl_pips * pip * r_max

    # Sizing cu risc 1.5 × risk_base
    frac      = session_cfg.get("account_fraction")
    risk_base = session_cfg.get("risk_base", session_cfg.get("risk_pct", 0.01))
    risk_pct  = risk_base * 1.5
    capital   = 1000.0
    if frac and _mt5_exec is not None:
        _ai = _mt5_exec.account_info()
        if _ai:
            capital = float(_ai.equity) * float(frac)
    lots, risk_usd = _calc_lots(symbol, entry, sl, capital, risk_pct)

    sn_id = f"SN{state.get('sn_counter', 0) + 1}"
    state["sn_counter"] = state.get("sn_counter", 0) + 1

    order_type = (_mt5_exec.ORDER_TYPE_BUY_STOP if direction == 1
                  else _mt5_exec.ORDER_TYPE_SELL_STOP)
    request = {
        "action":       _mt5_exec.TRADE_ACTION_PENDING,
        "symbol":       symbol,
        "volume":       lots,
        "type":         order_type,
        "price":        entry,
        "sl":           round(sl, info.digits),
        "tp":           round(tp, info.digits),
        "type_time":    _mt5_exec.ORDER_TIME_GTC,
        "type_filling": _mt5_exec.ORDER_FILLING_RETURN,
        "comment":      sn_id[:31],
    }
    result = _mt5_exec.order_send(request)
    if result and result.retcode == _mt5_exec.TRADE_RETCODE_DONE:
        dir_str = "LONG" if direction == 1 else "SHORT"
        top = news_events[0] if news_events else {}
        log.info(f"  [SN] {sn_id} {symbol} {dir_str} @ {entry:.5f} SL={sl:.5f} TP={tp:.5f} #{result.order}")
        state.setdefault("smart_news_tickets", {})[sn_id] = {
            "ticket":    result.order,
            "symbol":    symbol,
            "direction": direction,
            "entry":     entry,
            "sl":        round(sl, info.digits),
            "tp":        round(tp, info.digits),
            "risk_usd":  risk_usd,
            "phase":     0,  # 0=watching, 1=3R SL moved, 2=4R SL moved
        }
        _send_telegram(
            f"📰 <b>Ordin Stire [{dir_str}] {symbol}</b>\n"
            f"Eveniment: <b>{top.get('title','?')}</b> ({top.get('currency','?')})\n"
            f"Actual: {top.get('actual','?')} vs Forecast: {top.get('forecast','?')}\n"
            f"Entry: {entry:.5f} | SL: {sl:.5f} | TP: {tp:.5f} ({r_max:.1f}R)\n"
            f"Risk: {risk_pct*100:.2f}% — {risk_usd:.2f} USD\n"
            f"<i>{session_cfg.get('session_id', '')}</i>"
        )
    else:
        rc = result.retcode if result else "None"
        log.warning(f"  [SN] {sn_id} {symbol} ordin esuat retcode={rc}")


def _smart_news_trailing_check(
    state: dict,
    session_id: str = "",
    log=None,
) -> None:
    """
    Verifica pozitiile din smart news si ajusteaza SL la 3R (→ 1R fata de TP)
    si la 4R (→ 2R fata de TP). Apelat la fiecare iteratie principala.
    """
    if _mt5_exec is None:
        return
    sn_tickets = state.get("smart_news_tickets", {})
    if not sn_tickets:
        return

    done_keys = []
    for sn_id, sn in list(sn_tickets.items()):
        ticket    = sn.get("ticket")
        symbol    = sn.get("symbol", "")
        direction = sn.get("direction", 0)
        entry     = sn.get("entry", 0.0)
        sl        = sn.get("sl", 0.0)
        tp        = sn.get("tp", 0.0)
        phase     = sn.get("phase", 0)
        risk_usd  = sn.get("risk_usd")

        if not ticket or not symbol or direction == 0:
            done_keys.append(sn_id)
            continue

        positions = _mt5_exec.positions_get(ticket=ticket)
        if not positions:
            # Pozitia nu mai exista — inchisa de TP/SL, remove
            if log:
                log.info(f"  [SN] {sn_id} {symbol} inchis (TP/SL sau manual)")
            done_keys.append(sn_id)
            continue

        pos  = positions[0]
        risk = abs(entry - sl)
        if risk <= 0:
            continue

        current_price = pos.price_current
        profit_r = (current_price - entry) * direction / risk

        if profit_r >= 4.0 and phase < 2:
            # Faza 2: SL la 2R fata de TP
            new_sl = tp - direction * risk * 2.0
            info = _mt5_exec.symbol_info(symbol)
            new_sl_r = round(new_sl, info.digits if info else 5)
            res = _mt5_exec.order_send({
                "action":   _mt5_exec.TRADE_ACTION_SLTP,
                "symbol":   symbol,
                "position": ticket,
                "sl":       new_sl_r,
                "tp":       tp,
            })
            if res and res.retcode == _mt5_exec.TRADE_RETCODE_DONE:
                sn["sl"]    = new_sl_r
                sn["phase"] = 2
                if log:
                    log.info(f"  [SN] {sn_id} {symbol} SL→{new_sl_r:.5f} (4R, faza2)")
                _send_telegram(
                    f"📊 <b>SL ajustat 4R — {symbol}</b>\n"
                    f"SL mutat la 2R fata de TP: {new_sl_r:.5f}\n"
                    f"<i>{session_id}</i>"
                )

        elif profit_r >= 3.0 and phase < 1:
            # Faza 1: SL la 1R fata de TP
            new_sl = tp - direction * risk * 1.0
            info = _mt5_exec.symbol_info(symbol)
            new_sl_r = round(new_sl, info.digits if info else 5)
            res = _mt5_exec.order_send({
                "action":   _mt5_exec.TRADE_ACTION_SLTP,
                "symbol":   symbol,
                "position": ticket,
                "sl":       new_sl_r,
                "tp":       tp,
            })
            if res and res.retcode == _mt5_exec.TRADE_RETCODE_DONE:
                sn["sl"]    = new_sl_r
                sn["phase"] = 1
                if log:
                    log.info(f"  [SN] {sn_id} {symbol} SL→{new_sl_r:.5f} (3R, faza1)")
                _send_telegram(
                    f"📊 <b>SL ajustat 3R — {symbol}</b>\n"
                    f"SL mutat la 1R fata de TP: {new_sl_r:.5f}\n"
                    f"<i>{session_id}</i>"
                )

    for k in done_keys:
        sn_tickets.pop(k, None)


def _news_close_check(
    state: dict,
    outcomes_file: str,
    log,
    session_id: str = "",
    execute_trades: bool = False,
    smart_news_enabled: bool = False,
    news_events: list | None = None,
    session_cfg: dict | None = None,
) -> None:
    """
    La prima iteratie de pauza de stiri (tranzitia False → True):
    - anuleaza ordinele pending neactivate (TRADE_ACTION_REMOVE)
    - inchide la piata pozitiile triggerate deschise (TRADE_ACTION_DEAL)
    Daca smart_news_enabled=True: inchide doar pozitiile contra sentimentului stirii.
    Apelat o singura data per tranzitie, din bucla principala.
    """
    total = sum(len(v) for v in state["pending"].values())
    if total == 0:
        log.info("  [STIRI] Nicio pozitie/ordin activ — nimic de inchis.")
        # Smart news: daca nu avem pozitii, incearca ordin in directia stirii
        if smart_news_enabled and execute_trades and news_events and session_cfg:
            try:
                from live.news_guard import news_direction_for_symbol
                for market in session_cfg.get("markets", []):
                    nd = news_direction_for_symbol(market, news_events)
                    if nd != 0:
                        _smart_news_place_order(market, nd, news_events, state, session_cfg, log)
            except Exception as _e:
                log.warning(f"  [SN] Eroare ordin stire: {_e}")
        return

    outcome_rows   = []
    sigs_to_remove = []
    now = now_local()

    # Smart news: precalculeaza directia neta pentru fiecare simbol
    _sn_dir: dict[str, int] = {}
    if smart_news_enabled and news_events:
        try:
            from live.news_guard import news_direction_for_symbol
            for sym in list(state["pending"].keys()):
                _sn_dir[sym] = news_direction_for_symbol(sym, news_events)
        except Exception:
            pass

    for symbol, pending in list(state["pending"].items()):
        for sig_id, p in list(pending.items()):
            d         = p["direction"]
            fmt       = ".2f" if p["entry"] > 100 else ".5f"
            dir_str   = "LONG" if d == 1 else "SHORT"
            ticket    = state.get("mt5_tickets", {}).get(sig_id)
            triggered = p.get("triggered", False)

            # Smart news: daca pozitia e IN directia stirii, las-o deschisa
            if smart_news_enabled and triggered and _sn_dir.get(symbol, 0) == d:
                log.info(f"  [SN] {sig_id} {symbol} {dir_str} mentinuta — aliniata cu stirea")
                continue

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
                result = _close_position_robust(
                    symbol, pos.volume, close_type, ticket,
                    close_price, "news_close", log
                )
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
                        "pnl_usd":      _pnl(result_r, p.get("risk_usd")),
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
                    "pnl_usd":    0.0,
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
        seen_in_batch: set = set()
        new_rows = []
        for r in outcome_rows:
            sid = r.get("signal_id")
            if sid not in existing_ids and sid not in seen_in_batch:
                new_rows.append(r)
                seen_in_batch.add(sid)
        if new_rows:
            pd.DataFrame(new_rows).reindex(columns=_OUTCOMES_COLS).to_csv(
                outcomes_file, mode="a", header=False, index=False)

    for symbol, sig_id in sigs_to_remove:
        state["pending"].get(symbol, {}).pop(sig_id, None)

    # Smart news: dupa ce am inchis/anulat, plaseaza ordine in directia stirii
    if smart_news_enabled and execute_trades and news_events and session_cfg:
        try:
            from live.news_guard import news_direction_for_symbol
            for market in session_cfg.get("markets", []):
                nd = news_direction_for_symbol(market, news_events)
                if nd != 0:
                    # Verifica daca mai avem pozitie deschisa in aceasta directie
                    existing = state["pending"].get(market, {})
                    has_open_in_dir = any(
                        p.get("triggered") and p.get("direction") == nd
                        for p in existing.values()
                    )
                    if not has_open_in_dir:
                        _smart_news_place_order(market, nd, news_events, state, session_cfg, log)
        except Exception as _e:
            log.warning(f"  [SN] Eroare ordin stire post-close: {_e}")


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
                  # Pozitii simultane per piata
                  "max_concurrent_per_market", "min_bars_between_trades",
                  "break_even_enabled", "be_phase2_enabled",
                  "be_trigger_pct", "be_lock1_pct",
                  "be_lock2_pct", "be_phase2_zone_pct",
                  # Flag pattern
                  "flag_enabled", "flag_r_ratio", "flag_risk_pct",
                  # Inside Bar pattern
                  "inside_bar_enabled", "inside_bar_r_ratio", "inside_bar_risk_pct",
                  # Piete (permite profil sa specifice piata per sesiune)
                  "markets"):
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
                       "news_pre_minutes", "news_post_minutes", "smart_news_enabled"):
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
        # Handler pentru notificari automate ERROR/WARNING → UI Notifications
        _nh = _NotificationHandler(session_cfg["session_id"])
        _nh.setLevel(logging.WARNING)
        _nh.setFormatter(fmt)
        log.addHandler(_nh)

    # Init CSV-uri
    if not os.path.exists(signals_file):
        pd.DataFrame(columns=[
            "signal_id", "time", "symbol", "direction", "dir_str",
            "entry", "sl", "tp", "r_ratio", "atr_pips", "n_optional", "rsi",
        ]).to_csv(signals_file, index=False)
    if not os.path.exists(outcomes_file):
        pd.DataFrame(columns=_OUTCOMES_COLS).to_csv(outcomes_file, index=False)
    else:
        # Auto-migrare: adauga coloane lipsa fara a pierde datele existente
        try:
            _hdr = pd.read_csv(outcomes_file, nrows=0)
            _missing_cols = [c for c in _OUTCOMES_COLS if c not in _hdr.columns]
            if _missing_cols:
                _full = pd.read_csv(outcomes_file, on_bad_lines="skip")
                _full.reindex(columns=_OUTCOMES_COLS).to_csv(outcomes_file, index=False)
                log.info(f"outcomes.csv migrat: adaugate coloane {_missing_cols}")
        except Exception as _me:
            log.warning(f"Migrare automata outcomes.csv esuata: {_me}")

    # Incarca stare (cu fallback la coruptie — ex: reboot in mijlocul scrierii)
    _empty_state = {"pending": {}, "signal_counter": 0, "flag_signal_counter": 0, "ib_signal_counter": 0, "last_checked": {}}
    try:
        state = pickle.load(open(state_file, "rb")) if os.path.exists(state_file) else _empty_state
    except Exception as _e:
        log.warning(f"state.pkl corupt ({_e}) — resetat la stare goala.")
        state = _empty_state
    state.setdefault("mt5_tickets", {})
    state.setdefault("comment_map", {})   # sig_id[:16] -> full_sig_id (ICMarketsEU 16-char truncation)
    state.setdefault("flag_signal_counter", 0)
    state.setdefault("ib_signal_counter", 0)
    state.setdefault("smart_news_tickets", {})
    state.setdefault("sn_counter", 0)

    # Sincronizeaza signal_counter cu ce e deja in signals.csv
    # (previne reutilizarea ID-urilor dupa restart cu state.pkl fresh)
    if os.path.exists(signals_file):
        try:
            import re as _re
            _existing = pd.read_csv(signals_file, usecols=["signal_id"])["signal_id"].dropna()
            _max_sig = max(
                (int(m.group(1)) for sid in _existing
                 if (m := _re.search(r"SIG(\d+)$", str(sid)))),
                default=0,
            )
            _max_flg = max(
                (int(m.group(1)) for sid in _existing
                 if (m := _re.search(r"FLG(\d+)$", str(sid)))),
                default=0,
            )
            _max_ib = max(
                (int(m.group(1)) for sid in _existing
                 if (m := _re.search(r"IB(\d+)$", str(sid)))),
                default=0,
            )
            if _max_sig > state["signal_counter"]:
                state["signal_counter"] = _max_sig
                log.info(f"  signal_counter sincronizat la {_max_sig} din signals.csv")
            if _max_flg > state["flag_signal_counter"]:
                state["flag_signal_counter"] = _max_flg
                log.info(f"  flag_signal_counter sincronizat la {_max_flg} din signals.csv")
            if _max_ib > state["ib_signal_counter"]:
                state["ib_signal_counter"] = _max_ib
                log.info(f"  ib_signal_counter sincronizat la {_max_ib} din signals.csv")
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
        _expected_mt5_login = acc.login   # stocat pentru detectia schimbarii de cont
    except Exception as e:
        log.error(f"MT5 nu e disponibil: {e}")
        # Curatam lock file-ul — altfel UI vede PID mort si afiseaza 0/20 sesiuni
        try:
            if os.path.exists(lock_file):
                os.remove(lock_file)
        except OSError:
            pass
        return

    # Migrare format vechi pending (flat sig_id->dict) la format nou (symbol->{sig_id->dict})
    _migrate_pending_format(state, session_cfg, log)

    # Reconciliere tickets la pornire — curata orfanele din state
    _reconcile_mt5_tickets(state, log)

    # Recupereaza outcome-uri pierdute la crash/reset: cauta in MT5 history dupa comment=sig_id
    # Previne marcarea gresita ca "expirat 0R" a pozitiilor inchise in lipsa botului
    _recover_lost_outcomes(state, session_cfg, outcomes_file, log)

    # Scanare completa history MT5 pentru pozitii inchise netrackuite (state complet gol).
    # Complementara cu _recover_lost_outcomes; acopera crash total / state.pkl sters manual.
    _scan_mt5_history_for_missing_outcomes(state, session_cfg, outcomes_file, log)

    # Detecteaza ordine MT5 netrackuite (coruptie state / crash) si alerteaza via Telegram
    _detect_orphan_mt5_orders(
        state, session_cfg.get("markets", []),
        session_cfg.get("session_id", "?"), log,
        signals_file=signals_file,
    )

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

    # Auto-inregistreaza pip_size din MT5 pentru simboluri non-forex neinregistrate in _INDEX_PIP.
    # Necesar cand se adauga o piata noua (ex: NAS100) care nu e in lista hardcodata.
    # Nu afecteaza simbolurile existente (deja in _INDEX_PIP) — loop-ul le sare.
    import strategy.signals as _sig_mod
    _FX_CODES = {"USD","EUR","GBP","JPY","AUD","CAD","CHF","NZD",
                 "SGD","HKD","NOK","SEK","DKK","TRY","ZAR","MXN"}
    for _mkt, _sym_mt5 in resolved.items():
        if _mkt in _sig_mod._INDEX_PIP:
            continue  # deja inregistrat corect
        if len(_mkt) == 6 and _mkt[:3] in _FX_CODES and _mkt[3:] in _FX_CODES:
            continue  # forex standard — fallback pip_size() e corect (0.0001 / 0.01 JPY)
        # Non-forex necunoscut (indice, crypto, marfa): citeste din MT5
        if _mt5_exec is not None:
            _sinfo = _mt5_exec.symbol_info(_sym_mt5)
            if _sinfo is not None and _sinfo.point > 0:
                # Indici (digits <= 2, ex: NAS100, DAX) → pip = 1.0 (conventional in engine)
                # Crypto/marfa cu zecimale → pip = point (ex: ETHUSD point=0.01)
                _pip_auto = 1.0 if _sinfo.digits <= 2 else _sinfo.point
                _sig_mod._INDEX_PIP[_mkt] = _pip_auto
                log.info(f"[PIP_AUTO] {_mkt}: pip_size={_pip_auto} inregistrat din MT5 "
                         f"(digits={_sinfo.digits}, point={_sinfo.point})")
            else:
                log.warning(f"[PIP_AUTO] {_mkt}: simbol necunoscut in MT5 — "
                            f"pip_size fallback forex (0.0001). Adauga manual in _INDEX_PIP.")
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
            f"<i>{now_local().strftime('%Y-%m-%d %H:%M:%S')}</i>"
        )

    try:
      while True:
        try:
            iteration += 1
            log.info(f"--- {session_cfg['session_id']} iter {iteration} "
                     f"@ {now_local().strftime('%H:%M:%S')} ---")

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
                    smart_news_enabled=session_cfg.get("smart_news_enabled", False),
                    news_events=news_events,
                    session_cfg=session_cfg,
                )
                with open(state_file, "wb") as f:
                    pickle.dump(state, f)
            _was_news_paused = news_paused

            # Smart news trailing SL check (la fiecare iteratie)
            if state.get("smart_news_tickets"):
                _smart_news_trailing_check(
                    state=state,
                    session_id=session_cfg.get("session_id", ""),
                    log=log,
                )

            # Recuperare runtime pentru semnalele pending fara ticket MT5
            _recover_lost_outcomes(state, session_cfg, outcomes_file, log)

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

                # Vineri dupa ora de inchidere — nu mai plasam semnale noi
                # (bot repornit dupa friday_close_hour; _friday_close_check le-ar anula oricum)
                if session_cfg.get("friday_close_enabled", True):
                    _now_fc = now_local()
                    if _now_fc.weekday() == 4 and _now_fc.hour >= session_cfg.get("friday_close_hour", 20):
                        continue

                sigs = _check_signals(df, symbol, cfg, state, session_cfg)
                for sig in sigs:
                    # Evita duplicate in signals.csv (ID identic — doua instante simultane)
                    _sig_exists = False
                    try:
                        _ex_df = pd.read_csv(signals_file, usecols=["signal_id", "direction", "entry", "symbol"])
                        _sig_exists = sig["signal_id"] in _ex_df["signal_id"].values
                        # Dedup dupa (symbol, direction, entry) — prinde re-detectia aceluiasi
                        # setup dupa restart cand se genereaza un ID nou dar acelasi trade
                        if not _sig_exists:
                            _recent = _ex_df[
                                (_ex_df["symbol"] == sig["symbol"]) &
                                (_ex_df["direction"] == sig["direction"]) &
                                ((_ex_df["entry"] - sig["entry"]).abs() < 1e-6)
                            ]
                            if not _recent.empty:
                                log.warning(
                                    f"  [DEDUP] {sig['signal_id']} {symbol}: entry identic cu "
                                    f"{_recent.iloc[-1]['signal_id']} deja in signals.csv — skipped"
                                )
                                _sig_exists = True
                    except Exception:
                        pass
                    # Dedup si in pending curent (acelasi symbol, direction, entry)
                    if not _sig_exists:
                        for _existing_sig in state["pending"].get(symbol, {}).values():
                            if (
                                _existing_sig.get("direction") == sig["direction"]
                                and abs(_existing_sig.get("entry", 0) - sig["entry"]) < 1e-6
                            ):
                                log.warning(
                                    f"  [DEDUP] {sig['signal_id']} {symbol}: entry identic cu "
                                    f"un semnal deja in pending — skipped"
                                )
                                _sig_exists = True
                                break
                    if _sig_exists:
                        continue
                    pd.DataFrame([sig]).reindex(columns=_SIGNALS_COLS).to_csv(
                        signals_file, mode="a", header=False, index=False)
                    state["pending"].setdefault(symbol, {})[sig["signal_id"]] = {
                        "direction":  sig["direction"],
                        "entry":      sig["entry"],
                        "sl":         sig["sl"],
                        "tp":         sig["tp"],
                        "r_ratio":    sig["r_ratio"],
                        "n_optional": sig.get("n_optional", 0),
                        "armed_at":   sig["time"],
                        "triggered":  False,
                        "signal_type": sig.get("signal_type", "pullback"),
                        "be_phase":           0,
                        "be_current_sl":      sig["sl"],
                        "be_in_zone":         False,
                        "be_notified_phases": set(),
                        "be_last_t":          None,
                    }
                    log.info(
                        f"  *** SEMNAL [{sig.get('signal_type', 'pullback').upper()}]: "
                        f"{sig['signal_id']} {symbol} {sig['dir_str']} "
                        f"entry={sig['entry']:.5f} sl={sig['sl']:.5f} tp={sig['tp']:.5f} "
                        f"({sig['r_ratio']:.1f}R) RSI={sig['rsi']:.0f}"
                    )
                    # execute_trades=True → Telegram vine din "Ordin plasat" (cu ticket+lots)
                    _notify_signal(sig, session_cfg["session_id"],
                                   telegram=not session_cfg.get("execute_trades", False))

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
                        _sig_type = sig.get("signal_type", "pullback")
                        if _sig_type == "flag":
                            risk_pct = session_cfg.get("flag_risk_pct", 0.01)
                        elif _sig_type == "inside_bar":
                            risk_pct = session_cfg.get("inside_bar_risk_pct", 0.01)
                        else:
                            risk_pct = _pick_risk_pct(sig.get("n_optional", 0), session_cfg)
                        lots, risk_usd = _calc_lots(sig["symbol"], sig["entry"], sig["sl"],
                                                    capital, risk_pct)
                        ticket = _place_order(sig, lots,
                                              session_cfg.get("expire_bars", 4),
                                              session_cfg["bar_minutes"], log)
                        if ticket:
                            # Ordin plasat cu succes — stocheaza lot si risk real in pending
                            state["mt5_tickets"][sig["signal_id"]] = ticket
                            # comment_map: sig_id[:16] -> full_sig_id (recuperare dupa truncation ICMarketsEU)
                            state["comment_map"][sig["signal_id"][:16]] = sig["signal_id"]
                            state["pending"][symbol][sig["signal_id"]]["lot_size"] = lots
                            state["pending"][symbol][sig["signal_id"]]["risk_usd"] = risk_usd
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
                        # Guard anti-duplicat: verifica daca exista deja un ordin MT5 pending
                        # pentru acelasi simbol/directie/entry (plasare anterioara neconfirmata
                        # in state — ex: crash intre order_send si pickle.dump).
                        # Daca exista, adopta ticket-ul existent in loc sa plaseze un ordin nou.
                        if _mt5_exec is not None:
                            _d_ord = _p["direction"]
                            _stop_types = (4, 2) if _d_ord == 1 else (5, 3)  # BUY/SELL STOP+LIMIT
                            try:
                                from strategy.signals import pip_size as _pip_sz
                                _tol = 5 * _pip_sz(symbol)
                            except Exception:
                                _tol = 0.001
                            _tracked = set(state.get("mt5_tickets", {}).values())
                            _dup_ticket = None
                            for _o in (_mt5_exec.orders_get(symbol=symbol) or []):
                                if _o.ticket in _tracked:
                                    continue
                                if (_o.type in _stop_types and
                                        abs(_o.price_open - _p["entry"]) < _tol):
                                    _dup_ticket = _o.ticket
                                    break
                            if _dup_ticket is not None:
                                state["mt5_tickets"][_sid] = _dup_ticket
                                state["comment_map"][_sid[:16]] = _sid
                                log.warning(
                                    f"  [DEDUP] {_sid}: ordin MT5 #{_dup_ticket} deja existent "
                                    f"@ {_p['entry']:.5f} — adoptat, plasare noua evitata"
                                )
                                _send_telegram(
                                    f"⚠️ <b>[DEDUP] {_sid}</b>\n"
                                    f"Ordin MT5 #{_dup_ticket} adoptat (era orfan in MT5)\n"
                                    f"<i>{session_cfg['session_id']}</i>"
                                )
                                continue
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
                        _lots, _risk_usd = _calc_lots(symbol, _p["entry"], _p["sl"], capital, _risk_pct)
                        log.info(f"  [RETRY] {_sid}: incerc plasare ordin (bara precedenta → None)")
                        _ticket = _place_order(_sig_retry, _lots,
                                               session_cfg.get("expire_bars", 4),
                                               session_cfg["bar_minutes"], log)
                        if _ticket:
                            state["mt5_tickets"][_sid] = _ticket
                            state["comment_map"][_sid[:16]] = _sid
                            state["pending"][symbol][_sid]["lot_size"] = _lots
                            state["pending"][symbol][_sid]["risk_usd"] = _risk_usd
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

            # Verifica sanatatea conexiunii MT5 si notifica la probleme
            _check_mt5_health(log, session_key, _expected_mt5_login)

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
