# Live Readiness — Daily Engine + Special Engine (audit final, 20.11.2026)

Cont: ICMarketsEU #13136652, **REAL**, equity **295,50 $** (după testul real de azi, −0,20 $), levier 1:30.
Date: Shadow Daily 02–19.11 (43 de rânduri), Shadow Special 09–19.11 (13 rânduri), sincronizate de pe laptop (commit
`5cadb80`, 20.11 10:45). Backtest: barele M5 din MT5 (februarie 2021 → 20.11.2026, ~5,7 ani), costurile reale ale contului.
Script: `python scripts/research_daily/live_readiness_2026_11.py` → `data/research_daily/live_readiness_2026_11.json`.

> Nicio configurație nu a fost schimbată automat. Recomandările de mai jos sunt pentru decizia ta.

---

## 1. Calitatea datelor Shadow — ce am găsit înainte de orice statistică

| Problemă | Efect | Remediere |
|---|---|---|
| **Ora serverului greșită după miezul nopții** (Daily, Noisy): un tick vechi de EXACT 60 min (pauza indicilor ~00:56 RO) trecea drept „proaspăt” → offset −1h → barele zilei mutate cu o oră | 4 re-intrări **fantomă** în Shadow Daily (DE40 09.11 / 17.11 / 18.11, US500 18.11) = **+9,9R inexistent** | `server_clock.py` (comun Daily + Noisy); reprodus pe barele reale (`scripts/test_server_clock.py`) |
| **Dubluri** 13.11 (două procese au scris aceleași trade-uri) | +2 rânduri DE40 | `daily_engine.engine.split_valid` — jurnalul NU e rescris (e unit între PC și laptop), rândurile sunt ignorate la citire și listate în UI |
| **NR4 Special calculat pe bara D1 în formare** (JP225: ziua Tokyo începe la 17:00 server din ziua precedentă) | 2 din 3 trade-uri Shadow JP225 (10.11, 18.11) **nu erau zile NR4** | `special_engine._d1_for`: doar bare închise; decizia NR4 așteaptă închiderea barei de ieri (00:00 server, mereu înainte de 09:00 Tokyo) |
| GBPUSD scos din slot pe 06.11 | apare doar în totaluri (nu pe carduri) | deja tratat (rândul „Piețe scoase din configurație”) |

**După curățare, Shadow = backtest pe aceleași zile, trade cu trade:** DE40 **+23,75R** (Shadow) vs **+23,74R** (backtest),
US500 identic (06.11 lipsește din Shadow: engine-ul nu rula la ora NY), USTEC NOISE identic pe zilele rulate (13.11 fără
înregistrări Shadow). Engine-urile execută exact strategia testată.

## 2. Shadow — rezultate pe configurații (după curățare)

| Engine · piață | Perioada | Configurația | Trade-uri | WR | Total | Medie |
|---|---|---|---|---|---|---|
| Daily · GBPUSD | 02–06.11 | Londra, fără re-intrări (inițială) | 5 | 0% | −5,76R | −1,15R |
| Daily · US500 | 02.11 + 09–19.11 | NY (re-intrări din 09.11) | 11 | 36% | +4,27R | +0,39R |
| Daily · DE40 | 03–06.11 | Frankfurt, fără re-intrări | 4 | 25% | +6,50R | +1,63R |
| Daily · DE40 | 09–12.11 | Frankfurt + re-intrări max 3 | 5 | 20% | +3,38R | +0,68R |
| Daily · DE40 | 13–19.11 | Londra + Frankfurt + NY, max 3 | 12 | 42% | +13,86R | +1,16R |
| Special · JP225 | 10–18.11 | ORB 5 min direcție, NR4 | 3 (1 valid) | — | +5,12R (valid: +3,31R) | — |
| Special · USTEC | 09–19.11 | NOISE (Beat the Market) | 10 | 40% | +0,22R | +0,02R |

3 trade-uri DE40 au fost **blocate** de limita globală de risc (06.11, 11.11, 12.11 — toate pierderi, −3R): lotul minim
0,1 pe un SL de 90–139 puncte = 5–8% din equity-ul de atunci (~195 $) > limita de 5% (ridicată de la 2% pe 06.11).

