"""
MT5 Sync router — reconciliere manuala MT5 ↔ outcomes.csv
==========================================================
GET  /mt5/sync-status   — status ultima sincronizare + discrepante detectate
POST /mt5/sync          — ruleaza reconciliere completa (toate sesiunile cu execute_trades=True)

Exclude sesiunile OBS (execute_trades=False).
Sigur de rulat si cu botul activ — scrie doar in outcomes.csv, nu in state.pkl.
"""

import os
import re
import pickle
import threading
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException

from api.config import DATA_DIR, SESSIONS

router = APIRouter(prefix="/mt5", tags=["mt5"])

_SYNC_LOCK = threading.Lock()
_last_sync_result: Optional[dict] = None

_OUTCOMES_COLS = [
    "signal_id", "time_check", "symbol", "direction", "status",
    "entry", "sl", "tp", "r_ratio", "armed_at", "triggered_at",
    "exit_price", "exit_time", "result_r", "pnl_usd",
]

_BOT_SIG_RE      = re.compile(r"^S\d+-[A-Z0-9]+-(?:[A-Z0-9]+-)?(?:SIG|IB|FLG)\d*", re.IGNORECASE)
_BOT_SIG_FULL_RE = re.compile(r"^S\d+-[A-Z0-9]+-(?:[A-Z0-9]+-)?(?:SIG|IB|FLG)\d{4,}$", re.IGNORECASE)


def _mt5_exec():
    """Import MetaTrader5 lazy — nu esueaza daca nu e disponibil."""
    try:
        import MetaTrader5 as mt5
        if not mt5.initialize():
            return None
        return mt5
    except Exception:
        return None


def _load_state(session_id: str) -> Optional[dict]:
    pkl = os.path.join(DATA_DIR, "live_signals", session_id, "state.pkl")
    if not os.path.exists(pkl):
        return None
    try:
        with open(pkl, "rb") as f:
            return pickle.load(f)
    except Exception:
        return None


def _load_outcomes(session_id: str) -> pd.DataFrame:
    csv = os.path.join(DATA_DIR, "live_signals", session_id, "outcomes.csv")
    if not os.path.exists(csv):
        return pd.DataFrame(columns=_OUTCOMES_COLS)
    try:
        return pd.read_csv(csv)
    except Exception:
        return pd.DataFrame(columns=_OUTCOMES_COLS)


