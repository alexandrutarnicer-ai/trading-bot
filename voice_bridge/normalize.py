"""
voice_bridge.normalize — traduce vorbirea in comenzi pentru Router.

Whisper transcrie vorbire naturala ("cum merge botul", "pune pe pauza sesiunea
sapte") — NU comenzi cu "/". Acest modul mapeaza fraze rostite (RO + EN) la
string-urile exacte pe care le asteapta telegram_bridge.router.Router:

    "cum merge botul"            → "/status"
    "raportul"                   → "/raport"
    "cum stau pietele"           → "/piete"
    "pune pe pauza sesiunea 7"   → "/pauza S7"
    "reia sesiunea sapte"        → "/reia S7"
    "de ce e XRP pe wait"        → "ai de ce e XRP pe wait"   (intrebare libera → AI rapid)
    "intreaba claude ..."        → "claude ..."               (agent read-only)

SIGURANTA: produce DOAR comenzi read-only. Nu genereaza niciodata "claude!" / "/edit"
(modificari de cod) — canalul vocal nu are whitelist. Functie PURA (testabila offline).
"""

from __future__ import annotations

import re

# Semnale de control (nu merg la Router — le trateaza bucla principala).
STOP    = "__STOP__"      # opreste asistentul complet (inchide procesul)
PAUSE   = "__PAUSE__"     # pune EMA pe pauza/mut (ramane pornita; ideal pe Discord)
RESUME  = "__RESUME__"    # scoate EMA din pauza
CANCEL  = "__CANCEL__"    # anuleaza / n-am zis nimic
IGNORE  = None            # gol / neinteligibil

_NUM_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19, "twenty": 20,
    # romana
    "unu": 1, "una": 1, "doi": 2, "doua": 2, "trei": 3, "patru": 4, "cinci": 5,
    "sase": 6, "sapte": 7, "opt": 8, "noua": 9, "zece": 10, "unsprezece": 11,
    "doisprezece": 12, "treisprezece": 13, "paisprezece": 14, "cincisprezece": 15,
    "saisprezece": 16, "saptesprezece": 17, "optsprezece": 18, "nouasprezece": 19,
    "douazeci": 20,
}

# NOTA: toate trigger-urile sunt in forma DEJA CURATATA (fara apostrof/cratima),
# fiindca _any() le compara cu textul dupa _clean() (punctuatie → spatiu).
_STOP_WORDS   = ("goodbye", "good bye", "exit", "quit",
                 "shut down", "shutdown", "la revedere", "inchide te", "inchidete",
                 "opreste te", "gata")
_CANCEL_WORDS = ("never mind", "nevermind", "cancel", "forget it", "anuleaza",
                 "las o balta", "n am zis nimic", "nimic")
_PAUSE_WORDS  = ("pause", "pauza", "pune pe pauza", "opreste sesiunea", "suspend")
_RESUME_WORDS = ("resume", "reia", "unpause", "porneste sesiunea", "continua sesiunea")
# „culca-te" / „wake up" = pauza/revenire pentru EMA insasi (mut, ramane pornita).
# Distinct de STOP (inchide procesul). Fara numar de sesiune → se aplica lui EMA.
_SLEEP_WORDS  = ("go to sleep", "sleep", "culca te", "adormi", "mute",
                 "stop listening", "opreste ascultarea", "nu ma mai asculta", "taci")
_WAKE_WORDS   = ("wake up", "trezeste te", "unmute", "resume listening",
                 "reia ascultarea", "poti asculta")
_REPORT_WORDS = ("report", "raport", "scorecard", "rezultate", "score card")
_MARKETS_WORDS = ("markets", "piete", "piata", "clasament")
_HELP_WORDS   = ("help", "ajutor", "what can you do", "ce poti", "ce stii", "comenzi")
_STATUS_WORDS = ("status", "stare", "how s the bot", "how is the bot",
                 "bot status", "system status", "cum merge", "cum sta",
                 "ce face botul", "situatia", "how are we doing", "how s it going")


def _clean(raw: str) -> str:
    """lower + fara punctuatie + spatii colapsate + diacritice romanesti simplificate."""
    t = (raw or "").lower().strip()
    # simplifica diacriticele romanesti (whisper le poate scrie oricum)
    for a, b in (("ă", "a"), ("â", "a"), ("î", "i"), ("ș", "s"), ("ş", "s"),
                 ("ț", "t"), ("ţ", "t")):
        t = t.replace(a, b)
    t = re.sub(r"[^\w\s]", " ", t)     # scoate punctuatia
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _any(text: str, words) -> bool:
    return any(w in text for w in words)


