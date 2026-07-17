import { ShieldAlert } from "lucide-react";
import { useLiveTrading, useSetLiveTrading } from "../api/hooks";

/**
 * Trading LIVE — deblocarea explicită a contului real, per componentă.
 *
 * Default totul e BLOCAT (demo-only): botul și motorul AI refuză conturile
 * reale la conectare. Activarea unui switch aici scrie data/live_trading.json
 * (per mașină, negitat) și cere DOUĂ confirmări. Se aplică la următoarea
 * pornire/reconectare a componentei.
 */
export function LiveTradingCard() {
  const { data } = useLiveTrading();
  const setLive = useSetLiveTrading();
  if (!data) return null;
  const { flags, account } = data;

  const toggle = (component: "bot" | "ai_engine", label: string) => {
    const on = !flags[component];
    if (on) {
      if (!confirm(`⚠️ ACTIVEZI tranzacționarea pe CONT REAL pentru ${label}?\n\n` +
                   "Ordinele se vor plasa cu BANI REALI la următoarea pornire " +
                   "a componentei pe un cont live."))
        return;
      if (!confirm(`Confirmare finală: ${label} va putea tranzacționa LIVE pe această mașină. Continui?`))
        return;
    }
    setLive.mutate({ component, allowed: on });
  };

  const Row = ({ component, label, desc }: {
    component: "bot" | "ai_engine"; label: string; desc: string;
  }) => {
    const on = flags[component];
    return (
      <div className="flex items-center gap-3 flex-wrap">
        <button onClick={() => toggle(component, label)} disabled={setLive.isPending}
          className={`relative w-10 h-5 rounded-full transition-colors shrink-0 ${on ? "bg-loss" : "bg-surface-border"}`}
          title={on ? "Dezactivează (revine la DEMO-only)" : "Activează tranzacționarea LIVE"}>
          <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-all ${on ? "left-5" : "left-0.5"}`} />
        </button>
        <span className="text-xs font-semibold text-white w-24">{label}</span>
        <span className={`text-[10px] px-1.5 py-0.5 rounded font-semibold ${on ? "bg-loss/20 text-loss" : "bg-profit/20 text-profit"}`}>
          {on ? "LIVE DEBLOCAT" : "DEMO-only"}
        </span>
        <span className="text-[10px] text-slate-500">{desc}</span>
      </div>
    );
  };

  return (
    <div className={`rounded-xl border p-4 space-y-3 ${(flags.bot || flags.ai_engine) ? "bg-loss/5 border-loss/40" : "bg-surface border-surface-border"}`}>
      <h3 className="text-sm font-semibold text-white flex items-center gap-2">
        <ShieldAlert size={15} className={(flags.bot || flags.ai_engine) ? "text-loss" : "text-slate-400"} />
        Trading LIVE (cont real)
        <span className="text-[10px] text-slate-500 font-normal">per mașină · se aplică la următoarea pornire a componentei</span>
      </h3>
      <Row component="bot" label="Bot (sesiuni)"
        desc="cele 20 de sesiuni pe reguli — recomandat doar sesiunile cu edge validat" />
      <Row component="ai_engine" label="AI Engine"
        desc="motorul autonom AI — recomandat să rămână pe DEMO până demonstrează edge" />
      <div className="text-[10px] text-slate-500 border-t border-surface-border/40 pt-2">
        Cont MT5 curent:{" "}
        {account.connected
          ? <span className={account.is_demo ? "text-profit" : "text-loss font-semibold"}>
              {account.login} ({account.server}) — {account.is_demo ? "DEMO" : "⚠ CONT REAL"}
            </span>
          : <span className="text-slate-600">neconectat</span>}
        {" "}· Cu switch-ul pe DEMO-only, componenta REFUZĂ pornirea pe un cont real (protecție implicită).
        Activarea trimite notificare Telegram și cere două confirmări.
      </div>
      {setLive.isError && <div className="text-[10px] text-loss">{(setLive.error as Error).message}</div>}
    </div>
  );
}
