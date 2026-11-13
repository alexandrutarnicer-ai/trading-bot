import { useState } from "react";
import { CalendarClock, Loader2, Play, Square, FlaskConical } from "lucide-react";
import { PositionSizingCard } from "../components/PositionSizingCard";
import { useDailyConfig, useDailyMarketPreview, useDailyPresets, useDailySaveMarket, useDailySaveSlot, useDailyStatus,
  useDailyTrades, useDailyLogs, useDailyStart, useDailyStop, useMt5Markets, useDailyMarketMode,
  useDailySaveProfitLock, useDailySaveSizing, useDailySaveSessions, useDailySaveAlert, useBacktestRefresh } from "../api/hooks";
import type { DailyBacktestAuto, DailyMarketConfig, DailyMarketMode, DailyMarketStatus, DailyQuickBacktest, DailyReentry,
  DailyScore } from "../api/types";
import { BacktestAutoBadge } from "../components/BacktestAutoBadge";

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
  stopped:       { label: "Engine oprit", cls: "bg-slate-700/40 text-slate-500" },
  paused:        { label: "Pe pauză", cls: "bg-amber-500/15 text-amber-300" },
};

const fmt = (v: number | undefined) => (v == null ? "—" : Math.abs(v) >= 100 ? v.toFixed(2) : v.toFixed(5));
const fmtR = (v: number | null | undefined) => (v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(2)}R`);
const rCls = (v: number | null | undefined) => (v == null ? "text-slate-400" : v > 0 ? "text-profit" : v < 0 ? "text-loss" : "text-slate-300");

// Rezultatele cercetarii (scripts/research_daily/orb_rr_reentry.py, ~10–14 ani M5, costuri reale) — afisate langa optiuni
// Profit Lock — backtest pe tot istoricul M5 (scripts/research_daily/daily_profit_lock.py, costuri reale, 2026-11-12)
const PLOCK_RESEARCH: Record<string, string> = {
  DE40: "Backtest (tot istoricul M5, configurația curentă cu re-intrări): fără Profit Lock +0,095R/trade, DD −66R; " +
        "3,5→3R +0,046 · 4,5→4R +0,072 · 5→4R +0,095 (DD −57R) · 6→5R +0,084 · 8→6R +0,089. La 4,5→4R profitul protejat " +
        "(+291R) e mai mic decât cel pierdut din trade-urile care ar fi mers mai departe (−371R). Doar 5→4R e la egalitate.",
  US500: "Backtest (tot istoricul M5, configurația curentă cu re-intrări): fără Profit Lock +0,046R/trade; 3,5→3R +0,011 · " +
         "4,5→4R +0,022 · 6→5R +0,035 · 8→6R +0,043 — niciun prag nu e mai bun decât strategia actuală.",
};

const MODE_UI: Record<DailyMarketMode, { label: string; on: string }> = {
  live:   { label: "LIVE",   on: "bg-loss/25 text-loss" },
  shadow: { label: "SHADOW", on: "bg-violet-500/25 text-violet-200" },
  pause:  { label: "PAUZĂ",  on: "bg-amber-500/25 text-amber-200" },
};

const RESEARCH: Record<string, { rr: string; re: string }> = {
  GBPUSD: { rr: "Backtest: fără TP +0,075R/trade; 2R −0,016 · 3R 0,000 · 4R −0,005 — ținta fixă taie trade-urile mari.",
            re: "Backtest: re-intrări (prima oră, max 3, stop la 2 pierderi) → +0,027R/trade (față de +0,075), 6,6 vs 4,6 trade-uri/săpt. Fără stopul pe pierderi: +0,015R." },
  US500:  { rr: "Backtest: fără TP +0,059R/trade (KEEP); 2R +0,006 · 3R +0,009 · 4R +0,030 — ținta fixă taie zilele de trend.",
            re: "Backtest: re-intrări în prima oră → +0,049R/trade (față de +0,059), 5,3 vs 4,4 trade-uri/săpt. Fereastră 90 / 120 min: +0,035 / +0,038R." },
};

const fmtBt = (b?: DailyQuickBacktest | null) => !b ? "—" : !b.ok ? (b.detail ?? "indisponibil") : !b.trades ? (b.detail ?? "0 trade-uri") :
  `${b.trades} trade-uri (${b.per_week}/săpt) · ${fmtR(b.expectancy_R)}/trade · WR ${Math.round((b.win_rate ?? 0) * 100)}% · ` +
  `DD ${b.max_dd_R}R · verdict ${b.verdict ?? "—"} (train ${fmtR(b.train_R)} / test ${fmtR(b.test_R)}) · ${b.period}`;

/** Schimbarea pietei unui slot: bursa (sablon testat) + simbolul din MT5 + costuri auto din spread; previzualizare cu
 *  backtest rapid inainte de salvare. */
function ChangeMarket({ slot, current }: { slot: number; current: DailyMarketConfig }) {
  const { data: pre } = useDailyPresets();
  const { data: mk } = useMt5Markets();
  const preview = useDailyMarketPreview();
  const save = useDailySaveSlot();
  const [open, setOpen] = useState(false);
  const [symbol, setSymbol] = useState(current.symbol);
  const [preset, setPreset] = useState(current.preset ?? "london");
  const [mode, setMode] = useState<"auto" | "manual">("auto");
  const [slip, setSlip] = useState<number>(current.slip);
  const [comm, setComm] = useState<number>(current.comm);
  const pv = preview.data;
  const body = { slot, symbol: symbol.trim().toUpperCase(), preset, costs_mode: mode,
                 ...(mode === "manual" ? { slip, comm } : {}) };
  const sameAsNow = body.symbol === current.symbol && preset === current.preset;
  const btn = (on: boolean) => `px-2 py-0.5 rounded border ${on ? "border-cyan-500/50 text-cyan-200" : "border-surface-border text-slate-500"}`;
  return (
    <div className="space-y-1.5">
      <button onClick={() => setOpen(!open)} className="text-slate-400 hover:text-white">
        {open ? "▾" : "▸"} Schimbă piața slotului {slot + 1} · acum {current.symbol} ({pre?.presets?.[current.preset ?? ""]?.label ?? current.tz})
        · costuri {current.costs_mode === "auto" ? "auto" : "fixe"}: slip {current.slip} · comision {current.comm}
      </button>
      {open && (
        <div className="space-y-2 pl-2 border-l-2 border-surface-border">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-slate-300 w-16">Bursa</span>
            {Object.entries(pre?.presets ?? {}).map(([k, p]) => (
              <button key={k} className={btn(preset === k)} onClick={() => setPreset(k)}
                title={`${p.open}–${p.last_bar} ${p.tz} · interval ${p.or_minutes} min · ${p.entry}`}>{p.label}</button>
            ))}
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-slate-300 w-16">Piața</span>
            <input list={`daily-syms-${slot}`} value={symbol} onChange={e => setSymbol(e.target.value)}
              className="w-40 bg-surface-card border border-surface-border rounded px-2 py-0.5 text-white" />
            <datalist id={`daily-syms-${slot}`}>
              {(mk?.items ?? []).filter(x => x.tradable).map(x => <option key={x.name} value={x.name}>{x.description}</option>)}
            </datalist>
            <span className="text-slate-300 ml-2">Costuri</span>
            <button className={btn(mode === "auto")} onClick={() => setMode("auto")}>Auto (din spread-ul MT5)</button>
            <button className={btn(mode === "manual")} onClick={() => setMode("manual")}>Manual</button>
            {mode === "manual" && (
              <span className="flex items-center gap-1">slip
                <input type="number" step="any" value={slip} onChange={e => setSlip(Number(e.target.value))}
                  className="w-20 bg-surface-card border border-surface-border rounded px-1" /> comision
                <input type="number" step="any" value={comm} onChange={e => setComm(Number(e.target.value))}
                  className="w-20 bg-surface-card border border-surface-border rounded px-1" /> (unități de preț)</span>
            )}
          </div>
          <div className="text-[10px] text-slate-500">
            Auto: slippage = 25% din spread-ul live; „comision” = diferența dintre spread-ul live și cel din istoricul barelor
            (markup-ul contului — pe FX Standard ~0,8–0,9 pip, pe indici ~0). Ora, intervalul și modul vin din bursa aleasă
            (varianta testată). Re-intrările / R:R ale slotului se păstrează.
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => preview.mutate(body)} disabled={preview.isPending || !body.symbol}
              className="px-3 py-1 rounded border border-cyan-500/40 text-cyan-200 disabled:opacity-40">
              {preview.isPending ? "Calculez (~3 ani M5)…" : "Previzualizează (costuri + backtest)"}
            </button>
            <button disabled={!pv || save.isPending || sameAsNow && mode === (current.costs_mode ?? "manual")}
              onClick={() => window.confirm(`Schimbi slotul ${slot + 1}: ${current.symbol} → ${body.symbol} (${pre?.presets?.[preset]?.label})?`)
                && save.mutate(body, { onSuccess: () => { setOpen(false); preview.reset(); } })}
              className="px-3 py-1 rounded bg-cyan-500/20 text-cyan-200 border border-cyan-500/40 font-semibold disabled:opacity-40">
              {save.isPending ? "Salvez…" : "Salvează piața"}</button>
            {(preview.isError || save.isError) && <span className="text-loss">{((preview.error ?? save.error) as Error).message}</span>}
          </div>
          {pv && (
            <div className="rounded border border-surface-border bg-surface-card px-2 py-1.5 space-y-0.5">
              <div className="text-slate-300">{pv.market.symbol} — {pv.description} · {pv.market.open}–{pv.market.last_bar} ({pv.market.tz}) ·
                interval {pv.market.or_minutes} min · {pv.market.entry}</div>
              <div className="text-slate-400">spread live {pv.costs.spread_live_points} points (istoric {pv.costs.spread_hist ?? "—"}) ·
                markup {pv.costs.markup_points} points → slip {pv.costs.slip} · comision {pv.costs.comm}</div>
              <div className={pv.margin_min_lot != null && pv.margin_min_lot > 75 ? "text-loss" : "text-slate-400"}>
                lot minim {pv.volume_min} · marja la lotul minim {pv.margin_min_lot ?? "—"} $
                {pv.margin_min_lot != null && pv.margin_min_lot > 75 && " — mare pentru contul actual (~206 $, partajat)"}</div>
              <div className="text-white">Backtest ~3 ani: {fmtBt(pv.backtest)}</div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function MarketSettings({ symbol, orMinutes, slot }: { symbol: string; orMinutes?: number; slot?: number }) {
  const { data } = useDailyConfig();
  const save = useDailySaveMarket();
  const cfg = data?.markets?.find((x: DailyMarketConfig) => x.symbol === symbol);
  const [open, setOpen] = useState(false);
  const [rr, setRr] = useState<number | null | undefined>(undefined);
  const [re, setRe] = useState<DailyReentry | undefined>(undefined);
  if (!cfg) return null;
  const curRr = rr === undefined ? cfg.rr : rr;
  const curRe = re ?? cfg.reentry;
  const dirty = rr !== undefined || re !== undefined;
  const set = (patch: Partial<DailyReentry>) => setRe({ ...curRe, ...patch });
  const btn = (on: boolean) => `px-2 py-0.5 rounded border ${on ? "border-cyan-500/50 text-cyan-200" : "border-surface-border text-slate-500"}`;
  const num = (v: string) => (v === "" ? 0 : Number(v));
  const info = RESEARCH[symbol];
  const winBeforeOr = (orMinutes ?? 0) >= curRe.window_min;
  return (
    <div className="border-t border-surface-border pt-2 text-[11px] space-y-2">
      {slot != null && <ChangeMarket key={`${cfg.symbol}-${cfg.preset}`} slot={slot} current={cfg} />}
      <button onClick={() => setOpen(!open)} className="text-slate-400 hover:text-white">
        {open ? "▾" : "▸"} Opțiuni: R:R {cfg.rr ? `${cfg.rr}R` : "fără TP"} · re-intrări {cfg.reentry.enabled ? "PORNITE" : "oprite"}
      </button>
      {open && (
        <div className="space-y-2 pl-2 border-l-2 border-surface-border">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-slate-300 w-24">Țintă (R:R)</span>
            {[null, 2, 3, 4].map(v => (
              <button key={String(v)} className={btn(curRr === v)} onClick={() => setRr(v)}>{v ? `${v}R` : "fără TP (actual)"}</button>
            ))}
            <input type="number" min={0.5} max={10} step={0.5} value={curRr ?? ""} placeholder="alt R"
              onChange={e => setRr(e.target.value === "" ? null : num(e.target.value))}
              className="w-16 bg-surface-card border border-surface-border rounded px-2 py-0.5" />
          </div>
          {info && <div className="text-[10px] text-slate-500">{info.rr}</div>}
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={curRe.enabled} onChange={e => set({ enabled: e.target.checked })} />
            <span className="text-slate-300">Re-intrări în fereastra fierbinte</span>
            <span className="text-slate-500">(oprit = un trade pe zi, ca până acum)</span>
          </label>
          {curRe.enabled && (
            <div className="grid grid-cols-2 gap-x-3 gap-y-1">
              <label className="flex items-center gap-1">fereastră
                <input type="number" min={15} max={240} step={5} value={curRe.window_min} onChange={e => set({ window_min: num(e.target.value) })}
                  className="w-14 bg-surface-card border border-surface-border rounded px-1" /> min de la deschidere</label>
              <label className="flex items-center gap-1">max
                <input type="number" min={2} max={10} value={curRe.max_trades} onChange={e => set({ max_trades: num(e.target.value) })}
                  className="w-12 bg-surface-card border border-surface-border rounded px-1" /> trade-uri / zi</label>
              <label className="flex items-center gap-1">stop după
                <input type="number" min={0} max={10} value={curRe.max_consec_losses} onChange={e => set({ max_consec_losses: num(e.target.value) })}
                  className="w-12 bg-surface-card border border-surface-border rounded px-1" /> pierderi la rând <span className="text-slate-500">(0 = fără)</span></label>
              <label className="flex items-center gap-1">pauză
                <input type="number" min={1} max={12} value={curRe.cooldown_bars} onChange={e => set({ cooldown_bars: num(e.target.value) })}
                  className="w-12 bg-surface-card border border-surface-border rounded px-1" /> lumânări M5 după ieșire</label>
            </div>
          )}
          {curRe.enabled && (
            <div className="text-[10px] text-slate-500">
              Un singur trade deschis odată. După ce se închide (SL sau TP), noul trade intră doar la o NOUĂ rupere a aceluiași interval de
              deschidere (oricare margine; preț deja dincolo de margine → intrare imediată), dacă începe în primele {curRe.window_min} min
              de la deschidere.
              {winBeforeOr && <span className="text-loss"> Fereastra ({curRe.window_min} min) nu depășește intervalul de deschidere
                ({orMinutes} min) → re-intrările nu au timp să apară; mărește fereastra.</span>}
            </div>
          )}
          {curRe.enabled && info && <div className="text-[10px] text-yellow-300/90">{info.re}</div>}
          <ProfitLockSettings symbol={symbol} cfg={cfg} />
          <SessionsSettings symbol={symbol} cfg={cfg} />
          <div className="flex items-center gap-2">
            <button disabled={!dirty || save.isPending}
              onClick={() => save.mutate({ symbol, rr: curRr ?? null, reentry: curRe }, { onSuccess: () => { setRr(undefined); setRe(undefined); } })}
              className="px-3 py-1 rounded bg-cyan-500/20 text-cyan-200 border border-cyan-500/40 font-semibold disabled:opacity-40">Salvează</button>
            {dirty && <button onClick={() => { setRr(undefined); setRe(undefined); }} className="px-3 py-1 rounded border border-surface-border text-slate-400">Renunță</button>}
            <span className="text-[10px] text-slate-500">se aplică din mers; în Execuție TP-ul e atașat ordinului real</span>
            {save.isError && <span className="text-loss">{(save.error as Error).message}</span>}
          </div>
        </div>
      )}
    </div>
  );
}

const SESSION_ORDER = ["london", "frankfurt", "new_york"] as const;
const SESSION_NAME: Record<string, string> = { london: "Londra", frankfurt: "Frankfurt", new_york: "New York", custom: "fereastra proprie" };

/** În ce sesiuni tranzacționează piața (oricâte, minim una) + câte trade-uri / zi pe piață (toate sesiunile). */
function SessionsSettings({ symbol, cfg }: { symbol: string; cfg: DailyMarketConfig }) {
  const save = useDailySaveSessions();
  const { data: pre } = useDailyPresets();
  const cur = { sessions: (cfg.sessions ?? [cfg.preset ?? "london"]) as string[], max: cfg.max_trades_per_day ?? 1 };
  const [v, setV] = useState<typeof cur | null>(null);
  const val = v ?? cur;
  const dirty = v != null && JSON.stringify(v) !== JSON.stringify(cur);
  const toggle = (sid: string) => {
    const has = val.sessions.includes(sid);
    const next = has ? val.sessions.filter(x => x !== sid) : SESSION_ORDER.filter(x => x === sid || val.sessions.includes(x));
    setV({ ...val, sessions: next });
  };
  const roTime = (sid: string) => {
    const p = pre?.presets?.[sid];
    if (!p) return "";
    const tzName = p.tz.split("/")[1]?.replace("_", " ");
    return `${p.open} ${tzName} · interval ${p.or_minutes} min · ${p.entry === "breakout" ? "stop pe margini" : "pe direcție"}`;
  };
  return (
    <div className="border-t border-surface-border/60 pt-2 space-y-1">
      <div className="text-slate-300">Sesiuni în care tranzacționează {symbol}</div>
      <div className="flex flex-col gap-0.5 pl-1">
        {SESSION_ORDER.map(sid => (
          <label key={sid} className="flex items-center gap-2">
            <input type="checkbox" checked={val.sessions.includes(sid)} onChange={() => toggle(sid)} />
            <span className="text-slate-200 w-20">{SESSION_NAME[sid]}</span>
            <span className="text-slate-500">{roTime(sid)}</span>
          </label>
        ))}
      </div>
      <label className="flex items-center gap-2 pl-1">
        <span className="text-slate-300">Trade-uri maxime / zi pe piață</span>
        <input type="number" min={1} max={20} value={val.max} onChange={e => setV({ ...val, max: Number(e.target.value) || 1 })}
          className="w-14 bg-surface-card border border-surface-border rounded px-1" />
        <span className="text-slate-500">(toate sesiunile + re-intrările; implicit 1)</span>
      </label>
      <div className="text-[10px] text-slate-500 pl-1">
        Trade-urile se admit în ordinea în care apar: peste limită, sau cât timp altă sesiune a pieței are o poziție
        deschisă, sesiunea nu mai deschide nimic în ziua respectivă. Cealaltă piață are propria limită. Backtestul cardului
        se recalculează automat pe configurația nouă. Backtest (tot istoricul M5): DE40 Frankfurt + New York → max 1: +0,082R
        (5,0 / săpt) · max 2: +0,082R (7,9 / săpt) · max 3: +0,074R; US500 cu Londra sau Frankfurt adăugată = negativ (−0,03…−0,10R).
      </div>
      {val.sessions.length === 0 && <div className="text-loss pl-1">alege cel puțin o sesiune</div>}
      {dirty && (
        <div className="flex items-center gap-2 pl-1">
          <button disabled={!val.sessions.length || save.isPending}
            onClick={() => save.mutate({ symbol, sessions: val.sessions, max_trades_per_day: val.max }, { onSuccess: () => setV(null) })}
            className="px-3 py-1 rounded bg-cyan-500/20 text-cyan-200 border border-cyan-500/40 font-semibold disabled:opacity-40">Salvează sesiunile</button>
          <button onClick={() => setV(null)} className="px-3 py-1 rounded border border-surface-border text-slate-400">Renunță</button>
          {save.isError && <span className="text-loss">{(save.error as Error).message}</span>}
        </div>
      )}
    </div>
  );
}

function ProfitLockSettings({ symbol, cfg }: { symbol: string; cfg: DailyMarketConfig }) {
  const save = useDailySaveProfitLock();
  const cur = cfg.profit_lock ?? { enabled: false, trigger_R: 4.5, lock_R: 4 };
  const [pl, setPl] = useState<typeof cur | null>(null);
  const v = pl ?? cur;
  const bad = v.trigger_R < 3 || v.lock_R < 0 || v.lock_R >= v.trigger_R;
  const dirty = pl != null && JSON.stringify(pl) !== JSON.stringify(cur);
  function doSave() {
    if (v.enabled && !cur.enabled && !window.confirm(
      `Pornești Profit Lock pe ${symbol}?\nCând un trade atinge +${v.trigger_R}R, SL-ul se mută la +${v.lock_R}R ` +
      `(și pe poziția reală, în modul LIVE).\n\nÎn backtest nicio variantă n-a fost mai bună decât strategia actuală.`)) return;
    save.mutate({ symbol, profit_lock: v }, { onSuccess: () => setPl(null) });
  }
  return (
    <div className="border-t border-surface-border/60 pt-2 space-y-1">
      <label className="flex items-center gap-2">
        <input type="checkbox" checked={v.enabled} onChange={e => setPl({ ...v, enabled: e.target.checked })} />
        <span className="text-slate-300">Profit Lock</span>
        <span className="text-slate-500">(oprit = strategia actuală; pornit = la +Trigger R, SL → +Lock R)</span>
      </label>
      {v.enabled && (
        <div className="flex items-center gap-3 flex-wrap pl-5">
          <label className="flex items-center gap-1">Trigger
            <input type="number" min={3} step={0.5} value={v.trigger_R} onChange={e => setPl({ ...v, trigger_R: Number(e.target.value) })}
              className="w-16 bg-surface-card border border-surface-border rounded px-1" /> R</label>
          <label className="flex items-center gap-1">Lock
            <input type="number" min={0} step={0.5} value={v.lock_R} onChange={e => setPl({ ...v, lock_R: Number(e.target.value) })}
              className="w-16 bg-surface-card border border-surface-border rounded px-1" /> R</label>
          {bad && <span className="text-loss">trigger minim 3R; lock între 0 și trigger</span>}
        </div>
      )}
      {PLOCK_RESEARCH[symbol] && <div className="text-[10px] text-slate-500 pl-5">{PLOCK_RESEARCH[symbol]}</div>}
      {dirty && (
        <div className="flex items-center gap-2 pl-5">
          <button disabled={bad || save.isPending} onClick={doSave}
            className="px-3 py-1 rounded bg-cyan-500/20 text-cyan-200 border border-cyan-500/40 font-semibold disabled:opacity-40">Salvează Profit Lock</button>
          <button onClick={() => setPl(null)} className="px-3 py-1 rounded border border-surface-border text-slate-400">Renunță</button>
          {save.isError && <span className="text-loss">{(save.error as Error).message}</span>}
        </div>
      )}
    </div>
  );
}

function MarketModeSelector({ slot, symbol, mode }: { slot: number; symbol: string; mode: DailyMarketMode }) {
  const set = useDailyMarketMode();
  function choose(target: DailyMarketMode) {
    if (target === mode || set.isPending) return;
    if (target === "live") {
      if (!window.confirm(`Treci ${symbol} pe LIVE?\n\nDe la următoarea fereastră plasează ORDINE REALE pe ${symbol} ` +
        "(SL atașat, închidere în aceeași zi). Cealaltă piață NU e afectată.\n\nPe un cont REAL trebuie în plus deblocat " +
        "„Daily Engine” în Settings → Trading LIVE.")) return;
      if (!window.confirm(`Confirmare finală: ${symbol} va tranzacționa cu ordine reale. Continui?`)) return;
    } else if (target === "pause" && !window.confirm(`Pui ${symbol} pe PAUZĂ? Fără intrări noi; o poziție deschisă rămâne gestionată.`)) {
      return;
    } else if (target === "shadow" && mode === "live" && !window.confirm(
      `Treci ${symbol} pe SHADOW? Fără ordine noi; o poziție reală deschisă azi rămâne gestionată până la SL / finalul ferestrei.`)) {
      return;
    }
    set.mutate({ slot, mode: target });
  }
  return (
    <div className="ml-auto flex flex-col items-end gap-0.5">
      <div className="flex rounded-lg border border-surface-border overflow-hidden text-[11px] font-semibold">
        {(["live", "shadow", "pause"] as DailyMarketMode[]).map(k => (
          <button key={k} onClick={() => choose(k)} disabled={set.isPending}
            className={`px-2 py-0.5 border-l first:border-l-0 border-surface-border ${mode === k ? MODE_UI[k].on : "text-slate-500 hover:text-slate-300"}`}>
            {mode === k ? "● " : ""}{MODE_UI[k].label}
          </button>
        ))}
      </div>
      {set.isError && <span className="text-[10px] text-loss">{(set.error as Error).message}</span>}
    </div>
  );
}

function MarketCard({ m, score, bt, slot, auto, paused, cfgM }: {
  m: DailyMarketStatus; score?: DailyScore; slot?: number;
  bt?: { trades: number; expectancy_R: number; period: string; verdict: string };
  auto?: DailyBacktestAuto; paused?: boolean; cfgM?: DailyMarketConfig;
}) {
  const retry = useBacktestRefresh("daily");
  const isPaused = paused ?? m.paused ?? false;
  const mode: DailyMarketMode = isPaused ? "pause" : (cfgM?.exec_mode ?? m.exec_mode ?? "shadow");
  const ph = PHASE[isPaused && m.phase !== "in_position" ? "paused" : m.phase] ?? PHASE.waiting_open;
  const r = auto?.result;
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
        <span className={`text-[11px] px-2 py-0.5 rounded-full font-semibold ${ph.cls}`}>{ph.label}</span>
        {slot != null && <MarketModeSelector slot={slot} symbol={m.symbol} mode={mode} />}
      </div>
      {mode === "live" && (
        <div className={`text-[11px] rounded-lg px-2 py-1 border ${m.execution?.active ? "bg-loss/10 border-loss/30 text-loss" : "bg-warn/10 border-warn/30 text-warn"}`}>
          {m.execution?.active ? `LIVE — ordine reale (${m.execution.reason})` : `LIVE cerut, dar BLOCAT: ${m.execution?.reason ?? "engine oprit"}`}
          {" "}· se aplică de la următoarea fereastră (ziua se activează înainte de formarea intervalului)
        </div>
      )}
      {m.locked && m.phase === "in_position" && (
        <div className="text-[11px] text-profit bg-profit/10 border border-profit/30 rounded-lg px-2 py-1">
          🔒 Profit Lock activ — SL la {fmt(m.sl_now)} (+{m.profit_lock?.lock_R}R)
        </div>
      )}
      {isPaused && (
        <div className="text-[11px] text-amber-300/90 bg-amber-500/10 border border-amber-500/20 rounded-lg px-2 py-1">
          Pe pauză: nu se deschid trade-uri noi (shadow sau real); ordinele de intrare neactivate se anulează; o poziție deja
          deschisă rămâne gestionată (SL, Profit Lock, închidere la final de fereastră). Starea persistă la restart.
        </div>
      )}

      <div className="grid grid-cols-2 gap-2 text-[11px]">
        {(m.sessions?.length ?? 0) > 1 && (
          <div className="col-span-2 space-y-0.5 bg-surface-card/60 rounded-lg px-2 py-1">
            <div className="text-slate-500">Sesiuni (max {m.max_trades_per_day ?? 1} trade-uri / zi pe piață)</div>
            {m.sessions!.map(ss => (
              <div key={ss.session} className="flex items-center gap-2">
                <span className="text-slate-200 w-20">{SESSION_NAME[ss.session] ?? ss.session}</span>
                <span className="text-slate-400 w-24">{ss.window_app ?? ss.window_ro}</span>
                <span className={(PHASE[ss.phase] ?? PHASE.waiting_open).cls + " px-1.5 rounded"}>{(PHASE[ss.phase] ?? { label: ss.phase }).label}</span>
                {ss.phase === "closed" && ss.R_today != null && <span className={rCls(ss.R_today)}>{fmtR(ss.R_today)}</span>}
                {(ss.blocked_reason || ss.no_new_entries) && <span className="text-amber-300/80">{ss.blocked_reason ?? ss.no_new_entries}</span>}
              </div>
            ))}
          </div>
        )}
        <div className="text-slate-500">Fereastra (ora {m.app_tz_label ?? "RO"}){(m.sessions?.length ?? 0) > 1 ? ` · ${SESSION_NAME[m.session ?? ""] ?? ""}` : ""}</div>
        <div className="text-white font-semibold"
          title={m.app_tz_label === "DE" ? `ora RO: ${m.window_ro ?? "—"}` : undefined}>{m.window_app ?? m.window_ro ?? "—"}</div>
        <div className="text-slate-500">Ora bursei</div>
        <div className="text-slate-300">{m.window_local ?? "—"}</div>
        <div className="text-slate-500">Regulă</div>
        <div className="text-slate-300">
          interval {m.or_minutes} min · {m.entry_mode === "breakout" ? "ordine stop pe margini" : "intrare pe direcție"} ·
          {m.rr ? ` TP ${m.rr}R` : " închidere la final"}{m.reentry?.enabled ? ` · re-intrări ${m.reentry.window_min} min (max ${m.reentry.max_trades})` : ""}
        </div>
        {(m.trades_today ?? 0) > 1 && (<>
          <div className="text-slate-500">Trade-uri azi</div>
          <div className="text-slate-300">{m.trades_today} · <span className={rCls(m.R_today)}>{fmtR(m.R_today)}</span> închise</div>
        </>)}
        {m.reentry_stop && (m.trades_today ?? 0) > 1 && (<>
          <div className="text-slate-500">Re-intrări</div>
          <div className="text-slate-400">gata: {m.reentry_stop}</div>
        </>)}
        {m.reentry_wait && <div className="col-span-2 text-amber-300/80">așteaptă o nouă rupere a intervalului (re-intrarea {(m.k ?? 0) + 1})</div>}
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
      <MarketSettings symbol={m.symbol} orMinutes={m.or_minutes} slot={slot} />

      <div className="border-t border-surface-border pt-2 grid grid-cols-2 gap-2 text-[11px]">
        <div>
          <div className="text-slate-500">Shadow (date noi)</div>
          <div className="text-white">
            {score?.trades ?? 0} trade-uri · <span className={rCls(score?.expectancy_R)}>{fmtR(score?.expectancy_R)}</span>/trade
          </div>
          <div className="text-slate-500">{score?.wins ?? 0}W / {score?.losses ?? 0}L · total <span className={rCls(score?.total_R)}>{fmtR(score?.total_R)}</span></div>
        </div>
        <div>
          <div className="text-slate-500 flex items-center gap-1.5">
            Backtest ~3 ani (config. curentă)
            <BacktestAutoBadge a={auto} onRetry={() => retry.mutate(slot)} retrying={retry.isPending} />
          </div>
          {auto?.status === "completed" && r?.ok ? (<>
            <div className="text-white">{r.trades} trade-uri · <span className={rCls(r.expectancy_R)}>{fmtR(r.expectancy_R)}</span>/trade</div>
            <div className="text-slate-500">verdict M0: {r.verdict ?? "—"} · train {fmtR(r.train_R)} / test {fmtR(r.test_R)} · {r.period}</div>
          </>) : auto?.status === "failed" ? (
            <div className="text-loss">{auto.error ?? "eșuat"}</div>
          ) : (
            <div className="text-slate-500">{auto?.status === "outdated" ? "configurația s-a schimbat — rezultat nou în curând" : "se calculează…"}</div>
          )}
          {bt && <div className="text-[10px] text-slate-600 mt-0.5">cercetare {bt.period}: {bt.trades} trade-uri · {fmtR(bt.expectancy_R)}/trade · {bt.verdict}</div>}
        </div>
      </div>
    </div>
  );
}

function ModesSummary({ markets, running, sizing, alertR }: {
  markets?: DailyMarketConfig[]; running?: boolean; sizing?: Record<string, unknown> | null; alertR?: number;
}) {
  const save = useDailySaveSizing();
  const saveAlert = useDailySaveAlert();
  const [al, setAl] = useState<number | null>(null);
  const cur = Number(sizing?.max_margin_pct ?? 80);
  const [mm, setMm] = useState<number | null>(null);
  const anyLive = (markets ?? []).some(x => x.exec_mode === "live" && !x.paused);
  return (
    <div className={`rounded-xl border p-4 text-xs space-y-1 ${anyLive ? "bg-loss/5 border-loss/40" : "bg-surface border-surface-border"}`}>
      <div className="font-semibold text-white">
        Modul se alege pe FIECARE piață (Live / Shadow / Pauză, pe card) — o piață nu o afectează pe cealaltă.
        {running === false && <span className="ml-2 text-amber-400 font-normal">Engine-ul e OPRIT: modurile se aplică după Start.</span>}
      </div>
      <div className="text-[11px] text-slate-400">
        {(markets ?? []).map(x => `${x.symbol}: ${MODE_UI[(x.paused ? "pause" : x.exec_mode ?? "shadow") as DailyMarketMode].label}`).join(" · ")}
        {" "}— LIVE plasează ordine reale doar dacă, pe cont real, „Daily Engine” e deblocat în Settings → Trading LIVE.
        Magic 880001 — apare ca „Daily” în Tranzacții.
      </div>
      <div className="flex items-center gap-2 text-[11px] text-slate-400 pt-1">
        Limită de marjă: marja totală folosită (toate engine-urile + manual) după un ordin Daily ≤
        <input type="number" min={10} max={95} step={5} value={mm ?? cur} onChange={e => setMm(Number(e.target.value))}
          className="w-14 bg-surface-card border border-surface-border rounded px-1 text-white" /> % din equity
        {mm != null && mm !== cur && (
          <button onClick={() => save.mutate({ ...(sizing ?? {}), max_margin_pct: mm }, { onSuccess: () => setMm(null) })}
            className="px-2 py-0.5 rounded bg-cyan-500/20 text-cyan-200 border border-cyan-500/40">Salvează</button>
        )}
        <span className="text-slate-500">(lotul e redus sau ordinul nu se plasează; DE40 la lotul minim ≈ 148 $)</span>
      </div>
      <div className="flex items-center gap-2 text-[11px] text-slate-400">
        🚀 Alertă de profit (Notificări + Telegram) când un trade deschis trece de
        <input type="number" min={0} max={100} step={0.5} value={al ?? alertR ?? 5} onChange={e => setAl(Number(e.target.value))}
          className="w-14 bg-surface-card border border-surface-border rounded px-1 text-white" /> R
        {al != null && al !== (alertR ?? 5) && (
          <button onClick={() => saveAlert.mutate(al, { onSuccess: () => setAl(null) })}
            className="px-2 py-0.5 rounded bg-cyan-500/20 text-cyan-200 border border-cyan-500/40">Salvează</button>
        )}
        <span className="text-slate-500">— o singură dată pe trade, nu închide nimic (0 = oprită). Acum: {(alertR ?? 5) ? `ACTIVĂ la +${alertR ?? 5}R` : "OPRITĂ"}</span>
      </div>
    </div>
  );
}

export function DailyEnginePage() {
  const { data: dcfg } = useDailyConfig();
  const { data: st } = useDailyStatus();
  const { data: trades } = useDailyTrades();
  const start = useDailyStart();
  const stop = useDailyStop();
  const [showLogs, setShowLogs] = useState(false);
  const { data: logs } = useDailyLogs(showLogs);
  const running = st?.running ?? false;
  const sc = st?.scorecard;

  // un card per SLOT din configuratie (piata poate fi schimbata), cu starea live suprapusa pe simbol
  const byStatus: Record<string, DailyMarketStatus> = Object.fromEntries((st?.markets ?? []).map(x => [x.symbol, x]));
  const cfgMarkets = dcfg?.markets;
  const slotCards = (dcfg?.markets ?? []).map((c, slot) => ({
    slot,
    m: byStatus[c.symbol] ?? { symbol: c.symbol, label: c.label, phase: st?.running ? "waiting_open" : "stopped",
                               or_minutes: c.or_minutes, entry_mode: c.entry, rr: c.rr, reentry: c.reentry } as DailyMarketStatus,
  }));
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

      <ModesSummary markets={cfgMarkets} running={st?.running} sizing={(dcfg as { sizing?: Record<string, unknown> } | undefined)?.sizing}
        alertR={(dcfg as { alert_R?: number } | undefined)?.alert_R} />

      <div className="text-[11px] text-slate-500 bg-surface rounded-xl border border-surface-border px-4 py-2">
        Implicit un trade pe zi pe piață (re-intrările din „Opțiuni” sunt opționale), închis obligatoriu în aceeași zi (niciodată
        peste noapte). Două sloturi (dimineață / după-amiază); piața fiecăruia se poate schimba din card. Orele urmează ora bursei —
        în săptămânile cu decalaj de fus SUA/RO fereastra de după-amiază se mută automat cu o oră mai devreme.
        Trade-urile sunt virtuale: nu apar în MT5 și nu afectează contul. Edge-ul din backtest e mic (+0,06…0,08R/trade)
        și trebuie confirmat aici, pe date noi, înainte de orice ordin real.
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {slotCards.map(({ m, slot }) => (
          <MarketCard key={`${slot}-${m.symbol}`} m={m} slot={slot} score={sc?.by_symbol?.[m.symbol]} bt={st?.backtest_ref?.[m.symbol]}
            auto={st?.backtest_auto?.find(a => a.slot === slot)} paused={cfgMarkets?.[slot]?.paused} cfgM={cfgMarkets?.[slot]} />
        ))}
        {slotCards.length === 0 && (
          <div className="md:col-span-2 text-center text-sm text-slate-500 py-6 bg-surface rounded-xl border border-surface-border">
            {running ? "Se conectează la MT5..." : "Pornește motorul ca să vezi starea zilei pe fiecare piață."}
          </div>
        )}
      </div>

      {(() => {
        const inCfg = new Set((cfgMarkets ?? []).map(x => x.symbol));
        const gone = Object.entries(sc?.by_symbol ?? {}).filter(([sym]) => !inCfg.has(sym));
        return gone.length ? (
          <div className="text-[11px] text-slate-400 bg-surface rounded-xl border border-surface-border px-4 py-2">
            Piețe scoase din configurație (incluse în totalul de mai jos și în rapoarte):{" "}
            {gone.map(([sym, v]) => <span key={sym} className="mr-3"><b className="text-slate-300">{sym}</b> {v.trades} trade-uri ·
              {" "}{v.wins}W / {v.losses}L · <span className={rCls(v.total_R)}>{fmtR(v.total_R)}</span></span>)}
          </div>
        ) : null;
      })()}

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
        {Object.entries(sc?.by_symbol ?? {}).filter(([, v]) => (v.blocked_trades ?? 0) > 0 && v.blocked_pnl_money_est != null).map(([sym, v]) => (
          <div key={sym} className="mb-2 text-[11px] bg-amber-500/10 border border-amber-500/30 rounded-lg px-3 py-1.5 text-amber-300">
            ⛔ <b>{sym}</b>: {v.blocked_trades} trade-uri ar fi fost BLOCATE în EXECUȚIE (limita globală de risc — lotul minim
            depășește % permis din cont). La lotul minim ar fi însemnat{" "}
            <b className={rCls(v.blocked_pnl_money_est)}>{v.blocked_pnl_money_est! > 0 ? "+" : ""}{v.blocked_pnl_money_est!.toFixed(2)} USD</b>
            {" "}({fmtR(v.total_R)}) — sumă ipotetică, nu e inclusă în estimarea totală.
          </div>
        ))}
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
                    {t.blocked && t.blocked_pnl_money_est != null ? (
                      <>
                        <td className="text-amber-400" title={`În EXECUȚIE ordinul NU s-ar plasa: ${t.blocked_reason ?? "limita globală de risc"}`}>
                          ⛔ blocat <span className="text-slate-500">({t.blocked_lots} min)</span>
                        </td>
                        <td className={`text-right italic ${rCls(t.blocked_pnl_money_est)}`}
                            title={`Ce ar fi însemnat la lotul ${t.blocked_lots} (risc ~${t.blocked_risk_money?.toFixed(2)} ${t.currency ?? ""}) — NU s-ar fi tranzacționat (limita globală de risc). Nu intră în totalul estimat.`}>
                          ({t.blocked_pnl_money_est > 0 ? "+" : ""}{t.blocked_pnl_money_est.toFixed(2)} {t.currency ?? ""})
                        </td>
                      </>
                    ) : (
                      <>
                        <td className="text-slate-400">{t.lots ?? "—"}</td>
                        <td className={`text-right ${rCls(t.pnl_money_est)}`}>{t.pnl_money_est != null ? `${t.pnl_money_est > 0 ? "+" : ""}${t.pnl_money_est.toFixed(2)} ${t.currency ?? ""}` : "—"}</td>
                      </>
                    )}
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
