import { useState } from "react";
import { Plus, Trash2, KeyRound, RefreshCw } from "lucide-react";
import { useAiProviders, useAiSaveProviders, useAiTestProvider, useAiProviderModels, useAiTestAllProviders } from "../api/hooks";
import type { AiProviderTestResult } from "../api/types";
import type { AiTestAllResult } from "../api/hooks";

/**
 * Surse AI (Consiliu) — registru multi-provider cu failover automat.
 * Vezi docs/PLAN_SURSE_AI_MULTI_PROVIDER.md. Schimbarile se aplica la
 * urmatorul consiliu (motorul reciteste config-ul per iteratie).
 */

// Rolurile obligatorii + cele OPTIONALE (Quant / Avocatul Diavolului). Cele
// optionale au aceleasi optiuni de sursa + failover ca cele obligatorii —
// ruleaza doar cand sunt activate (AI Engine: card Consens · Filtru: per sesiune).
const ROLE_LABELS: Record<string, string> = {
  technical:       "Analist Tehnic",
  macro:           "Analist Macro",
  risk:            "Risk Manager",
  head_trader:     "Head Trader",
  quant:           "🧮 Analist Cantitativ (opțional)",
  devils_advocate: "😈 Avocatul Diavolului (opțional)",
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
  const testAllMut = useAiTestAllProviders();
  const [testAll, setTestAll] = useState<AiTestAllResult | null>(null);
  const modelsMut = useAiProviderModels();
  const [testResults, setTestResults] = useState<Record<string, AiProviderTestResult>>({});
  const [testing, setTesting] = useState<string | null>(null);
  const [keyDrafts, setKeyDrafts] = useState<Record<string, string>>({});
  const [showAdd, setShowAdd] = useState(false);
  const [addForm, setAddForm] = useState({
    name: "", type: "openai_compatible", model: "", base_url: "", key: "",
  });
  // Descoperire dinamica de modele: liste per sursa (+"__add" pt formularul nou)
  const [modelLists, setModelLists] = useState<Record<string, string[]>>({});
  const [modelDrafts, setModelDrafts] = useState<Record<string, string>>({});
  const [discovering, setDiscovering] = useState<string | null>(null);
  const [discoverErr, setDiscoverErr] = useState<Record<string, string>>({});

  const discover = (key: string, body: Parameters<typeof modelsMut.mutate>[0], force = false) => {
    if (discovering === key || (!force && modelLists[key]?.length)) return;
    setDiscovering(key);
    setDiscoverErr(p => ({ ...p, [key]: "" }));
    modelsMut.mutate(body, {
      onSuccess: r => {
        setDiscovering(null);
        if (r.ok) setModelLists(p => ({ ...p, [key]: r.models }));
        else setDiscoverErr(p => ({ ...p, [key]: r.detail || "descoperire eșuată" }));
      },
      onError: e => {
        setDiscovering(null);
        setDiscoverErr(p => ({ ...p, [key]: (e as Error).message }));
      },
    });
  };

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
        <div className="flex items-center gap-2">
          <button
            onClick={() => testAllMut.mutate(undefined, { onSuccess: r => setTestAll(r) })}
            disabled={testAllMut.isPending}
            title="Testează TOATE sursele în paralel (auth + disponibilitate + latență)"
            className="flex items-center gap-1 text-[11px] px-2 py-1 rounded-lg bg-blue-500/20 text-blue-300 hover:bg-blue-500/30 disabled:opacity-50">
            {testAllMut.isPending ? "Se testează..." : "🩺 Testează sursele"}
          </button>
          <button onClick={() => setShowAdd(s => !s)}
            className="flex items-center gap-1 text-[11px] px-2 py-1 rounded-lg bg-surface-border/40 text-slate-300 hover:text-white">
            <Plus size={12} /> Adaugă sursă
          </button>
        </div>
      </div>

      {/* Rezultat "Testeaza sursele" — sumar sanatate + per sursa */}
      {testAll && (
        <div className={`rounded-lg border p-3 space-y-1.5 ${testAll.all_down ? "border-loss/50 bg-loss/10" : "border-surface-border bg-surface/60"}`}>
          <div className="flex items-center gap-2 flex-wrap text-[11px]">
            <span className="font-semibold text-white">Diagnostic surse:</span>
            <span className="text-profit">{testAll.n_healthy} sănătoase</span>
            <span className="text-slate-600">·</span>
            <span className={testAll.failed.length ? "text-loss" : "text-slate-500"}>
              {testAll.failed.length} picate
            </span>
            <span className="text-slate-600">din {testAll.n_total}</span>
            {testAll.all_down && <span className="ml-auto text-loss font-semibold">⛔ NICIO SURSĂ DISPONIBILĂ</span>}
          </div>
          {testAll.healthy.length > 0 && (
            <div className="text-[10px] text-slate-400">
              Disponibile: <span className="text-profit font-mono">{testAll.healthy.join(", ")}</span>
            </div>
          )}
          {testAll.roles_at_risk.length > 0 && (
            <div className="text-[10px] text-amber-400">
              ⚠ Roluri fără acoperire (sursă + Ollama picate): {testAll.roles_at_risk.join(", ")}
            </div>
          )}
          <div className="space-y-0.5 pt-1">
            {Object.entries(testAll.results).map(([name, r]) => (
              <div key={name} className="flex items-center gap-2 text-[10px]">
                <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${r.ok ? "bg-profit" : "bg-loss"}`} />
                <span className="font-mono text-slate-300 w-24 shrink-0">{name}</span>
                {r.ok
                  ? <span className="text-profit">✓ {r.latency_s}s{r.detail ? ` · ${r.detail}` : ""}</span>
                  : <span className="text-loss truncate">✗ {r.kind ? `[${r.kind}] ` : ""}{r.detail}</span>}
              </div>
            ))}
          </div>
        </div>
      )}

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
            <div className="flex items-center gap-1">
              <input list="models-__add" placeholder="model (ex: gemini-2.5-flash)" value={addForm.model}
                onChange={e => setAddForm(f => ({ ...f, model: e.target.value }))}
                className="flex-1 bg-surface-card border border-surface-border rounded px-2 py-1 text-xs text-white font-mono" />
              <datalist id="models-__add">
                {(modelLists["__add"] ?? []).map(m => <option key={m} value={m} />)}
              </datalist>
              <button type="button" title="Descoperă modelele disponibile (necesită cheie API)"
                onClick={() => discover("__add", {
                  type: addForm.type,
                  base_url: addForm.base_url.trim() || undefined,
                  key: addForm.key.trim() || undefined,
                }, true)}
                className="text-[10px] px-2 py-1 rounded bg-blue-500/20 text-blue-300 hover:bg-blue-500/30 whitespace-nowrap">
                {discovering === "__add" ? "Caut..." : "Descoperă"}
              </button>
            </div>
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
          {discoverErr["__add"] && (
            <div className="text-[10px] text-amber-400/80">modele: {discoverErr["__add"]}</div>
          )}
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
                <input list={`models-${name}`}
                  value={modelDrafts[name] ?? p.model ?? ""}
                  onChange={e => setModelDrafts(d => ({ ...d, [name]: e.target.value }))}
                  onFocus={() => discover(name, { name })}
                  title="Modelul sursei — focus = descoperă lista live de la API"
                  className="w-44 bg-surface-card border border-surface-border rounded px-1.5 py-0.5 text-[10px] text-slate-300 font-mono" />
                <datalist id={`models-${name}`}>
                  {(modelLists[name] ?? []).map(m => <option key={m} value={m} />)}
                </datalist>
                <button title="Reîncarcă modelele disponibile"
                  onClick={() => discover(name, { name }, true)}
                  className="text-slate-600 hover:text-slate-300">
                  <RefreshCw size={11} className={discovering === name ? "animate-spin" : ""} />
                </button>
                {modelDrafts[name] !== undefined && modelDrafts[name] !== p.model && modelDrafts[name].trim() && (
                  <button
                    onClick={() => save.mutate({ providers: { [name]: { model: modelDrafts[name].trim() } } },
                      { onSuccess: () => setModelDrafts(d => { const n = { ...d }; delete n[name]; return n; }) })}
                    className="text-[10px] px-2 py-0.5 rounded bg-profit/20 text-profit">
                    Salvează model
                  </button>
                )}
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
              {modelLists[name] && !discoverErr[name] && (
                <div className="text-[10px] text-slate-500">
                  {modelLists[name].length} modele disponibile la sursă — tastează în câmpul model pentru sugestii
                </div>
              )}
              {discoverErr[name] && (
                <div className="text-[10px] text-amber-400/80">modele: {discoverErr[name]}</div>
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
