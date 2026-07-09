import { useMt5Orders } from "../api/hooks";
import { Layers } from "lucide-react";

/**
 * Tabel "Ordine Active" — sursa de adevar: exclusiv MT5.
 * Pozitii deschise + ordine pending, clasificate pe sursa (Bot / AI / Manual),
 * plus sumar de capital: equity, marja folosita/libera, P&L flotant.
 */

const SOURCE_BADGE: Record<string, { label: string; cls: string }> = {
  bot:    { label: "BOT",    cls: "bg-blue-500/20 text-blue-300" },
  ai:     { label: "AI",     cls: "bg-purple-500/20 text-purple-300" },
  manual: { label: "MANUAL", cls: "bg-slate-600/40 text-slate-300" },
};

function Src({ s }: { s: string }) {
  const b = SOURCE_BADGE[s] ?? SOURCE_BADGE.manual;
  return <span className={`text-[9px] px-1.5 py-0.5 rounded font-semibold ${b.cls}`}>{b.label}</span>;
}

export function ActiveOrdersTable() {
  const { data } = useMt5Orders();

  if (!data) return null;
  if (!data.connected) {
    return (
      <div className="bg-surface rounded-xl border border-surface-border p-4 text-xs text-slate-500">
        Ordine Active: MT5 deconectat {data.error ? `(${data.error})` : ""}
      </div>
    );
  }

  const acc = data.account;
  const nothing = data.positions.length === 0 && data.pending.length === 0;

  return (
    <div className="bg-surface rounded-xl border border-surface-border p-4 space-y-3">
      <div className="flex items-center gap-2 flex-wrap">
        <Layers size={15} className="text-slate-400" />
        <h3 className="text-sm font-semibold text-white">Ordine Active</h3>
        <span className="text-[10px] text-slate-500">sursă: MT5 (timp real)</span>
        {acc && (
          <div className="ml-auto flex items-center gap-3 text-[11px] flex-wrap">
            <span className="text-slate-500">Capital folosit (marjă):{" "}
              <span className="font-mono text-amber-300">{acc.margin_used.toFixed(2)} $</span>
            </span>
            <span className="text-slate-500">Disponibil:{" "}
              <span className="font-mono text-profit">{acc.margin_free.toFixed(2)} $</span>
            </span>
            <span className="text-slate-500">P&L flotant:{" "}
              <span className={`font-mono ${acc.floating_pnl >= 0 ? "text-profit" : "text-loss"}`}>
                {acc.floating_pnl >= 0 ? "+" : ""}{acc.floating_pnl.toFixed(2)} $
              </span>
            </span>
            {acc.margin_level != null && (
              <span className="text-slate-500">Nivel marjă:{" "}
                <span className="font-mono text-slate-300">{acc.margin_level.toFixed(0)}%</span>
              </span>
            )}
          </div>
        )}
      </div>

      {nothing ? (
        <div className="text-xs text-slate-500">Nicio poziție deschisă și niciun ordin pending.</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-[10px] text-slate-500 border-b border-surface-border">
                <th className="text-left  px-2 py-1.5">Sursă</th>
                <th className="text-left  px-2 py-1.5">Simbol</th>
                <th className="text-left  px-2 py-1.5">Tip</th>
                <th className="text-right px-2 py-1.5">Volum</th>
                <th className="text-right px-2 py-1.5">Entry</th>
                <th className="text-right px-2 py-1.5">Curent</th>
                <th className="text-right px-2 py-1.5">SL</th>
                <th className="text-right px-2 py-1.5">TP</th>
                <th className="text-right px-2 py-1.5">Marjă $</th>
                <th className="text-right px-2 py-1.5">P&L $</th>
              </tr>
            </thead>
            <tbody>
              {data.positions.map(p => (
                <tr key={`p${p.ticket}`} className="border-b border-surface-border/40">
                  <td className="px-2 py-1.5"><Src s={p.source} /></td>
                  <td className="px-2 py-1.5 text-white font-medium">{p.symbol}</td>
                  <td className={`px-2 py-1.5 font-semibold ${p.type === "LONG" ? "text-profit" : "text-loss"}`}>
                    {p.type}
                  </td>
                  <td className="px-2 py-1.5 text-right font-mono text-slate-300">{p.volume}</td>
                  <td className="px-2 py-1.5 text-right font-mono text-slate-300">{p.entry}</td>
                  <td className="px-2 py-1.5 text-right font-mono text-slate-400">{p.current}</td>
                  <td className="px-2 py-1.5 text-right font-mono text-slate-500">{p.sl ?? "—"}</td>
                  <td className="px-2 py-1.5 text-right font-mono text-slate-500">{p.tp ?? "—"}</td>
                  <td className="px-2 py-1.5 text-right font-mono text-amber-300/80">{p.margin.toFixed(2)}</td>
                  <td className={`px-2 py-1.5 text-right font-mono font-semibold ${p.profit >= 0 ? "text-profit" : "text-loss"}`}>
                    {p.profit >= 0 ? "+" : ""}{p.profit.toFixed(2)}
                  </td>
                </tr>
              ))}
              {data.pending.map(o => (
                <tr key={`o${o.ticket}`} className="border-b border-surface-border/40 opacity-70">
                  <td className="px-2 py-1.5"><Src s={o.source} /></td>
                  <td className="px-2 py-1.5 text-white font-medium">{o.symbol}</td>
                  <td className="px-2 py-1.5 text-slate-400">{o.type}</td>
                  <td className="px-2 py-1.5 text-right font-mono text-slate-300">{o.volume}</td>
                  <td className="px-2 py-1.5 text-right font-mono text-slate-300">{o.entry}</td>
                  <td className="px-2 py-1.5 text-right font-mono text-slate-600">pending</td>
                  <td className="px-2 py-1.5 text-right font-mono text-slate-500">{o.sl ?? "—"}</td>
                  <td className="px-2 py-1.5 text-right font-mono text-slate-500">{o.tp ?? "—"}</td>
                  <td className="px-2 py-1.5 text-right font-mono text-slate-600">—</td>
                  <td className="px-2 py-1.5 text-right font-mono text-slate-600">—</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
