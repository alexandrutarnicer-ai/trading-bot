"""
voice_bridge.tts — Text-to-Speech pentru EMA (+ modelarea textului pt vorbire).

Doua motoare:
  • pyttsx3 (SAPI Windows)  — ZERO setup, merge din prima. Implicit.
  • Piper (optional)        — voce neurala mai buna + efect "eerie" (pitch-down +
                              reverb) pentru vibe-ul inspirat de Xal'atath.

`speakable()` transforma raspunsul Router-ului (emoji, HTML, markdown, liste) intr-un
text curat de rostit + il scurteaza (log-ul pastreaza tot). Functie PURA (testabila).

Motoarele grele (pyttsx3/piper/numpy/winsound) se importa LAZY — modulul se importa
fara ele (pentru selftest offline). Vorbirea e serializata printr-un thread dedicat
(Speaker) + coada, ca sa nu se suprapuna apeluri din thread-uri diferite ale Router-ului.
"""

from __future__ import annotations

import logging
import os
import queue
import re
import subprocess
import tempfile
import threading
import unicodedata

log = logging.getLogger("voice_bridge.tts")

# Preset-uri de stil. `rate`/`pitch_semitones`/`reverb` = pyttsx3/piper; `edge_rate`/
# `edge_pitch` = edge-tts (siruri SSML); `edge_voice` (optional) = voce preferata.
STYLE_PRESETS = {
    "jarvis":   {"female": False, "rate": 178, "eerie": False,
                 "pitch_semitones": 0.0, "reverb": 0.0,
                 "edge_rate": "+0%", "edge_pitch": "+0Hz",
                 "edge_voice": "en-GB-RyanNeural"},   # masculin, britanic, calm
    "xalatath": {"female": True, "rate": 148, "eerie": True,
                 "pitch_semitones": -3.0, "reverb": 0.28,
                 "edge_rate": "-8%", "edge_pitch": "-20Hz"},
    "calm":     {"female": True, "rate": 165, "eerie": False,
                 "pitch_semitones": 0.0, "reverb": 0.0,
                 "edge_rate": "+0%", "edge_pitch": "+0Hz"},
    "neutral":  {"female": None, "rate": 175, "eerie": False,
                 "pitch_semitones": 0.0, "reverb": 0.0,
                 "edge_rate": "+0%", "edge_pitch": "+0Hz"},
}

# Voce edge-tts implicita dupa limba (fluente, gratuite, fara cheie).
_EDGE_VOICE_BY_LANG = {"ro": "ro-RO-AlinaNeural", "en": "en-GB-RyanNeural"}

# ── modelarea textului pentru vorbire (PURA) ─────────────────────────────────

_HTML_TAG = re.compile(r"<[^>]+>")
_MULTISPACE = re.compile(r"[ \t]+")
# inlocuiri care se citesc mai bine
_REPLACEMENTS = [
    ("→", " catre "), ("·", ". "), ("—", ", "), ("–", ", "),
    ("&", " si "), ("%", " la suta"), ("/", " "), ("|", ". "),
]


def speakable(text: str, max_chars: int = 700) -> str:
    """Curata un raspuns (emoji/HTML/markdown/liste) → text de rostit, scurtat."""
    if not text:
        return ""
    s = _HTML_TAG.sub("", text)                     # scoate tag-uri HTML
    s = s.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    for a, b in _REPLACEMENTS:
        s = s.replace(a, b)
    # scoate emoji si alte simboluri (categoria Unicode 'So') + marcaje markdown
    s = "".join(ch for ch in s
                if unicodedata.category(ch) not in ("So", "Sk", "Cs")
                and ch not in "*_`#>•~^")
    # liniile devin propozitii scurte (pauze naturale)
    lines = [ln.strip(" .-") for ln in s.splitlines()]
    lines = [ln for ln in lines if ln]
    s = ". ".join(lines)
    s = _MULTISPACE.sub(" ", s).strip()
    s = re.sub(r"\.\s*\.\s*", ". ", s)              # colapseaza ".. " → ". "
    if len(s) > max_chars:
        cut = s[:max_chars]
        # taie la ultima granita de propozitie ca sa nu ramana la jumatate
        idx = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
        if idx > max_chars * 0.5:
            cut = cut[:idx + 1]
        s = cut.rstrip() + " ... restul e in jurnal."
    return s


