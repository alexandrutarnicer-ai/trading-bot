# Sesiuni Live — Trading Bot

Patru sesiuni independente. Capital separat, loguri separate. Pot rula simultan fara conflict.

---

## Sesiune 1 — FX Long, M15

| Parametru | Valoare |
|-----------|---------|
| Script | `python live/session1_m15_long.py` |
| Piete | EURUSD, GBPUSD, EURJPY |
| Directie | LONG only |
| Timeframe | M15 (trend M30) |
| Pullback window | 8 |
| Sesiune activa | 10-18h UTC (13-21h EET vara) |
| Skip ore | 15-16h UTC |
| Skip zile | Luni |
| Frecventa | ~0.9 trades/saptamana |
| Expectancy test | +0.375R |
| DD max | -50.6% |
| Output | `data/live_signals/session1/` |

---

## Sesiune 2 — FX Both, M15, 6 piete

| Parametru | Valoare |
|-----------|---------|
| Script | `python live/session2_m5_both.py` |
| Piete EUR | EURUSD, GBPUSD, EURJPY |
| Piete JPY | USDJPY, AUDJPY, NZDJPY |
| Directie | BOTH (long + short) |
| Timeframe | M15 (trend M30) |
| Pullback window | 6 |
| Sesiune EUR | 10-18h UTC (13-21h EET vara) |
| Sesiune JPY | 02-10h UTC (05-13h EET vara) |
| Skip ore | 15-16h UTC |
| Skip zile | niciunul |
| Frecventa | ~3.2 trades/saptamana |
| Expectancy test | +0.142R |
| DD max | -45.4% |
| Output | `data/live_signals/session2/` |

---

## Sesiune 3 — BTC Crypto, M15

| Parametru | Valoare |
|-----------|---------|
| Script | `python live/session3_btc_both.py` |
| Piete | BTCUSD |
| Directie | BOTH (long + short) |
| Timeframe | M15 (trend M30) |
| Pullback window | 8 |
| Sesiune activa | 00-09h UTC + 15-18h UTC |
| Skip ore | 10-14h UTC (EU mid/news), 19-23h UTC (US prime) |
| Skip zile | Sambata (lichiditate scazuta, WR 12%) |
| Frecventa | ~2.4 trades/saptamana |
| Expectancy test | +0.336R, p=0.0075*** |
| DD max | -22.5% |
| Capital | $500 → $3355 (+571%, 6 ani) |
| Spread | $12.00 (1200 ticks), spread/SL=4.5% |
| Output | `data/live_signals/session3/` |

**Validare (2026-06-08):**
- TRAIN 523 trades: +0.211R, p=0.0075***
- TEST  224 trades: +0.336R, p=0.0075***
- Toate cele 7 ani (2020-2026) pozitive, inclusiv bear 2022 (+0.263R)
- Swap: 3.7% din PnL brut (neglijabil)

**De ce functioneaza filtrul de sesiune:**
Pullback-urile BTC M15 nu tin structura in EU mid (stiri, ECB) si US prime (algo noise).
Asia + pre-EU (00-09h) si EU/early-US (15-18h) au miscare mai curata pe swing-uri.

---

## Sesiune 4 — GER40 + US30, LONG only, DEMO EXECUTION

> **ATENTIE:** Aceasta sesiune este in validare statistica. Executa ordine pe **demo** (nu real).
> Statistica insuficienta pentru real — re-evaluare planificata Dec 2026.

| Parametru | GER40 | US30 |
|-----------|-------|------|
| Script | `python live/session4_obs.py` | (acelasi script) |
| Directie | LONG only | LONG only |
| Timeframe | M15 (trend M30) | M15 (trend M30) |
| Pullback window | 6 | 6 |
| Sesiune activa | 09-14h UTC | 14-21h UTC |
| EET vara | 12:00-17:00 | 17:00-00:00 |
| EET iarna | 11:00-16:00 | 16:00-23:00 |
| Skip zile | Luni | Luni |
| Frecventa | ~0.35/saptamana | ~0.45/saptamana |
| Exp test | +0.480R p=0.045 | +0.224R p=0.165 |
| DD max | -31.8% | -15.3% |
| Capital | $175 (demo) | $175 (demo) |
| Output | `data/live_signals/session4/` | (acelasi director) |

**Frecventa totala S4: ~0.8 semnale/saptamana** (GER40 + US30 combinate).
In medie: 1 semnal la 8-10 zile lucratoare. Saptamani fara semnal sunt normale.

**De ce nu executam pe real (doar demo):**
- GER40: p=0.045 pre-Bonferroni, dar train (2017-2023) = -0.257R (regime-dependent)
- US30: train pozitiv (+0.074R) dar p=0.165 — prea putine date (74 teste in 2.5 ani)
- Dupa 50 semnale live per simbol, re-testam statistica (Dec 2026)

