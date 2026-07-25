import { useState } from "react";
import { Mic, Power, Loader2, Pause, Play, Moon } from "lucide-react";
import {
  useVoiceStatus, useVoiceStart, useVoiceStop, useVoicePause, useVoiceResume,
  useVoiceConfig, useSaveVoiceConfig,
  useVoiceAutostartStatus, useVoiceAutostartEnable, useVoiceAutostartDisable,
} from "../api/hooks";

/**
 * Card in Profile pentru EMA — asistentul vocal (voice_bridge/). Controale:
 *   • Start / Stop  — porneste/opreste procesul lui EMA.
 *   • Pauza / Reia  — MUT (microfon oprit) fara sa opresti procesul. Pentru
 *                     scenariul „sunt pe Discord cu prietenii" — un click si EMA
 *                     nu mai asculta; alt click si revine.
 * Read-only prin design (nu poate plasa/inchide ordine, nu modifica cod).
 */
export function VoiceBridgeCard() {
  const { data: st } = useVoiceStatus();
  const start  = useVoiceStart();
  const stop   = useVoiceStop();
  const pause  = useVoicePause();
  const resume = useVoiceResume();
  const { data: vcfg } = useVoiceConfig();
  const saveCfg = useSaveVoiceConfig();
  const { data: auto } = useVoiceAutostartStatus();
  const autoEnable  = useVoiceAutostartEnable();
  const autoDisable = useVoiceAutostartDisable();
  const [busy, setBusy] = useState(false);

  const running = st?.running ?? false;
  const paused  = st?.paused ?? false;
  const name    = st?.assistant_name || "Jarvis";
  const modeLabel: Record<string, string> = {
    wake: 'wake word ("Hey Jarvis")', name: 'nume ("Jarvis, …")', ptt: "push-to-talk",
  };

  const toggle = async () => {
    setBusy(true);
    try {
      if (running) await stop.mutateAsync();
      else         await start.mutateAsync();
    } catch { /* eroarea apare in status */ }
    setBusy(false);
  };

  const togglePause = async () => {
    try {
      if (paused) await resume.mutateAsync();
      else        await pause.mutateAsync();
    } catch { /* status reflecta */ }
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
          <Mic size={15} className="text-fuchsia-400" />
          <span className="text-sm font-semibold text-white">{name} — asistent vocal</span>
        </div>
        <span className={`flex items-center gap-1.5 text-[11px] font-medium ${
          running ? (paused ? "text-amber-300" : "text-emerald-300") : "text-slate-500"
        }`}>
          <span className={`h-2 w-2 rounded-full ${
            running ? (paused ? "bg-amber-400" : "bg-emerald-400 animate-pulse") : "bg-slate-600"
          }`} />
          {running ? (paused ? "în pauză (mut)" : "activ · ascultă") : "oprit"}
        </span>
      </div>

      <p className="text-[11px] text-slate-400 leading-snug">
        Comandă botul prin voce: spune <code>„Hey Jarvis"</code> apoi <code>„status"</code>,
        {" "}<code>„report"</code>, <code>„pause session 7"</code> sau întreabă liber (engleză).
        {" "}Local, <span className="text-slate-300">doar-citire</span> (nu plasează ordine).
      </p>

      {/* Mod de activare — push-to-talk dezactivat implicit, doar dacă îl alegi */}
      <label className="flex items-center justify-between gap-2">
        <span className="text-[11px] text-slate-300">Mod de activare</span>
        <select
          value={vcfg?.wake_mode ?? "openwakeword"}
          onChange={(e) => saveCfg.mutate({ wake_mode: e.target.value })}
          disabled={saveCfg.isPending}
          className="bg-surface-input border border-surface-border rounded-md text-[11px] text-slate-200 px-2 py-1 disabled:opacity-50"
        >
          <option value="openwakeword">„Hey Jarvis" (recomandat)</option>
          <option value="ptt">Push-to-talk (ENTER)</option>
          <option value="name">Nume („Jarvis, …")</option>
        </select>
      </label>
      {vcfg?.wake_mode && vcfg.wake_mode !== "openwakeword" && (
        <p className="text-[10px] text-amber-300/80">
          Nu e „Hey Jarvis". Se aplică la următoarea pornire (Stop → Start).
        </p>
      )}
      {saveCfg.isSuccess && running && (
        <p className="text-[10px] text-slate-500">Salvat — repornește Jarvis (Stop → Start) ca să se aplice.</p>
      )}

      {/* status compact cand ruleaza */}
      {running && (
        <div className="grid grid-cols-3 gap-2 text-[10px]">
          <div><div className="text-slate-500">Mod</div>
            <div className="text-slate-300">{st?.mode ? (modeLabel[st.mode] ?? st.mode) : "—"}</div></div>
          <div><div className="text-slate-500">Voce</div>
            <div className="text-slate-300">{st?.voice_style ?? "—"}</div></div>
          <div><div className="text-slate-500">STT</div>
            <div className="text-slate-300">{st?.stt_model ?? "—"}</div></div>
        </div>
      )}

      {/* Pauza / Reia — pentru „sunt pe Discord". Doar cand ruleaza. */}
      {running && (
        <button
          onClick={togglePause}
          disabled={pause.isPending || resume.isPending}
          className={`w-full flex items-center justify-center gap-2 py-2 rounded-lg text-xs font-semibold transition-colors ${
            paused
              ? "bg-emerald-500/15 text-emerald-300 hover:bg-emerald-500/25"
              : "bg-amber-500/15 text-amber-300 hover:bg-amber-500/25"
          } disabled:opacity-50`}
          title={paused ? "Reia ascultarea" : "Mut EMA (microfon oprit) — ex: cand joci pe Discord"}
        >
          {paused ? <Play size={14} /> : <Pause size={14} />}
          {paused ? "Reia ascultarea" : "Pauză (mut — sunt pe Discord)"}
        </button>
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
        {running ? "Oprește EMA" : "Pornește EMA"}
      </button>

      {/* Autostart la boot — dezactivat implicit */}
      <label className="flex items-center justify-between gap-2 pt-1">
        <div className="flex flex-col">
          <span className="text-xs text-slate-300">Pornire automată la boot</span>
          <span className="text-[10px] text-slate-500">
            Pornește EMA la fiecare login Windows. Dezactivat implicit — microfonul
            ar asculta de la pornire (pune-o pe pauză când nu vrei).
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

      <div className="flex items-start gap-2 text-[10px] text-slate-500 leading-snug">
        <Moon size={12} className="flex-shrink-0 mt-0.5" />
        <span>
          Poți muta și vocal: <code>„Jarvis, go to sleep"</code> / <code>„Jarvis, wake up"</code>.
          Prima pornire descarcă modelul Whisper. Detalii: docs/VOICE_BRIDGE.md.
        </span>
      </div>
    </div>
  );
}
