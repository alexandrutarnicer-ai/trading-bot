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

# API backend (dashboard web)
python api/main.py   # sau: uvicorn api.main:app --reload --port 8000

# Frontend dev server
cd frontend && npm run dev

# Descarca date istorice din MT5
python scripts/descarca_date.py
python scripts/descarca_date_istorice.py

# Analiza rezultate live
python scripts/analiza_observe.py
python scripts/analiza_observe.py --session session1

# Test aplicare parametri profil in sesiuni live (77 teste)
python scripts/test_profile_params.py
```

Nu există test suite sau linter configurat. Validarea corectitudinii se face prin reproducerea numerelor baseline (vezi mai jos).

---

## Arhitectura

Proiectul are trei componente distincte: **backtest** (date CSV), **live** (date MT5 real-time), **API+frontend** (dashboard web).

```
adapters/          — surse de date (CsvDataSource / Mt5DataSource)
strategy/          — indicatori, structura swing, semnale, costuri
engine/            — simulare backtest (single.py = un simbol, portfolio.py = multi-simbol)
live/              — generatoare de semnale live + executor ordine MT5
api/               — FastAPI backend pentru dashboard web
  routers/         — bot, sessions, profiles, backtest, backtest_history, markets,
                     data_download, settings, mt5status
  models.py        — Pydantic models (BotStatus, SessionStatus, etc.)
  telegram.py      — helper Telegram (citeste token/chat_id din data/telegram_config.json)
frontend/          — React + Vite + TypeScript + Tailwind CSS (dark theme)
  src/api/         — types.ts, hooks.ts, client.ts
  src/components/  — BotControl, SessionEditor, BacktestPanel, SignalFeed, etc.
  src/pages/       — Dashboard, ProfilePage, HistoryPage
