import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./client";
import type {
  BotStatus, SessionStatus, Signal, Outcome, EquityCurvePoint,
  Profile, ProfileSummary, Meta,
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

export const useRunBacktest = () =>
  useMutation({
    mutationFn: (session: object) =>
      apiFetch("/backtest/run", { method: "POST", body: { session } }),
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
