export interface BotStatus {
  running: boolean;
  pid: number | null;
  sessions_active: number;
  active_profile_id: string | null;
  active_profile_name: string | null;
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
}

export interface TelegramConfig {
  token_masked: string;
  chat_id: string;
  configured: boolean;
}

export interface Profile {
  id: string;
  name: string;
  description: string;
  updated_at: string | null;
  sessions: ProfileSession[];
  start_balance: number;
}

export interface ProfileSummary {
  id: string;
  name: string;
  description: string;
  updated_at: string | null;
  sessions: number;
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
  train: { trades: number; expectancy: number };
  test: { trades: number; expectancy: number };
  per_symbol: Record<string, { trades: number; win_rate: number; expectancy: number }>;
  markets: string[];
  skipped_markets?: string[];
  session_id: string;
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
