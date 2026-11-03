import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./client";
import type {
  BotStatus, SessionStatus, Signal,
  Profile, ProfileSummary, Meta,
  DataCheckResult, DownloadJob, TelegramConfig, Mt5Status, Mt5TradeStats, Mt5EquityCurveResponse,
  Mt5WeeklyStats, Mt5TopMarketsResponse, Mt5MarketStatsResponse, Mt5TransactionsResponse,
  Mt5CostsResponse, Mt5CostsDailyResponse, Mt5SessionsResponse,
  BacktestHistoryEntry, BacktestJob,
  NotificationsResponse,
  UptimeResponse, SessionChangesResponse, TimezoneConfig,
  SystemLogsResponse,
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

export const useMt5WeeklyStats = (source: string = "all") =>
  useQuery<Mt5WeeklyStats>({
    queryKey: ["mt5-weekly-stats", source],
    queryFn:  () => apiFetch(`/mt5/weekly-stats?source=${source}`),
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
  useQuery<{
    symbols: string[];
    items?: { name: string; description: string; path: string; tradable: boolean }[];
    account?: { login: number; server: string; is_demo: boolean } | null;
    error: string | null;
  }>({
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

// Autostart-ul engine-urilor: useEngines / useEngineAction (Engine Lifecycle comun, la final).

// ── Punte Telegram (control + autostart) ─────────────────────────────────────

export interface TelegramBridgeStatus {
  running: boolean;
  pid: number | null;
  configured: boolean;
  ts: string | null;
  idle: boolean;
  allow_writes: boolean;
  last_message_ts: string | null;
  level_ai: boolean | null;
  level_claude: boolean | null;
  claude_detected: boolean | null;
  matrix_enabled: boolean;
}

export const useBridgeStatus = () =>
  useQuery<TelegramBridgeStatus>({
    queryKey: ["bridge-status"],
    queryFn:  () => apiFetch("/telegram-bridge/status"),
    refetchInterval: 15_000,
    refetchIntervalInBackground: false,
  });

export const useBridgeStart = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch("/telegram-bridge/start", { method: "POST" }),
    onSuccess: () => { setTimeout(() => qc.invalidateQueries({ queryKey: ["bridge-status"] }), 3000); },
  });
};

export const useBridgeStop = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch("/telegram-bridge/stop", { method: "POST" }),
    onSuccess: () => { setTimeout(() => qc.invalidateQueries({ queryKey: ["bridge-status"] }), 1500); },
  });
};

export const useBridgeAutostartStatus = () =>
  useQuery<{ enabled: boolean }>({
    queryKey: ["bridge-autostart-status"],
    queryFn:  () => apiFetch("/telegram-bridge/autostart/status"),
    refetchInterval: 30_000,
  });

export const useBridgeAutostartEnable = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch("/telegram-bridge/autostart/enable", { method: "POST" }),
    onSuccess: () => { setTimeout(() => qc.invalidateQueries({ queryKey: ["bridge-autostart-status"] }), 4000); },
  });
};

export const useBridgeAutostartDisable = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch("/telegram-bridge/autostart/disable", { method: "POST" }),
    onSuccess: () => { setTimeout(() => qc.invalidateQueries({ queryKey: ["bridge-autostart-status"] }), 4000); },
  });
};

// ── Al doilea canal Matrix (configurare) ─────────────────────────────────────

export interface MatrixConfig {
  enabled: boolean;
  homeserver: string;
  room_id: string;
  allowed_users: string[];
  token_set: boolean;
}

export const useMatrixConfig = () =>
  useQuery<MatrixConfig>({
    queryKey: ["matrix-config"],
    queryFn:  () => apiFetch("/telegram-bridge/matrix-config"),
    staleTime: 30_000,
  });

export const useSaveMatrixConfig = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { enabled: boolean; homeserver: string; room_id: string;
                         allowed_users: string[]; access_token?: string }) =>
      apiFetch("/telegram-bridge/matrix-config", { method: "PUT", body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["matrix-config"] }),
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

