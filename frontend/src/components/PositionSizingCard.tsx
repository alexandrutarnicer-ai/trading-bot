import { useState } from "react";
import { RefreshCw, Scale } from "lucide-react";
import { useSizingPreview } from "../api/hooks";

/**
 * Dimensionarea pozitiei — explicata si calculata live, cu ACEEASI logica pe care o folosesc
 * ordinele (position_sizing, comuna Custom / AI / Daily). Separa clar:
 *   - ce vine automat din MT5 (read-only, sincronizat),
 *   - ce configurezi tu (fractie, risc%, lot fix),
 *   - lantul de calcul pe un SL tipic real + verdictul (ex: lotul minim depaseste tinta).
 */

const money = (v: number | null | undefined, cur = "USD") =>
  v == null ? "—" : `${v.toLocaleString("ro-RO", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${cur}`;

export function PositionSizingCard({ symbol, fraction, riskPct, fixedLots, capitalSync = true, capitalUsd, engine }: {
  symbol?: string; fraction: number; riskPct: number; fixedLots?: number | null;
  capitalSync?: boolean; capitalUsd?: number | null; engine: string;
}) {
  const { data, isFetching, refetch, error } = useSizingPreview({ symbol, fraction, riskPct, fixedLots, capitalSync, capitalUsd });
  const [howOpen, setHowOpen] = useState(false);
  const a = data?.account;
  const s = data?.spec;
  const r = data?.result;
  const cur = a?.currency ?? "USD";

  if (!symbol) return <div className="text-[11px] text-slate-500">Alege o piață pentru calculul lotului.</div>;
  if (error || (data && !data.connected)) {
    return <div className="text-[11px] text-warn/80">MT5 indisponibil — calculul se face la fiecare ordin cu datele reale ale contului. {data?.error ?? ""}</div>;
  }

  return (
    <div className="rounded-lg border border-surface-border bg-surface/50 p-3 space-y-2.5 text-[11px]">
      <div className="flex items-center gap-2">
        <Scale size={13} className="text-blue-300" />
        <span className="font-semibold text-white">Dimensionarea poziției — {symbol}</span>
        <span className="text-slate-500">· aceeași logică pe Custom / AI / Daily ({engine})</span>
        <button onClick={() => refetch()} title="Recitește din MT5" className="ml-auto text-slate-500 hover:text-white">
          <RefreshCw size={11} className={isFetching ? "animate-spin" : ""} />
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        <div className="rounded border border-emerald-500/20 bg-emerald-500/5 p-2 space-y-0.5">
          <div className="text-[10px] uppercase tracking-wider text-emerald-300">
            Din MT5 — automat {data?.synced_at ? `· sincronizat ${data.synced_at.slice(11, 16)}` : ""}
          </div>
          <div className="text-slate-300">Equity <b>{money(a?.equity, cur)}</b> · balance {money(a?.balance, cur)}</div>
          <div className="text-slate-400">Marjă liberă {money(a?.free_margin, cur)} · levier 1:{a?.leverage ?? "?"} · cont {a?.is_demo ? "DEMO" : "REAL"}</div>
          <div className="text-slate-400">Lot min {s?.volume_min} · pas {s?.volume_step} · max {s?.volume_max}</div>
          <div className="text-slate-400">Valoare tick ({s?.tick_size}): {money(s?.tick_value, cur)} / lot
            {s?.margin_per_lot ? ` · marjă ${money(s.margin_per_lot, cur)} / lot` : ""}</div>
        </div>
        <div className="rounded border border-blue-500/20 bg-blue-500/5 p-2 space-y-0.5">
          <div className="text-[10px] uppercase tracking-wider text-blue-300">Configurat de tine</div>
          {fixedLots ? (
            <div className="text-slate-300">Lot FIX <b>{fixedLots}</b> pe ordin — fracția și riscul sunt ignorate</div>
          ) : (<>
            <div className="text-slate-300">Fracție <b>{(fraction * 100).toFixed(1)}%</b> din {capitalSync ? "equity-ul MT5" : `capitalul fix (${money(capitalUsd ?? 0, cur)}, plafonat la equity)`}</div>
            <div className="text-slate-300">Risc <b>{(riskPct * 100).toFixed(2)}%</b> din capitalul alocat, pe trade</div>
          </>)}
          <div className="text-slate-500">SL-ul vine din strategie (nu din fracție); exemplul folosește {data?.sl?.source ?? "—"}.</div>
        </div>
      </div>

      {r && data?.sl?.distance ? (
        <div className="space-y-1">
          <div className="text-[10px] uppercase tracking-wider text-slate-500">Calculul (ca la un ordin real)</div>
          {r.mode === "risk" ? (
            <div className="font-mono text-slate-300 leading-relaxed">
              {money(r.capital_base, cur)} × {(r.fraction * 100).toFixed(1)}% = <b>{money(r.capital, cur)}</b> alocat
              {" → "}× {(riskPct * 100).toFixed(2)}% = țintă <b>{money(r.target_money, cur)}</b>
              {" → "}lot brut {r.raw_lots ?? "—"}
              {" → "}lot final <b>{r.lots}</b>
              {" → "}risc real <b className={r.at_min_lot ? "text-warn" : "text-profit"}>{money(r.risk_money, cur)}</b>
              {r.risk_pct_equity != null && <span className="text-slate-500"> ({r.risk_pct_equity}% din equity)</span>}
            </div>
          ) : (
            <div className="font-mono text-slate-300">lot fix {r.lots} → risc la SL <b>{money(r.risk_money, cur)}</b>
              {r.risk_pct_equity != null && <span className="text-slate-500"> ({r.risk_pct_equity}% din equity)</span>}</div>
          )}
          {r.margin_need != null && (
            <div className="text-slate-500">Marjă necesară {money(r.margin_need, cur)}{r.margin_pct_free != null ? ` (${r.margin_pct_free}% din marja liberă)` : ""}</div>
          )}
          {r.reason ? (
            <div className="text-loss">Nu se plasează: {r.reason}.</div>
          ) : r.at_min_lot && r.mode === "risk" ? (
            <div className="rounded bg-warn/10 border border-warn/30 px-2 py-1 text-warn">
              Lotul minim al brokerului ({s?.volume_min}) riscă {money(r.risk_money, cur)} — de {r.ratio?.toFixed(1)}× ținta.
              La acest cont <b>fracția nu mai schimbă lotul</b>: se plasează mereu lotul minim
              {r.equity_for_target ? <> până când equity-ul ajunge la ~{money(r.equity_for_target, cur)}</> : null}.
            </div>
          ) : r.capped_max ? (
            <div className="text-warn">Lotul calculat depășește maximul brokerului — plafonat la {s?.volume_max}.</div>
          ) : (
            <div className="text-profit">✓ Lotul calculat respectă ținta de risc (diferența vine doar din pasul de volum).</div>
          )}
        </div>
      ) : (
        <div className="text-slate-500">Fără SL tipic disponibil pentru exemplu — calculul real se face la fiecare ordin.</div>
      )}

      <button onClick={() => setHowOpen(v => !v)} className="text-[10px] text-slate-500 hover:text-slate-300">
        {howOpen ? "▾" : "▸"} Cum funcționează și de ce există
      </button>
      {howOpen && (
        <div className="text-slate-400 space-y-1 leading-relaxed">
          <p><b>Ce este:</b> fracția spune ce parte din cont „aparține” acestei piețe când se calculează lotul. Riscul% spune cât
            din partea aceea poți pierde dacă e atins SL-ul. Lotul se calculează la fiecare ordin cu equity-ul REAL din MT5.</p>
          <p><b>Ce influențează:</b> doar mărimea lotului (deci banii riscați). NU schimbă SL / TP, protecția capitalului, circuit
            breaker-ul sau limitele globale.</p>
          <p><b>De ce există:</b> același cont rulează mai multe piețe și engine-uri; fracția împiedică o singură piață să riște
            un procent mare din tot contul. Suma fracțiilor NU trebuie să fie 100% — fiecare e un plafon separat.</p>
          <p><b>Limita:</b> brokerul are un lot minim. Când ținta e sub lotul minim, se plasează lotul minim (riscul real crește);
            pe conturi mici asta face fracția practic inactivă. Lot fix = alternativa: volum exact, ales de tine.</p>
          <p><b>Siguranță:</b> dacă equity-ul MT5 nu se poate citi, ordinul NU se plasează (nu se mai ghicește un capital).</p>
        </div>
      )}
    </div>
  );
}
