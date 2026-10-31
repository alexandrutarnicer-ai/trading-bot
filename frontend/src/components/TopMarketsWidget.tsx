import { useState } from "react";
import { useMt5TopMarkets } from "../api/hooks";
import { InfoTooltip } from "./InfoTooltip";

type Period = "day" | "week" | "month" | "all";

const PERIOD_LABELS: Record<Period, string> = {
  day:   "Azi",
  week:  "Săpt",
  month: "Lună",
  all:   "Tot",
};

const fmtR = (v: number) =>
  `${v >= 0 ? "+" : ""}${v.toFixed(2)}R`;
const fmtUsd = (v: number) =>
  `${v >= 0 ? "+" : ""}${v.toLocaleString("ro-RO", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} $`;

export function TopMarketsWidget({ source = "all" }: { source?: string }) {
  const [period, setPeriod] = useState<Period>("week");
  const { data: mt5Data, isLoading } = useMt5TopMarkets(period, 5, source);
  const items = mt5Data?.items;

  return (
    <div className="bg-surface-card border border-surface-border rounded-xl p-4 space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-white">Top 5 Piețe</span>
          <InfoTooltip text={
            "Cele mai profitabile 5 piețe după R cumulat, calculate direct din tranzacțiile MT5 (history_deals_get, cont-wide). " +
            "R e recalculat din SL-ul original al ordinului de deschidere."
          } />
        </div>

        {/* Period tabs */}
        <div className="flex gap-1">
          {(Object.keys(PERIOD_LABELS) as Period[]).map((p) => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={`text-[11px] px-2.5 py-1 rounded-lg transition-colors ${
                period === p
                  ? "bg-blue-600 text-white font-medium"
                  : "text-slate-400 hover:text-slate-300 hover:bg-surface-border/30"
              }`}
            >
              {PERIOD_LABELS[p]}
            </button>
          ))}
        </div>
      </div>

      {mt5Data && !mt5Data.connected && (
        <div className="text-[11px] text-warn/80 bg-warn/10 border border-warn/30 rounded-lg px-3 py-2">
          MT5 neconectat — {mt5Data.error ?? "clasamentul nu este disponibil"}.
        </div>
      )}

      {/* Content */}
      {isLoading ? (
        <div className="space-y-2">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-9 rounded-lg bg-surface-border/30 animate-pulse" />
          ))}
        </div>
      ) : !items || items.length === 0 ? (
        <div className="text-center py-4 text-slate-500 text-xs">
          Nicio tranzacție în perioada selectată
        </div>
      ) : (
        <div className="space-y-1.5">
          {items.map((entry, idx) => {
            const rColor  = entry.total_r > 0 ? "text-profit" : entry.total_r < 0 ? "text-loss" : "text-slate-400";
            const rankColors = ["text-yellow-400", "text-slate-300", "text-amber-700"];
            return (
              <div
                key={entry.symbol}
                className="flex items-center gap-3 px-3 py-2 rounded-lg bg-surface hover:bg-surface-border/20 transition-colors"
              >
                {/* Rank */}
                <span className={`text-xs font-bold w-4 text-center flex-shrink-0 ${rankColors[idx] ?? "text-slate-600"}`}>
                  {idx + 1}
                </span>

                {/* Symbol */}
                <span className="text-sm font-semibold text-white w-16 flex-shrink-0">{entry.symbol}</span>

                {/* Trades + Win rate */}
                <div className="flex-1 min-w-0">
                  <span className="text-[11px] text-slate-400">
                    {entry.trades}T · {entry.win_rate.toFixed(0)}% WR
                  </span>
                </div>

                {/* Total R */}
                <span className={`text-sm font-bold font-mono tabular-nums ${rColor} flex-shrink-0`}>
                  {fmtR(entry.total_r)}
                </span>

                {/* P&L USD */}
                {entry.pnl_usd != null && (
                  <span className={`text-[11px] font-mono tabular-nums flex-shrink-0 ${
                    entry.pnl_usd > 0 ? "text-profit/70" : entry.pnl_usd < 0 ? "text-loss/70" : "text-slate-500"
                  }`}>
                    {fmtUsd(entry.pnl_usd)}
                  </span>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
