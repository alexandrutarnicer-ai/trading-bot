# Special Take Profit Mode — cercetare, decizie, implementare (2026-11-05)

## 1. Regula și ce face ea în realitate

Propunerea userului, pentru RR 1:2, cu extensie +0,10R, SL 0,10R sub prag și pas 0,50R:

| Moment | SL | TP |
|---|---|---|
| intrare | −1R | 2,10R |
| prețul atinge 2,0R | 1,90R | 2,60R |
| prețul atinge 2,5R | 2,40R | 3,10R |
| prețul atinge 3,0R | 2,90R | 3,60R |

Formula generică (`profit_lock.levels`):
- pragul L = rr + k × pas;
- SL = L − offset;
- TP = L + pas + extensie.

Funcționează la fel pentru orice RR (2R → 2,10R, 3R → 3,10R, 4R → 4,10R) și pentru BUY și SELL. Conversia R → preț e
`entry ± R × risc`. Rotunjirea la tick se face departe de piață; SL-ul e monoton.

**Constatare matematică (confirmată de backtest):**
- pragul următor (L + pas) e **mereu sub** TP (L + pas + extensie);
- un preț continuu trece întâi prin prag și mută TP-ul mai departe, deci **TP-ul nu se atinge decât printr-un gap**;
- mecanismul real e un **trailing stop în trepte, pornit de la RR-ul inițial**;
- extensia (+0,10 / 0,15 / 0,20R) contează doar la gap-uri. În backtest, cele trei valori dau rezultate practic identice.

## 2. Metodologie

- **Intrări:** exact engine-ul respectiv. Se schimbă DOAR ieșirea, simulată cu `profit_lock.simulate_path`, aceeași
  funcție folosită live.
  - **Custom:** profilul standard ca acum (S15 GBPUSD LONG, S1 EURUSD BOTH; M15+M30, break-even-ul configurat, TP 2R),
    semnalele din `engine.portfolio.run_portfolio`.
    - Ieșiri pe M1, 2021-01 → 2026-11, închidere vineri la 20:00.
    - Costuri: spread-ul contului Standard (0,9 / 0,8 pip) + 25% slippage + swap pe nopți.
    - Filtrul AI nu se simulează.
  - **Daily:** configurația curentă (GBPUSD Londra 5 min, DE40 Frankfurt 5 min, breakout). Ieșiri pe M5, GBPUSD
    2010–2026, DE40 2013–2026. Costurile sunt ale engine-ului.
  - **Noisy:** configurația curentă (US500 M1, TP 2R, stop de timp 20 de bare), ultimele 12 luni din MT5.
- **Ordinea în bară e conservatoare:** gap → SL → TP → abia apoi treptele (noul SL se aplică de la bara următoare).
- **Selecție:** parametrii se aleg pe TRAIN (primele 70% din trade-uri, în timp); rezultatul se raportează pe TEST
  (ultimele 30%).
- **Granularitate:** am făcut și un test de realism, cu treptele recalculate doar la închiderea barei M15 (cum
  verifică Custom live) și SL-ul brokerului lovit oricând.
- **AI Engine nu a fost testat.** TP-ul îl alege consiliul, iar ledger-ul real are prea puține trade-uri pe piețele cu
  date M1.

## 3. Rezultate (toate variantele, după costuri)

**Custom GBPUSD (S15 M15+M30)**

