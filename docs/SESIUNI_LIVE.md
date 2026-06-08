# Sesiuni Live OBSERVE — Ghid Complet

**Ultima actualizare:** 2026-06-08  
**Stare:** Pregătite pentru rulare OBSERVE (forward test fără execuție reală)

---

## 1. Arhitectura — două sesiuni complet separate

Botul rulează două sesiuni independente, fără niciun filtru comun și fără capital partajat:

| | Session 1 | Session 2 |
|---|---|---|
| **Fișier** | `live/session1_m15_long.py` | `live/session2_m5_both.py` |
| **ID** | S1-M15-LONG | S2-M15-BOTH |
| **Timeframe** | M15 entry + M30 trend | M15 entry + M30 trend |
| **Direcție** | LONG only | BOTH (long + short) |
| **Piețe** | EURUSD, GBPUSD, EURJPY | EURUSD, GBPUSD, EURJPY + USDJPY, AUDJPY, NZDJPY |
| **PW** | 8 | 6 |
| **Skip luni** | Da | Nu |
| **Sesiune** | 10–18h EET (toate) | EUR: 10–18h / JPY: 02–10h |
| **Frecvență așteptată** | ~0.9/săptămână | ~3.2/săptămână |
| **Expectancy test** | +0.375R | +0.142R |
| **Max DD backtest** | −50.6% | −52.9% |
| **Output** | `data/live_signals/session1/` | `data/live_signals/session2/` |

---

## 2. Configurațiile complete cu toate filtrele

### Session 1 — S1-M15-LONG
```
Piete:       EURUSD, GBPUSD, EURJPY
TF entry:    M15   (bara de 15 minute)
TF trend:    M30   (EMA200 — determina directia)
Directie:    LONG only (BUY stop)
PW:          8 bare M15 (2 ore)
Expire:      4 bare M15 fara trigger = semnal expirat
Sesiune:     10:00–18:00 EET
Skip luni:   DA
Skip ore:    15:00–16:00 EET
RSI buy:     40–65
Reward:      2.5R / 3.5R / 4.5R (criterii optionale)
Corelatie:   EURUSD + GBPUSD nu simultan
CB:          3 pierderi consecutive/zi
```

### Session 2 — S2-M15-BOTH
```
Piete EUR:   EURUSD, GBPUSD, EURJPY   → sesiune 10:00–18:00 EET
Piete JPY:   USDJPY, AUDJPY, NZDJPY   → sesiune 02:00–10:00 EET (Tokyo)
TF entry:    M15
TF trend:    M30
Directie:    BOTH (BUY stop + SELL stop)
PW:          6 bare M15 (1h30min)
Expire:      4 bare M15 fara trigger = semnal expirat
Skip luni:   NU (lunea activă — +0.6 trades/sapt)
Skip ore:    15:00–16:00 EET (EUR only, relevant)
RSI buy:     40–65  |  RSI sell: 35–60
Reward:      2.5R / 3.5R / 4.5R
```

---

## 3. Fișiere output per sesiune

Fiecare sesiune scrie în directorul său propriu:

```
data/live_signals/
├── session1/
│   ├── signals.csv       ← toate semnalele generate (un rând per semnal)
│   ├── outcomes.csv      ← rezultatele: TP / SL / expirat / invalidat
│   ├── state.pkl         ← stare persistenta (semnale pendinge, contoare)
│   └── generator.log     ← log text complet cu timestamp
└── session2/
    └── (aceleași fișiere)
```

### Format signals.csv
| Coloană | Descriere |
|---|---|
| `signal_id` | ID unic: `S1-M15-LONG-SIG0001` |
| `time` | Timestamp bara de semnal (EET) |
| `symbol` | Simbolul (ex: EURUSD) |
| `direction` | 1=LONG, -1=SHORT |
| `dir_str` | "LONG" / "SHORT" |
| `entry` | Prețul de intrare (Buy/Sell Stop) |
| `sl` | Stop Loss |
| `tp` | Take Profit |
| `r_ratio` | Reward ratio (2.5 / 3.5 / 4.5) |
| `atr_pips` | ATR la momentul semnalului |
| `n_optional` | Număr criterii opționale îndeplinite |
| `rsi` | RSI la momentul semnalului |

### Format outcomes.csv
| Coloană | Descriere |
|---|---|
| `signal_id` | Referință la signals.csv |
| `status` | `TP` / `SL` / `expirat` / `invalidat` |
| `result_r` | Rezultat în R (+2.5 / +3.5 / +4.5 / -1.0 / 0.0) |
| `exit_price` | Prețul de ieșire (la TP/SL) |
| `exit_time` | Timestamp ieșire |
| `triggered_at` | Când a intrat ordinul stop (buy/sell stop activat) |

---

## 4. Cum se pornesc

**Condiție prealabilă:** MT5 desktop deschis și logat pe contul DEMO.

```bash
# Terminal 1 — Session 1 (M15, LONG, EUR pairs)
python live/session1_m15_long.py

# Terminal 2 — Session 2 (M15, BOTH, EUR + JPY pairs)
python live/session2_m5_both.py

# Oprire: Ctrl+C în fiecare terminal
# La Ctrl+C se afișează automat sumarul sesiunii curente
```

**Comportament la pornire:**
- Se conectează la MT5 (verifică că e DEMO, nu LIVE)
- Încarcă 2000 bare M15 + 1000 bare M30 per simbol
- Restabilește starea din `state.pkl` (dacă există din sesiunea anterioară)
- Intră în buclă: verifică la fiecare bară M15 închisă (~15 min)

**Comportament la repornire:** Starea (semnale pendinge, contoare) se restaurează automat din `state.pkl`. Nu se pierd semnale între reporniri.

