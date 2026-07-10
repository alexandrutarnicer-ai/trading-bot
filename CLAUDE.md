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

# Pornire dashboard (API + frontend + browser) cu dublu-click, fara IDE
start_ui.bat   # Windows: deschide doua ferestre terminal + browser la localhost:5173

# API backend (dashboard web)
python api/main.py   # sau: uvicorn api.main:app --reload --port 8000
# IMPORTANT: fara --reload, modificarile Python nu sunt preluate fara restart manual.

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

# Test logica filling modes + plasare ordine demo pe toate pietele (MT5 deschis)
python scripts/test_filling_logic.py              # unit tests + MT5 real
python scripts/test_filling_logic.py --unit-only  # doar unit tests (fara MT5)
python scripts/test_filling_logic.py XRPUSD       # un singur simbol

# M0 — audit statistic de robustete al sesiunilor (verdict KEEP/OBSERVE/DEMOTE)
python -m m0.audit                     # toate cele 20 sesiuni -> data/m0_audit.csv + docs/M0_RESULTS.md
python -m m0.audit --sessions S1,S3    # doar unele
python -m m0.audit --quick             # bootstrap redus (test rapid)
python -m m0.selftest                  # verificari integritate M0 (rapid, fara MT5)

# AI Engine — motor autonom AI, separat de botul pe reguli (MT5 DEMO + Ollama)
start_ai_engine.bat                    # dublu-click: porneste Ollama + motorul
setup_ai_engine.bat                    # instalare completa pe dispozitiv nou (laptop)
python -m ai_engine                    # manual
python -m ai_engine.selftest           # 21 verificari, include consiliu LIVE pe Ollama
python -m ai_engine.report             # scorecard + decizii + outcomes
python -m ai_engine.report --councils  # + transcripturile dezbaterilor AI
```

Nu există test suite sau linter configurat. Validarea corectitudinii se face prin reproducerea numerelor baseline (vezi mai jos). Pentru M0, `python -m m0.selftest` verifica reproducerea baseline-ului (284 trade-uri) + verdictele.

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
                     data_download, settings, mt5status, notifications, reports
  models.py        — Pydantic models (BotStatus, SessionStatus, etc.)
  notifications.py — store notificari (thread-safe, max 500, data/notifications.json)
  telegram.py      — helper Telegram (citeste token/chat_id din data/telegram_config.json)
frontend/          — React + Vite + TypeScript + Tailwind CSS (dark theme)
  src/api/         — types.ts, hooks.ts, client.ts
  src/components/  — BotControl, SessionEditor, BacktestPanel, SignalFeed, etc.
  src/pages/       — Dashboard, ProfilePage, NotificationsPage, ReportsPage, AuditPage, GuidePage
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

**Criterii optionale:**
1. `rsi` — RSI in range definit (ex: 40-65 pentru LONG)
2. `ema_alignment` — EMA8 > EMA20 > EMA50 (LONG) sau invers (SHORT)
3. `adx_d1` — trend puternic pe D1: ADX(14) zilnic > 25 (coloana `f2_adx` din `_enrich`, lag 1 zi) — **dezactivat by default**. A inlocuit `body_strength` in UI; `body_strength` ramane functional in backend pentru profile vechi (tot dezactivat by default).

Pragurile sunt configurabile per sesiune via UI, **inclusiv 0** (threshold 0 = nivelul respectiv se acorda intotdeauna). Valorile default produc același comportament ca sistemul vechi.

**`pullback_enabled` (default `true`):** strategia principala pullback-in-trend poate fi dezactivata per sesiune (UI: sectiunea "Strategia Pullback (principală)"). Gate-uit in `engine/portfolio.py`, `live/signal_generator.py::_check_signals`, API backtest si m0. Cu toggle ON (default) comportamentul e identic cu inainte — baselines neschimbate (verificat: 284 trades).

### `engine/portfolio.run_portfolio()`

Split train/test automat la 70%/30% din evenimente (nu din timp). `split_time` este calculat dinamic la fiecare rulare. Gestioneaza: pozitii simultane, verificare marja, circuit breaker (3 pierderi/zi), corelare perechi (EURUSD↔GBPUSD — nu deschide ambele simultan), swap overnight.

### `m0/` — audit statistic de robustete (Milestone 0 din planul AI)

Pachet **read-only** care determina care sesiuni au un edge real, distinct de norocul de cautare, inainte de a construi orice strat AI peste ele. Nu atinge nimic live; reutilizeaza exact `engine.portfolio.run_portfolio`. Vezi [docs/AI_ENGINE_FEASIBILITY.md](docs/AI_ENGINE_FEASIBILITY.md) (context) si [docs/M0_METHOD.md](docs/M0_METHOD.md) (metoda pe intelesul tuturor).

- `m0/session_runner.py` — mapeaza o sesiune din profil → params `run_portfolio` (**copiat verbatim** din `api/routers/backtest.py`; `SPREAD_DEFAULTS` duplicat — tine-l sincronizat daca cel din API se schimba). Suporta optional fereastra de date (pentru fold-uri). Validat: reproduce baseline-ul documentat (284 trade-uri).
- `m0/stats.py` — stationary block bootstrap (P(edge>0) + CI), Probabilistic/Deflated Sharpe cu prag de "trial-uri de breakeven" N*, consistenta pe 8 fold-uri + trend Spearman.
- `m0/robustness.py` — **sursa unica de adevar**: `evaluate_trades(df, split_time)` + `classify()` + `to_result_payload()`. Folosit ATAT de `m0.audit` CAT si de worker-ul de backtest din API, ca sa nu diverge. Verdict: KEEP (exp>0 ȘI P(edge>0)≥95% ȘI ≥60% fold-uri pozitive) / DEMOTE (exp≤0 SAU P(edge>0)<75%) / OBSERVE / INSUFF (<30 trade-uri).
- `m0/audit.py` — ruleaza toate cele 20 sesiuni → `data/m0_audit.csv` + `docs/M0_RESULTS.md`.
- `m0/selftest.py`, `m0/validate_runner.py` — verificari de integritate.

**Integrare in Audit tab:** `api/routers/backtest.py::_run_backtest_job` apeleaza `evaluate_trades` (n_boot=2000) pe seria de trade-uri si adauga cheia `robustness` in rezultat (fail-open — daca esueaza, backtestul se salveaza normal fara verdict). Frontend: `RobustnessResult` in `types.ts`, banner `RobustnessBanner` in capul lui `ResultsGrid` din `AuditPage.tsx` (verdict + P(edge>0) + Fold+ + N* + CI, cu tooltips), documentat in `GuidePage.tsx`. **Necesita restart API** (fara `--reload` codul vechi ramane in memorie).

### `ai_engine/` — motor de trading autonom AI (separat de botul pe reguli)

Motor experimental care isi alege singur strategia: perceptie numerica la fiecare bara M15 (gratuit) → consiliu de 4 agenti AI pe trigger-uri (regime flip, breakout tension, vol spike, news window, heartbeat 24h) → decizie JSON validata pe rails hard → executie DOAR pe cont DEMO. Vezi [docs/AI_ENGINE.md](docs/AI_ENGINE.md).

- **Surse AI multiple (v0.3):** registru deschis in `providers.py` — adaptori `ollama` / `anthropic` (SDK oficial) / `gemini` / `openai_compatible` (Groq, DeepSeek etc.), cu interfata comuna `chat_json`. Rolurile consiliului se distribuie pe surse (`role_assignments` in config). `ProviderRegistry` = sanatate per sursa + failover automat (quota→6h pauza, 429→60s, retea→2min, 401→dezactivat pana la retest) + revenire lazy; Ollama e safety-net (mereu enabled, nu se sterge). Chei API in `data/ai/providers.json` (gitignored). Hot-reload per iteratie (`registry.refresh`) — schimbarile din UI NU necesita restart de motor. Transcript per rol: `_provider`/`_latency_s`/`_fallback_from`. UI: cardul "Surse AI" in tab (`AiProvidersCard.tsx`), API: `GET/PUT /ai/providers`, `POST /ai/providers/test`. Plan: `docs/PLAN_SURSE_AI_MULTI_PROVIDER.md`.
- **LLM local gratuit:** Ollama + `qwen3:8b` pe GPU (`think:false` obligatoriu — altfel 10-15x mai lent) — sursa default a consiliului.
- **Consiliu (`council.py`):** Analist Tehnic → Analist Macro → Risk Manager (VETO absolut, aplicat in cod, nu de model) → Head Trader (JSON strict, retry cu feedback la JSON invalid). Orice eroare LLM → WAIT (fail-safe).
- **Rails hard (`executor.py::validate_decision` + clamp in `config.py`):** geometrie SL/TP, RR≥1, SL≤5×ATR, max 3 pozitii, stop zilnic -3R, risc≤1%. LLM-ul propune, rails-urile dispun.
- **Veto cod-enforced + reparare TP (`council.py::_sanitize`):** veto-ul Risk Manager e onorat DOAR cu un cod de risc valid (NEWS_IMMINENT/DAILY_STOP/MAX_POSITIONS/EXTREME_VOL/WEEKEND_GAP/BAD_GEOMETRY); veto necalificat → prudenta (risc redus la 0.25%), nu blocaj (fix pentru paralizia 29/29 veto observata 2026-07-09). `_repair_tp` recalculeaza TP la `target_rr` (default 2.0R) cand modelul propune RR<min_rr (SL structural pastrat) — evita respingerea unui setup directional bun pe TP prea aproape.
- **Izolare totala:** magic 770015 + comment "AI-{id}", filtrare stricta pe magic — nu vede/atinge pozitiile sesiunilor pe reguli. `executor.connect()` refuza non-DEMO (RuntimeError).
- **Ledger SQLite (`data/ai/ledger.db`):** snapshots, transcripturi complete de consiliu, decizii, outcomes (R/pnl via pattern hedging-safe order→position_id→deals). `python -m ai_engine.report` = scorecard.
- **Reutilizeaza:** `strategy.preparation._enrich` (perceptie), `live.news_guard._fetch_forexfactory` (calendar, cu cache TTL 10 min in perception), `api.telegram.send_message` (notificari), `Mt5DataSource` (bare + enforcement demo).
- Config utilizator: `ai_engine/config.json` (auto-creat la prima rulare). Mode `demo`/`shadow`. Piete default alese pentru cont ~$1000 la 1:30: EURUSD/USDJPY/GBPUSD/AUDUSD/USDCAD (XAUUSD/BTCUSD/US30 nu incap — risc lot minim $12-16 sau marja $260-310).
- **API + UI:** router `api/routers/ai_engine.py` (`/ai/status|start|stop|decisions|council/{id}|outcomes|config|logs`), tab "AI Engine" in NavBar (`AiEnginePage.tsx`) cu buton On/Off, scorecard, editor piete (validat contra MT5), decizii cu transcript dezbatere, log viewer. Heartbeat: `data/ai/status.json` scris la fiecare iteratie. Rail suplimentar: marja ordin ≤ 40% din marja libera. Reconectare automata MT5 daca toate pietele esueaza intr-o iteratie.
- **Instalare alt dispozitiv:** `setup_ai_engine.bat` (winget Python+Ollama, pull model, selftest). Un singur dispozitiv ruleaza motorul odata.

### `live/signal_generator.py` — engine-ul live

Ruleaza in loop infinit la fiecare bara noua. Per iteratie:
1. `_is_paused()` — verifica daca sesiunea e pe pauza (`data/paused_sessions.json`)
2. `_update_outcomes()` — verifica semnalele pending din `state.pkl` (SL/TP atins, expirare, invalidare). Anuleaza automat ordinele MT5 la expirare. **Ruleaza intotdeauna, inclusiv cand sesiunea e pe pauza.**
3. `_check_signals()` — detecteaza setup-uri noi pe bare INCHISE (offset 3, 2 — offset 1 este bara curenta partiala, ignorata intentionat pentru a preveni detectia dubla). **Sarit cand sesiunea e pe pauza.**
4. `_place_order()` — plaseaza BUY_STOP/SELL_STOP in MT5. Returneaza: `int` (ticket OK), `None` (pret deja depasit — retry bara urm.), `False` (eroare MT5 reala — scoate din pending). **Sarit cand sesiunea e pe pauza.**
5. `_friday_close_check()` — vineri la ora configurata, inchide pozitiile triggerate deschise printr-un ordin TRADE_ACTION_DEAL. Executa o singura data pe saptamana (tracking `state["friday_close_date"]`).
6. `_news_close_check()` — la tranzitia `news_paused False → True`, inchide pozitii triggerate (TRADE_ACTION_DEAL) SI anuleaza ordine pending neactivate (TRADE_ACTION_REMOVE). Apelata o singura data per tranzitie (tracking `_was_news_paused`). Status outcomes: `"news_close"` sau `"news_cancel"`.

**Invariant critic:** Daca `execute_trades=True` si semnalul nu are ticket MT5 (`sig_id not in state["mt5_tickets"]`), nu se marcheaza niciodata `triggered=True` din bare. `outcomes.csv` reflecta doar ordine executate real in MT5.

**Pauza sesiune (`_is_paused`):**
Citeste `data/paused_sessions.json` la fiecare iteratie. Cand sesiunea e pe pauza:
- `_update_outcomes()` continua → pozitiile deschise sunt monitorizate pana la SL/TP
- `_check_signals()` si retry ordine noi sunt sarite → nu se deschid pozitii noi
- Efectul pauzei intra la bara urmatoare (max 15 min pentru M15). **Nu necesita restart bot.**
- Pauza manuala trimite notificare Telegram (din `api/routers/sessions.py`).

**Protectie la stiri (`_is_news_paused`, `live/news_guard.py`):**
`news_guard.py` ruleaza ca daemon thread in `run_all.py` (pornit la start bot). Polleaza ForexFactory (primar, fara API key) la fiecare 300s, cu fallback pe MT5 calendar. Scrie `data/news_auto_paused.json` cu session_key-urile care trebuie puse pe pauza. Sesiunile citesc acest fisier via `_is_news_paused()`. La oprire bot, `news_clear_all()` sterge fisierul.
- `SYMBOL_CURRENCIES` dict mapeaza fiecare simbol la valutele constitutive (ex: EURUSD→[EUR,USD], GER40→[EUR])
- Pauza automata trimite notificare Telegram per sesiune; auto-resume la expirarea ferestrei de stire
- Configurabil per sesiune: `news_impact_level` (1/2/3), `news_pre_minutes`, `news_post_minutes`
- `_news_close_check()` se activeaza o singura data la tranzitia `False→True` — inchide imediat tot

**Inchidere Vineri (`_friday_close_check`):**
Apelata dupa procesarea semnalelor, la fiecare iteratie de vineri. Parametri din `session_cfg`:
- `friday_close_enabled` (default `True`) — dezactivat pentru S3/BTC (piata deschisa weekend)
- `friday_close_hour` (default `20`) — ora la care se inchid pozitiile

**Aplicare parametri profil activ (`_apply_profile_overrides`):**
La pornire, `run_generator` cauta `data/active_profile_runtime.json` (scris de API la start bot). Daca exista, gaseste sesiunea dupa `session_key` si suprascrie:
- In `session_cfg`: `pullback_window`, `session_start/end`, `skip_hours`, `skip_weekdays`, `expire_bars`, `execute_trades`, `account_fraction`, `risk_pct`, `only_long`, `friday_close_enabled`, `friday_close_hour`
- In `cfg` (strategy): RSI thresholds, EMA alignment toggle, body_strength, reward_ladder (r_base/mid/top/max si praguri)

Cand botul e pornit din CLI (`python live/run_all.py`) fara profil activ, valorile hardcodate din fiecare script SESSION_CONFIG sunt folosite. Fiecare script are `"session_key": "sessionN"` pentru mapare la profil.

Starea persistenta per sesiune: `state.pkl` (pending dict + counter + tickets MT5 + friday_close_date), `signals.csv` (toate semnalele), `outcomes.csv` (rezultate finale), `generator.log`.

**Coruptie `state.pkl`:** Daca o sesiune se opreste fortat in mijlocul scrierii, `state.pkl` poate ramane cu chei invalide in `pending` (ex: cheia e simbolul — `{"USDJPY": {}}` — in loc de un signal ID gen `SIG1`). Sesiunea continua sa ruleze dar nu proceseaza corect semnalele respective. Curatare: opreste sesiunea, sterge cheile goale cu `pickle.load` + `pop` + `pickle.dump`, reporneste. Sesiunile au fallback la `_empty_state` la coruptie totala a fisierului.

**`_send_telegram(text)` — non-blocking, daemon thread:**
Toate notificarile Telegram din `signal_generator.py` sunt trimise in `threading.Thread(target=_do_send, daemon=True).start()`. Botul nu asteapta niciodata raspunsul Telegram — timeout-ul de retea (8s) nu afecteaza performanta loop-ului principal.

**`_NotificationHandler` — rate-limiting notificari:**
Handler de logging care captureaza WARNING/ERROR din sesiunile live si le scrie in `data/notifications.json` (tab Notificari din UI). Implementeaza rate-limit: acelasi mesaj (primele 80 caractere) nu e retrimis mai devreme de 600s. Mesajele de rutina (`iter `, `Urmatoarea bara`, `Niciun semnal nou`, `[DEDUP]`, `[ORPHAN] Niciun`) sunt ignorate complet. Cache intern max 200 chei (LRU trim la 50 cand depasit). Previne flood de notificari repetitive (ex: 96+ WARNING/zi pentru aceeasi eroare).

**Reconciliere MT5 la startup — 3 straturi:**

1. **`_recover_lost_outcomes(state, session_cfg, outcomes_file, log)`** — apelata la fiecare pornire sesiune, dupa `_reconcile_mt5_tickets`. Pentru semnale pending FARA ticket MT5 (state sters la crash), cauta in MT5 `history_orders_get()` (10 zile lookback) dupa `o.comment == sig_id`. Daca gaseste:
   - Ordin inca pending → actualizeaza `mt5_tickets[sig_id] = ticket`
   - Pozitie deschisa → actualizeaza `mt5_tickets` + `triggered=True`
   - Pozitie inchisa → scrie outcome real (TP/SL/R/pnl_usd) in `outcomes.csv`, sterge din `pending`, trimite Telegram `[RECOVER]`
   - Daca sig_id deja in outcomes.csv → sare (nu duplica)

2. **Fix expirare in `_update_outcomes`** — inainte de a scrie `status=expirat, result_r=0.0`, verifica daca pozitia MT5 era de fapt INCHISA (`_check_mt5_position_closed`). Daca da, scrie TP/SL real + trimite Telegram `[RECOVER]`. Acopera scenariul: bot restartuit dupa ce pozitia fusese triggerata si inchisa in lipsa lui.

3. **Fix invalidare in `_update_outcomes`** — acelasi mecanism: bara invalideaza structura DAR MT5 poate fi deja inchis cu TP/SL real → prioritate MT5.

**Principiu: MT5 are intotdeauna prioritate.** Bot-ul nu poate marca niciodata `expirat/invalidat` daca MT5 confirma ca pozitia a fost executata real. Orice corectie trimite notificare Telegram cu prefix `[RECOVER]` si apare in tab-ul Notificari.

**`_CLOSED_STATUSES`:** `["TP", "SL", "vineri_close", "news_close", "be_lock", "be_lock2"]` — include acum `be_lock` si `be_lock2` pentru statisticile corecte in `sessions.py` si `reports.py`.

**Notificare ACTIVAT ordin MT5:**
La tranzitia `triggered=False → True` (ordinul BUY_STOP/SELL_STOP a fost atins de pret si activat), se trimite Telegram: `ACTIVAT #ticket: LONG/SHORT SYMBOL @ entry | SL ... | TP ... (R)`. Se trimite o singura data per semnal (persitat in `state.pkl` — `triggered=True` previne re-trimiterea). Activ doar cand `execute_trades=True`.

