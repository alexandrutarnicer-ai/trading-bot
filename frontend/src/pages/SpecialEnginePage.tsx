import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Play, Sparkles, Square } from "lucide-react";
import { apiFetch } from "../api/client";

/** Special Engine — mod PER PIATA (Live / Shadow / Pauza, implicit Shadow). Hook-urile / tipurile stau aici
 *  (engine izolat, doar pe alex-live). Ordinele reale: special_engine/executor.py (magic 660001).
 *  A = portofoliu intraday ADAPTIV (selectie trimestriala walk-forward, doar din trecut) in zilele NR4
 *  B = „Beat the Market” (noise area, Zarattini et al. 2024) pe USTEC, fara selectie */

interface Score { trades: number; wins: number; losses: number; total_R: number; expectancy_R: number | null;
  win_rate: number | null; max_dd_R: number; pnl_money_est: number | null }
interface Comp { comp: string; strategy: "A" | "B"; symbol?: string; kind?: string; variant?: string | null; window?: string;
  window_ro?: string; phase: string; reason?: string; nr?: boolean | null; side?: number; entry?: number; sl?: number;
  open_R?: number; trades_today?: number; R_today?: number; or_hi?: number; or_lo?: number;
  mode?: MarketMode; execution?: { active: boolean; reason: string }; exec_error?: string;
  real_positions?: { ticket: number; side: string; volume: number; price: number; sl: number; profit?: number | null }[] }
type MarketMode = "live" | "shadow" | "pause";
interface CapitalInfo { account_equity: number | null; engine_capital: number; risk_per_trade: number; open_risk: number;
  open_risk_limit: number; available_risk: number; margin_used: number | null; positions: number; orders: number;
  max_positions: number }
interface SpecialCfg { risk_pct: number; notify_trades: boolean; notify_telegram: boolean; max_open_risk_pct: number;
  max_positions: number; max_margin_pct: number; noise_stop_mult: number;
  capital: { capital_sync_mt5: boolean; capital_usd: number | null; fraction: number } }
interface SelRow { comp: string; n: number; mean_R: number; t: number; selected: boolean }
interface Selection { quarter?: string | null; computed_at?: string; components?: string[]; table?: SelRow[];
  params?: Record<string, number>; error?: string }
interface Ref { label: string; trades_per_month: number; expectancy_R: number; test_R: number; max_dd_R: number;
  pct_months_pos: number; month_pct_at_05: number; dd_pct_at_05: number; verdict: string; period: string; note?: string }
interface Status { running: boolean; pid: number | null; updated?: string; components?: Comp[]; errors?: string[];
  selection?: Selection; selection_note?: string; scorecard?: { total: Score; A: Score; B: Score; by_component: Record<string, Score> };
  research: Record<"A" | "B" | "AB", Ref>; config?: SpecialCfg; markets?: Record<string, MarketMode>; capital?: CapitalInfo }
interface Trade { day: string; strategy: string; comp: string; symbol: string; d: number; entry: number; exit: number; R: number;
  why: string; entry_t: string; exit_t: string; pnl_money_est?: number;
  // doar afisare (annotate_trade): momentele in fusul aplicatiei + ora bursei, observat live / reconstituit
  entry_app?: string; exit_app?: string; entry_exch?: string; exit_exch?: string; exch_label?: string; app_label?: string;
  live?: boolean | null; live_note?: string; recorded_app?: string }

/** Momentul in fusul aplicatiei; ziua apare doar daca difera de ziua bursei (ex. JP225 / Sydney). */
const tm = (app: string | undefined, raw: string, day: string, label?: string) =>
  app ? `${app.slice(0, 10) !== day ? app.slice(5, 10) + " " : ""}${app.slice(11, 16)} ${label ?? ""}`.trim() : raw.slice(11, 16);

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
  paused: { label: "Pe pauză", cls: "bg-amber-500/15 text-amber-300" },
  error: { label: "Eroare", cls: "bg-loss/15 text-loss" },
};
const MODE_UI: Record<MarketMode, { label: string; on: string }> = {
  live: { label: "LIVE", on: "bg-loss/25 text-loss" },
  shadow: { label: "SHADOW", on: "bg-violet-500/25 text-violet-200" },
  pause: { label: "PAUZĂ", on: "bg-amber-500/25 text-amber-200" },
};

