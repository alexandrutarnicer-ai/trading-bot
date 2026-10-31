import { useState } from "react";
import { useSignals, useMt5Transactions } from "../api/hooks";
import type { Signal, Mt5Transaction } from "../api/types";

export type FeedView = "trades" | "signals";

interface Props {
  sessionId: string;
  view: FeedView;
  source?: "all" | "bot" | "ai" | "manual";   // filtrul Dashboard (pagina intreaga)
  symbol?: string;                             // simbolul cardului selectat
}

// Starea unui semnal din jurnalul Bot Engine. Doar eticheta — rezultatele
// (R / USD) ale tranzactiilor executate vin exclusiv din MT5 (vederea "Tranzacții").
function signalStatusBadge(status: string | null) {
  switch (status) {
    case null:
    case undefined:
      return <span className="text-[10px] text-slate-600">în așteptare</span>;
    case "ai_reject":
      // Fara procent inline: la o respingere `confidence` e convingerea de NU a
      // consiliului, nu o incredere comparabila cu pragul. Motivul e in Notificari.
      return (
        <span
          className="text-[10px] font-bold text-purple-400"
          title="Respins de Filtrul AI Pre-Trade — vezi cauza și motivul complet în Notificări"
        >
          ⛔ respins AI
        </span>
      );
    case "global_block":
      return (
        <span className="text-[10px] font-bold text-orange-400"
              title="Blocat de Setările Globale (protecție capital / circuit breaker / poziții simultane) — motivul e în Notificări">
          🛡 blocat global
        </span>
      );
    case "expirat":   return <span className="text-[10px] text-slate-500">expirat</span>;
    case "invalidat": return <span className="text-[10px] text-warn">invalidat</span>;
    case "news_cancel": return <span className="text-[10px] text-slate-500">anulat (știre)</span>;
    default:
      // TP / SL / vineri_close / news_close / be_lock* — ordin executat; rezultatul e in MT5
      return (
        <span className="text-[10px] text-blue-400" title="Executat — rezultatul real e în vederea Tranzacții (MT5)">
          executat
        </span>
      );
  }
}

const SOURCE_BADGE: Record<Mt5Transaction["source"], { label: string; cls: string }> = {
  bot:    { label: "BOT", cls: "bg-blue-500/15 text-blue-300" },
  ai:     { label: "AI",  cls: "bg-purple-500/15 text-purple-300" },
  manual: { label: "MAN", cls: "bg-slate-500/20 text-slate-300" },
};

const STRATEGY_LABEL: Record<string, string> = {
  pullback: "pullback", inside_bar: "inside bar", flag: "flag", smart_news: "știre",
};

function mt5StatusBadge(t: Mt5Transaction) {
  const usdStr = ` (${t.pnl_usd >= 0 ? "+" : ""}${t.pnl_usd.toFixed(2)} USD)`;
  const rStr = t.result_r != null ? `${t.result_r >= 0 ? "+" : ""}${t.result_r.toFixed(2)}R ` : "";
  const color = t.status === "TP" ? "text-profit" : t.status === "SL" ? "text-loss" : "text-slate-400";
  return (
    <span className={`text-[10px] font-bold ${color}`}>
      {rStr}{t.status}<span className="font-normal opacity-75">{usdStr}</span>
    </span>
  );
}

function FeedSkeleton() {
  return (
    <div className="space-y-2">
      {[...Array(5)].map((_, i) => (
        <div key={i} className="h-12 rounded-lg bg-surface-border/30 animate-pulse" />
      ))}
    </div>
  );
}

