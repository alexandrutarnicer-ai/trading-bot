import { useState } from "react";
import { MessageSquare, Power, Loader2, ShieldAlert } from "lucide-react";
import {
  useBridgeStatus, useBridgeStart, useBridgeStop,
  useBridgeAutostartStatus, useBridgeAutostartEnable, useBridgeAutostartDisable,
} from "../api/hooks";

/**
 * Card in Profile (langa setarile Telegram) pentru PUNTEA Telegram — chat-ul de
 * colaborare (comanzi bot + AI + Claude de pe telefon). Controalele apar DOAR
 * daca Telegram e configurat (token + chat_id). Autostart la boot = OFF by default.
 */
export function TelegramBridgeCard() {
  const { data: st } = useBridgeStatus();
  const start = useBridgeStart();
  const stop  = useBridgeStop();
  const { data: auto } = useBridgeAutostartStatus();
  const autoEnable  = useBridgeAutostartEnable();
  const autoDisable = useBridgeAutostartDisable();
  const [busy, setBusy] = useState(false);

  const configured = st?.configured ?? false;
  const running    = st?.running ?? false;

  const toggle = async () => {
    setBusy(true);
    try {
      if (running) await stop.mutateAsync();
      else         await start.mutateAsync();
    } catch { /* eroarea apare in status */ }
    setBusy(false);
  };

  const toggleAutostart = async () => {
    try {
      if (auto?.enabled) await autoDisable.mutateAsync();
      else               await autoEnable.mutateAsync();
    } catch { /* UAC / eroare */ }
  };

  return (
    <div className="bg-surface-card border border-surface-border rounded-xl p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <MessageSquare size={15} className="text-sky-400" />
          <span className="text-sm font-semibold text-white">Punte Telegram — chat colaborare</span>
        </div>
        <span className={`flex items-center gap-1.5 text-[11px] font-medium ${
          running ? "text-emerald-300" : "text-slate-500"
        }`}>
          <span className={`h-2 w-2 rounded-full ${running ? "bg-emerald-400 animate-pulse" : "bg-slate-600"}`} />
          {running ? (st?.idle ? "activ · inactiv (economie)" : "activ") : "oprit"}
        </span>
      </div>

      <p className="text-[11px] text-slate-400 leading-snug">
        Comandă botul de pe telefon prin acest chat: <code>/status</code>, <code>/raport</code>,
        {" "}<code>ai …</code>, <code>claude …</code> (analiză), și — cu modul edit — <code>claude! …</code>{" "}
        pentru fix critic de la distanță. Proces separat, nu afectează botul/motorul.
      </p>

      {!configured ? (
        <div className="flex items-start gap-2 text-[11px] text-amber-300 bg-amber-500/10 border border-amber-500/30 rounded-lg p-2.5">
          <ShieldAlert size={14} className="flex-shrink-0 mt-0.5" />
          <span>Configurează mai întâi Telegram (token + Chat ID) în secțiunea de deasupra —
            puntea nu poate porni fără ele.</span>
        </div>
      ) : (
        <>
          {/* status compact */}
          {running && (
            <div className="grid grid-cols-3 gap-2 text-[10px]">
              <div><div className="text-slate-500">Claude CLI</div>
                <div className={st?.claude_detected ? "text-emerald-300" : "text-amber-300"}>
                  {st?.claude_detected ? "detectat" : "fallback API"}</div></div>
              <div><div className="text-slate-500">Mod edit</div>
                <div className={st?.allow_writes ? "text-amber-300 font-semibold" : "text-slate-300"}>
                  {st?.allow_writes ? "ACTIVAT ⚠" : "read-only"}</div></div>
              <div><div className="text-slate-500">Ultim mesaj</div>
                <div className="text-slate-300">{st?.last_message_ts?.slice(11, 16) ?? "—"}</div></div>
            </div>
          )}

          {/* Start / Stop */}
          <button
            onClick={toggle}
            disabled={busy}
            className={`w-full flex items-center justify-center gap-2 py-2 rounded-lg text-xs font-semibold transition-colors ${
              running
                ? "bg-loss/15 text-loss hover:bg-loss/25"
                : "bg-emerald-500/15 text-emerald-300 hover:bg-emerald-500/25"
            } disabled:opacity-50`}
          >
            {busy ? <Loader2 size={14} className="animate-spin" /> : <Power size={14} />}
            {running ? "Oprește puntea" : "Pornește puntea"}
          </button>

          {/* Autostart la boot */}
          <label className="flex items-center justify-between gap-2 pt-1">
            <div className="flex flex-col">
              <span className="text-xs text-slate-300">Pornire automată la boot</span>
              <span className="text-[10px] text-slate-500">
                Ca la bot — pornește puntea la fiecare login Windows. Dezactivat implicit.
              </span>
            </div>
            <button
              onClick={toggleAutostart}
              disabled={autoEnable.isPending || autoDisable.isPending}
              className={`relative inline-flex h-5 w-9 flex-shrink-0 items-center rounded-full transition-colors ${
                auto?.enabled ? "bg-emerald-500/70" : "bg-slate-600"
              } disabled:opacity-50`}
              title={auto?.enabled ? "Autostart ON — click pentru dezactivare (UAC)" : "Autostart OFF — click pentru activare (UAC)"}
            >
              <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${
                auto?.enabled ? "translate-x-4" : "translate-x-1"
              }`} />
            </button>
          </label>
          {(autoEnable.isPending || autoDisable.isPending) && (
            <p className="text-[10px] text-slate-500">Se deschide fereastra UAC pentru permisiuni admin…</p>
          )}

          <p className="text-[10px] text-slate-600 leading-snug">
            Detalii + comenzi: docs/TELEGRAM_BRIDGE.md · Ghid secțiunea 13. Trimite <code>/ajutor</code> pe chat.
          </p>
        </>
      )}
    </div>
  );
}