### `live/run_all.py` — lansator

Porneste S1–S6 ca subprocese independente. La repornire: citeste `data/run_all.pid`, ucide instanta anterioara + toate sesiunile copil via `taskkill /F /T /PID <old>`, asteapta 3s, porneste sesiunile noi. La oprire (Ctrl+C / SIGTERM / SIGBREAK): trimite Telegram, termina toate procesele copil, sterge PID file, sterge `data/news_auto_paused.json`.

Fiecare sesiune are si propriul `session.lock` (PID file per sesiune) care previne doua instante ale aceleiasi sesiuni.

**Telegram start/stop din UI (`api/routers/bot.py`):**
- Cand pornit din UI: `bot.py` seteaza `env["BOT_API_START"] = "1"` si trimite mesaj Telegram cu profilul si sesiunile active. `run_all.py` verifica variabila si sarita propriul mesaj de start pentru a evita dublura.
- Cand oprit din UI: `taskkill /F /T` nu declanseaza signal handlers Python, deci `_stop_all()` din `run_all.py` nu ruleaza. `bot.py` trimite el insusi notificarea de stop.
- **Ambele thread-uri (start + stop) sunt NON-DAEMON** — garantat ca se finalizeaza chiar daca uvicorn face reload intre timp. Stop-ul trimite Telegram **indiferent** de returncode-ul `taskkill` (starea e oricum curatata).

