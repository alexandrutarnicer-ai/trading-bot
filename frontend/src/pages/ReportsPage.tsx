import { useState } from "react";
import {
  BarChart2, TrendingUp, TrendingDown, Clock, Settings,
  Filter, ChevronDown, ChevronRight, Trophy, Target, Minus,
} from "lucide-react";
import {
  useTransactions, useMarketStats, useBotUptime, useSessionChanges,
} from "../api/hooks";
import type { Transaction, MarketStat, UptimeEntry, SessionChangeEntry } from "../api/types";

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
};

// ── Transactions table ────────────────────────────────────────────────────────

const STATUS_FILTERS = ["Toate", "TP", "SL", "Deschis", "Expirat", "Vineri", "Știri"];
const STATUS_MAP: Record<string, string> = {
  "Toate":    "",
  "TP":       "TP",
  "SL":       "SL",
  "Deschis":  "open",
  "Expirat":  "expirat",
  "Vineri":   "vineri_close",
  "Știri":    "news_close",
};

function TransactionsTab() {
  const [statusFilter, setStatusFilter] = useState("Toate");
  const [dirFilter,    setDirFilter]    = useState<"" | "LONG" | "SHORT">("");
  const [page,         setPage]         = useState(0);
  const PER_PAGE = 50;

  const { data, isLoading } = useTransactions({
    status:    STATUS_MAP[statusFilter] || undefined,
    direction: dirFilter || undefined,
    limit:     PER_PAGE,
    offset:    page * PER_PAGE,
  });

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const pages = Math.ceil(total / PER_PAGE);

  function fmt(t: Transaction) {
    const decimals = t.entry > 100 ? 2 : 5;
    return t.entry.toFixed(decimals);
  }

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex items-center gap-3 flex-wrap">
        <Filter size={13} className="text-slate-500 flex-shrink-0" />
        <div className="flex gap-1 flex-wrap">
          {STATUS_FILTERS.map(f => (
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
        <span className="text-[10px] text-slate-500 ml-auto">{total} tranzacții</span>
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
                <th className="text-left px-3 py-2 text-slate-500 font-medium">Sesiune</th>
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
              {items.map((t, i) => {
                const isWin  = t.result_r > 0;
                const isLoss = t.result_r < 0;
                return (
                  <tr
                    key={`${t.signal_id}-${i}`}
                    className={`transition-colors hover:bg-surface-border/10 ${
                      t.status === "TP" ? "bg-profit/4" : t.status === "SL" ? "bg-loss/4" : ""
                    }`}
                  >
                    <td className="px-3 py-2 font-semibold text-white">{t.symbol}</td>
                    <td className="px-3 py-2 text-slate-400 truncate max-w-[100px]">{t.session_label.replace(/^S\d+ — /, "")}</td>
                    <td className="px-3 py-2 text-center">
                      <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold ${
                        t.direction === 1
                          ? "bg-profit/20 text-profit"
                          : "bg-loss/20 text-loss"
                      }`}>
                        {t.dir_str}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-slate-300">{fmt(t)}</td>
                    <td className="px-3 py-2 text-center">
                      <span className={`text-[9px] font-medium ${
                        t.status === "TP" ? "text-profit"
                        : t.status === "SL" ? "text-loss"
                        : "text-slate-500"
                      }`}>
                        {STATUS_LABELS[t.status] ?? t.status}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right text-slate-500 font-mono">{t.r_ratio}R</td>
                    <td className={`px-3 py-2 text-right font-mono font-semibold ${rColor(t.result_r)}`}>
                      {fmtR(t.result_r)}
                    </td>
                    <td className={`px-3 py-2 text-right font-mono ${t.pnl_usd != null ? rColor(t.pnl_usd) : "text-slate-600"}`}>
                      {fmtUsd(t.pnl_usd)}
                    </td>
                    <td className="px-3 py-2 text-right text-slate-500">
                      {t.exit_time ? fmtTime(t.exit_time) : t.time_check ? fmtTime(t.time_check) : "—"}
                    </td>
                  </tr>
                );
              })}
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
    </div>
  );
}

// ── Market stats tab ──────────────────────────────────────────────────────────

function MarketStatsTab() {
  const { data, isLoading } = useMarketStats();
  const items = data?.items ?? [];

  const totalTrades = items.reduce((s, m) => s + m.trades, 0);
  const totalR      = items.reduce((s, m) => s + m.total_r, 0);

  return (
    <div className="space-y-4">
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
                <th className="text-left px-3 py-2.5 text-slate-500 font-medium">Sesiuni</th>
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
                  <td className="px-3 py-2.5 text-slate-500 text-[10px] max-w-[140px] truncate">
                    {m.sessions.map(s => s.replace(/^S\d+ — /, "")).join(", ")}
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

// ── Page ──────────────────────────────────────────────────────────────────────

const TABS = [
  { id: "transactions", label: "Tranzacții", icon: <BarChart2 size={13} /> },
  { id: "markets",      label: "Piețe",      icon: <Trophy size={13} /> },
  { id: "uptime",       label: "Uptime Bot",  icon: <Clock size={13} /> },
  { id: "changes",      label: "Modificări",  icon: <Settings size={13} /> },
] as const;

type ReportTab = (typeof TABS)[number]["id"];

export function ReportsPage() {
  const [activeTab, setActiveTab] = useState<ReportTab>("transactions");

  return (
    <div className="p-4 md:p-6 space-y-5">
      {/* Page header */}
      <div className="flex items-center gap-3">
        <BarChart2 size={16} className="text-blue-400" />
        <h1 className="text-sm font-semibold text-white">Rapoarte</h1>
        <span className="text-[10px] text-slate-500">Date live din toate sesiunile active</span>
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
        {activeTab === "transactions" && <TransactionsTab />}
        {activeTab === "markets"      && <MarketStatsTab />}
        {activeTab === "uptime"       && <UptimeTab />}
        {activeTab === "changes"      && <SessionChangesTab />}
      </div>
    </div>
  );
}
