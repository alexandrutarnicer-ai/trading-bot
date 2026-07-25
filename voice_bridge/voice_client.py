"""
voice_bridge.voice_client — adaptorul de transport pentru Router.

Router-ul (telegram_bridge.router.Router) trimite raspunsuri prin `tg.send(chat_id,
text, parse_mode, reply_to)`. VoiceClient imita EXACT aceasta semnatura (ca
TelegramClient si MatrixClient), dar in loc sa trimita un mesaj, ROSTESTE textul
prin Speaker (TTS). Asa, Router-ul nu stie ca vorbeste — reutilizam 100% logica lui.
"""

from __future__ import annotations

import logging

log = logging.getLogger("voice_bridge.voice_client")


class VoiceClient:
    def __init__(self, speaker):
        self.speaker = speaker

    def send(self, chat_id: str, text: str, parse_mode: str | None = None,
             reply_to: int | None = None) -> int | None:
        """Aceeasi semnatura ca TelegramClient.send — chat_id/parse_mode/reply_to
        sunt ignorate (nu exista chat). Rosteste textul. Intoarce None (fara
        message_id — Router-ul trateaza None: nu leaga sesiuni de reply pe voce)."""
        try:
            self.speaker.speak(text or "")
        except Exception:
            log.exception("Rostirea raspunsului a esuat.")
        return None
