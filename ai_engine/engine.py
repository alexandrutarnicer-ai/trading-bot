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
import ctypes
import logging
from datetime import datetime, timedelta

from adapters.mt5_source import Mt5DataSource
from ai_engine.config import (load_config, save_default_config, load_keys,
                              market_cfg, isolated_markets, AI_DATA)
from ai_engine.providers import ProviderRegistry
from ai_engine.ledger import Ledger
from ai_engine import perception, triggers, council, executor, orchestrator
from tz_helper import now_local

log = logging.getLogger("ai_engine")

STATUS_PATH = os.path.join(AI_DATA, "status.json")
_last_errors: list[dict] = []   # ring buffer pentru UI (max 20)


def _record_error(where: str, err: str) -> None:
    _last_errors.append({"ts": datetime.now().isoformat(timespec="seconds"),
                         "where": where, "error": err[:300]})
    del _last_errors[:-20]


# ── Guard de instanta unica ──────────────────────────────────────────────────
# Motorul plaseaza ordine pe magic 770015. DOUA instante = expunere dublata SI
# pozitii care se calca (fiecare vede/inchide pozitiile celeilalte prin acelasi
# magic) + contentie pe ledger-ul SQLite. run() scria PID-ul fara sa-l verifice,
# deci un `python -m ai_engine` manual / dublu-click pe .bat / task de autostart
# suprapus peste o instanta vie pornea o a doua (observat: 3 instante simultan).
# Guard: mutex Windows NUMIT (atomic, eliberat automat de OS chiar si la taskkill)
# — Global daca privilegiile permit (cross-sesiune), altfel Local (per-sesiune,
# prinde cazul comun al dublurilor din aceeasi sesiune) + verificare PID din
# fisier ca plasa cross-sesiune cand n-avem Global.
_ERROR_ALREADY_EXISTS = 183
_MUTEX_NAMES = (r"Global\TradingBot_AIEngine_SingleInstance",
                r"Local\TradingBot_AIEngine_SingleInstance")
_single_instance_handle = None


def _pid_alive(pid: int) -> bool:
    try:
        STILL_ACTIVE = 259
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(h)
        return bool(ok) and code.value == STILL_ACTIVE
    except Exception:
        return False


def _other_engine_pid(pid_path: str) -> int | None:
    """PID-ul unei alte instante vii din fisierul PID (cross-sesiune), sau None."""
    try:
        with open(pid_path) as f:
            pid = int(f.read().strip())
    except (OSError, ValueError):
        return None
    return pid if (pid != os.getpid() and _pid_alive(pid)) else None


def _acquire_single_instance(names: tuple | None = None) -> tuple[bool, str]:
    """
    Obtine lock-ul de instanta unica via mutex Windows numit.
    Returneaza (True, name) daca suntem singura instanta; (False, name) daca alta
    o detine deja. Pe non-Windows nu blocheaza (motorul e Windows-only).
    `names` permite un nume alternativ (folosit de teste, sa nu se cioc­neasca cu
    motorul real care ruleaza).
    """
    global _single_instance_handle
    if os.name != "nt":
        return True, "(non-windows)"
    try:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateMutexW.restype = ctypes.c_void_p
        k32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    except Exception:
        return True, "(mutex indisponibil)"
    for name in (names or _MUTEX_NAMES):
        handle = k32.CreateMutexW(None, False, name)
        err = ctypes.get_last_error()
        if not handle:
            continue   # namespace refuzat (privilegii) → incearca Local
        if err == _ERROR_ALREADY_EXISTS:
            k32.CloseHandle(ctypes.c_void_p(handle))
            return False, name
        _single_instance_handle = handle   # tine handle-ul viu pe durata procesului
        return True, name
    return True, "(mutex indisponibil — fail-open)"


def _release_single_instance() -> None:
    global _single_instance_handle
    if _single_instance_handle:
        try:
            ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(_single_instance_handle))
        except Exception:
            pass
        _single_instance_handle = None


def _write_status(running: bool, cfg: dict | None = None,
                  scorecard: dict | None = None, equity: float | None = None,
                  providers_health: dict | None = None,
                  extra: dict | None = None) -> None:
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
        if extra:
            st.update(extra)   # scorecard_by_symbol, isolated_markets etc.
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
    open_decs = ledger.open_decisions()
    if not open_decs:
        return   # nimic de verificat → zero interogari MT5
    # Citim pozitiile + ordinele O SINGURA DATA pentru TOATE deciziile (nu N ori).
    # Snapshot consistent: toate deciziile evaluate pe aceeasi stare de piata.
    positions = executor.ai_positions(cfg["magic"])
    pending   = executor.ai_pending_orders(cfg["magic"])
    for dec in open_decs:
        try:
            out = executor.check_decision_outcome(dec, cfg, positions, pending)
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


