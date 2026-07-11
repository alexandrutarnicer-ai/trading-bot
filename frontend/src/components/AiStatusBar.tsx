import { Brain, AlertCircle } from "lucide-react";
import { useAiStatus } from "../api/hooks";

/**
 * Indicator de stare pentru Motorul AI pe Dashboard — analog cu BotStatusBar.
 * "AI activ · N piețe" cand ruleaza, "AI oprit" altfel. Accent mov (ca restul UI-ului AI).
 */
export function AiStatusBar() {
  const { data, isLoading } = useAiStatus();

  if (isLoading) return null;

  const running  = data?.running ?? false;
  const nMarkets = data?.markets?.length ?? 0;

  return (
    <div className={`flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium ${
      running
        ? "bg-purple-500/10 border border-purple-500/30 text-purple-300"
        : "bg-surface-card border border-surface-border text-slate-500"
    }`}>
      {running ? (
        <>
          <span className="relative flex h-2 w-2 flex-shrink-0">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-purple-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-purple-400" />
          </span>
          <Brain size={13} className="flex-shrink-0" />
          <span>
            AI activ
            {nMarkets > 0 && (
              <>
                {" · "}
                <span>{nMarkets} piețe</span>
              </>
            )}
            {data?.mode === "shadow" && (
              <span className="text-warn/80 font-normal"> · shadow</span>
            )}
          </span>
          {data?.pid && (
            <span className="opacity-30 font-normal text-xs">PID {data.pid}</span>
          )}
        </>
      ) : (
        <>
          <AlertCircle size={13} className="flex-shrink-0" />
          <span>AI oprit</span>
        </>
      )}
    </div>
  );
}
