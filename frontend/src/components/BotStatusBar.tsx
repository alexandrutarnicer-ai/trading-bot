import { Activity, AlertCircle } from "lucide-react";
import { useBotStatus } from "../api/hooks";

export function BotStatusBar() {
  const { data, isLoading } = useBotStatus();

  if (isLoading) return null;

  const running = data?.running ?? false;

  return (
    <div className={`flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium ${
      running
        ? "bg-profit/10 border border-profit/30 text-profit"
        : "bg-surface-card border border-surface-border text-slate-500"
    }`}>
      {running ? (
        <>
          <span className="relative flex h-2 w-2 flex-shrink-0">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-profit opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-profit" />
          </span>
          <Activity size={13} className="flex-shrink-0" />
          <span>Bot activ — {data?.sessions_active} sesiuni</span>
          {data?.pid && (
            <span className="opacity-30 font-normal text-xs">PID {data.pid}</span>
          )}
        </>
      ) : (
        <>
          <AlertCircle size={13} className="flex-shrink-0" />
          <span>Bot oprit</span>
          {data?.last_stopped_at && (
            <span className="text-xs text-slate-600 font-normal ml-1">
              · {formatRelative(data.last_stopped_at)}
            </span>
          )}
        </>
      )}
    </div>
  );
}

function formatRelative(iso: string): string {
  const d    = new Date(iso);
  const now  = new Date();
  const diff = Math.floor((now.getTime() - d.getTime()) / 60_000);
  if (diff < 1)  return "acum";
  if (diff < 60) return `acum ${diff}m`;
  const h = Math.floor(diff / 60);
  if (h < 24) return `azi ${d.toLocaleTimeString("ro-RO", { hour: "2-digit", minute: "2-digit" })}`;
  return `ieri ${d.toLocaleTimeString("ro-RO", { hour: "2-digit", minute: "2-digit" })}`;
}
