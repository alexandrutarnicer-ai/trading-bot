# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Comenzi frecvente

```bash
# Backtest portofoliu baseline (S1 — EURUSD+GBPUSD+EURJPY, LONG, 8 ani)
python portfolio_backtest.py

# Backtest S2 (6 perechi EUR+JPY, BOTH)
python session2_backtest.py

# Backtest S3 (BTC M15)
python session3_backtest.py

# Pornire toate sesiunile live (recomandat)
python live/run_all.py

# Sesiuni individual (MT5 deschis pe DEMO obligatoriu)
python live/session1_m15_long.py
python live/session2_m5_both.py
python live/session3_btc_both.py
python live/session4_obs.py
python live/session5_ger40_h1.py
python live/session6_us30_m15.py

# Descarca date istorice din MT5
python scripts/descarca_date.py
python scripts/descarca_date_istorice.py

# Analiza rezultate live
python scripts/analiza_observe.py
python scripts/analiza_observe.py --session session1
```

Nu există test suite sau linter configurat. Validarea corectitudinii se face prin reproducerea numerelor baseline (vezi mai jos).

---

## Arhitectura

Proiectul are doua moduri distincte: **backtest** (date CSV) si **live** (date MT5 real-time).

```
adapters/          — surse de date (CsvDataSource / Mt5DataSource)
strategy/          — indicatori, structura swing, semnale, costuri
engine/            — simulare backtest (single.py = un simbol, portfolio.py = multi-simbol)
live/              — generatoare de semnale live + executor ordine MT5
config/            — standard_profile.json (profil validat)
data/              — CSV-uri OHLC + output sesiuni live
scripts/           — descarca date, analiza, research (nu pentru productie)
```

### Fluxul de date

**Backtest:**
`CsvDataSource.load_bars()` → `strategy.preparation._enrich()` → `engine/portfolio.run_portfolio()`

**Live:**
`Mt5DataSource.load_bars()` → `strategy.preparation._enrich()` → `signal_generator._check_signals()` → `signal_generator._place_order()` (MT5 pending order)

### `strategy/preparation._enrich()`

Calculeaza toti indicatorii o singura data, identic pentru backtest si live. Input: bare M15 + bare M30 brute. Output: DataFrame M15 cu coloanele `trend` (1/-1/0 din EMA200 pe M30), `ema_fast/mid/slow` (8/20/50 pe M15), `rsi`, `atr`, `swing_high`, `swing_low`. Separarea adaptor/strategie este intentionata — adaugarea unui nou broker nu necesita modificari in strategy/.

### `strategy/structure.detect_setup()`

Detecteaza setup pullback-in-trend la bara `j`. Conditii stricte:
- Bullish: 2 HH crescatoare → ultimul HL (pullback low) dupa ultimul HH → bara `j` este **prima** care inchide peste maximul barei de pullback
- Window maxim: `pullback_window` bare (default 8 pentru S1/S3, 6 pentru S2/S4)
- Anti-lookahead: fereastra de cautare swinguri se opreste la `j - swing_n + 1` (nu `j`)

### `strategy/signals.reward_R()`

R/R dinamic pe scara: 0 criterii optionale → 2.5R; 1 criteriu → 3.5R; 2 criterii → 4.5R. Criteriile optionale: RSI in range + aliniere EMA8>EMA20>EMA50.

### `engine/portfolio.run_portfolio()`

Split train/test automat la 70%/30% din evenimente (nu din timp). `split_time` este calculat dinamic la fiecare rulare. Gestioneaza: pozitii simultane, verificare marja, circuit breaker (3 pierderi/zi), corelare perechi (EURUSD↔GBPUSD — nu deschide ambele simultan), swap overnight.

### `live/signal_generator.py` — engine-ul live

Ruleaza in loop infinit la fiecare bara noua. Per iteratie:
1. `_update_outcomes()` — verifica semnalele pending din `state.pkl` (SL/TP atins, expirare, invalidare). Anuleaza automat ordinele MT5 la expirare.
2. `_check_signals()` — detecteaza setup-uri noi pe ultimele 3 bare (offset 3, 2, 1)
3. `_place_order()` — plaseaza BUY_STOP/SELL_STOP in MT5. Returneaza: `int` (ticket OK), `None` (pret deja depasit — retry bara urm.), `False` (eroare MT5 reala — scoate din pending)

**Invariant critic:** Daca `execute_trades=True` si semnalul nu are ticket MT5 (`sig_id not in state["mt5_tickets"]`), nu se marcheaza niciodata `triggered=True` din bare. `outcomes.csv` reflecta doar ordine executate real in MT5.

