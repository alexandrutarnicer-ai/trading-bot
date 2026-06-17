import { TrendingUp, TrendingDown, Clock, Layers } from "lucide-react";
import type { SessionStatus } from "../api/types";

interface Props {
  session: SessionStatus;
  onClick: () => void;
  selected: boolean;
}

export function SessionCard({ session: s, onClick, selected }: Props) {
  const wr = s.outcomes_total > 0
    ? Math.round((s.wins / s.outcomes_total) * 100)
    : null;

  const statusColor = s.running ? "bg-profit" : "bg-surface-border";
  const borderColor = selected
    ? "border-blue-500"
    : s.running
    ? "border-profit/20"
    : "border-surface-border";

  return (
    <button
      onClick={onClick}
      className={`w-full text-left p-4 rounded-xl border bg-surface-card transition-all hover:border-blue-500/50 ${borderColor}`}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-2 mb-3">
        <div className="flex items-center gap-2">
          <span className={`mt-1 h-2 w-2 rounded-full flex-shrink-0 ${statusColor} ${s.running ? "animate-pulse" : ""}`} />
          <span className="font-semibold text-sm text-white leading-tight">{s.label}</span>
        </div>
        <div className="flex gap-1 flex-shrink-0">
          {!s.validated && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-warn/20 text-warn font-medium">DEMO</span>
          )}
          {!s.execute && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-surface-border text-slate-400 font-medium">OBS</span>
          )}
        </div>
      </div>

      {/* Markets */}
      <div className="flex flex-wrap gap-1 mb-3">
        {s.markets.map(m => (
          <span key={m} className="text-[10px] px-1.5 py-0.5 rounded bg-surface-border/60 text-slate-300">
            {m}
          </span>
        ))}
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-3 gap-2 text-center">
        <div>
          <div className="text-lg font-bold text-white">{s.signals_today}</div>
          <div className="text-[10px] text-slate-500">azi</div>
        </div>
        <div>
          <div className="text-lg font-bold text-white">{s.signals_total}</div>
          <div className="text-[10px] text-slate-500">total</div>
        </div>
        <div>
          {wr !== null ? (
            <>
              <div className={`text-lg font-bold ${wr >= 50 ? "text-profit" : "text-loss"}`}>{wr}%</div>
              <div className="text-[10px] text-slate-500">WR</div>
            </>
          ) : (
            <>
              <div className="text-lg font-bold text-slate-600">—</div>
              <div className="text-[10px] text-slate-500">WR</div>
            </>
          )}
        </div>
      </div>

      {/* Footer */}
      <div className="mt-3 pt-3 border-t border-surface-border flex items-center justify-between text-[10px] text-slate-500">
        <div className="flex items-center gap-1">
          <Layers size={10} />
          <span>{s.tf} · {s.direction} · {s.capital_pct}%</span>
        </div>
        {s.last_signal_time && (
          <div className="flex items-center gap-1">
            <Clock size={10} />
            <span>{s.last_signal_time}</span>
          </div>
        )}
      </div>
    </button>
  );
}
