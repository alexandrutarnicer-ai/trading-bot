import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./client";
import type {
  BotStatus, SessionStatus, Signal, Outcome, EquityCurvePoint,
  Profile, ProfileSummary, Meta,
  DataCheckResult, DownloadJob, TelegramConfig, Mt5Status, Mt5TradeStats, Mt5EquityCurveResponse,
  Mt5WeeklyStats, Mt5TopMarketsResponse, Mt5MarketStatsResponse, Mt5TransactionsResponse,
  Mt5CostsResponse, Mt5CostsDailyResponse, Mt5SessionsResponse,
  BacktestHistoryEntry, BacktestJob, WeeklyStats,
  NotificationsResponse, TransactionsResponse, MarketStatsResponse,
  UptimeResponse, SessionChangesResponse, TopMarketEntry, TimezoneConfig,
  SystemLogsResponse, SyncResult, CostsResponse, CostsDailyResponse,
} from "./types";


const POLL = 15_000; // refresh la 15s

export const useBotStatus = () =>
  useQuery<BotStatus>({
    queryKey: ["bot-status"],
    queryFn:  () => apiFetch("/bot/status"),
    refetchInterval: POLL,
    refetchIntervalInBackground: true,
  });

export const useSessions = () =>
  useQuery<SessionStatus[]>({
    queryKey: ["sessions"],
    queryFn:  () => apiFetch("/sessions"),
    refetchInterval: POLL,
    refetchIntervalInBackground: true,
  });

export const useWeeklyStats = () =>
  useQuery<WeeklyStats>({
    queryKey: ["weekly-stats"],
    queryFn:  () => apiFetch("/sessions/weekly_stats"),
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
  });

export const useMt5WeeklyStats = () =>
  useQuery<Mt5WeeklyStats>({
    queryKey: ["mt5-weekly-stats"],
    queryFn:  () => apiFetch("/mt5/weekly-stats"),
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
  });

export interface FrequencyEstimate {
  per_week:    number | null;
  per_month:   number | null;
  avg_max_dd:  number | null;
  missing:     Array<{ id: string; markets: string[] }>;
}

export const useFrequencyEstimate = (profileId?: string) =>
  useQuery<FrequencyEstimate>({
    queryKey: ["frequency-estimate", profileId ?? ""],
    queryFn:  () => apiFetch(`/sessions/frequency-estimate${profileId ? `?profile_id=${profileId}` : ""}`),
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
  });

export const useSignals = (sessionId: string) =>
  useQuery<Signal[]>({
    queryKey: ["signals", sessionId],
    queryFn:  () =>
      sessionId === "all"
        ? apiFetch("/sessions/all/signals?limit=50")
        : apiFetch(`/sessions/${sessionId}/signals?limit=30`),
    refetchInterval: POLL,
  });

export const useOutcomes = (sessionId: string) =>
  useQuery<Outcome[]>({
    queryKey: ["outcomes", sessionId],
    queryFn:  () =>
      sessionId === "all"
        ? apiFetch("/sessions/all/outcomes?limit=200")
        : apiFetch(`/sessions/${sessionId}/outcomes`),
    refetchInterval: POLL,
    enabled:  !!sessionId,
  });

export const useEquityCurve = () =>
  useQuery<EquityCurvePoint[]>({
    queryKey: ["equity-curve"],
    queryFn:  () => apiFetch("/sessions/all/equity-curve"),
    refetchInterval: POLL,
  });

export const useProfileList = () =>
  useQuery<ProfileSummary[]>({
    queryKey: ["profiles"],
    queryFn:  () => apiFetch("/profiles"),
  });

export const useProfile = (id: string) =>
  useQuery<Profile>({
    queryKey: ["profile", id],
    queryFn:  () => apiFetch(`/profiles/${id}`),
    enabled:  !!id,
    staleTime: Infinity,         // nu re-fetch automat — profilul e un editor, nu date live
    refetchOnWindowFocus: false, // alt-tab nu suprascrie editarile nesalvate
  });

