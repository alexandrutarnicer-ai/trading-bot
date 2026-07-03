import { useState } from "react";
import { useCosts, useMt5Stats } from "../api/hooks";
import type { SessionStatus } from "../api/types";
import type { Mt5Status, BotStatus } from "../api/types";
import type { StatsSource } from "../hooks/useStatsSource";
import { SourceToggle } from "./SourceToggle";

interface Props {
  sessions: SessionStatus[];
  mt5?: Mt5Status | null;
  botStatus?: BotStatus | null;
  source: StatsSource;
  onSourceChange: (s: StatsSource) => void;
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

export function TradingStatsPanel({ sessions, mt5, botStatus, source, onSourceChange }: Props) {
  const [expanded, setExpanded] = useState<"signals" | "trades" | null>(null);
  const { data: costsData } = useCosts();
  const { data: mt5Stats } = useMt5Stats();

  const changeSource = (s: StatsSource) => {
    onSourceChange(s);
    if (s === "mt5" && expanded === "trades") setExpanded(null);
  };

  // Sesiunile live (execute=true) + sesiunile care au avut tranzactii reale MT5 (pnl_count>0)
  // dar au fost ulterior oprite (execute=false). MT5 e sursa de adevar — daca pnl_usd exista,
  // trade-ul a fost real, indiferent de setarea curenta a profilului.
  const liveSessions = sessions.filter(x => x.execute || (x.pnl_count != null && x.pnl_count > 0));

  // Semnalele nu au echivalent in MT5 (sunt detectii pre-tranzactie ale botului) — mereu din Bot.
  const totalSignals = liveSessions.reduce((s, x) => s + x.signals_total,    0);
  const signalsToday = liveSessions.reduce((s, x) => s + x.signals_today,    0);
  const signalsYest  = liveSessions.reduce((s, x) => s + x.signals_yesterday, 0);

  // Trades/wins/losses — sursa "Bot" (agregat din outcomes.csv per sesiune).
  const botTotalTrades = liveSessions.reduce((s, x) => s + x.outcomes_total,    0);
  const botTradesToday  = liveSessions.reduce((s, x) => s + x.outcomes_today,    0);
  const botTradesYest   = liveSessions.reduce((s, x) => s + x.outcomes_yesterday, 0);
  const botTotalWins    = liveSessions.reduce((s, x) => s + x.wins,              0);
  const botTotalLosses  = liveSessions.reduce((s, x) => s + x.losses,            0);
  const botWinsToday    = liveSessions.reduce((s, x) => s + (x.wins_today    ?? 0), 0);
  const botWinsYest     = liveSessions.reduce((s, x) => s + (x.wins_yesterday ?? 0), 0);
  const botLossesToday  = liveSessions.reduce((s, x) => s + (x.losses_today    ?? 0), 0);
  const botLossesYest   = liveSessions.reduce((s, x) => s + (x.losses_yesterday ?? 0), 0);
  const botHasPnl       = liveSessions.some(x => x.pnl_usd_today != null || x.pnl_usd_yesterday != null);
  const botPnlToday     = liveSessions.reduce((s, x) => s + (x.pnl_usd_today    ?? 0), 0);
  const botPnlYesterday = liveSessions.reduce((s, x) => s + (x.pnl_usd_yesterday ?? 0), 0);
  const botPnlTracked   = liveSessions.reduce((s, x) => s + (x.pnl_count ?? 0), 0);
  const costItems       = costsData?.items ?? [];
  const botCommission   = costItems.reduce((s, x) => s + x.commission_usd, 0);
  const botSwap         = costItems.reduce((s, x) => s + x.swap_usd, 0);
  const botCostBroker   = costItems.length > 0
    ? Math.round((botCommission + botSwap) * 100) / 100
    : null;

  // Trades/wins/losses — sursa "MT5" (calculate direct din history_deals_get, independent de bot).
  const mt5Connected      = mt5Stats?.connected ?? false;
  const mt5TotalTrades    = mt5Stats?.total_trades ?? 0;
  const mt5TradesToday    = mt5Stats?.trades_today ?? 0;
  const mt5TradesYest     = mt5Stats?.trades_yesterday ?? 0;
  const mt5TotalWins      = mt5Stats?.wins ?? 0;
  const mt5TotalLosses    = mt5Stats?.losses ?? 0;
  const mt5WinsToday      = mt5Stats?.wins_today ?? 0;
  const mt5WinsYest       = mt5Stats?.wins_yesterday ?? 0;
  const mt5LossesToday    = mt5Stats?.losses_today ?? 0;
  const mt5LossesYest     = mt5Stats?.losses_yesterday ?? 0;
  const mt5HasPnl         = mt5Connected && (mt5Stats?.pnl_today != null || mt5Stats?.pnl_yesterday != null);
  const mt5PnlToday       = mt5Stats?.pnl_today ?? 0;
  const mt5PnlYesterday   = mt5Stats?.pnl_yesterday ?? 0;
  const mt5Commission     = mt5Stats?.commission_total ?? 0;
  const mt5Swap           = mt5Stats?.swap_total ?? 0;
  const mt5CostBroker     = mt5Connected && (mt5Stats?.commission_total != null || mt5Stats?.swap_total != null)
    ? Math.round((mt5Commission + mt5Swap) * 100) / 100
    : null;

  const usingMt5 = source === "mt5";

  const totalTrades = usingMt5 ? mt5TotalTrades : botTotalTrades;
  const tradesToday  = usingMt5 ? mt5TradesToday : botTradesToday;
  const tradesYest   = usingMt5 ? mt5TradesYest  : botTradesYest;
  const totalWins    = usingMt5 ? mt5TotalWins   : botTotalWins;
  const totalLosses  = usingMt5 ? mt5TotalLosses : botTotalLosses;
  const winsToday    = usingMt5 ? mt5WinsToday   : botWinsToday;
  const winsYest     = usingMt5 ? mt5WinsYest    : botWinsYest;
  const lossesToday  = usingMt5 ? mt5LossesToday : botLossesToday;
  const lossesYest   = usingMt5 ? mt5LossesYest  : botLossesYest;
  const hasPnl       = usingMt5 ? mt5HasPnl      : botHasPnl;
  const pnlToday     = usingMt5 ? mt5PnlToday    : botPnlToday;
  const pnlYesterday = usingMt5 ? mt5PnlYesterday : botPnlYesterday;
  const winRate      = totalWins + totalLosses > 0
    ? Math.round(totalWins / (totalWins + totalLosses) * 100)
    : null;

  // P&L real MT5 (equity - start_balance — sursa de adevar, include tot, independent de toggle)
  const mt5Equity    = mt5?.connected ? mt5.equity : null;
  const startBalance = botStatus?.active_profile_start_balance ?? null;
  const pnlMt5       = mt5Equity != null && startBalance != null
    ? Math.round((mt5Equity - startBalance) * 100) / 100
    : null;

  const totalCommission = usingMt5 ? mt5Commission : botCommission;
  const totalSwap        = usingMt5 ? mt5Swap        : botSwap;
  const costBroker       = usingMt5 ? mt5CostBroker  : botCostBroker;
  const pnlTracked       = usingMt5 ? mt5TotalTrades : botPnlTracked;

  const fmtUsd = (v: number) =>
    `${v >= 0 ? "+" : ""}${v.toLocaleString("ro-RO", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} $`;

  const toggle = (key: "signals" | "trades") =>
    setExpanded(prev => (prev === key ? null : key));

  return (
    <div className="space-y-2">
      <SourceToggle source={source} onChange={changeSource} />

      {usingMt5 && !mt5Connected && (
        <div className="text-[11px] text-warn/80 bg-warn/10 border border-warn/30 rounded-lg px-3 py-1.5">
          MT5 neconectat — {mt5Stats?.error ?? "statisticile directe nu sunt disponibile"}. Comută pe „Bot" pentru date din outcomes.csv.
        </div>
      )}

      {/* Stat cards row */}
      <div className="flex gap-2 flex-wrap">
        <StatCard
          label="Total Semnale"
          value={totalSignals}
          today={signalsToday}
          yesterday={signalsYest}
          sub={usingMt5 ? "mereu din Bot" : undefined}
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
          onClick={usingMt5 ? undefined : () => toggle("trades")}
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
                  title={`Comisioane: ${fmtUsd(totalCommission)} · Swap: ${fmtUsd(totalSwap)}. Sursă: ${usingMt5 ? "MT5 direct (history_deals_get)" : "outcomes.csv"} — ${pnlTracked} trades.`}
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
