# Analiza completă a proiectului Trading-Bot — Etapa 1 (doar analiză)

**Data:** 2026-10-30 · **Branch analizat:** `alex-live` (commit `14ccedb`) · **Mod:** read-only. Nu s-a modificat cod, configurație, date sau strategie. Singurul fișier creat este acest raport.

**Echipa (perspective):** [ENG] Senior Full-Stack/MT5 · [PO] Business Analyst / Product Owner · [TRD] Trader profesionist + știri · [QA] Senior QA MT5.

**Surse verificate:** cod (≈64.000 linii proprii), `CLAUDE.md`, `docs/*`, 339 commit-uri (2026-06-05 → 2026-10-30), `data/live_signals/session*/outcomes.csv` + `ai_filter.jsonl`, `data/ai/ledger.db` (citit read-only), profilul activ `data/active_profile_runtime.json`, `ai_engine/config.json`, `docs/M0_RESULTS.md`, **istoricul real al contului MT5** (`history_deals_get`, citire), API-ul local (`/api/mt5/*`), procesele care rulează pe acest PC.

> Notă metodologică: cifrele „în $” vin din MT5 (sursa de adevăr). Cifrele „în R” vin din `outcomes.csv` (bot) și `ledger.db` (AI). Eșantioanele live sunt mici (57 trade-uri bot, 89–92 AI) — concluziile statistice sunt indicative, nu definitive; acolo unde contează, am calculat semnificația.

---

## A. Executive Summary