| Variantă | n | Net R | R/trade | WR | PF | Avg win | Avg loss | DD (R) | Max pierderi la rând | Train | Test | ≥2R | ≥3R | ≥5R | Profit cedat pe blocări |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| current | 397 | -19.8 | -0.0498 | 36.8% | 0.925 | 1.662 | -1.045 | -45.7 | 16 | -0.1354 | +0.1479 | 25.7% | 1.3% | 0.3% | — |
| special e0.10 s0.5 o0.10 | 397 | -12.9 | -0.0325 | 35.0% | 0.952 | 1.831 | -1.036 | -47.4 | 16 | -0.1293 | +0.1908 | 28.7% | 3.8% | 0.3% | 0.259 |
| special e0.15 s0.5 o0.10 | 397 | -15.4 | -0.0387 | 34.5% | 0.943 | 1.855 | -1.037 | -48.4 | 16 | -0.1304 | +0.1730 | 29.5% | 3.8% | 0.3% | 0.261 |
| special e0.20 s0.5 o0.10 | 395 | -15.9 | -0.0401 | 33.9% | 0.941 | 1.901 | -1.037 | -47.2 | 16 | -0.1226 | +0.1511 | 30.6% | 3.8% | 0.3% | 0.256 |
| special e0.10 s1 o0.10 | 396 | -12.8 | -0.0322 | 34.8% | 0.952 | 1.845 | -1.036 | -48.1 | 16 | -0.1211 | +0.1745 | 28.5% | 5.8% | 0.3% | 0.321 |
| special e0.10 s0.5 o0.50 | 394 | -10.8 | -0.0275 | 34.8% | 0.959 | 1.865 | -1.036 | -45.2 | 16 | -0.1204 | +0.1871 | 28.4% | 8.6% | 1.3% | 0.663 |
| special e0.10 s1 o0.50 | 394 | -3.9 | -0.0099 | 34.8% | 0.985 | 1.915 | -1.036 | -42.4 | 16 | -0.1094 | +0.2201 | 28.4% | 8.4% | 1.5% | 0.56 |
| alt atr_trail k2 | 396 | -6.1 | -0.0155 | 34.8% | 0.977 | 1.893 | -1.036 | -43.8 | 16 | -0.1055 | +0.1939 | 28.5% | 5.6% | 2.0% | 0.462 |
| alt atr_trail k3 | 396 | -0.8 | -0.0020 | 34.8% | 0.997 | 1.932 | -1.036 | -37.3 | 16 | -0.0790 | +0.1773 | 28.5% | 5.6% | 2.5% | 0.559 |
| alt lock_from_1R s0.5 o0.5 | 397 | -4.9 | -0.0122 | 51.4% | 0.976 | 0.958 | -1.038 | -35.5 | 6 | -0.0791 | +0.1421 | 8.6% | 2.5% | 0.5% | 0.614 |

**Custom EURUSD (S1 M15+M30)**

| Variantă | n | Net R | R/trade | WR | PF | Avg win | Avg loss | DD (R) | Max pierderi la rând | Train | Test | ≥2R | ≥3R | ≥5R | Profit cedat pe blocări |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| current | 1133 | -9.4 | -0.0083 | 36.5% | 0.987 | 1.801 | -1.05 | -60.1 | 12 | -0.0477 | +0.0835 | 30.4% | 0.8% | 0.0% | — |
| special e0.10 s0.5 o0.10 | 1121 | 11.2 | +0.0100 | 35.4% | 1.015 | 1.943 | -1.05 | -44.7 | 15 | -0.0267 | +0.0953 | 34.7% | 2.1% | 0.0% | 0.235 |
| special e0.15 s0.5 o0.10 | 1121 | 11.5 | +0.0102 | 35.4% | 1.015 | 1.943 | -1.05 | -44.7 | 15 | -0.0267 | +0.0961 | 34.7% | 2.1% | 0.0% | 0.235 |
| special e0.20 s0.5 o0.10 | 1121 | 11.5 | +0.0102 | 35.4% | 1.015 | 1.943 | -1.05 | -44.7 | 15 | -0.0267 | +0.0961 | 34.7% | 2.1% | 0.0% | 0.235 |
| special e0.10 s1 o0.10 | 1120 | 1.5 | +0.0014 | 35.4% | 1.002 | 1.916 | -1.05 | -47.5 | 15 | -0.0306 | +0.0761 | 34.7% | 3.5% | 0.0% | 0.303 |
| special e0.10 s0.5 o0.50 | 1105 | 1.0 | +0.0009 | 35.7% | 1.001 | 1.896 | -1.049 | -51.9 | 15 | -0.0433 | +0.1039 | 34.9% | 5.4% | 0.5% | 0.577 |
| special e0.10 s1 o0.50 | 1117 | 2.6 | +0.0024 | 35.5% | 1.004 | 1.91 | -1.05 | -47.5 | 15 | -0.0290 | +0.0753 | 34.8% | 4.0% | 0.4% | 0.369 |
| alt atr_trail k2 | 1119 | -3.3 | -0.0030 | 35.5% | 0.996 | 1.901 | -1.05 | -51.5 | 15 | -0.0380 | +0.0787 | 34.8% | 3.4% | 0.4% | 0.371 |
| alt atr_trail k3 | 1119 | 1.1 | +0.0010 | 35.5% | 1.001 | 1.912 | -1.05 | -50.4 | 15 | -0.0336 | +0.0815 | 34.8% | 3.6% | 0.8% | 0.421 |
| alt lock_from_1R s0.5 o0.5 | 1130 | -18.1 | -0.0160 | 50.3% | 0.969 | 1.009 | -1.052 | -63.4 | 9 | -0.0701 | +0.1102 | 12.4% | 2.2% | 0.3% | 0.605 |

