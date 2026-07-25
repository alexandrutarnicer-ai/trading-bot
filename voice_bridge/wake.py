"""
voice_bridge.wake — declansarea ascultarii ("cand incepe EMA sa te asculte").

Trei moduri (config `wake_mode`):
  • "name" (IMPLICIT) — spui numele la inceput ("EMA, status"). Detectat prin STT
                        (Whisper), deci merge cu numele custom "EMA" fara model
                        antrenat. Bucla din bridge.py face detectia (are nevoie de
                        transcriere) — aici mode = "name" e doar un marcaj.
  • "openwakeword"    — wake acustic cu model pre-antrenat (ex "hey_jarvis").
  • "ptt"             — push-to-talk: apesi ENTER ca sa vorbesti.

openWakeWord se importa LAZY. Daca modul cerut nu e disponibil, cadem elegant pe un
mod care sigur functioneaza (name → ptt), ca sistemul sa mearga oricum.
"""

from __future__ import annotations

import logging

log = logging.getLogger("voice_bridge.wake")


def _resolve_mode(cfg: dict) -> str:
    """wake_mode are prioritate; altfel derivam din flag-urile vechi (compat)."""
    m = (cfg.get("wake_mode") or "").strip().lower()
    if m in ("name", "openwakeword", "ptt"):
        return m
    if cfg.get("push_to_talk"):
        return "ptt"
    if cfg.get("wake_word_enabled"):
        return "openwakeword"
    return "name"


class WakeSource:
    """`mode` = "name" / "wake" (openwakeword) / "ptt". Pentru "wake"/"ptt", `wait()`
    blocheaza pana la trigger. Pentru "name", detectia se face in bridge.py (STT)."""

    def __init__(self, cfg: dict, mic):
        self.cfg = cfg
        self.mic = mic
        requested = _resolve_mode(cfg)
        self.mode = requested
        self._oww = None
        if requested == "openwakeword":
            if self._init_openwakeword():
                self.mode = "wake"
            else:
                # fallback pe PTT (100% sigur) — NU pe 'name' (care e tot capricios)
                log.warning("openWakeWord indisponibil — trec pe PUSH-TO-TALK (ENTER). "
                            "Instaleaza: pip install openwakeword onnxruntime")
                self.mode = "ptt"

    def _init_openwakeword(self) -> bool:
        try:
            from openwakeword.model import Model  # lazy
            try:
                from openwakeword.utils import download_models
                download_models()
            except Exception as e:
                log.info("download_models a esuat (%s) — presupun ca sunt deja descarcate.", e)
            model = self.cfg.get("wake_model", "hey_jarvis")
            # pe Windows openWakeWord ruleaza pe onnxruntime (tflite nesuportat)
            try:
                self._oww = Model(wakeword_models=[model], inference_framework="onnx")
            except TypeError:
                self._oww = Model(wakeword_models=[model])   # versiune fara param
            except Exception:
                self._oww = Model()                          # incarca toate modelele
            self._threshold = float(self.cfg.get("wake_threshold", 0.5))
            log.info("Wake acustic activ: '%s' (prag %.2f). Spune «Hey Jarvis».",
                     model, self._threshold)
            return True
        except Exception as e:
            log.warning("Nu am putut initializa openWakeWord (%s).", e)
            self._oww = None
            return False

    # -- push-to-talk --
    def _wait_ptt(self) -> bool:
        name = self.cfg.get("assistant_name", "EMA")
        try:
            input(f"[ {name} ] Apasa ENTER si vorbeste (Ctrl+C = iesire)…  ")
            return True
        except EOFError:
            return False

    # -- wake acustic --
    def _wait_wake(self) -> bool:
        # openWakeWord intoarce {nume_model: scor}; cheia poate fi versionata
        # (ex "hey_jarvis_v0.1"), deci luam MAXIMUL scorurilor, nu o cheie fixa.
        try:
            self._oww.reset()
        except Exception:
            pass
        # IMPORTANT: inchidem generatorul (deci si InputStream-ul microfonului)
        # DETERMINIST la detectie, ca inregistrarea comenzii care urmeaza sa nu
        # deschida un al doilea stream peste cel de wake (device ocupat → comanda goala).
        gen = self.mic.frames()
        try:
            for frame in gen:
                scores = self._oww.predict(frame)
                if scores and max(scores.values()) >= self._threshold:
                    return True
        finally:
            gen.close()
        return False

    def wait(self) -> bool:
        """Doar pentru "wake"/"ptt". In mod "name", bridge.py nu apeleaza wait()."""
        if self.mode == "wake":
            return self._wait_wake()
        if self.mode == "ptt":
            return self._wait_ptt()
        return True   # "name": trigger-ul e gestionat de bucla (STT)
