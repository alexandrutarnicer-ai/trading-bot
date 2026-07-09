# Plan: Surse AI configurabile pentru Consiliu (multi-provider) — v2

**Status: IMPLEMENTAT 2026-07-09 (AI Engine v0.3)** — toate punctele de mai jos sunt live.
Contextul curent: AI Engine v0.2 ruleaza consiliul exclusiv pe Ollama local (qwen3:8b),
4 roluri secventiale in `ai_engine/council.py`, provider unic din `ai_engine/providers.py`.

## Obiectiv

1. Sursele de "creier" ale consiliului devin configurabile: Ollama (default, gratuit),
   Claude API, ChatGPT/OpenAI, **Gemini si orice alta entitate** (registru deschis).
2. Rolurile (Analist Tehnic / Analist Macro / Risk Manager / Head Trader) se pot
   **distribui pe surse diferite** — toate pe una, sau impartite oricum.
3. Buton per sursa: Activeaza / Dezactiveaza / **Testeaza** (disponibilitate + contract).
4. Daca o sursa esueaza, UI afiseaza **de ce**.
5. **Failover automat la epuizarea tokenilor/quotei**: rolurile sursei cazute se rerouteaza
   automat la o sursa disponibila sau la default (Ollama), cu revenire automata.

---

## 1. Registru deschis de surse (config)

In `ai_engine/config.json`:

```json
"providers": {
  "ollama":  { "enabled": true,  "type": "ollama",            "model": "qwen3:8b" },
  "claude":  { "enabled": false, "type": "anthropic",         "model": "claude-haiku-4-5" },
  "gemini":  { "enabled": false, "type": "gemini",            "model": "gemini-flash" },
  "grok":    { "enabled": false, "type": "openai_compatible", "model": "...", "base_url": "..." }
},
"role_assignments": {
  "technical":   "ollama",
  "macro":       "ollama",
  "risk":        "ollama",
  "head_trader": "ollama"
}
```

**4 tipuri de adaptor** (clase in `ai_engine/providers.py`, interfata comuna existenta
`chat_json(system, user, required_keys)`):

| Tip | Acopera | Auth |
|---|---|---|
| `ollama` | orice model local | fara, gratuit |
| `anthropic` | Claude (Haiku/Sonnet/Opus) — **SDK oficial `anthropic`** (pip install anthropic), structured outputs native pentru JSON strict | API key |
| `gemini` | Google Gemini (Flash/Pro) — are **free tier** cu quota zilnica | API key |
| `openai_compatible` | OpenAI/ChatGPT, Groq, DeepSeek, Mistral, xAI/Grok, OpenRouter, LM Studio etc. | API key + base_url |

- `openai_compatible` = workhorse-ul extensibilitatii: sursa noua = tip + URL + cheie +
  model din UI, zero cod nou.
- Ollama = **sursa default**: mereu prezenta, nu poate fi stearsa/dezactivata (safety net).
- Chei API: stocate local in `data/ai/providers.json` (NU se comite in git — adauga in
  .gitignore), mascate in UI, trimise doar catre providerul respectiv.

## 2. Distribuirea rolurilor

`council.convene` primeste un **registry** in loc de un provider unic; fiecare rol isi
cauta providerul din `role_assignments`. Engine **reciteste asignarile inainte de fiecare
consiliu** → schimbarile din UI se aplica la urmatorul consiliu FARA restart de motor.
Transcriptul din ledger inregistreaza per rol: `_provider`, `_latency`, si `_fallback_from`
daca a fost substituit.

## 3. Testarea unei surse ("match")

Buton **Testeaza** per sursa (+ automat la pornirea motorului pentru sursele enabled):
prompt de consiliu in miniatura → verifica lantul complet:
reachable → autentificare → JSON valid cu cheile obligatorii → sub timeout.
Rezultat inline: ✓ cu latenta, sau ✗ cu motivul exact (401 cheie invalida / quota /
retea / model refuza JSON).

## 4. Failover automat (mecanismul de sanatate)

Stare de sanatate per sursa, actualizata la fiecare apel:

```
          ┌──────────── SANATOS ────────────┐
          │        (rutare normala)          │
   eroare │                                  │ OK la expirarea pauzei
          ▼                                  │
   Clasificare eroare:                       │
   ├─ quota/credite epuizate → PAUZA 6h ─────┤   (tokenii nu revin repede)
   ├─ rate limit (429)       → PAUZA 60s* ───┤   (*sau cat cere retry-after)
   ├─ retea / server 5xx     → PAUZA 2min ───┤
   └─ cheie invalida (401/403) → DEZACTIVAT ─┘   (FARA auto-retry; omul repara cheia)
```