### `api/` — Dashboard web backend

**Routere:**
- `bot` — `GET /bot/status` (running, pid, sessions_active, active_profile, last_started_at, last_stopped_at), `POST /bot/start`, `POST /bot/stop`
- `sessions` — status sesiuni live, semnale, outcomes, equity curve
- `profiles` — CRUD profile JSON din `data/profiles/`. `standard` este protejat (403 la stergere). La `PUT /{profile_id}` apeleaza `_log_profile_change()` care difuiaza sesiunile si scrie in `data/session_changes_log.json`.
- `backtest` — `POST /backtest/run` (async job), `GET /backtest/{job_id}` (poll)
- `backtest_history` — `GET/POST/DELETE /backtest/history` — stocheaza rezultate in `data/backtest_history.json`
- `mt5status` — `GET /mt5/status` — cont/balance/equity/currency (via `api/mt5_pool.py`, cache TTL). `GET /mt5/orders` — pozitii deschise + ordine pending clasificate pe sursa (`bot`/`ai`/`manual` dupa magic 770015 + pattern comment) + sumar cont (marja folosita/libera, P&L flotant). Afisat in Dashboard ca tabel "Ordine Active" (`ActiveOrdersTable.tsx`). Toate endpointurile `/mt5/*` (stats, equity-curve, weekly-stats, top-markets, transactions, costs, costs-daily, sessions) sunt transformari peste lista de tranzactii cache-uita de pool — vezi nota `api/mt5_pool.py` mai jos.
- `ai_engine` — `GET/POST /ai/*` — status/start/stop/decizii/transcripturi/config/loguri pentru motorul AI (vezi sectiunea `ai_engine/`)
- `data_download` — descarca CSV-uri din MT5 via `Mt5DataSource`. Rezolva automat alias-uri de simboluri per broker (ex: GER40→DE40). Joburi persistate in `data/download_jobs.json`.
- `markets` — lista simboluri disponibile in MT5
- `settings` — configurare Telegram (token/chat_id in `data/telegram_config.json`). `POST /settings/telegram/test` trimite mesaj de test direct via Telegram API.
- `notifications` — CRUD notificari din `data/notifications.json`. `GET /notifications?limit=N`, `POST /notifications/mark-read`, `DELETE /notifications/{id}`, `DELETE /notifications` (clear all).
- `reports` — 5 endpointuri read-only: `GET /reports/transactions` (toate outcomes agregate, filtre status/symbol/direction/date + `obs_only=true` pentru sesiuni observatie), `GET /reports/market-stats` (clasament piete dupa R), `GET /reports/costs` (comisioane+swap per simbol), `GET /reports/costs-daily` (timeline zilnic comisioane+swap), `GET /reports/uptime` (istoric start/stop bot), `GET /reports/session-changes` (diff parametri la fiecare salvare profil). Endpointurile de rapoarte zilnic/saptamanal manual: `POST /reports/daily` si `POST /reports/weekly`.
- `mt5_sync` — `GET /mt5/sync-status` (statistici discrepante outcomes), `POST /mt5/sync` (resincronizare outcomes cu history MT5 — forteaza rescrierea entrarilor incorecte din CSV).

