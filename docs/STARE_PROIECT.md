# Stare Proiect — Trading Bot Pullback-in-Trend

**Ultima actualizare:** 2026-06-05  
**Faza curentă:** Faza 1, Pasul 1 complet ✓ — Mt5DataSource implementat + timezone confirmat

---

## 1. Scopul proiectului

Bot de trading forex care rulează o strategie de tip **pullback-in-trend** pe un portofoliu de 3 perechi (EURUSD, GBPUSD, USDJPY), pe un cont comun simulat. Scopul final: același motor validat să ruleze și live pe demo MT5, fără rescriere de logică.

---

## 2. Strategia validată

| Parametru | Valoare |
|---|---|
| Timeframe trend | M30, EMA200 |
| Timeframe intrare | M15, structură HH/HL |
| Tipul ordinului | Buy/Sell Stop |
| Fereastra pullback | 8 bare M15 (2 ore) |
| Scara reward | 2.5R / 3.5R / 4.5R (funcție de criterii opționale) |
| Risc per trade | 1.0% (standard) / 1.2% (toate criteriile) |
| RSI buy range | 40–65 |
| RSI sell range | 35–50 |
| Spread EURUSD | 0.5 pips |
| Spread GBPUSD | 0.8 pips |
| Spread USDJPY | 0.7 pips |
| Comision | 7.0 USD/lot round-turn |
| Sesiune activă | 10:00–18:00 |
| Skip luni | Da |
| Skip ore | 15:00–16:00 |
| ATR cap | EURUSD 7.5 pips |

---

## 3. Rezultate baseline (confirmate, neschimbate prin refactorizare)

### Portofoliu (cont comun, $1000 start)

| Metric | Valoare |
|---|---|
| Balantă finală | $2,726.97 |
| Randament total | +172.7% |
| Tranzacții | 470 (W: 124 / L: 338) |
| Rata de câștig | 26.4% |
| Expectancy | +0.212 R |
| Drawdown maxim | −28.9% |
| Swap total plătit | ~401 USD |
| Circuit breaker | 7 zile halted |

### Per pereche

| Simbol | Trades | Win% | Expectancy | PnL |
|---|---|---|---|---|
| EURUSD | 111 | 27.9% | +0.254 R | +509.6 USD |
| GBPUSD | 145 | 26.2% | +0.267 R | +772.8 USD |
| USDJPY | 214 | 25.7% | +0.153 R | +444.5 USD |

### Single-symbol (backtest.py, $1000 start, EURUSD+GBPUSD)

| Simbol | Trades | Win% | Expectancy | Drawdown |
|---|---|---|---|---|
| EURUSD | 233 | — | +0.084 R | −23.0% |
| GBPUSD | 244 | — | +0.113 R | −14.6% |

---

## 4. Arhitectura curentă (Faza 0 completă)

```
trading-bot/
├── backtest.py                  # entry-point single-symbol
├── portfolio_backtest.py        # entry-point multi-symbol / cont comun
│
├── strategy/                    # logica pura, fara I/O
│   ├── indicators.py            # ema(), rsi(), atr()
│   ├── structure.py             # mark_swings(), detect_setup()
│   ├── signals.py               # pip_size(), count_optional(), reward_R()
│   ├── costs.py                 # swap_cost(), pip_value_usd(), notional_usd()
│   └── preparation.py          # prepare_symbol() — indicatori calculati o singura data
│
├── engine/                      # simulare pura, fara I/O
│   ├── simulator.py             # simulate_trade() — walk-forward bar cu bar
│   ├── single.py                # run_symbol() — loop single-symbol
│   └── portfolio.py             # run_portfolio() — loop portofoliu, margin, corr, CB
│
├── ports/
│   └── data_source.py           # DataSource Protocol (contract abstract)
│
├── adapters/
│   ├── csv_source.py            # CsvDataSource — backtest din CSV
│   └── mt5_source.py           # Mt5DataSource — stub pentru live (Faza 1)
│
├── config/
│   └── standard_profile.json   # profil validat (nu modifica fara test de regresie)
│
├── data/                        # CSV-uri OHLC + CSV-uri trades/equity output
│
└── scripts/
    ├── descarca_date_istorice.py
    └── test_conexiune_mt5.py
```

### Principiul arhitectural cheie

```
Adaptor  →  load_bars() → OHLC brut
                ↓
         preparation.py → indicatori (EMA, RSI, ATR, swings, trend M30)
                ↓
         engine/  →  simulare / execuție
```

