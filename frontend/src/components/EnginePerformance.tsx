import { Activity, Brain, CalendarClock, Sigma, Zap } from "lucide-react";
import { useEnginePerformance, useDailyStatus, useAiStatus, useEngines, useNoisyStatus } from "../api/hooks";
import type { EnginePerf, EngineId } from "../api/types";

/**
 * Performanta pe engine — O SINGURA componenta folosita in doua forme:
 *  - <EnginePerformanceCards />   = cele 4 carduri de sus (TOTAL / Custom / AI / Daily)
 *  - <EnginePerformanceSection /> = sectiunile de analiza de jos, acelasi pattern pentru toate
 * Sursa: /mt5/engine-performance — aceeasi lista MT5 (pozitii inchise, dedup pe pozitie) ca
 * Tranzactii si Statistici, deci cifrele se leaga. Daily Engine ruleaza in SHADOW: banii reali
 * sunt 0, iar trade-urile virtuale sunt afisate separat, in R, niciodata adunate la bani.
 */

type Key = "total" | EngineId | "noisy";
type EngineKey = Exclude<Key, "total">;

const THEME: Record<Key, { label: string; text: string; dot: string; border: string; bg: string; icon: typeof Activity }> = {
  total:  { label: "TOTAL",         text: "text-blue-300",    dot: "bg-blue-400",    border: "border-blue-500/30",    bg: "bg-blue-500/5",    icon: Sigma },
  custom: { label: "Custom Engine", text: "text-emerald-300", dot: "bg-emerald-400", border: "border-emerald-500/30", bg: "bg-emerald-500/5", icon: Activity },
  ai:     { label: "AI Engine",     text: "text-purple-300",  dot: "bg-purple-400",  border: "border-purple-500/30",  bg: "bg-purple-500/5",  icon: Brain },
  daily:  { label: "Daily Engine",  text: "text-cyan-300",    dot: "bg-cyan-400",    border: "border-cyan-500/30",    bg: "bg-cyan-500/5",    icon: CalendarClock },
  noisy:  { label: "Noisy Engine",  text: "text-amber-300",   dot: "bg-amber-400",   border: "border-amber-500/30",   bg: "bg-amber-500/5",   icon: Zap },
};

const money = (v: number | null | undefined, cur: string) =>
  v == null ? "—" : `${v > 0 ? "+" : ""}${v.toLocaleString("ro-RO", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${cur}`;
