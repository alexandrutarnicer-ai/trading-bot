# AI Engine — motorul de trading autonom bazat pe AI

**Versiune:** 0.3 · **Status:** experiment pe cont DEMO · **Cost de rulare:** $0 (LLM local; surse API optionale)

## Surse AI multiple (v0.3) — consiliul pe mai multe "creiere"

Rolurile consiliului se pot distribui pe surse AI diferite, configurabile din
tab-ul AI Engine → cardul **Surse AI**: Ollama (local, gratuit, sursa default),
Claude (SDK oficial), Google Gemini (are free tier) si orice API compatibil
OpenAI (ChatGPT, Groq, DeepSeek, Mistral, xAI, OpenRouter...). Detalii de
proiectare: [PLAN_SURSE_AI_MULTI_PROVIDER.md](PLAN_SURSE_AI_MULTI_PROVIDER.md).

- **Failover automat:** daca sursa unui rol pica, rolul trece pe urmatoarea
  sursa sanatoasa, apoi pe Ollama. Pauze pe tip de eroare: quota epuizata → 6h,
  rate limit → 60s (sau Retry-After), retea → 2min, cheie invalida → DEZACTIVAT
  pana la retest manual. Revenirea e automata la expirarea pauzei.
- **Testeaza** per sursa: verifica lantul complet (reachable → auth → JSON valid)
  si afiseaza latenta sau motivul exact al esecului.
- **Hot-reload:** schimbarile (surse, roluri, chei) se aplica la urmatorul
  consiliu — fara restart de motor.
- **Audit:** transcriptul fiecarui consiliu inregistreaza per rol `_provider`,
  `_latency_s` si `_fallback_from` (daca a fost substituit).
- **Chei API:** local in `data/ai/providers.json` (gitignored), mascate in UI,
  trimise doar catre providerul respectiv. Cheie Gemini gratuita: aistudio.google.com.

Motor complet separat de botul pe reguli: analizeaza singur pietele, isi alege
strategia in functie de context (trend, structura, volatilitate, stiri), dezbate
fiecare decizie intr-un "consiliu de traderi AI" si executa DOAR pe cont demo,
cu rails de risc hard. Contextul si decizia de arhitectura: [AI_ENGINE_FEASIBILITY.md](AI_ENGINE_FEASIBILITY.md).

## Pornire

```bash
start_ai_engine.bat        # dublu-click: porneste Ollama + motorul
# sau manual:
python -m ai_engine        # necesita MT5 deschis pe cont DEMO + Ollama pornit
```

Verificari si rapoarte:

```bash
python -m ai_engine.selftest    # 21 verificari, include un consiliu LIVE pe Ollama
python -m ai_engine.report      # scorecard + ultimele decizii + outcomes
python -m ai_engine.report --councils   # + transcripturile dezbaterilor
```

## Cum functioneaza

```
la fiecare bara M15 (gratuit, local, fara AI):
  PERCEPTIE  — snapshot numeric per piata: trend M30/D1/W1, RSI, ATR+percentila,
               swinguri (S/R), range 20 bare, randamente, calendar ForexFactory
       │
  TRIGGERS   — consiliul AI se convoaca DOAR daca:
               regime flip M30/D1 · tensiune de breakout (<0.5 ATR de extrema)
               · spike volatilitate (ATR>p90) · stire High impact in <60 min
               · review pozitie deschisa (4h) · heartbeat (minim 1/zi/piata)
       │ (daca da)
  CONSILIU AI — 4 roluri, 4 apeluri LLM secventiale (qwen3:8b local pe RTX 4060,
               ~25-60s total), fiecare vede concluziile celui dinainte:
                 1. Analist Tehnic    — structura, trend, niveluri
                 2. Analist Macro     — stiri, sesiune, risc de eveniment
                 3. Risk Manager      — provocatorul; VETO absolut pe deschideri
                 4. Head Trader       — decizia finala, strict JSON
       │
  RAILS HARD — geometria SL/TP corecta · RR ≥ 1 · SL ≤ 5×ATR · stop zilnic -3R
               · risc ≤ 1% · expunere ANGAJATA ≤ 3 (pozitii + ordine pending, nu
                 doar pozitii — vezi mai jos) (orice ar cere LLM-ul)
       │
  EXECUTIE   — ordine market/stop pe MT5, DOAR cont DEMO (verificat la conectare),
               magic 770015 + comment "AI-{id}" — invizibil pentru botul pe reguli
       │
  LEDGER     — SQLite data/ai/ledger.db: snapshot + transcript complet + decizie
               + outcome real (R, pnl). Telegram la fiecare ordin/inchidere.
```