**Date persistente create de API:**
- `data/profiles/*.json` — profile utilizator
- `data/active_profile.json` — profilul activ curent (cu `started_at`), sters la stop
- `data/active_profile_runtime.json` — profilul complet activ la runtime (citit de signal_generator), sters la stop
- `data/bot_run_log.json` — `{last_started_at, last_stopped_at}` — persistent
- `data/backtest_history.json` — toate rezultatele backtest (max 200 intrari)
- `data/backtest_jobs.json` — joburi backtest async (max 150, supravietuiesc restart API)
- `data/download_jobs.json` — joburi descarcare date MT5 async (max 50, supravietuiesc restart API)
- `data/paused_sessions.json` — lista session_id-urilor pe pauza (ex: `["session1", "session3"]`), persistent peste restart bot
- `data/news_auto_paused.json` — lista sesiunilor puse automat pe pauza de News Guard, sters la stop bot
- `data/notifications.json` — toate notificarile (max 500, FIFO). Campuri per intrare: `id` (8 char uuid), `time` (ISO), `text` (HTML original), `text_plain` (HTML stripped), `category` (order/trade/signal/news/session/bot/system), `read` (bool). Scriere thread-safe via `threading.Lock()`.
- `data/bot_uptime_log.json` — istoric porniri/opriri bot (max 200). La `start_bot()`: append entry cu `stopped_at=None`. La `stop_bot()`: gaseste ultima intrare deschisa si completeaza `stopped_at` + `duration_sec`. Scris de `api/routers/bot.py`.
- `data/session_changes_log.json` — diff parametri profil la fiecare salvare (max 500). Per intrare: `profile_id`, `profile_name`, `time`, `sessions` (lista de `{id, changes: [{field, from, to}]}`). Scris de `api/routers/profiles.py` la `PUT /{profile_id}`.

**Routere sessions — endpoints:**
- `POST /sessions/{session_id}/pause` — adauga in `paused_sessions.json`, trimite Telegram
- `POST /sessions/{session_id}/resume` — sterge din `paused_sessions.json`, trimite Telegram
- `GET /sessions/frequency-estimate?profile_id=` — calculeaza trades/saptamana + trades/luna din `backtest_jobs.json`. Citeste profilul activ (sau cel specificat), exclude sesiunile pe pauza **si pe cele cu `execute_trades=False` (observatie)**; returneaza `{per_week, per_month, missing: [{id, markets}]}`. `missing` = sesiuni fara backtest recent (nu contribuie la estimat). Endpoint read-only, zero dependente de bot/MT5. **Trebuie plasat INAINTE de `/{session_id}` routes** (altfel FastAPI il intercepteaza ca session_id).
- `GET /sessions/all/signals` — agregate semnalele din toate sesiunile, sortate descrescator dupa `time`, limit=50. **Trebuie plasat INAINTE de `/{session_id}` routes** (altfel FastAPI il intercepteaza ca session_id). Folosit de SignalFeed in modul "ALL".
- `SessionStatus` include campurile: `paused: bool`, `news_paused: bool`, `news_events: list`, `signals_yesterday: int`, `outcomes_today: int`, `outcomes_yesterday: int`, `wins_today: int`, `wins_yesterday: int`, `losses_today: int`, `losses_yesterday: int` (folosite de TradingStatsPanel pentru trend azi vs ieri per categorie)

**Routere data_download — endpoints:**
- `GET /data/jobs` — lista tuturor joburilor de descarcare (din `download_jobs.json`)
- `DELETE /data/jobs/{job_id}` — sterge job finalizat
- `POST /data/download` — accepta si campul `label` (string human-readable afisat in Audit)
- `SYMBOL_ALIASES` in `data_download.py` — mapeaza simboluri canonice la variante broker: `GER40→[GER40, DE40, DAX40, ...]`, `US30→[US30, DJ30, ...]`, `UK100→[UK100, FTSE100, ...]` etc. Backend incearca candidatii in ordine; salveaza CSV sub numele canonic. Campul `mt5_symbol` in rezultat indica simbolul real gasit.

**Routere bot — endpoints noi:**
- `GET /bot/autostart/status` — verifica daca task-ul TradingBot-RunAll exista in Task Scheduler
- `POST /bot/autostart/enable` — ruleaza `scripts/setup_autostart.ps1` cu UAC elevation
- `POST /bot/autostart/disable` — ruleaza `scripts/remove_autostart.ps1` cu UAC elevation

**Routere backtest — endpoints:**
- `GET /backtest/jobs` — lista tuturor joburilor (din `backtest_jobs.json`)
- `DELETE /backtest/jobs/{job_id}` — sterge job finalizat
- Rezultatele includ `skipped_markets` (piete fara CSV) si `final_balance`

**`_pid_alive()` Windows:**
Ambele routere `bot.py` si `sessions.py` folosesc `GetExitCodeProcess(STILL_ACTIVE=259)` in loc de doar `OpenProcess`. `OpenProcess` singur returneaza True pentru procese moarte recent (kernel object lifecycle).

**Telegram + Notificari:**
`api/telegram.py` — helper shared folosit de `bot.py` pentru notificare la start/stop din UI. Citeste credentialele din `data/telegram_config.json` cu fallback pe env vars. `live/signal_generator.py` isi are propriul `_get_tg_creds()` care citeste acelasi fisier.
- **Captura notificari:** Ambele `api/telegram.py:send_message()` si `live/signal_generator.py:_send_telegram()` apeleaza `from api.notifications import log_notification(text)` la inceputul functiei (lazy import in `try/except`). Asigura ca 100% din notificarile Telegram apar si in tab-ul Notificari din UI, indiferent de sursa. Esecul `log_notification` nu afecteaza niciodata trimiterea Telegram sau botul.

**`api/config.py` — `get_profile_execute_map()`:**
Citeste `execute_trades` per sesiune din profilul activ la runtime (nu din `SESSIONS` static). Folosit de `sessions.py`, `reports.py`, `scheduled_reports.py` pentru a filtra sesiunile OBS (execute_trades=False) din toate agregarile. `session4` (GER40) si `session6` (US30) au `execute=False` in config; `session20` (XAUUSD) are `execute=True`. Fallback pe valorile statice din `SESSIONS` daca profilul nu e accesibil.

**`api/scheduled_reports.py` — rapoarte periodice automate:**
Pornit ca daemon thread la startup API. Trimite via Telegram + Notificari:
- **Zilnic la 23:30** — tranzactii din ziua respectiva (R, P&L, comisioane, top simboluri, per sesiune)
- **Vineri la 23:30** — rezumat saptamanal (Luni-Vineri)
Foloseste `get_profile_execute_map()` pentru a exclude OBS. Triggerable manual via `POST /reports/daily` si `POST /reports/weekly`.

**`api/watchdog.py` — daemon watchdog oprire neasteptata:**
Pornit automat la startup API (`@app.on_event("startup")`). Ruleaza ca thread daemon, polleaza la fiecare 30s: daca exista profil activ (`data/active_profile.json`) dar PID-ul botului (`data/run_all.pid`) nu mai e viu → trimite notificare Telegram ("Bot Trading oprit neasteptat!") si curata fisierele de stare (profil activ, pid). Acopera scenariile de crash sau oprire fortata fara Ctrl+C.

