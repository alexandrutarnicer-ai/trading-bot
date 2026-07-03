import { useState } from "react";

export type StatsSource = "mt5" | "bot";

const SOURCE_KEY = "statsSource";

function readStoredSource(): StatsSource {
  try {
    const v = localStorage.getItem(SOURCE_KEY);
    return v === "bot" ? "bot" : "mt5"; // MT5 e sursa default
  } catch {
    return "mt5";
  }
}

export function useStatsSource() {
  const [source, setSourceState] = useState<StatsSource>(readStoredSource);
  const setSource = (s: StatsSource) => {
    setSourceState(s);
    try { localStorage.setItem(SOURCE_KEY, s); } catch { /* ignore */ }
  };
  return [source, setSource] as const;
}
