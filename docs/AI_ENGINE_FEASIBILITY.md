# Autonomous AI Trading Engine — Architectural Analysis & Feasibility Study

**Date:** 2026-07-08
**Scope:** Analysis only — no implementation. Goal: determine whether a next-generation
autonomous AI trading engine is feasible and how it would integrate with the existing
trading-bot, **without investing money yet**.

---

## 1. Complete Analysis of the Existing Application

### 1.1 Overall architecture

The system is a **rule-based, multi-session, pending-order trend-following bot** with three
decoupled planes:

| Plane | Entry point | Data source | Purpose |
|---|---|---|---|
| Backtest | `portfolio_backtest.py`, `session*_backtest.py`, API jobs | CSV (`data/*.csv`, ~1.4 GB, ~200k M15 bars/symbol) | Strategy validation, 70/30 train/test split |
| Live | `live/run_all.py` → 20 session subprocesses | MT5 Python API (demo-enforced) | Signal detection + pending-order execution |
| Dashboard | FastAPI (`api/`, port 8000) + React/Vite (port 5173) | JSON files in `data/` | Control, monitoring, reporting |

Key architectural strength: **backtest and live share the exact same strategy code path**
(`strategy/preparation._enrich()` → `strategy/structure.detect_setup()` →
`strategy/signals`). The adapter layer (`adapters/csv_source.py` vs `adapters/mt5_source.py`)
is the only difference. This is a genuinely good design — most retail bots fail here.

### 1.2 Data flow (current)

```
BACKTEST:  CSV ──► _enrich() ──► run_portfolio() ──► trades/equity ──► backtest_jobs.json ──► UI
                     │
LIVE:      MT5 ──► _enrich() ──► _check_signals() ──► _place_order() ──► MT5 pending order
                                        │                                    │
                                   signals.csv                     _update_outcomes() ◄── MT5 history
                                                                          │
                                                                    outcomes.csv ──► API ──► UI/Telegram
```

Each of the 20 live sessions is an independent OS process running an infinite loop:
sleep to next bar close → pull 2000 bars → recompute all indicators from scratch →
check pause/news state (JSON files) → update outcomes → detect setups on closed bars
(offsets 3, 2) → place BUY_STOP/SELL_STOP → Friday-close / news-close checks.

### 1.3 Trading pipeline & signal generation

- **Trend filter:** EMA200 on M30 (or D1 for H1 sessions) → direction 1/-1/0.
- **Setup:** strict pullback-in-trend (`detect_setup`): 2 rising HHs → fresh HL after last
  HH → first close above pullback-bar high, within `pullback_window` bars. Anti-lookahead
  window `j - swing_n + 1` is correctly implemented.
- **Optional criteria (max 3):** RSI band, EMA 8/20/50 alignment, candle body vs ATR
  (disabled by default).
- **Reward ladder:** number of satisfied optional criteria maps to target R
  (2.5 / 3.5 / 4.5 / 5.5R) and to risk % per level.
- **Regime columns already computed but mostly unused:** `daily_trend` (EMA200 D1),
  `f1_weekly` (EMA50 W1), `f2_adx` (ADX D1 > 25), `f3_slope`, `f4_f1f3` — computed in
  `_enrich()` with proper 1-bar lag, gated only by the optional `regime_filter_col` param.
- **Optional patterns:** flag & inside-bar (`strategy/patterns.py`), off by default.

### 1.4 Strategy execution & risk management

- Position sizing: fixed fractional (`risk_pct` of `equity × account_fraction`), lot floor 0.01.
- Live lot calc reads `trade_tick_value/size` from MT5 → always correct; backtest uses
  static approximations in `strategy/costs.py`.
- Risk controls: margin check, 3-consecutive-loss daily circuit breaker, EURUSD↔GBPUSD
  correlation block, max trades/day, ATR cap, session-hour/weekday filters, Friday close,
  news guard (ForexFactory polling → auto-pause + close), optional 3-phase break-even.
