import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Dashboard } from "./pages/Dashboard";

const qc = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 20_000 } },
});

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <Dashboard />
    </QueryClientProvider>
  );
}