config/            — standard_profile.json (config backtest legacy — nu modifica)
data/              — CSV-uri OHLC + output sesiuni live + profiles/ + backtest_history.json
scripts/           — descarca date, analiza, research, teste (nu pentru productie)
```

### Fluxul de date

**Backtest:**
`CsvDataSource.load_bars()` → `strategy.preparation._enrich()` → `engine/portfolio.run_portfolio()`

**Live:**
`Mt5DataSource.load_bars()` → `strategy.preparation._enrich()` → `signal_generator._check_signals()` → `signal_generator._place_order()` (MT5 pending order)

**API:**
FastAPI servit pe port 8000. Frontend-ul React pe port 5173 face requests la `/api/*`. Backtestul rulează asincron — `POST /backtest/run` returnează `job_id`, clientul polleaza `GET /backtest/{job_id}` la 2s interval.

### `strategy/preparation._enrich()`

Calculeaza toti indicatorii o singura data, identic pentru backtest si live. Input: bare M15 + bare M30 brute. Output: DataFrame M15 cu coloanele `trend` (1/-1/0 din EMA200 pe M30), `ema_fast/mid/slow` (8/20/50 pe M15), `rsi`, `atr`, `swing_high`, `swing_low`. Separarea adaptor/strategie este intentionata — adaugarea unui nou broker nu necesita modificari in strategy/.

### `strategy/structure.detect_setup()`

Detecteaza setup pullback-in-trend la bara `j`. Conditii stricte:
- Bullish: 2 HH crescatoare → ultimul HL (pullback low) dupa ultimul HH → bara `j` este **prima** care inchide peste maximul barei de pullback
- Window maxim: `pullback_window` bare (default 8 pentru S1/S3, 6 pentru S2/S4)
- Anti-lookahead: fereastra de cautare swinguri se opreste la `j - swing_n + 1` (nu `j`)

### `strategy/signals.reward_R()`

R/R dinamic pe scara cu praguri configurabile. Numara criterii optionale satisfacute (`n_optional`), returneaza R-ul corespunzator din `reward_ladder`:

```python
def reward_R(n_optional, cfg):
    rl = cfg["reward_ladder"]
    t_mid = rl.get("threshold_mid", 1)   # default: 1 criteriu → mid R
    t_top = rl.get("threshold_top", 2)   # default: 2 criterii → top R
    t_max = rl.get("threshold_max", 3)   # default: 3 criterii → max R
    if "rr_if_6_criteria" in rl and n_optional >= t_max:
        return rl["rr_if_6_criteria"]    # max (ex: 5.5R)
    if n_optional >= t_top:
        return rl["rr_if_5_criteria"]    # top (ex: 4.5R)
    if n_optional >= t_mid:
        return rl["rr_if_4_criteria"]    # mid (ex: 3.5R)
    return rl["rr_if_3_criteria"]        # base (ex: 2.5R)
```

**Criterii optionale (3 total):**
1. `rsi` — RSI in range definit (ex: 40-65 pentru LONG)
2. `ema_alignment` — EMA8 > EMA20 > EMA50 (LONG) sau invers (SHORT)
3. `body_strength` — corp lumânare > `min_atr_ratio × ATR` — **dezactivat by default** (nu afecteaza baselines)

Pragurile sunt configurabile per sesiune via UI. Valorile default produc același comportament ca sistemul vechi cu 2 criterii și praguri fixe 1 și 2.

### `engine/portfolio.run_portfolio()`

Split train/test automat la 70%/30% din evenimente (nu din timp). `split_time` este calculat dinamic la fiecare rulare. Gestioneaza: pozitii simultane, verificare marja, circuit breaker (3 pierderi/zi), corelare perechi (EURUSD↔GBPUSD — nu deschide ambele simultan), swap overnight.

### `live/signal_generator.py` — engine-ul live

Ruleaza in loop infinit la fiecare bara noua. Per iteratie:
1. `_update_outcomes()` — verifica semnalele pending din `state.pkl` (SL/TP atins, expirare, invalidare). Anuleaza automat ordinele MT5 la expirare.
2. `_check_signals()` — detecteaza setup-uri noi pe ultimele 3 bare (offset 3, 2, 1)
3. `_place_order()` — plaseaza BUY_STOP/SELL_STOP in MT5. Returneaza: `int` (ticket OK), `None` (pret deja depasit — retry bara urm.), `False` (eroare MT5 reala — scoate din pending)

**Invariant critic:** Daca `execute_trades=True` si semnalul nu are ticket MT5 (`sig_id not in state["mt5_tickets"]`), nu se marcheaza niciodata `triggered=True` din bare. `outcomes.csv` reflecta doar ordine executate real in MT5.

**Aplicare parametri profil activ (`_apply_profile_overrides`):**
La pornire, `run_generator` cauta `data/active_profile_runtime.json` (scris de API la start bot). Daca exista, gaseste sesiunea dupa `session_key` si suprascrie:
- In `session_cfg`: `pullback_window`, `session_start/end`, `skip_hours`, `skip_weekdays`, `expire_bars`, `execute_trades`, `account_fraction`, `risk_pct`, `only_long`
- In `cfg` (strategy): RSI thresholds, EMA alignment toggle, body_strength, reward_ladder (r_base/mid/top/max si praguri)

Cand botul e pornit din CLI (`python live/run_all.py`) fara profil activ, valorile hardcodate din fiecare script SESSION_CONFIG sunt folosite. Fiecare script are `"session_key": "sessionN"` pentru mapare la profil.

Starea persistenta per sesiune: `state.pkl` (pending dict + counter + tickets MT5), `signals.csv` (toate semnalele), `outcomes.csv` (rezultate finale), `generator.log`.

### `live/run_all.py` — lansator

Porneste S1–S6 ca subprocese independente. La repornire: citeste `data/run_all.pid`, ucide instanta anterioara + toate sesiunile copil via `taskkill /F /T /PID <old>`, asteapta 3s, porneste sesiunile noi. La oprire (Ctrl+C / SIGTERM / SIGBREAK): trimite Telegram, termina toate procesele copil, sterge PID file.

Fiecare sesiune are si propriul `session.lock` (PID file per sesiune) care previne doua instante ale aceleiasi sesiuni.

### `api/` — Dashboard web backend

**Routere:**
- `bot` — `GET /bot/status` (running, pid, sessions_active, active_profile, last_started_at, last_stopped_at), `POST /bot/start`, `POST /bot/stop`
- `sessions` — status sesiuni live, semnale, outcomes, equity curve
- `profiles` — CRUD profile JSON din `data/profiles/`. `standard` este protejat (403 la stergere)
- `backtest` — `POST /backtest/run` (async job), `GET /backtest/{job_id}` (poll)
- `backtest_history` — `GET/POST/DELETE /backtest/history` — stocheaza rezultate in `data/backtest_history.json`
- `mt5status` — `GET /mt5/status` — conectare directa la MT5, returneaza cont/balance/equity/currency
- `data_download` — descarca CSV-uri din MT5 via `Mt5DataSource`
- `markets` — lista simboluri disponibile in MT5
- `settings` — configurare Telegram (token/chat_id in `data/telegram_config.json`)

**Date persistente create de API:**
- `data/profiles/*.json` — profile utilizator
- `data/active_profile.json` — profilul activ curent (cu `started_at`), sters la stop
- `data/active_profile_runtime.json` — profilul complet activ la runtime (citit de signal_generator), sters la stop
- `data/bot_run_log.json` — `{last_started_at, last_stopped_at}` — persistent
- `data/backtest_history.json` — toate rezultatele backtest (max 200 intrari)

**`_pid_alive()` Windows:**
Ambele routere `bot.py` si `sessions.py` folosesc `GetExitCodeProcess(STILL_ACTIVE=259)` in loc de doar `OpenProcess`. `OpenProcess` singur returneaza True pentru procese moarte recent (kernel object lifecycle).

**Telegram:**
`api/telegram.py` — helper shared folosit de `bot.py` pentru notificare la start/stop din UI. Citeste credentialele din `data/telegram_config.json` cu fallback pe env vars. `live/signal_generator.py` isi are propriul `_get_tg_creds()` care citeste acelasi fisier.

### Structura unui profil JSON (`data/profiles/*.json`)

```json
{
  "id": "standard",
  "name": "Standard Profile",
  "start_balance": 1000,
  "sessions": [{
    "id": "S1",
    "session_key": "session1",
    "markets": ["EURUSD", "GBPUSD", "EURJPY"],
    "entry_tf": "M15", "trend_tf": "M30",
    "direction": "LONG",
    "pullback_window": 8,
    "session_start": 10, "session_end": 18,
    "skip_hours": [15, 16], "skip_weekdays": [0],
    "expire_bars": 4,
    "account_fraction": 0.125, "risk_pct": 0.01,
    "risk_base": 0.01, "risk_mid": 0.01, "risk_top": 0.012, "risk_max": 0.015,
    "execute_trades": true,
    "rsi_enabled": true, "rsi_buy_min": 40, "rsi_buy_max": 65,
    "rsi_sell_min": 35, "rsi_sell_max": 60,
    "ema_alignment_enabled": true,
    "body_strength_enabled": false, "body_strength_min_atr_ratio": 0.15,
    "r_base": 2.5, "r_mid": 3.5, "r_top": 4.5, "r_max": 5.5,
    "r_mid_threshold": 1, "r_top_threshold": 2, "r_max_threshold": 3
  }]
}
```

**Nota:** `config/standard_profile.json` este config-ul legacy folosit de backtest si de sesiunile live cand nu exista profil activ runtime. NU modifica structura — este citit de `engine/portfolio.py` si `live/signal_generator.py`. `data/profiles/standard.json` este profilul UI (acelasi continut logic, format diferit).

---

## Sesiuni active

| ID | Script | Piete | TF | Directie | Status | Execute |
|----|--------|-------|----|----------|--------|---------|
| S1 | session1_m15_long.py | EURUSD/GBPUSD/EURJPY | M15+M30 | LONG | validat | True |
| S2 | session2_m5_both.py | USDJPY/AUDJPY/NZDJPY | M15+M30 | BOTH | validat | True |
| S3 | session3_btc_both.py | BTCUSD | M15+M30 | BOTH | validat p=0.0075*** | True |
| S4 | session4_obs.py | GER40+US30 | M15+M30 | LONG | DEMO — re-eval Dec 2026 | True |
| S5 | session5_ger40_h1.py | GER40+USDCHF | H1+D1 | BOTH | DEMO activ (din 1ce6a8e) | True |
| S6 | session6_us30_m15.py | US30 | M15+M30 | LONG | DEMO | True |

Capital: S3=62.5% din equity, S1/S2/S4/S6=12.5% fiecare. S5: account_fraction=0 (Demo fara capital alocat). Sizing dinamic: botul citeste equity real MT5 la fiecare trade.

---

## Numere baseline — nu le modifica

Orice schimbare la `strategy/` sau `engine/` trebuie sa reproduca exact:

```
python portfolio_backtest.py  →  S1: 284 trades, Exp +0.025R, DD -40.5%
                                  TRAIN 181t: -0.156R | TEST 103t: +0.344R | split 2024-01-09

python session2_backtest.py   →  S2: 1326 trades (879 train + 447 test), Exp +0.024R
                                  TRAIN 879t: -0.014R | TEST 447t: +0.099R | split 2024-03-21

python session3_backtest.py   →  S3: +0.211R train (p=0.0075***) | +0.336R test
                                  toate 7 ani pozitive (2020-2026 inclusiv bear 2022)
```

Daca numerele se schimba semnificativ → bug introdus, nu progres.

**Nota S2:** Numerele S2 au crescut fata de versiunile anterioare (era 1022 trades, split 2024-07-22) dupa adaugarea suportului multi-pozitie per simbol (`engine/portfolio.py`). Baselines curente reflecta comportamentul post-multi-position.

---

## Detalii tehnice importante

**pip_size pentru indici si crypto:** `_INDEX_PIP` in `strategy/signals.py` defineste 1.0 pentru indici (GER40, US30 etc.). BTCUSD este setat dinamic din `data/crypto_specs.json` (tick_size=0.01) in `session3_btc_both.py` — nu din fallback-ul default.

**Timestamps MT5:** `Mt5DataSource` converteste explicit din ora serverului broker la `Europe/Bucharest` (naive, fara tzinfo). Tot codul intern lucreaza in ora Romaniei.

**pip_value_usd pentru cross-uri:** `strategy/costs.py` calculeaza valoarea unui pip in USD pentru perechi cu quote non-USD (ex: EURGBP → 10 GBP × rate_GBPUSD). Nu folosi fallback-ul generic pentru perechi noi fara a verifica calculul.

**Swap BTC:** calculat ca procent anual din notional. Rate-ul variaza cu brokerul — verifica `data/crypto_specs.json`.

**`_place_order` filling modes:** incearca RETURN → FOK → IOC → fara filling, in ordine. ICMarketsEU respinge `ORDER_TIME_SPECIFIED` (retcode 10022) — se foloseste `ORDER_TIME_GTC`.

**AutoTrading dezactivat (retcode 10026/10027):** returneaza `None` (retry bara urm.), nu `False`.

**`body_strength` criteriu optional:** dezactivat by default (`enabled: false`) pentru a nu schimba baselines. Verifica intotdeauna ca `body_strength_enabled: false` in profilul standard inainte de a rula backtests de validare.

---

## Dashboard web — componente principale

**Dashboard.tsx:** Pagina principala. Afiseaza cont/balance/equity MT5 in header (citit din `useMt5Status`), profil activ, grid sesiuni (SessionCard), SignalFeed cu sume USD calculate per trade, EquityChart.

**SignalFeed.tsx:** Primeste `balanceUsd` si `capitalPct` ca props. Calculeaza `riskUsd = balance × (capitalPct/100) × 0.01`. La TP afiseaza `+3.5R TP (+175 USD)`, la SL afiseaza `-1R SL (-50 USD)`. USD = null daca MT5 deconectat.

**BotStatusBar.tsx:** Indicator running/stopped. Cand running: puls verde + "Bot activ — N sesiuni + PID". Cand stopped: ultima ora de oprire relativa ("azi 10:30", "ieri 14:45").

**BotControl.tsx:** Buton Start/Stop. La start trimite `{ profile_id, profile_name }` din profilul selectat curent. Afiseaza timpul de la ultima pornire/oprire.

**BacktestPanel.tsx:** Per sesiune profil. Capital + alocare per piata, range selector (1An/3Ani/Tot/Custom), verificare CSV → download daca lipsesc → run async → afisare rezultate + auto-save in history.

**HistoryPage.tsx:** Tab dedicat pentru toate backtestele rulate. Filtru sesiune, sumar stats (exp medie, nr rulari +), tabel expandabil cu params snapshot + per-symbol breakdown.

**NavBar.tsx:** 3 tab-uri: Dashboard / Profile / Istoric. Istoric afiseaza badge cu numarul de rulari.

---

## Configurare autostart Windows

```powershell
# Necesita Administrator — creeaza doua task-uri in Task Scheduler:
# TradingBot-MT5 (MT5 la login) + TradingBot-RunAll (run_all.py + 45s delay)
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
& "c:\trading-bot\scripts\setup_autostart.ps1"
```

Variabilele Telegram (`TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`) se seteaza in User Environment Variables Windows (nu in .env) — sunt citite de `start_bot.bat` din registry. In UI, configurarea se face din sectiunea Telegram Settings (accordion in ProfilePage).
