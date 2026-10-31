# M0 — Rezultate audit statistic sesiuni

*Generat: 2026-10-31 00:51 · 22 sesiuni · backtest pe toata istoria CSV*

Metoda: vezi [M0_METHOD.md](M0_METHOD.md). Verdictele sunt reguli mecanice pe metricile de mai jos, nu opinii — pragurile sunt in `m0/audit.py::classify`.

**Sumar:** 🟢 3 keep · 🟡 1 observe · 🔴 18 demote · ⚪ 0 insuficient

## Clasament

| Verdict | Sesiune | Piata | Dir | N | Exp (R) | P(edge>0) | Fold+ | N* trials | Train/Test | Note |
|---|---|---|---|---|---|---|---|---|---|---|
| 🟢 KEEP | S11 S11 — USDCAD M15 LONG+IB | USDCAD | LONG | 88 | 0.297 | 99% | 88% | 2 | 0.23/0.43 | edge in crestere in timp (dependenta de regim); Sharpe/trade mic — N*=2 trial-uri il explica (sensibil la cautare) |
| 🟢 KEEP | S22 S22 - SOFI.NAS M15 LONG obs | SOFI.NAS | LONG | 241 | 0.277 | 97% | 62% | 3 | 0.08/0.60 | Sharpe/trade mic — N*=3 trial-uri il explica (sensibil la cautare) |
| 🟢 KEEP | S3 S3 — BTCUSD M15 BOTH+IB | BTCUSD | BOTH | 1182 | 0.083 | 97% | 75% | 2 | 0.04/0.21 | edge in crestere in timp (dependenta de regim); Sharpe/trade mic — N*=2 trial-uri il explica (sensibil la cautare) |
| 🟡 OBSERVE | S2 S2 — AUDJPY M15 BOTH+BE | AUDJPY | LONG | 143 | 0.084 | 83% | 50% | 1 | 0.02/0.26 | Sharpe/trade mic — N*=1 trial-uri il explica (sensibil la cautare) |
| 🔴 DEMOTE | S17 S17 — AUDCAD H1 LONG+IB | AUDCAD | BOTH | 37 | 0.123 | 69% | 38% | 1 | 0.11/0.14 |  |
| 🔴 DEMOTE | S16 S16 — GBPAUD H1 BOTH+BE  | GBPAUD | BOTH | 153 | 0.088 | 73% | 50% | 1 | 0.07/0.14 |  |
| 🔴 DEMOTE | S20 S20 — XAUUSD Live | XAUUSD | BOTH | 782 | 0.025 | 68% | 62% | 1 | -0.10/0.19 | train negativ / test pozitiv (posibil regim recent); edge in crestere in timp (dependenta de regim) |
| 🔴 DEMOTE | S14 S14 — CHFJPY H1 LONG all | CHFJPY | BOTH | 180 | 0.013 | 54% | 50% | 1 | -0.07/0.20 | train negativ / test pozitiv (posibil regim recent) |
| 🔴 DEMOTE | S10 S10 — GBPCAD H1 LONG+Flag | GBPCAD | BOTH | 402 | -0.040 | 29% | 38% | 1 | -0.14/0.15 | train negativ / test pozitiv (posibil regim recent) |
| 🔴 DEMOTE | S9 S9 — USDJPY M15 LONG | USDJPY | LONG | 895 | -0.049 | 24% | 25% | 1 | -0.09/0.04 | train negativ / test pozitiv (posibil regim recent) |
| 🔴 DEMOTE | S1 S1 — EURUSD M15 LONG | EURUSD | BOTH | 1516 | -0.056 | 4% | 38% | 1 | -0.08/0.01 | train negativ / test pozitiv (posibil regim recent) |
| 🔴 DEMOTE | S18 S18 — NZDJPY H1 BOTH+IB | NZDJPY | BOTH | 190 | -0.060 | 23% | 38% | 1 | -0.12/0.09 | train negativ / test pozitiv (posibil regim recent) |
| 🔴 DEMOTE | S15 S15 — GBPUSD M15 LONG | GBPUSD | LONG | 559 | -0.060 | 12% | 25% | 1 | -0.07/-0.03 |  |
| 🔴 DEMOTE | S5 S5 — USDCHF H1 BOTH | USDCHF | BOTH | 832 | -0.064 | 6% | 38% | 1 | -0.11/0.05 | train negativ / test pozitiv (posibil regim recent); edge in crestere in timp (dependenta de regim) |
| 🔴 DEMOTE | S6 S6 — US30 M15 BOTH | US30 | BOTH | 844 | -0.067 | 13% | 38% | 1 | -0.08/-0.03 |  |
| 🔴 DEMOTE | S13 S13 — EURJPY M15 LONG | EURJPY | LONG | 357 | -0.068 | 21% | 50% | 1 | -0.12/0.04 | train negativ / test pozitiv (posibil regim recent) |
| 🔴 DEMOTE | S8 S8 — EURCAD H1 LONG+Flag | EURCAD | LONG | 408 | -0.083 | 12% | 25% | 1 | -0.10/-0.06 |  |
| 🔴 DEMOTE | S19 S19 — AUDNZD M15 BOTH | AUDNZD | BOTH | 40 | -0.132 | 28% | 38% | 1 | -0.45/0.46 | train negativ / test pozitiv (posibil regim recent); edge in crestere in timp (dependenta de regim) |
| 🔴 DEMOTE | S12 S12 — EURAUD H1 LONG | EURAUD | BOTH | 195 | -0.136 | 3% | 25% | 1 | -0.13/-0.14 |  |
| 🔴 DEMOTE | S4 S4 — GER40 M15 LONG+Flag | GER40 | BOTH | 1452 | -0.164 | 0% | 12% | 1 | -0.22/-0.01 |  |
| 🔴 DEMOTE | S7 S7 — XRPUSD M15 BOTH+Flag+IB | XRPUSD | BOTH | 1063 | -0.540 | 0% | 0% | 1 | -0.43/-0.92 |  |
| 🔴 DEMOTE | S21 S21 - CSCO.NAS M15 LONG obs | CSCO.NAS | LONG | 528 | -0.744 | 0% | 0% | 1 | -0.72/-0.95 |  |

