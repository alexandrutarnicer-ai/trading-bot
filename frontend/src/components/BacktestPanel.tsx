import { useState, useEffect, useRef } from "react";
import {
  useRunBacktest, useBacktestJob,
  useCheckData, useStartDownload, useDownloadJob,
  useBacktestHistory, useSaveBacktestHistory, useDeleteBacktestHistory,
} from "../api/hooks";
import { InfoTooltip } from "./InfoTooltip";
import type { BacktestResult, BacktestHistoryEntry, DataCheckResult, ProfileSession } from "../api/types";

interface Props {
  session: ProfileSession;
}

type Range = "1y" | "3y" | "all" | "custom";

const RANGE_LABELS: Record<Range, string> = {
  "1y": "1 An", "3y": "3 Ani", "all": "Tot", "custom": "Custom",
};

const BACKTEST_INFO =
  "Backtest rulează pe date CSV istorice (offline, nu live). " +
  "Split train/test la 70%/30% din tranzacții — nu din timp — " +
  "pentru a evita bias-ul pe perioade scurte. " +
  "Interpretează expectancy pozitiv pe TEST ca semnal real. " +
  "Necesită fișiere CSV în data/ — folosește butonul de descărcare dacă lipsesc.";

type Phase =
  | "idle"
  | "checking"
  | "needs_download"
  | "downloading"
  | "download_done"
  | "running"
  | "done"
  | "error";

