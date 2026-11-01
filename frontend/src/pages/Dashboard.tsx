import { useState, useEffect } from "react";
import { RefreshCw, TrendingUp, TrendingDown, Minus } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useBotStatus, useMt5Status, useMt5WeeklyStats, useDashboardMarkets } from "../api/hooks";
import type { Mt5PeriodStats, SourceFilter, MarketCardData, MarketEngineId } from "../api/types";
import { MarketCard, ENGINE_COLOR } from "../components/MarketCard";
import { SignalFeed, type FeedView } from "../components/SignalFeed";
import { EquityChart } from "../components/EquityChart";
import { TradingStatsPanel } from "../components/TradingStatsPanel";
import { TopMarketsWidget } from "../components/TopMarketsWidget";
import { EnginePerformanceCards, EnginePerformanceSection } from "../components/EnginePerformance";
import { EngineControlCards } from "../components/EngineControlCards";
import { TradingPace } from "../components/TradingPace";
import { ActiveOrdersTable } from "../components/ActiveOrdersTable";

// Vedere pentru randare — R e recalculat din SL-ul original al ordinelor
// (vezi api/mt5_pool.py), null doar daca nicio pozitie din perioada nu are SL rezolvabil.
interface ViewPeriod {
  start: string; end: string;
  trades: number; wins: number; losses: number; win_rate: number;
  pnl_usd: number | null;
  ddValue: number | null; ddUnit: "R" | "USD";
  totalR: number | null;
  costs: number | null;   // comisioane + swap ale perioadei (null = fara date)
}
const _costs = (comm?: number, swap?: number): number | null =>
  comm == null && swap == null ? null : Math.round(((comm ?? 0) + (swap ?? 0)) * 100) / 100;
const toViewMt5 = (p: Mt5PeriodStats): ViewPeriod => ({
  start: p.start, end: p.end, trades: p.trades, wins: p.wins, losses: p.losses,
  win_rate: p.win_rate, pnl_usd: p.pnl_usd,
  ddValue: p.total_r != null ? p.max_dd_r : p.max_dd_usd,
  ddUnit: p.total_r != null ? "R" : "USD",
  totalR: p.total_r,
  costs: _costs(p.commission_usd, p.swap_usd),
});

