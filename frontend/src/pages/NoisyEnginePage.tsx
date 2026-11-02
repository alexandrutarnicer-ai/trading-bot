import { useEffect, useState } from "react";
import { AlertTriangle, Loader2, OctagonX, Pause, Play, RotateCcw, Square, Zap } from "lucide-react";
import { useNoisyAction, useNoisyLogs, useNoisySaveConfig, useNoisyStatus, useNoisyTrades, useTimezone } from "../api/hooks";
import type { NoisyConfig, NoisySpreadInfo, NoisyStatus } from "../api/types";

// Ora RO (fereastra Noisy e definita si testata in ora RO) → ora din alt fus, pentru afisare.
function roToZone(hm: string, zone: string): string {
  const [h, m] = hm.split(":").map(Number);
  const now = new Date();
  const off = (tz: string) => {
    const p = new Intl.DateTimeFormat("en-GB", { timeZone: tz, hour: "2-digit", minute: "2-digit", hourCycle: "h23" })
      .formatToParts(now);
    const g = (k: string) => Number(p.find(x => x.type === k)?.value ?? 0);
    return g("hour") * 60 + g("minute");
  };
  let diff = off(zone) - off("Europe/Bucharest");
  if (diff > 720) diff -= 1440;
  if (diff < -720) diff += 1440;
  const tot = (((h * 60 + m + diff) % 1440) + 1440) % 1440;
  return `${String(Math.floor(tot / 60)).padStart(2, "0")}:${String(tot % 60).padStart(2, "0")}`;
}

/**
 * Noisy Engine — mean reversion pe M5, o singura piata (USDJPY), mod SHADOW.
 * Fara autostart: pornire DOAR manuala, cu confirmare (risc HIGH). Emergency Stop oprește imediat.
 * Toate limitele sunt optionale; bugetul e izolat de celelalte engine-uri.
 */

const STATE_CLS: Record<string, string> = {
  running: "bg-amber-500/15 text-amber-300 border-amber-500/40",
  in_position: "bg-amber-500/25 text-amber-200 border-amber-400/60",
  outside_window: "bg-slate-700/40 text-slate-300 border-surface-border",
  paused: "bg-slate-700/40 text-slate-300 border-surface-border",
  starting: "bg-slate-700/40 text-slate-300 border-surface-border",
  stopped: "bg-slate-800 text-slate-400 border-surface-border",
  budget_locked: "bg-loss/15 text-loss border-loss/40",
  loss_limit: "bg-loss/15 text-loss border-loss/40",
  loss_streak: "bg-loss/15 text-loss border-loss/40",
  trade_limit: "bg-yellow-500/15 text-yellow-300 border-yellow-500/40",
  risk_locked: "bg-loss/15 text-loss border-loss/40",
  error: "bg-loss/15 text-loss border-loss/40",
};
const DAYS = ["L", "Ma", "Mi", "J", "V", "S", "D"];
const REJECT_LABEL: Record<string, string> = {
  cost_atr: "cost/ATR", spread: "spread", stiri: "știri", trend: "trend", flip_flop: "flip-flop",
  veto: "protecții globale / spread live", cooldown: "pauză după ieșire", blocat: "pauză / buget",
  limita_trade: "limita trade-uri", limita_pierderi: "limita pierderi", serie_pierderi: "serie pierderi",
  interval: "interval minim", suprapuse: "max trade-uri simultane", directie: "direcție nepermisă",
};

/** Spread: aceeasi valoare in points (unitatea MT5 din Market Watch), pips si pret. */
function fmtSpread(points: number | null | undefined, sp?: NoisySpreadInfo) {
  if (points == null) return "—";
  const pt = sp?.point, pp = sp?.pip_points ?? 1, dg = sp?.digits ?? 5;
  const price = pt ? (points * pt).toFixed(Math.max(dg, 1)) : "?";
  return `${+points.toFixed(2)} points` + (pp > 1 ? ` = ${+(points / pp).toFixed(2)} pips` : "") + ` = ${price}`;
}

