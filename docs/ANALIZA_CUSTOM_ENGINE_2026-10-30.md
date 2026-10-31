# Analiza Custom Engine (fostul tab PROFILE) — Etapa de analiză

**Data:** 2026-10-30 · **Mod:** doar analiză. Nu am modificat cod, configurație sau date. Experimentele de backtest au rulat cu patch-uri aplicate doar în memorie.
**Surse verificate:** `live/signal_generator.py`, cele 22 de scripturi de sesiune, `strategy/`, `engine/portfolio.py`, `m0/`, `api/watchdog.py`, `api/routers/*`, `data/profiles/standard.json` + `test.json`, notificările, logurile de sesiune, istoricul MT5 real (doar citire), backtesturi de control.

---

## 1. Current State — cum funcționează acum

- **Tab-ul Profile** conține:
  - selectorul de profil (există 2 profile: `standard` cu 22 de sesiuni și `test`/„Test1” cu 2 sesiuni);
  - capitalul inițial, sincronizarea cu MT5 și Protecția Capitalului;
  - Telegram, puntea Telegram, Matrix și Live Trading;
  - editorul celor 22 de sesiuni.
- **O sesiune = un script Python separat** (`live/sessionN_*.py`), un proces, o piață și un director de stare (`data/live_signals/sessionN/`). La pornire, profilul suprascrie cele mai multe câmpuri din script prin `_apply_profile_overrides`.
- **Combinații de timeframe existente:**
  - 14 sesiuni M15/M30;
  - 6 sesiuni H1/D1;
  - 2 sesiuni H1/H4 (în profil);
  - **0 sesiuni M30/H4.**
- **Strategii:**
  - Pullback, cu R pe scara ladder 2.5/3.5/4.5/5.5;
  - Inside Bar, cu R fix (2R pe toate);
  - Flag, cu R fix (2R / 2.5R / 1R / 3R, diferit pe sesiuni).
- **Toate setările sunt per sesiune.** Nu există setări globale, cu o singură excepție: Protecția Capitalului, la nivel de profil.

## 2. Problems Found — problemele găsite (verificate)

| # | Problemă | Dovadă | Gravitate |
|---|---|---|---|
| 1 | **Backtestul folosește date din viitor (lookahead) pe trend.** Trendul TF mare se aliniază după ora de *deschidere* a barei, deci o bară H1 „vede” închiderea barei D1 de azi (până la ~23 h în viitor). Filtrele D1/W1 sunt decalate corect, coloana principală `trend` nu. | `strategy/preparation.py::_enrich` (`merge_asof` fără decalaj). Re-rulat cu aliniere la bare închise: **expectancy-ul scade în 8/8 sesiuni** (S5 −0.016→−0.077R, S14 −0.044→−0.115R, S18 +0.010→−0.025R, S1 −0.041→−0.061R). | **P0** — toate deciziile bazate pe backtest/M0 sunt prea optimiste |
| 2 | **S14 CHFJPY (LIVE) rulează pe H1/D1, dar UI-ul, profilul și backtestul spun H1/H4.** `entry_tf`/`trend_tf`/`bar_minutes` nu sunt suprascrise de profil, deci vin din script. La fel S10 (OBS). | `live/session14_chfjpy_h1.py` linia 25 `"trend_tf": "D1"`; lista de override-uri din `_apply_profile_overrides` | **P0** — ce vezi ≠ ce rulează |
| 3 | **Circuit Breaker-ul nu există în live.** Câmpul `circuit_breaker` (3 pe 20 de sesiuni) apare în UI cu tooltip „oprește tranzacționarea după N pierderi”, dar `signal_generator.py` nu conține nicio limită de pierderi. Există doar în backtest. | `grep circuit/consec/halt` în `live/` = 0 rezultate; `engine/portfolio.py:114,195` | **P0** — protecție afișată, dar inexistentă |
| 4 | **Protecția Capitalului e fragilă.** Rulează în watchdog-ul **API-ului**, doar dacă `data/active_profile.json` există (bot pornit din UI, pe aceeași mașină). Doar pune sesiunile pe pauză (nu închide poziții) și nu acoperă AI Engine. Botul pornit prin autostart sau pe laptop fără API = fără protecție. | `api/watchdog.py:107-180` | **P1** |
| 5 | **Treapta 5.5R din ladder nu poate fi atinsă.** Necesită 3 criterii opționale, dar doar RSI + EMA sunt active (ADX și body-strength sunt oprite). | `strategy/signals.py::reward_R`, profil `r_max_threshold=3` | P2 |
| 6 | **„Poziții simultane per piață” se aplică doar pullback-ului.** Inside Bar și Flag au câte un slot propriu → până la `max + 2` poziții pe aceeași piață, plus AI Engine pe același simbol. | `_check_signals` linii 1144-1175 | P1 (pentru regula globală) |
| 7 | **Filtrul AI Strict e pornit pe 18 sesiuni**, iar consiliul depășește bugetul de timp des (31 de evenimente în 3 luni, latență mediană 104 s). Când AI-ul pică, ordinele sunt blocate (7 notificări „STRICT” în ultima lună). | `ai_filter.jsonl`, notificări | P1 |
| 8 | **Sursele de știri: în practică doar una.** ForexFactory (cu 429 frecvente). Calendarul MT5 nu există în API-ul Python (cod mort). Finnhub nu e configurat (`data/finnhub_config.json` lipsește). | `live/news_guard.py`, `data/` | P1 |
| 9 | **Mod Inteligent (Smart News) e activ pe 12 sesiuni, dar nu a plasat niciodată un ordin.** Are nevoie de valoarea `actual`, pe care sursa actuală nu o oferă fiabil. | 0 notificări „Ordin Stire” în ultimele 500; memoria proiectului | P2 |
| 10 | **Fracțiile de capital însumează 324%** pe sesiunile active, iar riscul real depinde de lotul minim al brokerului. | profil | P1 |
| 11 | **Programarea barelor nu suportă H4 ca timeframe de intrare** (`now.minute % 240` nu se aliniază la limitele H4). M30 ca intrare funcționează. | `_next_bar_close` | P3 (doar dacă se adaugă intrare H4) |