## Coloane

- **N** — numar de trade-uri in backtest (dimensiunea esantionului).
- **Exp (R)** — expectancy: castig mediu per trade in multipli de risc.
- **P(edge>0)** — increderea (bootstrap) ca expectancy adevarat > 0. ≥95% = edge distinct de zgomot.
- **Fold+** — fractia din cele 8 sub-perioade in care sesiunea a fost pozitiva. Aproape de 100% = stabil in timp.
- **N\* trials** — de cate variante independente ai fi avut nevoie ca edge-ul sa fie explicat prin noroc de cautare. Mic = fragil.
- **Train/Test** — expectancy pe primele 70% / ultimele 30% (split-ul existent).

## Detaliu per sesiune

### 🟢 KEEP — S11 S11 — USDCAD M15 LONG+IB (USDCAD, LONG)

- Trade-uri: **88** · win rate 53% · profit factor 1.59 · perioada 2025-01-02 → 2026-06-11
- Expectancy: **0.297R** (bootstrap 95% CI: 0.043 … 0.540R) · Sharpe/trade 0.22
- P(edge>0) = **99%** · PSR vs 0 = 98% · breakeven trials N* = **2**
- Stabilitate: 88% din fold-uri pozitive · trend 0.64 (p=0.09) · fold exp: `-0.36 +0.07 +0.29 +0.69 +0.17 +0.47 +0.68 +0.37`
- Train/Test: 0.226R (57t) / 0.427R (31t) · max DD -6.7R
- ⚠ edge in crestere in timp (dependenta de regim); Sharpe/trade mic — N*=2 trial-uri il explica (sensibil la cautare)

### 🟢 KEEP — S22 S22 - SOFI.NAS M15 LONG obs (SOFI.NAS, LONG)

- Trade-uri: **241** · win rate 31% · profit factor 1.38 · perioada 2022-03-07 → 2026-08-07
- Expectancy: **0.277R** (bootstrap 95% CI: -0.014 … 0.589R) · Sharpe/trade 0.14
- P(edge>0) = **97%** · PSR vs 0 = 99% · breakeven trials N* = **3**
- Stabilitate: 62% din fold-uri pozitive · trend 0.40 (p=0.32) · fold exp: `-0.35 +0.39 -0.21 +0.18 +0.65 +1.27 -0.06 +0.37`
- Train/Test: 0.080R (149t) / 0.597R (92t) · max DD -21.8R
- ⚠ Sharpe/trade mic — N*=3 trial-uri il explica (sensibil la cautare)

