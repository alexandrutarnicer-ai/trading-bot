# Punte Telegram → App → Claude

Daemon standalone care iti permite sa comanzi botul de trading **de pe telefon**,
prin chat-ul Telegram existent: comenzi instant de stare, intrebari rapide catre
sursele AI, si — optional — sesiuni complete de Claude Code (citire cod, teste,
rapoarte, iar cu confirmare, modificari).

> **Nu afecteaza sistemul live.** Puntea e un proces separat, complet aditiv. Nu
> modifica niciun fisier al botului/motorului/API, nu deschide o a doua conexiune
> MT5, nu scrie in ledger. Citeste doar fisiere de stare (`data/ai/status.json`,
> `data/*.pid`) si API-ul local prin HTTP. E singurul consumator de `getUpdates`
> din proiect (tot restul codului trimite doar `sendMessage`).

---

## Pornire

Trei moduri:
- **Din UI (recomandat):** Profil → cardul **„Punte Telegram — chat colaborare"** →
  butonul *Pornește puntea*. Apare doar daca Telegram e configurat.
- **Autostart la boot:** acelasi card → toggle *Pornire automată la boot* (dezactivat
  implicit; cere UAC — creeaza task-ul `TradingBot-TelegramBridge`, neelevat).
- **Manual:** dublu-click `start_telegram_bridge.bat` sau `py -m telegram_bridge`.

La pornire iti trimite pe Telegram un mesaj cu starea puntii (whitelist, nivele
active, daca a gasit Claude CLI, daca scrierea e activata). Oprire: `Ctrl+C` sau
butonul *Oprește puntea* din UI.

**API (folosit de UI):** `GET/POST /api/telegram-bridge/{status,start,stop}` +
`/autostart/{status,enable,disable}`. Status: running, pid, configured, idle,
allow_writes, claude_detected, matrix_enabled.

## Mod EDIT de la distanta (fix critic de pe telefon)

Modificarile de cod (`claude!`) sunt **OFF implicit**. Le poti activa de pe telefon,
doar cat ai nevoie, cu o comanda:
- `/edit on` — activeaza modul EDIT (persistat, aplicat live, fara restart).
- `/edit off` — inapoi la read-only.
- `/edit` — arata starea curenta.

Whitelist-ul te-a filtrat deja (doar chat-ul tau), deci doar tu poti apela `/edit`.
Fluxul de scriere ramane in 2 pasi: `claude! <cerere>` → plan + cod → `CONFIRM <cod>`.

### Editor de REZERVA gratuit (cand Claude nu e disponibil)

Daca Claude CLI e indisponibil (nelogat/quota), `claude!` foloseste automat un
**editor liber** ca rezerva — comanda `/editors` arata ce e disponibil:
- **Aider** (recomandat, gratuit, open-source): `pip install aider-chat`. Foloseste
  cheile tale AI existente — implicit `groq/llama-3.3-70b-versatile` (cheia `groq`
  gratuita e injectata automat din `data/ai/providers.json`). Editeaza fisiere +
  face commit. Model schimbabil din `aider_model`.
- **Copilot** (agentic CLI, daca il ai instalat).

Flux: `claude!` → Claude indisponibil → „folosesc «aider»" + cod → `CONFIRM <cod>` →
editeaza direct cu Aider. Nu inlocuieste Claude; e plasa de siguranta pentru fix critic.

## Mod inactiv (economie / performanta)

Puntea foloseste **long-polling** — cand nu vin mesaje, blocheaza pe socket
(~zero CPU) si se trezeste **instant** la primul mesaj. Dupa `idle_sleep_after_s`
(default 1h) fara mesaje marcheaza starea „inactiv" (vizibila in UI) fara sa
piarda din reactivitate. Practic: e deja modul „sleep care se trezeste la mesaj".

**Verificare offline (fara Telegram/MT5/Claude):**
```bat
py -m telegram_bridge.selftest
```

---

## Ce chei / credentiale sunt necesare

| Ce | Unde | Necesar pentru |
|----|------|----------------|
| **Token Telegram + chat_id** | `data/telegram_config.json` (deja configurat) | tot — puntea le reutilizeaza |
| **Login Claude Code** | deja logat pe acest PC (`~/.local/bin/claude.exe`) | nivelul `claude …` (agent complet) |
| **Cheie Anthropic API** (optional) | `data/ai/providers.json` → `claude` + activeaza sursa in tab-ul AI Engine | fallback `claude …` cand CLI-ul pica |
| **Chei surse AI** (deja setate) | `data/ai/providers.json` (cerebras/mistral/gemini/groq…) | nivelul `ai …` + fallback |
| **GitHub Copilot CLI** (optional) | instaleaza `copilot` sau `gh` + extensia copilot | nivelul `copilot …` |