export const useMt5Stats = (source: string = "all") =>
  useQuery<Mt5TradeStats>({
    queryKey: ["mt5-stats", source],
    queryFn:  () => apiFetch(`/mt5/stats?source=${source}`),
    refetchInterval: POLL,
    retry: false,
  });

export const useMt5EquityCurve = (metric: "usd" | "r" = "usd", source: string = "all") =>
  useQuery<Mt5EquityCurveResponse>({
    queryKey: ["mt5-equity-curve", metric, source],
    queryFn:  () => apiFetch(`/mt5/equity-curve?metric=${metric}&source=${source}`),
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

export const useSetTelegramImportantOnly = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (enabled: boolean) =>
      apiFetch("/settings/telegram/important-only", { method: "PUT", body: { enabled } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["telegram-config"] }),
  });
};

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

export const useMt5TopMarkets = (period: string, limit = 5, source: string = "all") =>
  useQuery<Mt5TopMarketsResponse>({
    queryKey: ["mt5-top-markets", period, limit, source],
    queryFn:  () => apiFetch(`/mt5/top-markets?period=${period}&limit=${limit}&source=${source}`),
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

export const useMt5SessionStats = (source: string = "bot") =>
  useQuery<Mt5SessionsResponse>({
    queryKey: ["mt5-session-stats", source],
    queryFn:  () => apiFetch(`/mt5/sessions?source=${source}`),
    refetchInterval: POLL,
    refetchIntervalInBackground: false,
  });

export const useMt5Transactions = (params: {
  status?: string;
  direction?: string;
  symbol?: string;
  source?: "bot" | "ai" | "daily" | "noisy" | "manual";
  session_id?: string;
  date_from?: string;
  date_to?: string;
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
      if (params.source)    qs.set("source",    params.source);
      if (params.session_id) qs.set("session_id", params.session_id);
      if (params.date_from) qs.set("date_from", params.date_from);
      if (params.date_to)   qs.set("date_to",   params.date_to);
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
    refetchIntervalInBackground: false,   // nu polui cand fereastra e in fundal
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

import type { AiProvidersResponse, AiProviderTestResult, AiProviderModelsResult } from "./types";

// `poll=true` (AI Engine tab): reimprospatare la 15s pentru sanatatea live a
// surselor. `poll=false` (SessionEditor, montat permanent in tab-ul Profile):
// FARA interval — altfel /ai/providers ar fi cerut la nesfarsit chiar si cand
// esti pe Dashboard. React Query partajeaza query-ul pe cheie, deci polling-ul
// se face doar cat timp cardul cu poll=true e montat (AI tab vizitat).
export const useAiProviders = (poll = true) =>
  useQuery<AiProvidersResponse>({
    queryKey: ["ai-providers"],
    queryFn:  () => apiFetch("/ai/providers"),
    refetchInterval: poll ? 15_000 : false,
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

// Testeaza TOATE sursele in paralel (butonul "Testeaza sursele").
export interface AiTestAllResult {
  results: Record<string, AiProviderTestResult>;
  healthy: string[];
  failed: string[];
  n_healthy: number;
  n_total: number;
  all_down: boolean;
  roles_at_risk: string[];
}
export const useAiTestAllProviders = () =>
  useMutation<AiTestAllResult, Error, void>({
    mutationFn: () => apiFetch("/ai/providers/test-all", { method: "POST" }),
  });

// Descoperire LIVE de modele la o sursa (dropdown dinamic in AiProvidersCard).
// Sursa existenta: {name}. Sursa noua (formularul de adaugare): {type, base_url?, key?}.
export const useAiProviderModels = () =>
  useMutation<AiProviderModelsResult, Error, {
    name?: string; type?: string; base_url?: string; url?: string; key?: string;
  }>({
    mutationFn: body =>
      apiFetch("/ai/providers/models", { method: "POST", body }),
  });

// Costul real (MT5) al unui volum fix pe o piata — pentru campul "Loturi" din
// Limite per piata (marja necesara + USD per unitate de pret).
export const useAiLotInfo = () =>
  useMutation<import("./types").AiLotInfo, Error, { symbol: string; lots: number }>({
    mutationFn: body => apiFetch("/ai/lot-info", { method: "POST", body }),
  });

// ── Trading LIVE — deblocarea explicita a contului real, per componenta ──────

export interface LiveTradingState {
  flags: { bot: boolean; ai_engine: boolean; daily_engine?: boolean; noisy_engine?: boolean };
  account: { connected: boolean; is_demo: boolean | null;
             login: string | null; server: string | null };
}

export const useLiveTrading = () =>
  useQuery<LiveTradingState>({
    queryKey: ["live-trading"],
    queryFn:  () => apiFetch("/settings/live-trading"),
    refetchInterval: 30_000,
    refetchIntervalInBackground: false,
  });

export const useSetLiveTrading = () => {
  const qc = useQueryClient();
  return useMutation<{ ok: boolean; flags: LiveTradingState["flags"]; note: string },
                     Error, { component: "bot" | "ai_engine" | "daily_engine" | "noisy_engine"; allowed: boolean }>({
    mutationFn: body => apiFetch("/settings/live-trading", { method: "PUT", body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["live-trading"] }),
  });
};

// ─── Setari Globale (Bot + AI) — data/global_settings.json, hot-reload ───────
export interface GlobalSettings {
  capital_protection: { enabled: boolean; threshold_pct: number; start_balance: number | null };
  circuit_breaker: { enabled: boolean; max_consecutive_losses: number; max_daily_loss_pct: number };
  friday_close: { enabled: boolean; hour: number; exclude_crypto: boolean };
  news_protection: { enabled: boolean; impact_level: number; pre_minutes: number; post_minutes: number };
  max_concurrent_per_market: { enabled: boolean; max: number };
  ai_filter: { enabled: boolean; level: "permissive" | "balanced" | "strict"; strict: boolean };
  risk_cap: { enabled: boolean; max_risk_pct: number };
}

export const useGlobalSettings = () =>
  useQuery<GlobalSettings>({
    queryKey: ["global-settings"],
    queryFn:  () => apiFetch("/settings/global"),
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
  });

export const useSaveGlobalSettings = () => {
  const qc = useQueryClient();
  return useMutation<GlobalSettings, Error, Partial<GlobalSettings>>({
    mutationFn: body => apiFetch("/settings/global", { method: "PUT", body }),
    onSuccess: data => qc.setQueryData(["global-settings"], data),
  });
};

// ─── Verdicte M0 per sesiune (data/m0_audit.csv) — gate vizual in Settings ───
export interface M0Verdict { verdict: "KEEP" | "OBSERVE" | "DEMOTE" | "INSUFF"; n: number;
  expectancy: number | null; prob_positive: number | null; audited_at: string }
export const useM0Verdicts = () =>
  useQuery<Record<string, M0Verdict>>({
    queryKey: ["m0-verdicts"],
    queryFn:  () => apiFetch("/sessions/m0-verdicts"),
    staleTime: 10 * 60_000,
    refetchInterval: false,
  });

// ── Daily Engine ─────────────────────────────────────────────────────────────
import type { DailyStatus, DailyTrade } from "./types";

export const useDailyStatus = () =>
  useQuery<DailyStatus>({
    queryKey: ["daily-status"],
    queryFn:  () => apiFetch("/daily/status"),
    refetchInterval: 10_000,
    refetchIntervalInBackground: false,
  });

export const useDailyTrades = () =>
  useQuery<DailyTrade[]>({
    queryKey: ["daily-trades"],
    queryFn:  () => apiFetch("/daily/trades?limit=200"),
    refetchInterval: 30_000,
    refetchIntervalInBackground: false,
  });

export const useDailyLogs = (enabled: boolean) =>
  useQuery<{ lines: string[] }>({
    queryKey: ["daily-logs"],
    queryFn:  () => apiFetch("/daily/logs?lines=150"),
    refetchInterval: 15_000,
    refetchIntervalInBackground: false,
    enabled,
  });

export const useDailyStart = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch("/daily/start", { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["daily-status"] }),
  });
};

export const useDailyStop = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch("/daily/stop", { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["daily-status"] }),
  });
};

