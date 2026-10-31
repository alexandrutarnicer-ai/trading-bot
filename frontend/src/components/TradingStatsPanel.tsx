import { useState } from "react";
import { useMt5Stats } from "../api/hooks";
import type { SessionStatus } from "../api/types";
import type { Mt5Status, BotStatus } from "../api/types";

interface Props {
  sessions: SessionStatus[];
  mt5?: Mt5Status | null;
  botStatus?: BotStatus | null;
  source?: string;                 // filtrul Dashboard (all/bot/ai/manual)
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

const sum2 = (a?: number | null, b?: number | null): number | null =>
  a == null && b == null ? null : Math.round(((a ?? 0) + (b ?? 0)) * 100) / 100;

export function TradingStatsPanel({ sessions, mt5, botStatus, source = "all" }: Props) {
  const [expanded, setExpanded] = useState(false);
  const { data: mt5Stats } = useMt5Stats(source);

  // Semnalele nu au echivalent in MT5 (sunt detectii pre-tranzactie ale Custom Engine)
  // — singura statistica luata din jurnalul botului. Doar sesiunile live.
  const liveSessions = sessions.filter(x => x.execute);
  const totalSignals = liveSessions.reduce((s, x) => s + x.signals_total,     0);
  const signalsToday = liveSessions.reduce((s, x) => s + x.signals_today,     0);
  const signalsYest  = liveSessions.reduce((s, x) => s + x.signals_yesterday, 0);

  // Trades / wins / losses / P&L / costuri — exclusiv MT5 (history_deals_get, cont-wide).
  const connected   = mt5Stats?.connected ?? false;
  const totalTrades = mt5Stats?.total_trades ?? 0;
  const totalWins   = mt5Stats?.wins ?? 0;
  const totalLosses = mt5Stats?.losses ?? 0;
  const hasPnl      = connected && (mt5Stats?.pnl_today != null || mt5Stats?.pnl_yesterday != null);
  const totalCommission = mt5Stats?.commission_total ?? 0;
  const totalSwap       = mt5Stats?.swap_total ?? 0;
  const costBroker = connected ? sum2(mt5Stats?.commission_total, mt5Stats?.swap_total) : null;
  const costToday  = connected ? sum2(mt5Stats?.commission_today, mt5Stats?.swap_today) : null;
  const costYest   = connected ? sum2(mt5Stats?.commission_yesterday, mt5Stats?.swap_yesterday) : null;
  const winRate = totalWins + totalLosses > 0
    ? Math.round(totalWins / (totalWins + totalLosses) * 100)
    : null;

  // P&L real MT5 (equity - start_balance — include tot)
  const mt5Equity    = mt5?.connected ? mt5.equity : null;
  const startBalance = botStatus?.active_profile_start_balance ?? null;
  const pnlMt5       = mt5Equity != null && startBalance != null
    ? Math.round((mt5Equity - startBalance) * 100) / 100
    : null;

  const fmtUsd = (v: number) =>
    `${v >= 0 ? "+" : ""}${v.toLocaleString("ro-RO", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} $`;

  return (
    <div className="space-y-2">
      {mt5Stats && !connected && (
        <div className="text-[11px] text-warn/80 bg-warn/10 border border-warn/30 rounded-lg px-3 py-1.5">
          MT5 neconectat — {mt5Stats.error ?? "statisticile de tranzacționare nu sunt disponibile"}.
        </div>
      )}

      {/* Stat cards row */}
      <div className="flex gap-2 flex-wrap">
        <StatCard
          label="Total Semnale"
          value={totalSignals}
          today={signalsToday}
          yesterday={signalsYest}
          sub="detectate de Custom Engine"
          onClick={() => setExpanded(e => !e)}
          active={expanded}
        />
        <StatCard
          label="Total Trades"
          value={totalTrades}
          today={mt5Stats?.trades_today ?? 0}
          yesterday={mt5Stats?.trades_yesterday ?? 0}
          sub={[
            winRate !== null ? `${winRate}% win rate` : null,
            mt5Stats?.by_source ? `bot ${mt5Stats.by_source.bot} · AI ${mt5Stats.by_source.ai}${mt5Stats.by_source.manual ? ` · man ${mt5Stats.by_source.manual}` : ""}` : null,
          ].filter(Boolean).join(" · ") || undefined}
          accent={winRate !== null && winRate >= 50 ? "text-profit" : "text-white"}
        />
        <StatCard
          label="Câștiguri"
          value={totalWins}
          today={mt5Stats?.wins_today ?? 0}
          yesterday={mt5Stats?.wins_yesterday ?? 0}
          accent="text-profit"
        />
        <StatCard
          label="Pierderi"
          value={totalLosses}
          today={mt5Stats?.losses_today ?? 0}
          yesterday={mt5Stats?.losses_yesterday ?? 0}
          accent="text-loss"
        />
        {hasPnl && (
          <PnlCard todayUsd={mt5Stats?.pnl_today ?? 0} yesterdayUsd={mt5Stats?.pnl_yesterday ?? 0} />
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
              <div className="text-[10px] text-slate-600 mt-0.5">
                equity MT5 − capital start{source !== "all" && " · tot contul (nu depinde de filtru)"}
              </div>
            </div>
          )}
          {costBroker != null && (
            <div className="flex-1 min-w-0 px-4 py-2.5 rounded-xl border border-surface-border bg-surface-card">
              <div className="flex items-center gap-1 mb-0.5">
                <span className="text-[10px] text-slate-500 uppercase tracking-wider">Comisioane + Swap</span>
                <span
                  className="text-[10px] text-slate-600 cursor-help"
                  title={`Comisioane: ${fmtUsd(totalCommission)} · Swap: ${fmtUsd(totalSwap)}. Sursă: MT5 (cont-wide — Bot + AI + manual) — ${totalTrades} trades.`}
                >ⓘ</span>
              </div>
              <span className={`text-lg font-bold font-mono tabular-nums ${costBroker > 0 ? "text-profit" : costBroker < 0 ? "text-loss" : "text-slate-400"}`}>
                {fmtUsd(costBroker)}
              </span>
              <div className="text-[10px] text-slate-600 mt-0.5">
                com: {fmtUsd(totalCommission)} · swap: {fmtUsd(totalSwap)}
              </div>
              {(costToday != null || costYest != null) && (
                <div className="flex items-center gap-1 mt-1 text-[10px]">
                  <span className="text-slate-400">Azi: <strong className="text-slate-200">{costToday != null ? fmtUsd(costToday) : "—"}</strong></span>
                  <span className="text-slate-600">/</span>
                  <span className="text-slate-500">Ieri: {costYest != null ? fmtUsd(costYest) : "—"}</span>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Semnale per sesiune (jurnalul Custom Engine) */}
      {expanded && (
        <div className="border border-surface-border rounded-xl overflow-hidden">
          <div className="px-4 py-2 border-b border-surface-border/60 flex items-center justify-between">
            <span className="text-[10px] text-slate-500 uppercase tracking-wider font-medium">Semnale per sesiune</span>
            <button onClick={() => setExpanded(false)} className="text-slate-600 hover:text-slate-400 text-xs">✕</button>
          </div>
          <div className="divide-y divide-surface-border/40">
            {sessions.map(s => {
              if (s.signals_total === 0 && s.signals_today === 0) return null;
              return (
                <div key={s.id} className="flex items-center gap-3 px-4 py-2.5">
                  <div className="flex items-center gap-2 min-w-0 flex-1">
                    <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${s.running ? "bg-profit" : "bg-slate-600"}`} />
                    <span className="text-xs text-slate-300 font-medium">{s.label}</span>
                    {!s.execute && <span className="text-[9px] text-slate-500 border border-slate-700 rounded px-1">OBS</span>}
                    <span className="text-[10px] text-slate-600 truncate">{s.markets.join(" · ")}</span>
                  </div>
                  <div className="flex items-center gap-3 text-[10px] text-right flex-shrink-0">
                    <span className="text-slate-300 font-mono tabular-nums text-xs font-medium">{s.signals_total} total</span>
                    <span className="text-slate-500">
                      Azi: <strong className="text-slate-300">{s.signals_today}</strong>
                      <span className="text-slate-600 mx-1">/</span>
                      Ieri: {s.signals_yesterday}
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