function SpreadConfig({ d, set, sp, atr }: { d: NoisyConfig; set: (fn: (x: NoisyConfig) => void) => void; sp?: NoisySpreadInfo;
                         atr?: number | null }) {
  const x = d.spread;
  const num = (v: string) => (v === "" ? 0 : Number(v));
  const live = sp?.live_points;
  const typical = x.mode === "manual" ? (x.manual_points ?? sp?.typical_points ?? 0) : (sp?.typical_points ?? live ?? null);
  const max = x.max_mode === "manual" ? x.max_points : typical == null ? null : x.max_mult * typical;
  const prof = d.tf_profiles[d.timeframe];
  const cost = typical == null ? null : typical * (1 + 2 * Number(d.strategy.slip_frac ?? 0.25));
  const btn = (on: boolean) => `px-2 py-0.5 rounded border ${on ? "border-amber-500/50 text-amber-200" : "border-surface-border text-slate-500"}`;
  return (
    <div className="space-y-1.5">
      <div className="text-slate-400 font-semibold">Spread {d.symbol}
        <span className="font-normal text-slate-500"> · unitatea = points MT5 (coloana „Spread” din Market Watch){sp?.pip_points && sp.pip_points > 1 ? ` · 1 pip = ${sp.pip_points} points` : ""}</span>
      </div>
      <div className="text-[11px] text-slate-400">Acum în MT5: <b className="text-white">{fmtSpread(live, sp)}</b></div>
      <div className="flex items-center gap-2 flex-wrap">
        <span className="w-28 text-slate-300" title="Costul presupus al unui trade; intră și în filtrul cost/ATR.">Spread tipic (cost)</span>
        <button className={btn(x.mode === "auto")} onClick={() => set(c => { c.spread.mode = "auto"; })}>Auto (MT5 live)</button>
        <button className={btn(x.mode === "manual")} onClick={() => set(c => {
          c.spread.mode = "manual"; c.spread.manual_points = c.spread.manual_points ?? (sp?.typical_points ?? live ?? 0); })}>Manual</button>
        {x.mode === "manual" && (
          <span className="flex items-center gap-1">
            <input type="number" min={0} step={0.5} value={x.manual_points ?? ""} onChange={e => set(c => { c.spread.manual_points = num(e.target.value); })}
              className="w-20 bg-surface border border-surface-border rounded px-2 py-0.5" /> points
          </span>
        )}
      </div>
      <div className="text-[10px] text-slate-500 pl-28">
        = {fmtSpread(typical, sp)} · {x.mode === "auto" ? (sp?.auto_note || "mediana spread-ului live, înghețată pe zi la deschiderea ferestrei") : "valoarea ta (override)"}
      </div>
      <div className="flex items-center gap-2 flex-wrap">
        <span className="w-28 text-slate-300" title="Spread-ul LIVE peste care semnalul e respins (verificat la fiecare semnal).">Spread maxim</span>
        <button className={btn(x.max_mode === "auto")} onClick={() => set(c => { c.spread.max_mode = "auto"; })}>Auto</button>
        <button className={btn(x.max_mode === "manual")} onClick={() => set(c => {
          c.spread.max_mode = "manual"; c.spread.max_points = c.spread.max_points || +(max ?? 0).toFixed(1); })}>Manual</button>
        {x.max_mode === "auto" ? (
          <span className="flex items-center gap-1">
            <input type="number" min={1} max={20} step={0.1} value={x.max_mult} onChange={e => set(c => { c.spread.max_mult = num(e.target.value); })}
              className="w-16 bg-surface border border-surface-border rounded px-2 py-0.5" /> × tipic
          </span>
        ) : (
          <span className="flex items-center gap-1">
            <input type="number" min={0} step={0.5} value={x.max_points} onChange={e => set(c => { c.spread.max_points = num(e.target.value); })}
              className="w-20 bg-surface border border-surface-border rounded px-2 py-0.5" /> points <span className="text-slate-500">(0 = fără limită)</span>
          </span>
        )}
      </div>
      <div className="text-[10px] text-slate-500 pl-28">= {max ? fmtSpread(max, sp) : "fără limită"}</div>
      {typical != null && max != null && max > 0 && typical > max && (
        <div className="text-[11px] text-loss">Spread-ul tipic e peste maxim → TOATE semnalele vor fi respinse.</div>
      )}
      {cost != null && sp?.point && (
        <div className="text-[10px] text-yellow-300/90 rounded border border-yellow-500/30 bg-yellow-500/5 px-2 py-1">
          Filtrul cost/ATR ({d.timeframe}): intră doar când ATR ≥ {prof.min_atr_over_cost} × cost ≈ {fmtSpread(prof.min_atr_over_cost * cost, sp)}.
          Un spread mai mare înseamnă mai puține (sau zero) trade-uri — e intenționat: sub acest prag costul mănâncă mișcarea.
          {atr && sp.point ? <> ATR-ul ultimei bare {d.timeframe}: {fmtSpread(atr / sp.point, sp)} → trade-uri doar cu un spread tipic sub
            ≈ {fmtSpread(atr / sp.point / (prof.min_atr_over_cost * (1 + 2 * Number(d.strategy.slip_frac ?? 0.25))), sp)}.</> : null}
        </div>
      )}
    </div>
  );
}

const fmtR = (v?: number | null, d = 2) => (v == null ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(d)}R`);
const fmt$ = (v?: number | null) => (v == null ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(2)} $`);

function StartModal({ onCancel, onYes }: { onCancel: () => void; onYes: () => void }) {
  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4">
      <div className="max-w-md w-full rounded-xl border border-loss/50 bg-surface-card p-5 space-y-3">
        <div className="flex items-center gap-2 text-white font-semibold">
          <Zap size={16} className="text-amber-300" /> Start Noisy Engine?
        </div>
        <p className="text-xs text-slate-300">Acest engine:</p>
        <ul className="text-xs text-slate-300 list-disc pl-5 space-y-1">
          <li>analizează piața foarte des (la fiecare minut);</li>
          <li>poate deschide mai multe trade-uri pe oră (~25 pe zi);</li>
          <li>suportă costuri relativ mai mari (spread, comision, slippage);</li>
          <li>e expus la volatilitate și poate produce pierderi mai rapid decât celelalte engine-uri.</li>
        </ul>
        <p className="text-xs text-slate-400">
          Mod curent: <b className="text-amber-300">SHADOW</b> = trade-uri virtuale, zero ordine; <b className="text-loss">EXECUȚIE</b> =
          ordine reale (DEMO, sau REAL deblocat în Trading LIVE). Are buget propriu și se oprește singur la pragul setat.
        </p>
        <div className="flex items-center gap-2 text-xs font-bold text-loss"><AlertTriangle size={14} /> Risk level: HIGH</div>
        <div className="flex justify-end gap-2 pt-1">
          <button onClick={onCancel} className="px-4 py-1.5 rounded-lg text-xs text-slate-300 border border-surface-border hover:text-white">Cancel</button>
          <button onClick={onYes} className="px-4 py-1.5 rounded-lg text-xs font-semibold bg-amber-500/20 text-amber-200 border border-amber-500/50 hover:bg-amber-500/30">
            Yes, Start Noisy Engine
          </button>
        </div>
      </div>
    </div>
  );
}

function Stat({ k, v, cls = "text-white", sub }: { k: string; v: string; cls?: string; sub?: string }) {
  return (
    <div className="rounded-lg bg-surface border border-surface-border px-3 py-2">
      <div className="text-[10px] uppercase tracking-wider text-slate-500">{k}</div>
      <div className={`text-sm font-semibold ${cls}`}>{v}</div>
      {sub && <div className="text-[10px] text-slate-500">{sub}</div>}
    </div>
  );
}

