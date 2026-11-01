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
python -m ai_engine.selftest           # verificari (incl. test_consensus + consiliu LIVE pe Ollama)
python -m ai_engine.doctor             # diagnostic surse AI: verifica INFERENTA Ollama (nu doar reachable) + testeaza toate sursele
python -m ai_engine.report             # scorecard + decizii + outcomes
python -m ai_engine.report --councils  # + transcripturile dezbaterilor AI
python scripts/test_multi_council.py   # 44 teste: consens multi-council + roluri noi (fara Ollama/MT5)

# Daily Engine — intraday ORB la deschiderea Londrei / New York, mod SHADOW (zero ordine)
python -m daily_engine                 # manual (sau butonul din tab-ul Daily Engine)
python -m daily_engine.selftest        # 31 teste: strategie + ECHIVALENTA cu backtestul pe tot istoricul M5 + DST + motor simulat
python scripts/test_engine_lifecycle.py   # 13 teste: /engines start/stop verificat + watchdog Daily (offline)
python scripts/test_trading_pace.py       # 13 teste: ritmul de tranzactionare pe engine (offline)
python scripts/test_position_sizing.py    # 38 teste: dimensionare comuna, Custom = AI = Daily (offline)
python scripts/test_reports.py            # 37 teste: rapoarte saptamanal/lunar, program + failure handling (offline)
python scripts/research_daily/orb_compare.py   # cercetarea: 4 piete x 3 ferestre x 18 variante (M5, costuri reale, M0)

# Punte Telegram — comanda botul de pe telefon (proces STANDALONE, aditiv, optional)
start_telegram_bridge.bat              # dublu-click: porneste puntea
python -m telegram_bridge              # manual
python -m telegram_bridge.selftest     # 33 teste offline (fara Telegram/MT5/Claude)
```

Nu există test suite sau linter configurat. Validarea corectitudinii se face prin reproducerea numerelor baseline (vezi mai jos). Pentru M0, `python -m m0.selftest` verifica reproducerea baseline-ului (280 trade-uri) + verdictele.

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
telegram_bridge/   — punte Telegram → App → Claude (daemon STANDALONE, optional, aditiv)
```

### `telegram_bridge/` — comanda botul de pe telefon (proces separat, aditiv)

Daemon standalone care asculta chat-ul Telegram (getUpdates long-poll — SINGURUL consumator din proiect; restul codului trimite doar sendMessage) si raspunde pe 4 niveluri: comenzi instant (`/status`/`/raport`/`/piete`/`/pauza`), `ai <q>` (surse AI existente prin `ProviderRegistry`), `claude <q>` (Claude Code headless `-p`, read-only allowlist, `--resume` prin reply), `claude! <q>`+`CONFIRM` (scriere, 2 pasi, gated de `allow_writes`). **Izolare totala:** citeste doar fisiere de stare (`data/ai/status.json`, `data/*.pid`) + API-ul local prin HTTP; NU importa/modifica bot/motor/API, NU deschide a doua conexiune MT5. Whitelist HARD pe chat_id. Fallback claude: CLI → Claude API → surse AI → mesaj onest. Config: `data/telegram_bridge.json` (gitignored, exemplu in `telegram_bridge/config.example.json`); credentiale din `data/telegram_config.json`. Teste: `python -m telegram_bridge.selftest` (49, offline). Doc: `docs/TELEGRAM_BRIDGE.md`. Ghid UI: sectiunea 13.
- **Control din UI + autostart (2026-07-20):** router `api/routers/telegram_bridge.py` (`/telegram-bridge/status|start|stop` + `/autostart/status|enable|disable`, mirror al `/ai/*`) — puntea scrie `data/telegram_bridge.pid` + `data/telegram_bridge_status.json` la pornire; API-ul le citeste. UI: `TelegramBridgeCard.tsx` in Profil (langa `TelegramSettings`), afisat DOAR daca Telegram e configurat — buton Start/Stop + toggle autostart. Autostart: `scripts/setup_autostart_bridge.ps1`/`remove_autostart_bridge.ps1` (task `TradingBot-TelegramBridge`, RunLevel Limited, la login+60s; genereaza `telegram_bridge/start_bridge_auto.bat`; pur ASCII). Dezactivat implicit.
- **Mod EDIT de la distanta:** comanda `/edit on|off|status` comuta `allow_writes` LIVE (persistat via `config.set_config_value`, aplicat pe cfg-ul partajat de toate routerele, fara restart) — pentru fix critic de pe telefon. Whitelist-ul deja filtreaza expeditorul.
- **Mod inactiv:** long-poll = near-zero cost intre mesaje (blocheaza pe socket, trezire instant); dupa `idle_sleep_after_s` (1h) marcheaza `idle` in status (vizibilitate), fara pierdere de reactivitate.
- **Al doilea canal Matrix/Element (EU, gratuit — OPTIONAL, off by default):** `matrix_io.py` = client C-S API pe urllib (whoami/sync/send), semnatura `send` compatibila cu `TelegramClient` → **ACELASI Router** (comenzi identice). Ruleaza in thread separat in procesul puntii (`bridge.run_matrix` + `_guarded_matrix`), pornit DOAR daca `config.matrix_ready` (matrix_enabled+homeserver+room+token). Complet IZOLAT: tot corpul in try/except → un esec Matrix (retea/homeserver) NU atinge Telegram. Camera trebuie NEcriptata (E2E nesuportat). Token in `data/matrix_config.json` (gitignored). **Config din UI:** `GET/PUT /telegram-bridge/matrix-config` (non-secrete → telegram_bridge.json, token → matrix_config.json) + `MatrixSettings.tsx` in Profil (dupa `TelegramBridgeCard`) — homeserver/room/token/allowed + toggle. Pasi telefon: `docs/TELEGRAM_BRIDGE.md` + Ghid sect.13. **Live-testat de user la prima folosire** (nu pot testa fara contul Matrix); logica testata offline in selftest.
- **Editor de REZERVA gratuit (fallback la `claude!`):** cand Claude CLI e indisponibil, fluxul de scriere foloseste un editor liber — `executors.run_aider` (Aider open-source; foloseste `aider_model` implicit `groq/llama-3.3-70b-versatile`, cu cheia `groq` injectata automat din `data/ai/providers.json` via `_aider_env` dupa prefixul modelului) sau `run_copilot_write`. `reserve_editor_name`/`available_editors` decid disponibilul; `/editors` il arata. `_task_plan`: Claude indisponibil → `add_pending(..., backend="aider")` + cod → `CONFIRM` → `run_reserve_editor`. Off-switch: `editor_fallback_enabled`. Teste: `telegram_bridge.selftest` (57).

### Fluxul de date

**Backtest:**
`CsvDataSource.load_bars()` → `strategy.preparation._enrich()` → `engine/portfolio.run_portfolio()`

**Live:**
`Mt5DataSource.load_bars()` → `strategy.preparation._enrich()` → `signal_generator._check_signals()` → `signal_generator._place_order()` (MT5 pending order)

**API:**
FastAPI servit pe port 8000. Frontend-ul React pe port 5173 face requests la `/api/*`. Backtestul rulează asincron — `POST /backtest/run` returnează `job_id`, clientul polleaza `GET /backtest/{job_id}` la 2s interval.

### `strategy/preparation._enrich()`

Calculeaza toti indicatorii o singura data, identic pentru backtest si live. Input: bare M15 + bare M30 brute. Output: DataFrame M15 cu coloanele `trend` (1/-1/0 din EMA200 pe M30), `ema_fast/mid/slow` (8/20/50 pe M15), `rsi`, `atr`, `swing_high`, `swing_low`. Separarea adaptor/strategie este intentionata — adaugarea unui nou broker nu necesita modificari in strategy/.

**Trend TF mare echivalent cu live (fix lookahead, 2026-10-31):** in live bara TF mare curenta e IN FORMARE (close = pretul curent), deci trendul nu vede viitorul; in CSV aceeasi bara are close-ul FINAL (pana la ~23h in viitor pe H1/D1) → backtestul vedea viitorul. `_enrich(..., trend_live_equivalent=True)` calculeaza exact ce vede live-ul la inchiderea barei de intrare j: `sign(close_j − EMA_trend al ultimei bare TF INCHISE)` (identitate exacta pentru EMA recursiv `adjust=False`; verificat 0 nepotriviri pe 1200 bare simulate live). Activat automat de `prepare_symbol[_tf]` cand sursa are `historical=True` (`CsvDataSource`); **calea live (`Mt5DataSource`, `_enrich` direct din signal_generator/perception) e byte-identica** (`assert_frame_equal`). Cu `CsvDataSource.historical=False` se reproduce exact vechiul baseline (284 trades, +0.025R). Baseline-urile noi (fara lookahead) au fost aprobate de user pe 2026-10-31.

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

**R:R pe 3 niveluri fixe per piata (2026-10-31) — inlocuieste ladder-ul pe criterii pe sesiunile LIVE:** `rr_level` = `short` (2R) / `standard` (3R) / `extended` (4R), acelasi TP pentru TOATE strategiile pietei (pullback, IB, Flag) si risc constant 1% (risc la 4R = tot 1%, decizia userului). Implementat ca MIGRARE de date (`scripts/migrate_rr_levels.py`): nivelul scrie aceeasi valoare in `r_base/mid/top/max` + `inside_bar_r_ratio` + `flag_r_ratio` si 1% in `risk_*` → backtest/M0/live folosesc campurile existente, zero cod nou de trading. Nivel ales per piata pe backtest-ul fara lookahead cu criteriul ROBUST `max(min(train, test))`: 2R = S1,S5,S7,S11,S12,S14,S15,S18 · 3R = S8,S17,S19 · 4R = S9,S16,S22. Sesiunile de observatie pastreaza ladder-ul (UI le semnaleaza). `expire_bars` = 4 pe TOATE sesiunile (camp scos din UI). Criteriile RSI/EMA raman filtre, nu mai schimba TP-ul; ADX D1 scos din UI. Backup profil: `data/profiles/standard.json.bak-*` (local).

**Verdict M0 in UI:** `GET /sessions/m0-verdicts` (din `data/m0_audit.csv`) → badge „M0 KEEP/OBSERVE/DEMOTE" in antetul fiecarei sesiuni din Settings, rosu „⚠ live" cand o sesiune DEMOTE executa ordine reale.

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

- `m0/session_runner.py` — mapeaza o sesiune din profil → params `run_portfolio` (**copiat verbatim** din `api/routers/backtest.py`; `SPREAD_DEFAULTS` duplicat — tine-l sincronizat daca cel din API se schimba). Suporta optional fereastra de date (pentru fold-uri). Validat: reproduce baseline-ul documentat (280 trade-uri).
- `m0/stats.py` — stationary block bootstrap (P(edge>0) + CI), Probabilistic/Deflated Sharpe cu prag de "trial-uri de breakeven" N*, consistenta pe 8 fold-uri + trend Spearman.
- `m0/robustness.py` — **sursa unica de adevar**: `evaluate_trades(df, split_time)` + `classify()` + `to_result_payload()`. Folosit ATAT de `m0.audit` CAT si de worker-ul de backtest din API, ca sa nu diverge. Verdict: KEEP (exp>0 ȘI P(edge>0)≥95% ȘI ≥60% fold-uri pozitive) / DEMOTE (exp≤0 SAU P(edge>0)<75%) / OBSERVE / INSUFF (<30 trade-uri).
- `m0/audit.py` — ruleaza toate cele 20 sesiuni → `data/m0_audit.csv` + `docs/M0_RESULTS.md`.
- `m0/selftest.py`, `m0/validate_runner.py` — verificari de integritate.

**Integrare in Audit tab:** `api/routers/backtest.py::_run_backtest_job` apeleaza `evaluate_trades` (n_boot=2000) pe seria de trade-uri si adauga cheia `robustness` in rezultat (fail-open — daca esueaza, backtestul se salveaza normal fara verdict). Frontend: `RobustnessResult` in `types.ts`, banner `RobustnessBanner` in capul lui `ResultsGrid` din `AuditPage.tsx` (verdict + P(edge>0) + Fold+ + N* + CI, cu tooltips), documentat in `GuidePage.tsx`. **Necesita restart API** (fara `--reload` codul vechi ramane in memorie).

### `ai_engine/` — motor de trading autonom AI (separat de botul pe reguli)

Motor experimental care isi alege singur strategia: perceptie numerica la fiecare bara M15 (gratuit) → consiliu de 4 agenti AI pe trigger-uri (regime flip, breakout tension, vol spike, news window, heartbeat 24h) → decizie JSON validata pe rails hard → executie DOAR pe cont DEMO. Vezi [docs/AI_ENGINE.md](docs/AI_ENGINE.md).

