# Stare Proiect — Trading Bot Pullback-in-Trend

**Ultima actualizare:** 2026-06-08  
**Faza curentă:** Faza 2 — două sesiuni live OBSERVE pregătite și configurate

---

## 1. Scopul proiectului

Bot de trading forex care rulează o strategie de tip **pullback-in-trend** pe un portofoliu de perechi valutare, pe conturi demo MT5. Scopul final: validare forward prin OBSERVE (fără execuție reală), urmată de execuție live pe demo după confirmare statistică.

---

## 2. Strategia validată

### Principiu
1. Trend detectat pe M30 cu EMA200 (bara M15 trebuie să fie deasupra/sub EMA200 pe M30)
2. Structură HH/HL (uptrend) sau LL/LH (downtrend) cu swing-uri pe M15
3. Setup: ultima bară de retragere în fereastra PW → entry pe Buy/Sell Stop la ieșirea din retragere
4. Reward dinamic: 2.5R / 3.5R / 4.5R în funcție de criterii opționale (RSI, ATR, structură)

### Filtre active (ambele sesiuni)
| Filtru | Session 1 | Session 2 |
|---|---|---|
| Timeframe entry | M15 | M15 |
| Timeframe trend | M30 | M30 |
| Direcție | LONG only | BOTH |
| Pullback window | 8 bare | 6 bare |
| Expire setup | 4 bare M15 | 4 bare M15 |
| Skip luni | Da | Nu |
| Skip ore 15–16 | Da | Da (EUR) |
| RSI buy range | 40–65 | 40–65 |
| RSI sell range | N/A | 35–60 |
| ATR cap EURUSD | 7.5 pips | 7.5 pips |
| Corelație | EURUSD↔GBPUSD | EURUSD↔GBPUSD |
| Circuit breaker | 3 pierderi/zi | 3 pierderi/zi |
| Max pos/simbol | 1 | 1 |

---

## 3. Cele două sesiuni live

### Session 1 — S1-M15-LONG
```
Piete:     EURUSD, GBPUSD, EURJPY
Sesiune:   10:00–18:00 EET
Direcție:  LONG only
Edge:      test +0.344R | ~0.7 trades/sapt | DD -40.5%
Rulare:    python live/session1_m15_long.py
Output:    data/live_signals/session1/
```

### Session 2 — S2-M15-BOTH
```
Piete EUR: EURUSD, GBPUSD, EURJPY  → 10:00–18:00 EET
Piete JPY: USDJPY, AUDJPY, NZDJPY  → 02:00–10:00 EET (Tokyo)
Direcție:  BOTH (long + short)
Skip luni: Nu (activată — +0.6 trades/sapt, penalizare mică)
Edge:      test +0.127R | ~2.4 trades/sapt | DD -51.1%
Rulare:    python live/session2_m5_both.py
Output:    data/live_signals/session2/
```

**Cele două sesiuni sunt complet independente:** capital separat, loguri separate, fără filtre de conflict între ele.

---

## 4. Rezultatele complete ale backtestelor

### Baseline oficial Session 1 (M15 LONG, 3 piete EUR, $300, 8 ani)

| Metric | Valoare |
|---|---|
| Trades totale | 284 |
| Win Rate | 23.2% |
| Expectancy | +0.025R |
| **Test set (30%) Exp** | **+0.344R** |
| Test set trades | 103 |
| Max Drawdown | −40.5% |
| Frecvență | ~0.7/săptămână |
| Perioadă | 2018-05-22 → 2026-06-05 (8 ani) |
| Split train/test | 2024-01-09 |

### Baseline oficial Session 2 (M15 BOTH, 6 piete, $300, 8 ani)

| Metric | Valoare |
|---|---|
| Trades totale | 1022 |
| Win Rate | 22.9% |
| Expectancy | +0.029R |
| **Test set (30%) Exp** | **+0.127R** |
| Test set trades | 384 |
| Max Drawdown | −51.1% |
| Frecvență | ~2.4/săptămână |
| Split train/test | 2024-07-22 |

---

## 5. Istoricul experimentelor — tot ce a fost testat

### Timeframe-uri (2026-06-08)

| TF | Rezultat | Concluzie |
|---|---|---|
| **M15 entry + M30 trend** | WR 22–40%, TestR +0.14–+0.37R | **VALIDAT — baza strategiei** |
| M5 entry + M15 trend | WR ~16%, TestR −0.26R la −0.36R, DD −80% | **EȘUAT — excluded definitiv** |
| M1 entry + M5 trend | WR ~16%, TestR −0.12R la −0.18R, DD −82–95% | **EȘUAT — exclus definitiv** |

