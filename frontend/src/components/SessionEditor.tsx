import { useState, useMemo } from "react";
import { Pause, Play } from "lucide-react";
import type { ProfileSession, Meta } from "../api/types";
import { useMt5Markets, useMt5Status, useMarketAtr } from "../api/hooks";
import { BacktestPanel } from "./BacktestPanel";
import { InfoTooltip } from "./InfoTooltip";
import { ImageTooltip } from "./ImageTooltip";
import { MARKET_SPECS, calcOvershoot } from "../marketSpecs";

interface Props {
  session: ProfileSession;
  meta: Meta;
  onChange: (updated: ProfileSession) => void;
  onRemove?: () => void;
  onJobStarted?: () => void;
  onSaveAndNavigate?: () => void;
  onDownloadStarted?: () => void;
  paused?: boolean;
  onPauseToggle?: () => void;
  profileStartBalance?: number;
}

const HOURS = Array.from({ length: 24 }, (_, i) => i);
const WD_KEYS = [0, 1, 2, 3, 4, 5, 6] as const;

function getMandatoryCriteria(trend_tf: string) {
  return [
  {
    title: `Trend confirmat (EMA200 ${trend_tf})`,
    desc: `Prețul trebuie să fie DEASUPRA EMA200 pe ${trend_tf} pentru LONG, SUB pentru SHORT. Fără filtru de trend, niciun setup nu e luat în considerare.`,
  },
  {
    title: "Minimum 2 Higher Highs consecutive",
    desc: "Structura de piață confirmată: botul verifică cel puțin 2 maxime crescătoare (HH) înainte de a căuta pullback-ul.",
  },
  {
    title: "Pullback valid (Higher Low)",
    desc: "După ultimul HH, prețul retrage și formează un minim mai sus decât cel anterior. Trebuie să apară în fereastra configurată (Pullback window).",
  },
  {
    title: "Breakout confirmat pe bara curentă",
    desc: "Prima bară care se ÎNCHIDE deasupra maximului barei de pullback declanșează semnalul. Ordinul BUY_STOP e plasat la acel maxim + 1 pip.",
  },
  {
    title: "Capital + circuit breaker OK",
    desc: "Contul MT5 are marjă suficientă și nu s-a atins limita de pierderi consecutive pe zi (circuit breaker). Dacă una din condiții lipsește, ordinul nu e plasat.",
  },
  ];
}

const TIPS = {
  markets:       "Piețele pe care sesiunea generează semnale. Bifează simbolurile disponibile în contul tău MT5.",
  mt5_search:    "Caută orice simbol disponibil în contul MT5 curent (forex, indici, crypto, materii prime). MT5 trebuie să fie deschis și conectat.",
  entry_tf:      "Timeframe-ul barei de intrare — semnalul este detectat pe acest TF.",
  trend_tf:      "Timeframe mai mare folosit pentru filtrarea trendului (EMA200). Trebuie să fie > Entry TF.",
  direction:     "LONG = doar cumpărări; SHORT = doar vânzări; BOTH = ambele direcții.",
  pullback_window: [
    "Fereastra de căutare a pullback-ului după un Higher High (HH).",
    "",
    "Botul detectează un HH, apoi caută un Higher Low (HL) — o retragere — în MAXIM N bare. Prima bară care revine peste maximul retragerii declanșează ordinul de intrare.",
    "",
    "Ex: 8 = retragerea trebuie să apară în max 8 bare M15 (2h). Dacă pullback-ul durează mai mult, setup-ul e ignorat.",
    "",
    "Mare (10-12): mai multe semnale, retrageri mai lungi acceptate.",
    "Mic (4-6): semnale mai puține dar mai stricte, doar retrageri scurte și rapide.",
  ].join("\n"),
  expire_bars: [
    "Cât timp rămâne activ un ordin pending după plasare.",
    "",
    "Botul plasează BUY_STOP/SELL_STOP și așteaptă. Dacă prețul nu ajunge la entry în N bare M15, ordinul e ANULAT automat.",
    "",
    "Ex: 4 bare = ordinul e valid 1 oră (4×15min). Dacă prețul nu sparge nivelul în 1h, setup-ul expiră.",
    "",
    "Mic (2-3): intri doar când momentum-ul e proaspăt și direcția e clară.",
    "Mare (6-8): aștepți mai mult, dar riscul de entry în condiții deja schimbate crește.",
  ].join("\n"),
  criteria:      "3 criterii opționale care cresc R/R-ul. Fiecare nivel R are un prag configurabil (La ≥ N criterii). Praguri default: R-mid la ≥1, R-top la ≥2, R-max la ≥3. Criteriile sunt independente — activează oricare combinație.",
  rsi:           "RSI filtrează entry-urile în zone de supraCumpărare/supraVânzare. Gama recomandată: buy 40–65, sell 35–60.",
  ema:           "EMA8 > EMA20 > EMA50 pe TF de intrare — confirmă că trendul de scurt termen e aliniat cu cel de mediu termen.",
  body_strength: "Corp lumânare: bara de intrare trebuie să aibă un corp (close−open) mai mare decât ATR × ratio în direcția trade-ului. Confirmă că breakout-ul are impuls. Dezactivat implicit. Ratio recomandat: 0.10–0.25.",
  circuit_breaker: "Oprește tranzacționarea după N pierderi consecutive în aceeași zi. Repornește la miezul nopții.",
  risk_pct:      "Procentul din equity riscat per tranzacție. Equity-ul este citit din MT5 la fiecare ordin.",
  account_fraction: [
    "Fracția din equity-ul total MT5 alocat acestei sesiuni.",
    "",
    "Ex: 12.5% → la $800 equity → $100 capital sesiune.",
    "Fiecare trade din sesiune riscă risk% din această sumă.",
    "",
    "Sesiunea poate tranzacționa simultan pe mai multe piețe — capitalul NU e împărțit per piață, ci fiecare trade folosește aceeași bază de calcul a lot-ului.",
  ].join("\n"),
  execute_trades: [
    "ON → bot-ul plasează ordine reale BUY_STOP/SELL_STOP în MT5.",
    "OFF → mod observare: semnalele sunt loggate și trimise pe Telegram, fără ordine în MT5.",
    "",
    "Contul (Demo/Live) este cel în care ești logat în MT5 desktop — bot-ul se conectează automat la orice cont este activ. Equity-ul și capitalul se citesc live din MT5.",
  ].join("\n"),
  session_hours: "Intervalul orar (server MT5) în care sunt acceptate intrări noi. Non-stop ignoră complet restricțiile de ore — util pentru sesiuni crypto 24/7 care rulează continuu.",
  skip_hours:    "Ore server MT5 în care nu se plasează ordine noi. Util pentru evitarea știrilor (ex: 15:30 NFP).",
  skip_weekdays: "Zile ale săptămânii în care sesiunea nu tranzacționează.",
  friday_close:  "Vineri la ora configurată, toate pozițiile deschise (triggerate) sunt închise automat printr-un ordin la piață. Dezactivează pentru sesiunile crypto — BTC tranzacționează și în weekend.",
  news_protection: [
    "Când este activată, botul verifică calendarul economic la fiecare 5 minute (ForexFactory → MT5 calendar).",
    "Dacă există un eveniment de impact ridicat pentru valutele sesiunii în fereastra configurată, sesiunea este pusă pe pauză automat.",
    "",
    "Impact: 1=Scăzut, 2=Mediu, 3=Ridicat. Recomandat: 3 (doar știri mari: NFP, CPI, Fed, BCE).",
    "Pre-știre: minute înainte de eveniment — sesiunea intră pe pauză preventiv.",
    "Post-știre: minute după eveniment — sesiunea rămâne pe pauză pentru a lăsa volatilitatea să se calmeze.",
  ].join("\n"),
  news_impact:    "Nivelul minim de impact pentru a declanșa pauza. 1=Scăzut, 2=Mediu, 3=Ridicat (recomandat). Sursa principală: ForexFactory. Backup: MT5 calendar built-in.",
  news_pre:       "Minute înainte de eveniment în care sesiunea intră pe pauză preventiv. Recomandat: 15–30 min.",
  news_post:      "Minute după eveniment cât sesiunea rămâne pe pauză. Recomandat: 15–30 min pentru a lăsa volatilitatea să se calmeze.",
  max_concurrent: [
    "Numărul maxim de poziții simultane (pending + triggerate) permise per piață.",
    "",
    "Default: 1 — nu se plasează un nou ordin pe EURUSD dacă există deja unul pending sau deschis.",
    "2+ — permite mai multe poziții pe același simbol, ex: dacă primul trade merge bine și apare un nou setup.",
    "",
    "Se aplică și în backtest și în live. Crește capitalul necesar per sesiune.",
  ].join("\n"),
  min_bars_between: [
    "Numărul minim de bare care trebuie să treacă după plasarea unui semnal pe un simbol înainte de a plasa altul.",
    "",
    "Ex: 8 bare M15 = cel puțin 2 ore între ordine pe aceeași piață.",
    "0 = fără restricție (default) — ordinele pot fi plasate la fiecare bară.",
    "",
    "Activ doar când max_concurrent ≥ 2. Previne suprapuneri prea dese pe același simbol.",
  ].join("\n"),
};

