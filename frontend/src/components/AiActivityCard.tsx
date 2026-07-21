import { Brain } from "lucide-react";
import { useAiStatus } from "../api/hooks";

/**
 * Card compact cu activitatea Motorului AI pe Dashboard — separat de botul pe reguli.
 * Sursa: GET /ai/status (acelasi query ca AiStatusBar, partajat de React Query — fara
 * request suplimentar). Arata scorecardul motorului: decizii, trade-uri, W/L, R, piete.
 */
function Stat({ label, value, sub, valueClass }: {
  label: string; value: string; sub?: string; valueClass?: string;
}) {
  return (
    <div>
      <div className={`text-base font-bold leading-tight ${valueClass ?? "text-white"}`}>{value}</div>
      <div className="text-[10px] text-slate-500 mt-0.5">
        {label}{sub ? <span className="text-slate-600"> · {sub}</span> : null}
      </div>
    </div>
  );
}

export function AiActivityCard() {
  const { data } = useAiStatus();
  const running  = data?.running ?? false;
  const sc       = data?.scorecard ?? null;
  const markets  = data?.markets ?? [];
  const wr       = sc?.win_rate != null ? `${Math.round(sc.win_rate * 100)}%` : "—";
  const totalR   = sc?.total_R ?? 0;
  const expR     = sc?.expectancy_R ?? 0;

  return (
    <div className="bg-surface-card border border-surface-border rounded-xl p-4 space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Brain size={14} className="text-purple-400" />
          <span className="text-sm font-semibold text-white">Motor AI</span>
        </div>
        <span className={`flex items-center gap-1.5 text-[11px] font-medium ${
          running ? "text-purple-300" : "text-slate-500"
        }`}>
          <span className={`h-2 w-2 rounded-full ${running ? "bg-purple-400" : "bg-slate-600"}`} />
          {running ? `activ${markets.length ? ` · ${markets.length} piețe` : ""}` : "oprit"}
        </span>
      </div>

      {sc ? (
        <>
          <div className="grid grid-cols-3 gap-2">
            <Stat label="Decizii" value={String(sc.decisions)} sub={`${sc.waits} WAIT`} />
            <Stat label="Trade-uri" value={String(sc.closed_trades)}
                  sub={`${sc.wins ?? 0}W / ${sc.losses ?? 0}L`} />
            <Stat label="Win rate" value={wr} />
          </div>
          <div className="grid grid-cols-2 gap-2 pt-1 border-t border-surface-border">
            <Stat label="Total R" value={`${totalR >= 0 ? "+" : ""}${totalR.toFixed(2)}R`}
                  valueClass={totalR > 0 ? "text-profit" : totalR < 0 ? "text-loss" : "text-white"} />
            <Stat label="Expectancy" value={`${expR >= 0 ? "+" : ""}${expR.toFixed(3)}R`}
                  valueClass={expR > 0 ? "text-profit" : expR < 0 ? "text-loss" : "text-white"} />
          </div>
          {markets.length > 0 && (
            <div className="flex flex-wrap gap-1 pt-1">
              {markets.map(m => (
                <span key={m} className="text-[10px] px-1.5 py-0.5 rounded bg-purple-500/10 text-purple-300">
                  {m}
                </span>
              ))}
            </div>
          )}
          <p className="text-[10px] text-slate-600 leading-snug">
            Scorecard cumulat al motorului autonom AI (separat de estimarea botului pe reguli).
            Detalii în tab-ul AI Engine.
          </p>
        </>
      ) : (
        <div className="text-xs text-slate-500 text-center py-3">
          Fără date — motorul AI nu a rulat încă.
        </div>
      )}
    </div>
  );
}