def _extract_session_num(text: str) -> int | None:
    """Numarul sesiunii dintr-o fraza: 's7', 'session 7', 'sesiunea sapte', '7'."""
    m = re.search(r"\bs\s*(\d{1,2})\b", text)                       # s7 / s 7
    if m:
        return int(m.group(1))
    m = re.search(r"(?:session|sesiune[a]?)\s*"
                  r"(?:no\.?\s*|number\s*|numarul\s*|nr\s*)?(\d{1,2})", text)
    if m:
        return int(m.group(1))
    for w, n in _NUM_WORDS.items():                                 # numar rostit in litere
        if re.search(r"\b" + re.escape(w) + r"\b", text):
            return n
    m = re.search(r"\b(\d{1,2})\b", text)                           # orice numar simplu
    if m:
        return int(m.group(1))
    return None


_DEFAULT_WAKE_VARIANTS = ("hey jarvis", "hey jervis", "jarvis", "jervis", "javis")


def strip_wake_name(raw: str, variants=None) -> tuple[bool, str]:
    """
    Mod "name": detecteaza numele EMA la INCEPUTUL frazei si intoarce restul.

    (auzit_numele, restul_comenzii). Ex:
      "EMA, care e statusul"  → (True, "care e statusul")
      "ema"                   → (True, "")     # doar numele → EMA raspunde "Da?"
      "hai sa jucam ceva"     → (False, "")    # nu i s-a adresat → ignorat

    PURA / testabila. Variantele acopera transcrieri diverse ale lui Whisper.
    """
    t = _clean(raw)
    if not t:
        return False, ""
    vs = [v for v in (variants or _DEFAULT_WAKE_VARIANTS)]
    # cele mai lungi intai ("hey ema" inainte de "ema")
    for v in sorted({_clean(x) for x in vs if x}, key=len, reverse=True):
        if t == v:
            return True, ""
        if t.startswith(v + " "):
            return True, t[len(v) + 1:].strip()
    return False, ""


def to_command(raw: str, cfg: dict | None = None) -> tuple[str | None, str]:
    """
    (comanda_pentru_Router | semnal_control | None, eticheta_intent).

    Ordinea conteaza: control → pauza/reia → raport/piete/ajutor/status →
    prefix explicit claude/ai → fallback (orice altceva) la nivelul AI rapid.
    """
    t = _clean(raw)
    if not t:
        return IGNORE, "empty"

    if _any(t, _STOP_WORDS):
        return STOP, "control-stop"
    if _any(t, _CANCEL_WORDS):
        return CANCEL, "control-cancel"

    # „culca-te" / „trezeste-te" — pauza/revenire pentru EMA insasi (mut).
    if _any(t, _WAKE_WORDS):
        return RESUME, "control-resume"
    if _any(t, _SLEEP_WORDS):
        return PAUSE, "control-pause"

    # pauza / reia SESIUNE (au numar). Fara numar → se aplica lui EMA (sleep/wake).
    if _any(t, _RESUME_WORDS):
        n = _extract_session_num(t)
        return (f"/reia S{n}", "resume-session") if n else (RESUME, "control-resume")
    if _any(t, _PAUSE_WORDS):
        n = _extract_session_num(t)
        return (f"/pauza S{n}", "pause-session") if n else (PAUSE, "control-pause")

    if _any(t, _REPORT_WORDS):
        return "/raport", "report"
    if _any(t, _MARKETS_WORDS):
        return "/piete", "markets"
    if _any(t, _HELP_WORDS):
        return "/ajutor", "help"
    if _any(t, _STATUS_WORDS):
        return "/status", "status"

    # prefix explicit: "(intreaba) claude ..." → agent read-only
    m = re.match(r"(?:ask\s+claude|intreaba(?:\s*l)?\s*(?:pe\s+)?claude|claude)\b\s*(.*)", t)
    if m and m.group(1).strip():
        return "claude " + m.group(1).strip(), "claude"

    # prefix explicit: "(ask|intreaba|ai) ..." → AI rapid
    m = re.match(r"(?:ask|intreaba|intrebare|ai)\b\s*(.*)", t)
    if m and m.group(1).strip():
        return "ai " + m.group(1).strip(), "ai-explicit"

    # orice altceva = intrebare libera → nivelul AI rapid (Ollama / surse existente)
    return "ai " + t, "ai-default"