### 🟢 KEEP — S3 S3 — BTCUSD M15 BOTH+IB (BTCUSD, BOTH)

- Trade-uri: **1182** · win rate 37% · profit factor 1.14 · perioada 2020-06-23 → 2026-06-08
- Expectancy: **0.083R** (bootstrap 95% CI: -0.000 … 0.168R) · Sharpe/trade 0.06
- P(edge>0) = **97%** · PSR vs 0 = 98% · breakeven trials N* = **2**
- Stabilitate: 75% din fold-uri pozitive · trend 0.76 (p=0.03) · fold exp: `-0.15 +0.09 -0.03 +0.15 +0.15 +0.03 +0.15 +0.28`
- Train/Test: 0.036R (849t) / 0.206R (333t) · max DD -35.7R
- ⚠ edge in crestere in timp (dependenta de regim); Sharpe/trade mic — N*=2 trial-uri il explica (sensibil la cautare)

### 🟡 OBSERVE — S2 S2 — AUDJPY M15 BOTH+BE (AUDJPY, LONG)

- Trade-uri: **143** · win rate 42% · profit factor 1.13 · perioada 2025-01-02 → 2026-06-11
- Expectancy: **0.084R** (bootstrap 95% CI: -0.092 … 0.262R) · Sharpe/trade 0.06
- P(edge>0) = **83%** · PSR vs 0 = 76% · breakeven trials N* = **1**
- Stabilitate: 50% din fold-uri pozitive · trend 0.36 (p=0.39) · fold exp: `-0.02 +0.28 -0.03 -0.19 -0.04 +0.14 +0.22 +0.34`
- Train/Test: 0.020R (104t) / 0.256R (39t) · max DD -12.2R
- ⚠ Sharpe/trade mic — N*=1 trial-uri il explica (sensibil la cautare)

### 🔴 DEMOTE — S17 S17 — AUDCAD H1 LONG+IB (AUDCAD, BOTH)

- Trade-uri: **37** · win rate 35% · profit factor 1.18 · perioada 2025-01-02 → 2026-06-11
- Expectancy: **0.123R** (bootstrap 95% CI: -0.364 … 0.633R) · Sharpe/trade 0.07
- P(edge>0) = **69%** · PSR vs 0 = 68% · breakeven trials N* = **1**
- Stabilitate: 38% din fold-uri pozitive · trend 0.12 (p=0.78) · fold exp: `+0.92 -1.02 -0.31 -0.34 +1.85 -0.49 -1.02 +1.28`
- Train/Test: 0.112R (24t) / 0.142R (13t) · max DD -9.9R

### 🔴 DEMOTE — S16 S16 — GBPAUD H1 BOTH+BE  (GBPAUD, BOTH)

- Trade-uri: **153** · win rate 25% · profit factor 1.13 · perioada 2016-10-19 → 2026-06-11
- Expectancy: **0.088R** (bootstrap 95% CI: -0.183 … 0.379R) · Sharpe/trade 0.05
- P(edge>0) = **73%** · PSR vs 0 = 74% · breakeven trials N* = **1**
- Stabilitate: 50% din fold-uri pozitive · trend 0.14 (p=0.74) · fold exp: `+0.10 -0.66 -0.00 +0.08 +0.96 -0.13 -0.35 +0.71`
- Train/Test: 0.069R (110t) / 0.137R (43t) · max DD -19.6R

### 🔴 DEMOTE — S20 S20 — XAUUSD Live (XAUUSD, BOTH)

- Trade-uri: **782** · win rate 36% · profit factor 1.05 · perioada 2017-12-18 → 2026-06-05
- Expectancy: **0.025R** (bootstrap 95% CI: -0.075 … 0.128R) · Sharpe/trade 0.02
- P(edge>0) = **68%** · PSR vs 0 = 71% · breakeven trials N* = **1**
- Stabilitate: 62% din fold-uri pozitive · trend 0.64 (p=0.09) · fold exp: `-0.16 +0.10 -0.11 -0.25 +0.08 +0.03 +0.20 +0.32`
- Train/Test: -0.101R (441t) / 0.187R (341t) · max DD -58.8R
- ⚠ train negativ / test pozitiv (posibil regim recent); edge in crestere in timp (dependenta de regim)

