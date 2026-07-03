import { useState, useEffect } from "react";
import { RefreshCw, TrendingUp, TrendingDown, Minus, Play } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "../api/client";
import { useSessions, useBotStatus, useMt5Status, useWeeklyStats, useMt5WeeklyStats, useFrequencyEstimate, useMt5SessionStats } from "../api/hooks";
import { useStatsSource, type StatsSource } from "../hooks/useStatsSource";
import type { PeriodStats, Mt5PeriodStats, SessionStatus, Mt5SessionStat } from "../api/types";
import { BotStatusBar } from "../components/BotStatusBar";
import { SessionCard } from "../components/SessionCard";
import { SignalFeed } from "../components/SignalFeed";
import { EquityChart } from "../components/EquityChart";
import { TradingStatsPanel } from "../components/TradingStatsPanel";
import { TopMarketsWidget } from "../components/TopMarketsWidget";
import { SourceToggle } from "../components/SourceToggle";

// Vedere unificata pentru randare — R pentru sursa MT5 e recalculat din SL-ul
// original al ordinelor (vezi api/routers/mt5status.py::_fetch_closed_trades),
// null doar daca nicio pozitie din perioada nu are SL rezolvabil.
interface ViewPeriod {
  start: string; end: string;
  trades: number; wins: number; losses: number; win_rate: number;
  pnl_usd: number | null;
  ddValue: number | null; ddUnit: "R" | "USD";
  totalR: number | null;
}
const toView = (p: PeriodStats): ViewPeriod => ({
  start: p.start, end: p.end, trades: p.trades, wins: p.wins, losses: p.losses,
  win_rate: p.win_rate, pnl_usd: p.pnl_usd, ddValue: p.max_dd_r, ddUnit: "R", totalR: p.total_r,
});
const toViewMt5 = (p: Mt5PeriodStats): ViewPeriod => ({
  start: p.start, end: p.end, trades: p.trades, wins: p.wins, losses: p.losses,
  win_rate: p.win_rate, pnl_usd: p.pnl_usd,
  ddValue: p.total_r != null ? p.max_dd_r : p.max_dd_usd,
  ddUnit: p.total_r != null ? "R" : "USD",
  totalR: p.total_r,
});

// Suprapune statisticile MT5-directe pe cardul de sesiune, pastrand SessionCard
// neschimbat — cardul citeste mereu signals_today/signals_total/outcomes_total/wins,
// doar sursa numerelor se schimba. Starea de proces (running/paused/execute) ramane
// mereu din Bot, indiferent de sursa — MT5 nu are conceptul de sesiune pe pauza.
function mergeSessionWithMt5(s: SessionStatus, m: Mt5SessionStat | undefined): SessionStatus {
  if (!m) {
    return {
      ...s,
      signals_today: 0, signals_total: 0, outcomes_total: 0,
      wins: 0, losses: 0, pnl_usd_today: 0, pnl_usd_yesterday: 0,
      last_signal_time: null,
    };
  }
  return {
    ...s,
    signals_today: m.trades_today, signals_total: m.trades_total, outcomes_total: m.trades_total,
    wins: m.wins, losses: m.losses,
    pnl_usd_today: m.pnl_usd_today, pnl_usd_yesterday: m.pnl_usd_yesterday,
    last_signal_time: m.last_trade_time,
  };
}

