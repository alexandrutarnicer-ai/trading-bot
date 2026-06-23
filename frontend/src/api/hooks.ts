import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./client";
import type {
  BotStatus, SessionStatus, Signal, Outcome, EquityCurvePoint,
  Profile, ProfileSummary, Meta,
  DataCheckResult, DownloadJob, TelegramConfig, Mt5Status,
  BacktestHistoryEntry, BacktestJob, WeeklyStats,
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
    refetchInterval: POLL,
    refetchIntervalInBackground: true,
  });

export const useFrequencyEstimate = (profileId?: string) =>
  useQuery<{ per_week: number | null; per_month: number | null }>({
    queryKey: ["frequency-estimate", profileId ?? ""],
    queryFn:  () => apiFetch(`/sessions/frequency-estimate${profileId ? `?profile_id=${profileId}` : ""}`),
    refetchInterval: POLL,
    refetchIntervalInBackground: true,
  });

export const useSignals = (sessionId: string) =>
  useQuery<Signal[]>({
    queryKey: ["signals", sessionId],
    queryFn:  () => apiFetch(`/sessions/${sessionId}/signals?limit=30`),
    refetchInterval: POLL,
  });

export const useOutcomes = (sessionId: string) =>
  useQuery<Outcome[]>({
    queryKey: ["outcomes", sessionId],
    queryFn:  () => apiFetch(`/sessions/${sessionId}/outcomes`),
    refetchInterval: POLL,
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
    refetchIntervalInBackground: true,
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
