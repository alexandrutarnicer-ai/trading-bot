import { Pause, Play, Clock, Layers } from "lucide-react";
import type { SessionStatus } from "../api/types";
import { usePauseSession, useResumeSession } from "../api/hooks";

interface Props {
  session: SessionStatus;
  onClick: () => void;
  selected: boolean;
}

export function SessionCard({ session: s, onClick, selected }: Props) {
  const pause  = usePauseSession();
  const resume = useResumeSession();

  const wr = s.outcomes_total > 0
    ? Math.round((s.wins / s.outcomes_total) * 100)
    : null;

  const isPaused   = s.paused;
  const isNewsPaused = s.news_paused;
  const isRunning  = s.running;

  const dotColor = isPaused || isNewsPaused
    ? "bg-warn"
    : isRunning
    ? "bg-profit"
    : "bg-surface-border";

  const borderColor = selected
    ? "border-blue-500"
    : isPaused || isNewsPaused
    ? "border-warn/30"
    : isRunning
    ? "border-profit/20"
    : "border-surface-border";

  function handlePauseToggle(e: React.MouseEvent) {
    e.stopPropagation();
    if (isPaused) {
      resume.mutate(s.id);
    } else {
      pause.mutate(s.id);
    }
  }

  const busy = pause.isPending || resume.isPending;

  return (
    <button
      onClick={onClick}
      className={`w-full text-left p-4 rounded-xl border bg-surface-card transition-all hover:border-blue-500/50 ${borderColor}`}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-2 mb-3">
        <div className="flex items-center gap-2 min-w-0">
          <span className={`mt-1 h-2 w-2 rounded-full flex-shrink-0 ${dotColor} ${isRunning && !isPaused ? "animate-pulse" : ""}`} />
          <span className="font-semibold text-sm text-white leading-tight truncate">{s.label}</span>
        </div>

        <div className="flex items-center gap-1.5 flex-shrink-0">
          {/* LIVE/OBS badge */}
          {s.execute ? (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-profit/20 text-profit font-medium">LIVE</span>
          ) : (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-surface-border text-slate-400 font-medium">OBS</span>
          )}

          {/* News paused badge */}
          {isNewsPaused && !isPaused && (
            <span
              title={s.news_events[0] ? `${s.news_events[0].title} (${s.news_events[0].currency}, ${s.news_events[0].minutes_to >= 0 ? `in ${s.news_events[0].minutes_to} min` : `acum ${Math.abs(s.news_events[0].minutes_to)} min in urma`})` : "Pauza automata stiri"}
              className="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-400 font-medium cursor-help"
            >
              ⚡ ȘTIRI
            </span>
          )}

          {/* Manual paused badge */}
          {isPaused && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-warn/20 text-warn font-medium">PAUZA</span>
          )}

          {/* Pause/Play button */}
          <button
            onClick={handlePauseToggle}
            disabled={busy}
            title={isPaused ? "Reia sesiunea" : "Pune sesiunea pe pauză"}
            className={`p-1 rounded transition-colors ${
              busy
                ? "opacity-40 cursor-not-allowed"
                : isPaused
                ? "text-profit hover:bg-profit/10"
                : "text-slate-500 hover:text-warn hover:bg-warn/10"
            }`}
          >
            {isPaused
              ? <Play size={13} fill="currentColor" />
              : <Pause size={13} />
            }
          </button>
        </div>
      </div>

      {/* Markets */}
      <div className="flex flex-wrap gap-1 mb-3">
        {s.markets.map(m => (
          <span
            key={m}
            className={`text-[10px] px-1.5 py-0.5 rounded ${
              isPaused
                ? "bg-surface-border/40 text-slate-500"
                : "bg-surface-border/60 text-slate-300"
            }`}
          >
            {m}
          </span>
        ))}
      </div>

      {/* Stats row */}
      <div className={`grid grid-cols-3 gap-2 text-center ${isPaused || isNewsPaused ? "opacity-60" : ""}`}>
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
