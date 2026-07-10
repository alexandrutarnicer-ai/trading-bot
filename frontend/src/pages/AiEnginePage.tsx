import { useState, useEffect } from "react";
import { Bot, Play, Square, Brain, AlertTriangle, ChevronDown, ChevronRight, RefreshCw, Loader2 } from "lucide-react";
import {
  useAiStatus, useAiDecisions, useAiOutcomes, useAiCouncil, useAiConfig,
  useAiLogs, useAiStart, useAiStop, useAiSaveConfig,
} from "../api/hooks";
import type { AiDecision } from "../api/types";
import { AiProvidersCard } from "../components/AiProvidersCard";

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtR(v: number | null | undefined) {
  if (v == null) return "—";
  return `${v >= 0 ? "+" : ""}${v.toFixed(2)}R`;
}

const ACTION_STYLE: Record<string, string> = {
  OPEN_LONG:  "text-profit",
  OPEN_SHORT: "text-loss",
  CLOSE:      "text-amber-400",
  WAIT:       "text-slate-400",
};

const EXEC_BADGE: Record<string, { label: string; cls: string }> = {
  placed:   { label: "PLASAT",   cls: "bg-profit/20 text-profit" },
  rejected: { label: "RESPINS",  cls: "bg-amber-500/20 text-amber-300" },
  failed:   { label: "EȘUAT",    cls: "bg-loss/20 text-loss" },
  shadow:   { label: "SHADOW",   cls: "bg-blue-500/20 text-blue-300" },
  skipped:  { label: "—",        cls: "bg-slate-700/40 text-slate-400" },
  pending:  { label: "ÎN CURS",  cls: "bg-slate-700/40 text-slate-300" },
};

const ROLE_LABEL: Record<string, string> = {
  technical:   "📈 Analist Tehnic",
  macro:       "🌍 Analist Macro/Știri",
  risk:        "🛡 Risk Manager",
  head_trader: "🎯 Head Trader",
  error:       "⚠ Eroare",
};

// ── Council transcript (expandabil per decizie) ──────────────────────────────