function WeeklyStatsPanel({ source }: { source: string }) {
  const { data: mt5Data, isLoading } = useMt5WeeklyStats(source);
  const [period, setPeriod] = useState<"week" | "month">("week");

  function Trend({ curr, pre }: { curr: number; pre: number }) {
    if (pre === 0 && curr === 0) return <Minus size={11} className="text-slate-600" />;
    if (curr > pre) return <TrendingUp  size={11} className="text-profit" />;
    if (curr < pre) return <TrendingDown size={11} className="text-loss" />;
    return <Minus size={11} className="text-slate-600" />;
  }

  const rColor  = (r: number) => r > 0 ? "text-profit" : r < 0 ? "text-loss" : "text-slate-400";
  const fmtR    = (r: number) => `${r >= 0 ? "+" : ""}${r.toFixed(3)}R`;
  const fmtUsd  = (v: number | null | undefined) =>
    v == null ? null : `${v >= 0 ? "+" : ""}${v.toLocaleString("ro-RO", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} USD`;
  const fmtDd   = (v: number | null, unit: "R" | "USD") =>
    !v ? "—" : unit === "R" ? `${v.toFixed(1)}R` : fmtUsd(v);

  if (isLoading) {
    return <div className="h-24 rounded-xl bg-surface-card animate-pulse" />;
  }

  if (!mt5Data?.connected) {
    return (
      <div className="text-[11px] text-warn/80 bg-warn/10 border border-warn/30 rounded-lg px-3 py-2">
        MT5 neconectat — {mt5Data?.error ?? "indicele nu este disponibil"}.
      </div>
    );
  }

  const cur: ViewPeriod  = toViewMt5(period === "week" ? mt5Data.current_week  : mt5Data.current_month);
  const prev: ViewPeriod = toViewMt5(period === "week" ? mt5Data.previous_week : mt5Data.previous_month);

  const curLabel  = period === "week" ? "Săpt. curentă"   : "Luna curentă";
  const prevLabel = period === "week" ? "Săpt. anterioară" : "Luna anterioară";

  return (
    <div className="space-y-2">
      {/* Tab switcher */}
      <div className="flex gap-1 mb-1">
        {(["week", "month"] as const).map(p => (
          <button
            key={p}
            onClick={() => setPeriod(p)}
            className={`text-[10px] px-2.5 py-1 rounded-lg transition-colors ${
              period === p
                ? "bg-blue-500/20 text-blue-400 font-semibold"
                : "text-slate-500 hover:text-slate-300"
            }`}
          >
            {p === "week" ? "Săptămână" : "Lună"}
          </button>
        ))}
      </div>

      {/* Header row */}
      <div className="grid grid-cols-3 text-[10px] text-slate-500 uppercase tracking-wider pb-1">
        <div />
        <div className="text-center">{curLabel}</div>
        <div className="text-center">{prevLabel}</div>
      </div>

      {/* Trades */}
      <div className="grid grid-cols-3 items-center">
        <div className="text-[11px] text-slate-400">Trades</div>
        <div className="text-center flex items-center justify-center gap-1">
          <span className="text-xs font-semibold text-white">{cur.trades}</span>
          <Trend curr={cur.trades} pre={prev.trades} />
        </div>
        <div className="text-center text-[11px] text-slate-500">{prev.trades}</div>
      </div>

      {/* Wins / Losses */}
      <div className="grid grid-cols-3 items-center">
        <div className="text-[11px] text-slate-400">Câștiguri</div>
        <div className="text-center flex items-center justify-center gap-1">
          <span className="text-xs font-semibold text-profit">{cur.wins}</span>
          <Trend curr={cur.wins} pre={prev.wins} />
        </div>
        <div className="text-center text-[11px] text-slate-500">{prev.wins}</div>
      </div>

      <div className="grid grid-cols-3 items-center">
        <div className="text-[11px] text-slate-400">Pierderi</div>
        <div className="text-center flex items-center justify-center gap-1">
          <span className="text-xs font-semibold text-loss">{cur.losses}</span>
          <Trend curr={prev.losses} pre={cur.losses} />
        </div>
        <div className="text-center text-[11px] text-slate-500">{prev.losses}</div>
      </div>

      {/* Win rate */}
      <div className="grid grid-cols-3 items-center">
        <div className="text-[11px] text-slate-400">Win Rate</div>
        <div className="text-center flex items-center justify-center gap-1">
          <span className="text-xs font-semibold text-white">{cur.win_rate.toFixed(1)}%</span>
          <Trend curr={cur.win_rate} pre={prev.win_rate} />
        </div>
        <div className="text-center text-[11px] text-slate-500">{prev.win_rate.toFixed(1)}%</div>
      </div>

      {/* Total R (null cand nicio pozitie nu are SL rezolvabil) */}
      {cur.totalR != null && (
        <div className="grid grid-cols-3 items-center border-t border-surface-border/40 pt-2">
          <div className="text-[11px] text-slate-400">Total R</div>
          <div className="text-center flex items-center justify-center gap-1">
            <span className={`text-xs font-mono font-semibold ${rColor(cur.totalR)}`}>
              {fmtR(cur.totalR)}
            </span>
            <Trend curr={cur.totalR} pre={prev.totalR ?? 0} />
          </div>
          <div className={`text-center text-[11px] font-mono ${rColor(prev.totalR ?? 0)}`}>
            {fmtR(prev.totalR ?? 0)}
          </div>
        </div>
      )}

      {/* P&L USD (doar daca exista date reale) */}
      {(cur.pnl_usd != null || prev.pnl_usd != null) && (
        <div className={`grid grid-cols-3 items-center ${cur.totalR == null ? "border-t border-surface-border/40 pt-2" : ""}`}>
          <div className="text-[11px] text-slate-400">P&L USD</div>
          <div className="text-center flex items-center justify-center gap-1">
            {cur.pnl_usd != null
              ? <span className={`text-xs font-mono font-semibold ${rColor(cur.pnl_usd)}`}>{fmtUsd(cur.pnl_usd)}</span>
              : <span className="text-xs font-mono text-slate-600">—</span>
            }
            {cur.pnl_usd != null && prev.pnl_usd != null && <Trend curr={cur.pnl_usd} pre={prev.pnl_usd} />}
          </div>
          <div className={`text-center text-[11px] font-mono ${prev.pnl_usd != null ? rColor(prev.pnl_usd) : "text-slate-600"}`}>
            {fmtUsd(prev.pnl_usd) ?? "—"}
          </div>
        </div>
      )}

      {/* Comisioane + swap ale perioadei (doar daca exista date reale) */}
      {(cur.costs != null || prev.costs != null) && (
        <div className="grid grid-cols-3 items-center">
          <div className="text-[11px] text-slate-400 flex items-center gap-1">
            Costuri broker
            <span
              className="text-[10px] text-slate-600 cursor-help"
              title="Comision + swap ale pozițiilor închise în perioadă, din MT5 (aceeași sursă ca filtrul paginii). Spread-ul e deja în P&L."
            >ⓘ</span>
          </div>
          <div className="text-center">
            {cur.costs != null
              ? <span className={`text-xs font-mono font-semibold ${rColor(cur.costs)}`}>{fmtUsd(cur.costs)}</span>
              : <span className="text-xs font-mono text-slate-600">—</span>}
          </div>
          <div className={`text-center text-[11px] font-mono ${prev.costs != null ? rColor(prev.costs) : "text-slate-600"}`}>
            {fmtUsd(prev.costs) ?? "—"}
          </div>
        </div>
      )}

      {/* -DD max (R cand e rezolvabil, altfel USD) */}
      <div className="grid grid-cols-3 items-center">
        <div className="text-[11px] text-slate-400">-DD max</div>
        <div className="text-center flex items-center justify-center gap-1">
          <span className={`text-xs font-mono font-semibold ${(cur.ddValue ?? 0) < 0 ? "text-loss" : "text-slate-500"}`}>
            {fmtDd(cur.ddValue, cur.ddUnit)}
          </span>
          <Trend curr={-(cur.ddValue ?? 0)} pre={-(prev.ddValue ?? 0)} />
        </div>
        <div className={`text-center text-[11px] font-mono ${(prev.ddValue ?? 0) < 0 ? "text-loss/60" : "text-slate-600"}`}>
          {fmtDd(prev.ddValue, prev.ddUnit)}
        </div>
      </div>

      <div className="text-[10px] text-slate-600 pt-0.5">
        {cur.start} → {cur.end} · anterior: {prev.start} → {prev.end}
      </div>
    </div>
  );
}

