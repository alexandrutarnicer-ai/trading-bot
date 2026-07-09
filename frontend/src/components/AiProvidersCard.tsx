import { useState } from "react";
import { Plus, Trash2, KeyRound } from "lucide-react";
import { useAiProviders, useAiSaveProviders, useAiTestProvider } from "../api/hooks";
import type { AiProviderTestResult } from "../api/types";

/**
 * Surse AI (Consiliu) — registru multi-provider cu failover automat.
 * Vezi docs/PLAN_SURSE_AI_MULTI_PROVIDER.md. Schimbarile se aplica la
 * urmatorul consiliu (motorul reciteste config-ul per iteratie).
 */

const ROLE_LABELS: Record<string, string> = {
  technical:   "Analist Tehnic",
  macro:       "Analist Macro",
  risk:        "Risk Manager",
  head_trader: "Head Trader",
};

const TYPE_LABELS: Record<string, string> = {
  ollama:            "Ollama (local, gratuit)",
  anthropic:         "Claude (Anthropic)",
  gemini:            "Google Gemini",
  openai_compatible: "OpenAI-compatibil (ChatGPT, Groq, DeepSeek...)",
};

function fmtRetry(s: number): string {
  if (s >= 3600) return `~${Math.round(s / 3600)}h`;
  if (s >= 60) return `~${Math.round(s / 60)} min`;
  return `${s}s`;
}

