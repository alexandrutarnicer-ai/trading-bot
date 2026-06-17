import { useBacktestHistory } from "../api/hooks";

type Tab = "dashboard" | "profile" | "history";

interface Props {
  active: Tab;
  onChange: (t: Tab) => void;
}

const TABS: { id: Tab; label: string }[] = [
  { id: "dashboard", label: "Dashboard" },
  { id: "profile",   label: "Profile" },
  { id: "history",   label: "Istoric" },
];

export function NavBar({ active, onChange }: Props) {
  const { data: history } = useBacktestHistory();
  const historyCount = history?.length ?? 0;

  return (
    <header className="sticky top-0 z-10 bg-surface border-b border-surface-border flex items-center gap-6 px-6 h-12">
      <span className="text-sm font-bold text-white tracking-wide mr-4">Trading Bot</span>
      {TABS.map(({ id, label }) => (
        <button
          key={id}
          onClick={() => onChange(id)}
          className={`flex items-center gap-1.5 text-xs font-medium uppercase tracking-widest pb-0.5 border-b-2 transition-colors ${
            active === id
              ? "border-blue-500 text-white"
              : "border-transparent text-slate-400 hover:text-slate-200"
          }`}
        >
          {label}
          {id === "history" && historyCount > 0 && (
            <span className={`text-[10px] rounded-full px-1.5 py-0.5 font-normal ${
              active === "history"
                ? "bg-blue-500/30 text-blue-200"
                : "bg-surface-border text-slate-500"
            }`}>
              {historyCount}
            </span>
          )}
        </button>
      ))}
    </header>
  );
}
