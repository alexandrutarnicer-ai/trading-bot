import { useSignals, useOutcomes } from "../api/hooks";
import type { Outcome } from "../api/types";

interface Props {
  sessionId: string;
  balanceUsd?: number | null;
  capitalPct?: number;
}

function fmtUsd(n: number): string {
  const abs = Math.abs(n);
  const sign = n < 0 ? "-" : "+";
  const str = abs < 10 ? abs.toFixed(2) : abs.toFixed(0);
  return ` (${sign}${str} USD)`;
}

function statusBadge(o: Outcome, riskUsd: number | null) {
  if (o.status === "TP") {
    const usdStr = o.pnl_usd != null
      ? fmtUsd(o.pnl_usd)
      : riskUsd != null ? fmtUsd(o.result_r * riskUsd) : "";
    return (
      <span className="text-[10px] font-bold text-profit">
        +{o.r_ratio}R TP{usdStr ? <span className="font-normal opacity-75">{usdStr}</span> : null}
      </span>
    );
  }
  if (o.status === "SL") {
    const usdStr = o.pnl_usd != null
      ? fmtUsd(o.pnl_usd)
      : riskUsd != null ? fmtUsd(o.result_r * riskUsd) : "";
    return (
      <span className="text-[10px] font-bold text-loss">
        {o.result_r.toFixed(2)}R SL{usdStr ? <span className="font-normal opacity-75">{usdStr}</span> : null}
      </span>
    );
  }
  if (o.status === "expirat")  return <span className="text-[10px] text-slate-500">expirat</span>;
  if (o.status === "invalidat") return <span className="text-[10px] text-warn">invalidat</span>;
  return <span className="text-[10px] text-slate-500">{o.status}</span>;
}

export function SignalFeed({ sessionId, balanceUsd, capitalPct }: Props) {
  const { data: signals, isLoading: loadSig } = useSignals(sessionId);
  const { data: outcomes } = useOutcomes(sessionId);

  const outcomeMap = new Map((outcomes ?? []).map(o => [o.signal_id, o]));

  // Risc per trade in USD: balance × capitalPct% × 1% risc
  const riskUsd: number | null =
    balanceUsd && capitalPct
      ? balanceUsd * (capitalPct / 100) * 0.01
      : null;

  if (loadSig) {
    return (
      <div className="space-y-2">
        {[...Array(5)].map((_, i) => (
          <div key={i} className="h-12 rounded-lg bg-surface-border/30 animate-pulse" />
        ))}
      </div>
    );
  }

  if (!signals?.length) {
    return (
      <div className="text-center py-8 text-slate-500 text-sm">
        Niciun semnal înregistrat
      </div>
    );
  }

  return (
    <div className="space-y-1.5 max-h-[420px] overflow-y-auto pr-1">
      {signals.map(sig => {
        const outcome = outcomeMap.get(sig.signal_id);
        const fmt = sig.entry > 100 ? 2 : 5;
        const isLong = sig.direction === 1;

        return (
          <div
            key={sig.signal_id}
            className="flex items-center gap-3 px-3 py-2.5 rounded-lg bg-surface-border/20 hover:bg-surface-border/40 transition-colors"
          >
            {/* Direction badge */}
            <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded flex-shrink-0 ${
              isLong ? "bg-profit/20 text-profit" : "bg-loss/20 text-loss"
            }`}>
              {sig.dir_str}
            </span>

            {/* Symbol + time */}
            <div className="flex-1 min-w-0">
              <div className="flex items-baseline gap-2">
                <span className="text-sm font-semibold text-white">{sig.symbol}</span>
                <span className="text-[10px] text-slate-500">{sig.time.slice(0, 16)}</span>
              </div>
              <div className="text-[10px] text-slate-400 font-mono">
                {sig.entry.toFixed(fmt)} → TP {sig.tp.toFixed(fmt)}
              </div>
            </div>

            {/* R ratio + outcome */}
            <div className="text-right flex-shrink-0">
              <div className="text-xs text-slate-400">{sig.r_ratio}R</div>
              {outcome ? statusBadge(outcome, riskUsd) : (
                <span className="text-[10px] text-slate-600">pending</span>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