function WeeklyStatsPanel({ source, onSourceChange }: { source: StatsSource; onSourceChange: (s: StatsSource) => void }) {
  const { data: botData, isLoading: botLoading } = useWeeklyStats();
  const { data: mt5Data, isLoading: mt5Loading } = useMt5WeeklyStats();
  const [period, setPeriod] = useState<"week" | "month">("week");

  const usingMt5 = source === "mt5";
  const isLoading = usingMt5 ? mt5Loading : botLoading;

  function Trend({ curr, pre }: { curr: number; pre: number }) {
    if (pre === 0 && curr === 0) return <Minus size={11} className="text-slate-600" />;
    if (curr > pre) return <TrendingUp  size={11} className="text-profit" />;
    if (curr < pre) return <TrendingDown size={11} className="text-loss" />;
    return <Minus size={11} className="text-slate-600" />;
  }

  const rColor  = (r: number) => r > 0 ? "text-profit" : r < 0 ? "text-loss" : "text-slate-400";
  const fmtR    = (r: number) => `${r >= 0 ? "+" : ""}${r.toFixed(3)}R`;
  const fmtUsd  = (v: number | null | undefined) =>
    v == null ? null : `${v >= 0 ? "+" : ""}${v.toLocaleString("ro-RO", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} USD`;
  const fmtDd   = (v: number | null, unit: "R" | "USD") =>
    !v ? "—" : unit === "R" ? `${v.toFixed(1)}R` : fmtUsd(v);

  if (isLoading) {
    return <div className="h-24 rounded-xl bg-surface-card animate-pulse" />;
  }

  if (usingMt5 && !mt5Data?.connected) {
    return (
      <div className="space-y-2">
        <SourceToggle source={source} onChange={onSourceChange} />
        <div className="text-[11px] text-warn/80 bg-warn/10 border border-warn/30 rounded-lg px-3 py-2">
          MT5 neconectat — {mt5Data?.error ?? "indicele direct nu este disponibil"}. Comută pe „Bot" pentru date din outcomes.csv.
        </div>
      </div>
    );
  }
  if (!usingMt5 && !botData) return null;

  const cur: ViewPeriod  = usingMt5
    ? toViewMt5(period === "week" ? mt5Data!.current_week  : mt5Data!.current_month)
    : toView(period === "week" ? botData!.current_week  : botData!.current_month);
  const prev: ViewPeriod = usingMt5
    ? toViewMt5(period === "week" ? mt5Data!.previous_week : mt5Data!.previous_month)
    : toView(period === "week" ? botData!.previous_week : botData!.previous_month);

  const curLabel  = period === "week" ? "Săpt. curentă"   : "Luna curentă";
  const prevLabel = period === "week" ? "Săpt. anterioară" : "Luna anterioară";

  return (
    <div className="space-y-2">
      <SourceToggle source={source} onChange={onSourceChange} />

      {/* Tab switcher */}
      <div className="flex gap-1 mb-1">
        {(["week", "month"] as const).map(p => (
          <button
            key={p}
            onClick={() => setPeriod(p)}
            className={`text-[10px] px-2.5 py-1 rounded-lg transition-colors ${
              period === p
                ? "bg-blue-500/20 text-blue-400 font-semibold"
                : "text-slate-500 hover:text-slate-300"
            }`}
          >
            {p === "week" ? "Săptămână" : "Lună"}
          </button>
        ))}
      </div>

      {/* Header row */}
      <div className="grid grid-cols-3 text-[10px] text-slate-500 uppercase tracking-wider pb-1">
        <div />
        <div className="text-center">{curLabel}</div>
        <div className="text-center">{prevLabel}</div>
      </div>

      {/* Trades */}
      <div className="grid grid-cols-3 items-center">
        <div className="text-[11px] text-slate-400">Trades</div>
        <div className="text-center flex items-center justify-center gap-1">
          <span className="text-xs font-semibold text-white">{cur.trades}</span>
          <Trend curr={cur.trades} pre={prev.trades} />
        </div>
        <div className="text-center text-[11px] text-slate-500">{prev.trades}</div>
      </div>

      {/* Wins / Losses */}
      <div className="grid grid-cols-3 items-center">
        <div className="text-[11px] text-slate-400">Câștiguri</div>
        <div className="text-center flex items-center justify-center gap-1">
          <span className="text-xs font-semibold text-profit">{cur.wins}</span>
          <Trend curr={cur.wins} pre={prev.wins} />
        </div>
        <div className="text-center text-[11px] text-slate-500">{prev.wins}</div>
      </div>

      <div className="grid grid-cols-3 items-center">
        <div className="text-[11px] text-slate-400">Pierderi</div>
        <div className="text-center flex items-center justify-center gap-1">
          <span className="text-xs font-semibold text-loss">{cur.losses}</span>
          <Trend curr={prev.losses} pre={cur.losses} />
        </div>
        <div className="text-center text-[11px] text-slate-500">{prev.losses}</div>
      </div>

      {/* Win rate */}
      <div className="grid grid-cols-3 items-center">
        <div className="text-[11px] text-slate-400">Win Rate</div>
        <div className="text-center flex items-center justify-center gap-1">
          <span className="text-xs font-semibold text-white">{cur.win_rate.toFixed(1)}%</span>
          <Trend curr={cur.win_rate} pre={prev.win_rate} />
        </div>
        <div className="text-center text-[11px] text-slate-500">{prev.win_rate.toFixed(1)}%</div>
      </div>

      {/* Total R (doar sursa Bot — MT5 nu are conceptul de R) */}
      {cur.totalR != null && (
        <div className="grid grid-cols-3 items-center border-t border-surface-border/40 pt-2">
          <div className="text-[11px] text-slate-400">Total R</div>
          <div className="text-center flex items-center justify-center gap-1">
            <span className={`text-xs font-mono font-semibold ${rColor(cur.totalR)}`}>
              {fmtR(cur.totalR)}
            </span>
            <Trend curr={cur.totalR} pre={prev.totalR ?? 0} />
          </div>
          <div className={`text-center text-[11px] font-mono ${rColor(prev.totalR ?? 0)}`}>
            {fmtR(prev.totalR ?? 0)}
          </div>
        </div>
      )}

      {/* P&L USD (doar daca exista date reale) */}
      {(cur.pnl_usd != null || prev.pnl_usd != null) && (
        <div className={`grid grid-cols-3 items-center ${cur.totalR == null ? "border-t border-surface-border/40 pt-2" : ""}`}>
          <div className="text-[11px] text-slate-400">P&L USD</div>
          <div className="text-center flex items-center justify-center gap-1">
            {cur.pnl_usd != null
              ? <span className={`text-xs font-mono font-semibold ${rColor(cur.pnl_usd)}`}>{fmtUsd(cur.pnl_usd)}</span>
              : <span className="text-xs font-mono text-slate-600">—</span>
            }
            {cur.pnl_usd != null && prev.pnl_usd != null && <Trend curr={cur.pnl_usd} pre={prev.pnl_usd} />}
          </div>
          <div className={`text-center text-[11px] font-mono ${prev.pnl_usd != null ? rColor(prev.pnl_usd) : "text-slate-600"}`}>
            {fmtUsd(prev.pnl_usd) ?? "—"}
          </div>
        </div>
      )}

      {/* -DD max (R pentru Bot, USD pentru MT5) */}
      <div className="grid grid-cols-3 items-center">
        <div className="text-[11px] text-slate-400">-DD max</div>
        <div className="text-center flex items-center justify-center gap-1">
          <span className={`text-xs font-mono font-semibold ${(cur.ddValue ?? 0) < 0 ? "text-loss" : "text-slate-500"}`}>
            {fmtDd(cur.ddValue, cur.ddUnit)}
          </span>
          <Trend curr={-(cur.ddValue ?? 0)} pre={-(prev.ddValue ?? 0)} />
        </div>
        <div className={`text-center text-[11px] font-mono ${(prev.ddValue ?? 0) < 0 ? "text-loss/60" : "text-slate-600"}`}>
          {fmtDd(prev.ddValue, prev.ddUnit)}
        </div>
      </div>

      <div className="text-[10px] text-slate-600 pt-0.5">
        {cur.start} → {cur.end} · anterior: {prev.start} → {prev.end}
      </div>
    </div>
  );
}

