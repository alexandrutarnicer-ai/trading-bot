import { useState } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine,
} from "recharts";
import { useEquityCurve, useMt5EquityCurve } from "../api/hooks";
import type { StatsSource } from "../hooks/useStatsSource";
import { SourceToggle } from "./SourceToggle";

interface Props {
  source: StatsSource;
  onSourceChange: (s: StatsSource) => void;
}

type Mt5Metric = "usd" | "r";

function fmtUsd(v: number) {
  return `${v >= 0 ? "+" : ""}${v.toLocaleString("ro-RO", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} $`;
}

function MetricToggle({ metric, onChange }: { metric: Mt5Metric; onChange: (m: Mt5Metric) => void }) {
  const opt = (key: Mt5Metric, label: string) => (
    <button
      onClick={() => onChange(key)}
      className={`px-2 py-0.5 rounded text-[10px] font-medium transition-colors ${
        metric === key
          ? "bg-blue-500/20 text-blue-400"
          : "text-slate-500 hover:text-slate-300"
      }`}
    >
      {label}
    </button>
  );
  return (
    <div className="flex items-center gap-1">
      {opt("usd", "USD")}
      {opt("r", "R")}
    </div>
  );
}

function BotEquityChart() {
  const { data, isLoading } = useEquityCurve();

  if (isLoading) {
    return <div className="h-48 rounded-xl bg-surface-border/30 animate-pulse" />;
  }

  if (!data?.length) {
    return (
      <div className="h-48 flex items-center justify-center text-slate-500 text-sm">
        Niciun trade închis încă
      </div>
    );
  }

  // For the combined total: sum all outcomes sorted by date (R cumulat per sesiune, agregat pe timeline)
  const allPoints = [...data].sort((a, b) => a.date.localeCompare(b.date));
  const sessionCum: Record<string, number> = {};
  const combined: { date: string; total: number }[] = [];
  for (const p of allPoints) {
    sessionCum[p.session_id] = p.cumulative_r;
    const total = Object.values(sessionCum).reduce((a, b) => a + b, 0);
    combined.push({ date: p.date.slice(0, 10), total: Math.round(total * 100) / 100 });
  }

  const lastTotal = combined.at(-1)?.total ?? 0;
  const totalColor = lastTotal >= 0 ? "#22c55e" : "#ef4444";

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-xs text-slate-400">R cumulat — toate sesiunile</span>
        <span className={`text-sm font-bold ${lastTotal >= 0 ? "text-profit" : "text-loss"}`}>
          {lastTotal >= 0 ? "+" : ""}{lastTotal}R
        </span>
      </div>
      <ResponsiveContainer width="100%" height={180}>
        <LineChart data={combined} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#2a2d3d" />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 9, fill: "#64748b" }}
            tickLine={false}
            interval="preserveStartEnd"
          />
          <YAxis
            tick={{ fontSize: 9, fill: "#64748b" }}
            tickLine={false}
            axisLine={false}
          />
          <Tooltip
            contentStyle={{ background: "#1a1d27", border: "1px solid #2a2d3d", borderRadius: 8 }}
            labelStyle={{ color: "#94a3b8", fontSize: 10 }}
            itemStyle={{ color: totalColor, fontSize: 11 }}
            formatter={(v) => { const n = Number(v); return [`${n >= 0 ? "+" : ""}${n}R`, "Total"]; }}
          />
          <ReferenceLine y={0} stroke="#2a2d3d" strokeDasharray="4 4" />
          <Line
            type="monotone"
            dataKey="total"
            stroke={totalColor}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function Mt5EquityChart() {
  const [metric, setMetric] = useState<Mt5Metric>("usd");
  const { data, isLoading } = useMt5EquityCurve(metric);
  const isR = metric === "r";

  if (isLoading) {
    return <div className="h-48 rounded-xl bg-surface-border/30 animate-pulse" />;
  }

  if (!data?.connected) {
    return (
      <div className="h-48 flex items-center justify-center text-slate-500 text-sm text-center px-4">
        MT5 neconectat — {data?.error ?? "curba directă nu este disponibilă"}
      </div>
    );
  }

  if (!data.points.length) {
    return (
      <div className="h-48 flex items-center justify-center text-slate-500 text-sm text-center px-4">
        {isR
          ? "Niciun trade cu SL rezolvabil în istoricul MT5 — încearcă USD"
          : "Niciun trade închis încă"}
      </div>
    );
  }

  const combined = data.points.map(p => ({ date: p.date.slice(0, 10), total: p.value }));
  const lastTotal = combined.at(-1)?.total ?? 0;
  const totalColor = lastTotal >= 0 ? "#22c55e" : "#ef4444";
  const fmtVal = (v: number) => isR ? `${v >= 0 ? "+" : ""}${v.toFixed(3)}R` : fmtUsd(v);

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-400">
            {isR ? "R cumulat MT5" : "P&L cumulat MT5"} — toate tranzacțiile
          </span>
          <MetricToggle metric={metric} onChange={setMetric} />
        </div>
        <span className={`text-sm font-bold ${lastTotal >= 0 ? "text-profit" : "text-loss"}`}>
          {fmtVal(lastTotal)}
        </span>
      </div>
      <ResponsiveContainer width="100%" height={180}>
        <LineChart data={combined} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#2a2d3d" />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 9, fill: "#64748b" }}
            tickLine={false}
            interval="preserveStartEnd"
          />
          <YAxis
            tick={{ fontSize: 9, fill: "#64748b" }}
            tickLine={false}
            axisLine={false}
          />
          <Tooltip
            contentStyle={{ background: "#1a1d27", border: "1px solid #2a2d3d", borderRadius: 8 }}
            labelStyle={{ color: "#94a3b8", fontSize: 10 }}
            itemStyle={{ color: totalColor, fontSize: 11 }}
            formatter={(v) => [fmtVal(Number(v)), isR ? "R" : "P&L"]}
          />
          <ReferenceLine y={0} stroke="#2a2d3d" strokeDasharray="4 4" />
          <Line
            type="monotone"
            dataKey="total"
            stroke={totalColor}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function EquityChart({ source, onSourceChange }: Props) {
  return (
    <div className="space-y-2">
      <SourceToggle source={source} onChange={onSourceChange} />
      {source === "mt5" ? <Mt5EquityChart /> : <BotEquityChart />}
    </div>
  );
}