Adaptorul livrează **doar bare brute OHLC**. Toți indicatorii se calculează în `strategy/preparation.py` — o singură dată, identic, indiferent de sursă (CSV sau MT5). Adăugarea unui adaptor nou nu necesită modificarea motorului.

---

## 5. Filtre de portofoliu implementate

| Filtru | Detalii |
|---|---|
| **Margin check** | Verifică fonduri înainte de fiecare intrare |
| **Filtru corelație** | EURUSD + GBPUSD: nu intră simultan în aceeași direcție |
| **Circuit breaker** | Stop trading după 3 pierderi consecutive în aceeași zi |
| **Swap cost** | Modelat per noapte, miercuri = triple |
| **ATR cap** | EURUSD: max 7.5 pips volatilitate |
| **Skip luni** | Prima zi a săptămânii excludă |
| **Skip ore 15–16** | Zona de volatilitate ridicată excludă |

---

## 6. Experimente efectuate și concluzii

| Experiment | Rezultat | Decizie |
|---|---|---|
| **Breakeven stop la +1R** | 37% din trades devin BE, expectancy scade | **Revert** — incompatibil cu target-uri 2.5–4.5R |
| **RSI sell range 30–50** | Fără îmbunătățire semnificativă | **Revert** la 35–50 |
| **Pullback window 6 bare** | Rezultate mai slabe | **Revert** la 8 |
| **Pullback window 10 bare** | Rezultate mai slabe | **Revert** la 8 |
| **Filtru corelație EURUSD/GBPUSD** | Reduce supraexpunerea, DD ușor îmbunătățit | **Păstrat** |

---

## 7. Faza 1 — implementare live MT5

### Pasul 1 — COMPLET ✓ (2026-06-05)

**Implementat:**
- `adapters/mt5_source.py` — `Mt5DataSource` cu `load_bars()`, guard DEMO obligatoriu, context manager
- `scripts/verifica_aliniere_mt5.py` — script de verificare OHLC + timezone

**Concluzii verificare (rulat live pe ICMarkets EU Demo):**

| Verificare | Rezultat |
|---|---|
| OHLC match EURUSD M15/M30 | ✓ perfect (1 bara diferita = bara in formare la download CSV — normal) |
| OHLC match GBPUSD M15/M30 | ✓ idem |
| OHLC match USDJPY M15/M30 | ✓ MATCH PERFECT pe toate barele |
| Timezone timestamps MT5 | **UTC+3 (ICMarkets server time = ora României vara EEST)** |

**Detaliu timezone — critic pentru filtre:**

Timestamps din MT5 (via `copy_rates_from_pos`) sunt în **UTC+3** (ora serverului ICMarkets), nu UTC.
ICMarkets menține UTC+3 tot anul. România vara este EEST = UTC+3, deci:

- `t.hour in {15, 16}` → skip 15:00–16:00 **ora României vara** ✓ corect
- `sh <= t.hour < eh` (10–18) → sesiunea 10:00–18:00 **ora României vara** ✓ corect
- `t.weekday() == 0` → skip Luni in ora ICMarkets (= ora RO) ✓ corect

Iarna (EET = UTC+2), ICMarkets rămâne pe UTC+3, deci filtrele funcționează identic tot anul — nu există deviere sezonieră.

**Test definitiv:** ultima bara M15 (17:00 naive) − UTC curent (14:15) = +164 min ≈ UTC+3 (16 min diferenta = bara rulase 15 min din durata ei de 15 min la momentul testului).

### Pasul 2 — urmează

Scrie `live_runner.py`: `Mt5DataSource` + `prepare_symbol` + bucla de semnale fara executie (doar log setup-uri detectate).

**Ce NU trebuie modificat:**
- `strategy/` — zero modificări
- `engine/` — zero modificări
- `config/standard_profile.json` — zero modificări fără test de regresie

---

## 8. Cum se rulează

```bash
# Backtest single-symbol (EURUSD + GBPUSD)
python backtest.py

# Backtest portofoliu (EURUSD + GBPUSD + USDJPY)
python portfolio_backtest.py
```

Output-ul se salvează în `data/`: `trades_EURUSD.csv`, `portfolio_trades.csv`, `portfolio_equity.csv` etc.

---

## 9. Regula de aur — test de regresie

**Orice modificare la strategie sau motor trebuie să treacă testul de regresie:**

```
Portfolio: 1000 → 2726.97 USD (+172.7%), 470 trades, expectancy +0.212 R, DD -28.9%
EURUSD:    111 trades, +0.254 R
GBPUSD:    145 trades, +0.267 R
USDJPY:    214 trades, +0.153 R
```

Dacă numerele se schimbă — bug introdus, nu continuare.
