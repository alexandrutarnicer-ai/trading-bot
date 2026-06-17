import { useState } from "react";
import { ClipboardList, Trash2, ChevronDown, ChevronRight, X, AlertTriangle } from "lucide-react";
import { useBacktestJobs, useDeleteBacktestJob } from "../api/hooks";
import type { BacktestJob, BacktestResult } from "../api/types";

// ── Helpers ───────────────────────────────────────────────────────────────────

function expColor(v: number | undefined | null) {
  if (v == null) return "text-slate-400";
  return v > 0 ? "text-profit" : v < 0 ? "text-loss" : "text-slate-400";
}

function fmtR(v: number | undefined | null) {
  if (v == null) return "—";
  return `${v >= 0 ? "+" : ""}${v.toFixed(3)}R`;
}

function fmtPct(v: number | undefined | null) {
  if (v == null) return "—";
  return `${v.toFixed(1)}%`;
}

function fmtTs(iso: string) {
  const d = new Date(iso);
  const today = new Date();
  const isToday = d.toDateString() === today.toDateString();
  const time = d.toLocaleTimeString("ro-RO", { hour: "2-digit", minute: "2-digit" });
  return isToday ? `azi ${time}` : d.toLocaleDateString("ro-RO", { day: "2-digit", month: "short" }) + ` ${time}`;
}

function duration(started: string, completed: string | null) {
  if (!completed) return null;
  const s = new Date(started);
  const c = new Date(completed);
  const sec = Math.round((c.getTime() - s.getTime()) / 1000);
  if (sec < 60) return `${sec}s`;
  return `${Math.floor(sec / 60)}m ${sec % 60}s`;
}

// ── Error modal ───────────────────────────────────────────────────────────────

function classifyError(error: string): "no_data" | "no_data_range" | "no_trades" | "generic" {
  if (error.includes("Nicio piata disponibila in date CSV") || error.includes("date CSV"))
    return "no_data";
  if (error.includes("intervalul selectat"))
    return "no_data_range";
  if (error.includes("Niciun trade generat"))
    return "no_trades";
  return "generic";
}

