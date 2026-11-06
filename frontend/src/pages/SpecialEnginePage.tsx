import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Play, Sparkles, Square } from "lucide-react";
import { apiFetch } from "../api/client";

/** Special Engine — DOAR SHADOW (zero ordine). Hook-urile / tipurile stau aici (engine izolat, in test pe alex-live).
 *  A = portofoliu intraday ADAPTIV (selectie trimestriala walk-forward, doar din trecut) in zilele NR4
 *  B = „Beat the Market” (noise area, Zarattini et al. 2024) pe USTEC, fara selectie */

interface Score { trades: number; wins: number; losses: number; total_R: number; expectancy_R: number | null;
  win_rate: number | null; max_dd_R: number; pnl_money_est: number | null }
interface Comp { comp: string; strategy: "A" | "B"; symbol?: string; kind?: string; variant?: string | null; window?: string;
  window_ro?: string; phase: string; reason?: string; nr?: boolean | null; side?: number; entry?: number; sl?: number;
  open_R?: number; trades_today?: number; R_today?: number; or_hi?: number; or_lo?: number }
interface SelRow { comp: string; n: number; mean_R: number; t: number; selected: boolean }
interface Selection { quarter?: string | null; computed_at?: string; components?: string[]; table?: SelRow[];
  params?: Record<string, number>; error?: string }
interface Ref { label: string; trades_per_month: number; expectancy_R: number; test_R: number; max_dd_R: number;
  pct_months_pos: number; month_pct_at_05: number; dd_pct_at_05: number; verdict: string; period: string; note?: string }
interface Status { running: boolean; pid: number | null; updated?: string; components?: Comp[]; errors?: string[];
  selection?: Selection; selection_note?: string; scorecard?: { total: Score; A: Score; B: Score; by_component: Record<string, Score> };
  research: Record<"A" | "B" | "AB", Ref>; config?: { risk_pct: number; notify_trades: boolean } }
interface Trade { day: string; strategy: string; comp: string; symbol: string; d: number; entry: number; exit: number; R: number;
  why: string; entry_t: string; exit_t: string; pnl_money_est?: number }

const useStatus = () => useQuery<Status>({ queryKey: ["special-status"], queryFn: () => apiFetch("/special/status"),
  refetchInterval: 10_000, refetchIntervalInBackground: false });
const useTrades = () => useQuery<{ trades: Trade[] }>({ queryKey: ["special-trades"], queryFn: () => apiFetch("/special/trades"),
  refetchInterval: 30_000, refetchIntervalInBackground: false });
const useLogs = (on: boolean) => useQuery<{ lines: string[] }>({ queryKey: ["special-logs"], queryFn: () => apiFetch("/special/logs"),
  enabled: on, refetchInterval: on ? 15_000 : false });

