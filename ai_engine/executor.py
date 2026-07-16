"""
ai_engine.executor — mainile motorului: ordine MT5 pe cont DEMO, cu rails hard.

Principii:
  - REFUZA sa porneasca pe orice cont care nu e DEMO (acelasi guard ca Mt5DataSource).
  - Namespace propriu: magic number + prefix comment "AI" — nu atinge si nu vede
    niciodata pozitiile botului pe reguli (filtrare stricta pe magic).
  - Sanity checks INAINTE de orice ordin: geometrie SL/TP, RR minim, SL max N*ATR,
    numar maxim de pozitii, stop zilnic de pierdere. LLM-ul propune, rails-urile dispun.
  - mode="shadow" in config → totul identic, dar fara order_send (doar log).
"""

from __future__ import annotations

import logging
from datetime import datetime

import MetaTrader5 as mt5

log = logging.getLogger("ai_engine.executor")

_FILLINGS = []   # populat la connect() — IOC/FOK/RETURN in ordinea suportata


def connect() -> "mt5.AccountInfo":
    """Initializeaza MT5 si impune cont DEMO. Ridica RuntimeError altfel."""
    if not mt5.initialize():
        raise RuntimeError(f"mt5.initialize() a esuat: {mt5.last_error()}")
    acc = mt5.account_info()
    if acc is None:
        mt5.shutdown()
        raise RuntimeError("Nu pot citi contul MT5.")
    if acc.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO:
        mt5.shutdown()
        raise RuntimeError(
            f"BLOCAT — contul {acc.login} NU este DEMO. Motorul AI refuza sa ruleze.")
    global _FILLINGS
    _FILLINGS = [mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_RETURN]
    return acc


def equity() -> float:
    acc = mt5.account_info()
    return float(acc.equity) if acc else 0.0


def capital_base(cfg: dict) -> float:
    """
    Baza de capital a motorului AI pentru sizing (inainte de capital_fraction
    per piata):
      - capital_sync_mt5=True (default): equity-ul REAL din MT5 — comportamentul
        de dinainte, sincron cu contul la fiecare ordin.
      - capital_sync_mt5=False: capitalul FIX alocat AI-ului (capital_usd),
        PLAFONAT la equity-ul real cand acesta e disponibil — nu poti aloca
        mai mult capital decat exista in cont (protectie la typo: 100000 pe un
        cont de 700$ nu umfla riscul). Cu MT5 indisponibil (equity 0) se
        foloseste capitalul fix ca atare.
    """
    if cfg.get("capital_sync_mt5", True):
        return equity()
    cap = float(cfg.get("capital_usd") or 0.0)
    eq = equity()
    return min(cap, eq) if eq > 0 else cap


# ── Stare pozitii/ordine AI (filtrate pe magic) ──────────────────────────────

def ai_positions(magic: int) -> list:
    return [p for p in (mt5.positions_get() or []) if p.magic == magic]


def ai_pending_orders(magic: int) -> list:
    return [o for o in (mt5.orders_get() or []) if o.magic == magic]


def open_position_for(symbol: str, magic: int):
    pos = [p for p in ai_positions(magic) if p.symbol == symbol]
    return pos[0] if pos else None


# ── Stare piata: weekend (FX inchis) vs cripto (non-stop) ────────────────────

# Tokeni de cripto — aceste piete tranzactioneaza si in weekend (fara Vineri-close).
_CRYPTO_TOKENS = ("BTC", "ETH", "XRP", "LTC", "DOGE", "ADA", "SOL", "BNB", "DOT",
                  "AVAX", "MATIC", "LINK", "BCH", "XLM", "TRX")


def is_crypto(symbol: str) -> bool:
    """True daca simbolul e cripto (deschis in weekend, exceptat de la Vineri-close)."""
    s = symbol.upper()
    return any(tok in s for tok in _CRYPTO_TOKENS)


