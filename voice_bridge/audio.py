"""
voice_bridge.audio — captura microfon (sounddevice) + VAD simplu pe energie.

Doua moduri de folosire:
  • record_utterance()  — dupa trigger, inregistreaza pana la `max_utterance_s` sau
                          pana la `silence_s` de liniste. Intoarce float32 mono 16k.
  • frames()            — generator de cadre int16 de 80ms (1280 esantioane @16k),
                          formatul cerut de openWakeWord.

sounddevice/numpy se importa LAZY (modulul se importa fara ele — pt selftest offline).
"""

from __future__ import annotations

import logging

log = logging.getLogger("voice_bridge.audio")

FRAME_SAMPLES = 1280   # 80ms @ 16kHz — cadru openWakeWord


class Microphone:
    def __init__(self, cfg: dict):
        self.sr = int(cfg.get("sample_rate", 16000))
        self.device = cfg.get("input_device")
        self.max_s = float(cfg.get("max_utterance_s", 8))
        self.silence_s = float(cfg.get("silence_s", 1.0))
        self.energy = float(cfg.get("vad_energy", 0.006))

    def _sd(self):
        import sounddevice as sd  # lazy
        return sd

    def record_utterance(self):
        """Inregistreaza o comanda: asteapta scurt inceputul vorbirii, apoi opreste
        dupa `silence_s` de liniste. Intoarce np.float32 mono 16k (poate fi gol)."""
        import numpy as np
        sd = self._sd()

        block = int(self.sr * 0.05)          # blocuri de 50ms
        max_blocks = int(self.max_s / 0.05)
        silence_blocks = int(self.silence_s / 0.05)
        # cate blocuri de liniste tolerăm INAINTE sa fi inceput vorbirea (fereastra de start)
        start_grace_blocks = int(2.5 / 0.05)

        chunks = []
        silent = 0
        started = False
        heard_blocks = 0
        max_rms = 0.0

        with sd.InputStream(samplerate=self.sr, channels=1, dtype="float32",
                            blocksize=block, device=self.device) as stream:
            for i in range(max_blocks):
                data, _ = stream.read(block)
                mono = data.reshape(-1)
                rms = float(np.sqrt(np.mean(mono ** 2)) + 1e-9)
                max_rms = max(max_rms, rms)
                chunks.append(mono.copy())
                if rms >= self.energy:
                    started = True
                    heard_blocks += 1
                    silent = 0
                else:
                    silent += 1
                if not started:
                    if i >= start_grace_blocks:
                        break              # nimeni n-a vorbit — renunta
                    continue
                if silent >= silence_blocks:
                    break                  # gata liniste dupa vorbire → comanda completa

        if not started or heard_blocks < 2:
            # de ce n-a auzit: nivel prea mic vs prag (vizibil in log pt debug)
            if max_rms < 1e-4:
                log.info("Microfon: semnal ~zero (max RMS %.5f) — verifica device/permisiuni "
                         "(py -m voice_bridge.miccheck).", max_rms)
            else:
                log.debug("Microfon: sub prag (max RMS %.4f < vad_energy %.4f).",
                          max_rms, self.energy)
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(chunks).astype(np.float32)

    def frames(self):
        """Generator infinit de cadre int16 de 1280 esantioane (pt wake word)."""
        import numpy as np
        sd = self._sd()
        with sd.InputStream(samplerate=self.sr, channels=1, dtype="int16",
                            blocksize=FRAME_SAMPLES, device=self.device) as stream:
            while True:
                data, _ = stream.read(FRAME_SAMPLES)
                yield data.reshape(-1).astype(np.int16)
