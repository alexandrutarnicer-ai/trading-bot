/**
 * Mt5SyncButton — indicator sync MT5 + buton trigger reconciliere manuala.
 *
 * Afiseaza:
 *  - icon verde + "Sincronizat" — ultima sincronizare recenta fara discrepante
 *  - icon portocaliu + "X discrepante" — discrepante detectate (nu fixate)
 *  - icon rosu + "Eroare" — MT5 deconectat sau eroare sync
 *  - icon gri — nu a rulat inca
 *
 * Click → expandeaza panoul cu detalii + butoane Detecteaza / Corecteaza.
 */

import { useState } from "react";
import { useSyncStatus, useRunSync } from "../api/hooks";
import type { SyncDiscrepancy } from "../api/types";

function relTime(iso: string | null): string {
  if (!iso) return "";
  const ms  = Date.now() - new Date(iso.replace(" ", "T")).getTime();
  const min = Math.floor(ms / 60_000);
  if (min < 1)  return "acum";
  if (min < 60) return `${min}m`;
  const h = Math.floor(min / 60);
  if (h < 24)   return `${h}h`;
  return `${Math.floor(h / 24)}z`;
}

export default function Mt5SyncButton() {
  const [open, setOpen]   = useState(false);
  const { data: status }  = useSyncStatus();
  const { mutate: runSync, isPending } = useRunSync();

  const [lastResult, setLastResult] = useState<string | null>(null);

  const totalDisc = status?.total_discrepancies ?? 0;
  const hasError  = status?.ok === false;
  const noData    = status?.ok == null;

  let iconColor = "text-gray-500";
  let label     = "Sync MT5";
  let dot       = "bg-gray-400";

  if (hasError) {
    iconColor = "text-red-400";
    label     = "Eroare sync";
    dot       = "bg-red-500";
  } else if (noData) {
    iconColor = "text-gray-400";
    label     = "Sync MT5";
    dot       = "bg-gray-500";
  } else if (totalDisc > 0) {
    iconColor = "text-orange-400";
    label     = `${totalDisc} discrepante`;
    dot       = "bg-orange-400 animate-pulse";
  } else {
    iconColor = "text-green-400";
    label     = `Sincronizat ${relTime(status?.time ?? null)}`;
    dot       = "bg-green-400";
  }

  function handleSync(fix: boolean) {
    setLastResult(null);
    runSync({ fix }, {
      onSuccess: (r) => {
        if (r.ok === false) {
          setLastResult(`Eroare: ${r.error ?? "MT5 deconectat"}`);
        } else if (fix) {
          setLastResult(`Corectate ${r.total_fixed} intrari.`);
        } else {
          setLastResult(
            r.total_discrepancies
              ? `${r.total_discrepancies} discrepante detectate.`
              : "Nicio discrepanta."
          );
        }
      },
      onError: (e) => setLastResult(`Eroare: ${e.message}`),
    });
  }

  const allDisc: Array<SyncDiscrepancy & { sessionLabel: string }> = [];
  for (const sess of (status?.sessions ?? [])) {
    for (const d of sess.discrepancies) {
      allDisc.push({ ...d, sessionLabel: sess.label });
    }
  }

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-1.5 px-2 py-1 rounded-md
                   bg-gray-800 hover:bg-gray-700 transition text-xs text-gray-300"
        title="Sync MT5 ↔ Dashboard"
      >
        {/* dot indicator */}
        <span className={`inline-block w-2 h-2 rounded-full ${dot}`} />

        {/* icon sync */}
        <svg className={`w-3.5 h-3.5 ${iconColor}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0
               0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
        </svg>

        <span className="hidden sm:inline">{label}</span>
      </button>

      {open && (
        <div className="absolute right-0 top-8 z-50 w-80 bg-gray-900 border border-gray-700
                        rounded-lg shadow-xl p-3 text-xs text-gray-300">
          <div className="flex items-center justify-between mb-2">
            <span className="font-semibold text-gray-200">MT5 Sync</span>
            <button onClick={() => setOpen(false)} className="text-gray-500 hover:text-gray-300">✕</button>
          </div>

          {status?.time && (
            <p className="text-gray-500 mb-2">Ultima verificare: {status.time}</p>
          )}

          {hasError && (
            <p className="text-red-400 mb-2">{status?.error ?? "MT5 deconectat"}</p>
          )}

          {!hasError && !noData && totalDisc === 0 && (
            <p className="text-green-400 mb-2">Nicio discrepanta detectata.</p>
          )}

          {allDisc.length > 0 && (
            <div className="mb-2 max-h-40 overflow-y-auto space-y-1">
              {allDisc.map((d, i) => (
                <div key={i} className="bg-gray-800 rounded p-1.5">
                  <span className="text-orange-400 font-mono">{d.sig_id}</span>
                  <span className="text-gray-500 ml-1">({d.symbol})</span>
                  <br />
                  <span className="text-gray-400">{d.detail}</span>
                  {d.result_r != null && (
                    <span className={`ml-1 font-mono ${d.result_r > 0 ? "text-green-400" : "text-red-400"}`}>
                      {d.result_r > 0 ? "+" : ""}{d.result_r.toFixed(3)}R
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}

          {lastResult && (
            <p className="text-blue-300 mb-2">{lastResult}</p>
          )}

          <div className="flex gap-2 mt-2">
            <button
              onClick={() => handleSync(false)}
              disabled={isPending}
              className="flex-1 py-1 rounded bg-gray-700 hover:bg-gray-600
                         disabled:opacity-50 transition text-gray-200"
            >
              {isPending ? "..." : "Detecteaza"}
            </button>
            <button
              onClick={() => handleSync(true)}
              disabled={isPending}
              className="flex-1 py-1 rounded bg-blue-700 hover:bg-blue-600
                         disabled:opacity-50 transition text-white"
              title="Scrie corectiile in outcomes.csv (sigur si cu botul activ)"
            >
              {isPending ? "..." : "Corecteaza"}
            </button>
          </div>
          <p className="text-gray-600 mt-1.5">
            Exceptie: sesiunile OBS (execute_trades=False)
          </p>
        </div>
      )}
    </div>
  );
}
