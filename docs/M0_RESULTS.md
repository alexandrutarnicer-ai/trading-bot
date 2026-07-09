# M0 — Rezultate audit statistic sesiuni

*Generat: 2026-07-08 19:08 · 20 sesiuni · backtest pe toata istoria CSV*

Metoda: vezi [M0_METHOD.md](M0_METHOD.md). Verdictele sunt reguli mecanice pe metricile de mai jos, nu opinii — pragurile sunt in `m0/audit.py::classify`.

**Sumar:** 🟢 5 keep · 🟡 3 observe · 🔴 12 demote · ⚪ 0 insuficient

## Clasament

| Verdict | Sesiune | Piata | Dir | N | Exp (R) | P(edge>0) | Fold+ | N* trials | Train/Test | Note |
|---|---|---|---|---|---|---|---|---|---|---|
| 🟢 KEEP | S17 S17 — AUDCAD H1 LONG+IB | AUDCAD | BOTH | 47 | 0.407 | 99% | 75% | 2 | 0.32/0.59 | Sharpe/trade mic — N*=2 trial-uri il explica (sensibil la cautare) |
| 🟢 KEEP | S11 S11 — USDCAD M15 LONG+IB | USDCAD | LONG | 88 | 0.350 | 100% | 88% | 3 | 0.31/0.42 | Sharpe/trade mic — N*=3 trial-uri il explica (sensibil la cautare) |
| 🟢 KEEP | S14 S14 — CHFJPY H1 LONG all | CHFJPY | BOTH | 276 | 0.153 | 99% | 88% | 2 | 0.16/0.13 | Sharpe/trade mic — N*=2 trial-uri il explica (sensibil la cautare) |
| 🟢 KEEP | S18 S18 — NZDJPY H1 BOTH+IB | NZDJPY | BOTH | 292 | 0.152 | 98% | 62% | 2 | 0.21/0.04 | Sharpe/trade mic — N*=2 trial-uri il explica (sensibil la cautare) |
| 🟢 KEEP | S3 S3 — BTCUSD M15 BOTH+IB | BTCUSD | BOTH | 1176 | 0.110 | 100% | 88% | 4 | 0.06/0.23 | edge in crestere in timp (dependenta de regim); Sharpe/trade mic — N*=4 trial-uri il explica (sensibil la cautare) |
| 🟡 OBSERVE | S16 S16 — GBPAUD H1 BOTH+BE  | GBPAUD | BOTH | 461 | 0.095 | 93% | 75% | 1 | 0.08/0.14 | Sharpe/trade mic — N*=1 trial-uri il explica (sensibil la cautare) |
| 🟡 OBSERVE | S2 S2 — AUDJPY M15 BOTH+BE | AUDJPY | LONG | 148 | 0.090 | 83% | 75% | 1 | 0.01/0.30 | edge in crestere in timp (dependenta de regim); Sharpe/trade mic — N*=1 trial-uri il explica (sensibil la cautare) |
| 🟡 OBSERVE | S15 S15 — GBPUSD M15 LONG | GBPUSD | BOTH | 435 | 0.087 | 87% | 75% | 1 | 0.00/0.28 | Sharpe/trade mic — N*=1 trial-uri il explica (sensibil la cautare) |
| 🔴 DEMOTE | S19 S19 — AUDNZD M15 BOTH | AUDNZD | BOTH | 123 | 0.049 | 59% | 50% | 1 | -0.19/0.61 | train negativ / test pozitiv (posibil regim recent); edge in crestere in timp (dependenta de regim) |
| 🔴 DEMOTE | S20 S20 — XAUUSD Live | XAUUSD | BOTH | 792 | 0.025 | 68% | 62% | 1 | -0.10/0.18 | train negativ / test pozitiv (posibil regim recent) |
| 🔴 DEMOTE | S12 S12 — EURAUD H1 LONG | EURAUD | BOTH | 581 | -0.007 | 46% | 62% | 1 | 0.00/-0.03 |  |
| 🔴 DEMOTE | S5 S5 — USDCHF H1 BOTH | USDCHF | BOTH | 829 | -0.019 | 35% | 38% | 1 | -0.07/0.10 | train negativ / test pozitiv (posibil regim recent); edge in crestere in timp (dependenta de regim) |
| 🔴 DEMOTE | S1 S1 — EURUSD M15 LONG | EURUSD | BOTH | 1498 | -0.028 | 23% | 38% | 1 | -0.06/0.06 | train negativ / test pozitiv (posibil regim recent) |
| 🔴 DEMOTE | S9 S9 — USDJPY M15 LONG | USDJPY | LONG | 1002 | -0.041 | 21% | 25% | 1 | -0.06/0.02 | train negativ / test pozitiv (posibil regim recent) |
| 🔴 DEMOTE | S6 S6 — US30 M15 BOTH | US30 | BOTH | 873 | -0.052 | 17% | 25% | 1 | -0.07/0.00 | train negativ / test pozitiv (posibil regim recent) |
| 🔴 DEMOTE | S10 S10 — GBPCAD H1 LONG+Flag | GBPCAD | BOTH | 390 | -0.066 | 20% | 25% | 1 | -0.21/0.21 | train negativ / test pozitiv (posibil regim recent); edge in crestere in timp (dependenta de regim) |
| 🔴 DEMOTE | S8 S8 — EURCAD H1 LONG+Flag | EURCAD | LONG | 421 | -0.073 | 13% | 25% | 1 | -0.15/0.04 | train negativ / test pozitiv (posibil regim recent) |
| 🔴 DEMOTE | S13 S13 — EURJPY M15 LONG | EURJPY | BOTH | 901 | -0.083 | 6% | 25% | 1 | -0.13/0.03 | train negativ / test pozitiv (posibil regim recent) |
| 🔴 DEMOTE | S4 S4 — GER40 M15 LONG+Flag | GER40 | BOTH | 1466 | -0.163 | 0% | 12% | 1 | -0.22/-0.01 |  |
| 🔴 DEMOTE | S7 S7 — XRPUSD M15 BOTH+Flag+IB | XRPUSD | BOTH | 1062 | -0.529 | 0% | 0% | 1 | -0.40/-0.94 |  |