Concluzie: Strategia de pullback structural necesită minim M15. Sub M15, noise-ul distruge edge-ul.

### ONLY_LONG vs BOTH (2026-06-08)

| Config | TestR | T/wk | DD |
|---|---|---|---|
| M15 LONG PW=8, 3 EUR | +0.344R | 0.7 | −40.5% |
| M15 BOTH PW=4, 3 EUR | +0.255R | 1.2 | −58.5% |
| M15 BOTH PW=6, 6 piete | +0.165R | 2.6 | −51.3% |
| M15 BOTH PW=6, 6 piete, skip_mon=F | +0.142R | 3.2 | −52.9% |
| RSI sell_max=60 vs 50 | +0.134R vs +0.137R | identic | identic |

### PULLBACK_WINDOW (M15, LONG, 3 EUR)

| PW | TestR | T/wk |
|---|---|---|
| 4 | +0.214R | 1.4 |
| 6 | +0.210R | 1.6 |
| **8** | **+0.344R** | **0.7** |
| 10–16 | ~+0.180R | ~1.1 |

PW=8 rămâne optim pentru LONG. Saturare după PW=8.

### Asian session pairs (USDJPY/AUDJPY/NZDJPY, 02–10h EET)

| Config | TestR | TestN | T/wk |
|---|---|---|---|
| USDJPY LONG | +0.154R | 60 | validat |
| AUDJPY BOTH | +0.212R | 11 | prea puține date |
| NZDJPY LONG | +0.594R | 14 | prea puține date |
| ALL 6 piete BOTH PW=6 | +0.165R | 341 | 2.6 |

### Piete noi testate — individual M15 (2026-06-08)

| Simbol | TestR | Concluzie |
|---|---|---|
| EURGBP | +0.184R | Pozitiv dar 14 test trades — insuficient statistic |
| AUDUSD | −0.380R | Negativ — exclus |
| CADJPY | −0.769R | Negativ — exclus |
| CHFJPY | −0.158R | Negativ — exclus |
| GBPJPY | −0.620R | Negativ — exclus |
| USDCAD | −0.497R | Negativ — exclus |

Adăugarea de piete în portofoliu dilueaza edge-ul. Nicio piață nouă nu îmbunătățește combinatia de 6.

### Instrumente excluse (sesiunile anterioare)

| Instrument | Motiv excludere |
|---|---|
| GER40 | Edge real individual dar fals în portofoliu (swap overnight necontabilizat) |
| XAUUSD | p=0.183 nesemnificativ, necesită cont min $10k |
| US30 | TestR −0.266R |
| US500 | TestR −0.133R |
| USDJPY (portofoliu EUR) | TRAIN +0.057R / TEST −0.254R — OOS breakdown |

### SKIP_MONDAY impact (2026-06-08)

| Config | TestR | T/wk | DD |
|---|---|---|---|
| PW=6 skip_mon=True | +0.165R | 2.6 | −51.3% |
| **PW=6 skip_mon=False** | **+0.142R** | **3.2** | **−52.9%** |

Lunea adaugă 0.6 trades/săptămână cu penalizare de −0.023R. Adoptată în Session 2.

---

## 6. Arhitectura curentă

