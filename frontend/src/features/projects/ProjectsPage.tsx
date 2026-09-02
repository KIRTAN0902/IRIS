import { useSearchParams } from "react-router-dom";
import { FolderTree, Rocket, Target } from "lucide-react";
import { useProjects } from "@/hooks/queries";
import { EmptyState, Skeleton } from "@/components/ui/Overlay";
import { Lamp, Panel } from "@/components/ui/Panel";
import { cn, fmtDay } from "@/lib/format";
import { GoalsPage } from "@/features/goals/GoalsPage";
import { StartupPage } from "@/features/startup/StartupPage";

type ProjectTab = "projects" | "goals" | "startup";

export function ProjectsPage() {
  const [params, setParams] = useSearchParams();
  const currentTab = (params.get("tab") as ProjectTab) || "projects";

  const setTab = (tab: ProjectTab) => {
    setParams({ tab });
  };

  return (
    <div className="space-y-6">
      {/* Sub-Navigation Header */}
      <header className="flex flex-wrap items-center justify-between gap-4 border-b border-ops-line pb-4">
        <div className="flex items-baseline gap-3">
          <h1 className="font-[family-name:var(--font-display)] text-[22px] font-bold tracking-wide text-ink">
            PROJECTS & CONTEXTS
          </h1>
        </div>

        {/* Tab switcher */}
        <div className="flex items-center gap-1 border border-ops-line bg-ops-panel/40 p-1">
          <button
            onClick={() => setTab("projects")}
            className={cn(
              "flex items-center gap-2 px-3 py-1.5 text-[12px] font-medium tracking-wide transition-colors",
              currentTab === "projects"
                ? "bg-ops-raised text-ink font-semibold border-b-2 border-caution"
                : "text-ink-dim hover:text-ink hover:bg-ops-panel",
            )}
          >
            <FolderTree size={14} className={currentTab === "projects" ? "text-caution" : "text-ink-faint"} />
            <span>Projects</span>
          </button>
          <button
            onClick={() => setTab("goals")}
            className={cn(
              "flex items-center gap-2 px-3 py-1.5 text-[12px] font-medium tracking-wide transition-colors",
              currentTab === "goals"
                ? "bg-ops-raised text-ink font-semibold border-b-2 border-caution"
                : "text-ink-dim hover:text-ink hover:bg-ops-panel",
            )}
          >
            <Target size={14} className={currentTab === "goals" ? "text-caution" : "text-ink-faint"} />
            <span>Goals Tree</span>
          </button>
          <button
            onClick={() => setTab("startup")}
            className={cn(
              "flex items-center gap-2 px-3 py-1.5 text-[12px] font-medium tracking-wide transition-colors",
              currentTab === "startup"
                ? "bg-ops-raised text-ink font-semibold border-b-2 border-caution"
                : "text-ink-dim hover:text-ink hover:bg-ops-panel",
            )}
          >
            <Rocket size={14} className={currentTab === "startup" ? "text-caution" : "text-ink-faint"} />
            <span>Startup CRM</span>
          </button>
        </div>
      </header>

      {/* Tab Content */}
      {currentTab === "projects" && <ProjectsListView />}
      {currentTab === "goals" && <GoalsPage />}
      {currentTab === "startup" && <StartupPage />}
    </div>
  );
}

function ProjectsListView() {
  const projects = useProjects();
  return (
    <div className="space-y-5">
      <Panel
        title="Active Project Containers"
        lamp={<Lamp tone="dim" />}
        actions={
          <span className="font-[family-name:var(--font-telemetry)] text-[12px] text-ink-faint">
            {projects.data?.length ?? 0} registered
          </span>
        }
        bodyClassName="!p-0"
      >
        {projects.isLoading ? (
          <div className="p-4">
            <Skeleton className="h-32" />
          </div>
        ) : !projects.data?.length ? (
          <div className="p-4">
            <EmptyState
              message="No project containers yet."
              hint="Group related tasks under a deliverable container like 'SPM Submission' or 'NEXUS MVP'."
            />
          </div>
        ) : (
          <ol className="divide-y divide-ops-line">
            {projects.data.map((p) => (
              <li
                key={p.id}
                className="flex items-center gap-3 px-4 py-3 hover:bg-ops-raised/30 transition-colors"
              >
                <Lamp tone={p.status === "ACTIVE" ? "go" : "dim"} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline gap-2">
                    <p className="truncate text-[14px] font-medium text-ink">{p.name}</p>
                    <span className="font-[family-name:var(--font-telemetry)] text-[10px] uppercase tracking-wider text-ink-faint border border-ops-line px-1">
                      {p.area}
                    </span>
                  </div>
                  {p.description && (
                    <p className="line-clamp-1 text-[12px] text-ink-dim mt-0.5">{p.description}</p>
                  )}
                </div>
                {p.deadline && (
                  <span className="font-[family-name:var(--font-telemetry)] tnum text-[12px] text-caution">
                    due {fmtDay(p.deadline)}
                  </span>
                )}
                {p.task_count != null && (
                  <span className="font-[family-name:var(--font-telemetry)] tnum text-[12px] text-ink-faint">
                    {p.task_count} tasks
                  </span>
                )}
              </li>
            ))}
          </ol>
        )}
      </Panel>
    </div>
  );
}