## Coloane

- **N** — numar de trade-uri in backtest (dimensiunea esantionului).
- **Exp (R)** — expectancy: castig mediu per trade in multipli de risc.
- **P(edge>0)** — increderea (bootstrap) ca expectancy adevarat > 0. ≥95% = edge distinct de zgomot.
- **Fold+** — fractia din cele 8 sub-perioade in care sesiunea a fost pozitiva. Aproape de 100% = stabil in timp.
- **N\* trials** — de cate variante independente ai fi avut nevoie ca edge-ul sa fie explicat prin noroc de cautare. Mic = fragil.
- **Train/Test** — expectancy pe primele 70% / ultimele 30% (split-ul existent).

## Detaliu per sesiune

### 🟢 KEEP — S17 S17 — AUDCAD H1 LONG+IB (AUDCAD, BOTH)

- Trade-uri: **47** · win rate 49% · profit factor 1.73 · perioada 2025-01-02 → 2026-06-11
- Expectancy: **0.407R** (bootstrap 95% CI: 0.070 … 0.727R) · Sharpe/trade 0.25
- P(edge>0) = **99%** · PSR vs 0 = 96% · breakeven trials N* = **2**
- Stabilitate: 75% din fold-uri pozitive · trend 0.33 (p=0.42) · fold exp: `+0.24 -0.60 +1.38 +0.26 +0.46 +1.01 -0.56 +1.20`
- Train/Test: 0.322R (32t) / 0.587R (15t) · max DD -7.6R
- ⚠ Sharpe/trade mic — N*=2 trial-uri il explica (sensibil la cautare)

### 🟢 KEEP — S11 S11 — USDCAD M15 LONG+IB (USDCAD, LONG)