**Daily GBPUSD (London 5m breakout)**

| Variantă | n | Net R | R/trade | WR | PF | Avg win | Avg loss | DD (R) | Max pierderi la rând | Train | Test | ≥2R | ≥3R | ≥5R | Profit cedat pe blocări |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| current | 3974 | 275.9 | +0.0694 | 19.9% | 1.077 | 4.9 | -1.129 | -141.3 | 31 | +0.0707 | +0.0665 | 36.6% | 26.6% | 15.2% | — |
| standard 2R | 3974 | -79.6 | -0.0200 | 37.2% | 0.972 | 1.859 | -1.131 | -182.6 | 14 | -0.0474 | +0.0437 | 36.7% | 4.7% | 0.5% | — |
| special e0.10 s0.5 o0.10 | 3974 | 61.3 | +0.0154 | 37.0% | 1.022 | 1.963 | -1.129 | -82.8 | 14 | -0.0004 | +0.0523 | 36.6% | 6.7% | 0.7% | 0.328 |
| special e0.15 s0.5 o0.10 | 3974 | 60.3 | +0.0152 | 37.0% | 1.021 | 1.965 | -1.129 | -82.8 | 14 | -0.0007 | +0.0523 | 36.6% | 6.7% | 0.7% | 0.328 |
| special e0.20 s0.5 o0.10 | 3974 | 60.7 | +0.0153 | 37.0% | 1.021 | 1.965 | -1.129 | -82.9 | 14 | -0.0006 | +0.0523 | 36.6% | 6.8% | 0.7% | 0.328 |
| special e0.10 s1 o0.10 | 3974 | 34.2 | +0.0086 | 37.0% | 1.012 | 1.945 | -1.129 | -85.2 | 14 | -0.0041 | +0.0382 | 36.6% | 8.8% | 1.1% | 0.492 |
| special e0.10 s0.5 o0.50 | 3974 | 30.9 | +0.0078 | 37.0% | 1.011 | 1.943 | -1.129 | -86.1 | 14 | -0.0044 | +0.0361 | 36.6% | 11.5% | 1.2% | 0.719 |
| special e0.10 s1 o0.50 | 3974 | 10.2 | +0.0026 | 37.0% | 1.004 | 1.929 | -1.129 | -98.2 | 14 | -0.0054 | +0.0210 | 36.6% | 13.9% | 2.1% | 0.882 |
| alt atr_trail k2 | 3974 | 33.8 | +0.0085 | 37.0% | 1.012 | 1.945 | -1.129 | -97.2 | 14 | -0.0089 | +0.0489 | 36.6% | 8.8% | 2.7% | 0.887 |
| alt atr_trail k3 | 3974 | 57.1 | +0.0144 | 37.0% | 1.02 | 1.961 | -1.129 | -96.3 | 14 | +0.0028 | +0.0414 | 36.6% | 8.8% | 3.2% | 1.045 |
| alt lock_from_1R s0.5 o0.5 | 3974 | 11.1 | +0.0028 | 51.1% | 1.005 | 1.064 | -1.106 | -86.9 | 10 | -0.0050 | +0.0209 | 18.2% | 6.1% | 0.7% | 0.716 |

**Daily DE40 (Berlin 5m breakout)**