Puntea **nu introduce ea chei** nicaieri — le citeste din fisierele pe care le
gestionezi tu (aceleasi ca restul sistemului). Vezi sectiunea "Activare" mai jos.

---

## Cuvinte cheie

Mesajele **fara** cuvant cheie sunt ignorate (nimic accidental nu porneste ceva).

### Instant (fara AI, <1s)
| Comanda | Efect |
|---------|-------|
| `/status` | bot + motor AI + cont MT5 + pozitii deschise |
| `/raport` | scorecardul motorului AI (W/L, R, expectancy) |
| `/piete` | clasament per piata dupa R |
| `/pauza S7` · `/reia S7` | pauza/reia o sesiune a botului (ca in UI, reversibil) |
| `/reset` | reseteaza firul de conversatie Claude |
| `/ajutor` | lista comenzilor |

### AI rapid (~5-30s) — sursele AI existente
```
ai de ce e XRPUSD pe WAIT?
ai rezuma ce a facut motorul azi
```
Intrebarea + un context compact (scorecard, pozitii, erori, sanatate surse) merge
la prima sursa AI sanatoasa (aceeasi cascada ca motorul). Raspuns in proza.

### Claude (agent complet, read-only implicit)
```
claude analizeaza de ce a picat S7 azi si ruleaza testele relevante
claude+ si compara cu saptamana trecuta        (continua ultima conversatie)
```
Ruleaza `claude -p` headless in `C:\trading-bot`, cu **tools reale** dar restrictionate
la o allowlist **read-only** (Read/Grep/Glob + comenzi bash de citire/diagnostic:
`git log/status/diff`, `python -m ai_engine.report`, `python scripts/test_*`, …).
Edit/Write si orice actiune de piata **nu sunt in allowlist**, deci sunt refuzate
automat in modul headless. Poti si **sa raspunzi direct** la un mesaj al lui Claude
ca sa continui firul (fara sa mai scrii `claude`).

### Modificari de cod (OFF by default — 2 pasi)
```
claude! adauga un guard pentru cazul X in signal_generator
CONFIRM 428173
```
1. `claude! …` ruleaza intai in **plan mode** (read-only) si iti trimite planul +
   un cod de 6 cifre.
2. `CONFIRM <cod>` (in 5 min) reia sesiunea planului in mod scriere si il executa.

Activat doar cu `"allow_writes": true` in `data/telegram_bridge.json`. **Recomandat
sa il lasi oprit** pana ai incredere in flux (o saptamana de folosire read-only).

---

## Lant de fallback pentru `claude …`

1. **Claude Code CLI** (cu tools de repo) — primar.
2. **Claude API direct** (sursa `claude`) — degradat: raspunde din context injectat,
   fara acces la fisiere. Doar daca CLI-ul lipseste/pica.
3. **Sursele AI existente** (cerebras/mistral/ollama…).
4. **Mesaj onest** — doar comenzile locale disponibile.

Fiecare raspuns spune pe ce nivel/sursa a fost generat (`— via Claude Code · $0.01 · 3 ture`).

---

## Securitate

- **Whitelist HARD**: doar `chat_id`-ul tau (din `telegram_config.json`, sau lista
  `allowed_chat_ids`). Orice alt expeditor e ignorat + o alerta catre tine.
- **Read-only implicit**: allowlist de tools fara Edit/Write; scrierea e gated de
  `allow_writes` + confirmare in 2 pasi cu cod si expirare 5 min.
- **Un singur task greu simultan** (`single_task`); restul primesc "ocupat".
- **Timeout 10 min** per task Claude.
- **Mesaje vechi ignorate**: la pornire/dupa downtime, comenzile mai vechi de 3 min
  nu se executa (nu ruleaza comenzi "statute").
- **409 Conflict**: daca ruleaza doua instante ale puntii, a doua se opreste singura.

---

## Configurare

Optionala — totul are default-uri in `telegram_bridge/config.py`. Ca sa suprascrii,
copiaza `telegram_bridge/config.example.json` la `data/telegram_bridge.json`
(gitignored) si editeaza. Campuri utile:

```json
{
  "allow_writes": false,          // activeaza modificarile de cod (2 pasi)
  "copilot_enabled": false,       // activeaza nivelul "copilot ..."
  "level_ai_enabled": true,
  "level_claude_enabled": true,
  "claude_timeout_s": 600,
  "allowed_chat_ids": []          // gol = chat_id-ul din telegram_config.json
}
```

Restart-ul puntii aplica schimbarile.

---

## Fisiere

```
telegram_bridge/
  config.py       — defaults + data/telegram_bridge.json
  telegram_io.py  — getUpdates long-poll + sendMessage + chunking + stare persistenta
  status.py       — citeste starea (status.json, pid-uri, API local) — read-only
  commands.py     — comenzile instant
  ai_fast.py      — nivelul "ai ..." (ProviderRegistry existent)
  executors.py    — Claude CLI + fallback + Copilot
  router.py       — rutare, confirmare 2 pasi, single-task
  bridge.py       — bucla principala
  selftest.py     — verificari offline
start_telegram_bridge.bat
data/telegram_bridge.json         — config (gitignored)
data/telegram_bridge_state.json   — offset + sesiuni + confirmari (gitignored)
data/telegram_bridge.log          — log (gitignored)
```

## Autostart (Task Scheduler)

Din UI (cardul Punte → toggle) sau manual:
```powershell
& "c:\trading-bot\scripts\setup_autostart_bridge.ps1"    # ca Administrator
& "c:\trading-bot\scripts\remove_autostart_bridge.ps1"   # dezactivare
```
Creeaza task-ul `TradingBot-TelegramBridge` neelevat (`-RunLevel Limited`, la login,
+60s). Dezactivat implicit. Puntea nu are nevoie de MT5/Ollama.

---

## Al doilea canal: Matrix / Element (EU, gratuit) — OPTIONAL

Pe langa Telegram, puntea suporta **Matrix** — protocol deschis, EU (Element,
Londra; folosit de guvernul francez, Bundeswehr, NATO), GDPR, aplicatie de telefon
(Element), API de bot gratuit. **Acelasi Router** = comenzi identice cu Telegram
(`/status`, `ai …`, `claude …`, `/edit …`). Ruleaza intr-un thread separat in
procesul puntii, **off by default**, complet izolat (un esec Matrix nu atinge
Telegram-ul).

### Pasi de configurare pe telefon

1. **Instaleaza Element** (App Store / Google Play) sau deschide app.element.io.
2. **Creeaza cont** pe un homeserver EU. Pentru date in UE recomand un homeserver
   german: la inregistrare, „Edit" → homeserver `https://tchncs.de` (sau
   `https://matrix.org` — Element/Londra, GDPR). Alege user + parola.
3. **Creeaza o camera NEcriptata** doar pentru tine (bot-ul si tu):
   - Element → `+` → *New room* → dezactiveaza **„Enable end-to-end encryption"**
     (IMPORTANT — puntea nu citeste camere criptate) → creeaza.
   - Copiaza **Room ID**: în cameră → *Room info* → *Settings* → *Advanced* →
     „Internal room ID" (arata ca `!AbCdEf:tchncs.de`).
4. **Ia Access Token-ul** (contul din care va raspunde puntea):
   - Element → *All settings* → *Help & About* → jos, *Advanced* → **Access Token**
     → *click pentru a arata* → copiaza (`syt_...`).
   - *(Optional, mai curat: creeaza un cont separat „bot" si invita-l in camera.)*
5. **Pe PC**, pune token-ul in `data/matrix_config.json`:
   ```json
   { "access_token": "syt_...." }
   ```
6. **Pe PC**, in `data/telegram_bridge.json`:
   ```json
   {
     "matrix_enabled": true,
     "matrix_homeserver": "https://tchncs.de",
     "matrix_room_id": "!AbCdEf:tchncs.de",
     "matrix_allowed_users": ["@userul_tau:tchncs.de"]
   }
   ```
7. **Reporneste puntea** (butonul Stop→Start din UI). Iti trimite in cameră
   „🤖 Punte Matrix pornita". Trimite `/ajutor` — merge la fel ca pe Telegram.

**Securitate Matrix:** camera trebuie sa fie DM privat NEcriptat (doar tu + bot);
`matrix_allowed_users` restrange la ID-ul tau. E2E nu e suportat (foloseste camera
necriptata). Token-ul e in `data/matrix_config.json` (gitignored — nu se comite).