# Stare monitor surse AI (o singura notificare per tranzitie jos/revenit).
_all_sources_down = [False]


def _monitor_sources_health(registry) -> None:
    """
    Alerta Telegram cand TOATE sursele AI devin indisponibile (quota/picate/pauza),
    inclusiv Ollama. Fara nicio sursa, consiliul da WAIT la tot — operatorul trebuie
    instiintat imediat. Notifica o singura data per tranzitie si la revenire.
    """
    try:
        usable = registry.usable_sources()
    except Exception:
        return
    if not usable and not _all_sources_down[0]:
        _all_sources_down[0] = True
        snap = {}
        try:
            snap = registry.snapshot()
        except Exception:
            pass
        detail = ", ".join(f"{n}:{h.get('status','?')}" for n, h in snap.items()) or "?"
        log.error("TOATE sursele AI indisponibile — deciziile devin WAIT. [%s]", detail)
        _send_telegram(
            "🛑 <b>AI Engine — TOATE sursele AI indisponibile!</b>\n"
            f"Nicio sursă sănătoasă (quota epuizată / picate / Ollama defect): {detail}\n"
            "Consiliul dă WAIT la tot până revine cel puțin o sursă. "
            "Verifică din tab-ul AI Engine → «Testează sursele».")
    elif usable and _all_sources_down[0]:
        _all_sources_down[0] = False
        _send_telegram(
            "✅ <b>AI Engine — sursele AI și-au revenit</b>\n"
            f"Disponibile acum: {', '.join(usable)}. Deciziile se reiau normal.")


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


def _market_limits_text(symbol: str, m: dict, cfg: dict,
                        daily_r: float, trades_today: int) -> str:
    """
    Blocul "DESK LIMITS" adaugat la briefing cand piata are override-uri — asa
    consiliul PRIMESTE limitele (banda RR permisa, stop zilnic ramas, ordine
    ramase azi) si proiecteaza trade-ul IN interiorul lor, nu orbeste. Piata
    fara override → briefing identic byte-cu-byte cu inainte (zero drift LLM).
    """
    lines = [f"DESK LIMITS FOR {symbol} (hard rails — enforced by code, design within them):"]
    if m["capital_fraction"] != 1.0:
        lines.append(f"- capital allocated to this market: {m['capital_fraction'] * 100:.0f}% of account equity")
    if m["risk_pct"] is not None:
        lines.append(f"- max risk per trade on this market: {m['risk_pct'] * 100:.2f}%")
    if m["max_rr"] is not None:
        lines.append(f"- reward/risk must be between {cfg['min_rr']:.1f} and {m['max_rr']:.1f} "
                     "(a TP beyond the max is clamped by the desk)")
    if m["max_daily_loss_R"] is not None:
        lines.append(f"- daily loss stop for THIS market: -{m['max_daily_loss_R']:.1f}R "
                     f"(realized today on it: {daily_r:+.2f}R)")
    if m["max_trades_per_day"] is not None:
        left = max(0, int(m["max_trades_per_day"]) - trades_today)
        lines.append(f"- max orders per day on this market: {int(m['max_trades_per_day'])} "
                     f"(placed today: {trades_today}, remaining: {left})")
    if m.get("fixed_lots") is not None:
        lines.append(f"- position size on this market is FIXED at {m['fixed_lots']} lots "
                     "(the desk ignores risk-based sizing here; risk_pct is informational)")
    return "\n".join(lines)