- Trade-uri: **88** · win rate 52% · profit factor 1.68 · perioada 2025-01-02 → 2026-06-11
- Expectancy: **0.350R** (bootstrap 95% CI: 0.112 … 0.583R) · Sharpe/trade 0.24
- P(edge>0) = **100%** · PSR vs 0 = 99% · breakeven trials N* = **3**
- Stabilitate: 88% din fold-uri pozitive · trend 0.19 (p=0.65) · fold exp: `-0.39 +0.43 +0.88 +0.23 +0.17 +0.35 +0.78 +0.34`
- Train/Test: 0.314R (57t) / 0.417R (31t) · max DD -6.0R
- ⚠ Sharpe/trade mic — N*=3 trial-uri il explica (sensibil la cautare)

### 🟢 KEEP — S14 S14 — CHFJPY H1 LONG all (CHFJPY, BOTH)

- Trade-uri: **276** · win rate 42% · profit factor 1.26 · perioada 2021-08-11 → 2026-06-05
- Expectancy: **0.153R** (bootstrap 95% CI: 0.023 … 0.288R) · Sharpe/trade 0.11
- P(edge>0) = **99%** · PSR vs 0 = 97% · breakeven trials N* = **2**
- Stabilitate: 88% din fold-uri pozitive · trend -0.43 (p=0.29) · fold exp: `+0.22 +0.47 +0.04 +0.23 -0.15 +0.18 +0.06 +0.17`
- Train/Test: 0.160R (199t) / 0.133R (77t) · max DD -9.5R
- ⚠ Sharpe/trade mic — N*=2 trial-uri il explica (sensibil la cautare)

### 🟢 KEEP — S18 S18 — NZDJPY H1 BOTH+IB (NZDJPY, BOTH)

- Trade-uri: **292** · win rate 43% · profit factor 1.26 · perioada 2021-08-11 → 2026-06-05
- Expectancy: **0.152R** (bootstrap 95% CI: 0.011 … 0.306R) · Sharpe/trade 0.11
- P(edge>0) = **98%** · PSR vs 0 = 97% · breakeven trials N* = **2**
- Stabilitate: 62% din fold-uri pozitive · trend -0.45 (p=0.26) · fold exp: `+0.22 +0.41 +0.26 -0.11 +0.37 -0.06 -0.04 +0.17`
- Train/Test: 0.209R (195t) / 0.038R (97t) · max DD -12.4R
- ⚠ Sharpe/trade mic — N*=2 trial-uri il explica (sensibil la cautare)

### 🟢 KEEP — S3 S3 — BTCUSD M15 BOTH+IB (BTCUSD, BOTH)

- Trade-uri: **1176** · win rate 37% · profit factor 1.19 · perioada 2020-06-23 → 2026-06-08
- Expectancy: **0.110R** (bootstrap 95% CI: 0.025 … 0.195R) · Sharpe/trade 0.08
- P(edge>0) = **100%** · PSR vs 0 = 100% · breakeven trials N* = **4**
- Stabilitate: 88% din fold-uri pozitive · trend 0.71 (p=0.05) · fold exp: `-0.12 +0.12 +0.02 +0.17 +0.14 +0.05 +0.15 +0.35`
- Train/Test: 0.064R (849t) / 0.231R (327t) · max DD -29.3R
- ⚠ edge in crestere in timp (dependenta de regim); Sharpe/trade mic — N*=4 trial-uri il explica (sensibil la cautare)

### 🟡 OBSERVE — S16 S16 — GBPAUD H1 BOTH+BE  (GBPAUD, BOTH)

- Trade-uri: **461** · win rate 41% · profit factor 1.17 · perioada 2016-10-19 → 2026-06-11
- Expectancy: **0.095R** (bootstrap 95% CI: -0.032 … 0.222R) · Sharpe/trade 0.07
- P(edge>0) = **93%** · PSR vs 0 = 95% · breakeven trials N* = **1**
- Stabilitate: 75% din fold-uri pozitive · trend 0.57 (p=0.14) · fold exp: `-0.07 +0.05 -0.07 +0.05 +0.24 +0.20 +0.32 +0.04`
- Train/Test: 0.076R (316t) / 0.136R (145t) · max DD -16.4R
- ⚠ Sharpe/trade mic — N*=1 trial-uri il explica (sensibil la cautare)

