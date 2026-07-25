"""
voice_bridge.bridge — bucla principala a canalului vocal (asistentul "EMA").

Flux per interactiune:
  trezire (ENTER / "hey ...")  →  inregistrare microfon  →  Whisper (STT)
  →  normalize.to_command()    →  Router.handle()        →  raspuns rostit (TTS)

Reutilizeaza EXACT Router-ul din telegram_bridge (comenzi identice logic). Proces
STANDALONE, aditiv, izolat: nu importa botul/motorul in mod care le schimba starea,
citeste doar starea + API-ul local (prin comenzile Router-ului). READ-ONLY hard
(config forteaza allow_writes=False; normalizatorul nu produce comenzi de scriere).
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time

from telegram_bridge.router import Router
from telegram_bridge.telegram_io import BridgeState

from . import config, control, normalize
from .voice_client import VoiceClient

log = logging.getLogger("voice_bridge")

# Confirmarile rostite, pe limbi (celelalte raspunsuri vin din Router / AI).
_PHRASES = {
    "ro": {
        "online":  "{name} este online. {hint}.",
        "yes":     "Da?",
        "back":    "Am revenit.",
        "closing": "Ma inchid. Pe curand.",
        "paused":  "Intru in pauza. Trezeste-ma din interfata.",
        "here":    "Sunt aici.",
        "cancel":  "Am anulat.",
        "stt_err": "Eroare la recunoasterea vocala.",
        "didnt_catch": "Nu am inteles, mai spune o data.",
        "stt_down": "Recunoasterea vocala nu s-a putut incarca. Ruleaza setup.",
        "hint_name": "spune {name} urmat de comanda",
        "hint_ptt":  "apasa ENTER ca sa vorbesti",
        "hint_wake": "spune Hey Jarvis, apoi comanda",
    },
    "en": {
        "online":  "{name} is online. {hint}.",
        "yes":     "Yes?",
        "back":    "I'm back.",
        "closing": "Shutting down. Goodbye.",
        "paused":  "Going quiet. Wake me from the interface.",
        "here":    "I'm here.",
        "cancel":  "Cancelled.",
        "stt_err": "Speech recognition error.",
        "didnt_catch": "I didn't catch that, say it again.",
        "stt_down": "Speech recognition failed to load. Please run setup.",
        "hint_name": "say {name} then your command",
        "hint_ptt":  "press ENTER to talk",
        "hint_wake": "say Hey Jarvis, then your command",
    },
}


def _phrases(cfg: dict) -> dict:
    return _PHRASES.get((cfg.get("language") or "ro").lower(), _PHRASES["ro"])


def _apply_language(cmd: str, cfg: dict) -> str:
    """Pentru romana, cere nivelelor libere (ai/claude) sa raspunda scurt in romana —
    altfel Ollama/sursele raspund implicit in engleza. Comenzile /... nu sunt atinse."""
    lang = (cfg.get("language") or "ro").lower()
    if lang != "ro":
        return cmd
    for kw in ("ai ", "claude "):
        if cmd.startswith(kw):
            return kw + "Raspunde pe scurt, in limba romana. " + cmd[len(kw):]
    return cmd


def _setup_logging() -> None:
    os.makedirs(config.DATA_DIR, exist_ok=True)
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    handlers = [logging.StreamHandler(sys.stdout)]
    try:
        handlers.append(logging.FileHandler(config.LOG_PATH, encoding="utf-8"))
    except Exception:
        pass
    logging.basicConfig(level=logging.INFO, format=fmt, handlers=handlers)


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


def _write_status(cfg: dict, running: bool, mode: str = "", listening: bool = False,
                  paused: bool = False) -> None:
    if not cfg.get("write_status", True):
        return
    try:
        st = {
            "running": running,
            "pid": os.getpid(),
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "assistant_name": cfg.get("assistant_name", "EMA"),
            "mode": mode,                         # "wake" / "ptt"
            "listening": listening,
            "paused": paused,
            "voice_style": cfg.get("voice_style"),
            "stt_model": cfg.get("stt_model"),
            "read_only": True,
        }
        tmp = config.STATUS_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(st, f, ensure_ascii=False, indent=1)
        os.replace(tmp, config.STATUS_PATH)
    except Exception:
        pass


def _parse_args(argv):
    import argparse
    p = argparse.ArgumentParser(prog="voice_bridge", add_help=True,
                                description="EMA — asistent vocal (read-only).")
    p.add_argument("--wake", choices=["name", "ptt", "openwakeword"],
                   help="cum te aude: name (implicit) / ptt (ENTER) / openwakeword (hey jarvis)")
    p.add_argument("--ptt", action="store_true", help="scurtatura pentru --wake ptt")
    p.add_argument("--lang", choices=["ro", "en"], help="limba (STT + voce + raspunsuri)")
    p.add_argument("--device", type=int, help="index microfon (vezi py -m voice_bridge.miccheck)")
    p.add_argument("--debug", action="store_true",
                   help="verbose: arata tot ce aude EMA (chiar daca nu i s-a adresat)")
    return p.parse_args(argv)


def main(argv=None) -> int:
    _setup_logging()
    args = _parse_args(argv)
    cfg = config.load_config()
    config.save_default_config()

    # suprascrieri din linia de comanda (pentru testare rapida, fara editare JSON)
    if args.ptt:
        cfg["wake_mode"] = "ptt"
    if args.wake:
        cfg["wake_mode"] = args.wake
    if args.lang:
        cfg["language"] = args.lang
        cfg["stt_language"] = args.lang
    if args.device is not None:
        cfg["input_device"] = args.device
    if args.debug:
        cfg["_debug"] = True
        logging.getLogger("voice_bridge").setLevel(logging.DEBUG)
        log.info("Mod DEBUG activ — afisez tot ce aude EMA.")

    if not cfg.get("enabled", True):
        log.info("Canalul vocal e dezactivat (enabled=false). Ies.")
        return 0

    name = cfg.get("assistant_name", "EMA")

    # componente grele — import lazy, cu mesaj clar daca lipsesc dependintele
    try:
        from .tts import Speaker
        from .stt import Transcriber
        from .audio import Microphone
        from .wake import WakeSource
    except Exception as e:
        log.error("Import esuat (%s). Ruleaza setup_voice_bridge.bat.", e)
        return 2

    speaker = Speaker(cfg)
    transcriber = Transcriber(cfg)
    mic = Microphone(cfg)
    wake = WakeSource(cfg, mic)

    state = BridgeState(path=config.STATE_PATH)   # stare proprie (nu se ciocneste cu Telegram)
    voice = VoiceClient(speaker)
    router = Router(cfg, state, voice, chat_id="voice")

    _write_pid()
    _write_status(cfg, running=True, mode=wake.mode)

    P = _phrases(cfg)
    trigger_hint = {
        "ptt":  P["hint_ptt"],
        "wake": P["hint_wake"],
        "name": P["hint_name"].format(name=name),
    }.get(wake.mode, P["hint_name"].format(name=name))
    log.info("Canal vocal PORNIT — %s · mod=%s · STT=%s · stil=%s",
             name, wake.mode, cfg.get("stt_model"), cfg.get("voice_style"))
    speaker.speak_now(P["online"].format(name=name, hint=trigger_hint))

    # Warm-up STT: incarca modelul ACUM (nu la prima comanda) — surprinde erorile
    # de incarcare (ex: GPU fara cuDNN) devreme, cu mesaj clar, si scoate latenta.
    try:
        log.info("Warm-up model STT…")
        transcriber.load()
    except Exception as e:
        log.error("STT nu s-a putut incarca: %s", e)
        speaker.speak_now(P["stt_down"])

    def _listen_text() -> str:
        """Inregistreaza o rostire + o transcrie (sau '' daca gol/eroare). NU vorbeste
        — apelantul decide feedback-ul (evita mesaje duble)."""
        audio = mic.record_utterance()
        if audio is None or len(audio) == 0:
            return ""
        try:
            return transcriber.transcribe(audio)
        except Exception:
            log.exception("Transcriere esuata.")
            return ""

    was_paused = False
    try:
        while True:
            # ── Pauza / mut (ex: esti pe Discord) — microfon OPRIT complet ──
            if control.is_paused():
                if not was_paused:
                    was_paused = True
                    log.info("EMA pe PAUZA (microfon oprit). Reia din UI"
                             + (" sau cu wake word." if cfg.get("resume_by_voice")
                                and wake.mode == "wake" else "."))
                _write_status(cfg, running=True, mode=wake.mode, listening=False, paused=True)
                if cfg.get("resume_by_voice") and wake.mode == "wake":
                    # mod wake: tinem detectorul viu ca sa poti reveni si vocal
                    if wake.wait():
                        control.set_paused(False)
                else:
                    time.sleep(1.0)        # poll flag — revenire din UI
                if not control.is_paused():
                    was_paused = False
                    speaker.speak_now(P["back"])
                continue
            was_paused = False

            # ── Obtine textul comenzii, dupa mod ──
            if wake.mode == "name":
                # Mod IMPLICIT: asculta continuu, reactioneaza DOAR daca fraza
                # incepe cu numele ("EMA, ..."). Restul (ex: Discord) e ignorat.
                _write_status(cfg, running=True, mode=wake.mode, listening=True)
                heard = _listen_text()
                if not heard or control.is_paused():
                    if cfg.get("_debug") and not heard:
                        print("[DEBUG] Am inregistrat, dar Whisper n-a inteles nimic "
                              "(liniste / prea scurt / limba gresita).")
                    continue
                addressed, remainder = normalize.strip_wake_name(
                    heard, cfg.get("wake_name_variants"))
                if not addressed:
                    log.info("(nu mi s-a adresat): %r", heard)
                    if cfg.get("_debug"):
                        print(f"[DEBUG] Am auzit: {heard!r}\n"
                              f"        -> NU incepe cu numele. Spune 'EMA' clar, primul cuvant. "
                              f"Daca Whisper aude constant altceva pt 'EMA', adauga-l in "
                              f"wake_name_variants.")
                    continue
                if cfg.get("_debug"):
                    print(f"[DEBUG] Am auzit: {heard!r}  -> nume OK, comanda: {remainder!r}")
                command_text = remainder
                if not command_text:                 # doar numele → cere comanda
                    if cfg.get("ack_on_wake", True):
                        speaker.speak_now(P["yes"])
                    command_text = _listen_text()
                    if not command_text:
                        speaker.speak(P["didnt_catch"])   # feedback, nu tacere
                        continue
            else:
                # Mod "wake" (openWakeWord) / "ptt" (ENTER)
                _write_status(cfg, running=True, mode=wake.mode, listening=False)
                triggered = wake.wait()
                if not triggered:
                    break                      # EOF pe push-to-talk → iesire curata
                if control.is_paused():        # pusa pe pauza chiar in timp ce astepta
                    continue
                if cfg.get("ack_on_wake", True) and wake.mode == "wake":
                    speaker.speak_now(P["yes"])
                _write_status(cfg, running=True, mode=wake.mode, listening=True)
                command_text = _listen_text()
                if not command_text:
                    # dupa "Yes?" tacerea deruteaza — da feedback (mai putin la PTT)
                    if wake.mode != "ptt":
                        speaker.speak(P["didnt_catch"])
                    continue

            log.info("Auzit: %r", command_text)
            cmd, intent = normalize.to_command(command_text, cfg)

            if cmd is normalize.IGNORE:
                continue
            if cmd == normalize.STOP:
                speaker.speak_now(P["closing"])
                break
            if cmd == normalize.PAUSE:
                control.set_paused(True)
                speaker.speak_now(P["paused"])
                continue
            if cmd == normalize.RESUME:
                control.set_paused(False)      # deja activa; doar confirma
                speaker.speak(P["here"])
                continue
            if cmd == normalize.CANCEL:
                speaker.speak(P["cancel"])
                continue

            cmd = _apply_language(cmd, cfg)    # ai/claude → raspuns in romana
            log.info("Intent=%s → comanda Router: %r", intent, cmd)
            # Router-ul raspunde prin voice.send → speaker (sincron pt instant,
            # asincron pt ai/claude). Nu ascultam cat vorbeste (evitam feedback).
            router.handle(cmd, None, None)
            speaker.wait_idle(timeout=cfg.get("claude_timeout_s", 600) + 5)

    except KeyboardInterrupt:
        log.info("Oprire (Ctrl+C).")
    finally:
        try:
            speaker.stop()
        except Exception:
            pass
        _write_status(cfg, running=False, mode=wake.mode)
        _remove_pid()
    return 0