def _process_market(symbol: str, src: Mt5DataSource, registry: ProviderRegistry,
                    ledger: Ledger, cfg: dict, prev_snapshots: dict) -> None:
    snap = perception.build_snapshot(src, symbol)
    prev = prev_snapshots.get(symbol)
    prev_snapshots[symbol] = snap

    # O SINGURA citire de pozitii, refolosita pentru trigger SI pentru expunere
    # (aceeasi stare, la microsecunde distanta, inainte de consiliu) — evita al
    # doilea positions_get identic per piata triggerata.
    positions = executor.ai_positions(cfg["magic"])
    pos = next((p for p in positions if p.symbol == symbol), None)
    trig = triggers.evaluate(snap, prev, ledger.last_council_ts(symbol),
                             pos is not None, cfg)
    if trig is None:
        return

    log.info("CONSILIU pe %s — trigger: %s", symbol, trig)
    snap_id = ledger.add_snapshot(symbol, snap)
    briefing = perception.render_text(snap)

    today = datetime.now().date().isoformat()
    n_open = len(positions)
    # Expunere ANGAJATA = pozitii deschise + ordine pending (fiecare stop poate
    # deveni pozitie). Rail-ul foloseste asta ca sa nu depaseasca max_open_positions
    # la cold-start, cand heartbeat-ul convoaca toate pietele deodata (ledger gol).
    pending_orders = executor.ai_pending_orders(cfg["magic"])
    n_committed = n_open + len(pending_orders)
    # Expunere pe ACEST simbol: pozitie deschisa SAU ordin pending pe el. Motorul
    # nu face pyramiding — blocam un al doilea ordin pe acelasi simbol (defense-in-
    # depth peste guard-ul de instanta unica: nici o singura instanta nu stivuieste).
    symbol_committed = (pos is not None) or any(o.symbol == symbol for o in pending_orders)
    desk_state = {
        "open_positions": n_open,
        "committed": n_committed,
        "daily_r": ledger.daily_loss_R(today),
        "trigger": trig,
        "open_pos_desc": (
            f"{'LONG' if pos.type == 0 else 'SHORT'} {pos.volume} lots @ {pos.price_open}, "
            f"floating {pos.profit:+.2f}$" if pos else "none"),
    }

    # ── Config PER PIATA (market_overrides) ──
    # Piata fara override: mcfg = pure default-uri, briefing neschimbat, zero
    # interogari suplimentare → comportament identic cu inainte.
    mcfg = market_cfg(cfg, symbol)
    m_daily_r, m_trades = 0.0, 0
    if mcfg["_has_overrides"]:
        m_daily_r = ledger.daily_loss_R(today, symbol)
        m_trades  = ledger.placed_count(today, symbol)
        # Consiliul PRIMESTE limitele pietei in briefing — proiecteaza inauntrul lor.
        briefing += "\n\n" + _market_limits_text(symbol, mcfg, cfg, m_daily_r, m_trades)

    # Consens multi-council: consiliul primar propune, revizorii (daca exista)
    # confirma; executia e gate-uita de consens. Fara surse secundare/tertiare in
    # config → un singur convene, identic cu comportamentul de dinainte.
    decision, bundle, dur = orchestrator.decide(registry, symbol, snap, briefing,
                                                desk_state, cfg)
    # transcriptul stocat = rolurile consiliului primar (compat UI) + eventualul
    # bloc de consens/revizori sub chei cu prefix _ (nu strica rendarea existenta).
    transcript = dict(bundle.get("primary") or {})
    if bundle.get("consensus"):
        transcript["_consensus"] = bundle["consensus"]
        transcript["_reviewers"] = bundle["reviewers"]
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

    # ── Aplicarea limitelor PER PIATA pe decizia OPEN (inainte de rails) ──
    if mcfg["_has_overrides"]:
        # cap de risc per piata (consiliul poate cere mai putin, niciodata mai mult)
        if mcfg["risk_pct"] is not None and decision.get("risk_pct"):
            decision["risk_pct"] = min(decision["risk_pct"], mcfg["risk_pct"])
        # TP peste plafonul RR al pietei → adus la plafon (SL/directia raman)
        if council.clamp_tp_to_max_rr(decision, mcfg["max_rr"]):
            log.info("TP %s plafonat la max_rr=%.1f (limita pietei)", symbol, mcfg["max_rr"])

    # OPEN_LONG / OPEN_SHORT — rail-ul foloseste expunerea ANGAJATA (pozitii+pending)
    # + interdictia de pyramiding pe acelasi simbol + limitele per piata.
    market_state = None
    if mcfg["max_daily_loss_R"] is not None or mcfg["max_trades_per_day"] is not None:
        market_state = {"symbol": symbol, "daily_r": m_daily_r, "trades_today": m_trades,
                        "max_daily_loss_R": mcfg["max_daily_loss_R"],
                        "max_trades_per_day": mcfg["max_trades_per_day"]}
    # Pietele care ocupa deja sloturile (pentru mesajul de respingere clar cand
    # se atinge plafonul GLOBAL — altfel "expunere maxima pe USDCAD" pare per piata).
    committed_symbols = sorted({p.symbol for p in positions}
                               | {o.symbol for o in pending_orders})
    reason = executor.validate_decision(decision, snap, cfg, n_committed,
                                        desk_state["daily_r"],
                                        symbol_committed=symbol_committed,
                                        market_state=market_state,
                                        committed_symbols=committed_symbols)
    if reason:
        ledger.add_decision(symbol, council_id, decision, "rejected", reason)
        log.info("RESPINS %s: %s", symbol, reason)
        return

    dec_id = ledger.add_decision(symbol, council_id, decision, "pending")
    status, detail, ticket = executor.place(decision, snap, cfg, dec_id,
                                            capital_fraction=mcfg["capital_fraction"],
                                            fixed_lots=mcfg.get("fixed_lots"))
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

    # ── Guard de instanta unica (INAINTE de a atinge MT5/Ollama) ──
    # O a doua instanta ar dubla expunerea pe magic 770015. Verificam PRIMUL lucru.
    pid_path = os.path.join(AI_DATA, "ai_engine.pid")
    got_lock, lock_name = _acquire_single_instance()
    # Verificam SI fisierul PID, mereu: prinde o instanta care ruleaza cod vechi
    # (fara mutex) sau o instanta dintr-o alta sesiune cand n-avem mutex Global.
    # Fals-pozitivul de reutilizare PID e improbabil si esueaza in siguranta (refuz).
    other = _other_engine_pid(pid_path)
    if (not got_lock) or (other is not None):
        who = lock_name if not got_lock else f"PID {other}"
        log.error("Alt AI Engine ruleaza deja (%s) — NU pornesc a doua instanta "
                  "(as dubla expunerea pe magic %s).", who, cfg["magic"])
        _send_telegram("🤖⛔ AI Engine — pornirea unei A DOUA instante a fost BLOCATA "
                       f"({who} ruleaza deja). O singura instanta poate plasa ordine "
                       "pe magic 770015.")
        _release_single_instance()
        return
    with open(pid_path, "w") as f:
        f.write(str(os.getpid()))
    log.info("Instanta unica confirmata (lock: %s, PID %s).", lock_name, os.getpid())

    registry = ProviderRegistry(cfg["providers"], load_keys())
    if not registry.default_available():
        raise RuntimeError(
            "Sursa default (Ollama) nu e disponibila — modelul "
            f"{cfg['providers']['ollama'].get('model')} lipseste sau serverul e oprit. "
            "Ruleaza: ollama pull <model> / porneste Ollama. "
            "(Ollama e safety-net-ul failover-ului; celelalte surse sunt optionale.)")

    # Sonda PROFUNDA: Ollama poate raspunde la /api/tags (reachable) dar sa nu poata
    # RULA inferenta (runner llama-server lipsa/corupt) — un fals-pozitiv pe care
    # default_available() nu-l prinde. Nu oprim motorul (ramane sus, degradeaza
    # gratios pe surse cloud si se auto-repara dupa ce Ollama e reparat), dar
    # paginam operatorul CLAR, o singura data, la pornire.
    ok, detail = registry.default_probe()
    if not ok:
        log.error("SAFETY-NET Ollama DEFECT la pornire: %s", detail)
        _record_error("ollama_probe", detail)
        _send_telegram(
            "🛑 AI Engine — safety-net Ollama DEFECT la pornire.\n"
            f"{detail}\n"
            "Motorul ruleaza DEGRADAT (failover pe surse cloud daca sunt configurate + "
            "sanatoase; altfel toate deciziile devin WAIT). Repara Ollama: reinstaleaza "
            "de pe ollama.com/download. Diagnostic: python -m ai_engine.doctor")
    else:
        log.info("Ollama inferenta verificata OK (safety-net functional).")

    # impune DEMO by default; cont REAL doar cu deblocare explicita (live_guard)
    acc = executor.connect()
    log.info("MT5 conectat: cont %s (%s) equity %.2f %s — mod cont verificat",
             acc.login, acc.server, acc.equity, acc.currency)

    src = Mt5DataSource(n_bars=2000, component="ai_engine")
    src.connect()

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

            # Monitor sanatate surse AI: alerta imediata cand TOATE sursele sunt
            # indisponibile (quota epuizata / picate) — inclusiv safety-net-ul Ollama.
            # Fara nicio sursa, toate deciziile devin WAIT (fail-safe) → operatorul
            # trebuie instiintat. O singura notificare per tranzitie (jos/revenit).
            _monitor_sources_health(registry)

            try:
                _update_outcomes(ledger, cfg)
            except Exception as e:
                log.error("outcomes: %s", e)
                _record_error("outcomes", str(e))

            # Re-exporta trade-urile inchise in CSV-ul git-trackable (transfer PC↔laptop).
            # Fail-safe: orice eroare de export NU trebuie sa afecteze motorul.
            try:
                from ai_engine.export import export_closed_outcomes
                export_closed_outcomes()
            except Exception as e:
                log.debug("export ai_outcomes esuat (ignor): %s", e)

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

            # Pietele IZOLATE (market_overrides.isolated) nu intra in scorecard-ul
            # principal — datele lor raman separate, per piata (scorecard_by_symbol),
            # pana sunt promovate. Derivat din OVERRIDE-URI (nu din lista markets):
            # o piata izolata scoasa din urmarire ramane exclusa (istoricul ei nu
            # reintra pe tacute). Fara piete izolate → scorecard identic cu inainte.
            iso = isolated_markets(cfg)
            sc = ledger.scorecard(exclude_symbols=iso)
            log.info("scorecard: %s%s", sc, f" (izolate: {','.join(iso)})" if iso else "")
            _write_status(True, cfg, sc, executor.equity() or None,
                          providers_health=registry.snapshot(),
                          extra={"scorecard_by_symbol": ledger.scorecard_by_symbol(),
                                 "isolated_markets": iso})
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
        _release_single_instance()
        ledger.close()
        src.disconnect()