### 🟡 OBSERVE — S2 S2 — AUDJPY M15 BOTH+BE (AUDJPY, LONG)

- Trade-uri: **148** · win rate 43% · profit factor 1.15 · perioada 2025-01-02 → 2026-06-11
- Expectancy: **0.090R** (bootstrap 95% CI: -0.092 … 0.273R) · Sharpe/trade 0.06
- P(edge>0) = **83%** · PSR vs 0 = 79% · breakeven trials N* = **1**
- Stabilitate: 75% din fold-uri pozitive · trend 0.67 (p=0.07) · fold exp: `+0.08 +0.17 -0.29 -0.25 +0.12 +0.29 +0.45 +0.19`
- Train/Test: 0.008R (106t) / 0.296R (42t) · max DD -14.3R
- ⚠ edge in crestere in timp (dependenta de regim); Sharpe/trade mic — N*=1 trial-uri il explica (sensibil la cautare)

### 🟡 OBSERVE — S15 S15 — GBPUSD M15 LONG (GBPUSD, BOTH)

- Trade-uri: **435** · win rate 39% · profit factor 1.14 · perioada 2018-05-22 → 2026-06-05
- Expectancy: **0.087R** (bootstrap 95% CI: -0.063 … 0.227R) · Sharpe/trade 0.06
- P(edge>0) = **87%** · PSR vs 0 = 91% · breakeven trials N* = **1**
- Stabilitate: 75% din fold-uri pozitive · trend 0.55 (p=0.16) · fold exp: `-0.24 +0.23 -0.28 +0.09 +0.07 +0.35 +0.31 +0.17`
- Train/Test: 0.002R (303t) / 0.282R (132t) · max DD -25.6R
- ⚠ Sharpe/trade mic — N*=1 trial-uri il explica (sensibil la cautare)

### 🔴 DEMOTE — S19 S19 — AUDNZD M15 BOTH (AUDNZD, BOTH)

- Trade-uri: **123** · win rate 42% · profit factor 1.07 · perioada 2025-01-02 → 2026-06-12
- Expectancy: **0.049R** (bootstrap 95% CI: -0.347 … 0.435R) · Sharpe/trade 0.03
- P(edge>0) = **59%** · PSR vs 0 = 64% · breakeven trials N* = **1**
- Stabilitate: 50% din fold-uri pozitive · trend 0.67 (p=0.07) · fold exp: `+0.23 -1.19 -0.43 -0.01 +0.38 -0.24 +0.39 +1.38`
- Train/Test: -0.192R (86t) / 0.609R (37t) · max DD -31.2R
- ⚠ train negativ / test pozitiv (posibil regim recent); edge in crestere in timp (dependenta de regim)

### 🔴 DEMOTE — S20 S20 — XAUUSD Live (XAUUSD, BOTH)

- Trade-uri: **792** · win rate 37% · profit factor 1.05 · perioada 2017-12-18 → 2026-06-05
- Expectancy: **0.025R** (bootstrap 95% CI: -0.074 … 0.127R) · Sharpe/trade 0.02
- P(edge>0) = **68%** · PSR vs 0 = 71% · breakeven trials N* = **1**
- Stabilitate: 62% din fold-uri pozitive · trend 0.60 (p=0.12) · fold exp: `-0.15 +0.11 -0.17 -0.20 +0.05 +0.01 +0.21 +0.34`
- Train/Test: -0.095R (449t) / 0.183R (343t) · max DD -57.7R
- ⚠ train negativ / test pozitiv (posibil regim recent)

### 🔴 DEMOTE — S12 S12 — EURAUD H1 LONG (EURAUD, BOTH)