function CouncilView({ decisionId }: { decisionId: number }) {
  const { data, isLoading } = useAiCouncil(decisionId);
  if (isLoading) return <div className="text-xs text-slate-500 p-2">Se încarcă dezbaterea...</div>;
  if (!data) return <div className="text-xs text-slate-500 p-2">Transcript indisponibil.</div>;
  return (
    <div className="space-y-2 p-3 bg-surface/60 rounded-lg border border-surface-border/40">
      <div className="text-[10px] text-slate-500">
        Convocat de: <span className="text-slate-300">{data.trigger}</span> · durată {data.duration_s}s
      </div>
      {Object.entries(data.transcript).map(([role, view]) => (
        <div key={role} className="text-xs">
          <div className="text-[11px] font-semibold text-slate-300 mb-0.5">{ROLE_LABEL[role] ?? role}</div>
          <div className="text-slate-400 pl-3 border-l border-surface-border space-y-0.5">
            {typeof view === "string" ? (
              <div>{view}</div>
            ) : (
              Object.entries(view as Record<string, unknown>).map(([k, v]) => (
                <div key={k}>
                  <span className="text-slate-500">{k}:</span>{" "}
                  <span className="text-slate-300">{typeof v === "object" ? JSON.stringify(v) : String(v)}</span>
                </div>
              ))
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Decizii ───────────────────────────────────────────────────────────────────

function DecisionRow({ d }: { d: AiDecision }) {
  const [open, setOpen] = useState(false);
  const badge = EXEC_BADGE[d.exec_status] ?? EXEC_BADGE.pending;
  return (
    <div className="border border-surface-border rounded-lg bg-surface">
      <button
        className="w-full flex items-center gap-3 px-3 py-2 text-left hover:bg-surface-border/20"
        onClick={() => setOpen(o => !o)}
      >
        {open ? <ChevronDown size={14} className="text-slate-500 shrink-0" /> : <ChevronRight size={14} className="text-slate-500 shrink-0" />}
        <span className="text-[10px] text-slate-500 font-mono w-24 shrink-0">{d.ts.slice(5, 16)}</span>
        <span className="text-xs font-semibold text-white w-16 shrink-0">{d.symbol}</span>
        <span className={`text-xs font-semibold w-24 shrink-0 ${ACTION_STYLE[d.action] ?? ""}`}>{d.action}</span>
        <span className={`text-[9px] px-1.5 py-0.5 rounded shrink-0 ${badge.cls}`}>{badge.label}</span>
        {d.entry != null && (
          <span className="text-[10px] text-slate-400 font-mono hidden md:inline">
            {d.entry} / SL {d.sl} / TP {d.tp}
          </span>
        )}
        <span className="ml-auto text-[10px] text-slate-500 shrink-0">conf {d.confidence}%</span>
        {d.outcome && (
          <span className={`text-xs font-mono font-semibold shrink-0 ${(d.outcome.result_r ?? 0) >= 0 ? "text-profit" : "text-loss"}`}>
            {fmtR(d.outcome.result_r)}
          </span>
        )}
      </button>
      {open && (
        <div className="px-3 pb-3 space-y-2">
          <div className="text-xs text-slate-300 bg-surface/60 rounded-lg p-2 border border-surface-border/40">
            <span className="text-slate-500">Motivație: </span>{d.rationale || "—"}
          </div>
          {d.exec_detail && d.exec_status !== "placed" && (
            <div className="text-[10px] text-amber-400">→ {d.exec_detail}</div>
          )}
          <CouncilView decisionId={d.id} />
        </div>
      )}
    </div>
  );
}

// ── Config piete ──────────────────────────────────────────────────────────────

function MarketsEditor() {
  const { data: cfg } = useAiConfig();
  const save = useAiSaveConfig();
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState("");
  const currentMarkets = (cfg?.markets ?? []).join(", ");

  // Populeaza campul ori de cate ori se intra in editare — imun la refetch-uri
  // sau hot-reload care ar goli state-ul (bug: input gol la Editeaza).
  useEffect(() => {
    if (editing && text.trim() === "" && currentMarkets) {
      setText(currentMarkets);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editing, currentMarkets]);

  if (!cfg) return null;
  const start = () => { setText(currentMarkets); setEditing(true); };
  const submit = () => {
    const markets = text.split(",").map(s => s.trim().toUpperCase()).filter(Boolean);
    if (markets.length === 0) return;   // nu trimite lista goala
    save.mutate({ markets }, { onSuccess: () => setEditing(false) });
  };

  return (
    <div className="bg-surface rounded-xl border border-surface-border p-4 space-y-2">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-white">Piețe urmărite</h3>
        {!editing && (
          <button onClick={start} className="text-[11px] text-blue-400 hover:text-blue-300">Editează</button>
        )}
      </div>
      {editing ? (
        <div className="space-y-2">
          <input
            value={text} onChange={e => setText(e.target.value)}
            className="w-full bg-surface-card border border-surface-border rounded-lg px-3 py-1.5 text-xs text-white font-mono"
            placeholder={currentMarkets || "EURUSD, USDJPY, GBPUSD"}
          />
          <div className="flex gap-2">
            <button onClick={submit} disabled={save.isPending}
              className="text-[11px] px-3 py-1 rounded-lg bg-profit/20 text-profit hover:bg-profit/30">
              {save.isPending ? "Se validează în MT5..." : "Salvează"}
            </button>
            <button onClick={() => setEditing(false)} className="text-[11px] px-3 py-1 rounded-lg bg-surface-border/40 text-slate-300">
              Anulează
            </button>
          </div>
          {save.isError && <div className="text-[10px] text-loss">{(save.error as Error).message}</div>}
          {(save.data as { restart_needed?: boolean } | undefined)?.restart_needed && (
            <div className="text-[10px] text-amber-400">⚠ Motorul rulează — repornește-l ca să preia noile piețe.</div>
          )}
        </div>
      ) : (
        <div className="flex flex-wrap gap-1.5">
          {cfg.markets.map(m => (
            <span key={m} className="text-[11px] font-mono px-2 py-0.5 rounded bg-surface-border/40 text-slate-200">{m}</span>
          ))}
        </div>
      )}
      <div className="text-[10px] text-slate-500">
        Simbolurile se validează contra MT5 la salvare. Alese pentru cont ~$1000:
        risc lot minim $2–4, marjă $33–45/poziție.
      </div>
    </div>
  );
}

// ── Pagina ────────────────────────────────────────────────────────────────────

export function AiEnginePage() {
  const { data: st } = useAiStatus();
  const { data: decisions } = useAiDecisions(30);
  const { data: outcomes } = useAiOutcomes(30);
  const start = useAiStart();
  const stop  = useAiStop();
  const [showLogs, setShowLogs] = useState(false);
  const { data: logs, refetch: refetchLogs } = useAiLogs(120, showLogs);

  const running = st?.running ?? false;
  const sc = st?.scorecard;

  return (
    <div className="space-y-4">
      {/* Header status + On/Off */}
      <div className="bg-surface rounded-xl border border-surface-border p-4 flex items-center gap-4 flex-wrap">
        <div className="flex items-center gap-3">
          <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${running ? "bg-profit/20" : "bg-slate-700/40"}`}>
            <Brain size={20} className={running ? "text-profit" : "text-slate-500"} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-bold text-white">AI Engine</h2>
              <span className={`inline-flex items-center gap-1.5 text-[11px] font-semibold ${running ? "text-profit" : "text-slate-500"}`}>
                <span className={`w-2 h-2 rounded-full ${running ? "bg-profit animate-pulse" : "bg-slate-600"}`} />
                {running ? "ACTIV" : "OPRIT"}
              </span>
            </div>
            <div className="text-[11px] text-slate-500">
              {running
                ? `PID ${st?.pid} · model ${st?.model ?? "?"} · mode ${st?.mode ?? "?"} · ultimul heartbeat ${st?.ts?.slice(11, 19) ?? "?"}`
                : "Motor autonom AI — separat de botul pe reguli, doar cont DEMO"}
            </div>
          </div>
        </div>
        <div className="ml-auto flex items-center gap-2">
          {running ? (
            <button
              onClick={() => stop.mutate()}
              disabled={stop.isPending}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-loss/20 text-loss hover:bg-loss/30 disabled:opacity-50 text-sm font-semibold"
            >
              {stop.isPending
                ? <><Loader2 size={14} className="animate-spin" /> Se oprește...</>
                : <><Square size={14} /> Oprește</>}
            </button>
          ) : (
            <button
              onClick={() => start.mutate()}
              disabled={start.isPending}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-profit/20 text-profit hover:bg-profit/30 disabled:opacity-50 text-sm font-semibold"
            >
              {start.isPending
                ? <><Loader2 size={14} className="animate-spin" /> Se pornește...</>
                : <><Play size={14} /> Pornește</>}
            </button>
          )}
        </div>
        {(start.isError || stop.isError) && (
          <div className="w-full text-[11px] text-loss">
            {((start.error || stop.error) as Error)?.message}
          </div>
        )}
      </div>

      {/* Erori recente */}
      {st?.last_errors && st.last_errors.length > 0 && (
        <div className="bg-amber-500/10 border border-amber-500/30 rounded-xl p-3">
          <div className="flex items-center gap-2 text-amber-300 text-xs font-semibold mb-1">
            <AlertTriangle size={13} /> Erori recente motor
          </div>
          {st.last_errors.slice(-3).map((e, i) => (
            <div key={i} className="text-[10px] text-amber-200/80 font-mono">
              {e.ts.slice(11, 19)} [{e.where}] {e.error}
            </div>
          ))}
        </div>
      )}

      {/* Scorecard */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
        {[
          { label: "Decizii",       value: sc ? String(sc.decisions) : "—" },
          { label: "WAIT (răbdare)", value: sc ? String(sc.waits) : "—" },
          { label: "Trades închise", value: sc ? String(sc.closed_trades) : "—" },
          { label: "Total R",       value: sc ? fmtR(sc.total_R) : "—",
            color: sc && sc.total_R >= 0 ? "text-profit" : "text-loss" },
          { label: "Expectancy",    value: sc ? fmtR(sc.expectancy_R) : "—",
            color: sc && sc.expectancy_R >= 0 ? "text-profit" : "text-loss" },
        ].map(c => (
          <div key={c.label} className="bg-surface rounded-xl border border-surface-border p-3 text-center">
            <div className={`text-lg font-bold font-mono ${c.color ?? "text-white"}`}>{c.value}</div>
            <div className="text-[10px] text-slate-500">{c.label}</div>
          </div>
        ))}
      </div>

      <MarketsEditor />

      <AiProvidersCard />

      {/* Decizii */}
      <div className="space-y-2">
        <h3 className="text-sm font-semibold text-white flex items-center gap-2">
          <Bot size={15} className="text-slate-400" /> Decizii recente
          <span className="text-[10px] text-slate-500 font-normal">(click pentru motivație + dezbaterea completă)</span>
        </h3>
        {!decisions || decisions.length === 0 ? (
          <div className="text-xs text-slate-500 bg-surface rounded-xl border border-surface-border p-4">
            Nicio decizie încă. Motorul convoacă consiliul AI doar pe evenimente
            (schimbare de regim, breakout, volatilitate, știri) — nu la fiecare bară.
          </div>
        ) : (
          decisions.map(d => <DecisionRow key={d.id} d={d} />)
        )}
      </div>

      {/* Outcomes */}
      {outcomes && outcomes.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold text-white">Rezultate (outcomes)</h3>
          <div className="bg-surface rounded-xl border border-surface-border overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-[10px] text-slate-500 border-b border-surface-border">
                  <th className="text-left px-3 py-2">Timp</th>
                  <th className="text-left px-3 py-2">Simbol</th>
                  <th className="text-left px-3 py-2">Status</th>
                  <th className="text-right px-3 py-2">R</th>
                  <th className="text-right px-3 py-2">P&L</th>
                </tr>
              </thead>
              <tbody>
                {outcomes.map((o, i) => (
                  <tr key={i} className="border-b border-surface-border/40">
                    <td className="px-3 py-1.5 text-slate-400 font-mono text-[10px]">{o.ts.slice(5, 16)}</td>
                    <td className="px-3 py-1.5 text-white">{o.symbol}</td>
                    <td className="px-3 py-1.5 text-slate-300">{o.status}</td>
                    <td className={`px-3 py-1.5 text-right font-mono ${(o.result_r ?? 0) >= 0 ? "text-profit" : "text-loss"}`}>
                      {fmtR(o.result_r)}
                    </td>
                    <td className={`px-3 py-1.5 text-right font-mono ${(o.pnl_usd ?? 0) >= 0 ? "text-profit" : "text-loss"}`}>
                      {o.pnl_usd != null ? `${o.pnl_usd >= 0 ? "+" : ""}${o.pnl_usd.toFixed(2)}$` : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Logs */}
      <div className="space-y-2">
        <button
          onClick={() => setShowLogs(s => !s)}
          className="text-xs text-slate-400 hover:text-slate-200 flex items-center gap-1.5"
        >
          {showLogs ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
          Log motor (engine.log)
          {showLogs && (
            <RefreshCw size={11} className="ml-1 cursor-pointer hover:text-white"
              onClick={e => { e.stopPropagation(); refetchLogs(); }} />
          )}
        </button>
        {showLogs && (
          <pre className="bg-surface-card border border-surface-border rounded-xl p-3 text-[10px] text-slate-400 font-mono overflow-x-auto max-h-80 overflow-y-auto whitespace-pre-wrap">
            {logs?.lines?.length ? logs.lines.join("\n") : "Log gol sau indisponibil."}
          </pre>
        )}
      </div>
    </div>
  );
}
