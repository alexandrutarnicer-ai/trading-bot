import { useState } from "react";
import { useMt5TopMarkets } from "../api/hooks";
import type { TopMarketsSort } from "../api/types";
import { InfoTooltip } from "./InfoTooltip";

type Period = "day" | "week" | "month" | "all";

const PERIOD_LABELS: Record<Period, string> = {
  day:   "Azi",
  week:  "Săpt",
  month: "Lună",
  all:   "Tot",
};

const SORT_LABELS: Partial<Record<TopMarketsSort, string>> = { net: "$ net", r: "R" };

const fmtR = (v: number) =>
  `${v >= 0 ? "+" : ""}${v.toFixed(2)}R`;
const fmtUsd = (v: number) =>
  `${v >= 0 ? "+" : ""}${v.toLocaleString("ro-RO", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} $`;
const tone = (v: number) => (v > 0 ? "text-profit" : v < 0 ? "text-loss" : "text-slate-400");

/**
 * Clasamentul pietelor din MT5 — agregat pe SIMBOL peste toate engine-urile din filtrul de sursa
 * al Dashboard-ului (Toate = tot contul). Definitiile vin din api/trade_stats.py (aceleasi ca
 * restul Dashboard-ului: break-even nu e pierdere, win rate = W / (W + L)).
 */
export function TopMarketsWidget({ source = "all" }: { source?: string }) {
  const [period, setPeriod] = useState<Period>("week");
  const [sort, setSort] = useState<TopMarketsSort>("net");
  const { data: mt5Data, isLoading } = useMt5TopMarkets(period, 5, source, sort);
  const items = mt5Data?.items;
  const totalMarkets = mt5Data?.total_markets ?? items?.length ?? 0;

  const tab = (active: boolean) =>
    `text-[11px] px-2.5 py-1 rounded-lg transition-colors ${
      active
        ? "bg-blue-600 text-white font-medium"
        : "text-slate-400 hover:text-slate-300 hover:bg-surface-border/30"
    }`;

  return (
    <div className="bg-surface-card border border-surface-border rounded-xl p-4 space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-white">Top 5 Piețe</span>
          {totalMarkets > 0 && (
            <span className="text-[10px] text-slate-500">din {totalMarkets}</span>
          )}
          <InfoTooltip text={
            "Toate piețele tranzacționate, agregate pe simbol peste toate engine-urile din filtrul de sursă " +
            "(Toate = tot contul MT5: Custom + AI + Daily + Noisy + manual). " +
            "„$ net” = profit după comision + swap (spread-ul e deja în preț). " +
            "„R” = R cumulat, recalculat din SL-ul original — doar pozițiile cu SL. " +
            "Win rate = câștiguri / (câștiguri + pierderi); break-even nu e pierdere."
          } />
        </div>

        <div className="flex gap-1 items-center">
          {(Object.keys(SORT_LABELS) as TopMarketsSort[]).map((s) => (
            <button key={s} onClick={() => setSort(s)} className={tab(sort === s)}
                    title={s === "net" ? "Sortează după profit net în $" : "Sortează după R cumulat"}>
              {SORT_LABELS[s]}
            </button>
          ))}
          <span className="w-px h-4 bg-surface-border mx-1" />
          {(Object.keys(PERIOD_LABELS) as Period[]).map((p) => (
            <button key={p} onClick={() => setPeriod(p)} className={tab(period === p)}>
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
            const rankColors = ["text-yellow-400", "text-slate-300", "text-amber-700"];
            const hasR = entry.trades_with_r > 0;
            const primary = sort === "r"
              ? (hasR ? fmtR(entry.total_r) : "— R")
              : fmtUsd(entry.pnl_net);
            const primaryTone = sort === "r" ? (hasR ? tone(entry.total_r) : "text-slate-500") : tone(entry.pnl_net);
            const secondary = sort === "r" ? fmtUsd(entry.pnl_net) : (hasR ? fmtR(entry.total_r) : "fără R");
            const secondaryTone = sort === "r" ? tone(entry.pnl_net) : (hasR ? tone(entry.total_r) : "text-slate-600");
            return (
              <div
                key={entry.symbol}
                className="flex items-center gap-3 px-3 py-2 rounded-lg bg-surface hover:bg-surface-border/20 transition-colors"
                title={`Brut ${fmtUsd(entry.pnl_gross)} · comision ${fmtUsd(entry.commission)} · swap ${fmtUsd(entry.swap)}`
                  + (entry.breakeven ? ` · ${entry.breakeven} break-even` : "")}
              >
                <span className={`text-xs font-bold w-4 text-center flex-shrink-0 ${rankColors[idx] ?? "text-slate-600"}`}>
                  {idx + 1}
                </span>
                <span className="text-sm font-semibold text-white w-20 flex-shrink-0 truncate">{entry.symbol}</span>
                <div className="flex-1 min-w-0">
                  <span className="text-[11px] text-slate-400">
                    {entry.trades}T · {entry.wins}W/{entry.losses}L · {entry.win_rate.toFixed(0)}% WR
                  </span>
                </div>
                <span className={`text-sm font-bold font-mono tabular-nums ${primaryTone} flex-shrink-0`}>
                  {primary}
                </span>
                <span className={`text-[11px] font-mono tabular-nums flex-shrink-0 w-16 text-right opacity-70 ${secondaryTone}`}>
                  {secondary}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