# ── motoare ───────────────────────────────────────────────────────────────

class _Pyttsx3Engine:
    """SAPI Windows via pyttsx3 — zero setup. Reinitializat per rostire (SAPI +
    thread-uri = fragil daca reutilizezi acelasi engine la nesfarsit)."""

    def __init__(self, cfg: dict, style: dict):
        self.cfg = cfg
        self.style = style
        import pyttsx3  # lazy
        self._pyttsx3 = pyttsx3
        self._voice_id = self._pick_voice(style, cfg.get("tts_voice", ""))
        self._rate = int(cfg.get("tts_rate") or style.get("rate", 165))

    def _pick_voice(self, style: dict, want_substr: str) -> str | None:
        try:
            eng = self._pyttsx3.init()
            voices = eng.getProperty("voices")
            eng.stop()
        except Exception:
            return None
        want = (want_substr or "").lower().strip()
        # 1) override explicit din config (substring in id/nume)
        if want:
            for v in voices:
                if want in (v.id or "").lower() or want in (getattr(v, "name", "") or "").lower():
                    return v.id
        lang = (self.cfg.get("language") or "en").lower()
        # 2) voce pt LIMBA ceruta (crucial: RO — altfel citeste romana cu accent EN)
        male_first = style.get("female") is False   # Jarvis = masculin → David inainte de Zira
        en_hints = (("english", "en-gb", "en-us", "en_us", "david", "george", "mark", "zira", "hazel")
                    if male_first else
                    ("english", "en-us", "en-gb", "en_us", "zira", "hazel", "david"))
        lang_hints = {
            "ro": ("romanian", "andrei", "ro-ro", "ro_ro", "roman"),
            "en": en_hints,
        }.get(lang, ())
        for v in voices:
            blob = ((v.id or "") + " " + (getattr(v, "name", "") or "")).lower()
            if any(h in blob for h in lang_hints):
                return v.id
        if lang == "ro":
            log.warning("Nicio voce SAPI ROMANEASCA gasita — EMA ar suna in engleza pe "
                        "text romanesc. Pentru romana FLUENTA: `pip install edge-tts` "
                        "(recomandat) sau adauga o voce RO din Setari Windows > Ora si "
                        "limba > Limba > Romana > Voce.")
        # 3) preferinta de gen (feminin pentru vibe-ul Xal'atath)
        female_hint = ("zira", "hazel", "female", "susan", "eva", "hortense", "helena")
        if style.get("female"):
            for v in voices:
                blob = ((v.id or "") + " " + (getattr(v, "name", "") or "")).lower()
                if any(h in blob for h in female_hint):
                    return v.id
        return voices[0].id if voices else None

    def say(self, text: str) -> None:
        eng = self._pyttsx3.init()
        try:
            if self._voice_id:
                eng.setProperty("voice", self._voice_id)
            eng.setProperty("rate", self._rate)
            eng.say(text)
            eng.runAndWait()
        finally:
            try:
                eng.stop()
            except Exception:
                pass