**Concluzie Shadow:** 3 săptămâni = 20–40 de trade-uri pe piață — **prea puțin pentru a judeca un edge** (WR 30%, câștigurile
vin din puține zile de trend: DE40 +9,5R / +7,4R / +8,1R). Shadow-ul confirmă **corectitudinea execuției**, nu profitabilitatea;
pentru aceea contează backtestul pe 5,7 ani.

## 3. Backtest — configurațiile comparate (M5 MT5, 2021-02 → 2026-11, costuri reale)

| Configurație | n | WR | PF | Medie | Max DD | / săpt | Train / Test | Ultimele 12 luni | Ani + |
|---|---|---|---|---|---|---|---|---|---|
| **DE40** Frankfurt, fără re-intrări (inițial 03.11) | 1394 | 28% | 1,18 | +0,125R | −64R | 4,6 | +0,095 / +0,196 | +0,133 | 5/6 |
| DE40 Frankfurt + re-intrări max 3 (09.11) | 1861 | 28% | 1,17 | +0,125R | −66R | 6,2 | +0,095 / +0,194 | +0,060 | 5/6 |
| DE40 Frankfurt + NY, max 2, re-intrări | 2421 | 30% | 1,19 | +0,130R | −78R | 8,1 | +0,089 / +0,227 | +0,121 | 4/6 |
| **DE40 Frankfurt + NY, max 2, fără re-intrări** | 2399 | 32% | 1,17 | +0,113R | **−50R** | 8,0 | +0,084 / +0,181 | +0,114 | 5/6 |
| DE40 Frankfurt + NY, max 3, re-intrări | 2812 | 32% | 1,18 | +0,122R | −63R | 9,4 | +0,087 / +0,203 | +0,079 | 4/6 |
| DE40 Londra + Frankfurt + NY, max 3 (**ACTUAL**) | 3463 | 34% | 1,15 | +0,092R | −64R | 11,5 | +0,076 / +0,130 | **+0,019** | 3/6 |
| DE40 doar NY, re-intrări | 1769 | 38% | 1,15 | +0,085R | −42R | 5,9 | +0,084 / +0,088 | −0,014 | — |
| **US500** NY, fără re-intrări (inițial) | 1452 | 35% | 1,15 | +0,091R | −36R | 4,9 | +0,118 / +0,030 | +0,024 | 5/6 (2026 −) |
| US500 NY, re-intrări max 3 (**ACTUAL**) | 1746 | 36% | 1,15 | +0,094R | −49R | 5,9 | +0,126 / +0,020 | −0,006 | 5/6 (2026 −) |
| **JP225** ORB 5 min direcție, toate zilele | 1432 | 28% | 1,06 | +0,047R | −83R | 4,8 | +0,003 / +0,150 | +0,246 | 3/6 |
| **JP225 NR4 (ACTUAL Special A)** | 372 | 32% | **1,48** | **+0,330R** | **−18R** | 1,3 | +0,379 / +0,217 | +0,280 | **6/6** |
| **USTEC NOISE (ACTUAL Special B)** | 1374 | 42% | 1,24 | +0,085R | −22R | 4,7 | +0,104 / +0,042 | +0,068 | 6/6 |

Observații:
- **Configurația ACTUALĂ DE40 e cea mai slabă variantă**: Londra (08:00 UK) și Frankfurt (09:00 Berlin) se deschid în
  ACELAȘI minut, deci sesiunea Londra ia locul Frankfurtului (închidere 15:25 CET în loc de 17:25) — în 3 săptămâni nu
  există niciun trade „frankfurt”. Ultimele 12 luni: +0,019R.
- Re-intrările adaugă trade-uri cu medie mai mică și cresc drawdown-ul (−50R → −78R pe Frankfurt + NY).
- US500: edge-ul se stinge (test +0,02–0,03R, 2026 negativ).
- JP225 NR4: cel mai bun raport (PF 1,48, toți anii pozitivi, train ȘI test pozitive), dar eșantion mic (372 trade-uri,
  t = 2,2) și filtrul NR4 e o alegere a selecției trimestriale (risc de supra-optimizare moderat).