### 🔴 DEMOTE — S14 S14 — CHFJPY H1 LONG all (CHFJPY, BOTH)

- Trade-uri: **180** · win rate 41% · profit factor 1.02 · perioada 2021-08-11 → 2026-06-05
- Expectancy: **0.013R** (bootstrap 95% CI: -0.192 … 0.238R) · Sharpe/trade 0.01
- P(edge>0) = **54%** · PSR vs 0 = 56% · breakeven trials N* = **1**
- Stabilitate: 50% din fold-uri pozitive · trend 0.12 (p=0.78) · fold exp: `-0.12 +0.54 -0.22 -0.31 -0.42 +0.17 +0.39 +0.09`
- Train/Test: -0.068R (126t) / 0.202R (54t) · max DD -24.7R
- ⚠ train negativ / test pozitiv (posibil regim recent)

### 🔴 DEMOTE — S10 S10 — GBPCAD H1 LONG+Flag (GBPCAD, BOTH)

- Trade-uri: **402** · win rate 34% · profit factor 0.93 · perioada 2016-10-19 → 2026-06-11
- Expectancy: **-0.040R** (bootstrap 95% CI: -0.176 … 0.095R) · Sharpe/trade -0.03
- P(edge>0) = **29%** · PSR vs 0 = 27% · breakeven trials N* = **1**
- Stabilitate: 38% din fold-uri pozitive · trend 0.62 (p=0.10) · fold exp: `-0.51 -0.21 +0.35 -0.18 -0.14 -0.14 +0.18 +0.34`
- Train/Test: -0.138R (266t) / 0.152R (136t) · max DD -43.6R
- ⚠ train negativ / test pozitiv (posibil regim recent)

### 🔴 DEMOTE — S9 S9 — USDJPY M15 LONG (USDJPY, LONG)

- Trade-uri: **895** · win rate 23% · profit factor 0.94 · perioada 2018-05-22 → 2026-06-05
- Expectancy: **-0.049R** (bootstrap 95% CI: -0.176 … 0.085R) · Sharpe/trade -0.03
- P(edge>0) = **24%** · PSR vs 0 = 21% · breakeven trials N* = **1**
- Stabilitate: 25% din fold-uri pozitive · trend 0.40 (p=0.32) · fold exp: `-0.24 -0.01 -0.30 +0.33 -0.21 -0.21 -0.06 +0.32`
- Train/Test: -0.087R (631t) / 0.043R (264t) · max DD -93.0R
- ⚠ train negativ / test pozitiv (posibil regim recent)

### 🔴 DEMOTE — S1 S1 — EURUSD M15 LONG (EURUSD, BOTH)

- Trade-uri: **1516** · win rate 36% · profit factor 0.90 · perioada 2018-05-22 → 2026-06-05
- Expectancy: **-0.056R** (bootstrap 95% CI: -0.119 … 0.007R) · Sharpe/trade -0.05
- P(edge>0) = **4%** · PSR vs 0 = 3% · breakeven trials N* = **1**
- Stabilitate: 38% din fold-uri pozitive · trend 0.48 (p=0.23) · fold exp: `-0.26 +0.03 -0.05 -0.15 +0.01 -0.13 -0.04 +0.14`
- Train/Test: -0.081R (1077t) / 0.007R (439t) · max DD -118.8R
- ⚠ train negativ / test pozitiv (posibil regim recent)

### 🔴 DEMOTE — S18 S18 — NZDJPY H1 BOTH+IB (NZDJPY, BOTH)

