import { useState, useMemo } from "react";
import { Pause, Play } from "lucide-react";
import type { ProfileSession, Meta } from "../api/types";
import { useMt5Markets } from "../api/hooks";
import { BacktestPanel } from "./BacktestPanel";
import { InfoTooltip } from "./InfoTooltip";

interface Props {
  session: ProfileSession;
  meta: Meta;
  onChange: (updated: ProfileSession) => void;
  onRemove?: () => void;
  onJobStarted?: () => void;
  paused?: boolean;
  onPauseToggle?: () => void;
}

const HOURS = Array.from({ length: 24 }, (_, i) => i);
const WD_KEYS = [0, 1, 2, 3, 4, 5, 6] as const;

const TIPS = {
  markets:       "Piețele pe care sesiunea generează semnale. Bifează simbolurile disponibile în contul tău MT5.",
  mt5_search:    "Caută orice simbol disponibil în contul MT5 curent (forex, indici, crypto, materii prime). MT5 trebuie să fie deschis și conectat.",
  entry_tf:      "Timeframe-ul barei de intrare — semnalul este detectat pe acest TF.",
  trend_tf:      "Timeframe mai mare folosit pentru filtrarea trendului (EMA200). Trebuie să fie > Entry TF.",
  direction:     "LONG = doar cumpărări; SHORT = doar vânzări; BOTH = ambele direcții.",
  pullback_window: "Numărul maxim de bare în care se caută un pullback valid după un Higher High. Valori mici = setup-uri mai stricte.",
  expire_bars:   "Ordinul pending se anulează automat după N bare dacă nu a fost triggerat.",
  criteria:      "3 criterii opționale care cresc R/R-ul. Fiecare nivel R are un prag configurabil (La ≥ N criterii). Praguri default: R-mid la ≥1, R-top la ≥2, R-max la ≥3. Criteriile sunt independente — activează oricare combinație.",
  rsi:           "RSI filtrează entry-urile în zone de supraCumpărare/supraVânzare. Gama recomandată: buy 40–65, sell 35–60.",
  ema:           "EMA8 > EMA20 > EMA50 pe TF de intrare — confirmă că trendul de scurt termen e aliniat cu cel de mediu termen.",
  body_strength: "Corp lumânare: bara de intrare trebuie să aibă un corp (close−open) mai mare decât ATR × ratio în direcția trade-ului. Confirmă că breakout-ul are impuls. Dezactivat implicit. Ratio recomandat: 0.10–0.25.",
  circuit_breaker: "Oprește tranzacționarea după N pierderi consecutive în aceeași zi. Repornește la miezul nopții.",
  risk_pct:      "Procentul din equity riscat per tranzacție. Equity-ul este citit din MT5 la fiecare ordin.",
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
};

export function SessionEditor({ session, meta, onChange, onRemove, onJobStarted, paused, onPauseToggle }: Props) {
  const [open, setOpen]           = useState(false);
  const [confirmRemove, setConfirmRemove] = useState(false);
  const [showMt5Search, setShowMt5Search] = useState(false);
  const [mt5Query, setMt5Query]   = useState("");

  const { data: mt5Data, isLoading: loadingMt5 } = useMt5Markets();

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
    <div className="bg-surface-card rounded-xl border border-surface-border overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-3 hover:bg-surface-border/20 transition-colors">
        <button className="flex-1 flex items-center gap-3 text-left" onClick={() => setOpen((o) => !o)}>
          <span className="text-sm font-semibold text-white">{session.label || session.id}</span>
          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${dirBadgeColor}`}>
            {session.direction}
          </span>
          <span className={`text-xs px-2 py-0.5 rounded-full ${session.execute_trades ? "bg-blue-500/20 text-blue-300" : "bg-slate-700 text-slate-400"}`}>
            {session.execute_trades ? "LIVE" : "OBS"}
          </span>
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
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Toggle label="Execute trades (LIVE)" value={session.execute_trades}
                  tip={TIPS.execute_trades} onChange={(v) => upd({ execute_trades: v })} />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <NumField label="Circuit breaker" value={session.circuit_breaker} min={1}
                  tip={TIPS.circuit_breaker} onChange={(v) => upd({ circuit_breaker: v })} />
                <NumField label="Risk %" value={+(session.risk_pct * 100).toFixed(2)} step={0.1}
                  tip={TIPS.risk_pct} onChange={(v) => upd({ risk_pct: v / 100 })} />
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

          {/* Backtest */}
          <Section label="Backtest">
            <BacktestPanel session={session} onJobStarted={onJobStarted} />
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
