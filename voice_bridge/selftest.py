"""
voice_bridge.selftest — verificari OFFLINE (fara microfon/whisper/TTS/MT5).

Testeaza logica pura: normalizatorul de comenzi, modelarea textului pt vorbire si
garantia de siguranta (canalul vocal e read-only). Ruleaza rapid, fara dependinte grele.

    py -m voice_bridge.selftest
"""

from __future__ import annotations

import sys

from . import config, normalize, bridge
from .tts import speakable, STYLE_PRESETS, _EDGE_VOICE_BY_LANG

# consola Windows e cp1252 — forteaza UTF-8 ca sa nu pice pe sageti/emoji in output
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

_fail = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global _fail
    mark = "PASS" if cond else "FAIL"
    if not cond:
        _fail += 1
    line = f"[{mark}] {name}"
    if detail and not cond:
        line += f"  → {detail}"
    print(line)


def test_readonly_config() -> None:
    cfg = config.load_config()
    check("config: allow_writes FORTAT False", cfg.get("allow_writes") is False,
          f"allow_writes={cfg.get('allow_writes')}")
    check("config: copilot dezactivat pe voce", cfg.get("copilot_enabled") is False)
    check("config: are cheile Router-ului (kw_ai)", "kw_ai" in cfg)
    check("config: are api_base", bool(cfg.get("api_base")))
    # default-uri LIVRATE (VOICE_DEFAULTS) — independent de un data/voice_bridge.json local
    check("config: nume asistent livrat = Jarvis",
          config.VOICE_DEFAULTS["assistant_name"] == "Jarvis")
    check("config: wake_mode livrat = 'openwakeword' (Hey Jarvis)",
          config.VOICE_DEFAULTS["wake_mode"] == "openwakeword")


def test_wake_name() -> None:
    """Mod 'name' (secundar): reactioneaza doar cand fraza incepe cu numele."""
    cases_hit = [
        ("Jarvis, what's the status", "what s the status"),
        ("jarvis status",         "status"),
        ("hey jarvis pause session 7", "pause session 7"),
        ("Jervis, the report",    "the report"),
        ("jarvis",                ""),                 # doar numele → cere comanda
    ]
    for spoken, expected_rest in cases_hit:
        hit, rest = normalize.strip_wake_name(spoken)
        check(f"wake-name: {spoken!r} → adresat, rest={expected_rest!r}",
              hit and rest == expected_rest, f"hit={hit} rest={rest!r}")

    # NU i s-a adresat → ignorat
    for spoken in ("let's play something", "what are you doing tonight", "pass me the ball"):
        hit, _ = normalize.strip_wake_name(spoken)
        check(f"wake-name: {spoken!r} → ignorat (nu incepe cu numele)", not hit)

    # dupa strip, restul se normalizeaza corect intr-o comanda Router
    _, rest = normalize.strip_wake_name("Jarvis how's the bot")
    cmd, _ = normalize.to_command(rest)
    check("wake-name: «Jarvis how's the bot» → /status", cmd == "/status", f"{cmd!r}")


def test_normalize() -> None:
    cases = [
        # (rostit, comanda asteptata)
        ("cum merge botul",              "/status"),
        ("status",                       "/status"),
        ("how's the bot",                "/status"),
        ("system status please",        "/status"),
        ("raportul te rog",              "/raport"),
        ("show me the report",           "/raport"),
        ("scorecard",                    "/raport"),
        ("cum stau pietele",             "/piete"),
        ("markets",                      "/piete"),
        ("ajutor",                       "/ajutor"),
        ("what can you do",              "/ajutor"),
        ("pune pe pauza sesiunea 7",     "/pauza S7"),
        ("pause session seven",          "/pauza S7"),
        ("pause s7",                     "/pauza S7"),
        ("pauza sapte",                  "/pauza S7"),
        ("reia sesiunea 3",              "/reia S3"),
        ("resume session three",         "/reia S3"),
        ("unpause s12",                  "/reia S12"),
    ]
    for spoken, expected in cases:
        cmd, intent = normalize.to_command(spoken)
        check(f"normalize: {spoken!r} → {expected}", cmd == expected,
              f"am primit {cmd!r} (intent={intent})")

    # intrebari libere → nivelul AI rapid
    cmd, _ = normalize.to_command("de ce e XRP pe wait")
    check("normalize: intrebare libera → 'ai ...'",
          cmd.startswith("ai ") and "xrp" in cmd.lower(), f"{cmd!r}")

    cmd, _ = normalize.to_command("intreaba claude de ce a picat S7")
    check("normalize: 'intreaba claude ...' → 'claude ...'",
          cmd.startswith("claude ") and "s7" in cmd.lower(), f"{cmd!r}")

    # control: stop (inchide) vs pauza (mut) vs revenire
    check("normalize: 'exit' → STOP", normalize.to_command("exit")[0] == normalize.STOP)
    check("normalize: 'la revedere' → STOP",
          normalize.to_command("la revedere")[0] == normalize.STOP)
    check("normalize: 'cancel' → CANCEL",
          normalize.to_command("cancel")[0] == normalize.CANCEL)
    check("normalize: gol → IGNORE", normalize.to_command("   ")[0] is normalize.IGNORE)

    # pauza EMA (mut) — cuvinte dedicate + „pauza" fara numar de sesiune
    for phrase in ("culca te", "go to sleep", "stop listening", "mute", "pauza", "taci"):
        check(f"normalize: {phrase!r} → PAUSE (mut EMA)",
              normalize.to_command(phrase)[0] == normalize.PAUSE,
              f"{normalize.to_command(phrase)}")
    # revenire EMA
    for phrase in ("wake up", "trezeste te", "unmute", "reia"):
        check(f"normalize: {phrase!r} → RESUME",
              normalize.to_command(phrase)[0] == normalize.RESUME,
              f"{normalize.to_command(phrase)}")
    # dar pauza CU numar ramane pauza de SESIUNE, nu mut EMA
    check("normalize: 'pauza sesiunea 7' ramane /pauza S7 (nu mut EMA)",
          normalize.to_command("pune pe pauza sesiunea 7")[0] == "/pauza S7")


