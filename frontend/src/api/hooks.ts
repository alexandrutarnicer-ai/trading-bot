import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "./client";
import type { BotStatus, SessionStatus, Signal, Outcome, EquityCurvePoint } from "./types";

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
