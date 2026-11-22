import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, RefreshCw, Power } from "lucide-react";
import { apiFetch } from "../api/client";

/**
 * Sanatatea aplicatiei (api/health_monitor.py) + pornirea automata per engine (startup_gate.py).
 * Statusurile vin din verificari reale la 30 s; incidentele = probleme confirmate (un singur mesaj Telegram,
 * reamintiri rare, recuperare confirmata). Nimic de aici nu plaseaza / inchide ordine.
 */
type Comp = { status: string; detail: string; since: string | null; checked: string };
type Incident = { key: string; title: string; detail?: string; severity: string; first_seen_iso?: string; notified: boolean;
                  resolved_iso?: string; duration_s?: number };
type Health = { overall: string; components: Record<string, Comp>; started: string | null; boot_time: string | null;
                last_loop: string | null; startup_event: { last_seen: string; down_min: number; rebooted: boolean } | null;
                incidents: { active: Incident[]; history: Incident[]; outbox: number } };
type AutoRow = { id: string; label: string; eligible: boolean; enabled: boolean | null };

const ST: Record<string, string> = {
  healthy: "bg-profit/15 text-profit", recovering: "bg-sky-500/15 text-sky-300", degraded: "bg-warn/15 text-warn",
  unavailable: "bg-loss/15 text-loss", failed: "bg-loss/25 text-loss",
};
const ST_LABEL: Record<string, string> = {
  healthy: "OK", recovering: "în recuperare", degraded: "degradat", unavailable: "indisponibil", failed: "eșuat",
};
const NAME: Record<string, string> = {
  internet: "Internet", mt5: "MT5", ollama: "Ollama (AI)", gemini: "Gemini (opțional)", disk: "Disc", database: "Baza de date AI",
  telegram: "Telegram", power: "Alimentare / Sleep", "engine:custom": "Custom Engine", "engine:ai": "AI Engine",
  "engine:daily": "Daily Engine", "engine:special": "Special Engine",
};
const fmt = (iso?: string | null) => (iso ? iso.replace("T", " ").slice(5, 16) : "—");
const dur = (s?: number) => (s == null ? "" : s >= 3600 ? `${Math.floor(s / 3600)} h ${Math.floor((s % 3600) / 60)} min` : `${Math.max(1, Math.round(s / 60))} min`);

export const useHealth = () => useQuery<Health>({ queryKey: ["health-full"], queryFn: () => apiFetch("/health/full"),
  refetchInterval: 30_000, refetchIntervalInBackground: false });

export function HealthCard() {
  const qc = useQueryClient();
  const { data } = useHealth();
  const now = useMutation({ mutationFn: () => apiFetch("/health/check", { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["health-full"] }) });
  const comps = Object.entries(data?.components ?? {});
  const active = data?.incidents.active ?? [];
  const hist = [...(data?.incidents.history ?? [])].reverse().slice(0, 8);
  return (
    <div className="rounded-xl border border-surface-border bg-surface p-4 space-y-3">
      <div className="flex items-center gap-2">
        <Activity size={15} className="text-blue-400" />
        <h3 className="text-sm font-semibold text-white">Sănătatea aplicației</h3>
        {data && <span className={`text-[10px] px-1.5 py-0.5 rounded ${ST[data.overall]}`}>{ST_LABEL[data.overall] ?? data.overall}</span>}
        <span className="text-[10px] text-slate-500">verificat la 30 s · aplicația pornită {fmt(data?.started)} · Windows pornit {fmt(data?.boot_time)}</span>
        <button onClick={() => now.mutate()} disabled={now.isPending}
          className="ml-auto flex items-center gap-1 text-[11px] text-slate-400 hover:text-white disabled:opacity-40">
          <RefreshCw size={12} className={now.isPending ? "animate-spin" : ""} /> Verifică acum
        </button>
      </div>
      {data?.startup_event && (
        <div className="text-[11px] rounded bg-warn/10 border border-warn/30 text-warn px-3 py-1.5">
          La pornire: aplicația fusese oprită NECURAT (crash / pană de curent / restart) — ultimul semn de viață
          {" "}{fmt(data.startup_event.last_seen)}, întrerupere ~{data.startup_event.down_min} min
          {data.startup_event.rebooted ? " · Windows a repornit" : ""}.
        </div>
      )}
      {!data && <div className="text-[11px] text-slate-500">Se încarcă… (prima verificare apare la ~30 s după pornirea API-ului)</div>}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
        {comps.map(([k, c]) => (
          <div key={k} className="flex items-center gap-2 text-[11px]">
            <span className={`px-1.5 rounded w-24 text-center shrink-0 ${ST[c.status] ?? ""}`}>{ST_LABEL[c.status] ?? c.status}</span>
            <span className="text-slate-200 w-32 shrink-0">{NAME[k] ?? k}</span>
            <span className="text-slate-500 truncate" title={c.detail}>{c.detail}</span>
          </div>
        ))}
      </div>
      <div className="border-t border-surface-border/60 pt-2 space-y-1">
        <div className="text-[11px] text-slate-300">Incidente active {active.length ? `(${active.length})` : "— niciunul"}</div>
        {active.map(i => (
          <div key={i.key} className="text-[11px] text-slate-400">
            <span className={i.severity === "critical" ? "text-loss" : i.severity === "warning" ? "text-warn" : "text-sky-300"}>● </span>
            <b className="text-slate-200">{i.title}</b> · din {fmt(i.first_seen_iso)} · {i.notified ? "notificat pe Telegram" : "în confirmare (încă nenotificat)"}
          </div>
        ))}
        {(data?.incidents.outbox ?? 0) > 0 && (
          <div className="text-[11px] text-warn">{data!.incidents.outbox} mesaje Telegram în așteptare — se trimit automat când revine conexiunea</div>
        )}
        {hist.length > 0 && <div className="text-[11px] text-slate-500 pt-1">Rezolvate recent:</div>}
        {hist.map((i, n) => (
          <div key={n} className="text-[10px] text-slate-500">✓ {i.title} · {fmt(i.first_seen_iso)} → {fmt(i.resolved_iso)} ({dur(i.duration_s)})</div>
        ))}
      </div>
      <p className="text-[10px] text-slate-600">
        O componentă căzută nu oprește engine-urile care nu depind de ea (ex. Ollama afectează doar AI Engine; Telegram
        indisponibil nu blochează tranzacționarea — mesajele așteaptă). Pozițiile deschise rămân mereu protejate de SL / TP la broker.
      </p>
    </div>
  );
}

