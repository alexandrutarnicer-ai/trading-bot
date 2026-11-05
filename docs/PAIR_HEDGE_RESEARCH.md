# Perechea GBPUSD / EURUSD „opusă” — rezultat backtest (2026-11-04)

Ideea testată: semnal Custom Engine (Pullback + Inside Bar + Flag, fără filtru AI și fără break-even) pe piața de semnal
→ în minutul în care ordinul se activează, ordin OPUS la piață pe cealaltă piață. Fiecare picior are SL −1R și TP +2R.
1R pe hedge = riscul semnalului × ATR(hedge) / ATR(semnal), deci același risc în $. Regulile de management:

| Eveniment | Ce se întâmplă cu celălalt picior |
|---|---|
| un picior la SL, celălalt pe minus | se închide |
| un picior la SL, celălalt la 0…1R | SL → 0 |
| un picior la SL, celălalt ≥ 1R | SL = treapta atinsă, TP = treapta + 2R, mutat continuu, plafon 10R |
| un picior la TP 2R, celălalt între −1R și −0,5R | se închide |
| un picior la TP 2R, celălalt peste −0,5R | SL → −0,5R, continuă normal |

În plus: o singură pereche deschisă odată; totul se închide vineri la 20:00.

**Date și execuție:**
- M1 GBPUSD + EURUSD, 2021-01 → 2026-11, completat din MT5. Toate timeframe-urile sunt derivate din același M1.
- Simulare minut cu minut. Dacă SL și TP cad în același minut, contează SL (pesimist).
- Spread-ul live al contului Standard (0,9 / 0,8 pip) pe fiecare picior.
- Parametrii sesiunii: S15 (GBPUSD) / S1 (EURUSD) din profil, direcție BOTH.

## Rezultate (R pe pereche, după costuri)

| Semnal | TF | Perechi/săpt | Pereche (reguli) | Pereche fără reguli | Doar piața de semnal | Verdict M0 pereche |
|---|---|---|---|---|---|---|
| GBPUSD | M1+M5 | 13,7 | **−0,197** (DD −810R) | −0,243 | −0,131 | DEMOTE |
| GBPUSD | M15+M30 | 2,3 | **−0,001** (DD −18R) | −0,006 | −0,003 | DEMOTE |
| GBPUSD | M30+H1 | 1,2 | **−0,019** (DD −20R) | −0,012 | −0,046 | DEMOTE |
| EURUSD | M1+M5 | 15,5 | **−0,188** (DD −875R) | −0,211 | −0,105 | DEMOTE |
| EURUSD | M15+M30 | 3,3 | **−0,074** (DD −84R) | −0,072 | −0,001 | DEMOTE |
| EURUSD | M30+H1 | 1,7 | **−0,065** (DD −39R) | −0,087 | −0,037 | DEMOTE |

Cea mai bună variantă (GBPUSD M15+M30): train +0,013, test −0,034. Drawdown-ul e la jumătate față de semnalul singur
(−18R față de −35R), dar fără câștig. Pe M1+M5, fiecare an 2021–2026 e negativ.

Notă metodă: motorul de semnale rulează cu o balanță foarte mare. Altfel, pierderile simulate pe M1 duceau lotul sub
minim și semnalele dispăreau după 2022. Așa a arătat prima rulare, corectată.

## De ce nu funcționează

1. **Cele două piețe se mișcă împreună.** Când un picior pierde 1R, celălalt câștigă în medie aproape tot atât. Perechea
   e practic un short / long pe EURGBP, care se mișcă puțin.
2. **Trailing-ul aproape niciodată nu prinde trenduri lungi.** Cel mai bun picior trece de 3R în doar 0–12 perechi din
   359–4657. Nicio pereche n-a ajuns la 6R sau la 10R.
3. **Se plătesc două spread-uri.** Pe M1, riscul e de câțiva pips, iar spread-ul dublu mănâncă ~0,2R pe pereche.
4. **Regulile de management schimbă doar forma rezultatului, nu și semnul.** Câștig ≈ fără reguli.

Concluzie: nu există un avantaj de exploatat; nu se implementează în live.

Scripturi: `scripts/research_pair/build_data.py` (date) + `scripts/research_pair/pair_hedge.py` (test).
Rezultate brute: `data/research_pair/results.json` + `pairs_*.csv` (local, gitignored).
