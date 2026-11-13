export interface BotStatus {
  running: boolean;
  pid: number | null;
  sessions_active: number;
  sessions_paused: number;
  sessions_total: number;
  active_profile_id: string | null;
  active_profile_name: string | null;
  active_profile_start_balance: number | null;
  last_started_at: string | null;
  last_stopped_at: string | null;
}

export interface Mt5Status {
  connected: boolean;
  account: string | null;
  server: string | null;
  balance: number | null;
  equity: number | null;
  currency: string | null;
  algo_trading_enabled: boolean | null;
  error: string | null;
}

export interface Mt5EquityPoint {
  date: string;
  value: number;
}

export interface Mt5EquityCurveResponse {
  connected: boolean;
  metric?: "usd" | "r";
  points: Mt5EquityPoint[];
  error: string | null;
}

export interface Mt5TradeStats {
  connected: boolean;
  total_trades: number;
  by_source?: { bot: number; ai: number; manual: number; daily?: number; noisy?: number };
  wins: number;
  losses: number;
  trades_today: number;
  trades_yesterday: number;
  wins_today: number;
  wins_yesterday: number;
  losses_today: number;
  losses_yesterday: number;
  pnl_today: number | null;
  pnl_yesterday: number | null;
  pnl_total: number | null;
  commission_total: number | null;
  swap_total: number | null;
  commission_today: number | null;
  swap_today: number | null;
  commission_yesterday: number | null;
  swap_yesterday: number | null;
  error: string | null;
}

export interface SessionStatus {
  id: string;
  label: string;
  markets: string[];
  direction: string;
  tf: string;
  hours: string;
  validated: boolean;
  execute: boolean;
  capital_pct: number;
  running: boolean;
  pid: number | null;
  signals_today: number;
  signals_yesterday: number;
  signals_total: number;
  last_signal_time: string | null;
  // Rezultatele (trades/wins/P&L) vin exclusiv din MT5 — vezi Mt5SessionStat.
  paused: boolean;
  news_paused: boolean;
  news_events: Array<{
    title: string;
    currency: string;
    impact: string;
    event_time: string;
    minutes_to: number;
  }>;
}

export interface Signal {
  signal_id: string;
  time: string;
  symbol: string;
  direction: number;
  dir_str: string;
  entry: number;
  sl: number;
  tp: number;
  r_ratio: number;
  status: string | null;   // starea din jurnalul Custom Engine: ai_reject, expirat, TP, SL...
}

export interface ProfileSession {
  id: string;
  session_key: string;
  label: string;
  enabled: boolean;
  markets: string[];
  entry_tf: string;
  trend_tf: string;
  direction: string;
  pullback_window: number;
  session_start: number;
  session_end: number;
  skip_hours: number[];
  skip_weekdays: number[];
  expire_bars: number;
  account_fraction: number;
  // Lot FIX per ordin (optional, oprit by default). Cand e activ, sizing-ul NU se
  // mai face pe fractie/risc — se plaseaza volum fix, redus automat daca depaseste
  // capitalul disponibil. Simetric cu market_overrides.fixed_lots din AI Engine.
  fixed_lots_enabled?: boolean;
  fixed_lots?: number | null;
  risk_pct: number;
  risk_base: number;
  risk_mid: number;
  risk_top: number;
  risk_max: number;
  execute_trades: boolean;
  rsi_enabled: boolean;
  rsi_buy_min: number;
  rsi_buy_max: number;
  rsi_sell_min: number;
  rsi_sell_max: number;
  ema_alignment_enabled: boolean;
  adx_d1_enabled?: boolean;
  pullback_enabled?: boolean;
  body_strength_enabled: boolean;
  body_strength_min_atr_ratio: number;
  atr_max_pips: Record<string, number>;
  circuit_breaker: number;
  r_base: number;
  rr_level?: "short" | "standard" | "extended";
  r_mid: number;
  r_top: number;
  r_max: number;
  r_mid_threshold: number;
  r_top_threshold: number;
  r_max_threshold: number;
  backtest_results: BacktestResult | null;
  friday_close_enabled?: boolean;
  friday_close_hour?: number;
  news_protection_enabled?: boolean;
  news_impact_level?: number;
  news_pre_minutes?: number;
  news_post_minutes?: number;
  smart_news_enabled?: boolean;
  max_concurrent_per_market?: number;
  min_bars_between_trades?: number;
  break_even_enabled?: boolean;
  be_phase2_enabled?: boolean;
  be_trigger_pct?: number;
  be_lock1_pct?: number;
  be_lock2_pct?: number;
  be_phase2_zone_pct?: number;
  // Flag Pattern
  flag_enabled?: boolean;
  flag_r_ratio?: number;
  flag_risk_pct?: number;
  // Inside Bar Breakout
  inside_bar_enabled?: boolean;
  inside_bar_r_ratio?: number;
  inside_bar_risk_pct?: number;
  // Filtru AI Pre-Trade (validare finala inainte de MT5)
  ai_filter_enabled?: boolean;
  ai_filter_level?: "permissive" | "balanced" | "strict";
  // Strict (fail-closed): AI indisponibil → ordinul NU se plaseaza (default off = fail-open)
  ai_filter_strict?: boolean;
  // Multi-Council Consensus — pana la 3 consilii pe surse AI distincte
  ai_filter_primary_source?: string | null;
  ai_filter_secondary_source?: string | null;
  ai_filter_tertiary_source?: string | null;
  // Roluri AI optionale (Additional AI Roles)
  ai_role_quant_enabled?: boolean;
  ai_role_devils_advocate_enabled?: boolean;
}