def is_market_weekend_closed(symbol: str, now, friday_close_hour: int = 22) -> bool:
    """
    True daca piata `symbol` e inchisa pentru weekend la `now` (ora RO, naiv).

    FX/indici: inchis Vineri de la `friday_close_hour`, tot Sambata si toata Duminica
    (redeschide Luni 00:00 — conservator, evita gap-ul volatil de duminica seara).
    Cripto: mereu deschis -> intoarce mereu False.

    Alinierea cu botul pe reguli: aceeasi logica ca skip_weekdays {5,6} + friday_close.
    """
    if is_crypto(symbol):
        return False
    wd = now.weekday()   # 0=Luni ... 4=Vineri, 5=Sambata, 6=Duminica
    if wd == 4 and now.hour >= friday_close_hour:
        return True
    if wd in (5, 6):
        return True
    return False


# ── Validare decizie (rails) ─────────────────────────────────────────────────

def validate_decision(d: dict, snapshot: dict, cfg: dict,
                      n_committed: int, daily_r: float,
                      symbol_committed: bool = False,
                      market_state: dict | None = None) -> str | None:
    """
    Returneaza motivul respingerii sau None daca decizia e executabila.

    `n_committed` = expunerea angajata (pozitii deschise + ordine pending). Se
    numara si pending-urile pentru ca fiecare stop poate deveni pozitie — altfel
    la cold-start s-ar plasa mai multe ordine decat max_open_positions.

    `symbol_committed` = exista deja o pozitie SAU un ordin pending AI pe ACEST
    simbol. Motorul nu face pyramiding — un al doilea ordin pe acelasi setup e
    doar expunere dublata (vezi bug-ul 3x XRPUSD din instante multiple). Chiar cu
    o singura instanta, plafonul global (max_open_positions) nu impiedica stivuirea
    pe acelasi simbol; acest gate o interzice explicit.

    `market_state` (optional, din market_overrides): limitele PER PIATA —
      {symbol, daily_r, trades_today, max_daily_loss_R, max_trades_per_day}.
    None → comportament identic cu inainte (doar rails globale).
    """
    if d["action"] not in ("OPEN_LONG", "OPEN_SHORT"):
        return None   # CLOSE/WAIT nu au geometrie de validat aici

    if symbol_committed:
        return (f"exista deja o pozitie/ordin AI pe {snapshot.get('symbol', '?')} "
                "— fara pyramiding (o singura expunere per simbol)")
    if n_committed >= cfg["max_open_positions"]:
        return f"expunere maxima atinsa ({n_committed} pozitii+pending, max {cfg['max_open_positions']})"
    if daily_r <= -cfg["max_daily_loss_R"]:
        return f"stop zilnic de pierdere atins ({daily_r:+.1f}R)"

    # ── Rails PER PIATA (market_overrides) — active doar daca sunt configurate ──
    if market_state:
        ms = market_state
        mdl = ms.get("max_daily_loss_R")
        if mdl is not None and ms.get("daily_r", 0.0) <= -float(mdl):
            return (f"stop zilnic PE PIATA atins pe {ms.get('symbol', '?')} "
                    f"({ms.get('daily_r', 0.0):+.2f}R, limita -{float(mdl):.1f}R)")
        mtd = ms.get("max_trades_per_day")
        if mtd is not None and ms.get("trades_today", 0) >= int(mtd):
            return (f"anti-overtrading pe {ms.get('symbol', '?')}: "
                    f"{ms.get('trades_today', 0)} ordine plasate azi (max {int(mtd)}/zi)")

    price = snapshot["price"]
    atr   = snapshot["atr"] or 0
    sl, tp, entry = d["sl"], d["tp"], d["entry"]
    if sl is None or tp is None:
        return "SL sau TP lipsa"
    if d["order_type"] == "market":
        entry = price
    if entry is None:
        return "entry lipsa pentru ordin stop"

    long_ = d["action"] == "OPEN_LONG"
    if long_ and not (sl < entry < tp):
        return f"geometrie invalida LONG (sl={sl} entry={entry} tp={tp})"
    if not long_ and not (tp < entry < sl):
        return f"geometrie invalida SHORT (sl={sl} entry={entry} tp={tp})"

    risk_dist = abs(entry - sl)
    if risk_dist <= 0:
        return "distanta SL zero"
    rr = abs(tp - entry) / risk_dist
    if rr < cfg["min_rr"]:
        return f"RR {rr:.2f} sub minim {cfg['min_rr']}"
    if atr > 0 and risk_dist > cfg["max_sl_atr_mult"] * atr:
        return f"SL la {risk_dist / atr:.1f}xATR (max {cfg['max_sl_atr_mult']})"
    # ordin stop trebuie sa fie DINCOLO de pret in directia trade-ului
    if d["order_type"] == "stop":
        if long_ and entry <= price:
            return f"BUY_STOP {entry} sub pretul curent {price}"
        if not long_ and entry >= price:
            return f"SELL_STOP {entry} peste pretul curent {price}"
    return None


