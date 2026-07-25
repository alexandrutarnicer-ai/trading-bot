# Jarvis — Asistent vocal (canal vocal peste botul de trading)

**Jarvis** este un asistent vocal local care iti citeste starea botului si a motorului
AI, iti spune scorecardul, clasamentul pietelor, si poate pune/relua sesiuni — **prin
voce**. Implicit in **engleza** (STT precis + wake word „Hey Jarvis" cu model dedicat).

E **al treilea canal** dupa Telegram si Matrix, si se conecteaza la **exact acelasi
Router** (`telegram_bridge.router.Router`) — deci comenzile sunt identice logic;
doar transportul difera:

```
🎙️ "Hey Jarvis" → Whisper (STT) → normalize → Router → Jarvis vorbeste (TTS)
```

> **Aditiv si izolat, ca puntea Telegram.** Proces STANDALONE. Nu importa/modifica
> botul/motorul/API in mod care le schimba starea, nu deschide o a doua conexiune MT5.
> Reutilizeaza logica de comenzi existenta. Ruleaza local.

> **READ-ONLY prin design.** Microfonul nu are whitelist (oricine e langa PC poate
> vorbi), deci canalul vocal e **fortat read-only**: `allow_writes=False` mereu, iar
> normalizatorul nu produce NICIODATA comenzi de modificare (`claude!`, `/edit`).
> Nu poate plasa/inchide ordine, nu poate modifica cod.

---

## Instalare

Dublu-click **`setup_voice_bridge.bat`** (recomandat — instaleaza tot + curata configul
vechi + descarca modelele). Manual:

```bat
py -m pip install faster-whisper sounddevice numpy pyttsx3
py -m pip install openwakeword onnxruntime    REM wake word "Hey Jarvis" (onnx = Windows)
py -m pip install edge-tts                     REM voce neurala (optional, mai buna)
py -c "from openwakeword.utils import download_models; download_models()"
py -m voice_bridge.selftest                    REM verificare offline (fara microfon)
```

- **faster-whisper** — Speech-to-Text local (CPU/GPU CUDA). Prima rulare descarca `base` ~150MB.
- **sounddevice + numpy** — captura microfon.
- **openwakeword + onnxruntime** — wake word „Hey Jarvis" (model pre-antrenat; pe Windows ruleaza pe onnx).
- **pyttsx3** — voce SAPI Windows (zero download; ai deja David/Zira in engleza).
- **edge-tts** (optional) — voce neurala mai buna (`en-GB-RyanNeural`, britanic — ca Jarvis).

## Pornire

Din **UI** (recomandat): Profil → cardul **„Jarvis — asistent vocal"** → *Pornește*.
Sau dublu-click **`start_voice_bridge.bat`** (sau `py -m voice_bridge`).

Implicit ruleaza cu **wake word acustic**: spui **„Hey Jarvis"**, Jarvis raspunde
„Yes?", apoi spui comanda — „**what's the status**", „**the report**", „**pause session
7**". Modelul „hey_jarvis" e dedicat si fiabil (nu depinde de transcrierea numelui).

> **Daca „Hey Jarvis" nu merge** (openWakeWord neinstalat), Jarvis trece automat pe
> **push-to-talk** (apesi ENTER, vorbesti). Vezi *Testare rapida* mai jos.

> **Cand nu vrei sa asculte** (ex: joci pe Discord): **Pauza** — buton in UI sau
> „Jarvis, go to sleep". Vezi *Pauza / mut* mai jos.

---

## Ce poti spune

In modul implicit, incepi cu numele: „**EMA, <comanda>**". (In push-to-talk apesi
ENTER si spui doar comanda.) Normalizatorul (`voice_bridge/normalize.py`) mapeaza fraza
la comanda — vorbesti natural, RO sau EN.

