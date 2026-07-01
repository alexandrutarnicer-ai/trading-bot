"""
Repair outcomes.csv — curata datele corupte din toate sesiunile.
=================================================================
Ruleaza SEPARAT, cu botul OPRIT si MT5 conectat.

Probleme rezolvate:
1. Intrari duplicate cu acelasi signal_id
2. Signal IDs trunchiate (SIG00, IB000) — renumeste corect sau sterge duplicatele
3. Outcome-uri cu status=invalidat/expirat care ar trebui TP/SL (verifica MT5)
4. Intrari missing pentru pozitii MT5 inchise (nerecuperate)

Mod de utilizare:
    python scripts/repair_outcomes.py [--dry-run] [--session sessionN]

--dry-run: afiseaza ce ar face, fara sa modifice fisierele
--session: ruleaza doar pe o sesiune (ex: session13)
"""

import sys, os, argparse, pickle, re, shutil
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

_OUTCOMES_COLS = [
    "signal_id", "time_check", "symbol", "direction", "status",
    "entry", "sl", "tp", "r_ratio", "armed_at", "triggered_at",
    "exit_price", "exit_time", "result_r", "pnl_usd",
]

_BOT_SIG_RE      = re.compile(r"^S\d+-[A-Z0-9]+-(?:[A-Z0-9]+-)?(?:SIG|IB|FLG)\d*", re.IGNORECASE)
_BOT_SIG_FULL_RE = re.compile(r"^S\d+-[A-Z0-9]+-(?:[A-Z0-9]+-)?(?:SIG|IB|FLG)\d{4,}$", re.IGNORECASE)

# Sesiunile cu execute_trades=True
EXECUTE_SESSIONS = [
    "session1",  "session2",  "session3",  "session4",
    "session5",  "session6",  "session7",  "session8",
    "session9",  "session10", "session11", "session12",
    "session13", "session14", "session15", "session16",
    "session17", "session18", "session19",
]

SESSION_MARKETS = {
    "session1":  ["EURUSD"],   "session2":  ["AUDJPY"],
    "session3":  ["BTCUSD"],   "session4":  ["GER40"],
    "session5":  ["USDCHF"],   "session6":  ["US30"],
    "session7":  ["XRPUSD"],   "session8":  ["EURCAD"],
    "session9":  ["USDJPY"],   "session10": ["GBPCAD"],
    "session11": ["USDCAD"],   "session12": ["EURAUD"],
    "session13": ["EURJPY"],   "session14": ["CHFJPY"],
    "session15": ["GBPUSD"],   "session16": ["GBPAUD"],
    "session17": ["AUDCAD"],   "session18": ["NZDJPY"],
    "session19": ["AUDNZD"],
}


def _check_pos_closed(ticket: int, sig: dict):
    """Verifica daca o pozitie MT5 e inchisa si returneaza outcome real."""
    if mt5 is None:
        return None
    hist = mt5.history_orders_get(ticket=ticket)
    if not hist:
        return None
    order = hist[0]
    pos_id = getattr(order, "position_id", ticket) or ticket
    deals  = mt5.history_deals_get(position=pos_id)
    if not deals:
        return None
    close_deal = next((d for d in deals if d.entry == 1), None)
    if not close_deal:
        return None

    entry_deal  = next((d for d in deals if d.entry == 0), None)
    entry_price = float(entry_deal.price if entry_deal else order.price_open)
    exit_price  = float(close_deal.price)
    exit_time   = datetime.fromtimestamp(close_deal.time).strftime("%Y-%m-%d %H:%M:%S")
    pnl_usd     = round(float(close_deal.profit), 4)
    d_int       = sig.get("direction", 1)
    sl_price    = sig.get("sl", 0) or 0
    tp_price    = sig.get("tp", 0) or 0

    if sl_price and abs(entry_price - sl_price) > 1e-8:
        risk     = abs(entry_price - sl_price)
        result_r = round((exit_price - entry_price) * d_int / risk, 3)
        r_ratio  = round(abs(tp_price - entry_price) / risk, 3) if (
            tp_price and abs(tp_price - entry_price) > 1e-8
        ) else sig.get("r_ratio", 0.0)
    else:
        result_r = 0.0
        r_ratio  = sig.get("r_ratio", 0.0)

    status = "TP" if result_r > 0 else "SL"
    return {
        "status":       status,
        "result_r":     result_r,
        "pnl_usd":      pnl_usd,
        "exit_price":   exit_price,
        "exit_time":    exit_time,
        "entry":        entry_price,
        "r_ratio":      r_ratio,
    }