# ── Sizing (identic ca logica cu live/_calc_lots — tick value real MT5) ──────

def calc_lots(symbol: str, entry: float, sl: float,
              capital: float, risk_pct: float) -> tuple[float, float | None]:
    info = mt5.symbol_info(symbol)
    if info is None:
        return 0.0, None
    dist = abs(entry - sl)
    if dist <= 0 or info.trade_tick_size <= 0:
        return 0.0, None
    val_per_price_unit = info.trade_tick_value / info.trade_tick_size
    risk_usd_target = capital * risk_pct
    raw  = risk_usd_target / (dist * val_per_price_unit)
    step = info.volume_step if info.volume_step > 0 else 0.01
    lot  = max(info.volume_min, (raw // step) * step)
    lot  = round(lot, 2)
    risk_usd = round(lot * dist * val_per_price_unit, 2)
    return lot, risk_usd


def snap_fixed_lots(symbol: str, fixed_lots: float,
                    entry: float, sl: float) -> tuple[float, float | None]:
    """
    Volum FIX per ordin (market_overrides.fixed_lots), aliniat la specificatiile
    brokerului: clamp la [volume_min, volume_max] si rotunjit in JOS la volume_step
    (nu crestem niciodata expunerea peste ce a configurat utilizatorul, cu exceptia
    lotului minim — sub el ordinul nu exista). Returneaza (lot, risc_usd_la_SL).
    """
    info = mt5.symbol_info(symbol)
    if info is None:
        return 0.0, None
    step = info.volume_step if info.volume_step > 0 else 0.01
    # floor la step cu epsilon: fara el, 0.5 // 0.01 = 49 (float) → 0.49 in loc de 0.50
    lot = int(float(fixed_lots) / step + 1e-9) * step
    lot = max(info.volume_min, lot)
    if info.volume_max and info.volume_max > 0:
        lot = min(lot, info.volume_max)
    lot = round(lot, 2)
    dist = abs(entry - sl)
    risk_usd = None
    if dist > 0 and info.trade_tick_size > 0:
        risk_usd = round(lot * dist * (info.trade_tick_value / info.trade_tick_size), 2)
    return lot, risk_usd


# ── Sanitizare pret ordin STOP (pur, testabil fara MT5) ─────────────────────

def adjust_stop_bracket(entry: float, sl: float, tp: float, ref: float,
                        long_: bool, buf: float, digits: int) -> tuple:
    """
    Ajusteaza un bracket de ordin STOP fata de pretul LIVE `ref` (ask pt BUY,
    bid pt SELL). Motivul: brokerii ECN (ICMarketsEU) au trade_stops_level=0,
    deci nu exista un prag minim de distanta impus de broker — iar modelul pune
    adesea intrarea la ~0.5 pip de pretul din snapshot (invechit, bara inchisa).
    Intre snapshot si trimitere pretul se misca -> BUY_STOP ajunge sub/la piata
    -> serverul respinge cu 10015 "Invalid price" (aparea ca 'failed').

    Reguli:
    - daca pretul LIVE a atins deja nivelul de intrare (BUY_STOP: ref>=entry) ->
      breakout-ul s-a intamplat deja, NU urmarim -> (None, motiv).
    - daca intrarea e pe partea corecta dar mai aproape de `buf` -> muta TOT
      bracket-ul (entry+sl+tp) cu acelasi delta ca sa devina un stop valid,
      pastrand geometria R (risc/reward neschimbate).
    - normalizeaza toate preturile la `digits`.

    Returneaza (entry, sl, tp, None) sau (None, None, None, motiv_skip).
    """
    if long_:
        if entry <= ref:
            return None, None, None, (f"pretul curent {ref} a atins deja intrarea "
                                      f"{entry} — breakout ratat, nu urmarim")
        gap = entry - ref
        if gap < buf:
            delta = buf - gap
            entry += delta; sl += delta; tp += delta
    else:
        if entry >= ref:
            return None, None, None, (f"pretul curent {ref} a atins deja intrarea "
                                      f"{entry} — breakout ratat, nu urmarim")
        gap = ref - entry
        if gap < buf:
            delta = buf - gap
            entry -= delta; sl -= delta; tp -= delta
    return round(entry, digits), round(sl, digits), round(tp, digits), None


# ── Executie ─────────────────────────────────────────────────────────────────

def _send_with_fillings(req: dict):
    """order_send cu retry pe filling modes (10030/10006 → incearca urmatorul)."""
    last = None
    for f in _FILLINGS:
        req["type_filling"] = f
        res = mt5.order_send(req)
        last = res
        if res is None:
            continue
        if res.retcode == mt5.TRADE_RETCODE_DONE:
            return res
        if res.retcode not in (10030, 10006):
            return res
    req.pop("type_filling", None)
    res = mt5.order_send(req)
    return res if res is not None else last


def place(d: dict, snapshot: dict, cfg: dict, decision_id: int,
          capital_fraction: float = 1.0,
          fixed_lots: float | None = None) -> tuple[str, str, int | None]:
    """
    Executa o decizie OPEN_*. Returneaza (status, detail, ticket):
      status: "placed" | "rejected" | "failed" | "shadow"

    `capital_fraction` (market_overrides): fractia din equity folosita ca baza de
    sizing pe aceasta piata (risc $ = equity * fraction * risk_pct). Default 1.0
    = tot equity-ul, identic cu comportamentul de dinainte.

    `fixed_lots` (market_overrides.fixed_lots): volum FIX per ordin — inlocuieste
    complet sizing-ul dinamic pe risc (snap la volume_min/step/max al brokerului).
    None = sizing dinamic, identic cu comportamentul de dinainte. Rail-ul de marja
    (<=40% din marja libera) ramane activ si pe lot fix.
    """
    symbol = snapshot["symbol"]
    capital_fraction = max(0.05, min(1.0, float(capital_fraction or 1.0)))
    if cfg["mode"] == "shadow":
        return "shadow", "mode=shadow, ordin nesimulat in MT5", None

    if not mt5.symbol_select(symbol, True):
        return "failed", f"symbol_select({symbol}) a esuat", None
    tick = mt5.symbol_info_tick(symbol)
    info = mt5.symbol_info(symbol)
    if tick is None or info is None:
        return "failed", "tick/info indisponibil", None

    long_ = d["action"] == "OPEN_LONG"
    comment = f"{cfg['comment_prefix']}-{decision_id}"

    def _margin_ok(lots: float, price_ref: float) -> str | None:
        """Rail: marja ordinului sa nu depaseasca 40% din marja libera."""
        acc = mt5.account_info()
        otype = mt5.ORDER_TYPE_BUY if long_ else mt5.ORDER_TYPE_SELL
        need = mt5.order_calc_margin(otype, symbol, lots, price_ref)
        if acc is None or need is None:
            return None   # nu putem calcula — lasam brokerul sa decida
        if need > acc.margin_free * 0.40:
            return (f"marja necesara ${need:.0f} > 40% din marja libera "
                    f"${acc.margin_free:.0f}")
        return None

    if d["order_type"] == "market":
        entry = tick.ask if long_ else tick.bid
        # normalizeaza SL/TP la precizia simbolului (evita 10015 pe precizie)
        d["sl"] = round(d["sl"], info.digits)
        d["tp"] = round(d["tp"], info.digits)
        if fixed_lots:
            lots, risk_usd = snap_fixed_lots(symbol, fixed_lots, entry, d["sl"])
        else:
            lots, risk_usd = calc_lots(symbol, entry, d["sl"],
                                       capital_base(cfg) * capital_fraction, d["risk_pct"])
        if lots <= 0:
            return "rejected", "lot calculat 0 (capital insuficient?)", None
        m_err = _margin_ok(lots, entry)
        if m_err:
            return "rejected", m_err, None
        req = {
            "action":    mt5.TRADE_ACTION_DEAL,
            "symbol":    symbol,
            "volume":    lots,
            "type":      mt5.ORDER_TYPE_BUY if long_ else mt5.ORDER_TYPE_SELL,
            "price":     entry,
            "sl":        d["sl"],
            "tp":        d["tp"],
            "deviation": 20,
            "magic":     cfg["magic"],
            "comment":   comment,
            "type_time": mt5.ORDER_TIME_GTC,
        }
    else:
        # Sanitizeaza intrarea STOP fata de pretul LIVE (nu cel din snapshot).
        # Buffer minim REAL chiar si cand brokerul are stops_level=0 (ICMarkets):
        # cel putin 2x spread-ul curent si un plafon absolut de 10 puncte.
        ref    = tick.ask if long_ else tick.bid
        spread = abs(tick.ask - tick.bid)
        buf    = max((info.trade_stops_level or 0) * info.point,
                     2 * spread, 10 * info.point)
        n_entry, n_sl, n_tp, skip = adjust_stop_bracket(
            d["entry"], d["sl"], d["tp"], ref, long_, buf, info.digits)
        if skip:
            return "rejected", skip, None
        if n_entry != d["entry"]:
            log.info("STOP %s intrare ajustata la piata: %s -> %s (ref %s, buf %s)",
                     symbol, d["entry"], n_entry, ref, round(buf, info.digits))
        d["entry"], d["sl"], d["tp"] = n_entry, n_sl, n_tp

        if fixed_lots:
            lots, risk_usd = snap_fixed_lots(symbol, fixed_lots, d["entry"], d["sl"])
        else:
            lots, risk_usd = calc_lots(symbol, d["entry"], d["sl"],
                                       capital_base(cfg) * capital_fraction, d["risk_pct"])
        if lots <= 0:
            return "rejected", "lot calculat 0 (capital insuficient?)", None
        m_err = _margin_ok(lots, d["entry"])
        if m_err:
            return "rejected", m_err, None
        req = {
            "action":  mt5.TRADE_ACTION_PENDING,
            "symbol":  symbol,
            "volume":  lots,
            "type":    mt5.ORDER_TYPE_BUY_STOP if long_ else mt5.ORDER_TYPE_SELL_STOP,
            "price":   d["entry"],
            "sl":      d["sl"],
            "tp":      d["tp"],
            "magic":   cfg["magic"],
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
        }

    res = _send_with_fillings(req)
    if res is None:
        return "failed", f"order_send None: {mt5.last_error()}", None
    if res.retcode == mt5.TRADE_RETCODE_DONE:
        ticket = res.order or res.deal
        log.info("ORDIN PLASAT %s %s lots=%.2f risk=$%s ticket=%s",
                 d["action"], symbol, lots, risk_usd, ticket)
        return "placed", f"lots={lots} risk_usd={risk_usd}", int(ticket)
    return "failed", f"retcode={res.retcode} {res.comment}", None


def close_position(symbol: str, cfg: dict) -> tuple[str, str]:
    """Inchide pozitia AI de pe symbol (daca exista)."""
    if cfg["mode"] == "shadow":
        return "shadow", "mode=shadow"
    pos = open_position_for(symbol, cfg["magic"])
    if pos is None:
        return "skipped", "nicio pozitie AI deschisa pe simbol"
    tick = mt5.symbol_info_tick(symbol)
    long_ = pos.type == mt5.POSITION_TYPE_BUY
    req = {
        "action":    mt5.TRADE_ACTION_DEAL,
        "symbol":    symbol,
        "volume":    pos.volume,
        "type":      mt5.ORDER_TYPE_SELL if long_ else mt5.ORDER_TYPE_BUY,
        "position":  pos.ticket,
        "price":     tick.bid if long_ else tick.ask,
        "deviation": 20,
        "magic":     cfg["magic"],
        "comment":   f"{cfg['comment_prefix']}-close",
        "type_time": mt5.ORDER_TIME_GTC,
    }
    res = _send_with_fillings(req)
    if res is not None and res.retcode == mt5.TRADE_RETCODE_DONE:
        return "placed", f"pozitie {pos.ticket} inchisa"
    return "failed", f"retcode={getattr(res, 'retcode', None)}"


def cancel_order(ticket: int, cfg: dict) -> bool:
    res = mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": ticket})
    return res is not None and res.retcode == mt5.TRADE_RETCODE_DONE


# ── Urmarire outcomes ────────────────────────────────────────────────────────

def check_decision_outcome(dec: dict, cfg: dict,
                           positions: list | None = None,
                           pending: list | None = None) -> dict | None:
    """
    Verifica o decizie 'placed' fara outcome. Returneaza dict outcome sau None
    daca e inca activa. Foloseste pattern-ul hedging-safe: order → position_id →
    deals (acelasi ca in signal_generator).

    `positions`/`pending`: listele deja citite din MT5 (magic-filtered). Cand mai
    multe decizii se verifica in aceeasi iteratie, apelantul le citeste O SINGURA
    DATA si le paseaza — altfel fiecare decizie ar reface `positions_get`/`orders_get`
    (N interogari MT5 identice per bara). Daca lipsesc, le citeste el (compat).
    """
    ticket = dec.get("ticket")
    if not ticket:
        return None
    if pending is None:
        pending = ai_pending_orders(cfg["magic"])
    if positions is None:
        positions = ai_positions(cfg["magic"])

    # inca pending?
    if any(o.ticket == ticket for o in pending):
        # expira ordinele stop neactivate dupa decision_valid_bars
        try:
            placed = datetime.fromisoformat(dec["ts"])
            age_min = (datetime.now() - placed).total_seconds() / 60
            if age_min > cfg["decision_valid_bars"] * cfg["bar_minutes"]:
                if cancel_order(ticket, cfg):
                    return {"status": "expired", "exit_price": None,
                            "result_r": 0.0, "pnl_usd": 0.0}
        except Exception:
            pass
        return None

    # pozitie deschisa?
    if any(p.ticket == ticket or p.identifier == ticket for p in positions):
        return None

    # cauta in istorie: order → position_id → deals
    orders = mt5.history_orders_get(ticket=ticket)
    if not orders:
        return None
    order = orders[0]
    if order.state in (2, 5, 6):   # CANCELED / REJECTED / EXPIRED
        return {"status": "cancelled", "exit_price": None, "result_r": 0.0, "pnl_usd": 0.0}
    pos_id = order.position_id
    if not pos_id:
        return None
    deals = mt5.history_deals_get(position=pos_id)
    if not deals:
        return None
    exit_deals = [dl for dl in deals if dl.entry == mt5.DEAL_ENTRY_OUT]
    if not exit_deals:
        return None   # pozitia exista dar nu s-a inchis inca

    pnl = sum(dl.profit + dl.commission + dl.swap for dl in deals)
    exit_price = exit_deals[-1].price
    entry, sl = dec.get("entry"), dec.get("sl")
    result_r = None
    if entry and sl and abs(entry - sl) > 0:
        direction = 1 if dec["action"] == "OPEN_LONG" else -1
        result_r = round(direction * (exit_price - entry) / abs(entry - sl), 3)
    status = "TP" if (result_r or 0) > 0.2 else ("SL" if (result_r or 0) < -0.2 else "closed")
    return {"status": status, "exit_price": float(exit_price),
            "result_r": result_r, "pnl_usd": round(float(pnl), 2)}
