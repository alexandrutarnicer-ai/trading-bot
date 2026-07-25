"""
voice_bridge.config — configurarea canalului vocal (asistentul "EMA").

Model identic cu telegram_bridge.config: pornim de la DEFAULTS-urile puntii Telegram
(ca Router-ul sa aiba toate cheile de care are nevoie: kw_ai, level_*, api_base,
claude_*, single_task ...), adaugam cheile specifice vocii, apoi aplicam override
optional din data/voice_bridge.json (gitignored).

REGULA DE SIGURANTA: `allow_writes` e FORTAT False la final — canalul vocal nu are
whitelist (microfonul asculta pe oricine e langa PC), deci nu executa niciodata
modificari de cod. Normalizatorul (normalize.py) nici nu produce comenzi de scriere.
"""

from __future__ import annotations

import json
import os

from telegram_bridge import config as tg_config   # reutilizam DEFAULTS + credentiale

ROOT      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR  = os.path.join(ROOT, "data")
CFG_PATH  = os.path.join(DATA_DIR, "voice_bridge.json")
STATE_PATH = os.path.join(DATA_DIR, "voice_bridge_state.json")
LOG_PATH  = os.path.join(DATA_DIR, "voice_bridge.log")
PID_PATH  = os.path.join(DATA_DIR, "voice_bridge.pid")
STATUS_PATH = os.path.join(DATA_DIR, "voice_bridge_status.json")

# Cheile specifice vocii (peste DEFAULTS-urile Router-ului din telegram_bridge).
VOICE_DEFAULTS: dict = {
    "enabled": True,
    "assistant_name": "Jarvis",       # numele asistentului (in vorbire + log)

    # ── Trezire (wake) ──────────────────────────────────────────────────────
    # wake_mode alege CUM te aude Jarvis:
    #   "openwakeword" (IMPLICIT) — wake acustic cu model pre-antrenat "hey_jarvis"
    #                       (fiabil, ruleaza local, latenta mica). Spui "Hey Jarvis",
    #                       apoi comanda. Pe Windows foloseste onnxruntime (auto).
    #   "ptt"             — push-to-talk: apesi ENTER, apoi vorbesti (100% sigur).
    #   "name"            — spui numele la inceput ("Jarvis, status"), detectat prin
    #                       STT. Merge cu orice nume dar e mai capricios (transcriere).
    "wake_mode":         "openwakeword",
    "wake_model":        "hey_jarvis",  # model openWakeWord pre-antrenat
    "wake_threshold":    0.5,
    "wake_name":         "Jarvis",    # numele rostit (doar mod "name")
    "wake_name_variants": [           # variante de transcriere acceptate (mod "name")
        "jarvis", "hey jarvis", "jervis", "javis", "jarvez", "hey jervis"],
    "ack_on_wake":       True,        # confirmare scurta ("Yes?") cand te aude

    # compat (lasate pt suprascriere avansata; wake_mode are prioritate)
    "push_to_talk":      False,
    "wake_word_enabled": True,

    # ── Pauza / mut (scenariul „sunt pe Discord cu prietenii") ───────────────
    # Cand EMA e pe pauza (din UI sau comanda vocala „culca-te"), microfonul e
    # OPRIT complet (mut total) — nu asculta jocul/prietenii. Revenirea implicita
    # se face din UI (buton „Reia"). resume_by_voice=True tine wake-ul viu si in
    # pauza (doar mod wake acustic) ca sa poti reveni si vocal — dar atunci
    # microfonul ramane pornit; implicit False = mut real, gaming-safe.
    "resume_by_voice":   False,

    # ── Limba ────────────────────────────────────────────────────────────────
    # Controleaza: (1) limba STT (recunoastere), (2) alegerea vocii TTS,
    # (3) limba confirmarilor rostite, (4) hint-ul „raspunde in <limba>" pt AI.
    # "en" = engleza (implicit — STT precis, voci Windows disponibile), "ro" = romana.
    # FORTEAZA STT pe limba asta (auto-detect gresea des pe fraze scurte).
    "language":     "en",

    # ── Speech-to-Text (faster-whisper) ─────────────────────────────────────
    "stt_model":    "base",           # tiny/base/small/medium — base = rapid + precis pe EN
    "stt_language": None,             # None = deriva din `language`; "en"/"ro" forteaza direct
    # CPU implicit = FIABIL pe Windows. GPU (cuda) pica des fara cuDNN/cuBLAS si arunca
    # eroare la fiecare transcriere (parea „microfon stricat"). base pe CPU e sub 1s.
    # Pune "auto" ca sa incerce GPU (cu fallback automat pe CPU daca esueaza).
    "stt_device":   "cpu",            # cpu/auto/cuda
    "stt_compute":  "auto",           # auto/int8/float16 (CTranslate2)

    # ── Text-to-Speech ───────────────────────────────────────────────────────
    # "auto" (implicit) alege in ordine: Piper (daca e configurat) → edge-tts (daca
    # e instalat: `pip install edge-tts` — voci NEURALE fluente RO/EN, ex
    # ro-RO-AlinaNeural) → pyttsx3 (SAPI Windows, zero-setup, dar robotic). Pentru
    # romana FLUENTA recomandat edge-tts sau Piper cu voce RO — SAPI implicit pe
    # Windows e adesea doar engleza (de aia EMA „vorbea in engleza").
    "tts_engine":   "auto",           # auto/edge/piper/pyttsx3
    "voice_style":  "jarvis",         # preset: masculin, britanic, calm (vezi tts.STYLE_PRESETS)
    "tts_voice":    "",               # override: substring voce pyttsx3 SAU cale model piper
    "tts_rate":     150,              # pyttsx3 cuvinte/min (mai mic = mai deliberat)
    "speak_max_chars": 700,           # taie raspunsurile lungi la vorbire (log-ul are tot)

    # edge-tts (recomandat pt fluenta; ONLINE, gratuit, fara cheie):
    "edge_voice":   "",               # gol = auto dupa `language` (ro→ro-RO-AlinaNeural)

    # Piper (optional, OFFLINE) + efect eerie aplicat DOAR pe iesirea Piper (WAV):
    "piper_binary": "",               # cale piper.exe (gol = dezactivat)
    "piper_model":  "",               # cale voce .onnx (RO: ro_RO-mihai-medium.onnx)
    "tts_pitch_semitones": -3.0,      # coborare ton pentru vibe "void" (efect piper)
    "tts_reverb":   0.25,             # reverb usor 0..1 (efect piper)

    # ── Captura microfon ──────────────────────────────────────────────────────
    "sample_rate":    16000,          # 16k = ce vor whisper + openWakeWord
    "max_utterance_s": 8,             # inregistreaza cel mult atat per comanda
    "silence_s":      1.0,            # opreste inregistrarea dupa atata liniste
    "vad_energy":     0.004,          # prag RMS pentru "e vorbire" (0..1) — mai jos = mai sensibil
    "input_device":   None,           # index microfon sounddevice (None = implicit)

    # heartbeat status pt UI/API (mirror al telegram_bridge)
    "write_status": True,
}