- USTEC NOISE: robust statistic (t = 2,45, 6/6 ani), dar vezi capitalul (secțiunea 4).

## 4. Capital 300 $ — riscul REAL la lotul minim al brokerului

Specificații MT5 (citite azi): DE40 lot minim 0,1 = 0,11 $ / punct, marjă 137 $ · US500 0,1 = 0,10 $ / punct, marjă 36 $ ·
JP225 1 lot = 0,0063 $ / punct, marjă 18 $ / lot · USTEC 0,1 = 0,10 $ / punct, marjă 130 $.

| Piață · config | Risc la lotul minim (median / max) | Trade-uri care încap la 1% / 2% / 3% | Profit mediu / an | DD 12 luni median / cel mai rău | Serie max pierderi |
|---|---|---|---|---|---|
| DE40 Frankfurt + NY, max 2, fără re-intr., plafon 3% | 4,4 $ (1,5%) / 9 $ | 24% / 72% / 91% | +182 $ | **−120 $ / −215 $** | 19 |
| DE40 ACTUAL (L + F + NY, max 3), plafon 3% | 4,4 $ / 9 $ | 23% / 71% / 91% | +220 $ | −156 $ / **−348 $** | 26 |
| US500 NY, fără re-intr., 1% | 2,7 $ | 87% / 99% / 100% | +68 $ | −71 $ / −102 $ | 16 |
| **JP225 NR4, 1%** | 2,7 $ (≈5 loturi) | 99% / 100% / 100% | +59 $ | **−38 $ / −50 $** | 12 |
| USTEC NOISE (SL de protecție 2×) | **17 $ (5,7%)** | 0% / 2% / 11% | — | — | — |

**Ce înseamnă:**
- **DE40 nu încape sănătos în 300 $.** Lotul minim e deja ~1,5% risc median, iar un an obișnuit are un drawdown de ~40% din
  cont (cel mai rău: ~72%). Edge-ul e real, dar contul nu poate absorbi variația. Cu 1% risc, DE40 n-ar tranzacționa
  aproape deloc (doar 24% din zile).
- **JP225 NR4** se dimensionează fin (lot 1 = 0,0063 $ / punct): exact 1% risc, drawdown istoric ≤ 17% din cont.
- **USTEC NOISE** e imposibil la 300 $: riscul lotului minim e 5,7% din cont, iar marja 130 $.
- **Expunere combinată:** JP225 (02:05–08:00 RO) nu se suprapune cu DE40 (10:00–23:00 RO). DE40 + US500 se suprapun
  după 16:30: marja 137 + 36–71 $ (≤ 80% din equity, limita Daily) — și conturile Custom / AI rulează pe același cont,
  deci limita de marjă (care numără TOATE pozițiile) e cea care decide.
- Lotul minim peste riscul permis → **trade respins, nu rotunjit în sus** (implementat — secțiunea 6).

## 5. Recomandarea echipei (decizia îți aparține)

| Engine · piață | Recomandare | Configurație |
|---|---|---|
| **Special · JP225 (A, NR4)** | **LIVE** (după restartul Special cu fix-ul NR4) | risc 1% (setările engine-ului, fără override), max 2 poziții, plafon marjă 80% |
| **Special · USTEC (B, NOISE)** | **SHADOW** | lotul minim = 5,7% risc la 300 $ |
| **Daily · DE40** | **SHADOW până la ~600 $**; dacă vrei totuși Live: doar cu Protecția Capitalului pornită | sesiuni **Frankfurt + New York**, max **2** / zi, **fără re-intrări**, Market Risk Override **1% / maxim 3%**, Setări Globale → Protecția Capitalului **pornită** (ex. stop la 75% = ~220 $) |
| **Daily · US500** | **SHADOW** | edge în scădere (2026 negativ) |
| **Noisy** | **SHADOW ONLY** (cerința ta) | — |

Recomandare suplimentară: limita globală de risc pe trade e acum **5%** (ridicată pentru DE40) și slăbește Custom / AI —
cu Market Risk Override pe DE40 o poți readuce la **2%** fără să blochezi DE40.

