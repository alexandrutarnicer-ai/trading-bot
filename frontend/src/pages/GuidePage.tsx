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

// ── Architecture Diagram ──────────────────────────────────────────────────────

function ArchDiagram() {
  return (
    <div className="bg-surface rounded-xl border border-surface-border p-4 overflow-x-auto">
      <svg viewBox="0 0 720 260" className="w-full max-w-2xl mx-auto" style={{ minWidth: 480 }}>
        {/* MT5 */}
        <rect x="10" y="90" width="120" height="50" rx="8" fill="#1e293b" stroke="#3b82f6" strokeWidth="1.5" />
        <text x="70" y="111" textAnchor="middle" fill="#93c5fd" fontSize="11" fontWeight="600">MetaTrader 5</text>
        <text x="70" y="127" textAnchor="middle" fill="#64748b" fontSize="9">DEMO / LIVE</text>

        {/* Arrow MT5 → live session */}
        <path d="M 130 115 L 180 115" stroke="#3b82f6" strokeWidth="1.5" markerEnd="url(#arrowBlue)" fill="none" />
        <text x="155" y="108" textAnchor="middle" fill="#64748b" fontSize="8">bare OHLC</text>

        {/* Live Session */}
        <rect x="180" y="70" width="140" height="90" rx="8" fill="#1e293b" stroke="#22d3ee" strokeWidth="1.5" />
        <text x="250" y="93" textAnchor="middle" fill="#67e8f9" fontSize="11" fontWeight="600">signal_generator</text>
        <text x="250" y="108" textAnchor="middle" fill="#64748b" fontSize="9">_check_signals()</text>
        <text x="250" y="120" textAnchor="middle" fill="#64748b" fontSize="9">_update_outcomes()</text>
        <text x="250" y="132" textAnchor="middle" fill="#64748b" fontSize="9">_place_order()</text>
        <text x="250" y="149" textAnchor="middle" fill="#475569" fontSize="8">sessions 1–20</text>

        {/* Arrow live → MT5 (orders) */}
        <path d="M 180 100 Q 155 65 130 100" stroke="#f59e0b" strokeWidth="1.5" markerEnd="url(#arrowYellow)" fill="none" />
        <text x="142" y="72" textAnchor="middle" fill="#f59e0b" fontSize="8">ordine</text>

        {/* Arrow live → CSV */}
        <path d="M 320 115 L 380 115" stroke="#22d3ee" strokeWidth="1.5" markerEnd="url(#arrowCyan)" fill="none" />
        <text x="350" y="108" textAnchor="middle" fill="#64748b" fontSize="8">signals + outcomes</text>

        {/* CSV Storage */}
        <rect x="380" y="85" width="130" height="60" rx="8" fill="#1e293b" stroke="#475569" strokeWidth="1.5" />
        <text x="445" y="107" textAnchor="middle" fill="#94a3b8" fontSize="11" fontWeight="600">CSV Storage</text>
        <text x="445" y="122" textAnchor="middle" fill="#64748b" fontSize="9">signals.csv</text>
        <text x="445" y="135" textAnchor="middle" fill="#64748b" fontSize="9">outcomes.csv</text>

        {/* Arrow CSV → API */}
        <path d="M 510 115 L 560 115" stroke="#475569" strokeWidth="1.5" markerEnd="url(#arrowGray)" fill="none" />

        {/* API */}
        <rect x="560" y="90" width="100" height="50" rx="8" fill="#1e293b" stroke="#a855f7" strokeWidth="1.5" />
        <text x="610" y="111" textAnchor="middle" fill="#d8b4fe" fontSize="11" fontWeight="600">FastAPI</text>
        <text x="610" y="127" textAnchor="middle" fill="#64748b" fontSize="9">port 8000</text>

        {/* Arrow API → Frontend */}
        <path d="M 610 90 L 610 55" stroke="#a855f7" strokeWidth="1.5" markerEnd="url(#arrowPurple)" fill="none" />

        {/* Frontend */}
        <rect x="555" y="10" width="110" height="40" rx="8" fill="#1e293b" stroke="#a855f7" strokeWidth="1.5" />
        <text x="610" y="28" textAnchor="middle" fill="#d8b4fe" fontSize="11" fontWeight="600">React UI</text>
        <text x="610" y="43" textAnchor="middle" fill="#64748b" fontSize="9">port 5173</text>

        {/* Arrow MT5 → API direct (mt5status) */}
        <path d="M 70 90 Q 70 20 560 20" stroke="#3b82f6" strokeWidth="1" strokeDasharray="4 3" fill="none" markerEnd="url(#arrowBlue)" />
        <text x="300" y="13" textAnchor="middle" fill="#3b82f6" fontSize="8">status / balance (direct)</text>

        {/* Labels below */}
        <text x="250" y="185" textAnchor="middle" fill="#334155" fontSize="9">run_all.py pornește S1–S20 ca subprocese</text>
        <text x="250" y="198" textAnchor="middle" fill="#334155" fontSize="9">news_guard.py rulează ca daemon thread</text>

        {/* Strategy box */}
        <rect x="180" y="210" width="140" height="40" rx="8" fill="#0f172a" stroke="#334155" strokeWidth="1" />
        <text x="250" y="228" textAnchor="middle" fill="#475569" fontSize="10" fontWeight="600">strategy/</text>
        <text x="250" y="243" textAnchor="middle" fill="#334155" fontSize="9">preparation · signals · structure</text>
        <path d="M 250 210 L 250 160" stroke="#334155" strokeWidth="1" strokeDasharray="3 2" fill="none" />

        {/* Arrow markers */}
        <defs>
          <marker id="arrowBlue" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
            <path d="M 0 0 L 6 3 L 0 6 Z" fill="#3b82f6" />
          </marker>
          <marker id="arrowYellow" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
            <path d="M 0 0 L 6 3 L 0 6 Z" fill="#f59e0b" />
          </marker>
          <marker id="arrowCyan" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
            <path d="M 0 0 L 6 3 L 0 6 Z" fill="#22d3ee" />
          </marker>
          <marker id="arrowGray" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
            <path d="M 0 0 L 6 3 L 0 6 Z" fill="#475569" />
          </marker>
          <marker id="arrowPurple" markerWidth="6" markerHeight="6" refX="3" refY="3" orient="auto">
            <path d="M 0 0 L 6 3 L 0 6 Z" fill="#a855f7" />
          </marker>
        </defs>
      </svg>
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
        <text x="350" y="155" textAnchor="middle" fill="#475569" fontSize="9" fontStyle="italic">Criterii opționale: RSI · EMA alignment · Body Strength → cresc R/R (2.5R → 5.5R)</text>

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

// ── R-Ladder Diagram ──────────────────────────────────────────────────────────

function RLadderDiagram() {
  return (
    <div className="bg-surface rounded-xl border border-surface-border p-4">
      <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-3">
        Exemplu R-Ladder (configurare implicită)
      </div>
      <div className="grid grid-cols-4 gap-2">
        {[
          { tier: "Base", r: "2.5R", crit: "0 criterii opt.", color: "border-slate-500 text-slate-300" },
          { tier: "Mid",  r: "3.5R", crit: "≥ 1 criteriu",   color: "border-blue-500 text-blue-300" },
          { tier: "Top",  r: "4.5R", crit: "≥ 2 criterii",   color: "border-profit text-profit" },
          { tier: "Max",  r: "5.5R", crit: "≥ 3 criterii",   color: "border-yellow-400 text-yellow-300" },
        ].map(({ tier, r, crit, color }) => (
          <div key={tier} className={`border rounded-lg p-3 text-center ${color}`}>
            <div className="text-[10px] text-slate-500 uppercase tracking-wider">{tier}</div>
            <div className="text-lg font-mono font-bold mt-1">{r}</div>
            <div className="text-[10px] text-slate-500 mt-1">{crit}</div>
          </div>
        ))}
      </div>
      <div className="mt-3 text-xs text-slate-500">
        <strong className="text-slate-400">Criterii opționale:</strong>{" "}
        RSI în range configurabil · EMA8 &gt; EMA20 &gt; EMA50 (LONG) · Body strength &gt; ATR × factor
      </div>
    </div>
  );
}

// ── Week Stats Diagram ────────────────────────────────────────────────────────

function WeekStatsDiagram() {
  return (
    <div className="bg-surface rounded-xl border border-surface-border p-4">
      <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-3">
        Structura Indice Săptămânal
      </div>
      <div className="grid grid-cols-3 text-[10px] text-slate-500 mb-2 px-2">
        <span>Metric</span>
        <span className="text-center">Săpt. curentă</span>
        <span className="text-center">Săpt. anterioară</span>
      </div>
      {[
        { label: "Trades",   cur: "12",       prev: "8",       curColor: "text-white", prevColor: "text-slate-500" },
        { label: "Câștiguri",cur: "7",        prev: "5",       curColor: "text-profit", prevColor: "text-slate-500" },
        { label: "Pierderi", cur: "5",        prev: "3",       curColor: "text-loss",  prevColor: "text-slate-500" },
        { label: "Win Rate", cur: "58.3%",    prev: "62.5%",   curColor: "text-white", prevColor: "text-slate-500" },
        { label: "Total R",  cur: "+1.250R",  prev: "+0.875R", curColor: "text-profit", prevColor: "text-slate-500" },
        { label: "-DD max",   cur: "-2.0%",    prev: "-1.0%",   curColor: "text-loss",  prevColor: "text-slate-500" },
      ].map(({ label, cur, prev, curColor, prevColor }) => (
        <div key={label} className="grid grid-cols-3 items-center py-1.5 px-2 border-t border-surface-border/30">
          <span className="text-[11px] text-slate-400">{label}</span>
          <span className={`text-center text-[11px] font-mono font-semibold ${curColor}`}>{cur}</span>
          <span className={`text-center text-[11px] font-mono ${prevColor}`}>{prev}</span>
        </div>
      ))}
      <div className="mt-2 text-[10px] text-slate-600">
        ▲ TrendingUp = mai bine față de săptămâna trecută · ▼ TrendingDown = mai rău · — egal
      </div>
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
  { id: "overview",      label: "1. Prezentare generală" },
  { id: "dashboard",     label: "2. Dashboard" },
  { id: "profile",       label: "3. Profile & Sesiuni" },
  { id: "audit",         label: "4. Audit & Backteste" },
  { id: "strategy",      label: "5. Strategia" },
  { id: "risk",          label: "6. Gestionare risc" },
  { id: "config",        label: "7. Configurare avansată" },
  { id: "signals",       label: "8. Semnale & Ordine" },
  { id: "notifications", label: "9. Notificări" },
  { id: "reports",       label: "10. Rapoarte" },
  { id: "ai-engine",     label: "11. AI Engine" },
  { id: "live",          label: "12. Cont live" },
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
            <h1 className="text-lg font-bold text-white">Ghid Trading Bot</h1>
            <p className="text-xs text-slate-500">Documentație completă — interfață, strategie și configurare</p>
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
          <SubSection title="Ce este botul?">
            <p>
              Botul este un sistem automatizat de trading bazat pe strategia <strong className="text-white">pullback-in-trend</strong>.
              Detectează structuri de piață în timp real folosind date MT5, plasează ordine pending (BUY_STOP / SELL_STOP)
              în MetaTrader 5 și monitorizează continuu evoluția lor.
            </p>
            <p>
              Rulează <strong className="text-white">20 de sesiuni</strong> independente simultan, fiecare pe o piață
              diferită (EURUSD, BTCUSD, GER40 etc.) cu timeframe-uri și parametri proprii.
              Fiecare sesiune are propriul proces Python separat, fișiere de stare și log propriu.
            </p>
            <Note>
              Botul <strong>nu</strong> modifică niciodată fișierele de strategie sau de configurare în timp ce rulează.
              Toate schimbările intră în vigoare la bara următoare (max 15 min pentru M15).
            </Note>
          </SubSection>

          <SubSection title="Arhitectura sistemului">
            <ArchDiagram />
            <div className="grid grid-cols-2 gap-3 text-xs">
              <div className="space-y-1">
                <KV k="MT5 → Bot" v="Bare OHLC live (M15/H1) prin API Python" />
                <KV k="Bot → MT5" v="Ordine BUY_STOP / SELL_STOP via mt5.order_send()" />
                <KV k="Bot → CSV" v="signals.csv + outcomes.csv per sesiune" />
              </div>
              <div className="space-y-1">
                <KV k="API port" v="8000 (FastAPI/uvicorn)" />
                <KV k="UI port" v="5173 (React/Vite)" />
                <KV k="Poll interval" v="15s sesiuni, 2s backteste în curs" />
              </div>
            </div>
          </SubSection>

          <SubSection title="Pornire rapidă">
            <p>Cel mai simplu mod de a porni tot:</p>
            <div className="bg-surface rounded-lg border border-surface-border p-3 font-mono text-xs text-slate-300 space-y-1">
              <div><span className="text-slate-600"># Dublu-click pe:</span></div>
              <div className="text-white">start_ui.bat</div>
              <div className="text-slate-600 mt-2"># Sau manual:</div>
              <div>python api/main.py  <span className="text-slate-600"># API pe portul 8000</span></div>
              <div>cd frontend &amp;&amp; npm run dev  <span className="text-slate-600"># UI pe portul 5173</span></div>
            </div>
            <Warn>MT5 trebuie să fie <strong>deschis și conectat</strong> pe cont DEMO înainte de a porni botul.
              Dacă MT5 e deconectat, bara galbenă "Algo Trading dezactivat" apare în Dashboard.</Warn>
          </SubSection>
        </Section>

        {/* ── 2. DASHBOARD ── */}
        <Section id="dashboard" title="2. Dashboard">
          <SubSection title="Header — Cont MT5 și Status Bot">
            <p>
              Zona de sus afișează informații live despre contul MT5 și starea botului:
            </p>
            <div className="space-y-2">
              <KV k="Profil activ" v="Profilul selectat curent (ex: Standard Profile)" />
              <KV k="Cont" v="Numărul contului MT5 conectat" />
              <KV k="Balance" v="Soldul contului (fără tranzacții deschise)" />
              <KV k="Equity" v="Soldul real (balance ± profit/pierdere deschisă)" vColor="text-profit" />
              <KV k="Bot Status" v="Verde pulsant = activ; gri = oprit cu ora ultimei opriri" />
            </div>
            <Note>
              <strong>Equity &gt; Balance</strong> = tranzacții deschise în profit.
              <strong> Equity &lt; Balance</strong> = tranzacții deschise în pierdere.
              Equity se afișează în <span className="text-profit">verde</span> sau <span className="text-loss">roșu</span> față de balance.
            </Note>
          </SubSection>

          <SubSection title="Banner Algo Trading dezactivat">
            <p>
              Dacă apare un banner galben <strong className="text-warn">⚠ Algo Trading dezactivat în MT5!</strong>,
              înseamnă că butonul <em>AutoTrading</em> din MT5 este dezactivat.
              Botul detectează semnale în continuare, <strong className="text-white">dar nu plasează ordine</strong>.
            </p>
            <Tip>Activează butonul verde "Algo Trading" din bara de sus a MetaTrader 5 (toolbar).</Tip>
          </SubSection>

          <SubSection title="Carduri Frecvență Estimată">
            <p>
              Deasupra grilei de sesiuni, două carduri afișează frecvența estimată de trading:
            </p>
            <div className="grid grid-cols-2 gap-3 text-xs">
              <div className="bg-surface rounded-lg border border-surface-border p-3 text-center">
                <div className="text-[10px] text-slate-500 uppercase mb-1">Estimat / săptămână</div>
                <div className="text-xl font-mono font-bold text-white">~11.5 <span className="text-sm text-slate-400">trades</span></div>
              </div>
              <div className="bg-surface rounded-lg border border-surface-border p-3 text-center">
                <div className="text-[10px] text-slate-500 uppercase mb-1">Estimat / lună</div>
                <div className="text-xl font-mono font-bold text-white">~50 <span className="text-sm text-slate-400">trades</span></div>
              </div>
            </div>
            <p className="text-xs text-slate-400 mt-2">
              Calculul se bazează pe cele mai recente backteste finalizate din Audit, pe sesiunile
              cu <code className="bg-surface-border/40 px-1 rounded">execute_trades: true</code>.
              Sesiunile pe pauză și cele de observație (OBS) sunt excluse automat.
            </p>
            <div className="bg-warn/5 border border-warn/20 rounded-lg p-3 mt-2 text-xs space-y-1.5">
              <p className="text-warn font-medium">Badge „X fără date" — buton de acțiune</p>
              <p className="text-slate-400">
                Când unele sesiuni nu au backtest recent, apare un badge portocaliu{" "}
                <Badge color="bg-warn/20 text-warn" label="▶ 2 fără date" />{" "}
                în cardul Estimat / săptămână.
              </p>
              <p className="text-slate-400">
                <strong className="text-slate-300">Click pe badge</strong> → pornește automat backtestele lipsă
                (range 5 ani, toți parametrii din profilul activ). Rezultatele apar în tab-ul Audit.
                Badge-ul dispare după ce backtestele se finalizează și frecvența se actualizează.
              </p>
              <p className="text-slate-400">
                Butonul Refresh <span className="font-mono text-slate-300">↻</span> din header invalidează
                toate query-urile, inclusiv frecvența estimată — folosit pentru actualizare manuală imediată.
              </p>
            </div>
          </SubSection>

          <SubSection title="Grila Sesiuni">
            <p>
              Fiecare card de sesiune afișează:
            </p>
            <div className="grid grid-cols-2 gap-x-6 gap-y-1.5 text-xs">
              <KV k="Label" v="Ex: S3 — BTCUSD M15 BOTH" />
              <KV k="Badge LIVE/OBS" v="LIVE = ordine plasate real; OBS = observație" />
              <KV k="Dot verde/galben" v="Verde = running; galben = pe pauză" />
              <KV k="Badge PAUZA" v="Sesiunea nu mai deschide poziții noi" />
              <KV k="Semnale azi" v="Numărul de setup-uri detectate azi" />
              <KV k="Total semnale" v="Cumulate de la pornirea sesiunii" />
              <KV k="Win Rate %" v="(Câștiguri / Total tranzacții) × 100" />
              <KV k="TF + Direcție" v="Ex: M15+M30 · BOTH (LONG și SHORT)" />
            </div>
            <p className="mt-2 text-xs text-slate-400">
              <strong className="text-slate-300">Butonul ⏸/▶</strong> în colțul dreapta-sus al cardului pune/reia sesiunea.
              Efectul intră la bara următoare — nu este nevoie de restart bot.
            </p>
          </SubSection>

          <SubSection title="Signal Feed">
            <p>
              Panoul din stânga-jos listează semnalele recente. Implicit afișează <strong className="text-white">toate sesiunile</strong> (butonul <Badge color="bg-blue-500/20 text-blue-300" label="ALL" /> activ). Poți selecta o sesiune individuală din rândul de butoane de mai jos.
            </p>
            <div className="space-y-1.5 text-xs">
              <div className="flex items-center gap-3">
                <Badge color="bg-profit/20 text-profit" label="LONG" />
                <span className="text-slate-400">sau</span>
                <Badge color="bg-loss/20 text-loss" label="SHORT" />
                <span className="text-slate-400">— direcția tranzacției</span>
              </div>
              <KV k="Simbol + Timp" v="Ex: EURUSD · 14:30" />
              <KV k="Entry → TP" v="Prețurile de intrare și ieșire" />
              <KV k="+3.5R TP" v="Tranzacție câștigată cu 3.5× riscul asumat" vColor="text-profit" />
              <KV k="-1R SL" v="Tranzacție pierdută la stop loss" vColor="text-loss" />
              <KV k="+175 USD" v="Profit în USD (dacă MT5 conectat și execute=true)" vColor="text-profit" />
            </div>
            <Note>
              În modul ALL, suma USD nu se afișează (nu există un singur capital%). Suma în USD se calculează din: <code className="text-blue-300">balance × capital% × 1% risc × R</code> — disponibilă doar când e selectată o sesiune individuală.
            </Note>
          </SubSection>

          <SubSection title="Grafic Performanță (R cumulat)">
            <p>
              Graficul din dreapta-jos arată evoluția <strong className="text-white">R cumulat</strong> pentru toate sesiunile active.
              Linia <span className="text-profit">verde</span> = profit total acumulat. Linia <span className="text-loss">roșie</span> = pierdere.
            </p>
            <p className="text-xs text-slate-400">
              R = unitate de risc. Dacă riscai 50 USD/trade și ai +5R, ai câștigat ~250 USD total.
              Graficul combină toate sesiunile sortate cronologic după <code className="text-blue-300">exit_time</code>.
            </p>
          </SubSection>

          <SubSection title="Indice Periodic (Săptămânal / Lunar)">
            <WeekStatsDiagram />
            <div className="mt-3 space-y-1.5 text-xs">
              <KV k="Tab Săptămână / Lună" v="Comutare între intervalul curent și cel precedent" />
              <KV k="Trades" v="Tranzacții cu status final (TP/SL/vineri/news)" />
              <KV k="Câștiguri/Pierderi" v="Trades cu result_r > 0 / result_r < 0" />
              <KV k="Total R" v="Suma tuturor result_r din interval" />
              <KV k="P&L USD" v="Suma pnl_usd (profit real MT5) — apare doar când există date" />
              <KV k="-DD max R" v="Cel mai adânc jgheab de la peak-ul R al perioadei" vColor="text-loss" />
            </div>
            <Tip>
              Tab-ul Lună oferă o perspectivă mai stabilă decât săptămâna — fluctuațiile săptămânale
              sunt normale. P&L USD apare doar pentru sesiunile cu execute_trades=True care au ordine
              închise prin MT5 (câmpul pnl_usd din outcomes.csv).
            </Tip>
          </SubSection>

          <SubSection title="P&L Real MT5 și Comisioane">
            <p>
              Sub grila de statistici, două carduri secundare afișează date financiare agregate:
            </p>
            <div className="space-y-2 text-xs mt-2">
              <div className="bg-surface rounded-lg border border-surface-border p-3 space-y-1">
                <div className="text-[11px] font-semibold text-slate-300">P&L Real MT5</div>
                <div className="text-slate-400">
                  <code className="text-blue-300">equity curentă MT5 − capital inițial din profil</code>
                  {" "}— sursa de adevăr absolut. Include toate tranzacțiile, comisioane, swap și cele fără date în bot.
                </div>
                <Tip>Setează <strong className="text-white">Capital Inițial</strong> corect în Profile înainte de prima pornire — sau folosește butonul <Badge color="bg-blue-600/20 text-blue-400" label="↓ Import din MT5" /> pentru a prelua equity curentă.</Tip>
              </div>
              <div className="bg-surface rounded-lg border border-surface-border p-3 space-y-1">
                <div className="text-[11px] font-semibold text-slate-300">Comisioane + Swap</div>
                <div className="text-slate-400">Suma comisioanelor și swap-ului din <code className="text-blue-300">outcomes.csv</code>. Detalii complete în tab-ul Rapoarte → Comisioane.</div>
              </div>
            </div>
            <Note>
              Sesiunile de observație (<Badge color="bg-surface-border text-slate-500" label="OBS" />) sunt excluse din toate agregările. Excepție: dacă o sesiune a avut tranzacții reale MT5 (<code className="text-blue-300">pnl_usd ≠ 0</code>) și ulterior a fost oprită din execuție, tranzacțiile istorice rămân vizibile în statistici. MT5 este sursa de adevăr — dacă există <code className="text-blue-300">pnl_usd</code> real, trade-ul a fost executat indiferent de setarea curentă a profilului.
            </Note>
          </SubSection>

          <SubSection title="Statistici Totale (TradingStatsPanel)">
            <p>Carduri care afișează agregatul tuturor sesiunilor:</p>
            <div className="grid grid-cols-2 gap-3 text-xs">
              <KV k="Total Semnale" v="Toate setup-urile detectate" />
              <KV k="Total Trades" v="Tranzacții cu outcome final" />
              <KV k="Câștiguri" v="Numărul TP-urilor + ▲/▼ azi vs ieri" vColor="text-profit" />
              <KV k="Pierderi" v="Numărul SL-urilor + ▲/▼ azi vs ieri" vColor="text-loss" />
              <KV k="P&L USD" v="Suma P&L real azi + ieri (din MT5)" vColor="text-profit" />
            </div>
            <p className="text-xs text-slate-400 mt-2">
              Fiecare card numeric afișează și <em>X azi</em> față de <em>ieri</em> cu indicator trend ▲/▼.
              Câștigurile și Pierderile au acum trend separat (câștiguri azi vs ieri, pierderi azi vs ieri)
              — câmpurile <code className="text-blue-300">wins_today</code>, <code className="text-blue-300">wins_yesterday</code>, <code className="text-blue-300">losses_today</code>, <code className="text-blue-300">losses_yesterday</code> din <code className="text-blue-300">SessionStatus</code>.
              Cardul P&L USD apare doar când există date reale MT5 (execute_trades=True + ordine închise).
              Click pe "Total Semnale" sau "Total Trades" expandează breakdownul per sesiune.
            </p>
          </SubSection>

          <SubSection title="Carduri frecvență estimată + -DD%">
            <p>Deasupra grilei de sesiuni, 3 carduri rezumă performanța estimată:</p>
            <div className="space-y-1.5 text-xs">
              <KV k="Estimat / săptămână" v="Trades/săpt din backtestele active ale sesiunilor LIVE" />
              <KV k="Estimat / lună" v="Trades/lună (× 30.44 / 7 din estimatul săptămânal)" />
              <KV k="-DD% mediu estimat" v="Media max_dd din backtestele sesiunilor active" vColor="text-loss" />
            </div>
            <div className="mt-2 space-y-1 text-xs text-slate-400">
              <p>Sesiunile excluse din calcul: pe pauză + execute_trades=False (observație).</p>
              <p>Badge portocaliu → backtest lipsă pentru unele sesiuni. Click → lansează automat backtestele lipsă (5 ani).</p>
            </div>
            <Note>
              -DD% mediu estimat reflectă scăderea maximă procentuală din backteste, nu din trading-ul live.
              Poate fi diferit de experiența reală dacă condițiile de piață s-au schimbat față de perioada testată.
            </Note>
          </SubSection>

          <SubSection title="P&L USD pe cardurile sesiunilor" defaultOpen={false}>
            <p>
              Fiecare card de sesiune din grila Dashboard afișează (când există date reale MT5):
            </p>
            <div className="space-y-1 text-xs">
              <KV k="+150.25 USD azi" vColor="text-profit" v="Suma profit/pierdere azi (ordine MT5 închise)" />
              <KV k="-50.00 ieri" vColor="text-loss" v="Suma profit/pierdere ieri" />
            </div>
            <Note>
              Apare doar dacă sesiunea are execute_trades=True și cel puțin un ordin MT5 închis (TP/SL/vineri/știri)
              cu câmpul pnl_usd populat. Sesiunile de observație (execute=false) nu afișează P&L.
            </Note>
          </SubSection>

          <SubSection title="Widget Top 5 Piețe" defaultOpen={false}>
            <p>
              Card în josul panoului Dashboard care afișează cele mai profitabile 5 piețe după R cumulat,
              cu filtre de perioadă.
            </p>
            <div className="grid grid-cols-2 gap-1.5 text-xs">
              <KV k="Azi" v="Tranzacții închise în ziua curentă" />
              <KV k="Săpt" v="Tranzacții din săptămâna curentă (luni → azi)" />
              <KV k="Lună" v="Tranzacții din luna curentă (1 → azi)" />
              <KV k="Tot" v="Toate tranzacțiile istorice" />
            </div>
            <p className="text-xs text-slate-400 mt-1">
              Per piață: simbolul, număr trades, win rate%, R cumulat, P&L USD.
              Sortat descrescător după Total R. P&L USD apare doar pentru sesiunile cu execute_trades=True.
              Se actualizează la 30 secunde.
            </p>
          </SubSection>
        </Section>

        {/* ── 3. PROFILE & SESIUNI ── */}
        <Section id="profile" title="3. Profile & Sesiuni">
          <SubSection title="Ce este un Profil?">
            <p>
              Un profil grupează configurarea tuturor sesiunilor active. Poți crea multiple profile
              (ex: "Conservator", "Agresiv") și activa unul la pornirea botului.
            </p>
            <div className="space-y-1 text-xs">
              <KV k="standard" v="Profilul implicit — protejat la ștergere" />
              <KV k="Profil activ" v="Cel selectat la Start Bot — aplicat tuturor sesiunilor" />
              <KV k="Salvare" v="Butonul Salvează apare atât sus cât și jos în listă" />
            </div>
            <Note>
              Modificările unui profil nu se aplică botului în timp real dacă acesta rulează deja.
              Trebuie să oprești și repornești botul cu noul profil.
            </Note>
          </SubSection>

          <SubSection title="Configurarea unei Sesiuni">
            <p>Fiecare sesiune în profil are secțiunile:</p>
            <div className="space-y-3">
              <div>
                <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1.5">Parametri de bază</div>
                <div className="grid grid-cols-2 gap-1.5 text-xs">
                  <KV k="Piețe" v="Ex: EURUSD, GBPUSD (multi-select)" />
                  <KV k="Entry TF" v="M15 sau H1 (timeframe intrare)" />
                  <KV k="Trend TF" v="M30 sau D1 (timeframe trend)" />
                  <KV k="Direcție" v="LONG / BOTH (LONG+SHORT)" />
                  <KV k="Pullback window" v="Câte bare caută structura (6–8)" />
                  <KV k="Expire bars" v="Bare max fără trigger (4 = 1h pe M15)" />
                </div>
              </div>

              <div>
                <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1.5">Ore sesiune</div>
                <div className="grid grid-cols-2 gap-1.5 text-xs">
                  <KV k="Non-stop" v="Session start=0, end=24 (fără restricție)" />
                  <KV k="Skip ore" v="Ex: [15, 16] = sari orele de volatilitate" />
                  <KV k="Skip zile" v="Ex: [0] = sari Lunea (0=Luni, 6=Duminică)" />
                </div>
              </div>

              <div>
                <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1.5">Capital & Risc</div>
                <div className="grid grid-cols-2 gap-1.5 text-xs">
                  <KV k="Account fraction" v="0.125 = 12.5% din equity MT5 alocat sesiunii" />
                  <KV k="Risk % per tier" v="Procent din capital riscat per trade (ex: 1%)" />
                </div>
                <Tip>
                  Breakdown live sub câmpul account_fraction: <em>$capital sesiune · $X/piață + risc/trade ~$Y</em>
                </Tip>
              </div>
            </div>
          </SubSection>

          <SubSection title="Criterii opționale și R-Ladder">
            <RLadderDiagram />
            <div className="mt-3 space-y-2 text-xs">
              <p>
                Criteriile opționale cresc R/R-ul tranzacției. Cu cât mai multe criterii sunt îndeplinite,
                cu atât R-ul țintit este mai mare.
              </p>
              <div className="grid grid-cols-2 gap-1.5">
                <KV k="RSI" v="RSI în range specificat (ex: 40–65 LONG)" />
                <KV k="EMA Alignment" v="EMA8 > EMA20 > EMA50 (LONG) sau invers" />
                <KV k="Body Strength" v="Corp lumânare > factor × ATR (dezactivat implicit)" />
              </div>
            </div>
          </SubSection>

          <SubSection title="Break-Even (BE)" defaultOpen={false}>
            <p>Mecanism opțional care mută SL-ul pe profit parțial:</p>
            <div className="space-y-1.5 text-xs">
              <KV k="BE Trigger %" v="La câte % din distanța SL→TP se activează Faza 1" />
              <KV k="BE Lock 1 %" v="SL se mută la X% din SL original (ex: 30% = SL la entry -30%)" />
              <KV k="Faza 2" v="Opțional — trailing SL când prețul intră în zona TP" />
              <KV k="BE Lock 2 %" v="SL la X% din distanța originală (ex: 50%)" />
            </div>
            <Warn>Break-Even este dezactivat implicit. Activarea schimbă baselines — rulează backtest înainte.</Warn>
          </SubSection>

          <SubSection title="Protecție știri (News Guard)" defaultOpen={false}>
            <p>
              Când activat, sesiunea intră automat pe pauză în jurul evenimentelor economice importante.
              Pozițiile deschise sunt închise, ordinele pending sunt anulate.
            </p>
            <div className="grid grid-cols-2 gap-1.5 text-xs">
              <KV k="Impact level" v="1 = Scăzut, 2 = Mediu, 3 = Mare (High)" />
              <KV k="Pre minutes" v="Minute înainte de eveniment pentru pauză" />
              <KV k="Post minutes" v="Minute după eveniment pentru reluare" />
            </div>
            <Note>
              News Guard polleaza ForexFactory la fiecare 5 minute. Nu necesită API key.
            </Note>
          </SubSection>

          <SubSection title="Mod Inteligent (Smart News Protection)" defaultOpen={false}>
            <p>
              Extensie a protecției la știri — disponibil doar când „Pauză automată la știri" este activat.
              În loc să închidă toate pozițiile, botul analizează sentimentul știrii și decide direcția.
            </p>
            <div className="space-y-2 text-xs">
              <div>
                <p className="font-medium text-white mb-1">Logică sentiment:</p>
                <div className="grid grid-cols-2 gap-1 text-slate-300">
                  <span>actual &gt; forecast</span><span className="text-profit">→ bullish pentru valuta raportoare</span>
                  <span>actual &lt; forecast</span><span className="text-loss">→ bearish pentru valuta raportoare</span>
                  <span>actual = null</span><span className="text-slate-500">→ eveniment nelansat, skip</span>
                </div>
              </div>
              <div>
                <p className="font-medium text-white mb-1">Acțiuni la știre negativă (ex: USD bearish):</p>
                <div className="grid grid-cols-1 gap-0.5">
                  <KV k="LONG EURUSD deschis" v="Menținut (USD slab → EURUSD sus)" vColor="text-profit" />
                  <KV k="SHORT EURUSD deschis" v="Închis imediat (contra sentimentului)" vColor="text-loss" />
                  <KV k="Nicio poziție" v="Plasează BUY_STOP pe EURUSD (risc 1.5× base)" />
                </div>
              </div>
              <div>
                <p className="font-medium text-white mb-1">Trailing SL pentru ordinele din știri:</p>
                <div className="grid grid-cols-2 gap-1">
                  <KV k="La 3R profit" v="SL → 1R față de TP (blochează profit)" />
                  <KV k="La 4R profit" v="SL → 2R față de TP (mai mult room)" />
                </div>
              </div>
            </div>
            <Note>
              Parsarea sentimentului este simplificată. Nu funcționează corect pentru indicatori inversați
              (șomaj, CPI în context dovish/hawkish). Testează întotdeauna pe cont DEMO înainte de live.
              Ordinele de știri sunt marcate „SN" și urmărite separat față de semnalele pullback normale.
            </Note>
          </SubSection>

          <SubSection title="Protecție Capital (la nivel de profil)" defaultOpen={false}>
            <p>
              Funcție de protecție automată a contului, configurată la nivel de profil (nu per sesiune).
              Watchdog-ul API o verifică la fiecare 30 secunde cât botul rulează.
            </p>
            <div className="grid grid-cols-2 gap-1.5 text-xs">
              <KV k="Implicit" v="Dezactivat — nu afectează funcționarea normală" />
              <KV k="Prag implicit" v="70% din capitalul de start al profilului" />
              <KV k="Interval verificare" v="La fiecare 30 secunde (watchdog API)" />
              <KV k="Acțiune" v="Pauză automată toate sesiunile cu execute_trades=True" />
            </div>
            <p className="text-xs mt-1">
              Când equity MT5 scade sub prag → watchdog pune pe pauză toate sesiunile live active
              (cele cu execute_trades activat, care nu erau deja pe pauză). Sesiunile de observație
              și cele deja pe pauză nu sunt afectate.
            </p>
            <Note>
              Trimite notificare Telegram + UI la activare. Se dezactivează automat (flag resetat)
              dacă equity revine peste prag. Salvare individuală prin butonul „Salvează protecție"
              din secțiunea dedicată de deasupra listei de sesiuni.
            </Note>
          </SubSection>

          <SubSection title="Backtest Panel (în Profile)" defaultOpen={false}>
            <p>
              Fiecare sesiune din Profile are un panou de backtest cu:
            </p>
            <div className="space-y-1.5 text-xs">
              <KV k="Range date" v="1An / 3Ani / Tot / Custom" />
              <KV k="Capital inițial" v="Simulat în USD per sesiune" />
              <KV k="Capital per piață" v="Alocat automat (capital / n_piete)" />
              <KV k="Minim capital" v="Fiecare piață are un minim (ex: EURUSD min 150 USD)" />
            </div>
            <p className="text-xs text-slate-400 mt-1">
              Dacă datele CSV lipsesc, backtestul oferă descărcare automată din MT5.
              Jobul apare în tab-ul Audit cu status și rezultate.
            </p>
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
              <code className="text-blue-300 ml-1">skip_hours</code> din Profile → sesiune, apoi rulează un backtest nou
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
              <KV k="R-Ladder" v="R base/mid/top/max cu riscul % și pragurile de criterii" />
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
        <Section id="risk" title="6. Gestionare risc">
          <SubSection title="Calculul poziției">
            <div className="space-y-2 text-xs">
              <p>Formula pentru dimensiunea poziției:</p>
              <div className="bg-surface rounded-lg border border-surface-border p-3 font-mono text-xs space-y-1 text-slate-300">
                <div>risk_usd = equity_mt5 × account_fraction × risk_pct</div>
                <div>lots = risk_usd / (risk_dist_pips × pip_value_usd)</div>
              </div>
              <div className="space-y-1 mt-2">
                <KV k="equity_mt5" v="Equity real citit din MT5 la fiecare trade" />
                <KV k="account_fraction" v="Ex: 0.125 = 12.5% din equity alocat sesiunii" />
                <KV k="risk_pct" v="Ex: 0.01 = 1% din capital sesiunii riscat" />
                <KV k="lot minim" v="0.01 — tranzacțiile sub acest lot sunt respinse" />
              </div>
            </div>
            <Warn>
              Dacă equity × account_fraction × risk_pct nu acoperă 0.01 lot, trade-ul este sarit
              (apare ca <em>skipped_margin</em> în rezultatele backtest).
            </Warn>
          </SubSection>

          <SubSection title="Circuit Breaker" defaultOpen={false}>
            <p>
              Dacă o sesiune înregistrează <strong className="text-white">N pierderi consecutive</strong>
              într-o zi (default N=3), nu mai deschide poziții noi în acea zi.
            </p>
            <Tip>
              Circuit breaker resetat automat la miezul nopții (ziua nouă). Configurabil per sesiune din Profile.
            </Tip>
          </SubSection>

          <SubSection title="Corelare perechi" defaultOpen={false}>
            <p>
              Motor-ul de portofoliu previne deschiderea simultană a EURUSD și GBPUSD în aceeași direcție,
              deoarece sunt corelate pozitiv. Dacă EURUSD e deja deschis LONG, GBPUSD LONG este sarit.
            </p>
          </SubSection>

          <SubSection title="Vineri Close" defaultOpen={false}>
            <p>
              Vineri la ora configurată (<code className="text-blue-300">friday_close_hour</code>, default 20:00),
              toate pozițiile triggerate deschise sunt închise via <code className="text-blue-300">TRADE_ACTION_DEAL</code>.
              Ordinele pending neactivate rămân — vor expira natural sau la bara următoare.
            </p>
            <Note>Sesiunea BTC (BTCUSD) are vineri_close dezactivat — piața e deschisă în weekend.</Note>
          </SubSection>
        </Section>

        {/* ── 7. CONFIGURARE AVANSATĂ ── */}
        <Section id="config" title="7. Configurare avansată">
          <SubSection title="Start/Stop Bot din UI">
            <p>
              Butonul <strong className="text-white">Start Bot</strong> din header pornește
              <code className="text-blue-300 mx-1">run_all.py</code> care lansează toate sesiunile S1–S20
              ca subprocese independente.
            </p>
            <div className="space-y-1 text-xs">
              <KV k="La start" v="Se aplică profilul selectat; notificare Telegram trimisă" />
              <KV k="La stop" v="taskkill /F /T ucide toate subprocesele; notificare Telegram" />
              <KV k="Restart" v="Stop urmat de Start — sesiunile preiau starea din state.pkl" />
            </div>
            <Note>
              Dacă botul se oprește neașteptat (crash), watchdog-ul API detectează în 30s și trimite
              notificare Telegram <em>"Bot Trading oprit neașteptat!"</em> și curăță fișierele de stare.
            </Note>
          </SubSection>

          <SubSection title="Configurare Telegram" defaultOpen={false}>
            <p>
              Telegram trimite notificări pentru: semnal nou, ordin activat, TP, SL, vineri_close,
              news_close, start/stop bot, sesiune pauza/reluare, auto-pauza știri.
            </p>
            <div className="space-y-1 text-xs">
              <KV k="Token bot" v="De la @BotFather pe Telegram (format: 1234567890:ABCdef...)" />
              <KV k="Chat ID" v="ID-ul tău personal sau al unui grup (ex: -100123456789)" />
              <KV k="Test" v="Butonul 'Trimite mesaj de test' din Settings verifică conexiunea" />
            </div>
            <Note>
              Configurarea Telegram se face din Profile → secțiunea Settings (accordion jos).
              Credentials sunt stocate în <code className="text-blue-300">data/telegram_config.json</code>.
            </Note>
          </SubSection>

          <SubSection title="Autostart Windows" defaultOpen={false}>
            <p>
              Toggle-ul din NavBar activează/dezactivează pornirea automată a botului la login Windows.
              Creează două task-uri în Task Scheduler:
            </p>
            <div className="space-y-1 text-xs">
              <KV k="TradingBot-MT5" v="Pornește MT5 la login" />
              <KV k="TradingBot-RunAll" v="Pornește run_all.py după 45s delay" />
            </div>
            <Warn>Necesită aprobare UAC (Administrator) la activare/dezactivare.</Warn>
          </SubSection>

          <SubSection title="Descărcare date istorice" defaultOpen={false}>
            <p>
              Datele CSV OHLC sunt descărcate din MT5 via Profile → sesiune → Rulează Backtest → Descarcă date.
              Procesul rulează async și apare în tab-ul Audit → Descărcări Date.
            </p>
            <Tip>
              Dacă descărcarea returnează puține bare: deschide graficul simbolului în MT5 pe timeframe-ul
              dorit și <strong>derulează complet spre stânga</strong> pentru a forța cache-ul istoricului,
              apoi reîncearcă.
            </Tip>
          </SubSection>

          <SubSection title="Fus Orar (România / Germania)" defaultOpen={false}>
            <p>
              Botul poate rula în fusul orar al României (default) sau al Germaniei. Setarea se face
              din Profile → secțiunea <strong>Fus Orar</strong> (sub configurarea Telegram).
            </p>
            <div className="space-y-1 text-xs">
              <KV k="România (default)" v="Europe/Bucharest — UTC+2 iarnă / UTC+3 vară" />
              <KV k="Germania" v="Europe/Berlin — UTC+1 iarnă / UTC+2 vară" />
              <KV k="Diferență" v="Mereu exact 1 oră (DST simultan în ambele țări)" />
            </div>
            <p>
              Schimbarea afectează <strong>exclusiv sesiunile live</strong>: ora barelor MT5, filtrele
              session_start/session_end, friday_close_hour și ora curentă în log-uri.
              Backtestul pe CSV nu este afectat (datele sunt deja în ora României).
            </p>
            <Warn>
              Schimbarea fusului orar necesită confirmare în UI. Efectul intră la bara următoare
              (max 15 min pentru M15 / 1 oră pentru H1) — fără restart bot.
            </Warn>
            <Tip>
              Dacă rulezi botul pe o mașină configurată în Germania, setează fusul orar pe Germania
              astfel încât session_start=10 să însemne 10:00 ora Germaniei (nu 10:00 ora României).
            </Tip>
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
              Tabel paginat (50/pagină) cu <strong className="text-white">toate outcomes</strong> agregate din toate
              sesiunile, sortate descrescător după <code className="text-blue-300">exit_time</code>.
            </p>
            <div className="space-y-1.5 text-xs mt-2">
              <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Filtre disponibile</div>
              <div className="flex flex-wrap gap-1.5">
                {["TP", "SL", "Deschis", "Expirat", "Vineri", "Știri", "Toate"].map(s => (
                  <Badge key={s} color="bg-surface-border text-slate-400" label={s} />
                ))}
              </div>
              <div className="flex flex-wrap gap-1.5 mt-1">
                {["LONG", "SHORT", "Ambele"].map(d => (
                  <Badge key={d} color="bg-surface-border text-slate-400" label={d} />
                ))}
              </div>
            </div>
            <div className="mt-3 grid grid-cols-2 gap-1.5 text-xs">
              <KV k="Sesiune" v="ID-ul sesiunii (ex: session7)" />
              <KV k="Simbol" v="Piața tranzacționată" />
              <KV k="Direcție" v="LONG / SHORT" vColor="text-profit" />
              <KV k="Entry / Exit" v="Prețurile de intrare și ieșire" />
              <KV k="Result R" v="R realizat (ex: +3.5 sau -1.0)" />
              <KV k="P&L USD" v="Profit real din MT5 (NaN = expirat/obs)" />
            </div>
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
          <SubSection title="Ce este și prin ce diferă de bot">
            <p>
              <strong className="text-white">AI Engine</strong> este un motor de trading complet separat de botul pe reguli:
              nu folosește strategia pullback, ci un <strong className="text-white">consiliu de 4 agenți AI</strong> care
              rulează local pe placa video (Ollama, gratuit, nelimitat) și dezbat fiecare decizie:
              Analist Tehnic → Analist Macro/Știri → Risk Manager (cu drept de veto absolut) → Head Trader.
            </p>
            <div className="space-y-2">
              <KV k="Izolare" v="Magic 770015 + comment 'AI-' — nu vede și nu atinge pozițiile botului" />
              <KV k="Siguranță" v="Refuză orice cont non-DEMO; risc max 1%/trade; max 3 poziții; stop zilnic -3R" />
              <KV k="Cost" v="0 $ — modelul AI (qwen3:8b) rulează local pe GPU" />
              <KV k="Piețe" v="EURUSD, USDJPY, GBPUSD, AUDUSD, USDCAD — dimensionate pentru cont ~$1000" />
            </div>
          </SubSection>
          <SubSection title="Tab-ul AI Engine">
            <p>
              Din tab-ul <strong className="text-white">AI Engine</strong> poți: porni/opri motorul (buton On/Off),
              vedea scorecard-ul (decizii, WAIT-uri, trades, R total, expectancy), edita piețele urmărite
              (validate automat contra MT5), citi fiecare decizie cu <strong className="text-white">motivația completă
              și transcriptul dezbaterii</strong> (click pe decizie), vedea rezultatele și log-ul motorului.
            </p>
            <Note>
              Consiliul AI se convoacă doar pe evenimente (schimbare de regim, tensiune de breakout, spike de
              volatilitate, știri High-impact, review poziție, heartbeat zilnic) — nu la fiecare bară. Multe
              decizii vor fi WAIT: asta e disciplină, nu inactivitate.
            </Note>
            <Warn>
              Rezultatele AI sunt separate de rapoartele botului (ledger propriu — data/ai/ledger.db), dar
              P&L-ul contului MT5 din Dashboard include TOT (bot + AI + manual), fiind citit direct din equity.
            </Warn>
          </SubSection>
          <SubSection title="Instalare pe alt dispozitiv (laptop)">
            <p>
              Rulează <code className="text-slate-300">setup_ai_engine.bat</code> — instalează automat Python,
              Ollama și modelul AI, apoi rulează verificările. Pe laptop fără GPU dedicat folosește un model mai mic
              (<code className="text-slate-300">qwen3:4b</code> în ai_engine/config.json). Motorul se rulează pe un
              singur dispozitiv odată (același cont demo).
            </p>
          </SubSection>
        </Section>

        {/* ── 12. CONT LIVE ── */}
        <Section id="live" title="12. Lansare cont live">
          <SubSection title="Demo vs Live — ce se schimbă">
            <p>
              Botul nu distinge între demo și live — folosește același API MT5. Singura diferință este contul activ logat în MT5.
              Atâta timp cât MT5 este deschis și logat pe contul live, ordinele sunt plasate cu bani reali.
            </p>
            <div className="grid grid-cols-1 gap-2 text-xs mt-3">
              {[
                { label: "Funcționează identic", items: ["Detectare semnale (strategie neschimbată)", "Calculul loturilor din equity real MT5", "Filling modes (FOK/IOC/RETURN cu retry)", "Reconciliere la restart (recovery din history MT5)", "Notificări Telegram", "Toate protecțiile (BE, news guard, vineri close)"] },
                { label: "Necesită atenție la tranziție", items: ["Capital Inițial — setează ÎNAINTE de prima pornire", "Simboluri broker — live poate folosi alias-uri diferite față de demo", "AutoTrading activat în MT5 (butonul verde)", "Stop level mai mare pe live = mai puține semnale acceptate"], color: "text-amber-400" },
              ].map(({ label, items, color }) => (
                <div key={label} className="bg-surface rounded-lg border border-surface-border p-3 space-y-1.5">
                  <div className={`text-[11px] font-semibold ${color ?? "text-slate-300"}`}>{label}</div>
                  <ul className="space-y-0.5">
                    {items.map(i => <li key={i} className="text-[10px] text-slate-400 flex gap-1.5"><span className="text-slate-600 mt-0.5">·</span>{i}</li>)}
                  </ul>
                </div>
              ))}
            </div>
          </SubSection>

          <SubSection title="Lista de verificare înainte de prima pornire live">
            <div className="space-y-2 mt-1">
              {[
                { step: "1", title: "Setează Capital Inițial", desc: "Profile → câmpul \"Capital Inițial\" → introdu suma de start a contului live. Alternativ, folosește butonul \"↓ Import din MT5\" pentru a prelua equity curentă automat. Salvează profilul." },
                { step: "2", title: "Verifică simbolurile", desc: "Markets → conectează MT5 pe contul live → verifică că toate simbolurile sesiunilor active sunt disponibile. Unii brokeri folosesc alias-uri (ex: GER40 → DE40). Dacă lipsesc, actualizează SYMBOL_ALIASES în settings sau contactează brokerul." },
                { step: "3", title: "AutoTrading activ în MT5", desc: "Butonul \"AutoTrading\" din bara de instrumente MT5 trebuie să fie verde. Dacă este gri/roșu, click pentru activare. Dashboard-ul afișează banner galben de avertizare când este dezactivat." },
                { step: "4", title: "Verifică account_fraction și risc/trade", desc: "În Profile → SessionEditor, verifică că breakdown-ul live (capital sesiune × fracție / piețe) și risc/trade în USD corespund toleranței tale la risc pentru suma reală." },
                { step: "5", title: "Pornește botul din UI", desc: "Click Start Bot → selectează profilul → confirmă. La prima bară nouă, botul va detecta semnale și va plasa ordine reale în MT5. Urmărește tab-ul Notificări și log-urile pentru primele ore." },
                { step: "6", title: "Verifică primele ordine", desc: "La primul semnal: verifică că ordinul apare în MT5 cu prețul corect (BUY_STOP/SELL_STOP). Compară entry/SL/TP din Dashboard cu ordinul MT5. Dacă există discrepanțe, folosește butonul Sync MT5 din NavBar." },
              ].map(({ step, title, desc }) => (
                <div key={step} className="flex gap-3 bg-surface rounded-lg border border-surface-border p-3">
                  <div className="w-6 h-6 rounded-full bg-blue-600/20 border border-blue-500/40 flex items-center justify-center flex-shrink-0 mt-0.5">
                    <span className="text-[11px] font-bold text-blue-400">{step}</span>
                  </div>
                  <div className="space-y-0.5">
                    <div className="text-xs font-semibold text-slate-200">{title}</div>
                    <div className="text-[11px] text-slate-400 leading-relaxed">{desc}</div>
                  </div>
                </div>
              ))}
            </div>
          </SubSection>

          <SubSection title="Comportament la restart și crash" defaultOpen={false}>
            <p>
              Botul este proiectat să fie robust la reporniri neașteptate:
            </p>
            <div className="space-y-1.5 text-xs mt-2">
              <div className="bg-surface rounded-lg border border-surface-border p-3 space-y-1.5">
                <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">La fiecare restart</div>
                <KV k="_reconcile_mt5_tickets" v="Sincronizează ordinele pending cu biletele MT5 active" />
                <KV k="_recover_lost_outcomes" v="Găsește în history MT5 tranzacțiile închise în lipsa botului" />
                <KV k="_scan_mt5_history" v="Scanare completă 10 zile — prinde orice outcome neînregistrat" />
              </div>
              <Note>
                Ordinele pending în MT5 sunt <strong className="text-white">independente de bot</strong> — rămân active chiar dacă botul se oprește.
                La restart, botul le regăsește și continuă monitorizarea. Niciun ordin nu se pierde la crash.
              </Note>
            </div>
          </SubSection>

          <SubSection title="Rapoarte automate (Telegram)" defaultOpen={false}>
            <p>
              Botul trimite automat rapoarte periodice via Telegram:
            </p>
            <div className="space-y-2 text-xs mt-2">
              <KV k="Zilnic — 23:30" v="Trades din ziua respectivă: Total R, P&L USD, top simboluri, per sesiune" />
              <KV k="Săptămânal — Vineri 23:30" v="Rezumat săptămâna curentă (Luni–Vineri): același format ca zilnicul" />
            </div>
            <Tip>
              Rapoartele automate folosesc doar sesiunile cu <code className="text-blue-300">execute_trades: true</code> — sesiunile de observație sunt excluse.
              Formatul include: 📊 Trades (W/L — WR%), 📈 Total R, 💵 P&L USD, 🏆 Top 3 simboluri.
            </Tip>
          </SubSection>

          <SubSection title="Monitorizare continuă" defaultOpen={false}>
            <p>Indicatori cheie de urmărit în primele zile pe live:</p>
            <div className="space-y-1.5 text-xs mt-2">
              <KV k="Banner galben AutoTrading" v="Dacă apare, click AutoTrading în MT5 — ordinele NU se plasează când este dezactivat" />
              <KV k="P&L Real MT5 vs așteptat" v="Compară zilnic cu suma raportată de MT5 — diferențe mari pot indica duplicate" />
              <KV k="Notificări [RECOVER]" v="Apar când botul a recuperat tranzacții închise în lipsa lui — normale după restart" />
              <KV k="min stops distance" v="Log warning = SL prea aproape de preț curent — ordinul nu s-a plasat, se reîncearcă la bara următoare" />
              <KV k="Sync MT5" v="Butonul din NavBar forțează resincronizarea outcomes cu history MT5 — folosește dacă P&L pare incorect" />
              <KV k="Notificări [DEDUP]" v="Apar când botul a detectat un ordin MT5 deja existent pentru același semnal și l-a adoptat în loc să plaseze un duplicat — pot apărea după un crash/restart" />
            </div>
          </SubSection>

          <SubSection title="Sync MT5 — Reconciliere manuală" defaultOpen={false}>
            <p>
              Butonul <strong className="text-white">Sync MT5</strong> din NavBar reconciliază <code className="text-blue-300">outcomes.csv</code> cu
              istoricul real din MT5. Principiu: <strong className="text-yellow-400">MT5 este sursa de adevăr</strong> — dacă o tranzacție
              există în MT5, ea trebuie să fie reflectată în dashboard.
            </p>
            <div className="grid grid-cols-2 gap-3 text-xs mt-3">
              <div className="bg-surface rounded-lg border border-surface-border p-3 space-y-1">
                <div className="text-[11px] font-semibold text-slate-300">Detectează</div>
                <div className="text-slate-400">Scanează history MT5 (10 zile) și raportează discrepanțele fără să modifice nimic. Arată ticket, simbol, R și P&L pentru fiecare poziție MT5 care lipsește din outcomes.csv.</div>
              </div>
              <div className="bg-surface rounded-lg border border-surface-border p-3 space-y-1">
                <div className="text-[11px] font-semibold text-slate-300">Corectează</div>
                <div className="text-slate-400">Scrie în outcomes.csv rândurile lipsă cu datele reale MT5. Sigur de rulat și cu botul activ — nu modifică state.pkl.</div>
              </div>
            </div>
            <div className="mt-3 space-y-1.5 text-xs">
              <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Ce detectează</div>
              <KV k="Pozitii MT5 lipsă din outcomes" v="Ordine executate în MT5 care nu au rând corespondent în outcomes.csv (ex: bot oprit înainte să scrie rezultatul)" />
              <KV k="Semnale triggered fără poziție deschisă" v="State.pkl are semnal ca triggered, dar poziția MT5 nu mai există — potențial trade neînregistrat" />
            </div>
            <Note>
              Sincronizarea filtrează automat semnalele altor sesiuni care tranzacționează același simbol (ex: S2-NZDJPY găsit în sesiunea care tranzacționează și ea NZDJPY). Prefixul comentariului MT5 (<code>S18-</code>, <code>S2-</code> etc.) identifică sesiunea de origine.
            </Note>
            <Tip>
              Dacă după sync mai apar discrepanțe persistente, verifică în MT5 că ordinul comentariul include prefix-ul corect al sesiunii. ICMarketsEU trunchiază comentariile la 16 caractere — semnalele cu ID lung (ex: <code>S18-NZDJPY-H1-IB0010</code>) sunt stocate trunchiat în MT5.
            </Tip>
          </SubSection>
        </Section>

        {/* Footer */}
        <div className="border-t border-surface-border pt-6 text-center text-xs text-slate-600 space-y-1">
          <p>Trading Bot — Ghid intern · Ultima actualizare: {new Date().toLocaleDateString("ro-RO")}</p>
          <p className="text-slate-700">
            Nicio modificare la fișierele <code>strategy/</code>, <code>engine/</code> sau <code>live/</code>
            nu este necesară pentru funcționarea UI.
          </p>
        </div>
      </div>
    </div>
  );
}