function DirBadge({ dir, label }: { dir: number; label: string }) {
  return (
    <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded flex-shrink-0 ${
      dir === 1 ? "bg-profit/20 text-profit" : "bg-loss/20 text-loss"
    }`}>
      {label}
    </span>
  );
}

function SignalsList({ sessionId }: { sessionId: string }) {
  const { data: signals, isLoading } = useSignals(sessionId);

  if (isLoading) return <FeedSkeleton />;
  if (!signals?.length) {
    return <div className="text-center py-8 text-slate-500 text-sm">Niciun semnal înregistrat</div>;
  }

  return (
    <div className="space-y-1.5 h-full overflow-y-auto pr-1">
      {signals.map((sig: Signal) => {
        const fmt = sig.entry > 100 ? 2 : 5;
        return (
          <div
            key={sig.signal_id}
            className="flex items-center gap-3 px-3 py-2.5 rounded-lg bg-surface-border/20 hover:bg-surface-border/40 transition-colors"
          >
            <DirBadge dir={sig.direction} label={sig.dir_str} />
            <div className="flex-1 min-w-0">
              <div className="flex items-baseline gap-2">
                <span className="text-sm font-semibold text-white">{sig.symbol}</span>
                <span className="text-[10px] text-slate-500">{sig.time.slice(0, 16)}</span>
              </div>
              <div className="text-[10px] text-slate-400 font-mono">
                {sig.entry.toFixed(fmt)} → TP {sig.tp.toFixed(fmt)}
              </div>
            </div>
            <div className="text-right flex-shrink-0">
              <div className="text-xs text-slate-400">{sig.r_ratio}R</div>
              {signalStatusBadge(sig.status)}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function TradesList({ sessionId, source = "all", symbol }: {
  sessionId: string; source?: "all" | "bot" | "ai" | "manual"; symbol?: string;
}) {
  // "all" = tot contul (Bot + AI + manual); o sesiune = doar tranzactiile Bot Engine ale ei
  // Paginare: inainte se afisau DOAR ultimele 50 (fara indiciu) → parea ca lipsesc
  // tranzactii fata de istoricul MT5. Acum: contor „X din total" + „Încarcă mai multe".
  const [limit, setLimit] = useState(50);
  // Pe o piata: „Toate" = tot ce s-a tranzactionat pe simbolul ei (Bot + AI + manual);
  // „Bot" = doar tranzactiile sesiunii Bot Engine; „AI"/„Manual" = acelea, pe simbol.
  const { data, isLoading } = useMt5Transactions(
    sessionId === "all"
      ? { limit, ...(source !== "all" ? { source } : {}) }
      : source === "bot" ? { source: "bot", session_id: sessionId, limit }
      : { limit, symbol, ...(source !== "all" ? { source } : {}) },
  );

  if (isLoading) return <FeedSkeleton />;
  if (data && !data.connected) {
    return (
      <div className="text-[11px] text-warn/80 bg-warn/10 border border-warn/30 rounded-lg px-3 py-2">
        MT5 neconectat — {data.error ?? "tranzacțiile nu sunt disponibile"}.
      </div>
    );
  }

  const items = data?.items ?? [];
  const total = data?.total ?? items.length;
  const header = (
    <div className="flex items-center gap-1.5 text-[10px] text-slate-500 pb-1 flex-wrap">
      <span className="ml-auto">{items.length} din {total} tranzacții MT5</span>
    </div>
  );
  if (!items.length) {
    return <div>{header}<div className="text-center py-8 text-slate-500 text-sm">Nicio tranzacție închisă înregistrată</div></div>;
  }

  return (
    <div className="space-y-1.5 h-full overflow-y-auto pr-1">
      {header}
      {items.map(t => {
        const fmt = t.entry > 100 ? 2 : 5;
        const src = SOURCE_BADGE[t.source] ?? SOURCE_BADGE.manual;
        return (
          <div
            key={t.ticket}
            className="flex items-center gap-3 px-3 py-2.5 rounded-lg bg-surface-border/20 hover:bg-surface-border/40 transition-colors"
          >
            <DirBadge dir={t.direction} label={t.dir_str} />
            <div className="flex-1 min-w-0">
              <div className="flex items-baseline gap-2">
                <span className="text-sm font-semibold text-white">{t.symbol}</span>
                <span className={`text-[9px] font-bold px-1 rounded ${src.cls}`}>{src.label}</span>
                {t.strategy && <span className="text-[9px] text-slate-500">{STRATEGY_LABEL[t.strategy] ?? t.strategy}</span>}
                <span className="text-[10px] text-slate-500">{(t.exit_time ?? t.entry_time ?? "").slice(0, 16)}</span>
              </div>
              <div className="text-[10px] text-slate-400 font-mono">
                {t.entry.toFixed(fmt)} → {t.exit_price != null ? t.exit_price.toFixed(fmt) : "—"}
              </div>
            </div>
            <div className="text-right flex-shrink-0">
              <div className="text-xs text-slate-400">{t.r_ratio != null ? `${t.r_ratio}R` : "—"}</div>
              {mt5StatusBadge(t)}
            </div>
          </div>
        );
      })}
      {items.length < total && (
        <button onClick={() => setLimit(l => l + 100)}
          className="w-full text-[11px] py-1.5 rounded border border-surface-border text-slate-400 hover:text-white">
          Încarcă mai multe ({total - items.length} rămase)
        </button>
      )}
    </div>
  );
}

export function SignalFeed({ sessionId, view, source = "all", symbol }: Props) {
  if (view === "trades") return <TradesList key={source} sessionId={sessionId} source={source} symbol={symbol} />;
  if (source === "ai" || source === "manual") {
    return (
      <div className="text-center py-8 text-slate-500 text-sm">
        Semnalele sunt detectate doar de Bot Engine — alege „Toate” sau „Bot” în filtrul de sursă.
      </div>
    );
  }
  return <SignalsList sessionId={sessionId} />;
}