---

## Sesiune 5 — GER40 + USDCHF, H1+D1, OBSERVARE

> **ATENTIE:** Sesiune in observare statistica. `execute_trades=False` — nu executa ordine, logheaza + Telegram.
> Activare dupa 20-30 semnale live per simbol cu p < 0.05.

| Parametru | GER40 | USDCHF |
|-----------|-------|--------|
| Script | `python live/session5_ger40_h1.py` | (acelasi script) |
| Directie | BOTH | BOTH |
| Timeframe | H1 entry + D1 trend | H1 entry + D1 trend |
| Pullback window | 8 (optim 6) | 8 |
| Sesiune activa | 07-16h UTC | 07-17h UTC |
| EET vara | 10:00-19:00 | 10:00-20:00 |
| EET iarna | 09:00-18:00 | 09:00-19:00 |
| Skip zile | niciunul | niciunul |
| Frecventa | ~0.3/saptamana | ~0.3/saptamana |
| Exp test | +0.6505R p=0.103 (borderline) | +0.5269R p=0.0896* (VIABLE) |
| DD max | -21.9% | -13.7% |
| Capital | $175 (observare) | $175 (observare) |
| Output | `data/live_signals/session5/` | (acelasi director) |

**Validare USDCHF (2026-06-11, tf_scan_targeted.py):**
- N=105 total, split Jan 2024 (~8 ani date 2018-2026)
- TRAIN: pozitiv
- TEST: +0.5269R, p=0.0896*, DD=-13.7%, Sp/SL=5.2%
- Spread 1.2 pip — adecvat (5.2% din SL median)

**GER40 H1+D1 — date insuficiente pentru concluzie:**
- N test ~22 trades — borderline statistic
- Paralel cu S4 (GER40 M15): ordine independente in MT5, niciun conflict

**Cand activam execute_trades=True:**
- USDCHF: acumuleaza 20-30 semnale live, re-evalueaza p pe date noi
- GER40: asteapta mai multa data — borderline (p=0.103) necesita confirmare

---

## Program complet — cand sa rulezi ce

> Toate orele in **UTC**. EET vara (EEST, GMT+3) = UTC+3. Iarna (EET, GMT+2) = UTC+2.

```
UTC     EET(vara)   S1 (EUR)   S2 EUR   S2 JPY   S3 BTC    S4 GER40   S4 US30   S5 GER40H1  S5 USDCHF
00-02   03-05       -          -        -        ACTIV      -          -         -           -
02-09   05-12       -          -        ACTIV    ACTIV      -          -         -           -          ← S2+S3
07-09   10-12       -          -        ACTIV    ACTIV      -          -         obs         obs        ← +S5
09-10   12-13       -          -        ACTIV    pauza      ACTIV      -         obs         obs
10-14   13-17       ACTIV      ACTIV    -        pauza      ACTIV      -         obs         obs        ← S1+S2+S4+S5
14-15   17-18       ACTIV      ACTIV    -        pauza      -          ACTIV     -           obs        ← +S4 US30
15-16   18-19       ACTIV*     ACTIV*   -        ACTIV      -          ACTIV     -           obs        ← S1+S2+S3+S4+S5
16-17   19-20       ACTIV      ACTIV    -        ACTIV      -          ACTIV     -           obs        ← S5 USDCHF pana 17h
17-18   20-21       ACTIV      ACTIV    -        ACTIV      -          ACTIV     -           -
18-21   21-00       -          -        -        pauza      -          ACTIV     -           -          ← S4 US30 singur
21-23   00-02       -          -        -        pauza      -          -         -           -
```
*S5 este in OBSERVARE (execute_trades=False) — logheaza semnale dar nu executa ordine.
*Ora 15-16 UTC: S1 si S2 au `skip_hours=(15,16)` — filtrare interna automata.

### Recomandare practica

**Porneste toate 5 sesiunile simultan** cu un singur comandă:

```bash
python live/run_all.py
```

Status automat la fiecare 5 minute (semnale azi + total + PID per sesiune). Ctrl+C opreste tot.

**Notificari Telegram automate:**
- La pornire: lista sesiunilor active
- La oprire (Ctrl+C / restart Windows / SIGTERM): mesaj cu motivul opririi
- La semnal nou: entry / SL / TP / R
- La inchidere trade: TP +R / SL -1R / expirat

> **Important:** Nu porni sesiuni individual (fara `run_all.py`) cat timp `run_all.py` ruleaza deja.
> Doua instante pe acelasi simbol scriu in acelasi `state.pkl` si pot produce duplicate in `outcomes.csv`.

Sau manual, in terminale separate:

```bash
python live/session1_m15_long.py   # Terminal 1
python live/session2_m5_both.py    # Terminal 2
python live/session3_btc_both.py   # Terminal 3
python live/session4_obs.py        # Terminal 4  [DEMO]
python live/session5_ger40_h1.py   # Terminal 5  [OBS — fara executie]
```

- S1 si S2 se activeaza cand piata europeana/asiatica se deschide
- S3 BTC este activa noaptea (03-12h EET) si seara (18-21h EET)
- **S4 GER40 unica: 12-17h EET** (vara) — paralel cu S1+S2, inainte de deschiderea NYSE
- **S4 US30 unica: 21-00h EET** (vara) — singura sesiune activa seara tarziu

### Zile saptamana

| Zi | S1 | S2 EUR | S2 JPY | S3 BTC | S4 GER40 | S4 US30 |
|----|----|--------|--------|--------|----------|---------|
| Luni | skip | activ | activ | activ | **SKIP** | **SKIP** |
| Marti-Vineri | activ | activ | activ | activ | activ | activ |
| Sambata | activ | activ | activ | **SKIP** | activ | activ |
| Duminica | activ | activ | activ | activ | activ | activ |

---

## Capital si risc

Sesiunile sunt independente. **Sizing dinamic** — botul citeste equity-ul real din MT5 si
aplica o fractie per sesiune la fiecare trade. Pe masura ce contul creste sau scade,
lot size-ul se ajusteaza automat (compound growth / drawdown protection).

| Sesiune | Fractie din equity | Start ($800) | Risc/trade | Status |
|---------|-------------------|-------------|------------|--------|
| S1 FX Long | 12.5% | $100 | 1% = $1.00 | validat, activ |
| S2 FX Both | 12.5% | $100 | 1% = $1.00 | validat, activ |
| S3 BTC | 62.5% | $500 | 1% = $5.00 | validat p=0.0075, activ |
| S4 GER40+US30 | 12.5% | $100 | 1% = $1.00 | DEMO activ — re-test Dec 2026 |
| S5 GER40+USDCHF H1 | — | $175 fix | 1% din $175 | OBSERVARE — execute_trades=False |
| **TOTAL activ** | **100%** | **$800** | | |

S5 nu participa la sizing dinamic din equity — foloseste `session_capital=175` fix pana la activare.
Exemplu la crestere: daca equity ajunge la $1000, S3 risca $6.25/trade (62.5% × 1%).
Fallback: daca MT5 nu returneaza equity, foloseste `session_capital` fix din config.

---

## Observare live + executie demo (paralel)

Toate sesiunile ruleaza **in paralel** — executa ordine pending in MT5 (demo) SI logeaza in CSV:

Fisiere generate per sesiune:
- `signals.csv` — toate semnalele detectate (entry/sl/tp/R)
- `outcomes.csv` — rezultate: TP/SL/expirat/invalidat
- `generator.log` — log detaliat

Dupa 30-50 trades per sesiune, compara `result_r` mediu din `outcomes.csv` cu expectancy din backtest.

---

## Rezultate backtest sumar

| Sesiune | N test | Exp test | p-val | DD | Capital | Status |
|---------|--------|----------|-------|----|---------|--------|
| S1 M15 Long | - | +0.375R | - | -50.6% | 12.5% equity | validat |
| S2 M15 Both | - | +0.142R | - | -45.4% | 12.5% equity | validat |
| S3 BTC Both | 224 | +0.336R | 0.0075*** | -22.5% | 62.5% equity | validat |
| S4 GER40 | 61 | +0.480R | 0.045 | -31.8% | 12.5% equity | DEMO activ — train negativ, Bonferroni p=2.2 |
| S4 US30 | 74 | +0.224R | 0.165 | -15.3% | 12.5% equity | DEMO activ — train pozitiv, statistic insuficient |
| S5 GER40 H1 | ~22 | +0.6505R | 0.103 | -21.9% | 12.5% rezervat | OBSERVARE — borderline, N insuficient |
| S5 USDCHF H1 | ~31 | +0.5269R | 0.0896* | -13.7% | 12.5% rezervat | OBSERVARE — VIABLE, acumuleaza live |

S3 are cea mai puternica validare statistica (p=0.0075 one-sided t-test).
Bonferroni (11 configuratii testate): p_corr = 0.0825 — edge sustinut si de rationale economic.

S4 este in **executie demo**: 48 configuratii testate → Bonferroni factor 48 → p_corr GER40=2.2, US30=7.9.
Re-evaluare planificata: Dec 2026 (dupa ~6 luni date live + 25-30 semnale/simbol).

S5 este in **observare pura** (execute_trades=False): USDCHF validat pe 8 ani, p=0.0896*; activare cand p < 0.05 pe date live.
Date: tf_scan_targeted.py rulat 2026-06-11 dupa descarca_h1_extra.py (8 ani USDCHF, 1.4 ani USDCAD/AUDJPY/CADJPY).
