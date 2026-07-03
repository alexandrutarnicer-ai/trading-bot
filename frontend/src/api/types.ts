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