export const useMeta = () =>
  useQuery<Meta>({
    queryKey: ["meta"],
    queryFn:  () => apiFetch("/profiles/meta"),
    staleTime: Infinity,
  });

export const useSaveProfile = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<Profile> }) =>
      apiFetch(`/profiles/${id}`, { method: "PUT", body: data }),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["profile", vars.id] });
      qc.invalidateQueries({ queryKey: ["profiles"] });
    },
  });
};

export const useCreateProfile = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { id: string; name: string; description?: string }) =>
      apiFetch("/profiles", { method: "POST", body: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["profiles"] }),
  });
};

export const useDeleteProfile = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiFetch(`/profiles/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["profiles"] }),
  });
};

export const useRunBacktest = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: {
      session: object;
      date_from?: string;
      date_to?: string;
      start_balance?: number;
      session_snapshot?: Record<string, unknown>;
    }) => apiFetch("/backtest/run", { method: "POST", body: payload }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["backtest-jobs"] }),
  });
};

export const useBacktestJob = (jobId: string | null) =>
  useQuery<{ status: string; results: object | null; error: string | null }>({
    queryKey: ["backtest-job", jobId],
    queryFn:  () => apiFetch(`/backtest/${jobId}`),
    enabled:  !!jobId,
    refetchInterval: (query) =>
      query.state.data?.status === "running" || query.state.data?.status === "pending"
        ? 2000
        : false,
  });

export const useMt5Markets = () =>
  useQuery<{ symbols: string[]; error: string | null }>({
    queryKey: ["mt5-markets"],
    queryFn:  () => apiFetch("/markets/mt5"),
    staleTime: 5 * 60 * 1000,
    retry: false,
  });

export const useMarketAtr = (symbols: string[], tf: string, enabled: boolean) =>
  useQuery<{
    error: string | null;
    data: Record<string, { atr: number; atr_pips: number | null; pip_size: number; digits: number } | null>;
  }>({
    queryKey: ["market-atr", symbols.join(","), tf],
    queryFn:  () => apiFetch(`/markets/atr?symbols=${symbols.join(",")}&tf=${tf}`),
    enabled:  enabled && symbols.length > 0,
    staleTime: 2 * 60 * 1000,
    retry: false,
  });

export const useCheckData = () =>
  useMutation({
    mutationFn: (params: { markets: string; entry_tf: string; trend_tf: string }) =>
      apiFetch<DataCheckResult>(
        `/data/check?markets=${params.markets}&entry_tf=${params.entry_tf}&trend_tf=${params.trend_tf}`
      ),
  });

export const useStartDownload = () =>
  useMutation({
    mutationFn: (body: { markets: string[]; timeframes: string[]; label?: string }) =>
      apiFetch<{ job_id: string }>("/data/download", { method: "POST", body }),
  });

export const useDownloadJob = (jobId: string | null) =>
  useQuery<DownloadJob>({
    queryKey: ["download-job", jobId],
    queryFn:  () => apiFetch(`/data/download/${jobId}`),
    enabled:  !!jobId,
    refetchInterval: (query) =>
      query.state.data?.status === "pending" || query.state.data?.status === "running"
        ? 2000
        : false,
  });

// ── Session pause/resume ─────────────────────────────────────────────────────

export const usePauseSession = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (sessionId: string) =>
      apiFetch(`/sessions/${sessionId}/pause`, { method: "POST" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["sessions"] });
      qc.invalidateQueries({ queryKey: ["bot-status"] });
    },
  });
};

export const useResumeSession = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (sessionId: string) =>
      apiFetch(`/sessions/${sessionId}/resume`, { method: "POST" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["sessions"] });
      qc.invalidateQueries({ queryKey: ["bot-status"] });
    },
  });
};

// ── Autostart Windows ────────────────────────────────────────────────────────

export const useAutostartStatus = () =>
  useQuery<{ enabled: boolean }>({
    queryKey: ["autostart-status"],
    queryFn:  () => apiFetch("/bot/autostart/status"),
    refetchInterval: 30_000,
  });

export const useAutostartEnable = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch("/bot/autostart/enable", { method: "POST" }),
    onSuccess: () => { setTimeout(() => qc.invalidateQueries({ queryKey: ["autostart-status"] }), 4000); },
  });
};

export const useAutostartDisable = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch("/bot/autostart/disable", { method: "POST" }),
    onSuccess: () => { setTimeout(() => qc.invalidateQueries({ queryKey: ["autostart-status"] }), 4000); },
  });
};

// ── Bot start/stop ──────────────────────────────────────────────────────────

export const useStartBot = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body?: { profile_id?: string; profile_name?: string }) =>
      apiFetch("/bot/start", { method: "POST", body: body ?? {} }),
    onSuccess: () => { setTimeout(() => qc.invalidateQueries({ queryKey: ["bot-status"] }), 1500); },
  });
};

export const useMt5Status = () =>
  useQuery<Mt5Status>({
    queryKey: ["mt5-status"],
    queryFn:  () => apiFetch("/mt5/status"),
    refetchInterval: POLL,
    retry: false,
  });

export const useMt5Stats = () =>
  useQuery<Mt5TradeStats>({
    queryKey: ["mt5-stats"],
    queryFn:  () => apiFetch("/mt5/stats"),
    refetchInterval: POLL,
    retry: false,
  });

export const useMt5EquityCurve = (metric: "usd" | "r" = "usd") =>
  useQuery<Mt5EquityCurveResponse>({
    queryKey: ["mt5-equity-curve", metric],
    queryFn:  () => apiFetch(`/mt5/equity-curve?metric=${metric}`),
    refetchInterval: POLL,
    retry: false,
  });

export const useStopBot = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch("/bot/stop", { method: "POST" }),
    onSuccess: () => { setTimeout(() => qc.invalidateQueries({ queryKey: ["bot-status"] }), 400); },
  });
};

// ── Telegram settings ───────────────────────────────────────────────────────

export const useTelegramConfig = () =>
  useQuery<TelegramConfig>({
    queryKey: ["telegram-config"],
    queryFn:  () => apiFetch("/settings/telegram"),
  });

export const useSaveTelegram = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { token: string; chat_id: string }) =>
      apiFetch("/settings/telegram", { method: "PUT", body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["telegram-config"] }),
  });
};

export const useClearTelegram = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch("/settings/telegram", { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["telegram-config"] }),
  });
};

export const useTestTelegram = () =>
  useMutation({
    mutationFn: () => apiFetch("/settings/telegram/test", { method: "POST" }),
  });

// ── Backtest jobs (Audit) ────────────────────────────────────────────────────

export const useBacktestJobs = () =>
  useQuery<BacktestJob[]>({
    queryKey: ["backtest-jobs"],
    queryFn:  () => apiFetch("/backtest/jobs"),
    refetchInterval: (query) => {
      const jobs = query.state.data;
      const hasActive = jobs?.some(j => j.status === "pending" || j.status === "running");
      return hasActive ? 3_000 : 15_000;
    },
  });

export const useDeleteBacktestJob = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (jobId: string) => apiFetch(`/backtest/jobs/${jobId}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["backtest-jobs"] }),
  });
};