export interface TelegramConfig {
  token_masked: string;
  chat_id: string;
  configured: boolean;
  important_only: boolean;
}

export interface TimezoneOption {
  tz: string;
  label: string;
}

export interface TimezoneConfig {
  timezone: string;
  label: string;
  supported: TimezoneOption[];
}

export interface Profile {
  id: string;
  name: string;
  description: string;
  updated_at: string | null;
  sessions: ProfileSession[];
  start_balance: number;
  capital_protection_enabled?: boolean;
  capital_protection_threshold_pct?: number;
  // Capital bot aliniat cu motorul AI: sync MT5 (default) sau capital fix alocat
  capital_sync_mt5?: boolean;
  capital_usd?: number;
}

export interface ProfileSummary {
  id: string;
  name: string;
  description: string;
  updated_at: string | null;
  sessions: number;
}

export interface WeekdayStat {
  name: string;
  trades: number;
  losses: number;
  loss_rate: number;
  expectancy: number;
}

export interface HourStat {
  trades: number;
  losses: number;
  loss_rate: number;
  expectancy: number;
}

// M0 — verdict de robustete statistica (vezi docs/M0_METHOD.md).
export interface RobustnessResult {
  verdict: "KEEP" | "OBSERVE" | "DEMOTE" | "INSUFF";
  notes: string[];
  prob_positive: number | null;   // P(edge>0) din bootstrap; ≥0.95 = distinct de zgomot
  ci_low: number | null;          // interval de incredere 95% pe expectancy (R)
  ci_high: number | null;
  frac_positive: number | null;   // fractia de fold-uri pozitive (stabilitate in timp)
  breakeven_trials: number;       // N* — cate variante ar explica edge-ul prin noroc
  psr_vs_zero: number | null;
  sharpe: number | null;
  trend_rho: number | null;       // trend Spearman al expectancy pe fold-uri
  fold_exp: (number | null)[];    // expectancy per sub-perioada
  n: number;
}

export interface BacktestResult {
  total_trades: number;
  win_rate: number;
  expectancy: number;
  max_dd: number;
  split_date: string;
  date_from: string | null;
  date_to: string | null;
  start_balance: number;
  final_balance?: number;
  skipped_margin?: number;
  train: { trades: number; expectancy: number };
  test: { trades: number; expectancy: number };
  per_symbol: Record<string, { trades: number; win_rate: number; expectancy: number }>;
  direction_stats?: Record<string, { trades: number; wins: number; losses: number; win_rate: number; expectancy: number }>;
  robustness?: RobustnessResult | null;
  /** validitatea rezultatului: R imposibil (contract nereprezentat), date vechi, ce NU se simuleaza */
  validity?: { valid: boolean; warnings: string[]; not_simulated: string[] } | null;
  be_lock_count?: number;
  be_lock2_count?: number;
  flag_stats?: { trades: number; win_rate: number; expectancy: number };
  inside_bar_stats?: { trades: number; win_rate: number; expectancy: number };
  flag_was_enabled?: boolean;
  inside_bar_was_enabled?: boolean;
  markets: string[];
  skipped_markets?: string[];
  session_id: string;
  weekday_stats?: Record<number, WeekdayStat>;
  hour_stats?: Record<number, HourStat>;
}

export interface Mt5PeriodStats {
  start: string;
  end: string;
  trades: number;
  wins: number;
  losses: number;
  win_rate: number;
  pnl_usd: number;
  max_dd_usd: number;
  total_r: number | null;
  max_dd_r: number | null;
  commission_usd?: number;
  swap_usd?: number;
}

export interface Mt5WeeklyStats {
  connected: boolean;
  current_week: Mt5PeriodStats;
  previous_week: Mt5PeriodStats;
  current_month: Mt5PeriodStats;
  previous_month: Mt5PeriodStats;
  error: string | null;
}

export interface BacktestJob {
  job_id: string;
  status: "pending" | "running" | "done" | "error";
  session_id: string;
  session_label: string;
  markets: string[];
  entry_tf: string;
  trend_tf: string;
  direction: string;
  started_at: string;
  completed_at: string | null;
  date_from: string | null;
  date_to: string | null;
  start_balance: number;
  error: string | null;
  results: BacktestResult | null;
  session_snapshot: Record<string, unknown> | null;
}

export interface BacktestHistoryEntry {
  id: string;
  timestamp: string;
  session_id: string;
  session_label: string;
  markets: string[];
  entry_tf: string;
  trend_tf: string;
  direction: string;
  start_balance: number;
  date_from: string | null;
  date_to: string | null;
  results: BacktestResult;
  session_snapshot: Record<string, unknown> | null;
}

export interface Meta {
  available_markets: string[];
  timeframes: string[];
  trend_timeframes: string[];
  directions: string[];
  weekday_names: Record<string, string>;
}

export interface DataFileInfo {
  symbol: string;
  tf: string;
  exists: boolean;
  bars: number;
  last_date: string | null;
}

export interface DataCheckResult {
  results: DataFileInfo[];
  all_available: boolean;
  missing: DataFileInfo[];
}