def repair_session(session_id: str, dry_run: bool):
    print(f"\n{'='*60}")
    print(f"Sesiune: {session_id}")
    print(f"{'='*60}")

    csv_path = os.path.join(DATA_DIR, "live_signals", session_id, "outcomes.csv")
    pkl_path = os.path.join(DATA_DIR, "live_signals", session_id, "state.pkl")

    if not os.path.exists(csv_path):
        print(f"  [SKIP] Nu exista outcomes.csv")
        return

    # Incarca state.pkl
    state = {}
    if os.path.exists(pkl_path):
        try:
            with open(pkl_path, "rb") as f:
                state = pickle.load(f)
        except Exception as e:
            print(f"  [WARN] state.pkl corupt: {e}")

    mt5_tickets = state.get("mt5_tickets", {})
    pending     = state.get("pending", {})
    markets     = SESSION_MARKETS.get(session_id, [])

    # Incarca outcomes
    df = pd.read_csv(csv_path)
    original_len = len(df)
    print(f"  {original_len} intrari in outcomes.csv")

    changes = []

    # ── 1. Detecteaza duplicate signal_id ──
    dup_ids = df[df.duplicated("signal_id", keep=False)]["signal_id"].unique()
    if len(dup_ids) > 0:
        print(f"\n  [1] {len(dup_ids)} signal_id-uri duplicate:")
        for sid in dup_ids:
            rows = df[df["signal_id"] == sid]
            print(f"     '{sid}' x{len(rows)}: {list(rows['status'])}")

    # ── 2. Detecteaza intrari cu status=invalidat/expirat care ar putea fi TP/SL ──
    wrong_status = df[df["status"].isin(["invalidat", "expirat"])]
    if len(wrong_status) > 0 and mt5 is not None:
        print(f"\n  [2] {len(wrong_status)} intrari cu status invalidat/expirat — verific MT5...")
        for idx, row in wrong_status.iterrows():
            sig_id = str(row.get("signal_id", ""))
            ticket = mt5_tickets.get(sig_id)
            if ticket is None:
                # Cauta in pending dupa pret
                for sym, sigs in pending.items():
                    for s_id, s_sig in sigs.items():
                        if s_id == sig_id:
                            ticket = mt5_tickets.get(s_id)
                            break

            if ticket:
                sig_dict = {}
                for sym, sigs in pending.items():
                    if sig_id in sigs:
                        sig_dict = sigs[sig_id]
                        break
                mt5_res = _check_pos_closed(ticket, sig_dict)
                if mt5_res and mt5_res["status"] in ("TP", "SL"):
                    old_status = str(row.get("status"))
                    print(
                        f"     {sig_id}: {old_status} → {mt5_res['status']} "
                        f"{mt5_res['result_r']:+.3f}R (ticket #{ticket})"
                    )
                    changes.append({
                        "idx":    idx,
                        "type":   "status_fix",
                        "sig_id": sig_id,
                        "update": mt5_res,
                    })

    # ── 3. Detecteaza ID-uri trunchiate (SIG00, IB000) ──
    trunc_mask = df["signal_id"].astype(str).apply(
        lambda s: bool(_BOT_SIG_RE.match(s)) and not bool(_BOT_SIG_FULL_RE.match(s))
    )
    trunc_rows = df[trunc_mask]
    if len(trunc_rows) > 0:
        print(f"\n  [3] {len(trunc_rows)} intrari cu signal_id trunchiat:")
        for _, row in trunc_rows.iterrows():
            sid    = str(row.get("signal_id", ""))
            status = str(row.get("status", ""))
            r      = row.get("result_r", 0)
            pnl    = row.get("pnl_usd", "N/A")
            print(f"     '{sid}' status={status} result_r={r} pnl_usd={pnl}")

    # ── 4. Scan MT5 history pentru outcome-uri lipsa ──
    if mt5 is not None and markets:
        print(f"\n  [4] Scanare MT5 history pentru {markets}...")
        dt_from = datetime.now() - timedelta(days=10)
        dt_to   = datetime.now()

        existing_sig_ids  = set(df["signal_id"].dropna().astype(str))
        existing_pos_keys = set()
        for _, row in df.iterrows():
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

        new_rows = []
        for symbol in markets:
            hist_orders = mt5.history_orders_get(dt_from, dt_to, group=symbol) or []
            tracked_tickets = set(mt5_tickets.values())

            for order in hist_orders:
                if order.state in (2, 5, 6):
                    continue
                comment = (getattr(order, "comment", "") or "").strip()
                if not _BOT_SIG_RE.match(comment):
                    continue
                if order.ticket in tracked_tickets:
                    continue

                is_full = bool(_BOT_SIG_FULL_RE.match(comment))
                sig_id  = comment if is_full else f"{comment}_{order.ticket}"

                if sig_id in existing_sig_ids:
                    continue

                pos_id = getattr(order, "position_id", 0) or order.ticket
                deals  = mt5.history_deals_get(position=pos_id)
                if not deals:
                    continue

                entry_deal = next((d for d in deals if d.entry == 0), None)
                close_deal = next((d for d in deals if d.entry == 1), None)
                if not close_deal:
                    continue

                entry_price = float(entry_deal.price if entry_deal else order.price_open)
                exit_price  = float(close_deal.price)
                exit_time   = datetime.fromtimestamp(close_deal.time).strftime("%Y-%m-%d %H:%M:%S")
                pnl_usd     = round(float(close_deal.profit), 4)
                d_int       = 1 if order.type in (0, 2, 4) else -1
                sl_price    = float(getattr(order, "sl", 0) or 0)
                tp_price    = float(getattr(order, "tp", 0) or 0)

                pos_key = (symbol, round(pnl_usd, 2), exit_time[:19])
                if pos_key in existing_pos_keys:
                    continue

                # Incearca match cu pending dupa pret
                if not is_full:
                    try:
                        from strategy.signals import pip_size as _psz
                        _pip = _psz(symbol)
                    except Exception:
                        _pip = 0.0001
                    for _s_id, _s_sig in pending.get(symbol, {}).items():
                        if (_s_sig.get("direction") == d_int and
                                abs(_s_sig.get("entry", 0) - entry_price) < 5 * _pip):
                            # Nu face match cu semnale ACTIVE (triggerate + au ticket MT5)
                            # → ar corupe tracking-ul cand pozitia se va inchide
                            if _s_id in mt5_tickets:
                                break  # semnal activ — ignora, pastreaza {comment}_{ticket}
                            sig_id = _s_id
                            break

                if sig_id in existing_sig_ids:
                    continue

                if sl_price and abs(entry_price - sl_price) > 1e-8:
                    risk     = abs(entry_price - sl_price)
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

                new_row = {
                    "signal_id":    sig_id,
                    "time_check":   datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
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
                }
                print(
                    f"     MISSING: {sig_id} {symbol} {status} "
                    f"{result_r:+.3f}R {pnl_usd:+.2f}USD (ticket #{order.ticket})"
                )
                new_rows.append(new_row)
                existing_sig_ids.add(sig_id)
                existing_pos_keys.add(pos_key)

        if new_rows:
            changes.append({"type": "add_missing", "rows": new_rows})
        else:
            print(f"     Nicio intrare lipsa.")

    # ── 5. Semnale din signals.csv fara outcome si fara pending ──
    signals_path = csv_path.replace("outcomes.csv", "signals.csv")
    if os.path.exists(signals_path):
        try:
            sig_df = pd.read_csv(signals_path)
        except Exception:
            sig_df = pd.DataFrame()

        if not sig_df.empty:
            existing_sig_ids_now = set(df["signal_id"].dropna().astype(str))
            # Adaugam si cele care tocmai au fost gasite in [4]
            for ch in changes:
                if ch.get("type") == "add_missing":
                    for r in ch.get("rows", []):
                        existing_sig_ids_now.add(r["signal_id"])

            # State pending (toate nivelurile)
            state_pending_ids = set()
            for sym_sigs in pending.values():
                state_pending_ids.update(sym_sigs.keys())

            # Construim fuzzy map al outcomes existente: (sym, dir, entry_rotunjit) -> sig_id
            try:
                from strategy.signals import pip_size as _psz
            except Exception:
                _psz = None

            def _pip_sym(sym):
                if _psz:
                    try:
                        return _psz(sym)
                    except Exception:
                        pass
                if "JPY" in sym.upper():
                    return 0.01
                if any(x in sym.upper() for x in ("BTC","ETH","XRP","GER","US30","UK100","XAU")):
                    return 1.0
                return 0.0001

            oc_fuzzy: dict = {}  # (sym, dir, entry_round5) -> sig_id
            for _, oc_row in df.iterrows():
                _sym = str(oc_row.get("symbol", ""))
                _dir = int(oc_row.get("direction", 0))
                _en  = float(oc_row.get("entry", 0))
                _pip = _pip_sym(_sym)
                _key = (_sym, _dir, round(_en / _pip) if _pip else round(_en, 5))
                oc_fuzzy[_key] = str(oc_row.get("signal_id", ""))

            orphan_sig_rows = []
            rename_pairs = []  # [(old_sig_id_in_outcomes, correct_sig_id_from_signals)]

            for _, srow in sig_df.iterrows():
                s_id  = str(srow.get("signal_id", ""))
                sym   = str(srow.get("symbol", ""))
                d_int = int(srow.get("direction", 0))
                s_en  = float(srow.get("entry", 0))
                s_sl  = float(srow.get("sl", 0))
                s_tp  = float(srow.get("tp", 0))
                s_rr  = float(srow.get("r_ratio", 0))

                if s_id in existing_sig_ids_now:
                    continue  # direct match — OK
                if s_id in state_pending_ids:
                    continue  # inca in pending — OK

                # Verifica fuzzy match cu outcomes existente
                _pip = _pip_sym(sym)
                _key = (sym, d_int, round(s_en / _pip) if _pip else round(s_en, 5))
                if _key in oc_fuzzy:
                    old_oc_id = oc_fuzzy[_key]
                    # Semnal acoperit de un outcome cu sig_id gresit (trunchiat/ticket-suffix)
                    # → propunem redenumire in outcomes.csv (o singura data per outcome)
                    if (old_oc_id != s_id and not _BOT_SIG_FULL_RE.match(old_oc_id)
                            and not any(p[0] == old_oc_id for p in rename_pairs)):
                        rename_pairs.append((old_oc_id, s_id))
                    continue

                # Semnal cu adevarat orfan — cauta in MT5 history
                orphan_sig_rows.append({
                    "sig_id": s_id, "symbol": sym, "direction": d_int,
                    "entry": s_en, "sl": s_sl, "tp": s_tp, "r_ratio": s_rr,
                })

            if rename_pairs:
                print(f"\n  [5a] {len(rename_pairs)} outcome-uri cu sig_id gresit (mismatch truncat):")
                for old_id, new_id in rename_pairs:
                    print(f"     '{old_id}' => '{new_id}'")
                changes.append({"type": "rename_sig_ids", "pairs": rename_pairs})

            if orphan_sig_rows and mt5 is not None:
                print(f"\n  [5b] {len(orphan_sig_rows)} semnale orfane — scanare MT5 history...")
                dt_from = datetime.now() - timedelta(days=10)
                dt_to   = datetime.now()
                existing_sig_ids_now2 = set(existing_sig_ids_now)
                orphan_new_rows = []

                for osig in orphan_sig_rows:
                    _s_id = osig["sig_id"]
                    _sym  = osig["symbol"]
                    _d    = osig["direction"]
                    _en   = osig["entry"]
                    _sl   = osig["sl"]
                    _tp   = osig["tp"]
                    _rr   = osig["r_ratio"]
                    _pip  = _pip_sym(_sym)

                    hist = mt5.history_orders_get(dt_from, dt_to, group=_sym) or []
                    matched_order = None
                    for order in hist:
                        if order.state in (2, 5, 6):
                            continue
                        if abs(order.price_open - _en) > 5 * _pip:
                            continue
                        d_ord = 1 if order.type in (0, 2, 4) else -1
                        if d_ord != _d:
                            continue
                        pos_id = getattr(order, "position_id", 0) or order.ticket
                        deals = mt5.history_deals_get(position=pos_id)
                        if not deals:
                            continue
                        close_deal = next((dd for dd in deals if dd.entry == 1), None)
                        if not close_deal:
                            continue  # pozitie inca deschisa
                        matched_order = (order, deals, close_deal)
                        break

                    if matched_order:
                        order, deals, close_deal = matched_order
                        entry_deal  = next((dd for dd in deals if dd.entry == 0), None)
                        entry_price = float(entry_deal.price if entry_deal else order.price_open)
                        exit_price  = float(close_deal.price)
                        exit_time   = datetime.fromtimestamp(close_deal.time).strftime("%Y-%m-%d %H:%M:%S")
                        pnl_usd     = round(float(close_deal.profit), 4)

                        if _sl and abs(entry_price - _sl) > 1e-8:
                            risk     = abs(entry_price - _sl)
                            result_r = round((exit_price - entry_price) * _d / risk, 3)
                            r_ratio  = round(abs(_tp - entry_price) / risk, 3) if (
                                _tp and abs(_tp - entry_price) > 1e-8
                            ) else _rr
                        else:
                            result_r = 0.0
                            r_ratio  = _rr

                        oc_status = "TP" if result_r > 0 else "SL"
                        t_done = getattr(order, "time_done", 0) or 0
                        trig_at = datetime.fromtimestamp(
                            t_done if t_done else order.time_setup
                        ).strftime("%Y-%m-%d %H:%M:%S")

                        # Verifica pos_key deduplicare
                        _pos_key = (_sym, round(pnl_usd, 2), exit_time[:19])
                        if _pos_key in existing_pos_keys:
                            print(f"     ORPHAN {_s_id}: pozitie deja in outcomes (pos_key match)")
                            continue

                        orphan_new_rows.append({
                            "signal_id":    _s_id,
                            "time_check":   datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "symbol":       _sym,
                            "direction":    _d,
                            "status":       oc_status,
                            "entry":        entry_price,
                            "sl":           _sl,
                            "tp":           _tp,
                            "r_ratio":      r_ratio,
                            "armed_at":     trig_at,
                            "triggered_at": trig_at,
                            "exit_price":   exit_price,
                            "exit_time":    exit_time,
                            "result_r":     result_r,
                            "pnl_usd":      pnl_usd,
                        })
                        existing_sig_ids_now2.add(_s_id)
                        existing_pos_keys.add(_pos_key)
                        print(
                            f"     ORPHAN FOUND: {_s_id} {_sym} {oc_status} "
                            f"{result_r:+.3f}R {pnl_usd:+.2f}USD (ticket #{order.ticket})"
                        )
                    else:
                        print(f"     ORPHAN NOT FOUND in MT5: {_s_id} ({_sym} @ {_en:.5f})")

                if orphan_new_rows:
                    changes.append({"type": "add_orphan", "rows": orphan_new_rows})
            elif orphan_sig_rows:
                print(f"\n  [5b] {len(orphan_sig_rows)} semnale orfane (MT5 nedisponibil):")
                for osig in orphan_sig_rows:
                    print(f"     {osig['sig_id']} ({osig['symbol']} @ {osig['entry']:.5f})")

    # Detecteaza daca exista duplicate reale (sintetic vs. real, sau acelasi pnl)
    # Doua pozitii diferite cu acelasi ID trunchiat si pnl diferit = PASTRAM ambele
    _SYNTHETIC = {"expirat", "invalidat"}
    _REAL_ST   = {"TP", "SL", "vineri_close", "news_close", "be_lock", "be_lock2"}
    needs_dedup = False
    for _sid, _grp in df.groupby("signal_id", sort=False):
        if len(_grp) <= 1:
            continue
        _statuses = set(_grp["status"].dropna().astype(str))
        if _statuses & _SYNTHETIC and _statuses & _REAL_ST:
            needs_dedup = True  # sintetic + real → eliminam sinteticul
            break
        try:
            _pnls = [round(float(p), 2) for p in _grp["pnl_usd"]
                     if str(p) not in ("nan", "None", "")]
        except Exception:
            _pnls = []
        if len(set(_pnls)) <= 1:
            needs_dedup = True  # acelasi pnl → duplicate real → eliminam
            break
    if needs_dedup:
        changes.append({"type": "dedup"})

    # ── Aplica modificarile ──
    if not changes:
        print(f"\n  Nicio modificare necesara.")
        return

    if dry_run:
        print(f"\n  [DRY-RUN] {len(changes)} seturi de modificari — nu s-a scris nimic.")
        return

    # Backup
    backup = csv_path + ".bak"
    shutil.copy2(csv_path, backup)
    print(f"\n  Backup: {backup}")

    df_work = df.copy()
    new_rows_all = []

    for ch in changes:
        if ch["type"] == "status_fix":
            idx    = ch["idx"]
            update = ch["update"]
            for col, val in update.items():
                if col in df_work.columns:
                    df_work.at[idx, col] = val
            print(f"  FIX: {ch['sig_id']} → {update['status']} {update['result_r']:+.3f}R")

        elif ch["type"] == "add_missing":
            new_rows_all.extend(ch["rows"])

        elif ch["type"] == "add_orphan":
            new_rows_all.extend(ch["rows"])

        elif ch["type"] == "rename_sig_ids":
            # Redenumeste sig_id-urile gresite (trunchiate) la sig_id-ul real din signals.csv
            for old_id, new_id in ch["pairs"]:
                mask = df_work["signal_id"].astype(str) == old_id
                if mask.any():
                    df_work.loc[mask, "signal_id"] = new_id
                    print(f"  RENAME: '{old_id}' => '{new_id}'")

        elif ch["type"] == "dedup":
            pass  # tratat mai jos cu drop_duplicates

    # Smart dedup signal_id:
    # - Sintetic (expirat/invalidat) + Real (TP/SL) cu acelasi ID → pastram realul
    # - Ambele reale, acelasi pnl → pastram ultima aparitie (cea mai recenta)
    # - Ambele reale, pnl diferit → pozitii diferite cu acelasi ID trunchiat → pastram ambele
    _SYNTHETIC = {"expirat", "invalidat"}
    _REAL_ST   = {"TP", "SL", "vineri_close", "news_close", "be_lock", "be_lock2"}
    before_dedup = len(df_work)
    dedup_parts = []
    for _sid, _grp in df_work.groupby("signal_id", sort=False):
        if len(_grp) == 1:
            dedup_parts.append(_grp)
            continue
        _statuses  = set(_grp["status"].dropna().astype(str))
        _has_real  = bool(_statuses & _REAL_ST)
        _has_synth = bool(_statuses & _SYNTHETIC)
        if _has_real and _has_synth:
            # Elimina sinteticele, pastreaza realele
            _kept = _grp[_grp["status"].isin(_REAL_ST)]
            dedup_parts.append(_kept if len(_kept) else _grp.tail(1))
            continue
        try:
            _pnls = [round(float(p), 2) for p in _grp["pnl_usd"]
                     if str(p) not in ("nan", "None", "")]
        except Exception:
            _pnls = []
        if len(set(_pnls)) <= 1:
            dedup_parts.append(_grp.tail(1))  # Acelasi pnl → dup adevarat → pastreaza ultima
        else:
            dedup_parts.append(_grp)  # Pnl diferit → pozitii diferite → pastram toate
    df_work = pd.concat(dedup_parts, ignore_index=True) if dedup_parts else df_work
    removed = before_dedup - len(df_work)
    if removed:
        print(f"  DEDUP: {removed} intrari duplicate eliminate")

    # Adauga randurile noi
    if new_rows_all:
        df_new = pd.DataFrame(new_rows_all).reindex(columns=_OUTCOMES_COLS)
        df_work = pd.concat([df_work, df_new], ignore_index=True)

    df_work.reindex(columns=_OUTCOMES_COLS).to_csv(csv_path, index=False)
    print(f"\n  Salvat: {len(df_work)} intrari (era {original_len})")


def main():
    parser = argparse.ArgumentParser(description="Repair outcomes.csv")
    parser.add_argument("--dry-run", action="store_true", help="Doar afiseaza, nu modifica")
    parser.add_argument("--session", help="Repara doar o sesiune (ex: session13)")
    args = parser.parse_args()

    if mt5 is not None:
        if not mt5.initialize():
            print("EROARE: MT5 nu e conectat — rulare fara verificare pozitii inchise")
    else:
        print("ATENTIE: MetaTrader5 nu e instalat — ruleaza fara MT5")

    if args.dry_run:
        print("\n=== DRY-RUN mode — nicio modificare ===")

    sessions = [args.session] if args.session else EXECUTE_SESSIONS

    for session_id in sessions:
        try:
            repair_session(session_id, dry_run=args.dry_run)
        except Exception as e:
            print(f"\n  EROARE la {session_id}: {e}")
            import traceback; traceback.print_exc()

    if mt5 is not None:
        mt5.shutdown()

    print("\n=== Done ===")


if __name__ == "__main__":
    main()