---

## 5. Cum se citesc log-urile în timp real

```
2026-06-08 10:15:05  --- S1-M15-LONG iter 1 @ 10:15:05 ---
2026-06-08 10:15:06  Niciun semnal nou. Pendinge: 0
2026-06-08 10:15:06  Urmatoarea bara 15min @ 10:30:05 — 899s

2026-06-08 10:30:06  --- S1-M15-LONG iter 2 @ 10:30:06 ---
2026-06-08 10:30:07  *** SEMNAL: S1-M15-LONG-SIG0001 EURUSD LONG entry=1.08450 sl=1.08200 tp=1.09200 (3.5R) RSI=52
2026-06-08 10:30:07  Urmatoarea bara 15min @ 10:45:05 — 898s

2026-06-08 10:45:06  --- S1-M15-LONG iter 3 ---
2026-06-08 10:45:07  TRIGGERAT: S1-M15-LONG-SIG0001 EURUSD LONG @ 1.08450
2026-06-08 10:45:07  Niciun semnal nou. Pendinge: 1
```

**Statusuri posibile:**
- `*** SEMNAL:` — setup nou detectat, scris în signals.csv
- `TRIGGERAT:` — ordinul stop a fost activat
- `PROFIT: ... TP +3.5R` — trade câștigat
- `PIERDERE: ... SL -1.0R` — trade pierdut
- `EXPIRAT:` — setup nu a triggereat în 4 bare M15 (1 oră)
- `INVALIDAT:` — SL atins înainte de trigger (bara a mers direct în SL)

---

## 6. Când putem compara datele cu backtestul

### Minimum statistic necesar: **30 trades închise** (TP sau SL)

| Sesiune | Frecvență | Timp estimat pentru 30 trades |
|---|---|---|
| Session 1 | 0.9/săpt | ~33 săptămâni (~8 luni) |
| Session 2 | 3.2/săpt | ~9–10 săptămâni (~2.5 luni) |

**Notă:** Un "trade închis" = un semnal care a atins TP sau SL (nu expirat/invalidat).  
Semnalele expirate și invalidate NU contează în comparația cu backtestul (backtestul nu le include).

### Interpretare anticipată:

**La 15–20 trades:** Prea devreme pentru concluzie, dar poți vedea dacă WR este complet în afara așteptărilor (sub 15% sau peste 60% ar fi alarme).

**La 30 trades:** Prima comparație validă. Dacă expectancy live este în intervalul `±0.15R` față de backtest, sesiunea este în linie.

**La 60+ trades:** Concluzie solidă. Dacă expectancy se menține ≥ 0.0R, sesiunea se confirmă.

---

## 7. Cum se rulează analiza

```bash
# Analiza ambelor sesiuni simultan
python scripts/analiza_observe.py

# Doar Session 1
python scripts/analiza_observe.py --session session1

# Doar Session 2
python scripts/analiza_observe.py --session session2
```

Output exemplu:
```
  ANALIZA OBSERVE — Session 1  (data/live_signals/session1)
  ====================================================================
  SEMNALE GENERATE: 42
  Perioada:  2026-06-10 — 2026-09-15  (97 zile / 13.9 sapt)
  Frecventa: 3.0 semnale/sapt  [backtest: 0.9/wk]

  PERFORMANTA (pe 31 trades inchise):
    Win Rate:    38.7%      [backtest: 40.0%]
    Expectancy:  +0.312R    [backtest: +0.375R]
    Drawdown:    -22.1%     [backtest: -50.6%]
    W:12  L:19

  COMPARATIE CU BACKTESTUL:
    Expectancy: live=+0.312R vs backtest=+0.375R  (diff=-0.063R)  → IN LINIE
    Win Rate:   live=38.7% vs backtest=40.0%  (diff=-1.3pp)
```

---

## 8. Ce facem cu rezultatele

### Dacă sesiunea e "în linie" cu backtestul (diff expectancy < ±0.15R):
→ Continuăm OBSERVE minim 60 trade-uri totale, apoi decidem dacă pornim execuție reală.

### Dacă sesiunea e semnificativ sub backtest (diff < −0.20R pe 30+ trades):
→ Investigăm: verificăm că sesiunile sunt corecte, că timezone-ul MT5 e aliniat, că spread-urile reale nu sunt mult mai mari decât estimatele.

### Dacă sesiunea e semnificativ peste backtest (diff > +0.20R):
→ Posibil noroc pe eșantion mic. Continuăm până la 60 trades.

---

## 9. Referințe backtest

### Session 1 — S1-M15-LONG (validat 2026-06-08)
```
Config: EURUSD + GBPUSD + EURJPY, M15 entry, M30 trend, LONG, PW=8
Backtest complet: 1096 trades, WR=22.7%, Exp=+0.048R
TEST set (30%):   341 trades, WR=?, Exp=+0.375R, DD=-50.6%
Frecventa:        0.9 trades/saptamana
```

### Session 2 — S2-M15-BOTH (validat 2026-06-08)
```
Config: 6 piete (EUR+JPY), M15 entry, M30 trend, BOTH, PW=6, skip_mon=False
Backtest complet: 1353 trades, WR=22.2%, Exp=+0.030R
TEST set (30%):   435 trades, WR=?, Exp=+0.142R, DD=-52.9%
Frecventa:        3.2 trades/saptamana
```

**Note importante:**
- AUDJPY și NZDJPY: swap-urile sunt **estimate** — verifică în MT5 înainte de execuție reală
- Session 2 include USDJPY pe sesiune Tokyo (02–10h EET), validat individual cu +0.154R test
- M5 și M1 au fost testate și excluse definitiv (WR~16%, TestR negativ, DD −80–95%)