| Variantă | n | Net R | R/trade | WR | PF | Avg win | Avg loss | DD (R) | Max pierderi la rând | Train | Test | ≥2R | ≥3R | ≥5R | Profit cedat pe blocări |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| current | 2595 | 216.9 | +0.0836 | 28.7% | 1.121 | 2.698 | -0.967 | -64.3 | 20 | +0.0705 | +0.1141 | 29.6% | 19.2% | 8.2% | — |
| standard 2R | 2595 | 78.8 | +0.0304 | 37.4% | 1.05 | 1.711 | -0.973 | -42.0 | 15 | +0.0111 | +0.0754 | 29.6% | 1.7% | 0.0% | — |
| special e0.10 s0.5 o0.10 | 2595 | 100.9 | +0.0389 | 37.4% | 1.064 | 1.734 | -0.973 | -39.0 | 15 | +0.0164 | +0.0913 | 29.6% | 3.4% | 0.1% | 0.306 |
| special e0.15 s0.5 o0.10 | 2595 | 100.9 | +0.0389 | 37.4% | 1.064 | 1.734 | -0.973 | -39.0 | 15 | +0.0164 | +0.0913 | 29.6% | 3.4% | 0.1% | 0.306 |
| special e0.20 s0.5 o0.10 | 2595 | 100.2 | +0.0386 | 37.4% | 1.063 | 1.733 | -0.973 | -39.0 | 15 | +0.0160 | +0.0913 | 29.6% | 3.4% | 0.1% | 0.306 |
| special e0.10 s1 o0.10 | 2595 | 106.2 | +0.0409 | 37.4% | 1.067 | 1.739 | -0.973 | -37.8 | 15 | +0.0172 | +0.0962 | 29.6% | 5.7% | 0.2% | 0.425 |
| special e0.10 s0.5 o0.50 | 2595 | 103.1 | +0.0397 | 37.4% | 1.065 | 1.736 | -0.973 | -39.6 | 15 | +0.0201 | +0.0855 | 29.6% | 8.3% | 0.7% | 0.703 |
| special e0.10 s1 o0.50 | 2595 | 118.6 | +0.0457 | 37.4% | 1.075 | 1.752 | -0.973 | -39.1 | 15 | +0.0230 | +0.0987 | 29.6% | 10.6% | 1.3% | 0.841 |
| alt atr_trail k2 | 2595 | 99.8 | +0.0385 | 37.4% | 1.063 | 1.732 | -0.973 | -42.4 | 15 | +0.0184 | +0.0851 | 29.6% | 5.7% | 1.6% | 0.741 |
| alt atr_trail k3 | 2595 | 112.9 | +0.0435 | 37.4% | 1.071 | 1.746 | -0.973 | -45.0 | 15 | +0.0212 | +0.0954 | 29.6% | 5.7% | 1.9% | 0.805 |
| alt lock_from_1R s0.5 o0.5 | 2595 | 87.4 | +0.0337 | 50.6% | 1.07 | 1.016 | -0.971 | -35.2 | 9 | +0.0382 | +0.0230 | 13.7% | 4.1% | 0.3% | 0.701 |

**Noisy US500 (M1, TP 2R, stop 20 bare)**

