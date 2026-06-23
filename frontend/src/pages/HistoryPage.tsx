import { useState, useMemo } from "react";
import { Trash2, ChevronDown, ChevronRight, BarChart2 } from "lucide-react";
import { useBacktestHistory, useDeleteBacktestHistory } from "../api/hooks";
import type { BacktestHistoryEntry, BacktestResult } from "../api/types";

const SESSION_LABELS: Record<string, string> = {
  S1: "S1 — FX Long",
  S2: "S2 — FX Both",
  S3: "S3 — BTC",
  S4: "S4 — GER40+US30",
  S5: "S5 — GER40+USDCHF H1",
  S6: "S6 — US30",
};

function expColor(v: number | undefined) {
  if (v === undefined || v === null) return "text-slate-400";
  return v > 0 ? "text-profit" : v < 0 ? "text-loss" : "text-slate-400";
}

function fmtDate(iso: string) {
  const d = new Date(iso);
  return `${d.toLocaleDateString("ro-RO")} ${d.toLocaleTimeString("ro-RO", { hour: "2-digit", minute: "2-digit" })}`;
}

function fmtDateShort(iso: string | null) {
  if (!iso) return "—";
  return iso.slice(0, 10);
}

function fmtR(v: number | undefined) {
  if (v === undefined || v === null) return "—";
  return `${v >= 0 ? "+" : ""}${v.toFixed(3)}R`;
}

function fmtPct(v: number | undefined) {
  if (v === undefined || v === null) return "—";
  return `${(v * 100).toFixed(1)}%`;
}

// ── Row detail ──────────────────────────────────────────────────────────────

function SnapshotBadge({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col items-center bg-surface rounded-lg border border-surface-border px-3 py-1.5">
      <span className="text-[10px] text-slate-500 uppercase tracking-wider">{label}</span>
      <span className="text-xs font-mono text-slate-200">{value}</span>
    </div>
  );
}

function tradesFrequency(r: BacktestResult): { perWeek: number; perMonth: number; days: number } | null {
  if (!r.date_from || !r.date_to || !r.total_trades) return null;
  const days = (new Date(r.date_to).getTime() - new Date(r.date_from).getTime()) / 86_400_000;
  if (days <= 0) return null;
  return {
    days:     Math.round(days),
    perWeek:  r.total_trades / (days / 7),
    perMonth: r.total_trades / (days / 30.44),
  };
}

function ResultsGrid({ r }: { r: BacktestResult }) {
  const freq = tradesFrequency(r);
  const cells = [
    { label: "Trades total",  value: String(r.total_trades) },
    { label: "Win Rate",      value: fmtPct(r.win_rate) },
    { label: "Expectancy",    value: fmtR(r.expectancy), color: expColor(r.expectancy) },
    { label: "Max DD",        value: fmtPct(r.max_dd), color: "text-loss" },
    { label: "Train trades",  value: String(r.train?.trades ?? "—") },
    { label: "Train exp",     value: fmtR(r.train?.expectancy), color: expColor(r.train?.expectancy) },
    { label: "Test trades",   value: String(r.test?.trades ?? "—") },
    { label: "Test exp",      value: fmtR(r.test?.expectancy), color: expColor(r.test?.expectancy) },
  ];

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-4 gap-2">
        {cells.map(c => (
          <div key={c.label} className="bg-surface rounded-lg border border-surface-border p-2 text-center">
            <div className={`text-sm font-mono font-semibold ${c.color ?? "text-white"}`}>{c.value}</div>
            <div className="text-[10px] text-slate-500 mt-0.5">{c.label}</div>
          </div>
        ))}
      </div>
      {freq && (
        <div className="flex items-center gap-3 text-[10px] text-slate-500 bg-surface/60 rounded-lg px-3 py-1.5 border border-surface-border/40">
          <span className="text-slate-400 font-medium">Frecvență:</span>
          <span><span className="text-slate-200 font-mono">{freq.perWeek.toFixed(1)}</span> trades/săpt</span>
          <span className="text-slate-600">·</span>
          <span><span className="text-slate-200 font-mono">{freq.perMonth.toFixed(1)}</span> trades/lună</span>
          <span className="text-slate-600">·</span>
          <span className="text-slate-500">{freq.days} zile testate</span>
        </div>
      )}
    </div>
  );
}