**`api/routers/mt5status.py` — `algo_trading_enabled`:**
Campul `algo_trading_enabled: bool | null` returnat in `GET /mt5/status`. Citit din `mt5.terminal_info().trade_allowed`. Dashboard-ul afiseaza un banner de avertizare galben cand este `false` (botul detecteaza semnale dar ordinele MT5 nu pot fi plasate).

**`api/mt5_pool.py` — acces MT5 centralizat, persistent, cache-uit (procesul API):**
Toate endpointurile `/mt5/*` trec prin acest pool. Inainte, FIECARE endpoint facea `mt5.initialize()` + `mt5.shutdown()` per request, si 9 endpointuri distincte interogau fiecare independent `history_deals_get` pe 400 zile pentru aceleasi date — Dashboard + Rapoarte declansau 6-9 astfel de interogari per ciclu de polling. Pool-ul rezolva:
- **Conexiune persistenta** — `_ensure_mt5()` apeleaza `initialize()` la fiecare acces necache-uit (revalidare ieftina; reconecteaza automat daca alt modul din API — markets/data_download/mt5_sync — a facut `shutdown()`), dar NU face niciodata `shutdown()`. Elimina handshake-ul IPC per-request (~8ms → ~0.02ms, masurat 489x mai ieftin).
- **Lock global (`RLock`)** — serializeaza tot accesul MT5 (modulul MetaTrader5 NU e thread-safe; endpointurile sync ruleaza in threadpool-ul FastAPI). Rezolva si un race latent: un `shutdown()` dintr-un request putea taia conexiunea altui request in curs.
- **Cache TTL** — `get_closed_trades(days)` interogheaza MT5 pe intreaga fereastra (400 zile) O SINGURA DATA per `_TRADES_TTL` (15s) si filtreaza local la fereastra ceruta; toate cele 9 endpointuri partajeaza aceeasi lista. `get_status()` (5s), `get_orders()` (6s), offset server (30 min). `invalidate()` forteaza reinterogarea.
- **Izolare totala fata de bot/AI:** pool-ul traieste DOAR in procesul API. Sesiunile live si motorul AI au fiecare propria conexiune MT5 in propriul proces — pool-ul nu le atinge. `mt5.initialize()` e idempotent si per-proces (mai multi clienti IPC coexista deja pe acelasi terminal). `api/watchdog.py::_get_mt5_equity` trece si el prin pool (fara `shutdown()` propriu care ar taia conexiunea calda).

