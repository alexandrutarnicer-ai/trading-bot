import { useBotStatus, useStartBot, useStopBot } from "../api/hooks";
import { InfoTooltip } from "./InfoTooltip";

const MT5_TIP =
  "Înainte de a porni bot-ul:\n" +
  "1. Deschide MetaTrader 5\n" +
  "2. Loghează-te pe contul dorit (Demo sau Live)\n" +
  "3. Activează AutoTrading (butonul verde din toolbar)\n\n" +
  "Bot-ul se conectează automat la contul activ din MT5. " +
  "Dacă MT5 nu este deschis, sesiunile nu pot plasa ordine.";

export function BotControl() {
  const { data: status, isLoading } = useBotStatus();
  const start = useStartBot();
  const stop  = useStopBot();

  const running = status?.running ?? false;
  const pending = start.isPending || stop.isPending;
  const error   = (start.error as Error | null)?.message
               ?? (stop.error  as Error | null)?.message;

  return (
    <div className={`rounded-xl border p-4 flex items-center gap-4 ${
      running ? "border-profit/30 bg-profit/5" : "border-surface-border bg-surface-card"
    }`}>
      {/* Status dot */}
      <div className="flex items-center gap-2 flex-1">
        <div className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${
          isLoading ? "bg-slate-600" :
          running   ? "bg-profit animate-pulse" : "bg-slate-600"
        }`} />
        <div>
          <div className="text-xs font-semibold text-white">
            {isLoading ? "Se verifică..." : running ? "Bot activ" : "Bot oprit"}
          </div>
          {running && status?.sessions_active !== undefined && (
            <div className="text-[10px] text-slate-500">
              {status.sessions_active} sesiune{status.sessions_active !== 1 ? "i" : ""} active
              {status.pid ? ` · PID ${status.pid}` : ""}
            </div>
          )}
        </div>
      </div>

      {error && (
        <span className="text-xs text-loss flex-1 text-center">{error}</span>
      )}

      {/* MT5 info */}
      <div className="flex items-center gap-1 text-xs text-slate-500">
        Necesită MT5 deschis
        <InfoTooltip text={MT5_TIP} wide />
      </div>

      {/* Action button */}
      {running ? (
        <button
          onClick={() => stop.mutate()}
          disabled={pending}
          className="text-xs px-4 py-1.5 rounded-lg bg-loss/80 hover:bg-loss disabled:opacity-50 text-white font-medium transition-colors"
        >
          {stop.isPending ? "Se oprește..." : "■ Oprește Bot"}
        </button>
      ) : (
        <button
          onClick={() => start.mutate()}
          disabled={pending || isLoading}
          className="text-xs px-4 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-medium transition-colors"
        >
          {start.isPending ? "Se pornește..." : "▶ Pornește Bot"}
        </button>
      )}
    </div>
  );
}