- Trade-uri: **190** · win rate 36% · profit factor 0.91 · perioada 2021-08-11 → 2026-06-05
- Expectancy: **-0.060R** (bootstrap 95% CI: -0.214 … 0.110R) · Sharpe/trade -0.05
- P(edge>0) = **23%** · PSR vs 0 = 26% · breakeven trials N* = **1**
- Stabilitate: 38% din fold-uri pozitive · trend -0.02 (p=0.96) · fold exp: `+0.19 -0.13 -0.07 -0.10 -0.30 +0.04 -0.47 +0.36`
- Train/Test: -0.124R (132t) / 0.086R (58t) · max DD -25.7R
- ⚠ train negativ / test pozitiv (posibil regim recent)

### 🔴 DEMOTE — S15 S15 — GBPUSD M15 LONG (GBPUSD, LONG)

- Trade-uri: **559** · win rate 36% · profit factor 0.90 · perioada 2018-05-22 → 2026-06-05
- Expectancy: **-0.060R** (bootstrap 95% CI: -0.161 … 0.037R) · Sharpe/trade -0.05
- P(edge>0) = **12%** · PSR vs 0 = 12% · breakeven trials N* = **1**
- Stabilitate: 25% din fold-uri pozitive · trend 0.00 (p=1.00) · fold exp: `-0.09 -0.07 +0.05 -0.21 -0.13 -0.10 -0.09 +0.16`
- Train/Test: -0.072R (403t) / -0.029R (156t) · max DD -55.7R

### 🔴 DEMOTE — S5 S5 — USDCHF H1 BOTH (USDCHF, BOTH)

- Trade-uri: **832** · win rate 37% · profit factor 0.89 · perioada 2018-05-29 → 2026-06-11
- Expectancy: **-0.064R** (bootstrap 95% CI: -0.149 … 0.018R) · Sharpe/trade -0.06
- P(edge>0) = **6%** · PSR vs 0 = 5% · breakeven trials N* = **1**
- Stabilitate: 38% din fold-uri pozitive · trend 0.74 (p=0.04) · fold exp: `-0.33 -0.18 -0.01 -0.28 +0.09 +0.01 -0.04 +0.23`
- Train/Test: -0.110R (602t) / 0.055R (230t) · max DD -93.1R
- ⚠ train negativ / test pozitiv (posibil regim recent); edge in crestere in timp (dependenta de regim)

### 🔴 DEMOTE — S6 S6 — US30 M15 BOTH (US30, BOTH)

- Trade-uri: **844** · win rate 36% · profit factor 0.91 · perioada 2017-11-24 → 2026-06-05
- Expectancy: **-0.067R** (bootstrap 95% CI: -0.176 … 0.047R) · Sharpe/trade -0.05
- P(edge>0) = **13%** · PSR vs 0 = 10% · breakeven trials N* = **1**
- Stabilitate: 38% din fold-uri pozitive · trend -0.10 (p=0.82) · fold exp: `+0.03 -0.14 -0.10 -0.11 +0.01 -0.21 -0.15 +0.13`
- Train/Test: -0.082R (608t) / -0.028R (236t) · max DD -89.8R

### 🔴 DEMOTE — S13 S13 — EURJPY M15 LONG (EURJPY, LONG)

- Trade-uri: **357** · win rate 34% · profit factor 0.90 · perioada 2018-05-22 → 2026-06-05
- Expectancy: **-0.068R** (bootstrap 95% CI: -0.237 … 0.098R) · Sharpe/trade -0.05
- P(edge>0) = **21%** · PSR vs 0 = 20% · breakeven trials N* = **1**
- Stabilitate: 50% din fold-uri pozitive · trend 0.29 (p=0.49) · fold exp: `-0.34 +0.29 -0.34 +0.21 -0.60 +0.11 -0.19 +0.33`
- Train/Test: -0.120R (238t) / 0.036R (119t) · max DD -50.8R
- ⚠ train negativ / test pozitiv (posibil regim recent)

### 🔴 DEMOTE — S8 S8 — EURCAD H1 LONG+Flag (EURCAD, LONG)

- Trade-uri: **408** · win rate 27% · profit factor 0.88 · perioada 2016-10-19 → 2026-06-11
- Expectancy: **-0.083R** (bootstrap 95% CI: -0.217 … 0.059R) · Sharpe/trade -0.06
- P(edge>0) = **12%** · PSR vs 0 = 13% · breakeven trials N* = **1**
- Stabilitate: 25% din fold-uri pozitive · trend 0.50 (p=0.21) · fold exp: `-0.05 -0.19 -0.21 -0.00 -0.25 -0.19 +0.02 +0.19`
- Train/Test: -0.096R (243t) / -0.064R (165t) · max DD -48.2R

