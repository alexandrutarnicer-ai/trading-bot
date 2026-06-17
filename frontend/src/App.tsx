import { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { NavBar } from "./components/NavBar";
import { Dashboard } from "./pages/Dashboard";
import { ProfilePage } from "./pages/ProfilePage";
import { AuditPage } from "./pages/AuditPage";
import { useBacktestJobs } from "./api/hooks";

const qc = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 0,
      refetchOnWindowFocus: true,
    },
  },
});

type Tab = "dashboard" | "profile" | "audit";

function AppInner() {
  const [tab, setTab] = useState<Tab>("dashboard");

  // Polling global pentru joburi active — activ indiferent de tab
  useBacktestJobs();

  return (
    <div className="min-h-screen bg-surface text-white">
      <NavBar active={tab} onChange={setTab} />
      {tab === "dashboard" ? (
        <Dashboard />
      ) : tab === "audit" ? (
        <AuditPage />
      ) : (
        <ProfilePage onNavigateToAudit={() => setTab("audit")} />
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
