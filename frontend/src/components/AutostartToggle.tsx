import { useState } from "react";
import { Power } from "lucide-react";
import { useAutostartStatus, useAutostartEnable, useAutostartDisable } from "../api/hooks";

export function AutostartToggle() {
  const { data, isLoading } = useAutostartStatus();
  const enable  = useAutostartEnable();
  const disable = useAutostartDisable();
  const [confirm, setConfirm] = useState(false);

  const enabled  = data?.enabled ?? false;
  const pending  = enable.isPending || disable.isPending;

  if (isLoading) return null;

  if (confirm && enabled) {
    return (
      <div className="flex items-center gap-1.5">
        <span className="text-[11px] text-slate-400">Dezactivezi autostart?</span>
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
    <button
      onClick={() => {
        if (enabled) {
          setConfirm(true);
        } else {
          enable.mutate();
        }
      }}
      disabled={pending}
      title={enabled ? "Autostart activ — click pentru dezactivare" : "Autostart inactiv — click pentru activare (necesita Administrator)"}
      className={`flex items-center gap-1.5 text-[11px] px-2.5 py-1 rounded-lg border transition-colors disabled:opacity-50 ${
        enabled
          ? "border-profit/40 text-profit/80 hover:border-profit hover:text-profit"
          : "border-surface-border text-slate-500 hover:border-slate-500 hover:text-slate-300"
      }`}
    >
      <Power size={11} />
      <span>Autostart {enabled ? "ON" : "OFF"}</span>
    </button>
  );
}
