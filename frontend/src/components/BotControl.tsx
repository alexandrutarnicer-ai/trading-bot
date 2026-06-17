import { useState } from "react";
import { useBotStatus, useStartBot, useStopBot } from "../api/hooks";
import { InfoTooltip } from "./InfoTooltip";

const MT5_TIP =
  "Înainte de a porni bot-ul:\n" +
  "1. Deschide MetaTrader 5\n" +
  "2. Loghează-te pe contul dorit (Demo sau Live)\n" +
  "3. Activează AutoTrading (butonul verde din toolbar)\n\n" +
  "Bot-ul se conectează automat la contul activ din MT5. " +
  "Dacă MT5 nu este deschis, sesiunile nu pot plasa ordine.";

interface Props {
  profileId?: string;
  profileName?: string;
}

export function BotControl({ profileId, profileName }: Props) {
  const { data: status, isLoading } = useBotStatus();
  const start = useStartBot();
  const stop  = useStopBot();

  const [confirmSwitch, setConfirmSwitch] = useState(false);

  const running = status?.running ?? false;
  const pending = start.isPending || stop.isPending;
  const error   = (start.error as Error | null)?.message
               ?? (stop.error  as Error | null)?.message;

  const activeProfileId   = status?.active_profile_id   ?? null;
  const activeProfileName = status?.active_profile_name ?? null;

  // Profilul activ nu e stiut (bot pornit inainte de feature) → nu fortam comparatia
  const isDifferentProfile = running && !!activeProfileId && !!profileId && activeProfileId !== profileId;
  const isKnownSameProfile = running && !!activeProfileId && activeProfileId === profileId;

  // Afisam intotdeauna numele profilului cand rulam — fie cel curent, fie cel diferit
  const runningName = isKnownSameProfile
    ? (profileName ?? activeProfileName ?? activeProfileId)
    : (activeProfileName ?? activeProfileId);

  const statusLabel =
    isDifferentProfile  ? `Bot activ pe: ${runningName}` :
    isKnownSameProfile  ? `Bot activ · ${runningName}` :
    running             ? "Bot activ" :
    "Bot oprit";

  const dotColor =
    isDifferentProfile  ? "bg-warn animate-pulse" :
    isKnownSameProfile  ? "bg-profit animate-pulse" :
    running             ? "bg-profit animate-pulse" :
    "bg-slate-600";

  const borderClass =
    running && !isDifferentProfile ? "border-profit/30 bg-profit/5" :
    running && isDifferentProfile  ? "border-warn/30 bg-warn/5" :
    "border-surface-border bg-surface-card";

  const handleStart = () => {
    if (isDifferentProfile) { setConfirmSwitch(true); return; }
    start.mutate({ profile_id: profileId, profile_name: profileName });
  };

  const handleConfirmSwitch = () => {
    setConfirmSwitch(false);
    start.mutate({ profile_id: profileId, profile_name: profileName });
  };

  return (
    <div className={`rounded-xl border p-4 space-y-2 ${borderClass}`}>
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2 flex-1">
          <div className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${isLoading ? "bg-slate-600" : dotColor}`} />
          <div>
            <div className="text-xs font-semibold text-white">
              {isLoading ? "Se verifică..." : statusLabel}
            </div>
            {running && !isDifferentProfile && status?.sessions_active !== undefined && (
              <div className="text-[10px] text-slate-500">
                {status.sessions_active} sesiune{status.sessions_active !== 1 ? "i" : ""} active
                {status.pid ? ` · PID ${status.pid}` : ""}
              </div>
            )}
          </div>
        </div>

        {error && !confirmSwitch && (
          <span className="text-xs text-loss flex-1 text-center">{error}</span>
        )}

        <div className="flex items-center gap-1 text-xs text-slate-500">
          Necesită MT5 deschis
          <InfoTooltip text={MT5_TIP} wide />
        </div>

        {running ? (
          <button onClick={() => stop.mutate()} disabled={pending}
            className="text-xs px-4 py-1.5 rounded-lg bg-loss/80 hover:bg-loss disabled:opacity-50 text-white font-medium transition-colors">
            {stop.isPending ? "Se oprește..." : "■ Oprește Bot"}
          </button>
        ) : (
          <button onClick={handleStart} disabled={pending || isLoading}
            className="text-xs px-4 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-medium transition-colors">
            {start.isPending ? "Se pornește..." : "▶ Pornește Bot"}
          </button>
        )}
      </div>

      {confirmSwitch && (
        <div className="bg-warn/10 border border-warn/30 rounded-lg p-3 flex items-center gap-3 flex-wrap">
          <span className="text-xs text-warn flex-1">
            Bot-ul rulează pe „{activeProfileName ?? activeProfileId}". Pornind, vei opri profilul curent și vei activa „{profileName ?? profileId}".
          </span>
          <button onClick={handleConfirmSwitch} disabled={pending}
            className="text-xs px-3 py-1 rounded bg-warn/80 hover:bg-warn text-white font-medium transition-colors disabled:opacity-50">
            {start.isPending ? "..." : "Da, schimbă profilul"}
          </button>
          <button onClick={() => setConfirmSwitch(false)}
            className="text-xs px-3 py-1 rounded border border-surface-border text-slate-400 hover:text-white transition-colors">
            Anulează
          </button>
        </div>
      )}
    </div>
  );
}