## 6. Ce s-a implementat

1. **Market Risk Override** (comun Daily + Special, `position_sizing` + `live/global_guard.risk_policy`):
   1. piață cu override pornit → risc / trade + **risc maxim la lotul minim** proprii (peste maxim = respins);
   2. override oprit → setările engine-ului + limita globală (exact ca înainte);
   3. **plafon absolut** (Setări Globale → `risk_cap.override_max_pct`, implicit 5%) — nicio piață nu îl poate depăși;
   4. protecțiile obligatorii (capital, circuit breaker, vineri, știri, poziții simultane, marjă, pauză, Emergency Stop)
      rămân aplicate separat — override-ul nu le poate ocoli.
   UI: Daily → „Opțiuni” pe fiecare piață; Special → „Risc per piață”; Setări Globale → plafonul absolut.
2. Fix-urile din secțiunea 1 (ora serverului, dubluri / fantome, NR4).
3. **Integrare Special în aplicație**: secțiunea Special jos în Dashboard, filtrul de sursă, Piețe active (JP225 / USTEC
   cu fazele lor), etichetele SPECIAL în Tranzacții / Rapoarte / Ordine active (apăreau MAN / MANUAL), rapoartele programate
   (rând Special + Shadow, inclus în TOTAL).
4. **Piețe active Daily: modul PER PIAȚĂ** (o piață Shadow lângă una Live apărea ca execuție; pauza manuală nu apărea).
5. Ordine active: pozițiile **Noisy** apăreau MANUAL.
6. Mesajul plasei de siguranță (`sweep_stale`) numește și pozițiile nerecunoscute.

## 7. Testul REAL controlat (aprobat de tine, 20.11 ~14:22 RO)

| Pas | Daily (US500, 0,1 loturi, magic 880001) | Special (JP225, 1 lot, magic 660001) |
|---|---|---|
| Cont / simbol / lot / risc verificate înainte | REAL #13136652 · US500 · 0,1 (minim) · SL 5 pct = 0,50 $ · marjă 36 $ | JP225 · 1 (minim) · SL 60 pct = 0,38 $ · marjă 18 $ |
| Plasare cu SL (+TP) | ✅ retcode 10009, SL 7114,7, TP 7129,7 | ✅ retcode 10009, SL atașat |
| Modificare SL (TP păstrat) | ✅ 7114,7 → 7116,7 | — (Special nu modifică SL: B iese prin închidere) |
| Închidere | ✅ de **Daily Engine de pe laptop** (`sweep_stale`: poziție necunoscută azi) — notificare Telegram | ✅ de **Special Engine de pe laptop** în < 1 s (`sweep_stale`) |
| Rezultat | −0,16 $ | −0,04 $ |
| Aplicație | apare în MT5, Tranzacții, Rapoarte (rândul Daily), Notificări | apare în MT5, Tranzacții, Rapoarte (rândul Special) |

Gate-ul Trading LIVE a fost verificat: pe acest PC Daily și Special sunt **blocate** pe cont real (nedeblocate în
Settings → Trading LIVE) — corect; deblocarea se face doar pe mașina care rulează engine-urile (laptopul).
Ce NU s-a testat pe contul real (testat pe MT5 simulat): închiderea prin funcția proprie a executorului (aceeași cale de
trimitere ca deschiderea), ordinele stop OCO DE40, mutarea SL de Profit Lock, deconectarea / reconectarea MT5.

## 8. Audit aplicație + regresie

Teste (toate trec): Daily selftest 120 · Noisy 97 · Special 43 · M0 · server_clock 16 · jurnal 7 · Market Risk 29 · NR4 9 ·
Daily piețe 58 · Special API · Piețe active · rapoarte 69 · costuri 31 · lifecycle 13 · ritm 13 · dimensionare 45 ·
Setări Globale 56 · backtest refresh 26 · Profit Lock 37 · Special TP live 19 · Noisy API 18 · safe_io · costuri backtest ·
validitate backtest · fus orar · reconectare MT5 · Trading LIVE · filtru AI · config AI · mod liniște · știri · sync ·
profil · lot fix · sănătate MT5 · comisioane · filling (unit) · `tsc`.