export interface DownloadFileResult {
  symbol: string;
  mt5_symbol: string | null;
  tf: string;
  success: boolean;
  bars: number;
  needs_scroll: boolean;
  error: string | null;
}

export interface DownloadJob {
  job_id: string;
  status: "pending" | "running" | "done" | "error";
  label: string;
  markets: string[];
  timeframes: string[];
  started_at: string;
  completed_at: string | null;
  results: DownloadFileResult[];
  any_needs_scroll: boolean;
  error: string | null;
}

// ── Notifications ─────────────────────────────────────────────────────────────

export interface NotificationItem {
  id: string;
  time: string;
  text: string;
  text_plain: string;
  category: "ai" | "order" | "signal" | "news" | "session" | "bot" | "trade" | "system";
  read: boolean;
}

export interface NotificationsResponse {
  items: NotificationItem[];
  unread: number;
}

// ── Reports ───────────────────────────────────────────────────────────────────

export interface MarketStat {
  symbol: string;
  trades: number;
  wins: number;
  losses: number;
  total_r: number;
  win_rate: number;
  expectancy: number;
  pnl_usd: number | null;
  sessions: string[];
}

/** Statistici pe un grup de tranzactii MT5 inchise — api/trade_stats.py::summarize (sursa unica
 *  pentru Top 5 Piete, Rapoarte → Piete si Rapoarte → Comisioane+Swap). */
export interface TradeGroupStats {
  trades: number;
  wins: number;
  losses: number;
  breakeven: number;
  /** wins / (wins + losses), % */
  win_rate: number;
  trades_with_r: number;
  total_r: number;
  /** R mediu pe trade-urile cu SL (null = niciun trade cu R) */
  expectancy_r: number | null;
  /** profitul deal-urilor de iesire — spread-ul e deja inclus */
  pnl_gross: number;
  commission: number;
  swap: number;
  /** comision + swap */
  costs: number;
  /** brut + comision + swap */
  pnl_net: number;
  cost_per_trade: number;
  /** spread estimat la spread-ul curent × volum (negativ), DEJA in pnl_gross; null = necunoscut */
  spread_est: number | null;
  spread_est_trades: number;
}

export type TopMarketsSort = "net" | "r" | "gross" | "trades";

export interface Mt5TopMarketEntry extends TradeGroupStats {
  symbol: string;
  /** compat: = pnl_gross */
  pnl_usd: number;
  /** compat: = expectancy_r ?? 0 */
  expectancy: number;
}

export interface Mt5TopMarketsResponse {
  connected: boolean;
  items: Mt5TopMarketEntry[];
  total_markets?: number;
  sort?: TopMarketsSort;
  totals?: TradeGroupStats;
  error: string | null;
}

export interface Mt5MarketStatsResponse {
  connected: boolean;
  items: Mt5TopMarketEntry[];
  total_markets?: number;
  totals?: TradeGroupStats;
  error: string | null;
}

export interface Mt5SessionStat {
  session_id: string;
  symbol: string;
  trades_today: number;
  trades_total: number;
  wins: number;
  losses: number;
  win_rate: number;
  pnl_usd_today: number;
  pnl_usd_yesterday: number;
  last_trade_time: string | null;
}

export interface Mt5SessionsResponse {
  connected: boolean;
  items: Mt5SessionStat[];
  error: string | null;
  unassigned?: Record<string, number>;   // tranzactii pe piete fara card (ex: AI pe AUDUSD)
}

// Filtrul de sursa al Dashboard-ului (pagina intreaga) — default "all".
export type SourceFilter = "all" | "bot" | "ai" | "daily" | "noisy" | "manual";

export interface Mt5Transaction {
  ticket: number;
  symbol: string;
  direction: number;
  dir_str: string;
  status: string;
  entry: number;
  sl: number | null;
  tp: number | null;
  r_ratio: number | null;
  entry_time: string | null;
  exit_price: number | null;
  exit_time: string | null;
  result_r: number | null;
  pnl_usd: number;
  commission_usd: number;
  swap_usd: number;
  // Atribuire din magic + comment-ul ordinului (api/mt5_pool.py::classify_trade)
  source: "bot" | "ai" | "daily" | "noisy" | "manual";
  session_id: string | null;
  strategy: "pullback" | "inside_bar" | "flag" | "smart_news" | null;
  ai_approved: boolean | null;     // verdictul Filtrului AI Pre-Trade (doar bot)
  ai_confidence: number | null;
}

export interface Mt5TransactionsResponse {
  connected: boolean;
  items: Mt5Transaction[];
  total: number;
  error: string | null;
}

export interface Mt5CostsResponse {
  connected: boolean;
  items: CostStat[];
  totals?: TradeGroupStats | null;
  by_source?: CostSourceStat[];
  /** fereastra de istoric (zile) */
  days?: number;
  error: string | null;
}

export interface Mt5CostsDailyResponse {
  connected: boolean;
  items: CostsDayEntry[];
  total_commission: number;
  total_swap: number;
  total_costs: number;
  totals?: TradeGroupStats;
  error: string | null;
}

export interface UptimeEntry {
  event: "start" | "stop";
  time: string;
  profile: string;
  stopped_at: string | null;
  duration_sec: number | null;
}

export interface UptimeResponse {
  items: UptimeEntry[];
}

export interface SessionChangeEntry {
  id: string;
  time: string;
  profile_id: string;
  profile_name: string;
  sessions_changed: Array<{
    session_id: string;
    session_label: string;
    markets: string[];
    changes: Record<string, { from: unknown; to: unknown }>;
  }>;
}