## 3. What Works — ce funcționează și trebuie protejat

- **Protecția la știri chiar oprește trading-ul.** Pauza se activează la timp (ex. „Core PCE … 15 min” la 15:15, o tranziție pe pauză, închidere). În MT5 apar 10 închideri `news_close`: **net +$5.29, 7/10 pe plus**, adică a blocat profit înainte de volatilitate.
- **Închiderea de vineri:** 3 închideri, **+$2.46**. Funcționează (`now_local`, ora RO, configurabilă).
- **Execuția MT5:** filling modes, trunchierea comentariului, hedging, recuperare. Lecții plătite, de păstrat neatinse.
- **Filtrul AI cu failover** pe consiliul unic (sursa aleasă → alte surse sănătoase → Ollama) și modul Strict ca fail-closed funcționează conform designului (testele trec: 71/71).
- **Engine-ul suportă tehnic M30 ca intrare și H4 ca trend:** maparea TF în `Mt5DataSource`, `tf_minutes`, programarea barelor la 30 de minute și CSV-urile M30/H4 există. **30m/4h nu e implementat ca sesiune, dar nu necesită cod nou de strategie.**

## 4. What Doesn't Work — ce nu funcționează și de ce

- **Circuit breaker live:** absent (problema 3).
- **UI ≠ live pe timeframe** (problema 2): profilul nu controlează TF-ul.
- **Backtest optimist** (problema 1): toate verdictele M0 și cifrele de „frecvență estimată” sunt calculate pe un trend care vede viitorul.
- **Mod Inteligent:** nu a produs nimic. Complexitate fără efect.
- **Roluri / consilii suplimentare:** `secondary_source` e gol peste tot (multi-council nu e folosit). Rolurile Quant/Devil sunt active pe 5-6 sesiuni și cresc latența, care e cauza principală a depășirilor de buget.
- **„Strong D1 Trend” (ADX):** oprit pe toate sesiunile (`adx_d1_enabled = null`). Singurele dependențe sunt opționale (criteriul din `signals.py`, câmpul din backtest/M0/override). Poate fi eliminat din UI fără impact. În backend rămâne inert (Keep → Deprecate).

## 5. Proposed Architecture — structura recomandată

