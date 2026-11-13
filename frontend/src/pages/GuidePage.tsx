import { useState, useRef } from "react";
import { ChevronDown, ChevronRight, BookOpen } from "lucide-react";

// ── Helpers ───────────────────────────────────────────────────────────────────

function Section({
  id,
  title,
  children,
}: {
  id: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section id={id} className="space-y-4 scroll-mt-16">
      <h2 className="text-base font-bold text-white border-b border-surface-border pb-2">
        {title}
      </h2>
      {children}
    </section>
  );
}

function SubSection({
  title,
  children,
  defaultOpen = true,
}: {
  title: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="bg-surface-card rounded-xl border border-surface-border overflow-hidden">
      <button
        className="w-full flex items-center gap-2 px-4 py-3 text-left hover:bg-surface-border/10 transition-colors"
        onClick={() => setOpen(o => !o)}
      >
        {open ? (
          <ChevronDown size={14} className="text-slate-400 flex-shrink-0" />
        ) : (
          <ChevronRight size={14} className="text-slate-400 flex-shrink-0" />
        )}
        <span className="text-sm font-semibold text-white">{title}</span>
      </button>
      {open && (
        <div className="px-4 pb-4 space-y-3 text-sm text-slate-300 leading-relaxed">
          {children}
        </div>
      )}
    </div>
  );
}