function Header({ st }: { st?: NoisyStatus }) {
  const act = useNoisyAction();
  const [ask, setAsk] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const run = (a: Parameters<typeof act.mutate>[0]) => {
    setErr(null);
    act.mutate(a, { onError: (x: Error) => setErr(x.message) });
  };
  const state = st?.state ?? "stopped";
  return (
    <div className="rounded-xl border border-surface-border bg-surface-card p-4 space-y-3">
      {ask && <StartModal onCancel={() => setAsk(false)} onYes={() => { setAsk(false); run("start"); }} />}
      <div className="flex items-center gap-3 flex-wrap">
        <Zap size={18} className="text-amber-300" />
        <div>
          <div className="text-white font-semibold">Noisy Engine <span className="text-slate-500 font-normal text-xs">· {st?.symbol ?? "USDJPY"} {st?.config?.timeframe ?? st?.timeframe ?? "M1"} · mean reversion · {(st?.config?.mode ?? st?.mode) === "execute" ? "EXECUȚIE" : "SHADOW"}</span></div>
          <div className="text-[11px] text-slate-500">Pornire doar manuală (fără autostart, fără repornire automată).</div>
        </div>
        <span className={`ml-auto text-[11px] font-semibold px-2.5 py-1 rounded-lg border ${STATE_CLS[state] ?? STATE_CLS.stopped}`}>
          {st?.state_label ?? "Stopped"}
        </span>
      </div>
      {st?.reason && <div className="text-[11px] text-slate-400">{st.reason}</div>}
      <div className="flex items-center gap-2 flex-wrap">
        {!st?.running ? (
          <button onClick={() => setAsk(true)} disabled={act.isPending}
            className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-semibold bg-amber-500/15 text-amber-300 border border-amber-500/40 hover:bg-amber-500/25 disabled:opacity-50">
            {act.isPending ? <Loader2 size={12} className="animate-spin" /> : <Play size={12} />} Start
          </button>
        ) : (
          <button onClick={() => window.confirm("Oprești Noisy Engine?") && run("stop")} disabled={act.isPending}
            className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-semibold bg-loss/15 text-loss hover:bg-loss/25 disabled:opacity-50">
            <Square size={12} /> Stop
          </button>
        )}
        {st?.paused ? (
          <button onClick={() => run("resume")} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs text-slate-200 border border-surface-border hover:text-white">
            <Play size={12} /> Resume
          </button>
        ) : (
          <button onClick={() => run("pause")} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs text-slate-300 border border-surface-border hover:text-white">
            <Pause size={12} /> Pauză (fără intrări noi)
          </button>
        )}
        {st?.budget_lock && (
          <button onClick={() => window.confirm("Resetezi bugetul Noisy? Pierderile de până acum nu se mai socotesc, blocarea dispare.") &&
                                window.confirm("Confirmare finală: reset buget?") && run("reset-budget")}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs text-yellow-300 border border-yellow-500/40">
            <RotateCcw size={12} /> Reset buget
          </button>
        )}
        <button onClick={() => window.confirm("EMERGENCY STOP: oprește Noisy imediat și blochează intrările până la Resume?") && run("emergency-stop")}
          className="ml-auto flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-bold bg-loss text-white hover:brightness-110">
          <OctagonX size={13} /> EMERGENCY STOP
        </button>
      </div>
      {err && <pre className="text-[11px] text-loss whitespace-pre-wrap">{err}</pre>}
    </div>
  );
}

function ModeSwitch({ st }: { st?: NoisyStatus }) {
  const save = useNoisySaveConfig();
  const exec = (st?.config?.mode ?? st?.mode) === "execute";
  const ex = st?.execution;
  function choose(target: "shadow" | "execute") {
    if ((target === "execute") === exec || save.isPending) return;
    if (target === "execute") {
      if (!window.confirm("Treci Noisy Engine pe EXECUȚIE?\n\nLa fiecare semnal plasează un ORDIN REAL la piață în contul MT5 " +
        "conectat (SL + țintă atașate, stop de timp, o poziție odată, buget propriu).\n\nPe un cont REAL trebuie în plus deblocat " +
        "„Noisy Engine” în Settings → Trading LIVE.")) return;
      if (!window.confirm("Confirmare finală: Noisy Engine va tranzacționa cu ordine reale. Continui?")) return;
    } else if (!window.confirm("Revii pe SHADOW? Nu se mai deschid ordine reale.")) return;
    save.mutate({ mode: target });
  }
  return (
    <div className={`rounded-xl border p-4 flex items-center gap-3 flex-wrap ${exec ? "bg-loss/5 border-loss/40" : "bg-surface-card border-surface-border"}`}>
      <div className="flex rounded-lg border border-surface-border overflow-hidden shrink-0 text-xs font-semibold">
        <button onClick={() => choose("shadow")} disabled={save.isPending}
          className={`px-3 py-1.5 ${!exec ? "bg-amber-500/20 text-amber-200" : "text-slate-500 hover:text-slate-300"}`}>{!exec ? "● " : ""}SHADOW</button>
        <button onClick={() => choose("execute")} disabled={save.isPending}
          className={`px-3 py-1.5 border-l border-surface-border ${exec ? "bg-loss/20 text-loss" : "text-slate-500 hover:text-slate-300"}`}>{exec ? "● " : ""}EXECUȚIE (LIVE)</button>
      </div>
      <div className="text-xs">
        <div className="font-semibold text-white">Mod activ: {exec ? "EXECUȚIE (ordine reale)" : "SHADOW (virtual)"}
          {st && !st.running && <span className="ml-2 text-amber-400 font-normal">— engine-ul e OPRIT: modul se aplică după Start</span>}
        </div>
        <div className="text-[11px] text-slate-500">
          {exec ? (ex?.active ? `Activ — ${ex.reason}. ` : `Blocat — ${ex?.reason ?? "pornește engine-ul ca să verifice contul"}. `)
                : "Trade-uri virtuale pe prețuri reale, zero ordine. "}
          Magic 990001 — apare ca „Noisy” în Tranzacții. Pe cont REAL: Settings → Trading LIVE → Noisy Engine.
        </div>
      </div>
      {save.isError && <span className="text-[11px] text-loss">{(save.error as Error).message}</span>}
    </div>
  );
}

