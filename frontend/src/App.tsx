import { BrowserRouter, Routes, Route } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RootLayout } from "./components/layout/root-layout";
import { DashboardPage } from "./pages/dashboard";
import { RfpListPage } from "./pages/rfp-list";
import { RfpDetailPage } from "./pages/rfp-detail";
import { ProposalListPage } from "./pages/proposal-list";
import { ProposalDetailPage } from "./pages/proposal-detail";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 10_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<RootLayout />}>
            <Route index element={<DashboardPage />} />
            <Route path="rfps" element={<RfpListPage />} />
            <Route path="rfps/:id" element={<RfpDetailPage />} />
            <Route path="proposals" element={<ProposalListPage />} />
            <Route path="proposals/:id" element={<ProposalDetailPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
