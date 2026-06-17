import { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { NavBar } from "./components/NavBar";
import { Dashboard } from "./pages/Dashboard";
import { ProfilePage } from "./pages/ProfilePage";

const qc = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 20_000 } },
});

type Tab = "dashboard" | "profile";

export default function App() {
  const [tab, setTab] = useState<Tab>("dashboard");

  return (
    <QueryClientProvider client={qc}>
      <div className="min-h-screen bg-surface text-white">
        <NavBar active={tab} onChange={setTab} />
        {tab === "dashboard" ? <Dashboard /> : <ProfilePage />}
      </div>
    </QueryClientProvider>
  );
}
