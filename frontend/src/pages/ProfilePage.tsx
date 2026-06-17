import { useState, useEffect } from "react";
import {
  useProfileList, useProfile, useMeta, useSaveProfile, useCreateProfile, useDeleteProfile,
  useBotStatus, useSessions, usePauseSession, useResumeSession,
} from "../api/hooks";
import { SessionEditor } from "../components/SessionEditor";
import { InfoTooltip } from "../components/InfoTooltip";
import { BotControl } from "../components/BotControl";
import { TelegramSettings } from "../components/TelegramSettings";
import { Mt5Status } from "../components/Mt5Status";
import type { Profile, ProfileSession } from "../api/types";

const DEFAULT_SESSION = (id: string): ProfileSession => ({
  id,
  session_key: "custom",
  label:        "",
  enabled:      true,
  markets:      [],
  entry_tf:     "M15",
  trend_tf:     "M30",
  direction:    "LONG",
  pullback_window: 8,
  session_start: 8,
  session_end:   18,
  skip_hours:    [],
  skip_weekdays: [],
  expire_bars:   4,
  account_fraction: 0.125,
  risk_pct:      0.01,
  risk_base:     0.01,
  risk_mid:      0.01,
  risk_top:      0.01,
  risk_max:      0.01,
  execute_trades: false,
  rsi_enabled:   true,
  rsi_buy_min:   40,
  rsi_buy_max:   65,
  rsi_sell_min:  35,
  rsi_sell_max:  60,
  ema_alignment_enabled: true,
  body_strength_enabled: false,
  body_strength_min_atr_ratio: 0.15,
  atr_max_pips:  {},
  circuit_breaker: 3,
  r_base: 2.5,
  r_mid:  3.5,
  r_top:  4.5,
  r_max:  5.5,
  r_mid_threshold: 1,
  r_top_threshold: 2,
  r_max_threshold: 3,
  backtest_results: null,
});

const PROFILE_TIP =
  "Un profil conține una sau mai multe sesiuni de tranzacționare. " +
  "Fiecare sesiune are propriile piețe, timeframe, filtre și parametri. " +
  "Profilul Standard este cel validat și activ — modifică-l cu atenție.";