- Trade-uri: **581** · win rate 36% · profit factor 0.99 · perioada 2016-10-19 → 2026-06-11
- Expectancy: **-0.007R** (bootstrap 95% CI: -0.140 … 0.129R) · Sharpe/trade -0.00
- P(edge>0) = **46%** · PSR vs 0 = 45% · breakeven trials N* = **1**
- Stabilitate: 62% din fold-uri pozitive · trend -0.02 (p=0.96) · fold exp: `+0.18 -0.23 -0.15 +0.03 +0.12 +0.12 -0.22 +0.10`
- Train/Test: 0.004R (403t) / -0.031R (178t) · max DD -45.6R

### 🔴 DEMOTE — S5 S5 — USDCHF H1 BOTH (USDCHF, BOTH)

- Trade-uri: **829** · win rate 35% · profit factor 0.97 · perioada 2018-05-29 → 2026-06-11
- Expectancy: **-0.019R** (bootstrap 95% CI: -0.121 … 0.083R) · Sharpe/trade -0.02
- P(edge>0) = **35%** · PSR vs 0 = 33% · breakeven trials N* = **1**
- Stabilitate: 38% din fold-uri pozitive · trend 0.81 (p=0.01) · fold exp: `-0.30 -0.05 -0.10 -0.24 +0.19 +0.04 -0.04 +0.34`
- Train/Test: -0.067R (599t) / 0.105R (230t) · max DD -75.6R
- ⚠ train negativ / test pozitiv (posibil regim recent); edge in crestere in timp (dependenta de regim)

### 🔴 DEMOTE — S1 S1 — EURUSD M15 LONG (EURUSD, BOTH)

- Trade-uri: **1498** · win rate 35% · profit factor 0.95 · perioada 2018-05-22 → 2026-06-05
- Expectancy: **-0.028R** (bootstrap 95% CI: -0.102 … 0.045R) · Sharpe/trade -0.02
- P(edge>0) = **23%** · PSR vs 0 = 19% · breakeven trials N* = **1**
- Stabilitate: 38% din fold-uri pozitive · trend 0.40 (p=0.32) · fold exp: `-0.24 +0.06 -0.04 -0.17 +0.12 -0.17 -0.05 +0.28`
- Train/Test: -0.064R (1069t) / 0.062R (429t) · max DD -105.1R
- ⚠ train negativ / test pozitiv (posibil regim recent)

### 🔴 DEMOTE — S9 S9 — USDJPY M15 LONG (USDJPY, LONG)

- Trade-uri: **1002** · win rate 35% · profit factor 0.94 · perioada 2018-05-22 → 2026-06-05
- Expectancy: **-0.041R** (bootstrap 95% CI: -0.132 … 0.054R) · Sharpe/trade -0.03
- P(edge>0) = **21%** · PSR vs 0 = 18% · breakeven trials N* = **1**
- Stabilitate: 25% din fold-uri pozitive · trend -0.12 (p=0.78) · fold exp: `-0.14 -0.04 -0.13 +0.26 -0.16 -0.21 -0.25 +0.35`
- Train/Test: -0.065R (710t) / 0.016R (292t) · max DD -91.3R
- ⚠ train negativ / test pozitiv (posibil regim recent)

### 🔴 DEMOTE — S6 S6 — US30 M15 BOTH (US30, BOTH)

- Trade-uri: **873** · win rate 37% · profit factor 0.93 · perioada 2017-11-24 → 2026-06-05
- Expectancy: **-0.052R** (bootstrap 95% CI: -0.158 … 0.057R) · Sharpe/trade -0.03
- P(edge>0) = **17%** · PSR vs 0 = 15% · breakeven trials N* = **1**
- Stabilitate: 25% din fold-uri pozitive · trend 0.19 (p=0.65) · fold exp: `-0.01 -0.12 -0.07 -0.11 +0.09 -0.26 -0.08 +0.15`
- Train/Test: -0.073R (627t) / 0.002R (246t) · max DD -78.3R
- ⚠ train negativ / test pozitiv (posibil regim recent)

### 🔴 DEMOTE — S10 S10 — GBPCAD H1 LONG+Flag (GBPCAD, BOTH)