// ── Engine Lifecycle comun (/engines) — status real + start/stop verificat + autostart ──
import type { EngineState, LifecycleEngineId } from "./types";

export const useEngines = () =>
  useQuery<EngineState[]>({
    queryKey: ["engines"],
    queryFn:  () => apiFetch("/engines"),
    refetchInterval: 10_000,
    refetchIntervalInBackground: false,
  });

export const useEngineAction = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, action }: { id: LifecycleEngineId; action: "start" | "stop" | "autostart/enable" | "autostart/disable" }) =>
      apiFetch(`/engines/${id}/${action}`, { method: "POST" }),
    onSettled: () => {
      for (const k of ["engines", "bot-status", "ai-status", "daily-status", "noisy-status", "sessions"])
        qc.invalidateQueries({ queryKey: [k] });
    },
  });
};

// ── Performanta pe engine (cele 4 carduri + sectiunile per engine) ───────────
import type { EnginePerformanceResponse } from "./types";

export const useEnginePerformance = () =>
  useQuery<EnginePerformanceResponse>({
    queryKey: ["engine-performance"],
    queryFn:  () => apiFetch("/mt5/engine-performance?days=365"),
    refetchInterval: 60_000,                 // aceeasi lista cache-uita ca /mt5/stats
    refetchIntervalInBackground: false,
  });