- Robust MT5 reconciliation (3 layers) with "MT5 is always the source of truth" invariant —
  operationally mature, battle-tested against broker quirks (16-char comment truncation,
  hedging-mode position IDs, retcode 10006 semantics).

### 1.5 Configuration system

- `config/standard_profile.json` (legacy backtest config) + `data/profiles/*.json` (UI
  profiles) + hardcoded `SESSION_CONFIG` dicts in each of 20 `live/sessionN_*.py` scripts +
  `data/active_profile_runtime.json` override chain. **Four sources of truth** for the same
  parameters, merged at runtime by `_apply_profile_overrides`.

### 1.6 Database structure

There is **no database**. Everything is flat files: CSV (bars, signals, outcomes),
JSON (profiles, jobs, notifications, uptime, pause state — each with its own ad-hoc
max-size/FIFO policy), pickle (`state.pkl` per session — documented corruption mode).
Concurrency is handled by per-file `threading.Lock()` in the API and by "one writer per
file" convention in live sessions.

### 1.7 Background services, scheduling, APIs

- `news_guard.py` daemon (300s poll), `api/watchdog.py` (30s poll), `api/scheduled_reports.py`
  (daily 23:30 / Friday weekly), Telegram fire-and-forget threads, Windows Task Scheduler
  autostart. API: ~12 routers, async backtest jobs with 2s client polling.

### 1.8 Logging & monitoring

Per-session `generator.log`, rate-limited notification capture into `notifications.json`,
Telegram push, uptime log, session-change audit log, MT5 health check. Monitoring is
**operational** (is the bot alive, did orders execute) not **statistical** (is the edge
decaying, is live tracking backtest — `scripts/compare_live_vs_backtest.py` exists but is
manual).

### 1.9 Performance characteristics & bottlenecks

- `mark_swings` is an O(n·N) Python loop; `detect_setup` and `simulate_trade` use
  `df.iloc[]` row access in hot loops → backtests of 200k bars × 20 symbols are
  minutes-scale, not seconds-scale. Fine for current use; a blocker for any ML/RL
  training loop that needs thousands of backtest evaluations.
- 20 processes × full indicator recompute over 2000 bars every 15 min — wasteful but
  harmless at this scale (bar-close cadence, no latency sensitivity).
- Research scripts already hit wall-clock limits (overnight scans, PID-tracked runs).

### 1.10 Scalability limitations

Single Windows machine, MT5 terminal must be open, file-based state, per-session
subprocess model (~20 process cap is fine; 200 would not be), no message bus, no
time-series database, JSON files rewritten whole on every update. None of this matters
at bar-close cadence with one broker — but it constrains what an AI layer may assume.

---

## 2. Evaluation of Current Trading Logic

### 2.1 Strengths

1. **Shared code path** backtest ↔ live (the single most important property for ML later:
   features computed identically offline and online).
2. **Disciplined anti-lookahead** (swing confirmation windows, 1-day lag on D1/W1 regime
   columns, closed-bar-only detection).
3. **Baseline-number regression testing** culture ("if numbers change, it's a bug").
4. **R-based accounting** — outcomes are already labeled in R multiples, which is exactly
   the label a meta-model needs.
5. Mature execution/reconciliation layer — the hardest, least-glamorous 80% of a live
   trading system already works.
6. Honest statistics: train/test split, p-values on S3, willingness to mark sessions
   "observation only".

### 2.2 Weaknesses

1. **The edge is thin and uniform.** S1 test +0.344R on 103 trades, S2 +0.099R on 447,
   with **negative training expectancy on S1/S2** (train −0.156R / −0.014R). A strategy
   whose train period loses and test period wins is fragile — the "edge" may be one
   favorable regime (2024–2026) rather than a durable effect. Only S3 (BTC) has
   statistical support (p=0.0075, 7/7 positive years).
