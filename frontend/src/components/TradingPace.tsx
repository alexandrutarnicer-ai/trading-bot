import { Activity, Brain, CalendarClock, Gauge } from "lucide-react";
import { useTradingPace } from "../api/hooks";
import type { EngineId, EnginePace, PaceConfidence } from "../api/types";
import { InfoTooltip } from "./InfoTooltip";

/**
 * Ritmul de tranzactionare pe engine — inlocuieste vechea „Frecventa estimata"
 * (suma din backteste, doar Custom, supraestima ~4,5x). Sursa: /dashboard/trading-pace —
 * trade-uri INCHISE reale (MT5; Daily = virtuale shadow), saptamani complete din regimul
 * curent (dupa ultima schimbare de configuratie), ponderare exponentiala, cache 15 min.
 */

const ENGINE: Record<EngineId, { label: string; text: string; border: string; icon: typeof Activity }> = {
  custom: { label: "Custom Engine", text: "text-emerald-300", border: "border-emerald-500/30", icon: Activity },
  ai:     { label: "AI Engine",     text: "text-purple-300",  border: "border-purple-500/30",  icon: Brain },
  daily:  { label: "Daily Engine",  text: "text-cyan-300",    border: "border-cyan-500/30",    icon: CalendarClock },
};

const CONF: Record<PaceConfidence, { label: string; cls: string }> = {
  insufficient: { label: "Date insuficiente", cls: "bg-slate-700/50 text-slate-400" },
  low:          { label: "Încredere scăzută", cls: "bg-warn/15 text-warn" },
  medium:       { label: "Încredere medie",   cls: "bg-blue-500/15 text-blue-300" },
  high:         { label: "Încredere ridicată", cls: "bg-profit/15 text-profit" },
};

const fmtDate = (iso?: string | null) => (iso ? iso.split("-").reverse().join(".") : "—");

function PaceCard({ id, p }: { id: EngineId; p?: EnginePace }) {
  const th = ENGINE[id];
  const Icon = th.icon;
  const conf = CONF[p?.confidence ?? "insufficient"];
  const unit = p?.virtual ? "trade-uri virtuale / săpt" : "trade-uri / săpt";
  return (
    <div className={`bg-surface-card rounded-xl border px-4 py-3 space-y-1.5 ${th.border}`}>
      <div className="flex items-center gap-2">
        <Icon size={13} className={th.text} />
        <span className={`text-[11px] font-semibold uppercase tracking-wider ${th.text}`}>{th.label}</span>
        <span className={`ml-auto text-[10px] px-1.5 py-0.5 rounded ${conf.cls}`}>{conf.label}</span>
      </div>
      {p?.per_week != null ? (
        <p className="text-xl font-bold font-mono text-white">
          ≈ {p.per_week.toFixed(1)} <span className="text-xs font-normal text-slate-400">{unit}</span>
          <span className="text-[11px] font-normal text-slate-500"> · tipic {p.low}–{p.high}</span>
        </p>
      ) : (
        <p className="text-sm text-slate-400">
          {p?.weeks ? `${p.trades_in_window} trade-uri în ${p.weeks} săpt. complete — prea puține` : "Nicio săptămână completă"}
          {p?.regime_since ? ` de la ${fmtDate(p.regime_since)}` : ""}
        </p>
      )}
      <div className="text-[10px] text-slate-500 space-y-0.5">
        <div>Săptămâna curentă: <span className="text-slate-300">{p?.current_week ?? 0}</span>
          {p?.weeks ? ` · bază: ${p.weeks} săpt. complete (${p.trades_in_window} trade-uri)` : ""}</div>
        {p?.previous && p.per_week == null && (
          <div>Înainte de schimbarea din {fmtDate(p.regime_since)}: <span className="text-slate-300">≈ {p.previous.per_week.toFixed(1)}/săpt</span>
            {" "}(tipic {p.previous.low}–{p.previous.high}, {p.previous.weeks} săpt.) — referință, nu estimare</div>
        )}
        {p?.regime_reason && p.per_week != null && (
          <div>Regim curent din {fmtDate(p.regime_since)} ({p.regime_reason})</div>
        )}
        {p?.reference != null && (
          <div>Reper {p.reference_kind === "backtest" ? "backtest" : "reguli"}: <span className="text-slate-300">≈ {p.reference.toFixed(1)}/săpt</span>
            {p.reference_kind === "backtest" && p.previous && ` (real ≈ ${p.previous.per_week.toFixed(1)} — backtestul supraestimează)`}
          </div>
        )}
      </div>
    </div>
  );
}

export function TradingPace() {
  const { data, isLoading } = useTradingPace();
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-1.5">
        <Gauge size={12} className="text-slate-500" />
        <span className="text-[10px] text-slate-500 uppercase tracking-wider">Ritm de tranzacționare</span>
        <InfoTooltip text={
          "Câte trade-uri închide fiecare engine pe săptămână, din istoricul REAL (MT5; Daily = trade-uri virtuale shadow). " +
          "Doar săptămâni complete de după ultima schimbare de configurație care afectează frecvența (piețe, ore, strategii, execuție); " +
          `cele recente cântăresc mai mult (înjumătățire ${data?.half_life_weeks ?? 3} săpt.). „Tipic” = intervalul P20–P80 al săptămânilor. ` +
          "Sub 2 săptămâni complete sau 5 trade-uri: „Date insuficiente” în loc de o cifră fals de precisă. Recalculat la 15 minute."} />
        {data?.computed_at && <span className="ml-auto text-[10px] text-slate-600">calculat {data.computed_at.slice(11, 16)}</span>}
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {isLoading
          ? [0, 1, 2].map(i => <div key={i} className="h-28 rounded-xl bg-surface-card animate-pulse" />)
          : (["custom", "ai", "daily"] as EngineId[]).map(id => <PaceCard key={id} id={id} p={data?.[id]} />)}
      </div>
    </div>
  );
}