export function ProfilePage({ onNavigateToAudit }: { onNavigateToAudit: () => void }) {
  const { data: profiles, isLoading: loadingList } = useProfileList();
  const { data: meta } = useMeta();
  const { data: botStatus } = useBotStatus();

  const runningProfileId = botStatus?.running ? (botStatus.active_profile_id ?? null) : null;

  const [activeId, setActiveId] = useState<string>("standard");
  const { data: serverProfile, isLoading: loadingProfile } = useProfile(activeId);

  const [draft, setDraft] = useState<Profile | null>(null);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (serverProfile) {
      setDraft(serverProfile);
      setDirty(false);
    }
  }, [serverProfile]);

  const { data: liveSessions } = useSessions();
  const pauseS  = usePauseSession();
  const resumeS = useResumeSession();

  const save   = useSaveProfile();
  const create = useCreateProfile();
  const del    = useDeleteProfile();
  const [newId, setNewId] = useState("");
  const [newName, setNewName] = useState("");
  const [showNew, setShowNew] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [profileDropOpen, setProfileDropOpen] = useState(false);

  const handleSessionChange = (idx: number, updated: ProfileSession) => {
    if (!draft) return;
    const sessions = [...draft.sessions];
    sessions[idx] = updated;
    setDraft({ ...draft, sessions });
    setDirty(true);
  };

  const handleSessionRemove = (idx: number) => {
    if (!draft) return;
    const sessions = draft.sessions.filter((_, i) => i !== idx);
    setDraft({ ...draft, sessions });
    setDirty(true);
  };

  const handleAddSession = () => {
    if (!draft) return;
    const existing = draft.sessions.map((s) => s.id);
    // Genereaza un ID unic
    let n = draft.sessions.length + 1;
    let newSid = `S${n}`;
    while (existing.includes(newSid)) { n++; newSid = `S${n}`; }
    const sessions = [...draft.sessions, DEFAULT_SESSION(newSid)];
    setDraft({ ...draft, sessions });
    setDirty(true);
  };

  const handleSave = async () => {
    if (!draft) return;
    setSaveError(null);
    try {
      await save.mutateAsync({ id: draft.id, data: draft });
      setDirty(false);
    } catch (e: unknown) {
      setSaveError(e instanceof Error ? e.message : "Eroare la salvare");
    }
  };

  const handleReset = () => {
    if (serverProfile) { setDraft(serverProfile); setDirty(false); }
  };

  const handleCreate = async () => {
    if (!newId.trim()) return;
    try {
      const created = await create.mutateAsync({
        id: newId.trim(),
        name: newName.trim() || newId.trim(),
      }) as Profile;
      setActiveId(created.id);
      setShowNew(false);
      setNewId("");
      setNewName("");
    } catch (e: unknown) {
      setSaveError(e instanceof Error ? e.message : "Eroare la creare");
    }
  };

  const handleDelete = async () => {
    try {
      await del.mutateAsync(activeId);
      setConfirmDelete(false);
      setActiveId("standard");
    } catch (e: unknown) {
      setSaveError(e instanceof Error ? e.message : "Eroare la stergere");
    }
  };

  if (loadingList || !meta) {
    return <div className="flex items-center justify-center h-64 text-slate-500 text-sm">Se încarcă...</div>;
  }

  return (
    <div className="max-w-4xl mx-auto px-4 py-6 space-y-5">
      {/* MT5 + Bot control + Telegram */}
      <Mt5Status />
      <BotControl profileId={activeId} profileName={draft?.name} />
      <TelegramSettings />

      {/* Profile selector */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          {/* Custom dropdown cu indicator ON */}
          <div
            className="relative"
            tabIndex={0}
            onBlur={() => setTimeout(() => setProfileDropOpen(false), 150)}
          >
            <button
              onClick={() => setProfileDropOpen((v) => !v)}
              className={`flex items-center gap-2 bg-surface-card border text-white text-sm rounded-lg px-3 py-1.5 focus:outline-none hover:border-slate-400 transition-colors ${
                runningProfileId && activeId === runningProfileId
                  ? "border-profit/60"
                  : "border-surface-border"
              }`}
            >
              {runningProfileId && activeId === runningProfileId && (
                <span className="w-2 h-2 rounded-full bg-profit animate-pulse flex-shrink-0" />
              )}
              <span>{profiles?.find((p) => p.id === activeId)?.name ?? activeId}</span>
              {runningProfileId && activeId === runningProfileId && (
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-profit/20 text-profit font-bold ml-1">ON</span>
              )}
              <span className="text-slate-500 text-xs ml-1">{profileDropOpen ? "▲" : "▼"}</span>
            </button>

            {profileDropOpen && (
              <div className="absolute top-full left-0 mt-1 bg-surface-card border border-surface-border rounded-xl shadow-xl z-20 min-w-[200px] py-1 overflow-hidden">
                {profiles?.map((p) => {
                  const isRunning  = p.id === runningProfileId;
                  const isSelected = p.id === activeId;
                  return (
                    <button
                      key={p.id}
                      onClick={() => { setActiveId(p.id); setProfileDropOpen(false); }}
                      className={`w-full flex items-center gap-2.5 px-3 py-2 text-sm text-left transition-colors hover:bg-surface-border/40 ${
                        isSelected ? "text-white bg-surface-border/20" : "text-slate-300"
                      }`}
                    >
                      <span className={`w-2 h-2 rounded-full flex-shrink-0 ${
                        isRunning ? "bg-profit animate-pulse" : "bg-transparent"
                      }`} />
                      <span className="flex-1">{p.name}</span>
                      {isRunning && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-profit/20 text-profit font-bold">ON</span>
                      )}
                    </button>
                  );
                })}
              </div>
            )}
          </div>
          <InfoTooltip text={PROFILE_TIP} />
        </div>

        <button
          onClick={() => setShowNew((v) => !v)}
          className="text-xs px-3 py-1.5 rounded-lg border border-surface-border text-slate-400 hover:text-white hover:border-slate-400 transition-colors"
        >
          + Profil nou
        </button>

        {/* Stergere profil — ascuns pentru standard */}
        {activeId !== "standard" && (
          confirmDelete ? (
            <div className="flex items-center gap-2">
              <span className="text-xs text-loss">Stergi profilul „{draft?.name}"?</span>
              <button onClick={handleDelete} disabled={del.isPending}
                className="text-xs px-2.5 py-1 rounded bg-loss/80 hover:bg-loss text-white transition-colors disabled:opacity-50">
                {del.isPending ? "..." : "Da, sterge"}
              </button>
              <button onClick={() => setConfirmDelete(false)}
                className="text-xs px-2.5 py-1 rounded border border-surface-border text-slate-400 hover:text-white transition-colors">
                Anulează
              </button>
            </div>
          ) : (
            <button
              onClick={() => setConfirmDelete(true)}
              className="text-xs px-3 py-1.5 rounded-lg border border-loss/40 text-loss/70 hover:border-loss hover:text-loss transition-colors"
            >
              Șterge profil
            </button>
          )
        )}

        {dirty && (
          <div className="flex items-center gap-2 ml-auto">
            {saveError && <span className="text-xs text-loss">{saveError}</span>}
            <button onClick={handleReset}
              className="text-xs px-3 py-1.5 rounded-lg border border-surface-border text-slate-400 hover:text-white transition-colors">
              Reset
            </button>
            <button onClick={handleSave} disabled={save.isPending}
              className="text-xs px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 transition-colors font-medium">
              {save.isPending ? "Se salvează..." : "Salvează"}
            </button>
          </div>
        )}
      </div>

      {/* New profile form */}
      {showNew && (
        <div className="bg-surface-card border border-surface-border rounded-xl p-4 flex gap-3 items-end flex-wrap">
          <div className="space-y-1">
            <label className="text-xs text-slate-500">ID (slug)</label>
            <input value={newId}
              onChange={(e) => setNewId(e.target.value.toLowerCase().replace(/\s/g, "_"))}
              placeholder="ex: agresiv"
              className="bg-surface border border-surface-border rounded px-2 py-1 text-sm text-white focus:outline-none focus:border-blue-500 w-36"
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-slate-500">Nume afișare</label>
            <input value={newName} onChange={(e) => setNewName(e.target.value)}
              placeholder="ex: Agresiv"
              className="bg-surface border border-surface-border rounded px-2 py-1 text-sm text-white focus:outline-none focus:border-blue-500 w-40"
            />
          </div>
          <button onClick={handleCreate} disabled={!newId.trim() || create.isPending}
            className="text-xs px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 transition-colors">
            Creează
          </button>
          <button onClick={() => setShowNew(false)}
            className="text-xs px-3 py-1.5 rounded-lg border border-surface-border text-slate-400 hover:text-white transition-colors">
            Anulează
          </button>
          <p className="w-full text-xs text-slate-500 mt-1">
            Profilul nou va fi gol — vei adăuga sesiunile manual.
          </p>
        </div>
      )}

      {/* Profile info + capital */}
      {draft && (
        <div className="flex items-center gap-3 flex-wrap text-xs text-slate-500">
          <span className="text-slate-300 font-medium">{draft.name}</span>
          {draft.description && <span>· {draft.description}</span>}
          <span className="text-slate-600">
            {draft.sessions.length} sesiune{draft.sessions.length !== 1 ? "i" : ""}
          </span>
          {draft.updated_at && (
            <span className="ml-auto">
              Ultima salvare: {draft.updated_at.slice(0, 16).replace("T", " ")}
            </span>
          )}
        </div>
      )}


      {/* Sessions */}
      {loadingProfile ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-14 rounded-xl bg-surface-border/30 animate-pulse" />
          ))}
        </div>
      ) : draft ? (
        <div className="space-y-3">
          {draft.sessions.length === 0 && (
            <div className="text-center py-10 text-slate-500 text-sm border border-dashed border-surface-border rounded-xl">
              Nicio sesiune. Apasă „+ Adaugă sesiune" pentru a configura prima sesiune.
            </div>
          )}
          {draft.sessions.map((session, idx) => {
            const liveS  = liveSessions?.find(s => s.id === session.session_key);
            const isPaused = liveS?.paused ?? false;
            return (
              <SessionEditor
                key={session.id + idx}
                session={session}
                meta={meta}
                onJobStarted={onNavigateToAudit}
                onChange={(updated) => handleSessionChange(idx, updated)}
                onRemove={() => handleSessionRemove(idx)}
                paused={isPaused}
                onPauseToggle={() =>
                  isPaused
                    ? resumeS.mutate(session.session_key)
                    : pauseS.mutate(session.session_key)
                }
              />
            );
          })}
          <button
            onClick={handleAddSession}
            className="w-full py-3 rounded-xl border border-dashed border-surface-border text-slate-500 hover:text-slate-300 hover:border-slate-500 transition-colors text-sm"
          >
            + Adaugă sesiune
          </button>
        </div>
      ) : null}
    </div>
  );
}
