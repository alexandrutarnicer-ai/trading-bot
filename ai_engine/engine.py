"""
ai_engine.engine — bucla principala a motorului AI.

Per bara M15:
  1. actualizeaza outcomes pentru deciziile plasate (TP/SL/expirare) → ledger + Telegram
  2. pentru fiecare piata: snapshot (gratuit) → trigger? → consiliu AI → decizie
  3. valideaza decizia pe rails → executa (demo) → ledger + Telegram

Fail-safe peste tot: orice eroare pe o piata nu opreste bucla; orice eroare LLM
inseamna WAIT; executorul refuza non-demo.
"""

from __future__ import annotations

import os
import json
import time
import logging
from datetime import datetime, timedelta

from adapters.mt5_source import Mt5DataSource
from ai_engine.config import load_config, save_default_config, load_keys, AI_DATA
from ai_engine.providers import ProviderRegistry
from ai_engine.ledger import Ledger
from ai_engine import perception, triggers, council, executor
from tz_helper import now_local

log = logging.getLogger("ai_engine")

STATUS_PATH = os.path.join(AI_DATA, "status.json")
_last_errors: list[dict] = []   # ring buffer pentru UI (max 20)


def _record_error(where: str, err: str) -> None:
    _last_errors.append({"ts": datetime.now().isoformat(timespec="seconds"),
                         "where": where, "error": err[:300]})
    del _last_errors[:-20]


