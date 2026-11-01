import { useState, useEffect } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { NavBar } from "./components/NavBar";
import { Dashboard } from "./pages/Dashboard";
import { ProfilePage } from "./pages/ProfilePage";
import { AuditPage } from "./pages/AuditPage";
import { GuidePage } from "./pages/GuidePage";
import { NotificationsPage } from "./pages/NotificationsPage";
import { ReportsPage } from "./pages/ReportsPage";
import { AiEnginePage } from "./pages/AiEnginePage";
import { SettingsPage } from "./pages/SettingsPage";
import { DailyEnginePage } from "./pages/DailyEnginePage";
import { NoisyEnginePage } from "./pages/NoisyEnginePage";
import { useBacktestJobs } from "./api/hooks";

const qc = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 0,
      refetchOnWindowFocus: true,
      gcTime: 90_000, // curata cache dupa 90s (default 5min) — reduce memoria in timp
    },
  },
});

type Tab = "dashboard" | "profile" | "ai" | "daily" | "noisy" | "settings" | "notifications" | "audit" | "reports" | "guide";

export interface PendingApply {
  sessionId: string;
  config: Record<string, unknown>;
}

// Auto-refresh dupa 4 ore pentru a preveni acumularea de memorie
const AUTO_REFRESH_MS = 4 * 60 * 60 * 1000;

function AppInner() {
  const [tab, setTab] = useState<Tab>("dashboard");
  const [pendingApply, setPendingApply] = useState<PendingApply | null>(null);
  // Taburi vizitate cel putin o data — lazy mount pentru paginile grele
  const [visited, setVisited] = useState<Set<Tab>>(new Set(["dashboard", "profile"]));

  // Polling global pentru joburi active — activ indiferent de tab
  useBacktestJobs();

  // Auto-refresh la 4 ore: elibereaza toata memoria acumulata
  useEffect(() => {
    const id = setTimeout(() => window.location.reload(), AUTO_REFRESH_MS);
    return () => clearTimeout(id);
  }, []);

  function handleTabChange(newTab: Tab) {
    setTab(newTab);
    setVisited(prev => prev.has(newTab) ? prev : new Set([...prev, newTab]));
  }

  function handleApplyConfig(sessionId: string, config: Record<string, unknown>) {
    setPendingApply({ sessionId, config });
    handleTabChange("profile");
  }

  return (
    <div className="min-h-screen bg-surface text-white">
      <NavBar active={tab} onChange={handleTabChange} />
      {/* Dashboard + Profile: montate permanent (stare critica: editari nesalvate) */}
      <div className={tab === "dashboard" ? undefined : "hidden"}>
        <Dashboard />
      </div>
      <div className={tab === "profile" ? undefined : "hidden"}>
        <ProfilePage
          onNavigateToAudit={() => handleTabChange("audit")}
          pendingApply={pendingApply}
          onClearPendingApply={() => setPendingApply(null)}
        />
      </div>
      {/* Pagini grele: montate lazy (la prima vizita) — nu polleaza pana nu sunt deschise */}
      {visited.has("ai") && (
        <div className={tab === "ai" ? undefined : "hidden"}>
          <div className="max-w-6xl mx-auto px-4 py-4">
            <AiEnginePage />
          </div>
        </div>
      )}
      {visited.has("daily") && (
        <div className={tab === "daily" ? undefined : "hidden"}>
          <div className="max-w-6xl mx-auto px-4 py-4">
            <DailyEnginePage />
          </div>
        </div>
      )}
      {visited.has("noisy") && (
        <div className={tab === "noisy" ? undefined : "hidden"}>
          <div className="max-w-6xl mx-auto px-4 py-4">
            <NoisyEnginePage />
          </div>
        </div>
      )}
      {visited.has("settings") && (
        <div className={tab === "settings" ? undefined : "hidden"}>
          <SettingsPage />
        </div>
      )}
      {visited.has("notifications") && (
        <div className={tab === "notifications" ? undefined : "hidden"}>
          <NotificationsPage />
        </div>
      )}
      {visited.has("audit") && (
        <div className={tab === "audit" ? undefined : "hidden"}>
          <AuditPage onApplyConfig={handleApplyConfig} />
        </div>
      )}
      {visited.has("reports") && (
        <div className={tab === "reports" ? undefined : "hidden"}>
          <ReportsPage />
        </div>
      )}
      {visited.has("guide") && (
        <div className={tab === "guide" ? undefined : "hidden"}>
          <GuidePage />
        </div>
      )}
    </div>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <AppInner />
    </QueryClientProvider>
  );
}
