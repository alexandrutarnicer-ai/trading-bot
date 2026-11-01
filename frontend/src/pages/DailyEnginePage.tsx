import { useState } from "react";
import { CalendarClock, Loader2, Play, Square, FlaskConical } from "lucide-react";
import { PositionSizingCard } from "../components/PositionSizingCard";
import { useDailyStatus, useDailyTrades, useDailyLogs, useDailyStart, useDailyStop, useDailySetMode } from "../api/hooks";
import type { DailyMarketStatus, DailyScore } from "../api/types";

// Daily Engine — motor intraday ORB pe deschiderea Londrei (dimineata) si New York (dupa-amiaza).
// Mod SHADOW: foloseste preturile reale, inregistreaza trade-uri VIRTUALE, nu plaseaza niciun ordin.

const PHASE: Record<string, { label: string; cls: string }> = {
  waiting_open:  { label: "Așteaptă deschiderea", cls: "bg-slate-700/40 text-slate-400" },
  forming_or:    { label: "Se formează intervalul", cls: "bg-blue-500/15 text-blue-300" },
  waiting_entry: { label: "Așteaptă intrarea", cls: "bg-amber-500/15 text-amber-300" },
  in_position:   { label: "Poziție virtuală deschisă", cls: "bg-profit/15 text-profit" },
  closed:        { label: "Încheiat azi", cls: "bg-slate-600/30 text-slate-300" },
  skipped:       { label: "Zi sărită", cls: "bg-slate-700/40 text-slate-400" },
  weekend:       { label: "Weekend", cls: "bg-slate-700/40 text-slate-500" },
  disabled:      { label: "Dezactivat", cls: "bg-slate-700/40 text-slate-500" },
  error:         { label: "Eroare", cls: "bg-loss/15 text-loss" },
};

