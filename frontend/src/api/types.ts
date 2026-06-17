export interface BotStatus {
  running: boolean;
  pid: number | null;
  sessions_active: number;
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
  signals_total: number;
  last_signal_time: string | null;
  outcomes_total: number;
  wins: number;
  losses: number;
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
  execute_trades: boolean;
  rsi_enabled: boolean;
  rsi_buy_min: number;
  rsi_buy_max: number;
  rsi_sell_min: number;
  rsi_sell_max: number;
  ema_alignment_enabled: boolean;
  atr_max_pips: Record<string, number>;
  circuit_breaker: number;
  r_base: number;
  r_mid: number;
  r_top: number;
  backtest_results: BacktestResult | null;
}

export interface Profile {
  id: string;
  name: string;
  description: string;
  updated_at: string | null;
  sessions: ProfileSession[];
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
  train: { trades: number; expectancy: number };
  test: { trades: number; expectancy: number };
  per_symbol: Record<string, { trades: number; win_rate: number; expectancy: number }>;
  markets: string[];
  session_id: string;
}

export interface Meta {
  available_markets: string[];
  timeframes: string[];
  trend_timeframes: string[];
  directions: string[];
  weekday_names: Record<string, string>;
}
