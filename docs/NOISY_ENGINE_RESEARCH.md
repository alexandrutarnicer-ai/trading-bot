# Noisy Engine — research, analiză și verdict

*Data: 2026-11-01 · Cont analizat: ICMarketsEU #13136652 (REAL, ~$206, 1:30) · Status: **research, NIMIC implementat***

Toate cifrele de mai jos sunt **măsurate pe contul real, doar citire, fără niciun ordin**. Scripturile sunt în `scripts/research_noisy/`, iar rezultatele brute în `data/research_noisy/*.json`. Sursele externe sunt marcate ca **[fapt documentat]**, **[cercetare]** sau **[experiență/opinie]**.

---

## Executive Summary

**Ce ar fi Noisy Engine:** un engine de frecvență mare (M1 / tick) pe o singură piață, care intră des și schimbă rapid bias-ul Long/Short.

**Verdict: NO-GO pentru Noisy Engine în forma cerută** (M1/tick, multe trade-uri pe zi, cu bani reali). Există o singură cale **condiționată și ieftină**: un test „Noisy-lite” în **SHADOW** (zero ordine). Ar rula pe **M5**, cu mean-reversion pe **USDJPY** (sau XAUUSD pe un cont mai mare), timp de 8–12 săptămâni, cu criterii de trecere fixate dinainte. Detalii în §20.

De ce, pe scurt, din datele noastre:

1. **Pe M1, momentum și continuarea de trend pierd chiar înainte de costuri** pe toate cele 12 piețe testate (brut −0,01…−0,07R pe trade). Zgomotul pe minut revine spre medie și nu continuă.
2. **Singurul efect pozitiv înainte de costuri e mean-reversion: aproximativ +0,05R brut pe trade.** Costul unui trade pe M1 e tot ~0,05–0,10R, deci edge-ul brut ≈ costul și net ≈ 0 sau negativ.
3. **Pe M5 (5 trade-uri/zi în loc de 30–40) costul scade la ~0,02R.** Mean-reversion iese ușor pozitiv pe 4 piețe, dar **niciuna nu trece pragul de semnificație corectat pentru 72 de combinații testate (t ≥ 2,98)**. Cele mai bune: USDJPY t = 2,0 și XAUUSD t = 1,47.
4. **Costul e factorul dominant, iar tipul contului schimbă totul.** Contul are acum comision 0 în istoric. Cu comisionul public Raw ($7/lot dus-întors), toate strategiile FX devin puternic negative (−0,1…−0,7R/trade).
5. **Lipsesc datele care dau edge-ul real al HFT.** Depth of Market e **indisponibil pe toate simbolurile** la broker, iar volumul real e **absent** (doar tick volume). Latența ordinului spre server **nu e măsurabilă** pe contul real fără ordine. Concurența la această frecvență e făcută de firme specializate, cu latențe de micro-secunde **[cercetare: Budish et al.; Aquilina et al.]**.
6. **Contul de $206 nu permite piața cea mai robustă (XAUUSD):** marja la lotul minim e ~$194, iar riscul la un SL tipic e ~2,7%, peste limita globală de 2%.

---

## 1. Concept

Noisy Engine, așa cum e definit în brief:

- **Piață și ritm:** o singură piață; monitorizare la nivel de tick/minut; mai multe trade-uri pe zi.
- **Adaptare:** schimbare rapidă Long/Short, cu reguli și filtre proprii.
- **Limite:** buget izolat, limite de trade-uri și de pierderi.
- **Pornire:** fără autostart, cu modal de confirmare, eventual pornire programată.
- **Restricții globale:** le respectă pe toate.

Concluzia research-ului reformulează conceptul. **Frecvența potrivită pentru acest cont și broker nu e M1/tick, ci M5 (3–6 trade-uri/zi).** Varianta care merită testată e „noisy” față de celelalte engine-uri (Custom ~4–5 trade-uri/săptămână), dar nu e HFT.

## 2. Market Research

Măsurat pe tick-urile reale ale brokerului, săptămâna 26–30 oct 2026, plus 12 luni de bare M1/M5.

| Piață | Lot min | Marjă lot min | Cost dus-întors* | Cost / range M1 | Cost / range M5 | Tick-uri/min | Spike spread** | Ora cea mai ieftină (RO) |
|---|---|---|---|---|---|---|---|---|
| EURUSD | 0.01 | $37 | $0.01 | 0.10 | 0.04 | 39 | 45× | 13 |
| GBPUSD | 0.01 | $45 | $0.02 | 0.17 | 0.07 | 66 | 42× | 16 |
| **USDJPY** | 0.01 | $33 | $0.006 | **0.06** | **0.02** | 61 | 98× | 3*** |
| AUDUSD | 0.01 | $35 | $0.01 | 0.13 | 0.05 | 44 | 37× | 3*** |
| **XAUUSD** | 0.01 | **$194** | $0.09 | **0.07** | **0.03** | 159 | 5× | 16 |
| XAGUSD | 0.01 | – | $0.12 | 0.33 | 0.13 | 116 | 2× | 16 |
| USTEC (US100) | 0.1 | $142 | $0.10 | 0.09 | 0.04 | 229 | 1× | 16 |
| US500 | 0.1 | $38 | $0.05 | 0.31 | 0.12 | 71 | 1× | 16 |
| US30 | 0.1 | $259 | $0.12 | 0.11 | 0.04 | 107 | 1× | 15 |
| DE40 | 0.1 | $144 | $0.06 | 0.08 | 0.03 | 75 | 5× | 10 |
| BTCUSD | 0.01 | $389 | $0.12 | 0.35 | 0.13 | 215 | 2× | 16 |
| ETHUSD | 0.01 | – | $0.03 | **1.90** | 0.73 | 136 | 1× | 16 |