class _PiperEngine:
    """Piper (subprocess) → WAV → efect eerie optional (numpy) → redare (winsound)."""

    def __init__(self, cfg: dict, style: dict):
        self.binary = cfg.get("piper_binary") or "piper"
        self.model = cfg.get("piper_model", "")
        if not (self.model and os.path.isfile(self.model)):
            raise RuntimeError("piper_model lipseste sau nu exista")
        self.eerie = bool(style.get("eerie"))
        self.pitch = float(cfg.get("tts_pitch_semitones", style.get("pitch_semitones", 0.0)))
        self.reverb = float(cfg.get("tts_reverb", style.get("reverb", 0.0)))

    def say(self, text: str) -> None:
        import wave  # lazy
        with tempfile.TemporaryDirectory() as td:
            wav = os.path.join(td, "ema.wav")
            proc = subprocess.run(
                [self.binary, "--model", self.model, "--output_file", wav],
                input=text.encode("utf-8"),
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if proc.returncode != 0 or not os.path.isfile(wav):
                raise RuntimeError(f"piper a esuat (rc={proc.returncode})")
            if self.eerie and (abs(self.pitch) > 0.01 or self.reverb > 0.01):
                try:
                    _apply_eerie(wav, self.pitch, self.reverb)
                except Exception as e:
                    log.warning("efect eerie sarit (%s)", e)
            _play_wav(wav)


def _apply_eerie(wav_path: str, pitch_semitones: float, reverb: float) -> None:
    """Coboara tonul (resampling) + reverb usor (comb filter). Rescrie WAV-ul in loc.

    Efect dependinte-usoare (numpy) pentru vibe-ul "void / Harbinger" — NU cloneaza
    o voce anume, doar intuneca timbrul unei voci feminine oarecare.
    """
    import wave
    import numpy as np  # lazy

    with wave.open(wav_path, "rb") as w:
        n, sr, sw, nframes = w.getnchannels(), w.getframerate(), w.getsampwidth(), w.getnframes()
        raw = w.readframes(nframes)
    if sw != 2:
        return  # lucram doar pe PCM16
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if n > 1:
        x = x.reshape(-1, n).mean(axis=1)

    # pitch-shift prin resampling liniar (schimba si durata — accept: suna mai lent+grav)
    factor = 2.0 ** (pitch_semitones / 12.0)     # <1 pentru pitch-down
    if abs(factor - 1.0) > 1e-3:
        idx = np.arange(0, len(x), factor)
        x = np.interp(idx, np.arange(len(x)), x).astype(np.float32)

    # reverb simplu: mixeaza cateva ecouri intarziate care se sting
    if reverb > 0.01:
        out = x.copy()
        for delay_ms, gain in ((45, 0.5), (90, 0.3), (150, 0.18)):
            d = int(sr * delay_ms / 1000.0)
            if d < len(out):
                echo = np.zeros_like(out)
                echo[d:] = out[:-d]
                out += echo * (gain * reverb)
        x = out

    peak = float(np.max(np.abs(x))) or 1.0
    x = (x / peak * 0.95 * 32767.0).astype(np.int16)
    with wave.open(wav_path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(x.tobytes())


def _play_wav(path: str) -> None:
    try:
        import winsound  # Windows
        winsound.PlaySound(path, winsound.SND_FILENAME)
        return
    except Exception:
        pass
    # fallback cross-platform
    for player in (["ffplay", "-autoexit", "-nodisp", path], ["aplay", path]):
        try:
            subprocess.run(player, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        except Exception:
            continue


def _play_mp3(path: str) -> None:
    """Reda un MP3 pe Windows fara dependinte extra, via MCI (winmm)."""
    try:
        import ctypes
        winmm = ctypes.windll.winmm
        alias = "ema_edge_mp3"
        p = path.replace('"', "")

        def mci(cmd: str) -> int:
            return winmm.mciSendStringW(cmd, None, 0, 0)

        mci(f"close {alias}")  # curata orice alias ramas
        if mci(f'open "{p}" type mpegvideo alias {alias}') != 0:
            if mci(f'open "{p}" alias {alias}') != 0:
                raise RuntimeError("MCI open mp3 esuat")
        try:
            mci(f"play {alias} wait")
        finally:
            mci(f"close {alias}")
        return
    except Exception:
        pass
    # fallback: ffplay daca exista
    try:
        subprocess.run(["ffplay", "-autoexit", "-nodisp", path],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


class _EdgeTTSEngine:
    """edge-tts — voci NEURALE Microsoft, fluente RO/EN, gratuite, fara cheie.
    ONLINE (trimite textul de rostit la serverele Microsoft). MP3 → redat via MCI.
    Rata/tonul (efectul „lent + grav") vin din stil (edge_rate/edge_pitch)."""

    def __init__(self, cfg: dict, style: dict):
        import edge_tts  # lazy — ridica daca nu e instalat
        self._edge = edge_tts
        lang = (cfg.get("language") or "en").lower()
        # prioritate: edge_voice din config > voce din stil > voce implicita pe limba
        self.voice = ((cfg.get("edge_voice") or "").strip()
                      or style.get("edge_voice")
                      or _EDGE_VOICE_BY_LANG.get(lang, "en-GB-RyanNeural"))
        self.rate = style.get("edge_rate", "+0%")
        self.pitch = style.get("edge_pitch", "+0Hz")

    def say(self, text: str) -> None:
        import asyncio
        with tempfile.TemporaryDirectory() as td:
            mp3 = os.path.join(td, "ema.mp3")

            async def _go():
                com = self._edge.Communicate(text, self.voice,
                                             rate=self.rate, pitch=self.pitch)
                await com.save(mp3)

            asyncio.run(_go())
            if not os.path.isfile(mp3) or os.path.getsize(mp3) == 0:
                raise RuntimeError("edge-tts nu a produs audio (offline?)")
            _play_mp3(mp3)


# ── Speaker: coada + thread dedicat (serializeaza rostirile) ─────────────────

class Speaker:
    """Rosteste texte pe rand (thread dedicat), ca apelurile din thread-urile
    Router-ului sa nu se suprapuna. `wait_idle()` = asteapta sa termine de vorbit
    (folosit ca sa NU asculte microfonul in timp ce vorbeste = evita feedback)."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        style_name = cfg.get("voice_style", "jarvis")
        self.style = STYLE_PRESETS.get(style_name, STYLE_PRESETS["neutral"])
        self.max_chars = int(cfg.get("speak_max_chars", 700))
        self._q: "queue.Queue[str|None]" = queue.Queue()
        self._done = threading.Event()
        self._done.set()
        self._engine = self._build_engine()
        self._worker = threading.Thread(target=self._run, daemon=True, name="EMA-Speaker")
        self._worker.start()

    def _build_engine(self):
        want = (self.cfg.get("tts_engine") or "auto").lower()
        # ordinea incercarilor: motorul cerut primul, apoi fallback-uri sanatoase.
        # auto = Piper (daca e configurat) → edge-tts (daca e instalat) → pyttsx3.
        if want == "auto":
            order = ["piper", "edge", "pyttsx3"]
        elif want in ("piper", "edge", "pyttsx3"):
            order = [want, "edge", "pyttsx3"]
        else:
            order = ["edge", "pyttsx3"]

        seen = set()
        for eng_name in order:
            if eng_name in seen:
                continue
            seen.add(eng_name)
            try:
                if eng_name == "piper":
                    if not self.cfg.get("piper_model"):
                        continue                     # neconfigurat → sari tacut
                    e = _PiperEngine(self.cfg, self.style)
                    log.info("TTS: Piper (%s) stil=%s",
                             os.path.basename(self.cfg["piper_model"]), self.cfg.get("voice_style"))
                    return e
                if eng_name == "edge":
                    e = _EdgeTTSEngine(self.cfg, self.style)
                    log.info("TTS: edge-tts voce=%s (%s/%s) stil=%s",
                             e.voice, e.rate, e.pitch, self.cfg.get("voice_style"))
                    return e
                if eng_name == "pyttsx3":
                    e = _Pyttsx3Engine(self.cfg, self.style)
                    log.info("TTS: pyttsx3 (SAPI) voce=%s rata=%d stil=%s lang=%s",
                             e._voice_id, e._rate, self.cfg.get("voice_style"),
                             self.cfg.get("language"))
                    return e
            except Exception as e:
                log.warning("Motor TTS '%s' indisponibil (%s).", eng_name, e)
                continue
        log.error("Niciun motor TTS disponibil. Vorbirea va fi doar in log.")
        return None

    def _run(self) -> None:
        while True:
            text = self._q.get()
            if text is None:
                return
            try:
                if self._engine is not None:
                    self._engine.say(text)
            except Exception:
                log.exception("Rostire esuata.")
            finally:
                if self._q.empty():
                    self._done.set()

    def speak(self, text: str) -> None:
        """Pune un raspuns la coada de rostit (modelat + scurtat)."""
        spoken = speakable(text, self.max_chars)
        if not spoken:
            return
        log.info("EMA rosteste: %s", spoken[:160])
        self._done.clear()
        self._q.put(spoken)

    def speak_now(self, text: str) -> None:
        """Rosteste si asteapta sa termine (pt confirmari scurte: greeting, «Da?»)."""
        self.speak(text)
        self.wait_idle(timeout=30)

    def wait_idle(self, timeout: float | None = None) -> bool:
        return self._done.wait(timeout=timeout)

    def stop(self) -> None:
        self._q.put(None)