const pnlCls = (v: number | null | undefined) => (v == null || v === 0 ? "text-white" : v > 0 ? "text-profit" : "text-loss");
const rTxt = (v: number | null | undefined) => (v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(2)}R`);

function Stat({ label, value, cls, sub }: { label: string; value: string; cls?: string; sub?: string }) {
  return (
    <div className="min-w-0">
      <div className={`text-sm font-bold font-mono leading-tight truncate ${cls ?? "text-white"}`}>{value}</div>
      <div className="text-[10px] text-slate-500 truncate">{label}{sub ? <span className="text-slate-600"> · {sub}</span> : null}</div>
    </div>
  );
}

function ShadowLine({ engine = "daily" }: { engine?: "daily" | "noisy" }) {
  const { data: d } = useDailyStatus();
  const { data: n } = useNoisyStatus();
  const sc = engine === "noisy" ? n?.scorecard : d?.scorecard;
  return (
    <div className={`text-[10px] border-t pt-1.5 ${engine === "noisy" ? "text-amber-300/80 border-amber-500/20" : "text-cyan-300/80 border-cyan-500/20"}`}>
      SHADOW (virtual, fără bani): {sc?.trades ?? 0} trade-uri · {sc?.wins ?? 0}W / {sc?.losses ?? 0}L ·{" "}
      <span className={pnlCls(sc?.total_R)}>{rTxt(sc?.total_R)}</span>
    </div>
  );
}

function PerfCard({ k, p, cur }: { k: Key; p?: EnginePerf; cur: string }) {
  const th = THEME[k];
  const Icon = th.icon;
  return (
    <div className={`rounded-xl border px-4 py-3 space-y-2 ${th.border} ${th.bg}`}>
      <div className="flex items-center gap-2">
        <Icon size={13} className={th.text} />
        <span className={`text-[11px] font-semibold uppercase tracking-wider ${th.text}`}>{th.label}</span>
        <span className="ml-auto text-[10px] text-slate-500">{p?.trades ?? 0} trade-uri</span>
      </div>
      <div className="grid grid-cols-3 gap-2">
        <Stat label="Win rate" value={p?.win_rate != null ? `${p.win_rate.toFixed(1)}%` : "—"}
              sub={p ? `${p.wins}W/${p.losses}L` : undefined} />
        <Stat label="Profit" value={money(p?.profit, cur)} cls={p?.profit ? "text-profit" : undefined} />
        <Stat label="Loss" value={money(p?.loss, cur)} cls={p?.loss ? "text-loss" : undefined} />
      </div>
      <div className="text-[10px] text-slate-500">
        Rezultat <span className={pnlCls(p?.pnl)}>{money(p?.pnl, cur)}</span>
        {" · "}după costuri <span className={pnlCls(p?.net)}>{money(p?.net, cur)}</span>
      </div>
      {k === "daily" && <ShadowLine />}
      {k === "noisy" && <ShadowLine engine="noisy" />}
    </div>
  );
}

export function EnginePerformanceCards() {
  const { data } = useEnginePerformance();
  const cur = data?.currency ?? "USD";
  if (data && !data.connected) {
    return <div className="text-[11px] text-warn/80">Performanța pe engine indisponibilă — MT5 neconectat ({data.error}).</div>;
  }
  const manual = data?.manual;
  return (
    <div className="space-y-1.5">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
        {(["total", "custom", "ai", "daily", "noisy"] as Key[]).map(k => <PerfCard key={k} k={k} p={data?.[k]} cur={cur} />)}
      </div>
      <p className="text-[10px] text-slate-600">
        Ultimele {data?.days ?? 365} zile · doar poziții închise (P&L flotant: Ordine Active) · profit brut din MT5, costurile
        (comision + swap) separat · cont {data?.is_demo === false ? "REAL" : data?.is_demo ? "DEMO" : "?"}
        {manual && manual.trades > 0 ? ` · ${manual.trades} tranzacții manuale (${money(manual.pnl, cur)}) excluse din TOTAL` : " · TOTAL = cele 4 engine-uri (manualele excluse)"}
      </p>
    </div>
  );
}

/** Sectiunea de analiza a unui engine — acelasi layout pentru toate, difera doar datele + culoarea. */
export function EnginePerformanceSection({ engine }: { engine: EngineKey }) {
  const { data } = useEnginePerformance();
  const { data: engines } = useEngines();
  const { data: ai } = useAiStatus();
  const { data: daily } = useDailyStatus();
  const { data: noisy } = useNoisyStatus();
  const th = THEME[engine];
  const Icon = th.icon;
  const cur = data?.currency ?? "USD";
  const p = data?.[engine];
  const st = engines?.find(e => e.id === engine);

  // Metricile specifice engine-ului (acelasi slot vizual pentru toate)
  let extra: { label: string; value: string; cls?: string }[] = [];
  let chips: string[] = (p?.symbols ?? []).map(s => `${s.symbol} ${s.pnl > 0 ? "+" : ""}${s.pnl.toFixed(2)}`);
  let note = "";
  if (engine === "custom") {
    extra = [{ label: "Medie / trade", value: rTxt(p?.avg_r), cls: pnlCls(p?.avg_r) },
             { label: "Sesiuni", value: st?.detail?.split(" ")[0] ?? "—" }];
    note = "Botul pe reguli (22 sesiuni, o piață fiecare). R calculat din SL-ul original al ordinului.";
  } else if (engine === "ai") {
    const sc = ai?.scorecard;
    extra = [{ label: "Medie / trade", value: rTxt(p?.avg_r), cls: pnlCls(p?.avg_r) },
             { label: "Decizii", value: sc ? `${sc.decisions} (${sc.waits} WAIT)` : "—" }];
    note = "Motorul autonom AI (consiliu Ollama + Gemini, magic 770015). Deciziile vin din ledger-ul motorului.";
  } else if (engine === "noisy") {
    const sc = noisy?.scorecard;
    extra = [{ label: "Shadow (virtual)", value: `${sc?.trades ?? 0} · ${rTxt(sc?.total_R)}`, cls: pnlCls(sc?.total_R) },
             { label: "Stare", value: noisy?.state_label ?? "—" }];
    chips = [`${noisy?.config?.symbol ?? "USDJPY"} ${noisy?.config?.timeframe ?? "M1"}`,
             noisy?.mode === "execute" ? "EXECUȚIE" : "SHADOW",
             noisy?.config ? `${noisy.config.window.start}–${noisy.config.window.end}` : ""].filter(Boolean);
    note = "Frecvență mare: mean reversion pe o singură piață, fără autostart (pornire doar manuală). Bani reali doar în modul Execuție.";
  } else {
    const sc = daily?.scorecard;
    extra = [{ label: "Shadow (virtual)", value: `${sc?.trades ?? 0} · ${rTxt(sc?.total_R)}`, cls: pnlCls(sc?.total_R) },
             { label: "Medie shadow", value: rTxt(sc?.expectancy_R), cls: pnlCls(sc?.expectancy_R) }];
    chips = (daily?.markets ?? []).map(m => `${m.symbol} ${m.window_ro ?? ""}`);
    note = "Intraday ORB la deschiderea Londrei / New York, mod SHADOW: fără ordine reale; banii reali rămân 0 până la activare.";
  }

  return (
    <div className={`bg-surface-card border rounded-xl p-4 space-y-3 ${th.border}`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Icon size={14} className={th.text} />
          <span className="text-sm font-semibold text-white">{th.label}</span>
        </div>
        <span className={`flex items-center gap-1.5 text-[11px] font-medium ${st?.running ? th.text : "text-slate-500"}`}>
          <span className={`h-2 w-2 rounded-full ${st?.running ? th.dot : "bg-slate-600"}`} />
          {st?.running ? "activ" : "oprit"}
        </span>
      </div>
      <div className="grid grid-cols-3 gap-2">
        <Stat label="Trade-uri" value={String(p?.trades ?? 0)} sub={p ? `${p.wins}W / ${p.losses}L` : undefined} />
        <Stat label="Win rate" value={p?.win_rate != null ? `${p.win_rate.toFixed(1)}%` : "—"} />
        <Stat label="Net (după costuri)" value={money(p?.net, cur)} cls={pnlCls(p?.net)} />
      </div>
      <div className="grid grid-cols-2 gap-2 pt-1 border-t border-surface-border">
        {extra.map(x => <Stat key={x.label} label={x.label} value={x.value} cls={x.cls} />)}
      </div>
      {chips.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {chips.map(c => <span key={c} className={`text-[10px] px-1.5 py-0.5 rounded ${th.bg} ${th.text}`}>{c}</span>)}
        </div>
      )}
      <p className="text-[10px] text-slate-600 leading-snug">{note}</p>
    </div>
  );
}