\* Spread median + comision din istoric (0), la lotul minim, fără slippage. \*\* Spread-ul maxim al minutelor din percentila 99 față de mediana spread-ului. \*\*\* Ora nocturnă: spread mic, dar și mișcare mică; nu e o fereastră utilă.

**Concluzii pe piețe:**

- **USDJPY:** cel mai ieftin raport cost/mișcare dintre FX, marjă mică ($33) și risc la lotul minim ~$0,40. **Cel mai potrivit pentru contul actual.** Slăbiciunea lui: spike-uri de spread de ~100× la rollover (23:00–00:00 RO).
- **XAUUSD:** cel mai robust la costuri (cost/range M5 0,03), spike-uri mici (5×) și foarte activ (159 tick-uri/min). **Nu încape însă în contul de $206:** marja la lotul minim e $194, iar riscul la un SL tipic M5 e ~$5,5 (2,7%).
- **EURUSD:** ieftin, dar mișcarea pe minut e mică. Pe test nu arată edge (§4). Popularitatea lui nu îl face potrivit.
- **US500:** costul e prea mare față de mișcare (0,31 pe M1). Rămâne bun pentru Daily (ORB pe 30 de minute), nu pentru frecvență mare.
- **USTEC, US30, DE40:** raport cost/mișcare bun, dar marja la lotul minim e $142–259. Pe M1 nu au arătat edge.
- **BTCUSD, XAGUSD și mai ales ETHUSD:** costul e prea mare față de mișcare. **Excluse.**

**Spread-ul în timp:**
- **FX:** spike-urile de spread (până la 250× mediana pe EURUSD) cad sistematic la **23:00 RO (rollover)**. Pe FX, orele 22:00–00:00 trebuie excluse obligatoriu.
- **Aurul:** spike-urile cad pe știrile din SUA (ex. joi 14:30, miercuri 20:00 RO = FOMC/date SUA).
- **Indicii US:** au spread aproape constant (1–5×).

## 3. Data

Verificat pe contul și terminalul nostru, nu doar teoretic:

| Sursă | Disponibil | Detalii |
|---|---|---|
| M1 OHLC (+ spread pe bară) | ✅ | 12 luni descărcate fără probleme |
| Tick-uri Bid/Ask (`copy_ticks_range`) | ✅ | FX/metale din **2023-07**, indici/crypto din **2023-11** |
| Tick volume | ✅ | doar număr de tick-uri, nu volum tranzacționat |
| Real volume | ❌ | 0 pe toate simbolurile (CFD/OTC) |
| Depth of Market (`market_book_add`) | ❌ | **gol pe toate cele 12 simboluri** |
| Latență Python → terminal | ✅ | ~0,013 ms per apel (median), neglijabilă |
| Latență ordin → server | ❓ | **nemăsurată**; necesită un cont DEMO |
| Calendar economic | ✅ | ForexFactory (deja în `news_guard`); MT5 Python nu are API de calendar |
| Sesiuni / program piață | ✅ | `symbol_info` + regulile existente |

**Ce înseamnă:** fără DOM și fără volum real nu putem construi strategii pe fluxul de ordine (order-flow, dezechilibre în carte), adică exact sursa de edge pe termen foarte scurt a firmelor HFT. Rămâne doar prețul (bid/ask) și tick volume-ul.