**Ce avem:** o platformă de trading complexă — un bot pe reguli (22 sesiuni, 1 piață/sesiune), un motor AI autonom (consiliu de agenți LLM), un filtru AI peste bot, un dashboard web cu 7 taburi, o punte Telegram/Matrix, ~90 de scripturi de research/test — care rulează **pe un cont REAL** ICMarketsEU (#13136652), depus $200 la 2026-07-25, sold actual **$206.09**.

**Rezultatul real în 3 luni (MT5):** 149 tranzacții închise, **net +$6.90 (+3.4%)**.
- **Bot Engine: 57 tranzacții, +$17.64.** Aproape tot câștigul vine din **Inside Bar** (+$14.62 / 41 trade-uri) — un pattern documentat ca „dezactivat implicit, nevalidat în baseline”, dar activ pe toate cele 22 de sesiuni. Strategia principală validată (pullback-in-trend) a dat **−$1.84 / 14 trade-uri**.
- **AI Engine: 92 tranzacții, −$11.53; −20.3R pe 89 trade-uri, expectancy −0.23R** (t ≈ −1.65, p unilateral ≈ 0.05). Octombrie a fost cea mai slabă lună (−16.9R). Încrederea raportată de AI **nu prezice** rezultatul (70–80%: −0.29R; >80%: −0.19R). Rulează pe `qwen3:1.7b`, un model foarte mic (documentația spune `qwen3:8b`).

**Cele mai importante constatări (consens întreaga echipă):**
1. **Bug P0 de date:** la închiderile „news_close” / „vineri_close”, botul scrie `exit_price = 0` (folosește `result.price` din `order_send`, care la ICMarkets vine 0). 13 rânduri au R între −400R și −1553R. `outcomes.csv` raportează **−$12.667** pentru bot, iar MT5 arată **+$17.64**. Rapoartele, statisticile din Dashboard, raportul zilnic Telegram și mesajele „Închis la știre” sunt afectate.
2. **Guvernanță:** auditul statistic M0 (construit chiar în proiect) a dat verdict **DEMOTE** pentru S1, S5, S7, S8, S9, S12, S19 — **toate rulează live pe bani reali**. S7 XRPUSD are cel mai prost verdict (−0.53R, P(edge)=0%) și e cea mai slabă sesiune și live (−$4.68). Uneltele de decizie există, dar verdictele lor nu se aplică.
3. **Configurația live ≠ ce a fost validat:** S1 rulează BOTH (validat LONG), Inside Bar pornit peste tot, break-even pe aproape toate sesiunile, filtru AI pe 17 sesiuni. Fracțiile de capital ale sesiunilor active însumează **324%** din cont. Botul live **nu are** circuit breaker, filtru de corelație sau plafon global de expunere. Acestea există doar în backtest.
4. **Filtrul AI respinge 82% din semnale** (413/501), cu o încredere medie de consens de ~20% și o latență mediană de **104 s** pe semnale M15. Testul contrafactual pe barele MT5 arată că semnalele respinse ar fi dat ≈ **+0.035R/trade înainte de costuri** (330 trade-uri simulate), adică aproximativ zero. Filtrul nu distruge valoare, dar nici nu demonstrează că adaugă. Adaugă însă latență, cost și complexitate.
5. **Complexitatea depășește valoarea:** nucleul strategiei are ~1.100 de linii (strategy + engine), adică <2% din cod. Restul este infrastructură, UI, AI, research și punți de comunicare. `live/signal_generator.py` are 4.315 linii și 64 de funcții. Există 22 de scripturi de sesiune aproape identice. Cele mai multe bug-uri istorice provin din sincronizarea stării locale (`state.pkl`/CSV) cu MT5.

**Recomandarea echipei în 3 propoziții:** (1) Oprim pierderile și corupția de date: reparăm `exit_price`, scoatem AI Engine de pe contul real (îl trecem pe demo/shadow) și oprim sesiunile DEMOTE. (2) Facem din MT5 singura sursă de adevăr pentru rezultate și eliminăm rapoartele paralele bazate pe CSV. (3) Simplificăm: un singur proces de bot cu sesiuni configurate din date, nu 22 de scripturi, un singur nucleu de risc comun pentru Bot și AI și un UI organizat pe „motoare”, care să permită adăugarea ulterioară a Daily și Noisy.

---

## B. Current Architecture

```
                  ┌──────────────────────── MetaTrader 5 (ICMarketsEU, cont REAL, hedging) ────────────────────────┐
                  │  magic 0 + comment "S<n>-SYM-SIG/IB/FLG"  (Bot)        magic 770015 + "AI-<id>"  (AI Engine)     │
                  └────────▲──────────────────────────▲─────────────────────────────────▲───────────────────────────┘
                           │ IPC (1 conexiune/proces)  │                                 │ (citire, pool cache-uit)
   ┌───────────────────────┴─────────┐   ┌─────────────┴──────────────┐      ┌──────────┴─────────────┐
   │ live/run_all.py                 │   │ ai_engine (python -m)       │      │ api/ FastAPI :8000      │
   │  ├─ news_guard (thread)         │   │  perception → triggers →    │      │  14 routere, mt5_pool,  │
   │  └─ 22 × sessionN_*.py          │   │  council (LLM) → rails →    │      │  watchdog, rapoarte     │
   │      → signal_generator.py      │   │  executor; ledger SQLite    │      │  programate (23:30)     │
   │      (state.pkl, signals.csv,   │   │  + watchdog                 │      └──────────▲─────────────┘
   │       outcomes.csv, ai_filter)  │   └─────────────▲──────────────┘                 │ /api/*
   │      └─ ai_engine.trade_filter ─┼─── același ProviderRegistry (Ollama/Gemini/Groq/Nvidia/Mistral/Cerebras…)
   └─────────────────────────────────┘                                          ┌────────┴──────────────┐
            ▲ strategy/ (indicatori, structură, patterns, costuri)              │ frontend React :5173   │
            ▲ engine/ (backtest single/portfolio) ◄── m0/ (audit robustețe)     │ 7 taburi               │
            ▲ adapters/ (CSV / MT5)                                            └────────────────────────┘
   telegram_bridge/ (proces separat, opțional): Telegram/Matrix → comenzi, AI, Claude CLI, Aider
```

**Stare operațională constatată:** pe acest PC rulează doar API, UI (Vite), MT5 și Ollama (~740 MB în total). **Botul și AI Engine rulează pe altă mașină (laptop), pe același cont real.** Datele se sincronizează prin commit-uri git („signals”, „config”, „date”). Pe acest PC, `data/ai/status.json` arată `running:false` din 2026-10-25 și ultima eroare „ollama refused”.

**Stack:** Python 3.14 (pandas, MetaTrader5, FastAPI, scipy), React + Vite + TypeScript + Tailwind, SQLite pentru AI, CSV/pickle/JSON pentru bot.

---

## C. Application Structure

| Modul | Fișiere / linii | Rol | Observații |
|---|---|---|---|
| `strategy/` | 7 / 568 | indicatori, swing, setup pullback, R ladder, patterns (Flag/IB), costuri | nucleul real al strategiei; curat |
| `engine/` | 4 / 527 | backtest (single, portfolio, simulator BE) | conține risk management-ul de portofoliu (circuit breaker, corelație), **absent în live** |
| `adapters/`, `ports/` | 3 / 259, 2 / 18 | CSV/MT5 data source | `ports/` nu e importat nicăieri |
| `live/` | 25 / 6.899 | `signal_generator.py` (4.315 linii), `news_guard.py` (789), `run_all.py`, 22 scripturi de sesiune (~60 linii fiecare) | scripturile diferă doar prin config, care oricum e suprascris de profil |
| `ai_engine/` | 18 / 4.983 | motor autonom + filtru pre-trade + surse AI + consens | bine izolat (magic, demo-guard), dar valoare negativă live |
| `m0/` | 7 / 976 | audit statistic (bootstrap, DSR, fold-uri) | **cea mai valoroasă unealtă de decizie din proiect, subutilizată** |
| `api/` | 26 / 7.196 | 14 routere, pool MT5, notificări, rapoarte programate, watchdog | parte din rapoarte se bazează pe CSV-uri corupte |
| `frontend/src/` | 40 / 15.436 | 7 taburi, 25 componente | `GuidePage.tsx` 2.303 linii; `HistoryPage.tsx` nu e folosit |
| `telegram_bridge/` | 12 / 2.349 | comandă de pe telefon (Telegram + Matrix), Claude/Aider ca editoare | putere mare (scriere cod de la distanță) pe sistem cu bani reali |
| `scripts/` | 89 / 22.213 | 69 research, ~25 teste, setup/autostart, reparații | 35% din tot codul; testele nu au un runner comun |
| rădăcină | backtest*.py, `combined_backtest.py`, `live_runner.py`, `_diagrama_patterns.py`, `_test_patterns.py`, `tz_helper.py`, `live_guard.py`, 10 `.bat`/`.ps1` | — | `combined_backtest`/`_diagrama`/`_test_patterns` nu sunt referențiate; `backtest.py` (rădăcină) e sursa `CONFIG`/`DATA_DIR` pentru API și AI, o cuplare ascunsă |

**Fluxul unui semnal Bot:** bară nouă → `_enrich` (EMA200 M30 trend, EMA 8/20/50, RSI, ATR, swing) → `detect_setup` (pullback) / `detect_inside_bar` / `detect_flag` → criterii opționale → R din ladder → dedup → [Filtru AI] → sizing (`_resolve_order_lots`) → BUY/SELL STOP în MT5 → monitorizare (`_update_outcomes`, BE, știri, vineri) → `outcomes.csv`.

**Fluxul unei decizii AI:** fiecare bară M15 → snapshot numeric (trend, ATR, efficiency ratio, calendar FF) → trigger (breakout_tension 76%, regime_flip 10%, news_window 6%, …) → consiliu (Technical → Macro → Risk[veto] → [Quant] → [Devil] → Head Trader JSON) → încredere = media membrilor ≥ prag 75 → rails (RR≥1, SL≤5×ATR, risc≤1%, max poziții, fără pyramiding, weekend) → ordin stop → ledger.

---

## D. Bot Engine Analysis

### Cum funcționează (simplu)
**Bot Engine caută, pe fiecare piață, o retragere într-un trend deja stabilit și intră când prețul iese din retragere în direcția trendului, cu SL sub/peste retragere și TP la 2.5–5.5R.** Pe lângă asta, pe fiecare piață caută și două pattern-uri secundare: Inside Bar (TP fix 2R) și Flag.

| Element | Valoare actuală |
|---|---|
| Date | bare MT5 închise (entry TF + trend TF), ora RO |
| Trend | EMA200 pe TF superior (M30, H4 sau D1) |
| Structură | 2 HH + HL (long) / 2 LL + LH (short), swing_n, fereastră pullback 6–8 bare |
| Intrare | prima bară care închide peste maximul barei de pullback → BUY STOP |
| Criterii opționale | RSI în interval, aliniere EMA 8>20>50, (ADX D1 / body strength – oprite) |
| SL/TP | SL structural; TP = R din ladder (2.5/3.5/4.5/5.5) după numărul de criterii; IB = 2R fix |
| Risk | `account_fraction` × equity × `risk_pct` (≈1%); opțional lot fix; BE în 3 faze |
| Filtre de timp | ore de sesiune, skip ore/zile, expirare după N bare, închidere vineri, protecție știri (pauză + închidere), Mod Inteligent la știri |
| Execuție | ordine stop GTC, retry pe filling modes, reconciliere MT5 la start (3 straturi) |

### Ce este bun
- [TRD] Logica pullback-in-trend este o idee de trading solidă și clară. Anti-lookahead-ul este tratat corect.
- [ENG] Indicatorii se calculează identic în backtest și live (`_enrich`). Strategia e separată de broker (adapters).
- [QA] Execuția MT5 e robustă la particularitățile ICMarkets (filling 10006/10030, trunchierea comentariului la 16 caractere, hedging position_id, GTC). Aceste lecții au fost plătite scump și trebuie păstrate.
- [PO] Pauza per sesiune, hot-reload pentru `execute_trades` și notificările fac produsul operabil.

### Ce este rău
1. **[QA/ENG] P0 — `exit_price = result.price` = 0** la închiderile forțate (`signal_generator.py:2798` și `:3327`). Calea corectă există deja în cod (`close_deal.price` din istoric, liniile 1329 și 2201), dar nu e folosită acolo.
2. **[TRD] Live ≠ validat.** Baseline-ul S1 (284 trade-uri, LONG) nu mai descrie ce rulează. S1 e BOTH + IB + BE + știri + AI-filter. Fiecare filtru suplimentar e un „trial” nevalidat out-of-sample.
3. **[TRD] Strategia principală nu a câștigat live:** 9 SL / 0 TP la pullback (în R, din outcomes), −$1.84 în MT5. Cu un WR istoric de ~23%, 9 pierderi la rând au probabilitate ~9.5%, deci nu e încă dovadă de eșec, dar nici confirmare.
4. **[TRD/QA] Lipsă de risk management la nivel de cont în live:** 14 procese independente, fără limită zilnică comună, fără corelație (multe sesiuni au expunere USD, JPY sau CAD simultan), fracții de capital care însumează 3.24× equity.
5. **[ENG] Monolit:** `signal_generator.py` concentrează detecția, execuția, reconcilierea, știrile, BE, AI-filter, Telegram și sizing-ul. Orice fix are risc de regresie mare.
6. **[ENG] 22 de procese Python** (fiecare cu pandas și o conexiune MT5 proprie). Estimat 2–3 GB RAM și 22 de clienți IPC pentru o logică ce poate rula într-un singur proces cu o buclă pe sesiuni.
7. **[QA] Starea în `state.pkl`** (pickle, fără scriere atomică documentată) + CSV-uri. Istoric de corupție (chei invalide, duplicate, outcome-uri greșite).

### Ce trebuie schimbat
Fix `exit_price` → risk manager comun la nivel de cont → aliniere config live la ce a trecut M0 → sesiuni ca date (un singur runner) → spargerea `signal_generator` în module (detecție / execuție / reconciliere / protecții).

---

## E. AI Engine Analysis

### Cum funcționează (simplu)
**AI Engine nu folosește strategia botului: își face singur analiza. La fiecare bară M15 calculează un rezumat numeric al pieței. Când apare un trigger (în 76% din cazuri „breakout tension”), convoacă un consiliu de 4–6 roluri LLM care propune un ordin stop. Rails-urile din cod îl validează sau îl resping.** În paralel, același consiliu este folosit ca **Filtru AI** peste semnalele botului (aprobă/respinge).

| Element | Valoare |
|---|---|
| Model | local `qwen3:1.7b` (Ollama) pentru Technical/Macro/Risk; Gemini pentru Head Trader/Quant/Devil; failover pe Groq, Nvidia, Mistral, Cerebras, OpenRouter |
| Convocări | 2.193 consilii în 3 luni; durată mediană 81 s, p90 243 s |
| Decizii | WAIT 68%, OPEN_LONG 27%, OPEN_SHORT 2%, CLOSE 3% |
| Execuție | 173 plasate, 468 respinse de rails, 1.545 sărite (WAIT etc.) |
| Încredere | media rolurilor; prag 75 |
| Filtrul AI (pe bot) | 501 evaluări, 82% respinse, încredere medie consens ~20%, mediană 104 s, 31 depășiri de buget de timp |

### Ce este bun
- [ENG/QA] Izolare excelentă: magic separat, guard de instanță unică, rails cod-enforced („LLM-ul propune, codul dispune”), fail-safe WAIT, ledger complet cu transcripturi. Aceasta este o fundație bună pentru *orice* motor viitor.
- [QA] Rails-urile au prins erori reale (stop pe partea greșită, pyramiding 3× XRP, TP sub RR minim).
- [PO] Transparența (transcripturi, scorecard, raport) este un plus de produs.

### Ce este rău
1. **[TRD] Fără edge demonstrat:** −0.23R/trade pe 89 trade-uri, WR 25%. 69 de ordine au expirat neactivate. Pe piețe: NZDJPY −5.5R, AUDUSD −5.4R, USDCAD −4.5R. Singura excepție este GBPUSD (+2.0R pe 3 trade-uri).
2. **[TRD] Încredere necalibrată:** încrederea mai mare nu duce la rezultate mai bune. Gate-ul pe prag 75 filtrează așadar zgomot.
3. **[TRD] Biais structural:** 76% din trigger-e sunt „breakout tension”, iar ordinele sunt exclusiv stop (breakout). În piețe choppy, breakout-urile false sunt cea mai frecventă pierdere. Fix-ul `regime_aware` (august) nu a oprit deteriorarea din octombrie.
4. **[ENG] Model prea mic pentru rolul cerut:** `qwen3:1.7b` produce JSON invalid și raționamente superficiale. Sursele cloud gratuite sunt instabile (429, 402, 404 „model not found”, 410 Gone, DNS). O mare parte din codul de failover și monitorizare există doar pentru a compensa această instabilitate.
5. **[QA] Latență:** 81–243 s pe o decizie M15 înseamnă că prețul se mișcă între analiză și ordin.
6. **[PO] Pe cont real**, în timp ce config-ul declară `mode: demo` și `live_trading.json` permite `ai_engine: true`. Eticheta „demo” este înșelătoare.

### Ce este util / ce este redundant
- **Util de păstrat:** rails-urile, executorul cu izolare, ledger-ul, `ProviderRegistry` (ca infrastructură), semnalul de regim (efficiency ratio) ca **feature numeric**, nu ca text pentru LLM.
- **Redundant / cost fără beneficiu dovedit:** consens multi-council (3 consilii), rolurile Quant/Devil, editorul de rezervă Aider, monitorizarea a 6+ surse gratuite instabile. Filtrul AI ca gate obligatoriu pe 17 sesiuni (vezi testul contrafactual).

---

## F. Trading Performance Analysis

### Imaginea reală (MT5, 2026-07-25 → 2026-10-30)

| Sursă | Trade-uri | Net $ | Observații |
|---|---:|---:|---|
| **Bot – Inside Bar** | 41 | **+14.62** | pattern secundar, TP fix 2R |
| Bot – Pullback (SIG) | 14 | −1.84 | strategia principală |
| **Bot total** | 57 | **+17.64** | |
| **AI Engine** | 92 | **−11.53** | −20.3R în R |
| **Cont** | 149 | **+6.90** | comision −0.04, swap −0.77 |

Pe lună (net $): Bot iul +2.3 / aug −0.2 / sep +7.1 / oct +8.4 · AI iul +2.6 / aug −3.2 / sep +1.0 / oct −11.9.

Bot pe sesiune (MT5 $): S14 CHFJPY +8.00 (1 trade) · S15 GBPUSD +5.98 (22) · S1 EURUSD +4.30 (3) · S11 USDCAD +1.86 (10) · S16 +1.20 · S5 USDCHF −1.53 · S8 EURCAD −2.35 · **S7 XRPUSD −4.68 (13)**.

### De ce (interpretarea traderului)
- **Bot-ul câștigă din IB cu TP 2R** și pierde la pullback cu TP 4–5R. TP-urile mari ale ladder-ului (media 4.28R la pullback live) cer un WR de ~20% stabil. Pe un eșantion mic, varianța domină. IB cu 2R are WR live ~36%, adică o distribuție mai „netedă”. Aceasta este o observație, nu încă o dovadă: 41 de trade-uri nu sunt suficiente.
- **AI-ul pierde** pentru că joacă aproape doar breakout-uri pe un TF mic, cu un model mic, cu întârziere de minute și cu încredere necalibrată. Pe contul de ~$200, loturile minime fac ca diferențele în $ să fie mici, dar în R pierderea este consistentă.
- **Filtrul AI**: semnalele respinse (simulare pe bare MT5, fără costuri și fără BE) ar fi dat 330 de trade-uri cu +11.5R (+0.035R/trade, WR 32%). După spread/comision, rezultatul ar fi aproximativ zero sau ușor negativ. Concluzie: filtrul a respins în principal trade-uri fără edge, deci **problema este calitatea semnalelor brute, nu filtrul.** Pe sesiuni, filtrul a blocat și trade-uri bune (S1: +18R respinse, S7: +18.5R) și trade-uri proaste (S5: −16R). Nu există un tipar consistent care să arate că AI-ul „știe”.
- **Știrile:** 10 închideri `news_close` + 3 `vineri_close` în MT5. Impactul lor real în $ este mic, dar în CSV apar ca pierderi uriașe din cauza bug-ului. Mod Inteligent (ordine pe știri) este practic inactiv: ForexFactory nu oferă valoarea `actual` în mod fiabil (vezi memoria proiectului).
- **M0 vs live:** cele mai bune sesiuni M0 (S11 KEEP, S14 KEEP, S15 OBSERVE) sunt și cele pozitive live. Cea mai proastă (S7 DEMOTE, −0.53R) este cea mai proastă și live. **M0 a prezis corect direcția**, ceea ce justifică folosirea lui ca gate obligatoriu.

### Pattern-uri
- TP fix moderat (2R) > TP mare pe ladder, la eșantionul actual.
- Crypto (XRP) pe M15 cu această strategie: negativ în backtest și live.
- Sesiunile H1 tranzacționează rar (sub 1 trade/lună), deci aproape nu contribuie.
- AI: deteriorare în octombrie, care coincide cu mai multe trade-uri (47 față de 14–19/lună). Mai multe ordine nu au însemnat mai multă valoare.

---

## G. Historical Problems

| # | Problemă | Cauză | Rezolvat? | A introdus altele? |
|---|---|---|---|---|
| 1 | Outcome-uri greșite / duplicate în CSV | ICMarkets trunchiază comentariul la 16 caractere; hedging position_id ≠ ticket | Da (comment_map, position_id→deals, chei dedup duble) | Da: un ordin vechi cu același prefix a fost asociat greșit unui semnal curent (fix 07-01) |
| 2 | **exit_price=0 la închideri forțate** | `result.price` din `order_send` = 0 | **NU — activ** | Corupe rapoartele, Telegram, statistici |
| 3 | Sesiuni „fantomă” elevate | Task Scheduler cu RunLevel Highest | Da (Limited) | Autostart fără profil → config hardcodat silențios (rezolvat) |
| 4 | 3 instanțe AI Engine simultan → 3× XRP | lipsa guard-ului de instanță | Da (mutex local + PID) | **Rămâne descoperit cross-mașină** (PC + laptop pe același cont) |
| 5 | Paralizie veto 29/29 | veto necalificat al LLM | Da (doar coduri valide) | — |
| 6 | Ollama „reachable dar mort” | instalare coruptă / antivirus | Da (probe + doctor) | — |
| 7 | Bat AI înghețat la boot | `timeout`/`pause` sub Task Scheduler | Parțial (memoria spune „recurent”) | — |
| 8 | Protecția la știri nu se activa sub 5 min | detecție/activare cuplate | Da (redesign 07-17) | FF dă 429 des, Mod Inteligent dormant |
| 9 | Notificare falsă „Ordin Stire EURUSD sâmbătă” | testele trimiteau Telegram real | Da (mock) | Arată riscul testelor fără sandbox |
| 10 | Încredere afișată „90% > prag 85 dar RESPINS” | semantică ambiguă | Da (UI) | — |
| 11 | `execute_trades` citit doar la start | design | Da (hot-reload) | — |
| 12 | Scorecard AI umflat de ordine expirate | `result_r=0` ≠ None | Da (în 2 locuri, de ținut sincron) | Duplicare logică |
| 13 | Groq 403 „1010” | lipsă User-Agent | Da | — |

**Tipar dominant [ENG+QA]:** cele mai multe bug-uri provin din **menținerea unei copii locale a stării de trading** (pending, outcome, P&L) în paralel cu MT5. Fiecare fix a adăugat un strat de reconciliere. Din cele 339 de commit-uri, ~122 sunt fix-uri, iar multe commit-uri recente sunt sincronizări de date între mașini („signals”, „config”, „date”), nu cod.

**Funcționalități începute și abandonate/dormante:** Mod Inteligent la știri (dormant fără Finnhub), canal Matrix (live-netestat), `HistoryPage` (nefolosit), `ports/` (nefolosit), consens multi-council (off), roluri Quant/Devil (off în motor), `voice_bridge`/EMA (pe alt branch), `combined_backtest.py`, scripturi `_diagrama/_test_patterns`, card comisioane AI (prototipat și eliminat).

**Decizii bune:** separarea strategy/adapters, M0 cu bootstrap/DSR, rails cod-enforced, izolarea pe magic, live_guard per componentă, mt5_pool, csv_cache, notificări non-blocante.
**Decizii greșite:** lansarea pe cont real înainte ca M0 să fie gate obligatoriu; activarea IB/BE/AI-filter global fără validare OOS; un proces per sesiune; două mașini pe același cont real; AI pe model 1.7B pe bani reali; rapoarte paralele bazate pe CSV în loc de MT5.

---

## H. Technical Debt

1. **Monolit** `live/signal_generator.py` (4.315 linii, 64 funcții).
2. **22 de scripturi de sesiune** aproape identice. Config-ul lor hardcodat este suprascris de profil, deci există două surse de adevăr, documentate ca o capcană (`session20` hardcodat `False` vs profil `True`).
3. **`SPREAD_DEFAULTS` duplicat de 6 ori** (API, M0, 4 scripturi research), cu un comentariu de tipul „ține-l sincronizat”.
4. **Logică duplicată Bot ↔ AI:** sizing/snap loturi (`_snap_lots_to_broker` vs `executor.snap_fixed_lots`), capital base (`_bot_capital_base` vs `capital_base`), weekend/market-open (3 implementări), scorecard (ledger + fallback API), filling/close robust.
5. **Cuplare ascunsă:** `api/` și `ai_engine/perception.py` importă `CONFIG`/`DATA_DIR` din `backtest.py` (script CLI din rădăcină).
6. **Cod mort:** `HistoryPage.tsx`, `ports/`, `combined_backtest.py`, `_diagrama_patterns.py`, `_test_patterns.py`, `live_runner.py` (folosit doar de un script), `body_strength` (înlocuit de ADX în UI, păstrat în backend), `docs/STARE_PROIECT.md` (oprit în iunie).
7. **Stare fragilă:** pickle + CSV + ~20 de fișiere JSON de stare în `data/`. Lipsește o bază de date unică pentru bot (AI-ul are SQLite).
8. **Teste ca scripturi independente** (~25 de fișiere `test_*.py`, ~600 de aserțiuni declarate în CLAUDE.md). Nu există runner, CI sau lint. Unele teste ating MT5 sau Telegram real.
9. **CLAUDE.md de ~600 de linii** este practic documentația principală a sistemului. Asta arată că sistemul e greu de înțeles fără ea.
10. **Git ca transport de date** între PC și laptop (CSV, ledger exportat). Index-ul curent are staged ștergerea `data/ai/ledger.db`, `live/start_bot.bat` și `ai_engine/start_ai_engine_auto.bat`. **Atenție la următorul commit** (nu am atins nimic).
11. **Resurse:** 22 de procese bot + motor AI + watchdog-uri + news guard + punte + API + Vite + Ollama + MT5. Vite rulează în mod dev, nu build de producție.

---

## I. Product / UX Analysis [PO]

**Taburi actuale:** Dashboard · Profile · AI Engine · Notificări · Audit · Rapoarte · Ghid.

| Problemă | Detaliu |
|---|---|
| „Profile” e de fapt **Bot Engine** | conține editorul de sesiuni și strategie, dar și Telegram, Bridge, Matrix, Live Trading, Capital. Amestecă configurarea motorului cu setările generale |
| Setările globale sunt împrăștiate | Telegram (Profile), Autostart (NavBar ×2), Live Trading (Profile), Surse AI (AI Engine), Capital AI (AI Engine) vs Capital Bot (Profile) |
| Dashboard-ul amestecă Bot + AI + cont | P&L Bot vs MT5 cu toggle de sursă; „Bot” arată acum cifre greșite (bug-ul P0) |
| „Audit” = Backtest + Download date | numele nu spune ce face; este de fapt „Research / Backtest” |
| „Rapoarte” dublează MT5 | Tranzacții / Piețe / Costuri din CSV-uri; Uptime și Modificări sunt utile operațional |
| „Ghid” de 2.300 de linii | semn că produsul nu se explică singur |
| Verdictul M0 nu e vizibil la decizia „execute” | userul poate pune live o sesiune DEMOTE fără niciun avertisment |

**Răspuns la exemplul din brief (reporting/analytics demo):** verificat. Raportarea paralelă a botului din `outcomes.csv` (taburile Rapoarte → Tranzacții/Piețe/Costuri, statisticile „Bot” din Dashboard, raportul zilnic) **nu oferă nimic ce MT5 nu oferă deja corect**. În plus, în prezent oferă cifre **greșite** (−$12.667 față de +$17.64 real). Ce adaugă cu adevărat aplicația peste MT5: **atribuirea pe sesiune/strategie** (cine a deschis trade-ul, cu ce semnal) și **R-ul**. Ambele pot fi derivate din MT5 (comment + SL inițial). **Recomandare: eliminăm raportarea paralelă bazată pe CSV și păstrăm o singură vedere „Performanță” calculată din MT5, cu atribuire pe engine/sesiune/strategie.** `outcomes.csv` rămâne doar ca jurnal tehnic. Dependențe de migrat: `api/routers/reports.py`, `sessions.py` (stats/equity/weekly), `scheduled_reports.py`, `TradingStatsPanel`, `SignalFeed` (USD), `ReportsPage`.

**Structura propusă (consens PO + ENG):**
```
Overview        — cont MT5, P&L real, expunere totală, stare motoare, alerte
Bot Engine      — sesiuni (editor), strategie, backtest/M0 per sesiune, status live    (fostul Profile + Audit)
AI Engine       — motor autonom, piețe, rails, decizii, transcripturi
[Daily Trading] — viitor
[Noisy 1m]      — viitor (research/paper întâi)
Performance     — din MT5, atribuit pe engine/sesiune/strategie (înlocuiește Rapoarte + stats CSV)
Research        — download date, backtest, audit M0, istoric                        (fostul Audit)
Settings        — Profile (seturi de config), Telegram/Bridge, Live Trading, Autostart, Surse AI, Capital
Notifications   — rămâne
Ghid            — redus, contextual (tooltips) + o pagină scurtă
```
Fiecare **Engine** are același schelet: Status · Config · Risk · Activitate · Performanță. Așa Daily și Noisy se adaugă ca engine-uri noi, nu ca taburi speciale.

---

## J. QA / Risk Analysis [QA]

### Riscuri majore (bani reali)
1. **Expunere necontrolată:** 14 sesiuni + AI, fără plafon global de risc, fără corelație și fără limită zilnică pe cont. Un eveniment USD (NFP/CPI) poate deschide simultan 6–8 poziții corelate.
2. **Două mașini, un cont:** guard-ul de instanță unică funcționează doar local. Dacă botul sau AI-ul pornește accidental pe ambele mașini, se dublează ordinele (incidentul 3× XRP s-ar putea repeta).
3. **Date corupte → decizii greșite:** userul vede pe Dashboard/Telegram pierderi false de mii de dolari.
4. **Puntea Telegram cu mod EDIT** poate scrie cod de la distanță pe sistemul cu bani reali. Whitelist-ul pe chat_id este singura protecție a canalului (plus CONFIRM).
5. **Dependență de surse AI gratuite instabile** în fluxul de execuție (filtru strict = fail-closed → semnale blocate; non-strict = fail-open → filtru inexistent).
6. **Starea locală** (pickle) pierdută sau coruptă la oprire forțată.

### Edge cases neacoperite / de verificat
- `order_send` DONE cu `price=0`, `deal=0` (cauza bug-ului P0). Nu există test.
- Închidere parțială / requote / gap peste SL la redeschiderea de luni.
- Restart în timpul unei știri (tranziția `_was_news_paused` se pierde?).
- Simbol cu `volume_min` mare (XRP 100 loturi) + fracție mică → risc real > risc configurat.
- Ceas: server broker vs Europe/Bucharest la schimbarea orei (octombrie/martie).
- Două procese care scriu `notifications.json` / `paused_sessions.json` simultan.
- MT5 reconectat pe alt cont (account_changed) în timpul unei poziții.

### Lipsuri de testare
- Nu există un runner unic (`pytest`) și nici CI. Baselines (284 trade-uri etc.) se verifică manual.
- Nu există un test de **reconciliere MT5 ↔ raportare** (ar fi prins bug-ul P0 în prima zi).
- Nu există un MT5 simulat comun. Fiecare test își face propriul mock.
- Nu există teste E2E pentru UI.

### Strategia de testare propusă
1. `pytest` cu markere `unit` / `mt5_demo` / `slow`. Toate testele existente sunt mutate sub un singur runner, fără efecte externe (Telegram mock-uit global).
2. **Golden baseline tests**: S1 284/S2 1326/S3 rulate automat la orice schimbare în `strategy/` sau `engine/`.
3. **MT5 fake** comun (poziții, ordine, deals, retcodes, `price=0`, filling).
4. **Test de reconciliere zilnic** (job): suma P&L din aplicație == suma P&L din MT5 per magic. Alertă la diferență > $0.50.
5. Teste de regresie pentru fiecare bug din secțiunea G.
6. Mediu demo separat pentru orice schimbare de execuție, înainte de contul real.

---

## K. What Should Stay
- `strategy/` (pullback + patterns), `engine/` backtest, `adapters/`.
- **M0** (devine gate obligatoriu).
- Execuția MT5 robustă (filling, hedging, comment_map, GTC, min stops) și reconcilierea care dă prioritate MT5.
- `live_guard` (DEMO/LIVE per componentă), izolarea pe magic, single-instance.
- AI: rails, executor, ledger, `ProviderRegistry` ca infrastructură, semnalul de regim (ER).
- `mt5_pool`, `csv_cache`, notificări + modul liniște, pauză per sesiune, hot-reload `execute_trades`.
- Protecția la știri (pauză/închidere) pentru evenimentele de impact 3. Este o regulă de risc validă.
- Telegram de bază (status/raport/pauză).

## L. What Should Be Removed (după confirmare)
| Element | Motiv |
|---|---|
| Raportarea paralelă din CSV (Rapoarte → Tranzacții/Piețe/Costuri, stats „Bot” din Dashboard, P&L din outcomes) | MT5 oferă același lucru corect; acum dă cifre greșite |
| 22 de scripturi `sessionN_*.py` | înlocuite de un runner + profil |
| Cod mort: `HistoryPage.tsx`, `ports/`, `combined_backtest.py`, `_diagrama_patterns.py`, `_test_patterns.py`, `body_strength` UI-less | neutilizate |
| Consens multi-council + roluri Quant/Devil + Aider fallback | off sau fără valoare dovedită, complexitate mare |
| Mod Inteligent la știri (ordine pe direcția știrii) | dormant, sursă de date nefiabilă, risc mare pe cont real |
| Canalul Matrix | netestat, duplicat al Telegram |
| AI Engine pe contul real | expectancy negativă (de mutat pe demo/shadow, nu șters) |
| Sesiunile DEMOTE de pe contul real (S1, S5, S7, S8, S9, S12, S19) | M0 + live confirmă lipsa edge-ului |

## M. What Should Be Changed
- Calculul `exit_price` la închideri forțate → din deal-ul MT5. Repararea datelor istorice din MT5.
- Config live aliniat la ce a trecut M0. Orice filtru nou (IB, BE, AI) se activează doar după OOS.
- Risk manager comun la nivel de cont: max risc deschis total, max poziții corelate pe valută, stop zilnic pe cont, plafon de fracție ≤100%.
- Filtrul AI: din gate obligatoriu devine **advisory/log** (scor salvat pentru meta-labeling ulterior) până când datele arată că adaugă valoare.
- Eticheta `mode: demo` a AI-ului trebuie să reflecte contul real.
- Taburile UI (secțiunea I).
- Sincronizarea PC↔laptop prin git → o singură mașină „de execuție”; cealaltă doar dashboard (citește MT5).

## N. What Should Be Consolidated (Bot ↔ AI)
| Comun | Azi | Țintă |
|---|---|---|
| Risk & sizing (capital base, snap loturi, marjă, fixed lots) | 2 implementări | `core/risk.py` unic |
| Execuție MT5 (place/close robust, filling, reconciliere) | 2 implementări | `core/execution.py` |
| Calendar piață (weekend, piață deschisă, crypto 24/7) | 3 implementări | `core/market_hours.py` |
| Știri (guard + perception FF) | 2 consumatori ai FF cu cache-uri diferite | un serviciu de știri |
| Performanță / scorecard | ledger + CSV + MT5 | MT5 + atribuire pe magic/comment |
| Notificări / Telegram | deja comune | păstrat |
| Config | profil JSON + `config.json` + scripturi | un model de config per engine, cu aceeași schemă de bază |
| Constante (SPREAD_DEFAULTS, pip/tick) | 6 copii | un singur modul |

## O. Optimization Opportunities
| Oportunitate | Beneficiu |
|---|---|
| 1 proces bot pentru toate sesiunile (buclă pe bare, o conexiune MT5) | −2 GB RAM estimat, −21 clienți IPC, un singur loc pentru risc global |
| Performanță din MT5 (deja cache-uit în `mt5_pool`) în loc de 40+ CSV | mai puțin I/O, zero divergență |
| Frontend build de producție în loc de Vite dev | RAM/CPU mai mici, pornire mai rapidă |
| AI: mai puține convocări (doar trigger-e cu istoric pozitiv), model local mai mare sau o sursă cloud plătită stabilă | latență și cost mai mici, calitate mai bună |
| Oprirea polling-urilor din UI pentru date eliminate | network mai puțin |
| Un singur `pytest` + golden tests | regresii prinse automat |
| SQLite pentru starea botului (pending/tickets) cu tranzacții | elimină coruperea pickle |

## P. Trading Recommendations [TRD]

1. **Disciplina de validare înaintea oricărei idei:** nicio sesiune sau filtru pe bani reali fără verdict M0 KEEP și fără minimum 30 de trade-uri pe demo/shadow. Numărul de trial-uri (N*) trebuie raportat. Cu 22 de piețe × 3 strategii × multe parametri, overfitting-ul este riscul principal al proiectului.
2. **Inside Bar 2R:** este cel mai promițător rezultat live, dar trebuie trecut prin M0 *separat* de pullback (cum a fost testat în backtest?). Dacă trece, poate deveni strategie de sine stătătoare, nu un „add-on” pe toate sesiunile.
3. **R ladder:** TP-urile de 4.5–5.5R pe M15 sunt rar atinse și cresc varianța. Ar trebui testat out-of-sample un TP plafonat (2–3R) sau un exit parțial. Nu se modifică nimic fără M0.
4. **Știri:** se păstrează pauza + închiderea pentru impact 3 pe valutele perechii. Se renunță la „Mod Inteligent” (tranzacționarea știrii) pe un cont de $200: spread-ul și slippage-ul de la release domină.
5. **AI:** rolul potrivit nu este „trader autonom pe M15”, ci **meta-labeling**: un scor de calitate pe semnalele botului, antrenat pe rezultatele lor (exact recomandarea din `AI_ENGINE_FEASIBILITY.md`, care a fost ocolită). Până atunci, motorul autonom rulează pe demo/shadow.
6. **Risk:** 0.5–1% pe trade este corect, dar trebuie aplicat **la nivel de cont**, cu maximum ~3% risc deschis total și maximum 2 poziții pe aceeași valută în aceeași direcție.
7. **Cont mic ($206):** loturile minime (XRP 100, indici, aur) fac riscul real mai mare decât cel configurat. Piețele trebuie limitate la cele unde lotul minim ≤ riscul țintă.

### Timeframe-uri (răspuns la sugestia 15m/30m · 30m/4h · 1h/1d)
- **15m/30m (actual):** raport 2×. TF-ul de trend este prea apropiat de cel de intrare: EMA200 pe M30 ≈ EMA400 pe M15. Nu oferă o perspectivă cu adevărat superioară. Totuși, este **singura combinație validată pe 8 ani** în proiect, deci nu se abandonează fără date.
- **30m/4h:** raport 8×, are logică. Nu a fost testat în proiect (doar H1/H4 pe S10 și S14).
- **1h/1d:** raport 24×, are logică pentru swing, dar dă ~1 trade/lună/piață (confirmat live: sesiunile H1 aproape nu tranzacționează). EMA200 pe D1 = ~10 luni de lag.
- **Recomandarea traderului:** standardul profesionist (Elder triple screen) folosește un raport de **4–6×** între trend și intrare. Varianta propusă: **trend H4 → confirmare H1 → intrare M15**, ca o singură familie cu 3 niveluri, în loc de perechi independente. Ca alternativă cu 2 niveluri: **M15/H1** și **H1/H4**. Timeframe-urile trebuie configurabile per sesiune (deja sunt: `entry_tf`/`trend_tf`), dar **numărul de combinații testate per piață trebuie limitat la 2–3**, alese pe M0 out-of-sample, nu pe cel mai bun rezultat in-sample.
- **Cât:** o combinație principală per piață (cea validată) + cel mult una secundară. Trei combinații pe aceeași piață triplează trial-urile și riscul de overfitting.
- **Sub M15:** proiectul a testat deja M5/M15 și M1/M5: WR ~16%, DD −80…−95%. Acest lucru este relevant direct pentru „Noisy 1m” (secțiunea Q).

**Dezacord în echipă:** [ENG] ar prefera să păstreze M15/M30 și să adauge doar M15/H1 (cost minim de implementare). [TRD] insistă pe structura pe 3 niveluri (H4/H1/M15) ca țintă pe termen mediu. **Compromis:** se testează întâi M15/H1 și M30/H4 prin M0 pe piețele KEEP, apoi se decide.

---

## Q. Future Architecture (Daily Trading + Noisy 1m)

Principiu: **„Engine” = plugin cu aceeași interfață**, peste un **nucleu comun** de date, risc, execuție și performanță.

```
core/
  data        (MT5 bars, cache, ora RO)          ← adapters/ actual
  risk        (sizing, plafoane cont, corelație, stop zilnic)   ← NOU, comun
  execution   (place/modify/close robust, reconciliere MT5)    ← extras din live + ai_engine
  market_hours, news_service, notifications
  performance (din MT5, atribuire magic/comment → engine/sesiune/strategie)
engines/
  bot_rules   (pullback, IB, flag — sesiuni ca date)   magic 7700xx
  ai_autonomous (shadow/demo până la edge)              magic 770015
  daily       (viitor: D1/H4, 1 decizie/zi)              magic dedicat
  noisy_1m    (viitor: research + paper întâi)           magic dedicat
research/  (backtest, M0 gate, download)
api/ + ui/ (taburi per engine, cu același schelet)
```

- **Daily Trading** se potrivește natural: TF mare, puține decizii, cost de spread mic relativ la SL. Poate folosi chiar AI-ul (latența nu contează la D1).
- **Noisy 1m:** [TRD+QA] avertizează că datele proprii ale proiectului arată că pullback pe M1 eșuează, iar pe un cont de $200 spread-ul + comisionul la SL de câțiva pipși consumă orice edge. Arhitectura trebuie să-l permită (engine separat, magic separat, buget de risc separat, kill-switch), dar **implementarea trebuie să înceapă ca paper-trading/research**, cu un criteriu clar de acceptare (expectancy după costuri > 0 pe OOS).
- Fiecare engine are: magic propriu, buget de risc din risk manager-ul comun, gate M0 obligatoriu înainte de LIVE, aceleași 5 sub-pagini în UI.

---

## R. Prioritized Action Plan

### P0 – Critical (protecția banilor și a adevărului datelor)

| # | Problema | Motiv / Impact | Beneficiu | Complexitate | Dependențe | Risc | Recomandare |
|---|---|---|---|---|---|---|---|
| P0.1 | `exit_price=0` la news/vineri close | rapoarte, Telegram și stats greșite cu mii de $ | date corecte | Mică (folosește deal-ul MT5 / tick ca fallback) | — | Mic | **Fix + script de reparare a celor 13 rânduri din MT5** |
| P0.2 | AI Engine pe cont real cu −0.23R | pierde bani consistent | stop pierderi | Mică (flag `live_trading.ai_engine=false` / shadow) | decizia userului | Niciunul tehnic | **Mutare pe demo/shadow** |
| P0.3 | Sesiuni DEMOTE live (S1, S5, S7, S8, S9, S12, S19) | fără edge în M0, S7 negativă și live | risc mai mic | Mică (toggle observație) | decizia userului | Pierdem trade-uri posibil bune (S1) | **Observație, nu ștergere** |
| P0.4 | Două mașini pe același cont real | ordine dublate posibile | o singură sursă de execuție | Mică (proces) + Medie (lock cross-mașină pe MT5, ex. verificare ordine/poziții proprii la start) | — | Mic | **O singură mașină de execuție** |
| P0.5 | Lipsa plafonului global de risc în live | expunere corelată nelimitată, fracții 324% | protecție la evenimente | Medie | — | Mediu (schimbă comportamentul) | **Risk manager minim: max risc deschis + max poziții/valută** |
| P0.6 | Index git cu ștergeri staged (ledger.db, .bat-uri) | pierdere de fișiere la următorul commit | — | Trivială | — | — | **Userul verifică înainte de commit** |

### P1 – High
| # | Problema | Beneficiu | Complexitate | Risc | Recomandare |
|---|---|---|---|---|---|
| P1.1 | Raportare paralelă din CSV | o singură sursă de adevăr (MT5) | Medie | Mic | Pagină „Performance” din MT5 cu atribuire; eliminare rapoarte CSV |
| P1.2 | M0 nu e gate | decizii pe dovezi | Mică–Medie | Mic | Verdict M0 afișat + avertisment/blocare la „execute=True” pe DEMOTE |
| P1.3 | Config live ≠ validat (IB, BE, BOTH, AI-filter) | știm ce rulează și de ce | Medie (rulări M0) | Mic | Re-audit M0 pe config-ul *actual* per sesiune |
| P1.4 | Test suite fragmentată | regresii prinse | Medie | Mic | pytest + golden baselines + MT5 fake + test de reconciliere |
| P1.5 | Filtru AI ca gate | −latență, −complexitate | Mică | Mic | Mod advisory (log scor), colectare de date pentru meta-labeling |

### P2 – Medium
| # | Problema | Beneficiu | Complexitate | Recomandare |
|---|---|---|---|---|
| P2.1 | 22 de procese + 22 de scripturi | −RAM, risc global posibil, o singură sursă de config | Mare | Runner unic, sesiuni ca date |
| P2.2 | Monolitul `signal_generator.py` | mentenanță, testabilitate | Mare | Spargere în detecție / execuție / reconciliere / protecții (după P1.4) |
| P2.3 | Logică duplicată Bot↔AI | un singur loc de fix | Medie | `core/risk`, `core/execution`, `core/market_hours` |
| P2.4 | Restructurare UI pe engine-uri + Settings separat | UX, pregătire Daily/Noisy | Medie | Conform secțiunii I |
| P2.5 | Stare pickle | robustețe | Medie | SQLite tranzacțional |
| P2.6 | Test TF M15/H1 și M30/H4 prin M0 | posibil edge mai robust | Medie | Doar pe piețele KEEP |

### P3 – Low
| # | Element | Recomandare |
|---|---|---|
| P3.1 | Cod mort (HistoryPage, ports, combined_backtest, _diagrama/_test_patterns) | Ștergere |
| P3.2 | Matrix, Aider, multi-council, Quant/Devil, Mod Inteligent știri | Ștergere sau arhivare pe branch |
| P3.3 | `SPREAD_DEFAULTS` ×6, `CONFIG` din `backtest.py` | Modul comun de constante |
| P3.4 | Ghid 2.300 linii, `STARE_PROIECT.md` învechit, CLAUDE.md 600 linii | Documentație scurtă + tooltips |
| P3.5 | Vite dev în producție | Build static servit de API |
| P3.6 | Script research (69) | Arhivare în `research/` separat de producție |

**Ordinea corectă:** P0 (siguranță + adevăr date) → P1.4 (plasă de teste) → P1.1–P1.3 (sursă unică de adevăr + gate M0) → P2.3/P2.1/P2.2 (consolidare nucleu) → P2.4 (UI) → P3 (curățenie) → abia apoi Daily, apoi Noisy (ca research).

---

## Răspunsuri la cele 19 întrebări

1. **Ce avem?** Un bot pe reguli cu 22 de sesiuni, un motor AI autonom, un filtru AI, un dashboard, o punte Telegram și mult research, totul pe un cont real de ~$206.
2. **Cum funcționează?** Bot: pullback-in-trend + Inside Bar/Flag, cu ordine stop în MT5. AI: snapshot numeric → consiliu LLM → rails → ordine stop. Filtru: consiliul aprobă/respinge semnalele botului.
3. **De ce așa?** A crescut incremental: o strategie validată în iunie, apoi piețe, pattern-uri, AI, punți și UI au fost adăugate rapid, fiecare cu propriile fix-uri.
4. **Ce a funcționat?** Execuția MT5 robustă, izolarea, rails-urile, M0 (care a prezis corect live), Inside Bar 2R (+$14.6).
5. **Ce nu a funcționat?** AI Engine (−20R), pullback-ul live (încă negativ), raportarea din CSV, rularea pe două mașini, filtrul AI ca valoare adăugată.
6. **De ce?** Prea multe idei puse live fără gate statistic. Model AI prea mic și cu latență. Copii locale ale stării în paralel cu MT5.
7. **Ce e inutil?** Raportarea paralelă din CSV, codul mort, Matrix/Aider/multi-council, Mod Inteligent la știri.
8. **Ce e duplicat?** Risk/sizing, execuție, market hours, scorecard, SPREAD_DEFAULTS, 22 de scripturi de sesiune.
9. **Ce păstrăm?** Secțiunea K.
10. **Ce eliminăm?** Secțiunea L.
11. **Ce modificăm?** Secțiunea M.
12. **Ce optimizăm?** Un singur proces bot, performanță din MT5, build UI de producție, mai puține convocări AI.
13. **Probleme tehnice?** Bug-ul exit_price, monolitul, starea pickle/CSV, lipsa unui runner de teste, duplicările, cuplarea cu `backtest.py`.
14. **Probleme de produs?** Taburi denumite după implementare, nu după scop. Setări împrăștiate. Cifre contradictorii (Bot vs MT5). Verdictul M0 invizibil la decizie.
15. **Cum a performat trading-ul?** +$6.90 (+3.4%) în 3 luni, după 149 de trade-uri. Practic breakeven.
16. **Care engine a mers mai bine?** **Bot Engine (+$17.6)**, mulțumită Inside Bar. AI Engine (−$11.5) a consumat jumătate din câștig.
17. **Cele mai mari riscuri?** Expunerea globală necontrolată, două mașini pe un cont, decizii luate pe date corupte, AI pe bani reali, scrierea de cod de la distanță.
18. **Arhitectura viitoare?** Nucleu comun (data/risk/execution/performance) + engine-uri plugin (Bot, AI, Daily, Noisy), UI pe engine-uri + Settings + Performance din MT5. Secțiunea Q.
19. **Ordinea?** P0 → teste → sursă unică de adevăr + gate M0 → consolidare nucleu → UI → curățenie → Daily → Noisy (research).
