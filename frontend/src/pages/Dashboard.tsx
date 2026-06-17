import { useState } from "react";
import { RefreshCw } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useSessions } from "../api/hooks";
import { BotStatusBar } from "../components/BotStatusBar";
import { SessionCard } from "../components/SessionCard";
import { SignalFeed } from "../components/SignalFeed";
import { EquityChart } from "../components/EquityChart";

export function Dashboard() {
  const { data: sessions, isLoading } = useSessions();
  const [selectedSession, setSelectedSession] = useState<string>("session3");
  const qc = useQueryClient();

  const selected = sessions?.find(s => s.id === selectedSession);

  function refresh() {
    qc.invalidateQueries();
  }

  return (
    <div className="min-h-screen bg-surface p-4 md:p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white">Trading Bot</h1>
          <p className="text-xs text-slate-500 mt-0.5">Standard Profile · Demo</p>
        </div>
        <div className="flex items-center gap-3">
          <BotStatusBar />
          <button
            onClick={refresh}
            className="p-2 rounded-lg bg-surface-card border border-surface-border text-slate-400 hover:text-white transition-colors"
          >
            <RefreshCw size={14} />
          </button>
        </div>
      </div>

      {/* Sessions grid */}
      <div>
        <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">
          Sesiuni active
        </h2>
        {isLoading ? (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
            {[...Array(6)].map((_, i) => (
              <div key={i} className="h-40 rounded-xl bg-surface-card animate-pulse" />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
            {sessions?.map(s => (
              <SessionCard
                key={s.id}
                session={s}
                selected={s.id === selectedSession}
                onClick={() => setSelectedSession(s.id)}
              />
            ))}
          </div>
        )}
      </div>

      {/* Bottom two columns */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Signal feed */}
        <div className="bg-surface-card rounded-xl border border-surface-border p-4">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-white">
              Semnale — {selected?.label ?? "—"}
            </h2>
            <div className="flex gap-1">
              {sessions?.map(s => (
                <button
                  key={s.id}
                  onClick={() => setSelectedSession(s.id)}
                  className={`text-[10px] px-2 py-0.5 rounded transition-colors ${
                    s.id === selectedSession
                      ? "bg-blue-500/20 text-blue-400"
                      : "text-slate-500 hover:text-slate-300"
                  }`}
                >
                  {s.id.replace("session", "S")}
                </button>
              ))}
            </div>
          </div>
          <SignalFeed sessionId={selectedSession} />
        </div>

        {/* Equity chart + stats */}
        <div className="space-y-4">
          <div className="bg-surface-card rounded-xl border border-surface-border p-4">
            <h2 className="text-sm font-semibold text-white mb-4">Performanță</h2>
            <EquityChart />
          </div>

          {/* Quick stats */}
          <div className="bg-surface-card rounded-xl border border-surface-border p-4">
            <h2 className="text-sm font-semibold text-white mb-3">Sumar</h2>
            <div className="grid grid-cols-3 gap-3">
              {[
                {
                  label: "Trades închise",
                  value: sessions?.reduce((a, s) => a + s.outcomes_total, 0) ?? 0,
                },
                {
                  label: "Win Rate",
                  value: (() => {
                    const wins   = sessions?.reduce((a, s) => a + s.wins, 0) ?? 0;
                    const total  = sessions?.reduce((a, s) => a + s.outcomes_total, 0) ?? 0;
                    return total > 0 ? `${Math.round(wins / total * 100)}%` : "—";
                  })(),
                },
                {
                  label: "Semnale azi",
                  value: sessions?.reduce((a, s) => a + s.signals_today, 0) ?? 0,
                },
              ].map(stat => (
                <div key={stat.label} className="text-center">
                  <div className="text-2xl font-bold text-white">{stat.value}</div>
                  <div className="text-[10px] text-slate-500 mt-0.5">{stat.label}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
