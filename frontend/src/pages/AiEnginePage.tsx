import { useState, useEffect } from "react";
import { Bot, Play, Square, Brain, AlertTriangle, ChevronDown, ChevronRight, RefreshCw, Loader2 } from "lucide-react";
import {
  useAiStatus, useAiDecisions, useAiOutcomes, useAiCouncil, useAiConfig,
  useAiLogs, useAiStart, useAiStop, useAiSaveConfig, useAiProviders,
} from "../api/hooks";
import type { AiDecision, MarketOverride } from "../api/types";
import { AiProvidersCard } from "../components/AiProvidersCard";
import { InfoTooltip } from "../components/InfoTooltip";

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
  technical:       "📈 Analist Tehnic",
  macro:           "🌍 Analist Macro/Știri",
  risk:            "🛡 Risk Manager",
  quant:           "🧮 Analist Cantitativ",
  devils_advocate: "😈 Avocatul Diavolului",
  head_trader:     "🎯 Head Trader",
  error:           "⚠ Eroare",
};

// ── Council transcript (expandabil per decizie) ──────────────────────────────

function ConsensusBlock({ consensus, reviewers }: {
  consensus: Record<string, unknown>;
  reviewers: Array<Record<string, unknown>>;
}) {
  const approved = Boolean(consensus.approved);
  const cc = consensus.consensus_confidence as number | null;
  const th = consensus.threshold as number;
  const n = consensus.n_participating as number;
  const veto = consensus.veto_code as string | null;
  return (
    <div className={`rounded-lg border p-2 ${approved ? "border-profit/40 bg-profit/5" : "border-loss/40 bg-loss/5"}`}>
      <div className="text-[11px] font-semibold text-white mb-1">
        🤝 Consens {n} consilii — {approved ? <span className="text-profit">EXECUTĂ</span> : <span className="text-loss">BLOCHEAZĂ</span>}
      </div>
      <div className="text-[10px] text-slate-400">
        {veto
          ? <>Veto absolut: <span className="text-loss font-semibold">{veto}</span></>
          : <>Media încrederilor: <span className="text-slate-200 font-mono">{cc ?? "—"}%</span> {approved ? "≥" : "<"} prag {th}%</>}
      </div>
      {reviewers.length > 0 && (
        <div className="mt-1 space-y-0.5">
          {reviewers.map((r, i) => (
            <div key={i} className="text-[10px] text-slate-500 flex items-center gap-1.5 flex-wrap">
              <span className="font-mono text-slate-300">{String(r.source)}</span>
              {r.error
                ? <span className="text-amber-400">indisponibil</span>
                : <>
                    <span className={r.approved ? "text-profit" : "text-loss"}>{r.approved ? "aprobă" : "respinge"}</span>
                    <span className="font-mono">{r.confidence != null ? `${r.confidence}%` : "—"}</span>
                    {r.veto_code ? <span className="text-loss">veto {String(r.veto_code)}</span> : null}
                  </>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function CouncilView({ decisionId }: { decisionId: number }) {
  const { data, isLoading } = useAiCouncil(decisionId);
  if (isLoading) return <div className="text-xs text-slate-500 p-2">Se încarcă dezbaterea...</div>;
  if (!data) return <div className="text-xs text-slate-500 p-2">Transcript indisponibil.</div>;
  const consensus = (data.transcript as Record<string, unknown>)._consensus as Record<string, unknown> | undefined;
  const reviewers = ((data.transcript as Record<string, unknown>)._reviewers as Array<Record<string, unknown>>) ?? [];
  return (
    <div className="space-y-2 p-3 bg-surface/60 rounded-lg border border-surface-border/40">
      <div className="text-[10px] text-slate-500">
        Convocat de: <span className="text-slate-300">{data.trigger}</span> · durată {data.duration_s}s
      </div>
      {consensus && <ConsensusBlock consensus={consensus} reviewers={reviewers} />}
      {Object.entries(data.transcript)
        .filter(([role]) => !role.startsWith("_"))
        .map(([role, view]) => (
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

// ── Consens multi-council + roluri (motorul autonom) ────────────────────────

function ConsensusConfig() {
  const { data: cfg } = useAiConfig();
  const { data: providers } = useAiProviders();
  const save = useAiSaveConfig();
  if (!cfg) return null;

  const enabled = Object.entries(providers?.providers ?? {})
    .filter(([, p]) => p.enabled).map(([n]) => n);
  const primary   = (cfg.council_primary_source as string | null) ?? null;
  const secondary = (cfg.council_secondary_source as string | null) ?? null;
  const tertiary  = (cfg.council_tertiary_source as string | null) ?? null;
  const threshold = (cfg.consensus_threshold as number) ?? 70;
  const chosen = [primary, secondary, tertiary].filter(Boolean) as string[];
  const optionsFor = (cur: string | null) => enabled.filter(s => s === cur || !chosen.includes(s));
  const nCouncils = 1 + (secondary ? 1 : 0) + (tertiary ? 1 : 0);
  const multiAvailable = enabled.length >= 2;

  const put = (patch: Record<string, unknown>) => save.mutate(patch as never);

  const Slot = ({ label, value, options, onChange, disabled, defaultLabel }: {
    label: string; value: string | null; options: string[];
    onChange: (v: string | null) => void; disabled?: boolean; defaultLabel?: string;
  }) => (
    <div className="flex items-center gap-2 text-[11px]">
      <span className="text-slate-400 w-28 shrink-0">{label}</span>
      <select disabled={disabled} value={value ?? ""}
        onChange={e => onChange(e.target.value || null)}
        className="bg-surface-card border border-surface-border rounded px-2 py-0.5 text-[11px] text-white disabled:opacity-40">
        <option value="">{defaultLabel ?? "— dezactivat —"}</option>
        {options.map(s => <option key={s} value={s}>{s}</option>)}
      </select>
    </div>
  );

  return (
    <div className="bg-surface rounded-xl border border-surface-border p-4 space-y-3">
      <h3 className="text-sm font-semibold text-white flex items-center gap-2">
        Consiliu multiplu + roluri (consens)
        <span className="text-[10px] text-slate-500 font-normal">se aplică la următorul consiliu</span>
      </h3>

      {/* Consiliu multiplu */}
      <div className="space-y-1.5">
        <div className="text-[11px] font-semibold text-slate-300">Consilii pe surse distincte</div>
        {!multiAvailable ? (
          <p className="text-[10px] text-slate-600">
            Necesită cel puțin 2 surse AI active (cardul Surse AI de mai sus). Active: {enabled.length}.
          </p>
        ) : (
          <>
            <Slot label="Consiliu 1 (primar)" value={primary} options={optionsFor(primary)}
              defaultLabel="distribuit pe roluri"
              onChange={v => put({ council_primary_source: v })} />
            <Slot label="Consiliu 2" value={secondary} options={optionsFor(secondary)}
              onChange={v => put({ council_secondary_source: v,
                ...(v ? {} : { council_tertiary_source: null }) })} />
            <Slot label="Consiliu 3" value={tertiary} options={optionsFor(tertiary)} disabled={!secondary}
              onChange={v => put({ council_tertiary_source: v })} />
          </>
        )}
      </div>

      {/* Pragul de consens */}
      <div className="flex items-center gap-3">
        <span className="text-[11px] text-slate-400 w-28 shrink-0">Prag consens</span>
        <input type="range" min={50} max={90} step={1} value={threshold}
          onChange={e => put({ consensus_threshold: Number(e.target.value) })}
          className="flex-1 accent-purple-500" />
        <span className="text-[11px] font-mono text-white w-10 text-right">{threshold}%</span>
      </div>
      <p className="text-[10px] text-slate-600">
        {nCouncils > 1
          ? `Consiliul primar propune trade-ul; ${nCouncils - 1} consiliu/consilii îl revizuiesc. Media încrederilor ≥ prag → execută; un veto valid blochează. Revizori indisponibili → decide primarul.`
          : "Un singur consiliu (implicit). Adaugă Consiliu 2/3 pentru confirmare prin consens."}
      </p>

      {/* Roluri optionale */}
      <div className="border-t border-surface-border/50 pt-2 space-y-1.5">
        <div className="text-[11px] font-semibold text-slate-300">Roluri suplimentare (toate consiliile)</div>
        <label className="flex items-center gap-2 text-[11px] text-slate-300 cursor-pointer">
          <input type="checkbox" checked={Boolean(cfg.role_quant_enabled)}
            onChange={e => put({ role_quant_enabled: e.target.checked })} className="accent-purple-500" />
          🧮 Analist Cantitativ (EV / probabilitate de câștig)
        </label>
        <label className="flex items-center gap-2 text-[11px] text-slate-300 cursor-pointer">
          <input type="checkbox" checked={Boolean(cfg.role_devils_advocate_enabled)}
            onChange={e => put({ role_devils_advocate_enabled: e.target.checked })} className="accent-purple-500" />
          😈 Avocatul Diavolului (pre-mortem, contra-teză)
        </label>
      </div>

      {save.isError && <div className="text-[10px] text-loss">{(save.error as Error).message}</div>}
    </div>
  );
}

// ── Limite per piata (market_overrides) ─────────────────────────────────────

function num(v: string): number | null {
  const n = parseFloat(v);
  return Number.isFinite(n) ? n : null;
}

// Tooltips (i) per coloana — explicatii scurte, in clar
const LIMIT_TIPS = {
  capital: [
    "Fracția din equity folosită ca bază de sizing pe această piață.",
    "Gol = 100% din cont (comportamentul de până acum).",
    "Ex: 50% la un cont de 2000$ → riscul se calculează din 1000$.",
    "Notă: la cont mic (~sub 1500$), lotul minim al brokerului domină — vezi Ghid.",
  ].join("\n"),
  risk: [
    "Cap de risc per tranzacție pe această piață (%).",
    "Gol = riscul decis de consiliu, cu limitele globale (default 0.5%, max 1%).",
    "Consiliul poate cere mai puțin, niciodată mai mult decât acest cap.",
    "La contul actual, ACEASTA e pârghia reală pentru poziții mai mari.",
  ].join("\n"),
  maxRr: [
    "Plafon Reward:Risk pe această piață.",
    "Un TP propus peste plafon e ADUS la plafon (SL și direcția rămân ale consiliului).",
    "Consiliul primește banda permisă (min–max) în briefing și proiectează în interiorul ei.",
    "Gol = fără plafon (comportamentul de până acum).",
  ].join("\n"),
  dailyStop: [
    "Stop zilnic de pierdere DOAR pe această piață (în R).",
    "Ex: 1.5 → după -1.5R realizat azi pe această piață, nu se mai deschide nimic azi pe ea.",
    "Separat de stopul global de -3R/zi (care rămâne activ pe tot motorul).",
    "Gol = doar stopul global.",
  ].join("\n"),
  maxTrades: [
    "Anti-overtrading: câte ordine pot fi PLASATE pe zi pe această piață.",
    "Ex: 2 → al treilea ordin din aceeași zi e respins automat.",
    "Gol = fără limită per piață (limitele globale de expunere rămân).",
  ].join("\n"),
  isolated: [
    "«Izolat» = piață în OBSERVAȚIE / test.",
    "Deciziile și rezultatele ei se salvează normal, dar SEPARAT:",
    "• NU intră în scorecard-ul principal (Decizii / Total R / Expectancy de sus)",
    "• rămân vizibile pe rândul piaței (t = trades, R = rezultat) și în status per piață",
    "Folosește-l când testezi o piață nouă și nu vrei să-ți murdărească statistica",
    "principală. Scoate bifa când piața «promovează» — de atunci rezultatele ei noi",
    "și istorice intră înapoi în scorecard-ul principal.",
  ].join("\n"),
};

function MarketLimitsRow({ symbol, ov, stats, orphan, effRiskPct, onSave, saving }: {
  symbol: string;
  ov: MarketOverride;
  stats?: { closed_trades: number; total_R: number } | null;
  orphan?: boolean;                       // are config dar nu mai e in lista de piete
  effRiskPct: string;                     // valoarea globala curenta (placeholder)
  onSave: (symbol: string, ov: MarketOverride | null, onDone: () => void) => void;
  saving: boolean;
}) {
  const [draft, setDraft] = useState<MarketOverride>(ov);
  const [dirty, setDirty] = useState(false);
  useEffect(() => { setDraft(ov); setDirty(false); }, [JSON.stringify(ov)]);  // eslint-disable-line react-hooks/exhaustive-deps

  const upd = (patch: Partial<MarketOverride>) => { setDraft(d => ({ ...d, ...patch })); setDirty(true); };
  const reset = () => { setDraft(ov); setDirty(false); };
  const inputCls = "w-14 bg-surface-card border border-surface-border rounded px-1 py-0.5 text-[11px] text-white font-mono placeholder:text-slate-600";

  return (
    <tr className={`border-b border-surface-border/40 ${orphan ? "opacity-60" : ""}`}>
      <td className="px-2 py-1.5">
        <span className="text-xs font-semibold text-white">{symbol}</span>
        {(draft.isolated ?? false) && <span className="ml-1.5 text-[9px] px-1 py-0.5 rounded bg-amber-500/20 text-amber-300">IZOLAT</span>}
        {orphan && <span className="ml-1.5 text-[9px] px-1 py-0.5 rounded bg-slate-600/40 text-slate-400" title="Piața nu mai e în lista urmărită — config-ul și izolarea ei rămân active până le ștergi">NEURMĂRIT</span>}
        {stats && stats.closed_trades > 0 && (
          <div className={`text-[9px] font-mono ${stats.total_R >= 0 ? "text-profit" : "text-loss"}`}>
            {stats.closed_trades}t · {stats.total_R >= 0 ? "+" : ""}{stats.total_R}R
          </div>
        )}
      </td>
      <td className="px-1 py-1.5">
        <input className={inputCls} type="number" min={5} max={100} step={5}
          placeholder="100"
          value={draft.capital_fraction != null ? Math.round(draft.capital_fraction * 100) : ""}
          onChange={e => upd({ capital_fraction: e.target.value === "" ? null : (num(e.target.value) ?? 100) / 100 })} />
      </td>
      <td className="px-1 py-1.5">
        <input className={inputCls} type="number" min={0.05} max={2} step={0.05}
          placeholder={effRiskPct}
          value={draft.risk_pct != null ? +(draft.risk_pct * 100).toFixed(2) : ""}
          onChange={e => upd({ risk_pct: e.target.value === "" ? null : (num(e.target.value) ?? 0.5) / 100 })} />
      </td>
      <td className="px-1 py-1.5">
        <input className={inputCls} type="number" min={1} max={10} step={0.5}
          placeholder="∞"
          value={draft.max_rr ?? ""}
          onChange={e => upd({ max_rr: e.target.value === "" ? null : num(e.target.value) })} />
      </td>
      <td className="px-1 py-1.5">
        <input className={inputCls} type="number" min={0.25} max={10} step={0.25}
          placeholder="global"
          value={draft.max_daily_loss_R ?? ""}
          onChange={e => upd({ max_daily_loss_R: e.target.value === "" ? null : num(e.target.value) })} />
      </td>
      <td className="px-1 py-1.5">
        <input className={inputCls} type="number" min={1} max={20} step={1}
          placeholder="∞"
          value={draft.max_trades_per_day ?? ""}
          onChange={e => upd({ max_trades_per_day: e.target.value === "" ? null : Math.round(num(e.target.value) ?? 1) })} />
      </td>
      <td className="px-1 py-1.5 text-center">
        <input type="checkbox" className="accent-amber-500"
          checked={draft.isolated ?? false}
          onChange={e => upd({ isolated: e.target.checked })} />
      </td>
      <td className="px-1 py-1.5 whitespace-nowrap">
        {dirty && (
          <>
            <button onClick={() => onSave(symbol, draft, () => setDirty(false))} disabled={saving}
              className="text-[10px] px-2 py-0.5 rounded bg-profit/20 text-profit hover:bg-profit/30 disabled:opacity-40">
              {saving ? "..." : "Salvează"}
            </button>
            <button onClick={reset} disabled={saving} title="Renunță la modificări (revine la valorile salvate)"
              className="ml-1 text-[10px] px-2 py-0.5 rounded bg-slate-700/50 text-slate-300 hover:bg-slate-700 disabled:opacity-40">
              ↺ Anulează
            </button>
          </>
        )}
        {!dirty && orphan && (
          <button onClick={() => onSave(symbol, null, () => {})} disabled={saving}
            title="Șterge config-ul rămas pentru această piață neurmărită"
            className="text-[10px] px-2 py-0.5 rounded bg-loss/20 text-loss hover:bg-loss/30 disabled:opacity-40">
            Șterge config
          </button>
        )}
      </td>
    </tr>
  );
}

function MarketLimitsCard() {
  const { data: cfg } = useAiConfig();
  const { data: st } = useAiStatus();
  const save = useAiSaveConfig();
  if (!cfg) return null;
  const overrides = (cfg.market_overrides ?? {}) as Record<string, MarketOverride>;
  const bySym = st?.scorecard_by_symbol ?? {};
  const markets = cfg.markets ?? [];
  // Piete cu config salvat dar scoase din lista urmarita — afisate ca sa nu
  // "dispara" pe tacute (izolarea lor ramane activa pana stergi config-ul).
  const orphans = Object.keys(overrides).filter(s => !markets.includes(s));
  const effRiskPct = `${(((cfg.risk_pct_default as number) ?? 0.005) * 100).toFixed(2)}`;

  // ov=null → sterge complet config-ul simbolului (butonul "Șterge config")
  const saveRow = (symbol: string, ov: MarketOverride | null, onDone: () => void) => {
    const next = { ...overrides };
    if (ov === null) {
      delete next[symbol];
    } else {
      const clean: MarketOverride = {};
      if (ov.capital_fraction != null && ov.capital_fraction !== 1.0) clean.capital_fraction = ov.capital_fraction;
      if (ov.risk_pct != null) clean.risk_pct = ov.risk_pct;
      if (ov.max_rr != null) clean.max_rr = ov.max_rr;
      if (ov.max_daily_loss_R != null) clean.max_daily_loss_R = ov.max_daily_loss_R;
      if (ov.max_trades_per_day != null) clean.max_trades_per_day = ov.max_trades_per_day;
      if (ov.isolated) clean.isolated = true;
      if (Object.keys(clean).length) next[symbol] = clean;
      else delete next[symbol];
    }
    // dirty se sterge DOAR la succes — daca salvarea esueaza, ramai in editare
    save.mutate({ market_overrides: next } as never, { onSuccess: onDone });
  };

  // Tooltip-ul se randeaza SUB header (position="below"): containerul are
  // overflow-x-auto → overflow-y devine auto (CSS) → ce e DEASUPRA header-ului e
  // taiat. Sub header cade in zona rindurilor, vizibila. `align="right"` pe
  // coloanele din dreapta ca sa nu iasa din marginea dreapta.
  const Th = ({ label, tip, align }: {
    label: string; tip?: string; align?: "center" | "right";
  }) => (
    <th className="px-1 py-1 whitespace-nowrap">
      {label}{tip && <> <InfoTooltip text={tip} wide position="below" align={align ?? "center"} /></>}
    </th>
  );

  return (
    <div className="bg-surface rounded-xl border border-surface-border p-4 space-y-2">
      <h3 className="text-sm font-semibold text-white flex items-center gap-2">
        Limite per piață
        <span className="text-[10px] text-slate-500 font-normal">
          câmp gol = valoarea globală curentă (afișată estompat) · se aplică la următorul consiliu, fără restart
        </span>
      </h3>
      <div className="overflow-x-auto">
        <table className="w-full text-left">
          <thead>
            <tr className="text-[9px] text-slate-500 uppercase">
              <th className="px-2 py-1">Piață</th>
              <Th label="Capital %" tip={LIMIT_TIPS.capital} />
              <Th label="Risc %/trade" tip={LIMIT_TIPS.risk} />
              <Th label="Max R:R" tip={LIMIT_TIPS.maxRr} />
              <Th label="Stop zi (R)" tip={LIMIT_TIPS.dailyStop} align="right" />
              <Th label="Max ord/zi" tip={LIMIT_TIPS.maxTrades} align="right" />
              <Th label="Izolat" tip={LIMIT_TIPS.isolated} align="right" />
              <th className="px-1 py-1"></th>
            </tr>
          </thead>
          <tbody>
            {markets.map(sym => (
              <MarketLimitsRow key={sym} symbol={sym}
                ov={overrides[sym] ?? {}}
                stats={bySym[sym] ? { closed_trades: bySym[sym].closed_trades, total_R: bySym[sym].total_R } : null}
                effRiskPct={effRiskPct}
                onSave={saveRow} saving={save.isPending} />
            ))}
            {orphans.map(sym => (
              <MarketLimitsRow key={sym} symbol={sym} orphan
                ov={overrides[sym] ?? {}}
                stats={bySym[sym] ? { closed_trades: bySym[sym].closed_trades, total_R: bySym[sym].total_R } : null}
                effRiskPct={effRiskPct}
                onSave={saveRow} saving={save.isPending} />
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-[10px] text-slate-600">
        O piață NOUĂ adăugată la „Piețe urmărite" pornește cu toate câmpurile goale = valorile globale (nimic de
        configurat obligatoriu). O piață scoasă din listă își păstrează config-ul (rând „NEURMĂRIT") — inclusiv
        izolarea — până apeși „Șterge config". Consiliul primește limitele configurate în briefing și proiectează
        trade-ul în interiorul lor; codul le aplică oricum ca rails hard.
      </p>
      {save.isError && <div className="text-[10px] text-loss">{(save.error as Error).message}</div>}
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

      <MarketLimitsCard />

      <AiProvidersCard />

      <ConsensusConfig />

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
