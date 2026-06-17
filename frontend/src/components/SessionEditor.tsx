import { useState } from "react";
import type { ProfileSession, Meta } from "../api/types";
import { BacktestPanel } from "./BacktestPanel";

interface Props {
  session: ProfileSession;
  meta: Meta;
  onChange: (updated: ProfileSession) => void;
}

const HOURS = Array.from({ length: 24 }, (_, i) => i);
const WD_KEYS = [0, 1, 2, 3, 4, 5, 6] as const;

export function SessionEditor({ session, meta, onChange }: Props) {
  const [open, setOpen] = useState(false);

  const upd = (patch: Partial<ProfileSession>) => onChange({ ...session, ...patch });

  const toggleHour = (h: number) => {
    const s = new Set(session.skip_hours);
    s.has(h) ? s.delete(h) : s.add(h);
    upd({ skip_hours: [...s].sort((a, b) => a - b) });
  };

  const toggleWd = (d: number) => {
    const s = new Set(session.skip_weekdays);
    s.has(d) ? s.delete(d) : s.add(d);
    upd({ skip_weekdays: [...s].sort((a, b) => a - b) });
  };

  const toggleMarket = (m: string) => {
    const arr = session.markets.includes(m)
      ? session.markets.filter((x) => x !== m)
      : [...session.markets, m];
    upd({ markets: arr });
  };

  const dirBadgeColor = {
    LONG: "bg-profit/20 text-profit",
    SHORT: "bg-loss/20 text-loss",
    BOTH: "bg-blue-500/20 text-blue-300",
  }[session.direction] ?? "bg-slate-700 text-slate-300";

  return (
    <div className="bg-surface-card rounded-xl border border-surface-border overflow-hidden">
      {/* Header row */}
      <button
        className="w-full flex items-center gap-3 px-4 py-3 hover:bg-surface-border/20 transition-colors text-left"
        onClick={() => setOpen((o) => !o)}
      >
        <span className="text-sm font-semibold text-white flex-1">{session.label}</span>
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${dirBadgeColor}`}>
          {session.direction}
        </span>
        <span className={`text-xs px-2 py-0.5 rounded-full ${session.execute_trades ? "bg-blue-500/20 text-blue-300" : "bg-slate-700 text-slate-400"}`}>
          {session.execute_trades ? "LIVE" : "OBS"}
        </span>
        <span className="text-xs text-slate-400">{session.markets.join(" · ")}</span>
        <span className="text-slate-500 ml-2">{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div className="border-t border-surface-border px-4 py-4 space-y-5">
          {/* Markets */}
          <Section label="Piete">
            <div className="flex flex-wrap gap-2">
              {meta.available_markets.map((m) => (
                <button
                  key={m}
                  onClick={() => toggleMarket(m)}
                  className={`text-xs px-2 py-0.5 rounded border transition-colors ${
                    session.markets.includes(m)
                      ? "bg-blue-600 border-blue-500 text-white"
                      : "bg-transparent border-surface-border text-slate-400 hover:border-slate-500"
                  }`}
                >
                  {m}
                </button>
              ))}
            </div>
          </Section>

          {/* Timeframes + direction */}
          <div className="grid grid-cols-3 gap-4">
            <Section label="Entry TF">
              <SegControl
                options={meta.timeframes}
                value={session.entry_tf}
                onChange={(v) => upd({ entry_tf: v })}
              />
            </Section>
            <Section label="Trend TF">
              <SegControl
                options={meta.trend_timeframes}
                value={session.trend_tf}
                onChange={(v) => upd({ trend_tf: v })}
              />
            </Section>
            <Section label="Directie">
              <SegControl
                options={meta.directions}
                value={session.direction}
                onChange={(v) => upd({ direction: v })}
              />
            </Section>
          </div>

          {/* Session hours + expire + pullback */}
          <div className="grid grid-cols-4 gap-4">
            <NumField label="Start ora" value={session.session_start} min={0} max={23}
              onChange={(v) => upd({ session_start: v })} />
            <NumField label="End ora" value={session.session_end} min={1} max={24}
              onChange={(v) => upd({ session_end: v })} />
            <NumField label="Expire bare" value={session.expire_bars} min={1} max={20}
              onChange={(v) => upd({ expire_bars: v })} />
            <NumField label="Pullback window" value={session.pullback_window} min={1} max={20}
              onChange={(v) => upd({ pullback_window: v })} />
          </div>

          {/* R-ratios */}
          <div className="grid grid-cols-3 gap-4">
            <NumField label="R-base" value={session.r_base} step={0.5}
              onChange={(v) => upd({ r_base: v })} />
            <NumField label="R-mid" value={session.r_mid} step={0.5}
              onChange={(v) => upd({ r_mid: v })} />
            <NumField label="R-top" value={session.r_top} step={0.5}
              onChange={(v) => upd({ r_top: v })} />
          </div>

          {/* RSI */}
          <Section label="RSI">
            <div className="space-y-2">
              <Toggle label="RSI activat" value={session.rsi_enabled}
                onChange={(v) => upd({ rsi_enabled: v })} />
              {session.rsi_enabled && (
                <div className="grid grid-cols-4 gap-3 mt-2">
                  <NumField label="Buy min" value={session.rsi_buy_min}
                    onChange={(v) => upd({ rsi_buy_min: v })} />
                  <NumField label="Buy max" value={session.rsi_buy_max}
                    onChange={(v) => upd({ rsi_buy_max: v })} />
                  <NumField label="Sell min" value={session.rsi_sell_min}
                    onChange={(v) => upd({ rsi_sell_min: v })} />
                  <NumField label="Sell max" value={session.rsi_sell_max}
                    onChange={(v) => upd({ rsi_sell_max: v })} />
                </div>
              )}
            </div>
          </Section>

          {/* EMA + execute + circuit breaker + risk */}
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Toggle label="EMA alignment" value={session.ema_alignment_enabled}
                onChange={(v) => upd({ ema_alignment_enabled: v })} />
              <Toggle label="Execute trades (LIVE)" value={session.execute_trades}
                onChange={(v) => upd({ execute_trades: v })} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <NumField label="Circuit breaker" value={session.circuit_breaker} min={1}
                onChange={(v) => upd({ circuit_breaker: v })} />
              <NumField label="Risk %" value={session.risk_pct * 100} step={0.1}
                onChange={(v) => upd({ risk_pct: v / 100 })} />
            </div>
          </div>

          {/* Skip hours */}
          <Section label="Skip ore">
            <div className="flex flex-wrap gap-1">
              {HOURS.map((h) => (
                <button
                  key={h}
                  onClick={() => toggleHour(h)}
                  className={`w-7 h-6 text-xs rounded transition-colors ${
                    session.skip_hours.includes(h)
                      ? "bg-warn/80 text-black font-medium"
                      : "bg-surface-border/50 text-slate-400 hover:bg-surface-border"
                  }`}
                >
                  {h}
                </button>
              ))}
            </div>
          </Section>

          {/* Skip weekdays */}
          <Section label="Skip zile">
            <div className="flex gap-1">
              {WD_KEYS.map((d) => (
                <button
                  key={d}
                  onClick={() => toggleWd(d)}
                  className={`px-2 py-1 text-xs rounded transition-colors ${
                    session.skip_weekdays.includes(d)
                      ? "bg-warn/80 text-black font-medium"
                      : "bg-surface-border/50 text-slate-400 hover:bg-surface-border"
                  }`}
                >
                  {meta.weekday_names[String(d)]}
                </button>
              ))}
            </div>
          </Section>

          {/* Backtest */}
          <Section label="Backtest">
            <BacktestPanel session={session} />
          </Section>
        </div>
      )}
    </div>
  );
}

// ── sub-components ──────────────────────────────────────────────

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <div className="text-xs text-slate-500 font-medium uppercase tracking-wider">{label}</div>
      {children}
    </div>
  );
}

function SegControl({
  options, value, onChange,
}: {
  options: string[]; value: string; onChange: (v: string) => void;
}) {
  return (
    <div className="flex gap-1 flex-wrap">
      {options.map((o) => (
        <button
          key={o}
          onClick={() => onChange(o)}
          className={`text-xs px-2 py-0.5 rounded border transition-colors ${
            value === o
              ? "bg-blue-600 border-blue-500 text-white"
              : "bg-transparent border-surface-border text-slate-400 hover:border-slate-500"
          }`}
        >
          {o}
        </button>
      ))}
    </div>
  );
}

function NumField({
  label, value, min, max, step = 1, onChange,
}: {
  label: string; value: number; min?: number; max?: number;
  step?: number; onChange: (v: number) => void;
}) {
  return (
    <div className="space-y-1">
      <label className="text-xs text-slate-500">{label}</label>
      <input
        type="number"
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full bg-surface border border-surface-border rounded px-2 py-1 text-xs text-white focus:outline-none focus:border-blue-500"
      />
    </div>
  );
}

function Toggle({
  label, value, onChange,
}: {
  label: string; value: boolean; onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex items-center gap-2 cursor-pointer select-none">
      <div
        onClick={() => onChange(!value)}
        className={`w-8 h-4 rounded-full transition-colors relative ${value ? "bg-blue-600" : "bg-surface-border"}`}
      >
        <div className={`absolute top-0.5 w-3 h-3 bg-white rounded-full shadow transition-transform ${value ? "translate-x-4" : "translate-x-0.5"}`} />
      </div>
      <span className="text-xs text-slate-300">{label}</span>
    </label>
  );
}