def test_no_write_commands() -> None:
    """GARANTIE: normalizatorul nu produce NICIODATA comenzi de scriere/edit."""
    dangerous_inputs = [
        "claude modifica signal generator", "claude! adauga un guard",
        "edit on", "slash edit on", "activeaza scrierea", "sterge sesiunea 7",
        "write to file", "run the bot live", "porneste trading live",
    ]
    ok = True
    for s in dangerous_inputs:
        cmd, _ = normalize.to_command(s)
        if cmd in (normalize.STOP, normalize.CANCEL, normalize.IGNORE):
            continue
        # singurele prefixe permise: /status /raport /piete /pauza /reia /ajutor, ai, claude
        low = cmd.lower()
        if low.startswith(("claude! ", "/edit")) or "claude!" in low:
            ok = False
        # "claude ..." e OK (read-only), dar sa nu contina "!"
    check("siguranta: niciun input produce 'claude!' sau '/edit'", ok)

    # verifica explicit ca prefixul de scriere din Router e blocat de config
    cfg = config.load_config()
    check("siguranta: allow_writes=False ⇒ Router refuza 'claude!'",
          cfg.get("allow_writes") is False)


def test_speakable() -> None:
    raw = ("📟 STARE SISTEM\n\n🟢 Bot: ACTIV — 18/20 sesiuni\n"
           "   profil: <b>Standard</b> · pid 1234\n💰 equity $1,043.50")
    s = speakable(raw)
    check("speakable: fara emoji", "📟" not in s and "🟢" not in s and "💰" not in s)
    check("speakable: fara tag-uri HTML", "<b>" not in s and "</b>" not in s)
    check("speakable: pastreaza continutul", "18" in s and "1,043" in s and "Standard" in s)
    check("speakable: '·' devine pauza", "·" not in s)

    long = ". ".join([f"propozitia numarul {i}" for i in range(200)])
    out = speakable(long, max_chars=200)
    check("speakable: scurteaza la max_chars", len(out) <= 240, f"len={len(out)}")
    check("speakable: noteaza trunchierea", "jurnal" in out)

    check("speakable: gol → gol", speakable("") == "" and speakable(None) == "")


def test_language() -> None:
    # default-urile LIVRATE (independent de un data/voice_bridge.json local)
    check("limba: default livrat = 'en'", config.VOICE_DEFAULTS["language"] == "en")
    check("limba: stt_model livrat = 'base'", config.VOICE_DEFAULTS["stt_model"] == "base")
    check("voce: stil implicit = 'jarvis'", config.VOICE_DEFAULTS["voice_style"] == "jarvis")
    # derivarea: stt_language urmeaza language cand nu e setat explicit
    cfg = config.load_config()
    check("limba: stt_language derivat din language",
          cfg.get("stt_language") == (cfg.get("language") or "en").lower(),
          f"stt_language={cfg.get('stt_language')} language={cfg.get('language')}")

    # edge-tts: voci implicite pe limba + stil jarvis cu voce britanica masculina
    check("edge: voce EN implicita = en-GB-RyanNeural (Jarvis)",
          _EDGE_VOICE_BY_LANG.get("en") == "en-GB-RyanNeural")
    check("edge: voce RO implicita exista", bool(_EDGE_VOICE_BY_LANG.get("ro")))
    check("stil jarvis: masculin + voce edge britanica",
          STYLE_PRESETS["jarvis"]["female"] is False
          and STYLE_PRESETS["jarvis"].get("edge_voice", "").startswith("en-GB"))

    # directiva de limba pt AI (Ollama raspunde EN implicit) — testata explicit pe RO
    ro = dict(config.load_config()); ro["language"] = "ro"
    out = bridge._apply_language("ai de ce e XRP pe wait", ro)
    check("apply_language(ro): 'ai …' cere raspuns in romana",
          out.startswith("ai Raspunde") and "in limba romana" in out and "xrp" in out.lower(),
          f"{out!r}")
    check("apply_language(ro): '/status' neatins",
          bridge._apply_language("/status", ro) == "/status")
    en = dict(config.load_config()); en["language"] = "en"
    check("apply_language(en): 'ai …' neatins",
          bridge._apply_language("ai why", en) == "ai why")

    # confirmari rostite pe limba
    check("phrases(ro): yes = 'Da?'", bridge._phrases(ro)["yes"] == "Da?")
    check("phrases(en): yes = 'Yes?'", bridge._phrases(en)["yes"] == "Yes?")


def test_style_presets() -> None:
    check("stil: 'xalatath' exista", "xalatath" in STYLE_PRESETS)
    check("stil: xalatath e feminin + eerie",
          STYLE_PRESETS["xalatath"]["female"] and STYLE_PRESETS["xalatath"]["eerie"])
    check("stil: xalatath coboara tonul",
          STYLE_PRESETS["xalatath"]["pitch_semitones"] < 0)


def run() -> int:
    print("=== voice_bridge selftest (offline) ===\n")
    test_readonly_config()
    print()
    test_wake_name()
    print()
    test_normalize()
    print()
    test_no_write_commands()
    print()
    test_speakable()
    print()
    test_language()
    print()
    test_style_presets()
    print()
    if _fail:
        print(f"❌ {_fail} verificari au esuat.")
        return 1
    print("✅ Toate verificarile au trecut.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
