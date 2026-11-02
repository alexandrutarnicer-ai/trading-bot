# Backtest vs Live — Custom Engine (analiză 2026-11-02)

Întrebarea: rezultatele reale coincid cât de cât cu ce au prezis testele? Analiza e reproductibilă (doar citire,
date proaspete MT5): perioada live **27.07 – 01.11.2026 (13,9 săptămâni)**, contul real ICMarketsEU (Standard).

**Concluzia pe scurt:** backtestul **reproduce bine semnalele** (91% din trade-urile comune au același rezultat, la
același preț de intrare). Totalurile diferă mult, iar diferența vine din ce backtestul **nu simulează** (Filtrul AI
pre-trade, pauze / perioade fără engine), nu dintr-o logică diferită. Cu **55 de trade-uri reale**, nicio diferență de
expectancy nu e semnificativă statistic. Pe sesiune, datele sunt insuficiente pentru orice concluzie.

## Metodă

- **Live = Actual:** tranzacțiile închise din MT5 (sursa unică), atribuite pe sesiune după comment
  (`mt5_pool.classify_trade`). R-ul live = pe preț, din SL-ul original.
- **Backtest = Expected:** `m0.session_runner` (= backtestul din UI, aceleași costuri / filtre), cu profilul **actual**,
  rulat pe date MT5 descărcate azi (2022 → 02.11.2026). Două repere:
  - *aceeași perioadă* — trade-urile backtestului din 27.07 – 01.11;
  - *termen lung* — tot istoricul.
- **Potrivire trade cu trade:** același simbol și aceeași direcție, intrare la ≤ 2h (H1: ≤ 5h). Motivul trade-urilor
  „ratate” vine din jurnalul live al laptopului (`signals.csv` + `outcomes.csv`, `origin/alex-live`).
- Scripturile se află în scratchpad-ul sesiunii (`bt_vs_live.py`); cifrele de mai jos sunt rezultatul lor.

## Portofoliu (13 sesiuni live; S7 XRPUSD exclus — backtest invalid, vezi mai jos)

| Metrică | Backtest, termen lung | Backtest, aceeași perioadă | **Live (MT5)** |
|---|---|---|---|
| Trade-uri / săptămână | 16,0 | 15,3 | **4,0** |
| Win rate | 34,9% | 28,3% | **43,6%** |
| Expectancy | +0,002R | −0,23R | **+0,13R** |
| Profit factor | ~1,0 | <1 | **1,24** |
| Total | — | −48,8R (212 trade-uri) | **+7,1R (55 trade-uri)**, DD −8,6R |
| Durata mediană | 4–20h (după TF) | idem | 3,2h (comparabilă pe sesiune: S15 4,6h vs 3,8h, S11 4,5h vs 5,0h) |

## De unde vine diferența

**1. Semnalele sunt aceleași.** 34 din cele 55 de trade-uri live au pereche în backtest, la același preț de intrare.
**91%** au același rezultat (câștig / pierdere). Logica de detecție backtest = live.

**2. Costurile: backtestul e ușor mai pesimist** decât realitatea pe aceste perechi FX. Pe perechile cu aceeași țintă
(2R): TP live +1,975R vs backtest +1,696R; SL live −1,011R vs backtest −1,092R. Cauzele:
- R-ul din backtest = $ / riscul țintă, cu lotul rotunjit în jos (capital de test 1000$, loturi 0,03–0,07) și cu costul
  spread-ului scăzut;
- R-ul live e pe preț.

Pe un cont de ~200$ lotul minim domină oricum în $, dar în R backtestul subestimează câștigurile cu ~0,25R. Slippage-ul
la intrările stop a fost neglijabil: prețurile de intrare sunt identice la 1–2 puncte.

**3. Ce NU simulează backtestul — aici e aproape toată diferența de volum și de rezultat.** Din cele 179 de trade-uri pe
care backtestul le-ar fi luat și live-ul nu:

| Motiv (jurnalul live) | Trade-uri | R în backtest |
|---|---|---|
| **respinse de Filtrul AI pre-trade** | **117** | **−25,7R** (−0,21R / trade) |
| fără semnal în jurnalul live (engine oprit / laptop închis / sesiune neactivă atunci) | 53 | −25,0R |
| alte statusuri (SL / expirat / închidere la știri / vineri, fără pereche MT5) | 9 | −4,3R |

Filtrul AI a evitat pierderi pe ansamblu, dar efectul e **amestecat** pe sesiuni:
- a ajutat: S9 USDJPY −17,9R evitate (27 trade-uri), S5 USDCHF −12,4R (17);
- a tăiat câștiguri: S1 EURUSD +3,5R (42 respinse), S12 +4,7R, S22 +7,0R.

Diferența de medie (−0,21R respinse vs +0,13R luate) dă t ≈ 1,7: **sugestiv, nu dovedit**.

