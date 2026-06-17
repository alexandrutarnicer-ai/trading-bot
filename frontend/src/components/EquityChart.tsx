import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine,
} from "recharts";
import { useEquityCurve } from "../api/hooks";

const SESSION_COLORS: Record<string, string> = {
  session1: "#3b82f6",
  session2: "#8b5cf6",
  session3: "#f59e0b",
  session4: "#06b6d4",
  session5: "#ec4899",
  session6: "#10b981",
};

export function EquityChart() {
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

  // Build combined chart: one entry per trade, R cumulat total per sesiune
  // Adunam R cumulat per sesiune si le agregam pe timeline
  const sessions = [...new Set(data.map(p => p.session_id))];

  // Group by session, build cumulative series
  const bySession: Record<string, { date: string; r: number }[]> = {};
  for (const s of sessions) {
    bySession[s] = data.filter(p => p.session_id === s).map(p => ({
      date: p.date,
      r:    p.cumulative_r,
    }));
  }

  // For the combined total: sum all outcomes sorted by date
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
