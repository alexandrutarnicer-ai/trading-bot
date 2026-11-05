import { Loader2, RefreshCw } from "lucide-react";
import type { BacktestAuto, BacktestAutoStatus } from "../api/types";

/** Statusul backtestului LEGAT DE CONFIGURATIA EXACTA (api/backtest_refresh.py): la orice schimbare de piață /
 *  reguli / costuri rezultatul vechi devine „Outdated” și un backtest nou pornește singur în fundal. */
const ST: Record<BacktestAutoStatus, { label: string; cls: string }> = {
  pending:     { label: "Pending",   cls: "bg-slate-600/30 text-slate-300" },
  running:     { label: "Running",   cls: "bg-blue-500/15 text-blue-300" },
  completed:   { label: "Completed", cls: "bg-profit/15 text-profit" },
  failed:      { label: "Failed",    cls: "bg-loss/15 text-loss" },
  outdated:    { label: "Outdated",  cls: "bg-amber-500/15 text-amber-300" },
  interrupted: { label: "Reluat",    cls: "bg-amber-500/15 text-amber-300" },
};

export function BacktestAutoBadge({ a, onRetry, retrying }: { a?: BacktestAuto<unknown>; onRetry?: () => void; retrying?: boolean }) {
  if (!a) return null;
  const s = ST[a.status] ?? ST.outdated;
  const busy = a.status === "pending" || a.status === "running";
  const title = [
    a.fingerprint ? `configurație ${a.fingerprint}` : "",
    a.finished_at ? `terminat ${a.finished_at.replace("T", " ").slice(0, 16)} UTC` : a.requested_at ? `cerut ${a.requested_at.replace("T", " ").slice(0, 16)} UTC` : "",
    a.note ?? "", a.error ? `eroare: ${a.error}` : "",
  ].filter(Boolean).join(" · ");
  return (
    <span className="inline-flex items-center gap-1" title={title}>
      <span className={`text-[10px] px-1.5 py-0.5 rounded font-semibold ${s.cls}`}>
        {busy && <Loader2 size={10} className="inline animate-spin mr-0.5" />}{s.label}
      </span>
      {onRetry && (a.status === "failed" || a.status === "completed") && (
        <button onClick={onRetry} disabled={retrying} title="Rulează din nou backtestul pe configurația curentă"
          className="text-slate-500 hover:text-white disabled:opacity-40"><RefreshCw size={10} /></button>
      )}
    </span>
  );
}
