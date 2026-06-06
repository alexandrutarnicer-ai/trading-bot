# Stare Proiect — Trading Bot Pullback-in-Trend

**Ultima actualizare:** 2026-06-06  
**Faza curentă:** Faza 1, Pasul 3 complet ✓ — baseline oficial validat, live_runner aliniat, script comparatie gata

---

## 1. Scopul proiectului

Bot de trading forex care rulează o strategie de tip **pullback-in-trend** pe un portofoliu de 3 perechi (EURUSD, GBPUSD, EURJPY), pe un cont comun simulat. Scopul final: același motor validat să ruleze și live pe demo MT5, fără rescriere de logică.

---

## 2. Strategia validată (baseline oficial)

| Parametru | Valoare |
|---|---|
| Timeframe trend | M30, EMA200 |
| Timeframe intrare | M15, structură HH/HL |
| Tipul ordinului | Buy Stop (ONLY_LONG=True) |
| Fereastra pullback | 8 bare M15 (2 ore) |
| Scara reward | 2.5R / 3.5R / 4.5R (funcție de criterii opționale) |
| Risc per trade | 1.0% (standard) / 1.2% (toate criteriile) |
| RSI buy range | 40–65 |
| Spread EURUSD | 0.5 pips |
| Spread GBPUSD | 0.8 pips |
| Spread EURJPY | 1.5 pips |
| Comision | 7.0 USD/lot round-turn |
| Sesiune activă | 10:00–18:00 ora României |
| Skip luni | Da |
| Skip ore | 15:00–16:00 |
| ATR cap | EURUSD 7.5 pips (validat pe train/test); EURJPY fără cap |
| ONLY_LONG | True — doar BUY |
| Max pozitii/pereche | 1 |
| Filtru corelatie | EURUSD ↔ GBPUSD: nu intră simultan |
| Circuit breaker | Stop după 3 pierderi consecutive/zi |

---

## 3. Baseline oficial (post-fix lookahead, post-optimizare)

> **ATENTIE:** Numerele din versiunile anterioare ale acestui doc (Faza 0: +172.7%, 470 trades)
> erau inflate de lookahead bias în `detect_setup`. Valorile de mai jos sunt reale.

### Portofoliu (EURUSD + GBPUSD + EURJPY, $1000 start, ONLY_LONG)

| Metric | Valoare |
|---|---|
| Balanță finală | **$1,588.18** |
| Randament total | **+58.8%** |
| Tranzacții | **114** (W:35 / L:78) |
| Win rate | **30.7%** |
| Expectancy | **+0.400 R** |
| Drawdown maxim | **−13.4%** |
| Swap total plătit | ~84 USD |
| Circuit breaker | 0 zile halted |
| Max simultan | 2 (perechi diferite) |

### Train / Test split (split la 2025-09-15, 70/30 cronologic)

| Set | Trades | Win% | Expectancy |
|---|---|---|---|
| TRAIN (primele 70%) | 86 | 27.9% | +0.287 R |
| TEST (ultimele 30%) | 28 | 39.3% | +0.748 R |

### Per pereche

| Simbol | Trades | Win% | Expectancy | PnL |
|---|---|---|---|---|
| EURUSD | 24 | 41.7% | +0.824 R | +259.9 USD |
| GBPUSD | 28 | 28.6% | +0.372 R | +130.2 USD |
| EURJPY | 62 | 27.4% | +0.249 R | +198.1 USD |

---

## 4. Fix-uri critice implementate

### Fix 1 — Lookahead bias în `detect_setup` (`strategy/structure.py`)

**Problema:** `mark_swings` foloseşte fereastră simetrică N=3 (k-N .. k+N). La bara j,
`detect_setup` citea swinguri la k=j-1 şi k=j-2, a căror confirmare necesita barele j+1, j+2
(date din viitor la momentul deciziei).

**Fix:** `look = df.iloc[a : j - swing_n + 1]` în loc de `df.iloc[a:j]`.
Ultimul swing utilizabil: `k = j-3`, fereastră de confirmare `[j-6:j-1]` — exclusiv bare deja închise.

**Consecinţă:** Barele j-1 şi j-2 (confirmarea lor depinde de bare viitoare) sunt excluse.
Fix transparent pentru toţi apelantii (`engine`, `live_runner`) prin `swing_n=3` default.

**Garanţie re-detectie:** Swing-urile folosite la bara j sunt determinate exclusiv de bare
imutabile → `compare_live_vs_backtest.py` garantat 0 nepotriviri din această sursă.

### Fix 2 — `pip_value_usd` pentru cross-uri cu quote non-JPY/USD (`strategy/costs.py`)

**Problema:** EURGBP (quote=GBP) cădea pe fallback `val_in_quote / price` (~8% eroare).