| Variantă | n | Net R | R/trade | WR | PF | Avg win | Avg loss | DD (R) | Max pierderi la rând | Train | Test | ≥2R | ≥3R | ≥5R | Profit cedat pe blocări |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| current | 3996 | -385.3 | -0.0964 | 37.4% | 0.857 | 1.55 | -1.081 | -402.5 | 14 | -0.0703 | -0.1573 | 27.3% | 1.2% | 0.1% | — |
| special e0.10 s0.5 o0.10 | 3980 | -356.8 | -0.0897 | 37.5% | 0.867 | 1.564 | -1.081 | -383.5 | 14 | -0.0630 | -0.1517 | 27.4% | 3.0% | 0.2% | 0.309 |
| special e0.15 s0.5 o0.10 | 3980 | -357.0 | -0.0897 | 37.5% | 0.867 | 1.564 | -1.081 | -383.7 | 14 | -0.0630 | -0.1519 | 27.4% | 3.0% | 0.2% | 0.309 |
| special e0.20 s0.5 o0.10 | 3980 | -357.0 | -0.0897 | 37.5% | 0.867 | 1.564 | -1.081 | -383.7 | 14 | -0.0630 | -0.1519 | 27.4% | 3.0% | 0.2% | 0.309 |
| special e0.10 s1 o0.10 | 3953 | -366.3 | -0.0927 | 37.4% | 0.863 | 1.558 | -1.08 | -391.5 | 14 | -0.0701 | -0.1454 | 27.4% | 4.5% | 0.3% | 0.436 |
| special e0.10 s0.5 o0.50 | 3900 | -361.6 | -0.0927 | 37.5% | 0.863 | 1.556 | -1.08 | -405.2 | 14 | -0.0747 | -0.1348 | 27.4% | 6.4% | 0.5% | 0.709 |
| special e0.10 s1 o0.50 | 3847 | -326.1 | -0.0848 | 37.6% | 0.874 | 1.57 | -1.08 | -392.0 | 14 | -0.0705 | -0.1181 | 27.5% | 7.9% | 1.0% | 0.85 |
| alt atr_trail k2 | 3892 | -316.3 | -0.0813 | 37.6% | 0.879 | 1.577 | -1.08 | -355.9 | 14 | -0.0582 | -0.1351 | 27.5% | 4.5% | 0.9% | 0.58 |
| alt atr_trail k3 | 3881 | -323.1 | -0.0833 | 37.5% | 0.877 | 1.575 | -1.08 | -364.7 | 14 | -0.0599 | -0.1376 | 27.5% | 4.6% | 1.2% | 0.621 |
| alt lock_from_1R s0.5 o0.5 | 3948 | -401.0 | -0.1016 | 50.7% | 0.814 | 0.879 | -1.111 | -418.7 | 10 | -0.0769 | -0.1592 | 13.5% | 3.2% | 0.3% | 0.702 |

### Actualizare la bara M15 (cum rulează Custom live)

| Piață | Variantă | n | R/trade | Train | Test | DD (R) | PF |
|---|---|---|---|---|---|---|---|
| Custom GBPUSD | current | 397 | -0.0498 | -0.1354 | +0.1479 | -45.7 | 0.925 |
| Custom GBPUSD | special e0.10 s0.5 o0.10 (userul) | 397 | -0.0298 | -0.1299 | +0.2011 | -47.4 | 0.956 |
| Custom GBPUSD | special e0.10 s1 o0.50 | 397 | -0.0332 | -0.1324 | +0.1956 | -48.7 | 0.951 |
| Custom GBPUSD | alt atr_trail k3 | 397 | -0.0328 | -0.1317 | +0.1955 | -47.4 | 0.951 |
| Custom EURUSD | current | 1133 | -0.0083 | -0.0477 | +0.0835 | -60.1 | 0.987 |
| Custom EURUSD | special e0.10 s0.5 o0.10 (userul) | 1120 | +0.0142 | -0.0233 | +0.1016 | -45.0 | 1.021 |
| Custom EURUSD | special e0.10 s1 o0.50 | 1112 | +0.0151 | -0.0228 | +0.1033 | -46.4 | 1.022 |
| Custom EURUSD | alt atr_trail k3 | 1120 | +0.0150 | -0.0214 | +0.0997 | -43.5 | 1.022 |

### Selecția pe train (piețele cu TP fix: Custom ×2 + Noisy)

| Variantă | Δ train medie | Δ train minimă | Δ test medie | Δ test minimă |
|---|---|---|---|---|
| alt atr_trail k3 (aleasă pe train) | +0,027 | +0,010 | +0,016 | **−0,002** |
| special e0.10 s0.5 o0.10 (**userul**) | +0,012 | **+0,006** | +0,020 | **+0,006** |
| special e0.10 s1 o0.50 | +0,015 | −0,000 | +0,034 | −0,008 |

## 4. Decizia echipei

1. **Custom Engine: implementat cu varianta userului (+0,10R / 0,10R / pas 0,50R).**
   - E singura variantă care îmbunătățește **toate** piețele cu TP fix **atât pe train, cât și pe test**.
   - Pe M15 (realismul live): EURUSD −0,008 → +0,014R/trade, iar drawdown-ul scade de la −60R la −45R. GBPUSD
     −0,050 → −0,030R.
   - Trailing-ul ATR k3 (alternativa echipei) are câștigul mediu cel mai mare pe train, dar e negativ pe o piață în
     test. Rămâne disponibil în UI (`mod: trailing ATR`), dar nu e implicit.
   - **Câștigul e mic** (+0,01…0,03R/trade) și nu e semnificativ statistic separat, pe fiecare piață. De aceea mecanismul
     e **OPRIT implicit**; activarea pe contul real e decizia userului, după observare.