def load_config() -> dict:
    """DEFAULTS Router (telegram_bridge) + VOICE_DEFAULTS + override voice_bridge.json.

    `allow_writes` e FORTAT False la final (read-only hard pe canalul vocal).
    """
    cfg = dict(tg_config.DEFAULTS)     # toate cheile de care are nevoie Router-ul
    cfg.update(VOICE_DEFAULTS)         # + cheile vocii (suprascriu unde se suprapun)

    allowed_keys = set(cfg.keys())
    if os.path.isfile(CFG_PATH):
        try:
            with open(CFG_PATH, encoding="utf-8") as f:
                user = json.load(f)
            cfg.update({k: v for k, v in user.items() if k in allowed_keys})
        except Exception:
            pass

    # auto-detect binar Claude (pentru nivelul optional "claude ..." read-only)
    if not cfg.get("claude_binary"):
        cfg["claude_binary"] = (tg_config._DEFAULT_CLAUDE
                                if os.path.isfile(tg_config._DEFAULT_CLAUDE) else "claude")

    # Deriva limba STT din `language` daca nu e setata explicit — auto-detect pe
    # fraze scurte gresea limba si nu recunostea „EMA"; fortarea ei e cheia.
    lang = (cfg.get("language") or "ro").strip().lower()
    if not cfg.get("stt_language"):
        cfg["stt_language"] = lang

    # ── HARD READ-ONLY: canalul vocal nu scrie niciodata cod ──
    cfg["allow_writes"] = False
    cfg["copilot_enabled"] = False
    return cfg


# Doar cheile pe care le tuning-uiesti frecvent ajung in fisierul de exemplu. NU
# scriem tot VOICE_DEFAULTS — altfel fisierul „ingheata" toata schema si viitoarele
# schimbari de default (ex: o voce mai buna) nu ar mai ajunge la user.
_STARTER_KEYS = ("language", "wake_mode", "wake_name", "tts_engine", "voice_style",
                 "edge_voice", "stt_model", "resume_by_voice")


def save_default_config() -> None:
    """Scrie un voice_bridge.json minimal de exemplu la prima rulare (doar cheile
    tunate des). Restul default-urilor raman LIVE in cod."""
    if not os.path.isfile(CFG_PATH):
        os.makedirs(DATA_DIR, exist_ok=True)
        example = {k: VOICE_DEFAULTS[k] for k in _STARTER_KEYS if k in VOICE_DEFAULTS}
        with open(CFG_PATH, "w", encoding="utf-8") as f:
            json.dump(example, f, indent=2, ensure_ascii=False)


def set_config_value(key: str, value) -> None:
    """Persista o singura cheie in data/voice_bridge.json (fara a pierde restul)."""
    os.makedirs(DATA_DIR, exist_ok=True)
    cur: dict = {}
    if os.path.isfile(CFG_PATH):
        try:
            with open(CFG_PATH, encoding="utf-8") as f:
                cur = json.load(f)
        except Exception:
            cur = {}
    cur[key] = value
    tmp = CFG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cur, f, indent=2, ensure_ascii=False)
    os.replace(tmp, CFG_PATH)