// ── Diagrama R:R proporțională ─────────────────────────────────────────────
function RRDiagram({ session, mt5Connected }: { session: ProfileSession; mt5Connected: boolean }) {
  const rBase    = session.r_base ?? 2.5;
  const rMid     = session.r_mid  ?? 3.5;
  const rTop     = session.r_top  ?? 4.5;
  const rMax     = session.r_max  ?? 5.5;
  const tMid     = session.r_mid_threshold ?? 1;
  const tTop     = session.r_top_threshold ?? 2;
  const tMax     = session.r_max_threshold ?? 3;
  const riskBase = session.risk_base ?? session.risk_pct ?? 0.01;
  const riskMid  = session.risk_mid  ?? riskBase;
  const riskTop  = session.risk_top  ?? riskBase;
  const riskMaxV = session.risk_max  ?? riskBase;

  const { data: atrData } = useMarketAtr(
    session.markets,
    session.entry_tf ?? "M15",
    mt5Connected && session.markets.length > 0,
  );

  const unit   = 32;   // 32px per 1R — suficient pentru 2 linii text per nivel
  const pTop   = 28;
  const pBot   = 22;
  const pLeft  = 62;
  const pRight = 82;
  const lineW  = 140;
  const W      = pLeft + lineW + pRight;
  const H      = (rMax + 1) * unit + pTop + pBot;

  const entryY  = pTop + rMax * unit;
  const slY     = entryY + unit;
  const tpBaseY = entryY - rBase * unit;
  const tpMidY  = entryY - rMid  * unit;
  const tpTopY  = entryY - rTop  * unit;
  const tpMaxY  = entryY - rMax  * unit;

  const candles: Array<[number, number, number, number, boolean]> = [
    [1.0, 0.5, 0.45, 1.1,  true ],
    [0.5, 0.1, 0.05, 0.6,  true ],
    [0.1, 0.4, 0.0,  0.5,  false],
    [0.4, 0.6, 0.3,  0.7,  false],
    [0.6, 0.0, -0.05,0.65, true ],
  ];
  const cW = 7; const cGap = 4;
  const cStart = pLeft - candles.length * (cW + cGap) + cGap;

  const levels = [
    { y: tpBaseY, r: rBase, color: "#94a3b8", risk: riskBase, thr: `≥0 cr.` },
    { y: tpMidY,  r: rMid,  color: "#60a5fa", risk: riskMid,  thr: `≥${tMid} cr.` },
    { y: tpTopY,  r: rTop,  color: "#4ade80", risk: riskTop,  thr: `≥${tTop} cr.` },
    { y: tpMaxY,  r: rMax,  color: "#fbbf24", risk: riskMaxV, thr: `≥${tMax} cr.` },
  ];

  // ATR-based SL distance per piata
  const atrRows = atrData?.data
    ? Object.entries(atrData.data)
        .filter(([, v]) => v != null)
        .map(([sym, v]) => {
          const d = v!;
          // pips sau puncte in functie de instrument
          const isIndex  = d.digits <= 2;
          const isCrypto = d.pip_size >= 0.01 && d.digits === 2;
          const slDist   = d.atr;  // 1R = 1×ATR (default sl_atr_factor=1)
          const label    = isIndex || isCrypto
            ? `${slDist.toFixed(isIndex ? 0 : 1)} pts`
            : `${d.atr_pips ?? "?"} pips`;
          return { sym, label };
        })
    : [];

  return (
    <div className="space-y-2">
      <svg width={W} height={H} className="select-none">
        {/* Zone colorata */}
        <rect x={pLeft} y={pTop} width={lineW} height={entryY - pTop}
          fill="#22c55e" fillOpacity={0.06} />
        <rect x={pLeft} y={entryY} width={lineW} height={unit}
          fill="#ef4444" fillOpacity={0.10} />

        {/* Linii TP */}
        {levels.map(({ y, r, color, risk, thr }) => (
          <g key={r}>
            <line x1={pLeft} y1={y} x2={pLeft + lineW} y2={y}
              stroke={color} strokeWidth={1} strokeDasharray="4 3" />
            {/* Linia 1: "4.5R  1.2%" pe acelasi rand */}
            <text x={pLeft + lineW + 5} y={y + 5}>
              <tspan fontSize={9} fill={color} fontWeight="700">{r}R</tspan>
              <tspan fontSize={8} fill={color} fillOpacity={0.8}> · {(risk * 100).toFixed(1)}%</tspan>
            </text>
            {/* Linia 2: threshold */}
            <text x={pLeft + lineW + 5} y={y + 16} fontSize={7.5} fill="#475569">
              {thr}
            </text>
          </g>
        ))}

        {/* Entry */}
        <line x1={pLeft - 6} y1={entryY} x2={pLeft + lineW} y2={entryY}
          stroke="#e2e8f0" strokeWidth={1.5} />
        <text x={pLeft + lineW + 5} y={entryY + 4} fontSize={9} fill="#e2e8f0" fontWeight="700">
          Entry
        </text>

        {/* SL */}
        <line x1={pLeft} y1={slY} x2={pLeft + lineW} y2={slY}
          stroke="#f87171" strokeWidth={1} strokeDasharray="4 3" />
        <text x={pLeft + lineW + 5} y={slY + 4} fontSize={9} fill="#f87171" fontWeight="600">
          -1R SL
        </text>

        {/* Lumânări fake */}
        {candles.map(([open, close, high, low, bull], i) => {
          const x   = cStart + i * (cW + cGap);
          const oY  = entryY + open  * unit;
          const cY  = entryY + close * unit;
          const hY  = entryY + high  * unit;
          const lY  = entryY + low   * unit;
          const bY  = Math.min(oY, cY);
          const bH  = Math.max(Math.abs(oY - cY), 1.5);
          const mX  = x + cW / 2;
          const col = bull ? "#4ade80" : "#f87171";
          return (
            <g key={i}>
              <line x1={mX} y1={hY} x2={mX} y2={lY} stroke={col} strokeWidth={0.8} />
              <rect x={x} y={bY} width={cW} height={bH}
                fill={bull ? col : "none"} stroke={col} strokeWidth={0.8} rx={0.5} />
            </g>
          );
        })}

        <text x={pLeft - 4} y={entryY + unit / 2 + 3} fontSize={8} fill="#f87171"
          textAnchor="middle">1R</text>
      </svg>

      {/* ATR per piata — distanta SL reala */}
      {atrRows.length > 0 && (
        <div className="flex flex-wrap gap-x-3 gap-y-1 px-1">
          <span className="text-[10px] text-slate-600 w-full">SL ≈ 1×ATR per piață:</span>
          {atrRows.map(({ sym, label }) => (
            <span key={sym} className="text-[10px] text-slate-400">
              <span className="text-slate-300 font-medium">{sym}</span> {label}
            </span>
          ))}
        </div>
      )}
      {mt5Connected && session.markets.length > 0 && !atrData && (
        <p className="text-[10px] text-slate-600 px-1">Se încarcă ATR din MT5...</p>
      )}
      {!mt5Connected && (
        <p className="text-[10px] text-slate-600 px-1">
          Conectează MT5 pentru distanțe reale SL per piață.
        </p>
      )}
    </div>
  );
}

