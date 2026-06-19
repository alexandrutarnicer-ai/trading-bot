import { useState, useEffect, useRef } from "react";
import {
  useRunBacktest, useBacktestJob,
  useCheckData, useStartDownload, useDownloadJob,
} from "../api/hooks";
import { InfoTooltip } from "./InfoTooltip";
import { MARKET_SPECS, calcOvershoot } from "../marketSpecs";
import type { DataCheckResult, ProfileSession } from "../api/types";

interface Props {
  session: ProfileSession;
  onJobStarted?: () => void;        // navighează la Audit fără să salveze (backtest)
  onSaveAndNavigate?: () => void;   // salvează profilul + navighează la Audit (backtest)
  onDownloadStarted?: () => void;   // navighează la Audit după pornire descărcare
}

type Range = "1y" | "3y" | "5y" | "all" | "custom";

const RANGE_LABELS: Record<Range, string> = {
  "1y": "1 An", "3y": "3 Ani", "5y": "5 Ani", "all": "Tot", "custom": "Custom",
};

const BACKTEST_INFO =
  "Backtest rulează pe date CSV istorice (offline, nu live). " +
  "Split train/test la 70%/30% din tranzacții — nu din timp — " +
  "pentru a evita bias-ul pe perioade scurte.\n\n" +
  "Expectancy: câștigul mediu per tranzacție în unități R (risc per trade). " +
  "Ex: +0.025R = câștig mediu de 2.5% din riscul per trade. " +
  "-0.332R = pierdere medie de 33.2% din risc per trade.\n\n" +
  "Interpretează expectancy pozitiv pe TEST ca semnal real. " +
  "Necesită fișiere CSV în data/ — folosește butonul de descărcare dacă lipsesc.";

type Phase =
  | "idle"
  | "checking"
  | "needs_download"
  | "downloading"
  | "dl_submitted"
  | "download_done"
  | "running"
  | "done"
  | "error"
  | "submitted";