// ── Download jobs (Audit) ────────────────────────────────────────────────────

export const useDownloadJobs = () =>
  useQuery<DownloadJob[]>({
    queryKey: ["download-jobs"],
    queryFn:  () => apiFetch("/data/jobs"),
    refetchInterval: (query) => {
      const jobs = query.state.data;
      const hasActive = jobs?.some(j => j.status === "pending" || j.status === "running");
      return hasActive ? 2_000 : 15_000;
    },
  });

export const useDeleteDownloadJob = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (jobId: string) => apiFetch(`/data/jobs/${jobId}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["download-jobs"] }),
  });
};

// ── Notifications ────────────────────────────────────────────────────────────

export const useNotifications = (limit = 100) =>
  useQuery<NotificationsResponse>({
    queryKey: ["notifications", limit],
    queryFn:  () => apiFetch(`/notifications?limit=${limit}`),
    refetchInterval: 20_000,
    refetchIntervalInBackground: false,
  });

export const useMarkNotificationsRead = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch("/notifications/mark-read", { method: "POST" }),
    onSuccess:  () => qc.invalidateQueries({ queryKey: ["notifications"] }),
  });
};

export const useDeleteNotification = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (nid: string) => apiFetch(`/notifications/${nid}`, { method: "DELETE" }),
    onSuccess:  () => qc.invalidateQueries({ queryKey: ["notifications"] }),
  });
};

export const useClearNotifications = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch("/notifications", { method: "DELETE" }),
    onSuccess:  () => qc.invalidateQueries({ queryKey: ["notifications"] }),
  });
};

// ── Reports ──────────────────────────────────────────────────────────────────

export const useTransactions = (params: {
  status?: string;
  symbol?: string;
  direction?: string;
  date_from?: string;
  date_to?: string;
  session_id?: string;
  obs_only?: boolean;
  limit?: number;
  offset?: number;
}) =>
  useQuery<TransactionsResponse>({
    queryKey: ["transactions", params],
    queryFn:  () => {
      const qs = new URLSearchParams();
      if (params.status)     qs.set("status",     params.status);
      if (params.symbol)     qs.set("symbol",     params.symbol);
      if (params.direction)  qs.set("direction",  params.direction);
      if (params.date_from)  qs.set("date_from",  params.date_from);
      if (params.date_to)    qs.set("date_to",    params.date_to);
      if (params.session_id) qs.set("session_id", params.session_id);
      if (params.obs_only)   qs.set("obs_only",   "true");
      qs.set("limit",  String(params.limit  ?? 200));
      qs.set("offset", String(params.offset ?? 0));
      return apiFetch(`/reports/transactions?${qs.toString()}`);
    },
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
  });

export const useMarketStats = () =>
  useQuery<MarketStatsResponse>({
    queryKey: ["market-stats"],
    queryFn:  () => apiFetch("/reports/market-stats"),
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
  });

export const useTopMarkets = (period: string) =>
  useQuery<TopMarketEntry[]>({
    queryKey: ["top-markets", period],
    queryFn:  () => apiFetch(`/sessions/top-markets?period=${period}&limit=5`),
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
  });

export const useMt5TopMarkets = (period: string, limit = 5) =>
  useQuery<Mt5TopMarketsResponse>({
    queryKey: ["mt5-top-markets", period, limit],
    queryFn:  () => apiFetch(`/mt5/top-markets?period=${period}&limit=${limit}`),
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
  });

export const useMt5MarketStats = () =>
  useQuery<Mt5MarketStatsResponse>({
    queryKey: ["mt5-market-stats"],
    queryFn:  () => apiFetch("/mt5/top-markets?period=all&limit=100"),
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
  });

export const useMt5SessionStats = () =>
  useQuery<Mt5SessionsResponse>({
    queryKey: ["mt5-session-stats"],
    queryFn:  () => apiFetch("/mt5/sessions"),
    refetchInterval: POLL,
    refetchIntervalInBackground: false,
  });

export const useMt5Transactions = (params: {
  status?: string;
  direction?: string;
  symbol?: string;
  limit?: number;
  offset?: number;
}) =>
  useQuery<Mt5TransactionsResponse>({
    queryKey: ["mt5-transactions", params],
    queryFn:  () => {
      const qs = new URLSearchParams();
      if (params.status)    qs.set("status",    params.status);
      if (params.direction) qs.set("direction", params.direction);
      if (params.symbol)    qs.set("symbol",    params.symbol);
      qs.set("limit",  String(params.limit  ?? 200));
      qs.set("offset", String(params.offset ?? 0));
      return apiFetch(`/mt5/transactions?${qs.toString()}`);
    },
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
  });

export const useMt5Costs = () =>
  useQuery<Mt5CostsResponse>({
    queryKey: ["mt5-costs"],
    queryFn:  () => apiFetch("/mt5/costs"),
    refetchInterval: 120_000,
    refetchIntervalInBackground: false,
  });

export const useMt5CostsDaily = () =>
  useQuery<Mt5CostsDailyResponse>({
    queryKey: ["mt5-costs-daily"],
    queryFn:  () => apiFetch("/mt5/costs-daily"),
    refetchInterval: 120_000,
    refetchIntervalInBackground: false,
  });

// ── Timezone ─────────────────────────────────────────────────────────────────

export const useTimezone = () =>
  useQuery<TimezoneConfig>({
    queryKey: ["timezone"],
    queryFn:  () => apiFetch("/settings/timezone"),
    staleTime: 60_000,
  });

export const useSetTimezone = () => {
  const qc = useQueryClient();
  return useMutation<TimezoneConfig, Error, string>({
    mutationFn: (tz: string) =>
      apiFetch("/settings/timezone", { method: "PUT", body: { timezone: tz } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["timezone"] }),
  });
};

export const useBotUptime = () =>
  useQuery<UptimeResponse>({
    queryKey: ["bot-uptime"],
    queryFn:  () => apiFetch("/reports/uptime"),
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
  });

export const useSessionChanges = () =>
  useQuery<SessionChangesResponse>({
    queryKey: ["session-changes"],
    queryFn:  () => apiFetch("/reports/session-changes"),
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
  });

export const useSystemLogs = (params: {
  session?: string;
  level?: string;
  lines_per_session?: number;
}) =>
  useQuery<SystemLogsResponse>({
    queryKey: ["system-logs", params],
    queryFn:  () => {
      const q = new URLSearchParams();
      if (params.session)           q.set("session",           params.session);
      if (params.level)             q.set("level",             params.level);
      if (params.lines_per_session) q.set("lines_per_session", String(params.lines_per_session));
      return apiFetch(`/reports/system-logs?${q}`);
    },
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
  });

export const useLogSessions = () =>
  useQuery<{ sessions: string[] }>({
    queryKey: ["log-sessions"],
    queryFn:  () => apiFetch("/reports/system-logs/sessions"),
    refetchInterval: 120_000,
    staleTime: 60_000,
    refetchIntervalInBackground: false,
  });

export const useCosts = () =>
  useQuery<CostsResponse>({
    queryKey: ["costs"],
    queryFn:  () => apiFetch("/reports/costs"),
    refetchInterval: 120_000,
    refetchIntervalInBackground: false,
  });

export const useCostsDaily = () =>
  useQuery<CostsDailyResponse>({
    queryKey: ["costs-daily"],
    queryFn:  () => apiFetch("/reports/costs-daily"),
    refetchInterval: 120_000,
    refetchIntervalInBackground: false,
  });

// ── MT5 Sync ─────────────────────────────────────────────────────────────────

export const useSyncStatus = () =>
  useQuery<SyncResult>({
    queryKey: ["mt5-sync-status"],
    queryFn:  () => apiFetch("/mt5/sync-status"),
    refetchInterval: 30_000,
  });

export const useRunSync = () => {
  const qc = useQueryClient();
  return useMutation<SyncResult, Error, { fix: boolean }>({
    mutationFn: ({ fix }) => apiFetch(`/mt5/sync?fix=${fix}`, { method: "POST" }),
    onSuccess:  () => {
      qc.invalidateQueries({ queryKey: ["mt5-sync-status"] });
      qc.invalidateQueries({ queryKey: ["sessions"] });
      qc.invalidateQueries({ queryKey: ["outcomes"] });
    },
  });
};

// ── Backtest history (legacy) ─────────────────────────────────────────────────

export const useBacktestHistory = (sessionId?: string) =>
  useQuery<BacktestHistoryEntry[]>({
    queryKey: ["backtest-history", sessionId ?? "all"],
    queryFn:  () => apiFetch(`/backtest/history${sessionId ? `?session_id=${sessionId}` : ""}`),
    staleTime: 10_000,
  });

export const useSaveBacktestHistory = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: object) =>
      apiFetch("/backtest/history", { method: "POST", body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["backtest-history"] }),
  });
};

export const useDeleteBacktestHistory = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiFetch(`/backtest/history/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["backtest-history"] }),
  });
};