- Trade-uri: **390** · win rate 33% · profit factor 0.89 · perioada 2016-10-19 → 2026-06-11
- Expectancy: **-0.066R** (bootstrap 95% CI: -0.210 … 0.091R) · Sharpe/trade -0.05
- P(edge>0) = **20%** · PSR vs 0 = 15% · breakeven trials N* = **1**
- Stabilitate: 25% din fold-uri pozitive · trend 0.71 (p=0.05) · fold exp: `-0.52 -0.30 +0.02 -0.13 -0.13 -0.01 -0.02 +0.58`
- Train/Test: -0.212R (254t) / 0.207R (136t) · max DD -58.1R
- ⚠ train negativ / test pozitiv (posibil regim recent); edge in crestere in timp (dependenta de regim)

### 🔴 DEMOTE — S8 S8 — EURCAD H1 LONG+Flag (EURCAD, LONG)

- Trade-uri: **421** · win rate 35% · profit factor 0.88 · perioada 2016-10-19 → 2026-06-11
- Expectancy: **-0.073R** (bootstrap 95% CI: -0.194 … 0.058R) · Sharpe/trade -0.06
- P(edge>0) = **13%** · PSR vs 0 = 12% · breakeven trials N* = **1**
- Stabilitate: 25% din fold-uri pozitive · trend 0.55 (p=0.16) · fold exp: `-0.14 -0.24 -0.10 -0.06 -0.43 +0.03 -0.11 +0.49`
- Train/Test: -0.152R (250t) / 0.042R (171t) · max DD -55.2R
- ⚠ train negativ / test pozitiv (posibil regim recent)

### 🔴 DEMOTE — S13 S13 — EURJPY M15 LONG (EURJPY, BOTH)

- Trade-uri: **901** · win rate 34% · profit factor 0.88 · perioada 2018-05-22 → 2026-06-05
- Expectancy: **-0.083R** (bootstrap 95% CI: -0.184 … 0.018R) · Sharpe/trade -0.06
- P(edge>0) = **6%** · PSR vs 0 = 4% · breakeven trials N* = **1**
- Stabilitate: 25% din fold-uri pozitive · trend -0.07 (p=0.87) · fold exp: `+0.17 -0.09 -0.30 -0.16 -0.07 -0.28 -0.10 +0.15`
- Train/Test: -0.126R (658t) / 0.033R (243t) · max DD -120.8R
- ⚠ train negativ / test pozitiv (posibil regim recent)

### 🔴 DEMOTE — S4 S4 — GER40 M15 LONG+Flag (GER40, BOTH)

- Trade-uri: **1466** · win rate 34% · profit factor 0.77 · perioada 2017-09-21 → 2026-06-05
- Expectancy: **-0.163R** (bootstrap 95% CI: -0.239 … -0.083R) · Sharpe/trade -0.12
- P(edge>0) = **0%** · PSR vs 0 = 0% · breakeven trials N* = **1**
- Stabilitate: 12% din fold-uri pozitive · trend 0.62 (p=0.10) · fold exp: `-0.17 -0.40 -0.08 -0.12 -0.17 -0.37 -0.07 +0.07`
- Train/Test: -0.218R (1082t) / -0.007R (384t) · max DD -278.5R

### 🔴 DEMOTE — S7 S7 — XRPUSD M15 BOTH+Flag+IB (XRPUSD, BOTH)

- Trade-uri: **1062** · win rate 38% · profit factor 0.45 · perioada 2025-01-01 → 2026-06-08
- Expectancy: **-0.529R** (bootstrap 95% CI: -0.658 … -0.412R) · Sharpe/trade -0.36
- P(edge>0) = **0%** · PSR vs 0 = 0% · breakeven trials N* = **1**
- Stabilitate: 0% din fold-uri pozitive · trend -0.33 (p=0.42) · fold exp: `-0.45 -0.49 -0.55 -0.23 -0.22 -0.39 -0.57 -1.34`
- Train/Test: -0.404R (816t) / -0.945R (246t) · max DD -565.7R
