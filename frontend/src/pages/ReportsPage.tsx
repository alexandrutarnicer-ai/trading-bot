import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  BarChart2, TrendingUp, TrendingDown, Clock, Settings,
  Filter, ChevronDown, ChevronRight, Trophy, Target, Minus,
  Terminal, AlertTriangle, AlertCircle, Info, RefreshCw, DollarSign,
  Send, Calendar, Download,
} from "lucide-react";
import {
  useBotUptime, useSessionChanges, useSystemLogs, useLogSessions,
  useMt5Transactions, useMt5MarketStats, useMt5Costs, useMt5CostsDaily,
} from "../api/hooks";
import { apiFetch } from "../api/client";
import type { UptimeEntry, SessionChangeEntry, SystemLogEntry, CostStat, CostsDayEntry, CostSourceStat, Mt5Transaction, Mt5TopMarketEntry, TopMarketsSort } from "../api/types";

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

// ── Transactions table ────────────────────────────────────────────────────────
// Sursa unica: istoricul MT5 (cont-wide), atribuit pe engine / sesiune / strategie
// din magic + comment-ul ordinului (api/mt5_pool.py::classify_trade).

const STATUS_FILTERS = ["Toate", "TP", "SL"];
const SOURCE_FILTERS: Array<{ id: "" | Mt5Transaction["source"]; label: string }> = [
  { id: "",       label: "Toate" },
  { id: "bot",    label: "Custom" },
  { id: "ai",     label: "AI" },
  { id: "daily",  label: "Daily" },
  { id: "noisy",  label: "Noisy" },
  { id: "manual", label: "Manual" },
];
const SOURCE_BADGE: Record<Mt5Transaction["source"], { label: string; cls: string }> = {
  bot:    { label: "CUSTOM", cls: "bg-emerald-500/15 text-emerald-300" },
  ai:     { label: "AI",  cls: "bg-purple-500/15 text-purple-300" },
  daily:  { label: "DAILY", cls: "bg-cyan-500/15 text-cyan-300" },
  noisy:  { label: "NOISY", cls: "bg-amber-500/15 text-amber-300" },
  manual: { label: "MAN", cls: "bg-slate-500/20 text-slate-300" },
};
const STRATEGY_LABEL: Record<string, string> = {
  pullback: "Pullback", inside_bar: "Inside Bar", flag: "Flag", smart_news: "Știre",
};