```
Settings (global — se aplică tuturor engine-urilor, prezente și viitoare)
  Notificări (Telegram + mod liniște) · Punte Telegram · Matrix · Live Trading · Fus orar
  Protecții globale:  Capital · Circuit Breaker · Știri · Închidere vineri · Poziții simultane · Filtru AI (OFF)
          │   un singur modul backend: core/global_guard.py  (citit de Bot ȘI AI Engine)
          ▼
Custom Engine
  [15m/30m] [30m/4h] [1h/1d]      ← tab-uri = familia de timeframe
     └─ Piețe (card per piață)  →  expand: Esențial | Strategii | Protecții | Avansat
```

**Principiul de prioritate recomandat (corectat față de propunere):**
`Global Safety (Capital, Circuit Breaker global, Live Guard)` → `Global Restrictions (Știri, Vineri, Poziții simultane)` → `Engine/Market restrictions (ore, zile, direcție)` → `Strategie → Semnal` → **`Risk sizing`** → `AI Validation` → `Execuție`.

Două ajustări față de lista ta:
- **(a)** Risk sizing trebuie calculat **înainte** de AI, ca filtrul să judece trade-ul real (lot, risc).
- **(b)** Regula globală acționează ca **plafon de siguranță**: când e activă, se aplică varianta **cea mai strictă** dintre global și piață, nu „suprascrie orice”. Exemplu: dacă globalul spune impact ≥2 și piața ≥3, rezultă ≥2. Așa un engine nu poate fi niciodată *mai permisiv* decât globalul, dar poate fi mai strict. (Decizie de confirmat — vezi Întrebări.)

**Garanția că niciun engine nu ocolește regula globală:** un singur punct de verificare (`global_guard.allow_new_order(engine, symbol, direction)`), apelat de **ambele** engine-uri chiar înainte de `order_send`, plus un test care eșuează dacă vreun apel `order_send` nou nu trece prin el.

## 6. Migration Plan — transferul configurațiilor actuale

- **Profile → fără selector, dar fără pierdere de date.** Dependențe reale de profil:
  - pornirea botului (scrie `active_profile_runtime.json`, citit de fiecare sesiune);
  - watchdog-ul Protecției Capitalului;
  - estimarea de frecvență + `run-missing`;
  - M0 audit;
  - jurnalul de modificări;
  - start/stop în UI și Telegram.
- **Recomandare:** păstrăm `data/profiles/standard.json` ca fișier unic de configurație (doar redenumit în UI: „configurația Custom Engine”) și eliminăm doar selectorul. Profilul `test` se arhivează în `data/profiles/_archive/`. Risc zero pentru live: formatul fișierului rămâne identic.
- **Session → Market:** în UI arătăm *piața* (sesiunea devine detaliu intern). Cheia `sessionN` rămâne în backend, pentru că de ea depind: directorul de stare, ID-urile semnalelor (`S15-…`, folosite și de atribuirea MT5), comentariile ordinelor, pauza și notificările.
  - **Atenție:** „Add Market” din UI cere azi un **script Python nou** per piață. Fără un runner generic (un singur proces care încarcă piețele din config), butonul nu poate funcționa. Recomand runner-ul generic **înainte** de „Add Market”.
- **Fiecare piață se mapează pe tab-ul TF după `entry_tf/trend_tf` real:**
  - 14 piețe → 15m/30m;
  - 6 piețe → 1h/1d;
  - S10 și S14 → **de decis** (UI spune H1/H4, live rulează H1/D1);
  - 30m/4h pornește gol.
- **Validare migrare:** se capturează `session_cfg`-ul efectiv rezultat după override-uri, pentru fiecare piață, înainte și după migrare. Diferența trebuie să fie zero (exceptând schimbările intenționate). Test automat nou.
- **Keep → Migrate → Deprecate → Remove:**
  - `adx_d1_enabled`, `body_strength_*`, `r_*_threshold`, `smart_news_enabled`, `ai_role_*`, `ai_filter_secondary/tertiary_source`: **Deprecate** (ignorate, păstrate în fișier o versiune), apoi **Remove**.
  - `expire_bars`: **Migrate** la o valoare comună.
  - `account_fraction`: **Keep** până la decizia de sizing.

## 7. Global Settings — ce devine global și de ce