**De ce trigger-uri, nu consiliu la fiecare bara:** un trader profesionist
monitorizeaza continuu dar isi reface teza doar pe evenimente. Asa obtinem
reactivitate M15 cu volum LLM de ~cateva consilii/zi/piata — gratuit si fara zgomot.

## Cadenta si timing

- **Bucla:** motorul se trezeste la fiecare inchidere de bara M15 (`:00:05, :15:05,
  :30:05, :45:05`). Perceptia foloseste ultima bara INCHISA (offset -2), deci datele
  sunt proaspete. Intre bare doarme (`_sleep_to_next_bar`).
- **Per bara:** proceseaza pietele SECVENTIAL. Fiecare piata: perceptie (gratuit) →
  triggers → daca s-a declansat, consiliu (LLM). Cooldown 120 min/piata limiteaza la
  ~cateva consilii/zi/piata. Un ciclu tipic cu 0-2 consilii dureaza < 2 min.
- **Buget de timp consiliu (240s):** o sursa cloud lenta nu poate bloca bucla — la
  depasire, consiliul returneaza WAIT si motorul trece mai departe. Daca un ciclu
  depaseste totusi 15 min, `_sleep_to_next_bar` se auto-corecteaza (sare la urmatoarea
  bara, fara drift permanent).
- **Ordinele:** intrarea STOP e calculata din bara inchisa, apoi ajustata la pretul
  LIVE inainte de trimitere (`adjust_stop_bracket`). Ordinele stop neactivate expira
  dupa `decision_valid_bars` (8 bare = 2h M15).
- **Cati markets?** perceptia e gratuita, deci limita e data de timpul de consiliu.
  5-7 piete sunt confortabile pe Ollama local (worst-case toate convoaca odata =
  ~7 × 60s = 7 min < bara de 15 min, cu bugetul de 240s ca plasa). Peste ~10 piete pe
  o singura sursa locala, riscul de a depasi bara creste — distribuie rolurile pe mai
  multe surse (cloud) sau creste `council_cooldown_min`.

## Inchidere weekend (piete FX/indici)

Pentru pietele FX/indici (cripto exceptat), motorul se opreste pentru weekend automat,
DETERMINIST (nu depinde de LLM):
- **Vineri** de la `weekend_close_hour` (default 22:00, ora RO) + toata Sambata si
  Duminica: motorul inchide pozitia AI + anuleaza ordinele pending pe acel simbol si
  NU deschide nimic (sare consiliul).
- **Luni** deschiderea se reia automat.
- **Cripto** (XRPUSD, BTCUSD...) ruleaza non-stop — `executor.is_crypto` le detecteaza
  dupa nume si le exclude de la inchiderea de weekend.
- Config: `weekend_close_enabled` (default true), `weekend_close_hour` (default 22).
  Foloseste ora Romaniei (`now_local`), deci e corect indiferent de fusul masinii.

## Expunere angajata (cold-start)

Rail-ul `max_open_positions` (default 3) numara pozitii deschise **+ ordine pending**
(`n_committed`). La prima pornire (ledger gol) heartbeat-ul convoaca TOATE pietele
deodata; fara acest contor, s-ar plasa cate un ordin stop per piata (ex: 5 ordine),
toate cu 0 pozitii deschise. Numarand si pending-urile, expunerea totala e plafonata la
3, iar ordinele se plaseaza secvential (contorul creste pe masura ce se plaseaza).

## Dashboard — tab-ul AI Engine

Tab dedicat in UI (intre Profile si Notificari): buton **Pornește/Oprește**, scorecard
(decizii / WAIT / trades / R total / expectancy), editor de piete (validate contra MT5
la salvare), lista deciziilor cu **motivatia + transcriptul complet al dezbaterii**
(click pe decizie), tabel outcomes, log-ul motorului si erorile recente. API:
`/api/ai/status|start|stop|decisions|council/{id}|outcomes|config|logs`.

## Instalare pe alt dispozitiv (laptop)

```bash
setup_ai_engine.bat    # instaleaza Python + Ollama + model + ruleaza verificarile
```

Pe laptop fara GPU dedicat: `"model": "qwen3:4b"` in config + `ollama pull qwen3:4b`.