// ── AI Engine ─────────────────────────────────────────────────────────────────

import type {
  AiStatus, AiDecision, AiConfig, AiOutcomeRow, AiCouncilTranscript,
  Mt5OrdersResponse,
} from "./types";

export const useAiStatus = () =>
  useQuery<AiStatus>({
    queryKey: ["ai-status"],
    queryFn:  () => apiFetch("/ai/status"),
    refetchInterval: 10_000,
  });

export const useAiDecisions = (limit = 30) =>
  useQuery<AiDecision[]>({
    queryKey: ["ai-decisions", limit],
    queryFn:  () => apiFetch(`/ai/decisions?limit=${limit}`),
    refetchInterval: 30_000,
    refetchIntervalInBackground: false,
    retry: false,   // 404 = ledger inca nu exista, nu insista
  });

export const useAiOutcomes = (limit = 50) =>
  useQuery<AiOutcomeRow[]>({
    queryKey: ["ai-outcomes", limit],
    queryFn:  () => apiFetch(`/ai/outcomes?limit=${limit}`),
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
    retry: false,
  });

export const useAiCouncil = (decisionId: number | null) =>
  useQuery<AiCouncilTranscript>({
    queryKey: ["ai-council", decisionId],
    queryFn:  () => apiFetch(`/ai/council/${decisionId}`),
    enabled:  decisionId != null,
    staleTime: Infinity,
  });