| Setare | Azi | Propunere | Motiv |
|---|---|---|---|
| Telegram, Bridge, Matrix, Live Trading, fus orar | în Profile | **Settings** | nu țin de un engine |
| Protecția Capitalului | profil, doar Bot, în API | **Global**, verificată *în* engine-uri (Bot + AI), nu în API; acțiune: oprește ordinele noi + opțional închide | să funcționeze și fără UI pornit |
| Închidere vineri | per sesiune | **Global** (ON/OFF + oră RO, default 20:00), crypto exceptat implicit | azi Bot = 20:00, AI = 22:00 — două reguli diferite |
| Circuit Breaker | inexistent live | **Global nou**: „N pierderi consecutive în aceeași zi (RO) pe cont → stop ordine noi până la 00:00” | „circuit” = o pierdere închisă (SL) |
| Protecție știri | per sesiune | **Global** (ON/OFF + impact 1/2/3 + pre/post) | aceeași regulă pentru toți |
| Poziții simultane | per sesiune, doar pullback | **Global** (OFF implicit): max poziții+ordine pe *simbol*, toate strategiile **și** ambele engine-uri | azi limita reală e `max+2` |
| Filtru AI Pre-Trade | per sesiune | **Global** (**OFF implicit**), cu Strict | conform cerinței |

**Numele tab-ului:** recomand **„Settings” (Setări)**. „Profile” sugerează un *set de configurații alternative*, concept pe care îl eliminăm. Conținutul real e configurația aplicației și a protecțiilor globale.

## 8. Custom Engine — structura nouă

- Tab-uri: **15m/30m · 30m/4h · 1h/1d**. Fiecare tab arată lista de piețe: status LIVE/OBS, pauză, rezultat MT5 și verdictul M0.
- **Card piață (închis):** simbol · direcție · ore · LIVE/OBS · ⏸ · rezultat MT5 · badge M0 (KEEP/OBSERVE/DEMOTE).
- **Card deschis, 4 grupe pliabile:**
  1. **Esențial:** direcție, ore/zile, lot/risc, nivel R:R, LIVE/OBS.
  2. **Strategii:** Pullback / Inside Bar / Flag (ON/OFF) + RSI + EMA.
  3. **Protecții:** break-even, știri/vineri (doar *mai strict* decât globalul).
  4. **Avansat (ascuns implicit):** pullback window, poziții simultane, distanța între trade-uri, backtest.
- **Eliminate din UI:** Strong D1 Trend, Expire Bars, pragurile ladder-ului, R individual pe IB/Flag, Mod Inteligent, roluri și consilii suplimentare.

## 9. Trading Analysis — recomandările traderului

- **R:R — 3 niveluri independente de criterii: VALIDAT ca direcție.**
  - Backtest pe 6 sesiuni: ladder-ul actual **nu e mai bun** decât un TP fix în 5/6 sesiuni (pe S11 iese aproape la egalitate).
  - Exemple: S1 ladder −0.041R vs 2R −0.023R; S15 ladder −0.056R vs 4R +0.028R; S16 ladder +0.105R vs 3R +0.186R.
  - **Niciun nivel nu e cel mai bun peste tot** (2R pe S11, 3R pe S16/S5, 4R pe S15), deci nivelul trebuie ales **per piață**, validat OOS.
  - 2R reduce drawdown-ul constant pe M15 (S1: −123R → −82R).
  - Recomand ca nivelurile să fie TP-uri **2R / 3R / 4R** cu **același risc** pe trade. Propunerea ta „3:1.2, 4:1.5” pare să crească și riscul (1.2%, 1.5%). Mărirea riscului odată cu ținta nu e justificată de date (WR scade odată cu R).
  - **Nume propuse:** **Scurt (2R) · Standard (3R) · Extins (4R)** — descriu ținta, nu o „calitate”.
- **Aceleași 3 niveluri pentru Inside Bar și Flag:** compatibil (IB e deja 2R = „Scurt”). Recomand IB implicit pe „Scurt”, deoarece IB a fost profitabil live tocmai cu 2R.
- **Expire Bars:** testat 2/3/4/6 pe 6 sesiuni. Diferențele sunt mici (<0.03R) și cu semn inconsecvent, deci nu există un optim robust. **Recomand valoarea comună 4 bare** (majoritatea actuală: 12/22): pe M15 = 1 h, pe H1 = 4 h, pe M30 = 2 h. Logica: un breakout care nu se declanșează în 4 bare nu mai e același setup.
- **RSI + EMA** rămân filtre independente (ON/OFF), nu mai influențează R-ul.
- **Timeframe-uri:**
  - 15m/30m e singura combinație cu istoric validat, dar raportul 2× e slab.
  - 30m/4h (8×) are logică și se poate activa fără cod nou de strategie. Recomand **să înceapă pe OBS**, după un M0 pe backtestul corectat.
  - 1h/1d dă puține trade-uri.