**⚠ Un singur dispozitiv ruleaza motorul la un moment dat.** Daca ambele PC-uri se
conecteaza la ACELASI cont MT5 demo si ruleaza motorul simultan:
- fiecare instanta plaseaza ordinele ei → expunere dublata, pozitii care se calca;
- ambele partajeaza acelasi namespace magic (770015), deci fiecare vede si poate
  inchide pozitiile celeilalte → haos.
Inainte de a porni motorul pe PC-ul nou, **opreste-l pe cel vechi** (tab AI Engine →
Oprește, sau `python -m ai_engine` inchis). Config-ul (`ai_engine/config.json` +
`data/ai/providers.json` cu cheile) se copiaza intre PC-uri — asa se "mostenesc"
sursele AI; e normal si corect. Doar rularea simultana e problema.

**Nota "5 ordine deodata la prima pornire":** e comportament asteptat — la ledger gol,
heartbeat-ul convoaca toate pietele in prima bara. Expunerea e totusi plafonata la
`max_open_positions` (3) prin contorul de expunere angajata (pozitii + pending).

## Configurare — `ai_engine/config.json`

| Camp | Default | Ce face |
|---|---|---|
| `markets` | EURUSD, USDJPY, GBPUSD, AUDUSD, USDCAD | pietele urmarite — alese pentru cont ~$1000 la 1:30 (risc lot minim $2-4, marja $33-45; XAUUSD/BTCUSD/US30 NU incap: risc $12-16 sau marja $260-310/pozitie) |
| `model` | `qwen3:8b` | modelul Ollama (schimbabil fara cod) |
| `mode` | `demo` | `demo` = ordine reale pe cont demo; `shadow` = doar log |
| `risk_pct_default` / `risk_pct_max` | 0.5% / 1% | risc per trade (clamp hard 2%) |
| `max_open_positions` | 3 | pozitii AI simultane (clamp hard 6) |
| `max_daily_loss_R` | 3.0 | stop zilnic — sub -3R nu mai deschide |
| `heartbeat_hours` | 24 | minim un consiliu/piata/zi |
| `council_cooldown_min` | 120 | minim intre consilii pe aceeasi piata |

Rails-urile din `config.py` sunt clamp-uri **hard** — consiliul poate cere mai
putin risc, niciodata mai mult.

## Siguranta

1. **DEMO enforced** — `executor.connect()` refuza orice cont non-demo (RuntimeError).
2. **Namespace izolat** — filtrare stricta pe `magic=770015`; motorul nu vede si nu
   atinge pozitiile botului pe reguli, si invers.
3. **Veto-ul Risk Manager e absolut** — codul il aplica (`council._sanitize`), nu
   buna-vointa modelului.
4. **Fail-safe LLM** — orice eroare de model/JSON → decizie WAIT; motorul nu
   tranzactioneaza niciodata pe o dezbatere corupta.
5. **Rails inainte de orice ordin** — `executor.validate_decision` respinge geometrie
   gresita, RR mic, SL aberant, depasiri de limite — indiferent ce a decis consiliul.
6. **Rail de marja** — ordinul e respins daca marja necesara depaseste 40% din marja
   libera a contului (protejeaza contul mic de pozitii disproportionate).
7. **Reconectare automata MT5** — daca toate pietele esueaza intr-o iteratie (terminal
   inchis/restartat), motorul reconecteaza singur si notifica pe Telegram.

## Evaluare — cand stim daca "creierul" are valoare?

Totul se scrie in `data/ai/ledger.db`. Dupa o perioada de demo (recomandat: minim
2-3 luni / 50+ decizii executate), scorecard-ul (`python -m ai_engine.report`)
raspunde cu date: expectancy R, win rate, calitatea deciziilor WAIT. Abia atunci
se discuta upgrade-ul creierului (model mai mare / Claude API — o linie in config)
sau renuntarea. Acelasi standard ca la M0: dovada, nu impresie.

## Limite cunoscute (v0.1)

- **Modelul local (8B) e semnificativ sub modelele frontier** la rationament
  financiar nuantat. Acesta e costul lui "gratuit". Arhitectura permite upgrade
  prin config, fara rescriere.
- Calendarul ForexFactory e best-effort (fallback: snapshot fara stiri).
- Sentiment din headline-uri / alte surse AI externe: neimplementat in v0.1.
- Nu exista inca panou in dashboard — raportarea e CLI + Telegram. (Candidat v0.2.)
- Pozitiile deschise sunt gestionate prin SL/TP setate la intrare + review de
  consiliu la 4h; nu exista trailing automat.