2. **One strategy, 20 markets.** All sessions run the same pullback logic with different
   knobs. There is no diversification of *logic*, only of *symbols* — correlated failure
   mode when trending regimes end.
3. **Regime information is computed but barely used.** `f1_weekly/f2_adx/f3_slope/
   daily_trend` exist in every enriched DataFrame yet gate nothing by default.
4. **Binary criteria, hand-tuned thresholds.** RSI 40–65, ADX 25, EMA alignment — each a
   step function on a continuum; the reward ladder quantizes a continuous confidence into
   4 buckets with hand-picked R targets.
5. **No feedback loop.** Live outcomes (~269 so far) are recorded and displayed but never
   fed back into any decision. Session enable/disable, risk levels, and market selection
   are all manual.
6. **Selection bias in research.** Memory of past scans shows dozens of configurations
   tested per market; sessions were promoted on best test-window numbers without
   deflated-Sharpe-style multiple-testing correction. Several sessions (S7 XRP "marginal
   1.4yr", XAUUSD "regime-dependent, training negative") were promoted anyway.
7. **Config sprawl** (4 sources of truth) and **duplicated pending-order logic** between
   `engine/portfolio.py` and `live/signal_generator.py` (same lifecycle re-implemented:
   invalidate/expire/trigger).
8. **Cost model drift risk:** static `BASE_USD_APROX` rates in backtest vs live tick
   values — documented, but it means backtest $ numbers are approximations.

### 2.3 Missing market information

- Volatility *state* (only ATR level used, no vol-of-vol, no regime probability)
- Cross-asset context (DXY, yields, equity risk-on/off) — each session sees only its symbol
- Spread/liquidity time-of-day structure (spread is a constant per symbol in backtest)
- Scheduled macro events are used only defensively (pause), never as context
- No sentiment or positioning data of any kind

### 2.4 Where the architecture limits AI integration

- **No event bus:** an AI service can only communicate via polled JSON files (workable,
  as pause/news already prove, but clunky beyond a few flags).
- **No feature store / DB:** every consumer recomputes features; an ML layer needs
  point-in-time correct feature snapshots persisted per signal.
- **Slow backtester:** model selection needs 10³–10⁴ evaluations; current engine supports ~10¹/hour.
- **Signals don't carry context:** `signals.csv` stores entry/SL/TP but not the feature
  vector at detection time — the training dataset for any meta-model must be
  reconstructed after the fact.
- **~269 live outcomes** is far too small to train anything on live data alone.

---

## 3. State-of-the-Art Research Summary

Findings from academic and industry literature (sources at end):

**Multi-agent LLM trading (TradingAgents, FinAgent, ContestTrade, Trading-R1).**
[TradingAgents (arXiv:2412.20138)](https://arxiv.org/abs/2412.20138) organizes LLM agents
as analyst/researcher/trader/risk roles with debate-based consensus and reports improved
cumulative return, Sharpe, and drawdown vs baselines — **but** on short equity backtests,
with per-decision LLM costs, no slippage-realistic execution, and no published live
track record. The 2025-26 literature (e.g. "Agentic Trading: When LLM Agents Meet
Financial Markets") is candid that results are backtest-era and sensitive to prompt/data
leakage (LLMs have memorized historical price context). **Conclusion: promising for
research/analysis workflows; unproven for autonomous execution; expensive per decision.**

**Reinforcement learning.** Systematic reviews ([arXiv:2512.10913](https://arxiv.org/html/2512.10913v1))
show impressive backtest numbers but persistent issues: sample inefficiency, regime
non-stationarity, overfitting, and near-zero published evidence of retail live-money
success. Hybrid (rules + RL) outperforms pure RL. RL needs millions of environment steps;
your data supports ~10⁵ bars/symbol and ~10²–10³ trades/config. **Conclusion: full RL
policy learning is not appropriate for this project's data and capital scale.**

**Market regime detection.** HMMs (and simpler k-means/threshold vol classifiers) on
returns/volatility are standard, well-understood, and used precisely as a *trade filter /
risk scaler* ([QuantStart](https://www.quantstart.com/articles/market-regime-detection-using-hidden-markov-models-in-qstrader/),
[LSEG](https://developers.lseg.com/en/article-catalog/article/market-regime-detection)).
Filtered (not smoothed) probabilities avoid lookahead. **Conclusion: highest
value-per-complexity item available to this codebase — the regime columns already exist.**

**Meta-labeling (López de Prado).** Exactly matches this bot's shape: keep the rule-based
primary signal (side), train a secondary classifier on primary-signal outcomes to predict
P(win), use it to size or veto trades ([Wikipedia](https://en.wikipedia.org/wiki/Meta-Labeling),
[Hudson & Thames](https://hudsonthames.org/meta-labeling-a-toy-example/)). Needs hundreds-to-thousands
of labeled trades — obtainable from the backtester. Known caveat: it cannot create edge
where none exists ([QuantConnect discussion](https://www.quantconnect.com/forum/discussion/14706/why-meta-labeling-is-not-a-silver-bullet/)).
**Conclusion: the single best-fit AI technique for this system.**

**News/sentiment.** FinBERT/LLM sentiment measurably improves equity prediction models;
for intraday FX the effect is weaker and data licensing is the bottleneck. The bot already
consumes the economic calendar defensively. **Conclusion: extend calendar usage to features
(time-to-event, event importance); defer headline sentiment.**

**Validation.** Deflated Sharpe Ratio and Combinatorial Purged CV (CPCV) are the accepted
countermeasures to the exact failure mode this project's research history exhibits
(many configs tested, best test-window promoted). CPCV shows lower probability of
backtest overfitting than plain walk-forward ([SSRN 4686376](https://papers.ssrn.com/sol3/Delivery.cfm/SSRN_ID4686376_code4361537.pdf?abstractid=4686376&mirid=1)).
**Conclusion: adopt regardless of any AI plans.**

---

## 4. Proposed Architecture — "Advisor" AI Engine

### 4.1 Design philosophy

The literature and this codebase's constraints (retail capital, one machine, thin edge,
~10² live trades) rule out an end-to-end learning trader. The realistic target is a
**probabilistic decision layer on top of the existing deterministic pipeline**:

> The rules keep deciding *where* a setup is. The AI decides **whether it's worth taking,
> how big, and under what regime** — and proves itself in shadow mode before touching money.

This is meta-labeling + regime gating + adaptive risk, which is how practitioners
actually deploy ML on rule-based systems.

### 4.2 Components (new, all optional/removable)

```
                        ┌──────────────────────────────────────────────┐
                        │              AI ENGINE (new service)          │
                        │                                              │
  bars (MT5/CSV) ──────►│  Feature Service      Regime Service (HMM/   │
                        │  (point-in-time        vol-state; per symbol │
                        │   feature vectors)     + global risk-on/off) │
                        │        │                     │               │
  signal detected ─────►│  Meta-Model ◄───────────────┘               │
  (candidate from       │  P(win | features, regime)                   │
   existing rules)      │        │                                     │
                        │  Decision Policy                             │
                        │  score→ {skip | size×k | normal | boost}     │
                        │        │                                     │
                        │  Shadow Ledger (every decision + features    │
                        │   + counterfactual outcome, SQLite)          │
                        └────────┼─────────────────────────────────────┘
                                 ▼
                    data/ai_advice.json  (polled by signal_generator,
                    same pattern as paused_sessions.json / news guard)
```

1. **Feature Service** — snapshots the enriched row + regime state + calendar context at
   signal time; persists it keyed by `sig_id` (fixes the "signals don't carry context" gap).
2. **Regime Service** — 2–3-state HMM (or quantile vol classifier) per symbol on daily
   returns/ATR, plus a global risk state; outputs filtered probabilities, updated on bar close.
3. **Meta-Model** — gradient-boosted trees (LightGBM/XGBoost) trained on **backtest-generated
   trades** (thousands available) with CPCV validation, calibrated probabilities
   (isotonic/Platt), retrained on schedule with walk-forward discipline. Inputs: optional-criteria
   values as *continuous* features, regime probabilities, ATR percentile, spread, hour/day,
   pullback depth, time-since-news. Output: calibrated P(profit) and expected R.
4. **Decision Policy** — deterministic, explainable mapping from calibrated probability to
   action: veto / half-size / normal / (later) 1.25×. Fractional-Kelly-capped. Never
   invents trades; can only reduce or skip. "Deciding when not to trade" falls out naturally.
5. **Shadow Ledger** — SQLite. Every candidate signal, feature vector, model score, action
   the policy *would* take, and eventual outcome — enabling continuous self-evaluation
   (calibration curves, live-vs-backtest drift, edge decay alarms) before and after go-live.
6. **Optional LLM layer (later, cheap mode)** — a scheduled (not per-tick) LLM pass that
   summarizes macro calendar + regime state into a daily "context brief" and flags
   anomalies for the human. Advisory text only; never a trade trigger.

### 4.3 Multi-agent assessment (Phase 5 answer)

A TradingAgents-style committee (Technical/Macro/News/Sentiment/Risk/Allocation/Execution
agents debating per trade) is **technically sound as a research pattern but not
recommended here**:

- Each decision would cost LLM inference ($0.01–$0.50/decision × ~dozens of signals/day)
  for signals risking ~$1–8 each at current capital — cost-per-decision can exceed risk-per-trade.
- No published live evidence that debate-consensus beats a calibrated classifier on
  bar-close FX signals; published wins are equity backtests with likely data-leakage.
- Latency and reliability: 20 sessions × LLM calls on bar close is a new failure surface.

**What survives from the multi-agent idea:** the *separation of concerns as services*
(regime, features, meta-model, policy = your "agents", communicating via a shared ledger
instead of debate), plus at most one scheduled LLM "analyst" producing a daily brief.
Consensus is replaced by a calibrated probability plus deterministic policy — same intent,
auditable, ~zero marginal cost.

### 4.4 Autonomy features mapped to design

| Requested capability | How delivered |
|---|---|
| Market structure analysis | existing `detect_setup` (kept as primary) |
| Regime understanding | Regime Service (HMM filtered probabilities) |
| Historical pattern learning | Meta-model trained on backtest trade corpus |
| Macro event monitoring | existing news_guard → features (time-to-event, impact) |
| News/sentiment | deferred (Phase 3 optional; FinBERT on calendar headlines) |
| Probabilities not certainties | calibrated P(win), expected R |
| Dynamic strategy selection | policy weights per (session × regime); pause sessions whose regime-conditional edge disappears |
| Adaptation | scheduled walk-forward retrain + drift alarms |
| Autonomous risk | policy scales risk_pct by probability & regime, capped fractional Kelly |
| Deciding not to trade | veto threshold |
| Learning from decisions | Shadow Ledger closes the loop |
| Self-evaluation | calibration + live-vs-backtest tracking, auto-alert on decay |

Manual configuration reduced: reward ladder thresholds, per-session risk levels, and
session enable/disable become policy outputs (human-approved at first, automatic later).

---

## 5. Feasibility Study (Phase 6)

### 5.1 Verdict

**Feasible in the "advisor/meta-labeling" form. Not feasible (at acceptable risk/cost) in
the "fully autonomous self-learning multi-agent trader" form.** Reasons:

- **Data:** ~200k M15 bars/symbol is ample for regime models and for backtest-generated
  meta-labels (10³–10⁴ trades), but 2–3 orders of magnitude short for deep RL; 269 live
  trades cannot train anything.
- **Edge:** AI can only amplify/filter an existing edge. S1/S2's negative train
  expectancy means the priority is *verifying the edge is real* (deflated Sharpe, CPCV),
  not layering intelligence on it. S3 is the only statistically defensible base.
- **Compute:** LightGBM + HMM retraining = minutes on the existing PC. No GPU, no cloud
  needed. RL/LLM-per-decision would need both.
- **Latency:** bar-close cadence (15 min) makes latency a non-issue — a major point in
  favor of feasibility.
- **Costs:** advisor path ≈ $0 infra (local Python, SQLite) + optional ~$5–30/month LLM
  for daily briefs. Multi-agent-per-trade path ≈ $100–1000+/month at scale, unjustifiable
  at current capital.
- **Regulatory:** demo-enforced today; personal live trading of own funds via a retail
  broker has no licensing burden in most EU jurisdictions (Romania included) as long as
  it's your own account; taxes and broker T&Cs on automated trading apply. Offering the
  system to others would change this entirely.
- **Key risks:** backtest overfitting (the #1 killer — [López de Prado](https://www.garp.org/hubfs/Whitepapers/a1Z1W0000054x6lUAA.pdf)),
  regime shift invalidating both rules and meta-model simultaneously, silent feature
  drift between offline and online computation, automation bias (trusting the score),
  and small-sample evaluation noise (a 100-trade shadow period cannot distinguish
  +0.1R from 0R edge — patience required).

### 5.2 What is unrealistic and the better alternative

| Vision element | Why unrealistic here | Alternative |
|---|---|---|
| End-to-end RL trader | data/sample inefficiency, no live evidence, non-stationarity | meta-labeling on rule signals |
| Per-trade LLM agent debate | cost ≥ risk-per-trade, unproven, new failure surface | calibrated classifier + daily LLM brief |
| Full autonomy from day 1 | 269 live trades of evidence; thin edge | staged autonomy: shadow → veto-only → sizing → gating |
| "Minimize all manual config" | some knobs are safety valves | automate *analysis*, keep human approval on risk changes until shadow stats mature |

---

## 6. Integration Plan (Phase 7)

Guiding rule: **the AI engine is one new process + a few files/tables; `signal_generator.py`
changes by ~30 lines.** Everything reuses proven patterns (JSON-file signaling, daemon
services, MT5-first invariants).

### 6.1 Architectural changes

1. **New service `ai/engine.py`** — runs like news_guard (single daemon or separate
   process): on each bar-close tick, refresh regime states; on request, score signals.
2. **Advice file `data/ai_advice.json`** — `{sig_key: {action, p_win, size_mult, regime,
   reasons[], ts}}`, written by the engine, polled by sessions (same as
   `paused_sessions.json` — zero new infra, effect at next bar, no bot restart).
3. **Hook in `_check_signals()`** — after a setup is detected and before `_place_order`:
   write candidate → wait ≤2s for advice → apply `{skip | size_mult}` → log advice fields
   into `signals.csv` extra columns. If the AI engine is down or slow → **proceed exactly
   as today** (fail-open, current behavior is the fallback).
4. **SQLite `data/ai/ledger.db`** — feature snapshots, scores, decisions, outcomes
   (joined from outcomes.csv), model metadata. First real database, scoped to AI only.
5. **Model registry `data/ai/models/`** — versioned LightGBM/HMM artifacts + training
   manifest (data range, CPCV folds, metrics, git hash). Rollback = repoint a symlink/
   config entry to the previous version.
6. **API router `api/routers/ai.py`** — status, current regimes, calibration stats,
   enable/disable, mode (`off | shadow | veto | full`); UI panel later.
7. **Backtester speed pass (enabler):** vectorize `mark_swings` / replace `iloc` row access
   with numpy arrays in `simulate_trade` & `detect_setup` — 10–50× likely, needed for
   CPCV/retraining loops. Must reproduce baseline numbers exactly (existing invariant
   protects this).

### 6.2 Event flow (live, full mode)

```
bar close ─► session detects setup ─► writes candidate (features via shared _enrich row)
          ─► ai engine scores (regime + meta-model) ─► ai_advice.json
          ─► session applies advice ─► place order (or skip) ─► MT5
          ─► outcome lands in outcomes.csv ─► nightly job joins into ledger.db
          ─► weekly retrain/calibration report ─► Telegram + UI
```

No message queue needed at this scale; if ever needed, swap file-polling for Redis
pub/sub without touching strategy code.

### 6.3 Deployment, monitoring, rollback

- Deploy: engine is a new entry in `run_all.py`'s process list (or standalone). Modes are
  runtime-switchable via the API (like pause) — no restarts.
- Monitoring: engine heartbeat file watched by existing watchdog; weekly calibration
  report (Brier score, realized-vs-predicted win rate by bucket, edge trend) via the
  existing scheduled_reports + Telegram path.
- Rollback: set mode `off` (instant, file flag) → system is byte-identical to today's
  behavior; model rollback via registry pointer.

---

## 7. Roadmap, Complexity, Cost (Phases 8.12–8.16)

| Milestone | Content | Effort (focused) | Exit criterion |
|---|---|---|---|
| **M0 — Statistical hardening** | Deflated Sharpe + CPCV evaluation of all 20 sessions on existing backtester; demote sessions that fail | 1–2 weeks | Honest list of sessions with real edge |
| **M1 — Backtester speed** | Vectorize hot loops; baseline numbers reproduced exactly | 1 week | ≥10× speedup, baselines identical |
| **M2 — Feature & ledger** | Feature snapshot per signal (live+backtest), SQLite ledger, signals.csv extra columns | 1–2 weeks | Every new signal carries its feature vector |
| **M3 — Regime service** | HMM/vol-state per symbol + global; UI panel; *shadow only* | 2 weeks | Regime probabilities logged per signal |
| **M4 — Meta-model v1** | LightGBM on backtest trades, CPCV, calibration; scores logged in shadow | 2–3 weeks | Calibrated P(win); shadow ledger accumulating |
| **M5 — Shadow evaluation** | ≥ 3 months / ≥ 150–300 live-shadow signals; compare "AI-filtered" vs actual counterfactually | calendar time | AI-filtered expectancy ≥ baseline with CI |
| **M6 — Veto mode** | AI may only *skip* trades (demo) | 1 week + observation | No degradation vs shadow prediction |
| **M7 — Sizing mode** | probability-scaled risk (0.5×–1.25×, Kelly-capped) | 1 week + observation | Improved risk-adjusted R on demo |
| **M8 — Optional** | daily LLM context brief; calendar-distance features; session auto-gating by regime | open | — |

- **Complexity estimate:** M0–M4 ≈ 6–9 weeks of focused work; total to sizing mode
  ≈ 3–4 months of code + ≥3 months mandatory shadow/demo calendar time.
- **Cost estimate:** infrastructure $0 (existing PC); optional LLM brief $5–30/month;
  optional news-sentiment data feed $0–50/month (skippable). The real cost is time.
- **Performance:** engine adds ≤2s at bar close (fail-open), negligible CPU; retraining
  is offline minutes-scale.
- **Scalability:** design stays valid to ~50 sessions / few brokers; beyond that,
  introduce Redis + a proper TSDB (out of scope now).

## 8. Technical risks (top 5, with mitigations)

1. **Overfitting the meta-model to backtest artifacts** → CPCV, purging/embargo, feature
   count discipline (<20), calibration on held-out years, deflated metrics.
2. **Offline/online feature skew** → single `_enrich()` code path (already exists), plus a
   parity test comparing live snapshot vs recomputed backtest features for the same bar.
3. **Small-sample false confidence in shadow results** → predefine sample-size gates
   (no promotion before N≥150 and CI excludes 0).
4. **Regime model instability (state flipping)** → probability smoothing + hysteresis;
   act only on sustained state changes.
5. **Base-strategy edge decay** (AI can't fix a dead edge) → M0 first; continuous
   edge-trend alarm in the ledger.

## 9. Final recommendation (Phase 8.18)

**Technically viable: yes — as a staged advisor engine (regime detection + meta-labeling
+ adaptive sizing) built on the existing, well-separated pipeline. Economically viable:
yes at ~$0 infra cost, provided expectations are calibrated** — at $800–$1,000 capital and
~+0.1–0.3R thin edges, the AI layer's realistic contribution is *filtering losers and
sizing winners*, worth perhaps 10–50% improvement in risk-adjusted expectancy, not a
money machine. The fully autonomous multi-agent LLM trader from the vision is **not
recommended**: per-decision cost, absence of live evidence, and this project's data scale
argue against it; its valuable ideas (role separation, consensus, self-critique) are
captured more cheaply by the service decomposition + calibrated probability + shadow
ledger proposed here.

**Do first, before any AI code:** M0 (deflated Sharpe / CPCV audit of the 20 sessions).
It costs two weeks, uses only existing tools, and determines whether there is an edge
worth amplifying — which is the entire premise of the project.

---

### Sources

- [TradingAgents: Multi-Agents LLM Financial Trading Framework (arXiv:2412.20138)](https://arxiv.org/abs/2412.20138) · [project page](https://tradingagents-ai.github.io/) · [GitHub](https://github.com/tauricresearch/tradingagents)
- [Agentic Trading: When LLM Agents Meet Financial Markets (arXiv:2605.19337)](https://arxiv.org/html/2605.19337v1)
- [ContestTrade: Multi-Agent Trading via Internal Contest (arXiv:2508.00554)](https://arxiv.org/pdf/2508.00554)
- [RL in Financial Decision Making: Systematic Review (arXiv:2512.10913)](https://arxiv.org/html/2512.10913v1)
- [Trading-R1: LLM Reasoning via RL (arXiv:2509.11420)](https://ideas.repec.org/p/arx/papers/2509.11420.html)
- [Market Regime Detection using HMM — QuantStart](https://www.quantstart.com/articles/market-regime-detection-using-hidden-markov-models-in-qstrader/) · [LSEG Dev Portal](https://developers.lseg.com/en/article-catalog/article/market-regime-detection) · [QuestDB glossary](https://questdb.com/glossary/market-regime-detection-using-hidden-markov-models/)
- [Meta-Labeling — Wikipedia](https://en.wikipedia.org/wiki/Meta-Labeling) · [Hudson & Thames toy example](https://hudsonthames.org/meta-labeling-a-toy-example/) · [QuantConnect: not a silver bullet](https://www.quantconnect.com/forum/discussion/14706/why-meta-labeling-is-not-a-silver-bullet/)
- [López de Prado — The 10 Reasons Most ML Funds Fail (GARP)](https://www.garp.org/hubfs/Whitepapers/a1Z1W0000054x6lUAA.pdf)
- [Deflated Sharpe Ratio (ResearchGate)](https://www.researchgate.net/publication/286121118_The_Deflated_Sharpe_Ratio_Correcting_for_Selection_Bias_Backtest_Overfitting_and_Non-Normality)
- [Backtest Overfitting in the ML Era (SSRN 4686376)](https://papers.ssrn.com/sol3/Delivery.cfm/SSRN_ID4686376_code4361537.pdf?abstractid=4686376&mirid=1) · [Purged CV — Wikipedia](https://en.wikipedia.org/wiki/Purged_cross-validation)
- [FinBERT](https://finbert.org/) · [Financial Sentiment with LLMs and FinBERT (arXiv:2410.01987)](https://arxiv.org/abs/2410.01987) · [Hybrid Sentiment for Market-Neutral Alpha (MDPI)](https://doi.org/10.3390/ai7040138)