export function AutostartCard() {
  const qc = useQueryClient();
  const { data } = useQuery<AutoRow[]>({ queryKey: ["autostart-all"], queryFn: () => apiFetch("/engines/autostart/all"),
    refetchInterval: 60_000, refetchIntervalInBackground: false });
  const act = useMutation({
    mutationFn: ({ id, on }: { id: string; on: boolean }) =>
      apiFetch(`/engines/${id}/autostart/${on ? "enable" : "disable"}`, { method: "POST" }),
    onSuccess: () => setTimeout(() => qc.invalidateQueries({ queryKey: ["autostart-all"] }), 15_000),
  });
  return (
    <div className="rounded-xl border border-surface-border bg-surface p-4 space-y-2">
      <div className="flex items-center gap-2">
        <Power size={15} className="text-blue-400" />
        <h3 className="text-sm font-semibold text-white">Pornire automată (după login / restart Windows)</h3>
        <span className="text-[10px] text-slate-500">oprită implicit · fiecare separat · confirmare UAC</span>
      </div>
      {(data ?? []).map(r => (
        <div key={r.id} className="flex items-center gap-3 text-[11px]">
          <span className="text-slate-200 w-56">{r.label}</span>
          {!r.eligible ? (
            <span className="text-slate-500">doar pornire manuală (exclus intenționat)</span>
          ) : (
            <>
              <span className={r.enabled ? "text-profit" : "text-slate-500"}>{r.enabled == null ? "?" : r.enabled ? "PORNITĂ" : "oprită"}</span>
              <button disabled={act.isPending}
                onClick={() => (r.enabled || window.confirm(`Activezi pornirea automată pentru ${r.label}? La fiecare login Windows ` +
                  "aplicația verifică internetul, MT5 (cont conectat) și — pentru AI — Ollama, apoi pornește engine-ul. Dacă " +
                  "verificările nu trec, engine-ul rămâne oprit și primești un mesaj pe Telegram.")) && act.mutate({ id: r.id, on: !r.enabled })}
                className="px-2 py-0.5 rounded border border-surface-border text-slate-300 hover:text-white disabled:opacity-40">
                {r.enabled ? "Dezactivează" : "Activează"}</button>
            </>
          )}
        </div>
      ))}
      <p className="text-[10px] text-slate-600">
        Pornirea nu are loc doar pentru că a trecut o întârziere: engine-ul pornește numai după ce dependențele sunt verificate
        (internet, MT5 conectat la broker + cont, Ollama pentru AI, configurație validă). Pozițiile și ordinele sunt re-citite
        din MT5; piețele pe Pauză rămân pe Pauză; Noisy nu pornește niciodată automat. „Aplicația” = API + monitorizare +
        watchdog-uri + rapoarte (fără ea nu există recuperare după restart). Jurnal: data/…/autostart.log.
      </p>
    </div>
  );
}

/** Dashboard: apare DOAR cand exista incidente active (altfel nu ocupa loc). Detalii in Settings → Sanatatea aplicatiei. */
export function HealthBanner() {
  const { data } = useHealth();
  const active = data?.incidents.active ?? [];
  if (!active.length) return null;
  const crit = active.some(i => i.severity === "critical");
  return (
    <div className={`flex items-start gap-3 rounded-xl px-4 py-2.5 border ${crit ? "bg-loss/10 border-loss/40" : "bg-warn/10 border-warn/40"}`}>
      <Activity size={16} className={crit ? "text-loss mt-0.5" : "text-warn mt-0.5"} />
      <div className="text-xs space-y-0.5">
        {active.map(i => (
          <div key={i.key} className={i.severity === "critical" ? "text-loss" : "text-warn"}>
            <b>{i.title}</b> <span className="opacity-70">· din {fmt(i.first_seen_iso)}{i.notified ? "" : " · în confirmare"}</span>
          </div>
        ))}
        <div className="text-slate-500">Detalii și istoric: Settings → Sănătatea aplicației. Pozițiile rămân protejate de SL / TP la broker.</div>
      </div>
    </div>
  );
}
