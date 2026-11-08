import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ApiError } from "@/api/client";
import { AppShell } from "@/components/layout/AppShell";
import { HomePage } from "@/features/home/HomePage";

const TodayPage = lazy(() => import("@/features/today/TodayPage").then((m) => ({ default: m.TodayPage })));
const TasksPage = lazy(() => import("@/features/tasks/TasksPage").then((m) => ({ default: m.TasksPage })));
const GoalsPage = lazy(() => import("@/features/goals/GoalsPage").then((m) => ({ default: m.GoalsPage })));
const SchedulePage = lazy(() => import("@/features/schedule/SchedulePage").then((m) => ({ default: m.SchedulePage })));
const ProjectsPage = lazy(() => import("@/features/projects/ProjectsPage").then((m) => ({ default: m.ProjectsPage })));
const DiaryPage = lazy(() => import("@/features/diary/DiaryPage").then((m) => ({ default: m.DiaryPage })));
const FinancePage = lazy(() => import("@/features/finance/FinancePage").then((m) => ({ default: m.FinancePage })));
const WorkoutsPage = lazy(() => import("@/features/gym/WorkoutsPage").then((m) => ({ default: m.WorkoutsPage })));
const StartupPage = lazy(() => import("@/features/startup/StartupPage").then((m) => ({ default: m.StartupPage })));
const AreaLensPage = lazy(() => import("@/features/areas/AreaLensPage").then((m) => ({ default: m.AreaLensPage })));
const InsightsPage = lazy(() => import("@/features/insights/InsightsPage").then((m) => ({ default: m.InsightsPage })));
const ModulesPage = lazy(() => import("@/features/modules/ModulesPage").then((m) => ({ default: m.ModulesPage })));
const FocusPage = lazy(() => import("@/features/focus/FocusPage").then((m) => ({ default: m.FocusPage })));
const SettingsPage = lazy(() => import("@/features/settings/SettingsPage").then((m) => ({ default: m.SettingsPage })));
const ContinuityPage = lazy(() => import("@/features/continuity/ContinuityPage").then((m) => ({ default: m.ContinuityPage })));
const AgyTerminalDeck = lazy(() => import("@/features/agy/AgyTerminalDeck").then((m) => ({ default: m.AgyTerminalDeck })));
const CoworkersPage = lazy(() => import("@/features/coworkers/CoworkersPage").then((m) => ({ default: m.CoworkersPage })));
const CoworkerChatPage = lazy(() => import("@/features/coworkers/CoworkerChatPage").then((m) => ({ default: m.CoworkerChatPage })));
const ConversationsPage = lazy(() => import("@/features/chat/ConversationsPage").then((m) => ({ default: m.ConversationsPage })));
const MemoryPage = lazy(() => import("@/features/home/MemoryPage").then((m) => ({ default: m.MemoryPage })));
const KnowledgePage = lazy(() => import("@/features/knowledge/KnowledgePage").then((m) => ({ default: m.KnowledgePage })));
const MeshPage = lazy(() => import("@/features/mesh/MeshPage").then((m) => ({ default: m.MeshPage })));
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
        <Suspense fallback={<div className="mx-auto w-full max-w-5xl p-4" role="status">Loading IRIS…</div>}><Routes>
          <Route element={<AppShell />}>
            <Route index element={<HomePage />} />
            <Route path="conversations" element={<ConversationsPage />} />
            <Route path="today" element={<TodayPage />} />
            <Route path="tasks" element={<TasksPage />} />
            <Route path="goals" element={<GoalsPage />} />
            <Route path="schedule" element={<SchedulePage />} />
            <Route path="projects" element={<ProjectsPage />} />
            <Route path="coworkers" element={<CoworkersPage />} />
            <Route path="coworkers/:coworkerId/chat" element={<CoworkerChatPage />} />
            <Route path="coworkers/:coworkerId" element={<CoworkerChatPage />} />
            <Route path="diary" element={<DiaryPage />} />
            <Route path="finance" element={<FinancePage />} />
            <Route path="gym" element={<WorkoutsPage />} />
            <Route path="focus" element={<FocusPage />} />
            <Route path="laptop" element={<ContinuityPage initialView="laptop" />} />
            <Route path="phone" element={<ContinuityPage initialView="phone" />} />
            <Route path="agy" element={<AgyTerminalDeck />} />
            <Route path="terminal" element={<Navigate to="/agy" replace />} />
            <Route path="settings" element={<SettingsPage />} />
            <Route path="memory" element={<MemoryPage />} />
            <Route path="knowledge" element={<KnowledgePage />} />
            <Route path="devices" element={<MeshPage />} />
            <Route path="mesh" element={<Navigate to="/devices" replace />} />
            <Route path="startup" element={<StartupPage />} />
            <Route path="college" element={<AreaLensPage area="COLLEGE" title="College" />} />
            <Route path="internship" element={<AreaLensPage area="INTERNSHIP" title="Internship" />} />
            <Route path="insights" element={<InsightsPage />} />
            <Route path="modules" element={<ModulesPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes></Suspense>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
