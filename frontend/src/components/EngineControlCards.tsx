import { useState } from "react";
import { Activity, Brain, CalendarClock, Loader2, Play, Square, Power, Zap, Sparkles } from "lucide-react";
import { useEngines, useEngineAction } from "../api/hooks";
import type { LifecycleEngineId, EngineState } from "../api/types";

/**
 * Carduri de stare + quick actions pentru fiecare engine (Engine Lifecycle comun, /engines).
 * Statusul vine din PID-ul real al procesului (nu dintr-un fisier de stare). Start/Stop sunt
 * verificate pe backend (procesul trebuie sa fie viu / oprit) — un esec apare in card.
 * Actiunile care pot plasa sau opri ordine reale cer confirmare.
 */

export const ENGINE_THEME: Record<LifecycleEngineId, { text: string; dot: string; bg: string; border: string; icon: typeof Activity }> = {
  custom: { text: "text-emerald-300", dot: "bg-emerald-400", bg: "bg-emerald-500/10", border: "border-emerald-500/30", icon: Activity },
  ai:     { text: "text-purple-300",  dot: "bg-purple-400",  bg: "bg-purple-500/10",  border: "border-purple-500/30",  icon: Brain },
  daily:  { text: "text-cyan-300",    dot: "bg-cyan-400",    bg: "bg-cyan-500/10",    border: "border-cyan-500/30",    icon: CalendarClock },
  noisy:  { text: "text-amber-300",   dot: "bg-amber-400",   bg: "bg-amber-500/10",   border: "border-amber-500/30",   icon: Zap },
  special: { text: "text-pink-300",   dot: "bg-pink-400",    bg: "bg-pink-500/10",    border: "border-pink-500/30",    icon: Sparkles },
};

export const NOISY_START_CONFIRM =
  "Start Noisy Engine?  — RISK LEVEL: HIGH\n\n" +
  "Acest engine:\n" +
  "• analizează piața foarte des (la fiecare bară de 1 sau 5 minute) și poate deschide mai multe trade-uri pe zi;\n" +
  "• suportă costuri relativ mai mari (spread, comision, slippage) față de celelalte engine-uri;\n" +
  "• e expus la volatilitate și poate produce pierderi mai rapid.\n\n" +
  "Acum rulează în SHADOW: trade-uri virtuale pe prețuri reale, ZERO ordine. Are buget propriu și se oprește singur la pragul setat.";

const CONFIRM: Partial<Record<string, string>> = {
  "custom:start": "Pornești Custom Engine? Sesiunile cu execuție activă plasează ordine REALE în MT5.",
  "custom:stop":  "Oprești Custom Engine? Pozițiile deja deschise rămân în MT5 cu SL/TP, dar nu mai sunt monitorizate.",
  "ai:start":     "Pornești AI Engine? Pe piețele în mod Activ poate plasa ordine în contul MT5 conectat.",
  "ai:stop":      "Oprești AI Engine? Pozițiile AI deschise rămân în MT5 cu SL/TP.",
  "noisy:start":  NOISY_START_CONFIRM,
  "special:stop": "Oprești Special Engine? Pozițiile reale deschise (dacă există) rămân cu SL-ul lor; la repornire " +
                  "se închid la finalul sesiunii sau dacă sunt din altă zi.",
};

function EngineCard({ e }: { e: EngineState }) {
  const act = useEngineAction();
  const [err, setErr] = useState<string | null>(null);
  const th = ENGINE_THEME[e.id];
  const Icon = th.icon;
  const busy = act.isPending;

  function run(action: "start" | "stop" | "autostart/enable" | "autostart/disable") {
    const msg = CONFIRM[`${e.id}:${action}`];
    if (msg && !window.confirm(msg)) return;
    setErr(null);
    act.mutate({ id: e.id, action }, { onError: (x: Error) => setErr(x.message) });
  }

  return (
    <div className={`rounded-xl border px-4 py-3 space-y-2 ${e.running ? `${th.bg} ${th.border}` : "bg-surface-card border-surface-border"}`}>
      <div className="flex items-center gap-2">
        <Icon size={14} className={e.running ? th.text : "text-slate-500"} />
        <span className="text-xs font-semibold uppercase tracking-wider text-white">{e.label}</span>
        <span className={`ml-auto flex items-center gap-1.5 text-[11px] font-semibold ${e.running ? th.text : "text-slate-500"}`}>
          <span className="relative flex h-2 w-2">
            {e.running && <span className={`animate-ping absolute inline-flex h-full w-full rounded-full ${th.dot} opacity-75`} />}
            <span className={`relative inline-flex rounded-full h-2 w-2 ${e.running ? th.dot : "bg-slate-600"}`} />
          </span>
          {e.running ? "RUNNING" : "STOPPED"}
        </span>
      </div>
      <div className="text-[11px] text-slate-400 truncate" title={e.detail}>
        {e.detail}{e.running && e.pid ? <span className="text-slate-600"> · PID {e.pid}</span> : null}
      </div>
      <div className="flex items-center gap-2">
        {e.running ? (
          <button onClick={() => run("stop")} disabled={busy}
            className="flex items-center gap-1.5 text-[11px] px-3 py-1 rounded-lg bg-loss/15 text-loss hover:bg-loss/25 disabled:opacity-50 font-semibold">
            {busy ? <Loader2 size={12} className="animate-spin" /> : <Square size={12} />} Stop
          </button>
        ) : (
          <button onClick={() => run("start")} disabled={busy}
            className={`flex items-center gap-1.5 text-[11px] px-3 py-1 rounded-lg ${th.bg} ${th.text} hover:brightness-125 disabled:opacity-50 font-semibold border ${th.border}`}>
            {busy ? <Loader2 size={12} className="animate-spin" /> : <Play size={12} />} Start
          </button>
        )}
        {e.id === "noisy" ? (
          <span className="ml-auto text-[10px] px-2 py-0.5 rounded border border-surface-border text-slate-500"
                title="Noisy Engine nu pornește automat — doar manual, cu confirmare">
            <Power size={10} className="inline mr-1" />Doar manual
          </span>
        ) : (
        <button
          onClick={() => run(e.autostart ? "autostart/disable" : "autostart/enable")}
          disabled={busy || e.autostart == null}
          title={"Pornire automată la login Windows (Task Scheduler; cere confirmare UAC). " +
                 "Statusul se actualizează în ~30s după confirmare."}
          className={`ml-auto flex items-center gap-1 text-[10px] px-2 py-0.5 rounded border transition-colors disabled:opacity-40 ${
            e.autostart ? `${th.border} ${th.text}` : "border-surface-border text-slate-500 hover:text-slate-300"}`}>
          <Power size={10} /> Autostart {e.autostart == null ? "?" : e.autostart ? "ON" : "OFF"}
        </button>
        )}
      </div>
      {(err || e.error) && (
        <pre className="text-[10px] text-loss whitespace-pre-wrap max-h-24 overflow-auto">{err ?? e.error}</pre>
      )}
    </div>
  );
}

export function EngineControlCards() {
  const { data, isLoading, error } = useEngines();
  if (isLoading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
        {[0, 1, 2, 3].map(i => <div key={i} className="h-24 rounded-xl bg-surface-card animate-pulse" />)}
      </div>
    );
  }
  if (error || !data) {
    return <div className="text-[11px] text-loss">Starea engine-urilor indisponibilă (API).</div>;
  }
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
      {data.map(e => <EngineCard key={e.id} e={e} />)}
    </div>
  );
}