function TransactionsTab() {
  const [statusFilter, setStatusFilter] = useState("Toate");
  const [sourceFilter, setSourceFilter] = useState<"" | Mt5Transaction["source"]>("");
  const [dirFilter,    setDirFilter]    = useState<"" | "LONG" | "SHORT">("");
  const [dateFrom,     setDateFrom]     = useState("");
  const [dateTo,       setDateTo]       = useState("");
  const [page,         setPage]         = useState(0);
  const PER_PAGE = 50;

  const status = statusFilter === "Toate" ? undefined : statusFilter;
  const query = useMt5Transactions({
    status,
    source:    sourceFilter || undefined,
    direction: dirFilter || undefined,
    date_from: dateFrom || undefined,
    date_to:   dateTo   || undefined,
    limit:     PER_PAGE,
    offset:    page * PER_PAGE,
  });

  // Descarcare CSV cu filtrele curente, fara paginare.
  function downloadCsv() {
    const qs = new URLSearchParams();
    if (status)       qs.set("status", status);
    if (sourceFilter) qs.set("source", sourceFilter);
    if (dirFilter)    qs.set("direction", dirFilter);
    if (dateFrom)     qs.set("date_from", dateFrom);
    if (dateTo)       qs.set("date_to", dateTo);
    window.open(`http://127.0.0.1:8000/api/mt5/transactions.csv?${qs.toString()}`, "_blank");
  }

  const total = query.data?.total ?? 0;
  const items = query.data?.items ?? [];
  const pages = Math.ceil(total / PER_PAGE);

  function fmt(entry: number) {
    const decimals = entry > 100 ? 2 : 5;
    return entry.toFixed(decimals);
  }

  const chip = (active: boolean) =>
    `text-[10px] px-2.5 py-1 rounded-lg transition-colors ${
      active
        ? "bg-blue-500/20 text-blue-400 border border-blue-500/30 font-medium"
        : "text-slate-500 hover:text-slate-300 border border-transparent"
    }`;

  return (
    <div className="space-y-4">
      {query.data && !query.data.connected && (
        <div className="text-[11px] text-warn/80 bg-warn/10 border border-warn/30 rounded-lg px-3 py-2">
          MT5 neconectat — {query.data.error ?? "tranzacțiile nu sunt disponibile"}.
        </div>
      )}

      {/* Filters */}
      <div className="flex items-center gap-3 flex-wrap">
        <Filter size={13} className="text-slate-500 flex-shrink-0" />
        <div className="flex gap-1 flex-wrap">
          {SOURCE_FILTERS.map(f => (
            <button key={f.id || "all"} onClick={() => { setSourceFilter(f.id); setPage(0); }}
              className={chip(sourceFilter === f.id)}>
              {f.label}
            </button>
          ))}
        </div>
        <div className="flex gap-1 flex-wrap ml-2">
          {STATUS_FILTERS.map(f => (
            <button key={f} onClick={() => { setStatusFilter(f); setPage(0); }} className={chip(statusFilter === f)}>
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
          title="Exportă tranzacțiile MT5 cu filtrele curente (include sursa, sesiunea și strategia)"
          className="flex items-center gap-1 text-[10px] px-2.5 py-1 rounded-lg border border-surface-border text-slate-300 hover:border-blue-500/40 hover:text-blue-400 transition-colors">
          <Download size={12} /> CSV
        </button>
        <span className="text-[10px] text-slate-500">{total} tranzacții</span>
      </div>

      {/* Table */}
      {query.isLoading ? (
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
                <th className="text-left px-3 py-2 text-slate-500 font-medium">Sursă</th>
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
              {items.map((t) => {
                const src = SOURCE_BADGE[t.source] ?? SOURCE_BADGE.manual;
                return (
                  <tr
                    key={t.ticket}
                    className={`transition-colors hover:bg-surface-border/10 ${
                      t.status === "TP" ? "bg-profit/4" : t.status === "SL" ? "bg-loss/4" : ""
                    }`}
                  >
                    <td className="px-3 py-2 font-semibold text-white">
                      {t.symbol}
                      {t.ai_approved && (
                        <span
                          className="ml-1.5 text-[8px] px-1 py-0.5 rounded font-bold bg-purple-500/20 text-purple-300 align-middle"
                          title={`Validat de Filtrul AI Pre-Trade${t.ai_confidence != null ? ` — încredere ${t.ai_confidence}%` : ""}`}
                        >
                          AI✓
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-slate-400 whitespace-nowrap">
                      <span className={`text-[9px] font-bold px-1 rounded ${src.cls}`}>{src.label}</span>
                      {t.session_id && <span className="ml-1.5">{t.session_id.replace("session", "S")}</span>}
                      {t.strategy && <span className="ml-1.5 text-slate-500">{STRATEGY_LABEL[t.strategy] ?? t.strategy}</span>}
                    </td>
                    <td className="px-3 py-2 text-center">
                      <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold ${
                        t.direction === 1 ? "bg-profit/20 text-profit" : "bg-loss/20 text-loss"
                      }`}>
                        {t.dir_str}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-slate-300">{fmt(t.entry)}</td>
                    <td className="px-3 py-2 text-center">
                      <span className={`text-[9px] font-medium ${
                        t.status === "TP" ? "text-profit" : t.status === "SL" ? "text-loss" : "text-slate-500"
                      }`}>
                        {t.status}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right text-slate-500 font-mono">{t.r_ratio != null ? `${t.r_ratio}R` : "—"}</td>
                    <td className={`px-3 py-2 text-right font-mono font-semibold ${rColor(t.result_r ?? 0)}`}>
                      {fmtR(t.result_r)}
                    </td>
                    <td className={`px-3 py-2 text-right font-mono ${rColor(t.pnl_usd)}`}>
                      {fmtUsd(t.pnl_usd)}
                    </td>
                    <td className="px-3 py-2 text-right text-slate-500">
                      {t.exit_time ?? t.entry_time ? fmtTime((t.exit_time ?? t.entry_time)!) : "—"}
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
// Toate pietele, agregate pe simbol peste engine-urile din filtrul de sursa — aceleasi
// definitii ca Top 5 din Dashboard (api/trade_stats.py).

const MARKET_PERIODS: Array<{ id: string; label: string }> = [
  { id: "day", label: "Azi" }, { id: "week", label: "Săpt" },
  { id: "month", label: "Lună" }, { id: "all", label: "Tot (365 z)" },
];
const MARKET_SORTS: Array<{ id: TopMarketsSort; label: string }> = [
  { id: "net", label: "$ net" }, { id: "r", label: "R" }, { id: "trades", label: "Trades" },
];

function MarketStatsTab() {
  const [period, setPeriod] = useState("all");
  const [source, setSource] = useState<"" | Mt5Transaction["source"]>("");
  const [sort, setSort]     = useState<TopMarketsSort>("net");
  const mt5Query = useMt5MarketStats(period, source || "all", sort);

  const isLoading = mt5Query.isLoading;
  const items: Mt5TopMarketEntry[] = mt5Query.data?.items ?? [];
  const tot = mt5Query.data?.totals;

  const chip = (active: boolean) =>
    `text-[10px] px-2.5 py-1 rounded-lg transition-colors ${
      active
        ? "bg-blue-500/20 text-blue-400 border border-blue-500/30 font-medium"
        : "text-slate-500 hover:text-slate-300 border border-transparent"
    }`;

  return (
    <div className="space-y-4">
      {mt5Query.data && !mt5Query.data.connected && (
        <div className="text-[11px] text-warn/80 bg-warn/10 border border-warn/30 rounded-lg px-3 py-2">
          MT5 neconectat — {mt5Query.data.error ?? "clasamentul nu este disponibil"}.
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-1">
          {MARKET_PERIODS.map(p => (
            <button key={p.id} onClick={() => setPeriod(p.id)} className={chip(period === p.id)}>{p.label}</button>
          ))}
        </div>
        <div className="flex items-center gap-1">
          {SOURCE_FILTERS.map(f => (
            <button key={f.id || "all"} onClick={() => setSource(f.id)} className={chip(source === f.id)}>{f.label}</button>
          ))}
        </div>
        <div className="flex items-center gap-1 ml-auto">
          <span className="text-[10px] text-slate-600">Sortare</span>
          {MARKET_SORTS.map(o => (
            <button key={o.id} onClick={() => setSort(o.id)} className={chip(sort === o.id)}>{o.label}</button>
          ))}
        </div>
      </div>

      {tot && tot.trades > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div className="bg-surface-card rounded-xl border border-surface-border px-4 py-3">
            <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Piețe</div>
            <div className="text-2xl font-bold font-mono text-white">{mt5Query.data?.total_markets ?? items.length}</div>
          </div>
          <div className="bg-surface-card rounded-xl border border-surface-border px-4 py-3">
            <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Trades</div>
            <div className="text-2xl font-bold font-mono text-white">{tot.trades}</div>
            <div className="text-[10px] text-slate-500 mt-0.5">
              {tot.wins}W / {tot.losses}L{tot.breakeven ? ` / ${tot.breakeven} BE` : ""} · {fmtPct(tot.win_rate)}
            </div>
          </div>
          <div className="bg-surface-card rounded-xl border border-surface-border px-4 py-3">
            <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">P&L net</div>
            <div className={`text-2xl font-bold font-mono ${rColor(tot.pnl_net)}`}>{fmtUsd(tot.pnl_net)}</div>
            <div className="text-[10px] text-slate-500 mt-0.5">brut {fmtUsd(tot.pnl_gross)} · costuri {fmtUsd(tot.costs)}</div>
          </div>
          <div className="bg-surface-card rounded-xl border border-surface-border px-4 py-3">
            <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Total R</div>
            <div className={`text-2xl font-bold font-mono ${rColor(tot.total_r)}`}>{fmtR(tot.total_r)}</div>
            <div className="text-[10px] text-slate-500 mt-0.5">{tot.trades_with_r} trades cu SL</div>
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
          <p>Nicio tranzacție în perioada / sursa selectată</p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-surface-border">
          <table className="w-full text-[11px]">
            <thead>
              <tr className="border-b border-surface-border bg-surface-card">
                <th className="text-left px-4 py-2.5 text-slate-500 font-medium">Simbol</th>
                <th className="text-right px-3 py-2.5 text-slate-500 font-medium">Trades</th>
                <th className="text-right px-3 py-2.5 text-slate-500 font-medium">W / L</th>
                <th className="text-right px-3 py-2.5 text-slate-500 font-medium">Win Rate</th>
                <th className="text-right px-3 py-2.5 text-slate-500 font-medium" title="R mediu pe trade-urile cu SL">Expectancy</th>
                <th className="text-right px-3 py-2.5 text-slate-500 font-medium">Total R</th>
                <th className="text-right px-3 py-2.5 text-slate-500 font-medium">P&L brut</th>
                <th className="text-right px-3 py-2.5 text-slate-500 font-medium" title="comision + swap">Costuri</th>
                <th className="text-right px-3 py-2.5 text-slate-500 font-medium">P&L net</th>
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
                  <td className="px-3 py-2.5 text-right text-slate-400 font-mono">
                    {m.wins}/{m.losses}{m.breakeven ? <span className="text-slate-600"> +{m.breakeven}BE</span> : null}
                  </td>
                  <td className="px-3 py-2.5 text-right">
                    <span className={m.win_rate >= 50 ? "text-profit font-medium" : "text-slate-400"}>
                      {fmtPct(m.win_rate)}
                    </span>
                  </td>
                  <td className={`px-3 py-2.5 text-right font-mono font-semibold ${m.expectancy_r != null ? rColor(m.expectancy_r) : "text-slate-600"}`}>
                    {fmtR(m.expectancy_r)}
                  </td>
                  <td className={`px-3 py-2.5 text-right font-mono font-semibold ${m.trades_with_r ? rColor(m.total_r) : "text-slate-600"}`}>
                    {m.trades_with_r ? fmtR(m.total_r) : "—"}
                  </td>
                  <td className={`px-3 py-2.5 text-right font-mono ${rColor(m.pnl_gross)}`}>{fmtUsd(m.pnl_gross)}</td>
                  <td className={`px-3 py-2.5 text-right font-mono ${m.costs < 0 ? "text-loss/80" : "text-slate-500"}`}>{fmtUsd(m.costs)}</td>
                  <td className={`px-3 py-2.5 text-right font-mono font-semibold ${rColor(m.pnl_net)}`}>{fmtUsd(m.pnl_net)}</td>
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

interface AuditRow { time: string; engine: string; action: string; market?: string | null; detail: string;
  before?: unknown; after?: unknown }

const AUDIT_ACTION: Record<string, string> = { mode: "mod", pause: "pauză", resume: "reluat", config: "configurare",
  start: "pornit", stop: "oprit", order: "ordin", blocked: "blocat", rejected: "respins" };

function EngineAuditPanel() {
  const { data } = useQuery<{ items: AuditRow[] }>({ queryKey: ["audit-log"], queryFn: () => apiFetch("/reports/audit-log?limit=200"),
    refetchInterval: 60_000, refetchIntervalInBackground: false });
  const items = data?.items ?? [];
  if (!items.length) return null;
  return (
    <div className="border border-surface-border rounded-xl p-3 space-y-1">
      <div className="text-xs font-semibold text-slate-300">Audit engine-uri (Daily / Special) — moduri, configurare, pornire / oprire</div>
      <div className="max-h-72 overflow-y-auto">
        <table className="w-full text-[11px]">
          <tbody>{items.map((r, i) => (
            <tr key={i} className="border-t border-surface-border/30">
              <td className="py-0.5 pr-2 text-slate-500 whitespace-nowrap">{new Date(r.time).toLocaleString("ro-RO")}</td>
              <td className="pr-2 text-slate-300 uppercase">{r.engine}</td>
              <td className="pr-2 text-slate-400">{AUDIT_ACTION[r.action] ?? r.action}</td>
              <td className="text-slate-300">{r.detail}</td>
            </tr>))}</tbody>
        </table>
      </div>
    </div>
  );
}

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
      <EngineAuditPanel />
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
// Ce costa tranzactionarea, din MT5 (api/trade_stats.py). Pe contul Standard comisionul e ~0:
// costul real e SPREAD-ul, care nu apare ca taxa separata (e in pretul de executie, deci deja in
// P&L) — il estimam la spread-ul curent × volum ca sa se vada cat consuma. Swap = dobanda overnight.

const ENGINE_LABEL: Record<CostSourceStat["source"], string> = {
  bot: "Custom Engine", ai: "AI Engine", daily: "Daily Engine", noisy: "Noisy Engine", manual: "Manual",
};

/** Cost total estimat = spread estimat (daca e cunoscut) + comision + swap. */
const estTotal = (s: { spread_est: number | null; costs: number }) => (s.spread_est ?? 0) + s.costs;

function CostsTab() {
  const [source, setSource] = useState<"" | Mt5Transaction["source"]>("");
  const [showAllDays, setShowAllDays] = useState(false);
  const mt5Sym  = useMt5Costs(source || "all");
  const mt5Day  = useMt5CostsDaily(source || "all");

  const symItems: CostStat[]        = mt5Sym.data?.items ?? [];
  const dayItems: CostsDayEntry[]   = mt5Day.data?.items ?? [];
  const bySource: CostSourceStat[]  = mt5Sym.data?.by_source ?? [];
  const tot = mt5Sym.data?.totals ?? null;
  const days = mt5Sym.data?.days ?? 365;
  const mt5NotConnected = mt5Sym.data && !mt5Sym.data.connected;

  const fmtMoney = (v: number | null | undefined, showPlus = true) => {
    if (v == null) return "—";
    const sign = v > 0 && showPlus ? "+" : "";
    return `${sign}${v.toLocaleString("ro-RO", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} $`;
  };
  const MoneyCell = ({ v, dimZero = true }: { v: number | null | undefined; dimZero?: boolean }) => {
    if (v == null) return <span className="text-slate-600">—</span>;
    if (Math.abs(v) < 0.005 && dimZero) return <span className="text-slate-600">0,00 $</span>;
    return <span className={v < 0 ? "text-loss" : v > 0 ? "text-profit" : "text-slate-400"}>{fmtMoney(v)}</span>;
  };
  const fmtDate = (s: string) =>
    new Date(s).toLocaleDateString("ro-RO", { day: "2-digit", month: "short" });

  const chip = (active: boolean) =>
    `text-[10px] px-2.5 py-1 rounded-lg transition-colors ${
      active
        ? "bg-blue-500/20 text-blue-400 border border-blue-500/30 font-medium"
        : "text-slate-500 hover:text-slate-300 border border-transparent"
    }`;

  if (mt5Sym.isLoading || mt5Day.isLoading) {
    return (
      <div className="space-y-2">
        {[...Array(6)].map((_, i) => (
          <div key={i} className="h-12 rounded-xl bg-surface-card animate-pulse" />
        ))}
      </div>
    );
  }

  const daysDesc = [...dayItems].reverse();
  const shownDays = showAllDays ? daysDesc : daysDesc.slice(0, 30);
  const maxDayCost = Math.max(...dayItems.map(d => Math.abs(estTotal(d))), 0.01);
  const totalEst = tot ? estTotal(tot) : 0;
  const withoutCosts = tot ? tot.pnl_net - totalEst : 0;   // ce ar fi fost fara spread + comision + swap

  return (
    <div className="space-y-6">
      {mt5NotConnected && (
        <div className="text-[11px] text-warn/80 bg-warn/10 border border-warn/30 rounded-lg px-3 py-2">
          MT5 neconectat — {mt5Sym.data?.error ?? "costurile nu sunt disponibile"}.
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        {SOURCE_FILTERS.map(f => (
          <button key={f.id || "all"} onClick={() => setSource(f.id)} className={chip(source === f.id)}>{f.label}</button>
        ))}
        <span className="text-[10px] text-slate-600 ml-auto">poziții închise · ultimele {days} zile</span>
      </div>

      {/* ── 1. Ce platesti ───────────────────────────────────────────── */}
      <div className="bg-surface-card border border-surface-border rounded-xl p-4 text-[11px] text-slate-400 space-y-1.5">
        <div className="text-slate-200 font-semibold text-xs mb-1">Ce plătești brokerului</div>
        <div><span className="text-slate-200">Spread</span> — diferența dintre prețul de cumpărare și cel de vânzare, plătită la fiecare intrare.
          Nu apare ca taxă separată: e deja în prețul de execuție, deci <b>deja inclus în P&L</b>. Pe contul Standard este costul principal.
          Valoarea de mai jos e o <b>estimare</b> la spread-ul curent × volumul fiecărui trade (la știri / deschidere spread-ul real e mai mare).</div>
        <div><span className="text-slate-200">Comision</span> — taxă pe lot; pe contul Standard e ~0 (broker-ul câștigă din spread).</div>
        <div><span className="text-slate-200">Swap</span> — dobânda pentru pozițiile ținute peste noapte; poate fi plătită (−) sau primită (+).</div>
      </div>

      {/* ── 2. Totaluri ──────────────────────────────────────────────── */}
      {tot && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <div className="bg-surface-card border border-surface-border rounded-xl p-4">
            <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Spread (estimat)</div>
            <div className="text-xl font-bold font-mono text-loss">{fmtMoney(tot.spread_est)}</div>
            <div className="text-[10px] text-slate-600 mt-1">deja în P&L · {tot.spread_est_trades}/{tot.trades} trades</div>
          </div>
          <div className="bg-surface-card border border-surface-border rounded-xl p-4">
            <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Comision</div>
            <div className={`text-xl font-bold font-mono ${tot.commission < 0 ? "text-loss" : "text-slate-300"}`}>{fmtMoney(tot.commission)}</div>
            <div className="text-[10px] text-slate-600 mt-1">taxă separată, real MT5</div>
          </div>
          <div className="bg-surface-card border border-surface-border rounded-xl p-4">
            <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Swap</div>
            <div className={`text-xl font-bold font-mono ${tot.swap < 0 ? "text-loss" : "text-profit"}`}>{fmtMoney(tot.swap)}</div>
            <div className="text-[10px] text-slate-600 mt-1">taxă separată, real MT5</div>
          </div>
          <div className="bg-surface-card border border-surface-border rounded-xl p-4">
            <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Cost total (estimat)</div>
            <div className="text-xl font-bold font-mono text-loss">{fmtMoney(totalEst)}</div>
            <div className="text-[10px] text-slate-600 mt-1">
              {tot.trades ? `${fmtMoney(totalEst / tot.trades)} / trade` : "—"}
            </div>
          </div>
          <div className="bg-surface-card border border-surface-border rounded-xl p-4">
            <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">P&L net real</div>
            <div className={`text-xl font-bold font-mono ${rColor(tot.pnl_net)}`}>{fmtMoney(tot.pnl_net)}</div>
            <div className="text-[10px] text-slate-600 mt-1">fără niciun cost ar fi fost ~{fmtMoney(withoutCosts)}</div>
          </div>
        </div>
      )}

      {/* ── 3. Pe engine ─────────────────────────────────────────────── */}
      {bySource.length > 0 && (
        <div>
          <div className="text-[11px] font-semibold text-slate-300 mb-3">Pe engine</div>
          <div className="overflow-x-auto rounded-xl border border-surface-border">
            <table className="w-full text-[11px]">
              <thead>
                <tr className="border-b border-surface-border bg-surface-card">
                  <th className="text-left px-3 py-2 text-slate-500 font-medium">Engine</th>
                  <th className="text-right px-3 py-2 text-slate-500 font-medium">Trades</th>
                  <th className="text-right px-3 py-2 text-slate-500 font-medium">Spread (est.)</th>
                  <th className="text-right px-3 py-2 text-slate-500 font-medium">Comision</th>
                  <th className="text-right px-3 py-2 text-slate-500 font-medium">Swap</th>
                  <th className="text-right px-3 py-2 text-slate-500 font-medium">Cost total (est.)</th>
                  <th className="text-right px-3 py-2 text-slate-500 font-medium">Cost / trade</th>
                  <th className="text-right px-3 py-2 text-slate-500 font-medium">P&L net</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-border/40">
                {bySource.map(r => (
                  <tr key={r.source} className="hover:bg-surface-border/10 transition-colors">
                    <td className="px-3 py-2.5 font-semibold text-white">{ENGINE_LABEL[r.source] ?? r.source}</td>
                    <td className="px-3 py-2.5 text-right text-slate-400">{r.trades}</td>
                    <td className="px-3 py-2.5 text-right"><MoneyCell v={r.spread_est} /></td>
                    <td className="px-3 py-2.5 text-right"><MoneyCell v={r.commission} /></td>
                    <td className="px-3 py-2.5 text-right"><MoneyCell v={r.swap} /></td>
                    <td className="px-3 py-2.5 text-right font-semibold"><MoneyCell v={estTotal(r)} dimZero={false} /></td>
                    <td className="px-3 py-2.5 text-right text-slate-400">{r.trades ? fmtMoney(estTotal(r) / r.trades) : "—"}</td>
                    <td className="px-3 py-2.5 text-right"><MoneyCell v={r.pnl_net} dimZero={false} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── 4. Pe piete ──────────────────────────────────────────────── */}
      {symItems.length > 0 && (
        <div>
          <div className="text-[11px] font-semibold text-slate-300 mb-3">Pe piețe <span className="text-slate-600 font-normal">(cele mai scumpe primele)</span></div>
          <div className="overflow-x-auto rounded-xl border border-surface-border">
            <table className="w-full text-[11px]">
              <thead>
                <tr className="border-b border-surface-border bg-surface-card">
                  <th className="text-left px-3 py-2 text-slate-500 font-medium">Piață</th>
                  <th className="text-right px-3 py-2 text-slate-500 font-medium">Trades</th>
                  <th className="text-right px-3 py-2 text-slate-500 font-medium">Spread (est.)</th>
                  <th className="text-right px-3 py-2 text-slate-500 font-medium">Comision</th>
                  <th className="text-right px-3 py-2 text-slate-500 font-medium">Swap</th>
                  <th className="text-right px-3 py-2 text-slate-500 font-medium">Cost total (est.)</th>
                  <th className="text-right px-3 py-2 text-slate-500 font-medium">Cost / trade</th>
                  <th className="text-right px-3 py-2 text-slate-500 font-medium">P&L brut</th>
                  <th className="text-right px-3 py-2 text-slate-500 font-medium">P&L net</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-border/40">
                {[...symItems].sort((a, b) => estTotal(a) - estTotal(b)).map(r => (
                  <tr key={r.symbol} className="hover:bg-surface-border/10 transition-colors">
                    <td className="px-3 py-2.5 font-semibold text-white">{r.symbol}</td>
                    <td className="px-3 py-2.5 text-right text-slate-400">{r.trades}</td>
                    <td className="px-3 py-2.5 text-right"><MoneyCell v={r.spread_est} /></td>
                    <td className="px-3 py-2.5 text-right"><MoneyCell v={r.commission} /></td>
                    <td className="px-3 py-2.5 text-right"><MoneyCell v={r.swap} /></td>
                    <td className="px-3 py-2.5 text-right font-semibold"><MoneyCell v={estTotal(r)} dimZero={false} /></td>
                    <td className="px-3 py-2.5 text-right text-slate-400">{r.trades ? fmtMoney(estTotal(r) / r.trades) : "—"}</td>
                    <td className="px-3 py-2.5 text-right"><MoneyCell v={r.pnl_gross} /></td>
                    <td className="px-3 py-2.5 text-right"><MoneyCell v={r.pnl_net} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── 5. Evolutie zilnica ──────────────────────────────────────── */}
      <div>
        <div className="flex items-center gap-2 mb-3">
          <span className="text-[11px] font-semibold text-slate-300">Evoluție zilnică</span>
          <span className="text-[10px] text-slate-600">zile cu poziții închise · {dayItems.length} zile</span>
        </div>
        {dayItems.length === 0 ? (
          <div className="text-center py-8 text-slate-500 text-xs">Nicio poziție închisă în perioadă</div>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-surface-border">
            <table className="w-full text-[11px]">
              <thead>
                <tr className="border-b border-surface-border bg-surface-card">
                  <th className="text-left px-3 py-2 text-slate-500 font-medium w-24">Data</th>
                  <th className="text-right px-3 py-2 text-slate-500 font-medium">Trades</th>
                  <th className="text-right px-3 py-2 text-slate-500 font-medium">Spread (est.)</th>
                  <th className="text-right px-3 py-2 text-slate-500 font-medium">Comision</th>
                  <th className="text-right px-3 py-2 text-slate-500 font-medium">Swap</th>
                  <th className="text-right px-3 py-2 text-slate-500 font-medium">Cost total (est.)</th>
                  <th className="text-right px-3 py-2 text-slate-500 font-medium">P&L net</th>
                  <th className="text-right px-3 py-2 text-slate-500 font-medium">R total</th>
                  <th className="px-3 py-2 text-slate-500 font-medium w-28">Cost vizual</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-border/40">
                {shownDays.map(row => {
                  const today = new Date().toISOString().slice(0, 10);
                  const isToday = row.date === today;
                  const c = estTotal(row);
                  const barPct = Math.round(Math.min(Math.abs(c) / maxDayCost * 100, 100));
                  return (
                    <tr key={row.date} className={`hover:bg-surface-border/10 transition-colors ${isToday ? "bg-blue-500/5" : ""}`}>
                      <td className="px-3 py-2.5 text-slate-300 font-medium">
                        {fmtDate(row.date)}
                        {isToday && <span className="ml-1 text-[9px] text-blue-400">azi</span>}
                      </td>
                      <td className="px-3 py-2.5 text-right text-slate-400">{row.trades}</td>
                      <td className="px-3 py-2.5 text-right"><MoneyCell v={row.spread_est} /></td>
                      <td className="px-3 py-2.5 text-right"><MoneyCell v={row.commission} /></td>
                      <td className="px-3 py-2.5 text-right"><MoneyCell v={row.swap} /></td>
                      <td className="px-3 py-2.5 text-right font-semibold"><MoneyCell v={c} dimZero={false} /></td>
                      <td className="px-3 py-2.5 text-right"><MoneyCell v={row.pnl_net} /></td>
                      <td className="px-3 py-2.5 text-right">
                        {row.trades_with_r
                          ? <span className={rColor(row.total_r)}>{row.total_r > 0 ? "+" : ""}{row.total_r.toFixed(2)}R</span>
                          : <span className="text-slate-600">—</span>}
                      </td>
                      <td className="px-3 py-2.5">
                        {barPct > 0 && (
                          <div className="flex-1 h-2 rounded-full bg-surface-border overflow-hidden">
                            <div className={`h-full rounded-full ${c < 0 ? "bg-loss/60" : "bg-profit/60"}`}
                                 style={{ width: `${barPct}%` }} />
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
              {tot && (
                <tfoot>
                  <tr className="border-t-2 border-surface-border bg-surface-card/80 font-semibold">
                    <td className="px-3 py-2.5 text-slate-400 text-[10px]">TOTAL ({dayItems.length} z)</td>
                    <td className="px-3 py-2.5 text-right text-slate-400">{tot.trades}</td>
                    <td className="px-3 py-2.5 text-right"><MoneyCell v={tot.spread_est} dimZero={false} /></td>
                    <td className="px-3 py-2.5 text-right"><MoneyCell v={tot.commission} dimZero={false} /></td>
                    <td className="px-3 py-2.5 text-right"><MoneyCell v={tot.swap} dimZero={false} /></td>
                    <td className="px-3 py-2.5 text-right"><MoneyCell v={totalEst} dimZero={false} /></td>
                    <td className="px-3 py-2.5 text-right"><MoneyCell v={tot.pnl_net} dimZero={false} /></td>
                    <td className="px-3 py-2.5 text-right">
                      <span className={rColor(tot.total_r)}>{tot.total_r > 0 ? "+" : ""}{tot.total_r.toFixed(2)}R</span>
                    </td>
                    <td />
                  </tr>
                </tfoot>
              )}
            </table>
          </div>
        )}
        {daysDesc.length > 30 && (
          <button onClick={() => setShowAllDays(v => !v)}
                  className="mt-2 text-[10px] text-blue-400 hover:text-blue-300">
            {showAllDays ? "Arată doar ultimele 30 de zile" : `Arată toate cele ${daysDesc.length} zile`}
          </button>
        )}
      </div>
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

export function ReportsPage() {
  const [activeTab, setActiveTab] = useState<ReportTab>("transactions");

  return (
    <div className="p-4 md:p-6 space-y-5">
      {/* Page header */}
      <div className="flex items-center gap-3 flex-wrap">
        <BarChart2 size={16} className="text-blue-400" />
        <h1 className="text-sm font-semibold text-white">Rapoarte</h1>
        <span className="text-[10px] text-slate-500">
          Tranzacții, piețe și costuri: direct din MT5 · Uptime, modificări, loguri: din aplicație
        </span>
        <ManualReportButtons />
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
        {activeTab === "costs"        && <CostsTab />}
        {activeTab === "uptime"       && <UptimeTab />}
        {activeTab === "changes"      && <SessionChangesTab />}
        {activeTab === "sistem"       && <SystemLogsTab />}
      </div>
    </div>
  );
}