### 🔴 DEMOTE — S19 S19 — AUDNZD M15 BOTH (AUDNZD, BOTH)

- Trade-uri: **40** · win rate 35% · profit factor 0.84 · perioada 2025-01-02 → 2026-06-12
- Expectancy: **-0.132R** (bootstrap 95% CI: -0.576 … 0.278R) · Sharpe/trade -0.08
- P(edge>0) = **28%** · PSR vs 0 = 31% · breakeven trials N* = **1**
- Stabilitate: 38% din fold-uri pozitive · trend 0.76 (p=0.03) · fold exp: `-0.30 -1.27 -1.20 +0.73 -0.04 -0.04 +0.07 +1.00`
- Train/Test: -0.449R (26t) / 0.456R (14t) · max DD -12.8R
- ⚠ train negativ / test pozitiv (posibil regim recent); edge in crestere in timp (dependenta de regim)

### 🔴 DEMOTE — S12 S12 — EURAUD H1 LONG (EURAUD, BOTH)

- Trade-uri: **195** · win rate 34% · profit factor 0.78 · perioada 2016-10-19 → 2026-06-11
- Expectancy: **-0.136R** (bootstrap 95% CI: -0.275 … 0.012R) · Sharpe/trade -0.12
- P(edge>0) = **3%** · PSR vs 0 = 6% · breakeven trials N* = **1**
- Stabilitate: 25% din fold-uri pozitive · trend 0.07 (p=0.87) · fold exp: `+0.22 -0.46 -0.25 -0.29 -0.14 -0.03 -0.31 +0.17`
- Train/Test: -0.133R (131t) / -0.143R (64t) · max DD -39.1R

### 🔴 DEMOTE — S4 S4 — GER40 M15 LONG+Flag (GER40, BOTH)

- Trade-uri: **1452** · win rate 34% · profit factor 0.77 · perioada 2017-09-21 → 2026-06-05
- Expectancy: **-0.164R** (bootstrap 95% CI: -0.242 … -0.084R) · Sharpe/trade -0.12
- P(edge>0) = **0%** · PSR vs 0 = 0% · breakeven trials N* = **1**
- Stabilitate: 12% din fold-uri pozitive · trend 0.62 (p=0.10) · fold exp: `-0.18 -0.41 -0.06 -0.12 -0.15 -0.35 -0.06 +0.03`
- Train/Test: -0.218R (1071t) / -0.012R (381t) · max DD -274.6R

### 🔴 DEMOTE — S7 S7 — XRPUSD M15 BOTH+Flag+IB (XRPUSD, BOTH)

- Trade-uri: **1063** · win rate 40% · profit factor 0.42 · perioada 2025-01-01 → 2026-06-08
- Expectancy: **-0.540R** (bootstrap 95% CI: -0.665 … -0.430R) · Sharpe/trade -0.40
- P(edge>0) = **0%** · PSR vs 0 = 0% · breakeven trials N* = **1**
- Stabilitate: 0% din fold-uri pozitive · trend -0.24 (p=0.57) · fold exp: `-0.39 -0.54 -0.54 -0.26 -0.32 -0.40 -0.52 -1.36`
- Train/Test: -0.428R (823t) / -0.925R (240t) · max DD -577.7R

### 🔴 DEMOTE — S21 S21 - CSCO.NAS M15 LONG obs (CSCO.NAS, LONG)

- Trade-uri: **528** · win rate 36% · profit factor 0.30 · perioada 2008-12-01 → 2026-08-10
- Expectancy: **-0.744R** (bootstrap 95% CI: -0.892 … -0.603R) · Sharpe/trade -0.52
- P(edge>0) = **0%** · PSR vs 0 = 0% · breakeven trials N* = **1**
- Stabilitate: 0% din fold-uri pozitive · trend 0.24 (p=0.57) · fold exp: `-1.19 -0.89 -0.43 -0.61 -0.65 -0.59 -0.77 -0.82`
- Train/Test: -0.723R (479t) / -0.953R (49t) · max DD -396.0R