const PHASE: Record<string, { label: string; cls: string }> = {
  waiting_open: { label: "Așteaptă deschiderea", cls: "bg-slate-700/40 text-slate-400" },
  forming_or: { label: "Se formează intervalul", cls: "bg-blue-500/15 text-blue-300" },
  waiting_entry: { label: "Așteaptă intrarea", cls: "bg-amber-500/15 text-amber-300" },
  watching: { label: "Urmărește benzile", cls: "bg-blue-500/15 text-blue-300" },
  in_position: { label: "Poziție virtuală", cls: "bg-profit/15 text-profit" },
  closed: { label: "Încheiat azi", cls: "bg-slate-600/30 text-slate-300" },
  skipped: { label: "Zi sărită", cls: "bg-slate-700/40 text-slate-400" },
  no_nr: { label: "Nu e zi NR4", cls: "bg-slate-700/40 text-slate-500" },
  weekend: { label: "Weekend", cls: "bg-slate-700/40 text-slate-500" },
  error: { label: "Eroare", cls: "bg-loss/15 text-loss" },
};
const fR = (v?: number | null, d = 2) => (v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(d)}R`);
const rc = (v?: number | null) => (v == null ? "text-slate-400" : v > 0 ? "text-profit" : v < 0 ? "text-loss" : "text-slate-300");

function ScoreBox({ title, s, r }: { title: string; s?: Score; r?: Ref }) {
  return (
    <div className="bg-surface rounded-xl border border-surface-border p-3 text-[11px] space-y-1">
      <div className="text-xs font-semibold text-white">{title}</div>
      <div className="text-slate-400">Shadow: <span className="text-white">{s?.trades ?? 0} trade-uri</span> · <span className={rc(s?.expectancy_R)}>{fR(s?.expectancy_R, 3)}</span>/trade · total <span className={rc(s?.total_R)}>{fR(s?.total_R)}</span></div>
      <div className="text-slate-500">{s?.wins ?? 0}W / {s?.losses ?? 0}L · DD {s?.max_dd_R ?? 0}R{s?.pnl_money_est != null ? ` · est. ${s.pnl_money_est > 0 ? "+" : ""}${s.pnl_money_est.toFixed(2)} USD` : ""}</div>
      {r && <div className="text-slate-500 border-t border-surface-border/40 pt-1">Backtest {r.period}: {r.trades_per_month}/lună · {fR(r.expectancy_R, 3)}/trade (test {fR(r.test_R, 3)}) · {r.pct_months_pos}% luni+ · la 0,5% risc ≈ {r.month_pct_at_05}%/lună, DD {r.dd_pct_at_05}% · {r.verdict}{r.note ? ` · ${r.note}` : ""}</div>}
    </div>
  );
}

export function SpecialEnginePage() {
  const qc = useQueryClient();
  const { data: st } = useStatus();
  const { data: tr } = useTrades();
  const [showLogs, setShowLogs] = useState(false);
  const { data: logs } = useLogs(showLogs);
  const act = useMutation({ mutationFn: (a: "start" | "stop") => apiFetch(`/special/${a}`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["special-status"] }) });
  const refresh = useMutation({ mutationFn: () => apiFetch("/special/selection/refresh", { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["special-status"] }) });
  const sel = st?.selection;
  const sc = st?.scorecard;
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 flex-wrap">
        <Sparkles size={18} className="text-fuchsia-400" />
        <h2 className="text-lg font-bold text-white">Special Engine</h2>
        <span className="text-[11px] px-2 py-0.5 rounded-full bg-fuchsia-500/15 text-fuchsia-300 font-semibold">SHADOW — zero ordine</span>
        <span className={`text-[11px] px-2 py-0.5 rounded-full font-semibold ${st?.running ? "bg-profit/15 text-profit" : "bg-slate-700/40 text-slate-400"}`}>
          {st?.running ? `RUNNING (PID ${st.pid})` : "STOPPED"}</span>
        <div className="ml-auto">
          {st?.running
            ? <button onClick={() => act.mutate("stop")} disabled={act.isPending} className="flex items-center gap-2 px-4 py-2 rounded-lg bg-loss/20 text-loss hover:bg-loss/30 text-sm font-semibold disabled:opacity-50"><Square size={14} /> Oprește</button>
            : <button onClick={() => act.mutate("start")} disabled={act.isPending} className="flex items-center gap-2 px-4 py-2 rounded-lg bg-profit/20 text-profit hover:bg-profit/30 text-sm font-semibold disabled:opacity-50">{act.isPending ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />} Pornește (shadow)</button>}
        </div>
        {act.isError && <div className="w-full text-[11px] text-loss">{(act.error as Error).message}</div>}
      </div>

      <div className="text-[11px] text-slate-500 bg-surface rounded-xl border border-surface-border px-4 py-2 space-y-1">
        <div><b className="text-slate-300">A — portofoliu adaptiv:</b> la începutul fiecărui trimestru alege, doar din trecut (ultimele {sel?.params?.lookback_months ?? 36} luni), combinațiile piață × strategie (ORB la deschiderea bursei / noise area) cu edge statistic (t ≥ {sel?.params?.t_min ?? 1.5}); le tranzacționează doar în zilele NR4 (range-ul de ieri = cel mai mic din ultimele 4 zile, Crabel). Fără edge → nu tranzacționează.</div>
        <div><b className="text-slate-300">B — Beat the Market (Zarattini, Aziz, Barbon 2024)</b> pe USTEC: intrare când prețul iese din „zona de zgomot” a ultimelor 14 zile, ieșire la revenirea sub max(bandă, VWAP), totul închis la finalul sesiunii NY. Parametrii din lucrare, fără optimizare.</div>
        <div>Intraday: nicio poziție peste noapte (fără swap). Trade-urile sunt virtuale; estimarea în bani = R × {((st?.config?.risk_pct ?? 0.005) * 100).toFixed(1)}% din equity.</div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <ScoreBox title="A — adaptiv NR4" s={sc?.A} r={st?.research?.A} />
        <ScoreBox title="B — noise area USTEC" s={sc?.B} r={st?.research?.B} />
        <ScoreBox title="Total (A + B)" s={sc?.total} r={st?.research?.AB} />
      </div>

      <div className="bg-surface rounded-xl border border-surface-border p-4 space-y-2">
        <div className="flex items-center gap-2 flex-wrap text-sm font-semibold text-white">
          Selecția trimestrului {sel?.quarter ?? "—"}
          <span className="text-[11px] font-normal text-slate-500">{sel?.computed_at ? `calculată ${sel.computed_at.replace("T", " ").slice(0, 16)} UTC` : ""}</span>
          {st?.selection_note && <span className="text-[11px] font-normal text-amber-300">{st.selection_note}</span>}
          <button onClick={() => refresh.mutate()} disabled={refresh.isPending || !st?.running} className="ml-auto text-[11px] font-normal text-slate-400 hover:text-white disabled:opacity-40">↻ recalculează</button>
        </div>
        <div className="text-[11px] text-slate-400">Componente active (A): {(sel?.components ?? []).length ? sel!.components!.join(" · ") : "niciuna — nicio combinație cu edge pe ultimele luni"}</div>
        {!!sel?.table?.length && (
          <table className="w-full text-[11px]">
            <thead><tr className="text-slate-500 text-left"><th>Componentă</th><th>Trade-uri (NR4, fereastra)</th><th>R mediu</th><th>t-stat</th><th>Aleasă</th></tr></thead>
            <tbody>{sel.table.slice(0, 12).map(r => (
              <tr key={r.comp} className="border-t border-surface-border/30">
                <td className="py-0.5 text-slate-300">{r.comp}</td><td className="text-slate-400">{r.n}</td>
                <td className={rc(r.mean_R)}>{fR(r.mean_R, 3)}</td><td className="text-slate-400">{r.t}</td>
                <td>{r.selected ? <span className="text-profit">✓</span> : <span className="text-slate-600">—</span>}</td>
              </tr>))}</tbody>
          </table>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {(st?.components ?? []).map(c => {
          const ph = PHASE[c.phase] ?? { label: c.phase, cls: "bg-slate-700/40 text-slate-400" };
          return (
            <div key={c.comp + c.strategy} className="bg-surface rounded-xl border border-surface-border p-3 text-[11px] space-y-1">
              <div className="flex items-center gap-2">
                <span className="text-sm font-bold text-white">{c.symbol}</span>
                <span className="text-slate-500">{c.strategy} · {c.kind === "ORB" ? `ORB ${c.variant}` : "noise area"}</span>
                <span className={`ml-auto px-2 py-0.5 rounded-full font-semibold ${ph.cls}`}>{ph.label}</span>
              </div>
              <div className="text-slate-400">Fereastra {c.window_ro} RO · {c.window}</div>
              {c.reason && <div className="text-slate-500">{c.reason}</div>}
              {c.side != null && <div className={c.side === 1 ? "text-profit" : "text-loss"}>{c.side === 1 ? "LONG" : "SHORT"} @ {c.entry}{c.sl != null ? ` · SL ${c.sl}` : ""} · deschis {fR(c.open_R)}</div>}
              {(c.trades_today ?? 0) > 0 && <div className="text-slate-300">Azi: {c.trades_today} trade-uri · <span className={rc(c.R_today)}>{fR(c.R_today)}</span></div>}
            </div>
          );
        })}
      </div>
      {!!st?.errors?.length && <div className="text-[11px] text-loss">{st.errors.join(" · ")}</div>}

      <div className="bg-surface rounded-xl border border-surface-border p-4">
        <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Trade-uri virtuale</h3>
        {!tr?.trades?.length ? <div className="text-[11px] text-slate-500">Încă niciun trade virtual închis.</div> : (
          <table className="w-full text-[11px]">
            <thead><tr className="text-slate-500 text-left"><th>Zi</th><th>Str.</th><th>Componentă</th><th>Dir</th><th>Intrare</th><th>Ieșire</th><th>Motiv</th><th className="text-right">Est. USD</th><th className="text-right">R</th></tr></thead>
            <tbody>{tr.trades.map((t, i) => (
              <tr key={i} className="border-t border-surface-border/30">
                <td className="py-0.5 text-slate-400">{t.day}</td><td className="text-slate-400">{t.strategy}</td><td className="text-slate-300">{t.comp}</td>
                <td className={t.d === 1 ? "text-profit" : "text-loss"}>{t.d === 1 ? "LONG" : "SHORT"}</td>
                <td className="text-slate-400">{t.entry_t.slice(11, 16)} @ {t.entry}</td><td className="text-slate-400">{t.exit_t.slice(11, 16)} @ {t.exit}</td>
                <td className="text-slate-500">{t.why}</td>
                <td className={`text-right ${rc(t.pnl_money_est)}`}>{t.pnl_money_est != null ? t.pnl_money_est.toFixed(2) : "—"}</td>
                <td className={`text-right font-semibold ${rc(t.R)}`}>{fR(t.R)}</td>
              </tr>))}</tbody>
          </table>
        )}
      </div>

      <div className="bg-surface rounded-xl border border-surface-border p-4">
        <button onClick={() => setShowLogs(!showLogs)} className="text-xs text-slate-400 hover:text-white">{showLogs ? "▾" : "▸"} Jurnal</button>
        {showLogs && <pre className="mt-2 text-[10px] text-slate-400 max-h-72 overflow-auto whitespace-pre-wrap">{(logs?.lines ?? []).join("")}</pre>}
      </div>
    </div>
  );
}
