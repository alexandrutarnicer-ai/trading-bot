import { Activity, AlertCircle } from "lucide-react";
import { useBotStatus } from "../api/hooks";

export function BotStatusBar() {
  const { data, isLoading } = useBotStatus();

  if (isLoading) return null;

  const running = data?.running ?? false;

  return (
    <div className={`flex items-center gap-3 px-4 py-2 rounded-lg text-sm font-medium ${
      running
        ? "bg-profit/10 border border-profit/30 text-profit"
        : "bg-loss/10 border border-loss/30 text-loss"
    }`}>
      {running ? (
        <>
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-profit opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-profit" />
          </span>
          <Activity size={14} />
          <span>Bot activ — {data?.sessions_active} sesiuni</span>
          {data?.pid && <span className="opacity-50 font-normal">PID {data.pid}</span>}
        </>
      ) : (
        <>
          <AlertCircle size={14} />
          <span>Bot oprit</span>
        </>
      )}
    </div>
  );
}
