import { useState } from "react";
import { useRunBacktest, useBacktestJob } from "../api/hooks";
import { InfoTooltip } from "./InfoTooltip";
import type { BacktestResult, ProfileSession } from "../api/types";

interface Props {
  session: ProfileSession;
}

type Range = "1y" | "3y" | "all" | "custom";

const RANGE_LABELS: Record<Range, string> = {
  "1y": "1 An", "3y": "3 Ani", "all": "Tot", "custom": "Custom",
};

const BACKTEST_INFO =
  "Backtest rulează pe date CSV istorice (offline). " +
  "Split train/test la 70%/30% din tranzacții — nu din timp — " +
  "pentru a evita bias-ul pe perioade scurte. " +
  "Rezultatele nu garantează performanță viitoare; " +
  "interpreteaza expectancy pozitiv pe TEST ca semnal relevant.";

export function BacktestPanel({ session }: Props) {
  const [jobId, setJobId] = useState<string | null>(null);
  const [range, setRange] = useState<Range>("all");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const run = useRunBacktest();
  const { data: job } = useBacktestJob(jobId);

  const getDateRange = (): { date_from?: string; date_to?: string } => {
    const offset = (years: number) => {
      const d = new Date();
      d.setFullYear(d.getFullYear() - years);
      return d.toISOString().slice(0, 10);
    };
    if (range === "1y") return { date_from: offset(1) };
    if (range === "3y") return { date_from: offset(3) };
    if (range === "custom") return {
      date_from: dateFrom || undefined,
      date_to:   dateTo   || undefined,
    };
    return {};
  };

  const handleRun = async () => {
    setJobId(null);
    const res = await run.mutateAsync({ session, ...getDateRange() }) as { job_id: string };
    setJobId(res.job_id);
  };

  const results = job?.results as BacktestResult | null;
  const isRunning = job?.status === "running" || job?.status === "pending";

  return (
    <div className="space-y-3">
      {/* Range selector */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-xs text-slate-500">Interval:</span>
        {(["1y", "3y", "all", "custom"] as Range[]).map((r) => (
          <button
            key={r}
            onClick={() => setRange(r)}
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

      {/* Custom date pickers */}
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

      {/* Run button */}
      <div className="flex items-center gap-3">
        <button
          onClick={handleRun}
          disabled={isRunning || run.isPending}
          className="flex items-center gap-2 px-3 py-1.5 text-xs font-medium rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {isRunning ? (
            <>
              <span className="w-2.5 h-2.5 rounded-full border-2 border-white border-t-transparent animate-spin" />
              Se rulează...
            </>
          ) : (
            <>▶ Rulează Backtest</>
          )}
        </button>
        {job?.status === "error" && (
          <span className="text-xs text-red-400">Eroare: {job.error}</span>
        )}
      </div>

      {/* Results */}
      {results && (
        <div className="bg-surface rounded-xl p-4 space-y-3 border border-surface-border">
          <div className="grid grid-cols-4 gap-3">
            <Stat label="Trades" value={String(results.total_trades)} />
            <Stat label="Win Rate" value={`${results.win_rate}%`} />
            <Stat
              label="Expectancy"
              value={`${results.expectancy >= 0 ? "+" : ""}${results.expectancy}R`}
              color={results.expectancy >= 0 ? "text-profit" : "text-loss"}
            />
            <Stat label="Max DD" value={`${results.max_dd}%`} color="text-warn" />
          </div>
          <div className="flex gap-6 text-xs text-slate-400 border-t border-surface-border pt-2">
            <span>
              <span className="text-slate-500">Train </span>
              {results.train.trades} trades
              <span className={`ml-1 font-medium ${results.train.expectancy >= 0 ? "text-profit" : "text-loss"}`}>
                ({results.train.expectancy >= 0 ? "+" : ""}{results.train.expectancy}R)
              </span>
            </span>
            <span>
              <span className="text-slate-500">Test </span>
              {results.test.trades} trades
              <span className={`ml-1 font-medium ${results.test.expectancy >= 0 ? "text-profit" : "text-loss"}`}>
                ({results.test.expectancy >= 0 ? "+" : ""}{results.test.expectancy}R)
              </span>
            </span>
            <span className="text-slate-500">Split: {results.split_date}</span>
          </div>
          {Object.keys(results.per_symbol).length > 0 && (
            <div className="grid grid-cols-3 gap-1.5">
              {Object.entries(results.per_symbol).map(([sym, s]) => (
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
        </div>
      )}
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