export function Dashboard() {
  // Piete active pe TOATE engine-urile (Custom / AI / Daily / Noisy) — S1/S2 raman in Custom Engine
  const { data: marketsData, isLoading, dataUpdatedAt } = useDashboardMarkets();
  const { data: botStatus } = useBotStatus();
  const { data: mt5 } = useMt5Status();
  // Filtrul de SURSA la nivel de pagina (default Toate): cardurile, statisticile,
  // indicele saptamanal, Top 5, graficul si lista de tranzactii folosesc aceeasi sursa.
  const [source, setSource] = useState<SourceFilter>("all");
  const [selectedMarket, setSelectedMarket] = useState<string | null>(null);
  const [hideStopped, setHideStopped] = useState(false);
  const [now, setNow] = useState(Date.now());
  const [feedView, setFeedView] = useState<FeedView>("trades");
  const qc = useQueryClient();

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 5_000);
    return () => clearInterval(id);
  }, []);

  const secsAgo = dataUpdatedAt ? Math.floor((now - dataUpdatedAt) / 1000) : null;
  const updateLabel = secsAgo === null ? null
    : secsAgo < 5  ? "acum"
    : secsAgo < 60 ? `${secsAgo}s`
    : `${Math.floor(secsAgo / 60)}m`;

  // Filtrul de sursa al paginii se aplica si cardurilor: pe un engine → doar pietele lui,
  // cu statisticile MT5 ale acelui engine pe piata (aceleasi definitii).
  const srcEngine: MarketEngineId | null =
    source === "bot" ? "custom" : source === "ai" || source === "daily" || source === "noisy" ? source : null;
  const markets: MarketCardData[] = (marketsData?.markets ?? [])
    .filter(m => !srcEngine || m.engine_ids.includes(srcEngine))
    .filter(m => !hideStopped || m.status !== "stopped")
    .map(m => srcEngine ? { ...m, stats: m.stats_by_engine?.[srcEngine] ?? null,
                            engines: m.engines.filter(e => e.engine === srcEngine) } : m);
  const counts = marketsData?.counts;
  const histOnly = marketsData?.history_only ?? [];

  function refresh() {
    qc.invalidateQueries();
  }

  const profileLabel = botStatus?.active_profile_name ?? "Standard";

  return (
    <div className="p-4 md:p-6 space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between gap-4">
        {/* Stanga: profil + cont MT5 */}
        <div className="flex items-center gap-4 flex-wrap">
          <div className="leading-tight">
            <h1 className="text-base font-bold text-white">Dashboard</h1>
            <p className="text-[10px] text-slate-500">4 engine-uri · rezultate direct din MT5 · profil {profileLabel.replace(/\s*Profile$/i, "").toLowerCase()}</p>
          </div>
          {mt5?.connected && (
            <div className="flex items-center gap-3 text-xs text-slate-400 bg-surface-card border border-surface-border rounded-lg px-3 py-1.5">
              <span className="text-slate-500">Cont</span>
              <span className="font-mono text-white">{mt5.account}</span>
              {mt5.server && <span className="text-slate-600">· {mt5.server}</span>}
              <span className="w-px h-3 bg-surface-border" />
              <span className="text-slate-500">Balance</span>
              <span className="font-mono text-white font-medium">
                {mt5.balance?.toLocaleString("ro-RO", { maximumFractionDigits: 2 })} {mt5.currency}
              </span>
              <span className="text-slate-500">Equity</span>
              <span className={`font-mono font-medium ${
                mt5.equity !== null && mt5.balance !== null
                  ? mt5.equity >= mt5.balance ? "text-profit" : "text-loss"
                  : "text-white"
              }`}>
                {mt5.equity?.toLocaleString("ro-RO", { maximumFractionDigits: 2 })} {mt5.currency}
              </span>
            </div>
          )}
          {mt5 && !mt5.connected && (
            <span className="text-[10px] text-slate-600 bg-surface-card border border-surface-border rounded px-2 py-1">
              MT5 deconectat
            </span>
          )}
        </div>

        {/* Dreapta: bot status + timer + refresh */}
        <div className="flex items-center gap-3 flex-shrink-0">
          {updateLabel && (
            <span className="text-[10px] text-slate-600 tabular-nums">
              actualizat {updateLabel}
            </span>
          )}
          <button
            onClick={refresh}
            className="p-2 rounded-lg bg-surface-card border border-surface-border text-slate-400 hover:text-white transition-colors"
            title="Reîncarcă datele"
          >
            <RefreshCw size={14} />
          </button>
        </div>
      </div>

      {/* Engine-uri: stare reala + Start/Stop + autostart (Engine Lifecycle comun) */}
      <EngineControlCards />

      {/* Performanta: TOTAL + cate un card per engine (aceeasi sursa MT5 ca Tranzactiile) */}
      <EnginePerformanceCards />

      {/* Filtru de SURSA pentru toata pagina (carduri, statistici, grafic, tranzactii) */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-[11px] text-slate-500">Arată tranzacțiile:</span>
        {([["all", "Toate"], ["bot", "Custom Engine"], ["ai", "AI Engine"], ["daily", "Daily Engine"], ["noisy", "Noisy Engine"], ["manual", "Manual"]] as const).map(([v, label]) => (
          <button key={v} onClick={() => setSource(v)}
            className={`text-[11px] px-2.5 py-1 rounded-lg border transition-colors ${
              source === v ? "border-blue-500 bg-blue-500/15 text-white font-semibold"
                           : "border-surface-border text-slate-400 hover:text-white"}`}>
            {label}
          </button>
        ))}
        {source !== "all" && (
          <span className="text-[10px] text-amber-400/80">
            filtru activ — cifrele de pe pagină includ doar {source === "bot" ? "Custom Engine" : source === "ai" ? "AI Engine" : source === "daily" ? "Daily Engine (ordine reale MT5; shadow = 0)" : source === "noisy" ? "Noisy Engine (ordine reale MT5; shadow = 0)" : "tranzacțiile manuale"}
          </span>
        )}
      </div>

      {/* Banner AutoTrading dezactivat */}
      {mt5?.connected && mt5.algo_trading_enabled === false && (
        <div className="flex items-center gap-3 bg-warn/10 border border-warn/40 rounded-xl px-4 py-3">
          <span className="text-warn text-lg leading-none">⚠</span>
          <div>
            <p className="text-sm font-semibold text-warn">Algo Trading dezactivat în MT5!</p>
            <p className="text-xs text-warn/70 mt-0.5">
              Semnalele sunt detectate dar ordinele <strong>nu vor fi plasate</strong>.
              Activează butonul „Algo Trading" din bara de sus a MetaTrader 5.
            </p>
          </div>
        </div>
      )}

      {/* Ritm de tranzactionare pe engine (inlocuieste Frecventa estimata) */}
      <TradingPace />

      {/* Piete active — toate engine-urile; o piata = un card, banda colorata = engine-urile ei */}
      <div>
        <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
          <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
            Piețe active
            {counts && (
              <span className="ml-2 normal-case font-normal text-slate-600">
                · {markets.length} piețe
                {counts.in_position ? ` · ${counts.in_position} în poziție` : ""}
                {counts.active ? ` · ${counts.active} active` : ""}
                {counts.observe ? ` · ${counts.observe} în observație` : ""}
                {counts.blocked ? ` · ${counts.blocked} blocate` : ""}
                {counts.stopped ? ` · ${counts.stopped} oprite` : ""}
              </span>
            )}
          </h2>
          <div className="flex items-center gap-3 text-[10px] text-slate-500 flex-wrap">
            {(Object.keys(ENGINE_COLOR) as MarketEngineId[]).map(id => (
              <span key={id} className="flex items-center gap-1">
                <span className={`w-2.5 h-1 rounded ${ENGINE_COLOR[id].bar}`} />{ENGINE_COLOR[id].label}
                {marketsData && <span className={marketsData.engines[id] ? "text-profit" : "text-slate-600"}>
                  {marketsData.engines[id] ? "pornit" : "oprit"}</span>}
              </span>
            ))}
            <label className="flex items-center gap-1 cursor-pointer">
              <input type="checkbox" checked={hideStopped} onChange={e => setHideStopped(e.target.checked)} />
              ascunde piețele oprite
            </label>
          </div>
        </div>
        {marketsData?.global_block && (
          <div className="text-[11px] text-warn bg-warn/10 border border-warn/30 rounded-lg px-3 py-2 mb-3">
            🛡 Setări Globale — ordinele noi sunt blocate pe tot contul: {marketsData.global_block}
          </div>
        )}
        {marketsData && !marketsData.mt5_connected && (
          <div className="text-[11px] text-warn/80 bg-warn/10 border border-warn/30 rounded-lg px-3 py-2 mb-3">
            MT5 neconectat — starea engine-urilor e afișată, rezultatele pe piață nu sunt disponibile.
          </div>
        )}
        {marketsData && Object.keys(marketsData.errors).filter(k => k !== "mt5").length > 0 && (
          <div className="text-[11px] text-slate-500 mb-2">
            Date indisponibile pentru: {Object.keys(marketsData.errors).filter(k => k !== "mt5").join(", ")} (restul piețelor e afișat normal).
          </div>
        )}
        {isLoading ? (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
            {[...Array(10)].map((_, i) => <div key={i} className="h-40 rounded-xl bg-surface-card animate-pulse" />)}
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
            {markets.map(m => (
              <MarketCard key={m.symbol} m={m} selected={m.symbol === selectedMarket}
                onClick={() => setSelectedMarket(s => (s === m.symbol ? null : m.symbol))} />
            ))}
            {!markets.length && <div className="text-xs text-slate-500 col-span-full py-4">Nicio piață configurată pentru filtrul ales.</div>}
          </div>
        )}
        {!srcEngine && histOnly.length > 0 && (
          <div className="text-[11px] text-slate-500 mt-2">
            + piețe cu tranzacții dar fără niciun engine configurat acum:{" "}
            {histOnly.map(h => (
              <button key={h.symbol} onClick={() => setSelectedMarket(h.symbol)}
                className="underline decoration-dotted hover:text-slate-300 mr-2">
                {h.symbol} ({Object.entries(h.sources).map(([s, n]) => `${s === "bot" ? "Custom" : s.toUpperCase()} ${n}`).join(", ")})
              </button>
            ))}
            — incluse în statistici și în lista de tranzacții.
          </div>
        )}
      </div>

      {/* Ordine active — sursa de adevar MT5 (pozitii + pending, Bot/AI/Manual) */}
      <ActiveOrdersTable />

      {/* Bottom two columns */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Coloana stanga: Tranzacții MT5 + Top 5 Piețe (sub tranzacții) */}
        <div className="space-y-4">
        <div className="bg-surface-card rounded-xl border border-surface-border p-4 flex flex-col h-[520px] overflow-hidden">
          <div className="flex items-center justify-between mb-4 flex-shrink-0">
            <div className="flex items-center gap-3 min-w-0">
              <h2 className="text-sm font-semibold text-white truncate">
                {feedView === "trades" ? "Tranzacții MT5" : "Semnale"}
                {" — "}{selectedMarket ?? "toate piețele"}
              </h2>
              <div className="flex gap-1 flex-shrink-0">
                {([["trades", "Tranzacții"], ["signals", "Semnale"]] as const).map(([v, label]) => (
                  <button
                    key={v}
                    onClick={() => setFeedView(v)}
                    title={v === "trades"
                      ? "Tranzacțiile închise, direct din MT5 — toate engine-urile (badge colorat); pe o piață: tot ce s-a tranzacționat pe ea"
                      : "Semnalele tuturor engine-urilor: setup-uri Custom, decizii AI, trade-uri Daily / Noisy — cu starea lor"}
                    className={`text-[10px] px-2 py-0.5 rounded transition-colors font-medium ${
                      feedView === v ? "bg-blue-500/20 text-blue-400" : "text-slate-500 hover:text-slate-300"
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
            {selectedMarket && (
              <button onClick={() => setSelectedMarket(null)}
                className="text-[10px] px-2 py-0.5 rounded bg-blue-500/20 text-blue-400 hover:text-white flex-shrink-0"
                title="Arată din nou toate piețele">
                {selectedMarket} ✕
              </button>
            )}
          </div>
          <div className="flex-1 min-h-0">
            <SignalFeed view={feedView} source={source} symbol={selectedMarket ?? undefined} />
          </div>
        </div>

          {/* Top 5 piete — mutat sub Tranzacții MT5 */}
          <TopMarketsWidget source={source} />
        </div>

        {/* Equity chart + stats */}
        <div className="space-y-4">
          <div className="bg-surface-card rounded-xl border border-surface-border p-4">
            <h2 className="text-sm font-semibold text-white mb-4">Performanță</h2>
            <EquityChart source={source} />
          </div>

          {/* Trading stats */}
          <div className="bg-surface-card rounded-xl border border-surface-border p-4">
            <h2 className="text-sm font-semibold text-white mb-3">Statistici</h2>
            <TradingStatsPanel markets={marketsData} mt5={mt5} botStatus={botStatus} source={source} />
          </div>

          {/* Weekly index */}
          <div className="bg-surface-card rounded-xl border border-surface-border p-4">
            <h2 className="text-sm font-semibold text-white mb-3">Indice Săptămânal</h2>
            <WeeklyStatsPanel source={source} />
          </div>
        </div>
      </div>

      {/* Analiza per engine — aceeasi componenta pentru toate, diferentiata prin culoare */}
      <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-4 gap-4">
        <EnginePerformanceSection engine="custom" />
        <EnginePerformanceSection engine="ai" />
        <EnginePerformanceSection engine="daily" />
        <EnginePerformanceSection engine="noisy" />
      </div>
    </div>
  );
}
