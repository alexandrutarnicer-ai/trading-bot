import { useState } from "react";
import { useMt5Status } from "../api/hooks";

const MT5_SETUP_GUIDE = [
  {
    title: "1. Instalează MetaTrader 5",
    items: [
      "Descarcă MT5 de la brokerul tău (ICMarkets, Pepperstone etc.)",
      "Instalează și deschide aplicația",
    ],
  },
  {
    title: "2. Loghează-te pe cont",
    items: [
      "Mergi la File → Login to Trade Account",
      "Introdu login, parolă și serverul brokerului",
      "Selectează contul Demo sau Live",
    ],
  },
  {
    title: "3. Activează AutoTrading",
    items: [
      "Apasă butonul \"AutoTrading\" din toolbar (devine verde)",
      "Sau folosește scurtătura Ctrl+E",
      "Fără AutoTrading, bot-ul nu poate plasa ordine",
    ],
  },
  {
    title: "4. Menține MT5 deschis",
    items: [
      "MT5 trebuie să rămână deschis în fundal",
      "Bot-ul Python se conectează prin IPC la MT5 terminal",
      "La repornire PC, MT5 se pornește automat dacă task scheduler e configurat",
    ],
  },
];

export function Mt5Status() {
  const { data, isLoading } = useMt5Status();
  const [open, setOpen] = useState(false);
  const [showGuide, setShowGuide] = useState(false);

  const connected = data?.connected ?? false;

  return (
    <div className="bg-surface-card rounded-xl border border-surface-border overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-3 px-4 py-3 hover:bg-surface-border/20 transition-colors text-left"
      >
        <div className={`w-2 h-2 rounded-full flex-shrink-0 ${
          isLoading ? "bg-slate-600" :
          connected  ? "bg-profit animate-pulse" : "bg-loss"
        }`} />
        <span className="text-sm font-semibold text-white flex-1">MetaTrader 5</span>

        {isLoading ? (
          <span className="text-xs text-slate-600">Se verifică...</span>
        ) : connected ? (
          <div className="flex items-center gap-3 text-xs text-slate-400">
            <span>
              Cont <span className="text-white font-mono">{data?.account}</span>
            </span>
            <span className="text-slate-600">·</span>
            <span>{data?.server}</span>
            {data?.balance != null && (
              <>
                <span className="text-slate-600">·</span>
                <span className="text-profit font-medium">
                  {data.balance.toLocaleString("ro-RO", { minimumFractionDigits: 2 })} {data?.currency}
                </span>
              </>
            )}
          </div>
        ) : (
          <span className="text-xs px-2 py-0.5 rounded-full bg-loss/20 text-loss">Deconectat</span>
        )}
        <span className="text-slate-500 ml-1">{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div className="border-t border-surface-border px-4 py-4 space-y-4">
          {connected ? (
            <div className="grid grid-cols-2 gap-3">
              {[
                { label: "Cont", value: data?.account ?? "—" },
                { label: "Server", value: data?.server ?? "—" },
                { label: "Balance", value: data?.balance != null ? `${data.balance.toLocaleString("ro-RO", { minimumFractionDigits: 2 })} ${data?.currency}` : "—" },
                { label: "Equity", value: data?.equity != null ? `${data.equity.toLocaleString("ro-RO", { minimumFractionDigits: 2 })} ${data?.currency}` : "—" },
              ].map(({ label, value }) => (
                <div key={label} className="bg-surface rounded-lg px-3 py-2">
                  <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-0.5">{label}</div>
                  <div className="text-sm text-white font-mono">{value}</div>
                </div>
              ))}
            </div>
          ) : (
            <div className="space-y-3">
              <div className="bg-loss/10 border border-loss/20 rounded-lg p-3">
                <p className="text-xs font-medium text-loss mb-1">MT5 nu este conectat</p>
                <p className="text-xs text-slate-400">
                  {data?.error ?? "Verifică că MetaTrader 5 este deschis și logat pe un cont."}
                </p>
              </div>
              <button
                onClick={() => setShowGuide((v) => !v)}
                className="text-xs text-slate-500 hover:text-slate-300 underline transition-colors"
              >
                {showGuide ? "Ascunde ghidul" : "Cum configurez MT5?"}
              </button>
              {showGuide && (
                <div className="bg-surface rounded-xl border border-surface-border p-4 space-y-4">
                  {MT5_SETUP_GUIDE.map((section) => (
                    <div key={section.title} className="space-y-1.5">
                      <div className="text-xs font-semibold text-white">{section.title}</div>
                      <ol className="space-y-1">
                        {section.items.map((item, i) => (
                          <li key={i} className="flex gap-2 text-xs text-slate-400">
                            <span className="text-slate-600 flex-shrink-0">{i + 1}.</span>
                            <span>{item}</span>
                          </li>
                        ))}
                      </ol>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