export const useAiConfig = () =>
  useQuery<AiConfig>({
    queryKey: ["ai-config"],
    queryFn:  () => apiFetch("/ai/config"),
    staleTime: 30_000,
  });

export const useAiLogs = (lines = 100, enabled = true) =>
  useQuery<{ lines: string[] }>({
    queryKey: ["ai-logs", lines],
    queryFn:  () => apiFetch(`/ai/logs?lines=${lines}`),
    refetchInterval: 15_000,
    refetchIntervalInBackground: false,
    enabled,
  });

export const useAiStart = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch("/ai/start", { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ai-status"] }),
  });
};

export const useAiStop = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch("/ai/stop", { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ai-status"] }),
  });
};

export const useAiSaveConfig = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Partial<AiConfig>) =>
      apiFetch("/ai/config", { method: "PUT", body }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ai-config"] });
      qc.invalidateQueries({ queryKey: ["ai-status"] });
    },
  });
};

// ── Ordine active MT5 ─────────────────────────────────────────────────────────

export const useMt5Orders = () =>
  useQuery<Mt5OrdersResponse>({
    queryKey: ["mt5-orders"],
    queryFn:  () => apiFetch("/mt5/orders"),
    refetchInterval: 15_000,
    refetchIntervalInBackground: false,
  });

// ── Surse AI multi-provider ───────────────────────────────────────────────────

import type { AiProvidersResponse, AiProviderTestResult } from "./types";

export const useAiProviders = () =>
  useQuery<AiProvidersResponse>({
    queryKey: ["ai-providers"],
    queryFn:  () => apiFetch("/ai/providers"),
    refetchInterval: 15_000,
    refetchIntervalInBackground: false,
  });

export const useAiSaveProviders = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      providers?: Record<string, Record<string, unknown>>;
      role_assignments?: Record<string, string>;
      keys?: Record<string, string>;
    }) => apiFetch("/ai/providers", { method: "PUT", body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ai-providers"] }),
  });
};

export const useAiTestProvider = () =>
  useMutation<AiProviderTestResult, Error, string>({
    mutationFn: (name: string) =>
      apiFetch("/ai/providers/test", { method: "POST", body: { name } }),
  });
