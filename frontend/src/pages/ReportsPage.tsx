import React, { useState } from "react";
import {
  BarChart2, TrendingUp, TrendingDown, Clock, Settings,
  Filter, ChevronDown, ChevronRight, Trophy, Target, Minus,
  Terminal, AlertTriangle, AlertCircle, Info, RefreshCw, DollarSign,
  Send, Calendar, Download,
} from "lucide-react";
import {
  useTransactions, useMarketStats, useBotUptime, useSessionChanges,
  useSystemLogs, useLogSessions, useCosts, useCostsDaily,
  useMt5Transactions, useMt5MarketStats, useMt5Costs, useMt5CostsDaily,
} from "../api/hooks";
import { apiFetch } from "../api/client";
import type { Transaction, MarketStat, UptimeEntry, SessionChangeEntry, SystemLogEntry, CostStat, CostsDayEntry, Mt5Transaction } from "../api/types";
import { useStatsSource, type StatsSource } from "../hooks/useStatsSource";
import { SourceToggle } from "../components/SourceToggle";

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtR(v: number | null | undefined) {
  if (v == null) return "—";
  return `${v >= 0 ? "+" : ""}${v.toFixed(3)}R`;
}

function fmtPct(v: number) {
  return `${v.toFixed(1)}%`;
}

function fmtUsd(v: number | null) {
  if (v == null) return "—";
  const sign = v >= 0 ? "+" : "";
  return `${sign}${v.toLocaleString("ro-RO", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} $`;
}

function fmtDuration(sec: number | null | undefined) {
  if (!sec) return "—";
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  if (h > 24) return `${Math.floor(h / 24)}z ${h % 24}h`;
  if (h > 0)  return `${h}h ${m}m`;
  return `${m}m`;
}

function fmtTime(iso: string) {
  const d = new Date(iso);
  return d.toLocaleString("ro-RO", {
    day: "2-digit", month: "short", year: "2-digit",
    hour: "2-digit", minute: "2-digit",
  });
}

function rColor(v: number) {
  return v > 0 ? "text-profit" : v < 0 ? "text-loss" : "text-slate-400";
}

const STATUS_LABELS: Record<string, string> = {
  TP:           "TP",
  SL:           "SL",
  open:         "Deschis",
  expirat:      "Expirat",
  invalidat:    "Invalidat",
  vineri_close: "Vineri",
  news_close:   "Știri",
  ai_reject:    "Respins AI",
};

// ── Transactions table ────────────────────────────────────────────────────────

const STATUS_FILTERS_BOT = ["Toate", "TP", "SL", "Deschis", "Expirat", "Vineri", "Știri", "Respins AI"];
const STATUS_FILTERS_MT5 = ["Toate", "TP", "SL"];
const STATUS_MAP: Record<string, string> = {
  "Toate":      "",
  "TP":         "TP",
  "SL":         "SL",
  "Deschis":    "open",
  "Expirat":    "expirat",
  "Vineri":     "vineri_close",
  "Știri":      "news_close",
  "Respins AI": "ai_reject",
};

// Vedere unificata pentru randare — Bot are sesiune/timp-check, MT5 are doar ticket.
interface ViewTxn {
  key: string;
  symbol: string;
  sessionLabel: string | null;
  direction: number;
  dirStr: string;
  status: string;
  entry: number;
  rRatio: number | null;
  resultR: number;
  pnlUsd: number | null;
  time: string | null;
  aiApproved: boolean | null;
  aiConfidence: number | null;
}
const toViewTxn = (t: Transaction, i: number): ViewTxn => ({
  key: `${t.signal_id}-${i}`, symbol: t.symbol, sessionLabel: t.session_label.replace(/^S\d+ — /, ""),
  direction: t.direction, dirStr: t.dir_str, status: t.status, entry: t.entry,
  rRatio: t.r_ratio, resultR: t.result_r, pnlUsd: t.pnl_usd,
  time: t.exit_time ?? t.time_check ?? null,
  aiApproved: t.ai_approved ?? null, aiConfidence: t.ai_confidence ?? null,
});
const toViewMt5Txn = (t: Mt5Transaction): ViewTxn => ({
  key: String(t.ticket), symbol: t.symbol, sessionLabel: null,
  direction: t.direction, dirStr: t.dir_str, status: t.status, entry: t.entry,
  rRatio: t.r_ratio, resultR: t.result_r ?? 0, pnlUsd: t.pnl_usd,
  time: t.exit_time ?? t.entry_time,
  aiApproved: null, aiConfidence: null,
});

