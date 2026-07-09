# Raport de noapte — 2026-07-09

Toate task-urile din lista de noapte: status, ce s-a facut, ce necesita actiunea ta.

## ⚠ Actiuni necesare de la tine (dimineata)

1. **Reporneste API-ul** (`python api/main.py` sau `start_ui.bat`) — serverul care ruleaza
   e pe codul vechi; fara restart nu exista tab-ul AI Engine si tabelul Ordine Active in UI.
2. Motorul AI a fost **repornit de mine** cu noile piete — ruleaza acum (verifica tab-ul
   AI Engine dupa restartul API-ului sau `python -m ai_engine.report`).

## AI Engine — task-uri

| # | Task | Status | Detalii |
|---|---|---|---|
| 1 | Eroare 404 in terminal | ✅ REZOLVAT | `ff_calendar_nextweek.json` nu e mereu publicat de ForexFactory — conditie normala, acum logata pe debug (nu mai apare ca WARNING). Calendarul saptamanii curente functioneaza. |
| 2 | AI functioneaza individual | ✅ VERIFICAT | 21 verificari selftest trec; motor separat complet de bot (magic 770015, ledger propriu). |
| 3 | UI complet + On/Off + logs | ✅ FACUT | Tab nou "AI Engine": buton Pornește/Oprește, scorecard, editor piete (validat contra MT5), decizii cu motivatie + transcriptul dezbaterii (click), outcomes, log viewer, erori recente. |
| 4 | AI + MT5 + trades + timezone | ✅ VERIFICAT | **Test ordin real: PASS** — BUY_STOP plasat prin executor (ticket 1798132979, SL/TP/magic corecte), verificat in MT5, anulat. Timezone: toate orele in ora Romaniei (verificat 23:19 PC = 23:16 log). Despre "trades soon": consiliul a luat 4 decizii azi, toate WAIT cu motive sanatoase (FOMC iminent, trend mixt) — disciplina, nu defect. Cu 5 piete si triggers, primele ordine vor veni cand apare un setup clar. |
| 5 | Reports separate | ✅ FACUT | Tot ce face AI sta in `data/ai/ledger.db` + tab-ul AI Engine. Nu se amesteca cu rapoartele botului. Atentie: P&L Real MT5 din Dashboard include tot contul (bot+AI). |
| 6 | Laptop + automatizare | ✅ FACUT | `setup_ai_engine.bat` — instaleaza Python, Ollama, modelul, ruleaza verificarile. Fara GPU dedicat: `qwen3:4b` in config. **Un singur dispozitiv ruleaza motorul odata!** |
| 7 | Error handling | ✅ FACUT | Reconectare automata MT5 (daca toate pietele esueaza), ring buffer de erori afisat in UI, fail-safe LLM → WAIT, rail nou de marja (≤40% din marja libera), heartbeat status.json. |
| 8 | Documentatie RO | ✅ FACUT | `docs/AI_ENGINE.md` actualizat (RO), Ghid tab nou "11. AI Engine", CLAUDE.md. |
| 9 | Analiza + imbunatatiri | ✅ FACUT | (a) **Pietele redimensionate pentru $1000**: XAUUSD/BTCUSD/US30 scoase (risc lot minim $12–16 sau marja $260–310/pozitie la 1:30!) → EURUSD/USDJPY/GBPUSD/AUDUSD/USDCAD (risc $2–4, marja $33–45). (b) Cache calendar 10 min (inainte: 10 fetch-uri HTTP identice/bara). (c) Rail de marja nou. (d) `think:false` pe model (25s/consiliu vs 100s+). |

## Bot existent — task-uri

| # | Task | Status | Detalii |
|---|---|---|---|
| 1 | Toggle Strategia Pullback | ✅ FACUT | Sectiune noua "Strategia Pullback (principală)" in editor, default ON pe toate sesiunile. Gate-uit peste tot (backtest, live, m0). Cu ON comportamentul e identic — **baselines verificate: 284 trades exact**. |
| 2 | Corp Lumânare inlocuit | ✅ FACUT | Inlocuit in UI cu **"3. Trend puternic D1 (ADX > 25)"** — criteriu mai valoros (foloseste coloana f2_adx deja calculata, fara lookahead). Dezactivat implicit → zero impact pe comportamentul curent. Body strength ramane in backend pentru profile vechi. |
| 3 | Praguri 0 criterii | ✅ FACUT | Pragurile Mid/Top/Max accepta acum 0 (0 = nivelul se acorda intotdeauna). Base ramane fara prag (fallback, needitabil) — exact cum ai cerut. |
| 4 | Tabel Ordine Active | ✅ FACUT | Jos in Dashboard: pozitii deschise + ordine pending direct din MT5, cu badge sursa (BOT/AI/MANUAL), marja per pozitie, si sumar: **capital folosit (marja), disponibil, P&L flotant, nivel marja**. Refresh 15s. |

## Teste finale (toate PASS)

- `python -m m0.selftest` — baselines 284 trades + verdicte + integrare API ✅
- `python -m ai_engine.selftest` — 21 verificari, consiliu LIVE (28s, WAIT cu veto corect) ✅
- Test ordin real pe demo: plasat → verificat → anulat ✅
- `npm run build` frontend — fara erori ✅
- Toate routerele API se importa ✅
- Motor AI repornit cu noile piete, heartbeat activ, 4 consilii rulate ✅

## Observatii pentru tine

- **De ce noile 5 piete**: am interogat specificatiile reale ICMarkets pentru contul tau.
  La $1000 cu levier 1:30, gold/BTC/US30 sunt matematic nepotrivite (o singura pozitie
  BTC la lot minim blocheaza $311 marja; gold risca $12 la lot minim = peste plafonul de
  1%). Cele 5 perechi forex permit sizing corect la 0.5% risc. Cand contul creste
  (~$3000+), le putem reactiva din editor.
- **WAIT-urile sunt normale**: consiliul a refuzat azi sa tranzactioneze inainte de FOMC
  Minutes si pe trend mixt — exact ce ai vrea de la un trader uman. Scorecard-ul
  urmareste si calitatea WAIT-urilor in timp.
- Config-ul tau `ai_engine/config.json` a fost actualizat cu noile piete; restul
  setarilor tale raman neatinse.

## Supraveghere peste noapte (adaugat 23:25)

- **Motor AI**: ACTIV (PID nou), heartbeat OK, 4 consilii rulate — toate WAIT cu motive corecte.
- **Ollama**: ACTIV. **Sleep PC**: dezactivat pe alimentare AC (verificat powercfg) — PC-ul nu adoarme.
- **Watchdog nou** (`python -m ai_engine.watchdog`, PID activ): verifica motorul la 5 min;
  daca a cazut → restart automat + notificare Telegram (max 5 restarturi — protectie crash-loop).
  Log: `data/ai/watchdog.log`.
- Butonul Stop din UI opreste acum si watchdog-ul (altfel ar fi reinviat motorul);
  butonul Start le porneste pe amandoua.