**Rutare per rol, la fiecare consiliu:**
sursa asignata → daca e in pauza/cazuta: urmatoarea sursa enabled+sanatoasa → **default
(Ollama)** → daca si aia esueaza: WAIT (fail-safe existent — niciodata decizie corupta).

**Revenire automata (lazy):** la expirarea pauzei, urmatorul consiliu incearca din nou
asignarea originala; daca raspunde → rolul revine pe creierul preferat. Zero interventie.

**Vizibilitate:**
- UI: starea pe randul sursei (`⚠ PAUZA — quota epuizata, revine ~14:30`) + rutarea
  efectiva la dropdown-ul rolului (`Risk Manager: Gemini ⚠→ Ollama (temporar)`).
- Telegram: 1 notificare per tranzitie (pauza/revenire), rate-limited.
- Ledger: `_fallback_from` per rol → scorecard-ul poate separa consiliile pe surse.

Sinergie cheie: failover-ul face free-tier-urile utilizabile — Gemini raspunde cat tine
quota zilnica, Ollama acopera silentios restul zilei, revenire automata la resetul quotei.

## 5. UI — cardul "Surse AI" (tab AI Engine)

```
┌─ Surse AI (Consiliu) ──────────────────────────── [+ Adauga sursa] ┐
│ ● Ollama qwen3:8b (local, implicit)   SANATOS      [Testeaza] ✓ 7s │
│ ● Claude claude-haiku-4-5             SANATOS      [Testeaza] ✓ 2s │
│ ⚠ Gemini gemini-flash (free tier)     PAUZA — quota epuizata,      │
│                                        revine ~14:30  [Testeaza]   │
│ ✗ Grok (openai_compatible)            DEZACTIVAT — 401 cheie       │
│    Cheie API: [••••••____] [Salveaza]  invalida     [Testeaza]     │
│                                                                    │
│ Roluri:  Analist Tehnic   [Ollama ▼]                               │
│          Analist Macro    [Gemini ▼]  ⚠ acum: Ollama (temporar)    │
│          Risk Manager     [Claude ▼]                               │
│          Head Trader      [Claude ▼]                               │
└────────────────────────────────────────────────────────────────────┘
```

"+ Adauga sursa": alege tip → nume → model → (base_url daca e compatible) → cheie →
Testeaza. API: extinde `api/routers/ai_engine.py` cu `GET/PUT /ai/providers`,
`POST /ai/providers/test`.

## 6. Costuri estimate (~20 consilii/zi × 4 roluri, ~1.5k in / 0.3k out tokens/apel)

| Asignare | Cost lunar estimat |
|---|---|
| Toate 4 pe Ollama (azi) | $0 |
| 1 rol pe Claude Haiku 4.5 ($1/$5 per MTok) | ~$2 |
| Toate 4 pe Haiku 4.5 | ~$7 |
| Toate 4 pe Claude Sonnet 5 (pret intro) | ~$14 |
| Toate 4 pe Claude Opus 4.8 | ~$36 |
| Gemini free tier | $0 (quota zilnica + failover) |

**Configuratie recomandata la start:** analisti pe Gemini free tier, Risk + Head Trader
pe Claude Haiku (~$4/luna), Ollama safety net. Bonus: API-urile raspund in 1-3s vs ~7s
local → consiliile mixte devin mai rapide.

## 7. Ce NU se atinge

Rails-urile de siguranta (`validate_decision`, marja, DEMO-only, veto-in-cod), executor,
triggers, perception, schema ledger — toate provider-agnostic deja. Config default
(toate rolurile pe Ollama) = comportament identic byte-cu-byte cu azi.

## 8. Pasi de implementare (~1 zi)

1. `providers.py`: clasa de baza + `AnthropicProvider` (SDK oficial) + `GeminiProvider`
   + `OpenAICompatibleProvider`; health state + clasificare erori + cooldowns.
2. `config.py`: schema providers/role_assignments + `data/ai/providers.json` (chei).
3. `council.py`: provider per rol + lant fallback + metadata `_provider/_fallback_from`.
4. `engine.py`: re-citire asignari per consiliu; health in `status.json`.
5. API: `GET/PUT /ai/providers`, `POST /ai/providers/test`.
6. UI: cardul Surse AI (stari, test, add-source, dropdown roluri cu rutare efectiva).
7. Selftest: teste failover cu provider mock care esueaza; test live per sursa enabled.
8. Docs: AI_ENGINE.md + Ghid + CLAUDE.md.

**Nota Gemini:** cheie gratuita la aistudio.google.com.