function TransactionsTab({ source }: { source: StatsSource }) {
  const usingMt5 = source === "mt5";
  const [statusFilter, setStatusFilter] = useState("Toate");
  const [dirFilter,    setDirFilter]    = useState<"" | "LONG" | "SHORT">("");
  const [dateFrom,     setDateFrom]     = useState("");
  const [dateTo,       setDateTo]       = useState("");
  const [page,         setPage]         = useState(0);
  const PER_PAGE = 50;

  const botQuery = useTransactions({
    status:    !usingMt5 ? (STATUS_MAP[statusFilter] || undefined) : undefined,
    direction: !usingMt5 ? (dirFilter || undefined) : undefined,
    date_from: dateFrom || undefined,
    date_to:   dateTo   || undefined,
    limit:     PER_PAGE,
    offset:    page * PER_PAGE,
  });

  // Descarcare CSV — sursa curenta (Bot = outcomes.csv / MT5 = cont-wide), fara paginare.
  function downloadCsv() {
    const qs = new URLSearchParams();
    const st = STATUS_MAP[statusFilter];
    if (st)        qs.set("status", st);
    if (dirFilter) qs.set("direction", dirFilter);
    if (dateFrom)  qs.set("date_from", dateFrom);
    if (dateTo)    qs.set("date_to", dateTo);
    const path = usingMt5 ? "/mt5/transactions.csv" : "/reports/transactions.csv";
    window.open(`http://localhost:8000/api${path}?${qs.toString()}`, "_blank");
  }
  const mt5Query = useMt5Transactions({
    status:    usingMt5 ? (STATUS_MAP[statusFilter] || undefined) : undefined,
    direction: usingMt5 ? (dirFilter || undefined) : undefined,
    limit:     PER_PAGE,
    offset:    page * PER_PAGE,
  });

  const isLoading = usingMt5 ? mt5Query.isLoading : botQuery.isLoading;
  const total = usingMt5 ? (mt5Query.data?.total ?? 0) : (botQuery.data?.total ?? 0);
  const items: ViewTxn[] = usingMt5
    ? (mt5Query.data?.items ?? []).map(toViewMt5Txn)
    : (botQuery.data?.items ?? []).map(toViewTxn);
  const pages = Math.ceil(total / PER_PAGE);
  const statusFilters = usingMt5 ? STATUS_FILTERS_MT5 : STATUS_FILTERS_BOT;

  function fmt(entry: number) {
    const decimals = entry > 100 ? 2 : 5;
    return entry.toFixed(decimals);
  }

  return (
    <div className="space-y-4">
      {usingMt5 && mt5Query.data && !mt5Query.data.connected && (
        <div className="text-[11px] text-warn/80 bg-warn/10 border border-warn/30 rounded-lg px-3 py-2">
          MT5 neconectat — {mt5Query.data.error ?? "tranzacțiile directe nu sunt disponibile"}. Comută pe „Bot" pentru date din outcomes.csv.
        </div>
      )}

      {/* Filters */}
      <div className="flex items-center gap-3 flex-wrap">
        <Filter size={13} className="text-slate-500 flex-shrink-0" />
        <div className="flex gap-1 flex-wrap">
          {statusFilters.map(f => (
            <button
              key={f}
              onClick={() => { setStatusFilter(f); setPage(0); }}
              className={`text-[10px] px-2.5 py-1 rounded-lg transition-colors ${
                statusFilter === f
                  ? "bg-blue-500/20 text-blue-400 border border-blue-500/30 font-medium"
                  : "text-slate-500 hover:text-slate-300 border border-transparent"
              }`}
            >
              {f}
            </button>
          ))}
        </div>
        <div className="flex gap-1 ml-2">
          {(["", "LONG", "SHORT"] as const).map(d => (
            <button
              key={d || "all"}
              onClick={() => { setDirFilter(d); setPage(0); }}
              className={`text-[10px] px-2.5 py-1 rounded-lg transition-colors ${
                dirFilter === d
                  ? d === "LONG"  ? "bg-profit/20 text-profit border border-profit/30 font-medium"
                  : d === "SHORT" ? "bg-loss/20 text-loss border border-loss/30 font-medium"
                  : "bg-blue-500/20 text-blue-400 border border-blue-500/30 font-medium"
                  : "text-slate-500 hover:text-slate-300 border border-transparent"
              }`}
            >
              {d || "Ambele"}
            </button>
          ))}
        </div>
        {/* Interval de date + export CSV */}
        <div className="flex items-center gap-1.5 ml-2">
          <input type="date" value={dateFrom}
            onChange={e => { setDateFrom(e.target.value); setPage(0); }}
            title="De la data (inclusiv)"
            className="bg-surface border border-surface-border rounded px-1.5 py-0.5 text-[10px] text-slate-300" />
          <span className="text-slate-600 text-[10px]">→</span>
          <input type="date" value={dateTo}
            onChange={e => { setDateTo(e.target.value); setPage(0); }}
            title="Până la data (inclusiv)"
            className="bg-surface border border-surface-border rounded px-1.5 py-0.5 text-[10px] text-slate-300" />
          {(dateFrom || dateTo) && (
            <button onClick={() => { setDateFrom(""); setDateTo(""); setPage(0); }}
              className="text-[10px] text-slate-500 hover:text-slate-300 px-1" title="Șterge intervalul">✕</button>
          )}
        </div>
        <button onClick={downloadCsv}
          title={usingMt5
            ? "Exportă tranzacțiile MT5 (cont-wide: bot + AI + manual) cu filtrele curente"
            : "Exportă tranzacțiile botului (outcomes.csv) cu filtrele curente"}
          className="flex items-center gap-1 text-[10px] px-2.5 py-1 rounded-lg border border-surface-border text-slate-300 hover:border-blue-500/40 hover:text-blue-400 transition-colors">
          <Download size={12} /> CSV{usingMt5 ? " (MT5)" : ""}
        </button>
        <span className="text-[10px] text-slate-500">{total} tranzacții</span>
      </div>

      {/* Table */}
      {isLoading ? (
        <div className="space-y-1">
          {[...Array(8)].map((_, i) => (
            <div key={i} className="h-10 rounded-lg bg-surface-card animate-pulse" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <div className="text-center py-16 text-slate-500">
          <BarChart2 size={32} className="mx-auto mb-3 opacity-30" />
          <p>Nicio tranzacție găsită</p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-surface-border">
          <table className="w-full text-[11px]">
            <thead>
              <tr className="border-b border-surface-border bg-surface-card">
                <th className="text-left px-3 py-2 text-slate-500 font-medium">Simbol</th>
                {!usingMt5 && <th className="text-left px-3 py-2 text-slate-500 font-medium">Sesiune</th>}
                <th className="text-center px-3 py-2 text-slate-500 font-medium">Dir</th>
                <th className="text-right px-3 py-2 text-slate-500 font-medium">Entry</th>
                <th className="text-center px-3 py-2 text-slate-500 font-medium">Status</th>
                <th className="text-right px-3 py-2 text-slate-500 font-medium">R/R</th>
                <th className="text-right px-3 py-2 text-slate-500 font-medium">Rezultat</th>
                <th className="text-right px-3 py-2 text-slate-500 font-medium">P&L $</th>
                <th className="text-right px-3 py-2 text-slate-500 font-medium">Data</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-border/40">
              {items.map((t) => (
                <tr
                  key={t.key}
                  className={`transition-colors hover:bg-surface-border/10 ${
                    t.status === "TP" ? "bg-profit/4" : t.status === "SL" ? "bg-loss/4" : ""
                  }`}
                >
                  <td className="px-3 py-2 font-semibold text-white">
                    {t.symbol}
                    {t.aiApproved && (
                      <span
                        className="ml-1.5 text-[8px] px-1 py-0.5 rounded font-bold bg-purple-500/20 text-purple-300 align-middle"
                        title={`Validat de Filtrul AI Pre-Trade${t.aiConfidence != null ? ` — încredere ${t.aiConfidence}%` : ""}`}
                      >
                        AI✓
                      </span>
                    )}
                  </td>
                  {!usingMt5 && <td className="px-3 py-2 text-slate-400 truncate max-w-[100px]">{t.sessionLabel}</td>}
                  <td className="px-3 py-2 text-center">
                    <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold ${
                      t.direction === 1
                        ? "bg-profit/20 text-profit"
                        : "bg-loss/20 text-loss"
                    }`}>
                      {t.dirStr}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-slate-300">{fmt(t.entry)}</td>
                  <td className="px-3 py-2 text-center">
                    <span className={`text-[9px] font-medium ${
                      t.status === "TP" ? "text-profit"
                      : t.status === "SL" ? "text-loss"
                      : t.status === "ai_reject" ? "text-purple-400"
                      : "text-slate-500"
                    }`}>
                      {STATUS_LABELS[t.status] ?? t.status}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-right text-slate-500 font-mono">{t.rRatio != null ? `${t.rRatio}R` : "—"}</td>
                  <td className={`px-3 py-2 text-right font-mono font-semibold ${rColor(t.resultR)}`}>
                    {fmtR(t.resultR)}
                  </td>
                  <td className={`px-3 py-2 text-right font-mono ${t.pnlUsd != null ? rColor(t.pnlUsd) : "text-slate-600"}`}>
                    {fmtUsd(t.pnlUsd)}
                  </td>
                  <td className="px-3 py-2 text-right text-slate-500">
                    {t.time ? fmtTime(t.time) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination */}
      {pages > 1 && (
        <div className="flex items-center justify-center gap-2">
          <button
            disabled={page === 0}
            onClick={() => setPage(p => p - 1)}
            className="text-[10px] px-3 py-1.5 rounded-lg border border-surface-border text-slate-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            ← Anterior
          </button>
          <span className="text-[10px] text-slate-500">
            {page + 1} / {pages}
          </span>
          <button
            disabled={page >= pages - 1}
            onClick={() => setPage(p => p + 1)}
            className="text-[10px] px-3 py-1.5 rounded-lg border border-surface-border text-slate-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            Următor →
          </button>
        </div>
      )}

      {/* ── OBS sessions (execute=False) — concept specific Bot, fara echivalent MT5 ── */}
      {!usingMt5 && <ObsTransactionsSection />}
    </div>
  );
}

function ObsTransactionsSection() {
  const [open, setOpen] = React.useState(false);
  const { data, isLoading } = useTransactions({ obs_only: true, limit: 200 });
  const items = data?.items ?? [];
  if (!open) {
    return (
      <div className="border-t border-surface-border/50 pt-3">
        <button
          onClick={() => setOpen(true)}
          className="text-[10px] text-slate-500 hover:text-slate-300 flex items-center gap-1.5 transition-colors"
        >
          <span className="w-4 h-4 rounded border border-slate-700 flex items-center justify-center text-[9px]">▶</span>
          Sesiuni OBS (observatie, fara executare) — {data?.total ?? "…"} semnale
        </button>
      </div>
    );
  }
  return (
    <div className="border-t border-surface-border/50 pt-3 space-y-3">
      <div className="flex items-center gap-2">
        <button onClick={() => setOpen(false)} className="text-[10px] text-slate-500 hover:text-slate-300">▼</button>
        <span className="text-[11px] font-semibold text-slate-400">Sesiuni OBS — observatie fara executare reala</span>
        <span className="text-[10px] bg-slate-700/50 text-slate-400 px-2 py-0.5 rounded-full">
          {data?.total ?? 0} semnale · nu apar in statistici
        </span>
      </div>
      {isLoading ? (
        <div className="space-y-1">{[...Array(3)].map((_, i) => <div key={i} className="h-8 rounded bg-surface-card animate-pulse" />)}</div>
      ) : items.length === 0 ? (
        <p className="text-[11px] text-slate-600 py-4 text-center">Niciun semnal OBS înregistrat</p>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-surface-border/50">
          <table className="w-full text-[11px]">
            <thead>
              <tr className="border-b border-surface-border/50 bg-surface-card/50">
                <th className="text-left px-3 py-2 text-slate-600 font-medium">Simbol</th>
                <th className="text-left px-3 py-2 text-slate-600 font-medium">Sesiune</th>
                <th className="text-left px-3 py-2 text-slate-600 font-medium">Status</th>
                <th className="text-right px-3 py-2 text-slate-600 font-medium">R</th>
                <th className="text-left px-3 py-2 text-slate-600 font-medium">Timp ieșire</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-border/30">
              {items.map((t) => (
                <tr key={t.signal_id} className="hover:bg-surface-border/5 transition-colors opacity-70">
                  <td className="px-3 py-2 text-slate-400 font-medium">{t.symbol}</td>
                  <td className="px-3 py-2 text-slate-600 text-[10px]">{t.session_label.replace(/^S\d+ — /, "")}</td>
                  <td className="px-3 py-2 text-slate-500">{t.status}</td>
                  <td className={`px-3 py-2 text-right font-mono ${t.result_r > 0 ? "text-profit/60" : t.result_r < 0 ? "text-loss/60" : "text-slate-600"}`}>
                    {t.result_r > 0 ? "+" : ""}{t.result_r.toFixed(3)}R
                  </td>
                  <td className="px-3 py-2 text-slate-600">{t.exit_time?.slice(0, 16) ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Market stats tab ──────────────────────────────────────────────────────────

function MarketStatsTab({ source }: { source: StatsSource }) {
  const usingMt5 = source === "mt5";
  const botQuery = useMarketStats();
  const mt5Query = useMt5MarketStats();

  const isLoading = usingMt5 ? mt5Query.isLoading : botQuery.isLoading;
  const items: MarketStat[] = usingMt5 ? (mt5Query.data?.items ?? []) : (botQuery.data?.items ?? []);

  const totalTrades = items.reduce((s, m) => s + m.trades, 0);
  const totalR      = items.reduce((s, m) => s + m.total_r, 0);

  return (
    <div className="space-y-4">
      {usingMt5 && mt5Query.data && !mt5Query.data.connected && (
        <div className="text-[11px] text-warn/80 bg-warn/10 border border-warn/30 rounded-lg px-3 py-2">
          MT5 neconectat — {mt5Query.data.error ?? "clasamentul direct nu este disponibil"}. Comută pe „Bot" pentru date din outcomes.csv.
        </div>
      )}

      {/* Summary cards */}
      {items.length > 0 && (
        <div className="grid grid-cols-3 gap-3">
          <div className="bg-surface-card rounded-xl border border-surface-border px-4 py-3">
            <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Piețe active</div>
            <div className="text-2xl font-bold font-mono text-white">{items.length}</div>
          </div>
          <div className="bg-surface-card rounded-xl border border-surface-border px-4 py-3">
            <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Total trades</div>
            <div className="text-2xl font-bold font-mono text-white">{totalTrades}</div>
          </div>
          <div className="bg-surface-card rounded-xl border border-surface-border px-4 py-3">
            <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Total R</div>
            <div className={`text-2xl font-bold font-mono ${rColor(totalR)}`}>{fmtR(totalR)}</div>
          </div>
        </div>
      )}

      {isLoading ? (
        <div className="space-y-2">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-16 rounded-xl bg-surface-card animate-pulse" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <div className="text-center py-16 text-slate-500">
          <Target size={32} className="mx-auto mb-3 opacity-30" />
          <p>Nicio tranzacție live înregistrată</p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-surface-border">
          <table className="w-full text-[11px]">
            <thead>
              <tr className="border-b border-surface-border bg-surface-card">
                <th className="text-left px-4 py-2.5 text-slate-500 font-medium">Simbol</th>
                <th className="text-right px-3 py-2.5 text-slate-500 font-medium">Trades</th>
                <th className="text-right px-3 py-2.5 text-slate-500 font-medium">Win Rate</th>
                <th className="text-right px-3 py-2.5 text-slate-500 font-medium">Expectancy</th>
                <th className="text-right px-3 py-2.5 text-slate-500 font-medium">Total R</th>
                <th className="text-right px-3 py-2.5 text-slate-500 font-medium">P&L $</th>
                {!usingMt5 && <th className="text-left px-3 py-2.5 text-slate-500 font-medium">Sesiuni</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-border/40">
              {items.map((m, i) => (
                <tr key={m.symbol} className="hover:bg-surface-border/10 transition-colors">
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-2">
                      {i === 0 && <Trophy size={11} className="text-yellow-400 flex-shrink-0" />}
                      {i === 1 && <Trophy size={11} className="text-slate-400 flex-shrink-0" />}
                      {i === 2 && <Trophy size={11} className="text-amber-600 flex-shrink-0" />}
                      {i > 2 && <span className="w-4 text-center text-[9px] text-slate-600">{i + 1}</span>}
                      <span className="font-semibold text-white">{m.symbol}</span>
                    </div>
                  </td>
                  <td className="px-3 py-2.5 text-right text-slate-300 font-mono">{m.trades}</td>
                  <td className="px-3 py-2.5 text-right">
                    <span className={m.win_rate >= 50 ? "text-profit font-medium" : "text-slate-400"}>
                      {fmtPct(m.win_rate)}
                    </span>
                  </td>
                  <td className={`px-3 py-2.5 text-right font-mono font-semibold ${rColor(m.expectancy)}`}>
                    {fmtR(m.expectancy)}
                  </td>
                  <td className={`px-3 py-2.5 text-right font-mono font-semibold ${rColor(m.total_r)}`}>
                    {fmtR(m.total_r)}
                  </td>
                  <td className={`px-3 py-2.5 text-right font-mono ${m.pnl_usd != null ? rColor(m.pnl_usd) : "text-slate-600"}`}>
                    {fmtUsd(m.pnl_usd)}
                  </td>
                  {!usingMt5 && (
                    <td className="px-3 py-2.5 text-slate-500 text-[10px] max-w-[140px] truncate">
                      {m.sessions.map(s => s.replace(/^S\d+ — /, "")).join(", ")}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Uptime tab ────────────────────────────────────────────────────────────────

function UptimeTab() {
  const { data, isLoading } = useBotUptime();
  const items = data?.items ?? [];

  // Calcula uptime total din entries
  const totalSec = items.reduce((s, e) => {
    if (e.event === "start" && e.duration_sec) return s + e.duration_sec;
    return s;
  }, 0);

  const sessions = items.filter(e => e.event === "start");

  return (
    <div className="space-y-4">
      {/* Summary */}
      {sessions.length > 0 && (
        <div className="grid grid-cols-2 gap-3">
          <div className="bg-surface-card rounded-xl border border-surface-border px-4 py-3">
            <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Sesiuni totale</div>
            <div className="text-2xl font-bold font-mono text-white">{sessions.length}</div>
          </div>
          <div className="bg-surface-card rounded-xl border border-surface-border px-4 py-3">
            <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Uptime acumulat</div>
            <div className="text-2xl font-bold font-mono text-white">{fmtDuration(totalSec)}</div>
          </div>
        </div>
      )}

      {isLoading ? (
        <div className="space-y-2">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-12 rounded-xl bg-surface-card animate-pulse" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <div className="text-center py-16 text-slate-500">
          <Clock size={32} className="mx-auto mb-3 opacity-30" />
          <p>Nicio sesiune bot înregistrată</p>
          <p className="text-xs mt-1 text-slate-600">Istoricul se populează la pornire/oprire bot.</p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-surface-border">
          <table className="w-full text-[11px]">
            <thead>
              <tr className="border-b border-surface-border bg-surface-card">
                <th className="text-left px-4 py-2.5 text-slate-500 font-medium">Eveniment</th>
                <th className="text-left px-3 py-2.5 text-slate-500 font-medium">Profil</th>
                <th className="text-right px-3 py-2.5 text-slate-500 font-medium">Pornit</th>
                <th className="text-right px-3 py-2.5 text-slate-500 font-medium">Oprit</th>
                <th className="text-right px-3 py-2.5 text-slate-500 font-medium">Durată</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-border/40">
              {items.filter(e => e.event === "start").map((e, i) => (
                <tr key={i} className="hover:bg-surface-border/10 transition-colors">
                  <td className="px-4 py-2.5">
                    <span className="flex items-center gap-1.5 text-profit">
                      <span className="w-2 h-2 rounded-full bg-profit" />
                      Pornit
                    </span>
                  </td>
                  <td className="px-3 py-2.5 text-slate-300">{e.profile || "—"}</td>
                  <td className="px-3 py-2.5 text-right text-slate-400 font-mono">{fmtTime(e.time)}</td>
                  <td className="px-3 py-2.5 text-right text-slate-400 font-mono">
                    {e.stopped_at ? fmtTime(e.stopped_at) : (
                      <span className="text-profit text-[10px]">în rulare</span>
                    )}
                  </td>
                  <td className="px-3 py-2.5 text-right text-slate-300 font-mono">
                    {fmtDuration(e.duration_sec)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Session changes tab ───────────────────────────────────────────────────────

function SessionChangesTab() {
  const { data, isLoading } = useSessionChanges();
  const items = data?.items ?? [];
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const FIELD_LABELS: Record<string, string> = {
    direction: "Direcție",
    entry_tf: "Timeframe intrare",
    trend_tf: "Timeframe trend",
    pullback_window: "Fereastră pullback",
    session_start: "Ore start",
    session_end: "Ore end",
    expire_bars: "Expire bare",
    account_fraction: "Fracție cont",
    risk_pct: "Risc %",
    execute_trades: "Execuție trades",
    rsi_enabled: "RSI",
    rsi_buy_min: "RSI buy min",
    rsi_buy_max: "RSI buy max",
    ema_alignment_enabled: "EMA Alignment",
    r_base: "R Base",
    r_mid: "R Mid",
    r_top: "R Top",
    r_max: "R Max",
    friday_close_enabled: "Închidere Vineri",
    break_even_enabled: "Break-Even",
    news_protection_enabled: "Protecție Știri",
  };

  function labelField(key: string) {
    return FIELD_LABELS[key] ?? key;
  }

  function fmtVal(v: unknown): string {
    if (v === null || v === undefined) return "—";
    if (typeof v === "boolean") return v ? "Da" : "Nu";
    if (typeof v === "number") return String(v);
    if (Array.isArray(v)) return v.join(", ") || "—";
    return String(v);
  }

  return (
    <div className="space-y-3">
      {isLoading ? (
        <div className="space-y-2">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-14 rounded-xl bg-surface-card animate-pulse" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <div className="text-center py-16 text-slate-500">
          <Settings size={32} className="mx-auto mb-3 opacity-30" />
          <p>Nicio modificare sesiune înregistrată</p>
          <p className="text-xs mt-1 text-slate-600">Modificările se înregistrează la salvarea unui profil.</p>
        </div>
      ) : (
        items.map(entry => (
          <div
            key={entry.id}
            className="border border-surface-border rounded-xl overflow-hidden"
          >
            {/* Header */}
            <div
              className="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-surface-border/10 transition-colors"
              onClick={() => setExpandedId(expandedId === entry.id ? null : entry.id)}
            >
              <span className="text-slate-500">
                {expandedId === entry.id ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
              </span>
              <Settings size={13} className="text-blue-400 flex-shrink-0" />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs font-medium text-white">{entry.profile_name}</span>
                  {entry.sessions_changed.length > 0 && (
                    <span className="text-[10px] text-slate-500">
                      {entry.sessions_changed.length} sesiune{entry.sessions_changed.length > 1 ? "i" : ""} modificată
                    </span>
                  )}
                </div>
                <div className="text-[10px] text-slate-500 mt-0.5">
                  {fmtTime(entry.time)}
                </div>
              </div>
              <div className="text-[10px] text-slate-600">
                {entry.sessions_changed.map(s => s.session_id).join(", ")}
              </div>
            </div>

            {/* Expanded */}
            {expandedId === entry.id && entry.sessions_changed.length > 0 && (
              <div className="border-t border-surface-border/40 px-4 py-3 space-y-4">
                {entry.sessions_changed.map(sess => (
                  <div key={sess.session_id}>
                    <div className="text-[10px] font-semibold text-slate-300 mb-2">
                      {sess.session_id} — {sess.markets.join(", ")}
                    </div>
                    <div className="space-y-1">
                      {Object.entries(sess.changes).map(([key, diff]) => (
                        <div key={key} className="grid grid-cols-[180px_1fr_1fr] gap-2 text-[10px]">
                          <span className="text-slate-500">{labelField(key)}</span>
                          <span className="text-loss/80 font-mono">{fmtVal(diff.from)}</span>
                          <span className="text-profit/80 font-mono">→ {fmtVal(diff.to)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))
      )}
    </div>
  );
}

// ── Costs tab ────────────────────────────────────────────────────────────────

function CostsTab({ source }: { source: StatsSource }) {
  const usingMt5 = source === "mt5";
  const botSym  = useCosts();
  const botDay  = useCostsDaily();
  const mt5Sym  = useMt5Costs();
  const mt5Day  = useMt5CostsDaily();

  const loadSym = usingMt5 ? mt5Sym.isLoading : botSym.isLoading;
  const loadDay = usingMt5 ? mt5Day.isLoading : botDay.isLoading;
  const perDay  = usingMt5 ? mt5Day.data : botDay.data;

  const symItems: CostStat[]   = usingMt5 ? (mt5Sym.data?.items ?? []) : (botSym.data?.items ?? []);
  const dayItems: CostsDayEntry[] = perDay?.items ?? [];

  const totalComm  = perDay?.total_commission ?? 0;
  const totalSwap  = perDay?.total_swap ?? 0;
  const totalCosts = perDay?.total_costs ?? 0;
  const hasAnyData = dayItems.some(d => d.has_cost_data);
  const mt5NotConnected = usingMt5 && mt5Sym.data && !mt5Sym.data.connected;

  // Zile cu date de cost (pentru bara vizuala)
  const maxCost = Math.max(...dayItems.map(d => Math.abs(d.total_costs)), 0.01);

  const fmtMoney = (v: number, showPlus = true) => {
    const sign = v > 0 && showPlus ? "+" : "";
    return `${sign}${v.toLocaleString("ro-RO", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} $`;
  };

  const MoneyCell = ({ v, dimZero = true }: { v: number; dimZero?: boolean }) => {
    if (v === 0 && dimZero) return <span className="text-slate-600">0,00 $</span>;
    return <span className={v < 0 ? "text-loss" : v > 0 ? "text-profit" : "text-slate-400"}>{fmtMoney(v)}</span>;
  };

  const fmtDate = (s: string) => {
    const d = new Date(s);
    return d.toLocaleDateString("ro-RO", { day: "2-digit", month: "short" });
  };

  if (loadSym || loadDay) {
    return (
      <div className="space-y-2">
        {[...Array(6)].map((_, i) => (
          <div key={i} className="h-12 rounded-xl bg-surface-card animate-pulse" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-6">

      {mt5NotConnected && (
        <div className="text-[11px] text-warn/80 bg-warn/10 border border-warn/30 rounded-lg px-3 py-2">
          MT5 neconectat — {mt5Sym.data?.error ?? "costurile directe nu sunt disponibile"}. Comută pe „Bot" pentru date din outcomes.csv.
        </div>
      )}

      {/* ── 1. Summary totals ─────────────────────────────────────────── */}
      <div className="grid grid-cols-3 gap-3">
        <div className="bg-surface-card border border-surface-border rounded-xl p-4">
          <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Comisioane broker</div>
          <div className={`text-xl font-bold font-mono ${totalComm < 0 ? "text-loss" : "text-slate-300"}`}>
            {fmtMoney(totalComm)}
          </div>
          <div className="text-[10px] text-slate-600 mt-1">plătit la broker per lot închis</div>
        </div>
        <div className="bg-surface-card border border-surface-border rounded-xl p-4">
          <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Swap overnight</div>
          <div className={`text-xl font-bold font-mono ${totalSwap < 0 ? "text-loss" : "text-profit"}`}>
            {fmtMoney(totalSwap, true)}
          </div>
          <div className="text-[10px] text-slate-600 mt-1">
            {totalSwap >= 0 ? "pozitiv = primit de la broker" : "negativ = plătit la broker"}
          </div>
        </div>
        <div className="bg-surface-card border border-surface-border rounded-xl p-4">
          <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Cost total net</div>
          <div className={`text-xl font-bold font-mono ${totalCosts < 0 ? "text-loss" : "text-slate-300"}`}>
            {fmtMoney(totalCosts)}
          </div>
          <div className="text-[10px] text-slate-600 mt-1">comisioane + swap</div>
        </div>
      </div>

      {/* ── 2. Daily timeline ─────────────────────────────────────────── */}
      <div>
        <div className="flex items-center gap-2 mb-3">
          <span className="text-[11px] font-semibold text-slate-300">Evoluție Zilnică</span>
          <span className="text-[10px] text-slate-600">
            {dayItems.length > 0 ? `din ${fmtDate(dayItems[0].date)} până azi` : ""}
          </span>
          {!hasAnyData && (
            <span className="text-[10px] text-warn ml-1">Date MT5 indisponibile — apar după prima închidere de ordin real</span>
          )}
        </div>
        <div className="overflow-x-auto rounded-xl border border-surface-border">
          <table className="w-full text-[11px]">
            <thead>
              <tr className="border-b border-surface-border bg-surface-card">
                <th className="text-left px-3 py-2 text-slate-500 font-medium w-24">Data</th>
                <th className="text-right px-3 py-2 text-slate-500 font-medium">Trades</th>
                <th className="text-right px-3 py-2 text-slate-500 font-medium">Cu date</th>
                <th className="text-right px-3 py-2 text-slate-500 font-medium">Comisioane</th>
                <th className="text-right px-3 py-2 text-slate-500 font-medium">Swap</th>
                <th className="text-right px-3 py-2 text-slate-500 font-medium">Cost total</th>
                <th className="text-right px-3 py-2 text-slate-500 font-medium">P&L USD</th>
                <th className="text-right px-3 py-2 text-slate-500 font-medium">R total</th>
                <th className="px-3 py-2 text-slate-500 font-medium w-28">Cost vizual</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-border/40">
              {[...dayItems].reverse().map(row => {
                const today = new Date().toISOString().slice(0, 10);
                const isToday = row.date === today;
                const barPct  = row.has_cost_data
                  ? Math.round(Math.min(Math.abs(row.total_costs) / maxCost * 100, 100))
                  : 0;
                return (
                  <tr key={row.date} className={`hover:bg-surface-border/10 transition-colors ${isToday ? "bg-blue-500/5" : ""}`}>
                    <td className="px-3 py-2.5 text-slate-300 font-medium">
                      {fmtDate(row.date)}
                      {isToday && <span className="ml-1 text-[9px] text-blue-400">azi</span>}
                    </td>
                    <td className="px-3 py-2.5 text-right text-slate-400">{row.trades}</td>
                    <td className="px-3 py-2.5 text-right">
                      {row.has_cost_data
                        ? <span className="text-slate-300">{row.trades_with_cost}</span>
                        : <span className="text-slate-600">—</span>}
                    </td>
                    <td className="px-3 py-2.5 text-right">
                      {row.has_cost_data && row.commission_usd !== 0
                        ? <MoneyCell v={row.commission_usd} />
                        : <span className="text-slate-600">—</span>}
                    </td>
                    <td className="px-3 py-2.5 text-right">
                      {row.has_cost_data && row.swap_usd !== 0
                        ? <MoneyCell v={row.swap_usd} />
                        : <span className="text-slate-600">—</span>}
                    </td>
                    <td className="px-3 py-2.5 text-right font-semibold">
                      {row.has_cost_data
                        ? <MoneyCell v={row.total_costs} dimZero={false} />
                        : <span className="text-slate-600">—</span>}
                    </td>
                    <td className="px-3 py-2.5 text-right">
                      {row.pnl_usd != null
                        ? <MoneyCell v={row.pnl_usd} />
                        : <span className="text-slate-600">—</span>}
                    </td>
                    <td className="px-3 py-2.5 text-right">
                      {row.total_r != null
                        ? <span className={row.total_r >= 0 ? "text-profit" : "text-loss"}>
                            {row.total_r > 0 ? "+" : ""}{row.total_r.toFixed(2)}R
                          </span>
                        : <span className="text-slate-600">—</span>}
                    </td>
                    <td className="px-3 py-2.5">
                      {row.has_cost_data && barPct > 0 ? (
                        <div className="flex items-center gap-1">
                          <div className="flex-1 h-2 rounded-full bg-surface-border overflow-hidden">
                            <div
                              className={`h-full rounded-full ${row.total_costs < 0 ? "bg-loss/60" : "bg-profit/60"}`}
                              style={{ width: `${barPct}%` }}
                            />
                          </div>
                        </div>
                      ) : (
                        <span className="text-slate-700 text-[9px]">fără date</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
            {dayItems.length > 0 && hasAnyData && (
              <tfoot>
                <tr className="border-t-2 border-surface-border bg-surface-card/80 font-semibold">
                  <td className="px-3 py-2.5 text-slate-400 text-[10px]">TOTAL</td>
                  <td className="px-3 py-2.5 text-right text-slate-400">
                    {dayItems.reduce((s, d) => s + d.trades, 0)}
                  </td>
                  <td className="px-3 py-2.5 text-right text-slate-400">
                    {dayItems.reduce((s, d) => s + d.trades_with_cost, 0)}
                  </td>
                  <td className="px-3 py-2.5 text-right"><MoneyCell v={totalComm} dimZero={false} /></td>
                  <td className="px-3 py-2.5 text-right"><MoneyCell v={totalSwap} dimZero={false} /></td>
                  <td className="px-3 py-2.5 text-right"><MoneyCell v={totalCosts} dimZero={false} /></td>
                  <td className="px-3 py-2.5 text-right">
                    {(() => {
                      const s = dayItems.reduce((acc, d) => acc + (d.pnl_usd ?? 0), 0);
                      return <MoneyCell v={s} dimZero={false} />;
                    })()}
                  </td>
                  <td className="px-3 py-2.5 text-right">
                    {(() => {
                      const s = dayItems.reduce((acc, d) => acc + (d.total_r ?? 0), 0);
                      return <span className={s >= 0 ? "text-profit" : "text-loss"}>{s > 0 ? "+" : ""}{s.toFixed(2)}R</span>;
                    })()}
                  </td>
                  <td />
                </tr>
              </tfoot>
            )}
          </table>
        </div>
        <p className="text-[10px] text-slate-600 mt-2">
          <span className="text-slate-500">Cu date</span> = trade-uri cu comisioane reale MT5. Zilele fără date = bot nu înregistra încă comisioane (înainte de 2026-07-01).
        </p>
      </div>

      {/* ── 3. Per-market breakdown ───────────────────────────────────── */}
      {symItems.some(r => r.has_cost_data) && (
        <div>
          <div className="text-[11px] font-semibold text-slate-300 mb-3">Pe Piețe</div>
          <div className="overflow-x-auto rounded-xl border border-surface-border">
            <table className="w-full text-[11px]">
              <thead>
                <tr className="border-b border-surface-border bg-surface-card">
                  <th className="text-left px-3 py-2 text-slate-500 font-medium">Piață</th>
                  <th className="text-right px-3 py-2 text-slate-500 font-medium">Trade-uri</th>
                  <th className="text-right px-3 py-2 text-slate-500 font-medium">Comisioane</th>
                  <th className="text-right px-3 py-2 text-slate-500 font-medium">Swap</th>
                  <th className="text-right px-3 py-2 text-slate-500 font-medium">Cost/trade</th>
                  <th className="text-right px-3 py-2 text-slate-500 font-medium">P&L Brut</th>
                  <th className="text-right px-3 py-2 text-slate-500 font-medium">P&L Net</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-border/40">
                {symItems.filter(r => r.has_cost_data).map(r => {
                  const costPerTrade = r.trades_with_mt5 > 0
                    ? r.total_costs / r.trades_with_mt5
                    : 0;
                  return (
                    <tr key={r.symbol} className="hover:bg-surface-border/10 transition-colors">
                      <td className="px-3 py-2.5 font-semibold text-white">{r.symbol}</td>
                      <td className="px-3 py-2.5 text-right text-slate-400">
                        {r.trades_with_mt5}/{r.trades}
                      </td>
                      <td className="px-3 py-2.5 text-right"><MoneyCell v={r.commission_usd} /></td>
                      <td className="px-3 py-2.5 text-right"><MoneyCell v={r.swap_usd} /></td>
                      <td className="px-3 py-2.5 text-right">
                        <span className="text-slate-400">{fmtMoney(costPerTrade)}</span>
                      </td>
                      <td className="px-3 py-2.5 text-right">
                        {r.pnl_net != null ? <MoneyCell v={r.pnl_gross} /> : <span className="text-slate-600">—</span>}
                      </td>
                      <td className="px-3 py-2.5 text-right">
                        {r.pnl_net != null ? <MoneyCell v={r.pnl_net} /> : <span className="text-slate-600">—</span>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

// ── System Logs tab ───────────────────────────────────────────────────────────

const LEVEL_CONFIG: Record<string, { label: string; color: string; icon: React.ReactElement }> = {
  ERROR:   { label: "Eroare",   color: "text-red-400",    icon: <AlertCircle  size={11} /> },
  WARNING: { label: "Warning",  color: "text-yellow-400", icon: <AlertTriangle size={11} /> },
  INFO:    { label: "Info",     color: "text-slate-400",  icon: <Info         size={11} /> },
};

function SystemLogsTab() {
  const [session,  setSession]  = useState("all");
  const [level,    setLevel]    = useState("WARNING");
  const [expanded, setExpanded] = useState<string | null>(null);

  // Sesiuni disponibile descoperite dinamic de pe disk
  const { data: sessionsData } = useLogSessions();
  const sessionsList = ["all", ...(sessionsData?.sessions ?? [])];

  const { data, isLoading, refetch, isFetching } = useSystemLogs({
    session,
    level,
    lines_per_session: 300,
  });

  const items = data?.items ?? [];
  const errCount  = items.filter(e => e.level === "ERROR").length;
  const warnCount = items.filter(e => e.level === "WARNING").length;

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex items-center gap-3 flex-wrap">
        <Terminal size={13} className="text-slate-500 flex-shrink-0" />

        {/* Level filter */}
        <div className="flex gap-1">
          {(["all","ERROR","WARNING","INFO"] as const).map(l => (
            <button
              key={l}
              onClick={() => setLevel(l)}
              className={`text-[10px] px-2.5 py-1 rounded-lg transition-colors border ${
                level === l
                  ? l === "ERROR"   ? "bg-red-500/20 text-red-400 border-red-500/30 font-medium"
                  : l === "WARNING" ? "bg-yellow-500/20 text-yellow-400 border-yellow-500/30 font-medium"
                  : l === "INFO"    ? "bg-slate-500/20 text-slate-300 border-slate-500/30 font-medium"
                  : "bg-blue-500/20 text-blue-400 border-blue-500/30 font-medium"
                  : "text-slate-500 border-transparent hover:text-slate-300"
              }`}
            >
              {l === "all" ? "Toate" : l}
            </button>
          ))}
        </div>

        {/* Session filter — dinamic, orice sesiune nouă apare automat */}
        <select
          value={session}
          onChange={e => setSession(e.target.value)}
          className="text-[10px] bg-surface-card border border-surface-border rounded-lg px-2 py-1 text-slate-300 focus:outline-none"
        >
          {sessionsList.map(s => (
            <option key={s} value={s}>{s === "all" ? "Toate sesiunile" : s}</option>
          ))}
        </select>

        {/* Summary badges */}
        {errCount > 0 && (
          <span className="flex items-center gap-1 text-[10px] text-red-400 bg-red-500/10 border border-red-500/20 px-2 py-0.5 rounded-full">
            <AlertCircle size={10} /> {errCount} erori
          </span>
        )}
        {warnCount > 0 && (
          <span className="flex items-center gap-1 text-[10px] text-yellow-400 bg-yellow-500/10 border border-yellow-500/20 px-2 py-0.5 rounded-full">
            <AlertTriangle size={10} /> {warnCount} warning-uri
          </span>
        )}

        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="ml-auto flex items-center gap-1 text-[10px] text-slate-400 hover:text-slate-200 transition-colors"
        >
          <RefreshCw size={11} className={isFetching ? "animate-spin" : ""} />
          Refresh
        </button>
        <span className="text-[10px] text-slate-500">{data?.total ?? 0} intrări</span>
      </div>

      {/* Log entries */}
      {isLoading ? (
        <div className="space-y-1">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="h-9 rounded-lg bg-surface-card animate-pulse" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <div className="text-center py-10 text-slate-500 text-xs">
          Niciun log la nivelul selectat.
        </div>
      ) : (
        <div className="space-y-px font-mono text-[11px]">
          {items.map((entry: SystemLogEntry, i: number) => {
            const key    = `${entry.time}-${entry.session}-${i}`;
            const cfg    = LEVEL_CONFIG[entry.level] ?? LEVEL_CONFIG.INFO;
            const isOpen = expanded === key;
            const isLong = entry.message.length > 120;

            return (
              <div
                key={key}
                className={`rounded-lg border transition-colors ${
                  entry.level === "ERROR"
                    ? "bg-red-950/20 border-red-900/30"
                    : entry.level === "WARNING"
                    ? "bg-yellow-950/20 border-yellow-900/30"
                    : "bg-surface-card border-surface-border"
                }`}
              >
                <div
                  className={`flex items-start gap-2 px-3 py-2 ${isLong ? "cursor-pointer" : ""}`}
                  onClick={() => isLong && setExpanded(isOpen ? null : key)}
                >
                  {/* Level icon */}
                  <span className={`mt-0.5 flex-shrink-0 ${cfg.color}`}>{cfg.icon}</span>

                  {/* Time */}
                  <span className="text-slate-500 flex-shrink-0 w-[130px]">{entry.time}</span>

                  {/* Session badge */}
                  <span className="text-blue-400/70 flex-shrink-0 w-[72px] truncate">{entry.session}</span>

                  {/* Message */}
                  <span className={`${cfg.color} flex-1 min-w-0 ${isOpen ? "whitespace-pre-wrap break-all" : "truncate"}`}>
                    {entry.message}
                  </span>

                  {isLong && (
                    <ChevronDown
                      size={11}
                      className={`flex-shrink-0 text-slate-500 transition-transform ${isOpen ? "rotate-180" : ""}`}
                    />
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

const TABS = [
  { id: "transactions", label: "Tranzacții",      icon: <BarChart2 size={13} /> },
  { id: "markets",      label: "Piețe",           icon: <Trophy size={13} /> },
  { id: "costs",        label: "Comisioane+Swap", icon: <DollarSign size={13} /> },
  { id: "uptime",       label: "Uptime Bot",      icon: <Clock size={13} /> },
  { id: "changes",      label: "Modificări",      icon: <Settings size={13} /> },
  { id: "sistem",       label: "Sistem",          icon: <Terminal size={13} /> },
] as const;

type ReportTab = (typeof TABS)[number]["id"];

function ManualReportButtons() {
  const [sending, setSending] = useState<"daily" | "weekly" | null>(null);
  const [lastSent, setLastSent] = useState<"daily" | "weekly" | null>(null);

  const send = async (type: "daily" | "weekly") => {
    setSending(type);
    try {
      await apiFetch(`/reports/send-${type}`, { method: "POST" });
      setLastSent(type);
      setTimeout(() => setLastSent(null), 4000);
    } catch {
      // silently fail — Telegram config may not be set
    } finally {
      setSending(null);
    }
  };

  return (
    <div className="flex items-center gap-2 ml-auto">
      <span className="text-[10px] text-slate-500">Trimite manual:</span>
      <button
        onClick={() => send("daily")}
        disabled={sending !== null}
        className="flex items-center gap-1.5 px-3 py-1.5 text-[11px] rounded-lg border border-surface-border bg-surface-card hover:border-blue-500/50 hover:text-blue-300 text-slate-300 transition-colors disabled:opacity-50"
      >
        {sending === "daily" ? <RefreshCw size={11} className="animate-spin" /> : <Send size={11} />}
        {lastSent === "daily" ? "✓ Trimis!" : "Zilnic"}
      </button>
      <button
        onClick={() => send("weekly")}
        disabled={sending !== null}
        className="flex items-center gap-1.5 px-3 py-1.5 text-[11px] rounded-lg border border-surface-border bg-surface-card hover:border-blue-500/50 hover:text-blue-300 text-slate-300 transition-colors disabled:opacity-50"
      >
        {sending === "weekly" ? <RefreshCw size={11} className="animate-spin" /> : <Calendar size={11} />}
        {lastSent === "weekly" ? "✓ Trimis!" : "Săptămânal"}
      </button>
    </div>
  );
}

// Tab-uri fara echivalent MT5 — concepte specifice botului (procese/profile),
// nu tranzactii, deci raman mereu pe date Bot indiferent de sursa selectata.
const BOT_ONLY_TABS: ReadonlySet<ReportTab> = new Set(["uptime", "changes", "sistem"]);

export function ReportsPage() {
  const [activeTab, setActiveTab] = useState<ReportTab>("transactions");
  const [statsSource, setStatsSource] = useStatsSource();

  return (
    <div className="p-4 md:p-6 space-y-5">
      {/* Page header */}
      <div className="flex items-center gap-3 flex-wrap">
        <BarChart2 size={16} className="text-blue-400" />
        <h1 className="text-sm font-semibold text-white">Rapoarte</h1>
        <span className="text-[10px] text-slate-500">
          {statsSource === "mt5"
            ? "Date live din toate tranzacțiile de pe MT5"
            : "Date live din toate sesiunile active"}
        </span>
        <ManualReportButtons />
      </div>

      {/* Sursa Bot / MT5 — se aplica taburilor Tranzacții / Piețe / Comisioane+Swap */}
      <div className="flex items-center gap-2 flex-wrap">
        <SourceToggle source={statsSource} onChange={setStatsSource} />
        {statsSource === "mt5" && BOT_ONLY_TABS.has(activeTab) && (
          <span className="text-[10px] text-slate-600">
            Acest tab e specific botului (fără echivalent MT5) — afișează mereu date Bot.
          </span>
        )}
      </div>

      {/* Tab selector */}
      <div className="flex gap-1 border-b border-surface-border pb-0">
        {TABS.map(t => (
          <button
            key={t.id}
            onClick={() => setActiveTab(t.id)}
            className={`flex items-center gap-1.5 text-xs font-medium px-4 py-2.5 border-b-2 transition-colors -mb-px ${
              activeTab === t.id
                ? "border-blue-500 text-white"
                : "border-transparent text-slate-400 hover:text-slate-200"
            }`}
          >
            {t.icon}
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div>
        {activeTab === "transactions" && <TransactionsTab source={statsSource} />}
        {activeTab === "markets"      && <MarketStatsTab source={statsSource} />}
        {activeTab === "costs"        && <CostsTab source={statsSource} />}
        {activeTab === "uptime"       && <UptimeTab />}
        {activeTab === "changes"      && <SessionChangesTab />}
        {activeTab === "sistem"       && <SystemLogsTab />}
      </div>
    </div>
  );
}