export interface SessionChangesResponse {
  items: SessionChangeEntry[];
}

export interface SystemLogEntry {
  time:    string;
  session: string;
  level:   "INFO" | "WARNING" | "ERROR";
  message: string;
}

export interface SystemLogsResponse {
  items: SystemLogEntry[];
  total: number;
}

export interface CostStat extends TradeGroupStats {
  symbol: string;
  trades_with_mt5: number;
  commission_usd: number;
  swap_usd: number;
  total_costs: number;
  sessions: string[];
  has_cost_data: boolean;
}

export interface CostSourceStat extends TradeGroupStats {
  source: "bot" | "ai" | "daily" | "noisy" | "manual";
}

export interface CostsDayAggregate {
  commission_usd: number;
  swap_usd: number;
  total_costs: number;
  trades_with_cost: number;
  has_cost_data: boolean;
}

export interface CostsDayEntry extends TradeGroupStats {
  date: string;
  trades_with_cost: number;
  commission_usd: number;
  swap_usd: number;
  total_costs: number;
  pnl_usd: number | null;
  has_cost_data: boolean;
}

// ── AI Engine (motor autonom AI — ai_engine/) ────────────────────────────────

export interface AiScorecard {
  decisions: number;
  waits: number;
  closed_trades: number;
  wins?: number;      // result_r > 0
  losses?: number;    // result_r < 0 (break-even nu e nici una)
  total_R: number;
  expectancy_R: number;
  win_rate: number | null;
}

export interface AiStatus {
  running: boolean;
  pid: number | null;
  ts: string | null;
  mode: "demo" | "shadow" | null;
  account_is_demo?: boolean;
  model: string | null;
  markets: string[] | null;
  equity: number | null;
  scorecard: AiScorecard | null;
  last_errors: { ts: string; where: string; error: string }[];
  // Config per piata: statistici SEPARATE per simbol + pietele izolate
  scorecard_by_symbol?: Record<string, AiScorecard> | null;
  isolated_markets?: string[] | null;
  market_status?: Record<string, AiMarketStatus> | null;
  global_limits?: { max_open_positions: number; max_daily_loss_R: number; daily_r: number } | null;
}

// Override-uri per piata (toate campurile optionale; lipsa = comportament global)
export interface MarketOverride {
  capital_fraction?: number | null;    // 0.05-1.0 — fractia din equity pt sizing
  risk_pct?: number | null;            // cap risc/trade pe piata
  max_rr?: number | null;              // plafon R:R (TP peste e limitat)
  max_daily_loss_R?: number | null;    // stop zilnic pe piata
  max_trades_per_day?: number | null;  // anti-overtrading
  fixed_lots?: number | null;          // volum FIX per ordin (null = sizing dinamic pe risc)
  isolated?: boolean;                  // LEGACY — inlocuit de mode
  mode?: "active" | "observe";         // observe = analizeaza, ZERO ordine, exclus din scorecard
}

// Starea LIVE a limitelor unei piete (status.json → market_status)
export interface AiMarketStatus {
  mode: "active" | "observe";
  daily_r: number;
  trades_today: number;
  max_daily_loss_R: number | null;
  max_trades_per_day: number | null;
  can_open: boolean;
  blocked_reason: string | null;
}

// Raspunsul POST /ai/lot-info — costul real (MT5) al unui volum fix pe o piata
export interface AiLotInfo {
  ok: boolean;
  detail?: string;
  symbol?: string;
  lots?: number;                           // volumul introdus de utilizator
  effective_lots?: number;                 // volumul REAL plasat (snap la broker)
  snapped?: boolean;                       // true daca eff != lots (a fost ajustat)
  below_min?: boolean;                     // introdus sub volume_min
  above_max?: boolean;                     // introdus peste volume_max
  price?: number;
  margin_usd?: number | null;              // marja pentru volumul EFECTIV
  value_per_price_unit_usd?: number | null; // USD per 1.0 unitate de pret la volumul efectiv
  volume_min?: number;
  volume_step?: number;
  volume_max?: number;
  free_margin?: number | null;
  currency?: string | null;
}

export interface AiOutcomeInfo {
  status: string;
  exit_price: number | null;
  result_r: number | null;
  pnl_usd: number | null;
}

export interface AiDecision {
  id: number;
  ts: string;
  symbol: string;
  action: "OPEN_LONG" | "OPEN_SHORT" | "CLOSE" | "WAIT";
  order_type: "market" | "stop" | null;
  entry: number | null;
  sl: number | null;
  tp: number | null;
  risk_pct: number | null;
  confidence: number;
  rationale: string;
  exec_status: string;
  exec_detail: string;
  ticket: number | null;
  council_id: number;
  outcome: AiOutcomeInfo | null;
}

export interface AiCouncilTranscript {
  council_id: number;
  ts: string;
  symbol: string;
  trigger: string;
  duration_s: number;
  transcript: Record<string, Record<string, unknown> | string>;
}