function Today({ st }: { st?: NoisyStatus }) {
  const lim = st?.config?.limits;
  const c = st?.counters;
  const l = (x?: { enabled: boolean; value: number }) => (x?.enabled ? `/${x.value}` : " (fără limită)");
  const b = st?.budget;
  const pct = b ? Math.max(0, Math.min(100, ((b.remaining - b.min_remaining) / Math.max(0.01, b.capital - b.min_remaining)) * 100)) : 0;
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
      <Stat k={`Trade-uri azi · ${st?.config?.timeframe ?? "M1"}`} v={`${c?.trades ?? 0}${l(lim?.max_trades_day)}`} sub={`R azi ${fmtR(st?.today?.R)} · ${fmt$(st?.today?.pnl_money)}`} />
      <Stat k={`Pierderi azi · ${st?.config?.timeframe ?? "M1"}`} v={`${c?.losses ?? 0}${l(lim?.max_losses_day)}`} sub={`la rând ${c?.consec_losses ?? 0}${l(lim?.max_consec_losses)}`}
            cls={(c?.losses ?? 0) > 0 ? "text-loss" : "text-white"} />
      <div className="rounded-lg bg-surface border border-surface-border px-3 py-2 col-span-2">
        <div className="text-[10px] uppercase tracking-wider text-slate-500">Buget izolat Noisy</div>
        <div className={`text-sm font-semibold ${b?.locked ? "text-loss" : "text-white"}`}>
          {b ? `${b.remaining.toFixed(2)} $ rămași din ${b.capital.toFixed(0)} $` : "—"}
          {b?.locked ? " · BLOCAT" : ""}
        </div>
        <div className="h-1.5 rounded bg-surface-border mt-1 overflow-hidden"><div className={`h-full ${b?.locked ? "bg-loss" : "bg-amber-400"}`} style={{ width: `${pct}%` }} /></div>
        <div className="text-[10px] text-slate-500 mt-0.5">
          realizat {fmt$(b?.realized)} · flotant {fmt$(b?.floating)} · stop la {b?.min_remaining.toFixed(2) ?? "—"} $ (P&L Noisy, nu equity-ul contului)
        </div>
      </div>
    </div>
  );
}

function Market({ st }: { st?: NoisyStatus }) {
  const o = st?.open, p = st?.pending, last = st?.last;
  return (
    <div className="rounded-xl border border-surface-border bg-surface-card p-4 space-y-2 text-xs">
      <div className="text-[11px] uppercase tracking-wider text-slate-500">Piață și poziție (virtual)</div>
      {o ? (
        <div className="text-white">
          <b className={o.dir === "LONG" ? "text-profit" : "text-loss"}>{o.dir}</b> @ {o.entry.toFixed(3)} · SL {o.sl.toFixed(3)} · țintă {o.tp.toFixed(3)} ·{" "}
          <span className={o.float_R >= 0 ? "text-profit" : "text-loss"}>{fmtR(o.float_R)}</span> · {o.bars_held * (st?.tf_min ?? 1)} min
        </div>
      ) : p ? (
        <div className="text-amber-300">Semnal {p.dir} la {p.signal_t.slice(11, 16)} — intrare la deschiderea barei următoare</div>
      ) : (
        <div className="text-slate-400">Fără poziție. Intrare când prețul se depărtează la peste {String(st?.config?.strategy?.dev_atr ?? 2)}×ATR de EMA20.</div>
      )}
      {last && (
        <div className="text-[11px] text-slate-500">
          Ultima bară {last.t.slice(11, 16)} · preț {last.close.toFixed(3)} · EMA20 {last.ema.toFixed(3)} · ATR {last.atr?.toFixed(3) ?? "—"} ·{" "}
          deviație <b className="text-slate-300">{last.dev_atr == null ? "—" : `${last.dev_atr >= 0 ? "+" : ""}${last.dev_atr.toFixed(2)}×ATR`}</b>
          {last.er != null && <> · efficiency ratio {last.er.toFixed(2)}</>}
        </div>
      )}
      {!!st?.real_positions?.length && (
        <div className="text-[11px] text-loss">
          Poziții REALE Noisy: {st.real_positions.map(p => `#${p.ticket} ${p.type} ${p.volume} @ ${p.price.toFixed(3)} (${p.profit >= 0 ? "+" : ""}${p.profit.toFixed(2)} $)`).join(" · ")}
        </div>
      )}
      {!!st?.rejected_recent?.length && (
        <div className="text-[11px] border-t border-surface-border pt-2 space-y-0.5">
          <div className="text-slate-500">Semnale respinse azi
            {st.rejects_today && <> ({Object.entries(st.rejects_today).map(([k, v]) => `${REJECT_LABEL[k] ?? k} ${v}`).join(" · ")})</>}:</div>
          {st.rejected_recent.slice(-5).reverse().map(r => (
            <div key={r.t + r.reason} className="text-slate-400">
              {r.t.slice(11, 16)} {r.dir} — <b className="text-yellow-300/90">{REJECT_LABEL[r.reason] ?? r.reason}</b>: {r.detail}
            </div>
          ))}
        </div>
      )}
      {!!st?.news_next?.length && (
        <div className="text-[11px] text-slate-500">Știri blocante: {st.news_next.map(([a, b]) => `${a.slice(5, 16).replace("T", " ")}–${b.slice(11, 16)}`).join(" · ")}</div>
      )}
    </div>
  );
}