const fmt = (v: number | undefined) => (v == null ? "—" : Math.abs(v) >= 100 ? v.toFixed(2) : v.toFixed(5));
const fmtR = (v: number | null | undefined) => (v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(2)}R`);
const rCls = (v: number | null | undefined) => (v == null ? "text-slate-400" : v > 0 ? "text-profit" : v < 0 ? "text-loss" : "text-slate-300");

function MarketCard({ m, score, bt }: {
  m: DailyMarketStatus; score?: DailyScore;
  bt?: { trades: number; expectancy_R: number; period: string; verdict: string };
}) {
  const ph = PHASE[m.phase] ?? PHASE.waiting_open;
  const side = m.side === 1 ? "LONG" : m.side === -1 ? "SHORT" : null;
  return (
    <div className="bg-surface rounded-xl border border-surface-border p-4 space-y-3">
      <div className="flex items-start gap-2">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-base font-bold text-white">{m.symbol}</span>
            {m.role && <span className="text-[10px] uppercase tracking-wider text-slate-500">{m.role}</span>}
          </div>
          <div className="text-[11px] text-slate-400">{m.label}</div>
        </div>
        <span className={`ml-auto text-[11px] px-2 py-0.5 rounded-full font-semibold ${ph.cls}`}>{ph.label}</span>
      </div>

      <div className="grid grid-cols-2 gap-2 text-[11px]">
        <div className="text-slate-500">Fereastra (ora {m.app_tz_label ?? "RO"})</div>
        <div className="text-white font-semibold"
          title={m.app_tz_label === "DE" ? `ora RO: ${m.window_ro ?? "—"}` : undefined}>{m.window_app ?? m.window_ro ?? "—"}</div>
        <div className="text-slate-500">Ora bursei</div>
        <div className="text-slate-300">{m.window_local ?? "—"}</div>
        <div className="text-slate-500">Regulă</div>
        <div className="text-slate-300">
          interval {m.or_minutes} min · {m.entry_mode === "breakout" ? "ordine stop pe margini" : "intrare pe direcție"} · închidere la final
        </div>
        {m.or_hi != null && (<>
          <div className="text-slate-500">Interval azi</div>
          <div className="text-slate-300">{fmt(m.or_lo)} – {fmt(m.or_hi)}</div>
        </>)}
        {side && m.entry != null && (<>
          <div className="text-slate-500">Poziție</div>
          <div className={side === "LONG" ? "text-profit font-semibold" : "text-loss font-semibold"}>
            {side} @ {fmt(m.entry)} · SL {fmt(m.sl)}
          </div>
        </>)}
        {m.phase === "in_position" && (<>
          <div className="text-slate-500">Rezultat deschis</div>
          <div className={rCls(m.open_R)}>{fmtR(m.open_R)} (ultimul {fmt(m.last)})</div>
        </>)}
        {m.phase === "closed" && (<>
          <div className="text-slate-500">Rezultat azi</div>
          <div className={rCls(m.R)}>{fmtR(m.R)} · ieșire {fmt(m.exit)} ({String(m.reason ?? "")})</div>
        </>)}
        {m.phase === "skipped" && m.reason && (<>
          <div className="text-slate-500">Motiv</div>
          <div className="text-slate-400">{m.reason}</div>
        </>)}
        {m.note && <div className="col-span-2 text-amber-400/80">{m.note}</div>}
      </div>

      <div className="border-t border-surface-border pt-2 grid grid-cols-2 gap-2 text-[11px]">
        <div>
          <div className="text-slate-500">Shadow (date noi)</div>
          <div className="text-white">
            {score?.trades ?? 0} trade-uri · <span className={rCls(score?.expectancy_R)}>{fmtR(score?.expectancy_R)}</span>/trade
          </div>
          <div className="text-slate-500">{score?.wins ?? 0}W / {score?.losses ?? 0}L · total <span className={rCls(score?.total_R)}>{fmtR(score?.total_R)}</span></div>
        </div>
        {bt && (
          <div>
            <div className="text-slate-500">Backtest {bt.period}</div>
            <div className="text-white">{bt.trades} trade-uri · <span className="text-profit">{fmtR(bt.expectancy_R)}</span>/trade</div>
            <div className="text-slate-500">verdict M0: {bt.verdict}</div>
          </div>
        )}
      </div>
    </div>
  );
}

function ModeSwitch({ mode, execution, running }: { mode?: string; execution?: { active: boolean; reason: string }; running?: boolean }) {
  const set = useDailySetMode();
  const exec = mode === "execute";
  // Selector cu doua stari explicite: un singur comutator „on/off” parea ca SHADOW e dezactivat
  // (gri = EXECUTIA oprita = SHADOW activ), iar click-ul cerea confirmarea pentru EXECUTIE.
  function choose(target: "shadow" | "execute") {
    if (target === mode || set.isPending) return;
    toggle();
  }
  function toggle() {
    if (!exec) {
      if (!window.confirm("Treci Daily Engine pe EXECUȚIE?\n\nDe la următoarea fereastră (deschiderea Londrei / a New York-ului)" +
        "plasează ORDINE REALE în contul MT5 conectat: GBPUSD ordine stop pe margini, US500 ordin la piață, SL atașat, " +
        "închidere obligatorie în aceeași zi.\n\nPe un cont REAL trebuie în plus deblocat „Daily Engine” în Settings → Trading LIVE.")) return;
      if (!window.confirm("Confirmare finală: Daily Engine va tranzacționa cu ordine reale. Continui?")) return;
    } else if (!window.confirm("Revii pe SHADOW? Nu se mai deschid ordine; pozițiile reale de azi se închid la finalul ferestrei.")) return;
    set.mutate(exec ? "shadow" : "execute");
  }
  return (
    <div className={`rounded-xl border p-4 flex items-center gap-3 flex-wrap ${exec ? "bg-loss/5 border-loss/40" : "bg-surface border-surface-border"}`}>
      <div className="flex rounded-lg border border-surface-border overflow-hidden shrink-0 text-xs font-semibold">
        <button onClick={() => choose("shadow")} disabled={set.isPending}
          className={`px-3 py-1.5 transition-colors ${!exec ? "bg-cyan-500/20 text-cyan-300" : "text-slate-500 hover:text-slate-300"}`}>
          {!exec ? "● " : ""}SHADOW
        </button>
        <button onClick={() => choose("execute")} disabled={set.isPending}
          className={`px-3 py-1.5 border-l border-surface-border transition-colors ${exec ? "bg-loss/20 text-loss" : "text-slate-500 hover:text-slate-300"}`}>
          {exec ? "● " : ""}EXECUȚIE
        </button>
      </div>
      <div className="text-xs">
        <div className="font-semibold text-white">
          Mod activ: {exec ? "EXECUȚIE (ordine reale)" : "SHADOW (virtual)"}
          {running === false && <span className="ml-2 text-amber-400 font-normal">— engine-ul e OPRIT: modul se aplică doar după Start</span>}
        </div>
        <div className="text-[11px] text-slate-500">
          {exec
            ? (execution?.active ? `Activ — ${execution.reason}. ` : `Blocat — ${execution?.reason ?? "?"}. `)
            : "Trade-uri virtuale pe prețuri reale, zero ordine. "}
          Se aplică de la următoarea fereastră (ziua trebuie activată înainte de formarea intervalului). Magic 880001 — apare ca „Daily” în Tranzacții.
        </div>
      </div>
      {set.isError && <span className="text-[11px] text-loss">{(set.error as Error).message}</span>}
    </div>
  );
}

export function DailyEnginePage() {
  const { data: st } = useDailyStatus();
  const { data: trades } = useDailyTrades();
  const start = useDailyStart();
  const stop = useDailyStop();
  const [showLogs, setShowLogs] = useState(false);
  const { data: logs } = useDailyLogs(showLogs);
  const running = st?.running ?? false;
  const sc = st?.scorecard;

  return (
    <div className="space-y-4">
      <div className="bg-surface rounded-xl border border-surface-border p-4 flex items-center gap-4 flex-wrap">
        <div className="flex items-center gap-3">
          <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${running ? "bg-profit/20" : "bg-slate-700/40"}`}>
            <CalendarClock size={20} className={running ? "text-profit" : "text-slate-500"} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-bold text-white">Daily Engine</h2>
              <span className={`inline-flex items-center gap-1.5 text-[11px] font-semibold ${running ? "text-profit" : "text-slate-500"}`}>
                <span className={`w-2 h-2 rounded-full ${running ? "bg-profit animate-pulse" : "bg-slate-600"}`} />
                {running ? "ACTIV" : "OPRIT"}
              </span>
              {st?.mode === "execute" ? (
                <span className={`inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full font-semibold ${st?.execution?.active ? "bg-loss/20 text-loss" : "bg-warn/15 text-warn"}`}>
                  ● EXECUȚIE — {st?.execution?.active ? `ordine reale (${st.execution.reason})` : `blocată: ${st?.execution?.reason ?? "?"}`}
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full bg-violet-500/15 text-violet-300 font-semibold">
                  <FlaskConical size={11} /> SHADOW — fără ordine reale
                </span>
              )}
            </div>
            <div className="text-[11px] text-slate-500">
              {running
                ? `PID ${st?.pid} · heartbeat ${st?.heartbeat?.slice(11, 19) ?? "?"} · ora server = UTC${st?.server_offset_h != null ? (st.server_offset_h >= 0 ? "+" : "") + st.server_offset_h : " (detectată la deschidere)"}`
                : "Tranzacționare intraday la deschiderea Londrei și a New York-ului — trade-uri virtuale pe prețuri reale"}
            </div>
          </div>
        </div>
        <div className="ml-auto">
          {running ? (
            <button onClick={() => stop.mutate()} disabled={stop.isPending}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-loss/20 text-loss hover:bg-loss/30 disabled:opacity-50 text-sm font-semibold">
              {stop.isPending ? <><Loader2 size={14} className="animate-spin" /> Se oprește...</> : <><Square size={14} /> Oprește</>}
            </button>
          ) : (
            <button onClick={() => start.mutate()} disabled={start.isPending}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-profit/20 text-profit hover:bg-profit/30 disabled:opacity-50 text-sm font-semibold">
              {start.isPending ? <><Loader2 size={14} className="animate-spin" /> Pornește...</> : <><Play size={14} /> Pornește</>}
            </button>
          )}
        </div>
        {(start.error || stop.error) && (
          <div className="w-full text-[11px] text-loss">{String((start.error ?? stop.error)?.message)}</div>
        )}
      </div>

      <ModeSwitch mode={st?.mode} execution={st?.execution} running={st?.running} />

      <div className="text-[11px] text-slate-500 bg-surface rounded-xl border border-surface-border px-4 py-2">
        Un trade pe zi pe piață, închis obligatoriu în aceeași zi (niciodată peste noapte). Orele urmează ora bursei —
        în săptămânile cu decalaj de fus SUA/RO fereastra de după-amiază se mută automat cu o oră mai devreme.
        Trade-urile sunt virtuale: nu apar în MT5 și nu afectează contul. Edge-ul din backtest e mic (+0,06…0,08R/trade)
        și trebuie confirmat aici, pe date noi, înainte de orice ordin real.
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {(st?.markets ?? []).map(m => (
          <MarketCard key={m.symbol} m={m} score={sc?.by_symbol?.[m.symbol]} bt={st?.backtest_ref?.[m.symbol]} />
        ))}
        {(!st?.markets || st.markets.length === 0) && (
          <div className="md:col-span-2 text-center text-sm text-slate-500 py-6 bg-surface rounded-xl border border-surface-border">
            {running ? "Se conectează la MT5..." : "Pornește motorul ca să vezi starea zilei pe fiecare piață."}
          </div>
        )}
      </div>

      <div className="bg-surface rounded-xl border border-surface-border p-4 space-y-3">
        <div className="text-sm font-semibold text-white">Dimensionarea poziției <span className="text-[11px] font-normal text-slate-500">— în SHADOW se calculează doar lotul ipotetic al fiecărui trade virtual (estimare în bani)</span></div>
        {(st?.markets ?? []).map(m => (
          <PositionSizingCard key={m.symbol} engine="Daily Engine" symbol={m.symbol}
            fraction={st?.sizing?.fraction ?? 1} riskPct={st?.sizing?.risk_pct ?? 0.01}
            capitalSync={st?.sizing?.capital_sync_mt5 ?? true} capitalUsd={st?.sizing?.capital_usd ?? null} />
        ))}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {[
          { label: "Trade-uri virtuale", value: String(sc?.trades ?? 0) },
          { label: "Win / Loss", value: `${sc?.wins ?? 0} / ${sc?.losses ?? 0}` },
          { label: "Win rate", value: sc?.win_rate != null ? `${Math.round(sc.win_rate * 100)}%` : "—" },
          { label: "Total", value: fmtR(sc?.total_R), cls: rCls(sc?.total_R) },
          { label: "Medie / trade", value: fmtR(sc?.expectancy_R), cls: rCls(sc?.expectancy_R) },
        ].map(c => (
          <div key={c.label} className="bg-surface rounded-xl border border-surface-border p-3 text-center">
            <div className="text-[10px] text-slate-500 uppercase tracking-wider">{c.label}</div>
            <div className={`text-lg font-bold ${c.cls ?? "text-white"}`}>{c.value}</div>
          </div>
        ))}
      </div>

      <div className="bg-surface rounded-xl border border-surface-border p-4">
        <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Trade-uri virtuale</h3>
        {!trades || trades.length === 0 ? (
          <div className="text-sm text-slate-500 py-4 text-center">Încă niciun trade înregistrat.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-[11px]">
              <thead className="text-slate-500">
                <tr className="text-left">
                  <th className="py-1">Zi</th><th>Piață</th><th>Direcție</th><th>Intrare</th><th>SL</th>
                  <th>Ieșire</th><th>Motiv</th><th>Lot ipotetic</th><th className="text-right">≈ bani (estimat)</th><th className="text-right">R</th>
                </tr>
              </thead>
              <tbody>
                {trades.map(t => (
                  <tr key={`${t.day}-${t.symbol}`} className="border-t border-surface-border">
                    <td className="py-1 text-slate-300">{t.day}</td>
                    <td className="text-white font-semibold">{t.symbol}</td>
                    <td className={t.side === "LONG" ? "text-profit" : "text-loss"}>{t.side}</td>
                    <td className="text-slate-300">{fmt(t.entry)}</td>
                    <td className="text-slate-400">{fmt(t.sl)}</td>
                    <td className="text-slate-300">{fmt(t.exit)}</td>
                    <td className="text-slate-400">{t.reason === "EOD" ? "final de zi" : t.reason}</td>
                    <td className="text-slate-400">{t.lots ?? "—"}</td>
                    <td className={`text-right ${rCls(t.pnl_money_est)}`}>{t.pnl_money_est != null ? `${t.pnl_money_est > 0 ? "+" : ""}${t.pnl_money_est.toFixed(2)} ${t.currency ?? ""}` : "—"}</td>
                    <td className={`text-right font-semibold ${rCls(t.R)}`}>{fmtR(t.R)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {st?.errors && st.errors.length > 0 && (
        <div className="bg-loss/10 border border-loss/30 rounded-xl p-3 text-[11px] text-loss space-y-0.5">
          {st.errors.map((e, i) => <div key={i}>{e}</div>)}
        </div>
      )}

      <div className="bg-surface rounded-xl border border-surface-border p-4">
        <button onClick={() => setShowLogs(v => !v)} className="text-xs text-slate-400 hover:text-white">
          {showLogs ? "▾ Ascunde jurnalul" : "▸ Arată jurnalul motorului"}
        </button>
        {showLogs && (
          <pre className="mt-2 max-h-80 overflow-auto text-[10px] text-slate-400 whitespace-pre-wrap">
            {(logs?.lines ?? []).join("") || "Jurnal gol."}
          </pre>
        )}
      </div>
    </div>
  );
}
