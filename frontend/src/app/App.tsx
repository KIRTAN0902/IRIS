import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ApiError } from "@/api/client";
import { AppShell } from "@/components/layout/AppShell";
import { IrisOSStage } from "@/components/layout/IrisOSStage";

const CoworkerChatPage = lazy(() =>
  import("@/features/coworkers/CoworkerChatPage").then((m) => ({ default: m.CoworkerChatPage })),
);
const AgyTerminalDeck = lazy(() =>
  import("@/features/agy/AgyTerminalDeck").then((m) => ({ default: m.AgyTerminalDeck })),
);
const SettingsPage = lazy(() =>
  import("@/features/settings/SettingsPage").then((m) => ({ default: m.SettingsPage })),
);
const StartupPage = lazy(() =>
  import("@/features/startup/StartupPage").then((m) => ({ default: m.StartupPage })),
);
const AreaLensPage = lazy(() =>
  import("@/features/areas/AreaLensPage").then((m) => ({ default: m.AreaLensPage })),
);
const InsightsPage = lazy(() =>
  import("@/features/insights/InsightsPage").then((m) => ({ default: m.InsightsPage })),
);
const ModulesPage = lazy(() =>
  import("@/features/modules/ModulesPage").then((m) => ({ default: m.ModulesPage })),
);

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (failureCount, error) =>
        failureCount < 2 && error instanceof ApiError && error.retryable,
      retryDelay: (attemptIndex) =>
        Math.min(1000 * 2 ** attemptIndex, 8000) + Math.random() * 250,
      refetchOnWindowFocus: true,
      staleTime: 30_000,
    },
  },
});

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Suspense
          fallback={
            <div className="flex h-screen items-center justify-center bg-ops-ground text-ink-faint text-sm">
              Initializing IRIS Personal OS…
            </div>
          }
        >
          <Routes>
            <Route element={<AppShell />}>
              {/* Sovereign Operating System Canvas */}
              <Route index element={<IrisOSStage />} />

              {/* Seamless URL mappings to Operating Lenses */}
              <Route path="home" element={<Navigate to="/?lens=home" replace />} />
              <Route path="chat" element={<Navigate to="/?lens=studio" replace />} />
              <Route path="conversations" element={<Navigate to="/?lens=studio" replace />} />
              <Route path="today" element={<Navigate to="/?lens=horizon&tab=overview" replace />} />
              <Route path="tasks" element={<Navigate to="/?lens=horizon&tab=priorities" replace />} />
              <Route path="goals" element={<Navigate to="/?lens=horizon&tab=projects" replace />} />
              <Route path="schedule" element={<Navigate to="/?lens=horizon&tab=schedule" replace />} />
              <Route path="projects" element={<Navigate to="/?lens=horizon&tab=projects" replace />} />
              <Route path="coworkers" element={<Navigate to="/?lens=fleet" replace />} />
              <Route path="coworkers/:coworkerId/chat" element={<CoworkerChatPage />} />
              <Route path="coworkers/:coworkerId" element={<CoworkerChatPage />} />
              <Route path="diary" element={<Navigate to="/?lens=horizon&tab=diary" replace />} />
              <Route path="finance" element={<Navigate to="/?lens=horizon&tab=finance" replace />} />
              <Route path="gym" element={<Navigate to="/?lens=horizon&tab=fitness" replace />} />
              <Route path="focus" element={<Navigate to="/?lens=horizon&tab=overview" replace />} />
              <Route path="laptop" element={<Navigate to="/?lens=vault&tab=mesh" replace />} />
              <Route path="phone" element={<Navigate to="/?lens=vault&tab=mesh" replace />} />
              <Route path="agy" element={<AgyTerminalDeck />} />
              <Route path="terminal" element={<Navigate to="/agy" replace />} />
              <Route path="settings" element={<SettingsPage />} />
              <Route path="settings/knowledge" element={<Navigate to="/?lens=vault&tab=graph" replace />} />
              <Route path="settings/mesh" element={<Navigate to="/?lens=vault&tab=mesh" replace />} />
              <Route path="settings/devices" element={<Navigate to="/?lens=vault&tab=mesh" replace />} />
              <Route path="knowledge" element={<Navigate to="/?lens=vault&tab=graph" replace />} />
              <Route path="devices" element={<Navigate to="/?lens=vault&tab=mesh" replace />} />
              <Route path="mesh" element={<Navigate to="/?lens=vault&tab=mesh" replace />} />
              <Route path="memory" element={<Navigate to="/?lens=vault&tab=memories" replace />} />
              <Route path="startup" element={<StartupPage />} />
              <Route path="college" element={<AreaLensPage area="COLLEGE" title="College" />} />
              <Route path="internship" element={<AreaLensPage area="INTERNSHIP" title="Internship" />} />
              <Route path="insights" element={<InsightsPage />} />
              <Route path="modules" element={<ModulesPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        </Suspense>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