export interface AiConfig {
  markets: string[];
  mode: "demo" | "shadow";
  model: string;
  risk_pct_default: number;
  risk_pct_max: number;
  max_open_positions: number;
  disabled_triggers?: string[];
  max_daily_loss_R: number;
  heartbeat_hours: number;
  council_cooldown_min: number;
  // Capitalul AI (baza de sizing): sync MT5 (default) sau capital fix alocat
  capital_sync_mt5?: boolean;
  capital_usd?: number;
  // Roluri optionale de consiliu (Additional AI Roles)
  role_quant_enabled?: boolean;
  role_devils_advocate_enabled?: boolean;
  // Consiliu multiplu (Multi-Council Consensus) — motorul autonom
  council_primary_source?: string | null;
  council_secondary_source?: string | null;
  council_tertiary_source?: string | null;
  consensus_threshold?: number;
  // Config per piata
  market_overrides?: Record<string, MarketOverride>;
  min_rr?: number;
  [k: string]: unknown;
}

export interface AiOutcomeRow {
  ts: string;
  symbol: string;
  status: string;
  exit_price: number | null;
  result_r: number | null;
  pnl_usd: number | null;
  decision_id: number;
}

// ── Ordine active MT5 (sursa de adevar: MT5) ─────────────────────────────────

export interface Mt5Position {
  ticket: number;
  symbol: string;
  type: "LONG" | "SHORT";
  volume: number;
  entry: number;
  current: number;
  sl: number | null;
  tp: number | null;
  profit: number;
  swap: number;
  source: "bot" | "ai" | "daily" | "noisy" | "manual";
  comment: string;
  margin: number;
  // Filtru AI Pre-Trade — null cand ordinul nu a trecut prin filtru
  ai_approved?: boolean | null;
  ai_confidence?: number | null;
}

export interface Mt5PendingOrder {
  ticket: number;
  symbol: string;
  type: string;
  volume: number;
  entry: number;
  sl: number | null;
  tp: number | null;
  source: "bot" | "ai" | "daily" | "noisy" | "manual";
  comment: string;
  ai_approved?: boolean | null;
  ai_confidence?: number | null;
}

export interface Mt5OrdersAccount {
  equity: number;
  balance: number;
  margin_used: number;
  margin_free: number;
  margin_level: number | null;
  currency: string;
  floating_pnl: number;
}

export interface Mt5OrdersResponse {
  connected: boolean;
  error: string | null;
  positions: Mt5Position[];
  pending: Mt5PendingOrder[];
  account: Mt5OrdersAccount | null;
}

// ── Surse AI multi-provider (consiliu) ───────────────────────────────────────

export interface AiProviderSpec {
  type: "ollama" | "anthropic" | "gemini" | "openai_compatible";
  model: string;
  enabled: boolean;
  base_url?: string | null;
  url?: string | null;
  has_key: boolean;
  needs_key: boolean;
  is_default: boolean;
}

export interface AiProviderHealth {
  status: "healthy" | "paused" | "disabled_auth";
  reason: string;
  retry_in_s: number;
  fails: number;
}

export interface AiProvidersResponse {
  providers: Record<string, AiProviderSpec>;
  role_assignments: Record<string, string>;
  health: Record<string, AiProviderHealth>;
  default: string;
}

export interface AiProviderTestResult {
  ok: boolean;
  latency_s: number;
  detail: string;
  kind: string | null;
}

export interface AiProviderModelsResult {
  ok: boolean;
  models: string[];
  count?: number;
  detail?: string;
  kind?: string | null;
}

// ── Daily Engine (intraday ORB, mod SHADOW) ──────────────────────────────────
export type DailyPhase =
  | "waiting_open" | "stopped" | "forming_or" | "waiting_entry" | "in_position" | "closed"
  | "skipped" | "weekend" | "disabled" | "error";

export interface DailyMarketStatus {
  symbol: string;
  label?: string;
  role?: string;
  entry_mode?: "breakout" | "direction";
  or_minutes?: number;
  day?: string;
  window_ro?: string;
  window_app?: string;          // fereastra in fusul aplicatiei (RO / DE) — doar afisare
  app_tz?: string;
  app_tz_label?: "RO" | "DE";
  window_local?: string;
  phase: DailyPhase;
  reason?: string;
  exec_armed?: boolean;
  exec_placed?: string | null;
  note?: string;
  or_hi?: number;
  or_lo?: number;
  side?: 1 | -1;
  entry?: number;          // pretul de intrare (virtual), cand exista pozitie
  entry_min?: number;
  sl?: number;
  last?: number;
  open_R?: number;
  R?: number;
  exit?: number;
  exit_min?: number;
  tp?: number | null;
  k?: number;                 // indexul trade-ului din zi (0 = primul; >= 1 = re-intrare)
  trades_today?: number;
  R_today?: number;
  reentry_stop?: string;
  reentry_wait?: boolean;
  rr?: number | null;
  reentry?: DailyReentry;
}
export interface DailyReentry {
  enabled: boolean; window_min: number; max_trades: number; max_consec_losses: number; cooldown_bars: number;
}
export interface DailyMarketConfig {
  symbol: string; label?: string; tz: string; open: string; last_bar: string; or_minutes: number;
  entry: "breakout" | "direction"; rr: number | null; reentry: DailyReentry; enabled: boolean;
  preset?: string; costs_mode?: "auto" | "manual"; slip: number; comm: number; backtest?: DailyQuickBacktest | null;
}
export interface DailyPreset { label: string; tz: string; open: string; last_bar: string; or_minutes: number; entry: "breakout" | "direction" }
export interface DailyQuickBacktest {
  ok: boolean; detail?: string; trades?: number; per_week?: number; expectancy_R?: number; win_rate?: number;
  total_R?: number; max_dd_R?: number; period?: string; verdict?: string | null; train_R?: number; test_R?: number;
}
export interface DailyMarketPreview {
  market: DailyMarketConfig; description?: string; volume_min: number; margin_min_lot: number | null;
  costs_mode: "auto" | "manual";
  costs: { slip: number; comm: number; spread_live: number; spread_hist: number | null; spread_live_points: number;
           markup_points: number; point: number; digits: number };
  backtest: DailyQuickBacktest;
}

