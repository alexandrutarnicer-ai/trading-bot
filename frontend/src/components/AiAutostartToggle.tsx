import { useState } from "react";
import { Bot } from "lucide-react";
import { useAiAutostartStatus, useAiAutostartEnable, useAiAutostartDisable } from "../api/hooks";
import { InfoTooltip } from "./InfoTooltip";

const AI_AUTOSTART_TIP =
  "Pornire automată Windows a MOTORULUI AI: la fiecare login, Ollama + MT5 " +
  "pornesc, iar după 120s motorul AI + watchdog-ul lui pornesc automat. " +
  "Task partajat cu botul: MT5 rămâne dacă oricare autostart e activ. " +
  "Activarea/dezactivarea necesită drepturi de Administrator (prompt UAC).";


export function AiAutostartToggle() {
  const { data, isLoading } = useAiAutostartStatus();
  const enable  = useAiAutostartEnable();
  const disable = useAiAutostartDisable();
  const [confirm, setConfirm] = useState(false);

  const enabled  = data?.enabled ?? false;
  const pending  = enable.isPending || disable.isPending;

  if (isLoading) return null;

  if (confirm && enabled) {
    return (
      <div className="flex items-center gap-1.5">
        <span className="text-[11px] text-slate-400">Dezactivezi autostart AI?</span>
        <button
          onClick={() => { disable.mutate(); setConfirm(false); }}
          disabled={pending}
          className="text-[11px] px-2 py-0.5 rounded border border-loss/50 text-loss hover:bg-loss/10 transition-colors disabled:opacity-50"
        >
          Da
        </button>
        <button
          onClick={() => setConfirm(false)}
          className="text-[11px] px-2 py-0.5 rounded border border-surface-border text-slate-500 hover:text-slate-300 transition-colors"
        >
          Nu
        </button>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2">
      <InfoTooltip text={AI_AUTOSTART_TIP} position="below" align="right" wide />
      <button
        onClick={() => {
          if (enabled) {
            setConfirm(true);
          } else {
            enable.mutate();
          }
        }}
        disabled={pending}
        className={`flex items-center gap-1.5 text-[11px] px-2.5 py-1 rounded-lg border transition-colors disabled:opacity-50 ${
          enabled
            ? "border-purple-400/40 text-purple-300/80 hover:border-purple-400 hover:text-purple-300"
            : "border-surface-border text-slate-500 hover:border-slate-500 hover:text-slate-300"
        }`}
      >
        <Bot size={11} />
        <span>Autostart AI {enabled ? "ON" : "OFF"}</span>
      </button>
    </div>
  );
}
