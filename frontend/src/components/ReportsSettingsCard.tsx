import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { FileBarChart, Loader2 } from "lucide-react";
import { apiFetch } from "../api/client";

/**
 * Rapoarte programate (Telegram + Notificări): orele, mașina care le trimite, analiza AI și
 * trimiterea manuală. Orele sunt în fusul orar al aplicației. Săptămânalul e mereu VINERI.
 */

interface ReportsConfig {
  enabled_on_this_machine: boolean;
  daily_time: string;
  weekly_weekday: number;
  weekly_time: string;
  monthly_day: number;
  monthly_time: string;
  ai_analysis: boolean;
  timezone?: string;
  last_weekly_window?: [string, string];
  last_monthly_window?: [string, string];
}

const fmt = (iso?: string) => (iso ? `${iso.slice(8, 10)}.${iso.slice(5, 7)} ${iso.slice(11, 16)}` : "—");

export function ReportsSettingsCard() {
  const qc = useQueryClient();
  const { data } = useQuery<ReportsConfig>({ queryKey: ["reports-config"], queryFn: () => apiFetch("/reports/config") });
  const [form, setForm] = useState<ReportsConfig | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => { if (data) setForm(data); }, [data]);
  const save = useMutation({
    mutationFn: (b: Partial<ReportsConfig>) => apiFetch("/reports/config", { method: "PUT", body: b }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["reports-config"] }); setMsg("Salvat."); },
    onError: (e: Error) => setMsg(e.message),
  });
  const send = useMutation({
    mutationFn: (kind: "weekly" | "monthly") => apiFetch(`/reports/send-${kind}`, { method: "POST" }),
    onSuccess: () => setMsg("Raport trimis pe Telegram (și în Notificări)."),
    onError: (e: Error) => setMsg(e.message),
  });
  if (!form) return null;
  const set = (k: keyof ReportsConfig, v: unknown) => setForm({ ...form, [k]: v } as ReportsConfig);
  const timeInput = (k: "daily_time" | "weekly_time" | "monthly_time") => (
    <input type="time" value={form[k]} onChange={e => set(k, e.target.value)}
      className="bg-surface-card border border-surface-border rounded px-2 py-0.5 text-xs text-white" />
  );

  return (
    <div className="bg-surface rounded-xl border border-surface-border p-4 space-y-3 text-xs">
      <div className="flex items-center gap-2">
        <FileBarChart size={15} className="text-blue-300" />
        <span className="text-sm font-semibold text-white">Rapoarte programate</span>
        <span className="text-slate-500">fus orar {form.timezone ?? "?"}</span>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <div className="space-y-1">
          <div className="text-slate-400">Zilnic — în fiecare zi la</div>{timeInput("daily_time")}
        </div>
        <div className="space-y-1">
          <div className="text-slate-400">Săptămânal — <b>vineri</b> la</div>{timeInput("weekly_time")}
          <div className="text-[10px] text-slate-500">Ultima fereastră: {fmt(form.last_weekly_window?.[0])} → {fmt(form.last_weekly_window?.[1])} (include weekendul)</div>
        </div>
        <div className="space-y-1">
          <div className="text-slate-400">Lunar — în ziua
            <input type="number" min={1} max={28} value={form.monthly_day} onChange={e => set("monthly_day", +e.target.value)}
              className="mx-1 w-12 bg-surface-card border border-surface-border rounded px-1 py-0.5 text-white" /> la</div>
          {timeInput("monthly_time")}
          <div className="text-[10px] text-slate-500">Luna completă precedentă: {fmt(form.last_monthly_window?.[0])} → {fmt(form.last_monthly_window?.[1])}</div>
        </div>
      </div>
      <label className="flex items-center gap-2 text-slate-300">
        <input type="checkbox" checked={form.ai_analysis} onChange={e => set("ai_analysis", e.target.checked)} />
        Analiză AI în raport (consultativă; dacă AI e indisponibil raportul se trimite oricum)
      </label>
      <label className="flex items-center gap-2 text-slate-300">
        <input type="checkbox" checked={form.enabled_on_this_machine} onChange={e => set("enabled_on_this_machine", e.target.checked)} />
        Trimite rapoartele de pe această mașină
        <span className="text-slate-500">— lasă activ DOAR pe mașina care rulează engine-urile (altfel primești rapoarte duble)</span>
      </label>
      <div className="flex items-center gap-2 flex-wrap">
        <button onClick={() => save.mutate(form)} disabled={save.isPending}
          className="px-3 py-1 rounded-lg bg-blue-500/20 text-blue-300 hover:bg-blue-500/30 disabled:opacity-50 font-semibold">
          {save.isPending ? <Loader2 size={12} className="animate-spin" /> : "Salvează"}
        </button>
        <button onClick={() => send.mutate("weekly")} disabled={send.isPending}
          className="px-3 py-1 rounded-lg border border-surface-border text-slate-300 hover:text-white disabled:opacity-50">Trimite săptămânalul acum</button>
        <button onClick={() => send.mutate("monthly")} disabled={send.isPending}
          className="px-3 py-1 rounded-lg border border-surface-border text-slate-300 hover:text-white disabled:opacity-50">Trimite lunarul acum</button>
        {send.isPending && <Loader2 size={12} className="animate-spin text-slate-400" />}
        {msg && <span className="text-slate-400">{msg}</span>}
      </div>
    </div>
  );
}