- **Știri:** păstrăm impactul 3 (High) ca implicit, cu pre/post 15 min — datele live susțin regula (+$5.29). Nivelul 2 (Medium) ar opri trading-ul mult prea des pe perechile USD/EUR, nu e recomandat implicit.
- **Mod Inteligent: se elimină.** Nu a funcționat niciodată (lipsa `actual`), iar tranzacționarea release-ului pe un cont de $200 e dominată de spread și slippage.
- **Strategii:** toate trei există și în live, și în backtest, cu aceeași logică (`detect_setup`, `detect_inside_bar`, `detect_flag` comune). Diferențele backtest ↔ live care contează: lookahead-ul pe trend (problema 1); știrile, filtrul AI și închiderea de vineri nu sunt simulate.

## 10. AI Analysis

- **Păstrăm:** consiliul principal, sursa selectabilă, failover-ul (sursă → alte surse sănătoase → Ollama) și Strict.
- **Eliminăm:** consiliile 2/3 și rolurile Quant/Devil. Reduc latența (sub bugetul de 240 s) și deci blocările în modul Strict.
- **Recomand ca Strict să rămână la alegere, dar cu avertisment în UI:** „Strict + AI picat = nu se plasează ordine”. Azi e pornit pe 18 sesiuni, deci căderile AI blochează trade-uri.
- **Filtrul global AI: OFF implicit.** Când e activ, se aplică tuturor engine-urilor. AI Engine își are deja propriul consiliu, deci globalul ar trebui aplicat doar engine-urilor pe reguli (de confirmat).

## 11. QA / Risk Analysis

**Riscuri:**
- Migrarea poate schimba tăcut parametrii efectivi. Mitigare: snapshot `session_cfg` înainte/după.
- Override-urile globale pot fi ocolite. Mitigare: un singur choke-point + test.
- Circuit breaker-ul nou poate bloca greșit. Mitigare: definiție clară, reset la 00:00 RO, persistat peste restart, test cu MT5 fals.
- Corectarea lookahead-ului **schimbă baseline-urile** (284/1326 trade-uri) — necesită acordul tău.

**Teste necesare (lipsesc azi):**
- circuit breaker live;
- prioritatea regulilor globale;
- echivalența config înainte/după migrare;
- „Add Market” end-to-end (pe demo);
- restart în timpul pauzei globale.

## 12. Backtesting

- **Ce face azi:**
  - aceleași funcții de detecție ca live-ul;
  - spread static pe simbol, comision din config, swap;
  - break-even;
  - split 70/30;
  - verdict M0.
- **Probleme:**
  - lookahead pe trend (P0);
  - știrile, filtrul AI și închiderea de vineri nu sunt simulate;
  - fără slippage;
  - spread fix, nu variabil.
- **Ce propun:**
  1. fix lookahead (alinierea trendului la bare închise) + re-generarea baseline-urilor și a verdictelor M0;
  2. simularea închiderii de vineri și a pauzei de știri (calendar istoric FF), ca opțiune;
  3. filtrul AI rămâne nesimulabil (non-determinist) — se marchează explicit în rezultate;
  4. UI: un singur buton „Testează piața” per card, cu rezultat + verdict M0, în loc de panoul actual.

## 13. UI/UX

- Progressive disclosure: card închis → 4 grupe → „Avansat” ascuns.
- Elimină aproximativ 40% din câmpuri: ladder, praguri, risk per nivel, expire, ADX, body, smart, roluri, surse 2/3, R pe IB/Flag.
- **Verdictul M0 lângă butonul LIVE**, cu avertisment la activarea unei piețe DEMOTE.

## 14. Performance (tehnic)