export function Dashboard() {
  const { data: sessions, isLoading, dataUpdatedAt } = useSessions();
  const { data: botStatus } = useBotStatus();
  const { data: mt5 } = useMt5Status();
  const { data: freqData } = useFrequencyEstimate(botStatus?.active_profile_id ?? undefined);
  const { data: mt5SessionsData } = useMt5SessionStats();
  const [selectedSession, setSelectedSession] = useState<string>("all");
  const [now, setNow] = useState(Date.now());
  const [runningMissing, setRunningMissing] = useState(false);
  const [runningAll, setRunningAll] = useState(false);
  const [statsSource, setStatsSource] = useStatsSource();
  const qc = useQueryClient();

  const estimatedFreq = (freqData?.per_week != null)
    ? { perWeek: freqData.per_week, perMonth: freqData.per_month ?? 0 }
    : null;

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 5_000);
    return () => clearInterval(id);
  }, []);

  const secsAgo = dataUpdatedAt ? Math.floor((now - dataUpdatedAt) / 1000) : null;
  const updateLabel = secsAgo === null ? null
    : secsAgo < 5  ? "acum"
    : secsAgo < 60 ? `${secsAgo}s`
    : `${Math.floor(secsAgo / 60)}m`;

  const selected = sessions?.find(s => s.id === selectedSession);

  const usingMt5Sessions = statsSource === "mt5";
  const mt5SessionMap = new Map((mt5SessionsData?.items ?? []).map(m => [m.session_id, m]));
  const cardSessions = usingMt5Sessions
    ? sessions?.map(s => mergeSessionWithMt5(s, mt5SessionMap.get(s.id)))
    : sessions;

  function refresh() {
    qc.invalidateQueries();
  }

  async function runAllBacktests() {
    if (runningAll || runningMissing) return;
    setRunningAll(true);
    try {
      const profileId = botStatus?.active_profile_id ?? "standard";
      await apiFetch(`/backtest/run-missing`, {
        method: "POST",
        body: { profile_id: profileId, force: true },
      });
      qc.invalidateQueries({ queryKey: ["frequency-estimate"] });
      qc.invalidateQueries({ queryKey: ["backtest-jobs"] });
      qc.invalidateQueries({ queryKey: ["download-jobs"] });
    } catch (e) {
      console.error("run-all failed", e);
    } finally {
      setRunningAll(false);
    }
  }

  async function runMissingBacktests(onDone?: () => void) {
    if (runningMissing) return;
    setRunningMissing(true);
    try {
      const profileId = botStatus?.active_profile_id ?? "standard";
      await apiFetch(`/backtest/run-missing`, {
        method: "POST",
        body: { profile_id: profileId },
      });
      qc.invalidateQueries({ queryKey: ["frequency-estimate"] });
      qc.invalidateQueries({ queryKey: ["backtest-jobs"] });
      qc.invalidateQueries({ queryKey: ["download-jobs"] });
      if (onDone) onDone();
    } catch (e) {
      console.error("run-missing failed", e);
    } finally {
      setRunningMissing(false);
    }
  }

  const profileLabel = botStatus?.active_profile_name ?? "Standard";

  return (
    <div className="p-4 md:p-6 space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between gap-4">
        {/* Stanga: profil + cont MT5 */}
        <div className="flex items-center gap-4 flex-wrap">
          <span className="text-sm font-semibold text-white">{profileLabel} Profile</span>
          {mt5?.connected && (
            <div className="flex items-center gap-3 text-xs text-slate-400 bg-surface-card border border-surface-border rounded-lg px-3 py-1.5">
              <span className="text-slate-500">Cont</span>
              <span className="font-mono text-white">{mt5.account}</span>
              {mt5.server && <span className="text-slate-600">· {mt5.server}</span>}
              <span className="w-px h-3 bg-surface-border" />
              <span className="text-slate-500">Balance</span>
              <span className="font-mono text-white font-medium">
                {mt5.balance?.toLocaleString("ro-RO", { maximumFractionDigits: 2 })} {mt5.currency}
              </span>
              <span className="text-slate-500">Equity</span>
              <span className={`font-mono font-medium ${
                mt5.equity !== null && mt5.balance !== null
                  ? mt5.equity >= mt5.balance ? "text-profit" : "text-loss"
                  : "text-white"
              }`}>
                {mt5.equity?.toLocaleString("ro-RO", { maximumFractionDigits: 2 })} {mt5.currency}
              </span>
            </div>
          )}
          {mt5 && !mt5.connected && (
            <span className="text-[10px] text-slate-600 bg-surface-card border border-surface-border rounded px-2 py-1">
              MT5 deconectat
            </span>
          )}
        </div>

        {/* Dreapta: bot status + timer + refresh */}
        <div className="flex items-center gap-3 flex-shrink-0">
          <BotStatusBar />
          {updateLabel && (
            <span className="text-[10px] text-slate-600 tabular-nums">
              actualizat {updateLabel}
            </span>
          )}
          <button
            onClick={refresh}
            className="p-2 rounded-lg bg-surface-card border border-surface-border text-slate-400 hover:text-white transition-colors"
            title="Reîncarcă datele"
          >
            <RefreshCw size={14} />
          </button>
        </div>
      </div>

      {/* Banner AutoTrading dezactivat */}
      {mt5?.connected && mt5.algo_trading_enabled === false && (
        <div className="flex items-center gap-3 bg-warn/10 border border-warn/40 rounded-xl px-4 py-3">
          <span className="text-warn text-lg leading-none">⚠</span>
          <div>
            <p className="text-sm font-semibold text-warn">Algo Trading dezactivat în MT5!</p>
            <p className="text-xs text-warn/70 mt-0.5">
              Semnalele sunt detectate dar ordinele <strong>nu vor fi plasate</strong>.
              Activează butonul „Algo Trading" din bara de sus a MetaTrader 5.
            </p>
          </div>
        </div>
      )}

      {/* Frecventa estimata trades */}
      {(() => {
        const missing = freqData?.missing ?? [];
        const missingTooltip = missing.length > 0
          ? missing.map(m => `${m.id}: ${m.markets.join(", ")}`).join("\n")
          : "";
        const avgDD = freqData?.avg_max_dd ?? null;
        return (
          <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-[10px] text-slate-600 uppercase tracking-wider">Frecvență estimată</span>
            <button
              onClick={runAllBacktests}
              disabled={runningAll || runningMissing}
              title="Rerulează backtestele pentru toate sesiunile active (actualizează estimările)"
              className="flex items-center gap-1.5 text-[10px] text-slate-500 hover:text-blue-400 disabled:opacity-40 transition-colors"
            >
              <RefreshCw size={11} className={runningAll ? "animate-spin text-blue-400" : ""} />
              {runningAll ? "Se recalculează..." : "Recalculează toate"}
            </button>
          </div>
          <div className="grid grid-cols-3 gap-3">
            {/* Card săptămână */}
            <div className="bg-surface-card rounded-xl border border-surface-border px-5 py-3 flex items-center justify-between gap-4">
              <div>
                <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Estimat / săptămână</p>
                {estimatedFreq
                  ? <p className="text-2xl font-bold font-mono text-white">~{estimatedFreq.perWeek.toFixed(1)} <span className="text-sm font-normal text-slate-400">trades</span></p>
                  : <p className="text-2xl font-bold font-mono text-slate-600">—</p>
                }
              </div>
              {missing.length > 0 && (
                <button
                  onClick={() => runMissingBacktests()}
                  disabled={runningMissing}
                  title={`${missing.length} sesiuni fără backtest:\n${missingTooltip}\n\nClick pentru a rula backtestele automat`}
                  className="flex-shrink-0 flex items-center gap-1.5 bg-warn/10 border border-warn/30 rounded-lg px-2.5 py-1.5 hover:bg-warn/20 transition-colors disabled:opacity-50"
                >
                  {runningMissing
                    ? <span className="text-warn text-[10px]">Se calculează...</span>
                    : <>
                        <Play size={10} className="text-warn fill-warn" />
                        <span className="text-warn text-xs font-bold">{missing.length}</span>
                        <span className="text-warn/70 text-[10px]">fără date</span>
                      </>
                  }
                </button>
              )}
            </div>
            {/* Card lună */}
            <div className="bg-surface-card rounded-xl border border-surface-border px-5 py-3 flex items-center justify-between gap-4">
              <div>
                <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Estimat / lună</p>
                {estimatedFreq
                  ? <p className="text-2xl font-bold font-mono text-white">~{estimatedFreq.perMonth.toFixed(0)} <span className="text-sm font-normal text-slate-400">trades</span></p>
                  : <p className="text-2xl font-bold font-mono text-slate-600">—</p>
                }
              </div>
              {missing.length > 0 && (
                <div className="flex-shrink-0 text-[10px] text-slate-600 text-right leading-tight max-w-[120px]">
                  {missing.map(m => m.markets[0]).join(", ")}
                </div>
              )}
            </div>
            {/* Card -DD% estimat */}
            <div className="bg-surface-card rounded-xl border border-surface-border px-5 py-3">
              <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">-DD% mediu estimat</p>
              {avgDD != null
                ? <>
                    <p className={`text-2xl font-bold font-mono ${avgDD < 0 ? "text-loss" : "text-slate-400"}`}>
                      {avgDD.toFixed(1)}%
                    </p>
                    <p className="text-[10px] text-slate-600 mt-0.5">din backteste active</p>
                  </>
                : <p className="text-2xl font-bold font-mono text-slate-600">—</p>
              }
            </div>
          </div>
          </div>
        );
      })()}

      {/* Sessions grid */}
      <div>
        <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
          <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
            Sesiuni active
          </h2>
          <SourceToggle source={statsSource} onChange={setStatsSource} />
        </div>
        {usingMt5Sessions && mt5SessionsData && !mt5SessionsData.connected && (
          <div className="text-[11px] text-warn/80 bg-warn/10 border border-warn/30 rounded-lg px-3 py-2 mb-3">
            MT5 neconectat — {mt5SessionsData.error ?? "statisticile directe pe sesiune nu sunt disponibile"}. Comută pe „Bot" pentru date din outcomes.csv.
          </div>
        )}
        {isLoading ? (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
            {[...Array(6)].map((_, i) => (
              <div key={i} className="h-40 rounded-xl bg-surface-card animate-pulse" />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
            {cardSessions?.map(s => (
              <SessionCard
                key={s.id}
                session={s}
                selected={s.id === selectedSession}
                onClick={() => setSelectedSession(s.id)}
              />
            ))}
          </div>
        )}
      </div>

      {/* Bottom two columns */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Signal feed */}
        <div className="bg-surface-card rounded-xl border border-surface-border p-4">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-white">
              {statsSource === "mt5"
                ? (selectedSession === "all" ? "Tranzacții MT5 — Toate sesiunile" : `Tranzacții MT5 — ${selected?.label ?? "—"}`)
                : (selectedSession === "all" ? "Semnale — Toate sesiunile" : `Semnale — ${selected?.label ?? "—"}`)}
            </h2>
            <div className="flex gap-1 flex-wrap justify-end">
              <button
                onClick={() => setSelectedSession("all")}
                className={`text-[10px] px-2 py-0.5 rounded transition-colors font-medium ${
                  selectedSession === "all"
                    ? "bg-blue-500/20 text-blue-400"
                    : "text-slate-500 hover:text-slate-300"
                }`}
              >
                ALL
              </button>
              {sessions?.map(s => (
                <button
                  key={s.id}
                  onClick={() => setSelectedSession(s.id)}
                  className={`text-[10px] px-2 py-0.5 rounded transition-colors ${
                    s.id === selectedSession
                      ? "bg-blue-500/20 text-blue-400"
                      : "text-slate-500 hover:text-slate-300"
                  }`}
                >
                  {s.id.replace("session", "S")}
                </button>
              ))}
            </div>
          </div>
          <SignalFeed
            sessionId={selectedSession}
            balanceUsd={mt5?.connected ? mt5.balance : null}
            capitalPct={selectedSession === "all" ? undefined : selected?.capital_pct}
            source={statsSource}
            symbol={selectedSession === "all" ? undefined : selected?.markets[0]}
          />
        </div>

        {/* Equity chart + stats */}
        <div className="space-y-4">
          <div className="bg-surface-card rounded-xl border border-surface-border p-4">
            <h2 className="text-sm font-semibold text-white mb-4">Performanță</h2>
            <EquityChart source={statsSource} onSourceChange={setStatsSource} />
          </div>

          {/* Trading stats */}
          <div className="bg-surface-card rounded-xl border border-surface-border p-4">
            <h2 className="text-sm font-semibold text-white mb-3">Statistici</h2>
            {sessions && sessions.length > 0
              ? <TradingStatsPanel
                  sessions={sessions}
                  mt5={mt5}
                  botStatus={botStatus}
                  source={statsSource}
                  onSourceChange={setStatsSource}
                />
              : <div className="text-xs text-slate-500 text-center py-4">Nicio sesiune activă</div>
            }
          </div>

          {/* Weekly index */}
          <div className="bg-surface-card rounded-xl border border-surface-border p-4">
            <h2 className="text-sm font-semibold text-white mb-3">Indice Săptămânal</h2>
            <WeeklyStatsPanel source={statsSource} onSourceChange={setStatsSource} />
          </div>

          {/* Top 5 piete */}
          <TopMarketsWidget source={statsSource} onSourceChange={setStatsSource} />
        </div>
      </div>
    </div>
  );
}