function PerSymbolTable({ ps }: { ps: BacktestResult["per_symbol"] }) {
  if (!ps || Object.keys(ps).length === 0) return null;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-slate-500 border-b border-surface-border">
            <th className="text-left py-1.5 font-normal">Simbol</th>
            <th className="text-right py-1.5 font-normal">Trades</th>
            <th className="text-right py-1.5 font-normal">WR</th>
            <th className="text-right py-1.5 font-normal">Exp</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(ps).map(([sym, v]) => (
            <tr key={sym} className="border-b border-surface-border/30 hover:bg-surface-border/10">
              <td className="py-1.5 font-mono text-slate-200">{sym}</td>
              <td className="text-right text-slate-400">{v.trades}</td>
              <td className="text-right text-slate-400">{fmtPct(v.win_rate)}</td>
              <td className={`text-right font-mono ${expColor(v.expectancy)}`}>{fmtR(v.expectancy)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function HistoryRow({
  entry,
  onDelete,
}: {
  entry: BacktestHistoryEntry;
  onDelete: (id: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const r = entry.results;
  const snap = entry.session_snapshot ?? {};

  return (
    <div className="border border-surface-border rounded-xl overflow-hidden">
      {/* Summary row */}
      <div
        className="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-surface-border/10 transition-colors"
        onClick={() => setExpanded(e => !e)}
      >
        {/* Expand icon */}
        <span className="text-slate-500 flex-shrink-0">
          {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </span>

        {/* Session badge */}
        <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-blue-500/20 text-blue-400 flex-shrink-0">
          {entry.session_id}
        </span>

        {/* Markets */}
        <div className="flex gap-1 flex-wrap flex-1 min-w-0">
          {entry.markets.map(m => (
            <span key={m} className="text-[10px] text-slate-400 font-mono bg-surface-border/30 px-1.5 py-0.5 rounded">
              {m}
            </span>
          ))}
        </div>

        {/* Date range */}
        <span className="text-[10px] text-slate-500 flex-shrink-0 hidden sm:block">
          {fmtDateShort(entry.date_from)} — {fmtDateShort(entry.date_to)}
        </span>

        {/* Key metrics */}
        <div className="flex gap-4 items-center flex-shrink-0">
          <div className="text-right hidden md:block">
            <div className="text-[10px] text-slate-500">Train</div>
            <div className={`text-xs font-mono font-semibold ${expColor(r?.train?.expectancy)}`}>
              {fmtR(r?.train?.expectancy)}
            </div>
          </div>
          <div className="text-right">
            <div className="text-[10px] text-slate-500">Test</div>
            <div className={`text-xs font-mono font-semibold ${expColor(r?.test?.expectancy)}`}>
              {fmtR(r?.test?.expectancy)}
            </div>
          </div>
          <div className="text-right hidden lg:block">
            <div className="text-[10px] text-slate-500">Trades</div>
            <div className="text-xs font-mono text-slate-300">{r?.total_trades ?? "—"}</div>
          </div>
          <div className="text-right hidden lg:block">
            <div className="text-[10px] text-slate-500">DD</div>
            <div className="text-xs font-mono text-loss">{fmtPct(r?.max_dd)}</div>
          </div>
        </div>

        {/* Timestamp */}
        <span className="text-[10px] text-slate-600 flex-shrink-0 hidden xl:block">
          {fmtDate(entry.timestamp)}
        </span>

        {/* Delete */}
        <button
          onClick={e => { e.stopPropagation(); onDelete(entry.id); }}
          className="text-slate-600 hover:text-loss transition-colors flex-shrink-0 p-1"
          title="Sterge"
        >
          <Trash2 size={13} />
        </button>
      </div>

      {/* Detail panel */}
      {expanded && (
        <div className="border-t border-surface-border bg-surface/50 p-4 space-y-4">
          {/* Config snapshot */}
          {Object.keys(snap).length > 0 && (
            <div>
              <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-2">Parametri sesiune</div>
              <div className="flex flex-wrap gap-2">
                {snap.pullback_window != null && (
                  <SnapshotBadge label="PW" value={String(snap.pullback_window)} />
                )}
                {snap.r_base != null && snap.r_max != null && (
                  <SnapshotBadge label="R-ladder" value={`${snap.r_base}R → ${snap.r_max}R`} />
                )}
                {snap.rsi_enabled != null && (
                  <SnapshotBadge label="RSI" value={snap.rsi_enabled ? "ON" : "OFF"} />
                )}
                {snap.ema_alignment_enabled != null && (
                  <SnapshotBadge label="EMA align" value={snap.ema_alignment_enabled ? "ON" : "OFF"} />
                )}
                {snap.body_strength_enabled != null && (
                  <SnapshotBadge label="Body str." value={snap.body_strength_enabled ? "ON" : "OFF"} />
                )}
                <SnapshotBadge label="TF" value={`${entry.entry_tf}+${entry.trend_tf}`} />
                <SnapshotBadge label="Dir" value={entry.direction} />
                <SnapshotBadge label="Capital" value={`${entry.start_balance.toLocaleString()} USD`} />
              </div>
            </div>
          )}

          {/* Results grid */}
          {r && (
            <>
              <div>
                <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-2">Rezultate globale</div>
                <ResultsGrid r={r} />
              </div>

              {/* Per symbol */}
              {r.per_symbol && Object.keys(r.per_symbol).length > 0 && (
                <div>
                  <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-2">Per simbol</div>
                  <PerSymbolTable ps={r.per_symbol} />
                </div>
              )}
            </>
          )}

          {/* Metadata */}
          <div className="text-[10px] text-slate-600 border-t border-surface-border/40 pt-2">
            Rulat: {fmtDate(entry.timestamp)} · Split: {fmtDateShort(r?.split_date)} ·
            Date: {fmtDateShort(entry.date_from)} — {fmtDateShort(entry.date_to)}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────────

export function HistoryPage() {
  const [filterSession, setFilterSession] = useState<string>("all");
  const { data: allHistory, isLoading } = useBacktestHistory();
  const delHistory = useDeleteBacktestHistory();

  // Derive available sessions from history
  const sessions = useMemo(() => {
    if (!allHistory) return [];
    const ids = [...new Set(allHistory.map(e => e.session_id))].sort();
    return ids;
  }, [allHistory]);

  const filtered = useMemo(() => {
    if (!allHistory) return [];
    if (filterSession === "all") return allHistory;
    return allHistory.filter(e => e.session_id === filterSession);
  }, [allHistory, filterSession]);

  // Summary stats for filtered set
  const summary = useMemo(() => {
    const withResults = filtered.filter(e => e.results?.test?.expectancy != null);
    if (withResults.length === 0) return null;
    const avgTest = withResults.reduce((a, e) => a + e.results.test.expectancy, 0) / withResults.length;
    const positive = withResults.filter(e => e.results.test.expectancy > 0).length;
    const best = withResults.reduce((b, e) =>
      e.results.test.expectancy > (b?.results.test.expectancy ?? -Infinity) ? e : b, null as BacktestHistoryEntry | null);
    return { avgTest, positive, total: withResults.length, best };
  }, [filtered]);

  const handleDelete = (id: string) => {
    if (confirm("Sterge aceasta rulare din istoric?")) {
      delHistory.mutate(id);
    }
  };

  return (
    <div className="p-4 md:p-6 space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <BarChart2 size={18} className="text-blue-400" />
          <h1 className="text-lg font-semibold text-white">Istoric Backteste</h1>
          {allHistory && (
            <span className="text-xs text-slate-500 bg-surface-card border border-surface-border rounded-full px-2 py-0.5">
              {allHistory.length} rulări
            </span>
          )}
        </div>
      </div>

      {/* Session filter */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-xs text-slate-500">Sesiune:</span>
        <button
          onClick={() => setFilterSession("all")}
          className={`text-xs px-3 py-1 rounded-lg border transition-colors ${
            filterSession === "all"
              ? "bg-blue-600 border-blue-500 text-white"
              : "border-surface-border text-slate-400 hover:border-slate-500 hover:text-white"
          }`}
        >
          Toate
        </button>
        {sessions.map(s => (
          <button
            key={s}
            onClick={() => setFilterSession(s)}
            className={`text-xs px-3 py-1 rounded-lg border transition-colors ${
              filterSession === s
                ? "bg-blue-600 border-blue-500 text-white"
                : "border-surface-border text-slate-400 hover:border-slate-500 hover:text-white"
            }`}
          >
            {s}
          </button>
        ))}
      </div>

      {/* Summary stats */}
      {summary && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="bg-surface-card border border-surface-border rounded-xl p-3 text-center">
            <div className="text-2xl font-bold text-white">{summary.total}</div>
            <div className="text-[10px] text-slate-500 mt-0.5">Rulări analizate</div>
          </div>
          <div className="bg-surface-card border border-surface-border rounded-xl p-3 text-center">
            <div className={`text-2xl font-bold ${expColor(summary.avgTest)}`}>
              {fmtR(summary.avgTest)}
            </div>
            <div className="text-[10px] text-slate-500 mt-0.5">Exp. medie TEST</div>
          </div>
          <div className="bg-surface-card border border-surface-border rounded-xl p-3 text-center">
            <div className="text-2xl font-bold text-profit">
              {summary.positive}/{summary.total}
            </div>
            <div className="text-[10px] text-slate-500 mt-0.5">Rulări cu exp+ pe TEST</div>
          </div>
          {summary.best && (
            <div className="bg-surface-card border border-surface-border rounded-xl p-3 text-center">
              <div className="text-2xl font-bold text-profit">
                {fmtR(summary.best.results.test.expectancy)}
              </div>
              <div className="text-[10px] text-slate-500 mt-0.5">
                Best test · {summary.best.session_id}
              </div>
            </div>
          )}
        </div>
      )}

      {/* List */}
      {isLoading ? (
        <div className="space-y-2">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-14 rounded-xl bg-surface-card animate-pulse" />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-16 text-slate-500">
          <BarChart2 size={32} className="mx-auto mb-3 opacity-30" />
          <p className="text-sm">Niciun backtest înregistrat</p>
          <p className="text-xs mt-1 text-slate-600">
            Rulează un backtest din tab-ul Profile → sesiune → Backtest
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {filtered.map(entry => (
            <HistoryRow
              key={entry.id}
              entry={entry}
              onDelete={handleDelete}
            />
          ))}
        </div>
      )}
    </div>
  );
}