function Score({ st }: { st?: NoisyStatus }) {
  const s = st?.scorecard, r = st?.backtest_ref ?? {};
  const rows: [string, string, string][] = [
    ["Trade-uri", String(s?.trades ?? 0), `${r.trades ?? "—"} (≈${r.per_day ?? "—"}/zi)`],
    ["Win rate", s?.win_rate == null ? "—" : `${(s.win_rate * 100).toFixed(1)}%`, r.win_rate == null ? "—" : `${(Number(r.win_rate) * 100).toFixed(1)}%`],
    ["Expectancy (după costuri)", fmtR(s?.expectancy_R, 3), fmtR(Number(r.expectancy_R), 3)],
    ["Brut / cost per trade", `${fmtR(s?.gross_R, 3)} / ${s?.cost_R == null ? "—" : s.cost_R.toFixed(3)}R`, `${fmtR(Number(r.gross_R), 3)} / ${r.cost_R ?? "—"}R`],
    ["Profit factor", s?.profit_factor == null ? "—" : String(s.profit_factor), String(r.profit_factor ?? "—")],
    ["Max drawdown", s ? `${s.max_dd_R.toFixed(1)}R` : "—", `${r.max_dd_R ?? "—"}R`],
    ["Serie max pierderi", String(s?.max_loss_streak ?? 0), String(r.max_loss_streak ?? "—")],
    ["Ținere medie", s?.avg_hold_min == null ? "—" : `${s.avg_hold_min} min`, `${r.avg_hold_min ?? "—"} min`],
    ["P&L virtual", fmt$(s?.pnl_money), "—"],
  ];
  return (
    <div className="rounded-xl border border-surface-border bg-surface-card p-4">
      <div className="text-[11px] uppercase tracking-wider text-slate-500 mb-2">Shadow vs backtest ({String(r.period ?? "")})</div>
      <table className="w-full text-xs">
        <thead><tr className="text-slate-500 text-left"><th className="py-1">Metrică</th><th>Shadow</th><th>Backtest</th></tr></thead>
        <tbody>{rows.map(([k, a, b]) => <tr key={k} className="border-t border-surface-border"><td className="py-1 text-slate-400">{k}</td><td className="text-white">{a}</td><td className="text-slate-400">{b}</td></tr>)}</tbody>
      </table>
      <div className="text-[10px] text-slate-500 mt-2">Criterii de trecere spre execuție: {String(r.pass_criteria ?? "")}</div>
    </div>
  );
}

const toMin = (hm: string) => { const [h, m] = hm.split(":").map(Number); return h * 60 + m; };

/** Validare identica cu backend-ul (config.validate_intervals): durata zero, suprapuneri (si peste miezul noptii). */
function windowErrors(iv: { start: string; end: string }[]): string[] {
  const errs: string[] = [];
  if (!iv.length) return ["cel puțin un interval orar este obligatoriu"];
  const segs: [number, number, number][] = [];
  iv.forEach((w, n) => {
    if (!/^\d{2}:\d{2}$/.test(w.start) || !/^\d{2}:\d{2}$/.test(w.end)) { errs.push(`intervalul ${n + 1}: oră invalidă`); return; }
    const a = toMin(w.start), b = toMin(w.end);
    if (a === b) { errs.push(`intervalul ${n + 1}: început = sfârșit (durată zero)`); return; }
    (a < b ? [[a, b]] : [[a, 1440], [0, b]]).forEach(([x, y]) => segs.push([x, y, n + 1]));
  });
  segs.forEach(([a1, b1, n1], i) => segs.slice(i + 1).forEach(([a2, b2, n2]) => {
    if (n1 !== n2 && a1 < b2 && a2 < b1) errs.push(`intervalele ${n1} și ${n2} se suprapun`);
  }));
  return [...new Set(errs)];
}

