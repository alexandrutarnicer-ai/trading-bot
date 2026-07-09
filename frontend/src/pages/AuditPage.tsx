import { useState, useMemo } from "react";
import { ClipboardList, Trash2, ChevronDown, ChevronRight, X, AlertTriangle, Download, Copy, Search, CheckSquare, Square } from "lucide-react";
import { useBacktestJobs, useDeleteBacktestJob, useDownloadJobs, useDeleteDownloadJob } from "../api/hooks";
import type { BacktestJob, BacktestResult, DownloadJob, DownloadFileResult, WeekdayStat, HourStat } from "../api/types";

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

// M0 — banner de verdict de robustete (vezi docs/M0_METHOD.md).
const VERDICT_META: Record<string, { label: string; icon: string; box: string; dot: string }> = {
  KEEP:    { label: "KEEP — edge robust",      icon: "🟢", box: "border-profit/40 bg-profit/10",   dot: "text-profit" },
  OBSERVE: { label: "OBSERVE — ambiguu",       icon: "🟡", box: "border-amber-500/40 bg-amber-500/10", dot: "text-amber-400" },
  DEMOTE:  { label: "DEMOTE — fara edge dovedit", icon: "🔴", box: "border-loss/40 bg-loss/10",     dot: "text-loss" },
  INSUFF:  { label: "INSUFF — prea putine date", icon: "⚪", box: "border-slate-600/40 bg-slate-700/20", dot: "text-slate-400" },
};

const ROB_TIPS: Record<string, string> = {
  "P(edge>0)":  "Increderea (bootstrap) ca expectancy adevarat > 0. ≥95% = edge distinct de zgomotul de esantion. Cifra cea mai bine fundamentata.",
  "Fold+":      "Fractia din cele 8 sub-perioade in care sesiunea a fost pozitiva. Aproape de 100% = edge stabil in timp, nu dependent de un singur regim.",
  "N* trials":  "De cate variante independente ai fi avut nevoie ca edge-ul sa fie explicat prin noroc de cautare. Mic (<10) = fragil, sensibil la multiple testing.",
  "CI 95%":     "Intervalul de incredere 95% pe expectancy. Daca include 0 sau e negativ, edge-ul nu e inca stabilit.",
};

function RobStat({ label, value, color }: { label: string; value: string; color?: string }) {
  const tip = ROB_TIPS[label];
  return (
    <div className="group relative flex items-center gap-1">
      <span className="text-slate-500">{label}:</span>
      <span className={`font-mono ${color ?? "text-slate-200"}`}>{value}</span>
      {tip && (
        <span className="relative inline-flex">
          <span className="text-[9px] text-slate-600 hover:text-slate-400 cursor-help leading-none">ⓘ</span>
          <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 hidden group-hover:block z-20
            bg-slate-800 border border-slate-600 text-slate-200 text-[10px] rounded-lg px-3 py-2
            w-56 text-left shadow-xl leading-relaxed pointer-events-none normal-case">
            {tip}
          </span>
        </span>
      )}
    </div>
  );
}

function RobustnessBanner({ rob }: { rob: NonNullable<BacktestResult["robustness"]> }) {
  const meta = VERDICT_META[rob.verdict] ?? VERDICT_META.INSUFF;
  const pPos = rob.prob_positive == null ? "—" : `${(rob.prob_positive * 100).toFixed(0)}%`;
  const fPos = rob.frac_positive == null ? "—" : `${(rob.frac_positive * 100).toFixed(0)}%`;
  const nStar = rob.breakeven_trials >= 100000 ? "∞" : String(rob.breakeven_trials);
  const ci = rob.ci_low == null || rob.ci_high == null
    ? "—" : `${rob.ci_low >= 0 ? "+" : ""}${rob.ci_low.toFixed(2)} … ${rob.ci_high >= 0 ? "+" : ""}${rob.ci_high.toFixed(2)}R`;
  const pColor = rob.prob_positive != null && rob.prob_positive >= 0.95 ? "text-profit"
    : rob.prob_positive != null && rob.prob_positive < 0.75 ? "text-loss" : "text-amber-400";

  return (
    <div className={`rounded-lg border p-2.5 space-y-1.5 ${meta.box}`}>
      <div className="flex items-center gap-2">
        <span className="text-sm">{meta.icon}</span>
        <span className={`text-xs font-semibold uppercase tracking-wide ${meta.dot}`}>{meta.label}</span>
        <span className="ml-auto text-[10px] text-slate-500">Robustete M0</span>
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px]">
        <RobStat label="P(edge>0)" value={pPos} color={pColor} />
        <RobStat label="Fold+" value={fPos} />
        <RobStat label="N* trials" value={nStar} color={rob.breakeven_trials < 10 ? "text-amber-400" : "text-slate-200"} />
        <RobStat label="CI 95%" value={ci} />
      </div>
      {rob.notes.length > 0 && (
        <div className="text-[10px] text-amber-400/90 leading-relaxed">
          ⚠ {rob.notes.join(" · ")}
        </div>
      )}
    </div>
  );
}