**`api/csv_cache.py` — cache CSV invalidat pe (mtime, size):**
`read_csv_cached(path, **kwargs)` cache-uieste DataFrame-urile de semnale/outcomes; invalidare exacta pe `(st_mtime_ns, st_size)` — fisierele se schimba doar cand botul scrie, deci zero staleness. Folosit de `sessions.py` si `reports.py`. `GET /sessions` (poll la 15s) citea 40 CSV-uri + rula `_resolve_outcome_sig_ids` (iterrows scump) la fiecare poll; acum `_read_outcomes_resolved` cache-uieste si rezultatul fuzzy-match-ului pe cheile ambelor fisiere. Rezultat masurat: `/sessions` 2.7x mai rapid (cald). Nu copiaza frame-ul returnat — apelantii fac boolean-indexing sau `.copy()` inainte de mutatie; frame-ul cache-uit nu e mutat in loc.

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
    "r_mid_threshold": 1, "r_top_threshold": 2, "r_max_threshold": 3,
    "friday_close_enabled": true, "friday_close_hour": 20
  }]
}
```

**Campuri noi in sesiune:**
- `session_start: 0` + `session_end: 24` → sesiune Non-stop (fara restrictie de ore). Signal generator-ul deja trateaza 0-24 corect.
- `friday_close_enabled` (bool, default `true`) + `friday_close_hour` (int 0-23, default `20`) — S3/BTC are `friday_close_enabled: false`.
- `account_fraction` (float 0-1) — fractia din equity MT5 alocata sesiunii. Vizibil si editabil in SessionEditor cu breakdown live ($capital × fractie, risc/trade în USD).
- `news_protection_enabled` (bool, default `false`) + `news_impact_level` (1/2/3) + `news_pre_minutes` + `news_post_minutes` — protectie automata la stiri. Cand activa, sesiunea intra pe pauza automatic + ordine/pozitii inchise imediat.
- `break_even_enabled` (bool, default `false`) + `be_trigger_pct` (default 80) + `be_lock1_pct` (default 30) + `be_lock2_pct` (default 50) + `be_phase2_zone_pct` (default 40) — mecanism break-even in 3 faze (vezi `engine/simulator.py`).
- `be_phase2_enabled` (bool, default `true`) — dezactiveaza independent Faza 2 BE fara a dezactiva intregul mecanism. Cand `false`, tranzitia Faza1→Faza3 sare direct la SL blocat la 50%.

**Nota:** `config/standard_profile.json` este config-ul legacy folosit de backtest si de sesiunile live cand nu exista profil activ runtime. NU modifica structura — este citit de `engine/portfolio.py` si `live/signal_generator.py`. `data/profiles/standard.json` este profilul UI (acelasi continut logic, format diferit).

---

## Sesiuni active

20 sesiuni individuale — o singura piata per sesiune. Fiecare are propriul script live, `session_key`, `state.pkl`, `signals.csv`, `outcomes.csv`.

| ID | Script | Piata | TF | Directie | Execute |
|----|--------|-------|----|----------|---------|
| session1  | session1_m15_long.py   | EURUSD  | M15+M30 | LONG | True  |
| session2  | session2_m5_both.py    | AUDJPY  | M15+M30 | BOTH | True  |
| session3  | session3_btc_both.py   | BTCUSD  | M15+M30 | BOTH | True  |
| session4  | session4_obs.py        | GER40   | M15+M30 | LONG | True  |
| session5  | session5_ger40_h1.py   | USDCHF  | H1+D1   | BOTH | True  |
| session6  | session6_us30_m15.py   | US30    | M15+M30 | LONG | True  |
| session7  | session7_xrp.py        | XRPUSD  | M15+M30 | BOTH | True  |
| session8  | session8_eurcad_h1.py  | EURCAD  | H1+D1   | BOTH | True  |
| session9  | session9_usdjpy.py     | USDJPY  | M15+M30 | BOTH | True  |
| session10 | session10_gbpcad_h1.py | GBPCAD  | H1+D1   | BOTH | True  |
| session11 | session11_usdcad.py    | USDCAD  | M15+M30 | BOTH | True  |
| session12 | session12_euraud_h1.py | EURAUD  | H1+D1   | BOTH | True  |
| session13 | session13_eurjpy.py    | EURJPY  | M15+M30 | BOTH | True  |
| session14 | session14_chfjpy_h1.py | CHFJPY  | H1+D1   | BOTH | True  |
| session15 | session15_gbpusd.py    | GBPUSD  | M15+M30 | BOTH | True  |
| session16 | session16_gbpaud_h1.py | GBPAUD  | H1+D1   | BOTH | True  |
| session17 | session17_audcad_h1.py | AUDCAD  | H1+D1   | BOTH | True  |
| session18 | session18_nzdjpy_h1.py | NZDJPY  | H1+D1   | BOTH | True  |
| session19 | session19_audnzd.py    | AUDNZD  | M15+M30 | BOTH | True  |
| session20 | session20_xauusd.py    | XAUUSD  | M15+M30 | BOTH | False |

`session20` (XAUUSD) are `execute_trades=False` — sesiune de observatie. Sizing dinamic: botul citeste equity real MT5 la fiecare trade. `account_fraction` per sesiune configurat in profil.

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

**pip_value_usd — arhitectura si intretinere:**
- **Live** (`live/signal_generator.py` → `_calc_lots`): citeste `info.trade_tick_value` si `info.trade_tick_size` direct din MT5 la fiecare trade. Intotdeauna 100% corect, independent de valorile din `costs.py`.
- **Backtest** (`strategy/costs.py` → `pip_value_usd`): foloseste valori statice — `_INDEX_TICK` (indici, XAUUSD), `_CRYPTO_TICK` (BTC/ETH/XRP), `BASE_USD_APROX` (ratele EUR/GBP/AUD→USD pentru cross-perechi). Formula cross-perechi: `val_in_quote × BASE_USD[baza] / cross_price` (ex: AUDCAD: 10 CAD × 0.64 / 0.88 = 7.27 USD).
- **Intretinere `BASE_USD_APROX`**: actualizeaza la 6 luni daca ratele deriva >5% (EUR=1.08, AUD=0.64, GBP=1.27 — last update: 2026-06-24). Afecteaza doar cifrele $ absolute, nu R-ul (backtestul e R-based).
- **Simboluri noi non-forex**: adauga obligatoriu in `_INDEX_TICK` sau `_CRYPTO_TICK` din `costs.py` SI in `_INDEX_PIP` din `signals.py`. Fara inregistrare explicita, formula forex (pip=0.0001, val=100000×pip) da pip_value gresit → lots=0 → 0 trades in backtest (ex: XRPUSD era 10.0 in loc de 0.01 USD/pip).
- **Dupa modificari `costs.py`/`signals.py`**: API-ul trebuie repornit — fara `--reload`, codul vechi ramane in memorie.

**Swap BTC:** calculat ca procent anual din notional. Rate-ul variaza cu brokerul — verifica `data/crypto_specs.json`.

**`pnl_usd` in `outcomes.csv`:** Coloana 14 din `_OUTCOMES_COLS`. Scrisa de `_pnl()` la inchiderea ordinelor MT5 reale (TP/SL/vineri_close/news_close). Valoarea vine din `deal.profit` returnat de `history_deals_get`. Ramane `NaN` pentru ordine expirate sau sesiunile cu `execute_trades=False`. Backfill retroactiv: `python scripts/backfill_pnl_usd.py` (necesita MT5 conectat).

**`_CLOSED_STATUSES`:** `["TP", "SL", "vineri_close", "news_close", "be_lock", "be_lock2"]` — toate statusurile care corespund pozitiilor reale inchise. Folosit in `_outcome_stats`, `weekly_stats._aggregate` si `equity_curve` din `api/routers/sessions.py`. Castigurile/pierderile sunt calculate din `result_r > 0` / `result_r < 0` (nu din status) pentru a acoperi si vineri_close cu R pozitiv. `be_lock`/`be_lock2` corespund exiturilor break-even — trebuie incluse explicit.

**`GET /sessions/frequency-estimate`:** Calculeaza frecventa estimata trades/saptamana + trades/luna din cele mai recente backtest-uri finalizate (din `data/backtest_jobs.json`). Filtreaza sesiunile pe pauza **si cele cu `execute_trades=False`**. Mapare: `job.session_id` ("S2") → `profile_session.id` ("S2"). Returneaza `{per_week, per_month, missing}` sau `null` daca nu exista backtest-uri.

**`POST /backtest/run-missing`:** Triggereza backteste automat pentru sesiunile cu `execute_trades=True` care nu au backtest recent. Citeste profilul activ (sau `profile_id` din body), construieste `session_cfg` din parametrii profilului, porneste joburi async cu range 5 ani (2021–azi). Returneaza `{job_ids, triggered}`. Apelat din Dashboard la click pe badge-ul "X fara date".

**`_place_order` filling modes — logica completa:**
- **Ordinea modurilor**: determinata din `symbol_info().filling_mode` bitmask. Bit 0 (1) = FOK suportat, bit 1 (2) = IOC suportat. Daca `fm=0` (Forex standard): RETURN → FOK → IOC. Daca `fm!=0` (crypto/indici): modurile cu bit setat primele, RETURN ca fallback. Ultima sansa: fara `type_filling`.
- **Retry pe retcode**: continua cu alt filling la `10030` (TRADE_RETCODE_INVALID_FILL) SI `10006` (TRADE_RETCODE_REJECT — ICMarketsEU returneaza asta in loc de 10030 pentru crypto/indici cu filling mode incompatibil). Orice alt retcode = eroare reala, iesire imediata cu `False`.
- **all_10006**: daca TOATE incercarile (inclusiv fara filling) returneaza `10006`, se returneaza `None` (retry bara urm.) in loc de `False`. ICMarketsEU returneaza `10006` si pentru piata temporar inchisa (crypto weekend/maintenance), nu `10018` ca standard. Semnalul expira natural dupa `expire_bars`.
- **Min stops distance**: inainte de `order_send`, verifica `trade_stops_level * point`. Daca distanta entry-pret_curent < min_dist, returneaza `None` cu log clar. Evita reject-ul garantat fara request MT5 inutil.
- ICMarketsEU respinge `ORDER_TIME_SPECIFIED` (retcode 10022) — se foloseste `ORDER_TIME_GTC`.

**`_close_position_robust(symbol, volume, order_type, position, price, comment, log)`**: helper pentru inchidere pozitii (TRADE_ACTION_DEAL) cu retry pe filling modes. Incearca IOC → FOK → RETURN → fara filling. Continua cu alt filling la 10006/10030; orice alta eroare returneaza imediat result-ul. Folosit in `_friday_close_check` si `_news_close_check` — inlocuieste `order_send` cu IOC-only care esua silentios pe crypto cu filling incompatibil.

**AutoTrading dezactivat (retcode 10026/10027):** returneaza `None` (retry bara urm.), nu `False`.

**ICMarketsEU — hedging mode:** Contul foloseste hedging mode, nu netting. In hedging mode `position_id ≠ order_ticket` — `history_deals_get(position=order_ticket)` returneaza gol. `_check_mt5_position_closed` rezolva asta prin `history_orders_get(ticket)` → `order.position_id` → `history_deals_get(position=position_id)`. Fara aceasta, toate outcome-urile ar folosi bar-based tracking (exit_price = exact SL, nu pretul real MT5). ORDER_STATE: CANCELED=2, REJECTED=5, EXPIRED=6 — FILLED=4 nu inseamna ordin orfan.

**`comment_map` — guard in `_scan_mt5_history_for_missing_outcomes`:**
ICMarketsEU trunchiaza comentariile la 16 caractere. `state["comment_map"][comment[:16]] = full_sig_id` e setat la plasarea fiecarui ordin nou. **Bug cunoscut rezolvat (2026-07-01):** la scanare history, un ordin vechi cu acelasi prefix 16-char ca un semnal curent pending era incorect asociat via comment_map → scria outcome din trecut sub sig_id-ul semnalului curent (afisa SL in dashboard pentru un ordin pending real in MT5). **Fix:** inainte sa folosim comment_map, verificam `_cm_match not in state["mt5_tickets"]` — daca semnalul are deja ticket activ, ordinul din history e alt trade cu prefix identic, se foloseste ID ticket-based ca fallback.

**Deduplicare semnale duplicate (restart re-detection):**
`_check_signals()` → inainte de scriere in signals.csv, verifica `(symbol, direction, entry)` in signals.csv existent si in pending dict. Previne re-detectia aceluiasi setup dupa restart (IDs diferite, trade identic). Semnale duplicate istorice gasite in session7/16/17/18/19 (generate inainte de implementarea dedup-ului) — curatate manual cu `scripts/repair_outcomes.py`.

**`_scan_mt5_history` — deduplicare imbunatatita (2026-07-01):**
`existing_pos_keys` include acum doua chei alternative per outcome existent:
- `(symbol, round(pnl_usd, 2), exit_time[:19])` — cheia originala
- `(symbol, round(pnl_usd, 2), round(entry_price, 5))` — cheia alternativa fara exit_time
Prinde duplicate unde exit_time difera intre inregistrarea bot (vineri_close la 20:00) si deal-ul MT5 real (23:01 dupa executia asincron).

**`body_strength` criteriu optional:** dezactivat by default (`enabled: false`) pentru a nu schimba baselines. Verifica intotdeauna ca `body_strength_enabled: false` in profilul standard inainte de a rula backtests de validare.

**Break-even — `engine/simulator.py`:** Mecanism in 3 faze controlat de `be_cfg` dict. Faza 1: cand pretul atinge `be_trigger_pct`% din distanta SL→TP, SL mutat la `be_lock1_pct`% din SL original. Faza 2 (optionala, `phase2_enabled`): cand pretul intra in zona `be_phase2_zone_pct`% din TP, SL blocat la `be_lock2_pct`%. Faza 3: reversal dupa Faza 2 → SL la 50%. Contorizate in `be_lock_count` (Faza1) si `be_lock2_count` (Faza2) in rezultatele backtest. Break-even este dezactivat by default (`break_even_enabled: false`) — nu afecteaza baselines.

**`setupSecond.py` — `npm install` cu `shell=True`:** Pe Windows, `npm` este `npm.cmd` (nu `npm.exe`). `subprocess.run(["npm", ...])` fara `shell=True` esueaza cu FileNotFoundError. Solutie: `subprocess.run("npm install", shell=True, cwd=frontend)`. Regula generala: orice comanda `.cmd` Windows in subprocess necesita `shell=True`.

---

## Dashboard web — componente principale

**Dashboard.tsx:** Pagina principala. Afiseaza cont/balance/equity MT5 in header (citit din `useMt5Status`), profil activ, grid sesiuni (SessionCard), SignalFeed cu sume USD calculate per trade, EquityChart. Banner de avertizare galben cand `mt5.algo_trading_enabled === false` — semnale detectate dar ordine blocate in MT5.
- **Widget frecventa estimata:** 2 carduri vizibile permanent deasupra grid-ului de sesiuni — "Estimat / săptămână" + "Estimat / lună". Calcul bazat pe `GET /sessions/frequency-estimate` (citeste backtest_jobs.json, exclude sesiunile pe pauza si cele cu `execute_trades=False`). Polleaza la 15s. Afiseaza "—" cand nu exista date backtest.
- **Badge sesiuni fara date (buton):** Cand unele sesiuni nu au backtest recent, cardul "Estimat / săptămână" afiseaza un badge portocaliu clickabil cu numarul lor (ex: "▶ 2 fara date") si hover tooltip cu lista exacta (`S9: USDJPY`, etc.). **Click pe badge** → apeleaza `POST /backtest/run-missing` cu profilul activ → porneste automat backtestele lipsa (range 5 ani) → invalideaza cache-ul de frecventa. Stare "Se calculeaza..." in timp ce ruleaza.

**SignalFeed.tsx:** Primeste `sessionId`, `balanceUsd` si `capitalPct` ca props. Calculeaza `riskUsd = balance × (capitalPct/100) × 0.01`. La TP afiseaza `+3.5R TP (+175 USD)`, la SL afiseaza `-1R SL (-50 USD)`. USD = null daca MT5 deconectat. Cand `sessionId === "all"` apeleaza `/sessions/all/signals` (50 semnale agregate) si dezactiveaza `useOutcomes` (USD nedisponibil fara sesiune specifica).

**BotStatusBar.tsx:** Indicator running/stopped. Cand running: puls verde + "Bot activ — N sesiuni + PID". Cand stopped: ultima ora de oprire relativa ("azi 10:30", "ieri 14:45").

**BotControl.tsx:** Buton Start/Stop. La start trimite `{ profile_id, profile_name }` din profilul selectat curent. Afiseaza timpul de la ultima pornire/oprire.

**SessionCard.tsx:** Card per sesiune in Dashboard. Include buton Pause/Play (⏸/▶) in header. Cand pe pauza: dot galben, badge "PAUZA", stats dimmate. Butonul apeleaza `POST /sessions/{id}/pause` sau `/resume`. Nu necesita restart bot — efectul intra la bara urmatoare.

**BacktestPanel.tsx:** Per sesiune profil. Capital + alocare per piata, range selector (1An/3Ani/Tot/Custom), verificare CSV → download daca lipsesc → trimite job in Audit tab (nu mai afiseaza inline). Dupa pornire descarcare: starea `dl_submitted` arata "Descarcarea rulează în Audit..." cu buton "Mergi la Audit" — identic cu flow-ul backtest. Prop `onDownloadStarted` pentru navigare la Audit.
- **Capital default per piata:** `profileStartBalance × account_fraction / n_markets` (calculat din props `profileStartBalance` pasata din ProfilePage → SessionEditor → BacktestPanel).
- **`minCapital` enforcement:** `frontend/src/marketSpecs.ts` defineste `minCapital` per piata (ex: EURUSD=150, US30=400, BTCUSD=150). Input-ul de alocare per piata are `min={minCap}` — border rosu + avertisment "⚠ min X" cand suma e sub minim. Calcul overshoot nu ruleaza sub minim.

**SessionEditor.tsx (Profile):** Editor complet per sesiune. Include:
- Toggle Non-stop (session_start=0/session_end=24) — ascunde campurile de ora
- Camp `account_fraction` cu breakdown live: $capital sesiune · $X/piata + risc/trade ~$Y (din equity MT5 live)
- Sectiune Criterii Obligatorii (dropdown, intotdeauna active — nu se pot dezactiva)
- Sectiune Criterii Optionale cu 4 carduri R/R (Base/Mid/Top/Max) + praguri + risk% per nivel
- Sectiune Inchidere Vineri (friday_close_enabled + friday_close_hour)
- Sectiune Protectie Stiri (news_protection_enabled + impact_level 1/2/3 + pre/post minutes)
- Sectiune Break-Even: toggle principal (`break_even_enabled`) + parametri faze + toggle Faza 2 independent (`be_phase2_enabled`) — cand dezactivat, campurile Faza 2 dispar
- Buton Pause/Play langa delete — acelasi mecanism ca Dashboard-ul, fara restart
- Tooltips (i) pentru expire_bars (exemplu: "4 bare = 1h") si pullback_window (exemplu: "8 = 2h M15")

**App.tsx — persistenta stare taburi + memory management:**
- Dashboard + Profile: montate permanent (stare critica: editari nesalvate profil).
- Notifications, Audit, Reports, Guide: **lazy mount** — montate doar la prima vizita. Hookurile lor nu polleaza pana nu sunt deschise → reduce semnificativ numarul de requesturi si amprenta de memorie.
- **Auto-refresh la 4 ore** — `setTimeout(() => window.location.reload(), 4h)` la startup. Elibereaza toata memoria acumulata (React state + React Query cache) dupa o sesiune lunga.
- **React Query `gcTime: 90_000`** — elibereaza cache dupa 90 secunde (vs 5 minute default).
- **`refetchIntervalInBackground: false`** pe toate hookurile non-critice (reports, costs, notifications, weekly-stats, frequency-estimate). Doar `useBotStatus` si `useSessions` polleaza in background.
- Polling redus: reports/costs 30s→60-120s, notifications 10s→20s, weekly-stats/frequency 15s→60s.

**ProfilePage.tsx:** Pagina Profile. Buton Salveaza/Reset apare atat in header cat si **la finalul listei de sesiuni** (duplicat de jos pentru scroll lung). Starea editarilor (`dirty`) e pastrata cand userul navigheaza la alt tab si revine.
- **Camp `start_balance` editabil** — input numeric direct in sectiunea "Capital Initial". Include buton "↓ Import din MT5" care preia equity curenta MT5 (`useMt5Status().data.equity`) cu un singur click. Apare doar cand MT5 e conectat.
- `start_balance` este punctul de referinta fix pentru `P&L Real MT5 = equity - start_balance`. Se seteaza o singura data la pornirea pe un cont nou.

**TradingStatsPanel.tsx:** Panel statistici in Dashboard. 4 carduri: Total Semnale, Total Trades, Castiguri, Pierderi. Fiecare arata numarul agregat + "X azi" + indicator trend ▲/▼ vs ieri. Castiguri si Pierderi arata acum si breakdownul azi/ieri (`wins_today`, `wins_yesterday`, `losses_today`, `losses_yesterday` din `SessionStatus`). Click pe "Total Semnale" sau "Total Trades" expandeaza breakdown per sesiune (ascunde sesiunile cu 0 activitate).
- **P&L Real MT5** — `equity MT5 − start_balance din profil`. Sursa de adevar absolut, include tot.
- **Comisioane + Swap** — din `/reports/costs`. Dezagregat: com: X $ · swap: Y $.
- Cardul "P&L Bot (partial)" a fost eliminat — datele partiale (fara backfill complet) induceau in eroare.
- Sesiunile OBS (execute_trades=False) excluse din TOATE agregerile.

**AuditPage.tsx:** Tab Audit (fostul Istoric). Doua sectiuni: **Descarcari Date** si **Backteste**.
- *Descarcari Date*: `DownloadJobRow` expandabil per simbol — arata alias MT5 folosit (ex: "MT5: DE40"), ✓/⚠/✗ per timeframe, warning scroll daca istoricul nu e incarcat. Joburile persista in `data/download_jobs.json`.
- *Backteste*: Joburi grupate In rulare / Erori / Finalizate. Rezultate expandabile cu tooltips, snapshot parametri, `CapitalSummary`. Erori clasificate: no_data / no_data_range / no_trades / generic. Persista in `data/backtest_jobs.json`. Cand break-even a fost activ, `ResultsGrid` afiseaza si statistici BE: "Faza 1: N", "Faza 2: N", "Total BE: N din M trades" (din campurile `be_lock_count` / `be_lock2_count`).
- **Frecventa trades:** `ResultsGrid` afiseaza un rand "Frecvență: X.X trades/săpt · Y.Y trades/lună · Z zile testate" calculat din `total_trades / (days / 7)`. Identic si in `HistoryPage.tsx`.
- **Search bar:** Input de cautare in headerul sectiunii Backteste. Filtreaza `filteredJobs` cu `useMemo` dupa `session_label`, `markets[]`, `direction`, `entry_tf` (case-insensitive). Afiseaza counter "X / total" cand search e activ.
- **Multi-select delete:** Checkbox per job (erori + finalizate). "Selecteaza tot" (toggle global). Buton "Sterge N selectate" cu `confirm()` dialog. Apeleaza `DELETE /backtest/jobs/{job_id}` per job selectat. Selectia se reseteaza automat dupa stergere.

**NotificationsPage.tsx:** Tab nou intre Profile si Audit. Afiseaza toate notificarile din `data/notifications.json` (max 200 la un apel). Functionalitati:
- Filtre categorie: Toate / Ordine / Tranzactii / Semnale / Stiri / Sesiuni / Bot / Sistem (apar doar categoriile cu intrari)
- Grupare pe zile: Azi / Ieri / data completa (luni, 12 iunie etc.)
- Card per notificare: icon categorie colorat, dot necitit, titlu (prima linie), preview corp (truncat), buton "Extinde/Ascunde", timp relativ (acum/5m/2h/3z) + timp absolut
- Actiuni: Marcheaza citite (header), Sterge tot (cu confirmare), Sterge individual (X la hover)
- Badge in NavBar cu numarul necitite — dot albastru pulsant

**ReportsPage.tsx:** Tab nou dupa Audit. 4 sub-taburi:
- **Tranzactii**: Tabel paginat (50/pagina) cu toate outcomes din toate sesiunile. Filtre: status (TP/SL/Deschis/Expirat/Vineri/Stiri/Toate), directie (LONG/SHORT/Ambele). Coloane: timp, sesiune, simbol, directie, entry, exit, result_r, pnl_usd, status.
- **Piete**: Clasament piete dupa Total R (descrescator). Trofee pentru top 3. Coloane: simbol, sesiuni active, trades, win rate, expectancy, P&L USD. Summary cards: cel mai bun simbol, cel mai slab, total P&L.
- **Uptime Bot**: Tabel start/stop din `data/bot_uptime_log.json`. Coloane: data start, data stop, durata formatata (Xh Ym). Summary: total sesiuni, uptime acumulat, ultima pornire. Durata calculata din `duration_sec`.
- **Modificari**: Accordion per eveniment din `data/session_changes_log.json`. Expandabil: lista sesiunilor modificate cu campuri `{field: from → to}`. Arata profilul, data si numarul de campuri schimbate.

**NavBar.tsx:** 6 tab-uri: Dashboard / Profile / Notificari / Audit / Rapoarte / Ghid. Badge notificari necitite pe "Notificari" (dot albastru pulsant + count). Badge joburi in curs pe "Audit" (dot pulsant + count activ, count gri finalizate). Contine si toggle Autostart Windows.

**App.tsx — persistenta stare taburi:** 6 taburi montate odata cu CSS `hidden`. `type Tab = "dashboard" | "profile" | "notifications" | "audit" | "reports" | "guide"`. Componentele `NotificationsPage` si `ReportsPage` sunt incluse ca div-uri `hidden` — starea lor (filtru activ, tab activ) supravietuieste navigarii.

---

## Configurare autostart Windows

```powershell
# Necesita Administrator — creeaza doua task-uri in Task Scheduler:
# TradingBot-MT5 (MT5 la login) + TradingBot-RunAll (run_all.py + 45s delay)
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
& "c:\trading-bot\scripts\setup_autostart.ps1"