function ModeSelector({ symbol, mode }: { symbol: string; mode: MarketMode }) {
  const qc = useQueryClient();
  const set = useMutation({
    mutationFn: (m: MarketMode) => apiFetch(`/special/markets/${symbol}/mode`, { method: "POST", body: { mode: m } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["special-status"] }),
  });
  function choose(m: MarketMode) {
    if (m === mode || set.isPending) return;
    if (m === "live") {
      if (!window.confirm(`Treci ${symbol} pe LIVE în Special Engine?\n\nLa următorul semnal plasează ORDINE REALE pe ${symbol} ` +
        "(SL atașat, închidere la finalul sesiunii). Celelalte piețe NU sunt afectate.\n\nPe un cont REAL trebuie în plus deblocat " +
        "„Special Engine” în Settings → Trading LIVE.")) return;
      if (!window.confirm(`Confirmare finală: ${symbol} va tranzacționa cu ordine reale. Continui?`)) return;
    } else if (m === "pause" && !window.confirm(`Pui ${symbol} pe PAUZĂ? Fără intrări noi; o poziție deschisă rămâne gestionată.`)) {
      return;
    }
    set.mutate(m);
  }
  return (
    <div className="flex rounded-lg border border-surface-border overflow-hidden text-[11px] font-semibold">
      {(["live", "shadow", "pause"] as MarketMode[]).map(k => (
        <button key={k} onClick={() => choose(k)} disabled={set.isPending}
          className={`px-2 py-0.5 border-l first:border-l-0 border-surface-border ${mode === k ? MODE_UI[k].on : "text-slate-500 hover:text-slate-300"}`}>
          {mode === k ? "● " : ""}{MODE_UI[k].label}
        </button>
      ))}
      {set.isError && <span className="px-2 text-loss">{(set.error as Error).message}</span>}
    </div>
  );
}