export function AiProvidersCard() {
  const { data } = useAiProviders();
  const save = useAiSaveProviders();
  const testMut = useAiTestProvider();
  const [testResults, setTestResults] = useState<Record<string, AiProviderTestResult>>({});
  const [testing, setTesting] = useState<string | null>(null);
  const [keyDrafts, setKeyDrafts] = useState<Record<string, string>>({});
  const [showAdd, setShowAdd] = useState(false);
  const [addForm, setAddForm] = useState({
    name: "", type: "openai_compatible", model: "", base_url: "", key: "",
  });

  if (!data) return null;
  const { providers, role_assignments, health } = data;
  const enabledNames = Object.keys(providers).filter(n => providers[n].enabled);

  const runTest = (name: string) => {
    setTesting(name);
    testMut.mutate(name, {
      onSuccess: r => { setTestResults(p => ({ ...p, [name]: r })); setTesting(null); },
      onError: e => {
        setTestResults(p => ({ ...p, [name]: { ok: false, latency_s: 0, detail: (e as Error).message, kind: "network" } }));
        setTesting(null);
      },
    });
  };

  const saveKey = (name: string) => {
    const key = keyDrafts[name];
    if (!key) return;
    save.mutate({ keys: { [name]: key } }, {
      onSuccess: () => setKeyDrafts(p => ({ ...p, [name]: "" })),
    });
  };

  const submitAdd = () => {
    const name = addForm.name.trim().toLowerCase().replace(/[^a-z0-9_-]/g, "");
    if (!name || !addForm.model.trim()) return;
    const spec: Record<string, unknown> = {
      type: addForm.type, model: addForm.model.trim(), enabled: false,
    };
    if (addForm.type === "openai_compatible" && addForm.base_url.trim())
      spec.base_url = addForm.base_url.trim();
    const body: Parameters<typeof save.mutate>[0] = { providers: { [name]: spec } };
    if (addForm.key.trim()) body.keys = { [name]: addForm.key.trim() };
    save.mutate(body, {
      onSuccess: () => { setShowAdd(false); setAddForm({ name: "", type: "openai_compatible", model: "", base_url: "", key: "" }); },
    });
  };

  return (
    <div className="bg-surface rounded-xl border border-surface-border p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-white flex items-center gap-2">
          Surse AI (Consiliu)
          <span className="text-[10px] text-slate-500 font-normal">
            failover automat pe Ollama · se aplică la următorul consiliu
          </span>
        </h3>
        <button onClick={() => setShowAdd(s => !s)}
          className="flex items-center gap-1 text-[11px] px-2 py-1 rounded-lg bg-surface-border/40 text-slate-300 hover:text-white">
          <Plus size={12} /> Adaugă sursă
        </button>
      </div>

      {showAdd && (
        <div className="border border-surface-border rounded-lg p-3 space-y-2 bg-surface/60">
          <div className="grid grid-cols-2 gap-2">
            <input placeholder="nume (ex: gemini2)" value={addForm.name}
              onChange={e => setAddForm(f => ({ ...f, name: e.target.value }))}
              className="bg-surface-card border border-surface-border rounded px-2 py-1 text-xs text-white" />
            <select value={addForm.type}
              onChange={e => setAddForm(f => ({ ...f, type: e.target.value }))}
              className="bg-surface-card border border-surface-border rounded px-2 py-1 text-xs text-white">
              {Object.entries(TYPE_LABELS).filter(([t]) => t !== "ollama").map(([t, l]) => (
                <option key={t} value={t}>{l}</option>
              ))}
            </select>
            <input placeholder="model (ex: gemini-2.5-flash)" value={addForm.model}
              onChange={e => setAddForm(f => ({ ...f, model: e.target.value }))}
              className="bg-surface-card border border-surface-border rounded px-2 py-1 text-xs text-white font-mono" />
            {addForm.type === "openai_compatible" && (
              <input placeholder="base URL (ex: https://api.groq.com/openai/v1)" value={addForm.base_url}
                onChange={e => setAddForm(f => ({ ...f, base_url: e.target.value }))}
                className="bg-surface-card border border-surface-border rounded px-2 py-1 text-xs text-white font-mono" />
            )}
            <input placeholder="cheie API" type="password" value={addForm.key}
              onChange={e => setAddForm(f => ({ ...f, key: e.target.value }))}
              className="bg-surface-card border border-surface-border rounded px-2 py-1 text-xs text-white font-mono" />
          </div>
          <button onClick={submitAdd} disabled={save.isPending}
            className="text-[11px] px-3 py-1 rounded-lg bg-profit/20 text-profit hover:bg-profit/30">
            Salvează sursa
          </button>
          {save.isError && <div className="text-[10px] text-loss">{(save.error as Error).message}</div>}
        </div>
      )}

      {/* Lista surselor */}
      <div className="space-y-2">
        {Object.entries(providers).map(([name, p]) => {
          const h = health[name];
          const tr = testResults[name];
          const stateDot = !p.enabled ? "bg-slate-600"
            : h?.status === "paused" ? "bg-amber-400"
            : h?.status === "disabled_auth" ? "bg-loss"
            : "bg-profit";
          const stateText = !p.enabled ? "INACTIV"
            : h?.status === "paused" ? `PAUZĂ — revine ${fmtRetry(h.retry_in_s)}`
            : h?.status === "disabled_auth" ? "DEZACTIVAT — cheie invalidă"
            : "SĂNĂTOS";
          return (
            <div key={name} className="border border-surface-border rounded-lg px-3 py-2 space-y-1.5">
              <div className="flex items-center gap-2 flex-wrap">
                <span className={`w-2 h-2 rounded-full shrink-0 ${stateDot}`} />
                <span className="text-xs font-semibold text-white">{name}</span>
                <span className="text-[10px] text-slate-500 font-mono">{p.model}</span>
                {p.is_default && (
                  <span className="text-[9px] px-1.5 py-0.5 rounded bg-blue-500/20 text-blue-300">DEFAULT</span>
                )}
                <span className={`text-[10px] ${h?.status === "paused" ? "text-amber-400" : h?.status === "disabled_auth" ? "text-loss" : "text-slate-500"}`}>
                  {stateText}
                </span>
                <div className="ml-auto flex items-center gap-1.5">
                  {!p.is_default && (
                    <button
                      onClick={() => save.mutate({ providers: { [name]: { enabled: !p.enabled } } })}
                      className={`text-[10px] px-2 py-0.5 rounded ${p.enabled ? "bg-slate-700/50 text-slate-300" : "bg-profit/20 text-profit"}`}>
                      {p.enabled ? "Dezactivează" : "Activează"}
                    </button>
                  )}
                  <button onClick={() => runTest(name)} disabled={testing === name}
                    className="text-[10px] px-2 py-0.5 rounded bg-blue-500/20 text-blue-300 hover:bg-blue-500/30">
                    {testing === name ? "Testez..." : "Testează"}
                  </button>
                  {!p.is_default && (
                    <button title="Șterge sursa"
                      onClick={() => { if (confirm(`Ștergi sursa ${name}?`)) save.mutate({ providers: { [name]: { _delete: true } } }); }}
                      className="text-slate-600 hover:text-loss">
                      <Trash2 size={12} />
                    </button>
                  )}
                </div>
              </div>
              {tr && (
                <div className={`text-[10px] ${tr.ok ? "text-profit" : "text-loss"}`}>
                  {tr.ok ? `✓ funcționează (${tr.latency_s}s, ${tr.detail})` : `✗ ${tr.detail}`}
                </div>
              )}
              {h?.status !== "healthy" && h?.reason && p.enabled && (
                <div className="text-[10px] text-amber-400/80">{h.reason}</div>
              )}
              {p.needs_key && (
                <div className="flex items-center gap-1.5">
                  <KeyRound size={11} className="text-slate-500 shrink-0" />
                  <input type="password"
                    placeholder={p.has_key ? "cheie salvată — înlocuiește..." : "cheie API"}
                    value={keyDrafts[name] ?? ""}
                    onChange={e => setKeyDrafts(d => ({ ...d, [name]: e.target.value }))}
                    className="flex-1 bg-surface-card border border-surface-border rounded px-2 py-0.5 text-[11px] text-white font-mono" />
                  <button onClick={() => saveKey(name)} disabled={!keyDrafts[name] || save.isPending}
                    className="text-[10px] px-2 py-0.5 rounded bg-profit/20 text-profit disabled:opacity-40">
                    Salvează
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Asignarea rolurilor */}
      <div className="border-t border-surface-border/50 pt-2 space-y-1.5">
        <div className="text-[11px] font-semibold text-slate-300">Roluri → surse</div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-1.5">
          {Object.entries(ROLE_LABELS).map(([role, label]) => {
            const assigned = role_assignments[role] ?? "ollama";
            const hAssigned = health[assigned];
            const degraded = providers[assigned]?.enabled && hAssigned && hAssigned.status !== "healthy";
            return (
              <div key={role} className="flex items-center gap-2 text-[11px]">
                <span className="text-slate-400 w-28 shrink-0">{label}</span>
                <select value={assigned}
                  onChange={e => save.mutate({ role_assignments: { [role]: e.target.value } })}
                  className="bg-surface-card border border-surface-border rounded px-2 py-0.5 text-[11px] text-white">
                  {enabledNames.map(n => <option key={n} value={n}>{n}</option>)}
                </select>
                {degraded && (
                  <span className="text-[9px] text-amber-400">⚠ acum: fallback (temporar)</span>
                )}
              </div>
            );
          })}
        </div>
        <div className="text-[10px] text-slate-600">
          Dacă sursa unui rol pică (quota/rețea), rolul trece automat pe următoarea sursă
          sănătoasă, apoi pe Ollama. Revenire automată la expirarea pauzei.
        </div>
      </div>
    </div>
  );
}
