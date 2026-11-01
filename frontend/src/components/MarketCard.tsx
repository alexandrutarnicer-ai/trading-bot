import type { MarketCardData, MarketEngine, MarketState, MarketEngineId } from "../api/types";

// Culorile engine-urilor — aceleasi ca ENGINE_THEME (EngineControlCards) si THEME (EnginePerformance)
export const ENGINE_COLOR: Record<MarketEngineId, { bar: string; badge: string; label: string }> = {
  custom: { bar: "bg-emerald-400", badge: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30", label: "CUSTOM" },
  ai:     { bar: "bg-purple-400",  badge: "bg-purple-500/15 text-purple-300 border-purple-500/30",   label: "AI" },
  daily:  { bar: "bg-cyan-400",    badge: "bg-cyan-500/15 text-cyan-300 border-cyan-500/30",         label: "DAILY" },
  noisy:  { bar: "bg-amber-400",   badge: "bg-amber-500/15 text-amber-300 border-amber-500/30",      label: "NOISY" },
};

export const STATE_STYLE: Record<MarketState, { dot: string; pill: string }> = {
  in_position: { dot: "bg-blue-400 animate-pulse", pill: "bg-blue-500/15 text-blue-300" },
  active:      { dot: "bg-profit",                 pill: "bg-profit/15 text-profit" },
  observe:     { dot: "bg-sky-300/70",             pill: "bg-sky-500/10 text-sky-300" },
  idle:        { dot: "bg-slate-500",              pill: "bg-slate-500/15 text-slate-400" },
  blocked:     { dot: "bg-warn",                   pill: "bg-warn/15 text-warn" },
  stopped:     { dot: "bg-slate-700",              pill: "bg-slate-700/30 text-slate-500" },
};

const MODE_TAG: Record<MarketEngine["mode"], string | null> = {
  live: null, execute: "EXEC", obs: "OBS", shadow: "SHADOW",
};

const usd = (v: number) => `${v >= 0 ? "+" : ""}${v.toFixed(2)} $`;
const pnlCls = (v: number) => (v > 0 ? "text-profit" : v < 0 ? "text-loss" : "text-slate-400");

function EngineRow({ e }: { e: MarketEngine }) {
  const c = ENGINE_COLOR[e.engine];
  const tag = MODE_TAG[e.mode];
  const ref = e.engine === "custom" ? e.ref : e.engine === "noisy" ? e.tf ?? "" : "";
  return (
    <div className="flex items-center gap-1.5 text-[10px] min-w-0" title={`${c.label}${ref ? " " + ref : ""} — ${e.status_label}: ${e.reason}`}>
      <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${STATE_STYLE[e.status].dot}`} />
      <span className={`px-1 rounded border font-bold flex-shrink-0 ${c.badge}`}>
        {c.label}{ref ? <span className="font-normal opacity-80"> {ref}</span> : null}
      </span>
      {tag && <span className="text-[9px] text-slate-500 border border-slate-700 rounded px-0.5 flex-shrink-0">{tag}</span>}
      <span className="text-slate-400 truncate">{e.reason}</span>
    </div>
  );
}

export function MarketCard({ m, selected, onClick }: { m: MarketCardData; selected: boolean; onClick: () => void }) {
  const st = m.stats;
  const virt = m.engines.filter(e => e.virtual_today && e.virtual_today.trades > 0);
  return (
    <button
      onClick={onClick}
      className={`text-left rounded-xl border bg-surface-card overflow-hidden transition-colors flex flex-col ${
        selected ? "border-blue-500/60 ring-1 ring-blue-500/40" : "border-surface-border hover:border-slate-600"
      } ${m.status === "stopped" ? "opacity-70" : ""}`}
    >
      {/* banda segmentata: cate un segment colorat pe fiecare engine care foloseste piata */}
      <div className="flex h-1 w-full">
        {m.engine_ids.map(id => <div key={id} className={`flex-1 ${ENGINE_COLOR[id].bar}`} />)}
      </div>
      <div className="p-3 flex flex-col gap-2 flex-1">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-baseline gap-1.5 min-w-0">
            <span className="text-sm font-bold text-white truncate">{m.symbol}</span>
            {m.direction && <span className="text-[9px] text-slate-500">{m.direction}</span>}
          </div>
          <span className={`text-[9px] font-semibold px-1.5 py-0.5 rounded flex-shrink-0 ${STATE_STYLE[m.status].pill}`}>
            {m.status_label}
          </span>
        </div>

        <div className="space-y-1">
          {m.engines.map(e => <EngineRow key={`${e.engine}-${e.ref}`} e={e} />)}
        </div>

        <div className="mt-auto pt-1.5 border-t border-surface-border/50 text-[10px] text-slate-500 space-y-0.5">
          <div className="flex items-center gap-2 flex-wrap">
            {st ? (
              <>
                <span><strong className="text-slate-300">{st.trades}</strong> trades</span>
                {st.win_rate != null && <span>WR <strong className="text-slate-300">{st.win_rate}%</strong></span>}
                {st.trades > 0 && <span className={pnlCls(st.pnl)}>{usd(st.pnl)}</span>}
              </>
            ) : <span className="text-warn/70">MT5 indisponibil</span>}
            <span className="ml-auto">semnale azi <strong className="text-slate-300">{m.signals_today}</strong></span>
          </div>
          {st && (st.pnl_today !== 0 || st.pnl_yesterday !== 0) && (
            <div className="flex gap-2">
              {st.pnl_today !== 0 && <span>azi <span className={pnlCls(st.pnl_today)}>{usd(st.pnl_today)}</span></span>}
              {st.pnl_yesterday !== 0 && <span>ieri <span className={pnlCls(st.pnl_yesterday)}>{usd(st.pnl_yesterday)}</span></span>}
            </div>
          )}
          {(m.positions > 0 || m.pending > 0) && (
            <div className="text-blue-300">
              {m.positions > 0 && `${m.positions} poziție/ii deschise`}{m.positions > 0 && m.pending > 0 && " · "}
              {m.pending > 0 && `${m.pending} ordin(e) în așteptare`}
            </div>
          )}
          {virt.map(e => (
            <div key={e.engine} className="text-slate-500">
              {ENGINE_COLOR[e.engine].label} virtual azi: {e.virtual_today!.trades} trade-uri ·{" "}
              <span className={pnlCls(e.virtual_today!.R)}>{e.virtual_today!.R >= 0 ? "+" : ""}{e.virtual_today!.R}R</span>
            </div>
          ))}
        </div>
      </div>
    </button>
  );
}
