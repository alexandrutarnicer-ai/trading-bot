type Tab = "dashboard" | "profile";

interface Props {
  active: Tab;
  onChange: (t: Tab) => void;
}

export function NavBar({ active, onChange }: Props) {
  return (
    <header className="sticky top-0 z-10 bg-surface border-b border-surface-border flex items-center gap-6 px-6 h-12">
      <span className="text-sm font-bold text-white tracking-wide mr-4">Trading Bot</span>
      {(["dashboard", "profile"] as Tab[]).map((t) => (
        <button
          key={t}
          onClick={() => onChange(t)}
          className={`text-xs font-medium uppercase tracking-widest pb-0.5 border-b-2 transition-colors ${
            active === t
              ? "border-blue-500 text-white"
              : "border-transparent text-slate-400 hover:text-slate-200"
          }`}
        >
          {t === "dashboard" ? "Dashboard" : "Profile"}
        </button>
      ))}
    </header>
  );
}