export interface DailyScore {
  trades: number;
  wins: number;
  losses: number;
  total_R: number;
  expectancy_R: number | null;
  win_rate: number | null;
  pnl_money_est?: number | null;
  blocked_trades?: number;                 // trade-uri pe care limita globala de risc le-ar fi BLOCAT in executie
  blocked_pnl_money_est?: number | null;   // ce ar fi insemnat ele la lotul minim (doar afisare)
}

export interface DailyStatus {
  running: boolean;
  pid: number | null;
  mode: string;
  heartbeat?: string;
  server_offset_h?: number | null;
  account?: { login?: number; server?: string; is_demo?: boolean };
  markets?: DailyMarketStatus[];
  scorecard?: DailyScore & { by_symbol: Record<string, DailyScore> };
  errors?: string[];
  backtest_ref?: Record<string, { trades: number; expectancy_R: number; period: string; verdict: string }>;
  sizing?: { capital_sync_mt5: boolean; capital_usd: number | null; fraction: number; risk_pct: number };
  execution?: { active: boolean; reason: string };
}

export interface DailyTrade {
  day: string;
  symbol: string;
  side: "LONG" | "SHORT";
  entry: number;
  sl: number;
  exit: number;
  R: number;
  reason: "SL" | "TP" | "EOD";
  lots?: number;            // lotul ipotetic (aceeasi dimensionare ca Custom / AI)
  risk_money?: number;
  pnl_money_est?: number;   // R × risc in bani — ESTIMARE, trade-ul e virtual
  // limita globala de risc l-ar fi BLOCAT in executie (lot 0): ce ar fi insemnat la lotul minim — doar afisare
  blocked?: boolean;
  blocked_reason?: string;
  blocked_lots?: number;
  blocked_risk_money?: number;
  blocked_pnl_money_est?: number;
  currency?: string;
  or_hi: number;
  or_lo: number;
  mode: string;
  recorded_at: string;
}

// ── Engine Lifecycle comun (/engines) ────────────────────────────────────────
export type EngineId = "custom" | "ai" | "daily";
/** Engine-urile din lifecycle (/engines) — include Noisy (shadow, fara tranzactii reale / performanta MT5). */
export type LifecycleEngineId = EngineId | "noisy" | "special";

export interface EngineState {
  id: LifecycleEngineId;
  label: string;
  running: boolean;
  pid: number | null;
  detail: string;
  mode: string | null;
  autostart: boolean | null;
  error: string | null;
}

// ── Performanta pe engine (/mt5/engine-performance) ──────────────────────────
export interface EnginePerf {
  trades: number;
  wins: number;
  losses: number;
  win_rate: number | null;   // % = wins / (wins + losses)
  profit: number;            // suma castigurilor (brut, din deal-urile de iesire)
  loss: number;              // suma pierderilor (negativ)
  pnl: number;               // profit + loss
  costs: number;             // comision + swap (negativ)
  net: number;               // pnl + costs
  avg_r: number | null;
  symbols: { symbol: string; pnl: number }[];
  first: string | null;
  last: string | null;
}

export interface EnginePerformanceResponse {
  connected: boolean;
  error: string | null;
  days?: number;
  currency?: string | null;
  is_demo?: boolean | null;
  total?: EnginePerf;
  custom?: EnginePerf;
  ai?: EnginePerf;
  special?: EnginePerf;
  daily?: EnginePerf;
  noisy?: EnginePerf;
  manual?: EnginePerf;
  account?: EnginePerf;
}

// ── Ritm de tranzactionare pe engine (/dashboard/trading-pace) ───────────────
export type PaceConfidence = "insufficient" | "low" | "medium" | "high";

export interface EnginePace {
  per_week: number | null;
  low: number | null;
  high: number | null;
  confidence: PaceConfidence;
  weeks: number;
  trades_in_window: number;
  current_week: number;
  weekly?: number[];
  regime_since?: string | null;
  regime_reason?: string | null;
  reference?: number | null;
  reference_kind?: string | null;
  virtual?: boolean;
  previous?: { per_week: number; low: number; high: number; weeks: number; trades_in_window: number; confidence: PaceConfidence };
}

export interface TradingPaceResponse {
  computed_at: string;
  connected: boolean;
  half_life_weeks: number;
  custom: EnginePace;
  ai: EnginePace;
  daily: EnginePace;
}