Limitări rămase (documentate, nu blochează):
- Rândurile fantomă / dublurile rămân în `trades.jsonl` (ignorate la citire); cele 2 trade-uri JP225 non-NR4 din Shadow
  Special nu sunt excluse automat (necesită D1 istoric) — numerele valide sunt în secțiunea 2.
- „Ritmul de tranzacționare” din Dashboard acoperă doar Custom / AI / Daily (nu Noisy / Special).
- Pornit exact în pauza zilnică a indicilor, prima detecție a orei serverului poate fi încă greșită până la primul tick nou.

## 9. Pași pe laptop înainte de Live (luni)

1. `sync_data.bat` (aduce codul), apoi **repornește dashboard-ul (API) + Daily + Special** — fix-urile se aplică doar după restart.
2. Decide configurația (secțiunea 5); setările se fac din UI (Daily → Opțiuni; Special → Risc per piață; Setări Globale).
3. Settings → **Trading LIVE**: deblochează DOAR engine-ul ales (Special și / sau Daily), apoi modul **LIVE** doar pe piața aleasă.
4. Prima zi: urmărește Notificările — fiecare ordin real, respingere (risc / marjă) și închidere apare acolo și pe Telegram.

**Status final:** Daily Engine — **Conditionally Ready** (tehnic gata; DE40 prea mare pentru 300 $ fără Protecția
Capitalului) · Special Engine — **Conditionally Ready** (JP225 Live după restart cu fix-ul NR4; USTEC Shadow Only) ·
Noisy Engine — **Shadow Only** · Custom / AI — neschimbate, regresie verde.

---

## 10. Decizii aplicate după raport (20.11.2026, decizia ta)

| Setare | Înainte | Acum |
|---|---|---|
| DE40 — sesiuni | Londra + Frankfurt + NY, max 3 / zi, re-intrări | **Frankfurt + New York, max 2 / zi, fără re-intrări** |
| DE40 — risc | setările globale (limita 5%) | **Market Risk Override: țintă 1%, maxim 6%** din equity la lotul minim |
| DE40 — mod | SHADOW | **SHADOW** (neschimbat) |
| Plafon absolut (override) | 5% | **6%** (altfel maximul DE40 era tăiat la 5%) |
| Limita globală de risc / trade | 5% | **3%** — Custom, AI, Noisy, US500, JP225, USTEC |
| Protecția Capitalului | oprită | oprită (recomandarea rămâne: pornită înainte de DE40 Live) |

Efectul verificat cu dimensionarea reală (MT5, equity 296 $): DE40 SL 50 pct → 0,1 lot, 5,5 $; SL 120 pct → 0,1 lot,
13,2 $ (4,5% — trece, override); SL 170 pct → respins (6,3% > 6%). US500 SL 30 pct → 0,1 lot, 3 $; SL 100 pct → respins
(3,4% > 3% global). La 6%: 99,3% din trade-urile DE40 istorice încap. Custom / AI: risc real maxim ~1,2% / trade → 3% nu
blochează nimic din ce trecea înainte.

**Reluare LIVE prin engine-ul real** (`scripts/research_daily/daily_live_replay.py` — execuție pornită, barele MT5 reale,
`order_send` interceptat, fișierele reale neatinse): 17.11 / 18.11 / 19.11 DE40 → BUY_STOP + SELL_STOP pe marginile
intervalului Frankfurt (0,1 lot, SL atașat, ~5,5 $ risc), OCO (cealaltă margine anulată la umplere), SL atins (−1R),
apoi ordin la piață la 17:00 RO pe direcția intervalului NY cu SL, închis la 23:00 (+5,5R / +3,7R / +8,1R); limita de 2 / zi
respectată, nicio re-intrare — identic cu backtestul.

**UI:** sesiunile se aleg doar din „Sesiuni” („Bursa” scoasă din „Schimbă piața”); Londra și Frankfurt se exclud
reciproc (se deschid în același minut).