def _write_status(running: bool, cfg: dict | None = None,
                  scorecard: dict | None = None, equity: float | None = None,
                  providers_health: dict | None = None) -> None:
    """Heartbeat pentru UI — scris la fiecare iteratie si la start/stop."""
    try:
        st = {
            "running":    running,
            "pid":        os.getpid() if running else None,
            "ts":         datetime.now().isoformat(timespec="seconds"),
            "mode":       cfg.get("mode") if cfg else None,
            "model":      cfg.get("model") if cfg else None,
            "markets":    cfg.get("markets") if cfg else None,
            "equity":     equity,
            "scorecard":  scorecard,
            "last_errors": _last_errors,
            "providers":  providers_health or {},
            "role_assignments": (cfg or {}).get("role_assignments"),
        }
        with open(STATUS_PATH, "w", encoding="utf-8") as f:
            json.dump(st, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


def _setup_logging() -> None:
    os.makedirs(AI_DATA, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(os.path.join(AI_DATA, "engine.log"), encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def _send_telegram(text: str) -> None:
    """Best-effort, reuses helperul API (care logheaza si in Notificari)."""
    try:
        from api.telegram import send_message
        import threading
        threading.Thread(target=send_message, args=(text,), daemon=True).start()
    except Exception:
        pass


def _sleep_to_next_bar(bar_minutes: int) -> None:
    now = datetime.now()
    minute = (now.minute // bar_minutes + 1) * bar_minutes
    nxt = now.replace(second=5, microsecond=0) + timedelta(minutes=minute - now.minute)
    time.sleep(max(5.0, (nxt - now).total_seconds()))


def _update_outcomes(ledger: Ledger, cfg: dict) -> None:
    for dec in ledger.open_decisions():
        try:
            out = executor.check_decision_outcome(dec, cfg)
        except Exception as e:
            log.warning("outcome check %s: %s", dec["symbol"], e)
            continue
        if out is None:
            continue
        ledger.add_outcome(dec["id"], dec["symbol"], out["status"],
                           out["exit_price"], out["result_r"], out["pnl_usd"])
        r_str = f"{out['result_r']:+.2f}R" if out["result_r"] is not None else "?R"
        pnl_str = f"{out['pnl_usd']:+.2f}$" if out["pnl_usd"] is not None else ""
        log.info("OUTCOME %s #%s: %s %s %s", dec["symbol"], dec["id"],
                 out["status"], r_str, pnl_str)
        if out["status"] not in ("expired", "cancelled"):
            _send_telegram(f"🤖 AI Engine — {dec['symbol']} {out['status']}: "
                           f"{r_str} {pnl_str}\n(decizia #{dec['id']})")


def _weekend_guard(symbol: str, cfg: dict) -> bool:
    """
    Automatizarea de weekend pentru pietele FX/indici (cripto exceptat).

    Daca piata `symbol` e inchisa pentru weekend (Vineri de la weekend_close_hour,
    tot Sambata + Duminica — ora RO), atunci:
      - inchide pozitia AI deschisa pe acel simbol (nu o lasa sa treaca gap-ul),
      - anuleaza ordinele pending AI pe acel simbol,
      - intoarce True -> motorul SARE consiliul pentru simbol (nu deschide nimic).

    Deschiderea se reia AUTOMAT Luni: guard-ul intoarce iar False, iar consiliul
    isi reia analiza normala. Cripto (XRPUSD, BTCUSD...) nu e afectat niciodata.
    Outcome-urile inchiderii/anularii sunt inregistrate de _update_outcomes la
    urmatoarea iteratie (pattern-ul standard order->position->deals).
    """
    if not cfg.get("weekend_close_enabled", True):
        return False
    now_ro = now_local()
    if not executor.is_market_weekend_closed(symbol, now_ro, cfg.get("weekend_close_hour", 22)):
        return False

    # Piata inchisa pentru weekend -> curata expunerea AI pe acest simbol.
    if executor.open_position_for(symbol, cfg["magic"]) is not None:
        status, detail = executor.close_position(symbol, cfg)
        if status == "placed":
            log.info("WEEKEND %s: pozitie inchisa inainte de weekend (%s)", symbol, detail)
            _send_telegram(f"🤖📅 AI Engine — {symbol}: pozitie inchisa pentru weekend "
                           f"(piata FX se inchide, se redeschide Luni).")
        elif status == "failed":
            log.warning("WEEKEND %s: inchidere esuata (%s) — reincerc la bara urmatoare",
                        symbol, detail)
    for o in executor.ai_pending_orders(cfg["magic"]):
        if o.symbol == symbol and executor.cancel_order(o.ticket, cfg):
            log.info("WEEKEND %s: ordin pending #%s anulat inainte de weekend", symbol, o.ticket)
            _send_telegram(f"🤖📅 AI Engine — {symbol} #{o.ticket}: ordin pending anulat pentru weekend.")
    return True


def _process_market(symbol: str, src: Mt5DataSource, registry: ProviderRegistry,
                    ledger: Ledger, cfg: dict, prev_snapshots: dict) -> None:
    snap = perception.build_snapshot(src, symbol)
    prev = prev_snapshots.get(symbol)
    prev_snapshots[symbol] = snap

    pos = executor.open_position_for(symbol, cfg["magic"])
    trig = triggers.evaluate(snap, prev, ledger.last_council_ts(symbol),
                             pos is not None, cfg)
    if trig is None:
        return

    log.info("CONSILIU pe %s — trigger: %s", symbol, trig)
    snap_id = ledger.add_snapshot(symbol, snap)
    briefing = perception.render_text(snap)

    today = datetime.now().date().isoformat()
    n_open = len(executor.ai_positions(cfg["magic"]))
    # Expunere ANGAJATA = pozitii deschise + ordine pending (fiecare stop poate
    # deveni pozitie). Rail-ul foloseste asta ca sa nu depaseasca max_open_positions
    # la cold-start, cand heartbeat-ul convoaca toate pietele deodata (ledger gol).
    n_committed = n_open + len(executor.ai_pending_orders(cfg["magic"]))
    desk_state = {
        "open_positions": n_open,
        "committed": n_committed,
        "daily_r": ledger.daily_loss_R(today),
        "trigger": trig,
        "open_pos_desc": (
            f"{'LONG' if pos.type == 0 else 'SHORT'} {pos.volume} lots @ {pos.price_open}, "
            f"floating {pos.profit:+.2f}$" if pos else "none"),
    }

    decision, transcript, dur = council.convene(registry, briefing, desk_state, cfg)
    council_id = ledger.add_council(symbol, trig, snap_id, transcript, dur)
    log.info("DECIZIE %s: %s (conf %s%%) — %s",
             symbol, decision["action"], decision["confidence"],
             decision["rationale"][:160])

    # ── executie ──
    if decision["action"] == "WAIT":
        ledger.add_decision(symbol, council_id, decision, "skipped", "WAIT")
        return

    if decision["action"] == "CLOSE":
        dec_id = ledger.add_decision(symbol, council_id, decision, "pending")
        status, detail = executor.close_position(symbol, cfg)
        ledger.set_exec(dec_id, status, detail)
        if status == "placed":
            _send_telegram(f"🤖 AI Engine — CLOSE {symbol}\nMotiv: {decision['rationale'][:300]}")
        return

    # OPEN_LONG / OPEN_SHORT — rail-ul foloseste expunerea ANGAJATA (pozitii+pending)
    reason = executor.validate_decision(decision, snap, cfg, n_committed,
                                        desk_state["daily_r"])
    if reason:
        ledger.add_decision(symbol, council_id, decision, "rejected", reason)
        log.info("RESPINS %s: %s", symbol, reason)
        return

    dec_id = ledger.add_decision(symbol, council_id, decision, "pending")
    status, detail, ticket = executor.place(decision, snap, cfg, dec_id)
    entry_used = decision.get("entry") if decision["order_type"] == "stop" else snap["price"]
    ledger.set_exec(dec_id, status, detail, ticket,
                    entry=entry_used if status == "placed" else None)
    log.info("EXECUTIE %s: %s (%s)", symbol, status, detail)
    if status == "placed":
        dir_ro = "LONG" if decision["action"] == "OPEN_LONG" else "SHORT"
        _send_telegram(
            f"🤖 AI Engine — {dir_ro} {symbol} ({decision['order_type']})\n"
            f"Entry {entry_used} | SL {decision['sl']} | TP {decision['tp']} | "
            f"risc {decision['risk_pct'] * 100:.2f}%\n"
            f"Încredere {decision['confidence']}% | {detail}\n"
            f"Motiv: {decision['rationale'][:400]}")


def run() -> None:
    _setup_logging()
    save_default_config()
    cfg = load_config()

    log.info("AI Engine v0.3 — mode=%s markets=%s surse=%s roluri=%s",
             cfg["mode"], ",".join(cfg["markets"]),
             ",".join(cfg["providers"].keys()), cfg["role_assignments"])

    registry = ProviderRegistry(cfg["providers"], load_keys())
    if not registry.default_available():
        raise RuntimeError(
            "Sursa default (Ollama) nu e disponibila — modelul "
            f"{cfg['providers']['ollama'].get('model')} lipseste sau serverul e oprit. "
            "Ruleaza: ollama pull <model> / porneste Ollama. "
            "(Ollama e safety-net-ul failover-ului; celelalte surse sunt optionale.)")

    acc = executor.connect()     # impune DEMO — arunca RuntimeError altfel
    log.info("MT5 conectat: cont %s (%s) equity %.2f %s — DEMO verificat",
             acc.login, acc.server, acc.equity, acc.currency)

    src = Mt5DataSource(n_bars=2000)
    src.connect()

    # PID file — permite oprirea curata din exterior
    pid_path = os.path.join(AI_DATA, "ai_engine.pid")
    with open(pid_path, "w") as f:
        f.write(str(os.getpid()))

    ledger = Ledger()
    prev_snapshots: dict = {}
    _write_status(True, cfg, ledger.scorecard(), float(acc.equity))
    _send_telegram(f"🤖 AI Engine pornit — mode={cfg['mode']}, model={cfg['model']}, "
                   f"piete: {', '.join(cfg['markets'])}")

    try:
        while True:
            # Hot-reload: config + asignari de rol + registru surse (pastreaza
            # sanatatea surselor neschimbate). Schimbarile din UI se aplica
            # de la iteratia urmatoare, fara restart de motor.
            try:
                cfg = load_config()
                registry.refresh(cfg["providers"], load_keys())
            except Exception as e:
                log.error("config reload: %s", e)
                _record_error("config_reload", str(e))

            try:
                _update_outcomes(ledger, cfg)
            except Exception as e:
                log.error("outcomes: %s", e)
                _record_error("outcomes", str(e))

            failures = 0
            processed = 0
            for symbol in cfg["markets"]:
                try:
                    # Weekend: FX inchis -> curata expunerea + sare consiliul (cripto ruleaza).
                    if _weekend_guard(symbol, cfg):
                        continue
                    processed += 1
                    _process_market(symbol, src, registry, ledger, cfg, prev_snapshots)
                except Exception as e:
                    failures += 1
                    log.error("piata %s: %s: %s", symbol, type(e).__name__, e)
                    _record_error(symbol, f"{type(e).__name__}: {e}")

            # Toate pietele PROCESATE au esuat → probabil MT5 cazut. Reconectare.
            # (pietele sarite pentru weekend nu se numara — altfel n-am reconecta
            #  niciodata intr-un weekend cu doar FX in lista.)
            if processed > 0 and failures == processed:
                log.warning("Toate pietele au esuat — reconectez MT5...")
                _send_telegram("🤖 AI Engine — conexiune MT5 pierduta, reconectez...")
                try:
                    src.disconnect()
                except Exception:
                    pass
                try:
                    executor.connect()
                    src.connect()
                    log.info("MT5 reconectat.")
                except Exception as e:
                    log.error("Reconectare esuata: %s — reincerc la bara urmatoare", e)
                    _record_error("mt5_reconnect", str(e))

            sc = ledger.scorecard()
            log.info("scorecard: %s", sc)
            _write_status(True, cfg, sc, executor.equity() or None,
                          providers_health=registry.snapshot())
            _sleep_to_next_bar(cfg["bar_minutes"])
    except KeyboardInterrupt:
        log.info("Oprire ceruta (Ctrl+C).")
    finally:
        _write_status(False, cfg)
        _send_telegram("🤖 AI Engine oprit.")
        try:
            os.remove(pid_path)
        except OSError:
            pass
        ledger.close()
        src.disconnect()