// ── Dimensionarea pozitiei (/sizing/preview) — aceeasi logica pe toate engine-urile ──
export interface SizingPreview {
  connected: boolean;
  error: string | null;
  symbol?: string;
  synced_at?: string;
  account?: { balance: number; equity: number; margin: number; free_margin: number; currency: string;
              leverage: number; is_demo: boolean; login: number; server: string;
              margin_call_pct: number; stop_out_pct: number } | null;
  spec?: { volume_min: number; volume_max: number; volume_step: number; tick_size: number; tick_value: number;
           contract_size: number; digits: number; stops_level_points: number; currency_profit: string;
           value_per_price_unit: number | null; price: number; margin_per_lot: number | null };
  inputs?: { fraction: number; risk_pct: number; fixed_lots: number | null };
  sl?: { distance: number | null; source: string };
  result?: { capital_base: number; fraction: number; capital: number; mode: "risk" | "fixed";
             lots?: number; raw_lots?: number | null; risk_money?: number | null; target_money?: number | null;
             at_min_lot?: boolean; capped_max?: boolean; ratio?: number | null; reason?: string | null;
             margin_need?: number; margin_pct_free?: number; risk_pct_equity?: number; equity_for_target?: number;
             risk_cap_pct?: number | null; risk_cap_note?: string };
}

// ── Noisy Engine (/noisy/*) ──────────────────────────────────────────────────
export interface NoisyLimit { enabled: boolean; value: number }
export interface NoisyConfig {
  mode: string;
  symbol: string;
  timeframe: "M1" | "M5";
  notify_trades: boolean;
  on_stop: "close" | "keep";
  poll_seconds: number;
  notify_telegram: boolean;
  /** intervale orare (ora RO), sursa de adevar; start/end = primul interval (compatibilitate) */
  window: { intervals: { start: string; end: string }[]; start: string; end: string; days: number[] };
  strategy: Record<string, number | boolean>;
  news: { enabled: boolean; pre_min: number; post_min: number };
  /** spread in POINTS MT5: tipic (cost) auto/manual + maxim acceptat auto (× tipic) / manual */
  spread: { mode: "auto" | "manual"; manual_points: number | null; max_mode: "auto" | "manual";
            max_mult: number; max_points: number; legacy_floor_price?: number };
  limits: { max_trades_day: NoisyLimit; max_losses_day: NoisyLimit; max_consec_losses: NoisyLimit };
  tf_profiles: Record<"M1" | "M5", { limits: { max_trades_day: NoisyLimit; max_losses_day: NoisyLimit; max_consec_losses: NoisyLimit };
                                     min_atr_over_cost: number; cost_filter_enabled: boolean }>;
  break_even: { enabled: boolean; trigger_pct: number; lock1_pct: number; phase2_enabled: boolean;
                phase2_zone_pct: number; lock2_pct: number };
  budget: { capital: number; min_remaining: number };
  sizing: { risk_pct: number };
  /** trade-uri suprapuse — OPTIONAL, oprit implicit */
  overlap: { enabled: boolean; max_open: number; min_interval_min: number; same_direction: boolean; opposite_direction: boolean };
}
export interface NoisyTrade {
  id: string; symbol: string; day: string; dir: "LONG" | "SHORT";
  signal_t: string; entry_t: string; exit_t: string;
  entry: number; exit: number; sl: number; tp: number; risk: number; cost: number;
  reason: string; gross_R: number; R: number; bars: number; lots: number; pnl_money: number | null;
  tf?: string; hold_min?: number;
}
export interface NoisyScore {
  trades: number; wins: number; losses: number; win_rate: number | null; total_R: number;
  expectancy_R: number | null; gross_R: number | null; cost_R: number | null; profit_factor: number | null;
  max_dd_R: number; max_loss_streak: number; pnl_money: number | null; avg_hold_min: number | null;
}
export interface NoisyStatus {
  running: boolean;
  pid: number | null;
  state?: string;
  state_label?: string;
  reason?: string;
  mode: string;
  symbol?: string;
  timeframe?: string;
  tf_min?: number;
  paused?: boolean;
  heartbeat?: string;
  open?: { id: string; dir: string; entry: number; sl: number; tp: number; float_R: number; bars_held: number; entry_t: string } | null;
  opens?: { id: string; dir: string; entry: number; sl: number; tp: number; float_R: number; bars_held: number; entry_t: string }[];
  pending?: { dir: string; signal_t: string } | null;
  last?: { t: string; close: number; ema: number; atr: number | null; dev_atr: number | null; spread: number; er: number | null } | null;
  counters?: { trades: number; losses: number; consec_losses: number; flips_hour: number };
  today?: { trades: number; R: number; pnl_money: number };
  budget?: { capital: number; min_remaining: number; realized: number; floating: number; remaining: number; locked: unknown };
  budget_lock?: { at: string; remaining: number } | null;
  scorecard?: NoisyScore;
  backtest_ref?: Record<string, number | string>;
  news_next?: [string, string][];
  errors?: string[];
  config?: NoisyConfig;
  execution?: { active: boolean; reason: string };
  real_positions?: { ticket: number; type: string; volume: number; price: number; sl: number; tp: number; profit: number }[];
  spread?: NoisySpreadInfo;
  rejects_today?: Record<string, number>;
  rejected_recent?: { t: string; dir: string; reason: string; detail: string }[];
}
export interface NoisyMarketInfo {
  ok: boolean; symbol: string; detail?: string; description?: string;
  point?: number; digits?: number; pip_points?: number;
  spread_live_points?: number | null; spread_live_price?: number | null; spread_live_pips?: number | null;
  contract_size?: number | null; volume_min?: number; volume_step?: number; margin_min_lot?: number | null;
  tradable?: boolean; currency_profit?: string;
}
export interface NoisySpreadInfo {
  mode: "auto" | "manual"; max_mode?: "auto" | "manual"; source: string; max_source?: string;
  point?: number; digits?: number; pip_points?: number;
  typical_points?: number; typical_price?: number; typical_pips?: number;
  max_points?: number; max_price?: number; max_pips?: number;
  live_points?: number | null; auto_note?: string;
}

