import { Gamepad2, Loader2 } from "lucide-react";
import { useAiGamingMode, useSetAiGamingMode } from "../api/hooks";

/**
 * Mod gaming AI (per mașină, data/ai/machine.json): placa video rămâne liberă pentru jocuri.
 * Pornit → Ollama pe procesor + descărcat după fiecare apel, rolurile pe sursa cloud (Gemini), Ollama doar rezervă.
 * Fără restart: AI Engine și filtrul AI din Custom recitesc configurația la fiecare iterație.
 */
export function GamingModeToggle({ compact = false }: { compact?: boolean }) {
  const { data } = useAiGamingMode();
  const set = useSetAiGamingMode();
  const on = data?.enabled ?? false;
  const busy = set.isPending;
  const title = on
    ? `Mod gaming PORNIT pe acest PC: placa video liberă; analizele pe ${data?.cloud_source ?? "Ollama"}, ` +
      "Ollama doar rezervă, pe procesor. Click → revine pe placa video."
    : "Mod gaming: eliberează placa video pentru jocuri (Ollama pe procesor, analizele pe sursa cloud). " +
      "Se aplică imediat, fără restart, doar pe acest calculator. Regulile de risc nu se schimbă.";

  function toggle() {
    if (!on && !window.confirm(
      "Pornești Modul gaming pe acest calculator?\n\n" +
      "• placa video se eliberează imediat (modelul Ollama e descărcat);\n" +
      `• analizele AI trec pe ${data?.cloud_source ?? "sursa cloud"}; dacă aceasta pică, Ollama rulează pe procesor (mai lent);\n` +
      "• regulile de risc și limitele nu se schimbă; la orice eroare AI decizia rămâne WAIT.")) return;
    set.mutate(!on);
  }

  return (
    <button onClick={toggle} disabled={busy} title={title}
      className={`flex items-center gap-1.5 rounded-lg font-semibold disabled:opacity-50 ${compact ? "text-[11px] px-2 py-1" : "text-xs px-3 py-2"} ${
        on ? "bg-amber-500/20 text-amber-300 hover:bg-amber-500/30 border border-amber-500/40"
           : "bg-surface-card text-slate-400 hover:text-slate-200 border border-surface-border"}`}>
      {busy ? <Loader2 size={12} className="animate-spin" /> : <Gamepad2 size={compact ? 12 : 14} />}
      {on ? "Mod gaming: PORNIT" : "Mod gaming"}
    </button>
  );
}
