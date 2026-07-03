import type { StatsSource } from "../hooks/useStatsSource";

export function SourceToggle({ source, onChange }: { source: StatsSource; onChange: (s: StatsSource) => void }) {
  const opt = (key: StatsSource, label: string) => (
    <button
      onClick={() => onChange(key)}
      className={`px-2.5 py-1 rounded-lg text-[11px] font-medium transition-colors
        ${source === key
          ? "bg-blue-500/20 text-blue-300 border border-blue-500/50"
          : "text-slate-500 border border-transparent hover:text-slate-300"
        }`}
    >
      {label}
    </button>
  );
  return (
    <div className="flex items-center gap-1 mb-2">
      <span className="text-[10px] text-slate-600 uppercase tracking-wider mr-1">Sursă:</span>
      {opt("mt5", "MT5 direct")}
      {opt("bot", "Bot")}
    </div>
  );
}