// ── Ritm de tranzactionare (inlocuieste "Frecventa estimata") — recalculat la 15 min ──
import type { TradingPaceResponse } from "./types";

export const useTradingPace = () =>
  useQuery<TradingPaceResponse>({
    queryKey: ["trading-pace"],
    queryFn:  () => apiFetch("/dashboard/trading-pace"),
    refetchInterval: 15 * 60_000,            // = cache-ul serverului; ritmul saptamanal nu se schimba mai des
    refetchIntervalInBackground: false,
    staleTime: 5 * 60_000,
  });

// ── Previzualizare dimensionare (acelasi calcul ca la ordine) ────────────────
import type { SizingPreview } from "./types";

export const useSizingPreview = (p: { symbol?: string; fraction: number; riskPct: number;
                                      fixedLots?: number | null; capitalSync?: boolean; capitalUsd?: number | null }) =>
  useQuery<SizingPreview>({
    queryKey: ["sizing-preview", p.symbol, p.fraction, p.riskPct, p.fixedLots ?? null, p.capitalSync ?? true, p.capitalUsd ?? null],
    queryFn: () => {
      const q = new URLSearchParams({ symbol: p.symbol ?? "", fraction: String(p.fraction), risk_pct: String(p.riskPct),
                                      capital_sync_mt5: String(p.capitalSync ?? true) });
      if (p.fixedLots) q.set("fixed_lots", String(p.fixedLots));
      if (p.capitalUsd) q.set("capital_usd", String(p.capitalUsd));
      return apiFetch(`/sizing/preview?${q.toString()}`);
    },
    enabled: !!p.symbol,
    staleTime: 30_000,
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
  });

/** Configurarea Daily (piete: R:R + re-intrari) — citita direct, ca editorul sa mearga si cu engine-ul oprit */
export const useDailyConfig = () =>
  useQuery<{ markets: DailyMarketConfig[] }>({
    queryKey: ["daily-config"],
    queryFn:  () => apiFetch("/daily/config"),
    staleTime: 10_000,
  });

export const useDailyPresets = () =>
  useQuery<{ presets: Record<string, DailyPreset>; slots: string[] }>({
    queryKey: ["daily-presets"],
    queryFn:  () => apiFetch("/daily/presets"),
    staleTime: 3_600_000,
  });

/** Previzualizarea unei piete noi pentru slot: costuri auto, marja, backtest rapid ~3 ani (nu salveaza nimic) */
export const useDailyMarketPreview = () =>
  useMutation({
    mutationFn: (b: { slot: number; symbol: string; preset: string; costs_mode?: "auto" | "manual"; slip?: number; comm?: number }) =>
      apiFetch<DailyMarketPreview>("/daily/market-preview", { method: "POST", body: b }),
  });

