import { useEffect, useState } from "react";
import { Target } from "lucide-react";
import { useSaveSpecialTpEngine, useSpecialTp } from "../api/hooks";
import type { SpecialTpCfg } from "../api/hooks";

/**
 * Special Take Profit Mode (profit_lock.py) — blocarea profitului în trepte.
 * La pragul RR inițial (ex. 2R): SL → prag − offset (1,9R), TP → prag + pas + extensie (2,6R); apoi la fiecare pas
 * (2,5R / 3R / …) SL-ul urcă din nou. SL-ul nu coboară niciodată. Deoarece pragul următor e mereu sub TP, TP-ul se
 * atinge doar printr-un gap → în practică e un trailing în trepte începând de la RR-ul inițial.
 * Configurare: Setări Globale (câștigă) → altfel setarea Custom Engine de aici. Daily / Noisy / AI: excluse (backtest).
 */
export function SpecialTpParams({ v, onChange, num }: {
  v: SpecialTpCfg; onChange: (p: Partial<SpecialTpCfg>) => void;
  num: (value: number, onChange: (v: number) => void, min: number, max: number, step?: number, w?: string) => React.ReactNode;
}) {
  return (<>
    mod
    <select value={v.mode} onChange={e => onChange({ mode: e.target.value as SpecialTpCfg["mode"] })}
      className="bg-surface border border-surface-border rounded px-1 py-0.5 text-xs text-white">
      <option value="special">trepte (propunerea userului)</option>
      <option value="atr_trail">trailing ATR (alternativa echipei)</option>
    </select>
    · TP inițial +{num(v.tp_extension_R, x => onChange({ tp_extension_R: x }), 0, 1, 0.05)}R
    · SL la {num(v.sl_offset_R, x => onChange({ sl_offset_R: x }), 0, 1, 0.05)}R sub prag
    {v.mode === "special"
      ? <>· pas {num(v.step_R, x => onChange({ step_R: x }), 0.1, 3, 0.1)}R</>
      : <>· {num(v.atr_mult, x => onChange({ atr_mult: x }), 0.5, 5, 0.5)}× ATR</>}
  </>);
}

const fmtR = (x: number) => `${x > 0 ? "+" : ""}${x.toFixed(3)}R`;

export function SpecialTpCard() {
  const { data } = useSpecialTp();
  const save = useSaveSpecialTpEngine();
  const [draft, setDraft] = useState<SpecialTpCfg | null>(null);
  useEffect(() => { if (data) setDraft(data.engine_cfg.custom); }, [data]);
  if (!data || !draft) return null;
  const eff = data.effective.custom;
  const globalOn = eff.source === "global";
  const dirty = JSON.stringify(draft) !== JSON.stringify(data.engine_cfg.custom);
  const num = (value: number, onChange: (v: number) => void, min: number, max: number, step = 1, w = "w-16") => (
    <input type="number" value={value} min={min} max={max} step={step} disabled={globalOn}
      onChange={e => onChange(Number(e.target.value))}
      className={`${w} bg-surface border border-surface-border rounded px-1.5 py-0.5 text-xs text-white disabled:opacity-40`} />
  );
  const on = draft.enabled;
  function saveIt() {
    if (draft!.enabled && !data!.engine_cfg.custom.enabled &&
        !window.confirm("Pornești Special TP pe Custom Engine? Va MODIFICA SL / TP pe pozițiile REALE deschise de sesiuni " +
          "(cont live). Validat doar în backtest — recomandarea echipei e SHADOW / demo întâi.")) return;
    save.mutate({ engine: "custom", cfg: draft! });
  }
  return (
    <div className="rounded-xl border border-surface-border bg-surface p-4 space-y-2 text-xs">
      <h3 className="text-sm font-semibold text-white flex items-center gap-2">
        <Target size={15} className="text-emerald-400" /> Special Take Profit — Custom Engine
        <span className={`text-[10px] px-1.5 py-0.5 rounded font-semibold ${eff.cfg.enabled ? "bg-profit/15 text-profit" : "bg-slate-700/40 text-slate-400"}`}>
          {eff.cfg.enabled ? `ACTIV (${eff.source === "global" ? "din Setări Globale" : "din engine"})` : "OPRIT"}
        </span>
      </h3>
      <div className="text-[11px] text-slate-400">
        Nu închide trade-ul la TP-ul inițial: la atingerea RR-ului (ex. 2R) SL-ul se blochează în profit (1,9R) și urcă în trepte
        (2,4R / 2,9R …) cât timp piața continuă; SL-ul nu coboară niciodată. Treptele se recalculează la închiderea barei.
      </div>
      {globalOn && <div className="text-[11px] text-blue-300">Controlat din Setări Globale — setarea de aici e ignorată cât timp globalul e pornit.</div>}
      <div className={`flex items-center gap-2 flex-wrap text-[11px] text-slate-400 ${globalOn ? "opacity-50" : ""}`}>
        <button disabled={globalOn} onClick={() => setDraft({ ...draft, enabled: !on })}
          className={`relative w-10 h-5 rounded-full transition-colors shrink-0 ${on ? "bg-emerald-600" : "bg-surface-border"}`}>
          <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-all ${on ? "left-5" : "left-0.5"}`} />
        </button>
        <SpecialTpParams v={draft} onChange={p => setDraft({ ...draft, ...p })} num={num} />
        <button disabled={!dirty || save.isPending || globalOn} onClick={saveIt}
          className="ml-2 px-3 py-1 rounded text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white disabled:opacity-40">
          {save.isPending ? "Se salvează..." : "Salvează"}
        </button>
        {save.isError && <span className="text-loss">{save.error.message}</span>}
      </div>
      <div className="border-t border-surface-border/40 pt-2">
        <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-1">Backtest (varianta implicită: +0,10R · 0,10R · pas 0,50R)</div>
        <table className="w-full text-[11px]">
          <thead><tr className="text-slate-500 text-left"><th>Engine / piață</th><th>TP actual</th><th>Special</th><th>DD actual → special</th><th>Eligibil</th></tr></thead>
          <tbody>{data.research.map(r => (
            <tr key={r.engine + r.market} className="border-t border-surface-border/30">
              <td className="py-0.5 text-slate-300">{r.engine} · {r.market}</td>
              <td className="text-slate-400">{fmtR(r.current)}</td>
              <td className={r.special > r.current ? "text-profit" : "text-loss"}>{fmtR(r.special)}</td>
              <td className="text-slate-400">{r.dd_current}R → {r.dd_special}R</td>
              <td className="text-slate-400">{r.engine === "Custom" ? "da" : "nu"}</td>
            </tr>))}</tbody>
        </table>
        <div className="text-[10px] text-slate-500 mt-1">
          Excluse: {Object.entries(data.not_eligible).map(([k, v]) => `${k} — ${v}`).join(" · ")}
        </div>
      </div>
    </div>
  );
}
