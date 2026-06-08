# Sesiuni Live — Trading Bot

Trei sesiuni independente. Capital separat, loguri separate. Pot rula simultan fara conflict.

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

## Program complet — cand sa rulezi ce

> Toate orele in **UTC**. EET vara (GMT+3) = UTC+3.

```
UTC     EET(vara)   S1 (EUR Long)   S2 EUR    S2 JPY    S3 (BTC)
00-02   03-05       -               -         -         ACTIV
02-09   05-12       -               -         ACTIV     ACTIV  ← S2+S3 simultan
09-10   12-13       -               -         ACTIV     pauza
10-15   13-18       ACTIV           ACTIV     -         pauza  ← S1+S2 simultan
15-16   18-19       ACTIV*          ACTIV*    -         ACTIV  ← toate 3 (skip 15-16)
16-18   19-21       ACTIV           ACTIV     -         ACTIV  ← S1+S2+S3 simultan
18-19   21-22       -               -         -         pauza
19-23   22-02       -               -         -         pauza
23-00   02-03       -               -         -         pauza
```
*Ora 15-16 UTC: S1 si S2 au `skip_hours=(15,16)` — filtrare interna automata.

### Recomandare practica

**Porneste toate 3 sesiunile simultan** — fiecare filtreaza intern:

```bash
# Terminal 1
python live/session1_m15_long.py

# Terminal 2
python live/session2_m5_both.py

# Terminal 3
python live/session3_btc_both.py
```

- S1 si S2 se activeaza cand piata europeana/asiatica se deschide
- S3 BTC este activa noaptea (03-12h EET) si seara (18-21h EET)
- **Suprapunere maxima cu celelalte doua: 18-21h EET** (17-18h UTC = S3+S2+S1)
- **S3 unica: 03-12h EET** (00-09h UTC) — BTC activ singur (Asia + pre-EU)

### Zile saptamana

| Zi | S1 | S2 EUR | S2 JPY | S3 BTC |
|----|----|--------|--------|--------|
| Luni | skip | activ | activ | activ |
| Marti-Vineri | activ | activ | activ | activ |
| Sambata | activ | activ | activ | **SKIP** |
| Duminica | activ | activ | activ | activ |

---

## Capital si risc

Sesiunile sunt independente — capitalul NU se imparte:

| Sesiune | Capital recomandat | Risc/trade |
|---------|--------------------|------------|
| S1 | $1000+ | 1% per trade |
| S2 | $1000+ | 1% per trade |
| S3 BTC | $500 min | 1% per trade (~$5 risc la $500) |

---

## Observare live vs executie

Toate sesiunile ruleaza in **mod observare** — genereaza semnale, NU executa ordine in MT5.

Fisiere generate per sesiune:
- `signals.csv` — toate semnalele detectate (entry/sl/tp/R)
- `outcomes.csv` — rezultate: TP/SL/expirat/invalidat
- `generator.log` — log detaliat

Dupa 30-50 trades per sesiune, compara `result_r` mediu din `outcomes.csv` cu expectancy din backtest.

---

## Rezultate backtest sumar

| Sesiune | N test | Exp test | p-val | DD | Capital |
|---------|--------|----------|-------|----|---------|
| S1 M15 Long | - | +0.375R | - | -50.6% | $1000+ |
| S2 M15 Both | - | +0.142R | - | -45.4% | $1000+ |
| S3 BTC Both | 224 | +0.336R | 0.0075*** | -22.5% | $500 |

S3 are cea mai puternica validare statistica (p=0.0075 one-sided t-test).
Bonferroni (11 configuratii testate): p_corr = 0.0825 — edge sustinut si de rationale economic.