- Runner unic în loc de 22 de procese: −2 GB RAM estimat, o conexiune MT5, permite „Add Market” și reguli globale ușor de aplicat.
- Mai puține roluri AI → latență ~½.

## 15. Trading Performance — fără sacrificarea robusteței

- Nivel R per piață, ales pe OOS (date: S15 4R, S16 3R, S11 2R) — nu un singur R pentru toți.
- Nicio piață DEMOTE pe bani reali (pe backtestul *corectat*).
- Circuit breaker + poziții simultane globale: reduc drawdown-ul în zilele corelate, fără să atingă semnalele.
- **Nu recomand** optimizarea Win Rate în sine: 2R crește WR-ul, dar nu e cel mai bun peste tot la expectancy.

## 16. Implementation Plan — ordinea recomandată

1. **Fix lookahead în backtest** + rerulare M0 (fundamentul tuturor deciziilor).
2. **Fix S14/S10:** profilul controlează timeframe-ul (sau aliniere manuală) — după decizia ta.
3. **Modul `global_guard`** + Settings (doar mutarea setărilor existente, fără reguli noi).
4. **Circuit Breaker global** (live) + teste.
5. **Închidere vineri globală**, știri globale, poziții simultane globale (OFF implicit), filtru AI global (OFF).
6. **Protecția Capitalului mutată** din API în engine-uri.
7. **Migrare:** eliminarea selectorului de profil, snapshot config înainte/după.
8. **R:R pe 3 niveluri** (backend: `reward_R` → nivel fix; ladder-ul deprecated) + Expire comun = 4.
9. **Eliminare:** Smart Mode, ADX, consilii/roluri suplimentare.
10. **Runner generic** → apoi tab-urile TF + „Add Market”.
11. **UI card compact.**
12. **Backtest:** vineri/știri simulate, UI simplificat.
13. Regresie completă → demo → live.

## 17. Regression Checklist

- [ ] `session_cfg` efectiv identic înainte/după migrare, pentru toate cele 22 de piețe.
- [ ] Baseline-uri (după fix-ul de lookahead, valori noi aprobate) reproduse.
- [ ] Plasare ordin / SL / TP / expirare / BE pe demo, pentru fiecare TF.
- [ ] Pauză știri: activare la `pre`, închidere poziții, reluare la `post` (Bot + AI).
- [ ] Închidere vineri globală: Bot + AI, crypto exceptat, ora RO.
- [ ] Circuit breaker: declanșare la N SL, blocare ordine noi, reset 00:00, supraviețuiește restartului.
- [ ] Poziții simultane globale: Pullback + IB + Flag + AI pe același simbol, restart, ordine pending.
- [ ] Protecția Capitalului fără API pornit.
- [ ] Filtrul AI OFF implicit; Strict fail-closed; failover până la Ollama.
- [ ] Reconectare MT5, restart aplicație, recuperare outcome-uri.
- [ ] Atribuirea MT5 (Bot/AI/sesiune/strategie) neschimbată.
- [ ] Toate suitele existente (news 65, profile 91, AI filter 71, MT5 health, live guard, close fill, comisioane, bridge, M0).

---

## Întrebări care necesită decizia ta (trimise și pe Telegram)

1. **R:R „2:1 · 3:1.2 · 4:1.5”** — înseamnă TP 2R/3R/4R cu risc 1%/1.2%/1.5%? Recomandare: TP 2R/3R/4R cu **același risc**.
2. **Regulile globale:** „cea mai strictă câștigă” (recomandat) sau „globalul înlocuiește complet setarea pieței”?
3. **Fix-ul de lookahead schimbă baseline-urile oficiale** (284 trade-uri etc.). Aprobi corectarea și noile baseline-uri?
4. **S14 CHFJPY** (live): păstrăm ce rulează (H1/D1) sau ce arată UI-ul (H1/H4)?
5. **Sizing:** „doar Lots” (risc variabil în $ după distanța SL) sau **risc % pe trade** cu lot calculat automat (recomandat) + lot fix opțional?
6. **„Add Market”** cere runner-ul generic (un proces pentru toate piețele) — aprobi să fie făcut înaintea noii structuri UI?
7. **Filtrul AI global** se aplică și AI Engine-ului (care are deja consiliu propriu) sau doar Custom Engine?
8. **Numele tab-ului:** „Settings” (recomandat) — confirmi?