2. **Daily Engine: exclus.** Varianta actuală (fără TP, închidere la final de zi) e de 2–5 ori mai bună: DE40 +0,084
   față de +0,039R, GBPUSD +0,069 față de +0,015R. Câștigul Daily vine din zilele cu trend complet, pe care blocarea în
   trepte le taie.
3. **Noisy Engine: exclus.** Stopul de timp de 20 de minute face efectul neglijabil (−0,096 → −0,090R), iar sistemul
   rămâne negativ.
4. **AI Engine: exclus** (netestat).

Excluderile sunt impuse în cod (`profit_lock.ELIGIBLE`). Niciun comutator, global sau pe engine, nu poate porni
mecanismul pe un engine neeligibil.

## 5. Arhitectură

- **`profit_lock.py`** (serviciu comun, pur):
  - `levels` / `stage`;
  - `plan_modification`: decizia live (modify / close / none), cu SL monoton față de SL-ul REAL din MT5, verificare
    `trade_stops_level` / `trade_freeze_level`, „nivel deja depășit → închidere la piață” și TP care nu se apropie
    niciodată de preț;
  - `simulate_path`: backtest;
  - `effective`: Global → Engine, plus eligibilitatea.
- **Configurare:**
  - `data/global_settings.json::special_tp` (Setări Globale; pornit → câștigă peste engine);
  - `special_tp` la nivelul profilului Custom (`data/profiles/standard.json` + profilul runtime, recitit la fiecare
    bară, fără restart);
  - API: `GET /settings/special-tp` (configurația ACTIVĂ per engine + motivul) și `PUT /settings/special-tp/engine`;
  - UI: rândul din Setări Globale + cardul „Special Take Profit — Custom Engine” din tab-ul Custom Engine (starea
    activă, sursa ei, tabelul de backtest).
- **Custom live** (`live/signal_generator._special_tp_step`), apelat după break-even pe pozițiile reale deschise:
  - **Oprit:** zero apeluri MT5.
  - **Vârful:** high / low al barelor ÎNCHISE de la activare. Bara în formare e ignorată, ca în backtestul M15.
  - **Poziția reală:** ticket ordin → `position_id` (cont hedging). Volumul real e folosit la închidere (poziții
    parțiale).
  - **Respins de broker:** starea reală rămâne, motivul se loghează o singură dată per treaptă, iar reîncercarea are loc
    la bara următoare.
  - **Restart:** compară cu SL-ul real, deci nu există dubluri și SL-ul nu coboară. Poziția închisă manual înseamnă că nu
    se face nimic.
  - **Break-even-ul existent nu mai trimite nimic** când Special TP a preluat poziția sau când SL-ul real e deja mai
    protector. Fără asta, BE ar fi coborât SL-ul și ar fi readus TP-ul la 2R.
  - **Interacțiunea cu celelalte protecții:** închiderea de vineri, protecția la știri și Setările Globale rămân
    neatinse, pentru că închid poziția indiferent de SL.

## 6. Teste

- `python scripts/test_profit_lock.py` (37): exemplul userului cifră cu cifră, BUY / SELL, tick, monoton,
  plan_modification (dubluri, restart, manual, nivel depășit, stops_level, TP); echivalență 400/400 cu
  `engine.simulator.simulate_trade` când e oprit.
- `python scripts/test_special_tp_live.py` (19): hook-ul live pe MT5 simulat.
- Cercetare: `python scripts/research_tp/tp_modes.py` → `tp_select.py` → `tp_granularity.py`
  (rezultate în `data/research_tp/`).

## 7. Limite

- **Backtestul nu poate determina ordinea în interiorul barei M1.** Ipoteza e conservatoare: SL-ul are prioritate.
- **Pe Custom live, treptele se mută doar la închiderea barei** (M15 / H1). Între bare protejează doar SL-ul deja trimis.
- **Filtrul AI pre-trade al Custom nu e simulat.** Intrările reale sunt un subset.
- **Pe contul de ~206 $, majoritatea pozițiilor sunt la lotul minim.** Nu există închideri parțiale, deci mecanismul
  mută doar SL-ul întregii poziții.