export function BacktestPanel({ session }: Props) {
  const [phase, setPhase]       = useState<Phase>("idle");
  const [range, setRange]       = useState<Range>("all");
  const [startBalance, setStartBalance] = useState(1000);
  const [marketAllocations, setMarketAllocations] = useState<Record<string, number>>({});
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo]     = useState("");
  const [checkResult, setCheckResult] = useState<DataCheckResult | null>(null);
  const [btJobId, setBtJobId]   = useState<string | null>(null);
  const [dlJobId, setDlJobId]   = useState<string | null>(null);
  const [phaseError, setPhaseError] = useState<string | null>(null);
  const [showHistory, setShowHistory] = useState(false);

  const startBalanceRef = useRef(startBalance);
  startBalanceRef.current = startBalance;

  const checkData   = useCheckData();
  const startDl     = useStartDownload();
  const runBt       = useRunBacktest();
  const saveHistory = useSaveBacktestHistory();
  const delHistory  = useDeleteBacktestHistory();

  const { data: dlJob }      = useDownloadJob(dlJobId);
  const { data: btJob }      = useBacktestJob(btJobId);
  const { data: historyData } = useBacktestHistory(session.id);

  // Sync market allocations when markets change (add/remove)
  const marketsKey = session.markets.join(",");
  useEffect(() => {
    const n = session.markets.length;
    if (n === 0) { setMarketAllocations({}); return; }
    setMarketAllocations(prev => {
      const defaultAlloc = startBalanceRef.current / n;
      const next: Record<string, number> = {};
      for (const m of session.markets) {
        next[m] = prev[m] ?? defaultAlloc;
      }
      return next;
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [marketsKey]);

  // Reset all allocations equally when total capital changes
  const handleBalanceChange = (val: number) => {
    setStartBalance(val);
    const n = session.markets.length;
    if (n > 0) {
      const eq = val / n;
      const next: Record<string, number> = {};
      for (const m of session.markets) next[m] = eq;
      setMarketAllocations(next);
    }
  };

  const resetEqual = () => {
    const n = session.markets.length;
    if (n === 0) return;
    const eq = startBalance / n;
    const next: Record<string, number> = {};
    for (const m of session.markets) next[m] = eq;
    setMarketAllocations(next);
  };

  const totalAllocated = Object.values(marketAllocations).reduce((a, b) => a + b, 0);
  const allocationOk   = session.markets.length === 0 || Math.abs(totalAllocated - startBalance) < 1;

  // Sync download job phase
  if (dlJobId && dlJob && phase === "downloading") {
    if (dlJob.status === "done")   setPhase("download_done");
    if (dlJob.status === "error") { setPhaseError(dlJob.error); setPhase("error"); }
  }
  // Sync backtest job phase
  if (btJobId && btJob && phase === "running") {
    if (btJob.status === "done")  setPhase("done");
    if (btJob.status === "error") { setPhaseError(btJob.error as string | null); setPhase("error"); }
  }

  const getDateRange = (): { date_from?: string; date_to?: string } => {
    const offset = (years: number) => {
      const d = new Date(); d.setFullYear(d.getFullYear() - years);
      return d.toISOString().slice(0, 10);
    };
    if (range === "1y") return { date_from: offset(1) };
    if (range === "3y") return { date_from: offset(3) };
    if (range === "custom") return { date_from: dateFrom || undefined, date_to: dateTo || undefined };
    return {};
  };

  const runBacktest = async () => {
    setBtJobId(null);
    setPhase("running");
    try {
      const res = await runBt.mutateAsync({ session, ...getDateRange(), start_balance: startBalance }) as { job_id: string };
      setBtJobId(res.job_id);
    } catch (e: unknown) {
      setPhaseError(e instanceof Error ? e.message : "Eroare");
      setPhase("error");
    }
  };

  const handleRun = async () => {
    if (!session.markets.length) {
      setPhaseError("Adaugă cel puțin o piață în sesiune");
      setPhase("error");
      return;
    }

    setPhase("checking");
    setPhaseError(null);
    setCheckResult(null);

    try {
      const result = await checkData.mutateAsync({
        markets:  session.markets.join(","),
        entry_tf: session.entry_tf,
        trend_tf: session.trend_tf,
      });
      setCheckResult(result);
      if (result.all_available) {
        await runBacktest();
      } else {
        setPhase("needs_download");
      }
    } catch (e: unknown) {
      setPhaseError(e instanceof Error ? e.message : "Eroare la verificarea datelor");
      setPhase("error");
    }
  };

  const handleDownload = async () => {
    const tfs = [...new Set([session.entry_tf, session.trend_tf])];
    setDlJobId(null);
    setPhase("downloading");
    try {
      const res = await startDl.mutateAsync({ markets: session.markets, timeframes: tfs });
      setDlJobId(res.job_id);
    } catch (e: unknown) {
      setPhaseError(e instanceof Error ? e.message : "Eroare la descărcare");
      setPhase("error");
    }
  };

  const reset = () => {
    setPhase("idle");
    setPhaseError(null);
    setCheckResult(null);
    setBtJobId(null);
    setDlJobId(null);
  };

  const btResults = btJob?.results as BacktestResult | null;

  // Auto-save to history when backtest completes
  useEffect(() => {
    if (phase === "done" && btResults && session.id) {
      saveHistory.mutate({
        session_id:      session.id,
        session_label:   session.label || session.id,
        markets:         btResults.markets ?? session.markets,
        entry_tf:        session.entry_tf,
        trend_tf:        session.trend_tf,
        direction:       session.direction,
        start_balance:   startBalance,
        date_from:       btResults.date_from,
        date_to:         btResults.date_to,
        results:         btResults,
        session_snapshot: {
          pullback_window:  session.pullback_window,
          risk_base:        session.risk_base,
          risk_mid:         session.risk_mid,
          risk_top:         session.risk_top,
          risk_max:         session.risk_max,
          r_base:           session.r_base,
          r_mid:            session.r_mid,
          r_top:            session.r_top,
          r_max:            session.r_max,
          rsi_enabled:      session.rsi_enabled,
          ema_alignment_enabled: session.ema_alignment_enabled,
          body_strength_enabled: session.body_strength_enabled,
        },
      });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase]);

  return (
    <div className="space-y-3">
      {/* Capital + alocare per piata */}
      <div className="bg-surface-border/20 rounded-lg p-3 space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-xs text-slate-400">Capital simulat</span>
          <div className="flex items-center gap-1.5">
            <input
              type="number" min={100} step={100}
              value={startBalance}
              onChange={(e) => handleBalanceChange(parseFloat(e.target.value) || 1000)}
              className="w-24 bg-surface border border-surface-border rounded px-2 py-1 text-xs text-white text-right font-mono focus:outline-none focus:border-blue-500"
            />
            <span className="text-xs text-slate-500">USD</span>
          </div>
        </div>

        {session.markets.length > 0 && (
          <div className="border-t border-surface-border/40 pt-2 space-y-1.5">
            <div className="flex items-center justify-between mb-1">
              <span className="text-[10px] text-slate-600 uppercase tracking-wider">Alocare per piată</span>
              <button
                onClick={resetEqual}
                className="text-[10px] text-slate-500 hover:text-slate-300 underline transition-colors"
              >
                = Egal
              </button>
            </div>
            {session.markets.map((m) => {
              const alloc = marketAllocations[m] ?? (startBalance / session.markets.length);
              const pct   = startBalance > 0 ? (alloc / startBalance * 100).toFixed(0) : "0";
              return (
                <div key={m} className="flex items-center gap-2">
                  <span className="text-xs text-slate-400 w-20 flex-shrink-0 font-mono">{m}</span>
                  <input
                    type="number" min={0} step={50}
                    value={Math.round(alloc)}
                    onChange={(e) => setMarketAllocations(prev => ({
                      ...prev, [m]: parseFloat(e.target.value) || 0,
                    }))}
                    className="w-20 bg-surface border border-surface-border rounded px-2 py-1 text-xs text-right font-mono text-white focus:outline-none focus:border-blue-500"
                  />
                  <span className="text-xs text-slate-500">USD</span>
                  <span className="text-xs text-slate-600 ml-auto">{pct}%</span>
                </div>
              );
            })}
            <div className="border-t border-surface-border/40 pt-1.5 flex justify-between text-xs">
              <span className="text-slate-500">Total alocat</span>
              <span className={`font-mono ${allocationOk ? "text-slate-400" : "text-warn"}`}>
                {totalAllocated.toLocaleString("ro-RO", { maximumFractionDigits: 0 })}
                {" / "}
                {startBalance.toLocaleString("ro-RO", { maximumFractionDigits: 0 })} USD
                {!allocationOk && " ⚠"}
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Range selector */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-xs text-slate-500">Interval:</span>
        {(["1y", "3y", "all", "custom"] as Range[]).map((r) => (
          <button key={r} onClick={() => setRange(r)}
            className={`text-xs px-2.5 py-1 rounded border transition-colors ${
              range === r
                ? "bg-blue-600 border-blue-500 text-white"
                : "bg-transparent border-surface-border text-slate-400 hover:border-slate-500"
            }`}
          >
            {RANGE_LABELS[r]}
          </button>
        ))}
        <InfoTooltip text={BACKTEST_INFO} wide />
      </div>

      {range === "custom" && (
        <div className="flex items-center gap-3">
          <div className="space-y-0.5">
            <label className="text-xs text-slate-500">De la</label>
            <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)}
              className="bg-surface border border-surface-border rounded px-2 py-1 text-xs text-white focus:outline-none focus:border-blue-500" />
          </div>
          <div className="space-y-0.5">
            <label className="text-xs text-slate-500">Până la</label>
            <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)}
              className="bg-surface border border-surface-border rounded px-2 py-1 text-xs text-white focus:outline-none focus:border-blue-500" />
          </div>
        </div>
      )}

      {/* ── IDLE / DONE ── */}
      {(phase === "idle" || phase === "done") && (
        <button onClick={handleRun}
          className="flex items-center gap-2 px-3 py-1.5 text-xs font-medium rounded-lg bg-blue-600 hover:bg-blue-500 transition-colors">
          ▶ Rulează Backtest
        </button>
      )}

      {/* ── CHECKING ── */}
      {phase === "checking" && (
        <StatusRow icon="⟳" color="text-slate-400" spin>Se verifică datele CSV...</StatusRow>
      )}

      {/* ── NEEDS DOWNLOAD ── */}
      {phase === "needs_download" && checkResult && (
        <div className="bg-surface rounded-xl border border-warn/40 p-4 space-y-3">
          <p className="text-xs font-medium text-warn">
            ⚠ Lipsesc {checkResult.missing.length} fișier(e) CSV necesare pentru backtest
          </p>
          <div className="space-y-1">
            {checkResult.results.map((r) => (
              <div key={`${r.symbol}-${r.tf}`} className="flex items-center gap-2 text-xs">
                <span className={r.exists ? "text-profit" : "text-loss"}>
                  {r.exists ? "✓" : "✗"}
                </span>
                <span className={r.exists ? "text-slate-400" : "text-slate-300"}>
                  {r.symbol}_{r.tf}.csv
                </span>
                {r.exists && r.last_date && (
                  <span className="text-slate-600">până {r.last_date} · {r.bars.toLocaleString()} bare</span>
                )}
              </div>
            ))}
          </div>
          <div className="flex gap-2 pt-1">
            <button onClick={handleDownload}
              className="text-xs px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 transition-colors">
              ⬇ Descarcă date din MT5
            </button>
            <button onClick={reset}
              className="text-xs px-3 py-1.5 rounded-lg border border-surface-border text-slate-400 hover:text-white transition-colors">
              Anulează
            </button>
          </div>
        </div>
      )}

      {/* ── DOWNLOADING ── */}
      {phase === "downloading" && (
        <div className="bg-surface rounded-xl border border-surface-border p-4 space-y-2">
          <StatusRow icon="⟳" color="text-blue-400" spin>
            Se descarcă date din MT5...
          </StatusRow>
          {dlJob?.results && dlJob.results.length > 0 && (
            <div className="space-y-1 mt-2">
              {dlJob.results.map((r, i) => (
                <div key={i} className="flex items-center gap-2 text-xs">
                  <span className={r.success ? "text-profit" : "text-loss"}>
                    {r.success ? "✓" : "✗"}
                  </span>
                  <span className="text-slate-300">{r.symbol} {r.tf}</span>
                  {r.success && <span className="text-slate-500">{r.bars.toLocaleString()} bare</span>}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── DOWNLOAD DONE ── */}
      {phase === "download_done" && dlJob && (
        <div className="bg-surface rounded-xl border border-surface-border p-4 space-y-3">
          <p className="text-xs font-medium text-white">Rezultate descărcare:</p>
          <div className="space-y-1">
            {dlJob.results.map((r, i) => (
              <div key={i} className="flex items-center gap-2 text-xs">
                <span className={r.success ? "text-profit" : "text-warn"}>
                  {r.success ? "✓" : "⚠"}
                </span>
                <span className={r.success ? "text-slate-400" : "text-slate-300"}>
                  {r.symbol} {r.tf}
                </span>
                {r.success
                  ? <span className="text-slate-500">{r.bars.toLocaleString()} bare</span>
                  : <span className="text-slate-500 italic">{r.error}</span>
                }
              </div>
            ))}
          </div>

          {dlJob.any_needs_scroll && (
            <div className="bg-warn/10 border border-warn/30 rounded-lg p-3 space-y-2">
              <p className="text-xs text-warn font-medium">
                📊 Unele simboluri nu au returnat date din MT5
              </p>
              <p className="text-xs text-slate-400">
                MT5 descarcă istoricul lazy — trebuie să forțezi descărcarea manual:
              </p>
              <ol className="text-xs text-slate-300 space-y-1 list-decimal list-inside">
                <li>Deschide MT5 și mergi la simbolul care lipsește</li>
                <li>Deschide graficul pe timeframe-ul cerut (M15 / M30 etc.)</li>
                <li>Derulează graficul <strong>complet spre stânga</strong> până ajungi la primele bare</li>
                <li>Asteaptă să se încarce datele (poate dura câteva secunde)</li>
                <li>Apasă butonul de mai jos pentru a reîncerca descărcarea</li>
              </ol>
              <button onClick={handleDownload}
                className="text-xs px-3 py-1.5 rounded-lg bg-warn/20 border border-warn/50 text-warn hover:bg-warn/30 transition-colors mt-1">
                ↺ Am derulat graficul în MT5, reîncearcă descărcarea
              </button>
            </div>
          )}

          <div className="flex gap-2 pt-1">
            {!dlJob.any_needs_scroll && (
              <button onClick={runBacktest}
                className="text-xs px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 transition-colors">
                ▶ Rulează Backtest
              </button>
            )}
            <button onClick={reset}
              className="text-xs px-3 py-1.5 rounded-lg border border-surface-border text-slate-400 hover:text-white transition-colors">
              Înapoi
            </button>
          </div>
        </div>
      )}

      {/* ── RUNNING ── */}
      {phase === "running" && (
        <StatusRow icon="⟳" color="text-blue-400" spin>Se rulează backtestul...</StatusRow>
      )}

      {/* ── ERROR ── */}
      {phase === "error" && (
        <div className="flex items-center gap-3">
          <span className="text-xs text-loss">{phaseError ?? "Eroare necunoscută"}</span>
          <button onClick={reset} className="text-xs text-slate-500 hover:text-white transition-colors underline">
            Reîncearcă
          </button>
        </div>
      )}

      {/* ── DONE — Results ── */}
      {phase === "done" && btResults && (
        <>
          {btResults.date_from && btResults.date_to && (
            <div className="flex items-center gap-2 text-xs text-slate-500 bg-surface-border/30 rounded-lg px-3 py-1.5 flex-wrap">
              <span>Perioadă testată:</span>
              <span className="text-slate-300 font-medium">{btResults.date_from}</span>
              <span>→</span>
              <span className="text-slate-300 font-medium">{btResults.date_to}</span>
              <span className="text-slate-600">
                ({Math.round((new Date(btResults.date_to).getTime() - new Date(btResults.date_from).getTime()) / (365.25 * 24 * 3600 * 1000) * 10) / 10} ani)
              </span>
              <span className="ml-auto text-slate-600">
                Capital: {startBalance.toLocaleString("ro-RO")} USD
              </span>
            </div>
          )}
          <div className="grid grid-cols-4 gap-3">
            <Stat label="Trades" value={String(btResults.total_trades)}
              tip="Numărul total de tranzacții simulate. Minim recomandat ≥ 30 pentru relevanță statistică." />
            <Stat label="Win Rate" value={`${btResults.win_rate}%`}
              tip="Procentul tranzacțiilor care au atins TP. Strategia rămâne profitabilă chiar la WR 40–45% datorită R/R asimetric." />
            <Stat label="Expectancy"
              value={`${btResults.expectancy >= 0 ? "+" : ""}${btResults.expectancy}R`}
              color={btResults.expectancy >= 0 ? "text-profit" : "text-loss"}
              tip="Câștigul mediu per tranzacție în unități R. Peste 0 = edge pozitiv. Valoarea din TEST este cea relevantă." />
            <Stat label="Max DD" value={`${btResults.max_dd}%`} color="text-warn"
              tip="Scăderea maximă procentuală față de vârful de equity anterior. DD > 40% → reconsideră sizing-ul." />
          </div>
          <div className="flex gap-6 text-xs text-slate-400 border-t border-surface-border pt-2">
            <span className="flex items-center gap-1">
              <span className="text-slate-500">Train</span>
              {btResults.train.trades} trades
              <span className={`ml-1 font-medium ${btResults.train.expectancy >= 0 ? "text-profit" : "text-loss"}`}>
                ({btResults.train.expectancy >= 0 ? "+" : ""}{btResults.train.expectancy}R)
              </span>
              <InfoTooltip text="Primele 70% din tranzacții — pot fi ușor overfitted. Nu este rezultatul relevant." />
            </span>
            <span className="flex items-center gap-1">
              <span className="text-slate-500">Test</span>
              {btResults.test.trades} trades
              <span className={`ml-1 font-medium ${btResults.test.expectancy >= 0 ? "text-profit" : "text-loss"}`}>
                ({btResults.test.expectancy >= 0 ? "+" : ""}{btResults.test.expectancy}R)
              </span>
              <InfoTooltip text="Ultimele 30% din tranzacții (date nevăzute). Acesta este rezultatul care contează." />
            </span>
            <span className="flex items-center gap-1 text-slate-500">
              Split: {btResults.split_date}
              <InfoTooltip text="Data de separare train/test — pe 70% din numărul de tranzacții, nu din timp." />
            </span>
          </div>
          {Object.keys(btResults.per_symbol).length > 0 && (
            <div className="grid grid-cols-3 gap-1.5">
              {Object.entries(btResults.per_symbol).map(([sym, s]) => (
                <div key={sym} className="bg-surface-border/40 rounded px-2 py-1 text-xs">
                  <span className="text-white font-medium">{sym}</span>
                  <span className="text-slate-400 ml-1">{s.trades}t</span>
                  <span className={`ml-1 ${s.expectancy >= 0 ? "text-profit" : "text-loss"}`}>
                    {s.expectancy >= 0 ? "+" : ""}{s.expectancy}R
                  </span>
                </div>
              ))}
            </div>
          )}
          <button onClick={handleRun}
            className="text-xs text-slate-500 hover:text-white underline transition-colors">
            Rulează din nou
          </button>
        </>
      )}

      {/* ── Istoric ── */}
      {historyData && historyData.length > 0 && (
        <div className="border-t border-surface-border/40 pt-3">
          <button
            onClick={() => setShowHistory(v => !v)}
            className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-300 transition-colors"
          >
            <span className={`inline-block transition-transform duration-150 ${showHistory ? "rotate-90" : ""}`}>▶</span>
            Istoric ({historyData.length} rulări)
          </button>

          {showHistory && (
            <div className="mt-2 space-y-1.5 max-h-72 overflow-y-auto pr-1">
              {historyData.map((entry) => (
                <HistoryRow
                  key={entry.id}
                  entry={entry}
                  onDelete={() => delHistory.mutate(entry.id)}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function HistoryRow({ entry, onDelete }: { entry: BacktestHistoryEntry; onDelete: () => void }) {
  const [expanded, setExpanded] = useState(false);
  const r = entry.results;

  const date = entry.timestamp.slice(0, 16).replace("T", " ");
  const period = entry.date_from && entry.date_to
    ? `${entry.date_from.slice(0, 7)} → ${entry.date_to.slice(0, 7)}`
    : null;

  return (
    <div className="bg-surface-border/20 rounded-lg overflow-hidden">
      <div className="flex items-center gap-2 px-2.5 py-1.5 text-xs">
        <button
          onClick={() => setExpanded(v => !v)}
          className="flex items-center gap-2 flex-1 text-left hover:text-white transition-colors text-slate-400"
        >
          <span className={`inline-block transition-transform duration-150 text-[9px] ${expanded ? "rotate-90" : ""}`}>▶</span>
          <span className="text-slate-500 flex-shrink-0">{date}</span>
          <span className="text-slate-300 font-medium truncate">{entry.markets.join(", ")}</span>
          {period && <span className="text-slate-600 flex-shrink-0 hidden sm:inline">{period}</span>}
          <span className={`ml-auto flex-shrink-0 font-mono font-medium ${
            r.expectancy >= 0 ? "text-profit" : "text-loss"
          }`}>
            {r.expectancy >= 0 ? "+" : ""}{r.expectancy}R
          </span>
          <span className="text-slate-500 flex-shrink-0">{r.total_trades}t</span>
        </button>
        <button
          onClick={onDelete}
          className="text-slate-600 hover:text-loss transition-colors flex-shrink-0 px-1"
          title="Șterge"
        >
          ×
        </button>
      </div>

      {expanded && (
        <div className="border-t border-surface-border/30 px-2.5 py-2 space-y-2">
          <div className="grid grid-cols-4 gap-2">
            <MiniStat label="Trades" value={String(r.total_trades)} />
            <MiniStat label="Win Rate" value={`${r.win_rate}%`} />
            <MiniStat
              label="Exp."
              value={`${r.expectancy >= 0 ? "+" : ""}${r.expectancy}R`}
              color={r.expectancy >= 0 ? "text-profit" : "text-loss"}
            />
            <MiniStat label="Max DD" value={`${r.max_dd}%`} color="text-warn" />
          </div>
          <div className="flex gap-4 text-[10px] text-slate-500">
            <span>
              Train: {r.train.trades}t
              <span className={r.train.expectancy >= 0 ? " text-profit" : " text-loss"}>
                {" "}({r.train.expectancy >= 0 ? "+" : ""}{r.train.expectancy}R)
              </span>
            </span>
            <span>
              Test: {r.test.trades}t
              <span className={r.test.expectancy >= 0 ? " text-profit" : " text-loss"}>
                {" "}({r.test.expectancy >= 0 ? "+" : ""}{r.test.expectancy}R)
              </span>
            </span>
            <span className="ml-auto">
              {entry.start_balance.toLocaleString("ro-RO", { maximumFractionDigits: 0 })} USD ·{" "}
              {entry.entry_tf} · {entry.direction}
            </span>
          </div>
          {Object.keys(r.per_symbol ?? {}).length > 0 && (
            <div className="flex gap-2 flex-wrap">
              {Object.entries(r.per_symbol).map(([sym, s]) => (
                <span key={sym} className="text-[10px] text-slate-500">
                  {sym}:{" "}
                  <span className={s.expectancy >= 0 ? "text-profit" : "text-loss"}>
                    {s.expectancy >= 0 ? "+" : ""}{s.expectancy}R
                  </span>
                  <span className="text-slate-600"> ({s.trades}t)</span>
                </span>
              ))}
            </div>
          )}
          {entry.session_snapshot && (
            <div className="text-[10px] text-slate-600 space-y-0.5">
              <div>
                Risk: base {((entry.session_snapshot.risk_base as number) * 100).toFixed(1)}% /
                mid {((entry.session_snapshot.risk_mid as number) * 100).toFixed(1)}% /
                top {((entry.session_snapshot.risk_top as number) * 100).toFixed(1)}% /
                max {((entry.session_snapshot.risk_max as number) * 100).toFixed(1)}%
              </div>
              <div>
                R: {entry.session_snapshot.r_base as number} /
                {entry.session_snapshot.r_mid as number} /
                {entry.session_snapshot.r_top as number} /
                {entry.session_snapshot.r_max as number} ·
                PW: {entry.session_snapshot.pullback_window as number}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function StatusRow({
  icon, color, spin = false, children,
}: {
  icon: string; color: string; spin?: boolean; children: React.ReactNode;
}) {
  return (
    <div className={`flex items-center gap-2 text-xs ${color}`}>
      <span className={spin ? "animate-spin inline-block" : ""}>{icon}</span>
      {children}
    </div>
  );
}

function Stat({ label, value, color, tip }: {
  label: string; value: string; color?: string; tip?: string;
}) {
  return (
    <div className="bg-surface-border/40 rounded-lg p-2 text-center">
      <div className={`text-sm font-bold ${color ?? "text-white"}`}>{value}</div>
      <div className="flex items-center justify-center gap-0.5 text-xs text-slate-500 mt-0.5">
        {label}{tip && <InfoTooltip text={tip} />}
      </div>
    </div>
  );
}

function MiniStat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="bg-surface-border/30 rounded px-2 py-1 text-center">
      <div className={`text-xs font-bold ${color ?? "text-white"}`}>{value}</div>
      <div className="text-[10px] text-slate-500">{label}</div>
    </div>
  );
}
