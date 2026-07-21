"""
telegram_bridge.bridge — bucla principala (long-polling getUpdates).

Porneste manual:  python -m telegram_bridge
Proces STANDALONE. Nu importa botul/motorul in mod care le schimba starea; citeste
doar fisiere de stare + API-ul local. Singurul consumator de getUpdates din proiect.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time

from . import config, executors
from .telegram_io import TelegramClient, BridgeState
from .router import Router

log = logging.getLogger("telegram_bridge")


def _write_pid() -> None:
    try:
        with open(config.PID_PATH, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
    except Exception:
        pass


def _remove_pid() -> None:
    try:
        os.remove(config.PID_PATH)
    except OSError:
        pass


def _write_status(cfg: dict, running: bool, idle: bool = False,
                  last_msg_ts: float | None = None) -> None:
    """Heartbeat pentru UI/API — running, allow_writes, idle, ultima activitate."""
    try:
        st = {
            "running": running,
            "pid": os.getpid(),
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "allow_writes": bool(cfg.get("allow_writes")),
            "idle": idle,
            "last_message_ts": (time.strftime("%Y-%m-%dT%H:%M:%S",
                                              time.localtime(last_msg_ts))
                                if last_msg_ts else None),
            "level_ai": bool(cfg.get("level_ai_enabled")),
            "level_claude": bool(cfg.get("level_claude_enabled")),
            "claude_detected": executors.claude_binary(cfg) is not None,
            "copilot_enabled": bool(cfg.get("copilot_enabled")),
            "matrix_enabled": bool(cfg.get("matrix_enabled")),
        }
        tmp = config.STATUS_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(st, f, ensure_ascii=False, indent=1)
        os.replace(tmp, config.STATUS_PATH)
    except Exception:
        pass


def run_matrix(cfg: dict, state: BridgeState) -> None:
    """
    Al doilea canal (Matrix/Element) — thread separat, ACELASI Router ca Telegram.
    Complet izolat: orice esec aici (retea, config, homeserver picat) e prins si NU
    afecteaza canalul Telegram sau restul aplicatiei. Pornit doar daca matrix_ready.
    """
    from .matrix_io import MatrixClient
    hs    = (cfg.get("matrix_homeserver") or "").strip()
    room  = (cfg.get("matrix_room_id") or "").strip()
    token = config.load_matrix_token()
    if not (hs and room and token):
        return
    allowed = {str(u).strip() for u in (cfg.get("matrix_allowed_users") or []) if str(u).strip()}
    client = MatrixClient(hs, token, room)
    try:
        me = client.whoami()
        log.info("Matrix: conectat ca %s in camera %s", me, room)
    except Exception as e:
        log.error("Matrix: whoami esuat (%s) — canalul Matrix NU porneste "
                  "(Telegram ramane neafectat).", e)
        return

    router = Router(cfg, state, client, room)   # transport-agnostic (are .send compatibil)
    since = None
    try:
        since, _ = client.sync(None, 0)          # drenaj: nu procesa mesaje vechi
    except Exception as e:
        log.warning("Matrix: sync initial esuat (%s).", e)
    try:
        client.send(room, "🤖 Punte Matrix pornita — trimite /ajutor pentru comenzi.")
    except Exception:
        pass

    poll_ms = int(cfg.get("matrix_poll_timeout_s", 30) * 1000)
    _last_alert: dict[str, float] = {}
    log.info("Canal Matrix activ (poll %ds).", poll_ms // 1000)
    while True:
        try:
            since, msgs = client.sync(since, poll_ms)
        except Exception as e:
            log.warning("Matrix sync a esuat (%s) — reincerc in 10s.", e)
            time.sleep(10)
            continue
        for m in msgs:
            try:
                sender = m.get("sender", "")
                if allowed and sender not in allowed:
                    now = time.time()
                    if now - _last_alert.get(sender, 0) > 600:
                        _last_alert[sender] = now
                        log.warning("Matrix: mesaj NEAUTORIZAT de la %s ignorat.", sender)
                    continue
                if (time.time() - float(m.get("ts", 0))) > cfg.get("ignore_messages_older_than_s", 180):
                    continue
                router.handle(m.get("text", ""), None, None)
            except Exception:
                log.exception("Matrix: eroare la procesarea unui mesaj.")


def _guarded_matrix(cfg: dict, state: BridgeState) -> None:
    """Wrapper: orice exceptie din canalul Matrix e logata, NU propagata (izolare)."""
    try:
        run_matrix(cfg, state)
    except Exception:
        log.exception("Canal Matrix oprit de o eroare (Telegram ramane activ).")


def _setup_logging() -> None:
    os.makedirs(config.DATA_DIR, exist_ok=True)
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    handlers = [logging.StreamHandler(sys.stdout)]
    try:
        handlers.append(logging.FileHandler(config.LOG_PATH, encoding="utf-8"))
    except Exception:
        pass
    logging.basicConfig(level=logging.INFO, format=fmt, handlers=handlers)


def _startup_text(cfg: dict, ids: set[str]) -> str:
    bin_ok = executors.claude_binary(cfg) is not None
    lines = [
        "🤖 Punte Telegram PORNITA",
        f"Whitelist: {', '.join(sorted(ids)) or '(gol!)'}",
        f"Nivele: instant ✓ · ai {'✓' if cfg.get('level_ai_enabled') else '✗'} · "
        f"claude {'✓' if cfg.get('level_claude_enabled') else '✗'}",
        f"Claude CLI: {'detectat ✓' if bin_ok else 'NEGASIT ✗ (fallback pe API/surse AI)'}",
        f"Scriere cod: {'ACTIVATA ⚠️' if cfg.get('allow_writes') else 'dezactivata 🔒'}",
        f"Copilot: {'activat' if cfg.get('copilot_enabled') else 'dezactivat'}",
        "",
        "Trimite /ajutor pentru comenzi.",
    ]
    return "\n".join(lines)


def main() -> int:
    _setup_logging()
    cfg = config.load_config()
    config.save_default_config()   # scrie un config.json de exemplu la prima rulare

    if not cfg.get("enabled", True):
        log.info("Puntea e dezactivata (enabled=false). Ies.")
        return 0

    token, owner_chat = config.load_credentials()
    if not token:
        log.error("Lipseste token-ul Telegram (data/telegram_config.json). Ies.")
        return 2

    ids = config.allowed_ids(cfg)
    if not ids:
        log.error("Whitelist gol si niciun chat_id in telegram_config.json. Ies "
                  "(refuz sa ascult de oricine).")
        return 2

    tg = TelegramClient(token)
    state = BridgeState()
    _write_pid()
    _write_status(cfg, running=True)

    # Drenaj backlog la prima rulare: nu executa comenzi vechi acumulate in Telegram.
    if state.offset == 0:
        try:
            pend = tg.get_updates(0, 0)
            if pend:
                state.offset = pend[-1]["update_id"] + 1
                state.save()
                log.info("Am ignorat %d mesaje din backlog la pornire.", len(pend))
        except RuntimeError:
            pass
        except Exception as e:
            log.warning("Drenaj backlog esuat: %s", e)

    # cate un router per chat autorizat (raspunde in chat-ul din care vine mesajul)
    routers: dict[str, Router] = {}
    def router_for(chat_id: str) -> Router:
        if chat_id not in routers:
            routers[chat_id] = Router(cfg, state, tg, chat_id)
        return routers[chat_id]

    # anunt de pornire catre proprietar
    try:
        tg.send(owner_chat or sorted(ids)[0], _startup_text(cfg, ids))
    except Exception:
        pass

    # Al doilea canal Matrix (optional) — thread separat, izolat. Un esec aici nu
    # atinge Telegram-ul (thread daemon, tot corpul in try/except).
    if config.matrix_ready(cfg):
        threading.Thread(target=lambda: _guarded_matrix(cfg, state),
                         daemon=True, name="MatrixBridge").start()
        log.info("Canal Matrix: pornit in thread separat.")

    log.info("Punte pornita. Whitelist=%s offset=%d", sorted(ids), state.offset)

    _last_alert: dict[str, float] = {}
    conflict_strikes = 0
    last_activity = time.time()   # ultima activitate (mesaj autorizat)
    idle_marked = False           # am marcat deja starea inactiva?
    idle_after = cfg.get("idle_sleep_after_s", 3600)

    while True:
        # Mod inactiv: long-polling e deja near-zero cost intre mesaje (blocheaza pe
        # socket, se trezeste INSTANT la un mesaj). Dupa `idle_after` fara mesaje
        # marcam starea (vizibilitate in UI); bucla ramane la fel de responsiva.
        idle_now = (time.time() - last_activity) > idle_after
        if idle_now and not idle_marked:
            idle_marked = True
            log.info("Mod inactiv (fara mesaje de %.0f min) — long-poll low-power, "
                     "trezire instant la urmatorul mesaj.", idle_after / 60)
        _write_status(cfg, running=True, idle=idle_now, last_msg_ts=last_activity)

        try:
            updates = tg.get_updates(state.offset, cfg.get("poll_timeout_s", 50))
            conflict_strikes = 0
        except RuntimeError as e:
            if str(e) == "conflict":
                conflict_strikes += 1
                log.error("getUpdates 409 CONFLICT — alta instanta a puntii polleaza? "
                          "(strike %d)", conflict_strikes)
                if conflict_strikes >= 3:
                    log.error("Prea multe conflicte — ies ca sa nu concurez cu cealalta instanta.")
                    try:
                        tg.send(owner_chat, "🛑 Punte oprita: o alta instanta deja polleaza Telegram.")
                    except Exception:
                        pass
                    return 3
                time.sleep(5)
                continue
            raise
        except KeyboardInterrupt:
            raise
        except Exception as e:
            log.warning("getUpdates a esuat (%s) — reincerc in 5s.", e)
            time.sleep(5)
            continue

        for upd in updates:
            try:
                state.offset = max(state.offset, upd["update_id"] + 1)
                msg = upd.get("message")
                if not msg:
                    continue

                from_id = str((msg.get("from") or {}).get("id", ""))
                chat_id = str((msg.get("chat") or {}).get("id", ""))

                # Whitelist HARD — expeditor SI chat trebuie autorizate.
                if from_id not in ids or (chat_id and chat_id not in ids):
                    now = time.time()
                    if now - _last_alert.get(from_id, 0) > 600:
                        _last_alert[from_id] = now
                        log.warning("Mesaj NEAUTORIZAT de la from=%s chat=%s ignorat.",
                                    from_id, chat_id)
                        try:
                            tg.send(owner_chat,
                                    f"🚫 Acces neautorizat ignorat (from={from_id}, chat={chat_id}).")
                        except Exception:
                            pass
                    continue

                # Sari mesajele vechi (downtime) — nu executa comenzi statute.
                age = time.time() - float(msg.get("date", 0))
                if age > cfg.get("ignore_messages_older_than_s", 180):
                    log.info("Mesaj vechi (%.0fs) ignorat la executie.", age)
                    continue

                # Mesaj autorizat → reactiveaza (iesire din mod inactiv)
                last_activity = time.time()
                if idle_marked:
                    idle_marked = False
                    log.info("Reactivat — mesaj primit dupa perioada inactiva.")
                text = msg.get("text", "")
                reply_to = (msg.get("reply_to_message") or {}).get("message_id")
                router_for(chat_id or from_id).handle(text, msg.get("message_id"), reply_to)
            except Exception:
                log.exception("Eroare la procesarea unui update.")
            finally:
                state.save()

    return 0


def entry() -> int:
    try:
        return main()
    except KeyboardInterrupt:
        log.info("Oprire (Ctrl+C).")
        try:
            token, owner = config.load_credentials()
            if token and owner:
                TelegramClient(token).send(owner, "🛑 Punte Telegram oprita.")
        except Exception:
            pass
        return 0
    finally:
        # curata markerul de proces + status running=false (best-effort)
        try:
            _write_status(config.load_config(), running=False)
        except Exception:
            pass
        _remove_pid()