Starea persistenta per sesiune: `state.pkl` (pending dict + counter + tickets MT5), `signals.csv` (toate semnalele), `outcomes.csv` (rezultate finale), `generator.log`.

### `live/run_all.py` — lansator

Porneste S1–S6 ca subprocese independente. La repornire: citeste `data/run_all.pid`, ucide instanta anterioara + toate sesiunile copil via `taskkill /F /T /PID <old>`, asteapta 3s, porneste sesiunile noi. La oprire (Ctrl+C / SIGTERM / SIGBREAK): trimite Telegram, termina toate procesele copil, sterge PID file.

Fiecare sesiune are si propriul `session.lock` (PID file per sesiune) care previne doua instante ale aceleiasi sesiuni.

---

## Sesiuni active

| ID | Script | Piete | TF | Directie | Status | Execute |
|----|--------|-------|----|----------|--------|---------|
| S1 | session1_m15_long.py | EURUSD/GBPUSD/EURJPY | M15+M30 | LONG | validat | True |
| S2 | session2_m5_both.py | +USDJPY/AUDJPY/NZDJPY | M15+M30 | BOTH | validat | True |
| S3 | session3_btc_both.py | BTCUSD | M15+M30 | BOTH | validat p=0.0075*** | True |
| S4 | session4_obs.py | GER40+US30 | M15+M30 | LONG | DEMO — re-eval Dec 2026 | True |
| S5 | session5_ger40_h1.py | GER40+USDCHF | H1+D1 | BOTH | OBSERVARE | **False** |
| S6 | session6_us30_m15.py | US30 | M15+M30 | LONG | DEMO | True |

S5 are `execute_trades=False` — logheaza semnale si trimite Telegram, nu plaseaza ordine MT5.

Capital: S3=62.5% din equity, S1/S2/S4/S6=12.5% fiecare. Sizing dinamic: botul citeste equity real MT5 la fiecare trade.

---

## Numere baseline — nu le modifica

Orice schimbare la `strategy/` sau `engine/` trebuie sa reproduca exact:

```
python portfolio_backtest.py  →  S1: 284 trades, Exp +0.025R, DD -40.5%
                                  TRAIN 181t: -0.156R | TEST 103t: +0.344R | split 2024-01-09

python session2_backtest.py   →  S2: 1022 trades, Exp +0.029R, DD -51.1%
                                  TRAIN 638t: -0.030R | TEST 384t: +0.127R | split 2024-07-22

python session3_backtest.py   →  S3: +0.211R train (p=0.0075***) | +0.336R test
                                  toate 7 ani pozitive (2020-2026 inclusiv bear 2022)
```

Daca numerele se schimba semnificativ → bug introdus, nu progres.

---

## Detalii tehnice importante

**pip_size pentru indici si crypto:** `_INDEX_PIP` in `strategy/signals.py` defineste 1.0 pentru indici (GER40, US30 etc.). BTCUSD este setat dinamic din `data/crypto_specs.json` (tick_size=0.01) in `session3_btc_both.py` — nu din fallback-ul default.

**Timestamps MT5:** `Mt5DataSource` converteste explicit din ora serverului broker la `Europe/Bucharest` (naive, fara tzinfo). Tot codul intern lucreaza in ora Romaniei.

**pip_value_usd pentru cross-uri:** `strategy/costs.py` calculeaza valoarea unui pip in USD pentru perechi cu quote non-USD (ex: EURGBP → 10 GBP × rate_GBPUSD). Nu folosi fallback-ul generic pentru perechi noi fara a verifica calculul.

**Swap BTC:** calculat ca procent anual din notional. Rate-ul variaza cu brokerul — verifica `data/crypto_specs.json`.

**`_place_order` filling modes:** incearca RETURN → FOK → IOC → fara filling, in ordine. ICMarketsEU respinge `ORDER_TIME_SPECIFIED` (retcode 10022) — se foloseste `ORDER_TIME_GTC`.

**AutoTrading dezactivat (retcode 10026/10027):** returneaza `None` (retry bara urm.), nu `False`.

---

## Configurare autostart Windows

```powershell
# Necesita Administrator — creeaza doua task-uri in Task Scheduler:
# TradingBot-MT5 (MT5 la login) + TradingBot-RunAll (run_all.py + 45s delay)
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
& "c:\trading-bot\scripts\setup_autostart.ps1"
```

Variabilele Telegram (`TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`) se seteaza in User Environment Variables Windows (nu in .env) — sunt citite de `start_bot.bat` din registry.