```
trading-bot/
├── backtest.py                  # entry-point single-symbol
├── portfolio_backtest.py        # entry-point multi-symbol (baseline oficial)
│
├── live/                        ← SESIUNI LIVE OBSERVE
│   ├── signal_generator.py      # engine generic (nu se rulează direct)
│   ├── session1_m15_long.py     # Session 1: M15 LONG 3 EUR piete
│   └── session2_m5_both.py      # Session 2: M15 BOTH 6 piete (EUR + JPY)
│
├── strategy/
│   ├── indicators.py            # ema(), rsi(), atr()
│   ├── structure.py             # mark_swings(), detect_setup() [fix lookahead ✓]
│   ├── signals.py               # pip_size(), count_optional(), reward_R()
│   ├── costs.py                 # swap_cost(), pip_value_usd() [fix EURGBP ✓]
│   └── preparation.py          # prepare_symbol(), prepare_symbol_tf()
│
├── engine/
│   ├── simulator.py             # simulate_trade()
│   ├── single.py                # run_symbol()
│   └── portfolio.py             # run_portfolio() — multi-pos, margin, corr, CB
│
├── adapters/
│   ├── csv_source.py            # CsvDataSource — backtest din CSV
│   └── mt5_source.py            # Mt5DataSource — live MT5, DEMO guard
│
├── config/
│   └── standard_profile.json   # profil validat
│
├── data/
│   ├── *_M15.csv, *_M30.csv    # date istorice OHLC
│   ├── *_M5.csv                 # M5 pentru 12 perechi (descărcate, nu folosite în prod)
│   └── live_signals/
│       ├── session1/            # signals.csv, outcomes.csv, state.pkl, generator.log
│       └── session2/            # idem
│
├── scripts/
│   ├── descarca_date.py         # descarca OHLC din MT5 → CSV
│   ├── analiza_observe.py       # analiza rezultate sesiuni OBSERVE
│   ├── compare_live_vs_backtest.py
│   ├── test_conexiune_mt5.py
│   ├── verifica_aliniere_mt5.py
│   └── research/                # scripturi de cercetare (nu pentru productie)
│       ├── test_suite.py
│       ├── extra_symbols_test.py
│       ├── asian_session_test.py
│       ├── m1_test.py
│       ├── session2_optimize.py
│       ├── descarca_m1.py
│       └── descarca_m5_extra.py
│
└── docs/
    ├── STARE_PROIECT.md         # acest fișier
    └── SESIUNI_LIVE.md          # ghid complet sesiuni OBSERVE
```

---

## 7. Cum se rulează

```bash
# Backtest portofoliu baseline (EURUSD + GBPUSD + EURJPY, ONLY_LONG)
python portfolio_backtest.py

# Session 1 — live OBSERVE (MT5 deschis pe DEMO)
python live/session1_m15_long.py

# Session 2 — live OBSERVE (MT5 deschis pe DEMO)
python live/session2_m5_both.py

# Analiza rezultate sesiuni OBSERVE (dupa acumulare date)
python scripts/analiza_observe.py
python scripts/analiza_observe.py --session session1
python scripts/analiza_observe.py --session session2

# Descarca date istorice
python scripts/descarca_date.py
```

---

## 8. Regula de aur — baseline oficial

**Orice modificare la strategie sau motor trebuie să reproducă:**

```
python portfolio_backtest.py   (Session 1)
→ EURUSD+GBPUSD+EURJPY, ONLY_LONG, $300, M15+M30, 8 ani:
  284 trades, Exp +0.025R, DD -40.5%
  TRAIN (181t): -0.156R  |  TEST (103t): +0.344R  |  Split: 2024-01-09

python session2_backtest.py    (Session 2)
→ 6 piete EUR+JPY, BOTH, $300, M15+M30, skip_mon=False:
  1022 trades, Exp +0.029R, DD -51.1%
  TRAIN (638t): -0.030R  |  TEST (384t): +0.127R  |  Split: 2024-07-22
```

Dacă numerele se schimbă semnificativ — bug introdus, nu continuare.

---

## 9. Criterii pentru trecerea la execuție reală

Ambele condiții trebuie îndeplinite:

1. **Minimum 30 trades închise** (TP sau SL, nu expirate/invalidate) în outcomes.csv
2. **Expectancy live ≥ 0.0R** și **în intervalul ±0.15R față de backtest**

Session 2 va atinge 30 trades în ~13 săptămâni (~3 luni, la 2.4/wk).  
Session 1 va atinge 30 trades în ~43 săptămâni (~10 luni, la 0.7/wk).

---

## 10. Fix-uri critice implementate

### Fix 1 — Lookahead bias în `detect_setup`
`mark_swings` folosea fereastră simetrică → bara j citea swinguri confirmate de bare viitoare.  
**Fix:** `look = df.iloc[a : j - swing_n + 1]` — ultimul swing utilizabil: k=j−3.

### Fix 2 — `pip_value_usd` pentru cross-uri quote non-USD
EURGBP cădea pe fallback greșit (~8% eroare).  
**Fix:** `val_in_quote * BASE_USD_APROX[quote]` — EURGBP: 10 GBP × 1.27 = $12.70/pip.

### Fix 3 — Session 2: M5→M15 entry
Session 2 a fost inițial proiectată cu M5 entry. Backtestele au confirmat M5 eșuat (WR=16%, DD−80%).  
**Fix:** Session 2 folosește M15 entry + M30 trend, identic cu Session 1.
