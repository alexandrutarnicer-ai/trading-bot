import { useState, useEffect } from "react";
import { RefreshCw, TrendingUp, TrendingDown, Minus, Play } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "../api/client";
import { useSessions, useBotStatus, useMt5Status, useWeeklyStats, useFrequencyEstimate } from "../api/hooks";
import { BotStatusBar } from "../components/BotStatusBar";
import { SessionCard } from "../components/SessionCard";
import { SignalFeed } from "../components/SignalFeed";
import { EquityChart } from "../components/EquityChart";
import { TradingStatsPanel } from "../components/TradingStatsPanel";

function WeeklyStatsPanel() {
  const { data, isLoading } = useWeeklyStats();

  if (isLoading) {
    return <div className="h-24 rounded-xl bg-surface-card animate-pulse" />;
  }
  if (!data) return null;

  const cur  = data.current_week;
  const prev = data.previous_week;

  function Trend({ curr, pre }: { curr: number; pre: number }) {
    if (pre === 0 && curr === 0) return <Minus size={11} className="text-slate-600" />;
    if (curr > pre) return <TrendingUp  size={11} className="text-profit" />;
    if (curr < pre) return <TrendingDown size={11} className="text-loss" />;
    return <Minus size={11} className="text-slate-600" />;
  }

  const rColor  = (r: number) => r > 0 ? "text-profit" : r < 0 ? "text-loss" : "text-slate-400";
  const fmtR    = (r: number) => `${r >= 0 ? "+" : ""}${r.toFixed(3)}R`;

  return (
    <div className="space-y-2">
      {/* Header row */}
      <div className="grid grid-cols-3 text-[10px] text-slate-500 uppercase tracking-wider pb-1">
        <div />
        <div className="text-center">Săpt. curentă</div>
        <div className="text-center">Săpt. anterioară</div>
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

      {/* Total R */}
      <div className="grid grid-cols-3 items-center border-t border-surface-border/40 pt-2">
        <div className="text-[11px] text-slate-400">Total R</div>
        <div className="text-center flex items-center justify-center gap-1">
          <span className={`text-xs font-mono font-semibold ${rColor(cur.total_r)}`}>
            {fmtR(cur.total_r)}
          </span>
          <Trend curr={cur.total_r} pre={prev.total_r} />
        </div>
        <div className={`text-center text-[11px] font-mono ${rColor(prev.total_r)}`}>
          {fmtR(prev.total_r)}
        </div>
      </div>

      {/* -DD max % */}
      <div className="grid grid-cols-3 items-center">
        <div className="text-[11px] text-slate-400">-DD max</div>
        <div className="text-center flex items-center justify-center gap-1">
          <span className={`text-xs font-mono font-semibold ${(cur.max_dd_r ?? 0) < 0 ? "text-loss" : "text-slate-500"}`}>
            {!(cur.max_dd_r) ? "—" : `${cur.max_dd_r.toFixed(1)}%`}
          </span>
          <Trend curr={-(cur.max_dd_r ?? 0)} pre={-(prev.max_dd_r ?? 0)} />
        </div>
        <div className={`text-center text-[11px] font-mono ${(prev.max_dd_r ?? 0) < 0 ? "text-loss/60" : "text-slate-600"}`}>
          {!(prev.max_dd_r) ? "—" : `${prev.max_dd_r.toFixed(1)}%`}
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
  const [selectedSession, setSelectedSession] = useState<string>("session3");
  const [now, setNow] = useState(Date.now());
  const [runningMissing, setRunningMissing] = useState(false);
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

  function refresh() {
    qc.invalidateQueries();
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
        return (
          <div className="grid grid-cols-2 gap-3">
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
          </div>
        );
      })()}

      {/* Sessions grid */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
            Sesiuni active
          </h2>
        </div>
        {isLoading ? (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
            {[...Array(6)].map((_, i) => (
              <div key={i} className="h-40 rounded-xl bg-surface-card animate-pulse" />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
            {sessions?.map(s => (
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
              Semnale — {selected?.label ?? "—"}
            </h2>
            <div className="flex gap-1">
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
            capitalPct={selected?.capital_pct}
          />
        </div>

        {/* Equity chart + stats */}
        <div className="space-y-4">
          <div className="bg-surface-card rounded-xl border border-surface-border p-4">
            <h2 className="text-sm font-semibold text-white mb-4">Performanță</h2>
            <EquityChart />
          </div>

          {/* Trading stats */}
          <div className="bg-surface-card rounded-xl border border-surface-border p-4">
            <h2 className="text-sm font-semibold text-white mb-3">Statistici</h2>
            {sessions && sessions.length > 0
              ? <TradingStatsPanel sessions={sessions} />
              : <div className="text-xs text-slate-500 text-center py-4">Nicio sesiune activă</div>
            }
          </div>

          {/* Weekly index */}
          <div className="bg-surface-card rounded-xl border border-surface-border p-4">
            <h2 className="text-sm font-semibold text-white mb-3">Indice Săptămânal</h2>
            <WeeklyStatsPanel />
          </div>
        </div>
      </div>
    </div>
  );
}
