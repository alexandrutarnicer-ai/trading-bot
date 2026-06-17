import { useState, useEffect } from "react";
import { RefreshCw } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useSessions, useBotStatus, useMt5Status } from "../api/hooks";
import { BotStatusBar } from "../components/BotStatusBar";
import { SessionCard } from "../components/SessionCard";
import { SignalFeed } from "../components/SignalFeed";
import { EquityChart } from "../components/EquityChart";

export function Dashboard() {
  const { data: sessions, isLoading, dataUpdatedAt } = useSessions();
  const { data: botStatus } = useBotStatus();
  const { data: mt5 } = useMt5Status();
  const [selectedSession, setSelectedSession] = useState<string>("session3");
  const [now, setNow] = useState(Date.now());
  const qc = useQueryClient();

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 5_000);
    return () => clearInterval(id);
  }, []);

  const secsAgo = dataUpdatedAt ? Math.floor((now - dataUpdatedAt) / 1000) : null;
  const updateLabel = secsAgo === null ? null
    : secsAgo < 5  ? "acum"
    : secsAgo < 60 ? `${secsAgo}s`
    : `${Math.floor(secsAgo / 60)}m`;

  const selected = sessions?.find(s => s.id === selectedSession);

  function refresh() {
    qc.invalidateQueries();
  }

  const profileLabel = botStatus?.active_profile_name ?? "Standard";

  return (
    <div className="p-4 md:p-6 space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between gap-4">
        {/* Stanga: profil + cont MT5 */}
        <div className="flex items-center gap-4 flex-wrap">
          <span className="text-sm font-semibold text-white">{profileLabel} Profile</span>
          {mt5?.connected && (
            <div className="flex items-center gap-3 text-xs text-slate-400 bg-surface-card border border-surface-border rounded-lg px-3 py-1.5">
              <span className="text-slate-500">Cont</span>
              <span className="font-mono text-white">{mt5.account}</span>
              {mt5.server && <span className="text-slate-600">· {mt5.server}</span>}
              <span className="w-px h-3 bg-surface-border" />
              <span className="text-slate-500">Balance</span>
              <span className="font-mono text-white font-medium">
                {mt5.balance?.toLocaleString("ro-RO", { maximumFractionDigits: 2 })} {mt5.currency}
              </span>
              <span className="text-slate-500">Equity</span>
              <span className={`font-mono font-medium ${
                mt5.equity !== null && mt5.balance !== null
                  ? mt5.equity >= mt5.balance ? "text-profit" : "text-loss"
                  : "text-white"
              }`}>
                {mt5.equity?.toLocaleString("ro-RO", { maximumFractionDigits: 2 })} {mt5.currency}
              </span>
            </div>
          )}
          {mt5 && !mt5.connected && (
            <span className="text-[10px] text-slate-600 bg-surface-card border border-surface-border rounded px-2 py-1">
              MT5 deconectat
            </span>
          )}
        </div>

        {/* Dreapta: bot status + timer + refresh */}
        <div className="flex items-center gap-3 flex-shrink-0">
          <BotStatusBar />
          {updateLabel && (
            <span className="text-[10px] text-slate-600 tabular-nums">
              actualizat {updateLabel}
            </span>
          )}
          <button
            onClick={refresh}
            className="p-2 rounded-lg bg-surface-card border border-surface-border text-slate-400 hover:text-white transition-colors"
            title="Reîncarcă datele"
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
          <SignalFeed
            sessionId={selectedSession}
            balanceUsd={mt5?.connected ? mt5.balance : null}
            capitalPct={selected?.capital_pct}
          />
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
                    const wins  = sessions?.reduce((a, s) => a + s.wins, 0) ?? 0;
                    const total = sessions?.reduce((a, s) => a + s.outcomes_total, 0) ?? 0;
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