function CapitalCard({ cap, cfg }: { cap?: CapitalInfo; cfg?: SpecialCfg }) {
  const qc = useQueryClient();
  const save = useMutation({
    mutationFn: (b: Record<string, unknown>) => apiFetch("/special/config", { method: "PUT", body: b }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["special-status"] }),
  });
  const [f, setF] = useState<Record<string, number | boolean | null> | null>(null);
  if (!cfg) return null;
  const v = f ?? { risk: cfg.risk_pct * 100, open: cfg.max_open_risk_pct * 100, pos: cfg.max_positions,
    margin: cfg.max_margin_pct, frac: cfg.capital.fraction * 100, sync: cfg.capital.capital_sync_mt5,
    usd: cfg.capital.capital_usd, nmult: cfg.noise_stop_mult };
  const num = (k: string) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...v, [k]: e.target.value === "" ? null : Number(e.target.value) });
  const inp = "w-16 bg-surface-card border border-surface-border rounded px-1 text-white";
  const money = (x?: number | null) => (x == null ? "—" : `${x.toFixed(2)} $`);
  function doSave() {
    save.mutate({ risk_pct: Number(v.risk) / 100, max_open_risk_pct: Number(v.open) / 100, max_positions: v.pos,
      max_margin_pct: v.margin, noise_stop_mult: v.nmult,
      capital: { capital_sync_mt5: v.sync, capital_usd: v.sync ? null : v.usd, fraction: Number(v.frac) / 100 } },
      { onSuccess: () => setF(null) });
  }
  return (
    <div className="bg-surface rounded-xl border border-surface-border p-4 space-y-2 text-[11px]">
      <div className="text-sm font-semibold text-white">Capital și risc — setările proprii ale Special Engine</div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        {[["Cont MT5 (equity)", money(cap?.account_equity)], ["Capitalul engine-ului", money(cap?.engine_capital)],
          ["Risc / trade (țintă)", money(cap?.risk_per_trade)],
          ["Risc deschis acum", `${money(cap?.open_risk)} din ${money(cap?.open_risk_limit)}`],
          ["Disponibil pt trade-uri noi", money(cap?.available_risk)], ["Marjă folosită (tot contul)", money(cap?.margin_used)],
          ["Poziții + ordine Special", `${(cap?.positions ?? 0) + (cap?.orders ?? 0)} / ${cap?.max_positions ?? cfg.max_positions}`]]
          .map(([k, val]) => (
            <div key={k} className="bg-surface-card rounded-lg px-2 py-1"><div className="text-slate-500">{k}</div><div className="text-white font-semibold">{val}</div></div>
          ))}
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-slate-300">
        <label className="flex items-center gap-1"><input type="checkbox" checked={!!v.sync} onChange={e => setF({ ...v, sync: e.target.checked })} />
          capital = equity MT5</label>
        {!v.sync && <label className="flex items-center gap-1">sumă fixă <input type="number" min={10} value={v.usd == null ? "" : Number(v.usd)} onChange={num("usd")} className={inp} /> $</label>}
        <label className="flex items-center gap-1">× <input type="number" min={5} max={100} value={Number(v.frac)} onChange={num("frac")} className={inp} /> %</label>
        <label className="flex items-center gap-1">risc / trade <input type="number" min={0.1} max={2} step={0.1} value={Number(v.risk)} onChange={num("risk")} className={inp} /> %</label>
        <label className="flex items-center gap-1">risc total deschis ≤ <input type="number" min={0.25} max={10} step={0.25} value={Number(v.open)} onChange={num("open")} className={inp} /> %</label>
        <label className="flex items-center gap-1">poziții ≤ <input type="number" min={1} max={10} value={Number(v.pos)} onChange={num("pos")} className={inp} /></label>
        <label className="flex items-center gap-1">marjă cont ≤ <input type="number" min={10} max={95} step={5} value={Number(v.margin)} onChange={num("margin")} className={inp} /> % equity</label>
        <label className="flex items-center gap-1">SL protecție B <input type="number" min={1} max={5} step={0.5} value={Number(v.nmult)} onChange={num("nmult")} className={inp} /> × R</label>
        {f && <button onClick={doSave} disabled={save.isPending} className="px-2 py-0.5 rounded bg-cyan-500/20 text-cyan-200 border border-cyan-500/40">Salvează</button>}
        {f && <button onClick={() => setF(null)} className="px-2 py-0.5 rounded border border-surface-border text-slate-400">Renunță</button>}
        {save.isError && <span className="text-loss">{(save.error as Error).message}</span>}
      </div>
      <div className="text-[10px] text-slate-500">
        Lotul fiecărui trade = risc% × capitalul engine-ului ÷ distanța până la SL (aceeași dimensionare ca la celelalte engine-uri).
        Înainte de orice ordin se verifică, în ordine: limita globală de risc / trade și Capital Protection (Setări Globale), riscul TOTAL
        deschis al Special Engine (toate piețele împreună — nicio piață nu folosește singură tot capitalul), numărul de poziții și marja
        totală a contului (cu pozițiile tuturor engine-urilor). Dacă lotul minim al brokerului depășește oricare limită → ordinul NU se
        plasează (motivul apare în Notificări + Audit). Setările Globale nu se schimbă de aici.
      </div>
    </div>
  );
}
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
        {Object.values(st?.markets ?? {}).some(m => m === "live")
          ? <span className="text-[11px] px-2 py-0.5 rounded-full bg-loss/20 text-loss font-semibold">
              LIVE pe: {Object.entries(st?.markets ?? {}).filter(([, m]) => m === "live").map(([k]) => k).join(", ")}</span>
          : <span className="text-[11px] px-2 py-0.5 rounded-full bg-fuchsia-500/15 text-fuchsia-300 font-semibold">SHADOW — zero ordine</span>}
        <span className={`text-[11px] px-2 py-0.5 rounded-full font-semibold ${st?.running ? "bg-profit/15 text-profit" : "bg-slate-700/40 text-slate-400"}`}>
          {st?.running ? `RUNNING (PID ${st.pid})` : "STOPPED"}</span>
        <div className="ml-auto">
          {st?.running
            ? <button onClick={() => act.mutate("stop")} disabled={act.isPending} className="flex items-center gap-2 px-4 py-2 rounded-lg bg-loss/20 text-loss hover:bg-loss/30 text-sm font-semibold disabled:opacity-50"><Square size={14} /> Oprește</button>
            : <button onClick={() => act.mutate("start")} disabled={act.isPending} className="flex items-center gap-2 px-4 py-2 rounded-lg bg-profit/20 text-profit hover:bg-profit/30 text-sm font-semibold disabled:opacity-50">{act.isPending ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />} Pornește</button>}
        </div>
        {act.isError && <div className="w-full text-[11px] text-loss">{(act.error as Error).message}</div>}
      </div>

      <div className="text-[11px] text-slate-500 bg-surface rounded-xl border border-surface-border px-4 py-2 space-y-1">
        <div><b className="text-slate-300">A — portofoliu adaptiv:</b> la începutul fiecărui trimestru alege, doar din trecut (ultimele {sel?.params?.lookback_months ?? 36} luni), combinațiile piață × strategie (ORB la deschiderea bursei / noise area) cu edge statistic (t ≥ {sel?.params?.t_min ?? 1.5}); le tranzacționează doar în zilele NR4 (range-ul de ieri = cel mai mic din ultimele 4 zile, Crabel). Fără edge → nu tranzacționează.</div>
        <div><b className="text-slate-300">B — Beat the Market (Zarattini, Aziz, Barbon 2024)</b> pe USTEC: intrare când prețul iese din „zona de zgomot” a ultimelor 14 zile, ieșire la revenirea sub max(bandă, VWAP), totul închis la finalul sesiunii NY. Parametrii din lucrare, fără optimizare.</div>
        <div>Intraday: nicio poziție peste noapte (fără swap). Fiecare piață are modul ei (Live / Shadow / Pauză, pe cardul pieței; o
          piață nouă din selecția trimestrială intră în SHADOW). Estimarea în bani = R × {((st?.config?.risk_pct ?? 0.01) * 100).toFixed(1)}%
          din capitalul engine-ului. B are în Live un SL de protecție la {st?.config?.noise_stop_mult ?? 2} × unitatea R (strategia iese la
          banda / VWAP); dimensionarea se face pe distanța până la acest SL.</div>
      </div>

      <CapitalCard cap={st?.capital} cfg={st?.config} />

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
                {c.symbol && <ModeSelector symbol={c.symbol} mode={(c.mode ?? st?.markets?.[c.symbol] ?? "shadow") as MarketMode} />}
              </div>
              {c.mode === "live" && (
                <div className={`rounded px-2 py-0.5 ${c.execution?.active ? "bg-loss/10 text-loss" : "bg-warn/10 text-warn"}`}>
                  {c.execution?.active ? `LIVE — ordine reale (${c.execution.reason})` : `LIVE cerut, dar BLOCAT: ${c.execution?.reason ?? "?"}`}
                </div>
              )}
              {!!c.real_positions?.length && c.real_positions.map(p => (
                <div key={p.ticket} className="text-white">Poziție REALĂ #{p.ticket}: {p.side} {p.volume} @ {p.price} · SL {p.sl}
                  {p.profit != null && <span className={rc(p.profit)}> · {p.profit.toFixed(2)} $</span>}</div>
              ))}
              {c.exec_error && <div className="text-loss">execuție: {c.exec_error}</div>}
              <div className="text-slate-400">Fereastra {c.window_ro} RO · {c.window}</div>
              {c.reason && <div className="text-slate-500">{c.reason}</div>}
              {c.side != null && <div className={c.side === 1 ? "text-profit" : "text-loss"}>{c.side === 1 ? "LONG" : "SHORT"} @ {c.entry}{c.sl != null ? ` · SL ${c.sl}` : ""} · deschis {fR(c.open_R)}</div>}
              {(c.trades_today ?? 0) > 0 && <div className="text-slate-300">Azi: {c.trades_today} trade-uri · <span className={rc(c.R_today)}>{fR(c.R_today)}</span></div>}
            </div>
          );
        })}
      </div>
      {!st?.components?.length && Object.keys(st?.markets ?? {}).length > 0 && (
        <div className="bg-surface rounded-xl border border-surface-border p-3 text-[11px] space-y-1">
          <div className="text-slate-400">Piețele engine-ului (modul se aplică după Start):</div>
          {Object.entries(st?.markets ?? {}).map(([sym, m]) => (
            <div key={sym} className="flex items-center gap-2"><span className="text-white font-semibold w-16">{sym}</span><ModeSelector symbol={sym} mode={m} /></div>
          ))}
        </div>
      )}
      {!!st?.errors?.length && <div className="text-[11px] text-loss">{st.errors.join(" · ")}</div>}

      <div className="bg-surface rounded-xl border border-surface-border p-4">
        <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Trade-uri (virtuale + cu ordin real)</h3>
        <div className="text-[10px] text-slate-500 mb-1">Orele sunt în ora {tr?.trades?.[0]?.app_label ?? "RO"} (în paranteză: ora bursei).
          „⟲ reconstituit” = engine-ul nu rula în timpul trade-ului; l-a recalculat la pornire din lumânările închise — nu e o observație live.</div>
        {!tr?.trades?.length ? <div className="text-[11px] text-slate-500">Încă niciun trade virtual închis.</div> : (
          <table className="w-full text-[11px]">
            <thead><tr className="text-slate-500 text-left"><th>Zi</th><th>Str.</th><th>Componentă</th><th>Dir</th><th>Intrare</th><th>Ieșire</th><th>Motiv</th><th>Observat</th><th className="text-right">Est. USD</th><th className="text-right">R</th></tr></thead>
            <tbody>{tr.trades.map((t, i) => (
              <tr key={i} className="border-t border-surface-border/30">
                <td className="py-0.5 text-slate-400">{t.day}</td><td className="text-slate-400">{t.strategy}</td><td className="text-slate-300">{t.comp}</td>
                <td className={t.d === 1 ? "text-profit" : "text-loss"}>{t.d === 1 ? "LONG" : "SHORT"}</td>
                <td className="text-slate-400">{tm(t.entry_app, t.entry_t, t.day, t.app_label)} @ {t.entry}
                  {t.entry_exch && <span className="text-slate-600"> ({t.entry_exch} {t.exch_label})</span>}</td>
                <td className="text-slate-400">{tm(t.exit_app, t.exit_t, t.day, t.app_label)} @ {t.exit}
                  {t.exit_exch && <span className="text-slate-600"> ({t.exit_exch} {t.exch_label})</span>}</td>
                <td className="text-slate-500">{t.why === "EOD" ? "final de sesiune" : t.why}
                  {(t as Trade & { mode?: string }).mode === "execute" && <span className="ml-1 text-loss font-semibold">REAL</span>}</td>
                <td title={t.live_note} className={t.live ? "text-profit" : t.live === false ? "text-amber-400" : "text-slate-500"}>
                  {t.live ? "✓ live" : t.live === false ? (t.live_note?.startsWith("parțial") ? "◐ parțial" : "⟲ reconstituit") : "—"}</td>
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