| Spui (dupa „EMA, …") | Face | EMA iti spune |
|---|---|---|
| „cum merge botul" / „status" / „how's the bot" | `/status` | bot + motor AI + cont MT5 + pozitii |
| „raportul" / „scorecard" | `/raport` | scorecardul motorului AI (W/L, R, expectancy) |
| „cum stau pietele" / „markets" | `/piete` | clasament per piata dupa R |
| „pune pe pauza sesiunea 7" / „pause session seven" | `/pauza S7` | confirma pauza |
| „reia sesiunea 3" / „resume session three" | `/reia S3` | confirma reluarea |
| „de ce e XRP pe wait?" (intrebare libera) | `ai <intrebare>` | raspuns de la sursele AI (Ollama etc.) |
| „intreaba claude de ce a picat S7" | `claude <cerere>` | agent Claude read-only (mai lent) |
| „ajutor" / „what can you do" | `/ajutor` | lista comenzilor |
| „culcă-te" / „go to sleep" / „mute" | pauza (mut) | EMA nu mai asculta pana o reiei |
| „trezește-te" / „wake up" | revenire | EMA asculta din nou |
| „exit" / „quit" / „la revedere" | — | EMA se inchide (opreste procesul) |
| „anuleaza" / „cancel" | — | ignora comanda curenta |

Orice fraza care nu se potriveste unei comenzi cunoscute merge automat la **nivelul
AI rapid** (Ollama / sursele existente), deci poti pur si simplu pune intrebari.

---

## Pauza / mut („sunt pe Discord cu prietenii")

Cand nu vrei ca EMA sa asculte (joci, esti in call), o pui pe **pauza** — microfonul
e **oprit complet**, nu transcrie nimic. Trei cai:

1. **Buton in UI** — Profil → cardul „EMA — asistent vocal" → *Pauză (mut)*. Un click
   si tace; alt click (*Reia ascultarea*) si revine. Efect in ~1s, fara restart.
2. **Vocal** — „EMA, culcă-te" (pauza) / „EMA, trezește-te" (revenire, doar daca
   `resume_by_voice` e activat — altfel revii din UI, ca microfonul sa fie chiar oprit).
3. **Stop total** — butonul *Oprește EMA* / „EMA, exit" opreste procesul de tot.

Implicit, revenirea din pauza se face **din UI** (`resume_by_voice: false`), tocmai ca
in pauza microfonul sa fie efectiv oprit — nimic din jocul/discutia ta nu e ascultat.

> **Cel mai „gaming-safe":** seteaza `wake_mode: "ptt"` (push-to-talk). Atunci EMA
> nu aude nimic decat cand apesi ENTER — zero ascultare in fundal.

---

## Limba (RO / EN)

**Implicit `language: "ro"` (romana).** Asta controleaza: (1) limba STT — **fortata**,
nu auto-detect (auto gresea des pe fraze scurte si nu recunostea „EMA"); (2) alegerea
vocii TTS; (3) confirmarile rostite; (4) un hint „raspunde in romana" pentru intrebarile
libere (Ollama raspunde altfel in engleza). Schimba in `en` pentru engleza.

> **Nota:** comenzile instant (`/status`, `/raport` …) raspund cu text **romanesc**
> indiferent de `language` (asa e formatat botul). Cu `language:"ro"` totul e coerent.

## Vocea EMA — fluenta + profil inspirat de Xal'atath

Preset implicit: **`voice_style: "xalatath"`** — voce feminina, ritm rar si deliberat,
cu ton coborat (si reverb „void" pe Piper) pentru vibe-ul sinistru al Harbinger-ului.

> **Nota (copyright):** nu se reproduce vocea *reala* a lui Xal'atath — e o interpretare
> a unui actor, detinuta de Blizzard. Preset-ul e „inspirat de", pe o voce sintetica
> generica intunecata la timbru — NU o clona. Pentru o voce anume, foloseste un
> instrument local de clonare (ex: Coqui XTTS) cu o mostra pe care ai dreptul sa o folosesti.

**De ce „vorbea in engleza"?** Windows-ul tau are adesea DOAR voci SAPI engleze
(Microsoft David/Zira) — nicio voce romaneasca — asa ca text romanesc e citit cu voce
engleza = sunet gresit. Ruleaza `py -m voice_bridge.voices` ca sa vezi ce ai. Fix:

**1. edge-tts (RECOMANDAT) — romana FLUENTA, gratuit, un pip.**
```bat
pip install edge-tts
```
Voci neurale Microsoft (online, fara cheie). EMA foloseste automat **ro-RO-AlinaNeural**
(feminina). Aplic si „lent + grav" din stil (`edge_rate`/`edge_pitch`) pentru vibe-ul
Xal'atath. Cu `tts_engine: "auto"` (implicit) e ales automat daca e instalat. Schimba
vocea cu `"edge_voice": "ro-RO-EmilNeural"` (masculin) etc. *(Online: textul de rostit
merge la serverele Microsoft — status de bot, fara date sensibile.)*

**2. pyttsx3 (SAPI Windows) — offline, zero setup, dar robotic.**
Fallback daca edge-tts lipseste. Alege o voce pt limba ceruta daca exista; daca n-ai
voce romaneasca, te avertizeaza in log. Voce RO offline: Setari Windows → Ora si limba
→ Limba → Romana → Optiuni → adauga „Voce".

**3. Piper (optional) — neural OFFLINE + efect eerie complet (ton + reverb).**
Voce RO: `ro_RO-mihai-medium.onnx`. Pentru vibe-ul complet configureaza Piper:

1. Descarca `piper` (binar Windows) si o voce feminina `.onnx`
   (ex: `en_US-hfc_female-medium`) de pe
   [rhasspy/piper releases](https://github.com/rhasspy/piper).
2. In `data/voice_bridge.json`:
   ```json
   {
     "tts_engine": "piper",
     "piper_binary": "C:\\tools\\piper\\piper.exe",
     "piper_model":  "C:\\tools\\piper\\ro_RO-mihai-medium.onnx",
     "voice_style":  "xalatath",
     "tts_pitch_semitones": -3.0,
     "tts_reverb": 0.28
   }
   ```
   Efectul eerie (`_apply_eerie` in `tts.py`) coboara tonul si adauga reverb usor pe
   WAV-ul de la Piper, inainte de redare. Regleaza `tts_pitch_semitones` (mai negativ
   = mai grav) si `tts_reverb` (0..1) dupa gust.

Alte preset-uri: `"calm"` (feminin, clar, fara efect), `"neutral"` (voce implicita).

---

## Testare rapida (linia de comanda — fara editare JSON)

Cand EMA „nu aude" sau nu raspunde, testeaza modurile din CLI ca sa izolezi problema:

```bat
py -m voice_bridge --ptt        REM push-to-talk: apesi ENTER, vorbesti (cel mai SIGUR)
py -m voice_bridge --debug      REM arata in consola TOT ce transcrie Whisper
py -m voice_bridge --wake=openwakeword   REM varianta "hey jarvis" (wake acustic dedicat)
py -m voice_bridge --lang=en    REM comuta pe engleza pt un test
py -m voice_bridge --device 2   REM forteaza microfonul cu indexul 2 (din miccheck)
```

- **`--ptt`** e cel mai sigur: elimina detectia wake. Daca aici EMA raspunde → tot lantul
  (mic→STT→Router→voce) e OK, si doar detectia numelui era problema.
- **`--debug`** in modul „name" printeaza „Am auzit: '...'" — vezi exact cum transcrie
  Whisper cuvantul „EMA" (si daca il aude ca altceva, il adaugi in `wake_name_variants`).

## Moduri de trezire (`wake_mode` in `data/voice_bridge.json`)

- **`"name"` (IMPLICIT):** spui numele la inceput — „EMA, status". Detectat prin STT,
  deci merge cu numele custom „EMA" **fara** model antrenat. EMA asculta continuu si
  reactioneaza doar cand fraza incepe cu numele ei (`wake_name` + `wake_name_variants`
  acopera transcrierile diverse ale lui Whisper: ema/emma/hey ema…). Cel mai natural.
  Compromis: microfonul e pornit (transcrie ca sa detecteze numele) — de asta exista
  Pauza pentru gaming.
- **`"ptt"` (push-to-talk):** apesi ENTER, apoi vorbesti (fara nume). Zero ascultare
  in fundal — **cel mai gaming-safe**.
- **`"openwakeword"`:** wake acustic cu model **pre-antrenat** (implicit `hey_jarvis`);
  spui „hey jarvis". openWakeWord nu are un model „EMA" gata facut.
- **Wake custom „hey EMA" (avansat):** [Picovoice Porcupine](https://picovoice.ai/)
  genereaza un keyword „hey EMA" (gratuit uz personal) → `.ppn` + access key; necesita
  `pip install pvporcupine` + un mic adaptor in `wake.py` (neinclus). Alternativ,
  antreneaza un model openWakeWord custom.

Daca `wake_mode: "openwakeword"` dar openWakeWord lipseste, cade elegant pe modul „name".

---

## Siguranta

- **Read-only hard:** `config.load_config()` forteaza `allow_writes=False` si
  `copilot_enabled=False`. Nivelul de scriere `claude!` din Router e blocat.
- **Normalizator whitelist:** produce doar `/status /raport /piete /pauza /reia /ajutor`,
  `ai …`, `claude …` (read-only). Testat: `test_no_write_commands` in selftest.
- **Fara whitelist pe microfon** (spre deosebire de Telegram/Matrix): oricine e langa
  PC poate cere starea sau pune o sesiune pe pauza. De asta scrierea e imposibila aici.
- **Un singur task greu** (`single_task`) — ca in puntea Telegram.

---

## Configurare (`data/voice_bridge.json`, gitignored)

Toate au default-uri in `voice_bridge/config.py` (`VOICE_DEFAULTS`). Campuri utile:

```json
{
  "assistant_name": "EMA",
  "wake_mode": "name",           // name / ptt / openwakeword
  "wake_name": "EMA",
  "wake_name_variants": ["ema", "emma", "hey ema", "hey emma"],
  "resume_by_voice": false,      // revenire din pauza si vocal (tine micul pornit)
  "wake_model": "hey_jarvis",    // doar wake_mode="openwakeword"

  "stt_model": "base",           // tiny/base/small/medium
  "stt_language": null,          // null=auto, "en"/"ro" forteaza
  "stt_device": "auto",          // auto/cpu/cuda

  "tts_engine": "auto",          // auto/pyttsx3/piper
  "voice_style": "xalatath",     // xalatath/calm/neutral
  "tts_rate": 150,               // pyttsx3 cuvinte/min
  "piper_binary": "",
  "piper_model": "",
  "tts_pitch_semitones": -3.0,
  "tts_reverb": 0.28,

  "max_utterance_s": 8,
  "silence_s": 1.0,
  "vad_energy": 0.006,
  "input_device": null           // index microfon sounddevice (null=implicit)
}
```

Restart-ul procesului aplica schimbarile.

---

## Autostart Windows (Task Scheduler) — OPTIONAL, dezactivat implicit

Din UI (cardul „EMA" → toggle *Pornire automată la boot*) sau manual:
```powershell
& "c:\trading-bot\scripts\setup_autostart_voice.ps1"    # ca Administrator
& "c:\trading-bot\scripts\remove_autostart_voice.ps1"   # dezactivare
```
Creeaza task-ul `TradingBot-VoiceEMA` neelevat (`-RunLevel Limited`, la login + ~60s;
genereaza `voice_bridge/start_voice_auto.bat`). **Dezactivat implicit.** API: `GET/POST
/voice-bridge/autostart/{status,enable,disable}` (mirror al puntii Telegram).

> **Atentie:** cu autostart activ, EMA porneste microfonul la fiecare login (mod „name"
> asculta continuu). Pune-o pe pauza cand nu vrei sa asculte, sau foloseste `wake_mode:
> "ptt"`. De asta e OFF implicit — tu decizi cand asculta.

## Fisiere

```
voice_bridge/
  config.py        — defaults (peste cele ale Router-ului) + voice_bridge.json; READ-ONLY fortat
  normalize.py     — vorbire → comanda Router (PUR, testabil)
  tts.py           — speakable() + Speaker (pyttsx3 / Piper + efect eerie)
  stt.py           — faster-whisper
  audio.py         — captura microfon + VAD
  wake.py          — push-to-talk / openWakeWord
  voice_client.py  — adaptor .send() pt Router (rosteste in loc sa trimita)
  bridge.py        — bucla principala (limba + confirmari + directiva RO pt AI)
  voices.py        — diagnostic voci TTS („de ce vorbeste EMA in engleza?")
  miccheck.py      — diagnostic microfon („EMA nu ma aude?") — device + nivel + STT
  selftest.py      — verificari offline
start_voice_bridge.bat / setup_voice_bridge.bat
data/voice_bridge.json         — config (gitignored)
data/voice_bridge_state.json   — stare (gitignored)
data/voice_bridge.log          — log (gitignored)
```

## Verificare

```bat
py -m voice_bridge.selftest
```

Testeaza normalizatorul, modelarea textului si garantia read-only — fara microfon,
whisper, TTS sau MT5.

---

## Depanare

- **EMA vorbeste in engleza / nu suna natural** — n-ai o voce romaneasca. Ruleaza
  `py -m voice_bridge.voices` (arata ce ai + recomandarea), apoi `pip install edge-tts`
  pentru romana fluenta. Vezi sectiunea *Vocea EMA*.
- **EMA nu recunoaste ce spui / nu porneste la „EMA …"** — verifica `language` (RO/EN)
  in `data/voice_bridge.json`. STT-ul e fortat pe limba aia; daca vorbesti alta limba,
  nu recunoaste. `stt_model: "small"` e mai bun ca `base` pe romana.
- **Am schimbat un default in cod dar EMA il ignora** — daca ai rulat EMA inainte, ai
  deja un `data/voice_bridge.json` cu valorile vechi (le suprascrie). **Sterge-l** o
  data (`del data\voice_bridge.json`) — se regenereaza minimal cu default-urile noi.
- **„Import esuat … ruleaza setup_voice_bridge.bat"** — lipsesc dependintele
  (`faster-whisper`/`sounddevice`/`pyttsx3`). Ruleaza setup-ul.
- **Nu se aude nimic** — pyttsx3 nu gaseste o voce SAPI. Verifica Windows →
  Settings → Time & Language → Speech. Sau seteaza `tts_voice` la un substring din
  numele vocii.
- **EMA nu ma aude / microfonul nu e detectat** — ruleaza `py -m voice_bridge.miccheck`.
  Iti arata microfoanele, un contor de nivel live (vorbesti si vezi daca capteaza) si
  un test complet (record → Whisper → detectie „EMA"). Cauze frecvente: (1) Windows
  Settings → Privacy & security → Microphone: permite accesul aplicatiilor DESKTOP;
  (2) microfon gresit → seteaza `"input_device"` la indexul corect din diagnostic;
  (3) nivel prea mic → coboara `"vad_energy"` (diagnosticul iti recomanda o valoare).
- **Taie prea repede / prea tarziu** — regleaza `silence_s` (mai mare = asteapta mai
  mult dupa ce te opresti) si `max_utterance_s`.
- **STT lent** — pune `stt_model: "tiny"` sau ruleaza pe GPU (`stt_device: "cuda"`).
- **Feedback (se aude pe sine)** — bucla nu asculta cat vorbeste (`wait_idle`); daca
  totusi apare, foloseste casti sau push-to-talk.
```