function Badge({ color, label }: { color: string; label: string }) {
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold ${color}`}>
      {label}
    </span>
  );
}

function Note({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex gap-2 bg-blue-500/10 border border-blue-500/30 rounded-lg p-3 text-xs text-blue-200">
      <span className="flex-shrink-0 text-blue-400">ℹ</span>
      <span>{children}</span>
    </div>
  );
}

function Warn({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex gap-2 bg-warn/10 border border-warn/30 rounded-lg p-3 text-xs text-warn">
      <span className="flex-shrink-0">⚠</span>
      <span>{children}</span>
    </div>
  );
}

function Tip({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex gap-2 bg-profit/10 border border-profit/30 rounded-lg p-3 text-xs text-profit">
      <span className="flex-shrink-0">💡</span>
      <span>{children}</span>
    </div>
  );
}

function KV({ k, v, vColor }: { k: string; v: string; vColor?: string }) {
  return (
    <div className="flex items-start gap-2 text-xs">
      <span className="text-slate-500 flex-shrink-0 w-32">{k}</span>
      <span className={`font-mono ${vColor ?? "text-slate-300"}`}>{v}</span>
    </div>
  );
}

// ── Strategy Diagram ──────────────────────────────────────────────────────────

function StrategyDiagram() {
  return (
    <div className="bg-surface rounded-xl border border-surface-border p-4 overflow-x-auto">
      <svg viewBox="0 0 700 200" className="w-full max-w-2xl mx-auto" style={{ minWidth: 460 }}>
        {/* Step 1 */}
        <rect x="10" y="75" width="115" height="50" rx="8" fill="#1e293b" stroke="#3b82f6" strokeWidth="1.5" />
        <text x="67" y="97" textAnchor="middle" fill="#93c5fd" fontSize="10" fontWeight="600">1. Trend</text>
        <text x="67" y="111" textAnchor="middle" fill="#64748b" fontSize="9">EMA200 pe M30</text>
        <text x="67" y="123" textAnchor="middle" fill="#64748b" fontSize="9">trend = 1 / -1 / 0</text>

        {/* Arrow */}
        <path d="M 125 100 L 155 100" stroke="#475569" strokeWidth="1.5" markerEnd="url(#a1)" fill="none" />

        {/* Step 2 */}
        <rect x="155" y="75" width="115" height="50" rx="8" fill="#1e293b" stroke="#22d3ee" strokeWidth="1.5" />
        <text x="212" y="97" textAnchor="middle" fill="#67e8f9" fontSize="10" fontWeight="600">2. Swing</text>
        <text x="212" y="111" textAnchor="middle" fill="#64748b" fontSize="9">HH → HL (LONG)</text>
        <text x="212" y="123" textAnchor="middle" fill="#64748b" fontSize="9">LL → LH (SHORT)</text>

        {/* Arrow */}
        <path d="M 270 100 L 300 100" stroke="#475569" strokeWidth="1.5" markerEnd="url(#a1)" fill="none" />

        {/* Step 3 */}
        <rect x="300" y="75" width="115" height="50" rx="8" fill="#1e293b" stroke="#f59e0b" strokeWidth="1.5" />
        <text x="357" y="97" textAnchor="middle" fill="#fcd34d" fontSize="10" fontWeight="600">3. Pullback</text>
        <text x="357" y="111" textAnchor="middle" fill="#64748b" fontSize="9">pret retrage spre</text>
        <text x="357" y="123" textAnchor="middle" fill="#64748b" fontSize="9">nivelul HL / LH</text>

        {/* Arrow */}
        <path d="M 415 100 L 445 100" stroke="#475569" strokeWidth="1.5" markerEnd="url(#a1)" fill="none" />

        {/* Step 4 */}
        <rect x="445" y="75" width="115" height="50" rx="8" fill="#1e293b" stroke="#22c55e" strokeWidth="1.5" />
        <text x="502" y="97" textAnchor="middle" fill="#86efac" fontSize="10" fontWeight="600">4. Intrare</text>
        <text x="502" y="111" textAnchor="middle" fill="#64748b" fontSize="9">bara închide peste</text>
        <text x="502" y="123" textAnchor="middle" fill="#64748b" fontSize="9">maximul pullback</text>

        {/* Optional criteria */}
        <text x="350" y="155" textAnchor="middle" fill="#475569" fontSize="9" fontStyle="italic">Filtre opționale: RSI · EMA alignment · TP fix pe nivelul R:R al pieței (2R / 3R / 4R)</text>

        {/* Bottom labels */}
        <text x="67" y="165" textAnchor="middle" fill="#334155" fontSize="8">TF trend: M30/D1</text>
        <text x="212" y="165" textAnchor="middle" fill="#334155" fontSize="8">window: 6–8 bare</text>
        <text x="357" y="165" textAnchor="middle" fill="#334155" fontSize="8">expire: 4 bare</text>
        <text x="502" y="165" textAnchor="middle" fill="#334155" fontSize="8">BUY/SELL STOP MT5</text>

        {/* Title */}
        <text x="350" y="25" textAnchor="middle" fill="#94a3b8" fontSize="11" fontWeight="600">Strategia Pullback-in-Trend</text>
        <text x="350" y="42" textAnchor="middle" fill="#475569" fontSize="9">Entry TF: M15 sau H1 · Trend TF: M30 sau D1</text>

        <defs>
          <marker id="a1" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
            <path d="M 0 0 L 6 3 L 0 6 Z" fill="#475569" />
          </marker>
        </defs>
      </svg>
    </div>
  );
}

// ── Signal lifecycle diagram ──────────────────────────────────────────────────

function SignalLifecycleDiagram() {
  return (
    <div className="bg-surface rounded-xl border border-surface-border p-4 overflow-x-auto">
      <svg viewBox="0 0 680 130" className="w-full" style={{ minWidth: 460 }}>
        {/* States */}
        {[
          { x: 10,  label: "Detectat",  sub: "signals.csv",  color: "#3b82f6" },
          { x: 165, label: "Plasat MT5", sub: "BUY/SELL STOP", color: "#f59e0b" },
          { x: 320, label: "Activat",   sub: "triggered=True", color: "#a855f7" },
          { x: 475, label: "Închis",    sub: "outcomes.csv",  color: "#22c55e" },
        ].map(({ x, label, sub, color }) => (
          <g key={label}>
            <rect x={x} y="30" width="130" height="50" rx="8" fill="#1e293b" stroke={color} strokeWidth="1.5" />
            <text x={x + 65} y="53" textAnchor="middle" fill={color} fontSize="10" fontWeight="600">{label}</text>
            <text x={x + 65} y="69" textAnchor="middle" fill="#64748b" fontSize="9">{sub}</text>
          </g>
        ))}
        {/* Arrows */}
        {[140, 295, 450].map(x => (
          <path key={x} d={`M ${x} 55 L ${x + 25} 55`} stroke="#475569" strokeWidth="1.5" markerEnd="url(#a2)" fill="none" />
        ))}
        {/* Labels on arrows */}
        <text x="153" y="47" textAnchor="middle" fill="#475569" fontSize="8">place_order</text>
        <text x="308" y="47" textAnchor="middle" fill="#475569" fontSize="8">pret atinge entry</text>
        <text x="463" y="47" textAnchor="middle" fill="#475569" fontSize="8">TP / SL / vineri</text>

        {/* Deviation: expirat */}
        <path d="M 230 80 Q 230 110 165 110 Q 100 110 100 80" stroke="#ef4444" strokeWidth="1" strokeDasharray="3 2" fill="none" markerEnd="url(#a3)" />
        <text x="197" y="120" textAnchor="middle" fill="#ef4444" fontSize="8">expirat (fără trigger)</text>

        {/* Deviation: invalidat */}
        <path d="M 297 55 Q 297 18 230 18 Q 163 18 163 55" stroke="#f97316" strokeWidth="1" strokeDasharray="3 2" fill="none" />
        <text x="230" y="13" textAnchor="middle" fill="#f97316" fontSize="8">invalidat (structura ruptă)</text>

        <defs>
          <marker id="a2" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
            <path d="M 0 0 L 6 3 L 0 6 Z" fill="#475569" />
          </marker>
          <marker id="a3" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
            <path d="M 0 0 L 6 3 L 0 6 Z" fill="#ef4444" />
          </marker>
        </defs>
      </svg>
    </div>
  );
}

// ── Table of contents ─────────────────────────────────────────────────────────

const TOC = [
  { id: "overview",        label: "1. Prezentare generală" },
  { id: "dashboard",       label: "2. Dashboard" },
  { id: "profile",         label: "3. Custom Engine" },
  { id: "audit",           label: "4. Audit & Backteste" },
  { id: "strategy",        label: "5. Strategia" },
  { id: "risk",            label: "6. Risc & Setări Globale" },
  { id: "config",          label: "7. Start / Autostart" },
  { id: "signals",         label: "8. Semnale & Ordine" },
  { id: "notifications",   label: "9. Notificări" },
  { id: "reports",         label: "10. Rapoarte" },
  { id: "ai-engine",       label: "11. AI Engine" },
  { id: "daily-engine",    label: "12. Daily Engine" },
  { id: "noisy-engine",    label: "12b. Noisy Engine" },
  { id: "live",            label: "13. Demo / Live" },
  { id: "data-recovery",   label: "14. Date & Recovery" },
  { id: "telegram-bridge", label: "15. Punte Telegram" },
  { id: "removed",         label: "16. Eliminat / Dormant" },
];

// ── Page ──────────────────────────────────────────────────────────────────────

export function GuidePage() {
  const [activeSection, setActiveSection] = useState("overview");
  const contentRef = useRef<HTMLDivElement>(null);

  function scrollTo(id: string) {
    setActiveSection(id);
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  return (
    <div className="flex min-h-screen">
      {/* Sidebar TOC */}
      <aside className="hidden lg:flex flex-col w-52 flex-shrink-0 sticky top-12 h-[calc(100vh-3rem)] overflow-y-auto border-r border-surface-border bg-surface p-4 space-y-1">
        <div className="flex items-center gap-2 mb-4">
          <BookOpen size={14} className="text-blue-400" />
          <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Cuprins</span>
        </div>
        {TOC.map(({ id, label }) => (
          <button
            key={id}
            onClick={() => scrollTo(id)}
            className={`text-left text-xs px-3 py-2 rounded-lg transition-colors ${
              activeSection === id
                ? "bg-blue-500/15 text-blue-400 border border-blue-500/30"
                : "text-slate-400 hover:text-slate-200 hover:bg-surface-card"
            }`}
          >
            {label}
          </button>
        ))}
      </aside>

      {/* Content */}
      <div ref={contentRef} className="flex-1 p-4 md:p-6 space-y-10 max-w-4xl">
        {/* Header */}
        <div className="flex items-center gap-3 mb-2">
          <BookOpen size={20} className="text-blue-400" />
          <div>
            <h1 className="text-lg font-bold text-white">Ghid No Trading</h1>
            <p className="text-xs text-slate-500">Documentație completă — cele 3 engine-uri, Dashboard, protecții, date (actualizat 31.10.2026)</p>
          </div>
        </div>

        {/* Mobile TOC */}
        <div className="lg:hidden flex flex-wrap gap-2">
          {TOC.map(({ id, label }) => (
            <button
              key={id}
              onClick={() => scrollTo(id)}
              className="text-[10px] px-2.5 py-1.5 rounded-lg bg-surface-card border border-surface-border text-slate-400 hover:text-slate-200 transition-colors"
            >
              {label}
            </button>
          ))}
        </div>

        {/* ── 1. PREZENTARE GENERALĂ ── */}
        <Section id="overview" title="1. Prezentare generală">
          <SubSection title="Ce este aplicația?">
            <p>
              Un sistem de trading automat pe <strong className="text-white">MetaTrader 5</strong>, cu
              <strong className="text-white"> trei engine-uri independente</strong> care rulează ca procese separate și
              un dashboard web (API + UI) care le controlează și le afișează rezultatele. Fiecare engine are propria
              conexiune MT5, propriile fișiere de stare și propriul jurnal — un engine căzut nu le afectează pe celelalte.
            </p>
            <div className="space-y-2 text-xs">
              <div className="bg-emerald-500/5 border border-emerald-500/30 rounded-lg p-3">
                <div className="font-semibold text-emerald-300">Custom Engine (botul pe reguli)</div>
                <div className="text-slate-400">22 de sesiuni, câte o piață fiecare (M15+M30 sau H1+D1). Strategii: pullback-in-trend,
                  Inside Bar, Flag. Ordine BUY_STOP / SELL_STOP, TP pe 3 niveluri R:R (2R / 3R / 4R). Pornire: tab Custom Engine
                  sau cardul de pe Dashboard. Identificare în MT5: comment <code>S&lt;n&gt;-…</code>.</div>
              </div>
              <div className="bg-purple-500/5 border border-purple-500/30 rounded-lg p-3">
                <div className="font-semibold text-purple-300">AI Engine (motorul autonom)</div>
                <div className="text-slate-400">Percepție numerică la fiecare bară M15 → consiliu de 4 roluri AI (Ollama local + Gemini)
                  convocat pe trigger-e → decizie validată de reguli hard (rails). Piețe curente: CHFJPY, GBPUSD. Magic 770015.</div>
              </div>
              <div className="bg-cyan-500/5 border border-cyan-500/30 rounded-lg p-3">
                <div className="font-semibold text-cyan-300">Daily Engine (intraday — implicit SHADOW)</div>
                <div className="text-slate-400">Opening Range Breakout la deschiderea Londrei (GBPUSD, 10:00 RO) și New York (US500, 16:30 RO),
                  un trade pe zi pe piață, închis în aceeași zi. Implicit trade-uri <b>virtuale</b>; poate trece pe Execuție (ordine reale) din tab-ul lui.
                  Magic rezervat 880001.</div>
              </div>
            </div>
            <Note>
              Modificările de configurație intră în vigoare fără restart: Custom Engine la bara următoare (execuție, pauză,
              Setări Globale), AI Engine și Daily Engine la iterația următoare (config recitit). Excepție: codul Python nou cere
              repornirea procesului respectiv (API-ul rulează fără <code>--reload</code>).
            </Note>
          </SubSection>

          <SubSection title="Arhitectura și fluxurile">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
              <div className="space-y-1">
                <KV k="MT5 → engine-uri" v="Bare + prețuri, fiecare engine cu conexiune proprie" />
                <KV k="Custom → MT5" v="Ordine pending; jurnal în data/live_signals/session*/" />
                <KV k="AI → MT5" v="Ordine stop (magic 770015); ledger SQLite data/ai/ledger.db" />
                <KV k="Daily → jurnal" v="Doar citire MT5; trade-uri virtuale în data/daily_engine/trades.jsonl" />
              </div>
              <div className="space-y-1">
                <KV k="MT5 → Dashboard" v="Rezultatele de trading vin EXCLUSIV din istoricul MT5" />
                <KV k="API" v="FastAPI pe portul 8000 (pool MT5 propriu, cache)" />
                <KV k="UI" v="React/Vite pe portul 5173" />
                <KV k="Telegram" v="Notificări + punte de control de pe telefon (opțional)" />
              </div>
            </div>
            <Note>
              <b>MT5 = sursa unică pentru rezultate.</b> Jurnalele engine-urilor (signals.csv, outcomes.csv, ledger) servesc
              doar funcționării lor (deduplicare, recuperare după restart). Atribuirea fiecărei tranzacții pe engine se face din
              <code> magic</code> + <code>comment</code>-ul ordinului; o tranzacție fără sursă cunoscută rămâne „Manual” — nu se ghicește.
            </Note>
          </SubSection>

          <SubSection title="Pornire rapidă">
            <div className="bg-surface rounded-lg border border-surface-border p-3 font-mono text-xs text-slate-300 space-y-1">
              <div><span className="text-slate-600"># Prima instalare / reparare (o singură dată, sigur de rulat din nou):</span></div>
              <div className="text-white">setup.bat            <span className="text-slate-600"># --with-ai = și Ollama + modelul AI · --check = doar verifică</span></div>
              <div className="mt-2"><span className="text-slate-600"># Dashboard (API + UI + browser) — de fiecare dată; restart = din nou:</span></div>
              <div className="text-white">start_ui.bat</div>
              <div className="text-white">stop_ui.bat          <span className="text-slate-600"># oprește dashboard-ul (engine-urile rămân pornite)</span></div>
              <div className="text-slate-600 mt-2"># Engine-urile — din cardurile de pe Dashboard (Start/Stop) sau manual:</div>
              <div>python live/run_all.py        <span className="text-slate-600"># Custom Engine</span></div>
              <div>python -m ai_engine           <span className="text-slate-600"># AI Engine (cere Ollama pornit)</span></div>
              <div>python -m daily_engine        <span className="text-slate-600"># Daily Engine (shadow)</span></div>
            </div>
            <Warn>MT5 trebuie să fie <strong>deschis și logat</strong>. Contul conectat acum este <b>REAL</b> — Custom Engine și
              AI Engine plasează ordine reale doar dacă au fost deblocate explicit în Settings → Trading LIVE.</Warn>
          </SubSection>
        </Section>

        {/* ── 2. DASHBOARD ── */}
        <Section id="dashboard" title="2. Dashboard">
          <SubSection title="Antet — cont MT5">
            <div className="space-y-1 text-xs">
              <KV k="Cont / server" v="Contul MT5 conectat la API" />
              <KV k="Balance" v="Soldul fără pozițiile deschise" />
              <KV k="Equity" v="Balance ± P&L flotant (verde peste balance, roșu sub)" vColor="text-profit" />
            </div>
            <p className="text-xs text-slate-400">Bannerul galben <b className="text-warn">Algo Trading dezactivat</b> apare când butonul AutoTrading
              din MT5 e oprit: semnalele se detectează, dar ordinele nu se plasează.</p>
          </SubSection>

          <SubSection title="Carduri de engine — status + Start / Stop + Autostart">
            <p>Un card per engine (verde Custom · mov AI · cyan Daily). Statusul <b>RUNNING / STOPPED</b> vine din PID-ul real al
              procesului, nu dintr-un fișier de stare — UI-ul nu poate arăta „Running” pentru un engine oprit.</p>
            <div className="space-y-1 text-xs">
              <KV k="Start" v="Pornește și VERIFICĂ (max ~12 s) că procesul trăiește; altfel arată eroarea + ultimele linii din jurnal" />
              <KV k="Stop" v="Oprește și verifică; pozițiile deja deschise rămân în MT5 cu SL/TP" />
              <KV k="Confirmare" v="Cerută la Start/Stop pentru Custom și AI (pot plasa / lăsa nemonitorizate ordine reale)" />
              <KV k="Autostart ON/OFF" v="Pornire automată la login Windows (Task Scheduler, prompt UAC; statusul se actualizează în ~30 s)" />
            </div>
          </SubSection>

          <SubSection title="Cele 4 carduri de performanță">
            <p>TOTAL (albastru) + Custom + AI + Daily: <b>Win rate</b>, <b>Profit</b>, <b>Loss</b>, rezultatul și netul după costuri.</p>
            <div className="space-y-1 text-xs">
              <KV k="Sursă" v="Istoricul MT5 — aceeași listă ca Tranzacțiile și Statisticile (cifrele se leagă)" />
              <KV k="Perioadă" v="Ultimele 365 de zile, doar poziții ÎNCHISE (P&L flotant: tabelul Ordine Active)" />
              <KV k="Win rate" v="Câștiguri / (câștiguri + pierderi); break-even exact nu se numără" />
              <KV k="Profit / Loss" v="Suma profitului brut al pozițiilor câștigătoare / pierzătoare (MT5)" />
              <KV k="Net" v="Rezultat + comision + swap" />
              <KV k="TOTAL" v="Custom + AI + Daily; tranzacțiile manuale sunt excluse (raportate separat în notă)" />
              <KV k="Daily" v="Banii reali = 0 (shadow); trade-urile virtuale apar separat, în R, niciodată adunate la bani" />
            </div>
          </SubSection>

          <SubSection title="Filtrul de sursă al paginii">
            <p>„Arată tranzacțiile: Toate / Custom Engine / AI Engine / Daily Engine / Manual” (implicit Toate) se aplică pe
              cardurile de piață, Statistici, Indicele Săptămânal, Top 5, graficul Performanță și lista de tranzacții.
              P&L Real (equity − capital de start) rămâne mereu la nivelul întregului cont.</p>
            <Note>Pe „Toate”, un card de piață arată tranzacțiile din toate sursele pe acel simbol (ex: EURUSD = Custom + AI).
              Tranzacțiile pe piețe fără card de sesiune sunt listate sub grilă, ca totalurile să se lege.</Note>
          </SubSection>

          <SubSection title="Ritm de tranzacționare (înlocuiește „Frecvența estimată”)">
            <p>Câte trade-uri închide fiecare engine pe săptămână, din istoricul <b>real</b>:</p>
            <div className="space-y-1 text-xs">
              <KV k="Date" v="Trade-uri închise în MT5 (Daily: trade-urile virtuale shadow)" />
              <KV k="Fereastră" v="Doar săptămâni COMPLETE de după ultima schimbare de configurație care afectează frecvența" />
              <KV k="Ponderare" v="Exponențială, înjumătățire 3 săptămâni — recentul contează mai mult" />
              <KV k="Tipic" v="Intervalul P20–P80 al săptămânilor" />
              <KV k="Încredere" v="Insuficient (< 2 săpt. sau < 5 trade-uri) / scăzută / medie / ridicată (volum + stabilitate)" />
              <KV k="Reper" v="Custom: backtestul (arată cât supraestimează); Daily: regulile (1/zi/piață × rata din backtest)" />
              <KV k="Recalculare" v="La 15 minute (cache pe server), zero interogări MT5 în plus" />
            </div>
            <Note>Când regimul curent e prea nou, cardul arată „Date insuficiente” și, separat, ritmul de dinainte de schimbare —
              ca referință, nu ca estimare.</Note>
          </SubSection>

          <SubSection title="Piețe active (toate engine-urile)">
            <div className="space-y-1 text-xs">
              <KV k="Un card = o piață" v="descoperite din configurările reale ale celor 4 engine-uri (nimic fix în cod); sesiunile S1 / S2… rămân doar în Custom Engine" />
              <KV k="Banda colorată de sus" v="un segment pentru fiecare engine care folosește piața: verde Custom · mov AI · cyan Daily · portocaliu Noisy" />
              <KV k="Rândurile din card" v="fiecare engine cu starea și motivul lui; OBS = observație, SHADOW = virtual (fără ordine), EXEC = execuție reală" />
              <KV k="Engine pornit ≠ piață activă" v="engine-ul poate rula, dar piața să fie în afara programului sau blocată" />
              <KV k="În poziție" v="poziție reală deschisă pe piață" />
              <KV k="Activ" v="poate deschide acum (în program, nimic nu blochează)" />
              <KV k="Observație" v="analizează, dar nu plasează ordine (Custom / AI în observație, Daily / Noisy în shadow)" />
              <KV k="În afara programului" v="ore / zi exclusă / weekend / fereastra engine-ului" />
              <KV k="Blocat" v="pauză, știri, Setări Globale (capital / circuit breaker), limite zilnice, buget, eroare — motivul e scris în card" />
              <KV k="Oprit" v="engine-ul (sau sesiunea) nu rulează" />
              <KV k="Trades / WR / P&L" v="din MT5, toate engine-urile pe acea piață (sau doar engine-ul ales în filtrul de sursă); trade-urile virtuale Daily / Noisy sunt separate, în R" />
              <KV k="Click pe card" v="Tranzacțiile și Semnalele de dedesubt arată doar piața aleasă, de la toate engine-urile; ✕ = înapoi la toate" />
              <KV k="Ascunde piețele nefolosite" v="ascunde piețele pe care niciun engine PORNIT nu le folosește acum: engine oprit, piață dezactivată sau sesiune pusă MANUAL pe pauză. Observația, shadow, „în afara programului” și blocările automate (știri, limite, buget) contează ca folosite. O piață cu poziții / ordine deschise rămâne mereu vizibilă. Cu filtrul de sursă ales, contează doar engine-ul ales. Bifa se păstrează" />
            </div>
            <Note>Sub carduri apar piețele cu tranzacții dar fără niciun engine configurat acum (ex. o piață scoasă din AI) —
              ca totalurile să se lege: carduri + aceste piețe = Total Trades din Statistici.</Note>
            <Note>Pauza / reluarea unei sesiuni și verdictul M0 sunt în tab-ul Custom Engine.</Note>
          </SubSection>

          <SubSection title="Tranzacții, Semnale, Ordine Active">
            <div className="space-y-1 text-xs">
              <KV k="Tranzacții MT5" v="Poziții închise de la toate engine-urile, „X din total” + Încarcă mai multe; badge CUSTOM / AI / DAILY / NOISY / MAN" />
              <KV k="Semnale" v="Toate engine-urile: setup-uri Custom (respins AI / expirat / executat / observație), decizii AI OPEN / CLOSE (plasat / respins de rails), trade-uri Daily / Noisy (virtuale în shadow)" />
              <KV k="Ordine Active" v="Poziții deschise + pending din MT5, pe sursă, cu marja folosită și P&L flotant" />
            </div>
          </SubSection>

          <SubSection title="Statistici, Indice Săptămânal, Top 5, Performanță">
            <div className="space-y-1 text-xs">
              <KV k="Semnale azi" v="Pe toate engine-urile (click = defalcare pe piață și engine)" />
              <KV k="Statistici" v="Total trades (Custom / AI / Daily / Noisy / manual), câștiguri, pierderi (azi vs ieri), P&L Real" />
              <KV k="Costuri broker (comision + swap)" v="Total = comision + swap pe pozițiile ÎNCHISE în ultimele 365 zile (tot contul sau sursa din filtru). Azi / Ieri = costurile pozițiilor închise azi / ieri (swap-ul acumulat pe toată durata lor). Cont Standard: comision ~0 — costul principal e spread-ul, care e deja în prețul de execuție (în P&L), nu aici" />
              <KV k="Indice Săptămânal" v="Săptămâna / luna curentă vs precedentă: trades, W/L, win rate, R, P&L, costuri broker, DD" />
              <KV k="Top 5 piețe" v="Toate piețele, agregate peste engine-urile din filtrul de sursă; sortare după $ net (după comision + swap) sau R, pe Azi / Săpt / Lună / Tot" />
              <KV k="Performanță" v="Curba cumulată (USD sau R din SL-ul original)" />
            </div>
            <Note>Aceeași listă MT5 și aceleași definiții peste tot (Dashboard, Tranzacții, Rapoarte, carduri de piață):
              câștig = profit &gt; 0, win rate = câștiguri / (câștiguri + pierderi), ultimele 365 zile, „azi” în fusul aplicației.</Note>
          </SubSection>

          <SubSection title="Analiza per engine (jos)">
            <p>Aceeași componentă pentru Custom, AI și Daily, diferențiată prin culoare: trade-uri, W/L, win rate, net, plus
              două metrici specifice (Custom: medie R + sesiuni active; AI: medie R + decizii/WAIT; Daily: rezultatul shadow).</p>
          </SubSection>
        </Section>

        {/* ── 3. PROFILE & SESIUNI ── */}
        <Section id="profile" title="3. Custom Engine — piețe, sesiuni, protecții">
          <SubSection title="Unde se configurează">
            <div className="space-y-1 text-xs">
              <KV k="Tab Custom Engine" v="Pornire/oprire bot + configurația celor 22 de sesiuni (profilul unic „standard”)" />
              <KV k="Tab Settings" v="MT5, Trading LIVE, Setări Globale, Telegram / punte / Matrix, fus orar" />
              <KV k="Profil" v="Un singur profil, mereu „standard” — selectorul și Profil nou / Șterge au fost eliminate" />
              <KV k="Salvare" v="Butonul Salvează apare sus și jos în listă" />
            </div>
            <Note>
              Pauza, execuția (Observație ⇄ Live) și Setările Globale se aplică de la bara următoare, fără restart.
              Parametrii de strategie ai unei sesiuni (ore, R:R, criterii) se aplică la repornirea botului.
            </Note>
          </SubSection>

          <SubSection title="Parametrii unei sesiuni">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-1.5 text-xs">
              <KV k="Piață" v="O piață per sesiune" />
              <KV k="Timeframe" v="M15 intrare + M30 trend, sau H1 intrare + D1 trend" />
              <KV k="Direcție" v="LONG sau BOTH (LONG + SHORT)" />
              <KV k="Pullback window" v="Câte bare caută structura (6–8)" />
              <KV k="Ore / zile" v="Non-stop sau interval; ore și zile sărite" />
              <KV k="Nivel R:R" v="Scurt 2R / Standard 3R / Extins 4R — același TP pentru toate strategiile pieței" />
              <KV k="Risc" v="1% pe trade la toate nivelurile (inclusiv 4R)" />
              <KV k="Risc / trade (% cont)" v="Cât din equity-ul REAL riscă un trade (= fracția × 1%; ex. 0,20%) — sau lot FIX; vezi cardul „Dimensionarea poziției”" />
              <KV k="Expirare ordin" v="4 bare pe toate sesiunile (fix, nu mai e câmp în UI)" />
              <KV k="Execuție" v="Live = ordine reale; Observație = doar semnale" />
            </div>
            <Note>
              <b>Nivelurile R:R</b> au fost alese per piață pe backtestul fără lookahead, cu criteriul robust max(min(train, test)):
              2R = S1, S5, S7, S11, S12, S14, S15, S18 · 3R = S8, S17, S19 · 4R = S9, S16, S22. Sesiunile de observație
              păstrează scara veche pe criterii (marcate în UI). <b>Badge-ul M0</b> din antetul sesiunii arată verdictul auditului
              statistic; roșu „⚠ live” = o sesiune DEMOTE care execută ordine reale.
            </Note>
            <Note>
              <b>Lot fix</b> (oprit implicit): volum fix pe ordin, aliniat la pasul/minimul brokerului; fracția și riscul sunt
              ignorate. Dacă marja ar depăși ~80% din marja liberă, lotul e redus automat și primești notificare.
            </Note>
            <Note>
              <b>Dimensionarea poziției — aceeași pe Custom, AI și Daily.</b> Lot = equity MT5 × fracție × risc% ÷ (distanța SL ×
              valoarea punctului din MT5), aliniat la lotul minim / pasul / maximul brokerului. Cardul din fiecare sesiune separă
              ce vine automat din MT5 (equity, marjă, specificații) de ce configurezi tu și arată calculul pe un SL tipic real.
              <b> Pe un cont mic, lotul minim domină:</b> dacă ținta e sub lotul minim, se plasează lotul minim (risc real mai mare)
              și fracția nu mai schimbă nimic — cardul arată de la ce equity ar începe să conteze. Fracția influențează doar lotul,
              nu SL/TP sau protecțiile. Dacă equity-ul MT5 nu se poate citi, ordinul NU se plasează.
            </Note>
          </SubSection>

          <SubSection title="Strategii și criterii">
            <div className="space-y-1 text-xs">
              <KV k="Pullback-in-trend" v="Principala: 2 HH + HL după ultimul HH, intrare la prima bară peste maximul pullback-ului" />
              <KV k="Inside Bar / Flag" v="Pattern-uri opționale per sesiune (ID-uri IB / FLG)" />
              <KV k="RSI / EMA" v="Filtre opționale (RSI în interval, EMA8 > EMA20 > EMA50); NU mai schimbă TP-ul" />
              <KV k="Trend TF" v="EMA200 pe timeframe-ul mare, calculat ca în live (fără lookahead în backtest)" />
            </div>
          </SubSection>

          <SubSection title="Protecții per sesiune" defaultOpen={false}>
            <div className="space-y-1 text-xs">
              <KV k="Știri" v="Pauză + închidere/anulare la evenimente (impact 1/2/3, minute înainte/după); activare la secundă" />
              <KV k="Vineri" v="Închide toate ordinele sesiunii la ora setată (cripto exceptat)" />
              <KV k="Circuit breaker" v="N pierderi consecutive azi → sesiunea nu mai deschide nimic până mâine (aplicat și în live)" />
              <KV k="Break-Even" v="Mută SL-ul în 3 faze (oprit implicit — schimbă rezultatele, testează în backtest)" />
            </div>
          </SubSection>

          <SubSection title="Filtru AI Pre-Trade" defaultOpen={false}>
            <p>
              Validarea finală a fiecărui semnal înainte de ordin, oprită implicit. Un singur consiliu AI de 4 roluri
              (Analist Tehnic → Analist Macro → Risk Manager → Head Trader), pe aceleași surse ca AI Engine.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-1.5 text-xs">
              <KV k="Permisiv / Echilibrat / Strict" v="Prag de încredere 50 / 70 / 85" />
              <KV k="Respins" v="Status ai_reject + notificare cu motivul (veto / „consiliul a decis NU” / sub prag)" />
              <KV k="AI indisponibil" v="FAIL-OPEN: trade-ul trece, notat (excepție: modul Strict = blocat)" />
              <KV k="Sursă" v="Sursa aleasă → celelalte surse sănătoase → Ollama (failover)" />
            </div>
            <Note>Jurnal complet: data/live_signals/&lt;sesiune&gt;/ai_filter.jsonl. Consiliile multiple și rolurile
              Quant / Avocatul Diavolului au fost eliminate (pe 617 verdicte reale au scăzut aprobarea fără un câștig dovedit).</Note>
          </SubSection>

          <SubSection title="Backtest din sesiune" defaultOpen={false}>
            <p className="text-xs">Fiecare sesiune are un panou de backtest (1 an / 3 ani / tot / custom). Dacă lipsesc datele CSV,
              se oferă descărcarea din MT5; jobul și rezultatul (cu verdictul M0) apar în tab-ul Audit.</p>
          </SubSection>
        </Section>

        {/* ── 4. AUDIT ── */}
        <Section id="audit" title="4. Audit & Backteste">
          <SubSection title="Structura tab-ului Audit">
            <p>Tab-ul Audit conține două secțiuni:</p>
            <div className="space-y-2">
              <div className="flex items-start gap-2">
                <Badge color="bg-blue-500/20 text-blue-300" label="Descărcări Date" />
                <span className="text-xs text-slate-400">
                  Joburi de descărcare CSV din MT5 — expandabile per simbol cu status per timeframe.
                </span>
              </div>
              <div className="flex items-start gap-2">
                <Badge color="bg-profit/20 text-profit" label="Backteste" />
                <span className="text-xs text-slate-400">
                  Toate joburile de backtest: In rulare / Erori / Finalizate. Click pe un job finalizat pentru rezultate.
                </span>
              </div>
            </div>
          </SubSection>

          <SubSection title="Căutare și ștergere în masă (Backteste)">
            <p>
              Headerul secțiunii Backteste include un câmp de căutare și controale de selecție multiplă:
            </p>
            <div className="space-y-2 text-xs">
              <div>
                <div className="text-[10px] text-slate-500 uppercase mb-1.5">Search bar</div>
                <KV k="Filtrare" v="Caută în sesiune, piețe, direcție, timeframe (case-insensitive)" />
                <KV k="Counter" v="Afișează 'X / total' când filtrul e activ" />
                <KV k="Reset" v="Golind câmpul revine la lista completă" />
              </div>
              <div>
                <div className="text-[10px] text-slate-500 uppercase mb-1.5">Multi-select</div>
                <KV k="Checkbox per job" v="Disponibil pe joburi Erori + Finalizate" />
                <KV k="Selectează tot" v="Toggle global — selectează/deselectează toate din lista filtrată" />
                <KV k="Șterge N selectate" v="Apelează DELETE per job selectat, cu confirmare" />
              </div>
            </div>
            <Note>
              Checkbox-urile apar doar pe joburile completate sau cu eroare — joburile în rulare nu pot fi șterse.
            </Note>
          </SubSection>

          <SubSection title="Interpretarea rezultatelor backtest">
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-3 text-xs">
                <div className="space-y-1">
                  <div className="text-[10px] text-slate-500 uppercase mb-1">Metrici principale</div>
                  <KV k="Trades" v="Minim ~30 pentru relevanță statistică" />
                  <KV k="Win Rate" v="O WR de 45% cu R/R 3.5 este profitabilă" />
                  <KV k="Expectancy" v="+0.025R = câștig mediu 2.5% din risc/trade" vColor="text-profit" />
                  <KV k="Max DD" v="Scădere maximă % față de peak. >40% = reconsideră sizing" vColor="text-loss" />
                </div>
                <div className="space-y-1">
                  <div className="text-[10px] text-slate-500 uppercase mb-1">Train vs Test</div>
                  <KV k="Train 70%" v="Primele 70% tranzacții cronologic" />
                  <KV k="Test 30%" v="Ultimele 30% — DATE NEVĂZUTE" vColor="text-profit" />
                  <KV k="Valoarea cheie" v="Test expectancy pozitiv = edge real" vColor="text-profit" />
                </div>
              </div>
              <Warn>
                <strong>Train expectancy</strong> poate fi supraevaluat (overfitting).
                Metrică relevantă pentru validare este <strong>Test expectancy</strong> pe date nevăzute.
              </Warn>
            </div>
          </SubSection>

          <SubSection title="Realismul rezultatului (față de live)">
            <div className="space-y-1 text-xs">
              <KV k="⛔ REZULTAT INVALID" v="trade-uri cu |R| peste 8 — contractul pieței nu e reprezentat corect în backtest (ex. XRPUSD după schimbarea contractului la broker: 1 lot = 1 XRP, lot minim 100). Nu folosi cifrele" />
              <KV k="Date vechi" v="datele CSV se opresc de mai mult de 14 zile — descarcă date noi înainte să compari cu live-ul" />
              <KV k="Costuri FX" v="spread-ul presupus e cel brut; pe contul Standard spread-ul live are un markup (~0,8 pip)" />
              <KV k="Nu se simulează" v="Filtrul AI pre-trade, Setările Globale, protecția la știri, pauzele / oprirea engine-ului, slippage-ul" />
            </div>
            <Note>Comparația cu tranzacțiile reale (27.07 – 01.11): semnalele backtestului = cele live (91% din trade-urile comune au
              același rezultat, la același preț), costurile backtestului sunt ușor pesimiste, iar volumul live e ~26% din backtest în
              principal din cauza Filtrului AI. Detalii: docs/BACKTEST_VS_LIVE.md.</Note>
          </SubSection>

          <SubSection title="Verdict de robustețe (M0)">
            <p>
              Fiecare backtest finalizat afișează în capul rezultatelor un <strong className="text-white">banner
              de verdict</strong> care răspunde la o singură întrebare: <em>edge-ul e real, sau e un artefact
              al cât de mult ai căutat?</em> Verdictul e mecanic (praguri fixe), nu o opinie.
            </p>
            <div className="space-y-2">
              <div className="flex items-start gap-2">
                <Badge color="bg-profit/20 text-profit" label="🟢 KEEP" />
                <span className="text-xs text-slate-400">Edge distinct de zgomot ȘI stabil în timp. Candidat solid.</span>
              </div>
              <div className="flex items-start gap-2">
                <Badge color="bg-amber-500/20 text-amber-300" label="🟡 OBSERVE" />
                <span className="text-xs text-slate-400">Semnal ambiguu — rulează pe observație (execute_trades=False) și strânge mai multe date.</span>
              </div>
              <div className="flex items-start gap-2">
                <Badge color="bg-loss/20 text-loss" label="🔴 DEMOTE" />
                <span className="text-xs text-slate-400">Edge indistinct de norocul de căutare — pune pe pauză; nu mai plăti spread/comision pe un ne-edge.</span>
              </div>
              <div className="flex items-start gap-2">
                <Badge color="bg-slate-700/40 text-slate-300" label="⚪ INSUFF" />
                <span className="text-xs text-slate-400">Sub 30 de trade-uri — prea puține date pentru a concluziona.</span>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3 text-xs mt-2">
              <div className="space-y-1">
                <div className="text-[10px] text-slate-500 uppercase mb-1">Metrici din banner</div>
                <KV k="P(edge>0)" v="Încrederea (bootstrap) că expectancy > 0. ≥95% = distinct de zgomot" vColor="text-profit" />
                <KV k="Fold+" v="Fracția din 8 sub-perioade pozitive. ~100% = stabil în timp" />
              </div>
              <div className="space-y-1">
                <div className="text-[10px] text-slate-500 uppercase mb-1">&nbsp;</div>
                <KV k="N* trials" v="Câte variante ar explica edge-ul prin noroc. Mic (<10) = fragil" vColor="text-amber-400" />
                <KV k="CI 95%" v="Interval de încredere pe expectancy. Include 0 = neconcludent" />
              </div>
            </div>
            <Tip>
              Regula: <strong>KEEP</strong> dacă expectancy &gt; 0 ȘI P(edge&gt;0) ≥ 95% ȘI ≥60% fold-uri pozitive.
              <strong> DEMOTE</strong> dacă expectancy ≤ 0 SAU P(edge&gt;0) &lt; 75%. Detalii complete în
              <strong className="text-white"> docs/M0_METHOD.md</strong>.
            </Tip>
            <Note>
              Verdictul apare doar pe backtestele rulate după activarea M0. Pentru un audit al tuturor
              sesiunilor deodată: <code className="text-slate-300">python -m m0.audit</code> → raport în docs/M0_RESULTS.md.
            </Note>
          </SubSection>

          <SubSection title="Statistici LONG/SHORT (sesiuni BOTH)" defaultOpen={false}>
            <p>
              Pentru sesiunile cu direcție BOTH, după tabelul per simbol apare un panou cu
              <strong className="text-white"> statistici separate pentru LONG și SHORT</strong>:
            </p>
            <div className="grid grid-cols-2 gap-3">
              <div className="bg-surface rounded-lg border border-profit/30 p-3 space-y-1 text-xs">
                <div className="text-profit font-semibold text-[11px]">▲ LONG</div>
                <KV k="Trades" v="74" />
                <KV k="Win Rate" v="54.1%" />
                <KV k="Câștiguri" v="40" vColor="text-profit" />
                <KV k="Pierderi" v="34" vColor="text-loss" />
                <KV k="Expectancy" v="+0.048R" vColor="text-profit" />
              </div>
              <div className="bg-surface rounded-lg border border-loss/30 p-3 space-y-1 text-xs">
                <div className="text-loss font-semibold text-[11px]">▼ SHORT</div>
                <KV k="Trades" v="52" />
                <KV k="Win Rate" v="46.1%" />
                <KV k="Câștiguri" v="24" vColor="text-profit" />
                <KV k="Pierderi" v="28" vColor="text-loss" />
                <KV k="Expectancy" v="-0.012R" vColor="text-loss" />
              </div>
            </div>
            <p className="text-xs text-slate-400 mt-2">
              Dacă una dintre direcții are expectancy negativ constant, poți schimba sesiunea din BOTH în LONG
              sau SHORT din Profile.
            </p>
            <Note>
              Această secțiune apare doar pentru backteste noi. Joburile vechi din Audit nu au câmpul direction_stats —
              rulează un backtest nou pentru a obține spliturile.
            </Note>
          </SubSection>

          <SubSection title="Analiza pierderi (skip_hours / skip_weekdays)" defaultOpen={false}>
            <p>
              Tabelele <em>Zile săptămână</em> și <em>Ore</em> arată distribuția tranzacțiilor și a pierderilor.
              Rândurile marcate cu <Badge color="bg-warn/10 text-warn" label="skip candidat" /> au expectancy
              negativ și ar putea fi excluse.
            </p>
            <Tip>
              Adaugă zilele/orele cu expectancy negativ în câmpurile <code className="text-blue-300">skip_weekdays</code> /
              <code className="text-blue-300 ml-1">skip_hours</code> din Custom Engine → sesiune, apoi rulează un backtest nou
              pentru a verifica îmbunătățirea.
            </Tip>
          </SubSection>

          <SubSection title="Frecvența trades în rezultate" defaultOpen={false}>
            <p>
              Rândul de frecvență din rezultatele backtest:
            </p>
            <div className="bg-surface/60 border border-surface-border rounded-lg px-3 py-2 text-[10px] text-slate-400 font-mono">
              Frecvență: <strong className="text-slate-200">2.3</strong> trades/săpt ·
              <strong className="text-slate-200 ml-1">9.9</strong> trades/lună ·
              <strong className="text-slate-200 ml-1">365</strong> zile testate
            </div>
            <p className="text-xs text-slate-400 mt-2">
              Calculat ca <code className="text-blue-300">total_trades / (zile_testate / 7)</code>.
              Este baza pentru estimatul din cardurile de frecvență din Dashboard.
            </p>
          </SubSection>

          <SubSection title="Configurare sesiune în Audit (snapshot complet)" defaultOpen={false}>
            <p>
              Fiecare backtest finalizat salvează un <strong className="text-white">snapshot complet</strong> al
              configurației sesiunii la momentul rulării. Poți verifica exact cu ce parametri a fost testat.
            </p>
            <div className="space-y-1.5 text-xs">
              <div className="text-[10px] text-slate-500 uppercase tracking-wider">Secțiuni afișate la expandare</div>
              <KV k="Strategie" v="Pullback window, Expire bare, Interval ore, Skip zile/ore" />
              <KV k="R:R" v="r_base…r_max (la nivelurile fixe 2R/3R/4R toate egale) + riscul %" />
              <KV k="Criterii opționale" v="RSI (range buy/sell), EMA alignment, Body strength" />
              <KV k="Break-Even" v="Trigger%, Lock1%, Lock2%, Faza2 zona%, toggle Faza2" />
              <KV k="Protecție" v="Închidere Vineri (ora), Protecție Știri (impact + fereastră)" />
              <KV k="Tranzacționare" v="Max concurent/piață, Min bare între trades" />
              <KV k="Capital simulat" v="Total USD + alocare per piață" />
            </div>
            <Note>
              Snapshot-ul este construit automat din configurația trimisă la backtest — nu mai necesită
              completare manuală din frontend. Sesiunile rulate prin „backteste lipsă" includ și ele snapshot complet.
            </Note>
          </SubSection>

          <SubSection title={'Butonul "Aplică config pe sesiune"'} defaultOpen={false}>
            <p>
              Pe orice backtest finalizat cu succes, în panoul expandat apare butonul:
            </p>
            <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg px-3 py-2 text-xs text-blue-300 font-mono inline-flex items-center gap-2">
              ⎘ Aplică config pe sesiunea S9
            </div>
            <div className="mt-3 space-y-2 text-xs text-slate-400">
              <p><strong className="text-slate-300">Ce face:</strong> preia parametrii din snapshot-ul backtest-ului
                (pullback window, R-ladder, RSI, BE, vineri, știri etc.) și le aplică direct în editorul sesiunii
                din Profile — fără salvare automată.</p>
              <p><strong className="text-slate-300">Flux:</strong></p>
              <ol className="list-decimal list-inside space-y-1 ml-2">
                <li>Click pe buton → navighează automat la tab Profile</li>
                <li>Sesiunea țintă se expandează automat și scroll se face la ea</li>
                <li>Banner verde: „Configurația sesiunii SX a fost aplicată. Salvează profilul..."</li>
                <li>Verifici parametrii vizual → click <strong className="text-white">Salvează</strong></li>
              </ol>
            </div>
            <Warn>
              Câmpurile de identitate <strong>(markets, direction, execute_trades, account_fraction)</strong> nu
              sunt suprascrise — rămân cele din profil. Doar parametrii de strategie sunt aplicați.
            </Warn>
            <Tip>
              Util pentru a testa variante de parametri în paralel (mai multe backteste cu settings diferite)
              și a aplica rapid cel mai bun set găsit.
            </Tip>
          </SubSection>
        </Section>

        {/* ── 5. STRATEGIA ── */}
        <Section id="strategy" title="5. Strategia">
          <SubSection title="Pullback-in-Trend — logica completă">
            <StrategyDiagram />
            <div className="mt-3 space-y-3 text-xs">
              <div>
                <strong className="text-slate-300">Pasul 1 — Trend:</strong>
                <span className="text-slate-400 ml-2">
                  EMA200 calculată pe timeframe-ul de trend (M30 sau D1).
                  Bara curentă peste EMA200 = trend bullish (1), sub = bearish (-1).
                </span>
              </div>
              <div>
                <strong className="text-slate-300">Pasul 2 — Structura Swing:</strong>
                <span className="text-slate-400 ml-2">
                  Se caută 2 Higher Highs (HH) cu un Higher Low (HL) intermediar pentru LONG.
                  Fereastra de căutare = <code className="text-blue-300">pullback_window</code> bare.
                </span>
              </div>
              <div>
                <strong className="text-slate-300">Pasul 3 — Pullback:</strong>
                <span className="text-slate-400 ml-2">
                  Prețul retrage spre nivelul HL după ultimul HH. Retras prea mult (sub HL) = setup invalidat.
                </span>
              </div>
              <div>
                <strong className="text-slate-300">Pasul 4 — Intrare:</strong>
                <span className="text-slate-400 ml-2">
                  Prima bară care închide <strong>peste maximul barei de pullback</strong> (anti-lookahead).
                  Se plasează BUY_STOP la <code className="text-blue-300">high + buffer</code>,
                  SL sub HL, TP la entry + R × distanță.
                </span>
              </div>
            </div>
          </SubSection>

          <SubSection title="Ciclul de viață al unui semnal" defaultOpen={true}>
            <SignalLifecycleDiagram />
            <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
              <div className="space-y-1">
                <div className="text-[10px] text-slate-500 uppercase mb-1">Statusuri finale (outcomes.csv)</div>
                <KV k="TP" vColor="text-profit" v="Take Profit atins — câștig R" />
                <KV k="SL" vColor="text-loss"   v="Stop Loss atins — pierdere 1R" />
                <KV k="vineri_close" v="Închis vineri la ora configurată" />
                <KV k="news_close"  v="Închis la eveniment economic" />
              </div>
              <div className="space-y-1">
                <div className="text-[10px] text-slate-500 uppercase mb-1">Statusuri intermediare</div>
                <KV k="expirat" v="Niciun trigger în expire_bars bare" />
                <KV k="invalidat" vColor="text-warn" v="Structura ruptă — ordinul MT5 anulat" />
                <KV k="news_cancel" v="Ordin pending anulat la știre" />
              </div>
            </div>
            <Note>
              Statusul <strong className="text-warn">invalidat</strong> înseamnă că botul a detectat că
              structura de pullback a fost ruptă și a trimis <code className="text-blue-300">TRADE_ACTION_REMOVE</code>
              pentru a anula ordinul pending din MT5. Nu se trimite notificare Telegram pentru acest status.
            </Note>
          </SubSection>

          <SubSection title="Recuperare automată la crash / restart" defaultOpen={false}>
            <p>
              Dacă botul se oprește neașteptat (crash, curent, restart manual) în timp ce o
              poziție este activă în MT5, <strong className="text-white">mecanismul de reconciliere</strong>{" "}
              corectează automat datele la repornire — fără intervenție manuală.
            </p>

            <div className="mt-3 font-mono text-xs bg-surface rounded-lg border border-surface-border p-4 space-y-3">
              <div className="text-[10px] text-slate-500 uppercase mb-2">Flux recuperare la startup</div>
              <div className="space-y-2 text-slate-300">
                <div className="flex items-start gap-2">
                  <span className="text-profit shrink-0">1.</span>
                  <span><code className="text-blue-300">_migrate_pending_format</code> — migrare format vechi state.pkl</span>
                </div>
                <div className="flex items-start gap-2">
                  <span className="text-profit shrink-0">2.</span>
                  <span><code className="text-blue-300">_reconcile_mt5_tickets</code> — curăță orfanele din state</span>
                </div>
                <div className="flex items-start gap-2">
                  <span className="text-warn font-semibold shrink-0">3.</span>
                  <span>
                    <code className="text-blue-300">_recover_lost_outcomes</code> — caută în MT5 history
                    (10 zile) după <code className="text-blue-300">comment = signal_id</code>:
                    <ul className="mt-1 ml-4 space-y-0.5 text-slate-400">
                      <li>· Ordin pending → actualizează mt5_tickets</li>
                      <li>· Poziție deschisă → marked triggered=True</li>
                      <li>· Poziție închisă → scrie TP/SL real în outcomes.csv + Telegram <span className="text-warn">[RECOVER]</span></li>
                    </ul>
                  </span>
                </div>
                <div className="flex items-start gap-2">
                  <span className="text-profit shrink-0">4.</span>
                  <span><code className="text-blue-300">_detect_orphan_mt5_orders</code> — alertează pentru ordine netrackuite</span>
                </div>
              </div>
            </div>

            <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
              <div className="bg-surface rounded-lg border border-loss/30 p-3 space-y-1">
                <div className="text-loss text-[10px] uppercase font-semibold mb-1">Fără mecanism (înainte)</div>
                <div className="text-slate-400 leading-relaxed">
                  Bot restartuit → semnal fără ticket → barul expiră →
                  scris <span className="text-loss">expirat 0R</span> în outcomes.csv<br/>
                  <span className="text-slate-500 text-[10px]">Dashboard ≠ MT5</span>
                </div>
              </div>
              <div className="bg-surface rounded-lg border border-profit/30 p-3 space-y-1">
                <div className="text-profit text-[10px] uppercase font-semibold mb-1">Cu mecanism (acum)</div>
                <div className="text-slate-400 leading-relaxed">
                  Bot restartuit → <code className="text-blue-300">_recover_lost_outcomes</code> →
                  găsit în MT5 history → scris <span className="text-profit">SL -1.1R</span> corect<br/>
                  <span className="text-slate-500 text-[10px]">Dashboard = MT5 ✓</span>
                </div>
              </div>
            </div>

            <Note>
              Orice corecție automată trimite notificare Telegram cu prefix{" "}
              <code className="text-warn">[RECOVER]</code> și apare în tab-ul Notificări.
              MT5 are întotdeauna prioritate față de starea locală a botului.
            </Note>

            <p className="text-xs text-slate-400 mt-2">
              <strong className="text-slate-300">Fix la expirare/invalidare:</strong> Dacă un semnal cu
              ticket MT5 ajunge la expirare sau invalidare din bare, botul verifică întâi MT5 înainte de
              a scrie <code className="text-blue-300">expirat</code>. Dacă pozitia era deja închisă în MT5
              (TP/SL real), scrie outcome-ul real în loc de <code className="text-loss">expirat 0R</code>.
            </p>
          </SubSection>

          <SubSection title="Când apare statusul 'invalidat'?" defaultOpen={false}>
            <p>
              <strong className="text-warn">Invalidat</strong> apare strict în fereastra{" "}
              <span className="text-orange-400 font-mono">Plasat → Activat</span> — ordinul BUY_STOP/SELL_STOP
              există deja în MT5 dar nu a fost încă triggerat de preț.
            </p>
            <p className="mt-2">
              Condiția exactă: <code className="text-blue-300">_update_outcomes()</code> verifică la fiecare bară dacă
              structura de swing care a justificat trade-ul mai este validă.
            </p>

            {/* Visual explanation */}
            <div className="bg-surface rounded-lg border border-surface-border p-4 font-mono text-xs mt-3 space-y-2">
              <div className="text-[10px] text-slate-500 uppercase mb-2">Exemplu LONG — structură ruptă</div>
              <div className="flex flex-col gap-1 text-slate-400">
                <span>         HH2</span>
                <span>    HH1   │      BUY_STOP ← ordin pending în MT5</span>
                <span>     │   ╱ ╲   ↑ Entry</span>
                <span>     │  ╱   ╲  │</span>
                <span>     │ ╱   <span className="text-warn">HL</span> ╲ │</span>
                <span>     │╱        <span className="text-loss">↓ prețul coboară SUB HL</span></span>
                <span className="text-warn mt-1">              → INVALIDAT: bot trimite TRADE_ACTION_REMOVE</span>
              </div>
              <div className="border-t border-surface-border/50 pt-2 mt-2 space-y-1 text-slate-500">
                <div>LONG: prețul <span className="text-loss">sub minimul pullback-ului (HL)</span> = structură ruptă</div>
                <div>SHORT: prețul <span className="text-loss">peste maximul pullback-ului (LH)</span> = structură ruptă</div>
              </div>
            </div>

            {/* Comparison table */}
            <div className="mt-3 space-y-1.5 text-xs">
              <div className="text-[10px] text-slate-500 uppercase mb-2">Diferența față de alte statusuri</div>
              <div className="grid grid-cols-3 gap-2">
                <div className="bg-surface rounded-lg border border-warn/30 p-2.5 space-y-1">
                  <div className="text-warn font-semibold text-[11px]">invalidat</div>
                  <div className="text-slate-400 text-[10px] leading-relaxed">
                    Prețul a spart structura de swing.<br />
                    Botul anulează activ ordinul din MT5.<br />
                    <span className="text-slate-500">result_r = 0</span>
                  </div>
                </div>
                <div className="bg-surface rounded-lg border border-slate-700 p-2.5 space-y-1">
                  <div className="text-slate-300 font-semibold text-[11px]">expirat</div>
                  <div className="text-slate-400 text-[10px] leading-relaxed">
                    Ordinul nu a fost triggerat în N bare (expire_bars).<br />
                    Structura poate fi încă validă.<br />
                    <span className="text-slate-500">result_r = 0</span>
                  </div>
                </div>
                <div className="bg-surface rounded-lg border border-slate-700 p-2.5 space-y-1">
                  <div className="text-slate-300 font-semibold text-[11px]">news_cancel</div>
                  <div className="text-slate-400 text-[10px] leading-relaxed">
                    Eveniment economic iminent.<br />
                    Anulat preventiv de News Guard.<br />
                    <span className="text-slate-500">result_r = 0</span>
                  </div>
                </div>
              </div>
            </div>

            <div className="mt-3 space-y-1 text-xs">
              <KV k="Gestionat de" v="_update_outcomes() — rulează și când sesiunea e pe pauză" />
              <KV k="MT5" v="TRADE_ACTION_REMOVE trimis → ordinul dispare din MT5" />
              <KV k="Telegram" v="Nu se trimite notificare (eveniment normal de management)" />
              <KV k="result_r" v="0 — nu este o pierdere, nu intră în statistici" />
              <KV k="pnl_usd" v="NaN — nu a existat poziție reală deschisă" />
            </div>

            <Warn>
              Dacă un ordin dispare din MT5 fără notificare Telegram, verifică outcomes.csv al sesiunii —
              cel mai probabil statusul este <strong>invalidat</strong> sau <strong>expirat</strong>,
              ambele comportamente normale și așteptate.
            </Warn>
          </SubSection>

          <SubSection title="Detectarea dublei intrări (offset 3/2)" defaultOpen={false}>
            <p>
              Botul caută semnale pe bare <strong>închise</strong> la offset 3 și 2 față de bara curentă.
              Bara 1 (cea curentă, parțial formată) este ignorată intenționat.
            </p>
            <div className="bg-surface rounded-lg border border-surface-border p-3 font-mono text-xs space-y-1">
              <div className="text-slate-500">Bara curentă (parțial):</div>
              <div className="flex gap-4">
                <span className="text-slate-600">offset 0 → ignorat</span>
                <span className="text-slate-600">offset 1 → ignorat</span>
                <span className="text-slate-400">offset 2 → verificat</span>
                <span className="text-slate-400">offset 3 → verificat</span>
              </div>
            </div>
            <p className="text-xs text-slate-400 mt-2">
              Aceasta previne detectarea dublă a aceluiași setup la bare consecutive.
            </p>
          </SubSection>
        </Section>

        {/* ── 6. GESTIONARE RISC ── */}
        <Section id="risk" title="6. Gestionare risc și Setări Globale">
          <SubSection title="Calculul poziției (Custom Engine)">
            <div className="bg-surface rounded-lg border border-surface-border p-3 font-mono text-xs space-y-1 text-slate-300">
              <div>capital = equity MT5 (sau capital fix alocat botului) × account_fraction</div>
              <div>lots = capital × 1% / (distanța SL × valoarea tick-ului din MT5)</div>
            </div>
            <div className="space-y-1 text-xs mt-2">
              <KV k="Valoarea tick-ului" v="Citită din MT5 la fiecare ordin (corectă pentru orice simbol)" />
              <KV k="Lot minim broker" v="Sub minim → ordinul nu se plasează (la cont mic, lotul minim domină riscul)" />
              <KV k="Lot fix" v="Alternativă per sesiune; redus automat dacă marja > 80% din marja liberă" />
            </div>
            <Note>AI Engine are propriile limite (rails): risc ≤ 1%, SL ≤ 5×ATR, RR ≥ 1, stop zilnic −3R, max poziții +
              ordine pending, fără pyramiding, marjă ≤ 40% din marja liberă. Daily Engine nu riscă bani (shadow).</Note>
          </SubSection>

          <SubSection title="Setări Globale (Settings → Setări Globale)">
            <p>Un singur punct de control peste Custom Engine și AI Engine. Regula: <b>cea mai strictă câștigă</b> — globalul e
              un minim de siguranță, o sesiune/piață poate fi mai strictă, niciodată mai permisivă. Toate secțiunile sunt
              <b> oprite implicit</b>; se aplică de la bara următoare, fără restart.</p>
            <div className="space-y-1 text-xs">
              <KV k="Protecție capital" v="Equity sub X% din capitalul de start → niciun ordin nou (Bot + AI); watchdog-ul pune și sesiunile pe pauză" />
              <KV k="Circuit breaker global" v="N pierderi consecutive azi pe tot contul sau pierdere zilnică ≥ X% → stop ordine noi" />
              <KV k="Închidere vineri" v="Ora = cea mai devreme dintre global și sesiune; cripto exceptat implicit" />
              <KV k="Protecție știri" v="Impact = minimul, minute înainte/după = maximul dintre global și sesiune" />
              <KV k="Max poziții / piață" v="Poziții + pending pe un simbol, pe tot contul, toate engine-urile" />
              <KV k="Special Take Profit" v="OPRIT implicit; doar Custom Engine (Daily / Noisy / AI excluse pe baza backtestului). La atingerea RR-ului (ex. 2R) SL-ul se blochează la 1,9R și urcă în trepte de 0,5R cât timp piața continuă; SL-ul nu coboară niciodată. Pornit în Setări Globale = câștigă; altfel setarea din tab-ul Custom Engine" />
              <KV k="Risc maxim pe trade" v="ACTIV la 2% din equity (Custom + AI + Daily): volumul peste limită e redus; dacă nici lotul minim nu încape, ordinul nu se plasează" />
              <KV k="Filtru AI" v="Doar Custom Engine: nivelul cel mai strict, Strict = SAU" />
            </div>
            <Note>Fișier: data/global_settings.json (sincronizat prin git, fără date). Eroare la citirea MT5 → ordinul e permis
              (fail-open) ca o problemă de conexiune să nu blocheze tot.</Note>
          </SubSection>

          <SubSection title="Circuit breaker per sesiune" defaultOpen={false}>
            <p className="text-xs">N pierderi consecutive azi ale sesiunii (doar trade-urile ei) → nu mai deschide nimic până a doua
              zi. Aplicat în backtest și, din 2026-10-31, și în live (din istoricul MT5).</p>
          </SubSection>

          <SubSection title="Închidere vineri" defaultOpen={false}>
            <div className="space-y-1 text-xs">
              <KV k="Pending" v="Anulate → status vineri_cancel" />
              <KV k="Poziții" v="Închise la piață → status vineri_close (cu prețul real de execuție)" />
              <KV k="Sweep MT5" v="Prinde orice ordin al sesiunii scăpat din stare (nu atinge AI / manual)" />
              <KV k="AI Engine" v="Vineri de la 22:00 + weekend: închide și nu deschide nimic pe FX / indici" />
            </div>
          </SubSection>
        </Section>

        {/* ── 7. CONFIGURARE AVANSATĂ ── */}
        <Section id="config" title="7. Pornire, oprire, autostart, configurare">
          <SubSection title="Start / Stop pentru fiecare engine">
            <div className="space-y-1 text-xs">
              <KV k="De unde" v="Cardurile de engine din Dashboard (toate trei) sau tab-ul fiecărui engine" />
              <KV k="Verificare" v="Start reușește doar dacă procesul trăiește după pornire; altfel vezi eroarea + jurnalul" />
              <KV k="Custom Engine" v="run_all.py pornește cele 22 de sesiuni; Stop = taskkill pe arbore + curățare lock-uri" />
              <KV k="AI Engine" v="Motor + watchdog propriu (repornește la crash); Stop oprește întâi watchdog-ul" />
              <KV k="Daily Engine" v="Watchdog-ul API îl repornește dacă moare fără Stop (max 3/oră, apoi alertă)" />
            </div>
            <Note>Custom Engine căzut fără Stop → watchdog-ul API trimite „Bot Trading oprit neașteptat!” (fără repornire automată
              — pozițiile reale cer o decizie). Toate pornirile/opririle trimit Telegram.</Note>
          </SubSection>

          <SubSection title="Autostart Windows (toate engine-urile)" defaultOpen={false}>
            <p>Toggle-ul „Autostart” din fiecare card de engine creează/șterge un task în Task Scheduler (prompt UAC):</p>
            <div className="space-y-1 text-xs">
              <KV k="TradingBot-MT5" v="MT5 la login — PARTAJAT; șters doar când niciun engine nu mai are autostart" />
              <KV k="TradingBot-RunAll" v="Custom Engine, la login + 90 s" />
              <KV k="TradingBot-AIEngine" v="Ollama + AI Engine + watchdog, la login + ~120 s" />
              <KV k="TradingBot-DailyEngine" v="Daily Engine, la login + 150 s (scripts/setup_autostart_engine.ps1 -Engine daily)" />
            </div>
            <Warn>Task-urile rulează NEELEVAT (RunLevel Limited) — altfel UI-ul nu le-ar putea opri. Nu le schimba pe „Highest”.
              Autostart-ul Custom Engine folosește ultimul profil activ (active_profile_runtime.json nu se mai șterge la stop).</Warn>
          </SubSection>

          <SubSection title="Telegram și notificări" defaultOpen={false}>
            <div className="space-y-1 text-xs">
              <KV k="Unde" v="Settings → Telegram (token de la @BotFather + chat ID); buton de test" />
              <KV k="Fișier" v="data/telegram_config.json" />
              <KV k="Doar importante" v="Opțional: pe Telegram doar trading + conexiune + pornire/oprire; tab-ul Notificări păstrează tot" />
            </div>
          </SubSection>

          <SubSection title="Descărcare date istorice" defaultOpen={false}>
            <p className="text-xs">Din panoul de backtest al sesiunii (descarcă din MT5, job în Audit → Descărcări). Alias-urile de
              broker sunt rezolvate automat (ex: GER40 → DE40). Cont real: descărcarea doar citește, nu tranzacționează.</p>
          </SubSection>

          <SubSection title="Fus orar (România / Germania)" defaultOpen={false}>
            <div className="space-y-1 text-xs">
              <KV k="Unde" v="Settings → Fus orar" />
              <KV k="România (implicit)" v="Europe/Bucharest — orele sesiunilor sunt calibrate pe ora României" />
              <KV k="Germania" v="Europe/Berlin — cu o oră în urma României" />
              <KV k="Ora serverului MT5" v="Re-detectată la 30 min (ICMarkets urmează DST-ul SUA)" />
            </div>
            <Warn>Pe Germania, orele de sesiune se aplică pe ora locală, deci ferestrele sunt decalate cu 1 h față de backtest
              (calibrat pe ora României). Trade-urile nu se opresc, dar pot cădea în alte ore. Diagnostic:
              <code> python scripts/diagnose_no_trades.py</code>.</Warn>
          </SubSection>
        </Section>

        {/* ── 8. SEMNALE & ORDINE ── */}
        <Section id="signals" title="8. Semnale & Ordine">
          <SubSection title="Fișierele de date per sesiune">
            <p>
              Fiecare sesiune salvează datele în <code className="text-blue-300">data/live_signals/sessionN/</code>:
            </p>
            <div className="space-y-2 text-xs">
              <div>
                <div className="text-[10px] text-slate-500 uppercase mb-1">signals.csv</div>
                <div className="space-y-0.5">
                  <KV k="signal_id" v="Ex: S3-BTC-BOTH-SIG0009" />
                  <KV k="time" v="Momentul detecției (ora Romaniei)" />
                  <KV k="direction" v="1 = LONG, -1 = SHORT" />
                  <KV k="entry / sl / tp" v="Prețurile de intrare, stop și target" />
                  <KV k="r_ratio" v="R/R țintit (ex: 3.5R)" />
                  <KV k="n_optional" v="Câte criterii opționale sunt îndeplinite (0–3)" />
                  <KV k="rsi" v="Valoarea RSI la momentul semnalului" />
                </div>
              </div>
              <div>
                <div className="text-[10px] text-slate-500 uppercase mb-1">outcomes.csv</div>
                <div className="space-y-0.5">
                  <KV k="status" v="TP / SL / expirat / vineri_close / news_close / invalidat" />
                  <KV k="triggered_at" v="Ora la care ordinul pending a fost activat în MT5" />
                  <KV k="exit_price" v="Prețul real de ieșire din MT5" />
                  <KV k="result_r" v="R realizat (ex: +3.5 sau -1.0)" />
                  <KV k="pnl_usd" v="Profit/pierdere reală în USD (din deal MT5)" />
                </div>
              </div>
            </div>
          </SubSection>

          <SubSection title="Filling modes ordine MT5" defaultOpen={false}>
            <p>
              Botul încearcă filling modes în ordine până la succes:
            </p>
            <div className="bg-surface rounded-lg border border-surface-border p-3 font-mono text-xs space-y-1 text-slate-400">
              <div>1. ORDER_FILLING_RETURN</div>
              <div>2. ORDER_FILLING_FOK</div>
              <div>3. ORDER_FILLING_IOC</div>
              <div>4. fără filling specificat</div>
            </div>
            <p className="text-xs text-slate-400 mt-2">
              ICMarketsEU respinge <code className="text-blue-300">ORDER_TIME_SPECIFIED</code> (retcode 10022)
              — se folosește <code className="text-blue-300">ORDER_TIME_GTC</code> (Good Till Cancelled).
            </p>
          </SubSection>

          <SubSection title="Hedging mode (ICMarketsEU)" defaultOpen={false}>
            <p>
              Contul ICMarketsEU rulează în <strong className="text-white">hedging mode</strong>
              (nu netting). În hedging, <code className="text-blue-300">position_id ≠ order_ticket</code>.
            </p>
            <p className="text-xs text-slate-400 mt-1">
              Pentru a verifica dacă TP/SL a fost atins: botul caută
              <code className="text-blue-300 mx-1">order.position_id</code> via
              <code className="text-blue-300 ml-1">history_orders_get(ticket)</code>
              și apoi deals-urile pe baza acelui position_id — nu pe ticket direct.
            </p>
          </SubSection>

          <SubSection title="Tracking pnl_usd" defaultOpen={false}>
            <p>
              Câmpul <code className="text-blue-300">pnl_usd</code> în outcomes.csv vine din
              <code className="text-blue-300 mx-1">deal.profit</code> returnat de
              <code className="text-blue-300">history_deals_get</code>.
            </p>
            <div className="space-y-1 text-xs">
              <KV k="Disponibil pt" v="TP, SL, vineri_close, news_close (pozitii reale inchise)" />
              <KV k="NaN pentru" v="expirat, invalidat, sesiuni cu execute_trades=False" />
              <KV k="Backfill" v="scripts/backfill_pnl_usd.py (necesita MT5 conectat)" />
            </div>
          </SubSection>
        </Section>

        {/* ── 9. NOTIFICĂRI ── */}
        <Section id="notifications" title="9. Notificări">
          <SubSection title="Cum funcționează Notificările">
            <p>
              Tab-ul <strong className="text-white">Notificări</strong> prinde automat toate mesajele trimise prin
              sistemul bot — același conținut ca notificările Telegram, stocat local în
              <code className="text-blue-300 mx-1">data/notifications.json</code> (max 500 intrări).
            </p>
            <p className="text-xs text-slate-400 mt-1">
              Capturat din două surse independente: <code className="text-blue-300">api/telegram.py</code> (start/stop bot,
              pauze, watchdog) și <code className="text-blue-300">live/signal_generator.py</code> (semnale, ordine activate,
              TP/SL, știri). Dacă Telegram nu e configurat, notificările apar totuși în UI.
            </p>
          </SubSection>

          <SubSection title="Categorii de notificări">
            <div className="grid grid-cols-2 gap-2 text-xs">
              {[
                { cat: "Ordine",     dot: "bg-profit",    desc: "BUY_STOP / SELL_STOP plasat sau activat în MT5" },
                { cat: "Tranzacții", dot: "bg-profit/70", desc: "TP, SL, vineri_close, news_close" },
                { cat: "Semnale",    dot: "bg-blue-400",  desc: "Semnal nou detectat de strategy" },
                { cat: "Știri",      dot: "bg-warn",      desc: "Pauză automată News Guard, eveniment economic" },
                { cat: "Sesiuni",    dot: "bg-slate-400", desc: "Pauză / reluare sesiune manuală" },
                { cat: "Bot",        dot: "bg-blue-300",  desc: "Start / Stop bot, crash watchdog" },
                { cat: "Sistem",     dot: "bg-slate-500", desc: "Mesaje tehnice neîncadrate în alte categorii" },
              ].map(({ cat, dot, desc }) => (
                <div key={cat} className="flex items-start gap-2 bg-surface-card rounded-lg border border-surface-border p-2.5">
                  <span className={`mt-1 w-2 h-2 rounded-full flex-shrink-0 ${dot}`} />
                  <div>
                    <div className="text-[11px] font-semibold text-slate-300">{cat}</div>
                    <div className="text-[10px] text-slate-500 leading-relaxed">{desc}</div>
                  </div>
                </div>
              ))}
            </div>
          </SubSection>

          <SubSection title="Interfața" defaultOpen={false}>
            <div className="space-y-1.5 text-xs">
              <KV k="Filtre categorie" v="Apar doar categoriile cu cel puțin o intrare" />
              <KV k="Grupare pe zile" v="Azi / Ieri / data completă" />
              <KV k="Timp relativ" v="acum / 5m / 2h / 3z + ora exactă sub card" />
              <KV k="Extinde / Ascunde" v="Mesajele multi-linie pot fi expandate" />
              <KV k="Dot necitit" v="Punct colorat în colțul iconiței de categorie" />
              <KV k="Badge NavBar" v="Numărul de necitite — dot albastru pulsant" />
            </div>
            <div className="mt-3 space-y-1.5 text-xs">
              <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Acțiuni disponibile</div>
              <KV k="Marchează citite" v="Setează read=true pe toate — badge dispare" />
              <KV k="× (hover)" v="Șterge o singură notificare" />
              <KV k="Șterge tot" v="Golește notifications.json (cu confirmare)" />
            </div>
            <Note>
              Notificările persistă peste restart API. Sunt șterse automat când se depășesc 500 (se elimină cele mai vechi).
            </Note>
          </SubSection>
        </Section>

        {/* ── 10. RAPOARTE ── */}
        <Section id="reports" title="10. Rapoarte">
          <SubSection title="Prezentare generală">
            <p>
              Tab-ul <strong className="text-white">Rapoarte</strong> oferă analiză agregată a activității botului.
              Nu afectează starea botului — toate cele 4 sub-taburi sunt read-only.
            </p>
            <div className="grid grid-cols-2 gap-2 text-xs mt-2">
              {[
                { tab: "Tranzacții",  desc: "Toate tranzacțiile live cu filtre + secțiune OBS" },
                { tab: "Piețe",       desc: "Clasament simboluri după performanță" },
                { tab: "Comisioane",  desc: "Timeline zilnic comisioane + swap per piață" },
                { tab: "Uptime Bot",  desc: "Istoric porniri/opriri cu durate" },
                { tab: "Modificări",  desc: "Diff parametri la fiecare salvare profil" },
              ].map(({ tab, desc }) => (
                <div key={tab} className="bg-surface-card rounded-lg border border-surface-border p-2.5 space-y-0.5">
                  <div className="text-[11px] font-semibold text-slate-300">{tab}</div>
                  <div className="text-[10px] text-slate-500">{desc}</div>
                </div>
              ))}
            </div>
          </SubSection>

          <SubSection title="Tranzacții">
            <p>
              Tabel paginat (50/pagină) cu tranzacțiile <strong className="text-white">închise din istoricul MT5</strong>,
              cele mai noi primele — aceeași sursă ca Dashboard-ul.
            </p>
            <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-1.5 text-xs">
              <KV k="Filtru sursă" v="Toate / Custom / AI / Daily / Manual (din magic + comment, fără ghicire)" />
              <KV k="Alte filtre" v="Rezultat (TP / SL / …), direcție, interval de date" />
              <KV k="Coloane" v="Sursă, sesiune + strategie (Custom), simbol, direcție, entry / exit, R, P&L, comision + swap" />
              <KV k="AI✓" v="Ordin Custom validat de Filtrul AI Pre-Trade (cu încrederea)" />
            </div>
            <Note>Daily Engine rulează în shadow → nu are tranzacții MT5; trade-urile lui virtuale sunt în tab-ul Daily Engine.</Note>
          </SubSection>

          <SubSection title="Piețe" defaultOpen={false}>
            <p>
              Clasament al simbolurilor după <strong className="text-white">Total R</strong> acumulat (descrescător).
              Primele 3 locuri primesc pictograme trofeu.
            </p>
            <div className="space-y-1.5 text-xs mt-2">
              <KV k="Trades" v="Total tranzacții cu outcome final" />
              <KV k="Win Rate" v="(Câștiguri / Total) × 100" />
              <KV k="Expectancy" v="Media result_r per trade" vColor="text-profit" />
              <KV k="P&L USD" v="Suma profit real (ordine MT5 închise)" />
              <KV k="Sesiuni active" v="Câte sesiuni tranzacționează simbolul" />
            </div>
            <Tip>
              Simbolurile cu expectancy negativ constant sunt candidați pentru dezactivare sau schimbare parametri —
              rulează un backtest cu noii parametri înainte de orice modificare.
            </Tip>
          </SubSection>

          <SubSection title="Uptime Bot" defaultOpen={false}>
            <p>
              Tabel cu toate evenimentele de start/stop ale botului din <code className="text-blue-300">data/bot_uptime_log.json</code>.
            </p>
            <div className="space-y-1.5 text-xs mt-2">
              <KV k="Data Start" v="Momentul pornirii botului din UI" />
              <KV k="Data Stop" v="Momentul opririi (null dacă botul rulează)" />
              <KV k="Durată" v="Ex: 14h 32m — calculat din duration_sec" />
              <KV k="Profil" v="Profilul activ la momentul pornirii" />
            </div>
            <div className="mt-3 space-y-1 text-xs">
              <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Summary</div>
              <KV k="Total sesiuni" v="Numărul de porniri înregistrate" />
              <KV k="Uptime total" v="Suma tuturor duration_sec în ore/zile" />
              <KV k="Ultima pornire" v="Data celei mai recente sesiuni active" />
            </div>
            <Note>
              Logul se actualizează automat la start/stop din UI. Opriri prin crash (fără click Stop) sunt detectate de watchdog și marcate ca necompletate.
            </Note>
          </SubSection>

          <SubSection title="Comisioane" defaultOpen={false}>
            <p>
              Tab dedicat costurilor de broker — comisioane și swap înregistrate la fiecare tranzacție reală MT5.
            </p>
            <div className="space-y-2 text-xs mt-2">
              <div className="bg-surface rounded-lg border border-surface-border p-3 space-y-1.5">
                <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Timeline zilnic (primar)</div>
                <KV k="Azi (evidențiat)" v="Ziua curentă cu fundal albastru" />
                <KV k="Com." v="Suma comisioanelor din ziua respectivă" />
                <KV k="Swap" v="Suma swap-ului din ziua respectivă" />
                <KV k="Total" v="Com + Swap combinate" />
                <KV k="Trades" v="Câte tranzacții cu date de cost în ziua respectivă" />
              </div>
              <div className="bg-surface rounded-lg border border-surface-border p-3 space-y-1.5">
                <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Breakdown per piață</div>
                <div className="text-slate-400">Afișat sub timeline — totalizat per simbol pentru toate datele disponibile.</div>
              </div>
            </div>
            <Note>
              Datele de cost (<code className="text-blue-300">commission_usd</code>, <code className="text-blue-300">swap_usd</code>) sunt înregistrate din June 2026.
              Tranzacțiile anterioare au <code className="text-blue-300">NaN</code> în aceste câmpuri și nu apar în timeline.
              Rulează <code className="text-blue-300">scripts/backfill_pnl_usd.py</code> cu MT5 conectat pentru a completa istoricul.
            </Note>
          </SubSection>

          <SubSection title="Modificări Sesiuni" defaultOpen={false}>
            <p>
              Istoric al tuturor modificărilor de parametri la fiecare salvare profil.
              Scris în <code className="text-blue-300">data/session_changes_log.json</code> la <code className="text-blue-300">PUT /profiles/{"{profile_id}"}</code>.
            </p>
            <div className="bg-surface rounded-lg border border-surface-border p-3 font-mono text-xs space-y-1.5 text-slate-400">
              <div className="text-[10px] text-slate-500 uppercase mb-2">Exemplu intrare</div>
              <div><span className="text-slate-500">profil:</span> Standard Profile · <span className="text-slate-500">data:</span> 2026-06-25 14:30</div>
              <div className="pl-2 space-y-0.5">
                <div><span className="text-blue-300">S5 — USDCHF:</span></div>
                <div className="pl-2"><span className="text-loss">pullback_window:</span> <span className="text-slate-500">6</span> → <span className="text-profit">8</span></div>
                <div className="pl-2"><span className="text-loss">r_base:</span> <span className="text-slate-500">2.5</span> → <span className="text-profit">3.0</span></div>
              </div>
            </div>
            <p className="text-xs text-slate-400 mt-2">
              Câmpurile nemodificate nu apar în diff. Fiecare acordeon afișează profilul, data
              și numărul total de câmpuri schimbate per sesiune.
            </p>
            <Tip>
              Util pentru a urmări evoluția configurației și pentru a reveni la parametrii anteriori dacă performanța se degradează după o modificare.
            </Tip>
          </SubSection>
        </Section>

        {/* ── 11. AI ENGINE ── */}
        <Section id="ai-engine" title="11. AI Engine (motor autonom AI)">
          <SubSection title="Ce este">
            <p>
              Motor separat de botul pe reguli: la fiecare bară M15 calculează o percepție numerică (trend, ATR, regim
              trend/chop, știri), iar pe anumite <b>trigger-e</b> convoacă un <b>consiliu de 4 roluri AI</b> care propune
              un trade JSON; regulile hard din cod (rails) îl validează sau îl resping.
            </p>
            <div className="space-y-1 text-xs">
              <KV k="Piețe" v="CHFJPY, GBPUSD (cele mai puțin slabe pe ledger-ul real; niciuna cu edge dovedit)" />
              <KV k="Trigger-e active" v="regime_flip, news_window, position_review (breakout_tension, heartbeat, vol_spike oprite)" />
              <KV k="Limite" v="Max 2 poziții + pending, fără pyramiding, risc ≤ 1%, stop zilnic −3R, marjă ≤ 40%" />
              <KV k="Izolare" v="Magic 770015 + comment „AI-”: nu vede și nu atinge pozițiile Custom Engine" />
              <KV k="Weekend" v="Vineri de la 22:00 și sâmbătă/duminică: închide și nu deschide pe FX/indici (cripto 24/7)" />
              <KV k="Instanță unică" v="Mutex + PID; plus detecție cross-mașină (alt PC pe același cont → nu mai convoacă)" />
            </div>
          </SubSection>

          <SubSection title="Surse AI: Ollama + Gemini">
            <div className="space-y-1 text-xs">
              <KV k="Ollama (local)" v="Analist Tehnic, Analist Macro, Risk Manager — model qwen3:8b, gratuit, safety-net (nu se șterge)" />
              <KV k="Gemini" v="Head Trader (free tier)" />
              <KV k="Failover" v="Sursă căzută / fără quota → rolul trece automat pe altă sursă sănătoasă, apoi Ollama" />
              <KV k="Buget de timp" v="240 s per consiliu, respectat și LA APEL (timeout = timpul rămas); depășit → WAIT" />
              <KV k="Ollama instabil" v="Reîncercare la conexiune închisă, pauză 30 s dacă e oprit, recuperare singur fără restart" />
            </div>
            <Note>Celelalte surse (Claude, ChatGPT, Groq, Mistral etc.) au fost scoase; cheile lor sunt păstrate local în
              data/ai/providers.removed-2026-10-31.json. O sursă nouă se poate adăuga oricând din cardul Surse AI.
              Butonul 🩺 testează toate sursele în paralel; <code>python -m ai_engine.doctor</code> verifică inferența reală Ollama.</Note>
          </SubSection>

          <SubSection title="Consiliul — 4 roluri">
            <div className="space-y-1 text-xs">
              <KV k="📈 Analist Tehnic" v="Direcția (bias) + încredere" />
              <KV k="🌍 Analist Macro" v="Contextul zilei, risc de știri + încredere" />
              <KV k="🛡️ Risk Manager" v="Veto doar cu cod valid (NEWS_IMMINENT, DAILY_STOP, MAX_POSITIONS, EXTREME_VOL, WEEKEND_GAP, BAD_GEOMETRY)" />
              <KV k="🎯 Head Trader" v="Decizia finală (approve, SL, TP, risc) + încredere" />
            </div>
            <Note><b>Încrederea</b> deciziei = media membrilor care raportează una (Tehnic, Macro, Head). Media sub prag
              (implicit 70) → WAIT. La o respingere, „încredere 90%” înseamnă cât de sigur e consiliul că trade-ul e SLAB.
              Multe decizii WAIT = disciplină, nu inactivitate.</Note>
          </SubSection>

          <SubSection title="Piețe: mod Activ / Observație + limite per piață">
            <div className="space-y-1 text-xs">
              <KV k="Activ" v="Analizează și poate plasa ordine" />
              <KV k="Observație" v="Analizează, decizia e salvată „shadow”, ZERO ordine noi; exclusă din scorecard" />
              <KV k="Limite per piață" v="Fracție capital, risc, R:R max, stop zilnic, max ordine/zi, lot fix" />
              <KV k="Stare live" v="Pe fiecare rând: ordine azi X/Y, R azi vs stop, dacă poate deschide + motiv" />
              <KV k="Adăugare piață" v="„+ Add Market” cu căutare în simbolurile reale din MT5" />
            </div>
            <Note>Vechiul „Izolat” doar scotea piața din scorecard, dar ea tranzacționa în continuare — a fost înlocuit de
              Observație (setările vechi sunt convertite automat).</Note>
          </SubSection>

          <SubSection title="Date și curățare" defaultOpen={false}>
            <p className="text-xs">Ledger SQLite <code>data/ai/ledger.db</code>: percepții, transcripturi, decizii, rezultate.
              Luni de la 12:00, pentru analizele FĂRĂ trade mai vechi de 28 de zile se golește doar textul greu (transcript +
              snapshot); trade-urile plasate rămân integral, niciun rând nu se șterge.</p>
          </SubSection>
        </Section>

        {/* ── 12. DAILY ENGINE ── */}
        <Section id="daily-engine" title="12. Daily Engine (intraday — Shadow sau Execuție)">
          <SubSection title="Ce face">
            <p>Tranzacționare în aceeași zi la deschiderea burselor, când intră volumul mare. Un trade pe zi pe piață,
              închis obligatoriu în aceeași zi (niciodată peste noapte). Fără RSI/EMA — doar preț și oră.</p>
            <div className="space-y-1 text-xs">
              <KV k="☀️ GBPUSD 10:00 → 16:30 RO" v="Deschiderea Londrei: interval 5 min, ordine stop pe ambele margini (rol: observație)" />
              <KV k="🌆 US500 16:30 → 23:00 RO" v="Deschiderea New York: interval 30 min, intrare la 17:00 pe direcția intervalului (principal)" />
              <KV k="Stop loss" v="Marginea opusă a intervalului; fără TP fix — ieșire la final de fereastră" />
              <KV k="Zi sărită" v="Interval fără direcție, ambele margini în aceeași bară, risc < 2× cost, piață închisă" />
              <KV k="Fus orar" v="Pe ora bursei: în săptămânile cu decalaj SUA/RO fereastra NY se mută singură la 15:30" />
            </div>
          </SubSection>

          <SubSection title="Când se plasează ordinele + R:R și re-intrări (opționale)" defaultOpen={false}>
            <div className="space-y-1 text-xs">
              <KV k="GBPUSD (Londra)" v="interval de deschidere 08:00–08:05 Londra (10:00–10:05 RO, prima lumânare M5) → de la 08:05 ordine stop pe ambele margini; ieșire la SL sau la 14:30 Londra (16:30 RO)" />
              <KV k="US500 (New York)" v="interval 09:30–10:00 NY (16:30–17:00 RO, 6 lumânări M5) → la 10:00 NY intrare la piață pe direcția intervalului; ieșire la SL sau la 16:00 NY (23:00 RO)" />
              <KV k="„Delay o lumânare”" v="primul trade așteaptă deja finalul intervalului (GBPUSD = 1 lumânare de 5 min, US500 = 30 min); la re-intrări pauza după ieșire e configurabilă (implicit 1 lumânare)" />
              <KV k="R:R (opțional)" v="oprit = fără TP (actual: poziția rămâne până la SL sau finalul ferestrei). Pornit = TP la N × risc (2R / 3R / 4R / altă valoare); în Execuție TP-ul e atașat ordinului real" />
              <KV k="Schimbă piața (per slot)" v="două sloturi (dimineață / după-amiază); pe fiecare alegi BURSA (Londra 08:00, Frankfurt 09:00, New York 09:30 — ora, intervalul și modul testate) și PIAȚA din MT5. Costurile se reglează AUTOMAT din spread (slippage = 25% din spread-ul live; „comision” = markup-ul contului = spread live − spread-ul din istoric) sau manual. Previzualizează arată costurile, marja la lotul minim și un backtest pe ~3 ani înainte de salvare; schimbarea e refuzată cât timp slotul are o poziție azi" />
              <KV k="Pause / Resume (per piață)" v="butonul de pe cardul pieței: fără intrări noi (shadow sau real), ordinele de intrare neactivate se anulează; o poziție deja deschisă rămâne pe SL și se închide la final de fereastră. Cealaltă piață continuă normal. Starea persistă la restart; nimic automat nu o reia (doar Resume)" />
              <KV k="Backtest pe configurația curentă" v="legat de configurația EXACTĂ (piață, bursă, interval, mod, R:R, re-intrări, costuri): la salvare rezultatul vechi devine „Outdated” și pornește singur un backtest nou în fundal (Pending → Running → Completed / Failed); o schimbare în timpul rulării aruncă rezultatul vechi. Același mecanism în Noisy (12 luni, configurația curentă)" />
              <KV k="Re-intrări (opțional)" v="după ce trade-ul se închide, Daily poate intra din nou la o NOUĂ rupere a aceluiași interval, doar în primele N minute de la deschidere (implicit 60), maxim K pe zi (3), un singur trade odată, STOP după 2 pierderi la rând, pauză de 1 lumânare după ieșire" />
            </div>
            <Warn>Testate pe 10–14 ani (M5, costuri reale): ținta fixă 2R / 3R / 4R a fost mai slabă decât „fără TP” pe ambele piețe
              (ORB câștigă din puținele zile de trend mare, pe care TP-ul le taie). Re-intrările adaugă ~1–2 trade-uri / săptămână,
              dar scad câștigul pe trade (GBPUSD +0,075 → +0,027R; US500 +0,059 → +0,049R). Sunt opționale pentru test în shadow.
              Frankfurt (DE40) a ieșit cel mai bine (+0,08…0,09R, KEEP, și cu re-intrări), dar marja lotului minim (~145 $) nu încape
              acum în cont. Detalii: docs/DAILY_ENGINE_PLAN.md §10.</Warn>
          </SubSection>
          <SubSection title="Mod per piață: LIVE / SHADOW / PAUZĂ, Profit Lock, limita de marjă" defaultOpen={false}>
            <div className="space-y-1 text-xs">
              <KV k="Unde" v="Pe cardul fiecărei piețe: LIVE / SHADOW / PAUZĂ. O piață nu o afectează pe cealaltă; modul persistă la restart" />
              <KV k="LIVE" v="ordine reale de la următoarea fereastră; pe cont REAL doar cu „Daily Engine” deblocat în Settings → Trading LIVE (altfel cardul arată „LIVE cerut, dar BLOCAT” + motivul). Două confirmări" />
              <KV k="SHADOW" v="trade-uri virtuale pe prețuri reale, zero ordine; o poziție reală deschisă azi rămâne gestionată până la SL / final" />
              <KV k="PAUZĂ" v="nicio intrare nouă (nici virtuală); ordinele de intrare neactivate se anulează; o poziție deschisă rămâne gestionată (SL, Profit Lock, final de fereastră)" />
              <KV k="Piață nouă într-un slot" v="pornește mereu în SHADOW — Live se aprobă per piață" />
              <KV k="Profit Lock (opțional, OPRIT)" v="„Opțiuni” pe card: la +Trigger R (minim 3R) SL-ul se mută la +Lock R (sub Trigger). Ex. 4,5R → 4R. În Live mută SL-ul real în MT5 (doar dacă e mai protector). Backtest: nicio variantă n-a fost mai bună decât strategia actuală (DE40 5→4R la egalitate, cu drawdown mai mic)" />
              <KV k="Limită de marjă" v="marja TOTALĂ a contului după un ordin Daily ≤ 80% din equity (toate engine-urile). DE40 la lotul minim ≈ 148 $ — cu alte poziții deschise ordinul nu se plasează (motivul în Notificări)" />
              <KV k="Vineri" v="închiderea de vineri din Setări Globale se aplică și pe Daily (poziții închise, nimic nou de la ora globală)" />
              <KV k="Alertă +5R" v="când un trade deschis trece de +5R primești o singură notificare (Notificări + Telegram) — nu se închide nimic automat, decizia e a ta. Pragul se schimbă din tab-ul Daily (0 = oprită)" />
              <KV k="Sesiuni (per piață)" v="„Opțiuni” pe card: bifezi Londra / Frankfurt / New York (oricâte, minim una). Fiecare sesiune folosește ora, intervalul și modul testate pe acea deschidere" />
              <KV k="Trade-uri maxime / zi" v="limită pe piață peste toate sesiunile și re-intrările (implicit 1; config vechi păstrează limita re-intrărilor). Trade-urile se admit în ordinea apariției; o piață nu are niciodată două poziții simultan; cealaltă piață are propria limită" />
              <KV k="Audit" v="schimbările de mod / pauză / configurare apar în Rapoarte → Modificări („Audit engine-uri”)" />
            </div>
          </SubSection>
          <SubSection title="Shadow → Execuție (ordine reale)">
            <div className="space-y-1 text-xs">
              <KV k="Unde" v="Pe cardul pieței: selectorul LIVE / SHADOW / PAUZĂ (două confirmări la LIVE)" />
              <KV k="Cont DEMO" v="Execuția merge direct" />
              <KV k="Cont REAL" v="În plus: Settings → Trading LIVE → „Daily Engine” deblocat (per mașină). Altfel: „Execuție blocată” + motivul" />
              <KV k="De când" v="De la următoarea fereastră — ziua trebuie activată înainte de formarea intervalului (comutat mai târziu → ziua rămâne shadow)" />
              <KV k="GBPUSD" v="BUY_STOP + SELL_STOP pe marginile intervalului; la umplerea uneia cealaltă se anulează" />
              <KV k="US500" v="Ordin la piață la 17:00 RO pe direcția intervalului" />
              <KV k="Mereu" v="SL atașat, lot din dimensionarea comună, Setări Globale + știri respectate, închidere la finalul ferestrei, nimic peste noapte" />
              <KV k="În Dashboard" v="Tranzacțiile reale apar ca „DAILY” (magic 880001) în Tranzacții, carduri și rapoarte" />
            </div>
            <Warn>Recomandarea rămâne: 2–3 luni de shadow înainte de execuție pe cont real — edge-ul din backtest e mic.</Warn>
          </SubSection>

          <SubSection title="Mod SHADOW — de ce și ce înseamnă">
            <p>Nu plasează niciun ordin: citește doar prețurile reale din MT5 și înregistrează trade-uri <b>virtuale</b> cu exact
              regulile din backtest. Edge-ul din cercetare e mic (+0,06…0,08R/trade) și nedovedit statistic după corecția de
              căutare multiplă — trebuie confirmat pe date noi înainte de bani reali.</p>
            <div className="space-y-1 text-xs">
              <KV k="Trade-uri virtuale" v="data/daily_engine/trades.jsonl (local mașinii pe care rulează)" />
              <KV k="Notificări" v="„🧪 Daily SHADOW” la intrare și la închidere, o singură dată pe zi / piață" />
              <KV k="În Dashboard" v="Card Daily: banii reali = 0; trade-urile virtuale separat, în R" />
              <KV k="Supraveghere" v="Watchdog-ul API îl repornește dacă moare fără Stop (max 3/oră)" />
            </div>
            <Note>Cercetarea completă (studii oficiale, ore de vârf, 216 variante testate, constrângerea contului de ~$200):
              docs/DAILY_ENGINE_PLAN.md. Trecerea la ordine reale = etapă separată, cu aprobare.</Note>
          </SubSection>
        </Section>

        {/* ── 12b. NOISY ENGINE ── */}
        <Section id="noisy-engine" title="12b. Noisy Engine (frecvență mare — Shadow sau Execuție)">
          <SubSection title="Ce face">
            <p>Engine activ pe <b>o singură piață (USDJPY)</b>, implicit pe bare de <b>1 minut</b>: când prețul se depărtează brusc de
              media lui (peste 2×ATR de EMA20), intră <b>contra mișcării</b> și iese la revenirea la medie, la SL (1,5×ATR) sau după 20 de bare.
              Long și Short, o singură poziție odată. Pe M1: ~25 de trade-uri pe zi (~2–3 pe oră), ținere medie ~8 minute.</p>
            <div className="space-y-1 text-xs">
              <KV k="Scop" v="FRECVENȚĂ (multe trade-uri), nu profit: backtestul pe M1 e ~0 după costuri (−0,01R/trade). M5 rămâne opțiune (~4/zi, +0,08R)" />
              <KV k="Pornire" v="DOAR manuală, cu confirmare (Risk level: HIGH). Fără autostart, nu e repornit de watchdog" />
              <KV k="Ferestre" v="unul sau mai multe intervale (ex. 10:00–13:00 + 16:00–22:00), ora RO, zilele bifate; fără suprapuneri (se verifică la salvare); un interval poate trece de miezul nopții (aparține zilei în care începe), dar nicio intrare care ar rămâne deschisă după 00:00. Implicit 10:00–20:00 (varianta testată)" />
              <KV k="Edit Market" v="piața se alege din lista reală MT5 (căutare); vezi spread-ul live, lotul minim, marja; schimbarea e refuzată cât timp există o poziție deschisă. Doar USDJPY a fost testat" />
              <KV k="Limite (opționale)" v="max 60 trade-uri / zi, max 25 pierderi / zi, max 8 la rând → blocat până a doua zi" />
              <KV k="Buget izolat" v="P&L-ul Noisy (în Execuție: din MT5, magic 990001), NU equity-ul contului; sub prag → „Stopped – Budget Limit” până la reset manual" />
              <KV k="Protecții" v="Setările Globale (capital, circuit breaker, știri, risc maxim) se aplică și nu pot fi ocolite; plus știri High pe USD/JPY și spread live" />
              <KV k="Emergency Stop" v="Oprește imediat, ÎNCHIDE pozițiile reale Noisy și blochează intrările până la Resume (fără AI)" />
              <KV k="M1 ⇄ M5" v="limitele au valori separate pe fiecare timeframe (M1: 60 / 25 / 8 · M5: 6 / 4 / 3); la comutare contoarele zilei se recalculează pe timeframe-ul ales" />
              <KV k="Setări Globale" v="se aplică toate (capital, circuit breaker, știri, închidere de vineri, risc maxim, poziții simultane); filtrul AI pre-trade e doar al Custom Engine" />
            </div>
          </SubSection>
          <SubSection title="Spread și motivul fiecărui semnal respins" defaultOpen={false}>
            <div className="space-y-1 text-xs">
              <KV k="Unitate" v="points MT5 (coloana „Spread” din Market Watch); pagina arată și pips și prețul. USDJPY: 1 point = 0,001 = 0,1 pips" />
              <KV k="Spread tipic (cost)" v="Auto = mediana spread-ului live din tick-urile MT5, înghețată pe zi la deschiderea ferestrei · Manual = valoarea ta" />
              <KV k="Spread maxim" v="Auto = N × tipic (implicit 1,5×) · Manual = points (0 = fără limită); peste el semnalul e respins" />
              <KV k="Filtrul cost/ATR" v="intră doar când mișcarea (ATR) e de cel puțin N ori costul (M1: 5×, M5: 15×). Un spread tipic mare = puține sau zero trade-uri — intenționat" />
              <KV k="Stop de timp" v="editabil în Configurare (bare; pe M1 1 bară = 1 minut, implicit 20). Pe US500 M1 durata 10–120 min nu schimbă rezultatul" />
              <KV k="Activ / Oprit (probă)" v="comutatorul din Configurare → Spread, separat pe M1 și M5; pragul e editabil. OPRIT = Noisy intră și când costul mănâncă mișcarea — bun ca să vezi engine-ul lucrând în SHADOW, NU pentru Execuție. La reactivare revine pragul de dinainte" />
              <KV k="De ce nu intră?" v="fiecare semnal respins apare în panoul pieței și în jurnal cu motivul și cifrele (cost/ATR, spread, știri, limite, interval, suprapuse, direcție…)" />
            </div>
            <Warn>Pe contul Standard spread-ul live al USDJPY e ~9 points (istoricul MT5 arată doar ~1 point brut). Cu 9 points, pe M1
              filtrul cost/ATR respinge aproape tot (ATR mediu ~20 points); de aceea, după ridicarea spread-ului, Noisy nu mai intra.
              Backtest la spread real (USDJPY): M1 ~0,6 trade-uri / zi (+0,09R), M5 ~0,1 / zi.</Warn>
            <Note>Piețe mai ieftine, testate (12 luni, spread live, cu filtre): XAGUSD M1 ~1,2 / zi ≈ 0R (marjă 51$) · US500 M1
              ~8 / zi −0,07R (marjă 38$) · UK100 M1 ~0,8 / zi −0,08R (marjă 72$). Niciuna nu are edge dovedit; indicii sunt de
              4–10× mai ieftini decât FX-ul pe contul Standard. Detalii: docs/NOISY_ENGINE_RESEARCH.md §21.</Note>
          </SubSection>
          <SubSection title="Trade-uri suprapuse (opțional, oprit implicit)" defaultOpen={false}>
            <div className="space-y-1 text-xs">
              <KV k="Oprit (implicit)" v="o poziție odată — varianta testată" />
              <KV k="Pornit" v="max deschise simultan (2–10), interval minim între intrări (minute), aceeași direcție da / nu, direcție opusă (hedging) da / nu" />
              <KV k="Ordinea regulilor" v="Setări Globale (inclusiv poziții simultane pe piață, numărate și pe pozițiile virtuale) → bugetul Noisy (riscul tuturor pozițiilor + cel nou) → limitele zilnice (max trade-uri = intrări) → max deschise → interval → direcție" />
            </div>
            <Note>Backtest 12 luni (M5, spread real): numărul de trade-uri se dublează, expectancy-ul nu se schimbă, drawdown-ul se dublează.</Note>
          </SubSection>
          <SubSection title="Break-Even și R:R (opționale, dezactivate implicit)" defaultOpen={false}>
            <div className="space-y-1 text-xs">
              <KV k="Break-Even" v="aceeași regulă și aceiași parametri ca în Custom Engine: trigger% din drumul spre țintă → la întoarcere SL la lock1%; Faza 2 opțională → SL la lock2%" />
              <KV k="În Execuție" v="SL-ul REAL e mutat la broker când trade-ul ajunge în faza respectivă (o singură dată pe fază)" />
              <KV k="R:R" v="implicit ținta = revenirea la EMA20 (~1,6R în medie); opțional R:R fix (ex. 1:2)" />
            </div>
            <Note>Testele pe 12 luni (USDJPY): Break-Even-ul crește win rate-ul (M5 44% → 48%, M1 41% → 45%) și reduce puțin scăderile,
              dar NU crește profitul (M5 +0,081R → +0,069R / trade). Țintele fixe 1,5 / 2 / 3R au fost mai slabe decât revenirea la EMA.
              Când bifezi Break-Even, pagina afișează aceste rezultate.</Note>
          </SubSection>
          <SubSection title="Shadow → Execuție (butonul de Live)" defaultOpen={false}>
            <div className="space-y-1 text-xs">
              <KV k="SHADOW (implicit)" v="trade-uri virtuale pe prețuri reale, zero ordine" />
              <KV k="EXECUȚIE" v="selectorul din tab-ul Noisy (două confirmări): la fiecare semnal, ordin real la piață cu SL + țintă, stop de timp, o poziție odată" />
              <KV k="Cont REAL" v="în plus: Settings → Trading LIVE → Noisy Engine (deblocare per mașină). Fără ea, Execuția rămâne blocată cu motivul afișat" />
              <KV k="La oprire" v="implicit închide pozițiile reale (configurabil: le lasă cu SL/țintă); Emergency Stop le închide mereu" />
              <KV k="În Dashboard" v="card portocaliu „Noisy Engine” (Doar manual), card de performanță cu banii reali + linia SHADOW separată, eticheta NOISY în Tranzacții" />
            </div>
            <Note>Pe M1 costurile (spread, eventual comision) cântăresc mult: backtestul arată un drawdown de ~117R pe an la ~0 câștig.
              Bugetul izolat oprește engine-ul înainte ca pierderile să atingă restul contului. Research complet: docs/NOISY_ENGINE_RESEARCH.md.</Note>
          </SubSection>
        </Section>

        {/* ── 13. DEMO / LIVE ── */}
        <Section id="live" title="13. Demo / Live">
          <SubSection title="Cum se deblochează contul real">
            <p>Implicit totul e DEMO-only: Custom Engine și AI Engine refuză un cont real. Deblocarea e explicită, per componentă
              și per mașină: <b>Settings → Trading LIVE</b> (două confirmări). Daily Engine în shadow e doar citire, deci rulează pe
              orice cont fără risc. Pentru modul Execuție pe cont real există un switch separat „Daily Engine” în Trading LIVE.</p>
            <div className="space-y-1 text-xs">
              <KV k="Fișier" v="data/live_trading.json (nu se sincronizează prin git)" />
              <KV k="La prima conectare reală" v="Telegram „⚠️🔴 CONT LIVE” o dată per proces" />
              <KV k="Eroare la citire" v="BLOCAT (fail-safe)" />
              <KV k="Aplicare" v="La următoarea conectare (repornește engine-ul dacă rulează)" />
            </div>
          </SubSection>

          <SubSection title="Listă de verificare înainte de live">
            <div className="space-y-1 text-xs">
              <KV k="1. Capital de start" v="Tab Custom Engine → Capital Inițial (sau Import din MT5) — baza pentru P&L Real" />
              <KV k="2. AutoTrading" v="Butonul din MT5 verde (altfel bannerul galben și nimic nu se plasează)" />
              <KV k="3. Execuție" v="Doar sesiunile dorite pe Live; DEMOTE (badge roșu ⚠ live) → de preferat Observație" />
              <KV k="4. Risc / marjă" v="Fracție cont, lot minim al brokerului, lot fix — verifică breakdown-ul în USD" />
              <KV k="5. Setări Globale" v="Protecție capital + circuit breaker recomandate pe cont real" />
              <KV k="6. Pornire" v="Cardul engine-ului → Start (confirmare); urmărește Notificările primele ore" />
              <KV k="7. Primul ordin" v="Verifică în MT5 entry / SL / TP față de notificare" />
            </div>
          </SubSection>

          <SubSection title="Rapoarte automate (Telegram)" defaultOpen={false}>
            <div className="space-y-1 text-xs">
              <KV k="Zilnic (opțional)" v="Pornit implicit, se poate opri din Settings; în fiecare zi la ora setată (23:30): tranzacțiile zilei din MT5. O singură dată pe zi, și după restart / cu două dashboard-uri pornite" />
              <KV k="Săptămânal" v="Vineri de la 20:00 (ora setată): așteaptă întâi închiderea pozițiilor de vineri (max 20 min) și istoricul MT5; fereastra e continuă — de la raportul trecut până în momentul trimiterii, deci închiderile de vineri intră în raport. Dacă aplicația e închisă vineri, se trimite la următoarea pornire (până luni 12:00)" />
              <KV k="Lunar" v="Pe 1 ale lunii la 09:00, DOAR luna calendaristică încheiată (niciodată luna curentă — o gardă refuză altceva); recuperat în primele 7 zile" />
              <KV k="Conținut lunar" v="Complet: performanța Custom / AI / Daily + TOTAL, comparație (profit, risc, drawdown, consistență), condiții de piață, evenimente, weekend, probleme, analiză AI consultativă" />
              <KV k="Conținut săptămânal" v="Esențial: partea de trading identică (performanță + comparație); piața într-un rând (trend / range pe piață), știrile High (următoarele 5), gap-uri de weekend și probleme grave DOAR dacă au existat, analiză AI în 3 puncte" />
              <KV k="Lipsuri" v="O sursă indisponibilă (MT5, calendar, AI) e marcată explicit — raportul se trimite oricum" />
              <KV k="MT5 încă nepregătit" v="în primele minute după pornire (sau cât timp terminalul nu e logat) raportul NU pleacă gol: se AMÂNĂ automat până MT5 e gata (notificare „amânat”), maxim 3h; apoi se trimite cu MT5 marcat „indisponibil — NU înseamnă zero tranzacții”" />
              <KV k="Unde se setează" v="Settings → Rapoarte programate (ore, AI, mașina care trimite, trimitere manuală)" />
            </div>
            <Note>Lasă „Trimite de pe această mașină” activ doar pe mașina care rulează engine-urile — altfel primești rapoarte duble.
              Fusul orar al rapoartelor = cel din Settings → Fus orar.</Note>
          </SubSection>
        </Section>

        {/* ── 14. DATE, STOCARE, RECOVERY ── */}
        <Section id="data-recovery" title="14. Date, stocare și recovery">
          <SubSection title="Sync PC ↔ laptop (sync_data.bat)">
            <div className="space-y-1 text-xs">
              <KV k="Cum" v="Dublu-click sync_data.bat pe dispozitivul pe care ești — același script pe ambele: trimite datele lui, aduce codul + datele celuilalt" />
              <KV k="Ce trimite" v="Doar datele engine-urilor care au rulat pe acel dispozitiv în ultimele 3 zile (semnale, ledger AI, trade-uri Daily) + setările modificate din UI" />
              <KV k="Engine-uri" v="Scriptul nu pornește și nu oprește nimic — tu alegi unde rulează (niciodată pe ambele)" />
              <KV k="Fișiere locale" v="Copiile locale care s-ar suprascrie sunt mutate în data/_sync_backup/<data-ora>/ — nu se șterge nimic" />
            </div>
            <Note>Când mută engine-urile: oprește-le pe un dispozitiv → sync_data.bat acolo → sync_data.bat pe celălalt → pornește-le.
              Dacă a venit cod nou, repornește dashboard-ul (start_ui.bat) și engine-urile. Nu folosi update_bot.bat pe alex-live (refuză).</Note>
          </SubSection>

          <SubSection title="Ce date există și unde">
            <div className="space-y-1 text-xs">
              <KV k="Istoric MT5" v="Sursa de adevăr pentru toate rezultatele (nu se copiază local)" />
              <KV k="Custom Engine" v="data/live_signals/session*/ — state.pkl, signals.csv, outcomes.csv, ai_filter.jsonl, generator.log" />
              <KV k="AI Engine" v="data/ai/ — ledger.db, status.json, engine.log, config surse" />
              <KV k="Daily Engine" v="data/daily_engine/ — trades.jsonl, state.json, status.json, engine/stdout/crash.log" />
              <KV k="API / UI" v="data/notifications.json, backtest_jobs.json, session_changes_log.json, bot_uptime_log.json" />
              <KV k="Config (în git)" v="data/profiles/standard.json, data/global_settings.json, ai_engine/config.json, daily_engine/config.json" />
              <KV k="Date de cercetare" v="data/*.csv, data/research_daily/ (OHLC, gitignored)" />
            </div>
            <Note>Branch-ul main = cod + fix-uri + configurație; datele operaționale nu intră în commit-uri (se sincronizează separat).</Note>
          </SubSection>

          <SubSection title="Ce se curăță automat">
            <div className="space-y-1 text-xs">
              <KV k="AI (luni 12:00)" v="Transcript + snapshot din analizele FĂRĂ trade > 28 zile; restul rămâne" />
              <KV k="Notificări" v="Maxim 500 (cele mai vechi ies)" />
              <KV k="Backteste / descărcări" v="Maxim 150 / 50 joburi; istoric backtest maxim 200" />
              <KV k="Jurnale" v="Rotație la 2 MB (Daily), fișiere per sesiune" />
            </div>
            <Note>signals.csv / outcomes.csv nu se curăță (deduplicare, contor ID-uri, recuperare).</Note>
          </SubSection>

          <SubSection title="Recovery după restart sau crash" defaultOpen={false}>
            <div className="space-y-1 text-xs">
              <KV k="Custom Engine" v="La pornire: reconciliază biletele MT5, recuperează rezultatele închise în lipsa lui ([RECOVER]), scanează 10 zile; MT5 are mereu prioritate" />
              <KV k="AI Engine" v="Watchdog propriu repornește motorul; rezultatele se recalculează din MT5" />
              <KV k="Daily Engine" v="Starea zilei se reconstruiește din bare la fiecare iterație — fără dubluri, fără notificări repetate" />
              <KV k="Ordinele" v="Pending-urile și pozițiile din MT5 rămân active cu SL/TP chiar dacă engine-ul e oprit" />
            </div>
            <Warn>state.pkl corupt (oprire forțată în timpul scrierii): oprește sesiunea, curăță cheile invalide, repornește.
              Sesiunea pornește oricum cu stare goală la corupție totală.</Warn>
          </SubSection>
        </Section>

        {/* ── 15. PUNTE TELEGRAM ── */}
        <Section id="telegram-bridge" title="15. Punte Telegram (control de pe telefon)">
          <SubSection title="Ce este și cum pornește">
            <p>
              Un daemon <strong>separat</strong> care îți permite să comanzi botul de pe telefon, prin
              chat-ul Telegram existent: comenzi instant de stare, întrebări rapide către sursele AI și
              sesiuni complete de Claude Code (analiză cod, teste, rapoarte).
            </p>
            <Note>
              Este <b>complet aditiv și izolat</b> — un proces separat care doar CITEȘTE starea (status.json,
              API local) și nu modifică botul, motorul AI sau API-ul. Nu deschide o a doua conexiune MT5.
              Pornirea e manuală și opțională — botul funcționează identic cu sau fără punte.
            </Note>
            <div className="grid grid-cols-1 gap-1.5 text-xs mt-2">
              <KV k="Pornire" v="dublu-click start_telegram_bridge.bat  (sau: py -m telegram_bridge)" />
              <KV k="Oprire" v="Ctrl+C în fereastra puntii" />
              <KV k="Test offline" v="py -m telegram_bridge.selftest  (fără Telegram/MT5/Claude)" />
              <KV k="Documentație" v="docs/TELEGRAM_BRIDGE.md" />
            </div>
          </SubSection>

          <SubSection title="Cele 4 niveluri de comandă">
            <div className="space-y-2 text-xs">
              <div className="bg-surface rounded-lg border border-surface-border p-3 space-y-1">
                <div className="flex items-center gap-2">
                  <Badge color="bg-slate-600/30 text-slate-200" label="Instant" />
                  <span className="text-slate-400">&lt;1s, fără AI</span>
                </div>
                <KV k="/status" v="bot + motor AI + cont MT5 + poziții deschise" />
                <KV k="/raport" v="scorecardul motorului AI (W/L, R, expectancy)" />
                <KV k="/piete" v="clasament per piață după R" />
                <KV k="/pauza S7 · /reia S7" v="pauză/reia o sesiune (ca în UI, reversibil)" />
                <KV k="/ajutor" v="lista completă de comenzi" />
              </div>
              <div className="bg-surface rounded-lg border border-surface-border p-3 space-y-1">
                <div className="flex items-center gap-2">
                  <Badge color="bg-emerald-600/30 text-emerald-200" label="ai …" />
                  <span className="text-slate-400">~5–30s, sursele AI existente</span>
                </div>
                <p className="text-slate-300">
                  <code>ai de ce e XRPUSD pe WAIT?</code> — întrebarea + context live (scorecard, poziții,
                  erori) merge la prima sursă AI sănătoasă. Răspuns în proză.
                </p>
              </div>
              <div className="bg-surface rounded-lg border border-surface-border p-3 space-y-1">
                <div className="flex items-center gap-2">
                  <Badge color="bg-indigo-600/30 text-indigo-200" label="claude …" />
                  <span className="text-slate-400">agent complet, read-only implicit</span>
                </div>
                <p className="text-slate-300">
                  <code>claude analizeaza de ce a picat S7 azi</code> — rulează Claude Code headless în repo,
                  cu tools REALE dar limitate la o listă read-only (citește cod, git, rulează teste/rapoarte;
                  NU poate edita). <code>claude+ …</code> continuă conversația (sau răspunzi direct la un mesaj
                  al lui Claude).
                </p>
              </div>
              <div className="bg-surface rounded-lg border border-surface-border p-3 space-y-1">
                <div className="flex items-center gap-2">
                  <Badge color="bg-amber-600/30 text-amber-200" label="claude! …" />
                  <span className="text-slate-400">modificări de cod — OFF implicit, 2 pași</span>
                </div>
                <p className="text-slate-300">
                  <code>claude! adauga un guard pentru X</code> → propune un PLAN + un cod de 6 cifre →
                  răspunzi <code>CONFIRM 428173</code> (în 5 min) → execută. Activat doar cu
                  <code> allow_writes: true</code>.
                </p>
              </div>
            </div>
          </SubSection>

          <SubSection title="Lanț de fallback pentru „claude …”" defaultOpen={false}>
            <p>Fiecare răspuns spune pe ce nivel/sursă a fost generat (ex: „— via Claude Code · $0.01 · 3 ture”):</p>
            <div className="space-y-1 text-xs mt-1">
              <KV k="1. Claude Code CLI" v="cu tools de repo — primar" />
              <KV k="2. Claude API direct" v="degradat: doar din context injectat, fără tools de repo" />
              <KV k="3. Surse AI existente" v="gemini / ollama (sursele din tab-ul AI Engine)" />
              <KV k="4. Mesaj onest" v="doar comenzile locale disponibile acum" />
            </div>
          </SubSection>

          <SubSection title="Securitate" defaultOpen={false}>
            <div className="space-y-1 text-xs">
              <KV k="Whitelist HARD" v="doar chat_id-ul tău; orice alt expeditor ignorat + alertă" vColor="text-emerald-300" />
              <KV k="Read-only implicit" v="fără Edit/Write; scrierea gated de allow_writes + confirmare" />
              <KV k="Un singur task greu" v="restul primesc „ocupat”; timeout 10 min per task Claude" />
              <KV k="Mesaje vechi ignorate" v="la pornire/downtime, comenzile > 3 min nu se execută" />
              <KV k="409 Conflict" v="dacă rulează 2 instanțe ale puntii, a doua se oprește singură" />
            </div>
            <Warn>
              „claude cu tools, comandat de pe telefon” = execuție pe PC-ul tău. De aceea whitelist-ul e
              hard, scrierea e OFF implicit și se cere confirmare în 2 pași. Recomandat: folosește read-only
              câteva zile înainte de a activa <code>allow_writes</code>.
            </Warn>
          </SubSection>

          <SubSection title="Ce chei trebuie activate" defaultOpen={false}>
            <p>Aproape nimic — tot ce e necesar e deja configurat. Pornești cu dublu-click pe .bat.</p>
            <div className="space-y-1 text-xs mt-1">
              <KV k="Telegram + whitelist" v="data/telegram_config.json — deja setat, reutilizat" vColor="text-emerald-300" />
              <KV k="ai … + fallback" v="data/ai/providers.json (ollama + gemini) — deja setat" vColor="text-emerald-300" />
              <KV k="claude … (agent)" v="login Claude Code pe acest PC — deja logat" vColor="text-emerald-300" />
              <KV k="Fallback Claude API" v="opțional: adaugă o sursă de tip „anthropic” în tab-ul AI Engine (nu e configurată acum)" />
              <KV k="Editări (claude!)" v="opțional: allow_writes: true în data/telegram_bridge.json" />
              <KV k="copilot …" v="opțional: instalează copilot / gh copilot + copilot_enabled: true" />
            </div>
            <Tip>
              Config-ul puntii (opțional) e în <code>data/telegram_bridge.json</code> — copiază-l din
              <code> telegram_bridge/config.example.json</code>. Sesiunile <code>claude …</code> costă din
              planul tău Claude — costul apare în fiecare răspuns.
            </Tip>
          </SubSection>

          <SubSection title="Pornire din UI + autostart la boot" defaultOpen={false}>
            <p>
              În <strong>Profil</strong>, sub setările Telegram, apare cardul
              <strong> „Punte Telegram — chat colaborare"</strong> — dar <strong>doar dacă Telegram
              e configurat</strong> (token + Chat ID). De acolo:
            </p>
            <div className="space-y-1 text-xs mt-1">
              <KV k="Pornește / Oprește" v="buton — pornește puntea fără terminal (îți trimite mesaj de start)" />
              <KV k="Pornire automată la boot" v="toggle — ca la bot, pornește la fiecare login Windows (UAC). Dezactivat implicit." />
              <KV k="Status live" v="activ/oprit · inactiv (economie) · mod edit · Claude CLI detectat" />
            </div>
            <Note>
              Autostart-ul creează task-ul <code>TradingBot-TelegramBridge</code> (neelevat, la login+60s).
              Puntea nu are nevoie de MT5/Ollama. Dezactivare din același toggle sau
              <code> scripts/remove_autostart_bridge.ps1</code>.
            </Note>
          </SubSection>

          <SubSection title="Mod EDIT de la distanță (fix critic de pe telefon)" defaultOpen={false}>
            <p>
              Modificările de cod (<code>claude!</code>) sunt oprite implicit. Le activezi de pe telefon,
              doar cât ai nevoie, cu o comandă — util dacă ești plecat și apare un bug critic:
            </p>
            <div className="space-y-1 text-xs mt-1">
              <KV k="/edit on" v="activează modul EDIT (persistat, aplicat live, fără restart)" vColor="text-amber-300" />
              <KV k="/edit off" v="înapoi la read-only" />
              <KV k="/edit" v="arată starea curentă" />
            </div>
            <Note>
              Whitelist-ul te-a filtrat deja (doar chat-ul tău), deci doar tu poți da <code>/edit</code>.
              Scrierea rămâne în 2 pași: <code>claude! …</code> → plan + cod → <code>CONFIRM &lt;cod&gt;</code>.
              <br /><b>Editor de rezervă gratuit:</b> dacă Claude CLI e indisponibil, <code>claude!</code>
              folosește automat <b>Aider</b> (gratuit: <code>pip install aider-chat</code>; model <code>gemini/gemini-2.5-flash</code>, cu cheia Gemini din providers.json).
              Vezi cu <code>/editors</code>.
              <br /><b>Notificări MT5/piețe:</b> deja active — botul trimite alertă la conexiune MT5 pierdută,
              broker deconectat, AutoTrading oprit; motorul AI la pierderea conexiunii MT5.
            </Note>
          </SubSection>

          <SubSection title="Al doilea canal: Matrix / Element (EU, gratuit)" defaultOpen={false}>
            <p>
              Pe lângă Telegram, poți folosi <strong>Matrix</strong> (Element) — protocol deschis, <strong>EU</strong>
              (Element/Londra; folosit de guvernul francez, Bundeswehr, NATO), GDPR, aplicație de telefon,
              gratuit. <strong>Aceleași comenzi</strong> ca pe Telegram. Rulează izolat (un eșec Matrix nu
              atinge Telegram-ul), <strong>oprit implicit</strong>.
            </p>
            <div className="space-y-1.5 mt-2">
              {[
                { step: "1", title: "Instalează Element + cont EU", desc: "App Store/Play. La înregistrare alege homeserver EU (ex: tchncs.de - Germania) sau matrix.org." },
                { step: "2", title: "Creează o cameră NEcriptată", desc: "+ → New room → dezactivează 'end-to-end encryption' → copiază Room ID din Room info → Advanced (!xxx:tchncs.de). Puntea nu citește camere criptate." },
                { step: "3", title: "Ia Access Token", desc: "Settings → Help & About → Advanced → Access Token → copiază (syt_...). Îl pui în data/matrix_config.json." },
                { step: "4", title: "Config pe PC", desc: "În data/telegram_bridge.json: matrix_enabled:true, matrix_homeserver, matrix_room_id, matrix_allowed_users:[@tu:tchncs.de]. Repornește puntea." },
              ].map(({ step, title, desc }) => (
                <div key={step} className="flex gap-3 bg-surface rounded-lg border border-surface-border p-3">
                  <div className="w-6 h-6 rounded-full bg-sky-600/20 border border-sky-500/40 flex items-center justify-center flex-shrink-0 mt-0.5">
                    <span className="text-[11px] font-bold text-sky-400">{step}</span>
                  </div>
                  <div className="space-y-0.5">
                    <div className="text-xs font-semibold text-slate-200">{title}</div>
                    <div className="text-[11px] text-slate-400 leading-relaxed">{desc}</div>
                  </div>
                </div>
              ))}
            </div>
            <Tip>
              Pași complet detaliați în <code>docs/TELEGRAM_BRIDGE.md</code>. La pornire îți trimite
              „🤖 Punte Matrix pornită" în cameră; apoi <code>/ajutor</code> merge la fel ca pe Telegram.
            </Tip>
          </SubSection>
        </Section>

        {/* ── 16. ELIMINAT / DEPRECATED ── */}
        <Section id="removed" title="16. Ce a fost eliminat sau e dormant">
          <SubSection title="Eliminat (nu mai există în UI / cod activ)">
            <div className="space-y-1 text-xs">
              <KV k="Sync MT5 + sursa „Bot”" v="A doua evidență a rezultatelor (diverga de MT5) — acum totul vine din MT5" />
              <KV k="Selector de profil" v="Un singur profil „standard”; Profil nou / Șterge scoase (fișierele vechi rămân pe disc)" />
              <KV k="Frecvența estimată + -DD% estimat" v="Înlocuite de Ritmul de tranzacționare (real, pe engine)" />
              <KV k="BotStatusBar / AiStatusBar / toggle-uri autostart din NavBar" v="Înlocuite de cardurile de engine (status + Start/Stop + autostart)" />
              <KV k="Câmpul Expire bars" v="Fix 4 bare pe toate sesiunile" />
              <KV k="ADX D1 (criteriu)" v="Scos din UI" />
              <KV k="Scara R pe criterii (sesiuni live)" v="Înlocuită de nivelurile fixe 2R / 3R / 4R" />
              <KV k="Roluri Quant / Avocatul Diavolului" v="Scoase din cod (prompturi, apeluri, config, UI)" />
              <KV k="Surse AI în afară de Ollama + Gemini" v="Scoase din config (cheile păstrate local)" />
              <KV k="„Izolat” la piețele AI" v="Înlocuit de modul Observație" />
              <KV k="Protecția capitalului din profil" v="Mutată în Setări Globale (valorile copiate exact)" />
            </div>
          </SubSection>
          <SubSection title="Dormant (cod păstrat, forțat oprit)" defaultOpen={false}>
            <div className="space-y-1 text-xs">
              <KV k="Mod Inteligent la știri" v="Forțat OFF (n-a plasat niciun ordin; fără date „actual” se comporta ca protecția standard). Testat în test_news_protection" />
              <KV k="Consilii multiple (consens)" v="Forțat OFF în AI Engine și în filtrul AI; codul consensus / orchestrator rămâne testat" />
              <KV k="Body Strength" v="Funcțional în backend pentru profile vechi, oprit implicit" />
            </div>
          </SubSection>
        </Section>

        {/* Footer */}
        <div className="border-t border-surface-border pt-6 text-center text-xs text-slate-600 space-y-1">
          <p>No Trading — Ghid intern · Ultima actualizare: {new Date().toLocaleDateString("ro-RO")}</p>
          <p className="text-slate-700">
            Nicio modificare la fișierele <code>strategy/</code>, <code>engine/</code> sau <code>live/</code>
            nu este necesară pentru funcționarea UI.
          </p>
        </div>
      </div>
    </div>
  );
}
