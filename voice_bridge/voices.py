"""
voice_bridge.voices — diagnostic voci TTS ("de ce vorbeste EMA in engleza?").

Ruleaza:  py -m voice_bridge.voices

Arata: vocile SAPI instalate (pyttsx3) + daca exista una romaneasca, daca edge-tts
e instalat (voci neurale fluente RO), starea Piper, si o recomandare concreta.
"""

from __future__ import annotations

import sys

from . import config

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def _sapi_voices():
    try:
        import pyttsx3
        eng = pyttsx3.init()
        vs = eng.getProperty("voices")
        eng.stop()
        return [(v.id, getattr(v, "name", ""), list(getattr(v, "languages", []) or [])) for v in vs]
    except Exception as e:
        return e


def _edge_ro_voices():
    try:
        import asyncio
        import edge_tts
        async def _list():
            vm = await edge_tts.VoicesManager.create()
            return vm.find(Language="ro")
        ro = asyncio.run(_list())
        return [v.get("ShortName") for v in ro]
    except Exception as e:
        return e


def main() -> int:
    cfg = config.load_config()
    lang = (cfg.get("language") or "ro").lower()
    print("=== EMA — diagnostic voci ===\n")
    print(f"Limba configurata (language): {lang}")
    print(f"STT (whisper): model={cfg.get('stt_model')} language={cfg.get('stt_language')}")
    print(f"tts_engine={cfg.get('tts_engine')}  voice_style={cfg.get('voice_style')}\n")

    # SAPI
    print("— Voci SAPI Windows (pyttsx3) —")
    sapi = _sapi_voices()
    ro_sapi = False
    if isinstance(sapi, Exception):
        print(f"  (pyttsx3 indisponibil: {sapi})")
    elif not sapi:
        print("  (niciuna gasita)")
    else:
        for vid, name, langs in sapi:
            blob = (vid + " " + name).lower()
            is_ro = any(h in blob for h in ("romanian", "andrei", "ro-ro", "ro_ro", "roman"))
            ro_sapi = ro_sapi or is_ro
            print(f"  {'[RO] ' if is_ro else '     '}{name or vid}")
    print()

    # edge-tts
    print("— edge-tts (voci neurale, fluente, gratuite) —")
    edge = _edge_ro_voices()
    edge_ok = not isinstance(edge, Exception)
    if isinstance(edge, Exception):
        print(f"  NEINSTALAT sau fara retea ({edge}).")
        print("  Instalare:  pip install edge-tts")
    else:
        print("  INSTALAT. Voci romanesti disponibile:")
        for v in edge:
            print(f"    {v}")
    print()

    # Piper
    print("— Piper (offline) —")
    pm = cfg.get("piper_model")
    print(f"  model: {pm or '(neconfigurat)'}")
    print()

    # Recomandare
    print("=== Recomandare ===")
    if edge_ok:
        print("  ✅ edge-tts e instalat — EMA poate vorbi romana FLUENT.")
        print("     Pune in data/voice_bridge.json:  \"tts_engine\": \"edge\"  (sau lasa \"auto\").")
        print("     Voce implicita RO: ro-RO-AlinaNeural (feminina). Schimba cu \"edge_voice\".")
    elif ro_sapi:
        print("  ✅ Ai o voce SAPI romaneasca — EMA o va folosi automat (offline).")
    else:
        print("  ⚠️ Nicio voce romaneasca gasita → EMA suna in engleza pe text romanesc.")
        print("     Cel mai simplu:  pip install edge-tts   (romana fluenta, online, gratuit).")
        print("     Sau: Setari Windows > Ora si limba > Limba > Romana > Optiuni > adauga Voce.")
        print("     Sau: language=\"en\" in voice_bridge.json (EMA vorbeste engleza).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