**Fix:** Dacă `quote in BASE_USD_APROX`, returnează `val_in_quote * BASE_USD_APROX[quote]`.
EURGBP: 10 GBP × 1.27 = **$12.70/pip** (corect), în loc de 10/0.86 = $11.63.

---

## 5. Experimente efectuate și concluzii

### Sesiunea de optimizare portofoliu (2026-06-06)

| Experiment | Rezultat | Decizie |
|---|---|---|
| **USDJPY în portofoliu** | TRAIN +0.057R / TEST −0.254R — OOS breakdown clar | **Eliminat** |
| **ONLY_LONG=True** | EURUSD BUY +0.84R vs SELL +0.11R; GBPUSD BUY +0.48R vs SELL −0.13R | **Activat** |
| **EURJPY individual** | 62t, +0.246R global, TRAIN +0.170R / TEST +0.404R — edge real | **Adăugat** |
| **ATR cap EURJPY 15.6** | p75 pe date întregi (OOS contaminat); TEST mai prost (+0.357 vs +0.404) | **Eliminat** |
| **ATR cap GBPUSD 9.9** | Eliminat de linter după commit; GBPUSD funcționează fără cap | **Absent** |
| **max_pos=2 (fără delay)** | +20 trades extra la −0.292R/trade, DD −19.1% vs −11.6% | **Rejectat** |
| **max_pos=2, delay 30min** | +17 extra la −0.219R, DD −17.2% | **Rejectat** |
| **max_pos=2, delay 1h** | +16 extra la −0.173R, DD −17.2% | **Rejectat** |
| **max_pos=3, delay 2h** | +15 extra la −0.264R — mai rău decât delay 1h | **Rejectat** |

### Testare perechi noi (13 simboluri, individual, ONLY_LONG)

Singura pereche nouă cu edge real confirmat pe ambele seturi:

| Pereche | Trades | Exp global | Train R | Test R |
|---|---|---|---|---|
| **EURJPY** ✓ | 62 | +0.246 | +0.170 | +0.404 |
| NZDUSD | 32 | +0.079 | +0.548 | −1.120 (OOS break) |
| CHFJPY | 57 | −0.186 | −0.298 | +0.076 |
| Restul 10 | — | negativ | negativ | — |

### Experimente anterioare (reținute din Faza 0)

| Experiment | Rezultat | Decizie |
|---|---|---|
| **Breakeven stop la +1R** | 37% trades BE, expectancy scade | **Revert** |
| **RSI sell range 30–50** | Fără îmbunătățire | **Revert** la 35–50 |
| **Pullback window 6 bare** | Mai slab | **Revert** la 8 |
| **Pullback window 10 bare** | Mai slab | **Revert** la 8 |

---

## 6. Arhitectura curentă

```
trading-bot/
├── backtest.py                  # entry-point single-symbol (backtest)
├── portfolio_backtest.py        # entry-point multi-symbol / cont comun ← BASELINE OFICIAL
├── live_runner.py               # entry-point live demo MT5 — mod OBSERVE ✓ (Faza 1)
│
├── strategy/                    # logica pura, fara I/O
│   ├── indicators.py            # ema(), rsi(), atr()
│   ├── structure.py             # mark_swings(), detect_setup() — FIX LOOKAHEAD ✓
│   ├── signals.py               # pip_size(), count_optional(), reward_R()
│   ├── costs.py                 # swap_cost(), pip_value_usd() — FIX EURGBP ✓, notional_usd()
│   └── preparation.py          # prepare_symbol() — indicatori calculati o singura data
│
├── engine/                      # simulare pura, fara I/O
│   ├── simulator.py             # simulate_trade() — walk-forward bar cu bar
│   ├── single.py                # run_symbol() — loop single-symbol
│   └── portfolio.py             # run_portfolio() — multi-pos support, margin, corr, CB
│
├── ports/
│   └── data_source.py           # DataSource Protocol (contract abstract)
│
├── adapters/
│   ├── csv_source.py            # CsvDataSource — backtest din CSV
│   └── mt5_source.py            # Mt5DataSource — live MT5, DEMO guard, conv. Europe/Bucharest
│
├── config/
│   └── standard_profile.json   # profil validat (nu modifica fara test de regresie)
│
├── data/
│   ├── EURUSD_M15.csv etc.      # CSV-uri OHLC (2024-01 pana 2026-06)
│   ├── portfolio_trades.csv     # output backtest curent
│   ├── portfolio_equity.csv     # curba equity
│   └── live_signals/            # log CSV ciclu cu ciclu din live_runner.py
│
└── scripts/
    ├── descarca_date.py              # descarca OHLC din MT5 → CSV
    ├── compare_live_vs_backtest.py   # Faza1 Pas3: verifica fidelitate live vs backtest ✓
    ├── test_conexiune_mt5.py
    └── verifica_aliniere_mt5.py     # verifica OHLC + timezone MT5 vs CSV
```