function ResultsGrid({ r }: { r: BacktestResult }) {
  const beLock  = r.be_lock_count  ?? 0;
  const beLock2 = r.be_lock2_count ?? 0;
  const beTotal = beLock + beLock2;
  const freq    = tradesFrequency(r);

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
    <div className="space-y-2">
      {r.robustness && <RobustnessBanner rob={r.robustness} />}
      <div className="grid grid-cols-4 gap-2">
        {cells.map(c => (
          <ResultCell key={c.label} label={c.label} value={c.value} color={c.color} />
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
      {beTotal > 0 && (
        <div className="flex items-center gap-3 text-[10px] text-slate-500 bg-surface/60 rounded-lg px-3 py-1.5 border border-surface-border/40">
          <span className="text-slate-400 font-medium">Break-Even:</span>
          <span>Faza 1: <span className="text-profit font-mono">{beLock}</span></span>
          {beLock2 > 0 && <span>Faza 2: <span className="text-profit font-mono">{beLock2}</span></span>}
          <span className="text-slate-600">·</span>
          <span>Total BE: <span className="text-profit font-mono">{beTotal}</span> din {r.total_trades} trades</span>
        </div>
      )}
      {r.flag_was_enabled && (
        <div className="flex items-center gap-3 text-[10px] text-slate-500 bg-surface/60 rounded-lg px-3 py-1.5 border border-surface-border/40">
          <span className="text-slate-400 font-medium">Flag:</span>
          {(r.flag_stats?.trades ?? 0) > 0 ? (
            <>
              <span><span className="text-slate-200 font-mono">{r.flag_stats!.trades}</span> trades</span>
              <span className="text-slate-600">·</span>
              <span>WR <span className="text-slate-200 font-mono">{r.flag_stats!.win_rate}%</span></span>
              <span className="text-slate-600">·</span>
              <span>Exp <span className={`font-mono ${r.flag_stats!.expectancy >= 0 ? "text-profit" : "text-loss"}`}>{r.flag_stats!.expectancy > 0 ? "+" : ""}{r.flag_stats!.expectancy.toFixed(3)}R</span></span>
            </>
          ) : (
            <span className="text-slate-600 italic">activat · 0 semnale detectate</span>
          )}
        </div>
      )}
      {r.inside_bar_was_enabled && (
        <div className="flex items-center gap-3 text-[10px] text-slate-500 bg-surface/60 rounded-lg px-3 py-1.5 border border-surface-border/40">
          <span className="text-slate-400 font-medium">Inside Bar:</span>
          {(r.inside_bar_stats?.trades ?? 0) > 0 ? (
            <>
              <span><span className="text-slate-200 font-mono">{r.inside_bar_stats!.trades}</span> trades</span>
              <span className="text-slate-600">·</span>
              <span>WR <span className="text-slate-200 font-mono">{r.inside_bar_stats!.win_rate}%</span></span>
              <span className="text-slate-600">·</span>
              <span>Exp <span className={`font-mono ${r.inside_bar_stats!.expectancy >= 0 ? "text-profit" : "text-loss"}`}>{r.inside_bar_stats!.expectancy > 0 ? "+" : ""}{r.inside_bar_stats!.expectancy.toFixed(3)}R</span></span>
            </>
          ) : (
            <span className="text-slate-600 italic">activat · 0 semnale detectate</span>
          )}
        </div>
      )}
    </div>
  );
}

// ── Capital summary ───────────────────────────────────────────────────────────

function CapitalSummary({ start, final: fin }: { start: number; final: number }) {
  const pnl    = fin - start;
  const pnlPct = start > 0 ? (pnl / start) * 100 : 0;
  const pos    = pnl >= 0;

  return (
    <div className="mt-3 flex items-center gap-3 px-3 py-2.5 rounded-lg bg-surface border border-surface-border">
      <div className="flex-1 text-center">
        <div className="text-[9px] text-slate-500 uppercase tracking-wider mb-0.5">Capital inițial</div>
        <div className="text-sm font-mono font-semibold text-slate-300">
          {start.toLocaleString("ro-RO", { maximumFractionDigits: 0 })} USD
        </div>
      </div>

      <div className="text-slate-600 text-xs">→</div>

      <div className="flex-1 text-center">
        <div className="text-[9px] text-slate-500 uppercase tracking-wider mb-0.5">Capital final</div>
        <div className={`text-sm font-mono font-semibold ${pos ? "text-profit" : "text-loss"}`}>
          {fin.toLocaleString("ro-RO", { maximumFractionDigits: 0 })} USD
        </div>
      </div>

      <div className="w-px h-8 bg-surface-border" />

      <div className="flex-1 text-center">
        <div className="text-[9px] text-slate-500 uppercase tracking-wider mb-0.5">P&L</div>
        <div className={`text-sm font-mono font-semibold ${pos ? "text-profit" : "text-loss"}`}>
          {pos ? "+" : ""}{pnl.toLocaleString("ro-RO", { maximumFractionDigits: 0 })} USD
        </div>
        <div className={`text-[10px] ${pos ? "text-profit/70" : "text-loss/70"}`}>
          {pos ? "+" : ""}{pnlPct.toFixed(1)}%
        </div>
      </div>
    </div>
  );
}

// ── Weekday / Hour analysis ──────────────────────────────────────────────────

function LossAnalysis({ weekday, hour }: {
  weekday?: Record<number, WeekdayStat>;
  hour?: Record<number, HourStat>;
}) {
  const [tab, setTab] = useState<"weekday" | "hour">("weekday");

  if (!weekday && !hour) return null;

  const wdEntries  = weekday ? Object.entries(weekday).map(([k, v]) => ({ wd: Number(k), ...v })) : [];
  const hrEntries  = hour    ? Object.entries(hour).map(([k, v]) => ({ h: Number(k), ...v })) : [];

  // Identifica zilele/orele cu pierderi cumulate mari
  const worstWd   = [...wdEntries].sort((a, b) => a.expectancy - b.expectancy).slice(0, 2);
  const worstHr   = [...hrEntries].sort((a, b) => a.expectancy - b.expectancy).slice(0, 3);

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <div className="text-[10px] text-slate-500 uppercase tracking-wider">
          Analiza pierderi (potențial skip)
        </div>
        <div className="flex gap-1">
          <button
            onClick={() => setTab("weekday")}
            className={`text-[10px] px-2 py-0.5 rounded transition-colors ${tab === "weekday" ? "bg-blue-500/20 text-blue-400 border border-blue-500/30" : "text-slate-500 hover:text-slate-300"}`}
          >
            Zile săptămână
          </button>
          <button
            onClick={() => setTab("hour")}
            className={`text-[10px] px-2 py-0.5 rounded transition-colors ${tab === "hour" ? "bg-blue-500/20 text-blue-400 border border-blue-500/30" : "text-slate-500 hover:text-slate-300"}`}
          >
            Ore
          </button>
        </div>
      </div>

      {tab === "weekday" && wdEntries.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-slate-500 border-b border-surface-border">
                <th className="text-left py-1.5 font-normal">Zi</th>
                <th className="text-right py-1.5 font-normal">Trades</th>
                <th className="text-right py-1.5 font-normal">Pierderi</th>
                <th className="text-right py-1.5 font-normal">Loss %</th>
                <th className="text-right py-1.5 font-normal">Expectancy</th>
                <th className="text-right py-1.5 font-normal"></th>
              </tr>
            </thead>
            <tbody>
              {wdEntries.sort((a, b) => a.wd - b.wd).map(({ wd, name, trades, losses, loss_rate, expectancy }) => (
                <tr key={wd} className="border-b border-surface-border/30">
                  <td className="py-1.5 font-medium text-slate-200">{name}</td>
                  <td className="text-right text-slate-400">{trades}</td>
                  <td className="text-right text-slate-400">{losses}</td>
                  <td className="text-right text-slate-400">{loss_rate.toFixed(1)}%</td>
                  <td className={`text-right font-mono ${expColor(expectancy)}`}>{fmtR(expectancy)}</td>
                  <td className="text-right pl-2">
                    {worstWd.some(w => w.wd === wd) && expectancy < 0 && (
                      <span className="text-[9px] text-warn bg-warn/10 px-1.5 py-0.5 rounded">
                        skip candidat
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {worstWd.filter(w => w.expectancy < 0).length > 0 && (
            <p className="text-[10px] text-slate-500 mt-1.5">
              💡 Zilele cu expectancy negativ sunt candidați pentru <strong className="text-slate-300">skip_weekdays</strong> în configuratorul de sesiune.
            </p>
          )}
        </div>
      )}

      {tab === "hour" && hrEntries.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-slate-500 border-b border-surface-border">
                <th className="text-left py-1.5 font-normal">Ora</th>
                <th className="text-right py-1.5 font-normal">Trades</th>
                <th className="text-right py-1.5 font-normal">Pierderi</th>
                <th className="text-right py-1.5 font-normal">Loss %</th>
                <th className="text-right py-1.5 font-normal">Expectancy</th>
                <th className="text-right py-1.5 font-normal"></th>
              </tr>
            </thead>
            <tbody>
              {hrEntries.sort((a, b) => a.h - b.h).map(({ h, trades, losses, loss_rate, expectancy }) => (
                <tr key={h} className="border-b border-surface-border/30">
                  <td className="py-1.5 font-mono text-slate-200">{String(h).padStart(2, "0")}:00</td>
                  <td className="text-right text-slate-400">{trades}</td>
                  <td className="text-right text-slate-400">{losses}</td>
                  <td className="text-right text-slate-400">{loss_rate.toFixed(1)}%</td>
                  <td className={`text-right font-mono ${expColor(expectancy)}`}>{fmtR(expectancy)}</td>
                  <td className="text-right pl-2">
                    {worstHr.some(w => w.h === h) && expectancy < 0 && (
                      <span className="text-[9px] text-warn bg-warn/10 px-1.5 py-0.5 rounded">
                        skip candidat
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {worstHr.filter(w => w.expectancy < 0).length > 0 && (
            <p className="text-[10px] text-slate-500 mt-1.5">
              💡 Orele cu expectancy negativ sunt candidați pentru <strong className="text-slate-300">skip_hours</strong> în configuratorul de sesiune.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

// ── Job row ───────────────────────────────────────────────────────────────────

function JobRow({
  job,
  onDelete,
  onShowError,
  onApplyConfig,
}: {
  job: BacktestJob;
  onDelete: (id: string) => void;
  onShowError: (job: BacktestJob) => void;
  onApplyConfig?: (sessionId: string, config: Record<string, unknown>) => void;
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

              {/* Rând 5: Break-Even */}
              {snap.break_even_enabled != null && (
                <div>
                  <div className="text-[9px] text-slate-600 uppercase tracking-wider mb-1.5">Break-Even</div>
                  <div className="flex flex-wrap gap-2">
                    <SnapBadge label="Break-Even" value={snap.break_even_enabled ? "ON" : "OFF"} />
                    {snap.break_even_enabled && <>
                      {snap.be_trigger_pct  != null && <SnapBadge label="Trigger"  value={`${snap.be_trigger_pct}%`} />}
                      {snap.be_lock1_pct    != null && <SnapBadge label="Lock 1"   value={`${snap.be_lock1_pct}%`} />}
                      {snap.be_lock2_pct    != null && <SnapBadge label="Lock 2"   value={`${snap.be_lock2_pct}%`} />}
                      {snap.be_phase2_zone_pct != null && <SnapBadge label="Faza 2 zonă" value={`${snap.be_phase2_zone_pct}%`} />}
                      <SnapBadge label="Faza 2" value={snap.be_phase2_enabled ? "ON" : "OFF"} />
                    </>}
                  </div>
                </div>
              )}

              {/* Rând 6: Vineri + Știri */}
              {(snap.friday_close_enabled != null || snap.news_protection_enabled != null) && (
                <div>
                  <div className="text-[9px] text-slate-600 uppercase tracking-wider mb-1.5">Protecție</div>
                  <div className="flex flex-wrap gap-2">
                    {snap.friday_close_enabled != null && (
                      <SnapBadge label="Înch. Vineri" value={snap.friday_close_enabled
                        ? `ON ora ${snap.friday_close_hour ?? 20}`
                        : "OFF"} />
                    )}
                    {snap.news_protection_enabled != null && (
                      <SnapBadge label="Știri" value={snap.news_protection_enabled
                        ? `Impact ≥${snap.news_impact_level ?? 2} · -${snap.news_pre_minutes ?? 15}min / +${snap.news_post_minutes ?? 15}min`
                        : "OFF"} />
                    )}
                  </div>
                </div>
              )}

              {/* Rând 7: Tranzacționare avansată */}
              {(snap.max_concurrent_per_market != null || snap.min_bars_between_trades != null) && (
                <div>
                  <div className="text-[9px] text-slate-600 uppercase tracking-wider mb-1.5">Tranzacționare</div>
                  <div className="flex flex-wrap gap-2">
                    {snap.max_concurrent_per_market != null && (
                      <SnapBadge label="Max concurent" value={String(snap.max_concurrent_per_market)} />
                    )}
                    {snap.min_bars_between_trades != null && snap.min_bars_between_trades as number > 0 && (
                      <SnapBadge label="Min bare intre" value={String(snap.min_bars_between_trades)} />
                    )}
                  </div>
                </div>
              )}

              {/* Rând 8: Capital */}
              <div>
                <div className="text-[9px] text-slate-600 uppercase tracking-wider mb-1.5">Capital simulat</div>
                <div className="flex flex-wrap gap-2">
                  <SnapBadge label="Total" value={`${(snap.start_balance as number ?? job.start_balance).toLocaleString()} USD`} />
                  {snap.market_allocations != null && Object.entries(snap.market_allocations as Record<string, number>).map(([m, v]) => (
                    <SnapBadge key={m} label={m} value={`${Math.round(v).toLocaleString()} USD`} />
                  ))}
                </div>
              </div>

              {/* Buton Aplică config */}
              {onApplyConfig && (
                <div className="pt-1 border-t border-surface-border/40">
                  <button
                    onClick={() => onApplyConfig(job.session_id, snap)}
                    className="flex items-center gap-2 text-xs px-3 py-1.5 rounded-lg bg-blue-500/10 border border-blue-500/30 text-blue-400 hover:bg-blue-500/20 transition-colors"
                    title="Aplică parametrii acestui backtest pe sesiunea din Profil (fără salvare automată)"
                  >
                    <Copy size={12} />
                    Aplică config pe sesiunea {job.session_id}
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Results grid */}
          <div>
            <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-2">Rezultate</div>
            <ResultsGrid r={r} />

            {/* Capital final */}
            {r.final_balance != null && (
              <CapitalSummary start={r.start_balance} final={r.final_balance} />
            )}

            {/* Task 2: Ordine sarite + perioada testata */}
            <div className="mt-2 flex flex-wrap gap-2 text-[10px] text-slate-500">
              {(r.date_from && r.date_to) && (
                <span className="bg-surface border border-surface-border rounded px-2 py-1">
                  📅 Perioadă testată: <strong className="text-slate-300">{r.date_from}</strong> → <strong className="text-slate-300">{r.date_to}</strong>
                </span>
              )}
              {r.skipped_margin != null && r.skipped_margin > 0 && (
                <span className="bg-warn/10 border border-warn/30 rounded px-2 py-1 text-warn">
                  ⚠ {r.skipped_margin} ordine anulate — fonduri insuficiente
                </span>
              )}
              {r.skipped_margin === 0 && (
                <span className="bg-surface border border-surface-border rounded px-2 py-1 text-slate-600">
                  ✓ 0 ordine anulate din lipsă de fonduri
                </span>
              )}
            </div>
          </div>

          {/* Per-symbol */}
          {r.per_symbol && Object.keys(r.per_symbol).length > 0 && (
            <div>
              <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-2">Per simbol</div>
              <div className="overflow-x-auto">
                {(() => {
                  const numMarkets = (r.markets?.length || Object.keys(r.per_symbol).length) + (r.skipped_markets?.length ?? 0);
                  const capitalPerSym = r.start_balance / (numMarkets || 1);
                  return (
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="text-slate-500 border-b border-surface-border">
                          <th className="text-left py-1.5 font-normal">Simbol</th>
                          <th className="text-right py-1.5 font-normal">Trades</th>
                          <th className="text-right py-1.5 font-normal">WR</th>
                          <th className="text-right py-1.5 font-normal">Exp</th>
                          <th className="text-right py-1.5 font-normal">Capital/Simbol</th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(r.per_symbol).map(([sym, v]) => (
                          <tr key={sym} className="border-b border-surface-border/30">
                            <td className="py-1.5 font-mono text-slate-200">{sym}</td>
                            <td className="text-right text-slate-400">{v.trades}</td>
                            <td className="text-right text-slate-400">{fmtPct(v.win_rate)}</td>
                            <td className={`text-right font-mono ${expColor(v.expectancy)}`}>{fmtR(v.expectancy)}</td>
                            <td className="text-right font-mono text-slate-400">
                              {capitalPerSym.toLocaleString("ro-RO", { maximumFractionDigits: 0 })} $
                            </td>
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
                            <td className="text-right text-slate-600">—</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  );
                })()}
              </div>
              {r.skipped_markets && r.skipped_markets.length > 0 && (
                <p className="text-[10px] text-slate-500 mt-1.5">
                  ⚠ {r.skipped_markets.join(", ")} — date CSV lipsă sau insuficiente (&lt;100 bare).
                  Descarcă datele din Profile → sesiune → Rulează Backtest → Descarcă date din MT5.
                </p>
              )}
            </div>
          )}

          {/* Direction stats LONG/SHORT — doar pentru sesiuni BOTH */}
          {r.direction_stats && Object.keys(r.direction_stats).length === 2 && (
            <div>
              <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-2">
                Statistici per direcție (BOTH)
              </div>
              <div className="grid grid-cols-2 gap-3">
                {(["LONG", "SHORT"] as const).map(dir => {
                  const s = r.direction_stats![dir];
                  if (!s) return null;
                  const isLong = dir === "LONG";
                  return (
                    <div key={dir} className="bg-surface rounded-lg border border-surface-border p-3 space-y-2">
                      <div className={`text-xs font-semibold ${isLong ? "text-profit" : "text-loss"}`}>
                        {isLong ? "▲ LONG" : "▼ SHORT"}
                      </div>
                      <div className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-[11px]">
                        <div className="flex justify-between">
                          <span className="text-slate-500">Trades</span>
                          <span className="font-mono text-white">{s.trades}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-slate-500">Win Rate</span>
                          <span className="font-mono text-white">{s.win_rate.toFixed(1)}%</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-slate-500">Câștiguri</span>
                          <span className="font-mono text-profit">{s.wins}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-slate-500">Pierderi</span>
                          <span className="font-mono text-loss">{s.losses}</span>
                        </div>
                        <div className="col-span-2 flex justify-between border-t border-surface-border/40 pt-1.5">
                          <span className="text-slate-500">Expectancy</span>
                          <span className={`font-mono ${s.expectancy >= 0 ? "text-profit" : "text-loss"}`}>
                            {s.expectancy >= 0 ? "+" : ""}{s.expectancy.toFixed(3)}R
                          </span>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Task 4: Analiza pierderi per zi/ora */}
          {(r.weekday_stats || r.hour_stats) && (
            <LossAnalysis weekday={r.weekday_stats} hour={r.hour_stats} />
          )}

          {/* Meta */}
          <div className="text-[10px] text-slate-600 border-t border-surface-border/40 pt-2">
            Rulat: {fmtTs(job.started_at)}
            {dur && ` · Durată: ${dur}`}
            {r.split_date && ` · Split: ${r.split_date}`}
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

// ── Download job row ─────────────────────────────────────────────────────────

function dlStatusDot(status: DownloadJob["status"]) {
  if (status === "running" || status === "pending")
    return <span className="w-2 h-2 rounded-full bg-blue-400 animate-pulse flex-shrink-0" />;
  if (status === "error")
    return <span className="w-2 h-2 rounded-full bg-loss flex-shrink-0" />;
  return <span className="w-2 h-2 rounded-full bg-profit flex-shrink-0" />;
}

function DownloadJobRow({ job, onDelete }: { job: DownloadJob; onDelete: (id: string) => void }) {
  const [expanded, setExpanded] = useState(false);
  const isActive  = job.status === "pending" || job.status === "running";
  const anyFailed = job.results.some(r => !r.success);
  const allOk     = job.results.length > 0 && job.results.every(r => r.success);
  const dur       = duration(job.started_at, job.completed_at);

  return (
    <div className="border border-surface-border rounded-xl overflow-hidden">
      {/* Summary row */}
      <div
        className={`flex items-center gap-3 px-4 py-3 transition-colors ${
          !isActive ? "cursor-pointer hover:bg-surface-border/10" : ""
        }`}
        onClick={() => !isActive && setExpanded(e => !e)}
      >
        {/* Expand chevron */}
        <span className="text-slate-500 flex-shrink-0 w-4">
          {!isActive && (
            expanded
              ? <ChevronDown size={14} />
              : <ChevronRight size={14} />
          )}
        </span>

        {dlStatusDot(job.status)}

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs font-medium text-white truncate">{job.label}</span>
            <span className="text-[10px] text-slate-500">{job.timeframes.join("+")}</span>
          </div>
          {isActive && (
            <span className="text-[10px] text-blue-400">descărcare în progres...</span>
          )}
          {job.status === "error" && job.error && (
            <span className="text-[10px] text-loss">{job.error}</span>
          )}
          {job.status === "done" && (
            <span className={`text-[10px] ${allOk ? "text-profit" : anyFailed ? "text-warn" : "text-slate-500"}`}>
              {allOk
                ? `${job.results.length} fișiere descărcate`
                : `${job.results.filter(r => r.success).length}/${job.results.length} fișiere OK${job.any_needs_scroll ? " · unele necesită scroll MT5" : ""}`
              }
            </span>
          )}
        </div>

        <div className="flex items-center gap-2 text-[10px] text-slate-600 flex-shrink-0">
          {dur && <span>{dur}</span>}
          <span>{fmtTs(job.started_at)}</span>
          {!isActive && (
            <button
              onClick={(e) => { e.stopPropagation(); if (confirm("Șterge această descărcare din audit?")) onDelete(job.job_id); }}
              className="p-1 text-slate-600 hover:text-loss transition-colors rounded"
            >
              <Trash2 size={12} />
            </button>
          )}
        </div>
      </div>

      {/* Expanded results */}
      {expanded && job.results.length > 0 && (
        <div className="border-t border-surface-border/40 px-4 py-3 space-y-2">
          {/* Group by symbol */}
          {Array.from(new Set(job.results.map(r => r.symbol))).map(sym => {
            const rows: DownloadFileResult[] = job.results.filter(r => r.symbol === sym);
            const mt5sym = rows.find(r => r.mt5_symbol)?.mt5_symbol;
            const alias = mt5sym && mt5sym !== sym ? mt5sym : null;
            return (
              <div key={sym} className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-medium text-slate-300">{sym}</span>
                  {alias && (
                    <span className="text-[10px] text-slate-500 bg-surface-border/40 rounded px-1.5 py-0.5">
                      MT5: {alias}
                    </span>
                  )}
                  {rows.every(r => r.error?.includes("nu există")) && (
                    <span className="text-[10px] text-loss">simbol inexistent în MT5</span>
                  )}
                </div>
                {rows.map((r, i) => (
                  <div key={i} className="flex flex-col gap-0.5 text-xs pl-3">
                    <div className="flex items-center gap-2">
                      <span className={r.success ? "text-profit" : r.needs_scroll ? "text-warn" : "text-loss"}>
                        {r.success ? "✓" : r.needs_scroll ? "⚠" : "✗"}
                      </span>
                      <span className="text-slate-500 font-mono">{r.tf}</span>
                      {r.success
                        ? <span className="text-slate-400">{r.bars.toLocaleString()} bare</span>
                        : <span className="text-slate-500 italic">{r.error}</span>
                      }
                    </div>
                    {/* Task 1: sugestii simbol broker */}
                    {!r.success && !r.needs_scroll && (r as DownloadFileResult & { suggestions?: string[] }).suggestions?.length ? (
                      <div className="pl-5 text-[10px] text-blue-400">
                        Disponibile la broker: {(r as DownloadFileResult & { suggestions?: string[] }).suggestions!.join(", ")}
                      </div>
                    ) : null}
                  </div>
                ))}
              </div>
            );
          })}

          {job.any_needs_scroll && (
            <div className="mt-2 p-2.5 rounded-lg bg-warn/10 border border-warn/30 text-xs text-warn">
              ⚠ Unele timeframe-uri nu au date — deschide MT5, derulează graficul complet spre stânga,
              apoi reîncearcă descărcarea din Profile.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export function AuditPage({ onApplyConfig }: { onApplyConfig?: (sessionId: string, config: Record<string, unknown>) => void }) {
  const { data: jobs, isLoading } = useBacktestJobs();
  const deleteJob = useDeleteBacktestJob();
  const [errorJob, setErrorJob] = useState<BacktestJob | null>(null);
  const [search, setSearch]     = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const { data: dlJobs } = useDownloadJobs();
  const deleteDlJob = useDeleteDownloadJob();

  const dlRunning = dlJobs?.filter(j => j.status === "pending" || j.status === "running") ?? [];
  const dlDone    = dlJobs?.filter(j => j.status !== "pending" && j.status !== "running") ?? [];

  // Filtrare backtest jobs dupa search
  const filteredJobs = useMemo(() => {
    if (!jobs) return [];
    if (!search.trim()) return jobs;
    const q = search.toLowerCase();
    return jobs.filter(j =>
      j.session_label.toLowerCase().includes(q) ||
      j.markets.some(m => m.toLowerCase().includes(q)) ||
      j.direction.toLowerCase().includes(q) ||
      j.entry_tf.toLowerCase().includes(q)
    );
  }, [jobs, search]);

  const running = filteredJobs.filter(j => j.status === "pending" || j.status === "running");
  const done    = filteredJobs.filter(j => j.status === "done");
  const error   = filteredJobs.filter(j => j.status === "error");

  // Multi-select helpers
  const donePlusError = [...done, ...error];
  const allDoneIds    = donePlusError.map(j => j.job_id);
  const allSelected   = allDoneIds.length > 0 && allDoneIds.every(id => selected.has(id));

  function toggleSelect(id: string) {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  function toggleSelectAll() {
    if (allSelected) {
      setSelected(new Set());
    } else {
      setSelected(new Set(allDoneIds));
    }
  }

  async function deleteSelected() {
    if (selected.size === 0) return;
    if (!confirm(`Șterge ${selected.size} joburi selectate din audit?`)) return;
    for (const id of Array.from(selected)) {
      await deleteJob.mutateAsync(id).catch(() => {});
    }
    setSelected(new Set());
  }

  const handleDelete = (id: string) => {
    if (confirm("Șterge acest job din audit?")) {
      deleteJob.mutate(id);
      setSelected(prev => { const n = new Set(prev); n.delete(id); return n; });
    }
  };

  return (
    <>
      {errorJob && (
        <ErrorModal job={errorJob} onClose={() => setErrorJob(null)} />
      )}

      <div className="p-4 md:p-6 space-y-8">

        {/* ── Descărcări date ── */}
        {(dlJobs && dlJobs.length > 0) && (
          <section className="space-y-3">
            <div className="flex items-center gap-3">
              <Download size={16} className="text-blue-400" />
              <h2 className="text-sm font-semibold text-white">Descărcări Date</h2>
              <span className="text-xs text-slate-500 bg-surface-card border border-surface-border rounded-full px-2 py-0.5">
                {dlJobs.length} total
              </span>
              {dlRunning.length > 0 && (
                <span className="flex items-center gap-1.5 text-xs text-blue-400 bg-blue-500/10 border border-blue-500/30 rounded-full px-2.5 py-0.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse" />
                  {dlRunning.length} în curs
                </span>
              )}
            </div>

            <div className="space-y-2">
              {dlRunning.map(job => (
                <DownloadJobRow key={job.job_id} job={job} onDelete={(id) => deleteDlJob.mutate(id)} />
              ))}
              {dlDone.map(job => (
                <DownloadJobRow key={job.job_id} job={job} onDelete={(id) => deleteDlJob.mutate(id)} />
              ))}
            </div>
          </section>
        )}

        {/* ── Backteste ── */}
        <section className="space-y-3">
          {/* Header + search + bulk actions */}
          <div className="flex items-center gap-3 flex-wrap">
            <ClipboardList size={16} className="text-blue-400 flex-shrink-0" />
            <h2 className="text-sm font-semibold text-white">Backteste</h2>
            {jobs && jobs.length > 0 && (
              <span className="text-xs text-slate-500 bg-surface-card border border-surface-border rounded-full px-2 py-0.5">
                {filteredJobs.length}{search ? ` / ${jobs.length}` : ""} total
              </span>
            )}
            {running.length > 0 && (
              <span className="flex items-center gap-1.5 text-xs text-blue-400 bg-blue-500/10 border border-blue-500/30 rounded-full px-2.5 py-0.5">
                <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse" />
                {running.length} în rulare
              </span>
            )}

            {/* Search */}
            <div className="relative ml-auto flex-shrink-0 min-w-[160px]">
              <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none" />
              <input
                type="text"
                placeholder="Caută sesiune, piață..."
                value={search}
                onChange={e => setSearch(e.target.value)}
                className="w-full pl-7 pr-2 py-1.5 text-xs bg-surface-card border border-surface-border rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-blue-500/50"
              />
              {search && (
                <button
                  onClick={() => setSearch("")}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-500 hover:text-white"
                >
                  <X size={11} />
                </button>
              )}
            </div>
          </div>

          {/* Bulk select controls */}
          {donePlusError.length > 0 && (
            <div className="flex items-center gap-3 px-1">
              <button
                onClick={toggleSelectAll}
                className="flex items-center gap-1.5 text-[10px] text-slate-400 hover:text-white transition-colors"
              >
                {allSelected
                  ? <CheckSquare size={13} className="text-blue-400" />
                  : <Square size={13} />
                }
                {allSelected ? "Deselectează tot" : "Selectează tot"}
              </button>
              {selected.size > 0 && (
                <button
                  onClick={deleteSelected}
                  className="flex items-center gap-1.5 text-[10px] text-loss hover:text-loss/80 bg-loss/10 border border-loss/30 rounded-lg px-2.5 py-1 transition-colors"
                >
                  <Trash2 size={11} />
                  Șterge {selected.size} selectate
                </button>
              )}
              {selected.size > 0 && (
                <button
                  onClick={() => setSelected(new Set())}
                  className="text-[10px] text-slate-500 hover:text-slate-300 transition-colors"
                >
                  Anulează selecția
                </button>
              )}
            </div>
          )}

          {/* Loading */}
          {isLoading ? (
            <div className="space-y-2">
              {[...Array(3)].map((_, i) => (
                <div key={i} className="h-14 rounded-xl bg-surface-card animate-pulse" />
              ))}
            </div>
          ) : (jobs ?? []).length === 0 ? (
            <div className="text-center py-10 text-slate-500">
              <ClipboardList size={28} className="mx-auto mb-3 opacity-30" />
              <p className="text-sm">Niciun backtest în audit</p>
              <p className="text-xs mt-1 text-slate-600">
                Rulează un backtest din tab-ul Profile → sesiune → Rulează Backtest
              </p>
            </div>
          ) : filteredJobs.length === 0 ? (
            <div className="text-center py-8 text-slate-500">
              <Search size={24} className="mx-auto mb-2 opacity-30" />
              <p className="text-sm">Niciun rezultat pentru „{search}"</p>
            </div>
          ) : (
            <div className="space-y-6">
              {running.length > 0 && (
                <div className="space-y-2">
                  <div className="text-[10px] text-slate-500 uppercase tracking-wider font-medium">
                    In rulare ({running.length})
                  </div>
                  {running.map(job => (
                    <JobRow key={job.job_id} job={job} onDelete={handleDelete} onShowError={setErrorJob} onApplyConfig={onApplyConfig} />
                  ))}
                </div>
              )}
              {error.length > 0 && (
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-slate-500 uppercase tracking-wider font-medium">
                      Erori ({error.length})
                    </span>
                  </div>
                  {error.map(job => (
                    <div key={job.job_id} className="flex items-start gap-2">
                      <button
                        onClick={() => toggleSelect(job.job_id)}
                        className="mt-3.5 flex-shrink-0 text-slate-500 hover:text-blue-400 transition-colors"
                      >
                        {selected.has(job.job_id)
                          ? <CheckSquare size={14} className="text-blue-400" />
                          : <Square size={14} />
                        }
                      </button>
                      <div className="flex-1 min-w-0">
                        <JobRow job={job} onDelete={handleDelete} onShowError={setErrorJob} onApplyConfig={onApplyConfig} />
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {done.length > 0 && (
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-slate-500 uppercase tracking-wider font-medium">
                      Finalizate ({done.length})
                    </span>
                  </div>
                  {done.map(job => (
                    <div key={job.job_id} className="flex items-start gap-2">
                      <button
                        onClick={() => toggleSelect(job.job_id)}
                        className="mt-3.5 flex-shrink-0 text-slate-500 hover:text-blue-400 transition-colors"
                      >
                        {selected.has(job.job_id)
                          ? <CheckSquare size={14} className="text-blue-400" />
                          : <Square size={14} />
                        }
                      </button>
                      <div className="flex-1 min-w-0">
                        <JobRow job={job} onDelete={handleDelete} onShowError={setErrorJob} onApplyConfig={onApplyConfig} />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </section>

      </div>
    </>
  );
}
