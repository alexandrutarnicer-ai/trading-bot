import { useState } from "react";
import { useCosts } from "../api/hooks";
import type { SessionStatus } from "../api/types";
import type { Mt5Status, BotStatus } from "../api/types";

interface Props {
  sessions: SessionStatus[];
  mt5?: Mt5Status | null;
  botStatus?: BotStatus | null;
}

function TodayYest({ today, yesterday }: { today: number; yesterday: number }) {
  if (today === 0 && yesterday === 0) return null;
  const delta = today - yesterday;
  const arrow = delta > 0 ? "▲" : delta < 0 ? "▼" : null;
  const arrowColor = delta > 0 ? "text-profit" : "text-warn";
  return (
    <div className="flex items-center gap-1 mt-1 text-[10px]">
      <span className="text-slate-400">Azi: <strong className="text-slate-200">{today}</strong></span>
      <span className="text-slate-600">/</span>
      <span className="text-slate-500">Ieri: {yesterday}</span>
      {arrow && <span className={`${arrowColor} font-medium`}>{arrow}</span>}
    </div>
  );
}

interface StatCardProps {
  label: string;
  value: number;
  sub?: string;
  today?: number;
  yesterday?: number;
  accent?: string;
  onClick?: () => void;
  active?: boolean;
}

function StatCard({ label, value, sub, today, yesterday, accent = "text-white", onClick, active }: StatCardProps) {
  return (
    <button
      onClick={onClick}
      className={`flex-1 min-w-0 text-left px-4 py-3 rounded-xl border transition-all
        ${active
          ? "border-blue-500/60 bg-blue-500/10"
          : "border-surface-border bg-surface-card hover:border-slate-600 hover:bg-surface-border/20"
        }
        ${onClick ? "cursor-pointer" : "cursor-default"}
      `}
    >
      <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">{label}</div>
      <div className={`text-2xl font-bold font-mono tabular-nums ${accent}`}>{value.toLocaleString()}</div>
      {sub && <div className="text-[10px] text-slate-600 mt-0.5">{sub}</div>}
      {today !== undefined && yesterday !== undefined && (
        <TodayYest today={today} yesterday={yesterday} />
      )}
    </button>
  );
}

function PnlCard({ todayUsd, yesterdayUsd }: { todayUsd: number; yesterdayUsd: number }) {
  const fmtUsd = (v: number) =>
    `${v >= 0 ? "+" : ""}${v.toLocaleString("ro-RO", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} $`;
  const todayColor   = todayUsd   > 0 ? "text-profit" : todayUsd   < 0 ? "text-loss" : "text-slate-400";
  const yesterdColor = yesterdayUsd > 0 ? "text-profit/70" : yesterdayUsd < 0 ? "text-loss/70" : "text-slate-500";
  return (
    <div className="flex-1 min-w-0 text-left px-4 py-3 rounded-xl border border-surface-border bg-surface-card cursor-default">
      <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">P&L USD</div>
      <div className={`text-2xl font-bold font-mono tabular-nums ${todayColor}`}>
        {fmtUsd(todayUsd)}
      </div>
      <div className={`flex items-center gap-1 mt-1 text-[10px] ${yesterdColor}`}>
        Ieri: <strong>{fmtUsd(yesterdayUsd)}</strong>
      </div>
    </div>
  );
}