### Principiul arhitectural cheie

```
Adaptor  →  load_bars() → OHLC brut
                ↓
         preparation.py → indicatori (EMA, RSI, ATR, swings, trend M30)
                ↓
         engine/  →  simulare / execuție
```

Adaptorul livrează **doar bare brute OHLC**. Toți indicatorii se calculează în
`strategy/preparation.py` — o singură dată, identic, indiferent de sursă (CSV sau MT5).

---

## 7. Filtre de portofoliu implementate

| Filtru | Detalii |
|---|---|
| **ONLY_LONG** | Doar direcția 1 (BUY); SELL ignorat complet |
| **Margin check** | Verifică fonduri înainte de fiecare intrare |
| **Filtru corelație** | EURUSD + GBPUSD: nu intră simultan în aceeași direcție |
| **Circuit breaker** | Stop trading după 3 pierderi consecutive în aceeași zi |
| **Swap cost** | Modelat per noapte, miercuri = triple |
| **ATR cap** | EURUSD: max 7.5 pips (validat train/test); celelalte: fără cap |
| **Skip luni** | Prima zi a săptămânii exclusă |
| **Skip ore 15–16** | Zona de volatilitate ridicată exclusă |
| **max_pos_per_symbol** | Max 1 poziție per pereche (parametru configurabil, testul cu 2 a eșuat) |
| **min_bars_between** | Delay configurabil între pozitii pe aceeasi pereche (activ la 0) |

---

## 8. Faza 1 — implementare live MT5

### Pasul 1 — COMPLET ✓ (2026-06-05)

- `adapters/mt5_source.py` — `Mt5DataSource`, DEMO guard, conversie Europe/Bucharest
- `scripts/verifica_aliniere_mt5.py` — verificare OHLC + timezone

**Timezone:** MT5 timestamps în ora serverului broker (UTC+3 vara pe ICMarketsEU).
`Mt5DataSource` detectează offset-ul programatic și convertește explicit la `Europe/Bucharest`.

### Pasul 2 — COMPLET ✓ (2026-06-05)

- `live_runner.py` — buclă M15 live, mod OBSERVE, zero execuție
- Scanează `df.iloc[-2]` (ultima bară **închisă**), zero logică copiată față de backtest
- Log CSV structurat în `data/live_signals/`

### Pasul 3 — COMPLET ✓ (2026-06-06)

- `scripts/compare_live_vs_backtest.py` — verifică că live_runner detectează exact
  aceleași setup-uri ca backtestul, bara cu bara
- Comparație la nivel de **detectie de setup** (nu tranzacții — OBSERVE nu are stare)
- Sursa bare re-detectie: MT5 (CSV istoric nu acoperă perioada live)
- Garanție teoretică: cu fix-ul de lookahead activ, 0 nepotriviri posibile din mark_swings
- Rulare: `python scripts/compare_live_vs_backtest.py` (cel mai recent CSV)
         `python scripts/compare_live_vs_backtest.py --all-logs` (toate sesiunile)

---

## 9. Cum se rulează

```bash
# Backtest portofoliu (configuratia activa: EURUSD + GBPUSD + EURJPY, ONLY_LONG)
python portfolio_backtest.py

# Live demo MT5 — mod OBSERVE (MT5 desktop deschis si logat pe DEMO)
python live_runner.py
# Oprire: Ctrl+C
# Log: data/live_signals/signals_YYYYMMDD_HHMMSS.csv

# Comparatie fidelitate live vs backtest (dupa acumulare date in sesiune)
python scripts/compare_live_vs_backtest.py
python scripts/compare_live_vs_backtest.py --all-logs

# Descarca date istorice din MT5
python scripts/descarca_date.py

# Verificare aliniere MT5 vs CSV + timezone
python scripts/verifica_aliniere_mt5.py
```

---

## 10. Regula de aur — baseline oficial

**Orice modificare la strategie sau motor trebuie să reproducă:**

```
Portfolio EURUSD+GBPUSD+EURJPY, ONLY_LONG=True, $1000 start:
  1000 -> 1588.18 USD (+58.8%), 114 trades, expectancy +0.400R, DD -13.4%
  TRAIN (86t): +0.287R  |  TEST (28t): +0.748R
  EURUSD: 24t +0.824R  |  GBPUSD: 28t +0.372R  |  EURJPY: 62t +0.249R
```

Dacă numerele se schimbă — bug introdus, nu continuare.

> **Nota:** Cifrele anterioare Faza 0 (+172.7%, 470 trades, +0.212R) erau inflate de
> lookahead bias. Nu mai sunt valide ca referință.
