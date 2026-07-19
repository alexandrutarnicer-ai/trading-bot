"""
telegram_bridge.bridge — bucla principala (long-polling getUpdates).

Porneste manual:  python -m telegram_bridge
Proces STANDALONE. Nu importa botul/motorul in mod care le schimba starea; citeste
doar fisiere de stare + API-ul local. Singurul consumator de getUpdates din proiect.
"""

from __future__ import annotations

import logging
import os
import sys
import time

from . import config, executors
from .telegram_io import TelegramClient, BridgeState
from .router import Router

log = logging.getLogger("telegram_bridge")


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

    log.info("Punte pornita. Whitelist=%s offset=%d", sorted(ids), state.offset)

    _last_alert: dict[str, float] = {}
    conflict_strikes = 0

    while True:
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
