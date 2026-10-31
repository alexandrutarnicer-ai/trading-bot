import { useEffect, useState } from "react";
import { Globe2 } from "lucide-react";
import { useGlobalSettings, useSaveGlobalSettings } from "../api/hooks";
import type { GlobalSettings } from "../api/hooks";

/**
 * Setări Globale — punct unic de control pentru Custom Engine + AI Engine.
 *
 * Regula: „cea mai strictă câștigă". Globalul e un minim de siguranță peste
 * setările fiecărei piețe; o piață poate fi mai strictă, niciodată mai permisivă.
 * Toate secțiunile sunt OPRITE implicit (comportament identic cu înainte).
 * Se aplică de la următoarea bară, fără restart (ambele engine-uri recitesc fișierul).
 */
type Sec = keyof GlobalSettings;

export function GlobalSettingsCard() {
  const { data } = useGlobalSettings();
  const save = useSaveGlobalSettings();
  const [draft, setDraft] = useState<GlobalSettings | null>(null);
  useEffect(() => { if (data) setDraft(data); }, [data]);
  if (!draft || !data) return null;

  const dirty = JSON.stringify(draft) !== JSON.stringify(data);
  const set = <S extends Sec>(sec: S, patch: Partial<GlobalSettings[S]>) =>
    setDraft({ ...draft, [sec]: { ...draft[sec], ...patch } });

  const toggle = (sec: Sec) => {
    const on = draft[sec].enabled;
    return (
      <button onClick={() => set(sec, { enabled: !on } as Partial<GlobalSettings[typeof sec]>)}
        className={`relative w-10 h-5 rounded-full transition-colors shrink-0 ${on ? "bg-blue-600" : "bg-surface-border"}`}>
        <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-all ${on ? "left-5" : "left-0.5"}`} />
      </button>
    );
  };

  const num = (value: number, onChange: (v: number) => void, min: number, max: number,
               step = 1, w = "w-16") => (
    <input type="number" value={value} min={min} max={max} step={step}
      onChange={e => onChange(Number(e.target.value))}
      className={`${w} bg-surface border border-surface-border rounded px-1.5 py-0.5 text-xs text-white`} />
  );

  const row = (sec: Sec, title: string, scope: string, children: React.ReactNode) => (
    <div className="flex items-center gap-3 flex-wrap py-1.5 border-t border-surface-border/40 first:border-t-0">
      {toggle(sec)}
      <span className="text-xs font-semibold text-white w-44">{title}</span>
      <span className="text-[10px] px-1.5 py-0.5 rounded bg-surface-border/40 text-slate-400">{scope}</span>
      {draft[sec].enabled && <div className="flex items-center gap-2 flex-wrap text-[11px] text-slate-400">{children}</div>}
    </div>
  );

  return (
    <div className="rounded-xl border border-surface-border bg-surface p-4 space-y-2">
      <h3 className="text-sm font-semibold text-white flex items-center gap-2">
        <Globe2 size={15} className="text-blue-400" />
        Setări Globale
        <span className="text-[10px] text-slate-500 font-normal">
          Bot + AI · „cea mai strictă regulă câștigă" · se aplică de la următoarea bară, fără restart
        </span>
      </h3>

      {row("capital_protection", "Protecția Capitalului", "Bot + AI", <>
        blochează ordinele noi când equity &lt;
        {num(draft.capital_protection.threshold_pct, v => set("capital_protection", { threshold_pct: v }), 1, 99)}% din
        {num(draft.capital_protection.start_balance ?? 0, v => set("capital_protection", { start_balance: v || null }), 0, 1e9, 1, "w-20")}$
        <span className="text-slate-600">(0 = capitalul inițial din profil)</span>
      </>)}

      {row("circuit_breaker", "Circuit Breaker global", "Bot + AI · tot contul", <>
        stop azi după
        {num(draft.circuit_breaker.max_consecutive_losses, v => set("circuit_breaker", { max_consecutive_losses: v }), 1, 50)} pierderi consecutive
        · sau pierdere zilnică ≥
        {num(draft.circuit_breaker.max_daily_loss_pct, v => set("circuit_breaker", { max_daily_loss_pct: v }), 0, 100, 0.5)}%
        <span className="text-slate-600">(0 = fără limită %)</span>
      </>)}

      {row("friday_close", "Închidere de vineri", "Bot + AI", <>
        de la ora
        {num(draft.friday_close.hour, v => set("friday_close", { hour: v }), 0, 23)}
        <label className="flex items-center gap-1">
          <input type="checkbox" checked={draft.friday_close.exclude_crypto}
            onChange={e => set("friday_close", { exclude_crypto: e.target.checked })} />
          exceptează cripto (piață deschisă în weekend)
        </label>
      </>)}

      {row("news_protection", "Protecție la știri", "Bot + AI", <>
        impact
        <select value={draft.news_protection.impact_level}
          onChange={e => set("news_protection", { impact_level: Number(e.target.value) })}
          className="bg-surface border border-surface-border rounded px-1 py-0.5 text-xs text-white">
          <option value={3}>High</option><option value={2}>Medium+</option><option value={1}>Toate</option>
        </select>
        · înainte
        {num(draft.news_protection.pre_minutes, v => set("news_protection", { pre_minutes: v }), 0, 720)}min · după
        {num(draft.news_protection.post_minutes, v => set("news_protection", { post_minutes: v }), 0, 720)}min
      </>)}

      {row("risk_cap", "Risc maxim pe trade", "Custom + AI + Daily", <>
        niciun trade nu riscă peste
        {num(draft.risk_cap.max_risk_pct, v => set("risk_cap", { max_risk_pct: v }), 0.1, 20, 0.1)}% din equity
        <span className="text-slate-600">(volumul se reduce; dacă nici lotul minim nu încape, ordinul nu se plasează)</span>
      </>)}

      {row("max_concurrent_per_market", "Poziții simultane / piață", "Bot + AI · tot contul", <>
        max
        {num(draft.max_concurrent_per_market.max, v => set("max_concurrent_per_market", { max: v }), 1, 20)}
        poziții + ordine pending pe același simbol (toate engine-urile și strategiile)
      </>)}

      {row("ai_filter", "Filtru AI pre-trade", "doar Custom Engine", <>
        nivel
        <select value={draft.ai_filter.level}
          onChange={e => set("ai_filter", { level: e.target.value as GlobalSettings["ai_filter"]["level"] })}
          className="bg-surface border border-surface-border rounded px-1 py-0.5 text-xs text-white">
          <option value="permissive">Permisiv (50%)</option>
          <option value="balanced">Echilibrat (70%)</option>
          <option value="strict">Strict (85%)</option>
        </select>
        <label className="flex items-center gap-1">
          <input type="checkbox" checked={draft.ai_filter.strict}
            onChange={e => set("ai_filter", { strict: e.target.checked })} />
          mod Strict (AI indisponibil → ordin blocat)
        </label>
      </>)}

      <div className="flex items-center gap-3 pt-2 border-t border-surface-border/40">
        <button disabled={!dirty || save.isPending} onClick={() => save.mutate(draft)}
          className="px-3 py-1 rounded text-xs font-semibold bg-blue-600 hover:bg-blue-500 text-white disabled:opacity-40">
          {save.isPending ? "Se salvează..." : "Salvează"}
        </button>
        {dirty && <button onClick={() => setDraft(data)} className="text-xs text-slate-400 hover:text-white">Renunță</button>}
        <span className="text-[10px] text-slate-500">
          O piață poate avea o regulă mai strictă decât globalul, niciodată una mai permisivă.
          Fiecare salvare trimite notificare Telegram.
        </span>
        {save.isError && <span className="text-[10px] text-loss">{save.error.message}</span>}
      </div>
    </div>
  );
}