export function TradingStatsPanel({ sessions, mt5, botStatus }: Props) {
  const [expanded, setExpanded] = useState<"signals" | "trades" | null>(null);
  const { data: costsData } = useCosts();

  // Sesiunile live (execute=true) + sesiunile care au avut tranzactii reale MT5 (pnl_count>0)
  // dar au fost ulterior oprite (execute=false). MT5 e sursa de adevar — daca pnl_usd exista,
  // trade-ul a fost real, indiferent de setarea curenta a profilului.
  const liveSessions = sessions.filter(x => x.execute || (x.pnl_count != null && x.pnl_count > 0));

  const totalSignals   = liveSessions.reduce((s, x) => s + x.signals_total,    0);
  const totalTrades    = liveSessions.reduce((s, x) => s + x.outcomes_total,   0);
  const signalsToday   = liveSessions.reduce((s, x) => s + x.signals_today,    0);
  const signalsYest    = liveSessions.reduce((s, x) => s + x.signals_yesterday, 0);
  const tradesToday    = liveSessions.reduce((s, x) => s + x.outcomes_today,    0);
  const tradesYest     = liveSessions.reduce((s, x) => s + x.outcomes_yesterday, 0);
  const totalWins      = liveSessions.reduce((s, x) => s + x.wins,              0);
  const totalLosses    = liveSessions.reduce((s, x) => s + x.losses,            0);
  const winsToday      = liveSessions.reduce((s, x) => s + (x.wins_today    ?? 0), 0);
  const winsYest       = liveSessions.reduce((s, x) => s + (x.wins_yesterday ?? 0), 0);
  const lossesToday    = liveSessions.reduce((s, x) => s + (x.losses_today    ?? 0), 0);
  const lossesYest     = liveSessions.reduce((s, x) => s + (x.losses_yesterday ?? 0), 0);
  const winRate        = totalWins + totalLosses > 0
    ? Math.round(totalWins / (totalWins + totalLosses) * 100)
    : null;

  const hasPnl       = liveSessions.some(x => x.pnl_usd_today != null || x.pnl_usd_yesterday != null);
  const pnlToday     = liveSessions.reduce((s, x) => s + (x.pnl_usd_today    ?? 0), 0);
  const pnlYesterday = liveSessions.reduce((s, x) => s + (x.pnl_usd_yesterday ?? 0), 0);

  // P&L real MT5 (equity - start_balance — sursa de adevar, include tot)
  const mt5Equity    = mt5?.connected ? mt5.equity : null;
  const startBalance = botStatus?.active_profile_start_balance ?? null;
  const pnlMt5       = mt5Equity != null && startBalance != null
    ? Math.round((mt5Equity - startBalance) * 100) / 100
    : null;

  // Comisioane + swap din outcomes.csv (via /reports/costs)
  const pnlTracked      = liveSessions.reduce((s, x) => s + (x.pnl_count ?? 0), 0);
  const costItems       = costsData?.items ?? [];
  const totalCommission = costItems.reduce((s, x) => s + x.commission_usd, 0);
  const totalSwap       = costItems.reduce((s, x) => s + x.swap_usd, 0);
  const costBroker      = costItems.length > 0
    ? Math.round((totalCommission + totalSwap) * 100) / 100
    : null;

  const fmtUsd = (v: number) =>
    `${v >= 0 ? "+" : ""}${v.toLocaleString("ro-RO", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} $`;

  const toggle = (key: "signals" | "trades") =>
    setExpanded(prev => (prev === key ? null : key));

  return (
    <div className="space-y-2">
      {/* Stat cards row */}
      <div className="flex gap-2 flex-wrap">
        <StatCard
          label="Total Semnale"
          value={totalSignals}
          today={signalsToday}
          yesterday={signalsYest}
          onClick={() => toggle("signals")}
          active={expanded === "signals"}
        />
        <StatCard
          label="Total Trades"
          value={totalTrades}
          today={tradesToday}
          yesterday={tradesYest}
          sub={winRate !== null ? `${winRate}% win rate` : undefined}
          accent={winRate !== null && winRate >= 50 ? "text-profit" : "text-white"}
          onClick={() => toggle("trades")}
          active={expanded === "trades"}
        />
        <StatCard
          label="Câștiguri"
          value={totalWins}
          today={winsToday}
          yesterday={winsYest}
          accent="text-profit"
        />
        <StatCard
          label="Pierderi"
          value={totalLosses}
          today={lossesToday}
          yesterday={lossesYest}
          accent="text-loss"
        />
        {hasPnl && (
          <PnlCard todayUsd={pnlToday} yesterdayUsd={pnlYesterday} />
        )}
      </div>

      {/* P&L Real MT5 + Comisioane */}
      {(pnlMt5 != null || costBroker != null) && (
        <div className="flex gap-2 flex-wrap pt-1 border-t border-surface-border/40">
          {pnlMt5 != null && (
            <div className="flex-1 min-w-0 px-4 py-2.5 rounded-xl border border-surface-border bg-surface-card">
              <div className="flex items-center gap-1 mb-0.5">
                <span className="text-[10px] text-slate-500 uppercase tracking-wider">P&L Real MT5</span>
                <span
                  className="text-[10px] text-slate-600 cursor-help"
                  title={`Equity curentă MT5 (${mt5Equity?.toFixed(2)} $) minus capitalul de start din profil (${startBalance?.toFixed(2)} $). Include toate tranzacțiile + comision + swap.`}
                >ⓘ</span>
              </div>
              <span className={`text-lg font-bold font-mono tabular-nums ${pnlMt5 > 0 ? "text-profit" : pnlMt5 < 0 ? "text-loss" : "text-slate-400"}`}>
                {fmtUsd(pnlMt5)}
              </span>
              <div className="text-[10px] text-slate-600 mt-0.5">equity MT5 − capital start</div>
            </div>
          )}
          {costBroker != null && (
            <div className="flex-1 min-w-0 px-4 py-2.5 rounded-xl border border-surface-border bg-surface-card">
              <div className="flex items-center gap-1 mb-0.5">
                <span className="text-[10px] text-slate-500 uppercase tracking-wider">Comisioane + Swap</span>
                <span
                  className="text-[10px] text-slate-600 cursor-help"
                  title={`Comisioane: ${fmtUsd(totalCommission)} · Swap: ${fmtUsd(totalSwap)}. Date înregistrate din ${pnlTracked} trades cu date MT5 complete.`}
                >ⓘ</span>
              </div>
              <span className={`text-lg font-bold font-mono tabular-nums ${costBroker > 0 ? "text-profit" : costBroker < 0 ? "text-loss" : "text-slate-400"}`}>
                {fmtUsd(costBroker)}
              </span>
              <div className="text-[10px] text-slate-600 mt-0.5">
                com: {fmtUsd(totalCommission)} · swap: {fmtUsd(totalSwap)}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Expandable breakdown */}
      {expanded && (
        <div className="border border-surface-border rounded-xl overflow-hidden">
          <div className="px-4 py-2 border-b border-surface-border/60 flex items-center justify-between">
            <span className="text-[10px] text-slate-500 uppercase tracking-wider font-medium">
              {expanded === "signals" ? "Semnale per sesiune" : "Trades per sesiune"}
            </span>
            <button onClick={() => setExpanded(null)} className="text-slate-600 hover:text-slate-400 text-xs">✕</button>
          </div>
          <div className="divide-y divide-surface-border/40">
            {sessions.map(s => {
              const val  = expanded === "signals" ? s.signals_total   : s.outcomes_total;
              const tday = expanded === "signals" ? s.signals_today   : s.outcomes_today;
              const tyes = expanded === "signals" ? s.signals_yesterday : s.outcomes_yesterday;
              if (val === 0 && tday === 0) return null;
              return (
                <div key={s.id} className="flex items-center gap-3 px-4 py-2.5">
                  <div className="flex items-center gap-2 min-w-0 flex-1">
                    <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${s.running ? "bg-profit" : "bg-slate-600"}`} />
                    <span className="text-xs text-slate-300 font-medium">{s.label}</span>
                    {!s.execute && <span className="text-[9px] text-slate-500 border border-slate-700 rounded px-1">OBS</span>}
                    <span className="text-[10px] text-slate-600 truncate">{s.markets.join(" · ")}</span>
                  </div>
                  <div className="flex items-center gap-3 text-[10px] text-right flex-shrink-0">
                    <span className="text-slate-300 font-mono tabular-nums text-xs font-medium">{val} total</span>
                    <span className="text-slate-500">
                      Azi: <strong className="text-slate-300">{tday}</strong>
                      <span className="text-slate-600 mx-1">/</span>
                      Ieri: {tyes}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