// ── SessionEditor ─────────────────────────────────────────────────────────

export function SessionEditor({ session, meta, onChange, onRemove, onJobStarted, onSaveAndNavigate, onDownloadStarted, paused, onPauseToggle, profileStartBalance }: Props) {
  const [open, setOpen]           = useState(false);
  const [confirmRemove, setConfirmRemove] = useState(false);
  const [showMt5Search, setShowMt5Search] = useState(false);
  const [mt5Query, setMt5Query]   = useState("");
  const [showMandatory, setShowMandatory] = useState(false);
  const [showRRChart, setShowRRChart] = useState(false);

  const { data: mt5Data, isLoading: loadingMt5 } = useMt5Markets();
  const { data: mt5Status } = useMt5Status();

  const mt5Filtered = useMemo(() => {
    if (!mt5Data?.symbols) return [];
    const q = mt5Query.trim().toUpperCase();
    if (!q) return mt5Data.symbols.slice(0, 40);
    return mt5Data.symbols.filter((s) => s.includes(q)).slice(0, 40);
  }, [mt5Data, mt5Query]);

  const upd = (patch: Partial<ProfileSession>) => onChange({ ...session, ...patch });

  const toggleMarket = (m: string) => {
    const arr = session.markets.includes(m)
      ? session.markets.filter((x) => x !== m)
      : [...session.markets, m];
    upd({ markets: arr });
  };

  const toggleHour = (h: number) => {
    const s = new Set(session.skip_hours);
    s.has(h) ? s.delete(h) : s.add(h);
    upd({ skip_hours: [...s].sort((a, b) => a - b) });
  };

  const toggleWd = (d: number) => {
    const s = new Set(session.skip_weekdays);
    s.has(d) ? s.delete(d) : s.add(d);
    upd({ skip_weekdays: [...s].sort((a, b) => a - b) });
  };

  // Calcul impact criterii opționale
  const activeCriteria = [
    session.rsi_enabled,
    session.ema_alignment_enabled,
    session.body_strength_enabled ?? false,
  ].filter(Boolean).length;

  const tMid = session.r_mid_threshold ?? 1;
  const tTop = session.r_top_threshold ?? 2;
  const tMax = session.r_max_threshold ?? 3;
  const getR = (n: number): number => {
    if (n >= tMax) return session.r_max ?? 5.5;
    if (n >= tTop) return session.r_top;
    if (n >= tMid) return session.r_mid;
    return session.r_base;
  };
  const currentR = getR(activeCriteria);
  const activeCard = activeCriteria >= tMax ? 3 : activeCriteria >= tTop ? 2 : activeCriteria >= tMid ? 1 : 0;

  const dirBadgeColor = {
    LONG:  "bg-profit/20 text-profit",
    SHORT: "bg-loss/20 text-loss",
    BOTH:  "bg-blue-500/20 text-blue-300",
  }[session.direction] ?? "bg-slate-700 text-slate-300";

  return (
    <div className={`rounded-xl border overflow-hidden transition-colors ${
      paused
        ? "bg-surface-card border-warn/30"
        : "bg-surface-card border-surface-border"
    }`}>
      {/* Header */}
      <div className={`flex items-center gap-2 px-4 py-3 hover:bg-surface-border/20 transition-colors ${paused ? "opacity-80" : ""}`}>
        <button className="flex-1 flex items-center gap-3 text-left" onClick={() => setOpen((o) => !o)}>
          <span className="text-sm font-semibold text-white">{session.label || session.id}</span>
          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${dirBadgeColor}`}>
            {session.direction}
          </span>
          {paused ? (
            <span className="text-xs px-2 py-0.5 rounded-full bg-warn/20 text-warn font-medium">
              PAUZA
            </span>
          ) : (
            <span className={`text-xs px-2 py-0.5 rounded-full ${session.execute_trades ? "bg-blue-500/20 text-blue-300" : "bg-slate-700 text-slate-400"}`}>
              {session.execute_trades ? "LIVE" : "OBS"}
            </span>
          )}
          {session.markets.length > 0
            ? <span className="text-xs text-slate-400 flex-1 truncate">{session.markets.join(" · ")}</span>
            : <span className="text-xs text-slate-600 flex-1 italic">fără piețe selectate</span>
          }
          <span className="text-slate-500">{open ? "▲" : "▼"}</span>
        </button>
        {/* Pause/Play */}
        {onPauseToggle && (
          <button
            onClick={(e) => { e.stopPropagation(); onPauseToggle(); }}
            title={paused ? "Reia sesiunea" : "Pune sesiunea pe pauză"}
            className={`ml-1 p-1 rounded transition-colors ${
              paused
                ? "text-profit hover:bg-profit/10"
                : "text-slate-500 hover:text-warn hover:bg-warn/10"
            }`}
          >
            {paused
              ? <Play size={13} fill="currentColor" />
              : <Pause size={13} />
            }
          </button>
        )}

        {/* Delete */}
        {onRemove && (
          confirmRemove ? (
            <div className="flex items-center gap-1.5 ml-1">
              <span className="text-xs text-loss">Stergi?</span>
              <button onClick={onRemove}
                className="text-xs px-2 py-0.5 rounded bg-loss/80 hover:bg-loss text-white transition-colors">Da</button>
              <button onClick={() => setConfirmRemove(false)}
                className="text-xs px-2 py-0.5 rounded border border-surface-border text-slate-400 hover:text-white transition-colors">Nu</button>
            </div>
          ) : (
            <button onClick={() => setConfirmRemove(true)}
              className="ml-1 text-slate-600 hover:text-loss transition-colors text-sm px-1"
              title="Sterge sesiunea">✕</button>
          )
        )}
      </div>

      {open && (
        <div className="border-t border-surface-border px-4 py-4 space-y-5">
          {/* Nume */}
          <div className="space-y-1">
            <label className="text-xs text-slate-500">Nume sesiune</label>
            <input value={session.label} onChange={(e) => upd({ label: e.target.value })}
              placeholder="ex: S7 — XAUUSD Long"
              className="w-full bg-surface border border-surface-border rounded px-2 py-1 text-sm text-white focus:outline-none focus:border-blue-500" />
          </div>

          {/* Piețe predefinite */}
          <Section label="Piețe" tip={TIPS.markets}>
            <div className="flex flex-wrap gap-2">
              {meta.available_markets.map((m) => (
                <button key={m} onClick={() => toggleMarket(m)}
                  className={`text-xs px-2 py-0.5 rounded border transition-colors ${
                    session.markets.includes(m)
                      ? "bg-blue-600 border-blue-500 text-white"
                      : "bg-transparent border-surface-border text-slate-400 hover:border-slate-500"
                  }`}>{m}</button>
              ))}
            </div>

            {/* MT5 search */}
            <div className="mt-2">
              <button
                onClick={() => { setShowMt5Search((v) => !v); setMt5Query(""); }}
                className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-300 transition-colors"
              >
                <span>{showMt5Search ? "▲" : "▼"}</span>
                Caută în MT5
                <InfoTooltip text={TIPS.mt5_search} />
              </button>

              {showMt5Search && (
                <div className="mt-2 space-y-2">
                  <input
                    value={mt5Query}
                    onChange={(e) => setMt5Query(e.target.value)}
                    placeholder="Ex: XAU, BTC, GER..."
                    className="w-full bg-surface border border-surface-border rounded px-2 py-1.5 text-xs text-white focus:outline-none focus:border-blue-500"
                    autoFocus
                  />
                  {loadingMt5 && (
                    <p className="text-xs text-slate-500">Se conectează la MT5...</p>
                  )}
                  {mt5Data?.error && (
                    <p className="text-xs text-loss">{mt5Data.error}</p>
                  )}
                  {!loadingMt5 && !mt5Data?.error && (
                    <div className="flex flex-wrap gap-1.5 max-h-32 overflow-y-auto">
                      {mt5Filtered.length === 0 && (
                        <span className="text-xs text-slate-600">Niciun simbol găsit</span>
                      )}
                      {mt5Filtered.map((sym) => (
                        <button key={sym} onClick={() => toggleMarket(sym)}
                          className={`text-xs px-2 py-0.5 rounded border transition-colors ${
                            session.markets.includes(sym)
                              ? "bg-blue-600 border-blue-500 text-white"
                              : "bg-surface-border/40 border-surface-border text-slate-400 hover:border-slate-500"
                          }`}>{sym}</button>
                      ))}
                    </div>
                  )}
                  {!mt5Query && mt5Data?.symbols && (
                    <p className="text-xs text-slate-600">
                      {mt5Data.symbols.length} simboluri disponibile — scrie pentru a filtra
                    </p>
                  )}
                </div>
              )}
            </div>
          </Section>

          {/* TF + directie */}
          <div className="grid grid-cols-3 gap-4">
            <Section label="Entry TF" tip={TIPS.entry_tf}>
              <SegControl options={meta.timeframes} value={session.entry_tf}
                onChange={(v) => upd({ entry_tf: v })} />
            </Section>
            <Section label="Trend TF" tip={TIPS.trend_tf}>
              <SegControl options={meta.trend_timeframes} value={session.trend_tf}
                onChange={(v) => upd({ trend_tf: v })} />
            </Section>
            <Section label="Direcție" tip={TIPS.direction}>
              <SegControl options={meta.directions} value={session.direction}
                onChange={(v) => upd({ direction: v })} />
            </Section>
          </div>

          {/* Ore sesiune */}
          <Section label="Ore Sesiune" tip={TIPS.session_hours}>
            <div className="space-y-2">
              <Toggle
                label="Non-stop (fără restricție de ore)"
                value={session.session_start === 0 && session.session_end === 24}
                onChange={(v) => upd({ session_start: v ? 0 : 10, session_end: v ? 24 : 18 })}
              />
              {!(session.session_start === 0 && session.session_end === 24) && (
                <div className="grid grid-cols-2 gap-3">
                  <NumField label="Start oră" value={session.session_start} min={0} max={23}
                    onChange={(v) => upd({ session_start: v })} />
                  <NumField label="End oră" value={session.session_end} min={1} max={24}
                    onChange={(v) => upd({ session_end: v })} />
                </div>
              )}
            </div>
          </Section>

          {/* Expire + pullback */}
          <div className="grid grid-cols-2 gap-4">
            <NumField label="Expire bare" value={session.expire_bars} min={1} max={20}
              tip={TIPS.expire_bars} onChange={(v) => upd({ expire_bars: v })} />
            <NumField label="Pullback window" value={session.pullback_window} min={1} max={20}
              tip={TIPS.pullback_window} onChange={(v) => upd({ pullback_window: v })} />
          </div>

          {/* ── CRITERII OPȚIONALE ── */}
          <Section label="Criterii Opționale" tip={TIPS.criteria}>
            {/* Criterii Obligatorii dropdown */}
            <div className="mb-3">
              <button
                onClick={() => setShowMandatory((v) => !v)}
                className="flex items-center gap-1.5 text-[10px] text-slate-600 hover:text-slate-400 transition-colors"
              >
                <span className="text-[8px]">{showMandatory ? "▲" : "▼"}</span>
                Criterii obligatorii (întotdeauna active)
              </button>
              {showMandatory && (
                <div className="mt-1.5 border border-surface-border/40 rounded-lg p-3 space-y-2.5 bg-surface-border/10">
                  {getMandatoryCriteria(session.trend_tf).map((c, i) => (
                    <div key={i} className="space-y-0.5">
                      <div className="text-[10px] font-semibold text-slate-300">
                        {i + 1}. {c.title}
                      </div>
                      <div className="text-[10px] text-slate-500 leading-relaxed">
                        {c.desc}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Counter vizual */}
            <div className="flex items-center gap-3 mb-3">
              <div className="flex gap-1">
                {[0, 1, 2].map((n) => (
                  <div key={n} className={`h-1.5 w-8 rounded-full transition-colors ${
                    n < activeCriteria ? "bg-blue-500" : "bg-surface-border"
                  }`} />
                ))}
              </div>
              <span className="text-xs text-slate-400">
                {activeCriteria}/3 active →{" "}
                <span className="font-semibold text-white">{currentR}R</span>
              </span>
            </div>

            {/* 4 carduri R/R cu thresholds */}
            <div className="grid grid-cols-4 gap-2 mb-3">
              {([
                { cardIdx: 0, label: "Base",   rField: "r_base" as const, riskField: "risk_base" as const, tField: null,                  tDefault: 0 },
                { cardIdx: 1, label: "Mid",    rField: "r_mid"  as const, riskField: "risk_mid"  as const, tField: "r_mid_threshold" as const, tDefault: 1 },
                { cardIdx: 2, label: "Top",    rField: "r_top"  as const, riskField: "risk_top"  as const, tField: "r_top_threshold" as const, tDefault: 2 },
                { cardIdx: 3, label: "Max",    rField: "r_max"  as const, riskField: "risk_max"  as const, tField: "r_max_threshold" as const, tDefault: 3 },
              ] as const).map(({ cardIdx, label, rField, riskField, tField, tDefault }) => (
                <div key={cardIdx} className={`rounded-lg p-2 border transition-colors ${
                  activeCard === cardIdx
                    ? "border-blue-500 bg-blue-500/10"
                    : "border-surface-border bg-surface-border/20"
                }`}>
                  <div className="text-[10px] text-slate-500 text-center mb-1.5 font-medium uppercase tracking-wider">{label}</div>
                  <div className="space-y-1">
                    <div>
                      <div className="text-[9px] text-slate-600 text-center">Reward R</div>
                      <input type="number" step={0.5} min={1}
                        value={session[rField] ?? (rField === "r_max" ? 5.5 : 2.5)}
                        onChange={(e) => upd({ [rField]: Number(e.target.value) })}
                        className="w-full bg-transparent text-center text-sm font-bold text-white focus:outline-none" />
                    </div>
                    <div className="border-t border-surface-border/50 pt-1">
                      <div className="text-[9px] text-slate-600 text-center">Risk %</div>
                      <input type="number" step={0.1} min={0.1} max={10}
                        value={+((session[riskField] ?? session.risk_pct ?? 0.01) * 100).toFixed(2)}
                        onChange={(e) => upd({ [riskField]: Number(e.target.value) / 100 })}
                        className="w-full bg-transparent text-center text-xs font-semibold text-slate-300 focus:outline-none" />
                    </div>
                    {tField && (
                      <div className="border-t border-surface-border/50 pt-1">
                        <div className="text-[9px] text-slate-600 text-center">La ≥ cr.</div>
                        <input type="number" step={1} min={1} max={3}
                          value={session[tField] ?? tDefault}
                          onChange={(e) => upd({ [tField]: Number(e.target.value) })}
                          className="w-full bg-transparent text-center text-[11px] text-slate-400 focus:outline-none" />
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>

            {/* Buton + diagrama R:R */}
            <div className="mb-1">
              <button
                onClick={() => setShowRRChart((v) => !v)}
                className="flex items-center gap-1.5 text-[10px] text-slate-600 hover:text-slate-400 transition-colors"
              >
                <span className="text-[8px]">{showRRChart ? "▲" : "▼"}</span>
                Vizualizare R:R proporțional
              </button>
              {showRRChart && (
                <div className="mt-2 border border-surface-border/30 rounded-lg bg-surface-border/5 p-3">
                  <RRDiagram session={session} mt5Connected={!!mt5Status?.equity} />
                </div>
              )}
            </div>

            {/* Criteriu 1 — RSI */}
            <div className="border border-surface-border rounded-lg p-3 space-y-2">
              <div className="flex items-center gap-2">
                <Toggle label="1. RSI Filter" value={session.rsi_enabled}
                  onChange={(v) => upd({ rsi_enabled: v })} />
                <InfoTooltip text={TIPS.rsi} />
              </div>
              {session.rsi_enabled && (
                <div className="grid grid-cols-4 gap-2 pt-1">
                  <NumField label="Buy min" value={session.rsi_buy_min}
                    onChange={(v) => upd({ rsi_buy_min: v })} />
                  <NumField label="Buy max" value={session.rsi_buy_max}
                    onChange={(v) => upd({ rsi_buy_max: v })} />
                  <NumField label="Sell min" value={session.rsi_sell_min}
                    onChange={(v) => upd({ rsi_sell_min: v })} />
                  <NumField label="Sell max" value={session.rsi_sell_max}
                    onChange={(v) => upd({ rsi_sell_max: v })} />
                </div>
              )}
            </div>

            {/* Criteriu 2 — EMA */}
            <div className="border border-surface-border rounded-lg p-3">
              <div className="flex items-center gap-2">
                <Toggle label="2. EMA Alignment (EMA8 > EMA20 > EMA50)" value={session.ema_alignment_enabled}
                  onChange={(v) => upd({ ema_alignment_enabled: v })} />
                <InfoTooltip text={TIPS.ema} />
              </div>
            </div>

            {/* Criteriu 3 — Corp lumânare */}
            <div className="border border-surface-border rounded-lg p-3 space-y-2">
              <div className="flex items-center gap-2">
                <Toggle label="3. Corp Lumânare (Body Strength)" value={session.body_strength_enabled ?? false}
                  onChange={(v) => upd({ body_strength_enabled: v })} />
                <InfoTooltip text={TIPS.body_strength} />
              </div>
              {(session.body_strength_enabled ?? false) && (
                <div className="pt-1 max-w-[160px]">
                  <NumField label="ATR ratio min" step={0.05}
                    value={session.body_strength_min_atr_ratio ?? 0.15}
                    onChange={(v) => upd({ body_strength_min_atr_ratio: v })} />
                </div>
              )}
            </div>
          </Section>

          {/* Setări generale */}
          <Section label="Setări Generale">
            {/* Alocare capital */}
            {(() => {
              const frac        = session.account_fraction ?? 0;
              const equity      = mt5Status?.equity ?? null;
              const capital     = equity != null ? equity * frac : null;
              const rBase       = session.risk_base ?? session.risk_pct ?? 0.01;
              const rMax        = session.risk_max  ?? 0.015;
              const riskBaseUsd = capital != null ? capital * rBase : null;
              const riskMaxUsd  = capital != null ? capital * rMax  : null;
              const fmt         = (v: number) => v >= 100 ? v.toFixed(0) : v.toFixed(2);
              return (
                <div className="mb-4 p-3 rounded-lg border border-surface-border/50 bg-surface-border/10 space-y-2">
                  <div className="flex items-center gap-3">
                    <div className="max-w-[110px]">
                      <NumField
                        label="Fracție cont"
                        value={+(frac * 100).toFixed(1)}
                        min={0} max={100} step={0.5}
                        tip={TIPS.account_fraction}
                        onChange={(v) => upd({ account_fraction: +(v / 100).toFixed(4) })}
                      />
                    </div>
                    <div className="flex-1 text-xs text-slate-500 leading-relaxed pt-3">
                      {equity != null && capital != null && riskBaseUsd != null && riskMaxUsd != null ? (
                        <>
                          <span className="text-slate-300 font-medium">${fmt(capital)}</span>
                          {" "}capital sesiune
                          {session.markets.length > 1 && (
                            <> · <span className="text-slate-400">${fmt(capital / session.markets.length)}</span>/piață</>
                          )}
                          <br />
                          risc/trade:{" "}
                          <span className="text-loss font-medium">~${fmt(riskBaseUsd)}</span>
                          {riskBaseUsd !== riskMaxUsd && (
                            <> → <span className="text-warn font-medium">~${fmt(riskMaxUsd)}</span></>
                          )}
                          <span className="text-slate-600"> (Base→Max)</span>
                          {session.markets.length > 0 && (
                            <span className="text-slate-600"> × max {session.markets.length} piețe simultan</span>
                          )}
                          {/* Lot minim per piată */}
                          {session.markets.length > 0 && (() => {
                            const capitalPerMarket = capital / session.markets.length;
                            const rows = session.markets.map(m => {
                              const spec = MARKET_SPECS[m.toUpperCase()];
                              if (!spec) return null;
                              const over = calcOvershoot(capitalPerMarket, rBase, spec);
                              return { m, spec, over };
                            }).filter(Boolean) as { m: string; spec: typeof MARKET_SPECS[string]; over: ReturnType<typeof calcOvershoot> }[];
                            if (rows.length === 0) return null;
                            return (
                              <div className="mt-2 pt-2 border-t border-surface-border/30">
                                <div className="flex items-center gap-1 text-[10px] text-slate-600 uppercase tracking-wider mb-1">
                                  Lot minim broker (estimat live)
                                  <InfoTooltip
                                    position="above"
                                    align="right"
                                    wide
                                    text={
                                      "Brokerul impune un volum minim per ordin (ex: 0.1 loturi pentru indici).\n\n" +
                                      "Dacă lotajul calculat din (capital × risc%) e sub acest minim, botul plasează automat lotajul minim — " +
                                      "riscând mai mult decât intenționat.\n\n" +
                                      "Valorile sunt estimații bazate pe un SL tipic pentru această strategie și cursuri valutare aproximative."
                                    }
                                  />
                                </div>
                                <div className="space-y-0.5">
                                  {rows.map(({ m, spec, over }) => (
                                    <div key={m} className="flex items-center gap-2 text-[11px]">
                                      <span className="font-mono text-slate-400 w-16 flex-shrink-0">{m}</span>
                                      <span className="text-slate-600">
                                        min {spec.volMin} lot
                                        <InfoTooltip
                                          position="above"
                                          text={`Volumul minim acceptat de broker pentru ${m}. Sub această valoare, ordinul este respins.`}
                                        />
                                      </span>
                                      {over ? (
                                        <>
                                          <span className="text-slate-600">→</span>
                                          <span className={over.factor >= 8 ? "text-loss" : "text-warn"}>
                                            ~${over.actualRisk.toFixed(0)} real
                                            <InfoTooltip
                                              position="above"
                                              wide
                                              text={
                                                `Riscul real estimat la lotajul minim de ${spec.volMin} loturi.\n\n` +
                                                `Intenționat: $${over.intendedRisk.toFixed(2)} (capital/piață × risc%)\n` +
                                                `Real (lot min): ~$${over.actualRisk.toFixed(0)}\n\n` +
                                                "Estimat pe SL tipic al strategiei — variază per semnal."
                                              }
                                            />
                                          </span>
                                          <span className={`font-mono text-[10px] ${over.factor >= 8 ? "text-loss/70" : "text-warn/70"}`}>
                                            ({over.factor.toFixed(0)}× int.
                                            <InfoTooltip
                                              position="above"
                                              wide
                                              text={
                                                `De câte ori riscul real depășește cel intenționat din cauza lotajului minim.\n\n` +
                                                `${over.factor.toFixed(0)}× = riscul real este de ~${over.factor.toFixed(0)} ori mai mare decât cel configurat.\n\n` +
                                                "Portocaliu = 2–8×, Roșu = peste 8×. Problema dispare când contul crește suficient pentru a genera natural lotajul minim."
                                              }
                                            />
                                            )
                                          </span>
                                        </>
                                      ) : (
                                        <span className="text-profit text-[10px]">
                                          ✓ lot calc. ok
                                          <InfoTooltip
                                            position="above"
                                            text="Lotajul calculat din risc% × capital depășește minimul brokerului — riscul real este aproape de cel intenționat."
                                          />
                                        </span>
                                      )}
                                    </div>
                                  ))}
                                </div>
                              </div>
                            );
                          })()}
                        </>
                      ) : (
                        <span className="text-slate-600">
                          {frac > 0
                            ? `${(frac * 100).toFixed(1)}% din equity MT5`
                            : "0% — sesiunea nu alocă capital"}
                          {equity == null ? " (MT5 deconectat)" : ""}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              );
            })()}
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Toggle label="Execute trades (LIVE)" value={session.execute_trades}
                  tip={TIPS.execute_trades} onChange={(v) => upd({ execute_trades: v })} />
              </div>
              <div>
                <NumField label="Circuit breaker" value={session.circuit_breaker} min={1}
                  tip={TIPS.circuit_breaker} onChange={(v) => upd({ circuit_breaker: v })} />
              </div>
            </div>
          </Section>

          {/* Skip ore */}
          <Section label="Skip ore (server MT5)" tip={TIPS.skip_hours}>
            <div className="flex flex-wrap gap-1">
              {HOURS.map((h) => (
                <button key={h} onClick={() => toggleHour(h)}
                  className={`w-7 h-6 text-xs rounded transition-colors ${
                    session.skip_hours.includes(h)
                      ? "bg-warn/80 text-black font-medium"
                      : "bg-surface-border/50 text-slate-400 hover:bg-surface-border"
                  }`}>{h}</button>
              ))}
            </div>
          </Section>

          {/* Skip zile */}
          <Section label="Skip zile" tip={TIPS.skip_weekdays}>
            <div className="flex gap-1">
              {WD_KEYS.map((d) => (
                <button key={d} onClick={() => toggleWd(d)}
                  className={`px-2 py-1 text-xs rounded transition-colors ${
                    session.skip_weekdays.includes(d)
                      ? "bg-warn/80 text-black font-medium"
                      : "bg-surface-border/50 text-slate-400 hover:bg-surface-border"
                  }`}>{meta.weekday_names[String(d)]}</button>
              ))}
            </div>
          </Section>

          {/* Vineri close */}
          <Section label="Închidere Vineri" tip={TIPS.friday_close}>
            <div className="space-y-2">
              <Toggle
                label="Închidere automată Vineri"
                value={session.friday_close_enabled ?? true}
                onChange={(v) => upd({ friday_close_enabled: v })}
              />
              {(session.friday_close_enabled ?? true) && (
                <div className="space-y-1.5">
                  <div className="max-w-[140px]">
                    <NumField
                      label="Oră închidere"
                      value={session.friday_close_hour ?? 20}
                      min={0} max={23}
                      onChange={(v) => upd({ friday_close_hour: v })}
                    />
                  </div>
                  <p className="text-[10px] text-slate-600">
                    Sesiunile crypto (ex: BTC) pot dezactiva această regulă — piața rulează și sâmbătă/duminică.
                  </p>
                </div>
              )}
            </div>
          </Section>

          {/* Protecție Știri */}
          <Section label="Protecție Știri" tip={TIPS.news_protection}>
            <div className="space-y-2">
              <Toggle
                label="Pauză automată la știri"
                value={session.news_protection_enabled ?? false}
                onChange={(v) => upd({ news_protection_enabled: v })}
              />
              {(session.news_protection_enabled ?? false) && (
                <div className="space-y-3 pt-1">
                  <div className="space-y-1.5">
                    <div className="text-xs text-slate-500">Impact minim <InfoTooltip text={TIPS.news_impact} /></div>
                    <div className="flex gap-1">
                      {[
                        { v: 1, label: "Scăzut" },
                        { v: 2, label: "Mediu" },
                        { v: 3, label: "Ridicat" },
                      ].map(({ v, label }) => (
                        <button
                          key={v}
                          onClick={() => upd({ news_impact_level: v })}
                          className={`text-xs px-2 py-1 rounded border transition-colors ${
                            (session.news_impact_level ?? 3) === v
                              ? "bg-amber-600/80 border-amber-500 text-white"
                              : "bg-transparent border-surface-border text-slate-400 hover:border-slate-500"
                          }`}
                        >
                          {v} — {label}
                        </button>
                      ))}
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="max-w-[130px]">
                      <NumField
                        label="Pre-știre (min)"
                        value={session.news_pre_minutes ?? 15}
                        min={0} max={120}
                        tip={TIPS.news_pre}
                        onChange={(v) => upd({ news_pre_minutes: v })}
                      />
                    </div>
                    <div className="max-w-[130px]">
                      <NumField
                        label="Post-știre (min)"
                        value={session.news_post_minutes ?? 15}
                        min={0} max={120}
                        tip={TIPS.news_post}
                        onChange={(v) => upd({ news_post_minutes: v })}
                      />
                    </div>
                  </div>
                  <p className="text-[10px] text-slate-600">
                    Sursa principală: ForexFactory (fără cheie API). Backup: MT5 calendar built-in. Verificare la fiecare 5 min.
                  </p>
                </div>
              )}
            </div>
          </Section>

          {/* Pozitii Simultane */}
          <Section label="Poziții Simultane" tip={TIPS.max_concurrent}>
            <div className="space-y-3">
              <div className="max-w-[160px]">
                <NumField
                  label="Max poziții per piață"
                  value={session.max_concurrent_per_market ?? 1}
                  min={1} max={5}
                  tip={TIPS.max_concurrent}
                  onChange={(v) => upd({ max_concurrent_per_market: v })}
                />
              </div>
              <p className="text-[10px] text-slate-600">
                Default: 1 (o singură poziție pending/activă per simbol). Crește dacă vrei mai multe
                intrări pe același simbol simultan — include atât ordine netriggerate cât și pozițiile deschise.
              </p>
              {(session.max_concurrent_per_market ?? 1) >= 2 && (
                <div className="max-w-[160px]">
                  <NumField
                    label="Bare minim între ordine"
                    value={session.min_bars_between_trades ?? 0}
                    min={0} max={50}
                    tip={TIPS.min_bars_between}
                    onChange={(v) => upd({ min_bars_between_trades: v })}
                  />
                </div>
              )}
              {(session.max_concurrent_per_market ?? 1) >= 2 && (session.min_bars_between_trades ?? 0) > 0 && (
                <p className="text-[10px] text-slate-600">
                  Ex: {session.min_bars_between_trades} bare {session.entry_tf} ≈{" "}
                  {session.entry_tf === "H1" ? `${session.min_bars_between_trades}h`
                    : session.entry_tf === "H4" ? `${(session.min_bars_between_trades ?? 0) * 4}h`
                    : session.entry_tf === "M30" ? `${Math.round((session.min_bars_between_trades ?? 0) * 0.5)}h`
                    : `${Math.round((session.min_bars_between_trades ?? 0) * 15 / 60 * 10) / 10}h`} distanță minimă.
                </p>
              )}
            </div>
          </Section>

          {/* Break-Even */}
          <Section label="Break-Even" tip={[
            "Mută automat SL-ul în profit când trade-ul avansează.",
            "",
            "Faza 1: când prețul atinge trigger% din TP și se întoarce → SL mutat la lock1% din TP.",
            "Faza 2: dacă prețul scade în zona 30-40% dar revine la trigger% și se întoarce din nou → SL mutat la lock2% din TP.",
            "",
            "Dezactivat implicit — nu afectează baselines.",
          ].join("\n")}>
            <div className="space-y-3">
              <Toggle
                label="Activează Break-Even"
                value={session.break_even_enabled ?? false}
                onChange={(v) => upd({ break_even_enabled: v })}
              />
              {(session.break_even_enabled) && (
                <div className="space-y-3 pl-2 border-l-2 border-surface-border">
                  <div className="grid grid-cols-2 gap-3">
                    <NumField label="Trigger TP%" value={session.be_trigger_pct ?? 80} min={50} max={99}
                      tip="Prețul trebuie să atingă X% din TP pentru a arma break-even."
                      onChange={(v) => upd({ be_trigger_pct: v })} />
                    <NumField label="Lock SL Faza 1%" value={session.be_lock1_pct ?? 30} min={5} max={60}
                      tip="SL mutat la X% din distanța TP la faza 1."
                      onChange={(v) => upd({ be_lock1_pct: v })} />
                  </div>

                  {/* Faza 2 — optional */}
                  <Toggle
                    label="Activează Faza 2 (opțional)"
                    value={session.be_phase2_enabled ?? true}
                    onChange={(v) => upd({ be_phase2_enabled: v })}
                  />
                  {(session.be_phase2_enabled ?? true) && (
                    <div className="grid grid-cols-2 gap-3">
                      <NumField label="Zonă Faza 2%" value={session.be_phase2_zone_pct ?? 40} min={20} max={70}
                        tip="Limita superioară a zonei de retragere Faza 2 (lock1–X%)."
                        onChange={(v) => upd({ be_phase2_zone_pct: v })} />
                      <NumField label="Lock SL Faza 2%" value={session.be_lock2_pct ?? 50} min={30} max={80}
                        tip="SL mutat la X% din distanța TP la faza 2."
                        onChange={(v) => upd({ be_lock2_pct: v })} />
                    </div>
                  )}

                  <p className="text-[10px] text-slate-600">
                    Notificări Telegram separate la Faza 1 și Faza 2. Se aplică în backtest și live.
                  </p>
                </div>
              )}
            </div>
          </Section>

          {/* Flag Pattern */}
          <Section label="Strategia Flag" tip="Pattern independent de pullback-in-trend. Bull Flag (LONG): pol ascendent + consolidare + breakout sus. Bear Flag (SHORT): pol descendent + consolidare + breakout jos. Statistic: 65–72% win rate în piețe trending cu filtru EMA200 (Bulkowski 2002).">
            <div className="space-y-3">
              <div className="flex items-center gap-1">
                <Toggle
                  label="Activează Flag Pattern"
                  value={session.flag_enabled ?? false}
                  onChange={(v) => upd({ flag_enabled: v })}
                />
                <ImageTooltip src="/diagrama_flag.png" alt="Diagrama Bull Flag" position="above" />
              </div>
              {session.flag_enabled && (
                <div className="grid grid-cols-2 gap-3 pl-2 border-l-2 border-surface-border">
                  <NumField
                    label="R/R Reward"
                    value={session.flag_r_ratio ?? 2.0}
                    min={1.0} max={10.0} step={0.5}
                    tip="Raportul reward/risk pentru semnalele flag. Independent de reward-ladder-ul pullback."
                    onChange={(v) => upd({ flag_r_ratio: v })}
                  />
                  <NumField
                    label="Risk % per trade"
                    value={(session.flag_risk_pct ?? 0.01) * 100}
                    min={0.1} max={5.0} step={0.1}
                    tip="Risk % din capital pentru semnalele flag. Independent de risk% pullback."
                    onChange={(v) => upd({ flag_risk_pct: v / 100 })}
                  />
                </div>
              )}
              {session.flag_enabled && (
                <p className="text-[10px] text-slate-600">
                  Semnalele flag sunt independente de pullback. ID prefix: <code>FLG</code>. Notificare Telegram separată.
                </p>
              )}
            </div>
          </Section>

          {/* Inside Bar Breakout */}
          <Section label="Strategia Inside Bar" tip="Pattern independent. O bară complet în interiorul barei anterioare (mother bar), urmată de un breakout în direcția trendului. Statistic: 60–68% win rate în piețe trending (Bulkowski 2021).">
            <div className="space-y-3">
              <div className="flex items-center gap-1">
                <Toggle
                  label="Activează Inside Bar Breakout"
                  value={session.inside_bar_enabled ?? false}
                  onChange={(v) => upd({ inside_bar_enabled: v })}
                />
                <ImageTooltip src="/diagrama_inside_bar.png" alt="Diagrama Inside Bar Breakout" position="above" />
              </div>
              {session.inside_bar_enabled && (
                <div className="grid grid-cols-2 gap-3 pl-2 border-l-2 border-surface-border">
                  <NumField
                    label="R/R Reward"
                    value={session.inside_bar_r_ratio ?? 2.0}
                    min={1.0} max={10.0} step={0.5}
                    tip="Raportul reward/risk pentru semnalele inside bar."
                    onChange={(v) => upd({ inside_bar_r_ratio: v })}
                  />
                  <NumField
                    label="Risk % per trade"
                    value={(session.inside_bar_risk_pct ?? 0.01) * 100}
                    min={0.1} max={5.0} step={0.1}
                    tip="Risk % din capital pentru semnalele inside bar."
                    onChange={(v) => upd({ inside_bar_risk_pct: v / 100 })}
                  />
                </div>
              )}
              {session.inside_bar_enabled && (
                <p className="text-[10px] text-slate-600">
                  Semnalele inside bar sunt independente de pullback și flag. ID prefix: <code>IB</code>. Notificare Telegram separată.
                </p>
              )}
            </div>
          </Section>

          {/* Backtest */}
          <Section label="Backtest">
            <BacktestPanel
              session={session}
              onJobStarted={onJobStarted}
              onSaveAndNavigate={onSaveAndNavigate}
              onDownloadStarted={onDownloadStarted}
              profileStartBalance={profileStartBalance}
            />
          </Section>
        </div>
      )}
    </div>
  );
}

// ── sub-components ──────────────────────────────────────────────

function Section({ label, tip, children }: {
  label: string; tip?: string; children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center text-xs text-slate-500 font-medium uppercase tracking-wider">
        {label}{tip && <InfoTooltip text={tip} />}
      </div>
      {children}
    </div>
  );
}

function SegControl({ options, value, onChange }: {
  options: string[]; value: string; onChange: (v: string) => void;
}) {
  return (
    <div className="flex gap-1 flex-wrap">
      {options.map((o) => (
        <button key={o} onClick={() => onChange(o)}
          className={`text-xs px-2 py-0.5 rounded border transition-colors ${
            value === o
              ? "bg-blue-600 border-blue-500 text-white"
              : "bg-transparent border-surface-border text-slate-400 hover:border-slate-500"
          }`}>{o}</button>
      ))}
    </div>
  );
}

function NumField({ label, value, min, max, step = 1, tip, onChange }: {
  label: string; value: number; min?: number; max?: number;
  step?: number; tip?: string; onChange: (v: number) => void;
}) {
  return (
    <div className="space-y-1">
      <label className="flex items-center text-xs text-slate-500">
        {label}{tip && <InfoTooltip text={tip} />}
      </label>
      <input type="number" value={value} min={min} max={max} step={step}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full bg-surface border border-surface-border rounded px-2 py-1 text-xs text-white focus:outline-none focus:border-blue-500" />
    </div>
  );
}

function Toggle({ label, value, tip, onChange }: {
  label: string; value: boolean; tip?: string; onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex items-center gap-2 cursor-pointer select-none">
      <div onClick={() => onChange(!value)}
        className={`w-8 h-4 rounded-full transition-colors relative flex-shrink-0 ${value ? "bg-blue-600" : "bg-surface-border"}`}>
        <div className={`absolute top-0.5 w-3 h-3 bg-white rounded-full shadow transition-transform ${value ? "translate-x-4" : "translate-x-0.5"}`} />
      </div>
      <span className="text-xs text-slate-300">{label}</span>
      {tip && <InfoTooltip text={tip} />}
    </label>
  );
}