[fapt documentat] Funcțiile `copy_ticks_range` și `market_book_add` sunt documentate în [referința MQL5 Python](https://www.mql5.com/en/docs/python_metatrader5/mt5copyticksrange_py) și [market_book_add](https://www.mql5.com/it/docs/python_metatrader5/mt5marketbookadd_py). Disponibilitatea DOM depinde de broker și instrument; la noi lipsește.

## 4. Strategy

Am testat 3 strategii-tip **fixate dinainte, fără optimizare**, pe 12 piețe × 2 timeframe-uri × 2 scenarii de cost:

- **MOM:** breakout Donchian 20 de bare; SL 1×ATR, TP 1,5×ATR, stop de timp.
- **MR:** mean reversion la EMA20 ± 2×ATR; TP la EMA20, SL 1,5×ATR.
- **TRD:** continuare de trend EMA20/EMA100 după pullback; SL 1×ATR, TP 2×ATR.

Detalii comune:
- Intrare la bara următoare (fără să vadă viitorul); la SL și TP în aceeași bară se presupune SL (prudent); o singură poziție odată.
- Doar în orele lichide; împărțire train 70% / test 30%.
- **Cost:** spread-ul real al orei + comision + slippage 25% din spread la intrare și la ieșire.

**M1, costuri măsurate (scenariul A):**

| | MOM brut → net | MR brut → net | TRD brut → net | Trade-uri/zi |
|---|---|---|---|---|
| EURUSD | −0.017 → −0.111R | +0.066 → +0.003R | +0.014 → −0.082R | 30–40 |
| USDJPY | −0.018 → −0.109R | +0.050 → −0.011R | −0.038 → −0.127R | 31–39 |
| XAUUSD | −0.047 → −0.113R | +0.048 → +0.004R | −0.020 → −0.084R | 31–44 |
| USTEC | −0.025 → −0.140R | +0.012 → −0.065R | −0.013 → −0.128R | 15–23 |
| DE40 | +0.012 → −0.065R | +0.013 → −0.038R | +0.059 → −0.018R | 24–33 |
| (restul) | negativ | negativ | negativ | |

**Concluzia pe M1:** momentum-ul nu există pe minut (brut negativ peste tot), iar mean-reversion are brut ≈ cost. **Nicio combinație pe M1 nu e profitabilă după costuri** pe test.

**M5, costuri măsurate, mean reversion:**

| | Trade-uri/zi | Net/trade | t-stat | P(edge>0) bootstrap | Trimestre + | Max DD | Serie pierderi | Cu slippage dublu | Cu comision Raw $7 |
|---|---|---|---|---|---|---|---|---|---|
| **USDJPY** | 5.1 | +0.069R | **2.00** | 0.97 | 3/5 | −44R | 9 | +0.062R | **−0.085R** |
| **XAUUSD** | 5.3 | +0.049R | 1.47 | 0.94 | 4/5 | −33R | 16 | +0.044R | +0.040R |
| AUDUSD | 5.1 | +0.040R | 1.18 | 0.90 | 4/5 | −45R | 9 | +0.029R | −0.118R |
| US30 | 3.0 | +0.009R | 0.21 | 0.58 | 3/5 | −26R | 17 | 0.000R | +0.009R |
| EURUSD | 5.2 | +0.006R | 0.18 | 0.59 | 4/5 | −37R | 17 | −0.003R | −0.120R |

Pe M5, momentum și trend au rămas negative pe toate piețele.

**De ce nu e suficient:**
- **Am încercat 72 de combinații.** Ca un rezultat să nu fie noroc de căutare, pragul corectat e t ≥ 2,98 (Bonferroni, p < 0,05/72). **Niciunul nu-l atinge.**
- **USDJPY (t = 2,0) depinde complet de faptul că nu plătim comision.**
- **XAUUSD are un drawdown de 33R:** la 1% risc pe trade, asta înseamnă −33% din cont.

**Strategii potrivite pentru un eventual test:** doar **mean reversion pe M5, în orele lichide, cu filtru de spread**. **Nu:** breakout/momentum pe M1, scalping pe tick, nimic bazat pe order-flow (date inexistente).

[cercetare] Singurul efect intraday bine documentat academic e momentum-ul „prima jumătate de oră prezice ultima jumătate de oră” pe indici: [Gao, Han, Li, Zhou, *JFE* 2018](https://econpapers.repec.org/RePEc:eee:jfinec:v:129:y:2018:i:2:p:394-414). E un efect pe ore, nu pe minute, și verificările independente arată că e greu de exploatat după costuri ([cxoadvisory](https://www.cxoadvisory.com/?p=25481)). Pe el se sprijină deja Daily Engine (ORB), nu Noisy.

### 4b. Piețe cu capital mic (adăugate la cerere: XRP + perechi FX ieftine)

Aceeași metodă, aceleași 3 strategii, costuri măsurate pe cont (scenariul A). Cost/range = costul unui trade dus-întors față de mișcarea tipică pe minut, respectiv pe 5 minute.

| Piață | Cost/range M1 | M1: cel mai bun net (MR) | M1 MOM / TRD net | M5: cel mai bun net (MR) | Verdict |
|---|---|---|---|---|---|
| XRPUSD | **2,55** | −2,93R | −4,1R | −1,03R | exclus (spread > mișcarea pe minut) |
| USDCAD | 0,19 | −0,12R | −0,21 / −0,19R | −0,06R | negativ |
| USDCHF | 0,30 | −0,22R | −0,36 / −0,36R | −0,07R | negativ |
| NZDUSD | 0,13 | −0,08R | −0,18 / −0,18R | +0,007R (test −0,024) | ~0 |
| EURJPY | 0,55 | −0,37R | −0,74 / −0,70R | −0,12R | negativ |
| GBPJPY | 0,24 | −0,13R | −0,35 / −0,30R | −0,03R | negativ |
| CHFJPY | 0,23 | −0,10R | −0,30 / −0,29R | −0,007R (test +0,012) | ~0 |
| NZDJPY | 0,30 | −0,14R | −0,38 / −0,34R | −0,09R | negativ |
| AUDJPY | 0,19 | −0,09R | −0,29 / −0,27R | −0,04R (test +0,015) | ~0 |
| EURGBP | 0,36 | −0,17R | −0,42 / −0,37R | +0,003R (test −0,025) | ~0 |
| EURCHF | 0,50 | −0,35R | −0,62 / −0,58R | −0,15R | negativ |

GBPUSD era deja în tabelul principal: pe M1, MR −0,05R, MOM −0,17R, TRD −0,14R.

**Concluzie pentru varianta pe M1 (23 de piețe în total):** pe M1, **nicio piață disponibilă nu are câștig după costuri**, cu niciuna dintre cele 3 strategii.

Motivul e același peste tot. Mean-reversion câștigă înainte de costuri doar **+0,03…+0,07R**, iar costul unui trade pe M1 e de **0,06R (USDJPY, cea mai ieftină) până la peste 0,4R**.

Ca M1 să funcționeze, câștigul pe trade ar trebui să fie de 2–3 ori mai mare decât am găsit. Practic asta înseamnă ținte mai mari și mai puține trade-uri, adică exact varianta M5.

### 4c. Țintă mai mare (R:R fix) și Break-Even — testat la cerere (2026-11-01)

Aceeași funcție ca engine-ul, pe barele reale de 12 luni (USDJPY), 30 de variante. Câștig mediu pe trade, după costuri:

| Variantă | M1 (~25/zi) | M5 (~4/zi) |
|---|---|---|
| **Acum** (țintă = revenirea la EMA20) | −0,010R · WR 41% · DD −117R | **+0,081R** · WR 44% · DD −31R |
| R:R fix 1,5 / 2 / 3R | −0,012 / −0,029 / −0,003R | +0,061 / +0,058 / +0,041R |
| Break-Even Custom implicit (80 / 30, faza 2 40 / 50) | −0,006R · WR 45% · DD −104R | +0,069R · WR 48% · DD −31R |
| Break-Even fără faza 2 (80 / 30) | −0,006R · WR 45% · DD −103R | +0,070R · WR 48% · DD −31R |
| BE după +0,5R (prototip) | −0,028R · WR 23% | +0,059R · WR 25% · DD −17R |

**Concluzie:** nici ținta mai mare, nici break-even-ul nu cresc profitul. Break-even-ul crește win rate-ul și reduce puțin scăderile.
La mean reversion prețul atinge des 80% din drum și revine, iar SL-ul mutat taie trade-uri care ar fi ajuns la țintă; o țintă
fixă mai depărtată e atinsă rar în 20 de bare. Ambele rămân OPȚIONALE în Noisy Engine, **dezactivate implicit**.

## 5. Filters

**Obligatorii (rapide, fără AI):**
1. **Global guard:** protecția capitalului, circuit breaker, știri, max poziții pe piață, risk cap. Prin `global_guard.check_open`, existent.
2. **Fereastră de timp:** doar orele lichide ale pieței; **exclus 22:00–00:00 RO** (rollover, spread până la 250×). Exclus vineri seara și duminică seara.
3. **Spread live ≤ 1,5× mediana orei** (din profilul măsurat). Altfel, nicio intrare.
4. **Știri High pe valutele pieței:** fără intrări între −5 și +15 minute; pozițiile se închid înainte.
5. **Cost/ATR:** dacă ATR-ul curent M5 < 15× costul dus-întors, nu se intră (mișcare prea mică față de cost).
6. **Buget / limite proprii** (§8).

**Opționale (testate doar dacă trec criteriile de shadow):**
- **Filtru de regim:** efficiency ratio. Mean-reversion merge în range, nu în trend. Indicatorul există deja în AI Engine (`_efficiency_ratio`).
- **Activitate:** tick-uri/minut peste mediana orei, ca semn de lichiditate.

Fiecare filtru opțional e o variantă nouă care trebuie validată pe test. Nu le adunăm „ca să arate bine”.

## 6. Long/Short Adaptation (anti flip-flop)

Mean-reversion schimbă natural direcția: cumpără după scădere, vinde după creștere. Riscul de flip-flop vine din intrări repetate pe zgomot. Reguli:
- **O singură poziție odată.** Fără inversare directă dintr-o poziție în cea opusă.
- **Pauză după o ieșire:** minimum 3 bare M5 (15 minute) până la o nouă intrare. După un SL, 6 bare.
- **Pauză în trend:** dacă efficiency ratio arată trend clar (≥ 0,35), mean-reversion stă deoparte, în loc să se pună în fața trendului.
- **Rata de inversare:** dacă direcția s-a schimbat de mai mult de 3 ori într-o oră, engine-ul se oprește până la ora următoare. Asta e și o metrică urmărită.

## 7. Execution

| Element | Măsurat / cunoscut | Impact |
|---|---|---|
| Spread | median EURUSD 0,1 pip, USDJPY 0,1 pip, XAU 9 cenți, USTEC 1 pt | se poate suporta pe M5, la limită pe M1 |
| Comision | **0 în istoricul contului** (de verificat tipul contului) | cu $7/lot RT orice FX pe M1/M5 devine negativ |
| Slippage | **nemăsurat**; ipoteza din test: 25% din spread × 2 | la 100% din spread, edge-ul XAU scade de la +0,049 la +0,032R |
| Latență ordin | **nemăsurată** (cont real) | trebuie măsurată pe DEMO |
| Stops level / freeze | 0 pe toate | nu blochează SL/TP apropiate |
| Spike-uri de spread | rollover FX 100–250×; știri US pe aur 20× | filtrele obligatorii 2–4 |

[fapt documentat] Prețul se poate schimba între trimiterea ordinului și execuție (slippage), mai ales în volatilitate și la volume mari: OANDA, citat în brief. [cercetare] Spread-urile se lărgesc în jurul anunțurilor macro, iar efectul e mai mare pe spread și volatilitate decât pe curs ([Cogent Economics & Finance, 2022](https://doaj.org/article/057342acef1742bf8a99571509ec8e90); [EBS, NTU](https://econ.ntu.edu.tw/wp-content/uploads/2023/12/macro_1050526.pdf)). Măsurătoarea noastră confirmă aceeași lărgire pe aur.

**Cât din edge consumă costul:**
- **Pe M1:** 100% sau mai mult.
- **Pe M5:** ~25–50% din edge-ul brut al mean-reversion la costurile actuale, și peste 100% cu comision Raw pe FX.

## 8. Risk

Ierarhia cerută în brief **e validă și se potrivește cu arhitectura existentă**, cu o precizare: limitele proprii stau după global guard și înainte de semnal. Global guard e aplicat deja de Custom, AI și Daily prin `check_open`.

**Global Safety → Global Risk (`global_guard`) → Budget Protection Noisy → Trade/Loss limits Noisy → Market config → Filtre obligatorii → Filtre opționale → Semnal → Execuție (cu verificarea cost/spread în ultimul moment)**

**Recomandarea Trader + PM pentru limite:**
- **Max Trades: per zi** (resetat la miezul nopții, ora aplicației). Implicit **6**, cât frecvența naturală măsurată; opțional dezactivat. Pe „engine run” e prea ușor de ocolit prin restart, iar „per interval” complică inutil.
- **Max Losses: per zi**, implicit **3 pierderi la rând** sau **4 pe zi**. Lockout **până a doua zi**: nu până la repornirea manuală, ca să nu încurajeze „încă o încercare” emoțională. Resetare manuală doar cu confirmare.
- **Budget Protection (izolat):**
  - Se calculează **pe trade-urile atribuite engine-ului** (magic propriu, ex. 990001).
  - **Pierdere = P&L realizat (profit + comision + swap, din deal-urile MT5) + P&L flotant al pozițiilor deschise acum.**
  - Se compară cu bugetul alocat și cu pragul minim. Exemplu: buget $100, minim $10 → stop când bugetul rămas (100 + P&L total) ≤ 10.
  - **Folosim P&L-ul engine-ului, nu equity-ul contului.** Equity-ul include celelalte engine-uri, iar o pierdere a Custom nu trebuie să oprească Noisy, nici invers.
  - P&L-ul MT5 e deja în valuta contului (USD), deci nu e nevoie de conversie suplimentară.
  - **Resetarea bugetului e doar manuală,** cu confirmare dublă și notificare Telegram.
- **Oprire de buget:** nicio intrare nouă și închiderea imediată a pozițiilor deschise (vezi §13).
- **Risc pe trade:** 1% din bugetul engine-ului, nu din cont, plafonat de limita globală de 2% din equity. **La lotul minim, riscul real e mai mare decât ținta la conturi mici,** iar `apply_risk_cap` blochează atunci ordinul. Pe USDJPY merge; pe XAU nu, la $206.

## 9. AI

**Latența măsurată acum, în acest research:**
- **Ollama local** (`qwen3:1.7b` pe acest PC): **9–14 s** per rol.
- **Gemini:** **8–12 s**.
- Consiliul complet (4 roluri): ~40 s.

Edge-ul mean-reversion pe M5 se desfășoară în ~40 de minute de ținere. Pe M1 ar fi minute, pe tick secunde.

| Variantă | Verdict |
|---|---|
| A. AI la fiecare semnal | **NU**: 10–40 s întârziere pe un semnal de M5 schimbă prețul de intrare; pe M1/tick e absurd |
| B. AI doar peste un prag de încredere | **NU**: aceeași latență, iar semnalul nu are „încredere” |
| C. AI la schimbarea de regim | posibil, dar regimul se calculează determinist (efficiency ratio) în milisecunde |
| D. AI periodic, pentru context | **DA, opțional**: de ex. o dată pe oră sau înainte de sesiune, un rezumat „zi de evitat” (știri, volatilitate) |
| **E. Fără AI în bucla de execuție** | **DA, recomandat**: logica rămâne deterministă, rapidă, testabilă |

În plus, modelul local mic (1,7B) a produs erori factuale clare în consultarea de azi: a confundat XAUUSD cu argintul și a inventat cifre. **Nu e de încredere pentru decizii de trading.**

**[REZOLVAT 2026-11-01, vezi `ai_engine/providers.py` + `scripts/test_gemini_truncation.py`]** Problemă descoperită în timpul research-ului, **în afara Noisy:** adaptorul Gemini cere maximum 2.000 de tokeni, iar `gemini-2.5-flash` își consumă bugetul pe „gândire” internă înainte de răspuns. Răspunsul lung a fost tăiat după 229 de caractere. Poate afecta și **Head Trader-ul din AI Engine**: un JSON tăiat duce la WAIT. **De verificat separat** (fix propus: `thinkingConfig.thinkingBudget: 0` sau o limită mai mare).

## 10. Resources

| Resursă | Estimare pentru 1 piață | Concluzie |
|---|---|---|
| CPU | 40–230 tick-uri/min = sub 4 evenimente/s; indicatorii pe M5 se calculează în < 1 ms | neglijabil (< 1% dintr-un nucleu) |
| RAM | o zi de tick-uri ≈ 100–300 MB brut (pentru research); în engine doar ultimele bare: < 50 MB | mic |
| GPU | nefolosit fără AI în buclă | **nu e necesar** |
| Rețea | conexiunea MT5 existentă; polling la 1 s | neglijabil |
| MT5 | aceeași conexiune / același terminal | ok; o singură instanță de engine (mutex, ca la Daily) |
| Disc | jurnal rotit (5 MB × 3) + trades.jsonl | neglijabil |

## 11. Backtesting

- **M1/M5 OHLC cu spread real orar** (folosit aici): suficient pentru M5, unde ținerea medie e de ~40 de minute.
- **Tick-uri reale:** pentru verificarea pe M5 a ordinii SL/TP în aceeași bară și a spread-ului exact la intrare. Avem tick-uri din 2023 (FX/metale), deci ~3 ani se pot reconstitui.
- [fapt documentat] MT5 Strategy Tester are modurile „Real ticks” (cel mai apropiat de realitate; spread-ul variază în bară), „Every tick” (spread fix pe bara M1), „1 minute OHLC” și „Open prices” ([MetaTrader 5 Help](https://www.metatrader5.com/en/terminal/help/algotrading/tick_generation)). [experiență] Un „99% modelling quality” nu garantează date bune ([MQL5 blog](https://www.mql5.com/en/blogs/post/762517)).
- **Latența și slippage-ul nu se pot simula credibil fără măsurători reale;** de aceea e nevoie de forward test pe DEMO (§12).
- **Disciplina e cea din M0** (`m0/robustness.py`, deja în proiect): split train/test, bootstrap, prag corectat pentru numărul de încercări.

## 12. Demo Testing

1. **Faza 0, înainte de orice cod nou:** confirmă **tipul contului** (Standard vs Raw) și comisionul real. Asta decide dacă FX are vreo șansă.
2. **Faza 1, shadow pe contul real** (ca Daily): semnale și trade-uri virtuale pe prețuri reale, zero ordine, 8–12 săptămâni.
3. **Faza 2, DEMO ICMarkets:** ordine reale pe demo pentru **latență, slippage, respingeri și execuția SL**. Minimum 200 de trade-uri.
4. **Faza 3, live cu buget mic** ($20–40), doar dacă fazele 1–2 trec criteriile din §20.

## 13. Live Safety (obligatorii)

- **Emergency Stop:** buton dedicat, independent de AI. Oprește intrările instant și **închide pozițiile Noisy** (magic propriu), fără să atingă celelalte engine-uri.
  - **Recomandare pentru oprirea normală:** pozițiile se închid. Ținerea medie e de ~40 de minute, iar a le lăsa nesupravegheate contrazice ideea de engine controlat.
  - **Decizia e a ta;** nu se implementează fără confirmare.
- **Fără autostart, pornire cu confirmare** (modalul din brief, risc HIGH). Pornirea programată e opțională: doar în fereastra configurată, cu oprire automată la final.
- **Niciodată overnight sau în weekend:** totul se închide la sfârșitul ferestrei (ca Daily).
- **Magic separat, comment `N-<SIM>`, atribuire în Dashboard, Tranzacții și Rapoarte** (`classify_trade`).
- **Deblocare LIVE separată:** componenta `noisy_engine` în `live_guard`, ca la Daily.
- **Global guard + risk cap** obligatorii; nu se pot ocoli.

## 14. Trading Council

Consultarea a rulat pe consiliul AI al aplicației, cu aceleași fapte pentru toate rolurile (`data/research_noisy/council_gemini.json`). O primă rulare pe modelul local `qwen3:1.7b` a fost **respinsă ca nesigură** din cauza erorilor factuale (`council.json`).

| Întrebare | Analist Tehnic | Analist Macro | Risk Manager (veto) | Head Trader |
|---|---|---|---|---|
| Piața | **USDJPY** (cel mai bun t) | **XAUUSD** (robust la costuri) | XAUUSD, cu rezerve | XAUUSD |
| Timeframe | M5 | M5 | M5 | M5 |
| Strategie | MR; nu MOM/TRD | MR; nu MOM/TRD | MR; nimic pe M1 | MR |
| Risc/trade | 2% | 2% | **1%**, buget izolat $20–40 | 1% |
| AI | nu în execuție | context știri/volatilitate | nu în execuție | context, nu semnale |
| Verdict | GO WITH CONDITIONS | GO WITH CONDITIONS | **NO-GO** până la condiții | **NO-GO WITH CONDITIONS** |

**Dezacordul principal: USDJPY vs XAUUSD.**
- **Opinia A (Tehnic):** USDJPY, pentru că are cel mai bun t-stat.
- **Opinia B (Macro, Risk):** XAUUSD, pentru că USDJPY moare la comision Raw.
- **Recomandarea finală a echipei:**
  - **USDJPY dacă contul rămâne fără comision**, pentru că XAUUSD nu încape fizic în $206.
  - **XAUUSD doar pe un cont/buget ≥ ~$600–800.**

**Erori ale consiliului, corectate de echipă:** consiliul a propus loturi de 0,0075 și 0,0037 pe XAUUSD. Sunt imposibile, lotul minim fiind 0,01. Asta confirmă că sizing-ul se face în cod (`position_sizing`), nu de AI.

**Condiția critică pe care o cer toate rolurile:** pragul de semnificație. Fără el, nu bani reali.

## 15. Architecture (dacă trece de shadow)

Reutilizare, fără logică duplicată:

| Componentă | Reutilizată din |
|---|---|
| Conexiune MT5, bare/tick-uri | `Mt5DataSource` / tiparul din `daily_engine` |
| Global guard, știri, capital, circuit breaker | `live/global_guard.check_open` + `news_window_active` |
| Sizing + risk cap | `position_sizing` (`size_by_risk`, `apply_risk_cap`) |
| Execuție (filling, retry, SL atașat, închidere) | tiparul `daily_engine/executor.py` (singurul fișier cu `order_send`) |
| Mod shadow / execute + deblocare LIVE | identic cu Daily (`MODES`, `live_guard`) |
| Lifecycle (start/stop verificat, fără autostart) | `api/engine_lifecycle.py` (o intrare nouă, fără task de autostart) |
| Telegram, Notificări, jurnale rotite | `api.telegram`, `log_utils` |
| Atribuire tranzacții / rapoarte / Dashboard | `mt5_pool.classify_trade` (magic nou), `engine-performance` |

Specific Noisy: `noisy_engine/strategy.py` (funcție PURĂ, identică cu backtestul, ca la Daily), plus limitele proprii (trade/loss/buget).

**Stări:** Stopped · Starting · Running · Paused · Risk Locked (global) · Budget Locked · Loss Limit · Trade Limit · Scheduled Stop · Error · Stopping. Starea se scrie în `status.json` cu motivul, iar UI-ul afișează de exemplu „Stopped – Budget Limit”.

## 16. UI / UX

- **Tab „Noisy Engine”:** piață (una), fereastră de timp, mod Shadow/Execuție (selectorul explicit, ca la Daily), buget + prag minim, Max Trades/zi (on/off + valoare), Max Losses (on/off + valoare), pornire programată (zi + start/stop).
- **Modal la Start:** risc **HIGH**, cu „Cancel” și „Yes, Start Noisy Engine”. Text propus: *„Noisy Engine analizează piața la fiecare minut și poate deschide până la N trade-uri pe zi. Costurile (spread, slippage) cântăresc mult la această frecvență, iar pierderile pot apărea mai repede decât la celelalte engine-uri. Bugetul lui e separat: se oprește singur la pragul setat.”*
- **Buton roșu Emergency Stop,** vizibil permanent când rulează.
- **Card de stare** cu motivul opririi; contoare azi (trade-uri X/N, pierderi X/N, buget rămas $).

## 17. Monitoring

Pe lângă cele din brief (trades, WR, PF, net P/L, medii, expectancy, max DD, loss streak, frecvență, ținere medie, ordine respinse/eșuate):
- **Cost per trade** (spread + comision + slippage) în $ și în R, plus **edge brut vs cost**.
- **Slippage real** = preț cerut vs preț executat, la intrare și la ieșire.
- **Latența ordinului** (trimitere → confirmare).
- **Expectancy după costuri pe fereastra mobilă de 50 de trade-uri,** cu alertă când devine negativă.
- **Rata de inversare Long/Short pe oră** (flip-flop).
- **Shadow vs backtest:** aceeași comparație ca la Daily.

## 18. Estimated Costs

- **Resurse de calcul:** neglijabile (§10).
- **Complexitate:** **medie**, ~60–70% reutilizare din Daily Engine, cu aceeași structură: strategie pură + executor + lifecycle + UI.
  - Etapa shadow: ~1 sesiune de lucru.
  - Execuția + limitele de buget + Emergency Stop + UI complet: încă 1–2 sesiuni.
- **Costul principal e timpul de validare (8–12 săptămâni de shadow),** nu codul.

## 19. Risks

**De trading:**
- edge-ul nu e semnificativ (t < 2,98);
- dependența totală de comision 0;
- drawdown lung (33–44R în 12 luni) și serii de 9–16 pierderi;
- regim de trend prelungit, care e dăunător mean-reversion;
- spike-uri de spread la rollover și știri.

**De execuție:**
- latența și slippage-ul nemăsurate;
- respingeri la volatilitate;
- un cont mic, care forțează lotul minim și face riscul real mai mare decât ținta.

**Tehnice:**
- încă un proces pe același terminal MT5;
- contenție pe marjă cu celelalte 3 engine-uri;
- riscul de pornire accidentală (de aceea fără autostart și cu confirmare).

[cercetare] Context comportamental:
- Pe piața de futures din Brazilia, **97% dintre cei care au făcut day trading peste 300 de zile au pierdut bani**, fără dovezi de învățare ([Chague, De-Losso, Giovannetti](https://repositorio.fgv.br/items/e87d04fc-4b4c-4a56-ab5a-1c84c1afde1b/full)).
- Pe orizonturi foarte scurte, câștigul se duce la cei mai rapizi; cursa s-a mutat la micro-secunde ([Budish, Cramton, Shim](https://econpapers.repec.org/RePEc:oup:qjecon:v:130:y:2015:i:4:p:1547-1621); [Aquilina, Budish, O'Neill](https://www.nber.org/system/files/working_papers/w29011/w29011.pdf)).
- [fapt documentat] BIS: FX e o piață OTC fragmentată, unde firmele de trading pe cont propriu (PTF) bazate pe viteză au un rol important pe spot ([BIS Quarterly Review, dec. 2022](https://www.bis.org/publ/qtrpdf/r_qt2212z.htm); [BIS 2022](https://bis.org/publ/qtrpdf/r_qt2212f.htm)).
- [fapt documentat] ESMA limitează efectul de levier pentru retail: 30:1 majore, 20:1 aur și indici majori, 2:1 crypto ([Irish Times / ESMA](https://www.irishtimes.com/business/personal-finance/europe-restricts-leverage-on-cfds-to-protect-retail-investors-1.3441764); [ESMA](https://www.esma.europa.eu/node/84933)). De aici marja mare pe aur și indici la un cont mic.

## 20. Final Verdict

### NO-GO pentru Noisy Engine ca engine de frecvență mare (M1/tick) cu bani reali.

Datele arată că pe M1 nu există edge după costuri pe nicio piață disponibilă. Lipsesc datele (DOM, volum real) și viteza necesare pentru edge-uri pe tick.

### GO WITH CONDITIONS doar pentru un experiment „Noisy-lite” în SHADOW

Condiții:
1. **Confirmă tipul contului / comisionul real** (Faza 0). Dacă e Raw ($7/lot), FX iese din discuție, iar varianta se reduce la XAUUSD pe buget mai mare. Dacă e Standard (comision 0, spread-urile măsurate aici), USDJPY rămâne candidatul.
2. **Mod shadow, zero ordine,** 8–12 săptămâni: M5, mean reversion, filtrele obligatorii din §5, anti flip-flop din §6, piața **USDJPY**.
3. **Criterii de trecere fixate ACUM** (ca să nu le mutăm după rezultat):
   - **≥ 250 de trade-uri shadow** cu expectancy după costuri **≥ +0,04R** și 2/3 luni pozitive;
   - rezultatul shadow în **intervalul de încredere 90% al backtestului**;
   - la reunirea backtestului cu forward-ul: **t ≥ 2,0 pe datele noi (out-of-sample)**, plus **t combinat ≥ 2,98**.
4. **Doar după aceea:** DEMO cu ordine reale pentru latență/slippage, apoi live cu buget izolat de **$20–40**, risc 1% din buget, limitele din §8 și Emergency Stop.

Dacă shadow-ul nu trece criteriile, Noisy se oprește acolo, cu cost aproape zero.

**Deciziile necesare de la tine:**
1. **Faza 0:** ce tip de cont ai (Standard / Raw)? Varianta recomandată: verifici în ICMarkets Client Area; costă 2 minute.
2. **Pornim experimentul shadow „Noisy-lite”?** Opțiuni: (a) da, USDJPY M5; (b) nu, închidem subiectul; (c) da, dar pe XAUUSD după o creștere a contului. **Recomandarea echipei: (a)**, dacă Faza 0 confirmă comisionul 0.
3. **La oprire (când trecem la execuție):** închidem pozițiile (recomandat) sau le lăsăm până la SL/TP?
4. **Separat:** verificăm problema adaptorului Gemini, care taie răspunsurile și poate afecta Head Trader-ul din AI Engine?

---

### Anexă — reproducere

```
python scripts/research_noisy/measure_markets.py   # spread / tick-uri / costuri / DOM (read-only)
python scripts/research_noisy/edge_test.py         # COST=A|B, TF=M1|M5
python scripts/research_noisy/candidate_check.py   # t-stat, bootstrap, trimestre, sensibilitate costuri
COUNCIL_ALL_GEMINI=1 python scripts/research_noisy/council_consult.py   # Trading Council (consultativ)
```

## 21. Actualizare 2026-11-02 — spread-ul REAL al contului și ce s-a schimbat în engine

**Spread-ul măsurat pe contul real (Standard, ICMarketsEU):** istoricul MT5 (tick-uri + bare) are spread-ul BRUT,
iar cotația executabilă (`symbol_info_tick`) include markup-ul contului Standard. USDJPY: istoric ~1 point (0,001),
live 8–10 points (0,008–0,010). Indicii și cripto nu au markup. Studiul inițial (spread_floor 0,001) a subestimat deci
costul FX de ~9 ori.

**Backtest 12 luni USDJPY la spread real** (`noisy_backtest.py --spread-points 9`):

| Variantă | Trade-uri / zi | R / trade |
|---|---|---|
| M5, filtrele Noisy (profil M5: cost/ATR 15×) | 0,08 | −0,245 (20 trade-uri) |
| M5, fără filtre | 5,1 | −0,096 |
| M1, filtrele Noisy | 0,6 | +0,086 (151 trade-uri — nesemnificativ) |
| M1, fără filtre | ~25 | −0,44 |
| M5, fără filtre, suprapuneri max 3 / 5 min | 9,9 | −0,092 (DD dublat: −149R → −298R) |

**De ce „nu mai plasa trade-uri” după ridicarea spread-ului:**
- `spread_floor` era în același timp costul presupus, limita de spread și baza filtrului `ATR ≥ N × cost`.
- La 0,01, pe M1 (ATR median ~0,020) n-a trecut nicio bară în ultimele ~2 săptămâni.
- Respingerea era tacită.

**Ce s-a schimbat în engine:**
- secțiunea `spread` separă tipicul (auto din tick-urile live, înghețat pe zi / manual) de maxim, în points;
- fiecare semnal respins e raportat cu motivul și cifrele;
- ferestre orare multiple;
- Edit Market;
- trade-uri suprapuse opționale.

*Corecție (aceeași zi):* o primă variantă raporta „M5 cu filtre: 1,7 / zi, −0,045R”. Valoarea venea dintr-o eroare a
scriptului: `--tf M5` păstra pragurile profilului M1 (5×). Scriptul e reparat (re-derivă profilul timeframe-ului ales).

### Piețe mai ieftine pentru Noisy (screening + backtest 12 luni, spread LIVE, 2026-11-02)

Screening-ul (cost = spread live + 2 × 25% slippage, raportat la ATR-ul M5 din fereastra lichidă):
- indicii sunt de 4–10× mai ieftini decât FX-ul (US30 2%, DE40 3%, USTEC 4%, XAUUSD 4%, US500 7% din ATR);
- FX-ul pe contul Standard ajunge la 26–70% (USDJPY 26%).

Filtru de accesibilitate: marja la lotul minim ≤ ~75$ (contul ~206$ e partajat cu celelalte engine-uri). Asta exclude
US30 (262$), XAUUSD (198$), DE40 / USTEC (~145$).

| Piață (fereastra RO) | Marja lot min | Spread live | M1 cu filtre | M5 cu filtre | M1 fără filtre |
|---|---|---|---|---|---|
| **XAGUSD** (10–20) | 51$ | 22 pts | **1,2 / zi, +0,011R**, DD −29R | 0,23 / zi, +0,196R (60 tr.) | −0,40R |
| **US500** (16:30–22:45) | 38$ | 30 pts | **7,8 / zi, −0,072R** (t −2,6), DD −165R | 0,31 / zi, +0,097R (80 tr.) | −0,16R |
| **UK100** (10–18) | 72$ | 90 pts | 0,8 / zi, −0,082R, DD −32R | 0,02 / zi | −0,40R |
| USDJPY (10–20), referință | 33$ | 9 pts | 0,6 / zi, +0,086R | 0,08 / zi, −0,245R | −0,44R |
| STOXX50 / F40 (10–18) | 35–45$ | 100–120 pts | 0,2–0,26 / zi, −0,09 … −0,14R | ~0 | −0,36 … −0,44R |

Recomandare:
1. **XAGUSD M1** — cel mai bun echilibru: ~1 trade / zi, ~0R, marjă mică.
2. **US500 M1** — frecvență mare (~8 / zi), accesibil, dar negativ semnificativ (−0,07R). Doar pentru test de
   frecvență în shadow.
3. **UK100 M1** — rar, ~0.

Pe M5 (XAGUSD / US500) rezultatele sunt pozitive, dar pe 60–80 de trade-uri, deci nesemnificative. Niciuna nu are un
edge dovedit. Fără filtrul cost/ATR toate sunt puternic negative.

Shadow real (harness izolat, 481 de iterații): config reală → 42 de semnale respinse azi, toate pe cost/ATR. Concluzia
rămâne: **USDJPY M1 nu are edge la costul real al acestui cont**. Decizia (piață mai ieftină / M5 / prag cost/ATR) e a
utilizatorului.