- **Surse AI multiple (v0.3):** registru deschis in `providers.py` — adaptori `ollama` / `anthropic` (SDK oficial) / `gemini` / `openai_compatible` (Groq, DeepSeek etc.), cu interfata comuna `chat_json`. Rolurile consiliului se distribuie pe surse (`role_assignments` in config). `ProviderRegistry` = sanatate per sursa + failover automat (quota→6h pauza, 429→60s, retea→2min, 401→dezactivat pana la retest) + revenire lazy; Ollama e safety-net (mereu enabled, nu se sterge). Chei API in `data/ai/providers.json` (gitignored). Hot-reload per iteratie (`registry.refresh`) — schimbarile din UI NU necesita restart de motor. Transcript per rol: `_provider`/`_latency_s`/`_fallback_from`. **Monitor sanatate surse (2026-07-17):** `POST /ai/providers/test-all` testeaza TOATE sursele activate in PARALEL (thread pool) → per sursa {ok, latency, detail, kind} + sumar (healthy/failed/roles_at_risk/all_down). UI: buton "🩺 Testeaza sursele" in `AiProvidersCard` cu panou de diagnostic. Motorul (`engine._monitor_sources_health`) trimite Telegram cand `registry.usable_sources()` devine gol (TOATE sursele picate/quota, inclusiv Ollama → toate deciziile WAIT) si la revenire, o data per tranzitie. Cercetare surse gratuite noi: `docs/AI_PROVIDERS_RESEARCH.md`. UI: cardul "Surse AI" in tab (`AiProvidersCard.tsx`) — sectiunea "Roluri → surse" listeaza TOATE cele 6 roluri, inclusiv cele optionale `quant`/`devils_advocate` (2026-07-16; inainte lipseau din UI si mergeau mereu pe fallback-ul ollama — backend-ul le suporta deja, cu acelasi failover ca rolurile obligatorii). API: `GET/PUT /ai/providers`, `POST /ai/providers/test`. Plan: `docs/PLAN_SURSE_AI_MULTI_PROVIDER.md`. **Descoperire dinamica de modele:** `list_models()` pe toti adaptorii + `POST /ai/providers/models` (`{name}` pt sursa salvata SAU `{type, base_url, key}` pt formularul de adaugare, inainte de salvare); in UI campul model e combobox (input+datalist) populat la focus, cu buton refresh. **User-Agent obligatoriu (`_USER_AGENT` in `_http_json`):** fara header, WAF-ul Cloudflare al unor API-uri (ex: Groq) respinge cu 403 "error code: 1010" — fals-pozitiv de bot, nu cheie gresita; clasificat `network` (pauza 2 min), NU `auth` (care ar dezactiva sursa pana la retest manual).
- **LLM local gratuit:** Ollama + `qwen3:8b` pe GPU (`think:false` obligatoriu — altfel 10-15x mai lent) — sursa default a consiliului.
- **Failure mode „Ollama reachable dar inferenta moarta" (`server_error`):** o instalare Ollama corupta/partiala (update intrerupt) sau un binar `llama-server.exe` pus in carantina de antivirus face ca `/api/tags` sa raspunda 200 (model listat) DAR `/api/chat` sa dea 500 „llama-server binary not found". `OllamaProvider.available()` verifica DOAR `/api/tags`, deci raporta sanatos gresit (fals-pozitiv) → 500-ul era clasificat drept `network` generic (retry la 120s la nesfarsit) → toate deciziile WAIT cu botul aparent OK. **Fix:** (1) `is_ollama_backend_broken()` + reclasificare in `OllamaProvider.chat` → `kind="server_error"` (cooldown 300s, `paused` nu `disabled` → auto-repara in ≤5 min dupa reinstalare) cu mesaj ACTIONABIL; prins si daca versiunea raporteaza 200+`{"error":...}`. (2) `OllamaProvider.probe()` / `ProviderRegistry.default_probe()` = verificare de inferenta reala (un apel mic), folosita la pornirea motorului — daca Ollama e reachable dar inferenta e moarta, motorul NU pica (ramane sus, degradeaza pe cloud, se auto-repara) dar PAGINEAZA operatorul o data + logheaza. (3) `python -m ai_engine.doctor` = diagnostic + remediere exacta. **Remediere:** reinstaleaza Ollama de pe ollama.com/download; verifica antivirusul; `ollama run <model> "ok"`. Test: `ai_engine.selftest::test_ollama_backend_broken`.
- **Consiliu (`council.py`):** Analist Tehnic → Analist Macro → Risk Manager (VETO absolut, aplicat in cod, nu de model) → [Analist Cantitativ] → [Avocatul Diavolului] → Head Trader (JSON strict, retry cu feedback la JSON invalid). Orice eroare LLM → WAIT (fail-safe). Rularea rolurilor e centralizata in `DebateRunner` (buget de timp + transcript + rutare pinned/assignments), reutilizat de `convene` SI de consiliul de revizie din `trade_filter`.
- **Semnal de regim trend/chop in briefing (`regime_aware`, default ON — 2026-08-08):** consiliul primea trend/ATR dar NU cat de choppy e piata, deci lua breakout-uri la marginea range-ului intr-o saptamana choppy (false break → reverse → SL; a fost cel mai mare tipar de pierdere, ex: 0/6 trade-uri intr-o saptamana cu FX efficiency ratio ~0.03-0.05). Fix: `perception.build_snapshot` calculeaza **Kaufman Efficiency Ratio** (20 bare M15) + percentila + eticheta `CHOPPY/TRENDING/NEUTRAL` (praguri <0.15 / >=0.35, calibrate pe distributia reala M15, universale FX/crypto/metale — `_efficiency_ratio`/`_regime_label`). `render_text(s, regime_aware=True)` adauga o linie factuala cu ER+regim; **cu `regime_aware=False` briefing-ul e byte-identic cu inainte** (comutabil din config `regime_aware`, hot-reload; `engine.py` paseaza flag-ul). Prompturile Technical/Risk/Head au clauze de regim (in chop: coboara increderea, size-down la 0.0025, prefera WAIT) — inerte cand lipseste linia de regim. Snapshot-ul stocheaza mereu campurile (analiza), indiferent de flag. Simulare LIVE: acelasi breakout → CHOPPY WAIT conf 40 / TRENDING OPEN conf 71. Teste: `python scripts/test_regime_signal.py` (16, offline) + selftest consiliu LIVE. Necesita restart motor.
- **Incredere = MEDIA MEMBRILOR consiliului + gate pe prag (2026-07-16):** `council.council_confidence(transcript)` = media rolurilor care raporteaza confidence (technical/macro/[quant]/head_trader; risk si devils_advocate nu au). `convene` seteaza `decision["confidence"]` la aceasta medie (head-ul ramane in `decision["head_confidence"]` + transcript). **`consensus_threshold` ("bara" din UI, default 70) se aplica si consiliului UNIC** (`orchestrator.decide`): media sub prag → WAIT `[Sub pragul de încredere]` — inainte, pragul exista doar in modul multi-council si se plasau ordine cu media membrilor ~60% la prag 70%. Acelasi gate cand revizorii pica si decide primarul singur. Filtrul pre-trade al botului NU e afectat (pragurile lui 50/70/85 raman calibrate pe confidence-ul Head Trader-ului per consiliu). UI: "conf medie X%" in DecisionRow. Teste: `test_multi_council.py` sectiunea 9.
- **Consens multi-council + roluri suplimentare (OPTIONAL, off by default) — `consensus.py` + `orchestrator.py`:** pana la 3 consilii pe surse AI distincte; increderile se combina prin **media efectiva + veto absolut** (`consensus.combine`: `effective = confidence daca aproba altfel 0`; orice veto hard valid → respins; altfel aprobat ⟺ media >= `consensus_threshold`, default 70). **Un consiliu = comportamentul de dinainte** (media unui numar = numarul). Motor autonom (`orchestrator.decide`): primarul construieste trade-ul (`convene`), revizorii il revizuiesc (`trade_filter.review_trade`), consens gate-uieste executia; revizori picati → decide primarul (fail-tolerant). Surse pinned fara failover (`ProviderRegistry.call_role_pinned`) — un consiliu nu poate deveni duplicatul altuia. Config (motor): `council_primary/secondary/tertiary_source` + `consensus_threshold` + `role_quant_enabled`/`role_devils_advocate_enabled`. Roluri noi: `quant` (EV/win-prob/SL-vs-ATR) si `devils_advocate` (pre-mortem, contra-teza) in `role_assignments`. Ledger transcript: chei `_consensus`/`_reviewers`. Hot-reload (fara restart). Teste: `scripts/test_multi_council.py` (44). Doc: `docs/MULTI_COUNCIL_CONSENSUS.md`.
- **Rails hard (`executor.py::validate_decision` + clamp in `config.py`):** geometrie SL/TP, RR≥1, SL≤5×ATR, stop zilnic -3R, risc≤1%. **Expunere ANGAJATA:** rail-ul `max_open_positions` (default 3) numara pozitii deschise **+ ordine pending** (`n_committed`), nu doar pozitii — altfel la cold-start (ledger gol) heartbeat-ul convoaca toate pietele deodata si s-ar plasa mai multe ordine stop decat limita (toate cu 0 pozitii deschise). Ordinele stop se plaseaza secvential per bara, deci contorul creste pe masura ce se plaseaza. LLM-ul propune, rails-urile dispun. **Fara pyramiding (`symbol_committed`):** `validate_decision` respinge un OPEN daca exista deja o pozitie SAU un ordin pending AI pe ACEL simbol — plafonul global `max_open_positions` nu impiedica stivuirea pe acelasi simbol (3 ordine pe acelasi setup incap sub 3), asa ca gate-ul per-simbol o interzice explicit (defense-in-depth peste guard-ul de instanta unica; a prins bug-ul 3x XRPUSD din instantele multiple).
- **Inchidere weekend (`engine.py::_weekend_guard`):** pentru pietele FX/indici (cripto exceptat — vezi `executor.is_crypto`), la Vineri de la `weekend_close_hour` (default 22, ora RO via `now_local`) + toata Sambata/Duminica: motorul inchide pozitia AI + anuleaza pending-urile pe acel simbol si SARE consiliul (nu deschide nimic). Deschiderea se reia AUTOMAT Luni. Config: `weekend_close_enabled`/`weekend_close_hour`. Aliniat cu `skip_weekdays {5,6}` + friday_close al botului. XRPUSD/BTCUSD ruleaza non-stop.
- **Buget de timp consiliu (`council.py::COUNCIL_TIME_BUDGET_S`, default 240s):** verificat INTRE roluri — o sursa cloud lenta/rate-limited nu poate bloca bucla motorului dincolo de o bara; depasit → ProviderError → WAIT (fail-safe). Aliniat cu `trade_filter.TIME_BUDGET_S`. Suprascriere: cheia config `council_time_budget_s`.
- **Geometrie stop (rejectii asteptate, NU bug):** `validate_decision` respinge un ordin stop pe partea gresita a pretului — BUY_STOP la/sub pret, SELL_STOP la/peste pret (ex: "SELL_STOP 1.14418 peste pretul curent 1.14206"). Sunt LLM-ul care confunda ocazional stop cu limit; rail-ul le prinde, niciun ordin gresit nu ajunge in piata. Promptul Head Trader are o sectiune "CRITICAL STOP DIRECTION" care reduce frecventa.
- **Veto cod-enforced + reparare TP (`council.py::_sanitize`):** veto-ul Risk Manager e onorat DOAR cu un cod de risc valid (NEWS_IMMINENT/DAILY_STOP/MAX_POSITIONS/EXTREME_VOL/WEEKEND_GAP/BAD_GEOMETRY); veto necalificat → prudenta (risc redus la 0.25%), nu blocaj (fix pentru paralizia 29/29 veto observata 2026-07-09). `_repair_tp` recalculeaza TP la `target_rr` (default 2.0R) cand modelul propune RR<min_rr (SL structural pastrat) — evita respingerea unui setup directional bun pe TP prea aproape.
- **Izolare totala:** magic 770015 + comment "AI-{id}", filtrare stricta pe magic — nu vede/atinge pozitiile sesiunilor pe reguli. `executor.connect()` refuza non-DEMO (RuntimeError).
- **Guard de instanta unica (`engine.py::_acquire_single_instance`):** DOUA instante ale motorului = expunere dublata pe magic 770015 + pozitii care se calca (fiecare vede/inchide pozitiile celeilalte prin acelasi magic) + contentie pe ledger. Inainte, `run()` scria PID-ul fara sa-l verifice, deci un `python -m ai_engine` manual / dublu-click pe `.bat` / task de autostart suprapus peste o instanta vie pornea o a doua (observat live: 3 instante simultan). Fix: la pornire, INAINTE de a atinge MT5/Ollama, `run()` obtine un **mutex Windows numit** (`Global\TradingBot_AIEngine_SingleInstance`, fallback `Local\`; atomic, eliberat automat de OS chiar si la taskkill) SI verifica fisierul PID (`_other_engine_pid`, plasa cross-sesiune / pentru instante pe cod vechi fara mutex). Daca alta instanta e detectata → NU porneste (log + Telegram „a doua instanta BLOCATA"), nu atinge MT5. `api/routers/ai_engine.py::ai_start` are propriul check PID (409); watchdog-ul are propriul anti-duplicat (`watchdog.pid`); guard-ul din `run()` e plasa comuna care prinde TOATE caile de pornire. Test: `ai_engine.selftest::test_single_instance`. **Remediere daca deja ruleaza multiple:** `taskkill` pe PID-urile orfane (cele care nu sunt in `data/ai/ai_engine.pid`), pastreaza-l pe cel din fisier.
- **Ledger SQLite (`data/ai/ledger.db`):** snapshots, transcripturi complete de consiliu, decizii, outcomes (R/pnl via pattern hedging-safe order→position_id→deals). `python -m ai_engine.report` = scorecard.
  - **`scorecard()` include `wins`/`losses` (2026-07-16):** wins = `result_r>0`, losses = `result_r<0` (break-even exact 0 nu e nici una); si in `scorecard_by_symbol` + fallback-ul din `ai_status` (tinut sincron). UI: cardul "Win / Loss" in scorecard + `Nt (xW/yL)` pe randul pietei.
  - **`scorecard()` — closed_trades numara DOAR tranzactii reale** (`status IN ('TP','SL','closed')`). Ordinele `expired`/`cancelled` (plasate dar niciodata activate) au `result_r=0.0` (NU None) in outcome, deci un filtru naiv `WHERE result_r IS NOT NULL` le numara gresit ca tranzactii — inflateaza closed_trades si trage expectancy spre 0. Fix in `ledger.scorecard()` SI in fallback-ul din `api/routers/ai_engine.py::ai_status` (trebuie sincronizate). Outcomes-urile expirate raman vizibile in lista `/ai/outcomes` (transparenta), doar nu se numara. Necesita **restart motor** (scorecard-ul e calculat in proces si scris in status.json la fiecare iteratie).
- **Reutilizeaza:** `strategy.preparation._enrich` (perceptie), `live.news_guard._fetch_forexfactory` (calendar, cu cache TTL 10 min in perception), `api.telegram.send_message` (notificari), `Mt5DataSource` (bare + enforcement demo).
- **Capitalul motorului (`capital_sync_mt5` + `capital_usd`, 2026-07-16):** baza de sizing e `executor.capital_base(cfg)` — sync ON (default) = equity-ul REAL MT5 la fiecare ordin (identic cu inainte); sync OFF = capital FIX alocat AI-ului (`capital_usd`, clamp 10..1M), PLAFONAT la equity cand MT5 e disponibil (typo-safe). Per piata se aplica `capital_fraction` peste aceasta baza. Campurile per piata goale = "auto" (riscul il decide consiliul in rails, capitalul = 100% din baza). UI: cardul "Capital AI Engine" (toggle sync + input $ + warning cand capitalul alocat > equity); API: `PUT /ai/config` valideaza. Hot-reload per iteratie. Teste: `python scripts/test_ai_capital.py` (22, incl. place() end-to-end pe MT5 simulat).
- **Config PER PIATA (`market_overrides` in config.json, OPTIONAL, default gol = comportament identic):** per simbol: `capital_fraction` (0.05-1.0 — baza de sizing devine equity×fraction; NOTA: la cont mic lotul minim al brokerului domina), `risk_pct` (cap per trade, clamp la `risk_pct_max` global), `max_rr` (TP peste plafon e ADUS la plafon de `council.clamp_tp_to_max_rr`, oglinda lui `_repair_tp`), `max_daily_loss_R` (stop zilnic PE PIATA, gate in `validate_decision` via `market_state`), `max_trades_per_day` (anti-overtrading, numarat cu `ledger.placed_count`), `fixed_lots` (0.01-100, 2026-07-16 — volum FIX per ordin, inlocuieste sizing-ul dinamic pe risc; `executor.snap_fixed_lots` aliniaza la volume_min/step/max cu floor+epsilon — `0.5//0.01=49` era bug float; rail-ul de marja ≤40% ramane; consiliul e informat in briefing; UI coloana "Loturi" + estimare USD live via `POST /ai/lot-info` — marja + $/unitate de pret din MT5, prin mt5_pool; **`lot-info` SNAP-uieste la volume_min/step/max al brokerului si intoarce `effective_lots`/`snapped`/`below_min`** (2026-07-17): pe XRPUSD volume_min=100, deci 0.01 loturi introduse aratau marja triviala $0.01 scaland liniar — acum arata costul volumului REAL plasat (100 loturi, ~$54) cu avertisment "sub minim"), `isolated` (piata in observatie: exclusa din scorecard-ul principal — `scorecard(exclude_symbols=...)`; datele raman per piata in `scorecard_by_symbol`, scrise in status.json + afisate in cardul UI). Consiliul PRIMESTE limitele in briefing (`engine._market_limits_text`) DOAR cand piata are override — piata fara override are briefing byte-identic (zero drift LLM). Sanitizare/clamp centralizate in `config.sanitize_market_overrides` (folosita si de API `PUT /ai/config`). Rezolvare: `config.market_cfg(cfg, symbol)`. `/ai/decisions` si `/ai/outcomes` accepta `?symbol=`. UI: cardul „Limite per piata" in tab-ul AI Engine. Teste: `python scripts/test_market_config.py` (34). Hot-reload per iteratie (fara restart).
- **Performanta — interogari MT5 deduplicate (behavior-preserving):** `_update_outcomes` citea `positions_get`+`orders_get` de N ORI (o data per decizie deschisa); acum le citeste O SINGURA DATA per bara si le paseaza la `check_decision_outcome(dec, cfg, positions, pending)` (snapshot consistent, N→1). `_process_market` citea pozitiile de doua ori (o data pt trigger via `open_position_for`, o data pt expunere via `ai_positions`) — la microsecunde distanta, inainte de consiliu; acum o singura citire refolosita. `_update_outcomes` sare complet MT5 cand nu exista decizii deschise. Zero schimbare de comportament (aceleasi valori, aceeasi stare). Test: `ai_engine.selftest::test_outcome_prefetch`.
- **Performanta API (`api/routers/ai_engine.py`):** `/ai/decisions` facea N+1 interogari (1 pt decizii + 1 outcome per decizie); acum outcome-urile se aduc intr-o singura interogare `WHERE decision_id IN (...)` (ultimul per decizie castiga). Toate endpointurile care deschid SQLite (`ai_status` fallback, `decisions`, `council`, `outcomes`) folosesc `contextlib.closing(_db())` — conexiunea se inchide GARANTAT si pe exceptie (inainte se scurgea la orice eroare SQL → resource leak).
- **Performanta frontend:** `useAiProviders(poll=false)` in `SessionEditor` (montat permanent in tab-ul Profile) — fara acest flag, `/ai/providers` era cerut la nesfarsit la 15s chiar si pe Dashboard; acum polling-ul se face doar cat timp `AiProvidersCard` (AI tab) e montat (React Query partajeaza query-ul pe cheie). `useAiStatus` a primit `refetchIntervalInBackground:false` (pauza cand fereastra e in fundal).
- Config utilizator: `ai_engine/config.json` (auto-creat la prima rulare). Mode `demo`/`shadow`. Piete default alese pentru cont ~$1000 la 1:30: EURUSD/USDJPY/GBPUSD/AUDUSD/USDCAD (XAUUSD/BTCUSD/US30 nu incap — risc lot minim $12-16 sau marja $260-310).
- **API + UI:** router `api/routers/ai_engine.py` (`/ai/status|start|stop|decisions|council/{id}|outcomes|config|logs`), tab "AI Engine" in NavBar (`AiEnginePage.tsx`) cu buton On/Off, scorecard, editor piete (validat contra MT5), decizii cu transcript dezbatere, log viewer. Heartbeat: `data/ai/status.json` scris la fiecare iteratie. Rail suplimentar: marja ordin ≤ 40% din marja libera. Reconectare automata MT5 daca toate pietele esueaza intr-o iteratie.
- **Instalare alt dispozitiv:** `setup_ai_engine.bat` (winget Python+Ollama, pull model, selftest). Un singur dispozitiv ruleaza motorul odata.

- **Optimizari 2026-10-31 (din ANALIZA_COMPLETA, ledger real 89 trade-uri, −20.3R):**
  - `disabled_triggers` (config + `PUT /ai/config` + UI „Trigger-e active" in cardul Capital): trigger-ele listate NU mai convoaca consiliul (`triggers.evaluate` itereaza candidatii `_candidates` in ordinea prioritatii si sare peste cei dezactivati; `[]` = identic cu inainte, verificat 0/5000 nepotriviri vs versiunea veche). Config curent: `breakout_tension` (76% din consilii, −0.24R/trade), `heartbeat`, `vol_spike` dezactivate; raman `regime_flip` (singurul pozitiv, +0.40R n=12 — NU semnificativ, t=0.64), `news_window`, `position_review`. Test: `scripts/test_ai_triggers.py`.
  - Piete reduse la **CHFJPY + GBPUSD**, `max_open_positions` 2. Nicio piata nu are edge dovedit — sunt cele mai putin slabe (CHFJPY +$4.35 real / 3 din 4 luni pozitive dar ~0R; GBPUSD +2R pe doar 3 trade-uri). Recomandarea ramane demo/shadow.
  - **Guard CROSS-MASINA** (`engine._check_foreign_instance`): ordine/pozitii pe magic 770015 aparute dupa pornire si absente din ledger-ul local = alta instanta pe acelasi cont (PC + laptop) → motorul nu mai convoaca consiliul (weekend/stiri raman active) + Telegram o data. Baseline = tichetele existente la pornire. Doua instante se blocheaza reciproc (fail-safe).
  - `status.json` are `account_is_demo` (tipul REAL al contului) — UI arata „⚠ CONT REAL" in loc de eticheta inselatoare `mode demo`.
  - **Consilii multiple + roluri Quant/Avocatul Diavolului ELIMINATE**: fortate OFF in `config.load_config` (motor) si in `run_generator` (filtrul botului, chiar daca profilul le are). Ramane un consiliu: sursa primara → failover → Ollama. UI pastreaza doar selectorul de sursa. Codul (consensus/orchestrator) ramane dormant, testat.

- **Stabilitate Ollama + curatenie AI (2026-10-31, etapa „AI Engine fixes"):**
  - **`RemoteDisconnected` la `[ollama_probe]`** = verificarea de inferenta de la PORNIREA motorului (6/6 cazuri in log, toate la boot): autostart-ul lanseaza Ollama „fara asteptare", motorul porneste la 6-20s → Ollama inca isi incarca modelul si inchide conexiunea. Nu afecta tradingul, dar eroarea ramanea afisata zile intregi in „Erori recente". Fix: `engine._probe_ollama_with_wait` (backoff ~2 min inainte de a declara indisponibil; backend corupt raportat imediat) + `_clear_recovered_errors` (eroarea dispare dupa primul apel Ollama reusit, `health.last_ok`).
  - **Bugetul consiliului respectat LA APEL** (`providers._ctx.deadline`, thread-local, setat de `call_role(..., deadline=)` din `DebateRunner.ask`): timeout HTTP = min(timeout sursa, timp ramas). Inainte un apel Ollama de 300s × 3 retry-uri JSON putea tine bucla (si sesiunea botului, prin filtrul AI) blocata mult peste 240s — 111 din 141 consilii esuate in ledger erau „buget depasit". Termen atins → `kind="budget"`: fara pauza pe sursa, fara failover (nu e vina sursei).
  - Ollama: retry automat o data (2s) la `RemoteDisconnected`/reset; conexiune REFUZATA = oprit → pauza 30s (`_OLLAMA_NETWORK_COOLDOWN`, local) si recovery lazy, fara restart; `keep_alive: 30m` (modelul ramane in RAM pe CPU); timeout implicit 180s; mesaje cu cauza (`_ollama_cause`: oprit / a inchis conexiunea / prea lent). Teste: `python scripts/test_ollama_resilience.py` (22, server Ollama simulat) + test pe Ollama real (oprit complet → eroare 4s + pauza 30s → repornit → recuperat singur).
  - **Surse AI: doar `ollama` + `gemini`** (config.json + DEFAULTS). Eliminate claude/chatgpt/groq/mistral/cerebras/openroute/hug1/hug2quen3/nvidia; cheile lor mutate in `data/ai/providers.removed-2026-10-31.json` (local, gitignored). Adaptorii de tip raman (o sursa noua se poate adauga din UI). Aider (puntea Telegram) trece pe `gemini/gemini-2.5-flash`. Roluri: technical/macro/risk → ollama, head_trader → gemini.
  - **Rolurile Quant + Avocatul Diavolului ELIMINATE din cod** (prompturi, apeluri in council/trade_filter, config, API, UI de asignare): pe 617 verdicte reale ale filtrului au scazut aprobarea 12% → 6%/4% fara dovada ca trade-urile respinse in plus erau mai proaste. Etichetele raman doar pentru afisarea transcripturilor VECHI.
  - **Mod piata Activ / Observatie** (`market_overrides.mode`, inlocuieste `isolated`): `isolated` DOAR excludea piata din scorecard — piata continua sa tranzactioneze (confuzia raportata de user). Acum `observe` = consiliul analizeaza, decizia se salveaza `exec_status="shadow"`, ZERO ordine noi (inchiderea pozitiilor ramane permisa), exclus din scorecard; `isolated:true` vechi → `observe` (compat). Modul nu intra in briefing (`_has_overrides` ignora `mode`). `engine.market_limit_status` (pura) → `status.json::market_status` (azi X/Y ordine, R azi vs stop, `can_open` + motiv) + `global_limits`; UI: coloana „Mod", stare live pe fiecare rand, rand cu limitele GLOBALE. Test: statusul UI = exact ce blocheaza `validate_decision` (`test_market_config.py` sect. 9, 65 teste).
  - **Piete urmarite din MT5:** `/markets/mt5` intoarce si `items` (name/description/path/`tradable` = trade_mode FULL) + `account` (demo/real); `MarketsEditor` = chip-uri + „+ Add Market" cu cautare (nume/descriere), simboluri netranzactionabile dezactivate, simbol inexistent in contul curent marcat rosu; backend-ul revalideaza la salvare (symbol_select).
  - **Curatare saptamanala date AI fara trade** (`api/data_cleanup.py`, luni de la 12:00 din scheduler-ul API, catch-up daca API porneste mai tarziu, marcaj `data/ai/cleanup_last_run.json`; manual `POST /reports/ai-data-cleanup?apply=` sau `python -m api.data_cleanup [--apply]`). Regula: tot ce tine de un trade PLASAT ramane integral; pentru analizele FARA trade mai vechi de 28 zile se goleste doar textul greu (transcript consiliu + snapshot → `{"_pruned": true}`; transcriptul verdictelor RESPINSE din `ai_filter.jsonl`). Nu se sterge niciun rand (FK/UI/statistici intacte); `signals.csv`/`outcomes.csv` NU se ating (dedup, contor ID-uri, recuperare). Teste: `python scripts/test_data_cleanup.py` (21, pe copii).

### Filtru AI Pre-Trade (`ai_engine/trade_filter.py`) — validare finala optionala per sesiune

Strat de "second opinion" AI peste botul pe reguli — **dezactivat by default** (`ai_filter_enabled: false` per sesiune; cu filtrul oprit comportamentul botului e identic cu inainte). Cand e activat, FIECARE semnal detectat trece prin consiliul AI de revizie (aceleasi 4 roluri + acelasi `ProviderRegistry`/`role_assignments` ca motorul AI, prompturi specifice de revizie — trade-ul e deja format, consiliul doar aproba/respinge) INAINTE de `_place_order`. Vezi [docs/AI_TRADE_FILTER.md](docs/AI_TRADE_FILTER.md).

- **Praguri:** `FILTER_LEVELS = {permissive: 50, balanced: 70, strict: 85}` — NU 90+ (modelele mici raporteaza rar confidence >85; paralizie garantata).
- **Reguli in cod:** veto Risk Manager cu cod valid (NEWS_IMMINENT/EXTREME_VOL/WEEKEND_GAP/BAD_GEOMETRY) → respins; head `approve=false` → respins; `confidence < prag` → respins; veto necalificat NU respinge (anti-paralizie, ca in `council._sanitize`).
- **Afisare respingere — `confidence` NU e comparabil cu pragul cand head-ul spune NU (2026-07-20):** la o respingere prin `approve=false`, `confidence` = cat de sigur e consiliul ca trade-ul e SLAB (o convingere de NU), NU o incredere de aprobare. Sursa de adevar a gate-ului e `consensus_confidence` = increderea EFECTIVA (0 cand nu s-a aprobat nimic; `effective = confidence daca aproba altfel 0`). Afisarea veche „Incredere 90% (prag 85%)" langa RESPINS parea o contradictie (90>85 dar respins) — incident raportat pe AUDNZD S19 (head approve=false, conf 90, prag 85: decizie corecta „long in rezistenta + RSI 76.6 + pre-CPI", NU bug). `signal_generator._ai_reject_cause(verdict)` distinge cauza (veto / „Consiliul AI a decis NU (X% convins)" / „Incredere consens Y% sub pragul Z%") si o pune in notificarea de respingere (filtru normal + smart-news). Frontend SignalFeed: badge-ul „⛔ respins AI" NU mai arata procentul inline (era ambiguu; motivul complet e in Notificari + `ai_filter.jsonl`); ReportsPage arata `AI✓`+conf DOAR pe aprobari (unde e corect). Teste: `test_ai_filter.py` (sectiunea `_ai_reject_cause`).
- **FAIL-OPEN (invers fata de motorul autonom):** orice eroare AI (Ollama picat, buget de timp 240s depasit, JSON invalid) → trade PERMIS cu `error` notat. Motorul autonom face WAIT la erori pentru ca acolo AI-ul e strategia; aici edge-ul e al botului pe reguli.
- **Mod STRICT per sesiune (`ai_filter_strict`, default `false`, 2026-07-16):** fail-closed — AI Filter ON + Strict ON + AI indisponibil (verdict fail-open cu `error`) → ordinul NU se plaseaza (outcome `ai_reject`, Telegram "Filtru AI STRICT: ordin BLOCAT"). Helper testabil `signal_generator._ai_strict_blocked(session_cfg, verdict)`; camp copiat de `_apply_profile_overrides`; toggle in SessionEditor sub nivelul de incredere. Strict OFF = fail-open identic cu inainte.
- **Rutare surse (2026-07-16):** consiliul UNIC cu `ai_filter_primary_source` setat ruleaza cu FAILOVER (sursa aleasa → celelalte surse sanatoase → ollama), NU pinned — un blip la sursa aleasa nu mai scotea filtrul in fail-open (vazut live: gemini 429 → fail-open desi alte surse erau sanatoase). Pinned ramane DOAR pentru ≥2 consilii (independenta opiniilor); daca TOATE consiliile pinned pica, `evaluate` ruleaza un consiliu de REZERVA cu failover complet inainte de fail-open. Buget de timp PER consiliu (fiecare `TIME_BUDGET_S`=240s propriu, nu comun) — consiliile 2/3 nu mai picau cand primul era lent (295s observat cu rolurile optionale active); la fel per revizor in `orchestrator.decide`.
- **Integrare in `signal_generator.py`:** `_ai_filter_check()` (dupa dedup, inainte de pending/plasare). Respins → semnal scris in signals.csv (audit) + outcome `status=ai_reject, result_r=0` + Telegram "⛔ Filtru AI: RESPINS" + NU intra in pending (zero retry). Aprobat → verdict stocat in pending entry (`ai_filter` key) → sufix dinamic `_ai_note(p)` pe notificarile Ordin plasat/ACTIVAT/PROFIT/PIERDERE. `ai_reject` nu intra in statistici (statisticile vin exclusiv din MT5, iar un semnal respins nu ajunge in MT5).
- **Jurnal:** `data/live_signals/<sesiune>/ai_filter.jsonl` (verdict + transcript complet). API: `api/ai_filter_log.py` (cache mtime) → badge BOT·AI in `/mt5/orders` (join pe comment[:16] — truncation ICMarketsEU), campuri `ai_approved`/`ai_confidence` pe `/mt5/transactions` (acelasi join). UI: SessionEditor sectiunea "Filtru AI Pre-Trade", SignalFeed (vederea Semnale) "⛔ respins AI", ReportsPage badge AI✓, NotificationsPage categoria "Filtru AI".
- **Config mostenita:** filtrul reincarca `ai_engine/config.json` + `data/ai/providers.json` la fiecare evaluare (`registry.refresh`) — schimbarile din tab-ul AI Engine se aplica imediat, zero configurare duplicata. Nu scrie in ledger-ul motorului (jurnal propriu JSONL). Teste: `python scripts/test_ai_filter.py`.
- **Consens multi-council + roluri (OPTIONAL, per sesiune, off by default):** filtrul poate rula pana la 3 consilii pe surse AI distincte (`ai_filter_primary/secondary/tertiary_source`) combinate prin `consensus.combine` (media efectiva + veto absolut, prag = nivelul din `ai_filter_level`), plus rolurile `ai_role_quant_enabled`/`ai_role_devils_advocate_enabled`. `evaluate` planifica sursele (`_plan_councils`) si ruleaza `run_review_council` per sursa (pinned). **Fara secondary/tertiary → un singur consiliu, verdict identic byte-cu-byte** (`_verdict` decide approve la nivel de consiliu, pragul se aplica pe media de consens; pentru 1 consiliu media = increderea lui). Fault-tolerant: un consiliu picat e ignorat, toate picate → fail-open. Jurnal: campuri noi `n_councils`/`consensus_confidence`/`sources`/`councils[]`. Notificare: sufix „consens N consilii". Vezi `docs/MULTI_COUNCIL_CONSENSUS.md`.

### `live/global_guard.py` — Setari Globale (punct unic de control Bot + AI, 2026-10-31)

`data/global_settings.json` (sincronizat prin git, hot-reload pe mtime — ambele engine-uri il recitesc la fiecare bara, fara restart). Regula **„cea mai stricta castiga"**: globalul e un minim de siguranta peste setarile per sesiune/piata. **Toate sectiunile OPRITE implicit** (fisier lipsa/corupt → default-uri → comportament identic). Sectiuni: `capital_protection` (equity < prag% din `start_balance`/profil → niciun ordin nou, Bot+AI), `circuit_breaker` (N pierderi CONSECUTIVE azi pe tot contul — semantica `engine/portfolio` — sau pierdere zilnica ≥ X% din balanta zilei), `friday_close` (ora = min(global, sesiune); cripto exceptat implicit; AI: `effective_ai_weekend`), `news_protection` (impact=min, pre/post=max; bot prin `news_guard._effective_configs`, AI prin `engine._global_news_guard` care anuleaza/inchide expunerea AI pe simbol si sare consiliul), `max_concurrent_per_market` (pozitii+pending pe simbol, TOT contul, toate engine-urile), `ai_filter` (DOAR Custom/Bot Engine; nivel=cel mai strict, Strict=OR), `risk_cap` (risc maxim pe trade % din equity — Custom + AI + Daily, vezi `position_sizing.py`; PORNIT la 2% in configuratia activa).
- Decizia unica `check_open(mt5, engine, symbol, session_key, session_cb)` (pura, MT5 injectat; totul oprit → zero interogari MT5; eroare MT5 → permis/fail-open). Istoricul zilei din MT5 (`closed_today`, atribuire ca `mt5_pool.classify_trade` — deal-ul de INTRARE).
- **Circuit breaker PER SESIUNE acum aplicat in live:** campul `circuit_breaker` din profil (exista in UI + backtest, dar live-ul nu-l aplica) e copiat de `_apply_profile_overrides`; N pierderi consecutive azi ale sesiunii (doar trade-urile ei, `S<n>-`) → sesiunea nu mai deschide nimic pana a doua zi.
- Bot: `_apply_global_fields` (campurile `GLOBAL_SESSION_FIELDS` recalculate la fiecare bara peste valorile sesiunii salvate in `_global_base`; global oprit → session_cfg revine EXACT) + `_global_block` inainte de filtrul AI (semnal → outcome `global_block`, Telegram o data/zi/motiv), la retry si la ordinele Mod Inteligent. AI: gate inainte de consiliu (daca nu exista pozitie) + re-verificat dupa `validate_decision`.
- API: `GET/PUT /settings/global` (merge partial, Telegram cu diff-ul). UI: `GlobalSettingsCard.tsx` in Profil.
- **Migrare + configuratie unica (2026-10-31):** Protectia Capitalului s-a mutat din profil (`capital_protection_enabled/threshold_pct`, valorile copiate exact: OFF, 85%) in `global_settings.capital_protection` (`start_balance: null` = `start_balance` din profil). `api/watchdog.py` citeste acum aceeasi sursa (strat suplimentar: pauza sesiuni + Telegram). Selectorul de profil + „Profil nou"/„Sterge profil" eliminate din UI — pagina lucreaza mereu pe `standard`; `data/profiles/test.json` (vechi, local) ramane neatins pe disc. Taburi (2026-10-31): **Custom Engine** (id intern `profile`, `ProfilePage` — BotControl + piete/strategii) si **Settings** (id `settings`, `SettingsPage.tsx` — MT5, Trading LIVE, Setari Globale, Telegram/punte/Matrix, fus orar; lazy mount). Endpointurile `/profiles/*` raman (folosite de BotControl/backtest). Teste: `python scripts/test_global_guard.py` (51, offline).

### `daily_engine/` — Daily Engine (intraday ORB), mod SHADOW (2026-10-31)

Al treilea motor, separat de Bot Engine si AI Engine. Implicit SHADOW; poate trece pe EXECUTIE (ordine reale) — vezi mai jos. Plan + cercetare: [docs/DAILY_ENGINE_PLAN.md](docs/DAILY_ENGINE_PLAN.md) (studii, ore de varf masurate, 216 variante testate, constrangerea contului ~$200 partajat).
- **Piete (config `daily_engine/config.json`, hot-reload):** GBPUSD dimineata = deschiderea Londrei 08:00 (10:00 RO), interval 5 min, ordine stop pe ambele margini, inchidere la 14:30 Londra (16:30 RO) — rol „observatie" (fragil, sensibil la slippage); US500 dupa-amiaza = deschiderea NY 09:30 (16:30 RO), interval 30 min, intrare pe directia lui, inchidere 16:00 NY (23:00 RO) — rol „principal". SL = marginea opusa, fara TP, max 1 trade/zi/piata, NICIODATA overnight. Fara RSI/EMA (orice filtru = varianta netestata).
- **Orele = ora LOCALA A BURSEI** (`zoneinfo`) → in saptamanile cu decalaj DST SUA/RO fereastra NY se muta singura la 15:30 RO. Ora serverului MT5 e DETECTATA din tick-ul proaspat (server − UTC; ICMarkets = NY+7), nu presupusa.
- **`strategy.evaluate_day` = functie PURA** recalculata de la zero la fiecare iteratie din barele M5 INCHISE de azi → restart-safe, fara stare ascunsa. **Identica cu backtestul** `scripts/research_daily/orb_m5.py::run` — selftest-ul o verifica pe tot istoricul (GBPUSD 3974 / US500 2464 trade-uri, diferenta R = 0). Orice schimbare de logica trebuie facuta in AMBELE si sa pastreze testul verde.
- **Moduri (2026-10-31): `shadow` (IMPLICIT) / `execute`** (`config.MODES`, comutator in tab-ul Daily Engine cu 2 confirmari → `PUT /daily/config {mode}`, hot-reload, Telegram). Shadow = conexiune MT5 doar citire, trade-uri virtuale in `data/daily_engine/trades.jsonl` (cu lot ipotetic + P&L estimat), ZERO ordine. Execute = ordine reale prin `daily_engine/executor.py` — SINGURUL fisier cu `order_send` (verificat de selftest): cont DEMO → permis; cont REAL → DOAR daca `daily_engine` e deblocat in Settings → Trading LIVE (`live_guard.COMPONENTS` include acum `daily_engine`; orice eroare de citire = blocat; motivul apare in `status.execution`).
- Evenimente (intrare/inchidere) → log + Telegram „🧪 Daily SHADOW", o singura data per zi/piata (`state.json`, supravietuieste restartului). Instanta unica: mutex `TradingBot_DailyEngine_SingleInstance` + PID `data/daily_engine/daily_engine.pid`.
- API `api/routers/daily_engine.py`: `/daily/status|start|stop|trades|config|logs` (+ `backtest_ref` pentru comparatia shadow vs backtest). UI: tab „Daily Engine" (`DailyEnginePage.tsx`, lazy mount) — On/Off, starea zilei pe fiecare piata (fereastra RO + ora bursei, interval, pozitie, R), scorecard shadow vs backtest, tabel trade-uri, jurnal.
- **Date de cercetare:** `data/research_daily/<SYM>_M5_server.csv` (descarcate din MT5, gitignored, ~250 MB); fara ele testul de echivalenta e sarit.
- **Executia reala (`DailyEngine._execute`):** ziua e ARMATA doar daca modul era `execute` (si contul permis) INAINTE de formarea intervalului (`_arm` la waiting_open / forming_or) — comutat mai tarziu, ziua ramane shadow. La `waiting_entry`: verificare cost (interval ≥ 2× spread+slip+comision), `global_guard.check_open(mt5, "daily", sym)` + fereastra de stiri GLOBALA, lot din `position_sizing` (config `sizing`). US500 (direction) = ordin la PIATA pe directia intervalului; GBPUSD (breakout) = BUY_STOP + SELL_STOP pe margini (OCO: la umplerea uneia, cealalta e anulata; pret deja dincolo de margine → piata, ca in backtest). SL atasat, fara TP, magic 880001, comment `D-<SIMBOL>-<MMDD>`. La `w_end`: anuleaza + inchide tot. `sweep_stale` (in orice mod, la fiecare iteratie) inchide / anuleaza orice pozitie / ordin Daily din alta zi — NICIODATA overnight. Pozitiile reale de azi sunt gestionate si dupa revenirea la shadow. Diferente fata de backtest (documentate): executie la pret real (slippage), OCO in loc de „ambele margini in aceeasi bara = zi sarita”. Teste: `daily_engine.selftest` sectiunea 6 (11, MT5 simulat: shadow fara ordine, REAL nedeblocat blocat, armare tarzie = shadow, intrare + inchidere, OCO, stale) + `test_engine_lifecycle.py` sectiunea 4.

### `api/engine_lifecycle.py` — Engine Lifecycle comun (2026-10-31)

Un singur contract pentru UI peste cele 3 engine-uri: `GET /engines` (status real = PID viu via routerele existente + autostart), `POST /engines/{custom|ai|daily}/start|stop` cu VERIFICARE (start: procesul trebuie sa fie viu in ~12s, altfel 500 `{message, log_tail}`; stop: verificat; 409 la dubla pornire / stop pe oprit), `GET/POST /engines/{id}/autostart[/enable|/disable]` (UAC). **DELEGA** la `bot.start_bot/stop_bot`, `ai_engine.ai_start/ai_stop`, `daily_engine.daily_start/daily_stop` — mecanismele testate in productie raman neatinse (Custom porneste mereu profilul „standard”). Statusul task-urilor: o singura interogare PowerShell pentru toate, cache 30s. Teste: `python scripts/test_engine_lifecycle.py` (13, offline).
- **Supraveghere Daily:** engine-ul scrie `data/daily_engine/desired_running.json` la pornire (orice cale); DOAR Stop-ul din UI il sterge (INAINTE de kill). `api/watchdog.py::_check_daily_engine` (la 30s): stare dorita + PID mort → Telegram + repornire, max 3/ora apoi alerta si renunta. Custom Engine ramane doar cu alerta (fara repornire automata — pozitii reale). AI are watchdog propriu.
- **Incident 2026-10-31 (lamurit):** prima instanta Daily s-a oprit la inchiderea terminalului de catre user — NU crash. De aceea: stdout/stderr → `data/daily_engine/stdout.log`, `faulthandler` → `crash.log`, log la iesire neasteptata. ATENTIE: cu watchdog-ul activ, inchiderea terminalului / taskkill extern = cadere → repornire automata; oprirea corecta e DOAR Stop-ul din UI (sterge `desired_running.json` inainte de kill).

### `position_sizing.py` — dimensionare COMUNA Custom / AI / Daily (2026-10-31)

O singura implementare PURA (primeste `symbol_info`, nu atinge MT5): `capital_base(sync, capital_fix, equity)` (sync = equity MT5; fix = plafonat la equity) → `× clamp_fraction(fractie)` (0..1) → `size_by_risk(info, entry, sl, capital, risk%)` (lot brut = risc tinta / (dist SL × tick_value/tick_size) → `snap_volume`: floor la volume_step cu epsilon, clamp volume_min/volume_max) → risc real. `size_fixed` (lot fix), `fit_to_margin` (reducere la cap × marja libera). Folosita de `signal_generator._calc_lots/_snap_lots_to_broker/_bot_capital_base/_session_capital`, `ai_engine/executor.calc_lots/snap_fixed_lots/capital_base` si `daily_engine.DailyEngine.virtual_size` (lot ipotetic + `risk_money` + `pnl_money_est` pe trade-urile shadow; config `sizing`).
- **Analiza Fraction Account (date reale):** 54/55 trade-uri bot la LOTUL MINIM — la ~$206 tinta din fractie ($0,3–0,6) e sub riscul lotului minim ($1–4), deci fractia nu schimba lotul; suma fractiilor live = 334% (nu e o impartire a contului, ci plafoane separate). `/sizing/preview` arata si `equity_for_target` (equity-ul la care fractia ar incepe sa conteze, ex. GBPUSD 20% → ~$785).
- **Erori reparate:** Custom calcula pe un capital fix de $1000 cand `account_info()` era None sau fractia lipsea (risc ~5x) → acum capital 0 → `_place_order` NU trimite (volum 0 → `None`, reincercare la bara urmatoare); `(raw // step) * step` fara epsilon (0.5 → 0.49); lipsa plafonului `volume_max` in modul dinamic.
- **Daily in executie:** foloseste aceeasi componenta (`size_by_risk`) pentru lotul real.
- **Ramas diferit intentionat:** AI are rail de marja 40% (si in dinamic), Custom doar la lot fix (80%); riscul AI il alege consiliul (plafonat).
- **Decizia userului (2026-10-31): varianta B, forma cea mai sigura.** (1) Calculul NU s-a schimbat (eliminarea fractiei ar fi crescut riscul pe sesiune de pana la 5x pe masura ce contul creste); in UI fractia e prezentata ca **„Risc / trade (% cont)” = account_fraction × risk_pct** (editarea scrie inapoi account_fraction — backtest / M0 neatinse). (2) **Limita globala de risc pe trade** `global_settings.risk_cap` {enabled, max_risk_pct} (DEFAULTS oprit; configuratia ACTIVA = pornit la 2%): `position_sizing.apply_risk_cap` — volumul peste limita e redus; daca nici lotul minim nu incape → 0 (ordinul NU se plaseaza). Aplicata in `_resolve_order_lots` (Custom, inclusiv lot fix), `executor._risk_cap` (AI → rejected) si `DailyEngine._capped` (executie + estimarea shadow); `global_guard.risk_cap_pct()`. La configurarea actuala nu blocheaza nimic (risc real maxim pe SL tipic = 1,24% USDCHF; loturi fixe S22 1,12%, S18 0,45%) — prinde doar SL-uri foarte largi / aur / indici. Testele care citesc setarile reale izoleaza limita (`_GG_iso`).
- API `GET /sizing/preview` (`api/routers/sizing.py`): valori sincronizate MT5 (balance/equity/marja/levier/tip cont/lot min-max-pas/tick/marja per lot) separat de cele configurate + lantul de calcul pe SL tipic (mediana SL-urilor reale MT5 pe simbol, altfel ATR M15 × 1.5). UI `PositionSizingCard` in SessionEditor, AI Engine (`AiSizingCard`) si Daily Engine. Teste: `python scripts/test_position_sizing.py` (38; Custom = AI = Daily pe 8 configuratii).

### Rapoarte programate — `api/scheduled_reports.py` + `api/reports_builder.py` (2026-10-31)

Ore in FUSUL APLICATIEI (`now_local`), config `data/reports_config.json` (`GET/PUT /reports/config`, UI Settings → Rapoarte programate): zilnic `daily_time`; **saptamanal DOAR vineri** `weekly_time` (23:30), fereastra CONTINUA vineri→vineri (`weekly_window`, include weekendul), recuperare doar in aceeasi vineri; **lunar** ziua `monthly_day` (1) la `monthly_time` (09:00), luna calendaristica COMPLETA (`monthly_window`), recuperare la prima ocazie; marcaje `data/reports_state.json` (scrise INAINTE de trimitere — fara dubluri). `enabled_on_this_machine` = pune False pe masina fara engine-uri (altfel rapoarte duble, fiecare cu datele ei locale). Manual: `POST /reports/send-weekly|send-monthly`.
- `build_period_report` — sectiuni IZOLATE (fiecare in try; lipsa → marcata + lista „Componente indisponibile”): performanta per engine + TOTAL (`engine_stats` = `_perf` + max_dd + profit factor + % zile pozitive; manualele separat; Daily shadow separat), comparatie (≥2 engine-uri cu ≥5 trade-uri; scor net/|DD| + consistenta), conditii de piata (barele MT5: range D1 vs 60 zile, volum tick H1, efficiency ratio → trend/range/mixt + verdict), evenimente High ForexFactory (doar sapt. curenta + urmatoare → lunar = Insufficient data), weekend (gap redeschidere / ATR D1), probleme (`_ISSUE_RULES` pe notificari + statusuri outcomes.csv + exec_status ledger; nota de acoperire — notificarile pastreaza max 500), analiza AI consultativa (faptele EXACTE din raport + context shadow, thread cu timeout 150s; Ollama a inventat cifre cand primea dict-uri brute). Mesaje < 3800 caractere. **Saptamanalul = varianta ESENTIALA (`brief`, implicit pentru `weekly`, 2026-11-01):** performanta + comparatia neschimbate; piata intr-un rand (`market_conditions_brief`), stiri = numarul din saptamana + urmatoarele 5 High, weekend doar gap-urile ≥0,3×ATR, probleme doar 🔴/🟠 (sectiunile lipsesc cand nu e nimic), AI in max 3 puncte (≤700 car.). Lunarul ramane complet; `build_period_report(..., brief=False)` = saptamanal complet.
- Fix: `is_important_notification` trateaza rapoartele ca importante (se suprimau in modul liniste); raportul zilnic se loga de doua ori. Teste: `python scripts/test_reports.py` (37).

### Metrici Dashboard (2026-10-31)

- **`GET /mt5/engine-performance`** (`mt5status.py::_perf`): TOTAL (Custom+AI+Daily) + per engine — trades, W/L, `win_rate = wins/(wins+losses)` (aceeasi definitie ca TradingStatsPanel), profit (suma castigurilor brute MT5), loss, pnl, costs (comision+swap), net, avg_r, top piete. Aceeasi lista ca `/mt5/stats` (cache pool) — verificat: 55+94=149, pnl = pnl_total. Manualele EXCLUSE din TOTAL (raportate separat). Doar pozitii INCHISE, 365 zile.
- **`GET /dashboard/trading-pace`** (`api/routers/dashboard.py`, cache 15 min): trade-uri inchise/saptamana per engine din istoric REAL; doar saptamani COMPLETE de dupa ultima schimbare de configuratie care afecteaza frecventa (Custom: ultima intrare din `session_changes_log.json` cu un camp din `FREQ_FIELDS`; AI: mtime `ai_engine/config.json`; Daily: prima linie din engine.log); EWMA cu injumatatire 3 sapt; interval P20–P80; incredere insufficient (<2 sapt sau <5 trade-uri) / low / medium / high (volum + CV); `previous` = ritmul regimului anterior ca REFERINTA cand cel curent e prea nou. Reper: Custom = backtest (vechea metrica, 21,1/sapt vs ~4,8 real = supraestimare ~4,5x), Daily = 5 × Σ rata zilelor cu trade din backtest (9,6). Functia `pace()` e pura. Teste: `python scripts/test_trading_pace.py` (13).
- **Atribuire Daily:** `mt5_pool.classify_trade` magic `880001` → `daily` (= `daily_engine/config.MAGIC`, rezervat; in shadow nu exista tranzactii). `/mt5/*?source=daily`, rapoarte cu sectiunea Daily Engine.

### `live_guard.py` — deblocarea Trading LIVE (cont real)

Default: TOT sistemul e DEMO-only — `Mt5DataSource.connect()` si `ai_engine/executor.connect()` refuza conturile reale cu RuntimeError. Deblocarea e EXPLICITA, per componenta, per masina: `data/live_trading.json` (`{"bot": false, "ai_engine": false}`, gitignored — nu se propaga prin git). UI: cardul "Trading LIVE" in Profil (`LiveTradingCard.tsx`, doua confirmari la activare); API: `GET/PUT /settings/live-trading` (Telegram la fiecare schimbare). `Mt5DataSource` are param `component` ("bot" in signal_generator, "ai_engine" in engine.py); `component=None` (scripturi research) = strict DEMO indiferent de flag-uri. La prima conectare pe cont REAL, componenta trimite Telegram `⚠️🔴 CONT LIVE` + log, o data per proces (`live_guard.notify_live_connection`). Orice eroare de citire a flag-urilor = BLOCAT (fail-safe). `mt5_pool.get_status()` include `is_demo` (afisat in card). Flag-urile se aplica la urmatoarea conectare (restart bot/motor daca ruleaza). Teste: `python scripts/test_live_guard.py` (26).

### `live/signal_generator.py` — engine-ul live

Ruleaza in loop infinit la fiecare bara noua. Per iteratie:
1. `_is_paused()` — verifica daca sesiunea e pe pauza (`data/paused_sessions.json`)
2. `_update_outcomes()` — verifica semnalele pending din `state.pkl` (SL/TP atins, expirare, invalidare). Anuleaza automat ordinele MT5 la expirare. **Ruleaza intotdeauna, inclusiv cand sesiunea e pe pauza.**
3. `_check_signals()` — detecteaza setup-uri noi pe bare INCHISE (offset 3, 2 — offset 1 este bara curenta partiala, ignorata intentionat pentru a preveni detectia dubla). **Sarit cand sesiunea e pe pauza.**
4. `_place_order()` — plaseaza BUY_STOP/SELL_STOP in MT5. Returneaza: `int` (ticket OK), `None` (pret deja depasit — retry bara urm.), `False` (eroare MT5 reala — scoate din pending). **Sarit cand sesiunea e pe pauza.**
5. `_friday_close_check()` — vineri la ora configurata inchide TOATE ordinele sesiunii inainte de weekend: (1) anuleaza pending-urile din state (TRADE_ACTION_REMOVE), (2) inchide pozitiile triggerate (TRADE_ACTION_DEAL), (3) **SWEEP MT5 direct pe simbolurile sesiunii** — plasa de siguranta care prinde orice ordin/pozitie a botului scapat din state (crash, ticket nesincronizat). Sweep-ul sare ordinele AI (magic 770015) si cele manuale (comment non-`S\d+-`). Executa o singura data pe saptamana (tracking `state["friday_close_date"]`). Primeste `markets` (simbolurile rezolvate) pentru sweep.
6. `_news_close_check()` — la tranzitia `news_paused False → True`, inchide pozitii triggerate (TRADE_ACTION_DEAL) SI anuleaza ordine pending neactivate (TRADE_ACTION_REMOVE). Apelata o singura data per tranzitie (tracking `_was_news_paused`). Status outcomes: `"news_close"` sau `"news_cancel"`.

**Invariant critic:** Daca `execute_trades=True` si semnalul nu are ticket MT5 (`sig_id not in state["mt5_tickets"]`), nu se marcheaza niciodata `triggered=True` din bare. `outcomes.csv` reflecta doar ordine executate real in MT5.

**Pauza sesiune (`_is_paused`):**
Citeste `data/paused_sessions.json` la fiecare iteratie. Cand sesiunea e pe pauza:
- `_update_outcomes()` continua → pozitiile deschise sunt monitorizate pana la SL/TP
- `_check_signals()` si retry ordine noi sunt sarite → nu se deschid pozitii noi
- Efectul pauzei intra la bara urmatoare (max 15 min pentru M15). **Nu necesita restart bot.**
- Pauza manuala trimite notificare Telegram (din `api/routers/sessions.py`).

**Protectie la stiri (`_is_news_paused`, `live/news_guard.py`) — REDESIGN 2026-07-17 (activare deterministica):**
`news_guard.py` ruleaza ca daemon thread in `run_all.py`. Polleaza ForexFactory/MT5/Finnhub la 300s. **Principiu nou: separa DETECTIA (guard lent) de ACTIVARE (sesiune rapida).** Guardul NU mai scrie un verdict inghetat activ/inactiv; scrie in `data/news_auto_paused.json` TOATE evenimentele relevante APROPIATE (active acum SAU care incep in `NEWS_HORIZON_MIN`=180 min ≫ poll) + config (`pre/post/impact/markets`) — `upcoming_relevant_for`. Sesiunea (`_is_news_paused`) **RE-EVALUEAZA ferestrele la timpul CURENT** (`events_active_at(utcnow)`), deci activarea e exacta la secunda indiferent de cand a poll-at guardul (chiar `pre=1 min` e onorat — inainte, o fereastra < 5 min cadea intre poll-uri si nu se activa niciodata). **Watch sub-bara** (`_sleep_watching_news` + `_news_watch_tick`, la `NEWS_CHECK_SECONDS`=30s): intre bare, sesiunea verifica DOAR protectia la stiri (re-eval + inchidere pe tranzitie + trailing) — o sesiune H1 reactioneaza in ~30s, nu o data/ora; semnalele raman aliniate la bara. Logica de fereastra e PURA/testabila (`event_window`, `events_active_at`, `upcoming_relevant_for`). Backward-compat: fisier format vechi (fara `pre`) → prezenta = pauza. Sentiment corect pentru indicatori INVERSATI (somaj/jobless claims → semn rasturnat, `_INVERTED_INDICATORS`). Fail-safe: guard picat/fisier corupt → nepauza. Doc complet: `docs/NEWS_PROTECTION_REDESIGN.md`. Teste: `python scripts/test_news_protection.py` (59, incl. ordine false end-to-end Mod Inteligent + guard piata inchisa + filtru AI pe ordine de stire). **ATENTIE: suita mock-uieste `sg._send_telegram`** — fara mock, ordinele FALSE din teste trimiteau notificari REALE „📰 Ordin Stire EURUSD/BTCUSD" (incident 2026-07-18: notificare „EURUSD Sambata" raportata ca bug de bot era artefact de test; botul live NU plasase nimic — zero `smart_news_tickets` in toate state.pkl).
- `SYMBOL_CURRENCIES` dict mapeaza fiecare simbol la valutele constitutive (ex: EURUSD→[EUR,USD], GER40→[EUR])
- Pauza automata trimite notificare Telegram per sesiune; auto-resume la expirarea ferestrei de stire
- Configurabil per sesiune: `news_impact_level` (1/2/3), `news_pre_minutes`, `news_post_minutes`, `smart_news_enabled`
- `_news_close_check()` se activeaza o singura data la tranzitia `False→True` (Mod Inteligent: pastreaza pozitiile aliniate cu sentimentul stirii, inchide contra, deschide in directia stirii via `_smart_news_place_order`)
- **Guard piata inchisa (`_market_is_open`, 2026-07-18):** `_smart_news_place_order` NU mai plaseaza „Ordin Stire" cand piata e inchisa. Un broker ACCEPTA un pending stop cu piata inchisa (asteapta redeschiderea) → retcode DONE + notificare, desi piata e inchisa. Guard la un singur choke point (ambele call-site-uri din `_news_close_check` trec prin el): FX/indici/metale = inchise Sambata/Duminica (`now_local().weekday()>=5`); cripto (`_is_crypto_symbol` — BTC/ETH/XRP...) = 24/7; oricare piata cu `trade_mode` MT5 ≠ FULL = inchisa (dezactivata/close-only/sarbatoare). Fail-open pe glitch de interogare MT5. Ceasul e injectabil (`_market_is_open(symbol, now=...)`) pentru teste deterministe. Regula NU atinge semnalele normale (deja gate-uite de `skip_weekdays`/`friday_close`). Teste: `test_news_protection.py` (sectiunea 6c).
- **Mod Inteligent ELIMINAT (2026-10-31):** `run_generator` forteaza `smart_news_enabled=False` (n-a plasat niciun ordin; fara `actual` de la FF se comporta identic cu protectia standard); toggle-ul scos din UI. Codul ramane dormant (acoperit de `test_news_protection.py`).
- **Filtru AI pe ordinele de stire (2026-07-19):** ordinele Mod Inteligent trec prin ACEEASI validare `_ai_filter_check` ca semnalele normale, cand `ai_filter_enabled` per sesiune (default OFF → comportament identic). Ordinea gate-urilor in `_smart_news_place_order`: piata deschisa → filtru AI (incl. `ai_filter_strict` fail-closed) → sizing → ordin. Respins → log + Telegram „⛔ Filtru AI: Ordin Stire RESPINS", fara ordin; aprobat → verdict atasat in `smart_news_tickets[sn_id]["ai_filter"]` + sufix `_ai_note` pe notificare; jurnalizat in `ai_filter.jsonl` (`log_verdict` din `_ai_filter_check`, `signal_type: "smart_news"`). `src` (Mt5DataSource al sesiunii) e pasat prin `_news_close_check(src=)` pentru briefing-ul consiliului; fara `src` → briefing fallback (judeca doar datele trade-ului). Teste: sectiunea 6d.

**Inchidere Vineri (`_friday_close_check`):**
Apelata dupa procesarea semnalelor, la fiecare iteratie de vineri. Inchide TOATE ordinele sesiunii (pending anulate + pozitii inchise), NU doar pozitiile triggerate. In plus fata de procesarea din `state`, ruleaza un **sweep MT5 direct** pe simbolurile sesiunii (`markets`) care prinde orice ordin/pozitie a botului scapat din state — statusuri: `vineri_cancel` (pending), `vineri_close` (pozitii). Parametri din `session_cfg`:
- `friday_close_enabled` (default `True`) — dezactivat pentru S3/BTC (piata deschisa weekend)
- `friday_close_hour` (default `20`) — ora la care se inchid pozitiile

**Capital bot aliniat cu motorul AI (`_bot_capital_base`, 2026-07-17):** baza de sizing a botului = `_bot_capital_base(session_cfg, equity)` — sync ON (default / camp lipsa) = equity real MT5 (identic cu inainte); sync OFF = capital FIX alocat botului (`capital_usd`, plafonat la equity, typo-safe). Peste baza se aplica `account_fraction` per sesiune. Campurile stau la nivel de PROFIL (`capital_sync_mt5`/`capital_usd`, ca `start_balance`), citite de `_apply_profile_overrides` in session_cfg si folosite in cele 3 locuri de sizing (plasare primara, retry, smart-news). UI: toggle in Profil → Capital Initial. Util cand acelasi cont ruleaza si motorul AI / trade-uri manuale (botul nu-si mareste pozitiile pe capitalul celorlalti). Persistat de `PUT /profiles/{id}`. Teste: `test_profile_params.py`.

**Lot FIX per sesiune (`fixed_lots_enabled`/`fixed_lots`, PER SESIUNE, optional, OFF by default — 2026-07-21):** oglinda pe partea de bot a `market_overrides.fixed_lots` din motorul AI. Cand e activ pe o sesiune, sizing-ul NU se mai face pe capital×risc — se plaseaza un volum FIX per ordin, aliniat la broker (`_snap_lots_to_broker`: floor la `volume_step` cu epsilon anti-float, clamp la `volume_min`/`volume_max`). Sursa unica de sizing: `_resolve_order_lots(symbol, entry, sl, direction, capital, risk_pct, session_cfg, log)` — ruteaza fix vs dinamic; cu fixed_lots OFF (default) intoarce EXACT `_calc_lots` (zero schimbare de comportament, baseline neatins). Folosit in cele 3 locuri de sizing (plasare primara, retry, smart-news). **Auto-reducere la marja (`_fixed_lot_size`):** daca marja necesara pentru lotul fix (`order_calc_margin`) depaseste `_FIXED_LOT_MARGIN_CAP` (0.80 = 80% din marja libera), lotul e redus automat la cel mai mare volum aliniat la step care incape (niciodata sub `volume_min`) si se NOTIFICA — sufix `_lot_reduction_note` pe mesajul de plasare (Telegram + Notificari, o data) + `log.info [LOT-FIX]` in generator.log. Fail-open: `order_calc_margin` esueaza → lot fix nemodificat. Campurile stau la nivel de SESIUNE (copiate in `_apply_profile_overrides`); estimarea USD in UI reutilizeaza `POST /ai/lot-info` (generic). UI: toggle „Lot fix (înlocuiește fracția)" + input volum + estimare marja/piata in SessionEditor → Setări Generale (fractia se estompeaza cand e activ). Teste: `python scripts/test_bot_fixed_lots.py` (32).

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

**`_check_mt5_health` — alerta conexiune MT5 cu PRAG DE PERSISTENTA (2026-07-21):**
Verificat la fiecare bara. Anti-spam pe 2 axe: (1) **doar `session1` trimite Telegram** (`_MT5_HEALTH_NOTIFIER`; inainte toate 20 sesiunile trimiteau simultan), stare partajata in `data/mt5_health_alert.json`, max 2 notificari/incident (`_MT5_HEALTH_MAX`, a 2-a la +`_MT5_HEALTH_REPEAT_S`=10min). (2) **Prag de persistenta pentru deconectari** (`_MT5_DISCONNECT_GRACE_S`=300s): un blip scurt de reconectare pe partea brokerului (frecvent, inofensiv — botul isi revine singur) NU mai trimite alerta. `_mark_seen(key)` inregistreaza `first_seen` la prima detectare (fara mesaj); `_should_alert(key, grace_s)` alerteaza doar cand deconectarea persista `>= grace_s`. La bare de 15 min asta = „inca cazuta la urmatoarea verificare". Se aplica `disconnected` (broker) + `ipc_lost` (terminal); `autotrading_off`/`account_changed` raman imediate (stari, nu blip-uri). La blip: `_resolve` sterge intrarea fara mesaj (count 0). Alerta include durata (`de peste N min`). Teste: `python scripts/test_mt5_health.py` (11, MT5 simulat).

**Reconciliere MT5 la startup — 3 straturi:**

1. **`_recover_lost_outcomes(state, session_cfg, outcomes_file, log)`** — apelata la fiecare pornire sesiune, dupa `_reconcile_mt5_tickets`. Pentru semnale pending FARA ticket MT5 (state sters la crash), cauta in MT5 `history_orders_get()` (10 zile lookback) dupa `o.comment == sig_id`. Daca gaseste:
   - Ordin inca pending → actualizeaza `mt5_tickets[sig_id] = ticket`
   - Pozitie deschisa → actualizeaza `mt5_tickets` + `triggered=True`
   - Pozitie inchisa → scrie outcome real (TP/SL/R/pnl_usd) in `outcomes.csv`, sterge din `pending`, trimite Telegram `[RECOVER]`
   - Daca sig_id deja in outcomes.csv → sare (nu duplica)

2. **Fix expirare in `_update_outcomes`** — inainte de a scrie `status=expirat, result_r=0.0`, verifica daca pozitia MT5 era de fapt INCHISA (`_check_mt5_position_closed`). Daca da, scrie TP/SL real + trimite Telegram `[RECOVER]`. Acopera scenariul: bot restartuit dupa ce pozitia fusese triggerata si inchisa in lipsa lui.

3. **Fix invalidare in `_update_outcomes`** — acelasi mecanism: bara invalideaza structura DAR MT5 poate fi deja inchis cu TP/SL real → prioritate MT5.

**Principiu: MT5 are intotdeauna prioritate.** Bot-ul nu poate marca niciodata `expirat/invalidat` daca MT5 confirma ca pozitia a fost executata real. Orice corectie trimite notificare Telegram cu prefix `[RECOVER]` si apare in tab-ul Notificari.

**`outcomes.csv` = jurnalul de lucru al Bot Engine, NU sursa statisticilor (2026-10-30).** Engine-ul il citeste si scrie pentru deduplicare, recuperare dupa restart si scanarea istoricului MT5 — ramane neatins. API-ul NU mai calculeaza din el trades/W/L/R/P&L (vezi „MT5 = sursa unica" mai jos).

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
- `reports` — doar date operationale ale aplicatiei: `GET /reports/uptime` (istoric start/stop bot), `GET /reports/session-changes` (diff parametri la fiecare salvare profil), `GET /reports/system-logs[/sessions]`, `POST /reports/send-daily|send-weekly` (raport Telegram manual). Tranzactiile/pietele/costurile vin din `/mt5/transactions|top-markets|costs|costs-daily`.
- **MT5 = sursa unica pentru rezultatele de trading (2026-10-30).** Eliminate: sursa interna „Bot" (comutatorul Bot/MT5 din UI, `SourceToggle`/`useStatsSource`), `/sessions/weekly_stats|top-markets|all/equity-curve|{id}/outcomes|all/outcomes`, `/reports/transactions[.csv]|market-stats|costs|costs-daily`, routerul `mt5_sync` (`/mt5/sync[-status]`, butonul „Sync MT5" — rescria `outcomes.csv` din API in paralel cu engine-ul) si campurile de rezultat din `SessionStatus`. Motiv: o a doua evidenta care diverga de MT5 (bug-ul `exit_price=0` la news/vineri close dadea −$12.667 in CSV vs +$17.64 real). **Atribuirea** pe engine/sesiune/strategie se face in `mt5_pool.classify_trade(magic, comment)`: magic 770015 → `ai`; comment `S<n>-…` → `bot`, `session_id=session<n>`, strategia din ultimul segment (tolerant la trunchierea la 16 caractere, ex. `S18-NZDJPY-H1-SI` → pullback); `SN<n>` → bot/smart_news; restul → `manual`. Campuri noi pe trade-urile din pool: `comment`, `source`, `session_id`, `strategy`; `/mt5/transactions` accepta `source`/`session_id`/`date_from`/`date_to` si intoarce atribuirea + `ai_approved`/`ai_confidence` (join `ai_filter.jsonl`); `/mt5/sessions` numara DOAR trade-urile `source=bot` (inainte atribuia si trade-urile AI de pe acelasi simbol sesiunii botului). Teste: `scripts/test_dashboard_commissions.py` (19).

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
- `SessionStatus` = doar starea Bot Engine: `running`, `execute`, `paused`, `news_paused`, `news_events`, `signals_today/yesterday/total`, `last_signal_time`. Rezultatele per sesiune vin din `/mt5/sessions` (cardul de sesiune le primeste ca prop `mt5`). `Signal` are campul `status` (eticheta din jurnalul engine-ului: `ai_reject`/`expirat`/`invalidat`/TP/SL… — fara R/USD).

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
- **Mod liniste „Doar notificari importante" (`important_only`, default OFF):** flag in `data/telegram_config.json` care, cand e activ, trimite pe Telegram DOAR notificarile importante — trading (ordine/TP/SL/filtru AI/stiri) + conexiune (MT5 pierdut/reconectat via cuvinte-cheie) + lifecycle bot (pornit/oprit/watchdog) — si SUPRIMA restul (sanatatea surselor AI „TOATE sursele indisponibile / si-au revenit", pauze manuale de sesiune, mesaje de sistem). **Filtreaza DOAR push-ul Telegram — toate notificarile raman logate complet in tab-ul Notificari** (jurnalul e sursa de adevar, neatins). Sursa unica de adevar: `api/notifications.py::is_important_notification(text)` (reutilizeaza `_categorize`; categorii importante `{order,trade,signal,news,bot}` + override pe cuvinte-cheie de conexiune + `_AI_TRADE_KEYWORDS`). **Categoria „ai" e scoasa INTENTIONAT din setul important** pentru ca `_categorize` conflateaza doua lucruri sub „ai": (a) deciziile filtrului AI pe trade-uri („Filtru AI: RESPINS", trading — importante, pastrate prin cuvintele-cheie `filtru ai`/`ai filter`) si (b) sanatatea surselor AI din `providers.py::_notify` („🤖 ✅/🛑/⚠/🔑 Sursa AI «x» s-a revenit/defecta/in pauza/dezactivata", zgomot operational — SUPRIMATE). Astea din urma contin „sursa ai" → `_categorize`=„ai", deci nu pot fi discriminate pe categorie; erau motivul pentru care userul primea in continuare notificari despre surse desi activase modul liniste (bug prins live 2026-08-04). Alerta AGREGATA din `engine.py` („TOATE sursele AI indisponibile / si-au revenit") e „system" → oricum suprimata. + `should_push_telegram(text)` (fail-open: orice eroare de citire a flag-ului => trimite, ca sa nu piarda din greseala o alerta de trading). Gate-uit in DOUA locuri (dupa `log_notification`, inainte de HTTP): `send_message` (acopera API + motorul AI, care deleaga aici) si `signal_generator._send_telegram` (bot). Motorul AI e acoperit automat. Nota: `_categorize` a fost extins „closed"→„close" ca mesajul „AI Engine — CLOSE {symbol}" sa fie corect „trade" (inainte cadea in „system" si s-ar fi suprimat). API: `PUT /settings/telegram/important-only {enabled}` (efect imediat, fara restart — bot/motor citesc flag-ul la fiecare notificare) + camp `important_only` in `GET /settings/telegram`; `save_telegram` face acum merge-preserve (nu mai suprascrie tot fisierul). UI: toggle in `TelegramSettings.tsx` (accordion „Notificari Telegram" din Profil), vizibil cand Telegram e configurat. Test-ul de test Telegram (`/settings/telegram/test`) foloseste calea proprie, deci merge mereu indiferent de flag. Teste: `python scripts/test_notification_quiet_mode.py` (80, offline).

**`api/config.py` — `get_profile_execute_map()`:**
Citeste `execute_trades` per sesiune din profilul activ la runtime (nu din `SESSIONS` static). Folosit de `sessions.py`, `reports.py`, `scheduled_reports.py` pentru a filtra sesiunile OBS (execute_trades=False) din toate agregarile. `session4` (GER40) si `session6` (US30) au `execute=False` in config; `session20` (XAUUSD) are `execute=True`. Fallback pe valorile statice din `SESSIONS` daca profilul nu e accesibil.

**`api/scheduled_reports.py` — rapoarte periodice automate:** vezi sectiunea „Rapoarte programate” (zilnic / saptamanal vineri / lunar, fusul aplicatiei, sectiuni izolate). Sursa rezultatelor = exclusiv MT5 (`mt5_pool.get_closed_trades`, atribuire `classify_trade`); MT5 indisponibil → sectiunea marcata, nu raport gol. Necesita restart API dupa modificari.

**`api/watchdog.py` — daemon watchdog oprire neasteptata:**
Pornit automat la startup API (`@app.on_event("startup")`). Ruleaza ca thread daemon, polleaza la fiecare 30s: daca exista profil activ (`data/active_profile.json`) dar PID-ul botului (`data/run_all.pid`) nu mai e viu → trimite notificare Telegram ("Bot Trading oprit neasteptat!") si curata fisierele de stare (profil activ, pid). Acopera scenariile de crash sau oprire fortata fara Ctrl+C.

**`api/routers/mt5status.py` — `algo_trading_enabled`:**
Campul `algo_trading_enabled: bool | null` returnat in `GET /mt5/status`. Citit din `mt5.terminal_info().trade_allowed`. Dashboard-ul afiseaza un banner de avertizare galben cand este `false` (botul detecteaza semnale dar ordinele MT5 nu pot fi plasate).

**`api/mt5_pool.py` — acces MT5 centralizat, persistent, cache-uit (procesul API):**
Toate endpointurile `/mt5/*` trec prin acest pool. Inainte, FIECARE endpoint facea `mt5.initialize()` + `mt5.shutdown()` per request, si 9 endpointuri distincte interogau fiecare independent `history_deals_get` pe 400 zile pentru aceleasi date — Dashboard + Rapoarte declansau 6-9 astfel de interogari per ciclu de polling. Pool-ul rezolva:
- **Conexiune persistenta** — `_ensure_mt5()` apeleaza `initialize()` la fiecare acces necache-uit (revalidare ieftina; reconecteaza automat daca alt modul din API — markets/data_download — a facut `shutdown()`), dar NU face niciodata `shutdown()`. Elimina handshake-ul IPC per-request (~8ms → ~0.02ms, masurat 489x mai ieftin).
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
- `fixed_lots_enabled` (bool, default `false`) + `fixed_lots` (float, loturi) — volum FIX per ordin in loc de sizing pe fractie/risc. Cand ON, `account_fraction`/`risk_pct` sunt IGNORATE; lotul e snap-uit la broker + redus automat daca depaseste 80% din marja libera (notificare). Vezi sectiunea „Lot FIX per sesiune".
- `news_protection_enabled` (bool, default `false`) + `news_impact_level` (1/2/3) + `news_pre_minutes` + `news_post_minutes` — protectie automata la stiri. Cand activa, sesiunea intra pe pauza automatic + ordine/pozitii inchise imediat.
- `break_even_enabled` (bool, default `false`) + `be_trigger_pct` (default 80) + `be_lock1_pct` (default 30) + `be_lock2_pct` (default 50) + `be_phase2_zone_pct` (default 40) — mecanism break-even in 3 faze (vezi `engine/simulator.py`).
- `be_phase2_enabled` (bool, default `true`) — dezactiveaza independent Faza 2 BE fara a dezactiva intregul mecanism. Cand `false`, tranzitia Faza1→Faza3 sare direct la SL blocat la 50%.

**Nota:** `config/standard_profile.json` este config-ul legacy folosit de backtest si de sesiunile live cand nu exista profil activ runtime. NU modifica structura — este citit de `engine/portfolio.py` si `live/signal_generator.py`. `data/profiles/standard.json` este profilul UI (acelasi continut logic, format diferit).

---

## Sesiuni active

22 sesiuni individuale — o singura piata per sesiune („Custom Engine” in UI; „Bot Engine” in cod si in documentatia mai veche = acelasi lucru). Fiecare are propriul script live, `session_key`, `state.pkl`, `signals.csv`, `outcomes.csv`.

| ID | Script | Piata | TF | Directie | Execute |
|----|--------|-------|----|----------|---------|
| session1  | session1_m15_long.py   | EURUSD  | M15+M30 | LONG | True  |
| session2  | session2_m5_both.py    | AUDJPY  | M15+M30 | BOTH | True  |
| session3  | session3_btc_both.py   | BTCUSD  | M15+M30 | BOTH | True  |
| session4  | session4_obs.py        | GER40   | M15+M30 | LONG | **False** (OBS) |
| session5  | session5_ger40_h1.py   | USDCHF  | H1+D1   | BOTH | True  |
| session6  | session6_us30_m15.py   | US30    | M15+M30 | LONG | **False** (OBS) |
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
| session20 | session20_xauusd.py    | XAUUSD  | M15+M30 | BOTH | True  |
| session21 | session21_csco.py      | CSCO.NAS| M15+M30 | LONG | **False** (OBS) |
| session22 | session22_sofi.py      | SOFI.NAS| M15+M30 | LONG | True (+ AI Engine) |

**Sesiuni stock CFD (S21/S22, 2026-08-08):** primele actiuni (Cisco/SoFi) adaugate pe baza unui backtest cu split train/test (M15+M30 = TF robust; M30+H1 avea train negativ). Filtru ore OOS-validat: CSCO skip 19-20h RO (pranzul US = chop de midday), SOFI skip doar 20h (19h e profitabil pe SOFI). Directie LONG, sesiune US 16-23h RO, `execute_trades=False` (OBSERVATIE pe cont real — edge subtire, frecventa ~0.4/sapt, backtest fara costuri). **Simbol non-forex nou → inregistrat obligatoriu** in `strategy/signals.py::_INDEX_PIP` (CSCO.NAS=0.01, SOFI.NAS=0.001) SI `strategy/costs.py::_INDEX_TICK` (tick_size, tick_value din MT5) — altfel `pip_size` da default forex → sizing gresit. News/AI-filter/break-even OFF pe aceste sesiuni (observatie curata, match cu backtest). UK100 a fost EXCLUS: nu incape pe cont ~$195 (margin 38%, risc lot minim ~7%/trade). **SOFI (session22) e LIVE in AMBELE motoare (2026-08-08):** `execute_trades=True` la bot + `SOFI.NAS` adaugat in `ai_engine/config.json::markets` (magic 770015, izolat de bot). CSCO ramane OBS. Atentie: AI Engine nu are gate de ore per-piata — proceseaza SOFI 24/7, dar in afara orelor US bara nu se schimba → fara trigger (auto-limitare); heartbeat-ul 24h poate convoca o data cu piata inchisa → ordinul esueaza curat. SOFI e candidatul mai slab/volatil — expunere dubla pe cont real, decizie asumata a userului.

**Sursa de adevar pentru `execute_trades` = profilul activ (`data/active_profile_runtime.json`), NU scriptul hardcodat.** Scripturile `sessionN_*.py` au un default hardcodat (ex: `session20_xauusd.py` are `execute_trades=False`), dar la pornire din UI `_apply_profile_overrides` il SUPRASCRIE cu valoarea din profil. In profilul `standard` curent, DOAR `session4` (GER40) si `session6` (US30) sunt pe observatie (`execute_trades=False`); toate celelalte, inclusiv `session20` (XAUUSD), sunt LIVE. Coloana de mai sus reflecta profilul, nu default-ul din script.

**`execute_trades` e HOT-RELOADED per bara (2026-07-17):** `_runtime_execute_trades(session_key)` reciteste valoarea din runtime profile (cache pe mtime) la FIECARE iteratie — un toggle observatie⇄live din UI se aplica de la bara urmatoare, ca butonul de pauza, NU doar la restart de bot. Dezactivarea executiei OPRESTE imediat ordinele noi (pozitiile/pending-urile deja plasate raman monitorizate); tranzitia trimite Telegram + WARNING in log. Inainte, `execute_trades` se citea doar la startup — un user care dezactiva executia unei piete din UI vedea ordine plasate in continuare pana la restart (perceput ca bug „aur executat desi era dezactivat"). Sizing dinamic: botul citeste equity real MT5 la fiecare trade; `account_fraction` per sesiune configurat in profil.

---

## Numere baseline — nu le modifica

Orice schimbare la `strategy/` sau `engine/` trebuie sa reproduca exact:

```
python portfolio_backtest.py  →  S1: 280 trades, Exp +0.012R, DD -40.4%
                                  TRAIN 181t: -0.156R | TEST 99t: +0.318R | split 2024-01-09

python session2_backtest.py   →  S2: 1254 trades (839 train + 415 test), Exp +0.014R
                                  TRAIN 839t: -0.025R | TEST 415t: +0.092R | split 2024-03-21

python session3_backtest.py   →  S3: 731 trades | +0.186R train (p=0.0153) | +0.237R test | split 2024-08-20
                                  6/7 ani pozitivi (2020 −0.02R; 2022 bear +0.26R)
```

Daca numerele se schimba semnificativ → bug introdus, nu progres.

**Baseline-uri actualizate 2026-10-31 (aprobate de user):** fix-ul de lookahead pe trendul TF mare (vezi `_enrich`, `trend_live_equivalent`). Vechile valori (284 / 1326 / +0.211R) erau optimiste — backtestul vedea inchiderea finala a barei TF in formare. Se reproduc cu `CsvDataSource.historical=False`.

**Nota S2:** Numerele S2 au crescut fata de versiunile anterioare (era 1022 trades, split 2024-07-22) dupa adaugarea suportului multi-pozitie per simbol (`engine/portfolio.py`). Baselines curente reflecta comportamentul post-multi-position.

---

## Detalii tehnice importante

**pip_size pentru indici si crypto:** `_INDEX_PIP` in `strategy/signals.py` defineste 1.0 pentru indici (GER40, US30 etc.). BTCUSD este setat dinamic din `data/crypto_specs.json` (tick_size=0.01) in `session3_btc_both.py` — nu din fallback-ul default.

**Timestamps MT5:** `Mt5DataSource` converteste explicit din ora serverului broker la `Europe/Bucharest` (naive, fara tzinfo). Tot codul intern lucreaza in ora Romaniei. **Offset server RE-DETECTAT periodic (2026-10-31, `_refresh_server_offset`):** inainte se detecta o singura data per proces — pornit cu piata inchisa (weekend/noapte) ramanea 0 pentru totdeauna (bare pe ora serverului), iar la schimbarea de ora a serverului (ICMarkets urmeaza DST-ul US: 25 oct–1 nov server UTC+3 vs RO UTC+2) offset-ul vechi decala barele 1h pana la restart. Acum: re-detectie la 30 min; un 0 (detectie neconcludenta, piata inchisa) NU suprascrie o valoare buna; cat timp e 0 reincearca la 15 min. **Fus Germania (`Europe/Berlin`):** orele de sesiune/skip_hours se aplica pe ora LOCALA configurata → fata de backtest (calibrat pe ora RO) ferestrele sunt decalate 1h; nu opreste trade-urile. Diagnostic pe masina utilizatorului: `python scripts/diagnose_no_trades.py` (read-only: fus/offset, cont + AutoTrading, deblocare LIVE, profil/executie/pauze, Setari Globale, filtru AI Strict fara surse AI, proces bot, semnale/blocaje 7 zile, tranzactii MT5).

**pip_value_usd — arhitectura si intretinere:**
- **Live** (`live/signal_generator.py` → `_calc_lots`): citeste `info.trade_tick_value` si `info.trade_tick_size` direct din MT5 la fiecare trade. Intotdeauna 100% corect, independent de valorile din `costs.py`.
- **Backtest** (`strategy/costs.py` → `pip_value_usd`): foloseste valori statice — `_INDEX_TICK` (indici, XAUUSD), `_CRYPTO_TICK` (BTC/ETH/XRP), `BASE_USD_APROX` (ratele EUR/GBP/AUD→USD pentru cross-perechi). Formula cross-perechi: `val_in_quote × BASE_USD[baza] / cross_price` (ex: AUDCAD: 10 CAD × 0.64 / 0.88 = 7.27 USD).
- **Intretinere `BASE_USD_APROX`**: actualizeaza la 6 luni daca ratele deriva >5% (EUR=1.08, AUD=0.64, GBP=1.27 — last update: 2026-06-24). Afecteaza doar cifrele $ absolute, nu R-ul (backtestul e R-based).
- **Simboluri noi non-forex**: adauga obligatoriu in `_INDEX_TICK` sau `_CRYPTO_TICK` din `costs.py` SI in `_INDEX_PIP` din `signals.py`. Fara inregistrare explicita, formula forex (pip=0.0001, val=100000×pip) da pip_value gresit → lots=0 → 0 trades in backtest (ex: XRPUSD era 10.0 in loc de 0.01 USD/pip).
- **Dupa modificari `costs.py`/`signals.py`**: API-ul trebuie repornit — fara `--reload`, codul vechi ramane in memorie.

**Swap BTC:** calculat ca procent anual din notional. Rate-ul variaza cu brokerul — verifica `data/crypto_specs.json`.

**`pnl_usd` in `outcomes.csv`:** Coloana 14 din `_OUTCOMES_COLS`. Scrisa de `_pnl()` la inchiderea ordinelor MT5 reale (TP/SL/vineri_close/news_close). Valoarea vine din `deal.profit` returnat de `history_deals_get`. Ramane `NaN` pentru ordine expirate sau sesiunile cu `execute_trades=False`. Backfill retroactiv: `python scripts/backfill_pnl_usd.py` (necesita MT5 conectat).

**Statusuri inchise in jurnalul engine-ului:** `TP`, `SL`, `vineri_close`, `news_close`, `be_lock`, `be_lock2` (pozitii reale inchise). API-ul nu le mai agrega — statisticile vin din MT5.

**`GET /sessions/frequency-estimate` (folosit acum doar ca REPER backtest in `/dashboard/trading-pace`):** Calculeaza frecventa estimata trades/saptamana + trades/luna din cele mai recente backtest-uri finalizate (din `data/backtest_jobs.json`). Filtreaza sesiunile pe pauza **si cele cu `execute_trades=False`**. Mapare: `job.session_id` ("S2") → `profile_session.id` ("S2"). Returneaza `{per_week, per_month, missing}` sau `null` daca nu exista backtest-uri.

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

**Brand (2026-10-31): „No Trading”** — `BrandLogo.tsx` (`BrandMark`: „N” din doua lumanari + diagonala, gradient albastru→cyan; `BrandLockup` in NavBar) sincron cu `frontend/public/favicon.svg`; titlul ferestrei „No Trading”. Antetul Dashboard-ului: „Dashboard” + subtitlu (inainte afisa „Standard Profile Profile” — numele profilului + sufixul „ Profile”). Task-urile Windows / procesele pastreaza numele tehnice `TradingBot-*` (nu le redenumi — autostart-ul existent le cauta dupa nume).

**Dashboard.tsx:** Pagina principala, de sus in jos (2026-10-31): antet cont MT5 (balance/equity) → `EngineControlCards` (status + Start/Stop + autostart per engine) → `EnginePerformanceCards` (4 carduri: TOTAL/Custom/AI/Daily) → filtrul de sursa → `TradingPace` (ritm real pe engine) → grila de sesiuni → Ordine Active → 2 coloane (stanga: Tranzactii MT5 + Top 5; dreapta: Performanta + Statistici + Indice Saptamanal) → `EnginePerformanceSection` x3 (custom/ai/daily). Banner galben cand `mt5.algo_trading_enabled === false`. **Panoul SignalFeed are inaltime FIXA `h-[520px]` + `overflow-hidden`** (nu `max-h`): intr-un wrapper `space-y-4` cu Top 5 dedesubt, grid-stretch nu-i da inaltime definita si lista s-ar revarsa. NU schimba inapoi la `max-h`.
- **Culori per engine (consecvente peste tot):** Custom = emerald, AI = purple, Daily = cyan, TOTAL = blue (`ENGINE_THEME` in `EngineControlCards.tsx`, `THEME` in `EnginePerformance.tsx`). „Bot Engine” a fost redenumit „Custom Engine” in tot UI-ul; badge-uri tranzactii CUSTOM / AI / DAILY / MAN.
- **`EngineControlCards.tsx`** (`/engines`, poll 10s): RUNNING/STOPPED din PID-ul real, Start/Stop verificat pe backend, eroarea (cu ultimele linii din jurnal) afisata in card, confirmare `window.confirm` la Start/Stop Custom si AI (ordine reale), toggle autostart per engine. Inlocuieste BotStatusBar/AiStatusBar (antet) si AutostartToggle/AiAutostartToggle (NavBar) — sterse.
- **`EnginePerformance.tsx`** (`/mt5/engine-performance`, poll 60s): O SINGURA componenta in doua forme — `EnginePerformanceCards` (win rate / profit / loss / rezultat / net) si `EnginePerformanceSection engine=…` (inlocuieste AiActivityCard). Daily: banii reali = 0 (shadow), trade-urile virtuale separat, in R, niciodata adunate la bani.
- **`TradingPace.tsx`** (`/dashboard/trading-pace`, poll 15 min = cache-ul serverului): inlocuieste „Frecventa estimata” (+ badge-ul „fara date”, butoanele de backteste si -DD estimat — eliminate; `useFrequencyEstimate` sters). Vezi `api/routers/dashboard.py`.

**Filtru de SURSA la nivel de pagina in Dashboard (2026-10-31):** bara „Arată tranzacțiile: Toate / Bot Engine / AI Engine / Manual” (default Toate) sub antet; un singur state `source` (`SourceFilter`) trimis la `/mt5/stats|weekly-stats|top-markets|equity-curve|sessions|transactions?source=`. Cardurile de piata (`/mt5/sessions?source=`): `bot` (implicit endpoint, compat) = tranzactiile sesiunii din comment; `all` = + AI/manual pe ACELASI simbol; `ai`/`manual` = doar acelea pe simbol; raspunsul are `unassigned` {simbol: n} = tranzactii pe piete fara card (ex: AI pe AUDUSD), afisat sub grid ca totalurile sa se lege (carduri + fara card = total). Lista de tranzactii pe o piata selectata: `all`/`ai`/`manual` filtreaza pe simbol, `bot` pe session_id. P&L Real (equity − capital start) ramane cont-wide (etichetat). Vederea Semnale e doar Bot Engine (mesaj pe AI/Manual). `by_source` din `/mt5/stats` e calculat pe tot contul. **SignalFeed.tsx (paginare 2026-10-31):** lista de tranzactii arata „X din TOTAL tranzactii MT5" + „Încarcă mai multe" (+100) si, pe ALL, filtru sursa Toate/BOT/AI/MAN — inainte arata tacit doar ultimele 50 (parea ca lipsesc trade-uri fata de MT5). `/mt5/stats` intoarce `by_source` {bot, ai, manual}, afisat sub „Total Trades" (cardurile de sesiune numara DOAR Bot Engine). **SignalFeed.tsx:** props `sessionId` + `view` (`"trades"` | `"signals"`, comutat din headerul panoului in Dashboard). `trades` = tranzactiile inchise din `/mt5/transactions` (pe „ALL" tot contul cu badge BOT/AI/MAN + strategie; pe o sesiune `source=bot&session_id=…`). `signals` = semnalele detectate de Bot Engine (`/sessions/{id|all}/signals`) cu eticheta de stare (respins AI / expirat / invalidat / executat) — fara R/USD (rezultatul real e in vederea trades).

**BotControl.tsx:** Buton Start/Stop. La start trimite `{ profile_id, profile_name }` din profilul selectat curent. Afiseaza timpul de la ultima pornire/oprire.

**SessionCard.tsx:** Card per sesiune in Dashboard. Include buton Pause/Play (⏸/▶) in header. Cand pe pauza: dot galben, badge "PAUZA", stats dimmate. Butonul apeleaza `POST /sessions/{id}/pause` sau `/resume`. Nu necesita restart bot — efectul intra la bara urmatoare. Linia P&L "USD azi / ieri" apare DOAR cand valoarea e reala (non-null SI ≠ 0) — `+0.00 USD` e ascuns per camp (2026-07-20).

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

**TradingStatsPanel.tsx:** Panel statistici in Dashboard. 4 carduri: Total Semnale (jurnalul Bot Engine — singura cifra care nu vine din MT5; click → breakdown per sesiune), Total Trades, Castiguri, Pierderi (toate din `/mt5/stats`, cont-wide) + "X azi" + trend ▲/▼ vs ieri.
- **P&L Real MT5** — `equity MT5 − start_balance din profil`. Sursa de adevar absolut, include tot.
- **Comisioane + Swap** — din `/mt5/stats` (`history_deals_get` CONT-WIDE, include si Motorul AI). Dezagregat: com: X $ · swap: Y $ + **rand Azi / Ieri** (`commission_today/yesterday` + `swap_today/yesterday`).
- Cardul "P&L Bot (partial)" a fost eliminat — datele partiale (fara backfill complet) induceau in eroare.
- Sesiunile OBS (execute_trades=False) excluse din TOATE agregerile.

**Indice Saptamanal (`WeeklyStatsPanel` in `Dashboard.tsx`) — rand Comisioane (2026-07-21):** pe langa Trades/W/L/Win Rate/Total R/P&L/-DD, panoul arata acum **Comisioane** (com+swap) pentru perioada curenta vs precedenta (saptamana/luna). Sursa: `/mt5/weekly-stats` (CONT-WIDE → include AI). `ViewPeriod.costs` = com+swap (null cand nu exista date). Randul apare doar daca exista date reale.

**Comisioanele Motorului AI — DOAR in totalul cont-wide MT5 (2026-07-21):** NU exista un breakdown separat de comisioane pentru AI. Cardul Comisioane + Swap si Indicele Saptamanal folosesc `history_deals_get` la nivel de CONT, deci include automat si comisioanele AI (magic 770015) alaturi de bot + manual — acolo distinctia nu conteaza. Un card AI-specific a fost prototipat (endpoint `/ai/costs` + `AiCostsCard`) dar ELIMINAT la cererea userului: afisa Total (tot istoricul) langa Azi/Ieri/Saptamana (ferestre suprapuse, NU se aduna), ceea ce parea gresit desi cifrele erau corecte (reconciliate exact: Bot + AI = total MT5 pe saptamana). Daca se reintroduce vreodata, foloseste etichete care fac evident ca sunt ferestre cumulate, nu o partitie. Teste comisioane: `python scripts/test_dashboard_commissions.py`.

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

**NavBar.tsx:** taburi Dashboard / Custom Engine / AI Engine / Daily Engine / Settings / Notificari / Audit / Rapoarte / Ghid. Badge notificari necitite + badge joburi Audit. Toggle-urile de autostart au fost mutate in cardurile de engine din Dashboard.

**App.tsx — persistenta stare taburi:** Dashboard + Custom Engine montate permanent; restul (AI, Daily, Settings, Notificari, Audit, Rapoarte, Ghid) lazy mount la prima vizita, apoi pastrate cu CSS `hidden` (starea supravietuieste navigarii).

---

## Configurare autostart Windows

```powershell
# Necesita Administrator — creeaza doua task-uri in Task Scheduler:
# TradingBot-MT5 (MT5 la login) + TradingBot-RunAll (run_all.py + 90s delay)
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
& "c:\trading-bot\scripts\setup_autostart.ps1"

# Dezactivare autostart bot (sterge TradingBot-RunAll; MT5 doar daca AI nu-l foloseste):
& "c:\trading-bot\scripts\remove_autostart.ps1"

# Autostart MOTOR AI (separat de bot) — TradingBot-MT5 (partajat) + TradingBot-AIEngine:
& "c:\trading-bot\scripts\setup_autostart_ai.ps1"
& "c:\trading-bot\scripts\remove_autostart_ai.ps1"
```

Autostart-ul fiecarui engine (Custom / AI / Daily) se activeaza/dezactiveaza din cardul lui pe Dashboard (`/engines/{id}/autostart/*`, UAC). Daily: `scripts/setup_autostart_engine.ps1 -Engine daily` / `remove_autostart_engine.ps1 -Engine daily` (task `TradingBot-DailyEngine`, login + 150s). Toate cele 3 remove-scripturi pastreaza `TradingBot-MT5` cat timp ORICARE alt engine are autostart.

**Task-urile bot/AI ruleaza NEELEVAT (`-RunLevel Limited`) — NU schimba in Highest.** Cu Highest, sesiunile pornite de task rulau elevated → UI-ul (API neelevat) nu le putea opri/inlocui (Access Denied; `CommandLine` invizibil in WMI pentru procese neelevate) → sesiuni "fantoma" care supravietuiesc oricator restarturi din UI si tin `session.lock` (observat live 12-13 iul 2026: 20 sesiuni orfane elevate au rulat o zi pe config hardcodat). Daca task-ul vechi (Highest) inca exista, re-ruleaza setup-ul ca sa-l recreeze Limited; orfanii elevati se inchid doar dintr-un PowerShell ADMIN sau la reboot.

**Profilul la autostart (`active_profile_runtime.json`):** fisierul NU se mai sterge la stop (doar `active_profile.json`, markerul de "bot pornit") — altfel un start din CLI/autostart dupa un stop pornea sesiunile pe SESSION_CONFIG hardcodat (fara filtru AI, fara parametrii din UI), complet silentios. Acum: autostart foloseste ultimul profil activ; `_apply_profile_overrides` logheaza WARNING vizibil (log + Notificari) daca fisierul chiar lipseste (prima rulare). `run_all.py::_kill_orphan_sessions` (dupa `_kill_old_instance`) matura sesiunile orfane dupa linia de comanda si avertizeaza `[!!]` daca vede procese python elevate pe care nu le poate atinge.

**Autostart AI Engine (`scripts/setup_autostart_ai.ps1` / `remove_autostart_ai.ps1`) — aliniat cu botul:**
- Genereaza `ai_engine/start_ai_engine_auto.bat`: incarca Telegram din registry → porneste Ollama daca nu ruleaza → **asteapta ~120s** (dupa botul cu 90s, ca MT5 sa fie conectat) → lanseaza watchdog-ul + motorul **DETASAT** si iese. **Critic:** `engine.run()` iese imediat daca Ollama SAU MT5-DEMO nu sunt gata (nu are retry propriu) — asteptarea de 120s acopera cazul normal, watchdog-ul (max 5 restarturi/5 min) acopera conectarea lenta.
- **Redesign bat 2026-07-18 (incident: bat inghetat la boot → motor nepornit 5h, task blocat "Running", zero urme):** bat-ul vechi folosea `timeout` (cere handle de consola interactiv, fragil sub Task Scheduler), rula motorul in FOREGROUND si se termina cu `pause` — orice esec il suspenda la infinit, fara log. Acum: (1) fiecare pas logat cu timestamp in `data/ai/autostart.log`; (2) asteptari cu `ping -n` (imune la lipsa consolei); (3) motor + watchdog lansate DETASAT, bat-ul iese curat (supravegherea = watchdog-ul, care NU contracareaza Stop-ul din UI — acela opreste intai watchdog-ul); (4) stdout/stderr-ul motorului capturat in log (crash-urile dinainte de `_setup_logging` nu mai sunt invizibile). Sablonul din `setup_autostart_ai.ps1` si bat-ul generat sunt tinute identice; .bat = CRLF obligatoriu.
- **TradingBot-MT5 e PARTAJAT** intre cele doua autostart-uri. Ambele setup-uri il (re)creeaza idempotent (`-Force`). La stergere, fiecare remove-script sterge MT5 **doar daca celalalt engine nu-l mai foloseste** (`remove_autostart.ps1` verifica `TradingBot-AIEngine`; `remove_autostart_ai.ps1` verifica `TradingBot-RunAll`) — dezactivarea unui autostart nu lasa niciodata celalalt fara MT5.
- API: `GET/POST /ai/autostart/{status,enable,disable}` in `api/routers/ai_engine.py` (mirror al `/bot/autostart/*`, pastrate pentru compat). UI: toggle-ul din cardul AI din Dashboard, prin `/engines/ai/autostart/*`. Scripturile sunt **pur ASCII** (fara em-dash) — Windows PowerShell 5.1 le citeste ca CP1252 fara BOM, deci non-ASCII strica parsarea.

**`scripts/setup_autostart.ps1` — detectare Python in sesiuni elevate:** Foloseste `py.exe` (Python Launcher, `C:\Windows\py.exe`) in loc de `python` pentru a gasi Python. `python` nu este disponibil in sesiuni elevate (UAC) cand e instalat ca Windows Store alias — `py.exe` este system-wide si functioneaza intotdeauna. API-ul adauga `-NoExit` la `Start-Process` pentru a tine fereastra deschisa dupa terminarea scriptului (vizibil si la erori).

Variabilele Telegram (`TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`) se seteaza in User Environment Variables Windows (nu in .env) — sunt citite de `start_bot.bat` din registry. In UI, configurarea se face din sectiunea Telegram Settings (accordion in ProfilePage). Butonul "Trimite mesaj de test" (`POST /settings/telegram/test`) verifica conexiunea real-time.

**setup.bat** — Instalare Python/Node/Git via winget. Daca se instaleaza ceva nou, deschide automat o fereastra CMD noua cu PATH proaspat si continua instalarea pip/npm fara interventia utilizatorului (nu mai necesita rulare de doua ori). Foloseste `py` (Python Launcher) in loc de `python` pentru a evita Windows Store alias.

**start_ui.bat** — Script dublu-click pentru pornire dashboard fara IDE. La fiecare rulare: opreste instante vechi (taskkill dupa titlu + `scripts/kill_ports.ps1` pe porturile 8000/5173), deschide fereastra `TradingBotAPI` (uvicorn) + `TradingBotUI` (npm dev), asteapta 8s, verifica porturile si deschide browserul. Afiseaza diagnostice complete la fiecare pas. Fisierele `.bat` din proiect folosesc CRLF obligatoriu — CMD.EXE pe Windows esueaza silentios cu LF-only dupa `chcp 65001`. Cand ruleaza in Windows Terminal, ferestrele noi se deschid ca taburi noi (nu ferestre separate).

**`scripts/kill_ports.ps1`** — Opreste procesele care asculta pe porturile date (`Get-NetTCPConnection` → `Stop-Process`). Apelat din `start_ui.bat` ca fallback dupa taskkill-ul pe titlu. Separat intr-un `.ps1` deoarece CMD nu poate pune pipe-uri (`|`) in string-urile PowerShell inline din `start ...`.
