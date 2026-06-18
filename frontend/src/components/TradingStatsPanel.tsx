import { useState } from "react";
import type { SessionStatus } from "../api/types";

interface Props {
  sessions: SessionStatus[];
}

function Trend({ today, yesterday }: { today: number; yesterday: number }) {
  if (yesterday === 0 && today === 0) return null;
  if (yesterday === 0)
    return <span className="text-[10px] text-profit ml-1">▲ nou</span>;
  const delta = today - yesterday;
  if (delta === 0)
    return <span className="text-[10px] text-slate-500 ml-1">= ieri {yesterday}</span>;
  return (
    <span className={`text-[10px] ml-1 ${delta > 0 ? "text-profit" : "text-warn"}`}>
      {delta > 0 ? "▲" : "▼"} {Math.abs(delta)} vs ieri
    </span>
  );
}

interface StatCardProps {
  label: string;
  value: number;
  sub?: string;
  today?: number;
  yesterday?: number;
  accent?: string;
  onClick?: () => void;
  active?: boolean;
}

function StatCard({ label, value, sub, today, yesterday, accent = "text-white", onClick, active }: StatCardProps) {
  return (
    <button
      onClick={onClick}
      className={`flex-1 min-w-0 text-left px-4 py-3 rounded-xl border transition-all
        ${active
          ? "border-blue-500/60 bg-blue-500/10"
          : "border-surface-border bg-surface-card hover:border-slate-600 hover:bg-surface-border/20"
        }
        ${onClick ? "cursor-pointer" : "cursor-default"}
      `}
    >
      <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">{label}</div>
      <div className={`text-2xl font-bold font-mono tabular-nums ${accent}`}>{value.toLocaleString()}</div>
      {sub && <div className="text-[10px] text-slate-600 mt-0.5">{sub}</div>}
      {today !== undefined && yesterday !== undefined && (
        <div className="flex items-center mt-1">
          <span className="text-xs text-slate-400">{today} azi</span>
          <Trend today={today} yesterday={yesterday} />
        </div>
      )}
    </button>
  );
}

export function TradingStatsPanel({ sessions }: Props) {
  const [expanded, setExpanded] = useState<"signals" | "trades" | null>(null);

  const totalSignals   = sessions.reduce((s, x) => s + x.signals_total,    0);
  const totalTrades    = sessions.reduce((s, x) => s + x.outcomes_total,   0);
  const signalsToday   = sessions.reduce((s, x) => s + x.signals_today,    0);
  const signalsYest    = sessions.reduce((s, x) => s + x.signals_yesterday, 0);
  const tradesToday    = sessions.reduce((s, x) => s + x.outcomes_today,    0);
  const tradesYest     = sessions.reduce((s, x) => s + x.outcomes_yesterday, 0);
  const totalWins      = sessions.reduce((s, x) => s + x.wins,              0);
  const totalLosses    = sessions.reduce((s, x) => s + x.losses,            0);
  const winRate        = totalWins + totalLosses > 0
    ? Math.round(totalWins / (totalWins + totalLosses) * 100)
    : null;

  const toggle = (key: "signals" | "trades") =>
    setExpanded(prev => (prev === key ? null : key));

  return (
    <div className="space-y-2">
      {/* Stat cards row */}
      <div className="flex gap-2 flex-wrap">
        <StatCard
          label="Total Semnale"
          value={totalSignals}
          today={signalsToday}
          yesterday={signalsYest}
          onClick={() => toggle("signals")}
          active={expanded === "signals"}
        />
        <StatCard
          label="Total Trades"
          value={totalTrades}
          today={tradesToday}
          yesterday={tradesYest}
          sub={winRate !== null ? `${winRate}% win rate` : undefined}
          accent={winRate !== null && winRate >= 50 ? "text-profit" : "text-white"}
          onClick={() => toggle("trades")}
          active={expanded === "trades"}
        />
        <StatCard
          label="Câștiguri"
          value={totalWins}
          accent="text-profit"
        />
        <StatCard
          label="Pierderi"
          value={totalLosses}
          accent="text-loss"
        />
      </div>

      {/* Expandable breakdown */}
      {expanded && (
        <div className="border border-surface-border rounded-xl overflow-hidden">
          <div className="px-4 py-2 border-b border-surface-border/60 flex items-center justify-between">
            <span className="text-[10px] text-slate-500 uppercase tracking-wider font-medium">
              {expanded === "signals" ? "Semnale per sesiune" : "Trades per sesiune"}
            </span>
            <button onClick={() => setExpanded(null)} className="text-slate-600 hover:text-slate-400 text-xs">✕</button>
          </div>
          <div className="divide-y divide-surface-border/40">
            {sessions.map(s => {
              const val  = expanded === "signals" ? s.signals_total   : s.outcomes_total;
              const tday = expanded === "signals" ? s.signals_today   : s.outcomes_today;
              const tyes = expanded === "signals" ? s.signals_yesterday : s.outcomes_yesterday;
              if (val === 0 && tday === 0) return null;
              return (
                <div key={s.id} className="flex items-center gap-3 px-4 py-2.5">
                  <div className="flex items-center gap-2 min-w-0 flex-1">
                    <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${s.running ? "bg-profit" : "bg-slate-600"}`} />
                    <span className="text-xs text-slate-300 font-medium">{s.label}</span>
                    <span className="text-[10px] text-slate-600 truncate">{s.markets.join(" · ")}</span>
                  </div>
                  <div className="flex items-center gap-3 text-xs text-right">
                    <span className="text-slate-300 font-mono tabular-nums">{val}</span>
                    <span className="text-slate-500 text-[10px]">
                      {tday} azi
                      {tyes > 0 && <span className="ml-1 text-slate-600">/ {tyes} ieri</span>}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
