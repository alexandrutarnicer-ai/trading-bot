"""
voice_bridge.stt — Speech-to-Text cu faster-whisper (local, gratuit).

Ruleaza local (CPU sau GPU CUDA — acelasi GPU pe care sta Ollama). Modelul se
incarca o data (lazy) la prima transcriere. Se importa lazy ca modulul sa poata
fi importat fara faster-whisper instalat (pentru selftest offline).
"""

from __future__ import annotations

import logging

log = logging.getLogger("voice_bridge.stt")


class Transcriber:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.model_name = cfg.get("stt_model", "base")
        self.language = cfg.get("stt_language")     # None = auto
        self._model = None

    def _candidates(self):
        """Lista (device, compute) de incercat, in ordine. CPU e mereu ultima plasa
        de siguranta — GPU pe Windows pica des (lipsa cuDNN/cuBLAS), si atunci CPU
        cu 'base' + int8 e suficient pt comenzi scurte."""
        device = (self.cfg.get("stt_device", "auto") or "auto").lower()
        compute = (self.cfg.get("stt_compute", "auto") or "auto").lower()
        out = []
        if device == "auto":
            gpu = False
            try:
                import ctranslate2
                gpu = ctranslate2.get_cuda_device_count() > 0
            except Exception:
                gpu = False
            if gpu:
                out.append(("cuda", "float16" if compute == "auto" else compute))
            out.append(("cpu", "int8" if compute == "auto" else compute))
        else:
            c = compute if compute != "auto" else ("float16" if device == "cuda" else "int8")
            out.append((device, c))
            if device != "cpu":
                out.append(("cpu", "int8"))   # fallback garantat
        return out

    def _ensure(self):
        if self._model is not None:
            return
        from faster_whisper import WhisperModel  # lazy
        last_err = None
        for dev, comp in self._candidates():
            try:
                log.info("Incarc faster-whisper '%s' (device=%s compute=%s)…",
                         self.model_name, dev, comp)
                self._model = WhisperModel(self.model_name, device=dev, compute_type=comp)
                log.info("Model STT gata (device=%s).", dev)
                return
            except Exception as e:
                last_err = e
                log.warning("STT pe %s a esuat (%s) — incerc urmatorul.", dev, str(e)[:200])
        raise RuntimeError(f"Nu am putut incarca modelul STT '{self.model_name}': {last_err}")

    def load(self) -> None:
        """Warm-up explicit (la pornire) — surprinde erorile devreme + evita latenta
        la prima comanda. Ridica daca nici CPU nu merge (dependinte lipsa)."""
        self._ensure()

    def transcribe(self, audio_f32) -> str:
        """audio_f32 = np.float32 mono 16kHz in [-1, 1] → text (poate fi gol)."""
        self._ensure()
        segments, _info = self._model.transcribe(
            audio_f32,
            language=self.language,
            beam_size=1,               # rapid; creste pentru acuratete
            vad_filter=True,           # taie tacerea → transcriere mai curata
            condition_on_previous_text=False,
        )
        text = " ".join(seg.text for seg in segments).strip()
        return text
