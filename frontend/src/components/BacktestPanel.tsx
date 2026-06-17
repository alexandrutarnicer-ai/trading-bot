import { useState } from "react";
import {
  useRunBacktest, useBacktestJob,
  useCheckData, useStartDownload, useDownloadJob,
} from "../api/hooks";
import { InfoTooltip } from "./InfoTooltip";
import type { BacktestResult, DataCheckResult, ProfileSession } from "../api/types";

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
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo]     = useState("");
  const [checkResult, setCheckResult] = useState<DataCheckResult | null>(null);
  const [btJobId, setBtJobId]   = useState<string | null>(null);
  const [dlJobId, setDlJobId]   = useState<string | null>(null);
  const [phaseError, setPhaseError] = useState<string | null>(null);

  const checkData   = useCheckData();
  const startDl     = useStartDownload();
  const runBt       = useRunBacktest();

  const { data: dlJob }  = useDownloadJob(dlJobId);
  const { data: btJob }  = useBacktestJob(btJobId);

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
      const res = await runBt.mutateAsync({ session, ...getDateRange() }) as { job_id: string };
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

  return (
    <div className="space-y-3">
      {/* Range selector — mereu vizibil */}
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

      {/* ── IDLE ── */}
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

      {/* ── RUNNING BACKTEST ── */}
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
          <div className="grid grid-cols-4 gap-3">
            <Stat label="Trades" value={String(btResults.total_trades)} />
            <Stat label="Win Rate" value={`${btResults.win_rate}%`} />
            <Stat label="Expectancy"
              value={`${btResults.expectancy >= 0 ? "+" : ""}${btResults.expectancy}R`}
              color={btResults.expectancy >= 0 ? "text-profit" : "text-loss"} />
            <Stat label="Max DD" value={`${btResults.max_dd}%`} color="text-warn" />
          </div>
          <div className="flex gap-6 text-xs text-slate-400 border-t border-surface-border pt-2">
            <span>
              <span className="text-slate-500">Train </span>
              {btResults.train.trades} trades
              <span className={`ml-1 font-medium ${btResults.train.expectancy >= 0 ? "text-profit" : "text-loss"}`}>
                ({btResults.train.expectancy >= 0 ? "+" : ""}{btResults.train.expectancy}R)
              </span>
            </span>
            <span>
              <span className="text-slate-500">Test </span>
              {btResults.test.trades} trades
              <span className={`ml-1 font-medium ${btResults.test.expectancy >= 0 ? "text-profit" : "text-loss"}`}>
                ({btResults.test.expectancy >= 0 ? "+" : ""}{btResults.test.expectancy}R)
              </span>
            </span>
            <span className="text-slate-500">Split: {btResults.split_date}</span>
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

function Stat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="bg-surface-border/40 rounded-lg p-2 text-center">
      <div className={`text-sm font-bold ${color ?? "text-white"}`}>{value}</div>
      <div className="text-xs text-slate-500 mt-0.5">{label}</div>
    </div>
  );
}