**4. Regim de piață.** În aceeași perioadă backtestul face −0,23R / trade, față de ~0 pe termen lung. Raportul lunar pe
octombrie arată piața predominant în *range* (efficiency ratio 0,02–0,13 pe JPY / CHF / EUR) — nefavorabil strategiilor
de trend. Live-ul a avut același regim, dar a luat doar o parte din trade-uri.

## Pe sesiune (insuficient statistic — sub 30 de trade-uri live peste tot)

| Sesiune | Backtest termen lung (exp / săpt) | Backtest perioada (n / exp) | Live (n / WR / exp) |
|---|---|---|---|
| S15 GBPUSD | −0,073 / 1,33 | 24 / −0,28 | 22 / 45% / +0,16 |
| S7 XRPUSD | **invalid** | invalid | 13 / 31% / −0,17 |
| S11 USDCAD | +0,041 / 1,28 | 17 / −0,29 | 10 / 40% / +0,05 |
| S5 USDCHF | +0,053 / 1,88 | 26 / −0,52 | 4 / 50% / +0,06 |
| S1 EURUSD | +0,007 / 3,81 | 53 / −0,05 | 3 / 67% / +1,00 |
| S9 USDJPY | −0,006 / 2,37 | 35 / −0,63 | 0 (27 respinse de AI) |
| S12, S14, S16, S17, S18, S19, S22, S8 | | 4–13 fiecare | 0–1 fiecare |

## Probleme ale backtestului găsite (și ce s-a făcut)

| Problemă | Impact | Stare |
|---|---|---|
| **XRPUSD (S7): contractul s-a schimbat la broker** (1 lot = 1 XRP, lot min 100, pas 1, tick 0,0001). R-uri de −26R … −7445R: swap-ul implicit de 8 $ / lot / noapte și comisionul forex pe lot se aplicau pe mii de „loturi” de 1 XRP. | Backtestul S7 era **invalid**. Live-ul S7 citește MT5 direct, deci e corect. | **REPARAT (2026-11-02, aprobat):** modelul de lot / comision / swap / levier per simbol în `strategy/costs.py` (lot min 100, pas 1, comision 0, swap ~20% / an, levier 1:2, spread real 0,0025). Forex / indici / BTC sunt neschimbați bit cu bit (baseline-urile S1 / S2 / S3 identice). `pip_size` (live) e neatins. **Rezultat nou S7: −0,60R / trade (592 de trade-uri, DEMOTE)**: fără spread ~0R (+0,013R); spread-ul real = ~0,6R pe trade la SL-ul median 0,0041. Live S7: −0,17R / 13 trade-uri. |
| CSV-urile de backtest erau din iunie – august | Perioada comparată cu live-ul lipsea | Avertisment automat în Audit când datele sunt mai vechi de 14 zile; descărcarea din UI le reîmprospătează. |
| Spread-ul presupus pe FX = cel brut | Contul Standard are markup ~0,8 pip | Notă în Audit. Analiza arată că, pe SL-urile M15 / H1 actuale, costurile backtestului sunt deja ușor pesimiste, deci impactul e mic. |
| Timpul din CSV = ora serverului (NY + 7), live = ora RO | Identice ~48 de săptămâni / an; decalaj de 1h în ~3–4 săptămâni (martie, sfârșit oct. – început nov.), când DST-ul SUA ≠ UE | Documentat, neschimbat (ar muta baseline-urile aprobate). |
| Nu se simulează Filtrul AI, Setările Globale, știrile, pauzele | Volumul live ≈ 26% din backtest | Listă afișată în Audit („Nu se simulează”). |

## Celelalte engine-uri

- **AI Engine:** nu există backtest (deciziile sunt ale LLM-ului). Live: 94 de trade-uri, −0,23R / trade (vezi analiza
  pe trigger-e, 2026-11-02).
- **Daily Engine:** shadow abia a început (niciun trade virtual sincronizat încă) → comparația din tab-ul Daily
  (shadow vs backtest) devine utilă după câteva săptămâni.
- **Noisy Engine:** shadow; backtestul cu spread-ul real (9 points USDJPY) e negativ pe M5 (−0,045R) și rar pe M1 (0,6 /
  zi). Vezi `docs/NOISY_ENGINE_RESEARCH.md`.

## Ce ar da o concluzie solidă

≥ 30 de trade-uri live pe sesiune, sau ≥ 200 pe portofoliu, cu aceeași configurație (profilul s-a schimbat pe 31.10:
R:R fix 2 / 3 / 4R; trade-urile vechi aveau ținte de 3,5 – 4,5R). La ritmul actual (4 / săptămână) asta înseamnă încă
**~9–10 luni**. Până atunci, măsura cea mai informativă e **potrivirea trade cu trade** (fidelitatea semnalelor), nu
expectancy-ul.