# Dezactivare autostart (sterge ambele task-uri):
& "c:\trading-bot\scripts\remove_autostart.ps1"
```

Autostart-ul poate fi activat/dezactivat si din NavBar-ul din UI (toggle cu UAC elevation automat — necesita acceptarea promptului de Administrator).

**`scripts/setup_autostart.ps1` — detectare Python in sesiuni elevate:** Foloseste `py.exe` (Python Launcher, `C:\Windows\py.exe`) in loc de `python` pentru a gasi Python. `python` nu este disponibil in sesiuni elevate (UAC) cand e instalat ca Windows Store alias — `py.exe` este system-wide si functioneaza intotdeauna. API-ul adauga `-NoExit` la `Start-Process` pentru a tine fereastra deschisa dupa terminarea scriptului (vizibil si la erori).

Variabilele Telegram (`TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`) se seteaza in User Environment Variables Windows (nu in .env) — sunt citite de `start_bot.bat` din registry. In UI, configurarea se face din sectiunea Telegram Settings (accordion in ProfilePage). Butonul "Trimite mesaj de test" (`POST /settings/telegram/test`) verifica conexiunea real-time.

**setup.bat** — Instalare Python/Node/Git via winget. Daca se instaleaza ceva nou, deschide automat o fereastra CMD noua cu PATH proaspat si continua instalarea pip/npm fara interventia utilizatorului (nu mai necesita rulare de doua ori). Foloseste `py` (Python Launcher) in loc de `python` pentru a evita Windows Store alias.

**start_ui.bat** — Script dublu-click pentru pornire dashboard fara IDE. La fiecare rulare: opreste instante vechi (taskkill dupa titlu + `scripts/kill_ports.ps1` pe porturile 8000/5173), deschide fereastra `TradingBotAPI` (uvicorn) + `TradingBotUI` (npm dev), asteapta 8s, verifica porturile si deschide browserul. Afiseaza diagnostice complete la fiecare pas. Fisierele `.bat` din proiect folosesc CRLF obligatoriu — CMD.EXE pe Windows esueaza silentios cu LF-only dupa `chcp 65001`. Cand ruleaza in Windows Terminal, ferestrele noi se deschid ca taburi noi (nu ferestre separate).

**`scripts/kill_ports.ps1`** — Opreste procesele care asculta pe porturile date (`Get-NetTCPConnection` → `Stop-Process`). Apelat din `start_ui.bat` ca fallback dupa taskkill-ul pe titlu. Separat intr-un `.ps1` deoarece CMD nu poate pune pipe-uri (`|`) in string-urile PowerShell inline din `start ...`.
