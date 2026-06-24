import { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { NavBar } from "./components/NavBar";
import { Dashboard } from "./pages/Dashboard";
import { ProfilePage } from "./pages/ProfilePage";
import { AuditPage } from "./pages/AuditPage";
import { GuidePage } from "./pages/GuidePage";
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

type Tab = "dashboard" | "profile" | "audit" | "guide";

function AppInner() {
  const [tab, setTab] = useState<Tab>("dashboard");

  // Polling global pentru joburi active — activ indiferent de tab
  useBacktestJobs();

  return (
    <div className="min-h-screen bg-surface text-white">
      <NavBar active={tab} onChange={setTab} />
      {/* Toate paginile sunt montate odata — CSS display:none pastreaza starea React */}
      <div className={tab === "dashboard" ? undefined : "hidden"}>
        <Dashboard />
      </div>
      <div className={tab === "profile" ? undefined : "hidden"}>
        <ProfilePage onNavigateToAudit={() => setTab("audit")} />
      </div>
      <div className={tab === "audit" ? undefined : "hidden"}>
        <AuditPage />
      </div>
      <div className={tab === "guide" ? undefined : "hidden"}>
        <GuidePage />
      </div>
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