function WindowsEditor({ d, set, appTz }: { d: NoisyConfig; set: (fn: (x: NoisyConfig) => void) => void; appTz?: string }) {
  const iv = d.window.intervals ?? [{ start: d.window.start, end: d.window.end }];
  const errs = windowErrors(iv);
  const tfMin = d.timeframe === "M5" ? 5 : 1;
  return (
    <div className="space-y-1.5">
      <div className="text-slate-400 font-semibold">Ferestre de intrare (ora RO)</div>
      {iv.map((w, i) => (
        <div key={i} className="flex items-center gap-2">
          <span className="text-slate-500 w-4">{i + 1}.</span>
          <input type="time" value={w.start} onChange={e => set(c => { c.window.intervals[i].start = e.target.value; })}
            className="bg-surface border border-surface-border rounded px-2 py-0.5" />
          <span>–</span>
          <input type="time" value={w.end} onChange={e => set(c => { c.window.intervals[i].end = e.target.value; })}
            className="bg-surface border border-surface-border rounded px-2 py-0.5" />
          {toMin(w.end) < toMin(w.start) && <span className="text-[10px] text-slate-500">peste miezul nopții</span>}
          {appTz && appTz !== "Europe/Bucharest" && (
            <span className="text-[10px] text-slate-500">ora DE {roToZone(w.start, appTz)}–{roToZone(w.end, appTz)}</span>
          )}
          <button disabled={iv.length <= 1} title={iv.length <= 1 ? "Cel puțin un interval" : "Șterge intervalul"}
            onClick={() => set(c => { c.window.intervals.splice(i, 1); })}
            className="ml-auto px-2 rounded border border-surface-border text-slate-500 hover:text-loss disabled:opacity-30">✕</button>
        </div>
      ))}
      <button onClick={() => set(c => {
        const last = c.window.intervals[c.window.intervals.length - 1];
        const s0 = Math.min(1380, toMin(last?.end ?? "15:00") + 60);
        const f = (m: number) => `${String(Math.floor(m / 60) % 24).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
        c.window.intervals.push({ start: f(s0), end: f(Math.min(1439, s0 + 120)) });
      })} className="px-2 py-0.5 rounded border border-surface-border text-slate-400 hover:text-white">+ Adaugă interval</button>
      {errs.length > 0 && <div className="text-[11px] text-loss">{errs.join(" · ")} — nu se poate salva.</div>}
      <div className="flex gap-1">
        {DAYS.map((x, i) => (
          <button key={x} onClick={() => set(c => { c.window.days = c.window.days.includes(i) ? c.window.days.filter(y => y !== i) : [...c.window.days, i].sort(); })}
            className={`px-2 py-0.5 rounded border ${d.window.days.includes(i) ? "border-amber-500/50 text-amber-200" : "border-surface-border text-slate-500"}`}>{x}</button>
        ))}
      </div>
      <div className="text-[10px] text-slate-500">
        Intră doar în intervalele de mai sus, în zilele bifate (un interval peste miezul nopții aparține zilei în care începe).
        Poziția deschisă se termină după regulile ei (max {Number(d.strategy.time_stop_bars) * tfMin} min); nicio intrare care ar
        rămâne deschisă după 00:00. Evită 22–00 (rollover: spread până la 250×). Backtestul a fost făcut pe 10:00–20:00.
      </div>
    </div>
  );
}

function Config({ cfg, sp, atr }: { cfg?: NoisyConfig; sp?: NoisySpreadInfo; atr?: number | null }) {
  const save = useNoisySaveConfig();
  const [d, setD] = useState<NoisyConfig | undefined>(cfg);
  const appTz = useTimezone().data?.timezone;   // RO / DE — doar pentru echivalentul afisat al ferestrei
  const [dirty, setDirty] = useState(false);
  useEffect(() => { if (!dirty) setD(cfg); }, [cfg, dirty]);
  if (!d) return null;
  const set = (fn: (x: NoisyConfig) => void) => { const c = structuredClone(d); fn(c); setD(c); setDirty(true); };
  const num = (v: string) => (v === "" ? 0 : Number(v));
  // limitele = profilul timeframe-ului ACTIV (M1 / M5 au valori separate, testate pe fiecare)
  const prof = d.tf_profiles[d.timeframe];
  const limRow = (k: keyof NoisyConfig["limits"], label: string) => (
    <label className="flex items-center gap-2">
      <input type="checkbox" checked={prof.limits[k].enabled}
        onChange={e => set(c => { c.tf_profiles[c.timeframe].limits[k].enabled = e.target.checked; })} />
      <span className="w-40 text-slate-300">{label}</span>
      <input type="number" min={1} value={prof.limits[k].value} disabled={!prof.limits[k].enabled}
        onChange={e => set(c => { c.tf_profiles[c.timeframe].limits[k].value = num(e.target.value); })}
        className="w-16 bg-surface border border-surface-border rounded px-2 py-0.5 disabled:opacity-40" />
      {!prof.limits[k].enabled && <span className="text-slate-500">dezactivat</span>}
    </label>
  );
  const be = d.break_even;
  const beNum = (label: string, key: "trigger_pct" | "lock1_pct" | "phase2_zone_pct" | "lock2_pct", min: number, max: number, tip: string) => (
    <label className="flex items-center gap-2" title={tip}>
      <span className="w-32 text-slate-300">{label}</span>
      <input type="number" min={min} max={max} value={be[key]}
        onChange={e => set(c => { c.break_even[key] = num(e.target.value); })}
        className="w-16 bg-surface border border-surface-border rounded px-2 py-0.5" />
    </label>
  );
  return (
    <div className="rounded-xl border border-surface-border bg-surface-card p-4 space-y-3 text-xs">
      <div className="flex items-center">
        <div className="text-[11px] uppercase tracking-wider text-slate-500">Configurare (se aplică din mers, fără restart)</div>
        {dirty && (
          <div className="ml-auto flex gap-2">
            <button onClick={() => { setD(cfg); setDirty(false); }} className="px-3 py-1 rounded border border-surface-border text-slate-400">Renunță</button>
            <button disabled={windowErrors(d.window.intervals ?? []).length > 0}
              onClick={() => save.mutate(d, { onSuccess: () => setDirty(false) })}
              className="px-3 py-1 rounded bg-amber-500/20 text-amber-200 border border-amber-500/40 font-semibold disabled:opacity-40">Salvează</button>
          </div>
        )}
      </div>
      <div className="grid md:grid-cols-2 gap-4">
        <div className="space-y-2">
          <WindowsEditor d={d} set={set} appTz={appTz} />
          <div className="text-slate-400 font-semibold pt-2">Timeframe</div>
          <div className="flex gap-2 items-center">
            {(["M1", "M5"] as const).map(tf => (
              <button key={tf} onClick={() => set(c => { c.timeframe = tf; })}
                className={`px-3 py-0.5 rounded border ${d.timeframe === tf ? "border-amber-500/50 text-amber-200" : "border-surface-border text-slate-500"}`}>{tf}</button>
            ))}
            <span className="text-[10px] text-slate-500">{d.timeframe === "M5" ? "~3–4 trade-uri / zi, +0,08R în backtest" : "~25 trade-uri / zi (~2–3 / oră), ~0R după costuri în backtest"}</span>
          </div>
          <div className="flex items-center gap-2 pt-1">
            La Stop / buget epuizat (în Execuție):
            {(["close", "keep"] as const).map(v => (
              <button key={v} onClick={() => set(c => { c.on_stop = v; })}
                className={`px-2 py-0.5 rounded border ${d.on_stop === v ? "border-amber-500/50 text-amber-200" : "border-surface-border text-slate-500"}`}>
                {v === "close" ? "închide pozițiile (recomandat)" : "le lasă cu SL/țintă"}
              </button>
            ))}
          </div>
          <div className="text-[10px] text-slate-500">Emergency Stop închide mereu pozițiile reale Noisy.</div>
          <label className="flex items-center gap-2 pt-1">
            <input type="checkbox" checked={d.notify_trades} onChange={e => set(c => { c.notify_trades = e.target.checked; })} />
            Telegram la fiecare trade <span className="text-slate-500">(pe M1 = zeci de mesaje / zi; pornire, blocări și buget se trimit mereu)</span>
          </label>
          <div className="pt-2"><SpreadConfig d={d} set={set} sp={sp} atr={atr} /></div>
          <div className="text-slate-400 font-semibold pt-2">Știri High pe {d.symbol.slice(0, 3)}/{d.symbol.slice(3, 6)}</div>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={d.news.enabled} onChange={e => set(c => { c.news.enabled = e.target.checked; })} />
            fără intrări cu
            <input type="number" min={0} value={d.news.pre_min} onChange={e => set(c => { c.news.pre_min = num(e.target.value); })} className="w-12 bg-surface border border-surface-border rounded px-1" /> min înainte și
            <input type="number" min={0} value={d.news.post_min} onChange={e => set(c => { c.news.post_min = num(e.target.value); })} className="w-12 bg-surface border border-surface-border rounded px-1" /> min după
          </label>
        </div>
        <div className="space-y-2">
          <div className="text-slate-400 font-semibold">Limite {d.timeframe} (opționale, resetate zilnic)</div>
          <div className="text-[10px] text-slate-500">Valori separate pe M1 și M5 — la comutare se folosesc automat cele ale timeframe-ului ales.</div>
          {limRow("max_trades_day", "Max trade-uri / zi")}
          {limRow("max_losses_day", "Max pierderi / zi")}
          {limRow("max_consec_losses", "Max pierderi la rând")}
          <div className="text-slate-400 font-semibold pt-2">Buget izolat</div>
          <div className="flex items-center gap-2">
            Capital <input type="number" min={1} value={d.budget.capital} onChange={e => set(c => { c.budget.capital = num(e.target.value); })} className="w-20 bg-surface border border-surface-border rounded px-2 py-0.5" /> $
            · stop sub <input type="number" min={0} value={d.budget.min_remaining} onChange={e => set(c => { c.budget.min_remaining = num(e.target.value); })} className="w-20 bg-surface border border-surface-border rounded px-2 py-0.5" /> $
          </div>
          <div className="flex items-center gap-2">
            Risc / trade <input type="number" step={0.1} min={0.05} value={+(d.sizing.risk_pct * 100).toFixed(2)} onChange={e => set(c => { c.sizing.risk_pct = num(e.target.value) / 100; })} className="w-16 bg-surface border border-surface-border rounded px-2 py-0.5" /> % din buget
            <span className="text-slate-500">(lotul minim 0,01 domină la buget mic)</span>
          </div>
          <div className="text-[10px] text-slate-500">Protecțiile globale (capital, circuit breaker, știri, închidere de vineri, risc maxim pe trade, poziții simultane) se aplică peste acestea și nu pot fi ocolite.</div>
          <div className="text-slate-400 font-semibold pt-2">Țintă (R:R)</div>
          <div className="flex items-center gap-2 flex-wrap">
            <button onClick={() => set(c => { c.strategy.tp_rr = 0; })}
              className={`px-2 py-0.5 rounded border ${!Number(d.strategy.tp_rr) ? "border-amber-500/50 text-amber-200" : "border-surface-border text-slate-500"}`}>
              revenirea la EMA20 (testat, implicit)
            </button>
            <button onClick={() => set(c => { c.strategy.tp_rr = Number(c.strategy.tp_rr) || 2; })}
              className={`px-2 py-0.5 rounded border ${Number(d.strategy.tp_rr) ? "border-amber-500/50 text-amber-200" : "border-surface-border text-slate-500"}`}>
              R:R fix
            </button>
            {!!Number(d.strategy.tp_rr) && (
              <span className="flex items-center gap-1">
                1 : <input type="number" step={0.1} min={0.5} max={10} value={Number(d.strategy.tp_rr)}
                  onChange={e => set(c => { c.strategy.tp_rr = num(e.target.value); })}
                  className="w-16 bg-surface border border-surface-border rounded px-2 py-0.5" />
              </span>
            )}
          </div>
          {!!Number(d.strategy.tp_rr) && (
            <div className="text-[10px] text-yellow-300/90">
              Backtest 12 luni (USDJPY): țintele fixe au fost mai slabe decât revenirea la EMA (M5: 1,5R +0,061R · 2R +0,058R ·
              3R +0,041R față de +0,081R; M1: toate ~0 sau negative). Prețul revine rar atât de departe în timpul trade-ului.
            </div>
          )}
          <div className="text-slate-400 font-semibold pt-2">Break-Even</div>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={be.enabled} onChange={e => set(c => { c.break_even.enabled = e.target.checked; })} />
            Activează Break-Even <span className="text-slate-500">(aceeași regulă ca în Custom Engine; dezactivat implicit)</span>
          </label>
          {be.enabled && (
            <div className="space-y-2 pl-2 border-l-2 border-surface-border">
              <div className="rounded-lg border border-yellow-500/40 bg-yellow-500/10 px-3 py-2 text-[11px] text-yellow-200 space-y-1">
                <div className="font-semibold">Ce au arătat testele (USDJPY, 12 luni, setările implicite 80 / 30 / 40 / 50)</div>
                <div>• M5: win rate 44% → 48%, dar câștigul mediu scade +0,081R → +0,069R / trade; drawdown neschimbat (−31R).</div>
                <div>• M1: win rate 41% → 45%, câștig ~0 (−0,010R → −0,006R); drawdown −117R → −104R.</div>
                <div>Pe scurt: mai multe trade-uri câștigătoare și scăderi puțin mai mici, dar <b>nu mai mult profit</b> — la
                  mean reversion prețul atinge des 80% din drum și revine, iar SL-ul mutat taie o parte din trade-urile care ar fi
                  ajuns la țintă. În Execuție, SL-ul real e mutat la broker când trade-ul ajunge în faza respectivă.</div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                {beNum("Trigger TP%", "trigger_pct", 50, 99, "Prețul trebuie să atingă X% din distanța până la țintă pentru a arma break-even.")}
                {beNum("Lock SL Faza 1%", "lock1_pct", 5, 60, "SL mutat la X% din distanța până la țintă la faza 1.")}
              </div>
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={be.phase2_enabled} onChange={e => set(c => { c.break_even.phase2_enabled = e.target.checked; })} />
                Activează Faza 2 (opțional)
              </label>
              {be.phase2_enabled && (
                <div className="grid grid-cols-2 gap-2">
                  {beNum("Zonă Faza 2%", "phase2_zone_pct", 20, 70, "Limita superioară a zonei de retragere Faza 2 (lock1–X%).")}
                  {beNum("Lock SL Faza 2%", "lock2_pct", 30, 80, "SL mutat la X% din distanța până la țintă la faza 2.")}
                </div>
              )}
              <p className="text-[10px] text-slate-500">Faza 1: prețul atinge trigger% din țintă și se întoarce → SL la lock1%. Faza 2: retragere în zona
                lock1–zonă%, din nou trigger% și întoarcere → SL la lock2%.</p>
            </div>
          )}
        </div>
      </div>
      <div className="text-[10px] text-slate-500 border-t border-surface-border pt-2">
        Strategia (testată pe 12 luni): EMA{String(d.strategy.ema)} ± {String(d.strategy.dev_atr)}×ATR{String(d.strategy.atr)} · SL {String(d.strategy.sl_atr)}×ATR · țintă {Number(d.strategy.tp_rr) ? `${d.strategy.tp_rr}R` : "EMA"} · stop de timp {String(d.strategy.time_stop_bars)} bare ·
        cost/ATR ≥ {String(prof.min_atr_over_cost)} ({d.timeframe}). Parametrii strategiei (EMA / ATR / deviație / SL) se schimbă doar în noisy_engine/config.json (orice schimbare = variantă netestată).
      </div>
      {save.isError && <div className="text-loss">{(save.error as Error).message}</div>}
    </div>
  );
}

function Trades() {
  const { data } = useNoisyTrades();
  if (!data?.length) return <div className="rounded-xl border border-surface-border bg-surface-card p-4 text-xs text-slate-500">Niciun trade virtual încă.</div>;
  return (
    <div className="rounded-xl border border-surface-border bg-surface-card p-4 overflow-x-auto">
      <div className="text-[11px] uppercase tracking-wider text-slate-500 mb-2">Trade-uri virtuale ({data.length})</div>
      <table className="w-full text-xs">
        <thead><tr className="text-slate-500 text-left"><th className="py-1">Intrare</th><th>Dir</th><th>Preț</th><th>Ieșire</th><th>Motiv</th><th>Brut</th><th>Net</th><th>$ (0,01)</th><th>Min</th></tr></thead>
        <tbody>
          {data.slice(0, 100).map(t => (
            <tr key={t.id} className="border-t border-surface-border">
              <td className="py-1 text-slate-400">{t.entry_t.slice(5, 16).replace("T", " ")}</td>
              <td className={t.dir === "LONG" ? "text-profit" : "text-loss"}>{t.dir}</td>
              <td className="text-white">{t.entry.toFixed(3)}</td>
              <td className="text-white">{t.exit.toFixed(3)}</td>
              <td className="text-slate-400">{t.reason}</td>
              <td className="text-slate-400">{fmtR(t.gross_R)}</td>
              <td className={t.R >= 0 ? "text-profit" : "text-loss"}>{fmtR(t.R)}</td>
              <td className="text-slate-300">{fmt$(t.pnl_money)}</td>
              <td className="text-slate-500">{t.hold_min ?? t.bars * (t.tf === "M5" ? 5 : 1)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Logs() {
  const [open, setOpen] = useState(false);
  const { data } = useNoisyLogs(open);
  return (
    <div className="rounded-xl border border-surface-border bg-surface-card p-4">
      <button onClick={() => setOpen(!open)} className="text-[11px] uppercase tracking-wider text-slate-500 hover:text-slate-300">
        {open ? "▾" : "▸"} Jurnal
      </button>
      {open && <pre className="mt-2 text-[10px] text-slate-400 whitespace-pre-wrap max-h-80 overflow-auto">{(data?.lines ?? []).join("")}</pre>}
    </div>
  );
}

export function NoisyEnginePage() {
  const { data: st } = useNoisyStatus();
  return (
    <div className="space-y-4">
      <Header st={st} />
      <ModeSwitch st={st} />
      <Today st={st} />
      <div className="grid lg:grid-cols-2 gap-4">
        <Market st={st} />
        <Score st={st} />
      </div>
      <Config cfg={st?.config} sp={st?.spread} atr={st?.last?.atr} />
      <Trades />
      <Logs />
      {!!st?.errors?.length && <pre className="text-[10px] text-loss whitespace-pre-wrap">{st.errors.join("\n")}</pre>}
    </div>
  );
}
