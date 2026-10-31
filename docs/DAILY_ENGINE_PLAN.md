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
