import { useState, useEffect } from "react";
import {
  useProfileList, useProfile, useMeta, useSaveProfile, useCreateProfile,
} from "../api/hooks";
import { SessionEditor } from "../components/SessionEditor";
import type { Profile, ProfileSession } from "../api/types";

export function ProfilePage() {
  const { data: profiles, isLoading: loadingList } = useProfileList();
  const { data: meta } = useMeta();

  const [activeId, setActiveId] = useState<string>("standard");
  const { data: serverProfile, isLoading: loadingProfile } = useProfile(activeId);

  // Local editable copy
  const [draft, setDraft] = useState<Profile | null>(null);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (serverProfile) {
      setDraft(serverProfile);
      setDirty(false);
    }
  }, [serverProfile]);

  const save = useSaveProfile();
  const create = useCreateProfile();
  const [newId, setNewId] = useState("");
  const [newName, setNewName] = useState("");
  const [showNew, setShowNew] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const handleSessionChange = (idx: number, updated: ProfileSession) => {
    if (!draft) return;
    const sessions = [...draft.sessions];
    sessions[idx] = updated;
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
      await create.mutateAsync({ id: newId.trim(), name: newName.trim() || newId.trim() });
      setActiveId(newId.trim());
      setShowNew(false);
      setNewId("");
      setNewName("");
    } catch (e: unknown) {
      setSaveError(e instanceof Error ? e.message : "Eroare la creare");
    }
  };

  if (loadingList || !meta) {
    return <div className="flex items-center justify-center h-64 text-slate-500 text-sm">Se incarca...</div>;
  }

  return (
    <div className="max-w-4xl mx-auto px-4 py-6 space-y-5">
      {/* Profile selector */}
      <div className="flex items-center gap-3">
        <select
          value={activeId}
          onChange={(e) => setActiveId(e.target.value)}
          className="bg-surface-card border border-surface-border text-white text-sm rounded-lg px-3 py-1.5 focus:outline-none focus:border-blue-500"
        >
          {profiles?.map((p) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>

        <button
          onClick={() => setShowNew((v) => !v)}
          className="text-xs px-3 py-1.5 rounded-lg border border-surface-border text-slate-400 hover:text-white hover:border-slate-400 transition-colors"
        >
          + Profil nou
        </button>

        {dirty && (
          <div className="flex items-center gap-2 ml-auto">
            {saveError && <span className="text-xs text-loss">{saveError}</span>}
            <button
              onClick={handleReset}
              className="text-xs px-3 py-1.5 rounded-lg border border-surface-border text-slate-400 hover:text-white transition-colors"
            >
              Reset
            </button>
            <button
              onClick={handleSave}
              disabled={save.isPending}
              className="text-xs px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 transition-colors font-medium"
            >
              {save.isPending ? "Se salveaza..." : "Salveaza"}
            </button>
          </div>
        )}
      </div>

      {/* New profile form */}
      {showNew && (
        <div className="bg-surface-card border border-surface-border rounded-xl p-4 flex gap-3 items-end">
          <div className="space-y-1">
            <label className="text-xs text-slate-500">ID (slug)</label>
            <input
              value={newId}
              onChange={(e) => setNewId(e.target.value.toLowerCase().replace(/\s/g, "_"))}
              placeholder="ex: agresiv"
              className="bg-surface border border-surface-border rounded px-2 py-1 text-sm text-white focus:outline-none focus:border-blue-500 w-40"
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-slate-500">Nume afisare</label>
            <input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="ex: Agresiv"
              className="bg-surface border border-surface-border rounded px-2 py-1 text-sm text-white focus:outline-none focus:border-blue-500 w-40"
            />
          </div>
          <button
            onClick={handleCreate}
            disabled={!newId.trim() || create.isPending}
            className="text-xs px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 transition-colors"
          >
            Creeaza
          </button>
          <button
            onClick={() => setShowNew(false)}
            className="text-xs px-3 py-1.5 rounded-lg border border-surface-border text-slate-400 hover:text-white transition-colors"
          >
            Anuleaza
          </button>
        </div>
      )}

      {/* Profile info */}
      {draft && (
        <div className="flex items-center gap-3 text-xs text-slate-500">
          <span className="text-slate-300 font-medium">{draft.name}</span>
          {draft.description && <span>· {draft.description}</span>}
          {draft.updated_at && (
            <span className="ml-auto">Ultima salvare: {draft.updated_at.slice(0, 16).replace("T", " ")}</span>
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
          {draft.sessions.map((session, idx) => (
            <SessionEditor
              key={session.id}
              session={session}
              meta={meta}
              onChange={(updated) => handleSessionChange(idx, updated)}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}
