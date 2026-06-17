import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./client";
import type {
  BotStatus, SessionStatus, Signal, Outcome, EquityCurvePoint,
  Profile, ProfileSummary, Meta,
  DataCheckResult, DownloadJob, TelegramConfig, Mt5Status,
} from "./types";

const POLL = 30_000; // refresh la 30s

export const useBotStatus = () =>
  useQuery<BotStatus>({
    queryKey: ["bot-status"],
    queryFn:  () => apiFetch("/bot/status"),
    refetchInterval: POLL,
  });

export const useSessions = () =>
  useQuery<SessionStatus[]>({
    queryKey: ["sessions"],
    queryFn:  () => apiFetch("/sessions"),
    refetchInterval: POLL,
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

export const useRunBacktest = () =>
  useMutation({
    mutationFn: (payload: { session: object; date_from?: string; date_to?: string; start_balance?: number }) =>
      apiFetch("/backtest/run", { method: "POST", body: payload }),
  });

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

export const useCheckData = () =>
  useMutation({
    mutationFn: (params: { markets: string; entry_tf: string; trend_tf: string }) =>
      apiFetch<DataCheckResult>(
        `/data/check?markets=${params.markets}&entry_tf=${params.entry_tf}&trend_tf=${params.trend_tf}`
      ),
  });

export const useStartDownload = () =>
  useMutation({
    mutationFn: (body: { markets: string[]; timeframes: string[] }) =>
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

export const useStopBot = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch("/bot/stop", { method: "POST" }),
    onSuccess: () => { setTimeout(() => qc.invalidateQueries({ queryKey: ["bot-status"] }), 1500); },
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
