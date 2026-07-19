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

```bat
:: dublu-click, sau:
start_telegram_bridge.bat
:: sau manual:
py -m telegram_bridge
```

La pornire iti trimite pe Telegram un mesaj cu starea puntii (whitelist, nivele
active, daca a gasit Claude CLI, daca scrierea e activata). Oprire: `Ctrl+C`.

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

## Autostart (optional, mai tarziu)

Pentru pornire automata la boot (ca botul), adauga un task in Task Scheduler care
ruleaza `start_telegram_bridge.bat` neelevat (`-RunLevel Limited`, ca `TradingBot-RunAll`).
Recomandat abia dupa ce fluxul e stabil — pana atunci, pornire manuala.
