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
  outcomes_total: number;
  outcomes_today: number;
  outcomes_yesterday: number;
  wins: number;
  losses: number;
  wins_today: number;
  wins_yesterday: number;
  losses_today: number;
  losses_yesterday: number;
  paused: boolean;
  news_paused: boolean;
  news_events: Array<{
    title: string;
    currency: string;
    impact: string;
    event_time: string;
    minutes_to: number;
  }>;
  pnl_usd_today: number | null;
  pnl_usd_yesterday: number | null;
  pnl_usd_total: number | null;
  pnl_count: number | null;
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
}

export interface Outcome {
  signal_id: string;
  time_check: string;
  symbol: string;
  direction: number;
  status: string;
  entry: number;
  sl: number;
  tp: number;
  r_ratio: number;
  triggered_at: string | null;
  exit_price: number | null;
  exit_time: string | null;
  result_r: number;
  pnl_usd: number | null;
  commission_usd: number | null;
  swap_usd: number | null;
}

export interface EquityCurvePoint {
  date: string;
  cumulative_r: number;
  session_id: string;
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
}

export interface TelegramConfig {
  token_masked: string;
  chat_id: string;
  configured: boolean;
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

export interface PeriodStats {
  start: string;
  end: string;
  trades: number;
  wins: number;
  losses: number;
  total_r: number;
  win_rate: number;
  max_dd_r: number;
  pnl_usd: number | null;
}

export interface WeeklyStats {
  current_week: PeriodStats;
  previous_week: PeriodStats;
  current_month: PeriodStats;
  previous_month: PeriodStats;
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
  category: "order" | "signal" | "news" | "session" | "bot" | "trade" | "system";
  read: boolean;
}

export interface NotificationsResponse {
  items: NotificationItem[];
  unread: number;
}

// ── Reports ───────────────────────────────────────────────────────────────────

export interface Transaction {
  signal_id: string;
  session_id: string;
  session_label: string;
  time_check: string;
  symbol: string;
  direction: number;
  dir_str: string;
  status: string;
  entry: number;
  sl: number;
  tp: number;
  r_ratio: number;
  triggered_at: string | null;
  exit_price: number | null;
  exit_time: string | null;
  result_r: number;
  pnl_usd: number | null;
}

export interface TransactionsResponse {
  items: Transaction[];
  total: number;
}

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

export interface MarketStatsResponse {
  items: MarketStat[];
}

export interface TopMarketEntry {
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

export interface Mt5TopMarketEntry {
  symbol: string;
  trades: number;
  wins: number;
  losses: number;
  total_r: number;
  win_rate: number;
  expectancy: number;
  pnl_usd: number;
}

export interface Mt5TopMarketsResponse {
  connected: boolean;
  items: Mt5TopMarketEntry[];
  error: string | null;
}

export interface Mt5MarketStatsResponse {
  connected: boolean;
  items: MarketStat[];
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
}

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
  error: string | null;
}

export interface Mt5CostsDailyResponse {
  connected: boolean;
  items: CostsDayEntry[];
  total_commission: number;
  total_swap: number;
  total_costs: number;
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

export interface SyncDiscrepancy {
  type: string;
  sig_id: string;
  symbol: string;
  ticket?: number;
  status?: string;
  result_r?: number;
  pnl_usd?: number;
  exit_time?: string;
  detail: string;
}

export interface SyncSessionReport {
  session_id: string;
  label: string;
  discrepancies: SyncDiscrepancy[];
  fixed: number;
}

export interface SyncResult {
  ok: boolean | null;
  time: string | null;
  total_discrepancies: number | null;
  total_fixed: number;
  fix_applied: boolean;
  error?: string;
  sessions: SyncSessionReport[];
}

export interface CostStat {
  symbol: string;
  trades: number;
  trades_with_mt5: number;
  commission_usd: number;
  swap_usd: number;
  total_costs: number;
  pnl_gross: number;
  pnl_net: number | null;
  sessions: string[];
  has_cost_data: boolean;
}

export interface CostsResponse {
  items: CostStat[];
}

export interface CostsDayEntry {
  date: string;
  trades: number;
  trades_with_cost: number;
  commission_usd: number;
  swap_usd: number;
  total_costs: number;
  pnl_usd: number | null;
  total_r: number | null;
  has_cost_data: boolean;
}

export interface CostsDailyResponse {
  items: CostsDayEntry[];
  total_commission: number;
  total_swap: number;
  total_costs: number;
}

// ── AI Engine (motor autonom AI — ai_engine/) ────────────────────────────────

export interface AiScorecard {
  decisions: number;
  waits: number;
  closed_trades: number;
  total_R: number;
  expectancy_R: number;
  win_rate: number | null;
}

export interface AiStatus {
  running: boolean;
  pid: number | null;
  ts: string | null;
  mode: "demo" | "shadow" | null;
  model: string | null;
  markets: string[] | null;
  equity: number | null;
  scorecard: AiScorecard | null;
  last_errors: { ts: string; where: string; error: string }[];
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
  max_daily_loss_R: number;
  heartbeat_hours: number;
  council_cooldown_min: number;
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
  source: "bot" | "ai" | "manual";
  comment: string;
  margin: number;
}

export interface Mt5PendingOrder {
  ticket: number;
  symbol: string;
  type: string;
  volume: number;
  entry: number;
  sl: number | null;
  tp: number | null;
  source: "bot" | "ai" | "manual";
  comment: string;
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
