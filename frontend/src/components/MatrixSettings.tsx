import { useState, useEffect } from "react";
import { Boxes, ChevronDown, ChevronRight, Check } from "lucide-react";
import { useMatrixConfig, useSaveMatrixConfig } from "../api/hooks";

/**
 * Card in Profil pentru AL DOILEA CHAT — Matrix / Element (EU, gratuit). Configurezi
 * homeserver + camera + access token + user permis, si activezi. Campurile non-secrete
 * merg in data/telegram_bridge.json, token-ul in data/matrix_config.json (gitignored).
 * Se aplica dupa un restart al puntii (Stop -> Start din cardul de deasupra).
 */
export function MatrixSettings() {
  const { data: cfg } = useMatrixConfig();
  const save = useSaveMatrixConfig();

  const [open, setOpen]           = useState(false);
  const [enabled, setEnabled]     = useState(false);
  const [homeserver, setHomeserver] = useState("https://matrix.org");
  const [roomId, setRoomId]       = useState("");
  const [allowed, setAllowed]     = useState("");
  const [token, setToken]         = useState("");
  const [saved, setSaved]         = useState(false);
  const [error, setError]         = useState<string | null>(null);

  useEffect(() => {
    if (cfg) {
      setEnabled(cfg.enabled);
      setHomeserver(cfg.homeserver || "https://matrix.org");
      setRoomId(cfg.room_id || "");
      setAllowed((cfg.allowed_users || []).join(", "));
    }
  }, [cfg]);

  const handleSave = async () => {
    setError(null); setSaved(false);
    try {
      await save.mutateAsync({
        enabled, homeserver: homeserver.trim(), room_id: roomId.trim(),
        allowed_users: allowed.split(",").map(s => s.trim()).filter(Boolean),
        ...(token.trim() ? { access_token: token.trim() } : {}),
      });
      setSaved(true); setToken("");
      setTimeout(() => setSaved(false), 3000);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Eroare la salvare");
    }
  };

  return (
    <div className="bg-surface-card border border-surface-border rounded-xl overflow-hidden">
      <button className="w-full flex items-center justify-between px-4 py-3 hover:bg-surface-border/10"
              onClick={() => setOpen(o => !o)}>
        <div className="flex items-center gap-2">
          <Boxes size={15} className="text-indigo-400" />
          <span className="text-sm font-semibold text-white">Al doilea chat — Matrix / Element (EU)</span>
        </div>
        <div className="flex items-center gap-2">
          <span className={`text-[10px] px-1.5 py-0.5 rounded ${
            cfg?.enabled ? "bg-emerald-500/15 text-emerald-300" : "bg-slate-600/30 text-slate-400"
          }`}>{cfg?.enabled ? "activat" : "oprit"}</span>
          {open ? <ChevronDown size={14} className="text-slate-400" /> : <ChevronRight size={14} className="text-slate-400" />}
        </div>
      </button>

      {open && (
        <div className="px-4 pb-4 space-y-3">
          <p className="text-[11px] text-slate-400 leading-snug">
            Canal alternativ EU, gratuit — aceleași comenzi ca pe Telegram. Rulează izolat, oprit
            implicit. Pași pe telefon: Ghid → secțiunea 13, sau <code>docs/TELEGRAM_BRIDGE.md</code>.
          </p>

          <label className="flex items-center justify-between gap-2">
            <span className="text-xs text-slate-300">Activează canalul Matrix</span>
            <button
              onClick={() => setEnabled(e => !e)}
              className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
                enabled ? "bg-emerald-500/70" : "bg-slate-600"}`}
            >
              <span className={`inline-block h-3.5 w-3.5 rounded-full bg-white transition-transform ${
                enabled ? "translate-x-4" : "translate-x-1"}`} />
            </button>
          </label>

          <Field label="Homeserver" hint="ex: https://matrix.org sau https://tchncs.de (EU)">
            <input value={homeserver} onChange={e => setHomeserver(e.target.value)}
              className="w-full bg-surface border border-surface-border rounded px-2 py-1.5 text-xs text-white"
              placeholder="https://matrix.org" />
          </Field>

          <Field label="Room ID" hint="ID intern al camerei NEcriptate (Room info → Advanced): !AbC:matrix.org">
            <input value={roomId} onChange={e => setRoomId(e.target.value)}
              className="w-full bg-surface border border-surface-border rounded px-2 py-1.5 text-xs text-white font-mono"
              placeholder="!AbCdEf:matrix.org" />
          </Field>

          <Field label="User(i) permis(i)" hint="ID-ul tău Matrix (opțional; separă cu virgulă)">
            <input value={allowed} onChange={e => setAllowed(e.target.value)}
              className="w-full bg-surface border border-surface-border rounded px-2 py-1.5 text-xs text-white font-mono"
              placeholder="@tu:matrix.org" />
          </Field>

          <Field label="Access Token" hint={cfg?.token_set ? "salvat ✓ — lasă gol ca să-l păstrezi" : "Element → Settings → Help & About → Advanced → Access Token"}>
            <input value={token} onChange={e => setToken(e.target.value)} type="password"
              className="w-full bg-surface border border-surface-border rounded px-2 py-1.5 text-xs text-white font-mono"
              placeholder={cfg?.token_set ? "•••••••• (setat)" : "syt_..."} />
          </Field>

          {error && <p className="text-[11px] text-loss">{error}</p>}
          <button onClick={handleSave} disabled={save.isPending}
            className="w-full flex items-center justify-center gap-2 py-2 rounded-lg text-xs font-semibold bg-indigo-500/15 text-indigo-300 hover:bg-indigo-500/25 disabled:opacity-50">
            {saved ? <><Check size={14} /> Salvat — repornește puntea</> : "Salvează configurația Matrix"}
          </button>
          <p className="text-[10px] text-slate-600">
            După salvare, oprește și pornește puntea (cardul de deasupra) ca al doilea canal să pornească.
          </p>
        </div>
      )}
    </div>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-[11px] font-medium text-slate-300">{label}</span>
        {hint && <span className="text-[9px] text-slate-500 text-right">{hint}</span>}
      </div>
      {children}
    </div>
  );
}
