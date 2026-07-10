import { useBacktestJobs, useDownloadJobs, useNotifications } from "../api/hooks";
import { AutostartToggle } from "./AutostartToggle";
import { AiAutostartToggle } from "./AiAutostartToggle";
import Mt5SyncButton from "./Mt5SyncButton";

type Tab = "dashboard" | "profile" | "ai" | "notifications" | "audit" | "reports" | "guide";

interface Props {
  active: Tab;
  onChange: (t: Tab) => void;
}

const TABS: { id: Tab; label: string }[] = [
  { id: "dashboard",     label: "Dashboard" },
  { id: "profile",       label: "Profile" },
  { id: "ai",            label: "AI Engine" },
  { id: "notifications", label: "Notificări" },
  { id: "audit",         label: "Audit" },
  { id: "reports",       label: "Rapoarte" },
  { id: "guide",         label: "Ghid" },
];

export function NavBar({ active, onChange }: Props) {
  const { data: btJobs } = useBacktestJobs();
  const { data: dlJobs } = useDownloadJobs();
  const { data: notifs } = useNotifications(200);

  const runningCount = (
    (btJobs?.filter(j => j.status === "pending" || j.status === "running").length ?? 0) +
    (dlJobs?.filter(j => j.status === "pending" || j.status === "running").length ?? 0)
  );
  const totalCount  = (btJobs?.length ?? 0) + (dlJobs?.length ?? 0);
  const unreadCount = notifs?.unread ?? 0;

  return (
    <header className="sticky top-0 z-10 bg-surface border-b border-surface-border flex items-center gap-1 px-6 h-12">
      <span className="text-sm font-bold text-white tracking-wide mr-5">Trading Bot</span>
      {TABS.map(({ id, label }) => (
        <button
          key={id}
          onClick={() => onChange(id)}
          className={`flex items-center gap-1.5 text-xs font-medium uppercase tracking-widest px-2 py-1.5 border-b-2 transition-colors ${
            active === id
              ? "border-blue-500 text-white"
              : "border-transparent text-slate-400 hover:text-slate-200"
          }`}
        >
          {label}

          {/* Badge notificări necitite */}
          {id === "notifications" && unreadCount > 0 && (
            <span className="flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse" />
              <span className="text-[10px] rounded-full px-1.5 py-0.5 font-normal bg-blue-500/30 text-blue-300">
                {unreadCount}
              </span>
            </span>
          )}

          {/* Badge audit în rulare */}
          {id === "audit" && runningCount > 0 && (
            <span className="flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse" />
              <span className="text-[10px] rounded-full px-1.5 py-0.5 font-normal bg-blue-500/30 text-blue-300">
                {runningCount}
              </span>
            </span>
          )}
          {id === "audit" && runningCount === 0 && totalCount > 0 && (
            <span className={`text-[10px] rounded-full px-1.5 py-0.5 font-normal ${
              active === "audit"
                ? "bg-blue-500/30 text-blue-200"
                : "bg-surface-border text-slate-500"
            }`}>
              {totalCount}
            </span>
          )}
        </button>
      ))}
      <div className="ml-auto flex items-center gap-2">
        <Mt5SyncButton />
        <AutostartToggle />
        <AiAutostartToggle />
      </div>
    </header>
  );
}