export function BacktestPanel({ session, onJobStarted, onSaveAndNavigate, onDownloadStarted }: Props) {
  const [phase, setPhase]       = useState<Phase>("idle");
  const [range, setRange]       = useState<Range>("5y");
  const [startBalance, setStartBalance] = useState(1000);
  const [marketAllocations, setMarketAllocations] = useState<Record<string, number>>({});
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo]     = useState("");
  const [checkResult, setCheckResult] = useState<DataCheckResult | null>(null);
  const [btJobId, setBtJobId]   = useState<string | null>(null);
  const [dlJobId, setDlJobId]   = useState<string | null>(null);
  const [phaseError, setPhaseError] = useState<string | null>(null);

  const startBalanceRef = useRef(startBalance);
  startBalanceRef.current = startBalance;

  const checkData = useCheckData();
  const startDl   = useStartDownload();
  const runBt     = useRunBacktest();

  const { data: dlJob } = useDownloadJob(dlJobId);
  const { data: btJob } = useBacktestJob(btJobId);

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
  // Sync backtest job phase — doar in modul inline (fara Audit tab)
  if (btJobId && btJob && phase === "running" && !onJobStarted && !onSaveAndNavigate) {
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
    if (range === "5y") return { date_from: offset(5) };
    if (range === "custom") return { date_from: dateFrom || undefined, date_to: dateTo || undefined };
    return {};
  };

  const runBacktest = async () => {
    setBtJobId(null);
    setPhase("running");
    try {
      const res = await runBt.mutateAsync({
        session,
        ...getDateRange(),
        start_balance: startBalance,
        session_snapshot: {
          // Strategie
          pullback_window:            session.pullback_window,
          expire_bars:                session.expire_bars,
          circuit_breaker:            session.circuit_breaker,
          // Ore sesiune
          session_start:              session.session_start,
          session_end:                session.session_end,
          skip_hours:                 session.skip_hours,
          skip_weekdays:              session.skip_weekdays,
          // R-ladder
          r_base:                     session.r_base,
          r_mid:                      session.r_mid,
          r_top:                      session.r_top,
          r_max:                      session.r_max,
          r_mid_threshold:            session.r_mid_threshold,
          r_top_threshold:            session.r_top_threshold,
          r_max_threshold:            session.r_max_threshold,
          // Risk
          risk_base:                  session.risk_base,
          risk_mid:                   session.risk_mid,
          risk_top:                   session.risk_top,
          risk_max:                   session.risk_max,
          // Criterii
          rsi_enabled:                session.rsi_enabled,
          rsi_buy_min:                session.rsi_buy_min,
          rsi_buy_max:                session.rsi_buy_max,
          rsi_sell_min:               session.rsi_sell_min,
          rsi_sell_max:               session.rsi_sell_max,
          ema_alignment_enabled:      session.ema_alignment_enabled,
          body_strength_enabled:      session.body_strength_enabled,
          body_strength_min_atr_ratio: session.body_strength_min_atr_ratio,
          // Capital per piata
          market_allocations:         marketAllocations,
          start_balance:              startBalance,
        },
      }) as { job_id: string };
      setBtJobId(res.job_id);
      // Nu redirectionam automat — afisam starea "submitted" cu butoane de actiune
      setPhase("submitted");
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
    const tfs   = [...new Set([session.entry_tf, session.trend_tf])];
    const label = `${session.id} — ${session.markets.join(" · ")} — ${tfs.join("+")}`;
    setDlJobId(null);
    setPhase("downloading");
    try {
      const res = await startDl.mutateAsync({ markets: session.markets, timeframes: tfs, label });
      setDlJobId(res.job_id);
      setPhase("dl_submitted");
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
              const alloc   = marketAllocations[m] ?? (startBalance / session.markets.length);
              const pct     = startBalance > 0 ? (alloc / startBalance * 100).toFixed(0) : "0";
              const spec    = MARKET_SPECS[m.toUpperCase()];
              const riskPct = session.risk_base ?? session.risk_pct ?? 0.01;
              const over    = spec ? calcOvershoot(alloc, riskPct, spec) : null;
              return (
                <div key={m}>
                  <div className="flex items-center gap-2">
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
                    {over && (
                      <span className={`text-[10px] font-mono font-medium ml-1 ${over.factor >= 8 ? "text-loss" : "text-warn"}`}>
                        ⚠ {over.factor.toFixed(0)}×
                      </span>
                    )}
                  </div>
                  {over && (
                    <div className="text-[10px] text-slate-500 pl-[88px] -mt-0.5 pb-1">
                      lot min {spec!.volMin} → live risc est.{" "}
                      <span className={over.factor >= 8 ? "text-loss/80" : "text-warn/80"}>
                        ~${over.actualRisk.toFixed(0)}
                      </span>
                      {" "}vs ${over.intendedRisk.toFixed(2)} intenționat
                    </div>
                  )}
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
        {(["1y", "3y", "5y", "all", "custom"] as Range[]).map((r) => (
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

      {/* ── SUBMITTED — job trimis, ramane pe pagina ── */}
      {phase === "submitted" && (
        <div className="rounded-xl border border-blue-500/30 bg-blue-500/5 p-3 space-y-2.5">
          {/* Status job */}
          <div className="flex items-center gap-2">
            {btJob?.status === "done" ? (
              <span className="text-[11px] font-medium text-profit">✓ Backtest finalizat</span>
            ) : btJob?.status === "error" ? (
              <span className="text-[11px] font-medium text-loss">✗ Backtest eșuat — vezi Audit</span>
            ) : (
              <>
                <span className="w-2 h-2 rounded-full bg-blue-400 animate-pulse flex-shrink-0" />
                <span className="text-[11px] text-blue-400 font-medium">Backtest în progres în Audit...</span>
              </>
            )}
          </div>

          {/* Avertisment modificari nesalvate */}
          {onSaveAndNavigate && (
            <p className="text-[10px] text-slate-500 leading-relaxed">
              Modificările din sesiune sunt <strong className="text-slate-400">nesalvate</strong>.
              Salvează înainte să vizionezi rezultatele, altfel configurația din Audit
              poate diferi de ce ai testat.
            </p>
          )}

          {/* Butoane */}
          <div className="flex flex-wrap gap-2">
            {onSaveAndNavigate && (
              <button
                onClick={onSaveAndNavigate}
                className="text-xs px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 transition-colors font-medium"
              >
                Salvează și mergi la Audit
              </button>
            )}
            {onJobStarted && (
              <button
                onClick={() => { reset(); onJobStarted(); }}
                className="text-xs px-3 py-1.5 rounded-lg border border-surface-border text-slate-400 hover:text-white transition-colors"
              >
                Mergi la Audit fără să salvezi
              </button>
            )}
            <button
              onClick={reset}
              className="text-xs px-3 py-1.5 rounded-lg border border-surface-border text-slate-400 hover:text-white transition-colors"
            >
              Rulează alt backtest
            </button>
          </div>
        </div>
      )}

      {/* ── DL SUBMITTED — descărcare pornita, merge la Audit ── */}
      {phase === "dl_submitted" && (
        <div className="rounded-xl border border-blue-500/30 bg-blue-500/5 p-3 space-y-2.5">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-blue-400 animate-pulse flex-shrink-0" />
            <span className="text-[11px] text-blue-400 font-medium">Descărcarea datelor rulează în Audit...</span>
          </div>

          {onSaveAndNavigate && (
            <p className="text-[10px] text-slate-500 leading-relaxed">
              Modificările din sesiune sunt <strong className="text-slate-400">nesalvate</strong>.
              Salvează înainte să vizionezi rezultatele.
            </p>
          )}

          <div className="flex flex-wrap gap-2">
            {onSaveAndNavigate && (
              <button
                onClick={onSaveAndNavigate}
                className="text-xs px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 transition-colors font-medium"
              >
                Salvează și mergi la Audit
              </button>
            )}
            {onDownloadStarted && (
              <button
                onClick={() => { reset(); onDownloadStarted(); }}
                className="text-xs px-3 py-1.5 rounded-lg border border-surface-border text-slate-400 hover:text-white transition-colors"
              >
                {onSaveAndNavigate ? "Mergi fără să salvezi" : "Mergi la Audit"}
              </button>
            )}
            <button
              onClick={reset}
              className="text-xs px-3 py-1.5 rounded-lg border border-surface-border text-slate-400 hover:text-white transition-colors"
            >
              Înapoi
            </button>
          </div>
        </div>
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

