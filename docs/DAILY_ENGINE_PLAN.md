# Daily Engine — investigație și plan (2026-10-31)

Status: **Faza 2 construită (2026-10-31) — Daily Engine în mod SHADOW** (GBPUSD dimineața + US500 după-amiaza, zero ordine reale). Fazele 3–4 necesită aprobarea userului.

## 1. Ce spun sursele oficiale și studiile

| Sursă | Ce arată |
|---|---|
| Chague & Giovannetti (FGV/CVM, 2019) — PDF-ul din `docs/books/` | 24.084 day-traderi din Brazilia: 92% renunță, 88% din cei care persistă >300 zile pierd, ~0,1% câștigă >300 R$/zi; performanța **nu** se îmbunătățește cu experiența |
| [ESMA, 2018](https://www.esma.europa.eu/node/84933) | 74–89% din conturile retail pe CFD pierd bani |
| [BIS Triennial Survey 2025](https://www.bis.org/media-releases/20250930-global-fx-trading-hits-96-trillion-day-april-2025-and-otc-interest-rate-derivatives-surge-79) | FX: 9,6 trilioane $/zi, concentrat în Londra + New York |
| [Gau & Wu / arXiv 2411.16244](https://arxiv.org/html/2411.16244v1) | Suprapunerea Londra–New York domină formarea prețului la EURUSD/USDJPY, dar mai ales în zilele cu știri macro SUA |
| [Gao, Han, Li, Zhou (JFE 2018)](https://econpapers.repec.org/RePEc:eee:jfinec:v:129:y:2018:i:2:p:394-414) | Prima jumătate de oră prezice ultima jumătate de oră (S&P 500) — efect real dar mic, [greu de capturat după costuri](https://cxoadvisory.com/calendar-effects/first-and-last-half-hours-of-trading-linked) |
| [Zarattini & Aziz (SSRN 4416622)](https://papers.ssrn.com/abstract=4416622) | Opening Range Breakout (ORB) la deschiderea bursei SUA — profitabil în studiul autorilor |
| [Replicare independentă ORB pe CFD-uri, 2015–2026](https://www.mql5.com/en/blogs/post/776235) | Brut se reproduce (+0,05…+0,13R); **net de costuri ≈ 0** pe NQ/SPX/Dow/DAX/FTSE |

Concluzie: ideea userului („intrăm când intră toată lumea”) e corectă ca **momentul cu cele mai mari mișcări**,
dar mișcare mare ≠ profit. Edge-ul, dacă există, e subțire și e mâncat ușor de costuri.

## 2. Cele mai bune ore — măsurat pe datele noastre (M15, iun 2023 – iun 2026, ora RO)

Range relativ la media zilei (1,00 = medie):

| Piață | Cele mai active ore (RO) | Cost / range orar |
|---|---|---|
| US30 | 16h (2,2x), 17h (2,2x), 18h | 0,8% |
| US500 | 17h (2,1x), 16h (1,8x) | 1,1–1,3% |
| XAUUSD | 16h, 17h (1,65x), 15h | 1,0% |
| GER40 | **10h (1,9x)**, 17h, 16h | 1,1% |
| EURUSD / GBPUSD | 17h (1,8x), 15h, 16h, 10h | 2,6–3,5% |

- **15:30–18:00 RO** = fereastra de vârf pentru TOATE piețele: știrile macro SUA (15:30 RO), deschiderea Wall Street
  (16:30 RO), suprapunerea Londra–New York (până la ~18:00–19:00 RO).
- **10:00–11:00 RO** = deschiderea Frankfurt/Londra — vârf pe DAX/FTSE.
- Orele asiatice (00–08 RO) sunt cele mai liniștite pe FX/indici europeni.
- Indicii au costul cel mai mic raportat la mișcare (≈1%) → mai potriviți pentru intraday decât FX (≈3%).
- **Capcană DST:** SUA și România schimbă ora în săptămâni diferite → ~3 săptămâni pe an Wall Street deschide la
  **15:30 RO** (martie și sfârșit oct – început nov, inclusiv ACUM). Engine-ul trebuie să lucreze pe ora locală a bursei.

## 3. Test exploratoriu ORB pe datele noastre (2017–2026)

160 de variante (10 piețe/deschideri × OR 15/30 min × direcție-lumânare/breakout × TP 1R/2R/3R/închidere zi),
cost round-trip scăzut, SL câștigă la ambiguitate în bară, închidere forțată în aceeași zi.

| Candidat | Trade-uri | R/trade | Train / Test | Ani + | t | La cost ×2 | La cost ×3 |
|---|---|---|---|---|---|---|---|
| **US30, NY 09:30, OR 15m, breakout, TP 3R** | 2102 | +0,105 | +0,098 / +0,120 | 9/10 | 3,3 | +0,068 | +0,032 |
| GER40, Berlin 09:00, OR 15m, breakout, închidere zi | 2118 | +0,088 | +0,097 / +0,066 | 8/10 | 2,1 | +0,040 | −0,008 |
| US500, NY 09:30, OR 15m, breakout, TP 2R | 600 (doar 2,5 ani) | +0,090 | +0,087 / +0,098 | 3/4 | 1,6 | +0,037 | −0,016 |
| EURUSD, NY 09:30, OR 30m, breakout, închidere zi | 1954 | +0,072 | +0,078 / +0,059 | 7/9 | 2,1 | — | — |
| UK100, Londra 08:00 | 2147 | −0,046 | negativ | 3/10 | — | — | — |

- Varianta „direcția primei lumânări” (cea din studiul ORB) iese slab — **confirmă replicarea independentă**.
  Varianta cu ordine stop la marginile intervalului iese mai bine.
- **Avertismente:** 160 de variante testate = risc de noroc de selecție (t=3,3 nu trece complet o corecție pentru
  160 de încercări); ordinele stop la deschidere au slippage real neinclus; M15 e grosier pentru un interval de 15 min.

## 4. Constrângerea contului (~$206, levier 1:30) — citit din MT5

| Piață | Marjă la lotul minim | Risc tipic la lotul minim (OR median) | Încape? |
|---|---|---|---|
| US30 | $259 (> equity) | $14,6 = 7,1% | **NU** |
| DE40 (GER40) | $144 (70% din equity) | $7,0 = 3,4% | **NU** |
| US500 | $38 | $1,4 = 0,7% | DA |
| EURUSD / USDJPY | $33–37 | ~0,5–0,6% | DA |

Cel mai bun candidat statistic (US30) nu încape în cont. Pe contul actual sunt realiste **US500** sau **EURUSD**.

## 5. Plan propus

**Faza 1 — Validare (doar backtest, zero risc), ~1–2 zile**
1. Descărcare M5 (și M1 unde există) + istoric US500 mai lung din MT5.
2. Rerulare ORB pe M5 (precizie reală a intervalului), cost realist măsurat la deschidere (spread la 16:30 RO) + slippage pe ordine stop.
3. Filtru zile cu știri majore (NFP/CPI/FOMC), evitarea vinerilor scurte/sărbătorilor SUA.
4. Audit M0 (Deflated Sharpe cu N=160 încercări, 8 fold-uri, bootstrap). **Poartă: doar KEEP trece mai departe.**

**Faza 2 — Construcție Daily Engine (doar dacă Faza 1 = KEEP)**
- Proces separat (ca AI Engine), magic propriu (ex. 880001), comment `D1-...` → atribuire separată în Dashboard (sursa „Daily”).
- Program pe ora locală a bursei: interval de deschidere → ordine stop → maxim 1 trade/zi/piață → **închidere forțată înainte de sfârșitul zilei, niciodată overnight**.
- Integrat cu Setări Globale (protecție capital, circuit breaker, știri), demo-only implicit (`live_guard`, componentă nouă).
- Tab nou „Daily Engine”: program, intervalul de azi, ordine/poziții, rezultate, statistici backtest.

**Faza 3 — Demo/observație 4–8 săptămâni**: comparăm execuțiile reale (slippage la deschidere) cu backtestul.

**Faza 4 — Live mic, doar cu aprobarea explicită a userului.**

## 6. Întrebări pentru user
1. Piața de start: US500 (recomandat — încape în cont) / EURUSD / US30 (necesită ~$600+)?
2. Fereastra: doar deschiderea New York (15:30/16:30 → închidere ~22:45 RO) (recomandat) sau și DAX 10:00?
3. Contul pentru Faza 3: cont DEMO separat (recomandat) sau observație pe contul real?
4. Pornim Faza 1 acum?

Scripturile exploratorii (nu sunt cod de producție): `scripts/research_daily/` — `hour_profile.py`, `orb_test.py`, `orb_sens.py`.

## 7. Rezultate Faza 1 (2026-10-31) — M5, istoric MT5 complet, costuri reale

Date noi: `data/research_daily/*_M5_server.csv` (US500 2017–2026, EURUSD/USDJPY 2010–2026; ora server = NY + 7h,
verificat pe scăderea spread-ului la deschiderea cash, inclusiv în săptămânile cu decalaj DST).
Scripturi: `scripts/research_daily/orb_m5.py` (grilă pre-înregistrată 18 variante/piață + verdict M0),
`orb_m5_detail.py` (pe ani, slippage, știri, long/short). Rezultate: `data/research_daily/orb_m5_results.csv`.

**Constrângere de buget:** ~$200 împărțiți cu Bot Engine + AI Engine → Daily Engine trebuie să ia puțină marjă și să
nu se suprapună pe simboluri. US500 nu e folosit de niciun alt engine; marjă la lot minim ≈ $38.

| Piață | Variante | Rezultat |
|---|---|---|
| EURUSD (17 ani) | 18 | **toate negative** (cel mai bun −0,017R) → DEMOTE |
| USDJPY (17 ani) | 18 | **toate negative** (cel mai bun −0,046R) → DEMOTE |
| US500 (9,6 ani) | 18 | 6 KEEP / 4 OBSERVE / 8 DEMOTE la M0 |

Cele mai bune pe US500:

| Variantă | n | R/trade | Train / Test | Fold-uri + | Ani + | Slippage ×4 | Risc la lot minim |
|---|---|---|---|---|---|---|---|
| OR 5m, breakout, închidere zi | 2263 | +0,089 | +0,104 / +0,075 | 6/8 | 6/10 | +0,003 | $0,76 |
| **OR 30m, direcție, închidere zi** | 2464 | +0,059 | +0,054 / +0,065 | **8/8** | 7/10 | **+0,032** | $1,00 |
| OR 30m, breakout, TP 3R | 2461 | +0,058 | +0,026 / +0,088 | 6/8 | 7/10 | +0,014 | $1,42 |

Observații:
- **Edge mic și nedovedit statistic:** N* (câte încercări suportă Sharpe-ul) = 1–3, iar noi am testat 18 (+160 în explorare).
  După corecția de căutare multiplă, nicio variantă nu e „dovedită”. 2026 e negativ până acum pe toate trei.
- Zilele cu știri (NFP) sunt **mai bune**, nu mai proaste — exact momentele „când intră toată lumea”. Nu le filtrăm.
- Varianta 30m-direcție intră la piață (fără ordin stop la deschidere) → aproape insensibilă la slippage; cea mai robustă.
- În bani: ~1 trade/zi, risc ~$1 (0,5% din cont), așteptare ~+$0,06/trade → câțiva zeci de $/an. **Nu e o sursă de venit**,
  e cel mult un strat mic, cu risc mic, care trebuie confirmat pe date viitoare.

Recomandare Faza 2: Daily Engine pe **US500, OR 30m direcție, închidere zi**, întâi în mod **SHADOW** pe contul real
(prețuri/spread reale, trade-uri virtuale înregistrate, ZERO ordine) — MT5 ține un singur cont pe terminal, deci un cont
demo separat ar cere un al doilea terminal. Trecere la ordine reale doar dacă shadow-ul confirmă pe ≥ 2–3 luni.

## 8. Comparație 4 piețe × dimineață / după-amiază (2026-10-31)

Script: `scripts/research_daily/orb_compare.py` → `data/research_daily/orb_compare.csv`. 216 variante (4 piețe × 3 ferestre × 18),
M5, costuri reale, M0. Dimineața: închidere forțată 16:25 RO (nu se suprapune cu după-amiaza). Verdicte: 202 DEMOTE, 8 OBSERVE, 6 KEEP.

| Piață | 09:00 RO (Frankfurt) | 10:00 RO (Londra) | 16:30 RO (New York) |
|---|---|---|---|
| **US500** | −0,085 (DEMOTE) | −0,051 (DEMOTE) | **+0,059…+0,089, 6 KEEP + 3 OBSERVE** |
| **GBPUSD** | −0,027 (DEMOTE) | **+0,075 (OBSERVE)** | −0,045 (DEMOTE) |
| EURUSD | −0,019 (DEMOTE) | +0,035 (OBSERVE, test ≈ 0) | −0,017 (DEMOTE) |
| GBPAUD | −0,065 (DEMOTE) | −0,041 (DEMOTE) | −0,126 (DEMOTE) |

(cea mai bună variantă din 18 pe fiecare celulă, R/trade)

- **Dimineață — GBPUSD la deschiderea Londrei (10:00 RO), OR 5 min, ordine stop, închidere 16:25 RO:** +0,075R,
  train +0,071 / test +0,084, ultimii 2 ani +0,069, 7/8 fold-uri. **Fragil:** la slippage ×2 scade la +0,033, la ×4 devine
  −0,048; variantele vecine (OR 15/30 min) sunt ~0; 2026 −0,47R până acum. Arată ca un vârf izolat, nu ca un efect larg.
- **După-amiază — US500 la deschiderea New York (16:30 RO):** singura celulă cu multe variante pozitive (9 din 18), deci
  efect mai larg, mai puțin dependent de o singură setare. Recomandat: OR 30 min, direcție, închidere 22:55 RO (8/8 fold-uri,
  rezistă la slippage ×4). Ultimii 2 ani ≈ 0 (+0,02).
- GBPAUD: negativ în toate cele 54 de variante → exclus.
- **Suprapunere de buget:** GBPUSD e deja tranzacționat de Bot Engine (S15) și de AI Engine → expunere dublă pe același
  simbol din același cont de ~$200. US500 nu e folosit de nimeni.

Recomandare: ambele în **SHADOW** (zero ordine) — US500 după-amiaza ca motor principal, GBPUSD dimineața ca candidat de
observație. Decizia de ordine reale se ia separat, pe datele shadow.

## 9. Re-intrare în prima oră după deschidere (2026-11-02) — RESPINS

Întrebare: dacă trade-ul zilei s-a închis pe SL (sau ziua a fost „invalidată”) în prima oră după deschiderea Londrei / New York-ului, să mai poată intra alte trade-uri? Script: `scripts/research_daily/orb_reentry.py` (aceleași reguli și costuri ca engine-ul; cu 1 trade/zi reproduce `orb_m5.run` trade cu trade: GBPUSD 3974, US500 2464). Re-intrare = după SL, o nouă rupere a ACELUIAȘI interval de deschidere (oricare margine), doar dacă intrarea e în primele W minute, max K trade-uri/zi, o poziție odată.

| Piață | Variantă | Trade-uri | R/trade | Total R | DD | Verdict |
|---|---|---|---|---|---|---|
| GBPUSD | **Acum (1/zi)** | 3974 | **+0,075** | **+297,6** | −139 | OBSERVE |
| GBPUSD | re-intrare 60 min, max 2 | 5793 | +0,027 | +156,1 | −192 | DEMOTE |
| GBPUSD | re-intrare 60 min, max 3 | 6265 | +0,015 | +96,9 | −233 | DEMOTE |
| US500 | **Acum (1/zi)** | 2464 | **+0,059** | **+145,8** | −55 | **KEEP** |
| US500 | re-intrare 60 min, max 2 | 2931 | +0,049 | +143,2 | −61 | OBSERVE |
| US500 | re-intrare 60 min, max 3 | 2945 | +0,050 | +147,0 | −61 | OBSERVE |

Trade-urile ÎN PLUS, luate separat: GBPUSD −0,078R/trade (60 min, 1819 trade-uri; test −0,149R), US500 −0,006R (467; antrenare −0,161R, test +0,100R) — fără câștig. Ferestrele 30 / 90 / 120 min: la fel sau mai rău (US500: intrarea e la 10:00, deci în fereastra de 30 min nu există re-intrare). Motiv: după un SL, intervalul de deschidere s-a dovedit „fals” (piață în range), iar ruperea în sens opus eșuează la fel de des; avantajul ORB e în PRIMA rupere.

Zilele „invalidate” pe GBPUSD (prima bară după interval atinge ambele margini, 322 de zile, aproape toate la 08:05): continuând căutarea, 314 trade-uri cu +0,326R — dar antrenare +0,458R / test −0,052R, 2013 aduce singur +57,8R, 2025–2026 negative, N* = 2 → zgomot, nu avantaj; în plus nerealizabil în live (ordinele stop se execută chiar în bara dublă). Decizie: rămâne 1 trade/zi/piață.


## 10. R:R fix (2R / 3R / 4R), re-intrări configurabile și alte intervale de deschidere (2026-11-03)

Implementare: ambele opțiuni sunt **per piață, oprite implicit** (`rr`, `reentry` în `daily_engine/config.json`; UI: „Opțiuni”
pe cardul pieței). Cu ele oprite, Daily face exact ce făcea: un trade pe zi, fără TP.

Re-intrare = după ce trade-ul curent se închide, de la lumânarea următoare (pauză configurabilă), o **nouă rupere a aceluiași
interval de deschidere** (oricare margine). Intrarea e permisă doar în primele `window_min` minute de la deschidere, cu un trade
deschis odată, maxim `max_trades` pe zi și STOP după `max_consec_losses` pierderi la rând. Funcția e verificată identică cu
`orb_reentry.py` pe tot istoricul.

Cercetare: `scripts/research_daily/orb_rr_reentry.py`, aceeași funcție ca engine-ul, costuri reale, verdict M0 →
`data/research_daily/orb_rr_reentry.csv`. Re-intrări = prima oră, max 3 pe zi, stop la 2 pierderi, pauză 1 lumânare.

**Configurația actuală (fără TP, fără re-intrări):**

| Piață | OR | R/trade | Trade-uri/săpt | Verdict |
|---|---|---|---|---|
| GBPUSD (Londra, breakout) | 5 | +0,075 | 4,6 | OBSERVE |
| US500 (New York, direcție) | 30 | +0,059 | 4,4 | KEEP |

**R:R fix**, aceeași piață și același OR:

| Piață | Fără TP | 2R | 3R | 4R |
|---|---|---|---|---|
| GBPUSD OR 5 | +0,075 | −0,016 | 0,000 | −0,005 |
| US500 OR 30 | +0,059 | +0,006 | +0,009 | +0,030 |

**Re-intrări** (fără TP):

| Piață | Fără re-intrări | Re-intrări 60 min, stop la 2 pierderi | 60 min, fără stop | 90 min | 120 min |
|---|---|---|---|---|---|
| GBPUSD OR 5 | +0,075 (4,6/săpt) | +0,027 (6,6/săpt) | +0,015 | +0,021 | +0,016 |
| US500 OR 30 | +0,059 (4,4/săpt) | +0,049 (5,3/săpt) | +0,050 | +0,035 | +0,038 |

**Alte intervale de deschidere (OR 5 / 15 / 30 / 60 min), fără TP:**
- GBPUSD: +0,075 / +0,004 / +0,026 / +0,009 → OR 5 rămâne cel mai bun.
- US500: +0,002 / +0,026 / +0,059 / +0,022 → OR 30 rămâne cel mai bun.
- Cu OR 60, re-intrările nu au efect: fereastra de 60 min se termină odată cu intervalul.

**Frankfurt (DE40, deschidere 09:00 Berlin), nou:**
- breakout: OR 5 +0,080 (KEEP), cu re-intrări +0,091 (KEEP, 6,2/săpt); OR 30 +0,070 (KEEP);
- direcție: OR 30 +0,080 (KEEP), cu re-intrări +0,082 (KEEP);
- singura piață unde re-intrările nu strică;
- **marja la lotul minim (0,1) e ~145 $**, iar riscul pe SL tipic e ~3–7 $ → nu încape acum în contul de ~206 $ partajat.

**Concluzii:**
1. Ținta fixă e mai slabă decât „fără TP” pe ambele piețe. ORB câștigă din puținele zile de trend mare, iar TP-ul le taie.
2. Re-intrările cresc frecvența cu 1–2 trade-uri pe săptămână, dar scad câștigul pe trade. Stopul la 2 pierderi la rând
   ajută (GBPUSD +0,027 față de +0,015 fără el).
3. Pentru test în shadow, cea mai puțin dăunătoare variantă e US500 cu re-intrări în prima oră (+0,049R).
4. DE40 e candidatul cel mai bun pentru Daily când contul permite marja.


## 11. Piața fiecărui slot — schimbabilă din UI, cu costuri automate (2026-11-03)

Daily păstrează pattern-ul cu **două sloturi** (dimineață / după-amiază). Pe fiecare se alege bursa, cu șablonul ei testat:

| Bursă | Ora locală | Interval de deschidere | Mod |
|---|---|---|---|
| Londra | 08:00–14:25 | 5 min | breakout |
| Frankfurt | 09:00–17:25 | 5 min | breakout |
| New York | 09:30–15:55 | 30 min | direcție |

Peste bursă se alege piața din MT5. Costurile se calculează **automat** din spread:
- **slippage** = 25% din spread-ul live;
- **„comision”** = spread-ul live minus spread-ul din istoricul barelor, adică markup-ul contului Standard, pe care istoricul nu
  îl conține;
- se pot și suprascrie manual.

„Previzualizează” rulează un backtest rapid pe ~3 ani, din MT5, cu aceeași funcție ca engine-ul.

**Ultimii 3 ani (2023-11 → 2026-11), costuri auto, fără TP, fără re-intrări:**

| Piață / bursă | Trade-uri/săpt | R/trade | Verdict M0 | Marjă lot minim |
|---|---|---|---|---|
| **DE40 / Frankfurt** | 4,8 | **+0,141** | KEEP (train +0,16 / test +0,09) | ~145 $ |
| GBPUSD / Londra | 4,7 | +0,066 | DEMOTE (train +0,28 / **test −0,43**) | ~45 $ |
| EURUSD / Londra | 4,7 | +0,032 | DEMOTE (test −0,18) | ~37 $ |
| US500 / New York | 5,0 | +0,029 | DEMOTE (test +0,00) | ~38 $ |
| XAUUSD / New York | 5,0 | −0,039 | DEMOTE | ~200 $ |
| US30 / New York | 5,0 | −0,035 | DEMOTE | ~262 $ |

Observații:
- **GBPUSD s-a degradat puternic în ultimele ~11 luni** (−0,43R pe trade).
- **US500 e ~0 pe ultimii 3 ani**, față de +0,059 pe tot istoricul.
- **DE40 e singurul solid și recent**, dar marja nu încape acum în contul de ~206 $ partajat.

## 12. Break-even în trepte + SL mai larg (2026-11-06) — RESPINS

Script: `scripts/research_daily/daily_be_ladder.py` (intrările exacte ale engine-ului, fără TP, închidere la final de
fereastră, costuri reale; ordinea pe bară conservatoare). Regula propusă: la 2R → SL pe 1R, la 3R → SL pe 2R …

| | R / trade actual | cu BE 2R → 1R | cea mai bună variantă BE (16) | SL × 1,25 / 1,5 / 2 |
|---|---|---|---|---|
| GBPUSD (3974 trade-uri) | +0,069 | −0,013 | +0,031 (5R → 3R) | +0,021 / +0,039 / +0,011 |
| DE40 (2595) | +0,084 | +0,046 | +0,087 (3R → 1R, zgomot) | +0,056 / +0,073 / +0,058 |
| GBPUSD ultimele 12 luni | **−0,468** | −0,161 | −0,162 | — |

- BE ridică win rate-ul (20 → 37%) și scade drawdown-ul, dar taie zilele de +5…+15R care fac profitul strategiei.
- BE nu repară o piață fără edge: GBPUSD rămâne puternic negativ pe ultimele 12 luni (și costul ~0,15R / trade).
- SL mai larg: nicio variantă peste SL-ul actual (marginea opusă a intervalului).

**Decizie (2026-11-06, alex-live):** slotul 1 GBPUSD Londra → **US500 New York** (30 min, direcție), pentru
observație în shadow. Pe 3 ani: GBPUSD +0,020R (test −0,473R) față de US500 +0,031R (test ≈ 0, DD −36R, marjă ~37 $).
Din 13 piețe × burse testate niciuna nu e KEEP în afară de DE40.

## 13. Pregătirea pentru Live (2026-11-12): moduri per piață, Profit Lock, DE40

**Moduri per piață:** fiecare slot are modul lui (LIVE / SHADOW / PAUZĂ) — o piață nu o afectează pe cealaltă.
LIVE pe cont real cere în continuare „Daily Engine” deblocat în Trading LIVE. O piață nouă într-un slot pornește în
SHADOW. Plus: limita de marjă (marja totală a contului după ordin ≤ 80% din equity) și închiderea de vineri globală.

**Profit Lock** (Trigger → Lock R, oprit implicit) — `scripts/research_daily/daily_profit_lock.py`, tot istoricul M5,
configurația curentă (re-intrări pornite):

| | fără | 3,5→3 | 4,5→4 | 5→4 | 6→5 | 8→6 | 10→8 |
|---|---|---|---|---|---|---|---|
| DE40 R/trade | **+0,095** | +0,046 | +0,072 | +0,095 | +0,084 | +0,089 | +0,089 |
| DE40 DD (R) | −66 | −67 | −56 | **−57** | −64 | −72 | −65 |
| US500 R/trade | **+0,046** | +0,011 | +0,022 | +0,019 | +0,035 | +0,043 | +0,043 |

La 4,5→4R pe DE40: profit protejat +291R, profit pierdut (trade-uri închise mai devreme decât ar fi mers) −371R.
Nicio variantă mai bună decât strategia actuală; 5→4R e la egalitate cu drawdown mai mic.

**DE40 — analiza de pregătire** (`scripts/research_daily/de40_live_readiness.py`):

| | trade-uri | R/trade | t | PF | WR | DD |
|---|---|---|---|---|---|---|
| Tot istoricul (2016–2026) | 3428 | +0,095 | 2,47 | 1,14 | 28% | −66R |
| Train (primele 70%) | 2399 | +0,111 | 2,37 | 1,16 | 29% | −52R |
| **Test (de la 10.08.2023)** | 1029 | **+0,058** | **0,87** | 1,08 | 27% | −55R |
| Shadow (10 trade-uri) | 10 | +0,89 | — | — | 20% | −5R |

- Pe ani: 2016 −0,01 · 2017 +0,08 · 2018 +0,08 · 2019 +0,05 · 2020 +0,09 · 2021 +0,18 · 2022 +0,35 · **2023 −0,13**
  · 2024 +0,01 · 2025 +0,29 · 2026 +0,02 → regim-dependent; perioada de test nu e semnificativă statistic (t 0,87).
- Ore: 92% din intrări în prima oră (09h Berlin, +0,10R); intrările târzii (11h+) sunt puține și slabe.
- Zile: luni ≈ 0 (+0,006R), joi cel mai bine (+0,18R).
- Costuri: spread live 0,5 puncte (istoric 0,8); **+1 punct de slippage înjumătățește edge-ul (+0,039R), +2 puncte îl
  anulează (−0,013R)** → execuția (slippage la breakout) e riscul principal.
- Cont (~195 $): marja la lotul minim 148 $ (76% din equity); riscul la lotul minim pe SL-ul real = 2,4 / 3,0 / 3,9 /
  4,9% din equity (P25 / mediană / P75 / P90) — de ~3× peste ținta de 1%; limita globală 5% ar bloca ~10% din trade-uri.
- Specificații MT5: tick 0,01, lot 0,1 / pas 0,1, stops / freeze level 0, filling IOC; profit în EUR (convertit de MT5).

**Verdict: CONDITIONALLY READY.** Tehnic gata (execuție testată pe MT5 simulat, toate protecțiile). Condiții: (1) accepți
~3% risc real pe trade la lotul minim (nu 1%); (2) DE40 ocupă ~76% din marjă — cu alte poziții deschise ordinul NU se
plasează (limita de marjă); (3) edge-ul out-of-sample e pozitiv dar nesemnificativ și sensibil la slippage. Recomandare:
LIVE doar pe DE40, cu US500 în SHADOW, după decizia ta; ideal cu un cont mai mare (~1000 $) ca riscul să coboare la ~1%.

## 14. DE40 la deschiderea New York + US30 (2026-11-12)

Tot istoricul M5, regulile curente (30 min, direcție, fără TP), costuri reale; risc / marjă pe contul de ~196 $.

| Variantă | trade-uri | R/trade | t | test (30%) | DD | marjă lot min | risc lot min (mediană) |
|---|---|---|---|---|---|---|---|
| DE40 Frankfurt 09:00 (actual) | 3428 | **+0,095** | 2,47 | +0,058 | −66R | 148 $ (76%) | 3,2% |
| DE40 la deschiderea NY (15:30 Berlin) | 2931 | +0,042 | 1,31 | +0,028 | −83R | 148 $ (76%) | 3,3% (21% din zile > 5%) |
| US500 NY (actual) | 2926 | +0,045 | 1,29 | +0,024 | −66R | 38 $ (20%) | 1,1% |
| **US30 NY** | 2465 | **−0,016** | −0,39 | −0,029 | −96R | **263 $ (135%)** | 9,0% |
| US30 Frankfurt 09:00 | 2576 | +0,074 | 1,10 | +0,140 | −140R | 263 $ | 1,8% (WR 16%, train +0,046) |
| US30 Londra 08:00 | 2574 | +0,051 | 0,97 | +0,144 | −98R | 263 $ | 1,8% (train +0,011) |

- DE40 după-amiaza: pozitiv, dar la jumătate față de dimineață, regim-dependent (2026 −0,13R); doi sloturi pe același
  simbol nu sunt suportate (același comment de zi).
- US30: la deschiderea NY e negativ; variantele Frankfurt / Londra sunt instabile (WR 16–23%, train ~0). Marja la lotul
  minim depășește contul (263 $ > 196 $) → pe contul actual NU se poate tranzacționa deloc.

## 15. Mai multe sesiuni pe aceeași piață + limita de trade-uri / zi (2026-11-13)

Fiecare piață poate tranzacționa în oricare dintre sesiunile Londra (08:00), Frankfurt (09:00), New York (09:30), cu
regulile testate pe fiecare deschidere. Trade-urile se admit în ordine cronologică: maxim N / zi pe piață (toate
sesiunile + re-intrările) și niciodată două poziții simultan pe aceeași piață. Tot istoricul M5, costuri reale,
configurația curentă (re-intrări pornite, max 3 / sesiune):

| Piață · sesiuni | max / zi | trade-uri / săpt | R/trade | total | DD | M0 |
|---|---|---|---|---|---|---|
| DE40 · Frankfurt (actual) | 3 | 6,6 | **+0,095** | +326R | −66R | KEEP |
| DE40 · Frankfurt + NY | 1 | 5,0 | +0,082 | +223R | −56R | KEEP |
| DE40 · Frankfurt + NY | 2 | 7,9 | +0,082 | +354R | −78R | KEEP |
| DE40 · Frankfurt + NY | 3 | 9,1 | +0,074 | +371R | −77R | KEEP |
| DE40 · Londra + Frankfurt + NY | 2 | 9,1 | +0,060 | +302R | −62R | KEEP |
| US500 · NY (actual) | 3 | 5,9 | **+0,045** | +133R | −66R | DEMOTE |
| US500 · Londra + NY | 2 | 8,9 | −0,064 | −318R | −325R | DEMOTE |
| US500 · Frankfurt + NY | 2 | 8,3 | −0,049 | −224R | −239R | DEMOTE |

Pe DE40 a doua sesiune (NY) adaugă frecvență (+1,3 trade-uri / săpt la max 2) cu același R/trade și drawdown mai mare;
pe US500 sesiunile europene sunt negative (deschiderea europeană nu se potrivește indicelui american).
