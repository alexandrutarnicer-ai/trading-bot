# AI Engine — motorul de trading autonom bazat pe AI

**Versiune:** 0.1 · **Status:** experiment pe cont DEMO · **Cost de rulare:** $0 (LLM local)

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
  RAILS HARD — geometria SL/TP corecta · RR ≥ 1 · SL ≤ 5×ATR · max 3 pozitii
               · stop zilnic -3R · risc ≤ 1% (orice ar cere LLM-ul)
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
**Un singur dispozitiv ruleaza motorul la un moment dat** (acelasi cont demo — doua
instante s-ar calca pe pozitii).

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
