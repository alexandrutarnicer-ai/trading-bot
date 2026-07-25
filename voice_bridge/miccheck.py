"""
voice_bridge.miccheck — diagnostic MICROFON ("EMA nu ma aude").

Ruleaza:  py -m voice_bridge.miccheck

Trei faze:
  1. Listeaza dispozitivele de intrare (si care e implicit / setat in config).
  2. Contor de nivel LIVE ~5s — vorbesti si vezi daca microfonul capteaza (RMS + bara),
     comparat cu pragul `vad_energy`.
  3. Test pipeline complet — inregistreaza o comanda (aceeasi cale ca EMA), o transcrie
     cu Whisper si verifica daca numele 'EMA' e detectat.

Nu atinge nimic — doar citeste microfonul si iti spune ce e in neregula + cum sa repari.
"""

from __future__ import annotations

import sys

from . import config, normalize

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def _fail(msg: str) -> int:
    print(msg)
    return 1


def main() -> int:
    cfg = config.load_config()
    try:
        import sounddevice as sd
        import numpy as np
    except Exception as e:
        return _fail("sounddevice/numpy nu sunt instalate — ruleaza setup_voice_bridge.bat\n"
                     f"({e})")

    print("=== EMA — diagnostic microfon ===\n")

    # ── Faza 1: dispozitive ──
    try:
        default_in = sd.default.device[0]
    except Exception:
        default_in = None
    try:
        devices = sd.query_devices()
    except Exception as e:
        return _fail(f"[EROARE] nu pot enumera dispozitivele audio: {e}")

    print("Dispozitive de INTRARE (microfoane):")
    n_inputs = 0
    for i, d in enumerate(devices):
        if d.get("max_input_channels", 0) > 0:
            n_inputs += 1
            mark = "  <== IMPLICIT" if i == default_in else ""
            cur = "  (setat in config)" if cfg.get("input_device") == i else ""
            print(f"  [{i}] {d['name']}  ({d['max_input_channels']} ch){mark}{cur}")
    if n_inputs == 0:
        return _fail("\n[EROARE] Niciun microfon detectat de Windows!\n"
                     "  - Conecteaza un microfon / casti cu microfon.\n"
                     "  - Windows: Settings > System > Sound > Input — alege un dispozitiv.\n"
                     "  - Settings > Privacy & security > Microphone — permite accesul.")
    print()

    dev = cfg.get("input_device")
    sr = int(cfg.get("sample_rate", 16000))
    thr = float(cfg.get("vad_energy", 0.006))
    print(f"Config EMA: input_device={dev if dev is not None else 'implicit'}  "
          f"sample_rate={sr}  vad_energy(prag)={thr}\n")

    # ── Faza 2: contor de nivel live ──
    print("FAZA 2 — vorbeste ~5 secunde acum (ex: 'EMA, test unu doi trei'):\n")
    dur, blk = 5.0, 0.1
    peak = 0.0
    total = above = 0
    try:
        with sd.InputStream(samplerate=sr, channels=1, dtype="float32",
                            blocksize=int(sr * blk), device=dev) as stream:
            for _ in range(int(dur / blk)):
                data, _ = stream.read(int(sr * blk))
                rms = float(np.sqrt(np.mean(data.reshape(-1) ** 2)) + 1e-9)
                peak = max(peak, rms)
                total += 1
                above += (rms >= thr)
                bar = "#" * min(40, int(rms * 400))
                print(f"  RMS {rms:.4f} |{bar}")
    except Exception as e:
        return _fail(f"\n[EROARE] nu pot deschide microfonul: {e}\n"
                     "  - Settings > Privacy & security > Microphone: permite aplicatiilor "
                     "DESKTOP accesul.\n"
                     "  - Microfonul poate fi folosit de alta aplicatie sau setat gresit.\n"
                     "  - Incearca alt index cu 'input_device' din lista de mai sus.")

    print(f"\nNivel maxim (peak RMS): {peak:.4f}   ·   prag vad_energy: {thr}")
    if peak < 0.002:
        print("\n[!] SEMNAL ~ZERO — microfonul nu capteaza nimic. Cauze probabile:")
        print("   1. Windows Settings > Privacy & security > Microphone -> activeaza")
        print("      'Let apps access your microphone' SI 'Let desktop apps access...'.")
        print("   2. Microfon gresit: seteaza 'input_device' la indexul corect (lista de sus)")
        print("      in data\\voice_bridge.json.")
        print("   3. Microfon mut / volum 0 in Windows > Sound > Input.")
        return 1
    elif peak < thr:
        rec = max(0.002, round(peak * 0.5, 4))
        print("\n[!] Semnal prezent, dar SUB prag — EMA nu-l considera 'vorbire'.")
        print(f"   Coboara pragul: pune  \"vad_energy\": {rec}  in data\\voice_bridge.json.")
        cfg["vad_energy"] = rec           # continuam faza 3 cu prag temporar mai mic
    else:
        print("[OK] Microfonul capteaza bine (peste prag).")

    # ── Faza 3: pipeline complet (record → whisper → wake) ──
    print("\nFAZA 3 — test complet. La ENTER, spune clar: 'EMA, care e statusul'")
    try:
        from .audio import Microphone
        from .stt import Transcriber
    except Exception as e:
        print(f"(sar faza 3 — lipsesc dependinte: {e})")
        return 0
    input("   Apasa ENTER, apoi vorbeste...  ")
    mic = Microphone(cfg)
    audio = mic.record_utterance()
    if audio is None or len(audio) == 0:
        print("\n[!] EMA nu a detectat vorbire (VAD). Coboara 'vad_energy' sau verifica device-ul.")
        return 1
    print(f"   (inregistrat {len(audio)/sr:.1f}s) — transcriu cu Whisper (prima data e mai lent)...")
    try:
        text = Transcriber(cfg).transcribe(audio)
    except Exception as e:
        return _fail(f"[EROARE] transcriere esuata: {e}\n  Ruleaza setup_voice_bridge.bat.")
    print(f"\n   STT a auzit: '{text}'")
    if not text.strip():
        print("   [!] Whisper n-a inteles nimic — verifica limba (language) si modelul (stt_model).")
        return 1
    hit, rest = normalize.strip_wake_name(text, cfg.get("wake_name_variants"))
    if hit:
        print(f"   [OK] Numele 'EMA' detectat! Comanda inteleasa: '{rest or '(doar numele)'}'")
        print("\n=== Totul functioneaza. Porneste EMA si vorbeste-i. ===")
        return 0
    print("   [!] Numele 'EMA' NU a fost detectat la inceputul frazei.")
    print("      - Spune 'EMA' clar, PRIMUL cuvant, apoi comanda.")
    print(f"      - Sau adauga cum a auzit Whisper in 'wake_name_variants' "
          f"(acum: {cfg.get('wake_name_variants')}).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