export const useDailySaveSlot = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (b: { slot: number; symbol: string; preset: string; costs_mode: "auto" | "manual"; slip?: number; comm?: number }) =>
      apiFetch("/daily/config", { method: "PUT", body: { markets: [b] } }),
    onSuccess: () => {
      for (const k of ["daily-config", "daily-status"]) qc.invalidateQueries({ queryKey: [k] });
    },
  });
};

export const useDailySaveMarket = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (m: { symbol: string; rr: number | null; reentry: DailyReentry }) =>
      apiFetch("/daily/config", { method: "PUT", body: { markets: [m] } }),
    onSuccess: () => {
      for (const k of ["daily-config", "daily-status"]) qc.invalidateQueries({ queryKey: [k] });
    },
  });
};

export const useDailySetMode = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (mode: "shadow" | "execute") => apiFetch("/daily/config", { method: "PUT", body: { mode } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["daily-status"] }),
  });
};

import type { DailyMarketConfig, DailyMarketPreview, DailyPreset, DailyReentry } from "./types";

// ── Noisy Engine ─────────────────────────────────────────────────────────────
import type { NoisyStatus, NoisyTrade, NoisyConfig, NoisyMarketInfo } from "./types";

export const useNoisyStatus = () =>
  useQuery<NoisyStatus>({
    queryKey: ["noisy-status"],
    queryFn:  () => apiFetch("/noisy/status"),
    refetchInterval: 5_000,
    refetchIntervalInBackground: false,
  });

export const useNoisyTrades = () =>
  useQuery<NoisyTrade[]>({
    queryKey: ["noisy-trades"],
    queryFn:  () => apiFetch("/noisy/trades?limit=300"),
    refetchInterval: 20_000,
    refetchIntervalInBackground: false,
  });

export const useNoisyLogs = (enabled: boolean) =>
  useQuery<{ lines: string[] }>({
    queryKey: ["noisy-logs"],
    queryFn:  () => apiFetch("/noisy/logs?lines=150"),
    refetchInterval: 10_000,
    refetchIntervalInBackground: false,
    enabled,
  });

/** start / stop / emergency-stop / pause / resume / reset-budget */
export const useNoisyAction = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (action: "start" | "stop" | "emergency-stop" | "pause" | "resume" | "reset-budget") =>
      apiFetch(`/noisy/${action}`, { method: "POST" }),
    onSettled: () => {
      for (const k of ["noisy-status", "engines"]) qc.invalidateQueries({ queryKey: [k] });
    },
  });
};

/** Specificatiile pietei din MT5 (point / digits / spread live / lot min / marja) — doar citire */
export const useNoisyMarketInfo = (symbol: string | undefined) =>
  useQuery<NoisyMarketInfo>({
    queryKey: ["noisy-market-info", symbol],
    queryFn:  () => apiFetch(`/noisy/market-info?symbol=${encodeURIComponent(symbol ?? "")}`),
    enabled: !!symbol,
    staleTime: 10_000,
    refetchInterval: 15_000,
    refetchIntervalInBackground: false,
  });

export const useNoisySaveConfig = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Partial<NoisyConfig>) =>
      apiFetch<NoisyConfig & { _notice?: string }>("/noisy/config", { method: "PUT", body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["noisy-status"] }),
  });
};

// ── Dashboard global: piete active + semnale din toate engine-urile ──────────
import type { DashboardMarkets, GlobalSignal } from "./types";

export const useDashboardMarkets = () =>
  useQuery<DashboardMarkets>({
    queryKey: ["dashboard-markets"],
    queryFn:  () => apiFetch("/dashboard/markets"),
    refetchInterval: 15_000,                 // starea engine-urilor; server cache 5 s
    refetchIntervalInBackground: false,
  });

export const useDashboardSignals = (symbol?: string, engine?: string, limit = 100) =>
  useQuery<GlobalSignal[]>({
    queryKey: ["dashboard-signals", symbol ?? "", engine ?? "", limit],
    queryFn:  () => apiFetch(`/dashboard/signals?limit=${limit}`
      + (symbol ? `&symbol=${encodeURIComponent(symbol)}` : "") + (engine ? `&engine=${engine}` : "")),
    refetchInterval: 30_000,
    refetchIntervalInBackground: false,
  });