// ── Dashboard global: piete active pe toate engine-urile (/dashboard/markets) ──
export type MarketEngineId = LifecycleEngineId;   // custom | ai | daily | noisy
export type MarketState = "in_position" | "active" | "observe" | "idle" | "blocked" | "stopped";
export interface MarketStats {
  trades: number; wins: number; losses: number; win_rate: number | null;
  pnl: number; net: number; costs: number;
  pnl_today: number; pnl_yesterday: number; trades_today: number;
}
export interface MarketEngine {
  symbol: string; engine: MarketEngineId; ref: string; session_key?: string;
  direction: string | null; tf: string | null;
  mode: "live" | "obs" | "shadow" | "execute";
  status: MarketState; status_label: string; reason: string;
  positions: number; signals_today: number;
  virtual_today?: { trades: number; R: number };
  window?: string | null; phase?: string;
  /** engine pornit + piata activa + nepusa manual pe pauza (sau cu pozitii deschise) */
  in_use: boolean; manual_pause?: boolean;
}
export interface MarketCardData {
  symbol: string; engines: MarketEngine[]; engine_ids: MarketEngineId[];
  status: MarketState; status_label: string;
  positions: number; pending: number; signals_today: number; direction: string | null;
  stats: MarketStats | null;
  stats_by_engine: Partial<Record<MarketEngineId, MarketStats>> | null;
  stats_other: MarketStats | null;
  /** cel putin un engine foloseste piata acum, sau exista pozitii / ordine pe ea */
  in_use: boolean;
}
export interface DashboardMarkets {
  computed_at: string;
  markets: MarketCardData[];
  history_only: { symbol: string; sources: Record<string, number>; stats: MarketStats }[];
  counts: Record<MarketState, number> & { unused?: number };
  global_block: string | null;
  engines: Record<MarketEngineId, boolean>;
  mt5_connected: boolean;
  errors: Record<string, string>;
}
export interface GlobalSignal {
  time: string; engine: MarketEngineId; symbol: string; direction: string; strategy: string;
  status: "pending" | "executed" | "rejected" | "expired" | "observe" | "virtual" | "other";
  status_label: string; id: string; ref: string; detail: string;
}

// ── Backtest legat de configuratia exacta (api/backtest_refresh.py) — Daily + Noisy ─────────────────────────
export type BacktestAutoStatus = "pending" | "running" | "completed" | "failed" | "outdated" | "interrupted";
export interface BacktestAuto<R = Record<string, unknown>> {
  status: BacktestAutoStatus;
  fingerprint?: string;
  requested_at?: string; started_at?: string; finished_at?: string;
  error?: string | null;
  note?: string;
  stale_result_summary?: string | null;
  result?: R | null;
}
export interface DailyBacktestResult {
  ok: boolean; trades?: number; days?: number; per_week?: number; expectancy_R?: number; win_rate?: number;
  total_R?: number; max_dd_R?: number; period?: string; verdict?: string | null; train_R?: number; test_R?: number;
  summary?: string; detail?: string;
}
export interface DailyBacktestAuto extends BacktestAuto<DailyBacktestResult> { slot: number; symbol?: string }
// declaration merging: campuri noi pe interfetele existente (pauza per piata + backtest automat)
export interface DailyMarketStatus { paused?: boolean }
export interface DailyStatus { backtest_auto?: DailyBacktestAuto[] }
export interface NoisyStatus { backtest_auto?: BacktestAuto<Record<string, unknown>> }
export interface DailyMarketConfig { paused?: boolean; paused_at?: string | null }

// ── Daily: mod per piata (Live / Shadow / Pauza) + Profit Lock (2026-11-12) ──
export type DailyMarketMode = "live" | "shadow" | "pause";
export interface DailyProfitLock { enabled: boolean; trigger_R: number; lock_R: number }
export interface DailyMarketConfig { exec_mode?: "live" | "shadow"; mode?: DailyMarketMode; profit_lock?: DailyProfitLock }
export interface DailyMarketStatus {
  mode?: DailyMarketMode; exec_mode?: "live" | "shadow"; execution?: { active: boolean; reason: string };
  profit_lock?: DailyProfitLock; locked?: boolean; sl_now?: number;
}

// ── Daily: mai multe sesiuni pe piață + limita de trade-uri / zi + alerta de profit (2026-11-13) ──
export type DailySessionId = "london" | "frankfurt" | "new_york" | "custom";
export interface DailySessionRow {
  session: DailySessionId; session_label?: string; phase: string; reason?: string; window_app?: string; window_ro?: string;
  window_local?: string; app_tz_label?: string; or_minutes?: number; entry_mode?: string; side?: number; entry?: number;
  sl?: number; open_R?: number; R?: number; trades_today?: number; R_today?: number; blocked?: string | null;
  blocked_reason?: string; no_new_entries?: string;
}
export interface DailyMarketConfig { sessions?: DailySessionId[]; max_trades_per_day?: number }
export interface DailyMarketStatus { session?: DailySessionId; sessions?: DailySessionRow[]; max_trades_per_day?: number }
