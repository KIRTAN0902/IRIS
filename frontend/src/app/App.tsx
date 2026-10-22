import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AppShell } from "@/components/layout/AppShell";
import { HomePage } from "@/features/home/HomePage";
import { TodayPage } from "@/features/today/TodayPage";
import { TasksPage } from "@/features/tasks/TasksPage";
import { GoalsPage } from "@/features/goals/GoalsPage";
import { SchedulePage } from "@/features/schedule/SchedulePage";
import { ProjectsPage } from "@/features/projects/ProjectsPage";
import { DiaryPage } from "@/features/diary/DiaryPage";
import { FinancePage } from "@/features/finance/FinancePage";
import { WorkoutsPage } from "@/features/gym/WorkoutsPage";
import { StartupPage } from "@/features/startup/StartupPage";
import { AreaLensPage } from "@/features/areas/AreaLensPage";
import { InsightsPage } from "@/features/insights/InsightsPage";
import { ModulesPage } from "@/features/modules/ModulesPage";
import { FocusPage } from "@/features/focus/FocusPage";
import { SettingsPage } from "@/features/settings/SettingsPage";
import { ContinuityPage } from "@/features/continuity/ContinuityPage";
import { AgyTerminalDeck } from "@/features/agy/AgyTerminalDeck";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: true,
      staleTime: 30_000,
    },
  },
});

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<HomePage />} />
            <Route path="today" element={<TodayPage />} />
            <Route path="tasks" element={<TasksPage />} />
            <Route path="goals" element={<GoalsPage />} />
            <Route path="schedule" element={<SchedulePage />} />
            <Route path="projects" element={<ProjectsPage />} />
            <Route path="diary" element={<DiaryPage />} />
            <Route path="finance" element={<FinancePage />} />
            <Route path="gym" element={<WorkoutsPage />} />
            <Route path="focus" element={<FocusPage />} />
            <Route path="laptop" element={<ContinuityPage initialView="laptop" />} />
            <Route path="phone" element={<ContinuityPage initialView="phone" />} />
            <Route path="agy" element={<AgyTerminalDeck />} />
            <Route path="terminal" element={<Navigate to="/agy" replace />} />
            <Route path="settings" element={<SettingsPage />} />
            <Route path="mesh" element={<Navigate to="/settings?tab=mesh" replace />} />
            <Route path="startup" element={<StartupPage />} />
            <Route path="college" element={<AreaLensPage area="COLLEGE" title="College" />} />
            <Route path="internship" element={<AreaLensPage area="INTERNSHIP" title="Internship" />} />
            <Route path="insights" element={<InsightsPage />} />
            <Route path="modules" element={<ModulesPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
