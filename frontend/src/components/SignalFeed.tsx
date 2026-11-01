import { useState } from "react";
import { useDashboardSignals, useMt5Transactions } from "../api/hooks";
import type { Mt5Transaction, SourceFilter, GlobalSignal } from "../api/types";
import { ENGINE_COLOR } from "./MarketCard";

export type FeedView = "trades" | "signals";

interface Props {
  view: FeedView;
  source?: SourceFilter;   // filtrul Dashboard (pagina intreaga)
  symbol?: string;         // piata selectata (card) — undefined = toate pietele
}

// filtrul de sursa al paginii → engine-ul semnalelor (manual nu are semnale)
const SOURCE_ENGINE: Record<SourceFilter, string | null> = {
  all: null, bot: "custom", ai: "ai", daily: "daily", noisy: "noisy", manual: null,
};

const SOURCE_BADGE: Record<Mt5Transaction["source"], { label: string; cls: string }> = {
  bot:    { label: "CUSTOM", cls: "bg-emerald-500/15 text-emerald-300" },
  ai:     { label: "AI",  cls: "bg-purple-500/15 text-purple-300" },
  daily:  { label: "DAILY", cls: "bg-cyan-500/15 text-cyan-300" },
  noisy:  { label: "NOISY", cls: "bg-amber-500/15 text-amber-300" },
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

const SIGNAL_STATUS_CLS: Record<GlobalSignal["status"], string> = {
  executed: "text-blue-400", rejected: "text-purple-400 font-bold", expired: "text-slate-500",
  pending: "text-slate-400", observe: "text-sky-300/80", virtual: "text-amber-300/80", other: "text-slate-400",
};

function SignalsList({ source, symbol }: { source: SourceFilter; symbol?: string }) {
  const [limit, setLimit] = useState(100);
  const { data: signals, isLoading } = useDashboardSignals(symbol, SOURCE_ENGINE[source] ?? undefined, limit);

  if (source === "manual") {
    return <div className="text-center py-8 text-slate-500 text-sm">Tranzacțiile manuale nu au semnale.</div>;
  }
  if (isLoading) return <FeedSkeleton />;
  if (!signals?.length) {
    return <div className="text-center py-8 text-slate-500 text-sm">Niciun semnal înregistrat{symbol ? ` pe ${symbol}` : ""}</div>;
  }

  return (
    <div className="space-y-1.5 h-full overflow-y-auto pr-1">
      <div className="text-[10px] text-slate-500 pb-1 text-right">
        {signals.length} semnale — Custom (setup-uri), AI (decizii OPEN / CLOSE), Daily / Noisy (trade-uri, virtuale în shadow)
      </div>
      {signals.map(sig => {
        const c = ENGINE_COLOR[sig.engine];
        const dir = sig.direction === "LONG" ? 1 : sig.direction === "SHORT" ? -1 : 0;
        return (
          <div key={`${sig.engine}-${sig.id}`} title={sig.detail}
            className="flex items-center gap-3 px-3 py-2.5 rounded-lg bg-surface-border/20 hover:bg-surface-border/40 transition-colors">
            {dir !== 0 ? <DirBadge dir={dir} label={sig.direction} />
              : <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-slate-500/20 text-slate-300">{sig.direction || "—"}</span>}
            <div className="flex-1 min-w-0">
              <div className="flex items-baseline gap-2">
                <span className="text-sm font-semibold text-white">{sig.symbol}</span>
                <span className={`text-[9px] font-bold px-1 rounded border ${c.badge}`}>
                  {c.label}{sig.engine === "custom" ? ` ${sig.ref}` : ""}
                </span>
                <span className="text-[10px] text-slate-500">{sig.time.slice(0, 16)}</span>
              </div>
              <div className="text-[10px] text-slate-400 truncate">{sig.strategy}</div>
            </div>
            <div className={`text-[10px] text-right flex-shrink-0 max-w-[45%] ${SIGNAL_STATUS_CLS[sig.status]}`}>
              {sig.status_label}
            </div>
          </div>
        );
      })}
      {signals.length >= limit && (
        <button onClick={() => setLimit(l => l + 100)}
          className="w-full text-[11px] py-1.5 rounded border border-surface-border text-slate-400 hover:text-white">
          Încarcă mai multe
        </button>
      )}
    </div>
  );
}

function TradesList({ source = "all", symbol }: { source?: SourceFilter; symbol?: string }) {
  // Tranzactiile inchise din MT5, toate engine-urile (badge CUSTOM / AI / DAILY / NOISY / MAN).
  // Piata selectata = tot ce s-a tranzactionat pe simbol, de oricare engine (filtrul de sursa ramane).
  // Paginare: contor „X din total" + „Încarcă mai multe" (nu se ascunde nimic).
  const [limit, setLimit] = useState(50);
  const { data, isLoading } = useMt5Transactions({
    limit, ...(symbol ? { symbol } : {}), ...(source !== "all" ? { source } : {}),
  });

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
    return (
      <div>{header}
        <div className="text-center py-8 text-slate-500 text-sm">
          {source === "daily"
            ? "Nicio tranzacție reală Daily Engine (magic 880001). În mod Shadow nu plasează ordine — trade-urile virtuale sunt în tab-ul Daily Engine."
            : "Nicio tranzacție închisă înregistrată"}
        </div>
      </div>
    );
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

export function SignalFeed({ view, source = "all", symbol }: Props) {
  if (view === "trades") return <TradesList key={`${source}-${symbol ?? ""}`} source={source} symbol={symbol} />;
  return <SignalsList key={`${source}-${symbol ?? ""}`} source={source} symbol={symbol} />;
}