function ErrorModal({ job, onClose }: { job: BacktestJob; onClose: () => void }) {
  const kind = classifyError(job.error ?? "");

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
      <div className="bg-surface-card border border-surface-border rounded-2xl shadow-2xl w-full max-w-lg">
        {/* Header */}
        <div className="flex items-center gap-3 px-5 py-4 border-b border-surface-border">
          <AlertTriangle size={16} className="text-loss flex-shrink-0" />
          <div className="flex-1">
            <div className="text-sm font-semibold text-white">
              Eroare backtest — {job.session_label}
            </div>
            <div className="text-[10px] text-slate-500 mt-0.5">
              {job.markets.join(" · ")} · {job.entry_tf}+{job.trend_tf}
            </div>
          </div>
          <button onClick={onClose} className="text-slate-500 hover:text-white transition-colors p-1">
            <X size={16} />
          </button>
        </div>

        {/* Body */}
        <div className="p-5 space-y-4">
          {kind === "no_data" && (
            <>
              <div className="bg-loss/10 border border-loss/30 rounded-xl p-4 space-y-2">
                <p className="text-sm font-medium text-loss">Date CSV lipsă</p>
                <p className="text-xs text-slate-300">
                  Nu s-au găsit fișiere CSV pentru una sau mai multe piețe:
                  <strong className="text-white"> {job.markets.join(", ")}</strong>.
                </p>
              </div>
              <div className="space-y-2">
                <p className="text-xs font-medium text-slate-300">Ce trebuie să faci:</p>
                <ol className="text-xs text-slate-400 space-y-1.5 list-decimal list-inside">
                  <li>Asigură-te că <strong className="text-white">MetaTrader 5 este deschis</strong> și conectat pe cont.</li>
                  <li>Mergi la tab-ul <strong className="text-white">Profile</strong>, deschide sesiunea <strong className="text-white">{job.session_label}</strong>.</li>
                  <li>În secțiunea <em>Backtest</em> apasă butonul <strong className="text-white">Rulează Backtest</strong> — dacă datele lipsesc, ți se va oferi opțiunea de descărcare.</li>
                  <li>Dacă MT5 nu returnează date: deschide graficul simbolului pe timeframe-ul cerut și <strong className="text-white">derulează complet spre stânga</strong> pentru a forța descărcarea istoricului.</li>
                </ol>
              </div>
            </>
          )}

          {kind === "no_data_range" && (
            <div className="space-y-2">
              <div className="bg-warn/10 border border-warn/30 rounded-xl p-4">
                <p className="text-sm font-medium text-warn">Interval de date gol</p>
                <p className="text-xs text-slate-300 mt-1">
                  Nu există date CSV în intervalul selectat
                  {job.date_from ? ` (de la ${job.date_from})` : ""}.
                </p>
              </div>
              <p className="text-xs text-slate-400">
                Încearcă un interval mai larg sau descarcă date istorice mai vechi din MT5.
              </p>
            </div>
          )}

          {kind === "no_trades" && (
            <div className="bg-warn/10 border border-warn/30 rounded-xl p-4">
              <p className="text-sm font-medium text-warn">Niciun trade generat</p>
              <p className="text-xs text-slate-300 mt-1">
                Datele există dar strategia nu a generat niciun setup în intervalul selectat.
                Încearcă un interval mai larg, verifică filtrele RSI/EMA sau ajustează
                parametrii sesiunii.
              </p>
            </div>
          )}

          {kind === "generic" && (
            <div className="space-y-2">
              <div className="bg-loss/10 border border-loss/30 rounded-xl p-4">
                <p className="text-sm font-medium text-loss">Eroare neașteptată</p>
                <pre className="text-[10px] text-slate-400 mt-2 overflow-auto max-h-48 whitespace-pre-wrap font-mono leading-relaxed">
                  {job.error}
                </pre>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end px-5 py-4 border-t border-surface-border">
          <button
            onClick={onClose}
            className="text-xs px-4 py-2 rounded-lg bg-surface border border-surface-border text-slate-300 hover:text-white hover:border-slate-400 transition-colors"
          >
            Am înțeles
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Status badge ──────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: BacktestJob["status"] }) {
  if (status === "pending" || status === "running") {
    return (
      <span className="flex items-center gap-1.5 text-[10px] font-semibold px-2.5 py-1 rounded-full bg-blue-500/15 text-blue-400 border border-blue-500/30">
        <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse" />
        In progres
      </span>
    );
  }
  if (status === "error") {
    return (
      <span className="flex items-center gap-1.5 text-[10px] font-semibold px-2.5 py-1 rounded-full bg-loss/15 text-loss border border-loss/30">
        <span className="w-1.5 h-1.5 rounded-full bg-loss" />
        Eroare
      </span>
    );
  }
  return (
    <span className="flex items-center gap-1.5 text-[10px] font-semibold px-2.5 py-1 rounded-full bg-profit/15 text-profit border border-profit/30">
      <span className="w-1.5 h-1.5 rounded-full bg-profit" />
      Gata
    </span>
  );
}

// ── Results grid ──────────────────────────────────────────────────────────────

const RESULT_TIPS: Record<string, string> = {
  "Trades":    "Numărul total de tranzacții simulate în intervalul ales. Minim ~30 pentru relevanță statistică.",
  "Win Rate":  "Procentul tranzacțiilor care au atins TP. O strategie asimetrică (R/R mare) poate fi profitabilă chiar cu WR 35-45%.",
  "Expectancy":"Câștigul mediu per tranzacție în unități R. +0.025R = câștig mediu de 2.5% din riscul asumat per trade. Valoarea relevantă este cea din TEST.",
  "Max DD":    "Scăderea maximă procentuală față de vârful de equity anterior. DD > 40% → reconsideră sizing-ul sau parametrii.",
  "Train t":   "Numărul de tranzacții din perioada de antrenament (primele 70% din tranzacții cronologic). Poate fi ușor overfitted — nu este rezultatul relevant.",
  "Train exp": "Expectancy pe perioada de antrenament. Atenție: parametrii au fost aleși parțial pe baza acestor date — poate fi supraevaluat.",
  "Test t":    "Numărul de tranzacții din perioada de test (ultimele 30% din tranzacții — date nevăzute). Acesta este eșantionul care contează pentru validare.",
  "Test exp":  "Expectancy pe date nevăzute (test). Acesta este indicatorul cheie: dacă e pozitiv pe TEST, strategia are probabil edge real.",
};

function ResultCell({ label, value, color }: { label: string; value: string; color?: string }) {
  const tip = RESULT_TIPS[label];
  return (
    <div className="bg-surface rounded-lg border border-surface-border p-2 text-center group relative">
      <div className={`text-sm font-mono font-semibold ${color ?? "text-white"}`}>{value}</div>
      <div className="flex items-center justify-center gap-1 mt-0.5">
        <span className="text-[10px] text-slate-500">{label}</span>
        {tip && (
          <span className="relative inline-flex">
            <span className="text-[9px] text-slate-600 hover:text-slate-400 cursor-help leading-none">ⓘ</span>
            <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 hidden group-hover:block z-20
              bg-slate-800 border border-slate-600 text-slate-200 text-[10px] rounded-lg px-3 py-2
              w-56 text-left shadow-xl leading-relaxed pointer-events-none">
              {tip}
            </span>
          </span>
        )}
      </div>
    </div>
  );
}

function ResultsGrid({ r }: { r: BacktestResult }) {
  const cells = [
    { label: "Trades",      value: String(r.total_trades) },
    { label: "Win Rate",    value: fmtPct(r.win_rate) },
    { label: "Expectancy",  value: fmtR(r.expectancy),       color: expColor(r.expectancy) },
    { label: "Max DD",      value: fmtPct(r.max_dd),          color: "text-loss" },
    { label: "Train t",     value: String(r.train?.trades ?? "—") },
    { label: "Train exp",   value: fmtR(r.train?.expectancy), color: expColor(r.train?.expectancy) },
    { label: "Test t",      value: String(r.test?.trades ?? "—") },
    { label: "Test exp",    value: fmtR(r.test?.expectancy),  color: expColor(r.test?.expectancy) },
  ];

  return (
    <div className="grid grid-cols-4 gap-2">
      {cells.map(c => (
        <ResultCell key={c.label} label={c.label} value={c.value} color={c.color} />
      ))}
    </div>
  );
}

// ── Job row ───────────────────────────────────────────────────────────────────

function JobRow({
  job,
  onDelete,
  onShowError,
}: {
  job: BacktestJob;
  onDelete: (id: string) => void;
  onShowError: (job: BacktestJob) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const r = job.results;
  const snap = job.session_snapshot ?? {};
  const dur = duration(job.started_at, job.completed_at);
  const isActive = job.status === "pending" || job.status === "running";

  return (
    <div className="border border-surface-border rounded-xl overflow-hidden">
      {/* Summary row */}
      <div
        className={`flex items-center gap-3 px-4 py-3 transition-colors ${
          job.status === "done" ? "cursor-pointer hover:bg-surface-border/10" : ""
        }`}
        onClick={() => job.status === "done" && setExpanded(e => !e)}
      >
        {/* Expand (only when done) */}
        <span className="text-slate-500 flex-shrink-0 w-4">
          {job.status === "done" && (
            expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />
          )}
        </span>

        {/* Status */}
        <StatusBadge status={job.status} />

        {/* Session */}
        <span className="text-xs font-semibold text-white flex-shrink-0">
          {job.session_label || job.session_id}
        </span>

        {/* Markets */}
        <div className="flex gap-1 flex-wrap flex-1 min-w-0">
          {job.markets.map(m => (
            <span key={m} className="text-[10px] text-slate-400 font-mono bg-surface-border/30 px-1.5 py-0.5 rounded">
              {m}
            </span>
          ))}
        </div>

        {/* Period */}
        {(job.date_from || job.date_to) && (
          <span className="text-[10px] text-slate-500 flex-shrink-0 hidden sm:block">
            {job.date_from?.slice(0, 7) ?? "—"} → {job.date_to?.slice(0, 7) ?? "azi"}
          </span>
        )}

        {/* Metrics (if done) */}
        {r && (
          <div className="flex gap-4 items-center flex-shrink-0">
            <div className="text-right hidden md:block">
              <div className="text-[10px] text-slate-500">Train</div>
              <div className={`text-xs font-mono font-semibold ${expColor(r.train?.expectancy)}`}>
                {fmtR(r.train?.expectancy)}
              </div>
            </div>
            <div className="text-right">
              <div className="text-[10px] text-slate-500">Test</div>
              <div className={`text-xs font-mono font-semibold ${expColor(r.test?.expectancy)}`}>
                {fmtR(r.test?.expectancy)}
              </div>
            </div>
            <div className="text-right hidden lg:block">
              <div className="text-[10px] text-slate-500">Trades</div>
              <div className="text-xs font-mono text-slate-300">{r.total_trades}</div>
            </div>
          </div>
        )}

        {/* Error button */}
        {job.status === "error" && (
          <button
            onClick={e => { e.stopPropagation(); onShowError(job); }}
            className="text-xs px-2.5 py-1 rounded-lg border border-loss/40 text-loss/80 hover:border-loss hover:text-loss transition-colors flex-shrink-0"
          >
            Vezi eroarea
          </button>
        )}

        {/* Timestamp + duration */}
        <span className="text-[10px] text-slate-600 flex-shrink-0 hidden xl:block">
          {fmtTs(job.started_at)}{dur && ` · ${dur}`}
        </span>

        {/* Delete — only non-active */}
        {!isActive && (
          <button
            onClick={e => { e.stopPropagation(); onDelete(job.job_id); }}
            className="text-slate-600 hover:text-loss transition-colors flex-shrink-0 p-1"
            title="Șterge"
          >
            <Trash2 size={13} />
          </button>
        )}
      </div>

      {/* Detail panel (done only) */}
      {expanded && r && (
        <div className="border-t border-surface-border bg-surface/50 p-4 space-y-4">
          {/* Snapshot */}
          {Object.keys(snap).length > 0 && (
            <div className="space-y-3">
              <div className="text-[10px] text-slate-500 uppercase tracking-wider">Configurare sesiune</div>

              {/* Rând 1: Strategie */}
              <div>
                <div className="text-[9px] text-slate-600 uppercase tracking-wider mb-1.5">Strategie</div>
                <div className="flex flex-wrap gap-2">
                  <SnapBadge label="TF" value={`${job.entry_tf}+${job.trend_tf}`} />
                  <SnapBadge label="Direcție" value={job.direction} />
                  {snap.pullback_window != null && <SnapBadge label="Pullback win." value={String(snap.pullback_window)} />}
                  {snap.expire_bars != null && <SnapBadge label="Expire bare" value={String(snap.expire_bars)} />}
                  {snap.circuit_breaker != null && <SnapBadge label="Circuit break." value={String(snap.circuit_breaker)} />}
                </div>
              </div>

              {/* Rând 2: Ore sesiune */}
              {(snap.session_start != null || (snap.skip_hours as number[] | undefined)?.length) && (
                <div>
                  <div className="text-[9px] text-slate-600 uppercase tracking-wider mb-1.5">Ore sesiune</div>
                  <div className="flex flex-wrap gap-2">
                    {snap.session_start != null && snap.session_end != null && (
                      <SnapBadge
                        label="Interval"
                        value={
                          snap.session_start === 0 && snap.session_end === 24
                            ? "Non-stop"
                            : `${snap.session_start}:00 – ${snap.session_end}:00`
                        }
                      />
                    )}
                    {(snap.skip_hours as number[] | undefined)?.length ? (
                      <SnapBadge label="Skip ore" value={(snap.skip_hours as number[]).join(", ")} />
                    ) : null}
                    {(snap.skip_weekdays as number[] | undefined)?.length ? (
                      <SnapBadge
                        label="Skip zile"
                        value={(snap.skip_weekdays as number[])
                          .map(d => ["Lu","Ma","Mi","Jo","Vi","Sb","Du"][d] ?? d)
                          .join(", ")}
                      />
                    ) : null}
                  </div>
                </div>
              )}

              {/* Rând 3: R-ladder */}
              <div>
                <div className="text-[9px] text-slate-600 uppercase tracking-wider mb-1.5">R-Ladder</div>
                <div className="flex flex-wrap gap-2">
                  {(["base","mid","top","max"] as const).map(tier => {
                    const r    = snap[`r_${tier}`] as number | undefined;
                    const risk = snap[`risk_${tier}`] as number | undefined;
                    const thr  = tier !== "base" ? snap[`r_${tier}_threshold`] as number | undefined : null;
                    if (r == null) return null;
                    return (
                      <div key={tier} className="flex flex-col items-center bg-surface rounded-lg border border-surface-border px-3 py-1.5 min-w-[64px]">
                        <span className="text-[9px] text-slate-500 uppercase tracking-wider">{tier}</span>
                        <span className="text-xs font-mono font-semibold text-white">{r}R</span>
                        {risk != null && (
                          <span className="text-[9px] text-slate-600">{(risk * 100).toFixed(1)}% risk</span>
                        )}
                        {thr != null && (
                          <span className="text-[9px] text-slate-600">≥{thr} crit.</span>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Rând 4: Criterii opționale */}
              <div>
                <div className="text-[9px] text-slate-600 uppercase tracking-wider mb-1.5">Criterii opționale</div>
                <div className="flex flex-wrap gap-2">
                  <SnapBadge
                    label="RSI"
                    value={snap.rsi_enabled
                      ? `ON  ${snap.rsi_buy_min}–${snap.rsi_buy_max} / ${snap.rsi_sell_min}–${snap.rsi_sell_max}`
                      : "OFF"}
                  />
                  <SnapBadge label="EMA align" value={snap.ema_alignment_enabled ? "ON" : "OFF"} />
                  <SnapBadge label="Body str." value={snap.body_strength_enabled ? "ON" : "OFF"} />
                </div>
              </div>

              {/* Rând 5: Capital */}
              <div>
                <div className="text-[9px] text-slate-600 uppercase tracking-wider mb-1.5">Capital simulat</div>
                <div className="flex flex-wrap gap-2">
                  <SnapBadge label="Total" value={`${(snap.start_balance as number ?? job.start_balance).toLocaleString()} USD`} />
                  {snap.market_allocations != null && Object.entries(snap.market_allocations as Record<string, number>).map(([m, v]) => (
                    <SnapBadge key={m} label={m} value={`${Math.round(v).toLocaleString()} USD`} />
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Results grid */}
          <div>
            <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-2">Rezultate</div>
            <ResultsGrid r={r} />
          </div>

          {/* Per-symbol */}
          {r.per_symbol && Object.keys(r.per_symbol).length > 0 && (
            <div>
              <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-2">Per simbol</div>
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
                    {Object.entries(r.per_symbol).map(([sym, v]) => (
                      <tr key={sym} className="border-b border-surface-border/30">
                        <td className="py-1.5 font-mono text-slate-200">{sym}</td>
                        <td className="text-right text-slate-400">{v.trades}</td>
                        <td className="text-right text-slate-400">{fmtPct(v.win_rate)}</td>
                        <td className={`text-right font-mono ${expColor(v.expectancy)}`}>{fmtR(v.expectancy)}</td>
                      </tr>
                    ))}
                    {/* Piete fara date CSV */}
                    {r.skipped_markets?.map(sym => (
                      <tr key={sym} className="border-b border-surface-border/20">
                        <td className="py-1.5 font-mono text-slate-500 flex items-center gap-1.5">
                          {sym}
                          <span className="text-[9px] text-loss bg-loss/10 px-1.5 py-0.5 rounded">lipsă CSV</span>
                        </td>
                        <td className="text-right text-slate-600">—</td>
                        <td className="text-right text-slate-600">—</td>
                        <td className="text-right text-slate-600">—</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {r.skipped_markets && r.skipped_markets.length > 0 && (
                <p className="text-[10px] text-slate-500 mt-1.5">
                  ⚠ {r.skipped_markets.join(", ")} — date CSV lipsă sau insuficiente (&lt;100 bare).
                  Descarcă datele din Profile → sesiune → Rulează Backtest → Descarcă date din MT5.
                </p>
              )}
            </div>
          )}

          {/* Meta */}
          <div className="text-[10px] text-slate-600 border-t border-surface-border/40 pt-2">
            Rulat: {fmtTs(job.started_at)}
            {dur && ` · Durată: ${dur}`}
            {r.split_date && ` · Split: ${r.split_date}`}
            {r.date_from && r.date_to && ` · Date: ${r.date_from} — ${r.date_to}`}
          </div>
        </div>
      )}
    </div>
  );
}

function SnapBadge({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col items-center bg-surface rounded-lg border border-surface-border px-3 py-1.5">
      <span className="text-[10px] text-slate-500 uppercase tracking-wider">{label}</span>
      <span className="text-xs font-mono text-slate-200">{value}</span>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export function AuditPage() {
  const { data: jobs, isLoading } = useBacktestJobs();
  const deleteJob = useDeleteBacktestJob();
  const [errorJob, setErrorJob] = useState<BacktestJob | null>(null);

  const running = jobs?.filter(j => j.status === "pending" || j.status === "running") ?? [];
  const done    = jobs?.filter(j => j.status === "done") ?? [];
  const error   = jobs?.filter(j => j.status === "error") ?? [];

  const handleDelete = (id: string) => {
    if (confirm("Șterge acest job din audit?")) {
      deleteJob.mutate(id);
    }
  };

  return (
    <>
      {errorJob && (
        <ErrorModal job={errorJob} onClose={() => setErrorJob(null)} />
      )}

      <div className="p-4 md:p-6 space-y-5">
        {/* Header */}
        <div className="flex items-center gap-3">
          <ClipboardList size={18} className="text-blue-400" />
          <h1 className="text-lg font-semibold text-white">Audit Backteste</h1>
          {jobs && jobs.length > 0 && (
            <span className="text-xs text-slate-500 bg-surface-card border border-surface-border rounded-full px-2 py-0.5">
              {jobs.length} total
            </span>
          )}
          {running.length > 0 && (
            <span className="flex items-center gap-1.5 text-xs text-blue-400 bg-blue-500/10 border border-blue-500/30 rounded-full px-2.5 py-0.5">
              <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse" />
              {running.length} în rulare
            </span>
          )}
        </div>

        {/* Loading */}
        {isLoading ? (
          <div className="space-y-2">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="h-14 rounded-xl bg-surface-card animate-pulse" />
            ))}
          </div>
        ) : jobs?.length === 0 ? (
          <div className="text-center py-16 text-slate-500">
            <ClipboardList size={32} className="mx-auto mb-3 opacity-30" />
            <p className="text-sm">Niciun backtest în audit</p>
            <p className="text-xs mt-1 text-slate-600">
              Rulează un backtest din tab-ul Profile → sesiune → Rulează Backtest
            </p>
          </div>
        ) : (
          <div className="space-y-6">
            {/* Running */}
            {running.length > 0 && (
              <section className="space-y-2">
                <div className="text-[10px] text-slate-500 uppercase tracking-wider font-medium">
                  In rulare ({running.length})
                </div>
                {running.map(job => (
                  <JobRow
                    key={job.job_id}
                    job={job}
                    onDelete={handleDelete}
                    onShowError={setErrorJob}
                  />
                ))}
              </section>
            )}

            {/* Errors */}
            {error.length > 0 && (
              <section className="space-y-2">
                <div className="text-[10px] text-slate-500 uppercase tracking-wider font-medium">
                  Erori ({error.length})
                </div>
                {error.map(job => (
                  <JobRow
                    key={job.job_id}
                    job={job}
                    onDelete={handleDelete}
                    onShowError={setErrorJob}
                  />
                ))}
              </section>
            )}

            {/* Done */}
            {done.length > 0 && (
              <section className="space-y-2">
                <div className="text-[10px] text-slate-500 uppercase tracking-wider font-medium">
                  Finalizate ({done.length})
                </div>
                {done.map(job => (
                  <JobRow
                    key={job.job_id}
                    job={job}
                    onDelete={handleDelete}
                    onShowError={setErrorJob}
                  />
                ))}
              </section>
            )}
          </div>
        )}
      </div>
    </>
  );
}