def _run_sync(fix: bool = False) -> dict:
    mt5 = _mt5_exec()
    if mt5 is None:
        return {
            "ok": False,
            "error": "MT5 nu este conectat",
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "sessions": [],
        }

    dt_from = datetime.now() - timedelta(days=10)
    dt_to   = datetime.now()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    sessions_report = []
    total_discrepancies = 0
    total_fixed = 0

    for sess in SESSIONS:
        session_id = sess["id"]
        if not sess.get("execute", True):
            continue  # Skip OBS

        state = _load_state(session_id)
        outcomes_df = _load_outcomes(session_id)
        outcomes_file = os.path.join(DATA_DIR, "live_signals", session_id, "outcomes.csv")
        markets = sess.get("markets", [])
        # Prefix semnal asteptat — ex: "S18-" pentru session18.
        # Ordinele care apartin altor sesiuni dar tranzactioneaza acelasi simbol
        # (ex: S2-NZDJPY gasit in session18 care si ea tradeaza NZDJPY) sunt ignorate.
        _label = sess.get("label", "")
        _sess_prefix = (_label.split()[0] + "-") if _label else ""

        existing_sig_ids: set = set()
        existing_pos_keys: set = set()
        if not outcomes_df.empty:
            existing_sig_ids = set(outcomes_df["signal_id"].dropna().astype(str))
            for _, row in outcomes_df.iterrows():
                try:
                    pnl = row.get("pnl_usd", "")
                    if str(pnl) not in ("nan", "", "None"):
                        existing_pos_keys.add((
                            str(row.get("symbol", "")),
                            round(float(pnl), 2),
                            str(row.get("exit_time", ""))[:19],
                        ))
                except Exception:
                    pass

        discrepancies = []
        new_rows_to_write = []

        # ── 1. Semnale pending triggered fara pozitie MT5 deschisa ──
        if state:
            mt5_tickets = state.get("mt5_tickets", {})
            pending = state.get("pending", {})
            for sym, sigs in pending.items():
                if sym not in markets:
                    continue
                for sig_id, sig in sigs.items():
                    if not sig.get("triggered"):
                        continue
                    ticket = mt5_tickets.get(sig_id)
                    if ticket is None:
                        discrepancies.append({
                            "type": "triggered_no_ticket",
                            "sig_id": sig_id,
                            "symbol": sym,
                            "detail": "Semnal triggered dar fara ticket MT5 in state.pkl",
                        })
                        continue
                    # Verifica daca pozitia e inca deschisa
                    # Retry de 2 ori (300ms pauza) pentru a evita false pozitive
                    # cauzate de latenta tranzitorie MT5 (ex: botul face o operatiune simultan)
                    pos = mt5.positions_get(ticket=ticket)
                    if not pos:
                        import time as _time
                        _time.sleep(0.3)
                        pos = mt5.positions_get(ticket=ticket)
                    if not pos:
                        _time.sleep(0.3)
                        # Fallback: cauta prin simbol (hedging mode edge case)
                        sym_pos = mt5.positions_get(symbol=sym) or []
                        pos = [p for p in sym_pos if p.ticket == ticket]
                    if not pos:
                        # Pozitia nu mai exista dupa 3 verificari — intr-adevar inchisa
                        if sig_id not in existing_sig_ids:
                            discrepancies.append({
                                "type": "triggered_position_closed_not_in_outcomes",
                                "sig_id": sig_id,
                                "symbol": sym,
                                "ticket": ticket,
                                "detail": "Pozitia MT5 e inchisa dar nu apare in outcomes.csv",
                            })

        # ── 2. Ordine MT5 inchise care nu sunt in outcomes.csv ──
        for symbol in markets:
            hist_orders = mt5.history_orders_get(dt_from, dt_to, group=symbol) or []
            tracked_tickets: set = set()
            if state:
                tracked_tickets = set(state.get("mt5_tickets", {}).values())

            for order in hist_orders:
                if order.state in (2, 5, 6):  # CANCELED, REJECTED, EXPIRED
                    continue
                comment = (getattr(order, "comment", "") or "").strip()
                if not _BOT_SIG_RE.match(comment):
                    continue
                # Ignora ordinele care apartin altor sesiuni ce tranzactioneaza acelasi simbol.
                # Prefixul "S18-" asigura ca numai semnalele acestei sesiuni sunt procesate.
                if _sess_prefix and not comment.upper().startswith(_sess_prefix.upper()):
                    continue
                if order.ticket in tracked_tickets:
                    continue  # Inca activ — gestionat de bot

                is_full = bool(_BOT_SIG_FULL_RE.match(comment))
                sig_id  = comment if is_full else f"{comment}_{order.ticket}"

                if sig_id in existing_sig_ids:
                    continue

                # Obtine deals pentru pozitie
                pos_id = getattr(order, "position_id", 0) or order.ticket
                deals  = mt5.history_deals_get(position=pos_id)
                if not deals:
                    continue

                entry_deal = next((d for d in deals if d.entry == 0), None)
                close_deal = next((d for d in deals if d.entry == 1), None)

                if not close_deal:
                    continue  # Pozitie inca deschisa

                entry_price = float(entry_deal.price if entry_deal else order.price_open)
                exit_price  = float(close_deal.price)
                exit_time   = datetime.fromtimestamp(close_deal.time).strftime("%Y-%m-%d %H:%M:%S")
                pnl_usd     = round(float(close_deal.profit), 4)
                d_int       = 1 if order.type in (0, 2, 4) else -1
                sl_price    = float(getattr(order, "sl", 0) or 0)
                tp_price    = float(getattr(order, "tp", 0) or 0)

                pos_key = (symbol, round(pnl_usd, 2), exit_time[:19])
                if pos_key in existing_pos_keys:
                    continue  # Pozitia deja in outcomes cu alt sig_id

                # Incearca sa gaseasca sig_id real din pending (comment trunchiat)
                if not is_full and state:
                    try:
                        from strategy.signals import pip_size as _psz
                        _pip = _psz(symbol)
                    except Exception:
                        _pip = 0.0001
                    for _s_id, _s_sig in state.get("pending", {}).get(symbol, {}).items():
                        if (_s_sig.get("direction") == d_int and
                                abs(_s_sig.get("entry", 0) - entry_price) < 5 * _pip):
                            sig_id = _s_id
                            break

                if sl_price and abs(entry_price - sl_price) > 1e-8:
                    risk = abs(entry_price - sl_price)
                    result_r = round((exit_price - entry_price) * d_int / risk, 3)
                    r_ratio  = round(abs(tp_price - entry_price) / risk, 3) if (
                        tp_price and abs(tp_price - entry_price) > 1e-8
                    ) else 0.0
                else:
                    result_r = 0.0
                    r_ratio  = 0.0

                status = "TP" if result_r > 0 else "SL"
                t_done = getattr(order, "time_done", 0) or 0
                triggered_at = datetime.fromtimestamp(
                    t_done if t_done else order.time_setup
                ).strftime("%Y-%m-%d %H:%M:%S")

                discrepancies.append({
                    "type":      "missing_in_outcomes",
                    "sig_id":    sig_id,
                    "symbol":    symbol,
                    "ticket":    order.ticket,
                    "status":    status,
                    "result_r":  result_r,
                    "pnl_usd":   pnl_usd,
                    "exit_time": exit_time,
                    "detail":    f"Pozitie MT5 #{order.ticket} inchisa ({status}) nu e in outcomes.csv",
                })

                if fix:
                    new_rows_to_write.append({
                        "signal_id":    sig_id,
                        "time_check":   now_str,
                        "symbol":       symbol,
                        "direction":    d_int,
                        "status":       status,
                        "entry":        entry_price,
                        "sl":           sl_price,
                        "tp":           tp_price,
                        "r_ratio":      r_ratio,
                        "armed_at":     triggered_at,
                        "triggered_at": triggered_at,
                        "exit_price":   exit_price,
                        "exit_time":    exit_time,
                        "result_r":     result_r,
                        "pnl_usd":      pnl_usd,
                    })
                    existing_sig_ids.add(sig_id)
                    existing_pos_keys.add(pos_key)

        # ── Scrie corectiile (fix=True) ──
        fixed_count = 0
        if fix and new_rows_to_write:
            # Dedup final in batch
            seen: set = set()
            deduped = []
            for r in new_rows_to_write:
                if r["signal_id"] not in seen:
                    deduped.append(r)
                    seen.add(r["signal_id"])
            pd.DataFrame(deduped).reindex(columns=_OUTCOMES_COLS).to_csv(
                outcomes_file, mode="a", header=not os.path.exists(outcomes_file),
                index=False
            )
            fixed_count = len(deduped)
            total_fixed += fixed_count

        total_discrepancies += len(discrepancies)
        sessions_report.append({
            "session_id":    session_id,
            "label":         sess.get("label", session_id),
            "discrepancies": discrepancies,
            "fixed":         fixed_count,
        })

    result = {
        "ok":                True,
        "time":              now_str,
        "total_discrepancies": total_discrepancies,
        "total_fixed":       total_fixed if fix else 0,
        "fix_applied":       fix,
        "sessions":          sessions_report,
    }

    global _last_sync_result
    _last_sync_result = result
    return result


@router.get("/sync-status")
def get_sync_status():
    """Returneaza rezultatul ultimei sincronizari (sau null daca nu a rulat inca)."""
    return _last_sync_result or {
        "ok": None,
        "time": None,
        "total_discrepancies": None,
        "sessions": [],
    }


@router.post("/sync")
def run_sync(fix: bool = False):
    """
    Ruleaza reconciliere MT5 ↔ outcomes.csv pentru toate sesiunile cu execute_trades=True.

    ?fix=false (default) — detectie doar, fara scriere
    ?fix=true  — scrie corectiile in outcomes.csv (sigur si cu botul activ)
    """
    if not _SYNC_LOCK.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Sync deja in desfasurare")
    try:
        return _run_sync(fix=fix)
    finally:
        _SYNC_LOCK.release()
