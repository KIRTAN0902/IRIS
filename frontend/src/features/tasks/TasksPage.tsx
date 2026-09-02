import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  Briefcase,
  CheckCircle2,
  Circle,
  Clock,
  FolderTree,
  GraduationCap,
  Plus,
  Rocket,
  Search,
  Trash2,
} from "lucide-react";
import {
  useCompleteTask,
  useCreateTask,
  useDeleteTask,
  useGoals,
  useProjects,
  useTasks,
  useUpdateTask,
} from "@/hooks/queries";
import type { TaskOut } from "@/types/api";
import { Button } from "@/components/ui/Button";
import { Dialog, DialogContent, ErrorState, Skeleton } from "@/components/ui/Overlay";
import { Field, Input, Select, Textarea } from "@/components/ui/Field";
import { Lamp } from "@/components/ui/Panel";
import { cn, humanDuration, urgencyLabel } from "@/lib/format";
import { TASK_PRIORITIES, type LifeArea, type TaskPriority } from "@/types/api";

type FilterTab = "active" | "all" | "completed" | "overdue";

/**
 * TASKS — Domain-Organized Action Register.
 *
 * Information Architecture:
 * - STARTUP (Marketory, NEXUS, Outreach, Customer Discovery, Experiments)
 * - INTERNSHIP (AI Internship, Deliverables, Client Work, Reports)
 * - COLLEGE (Assignments, Compiler Design, Agentic AI, SPM, DSA, Exams)
 *
 * Desktop Layout:
 * ┌───────────────────────┬───────────────────────┐
 * │       STARTUP         │      INTERNSHIP       │
 * └───────────────────────┴───────────────────────┘
 * ┌───────────────────────────────────────────────┐
 * │                    COLLEGE                    │
 * └───────────────────────────────────────────────┘
 *
 * Mobile Layout: Clean vertical stack with zero horizontal overflow.
 */
export function TasksPage() {
  const [params] = useSearchParams();
  const [filterTab, setFilterTab] = useState<FilterTab>(
    (params.get("tab") as FilterTab) || (params.get("overdue") === "1" ? "overdue" : "active"),
  );
  const [query, setQuery] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [defaultArea, setDefaultArea] = useState<LifeArea>("STARTUP");

  const projects = useProjects();
  const projectsMap = useMemo(() => {
    const map = new Map<number, string>();
    for (const p of projects.data ?? []) {
      map.set(p.id, p.name);
    }
    return map;
  }, [projects.data]);

  // Retrieve all tasks to categorize dynamically by domain
  const tasksQuery = useTasks({
    limit: 300,
  });

  const allTasks = tasksQuery.data ?? [];

  // Filter tasks by active status / tab & search query
  const filteredTasks = useMemo(() => {
    return allTasks.filter((t) => {
      // Status filter
      if (filterTab === "active" && t.status === "COMPLETED") return false;
      if (filterTab === "completed" && t.status !== "COMPLETED") return false;
      if (filterTab === "overdue" && (!t.is_overdue || t.status === "COMPLETED")) return false;

      // Search query filter
      if (query.trim()) {
        const q = query.toLowerCase();
        const projectName = t.project_id ? projectsMap.get(t.project_id) || "" : "";
        const matchTitle = t.title.toLowerCase().includes(q);
        const matchDesc = t.description ? t.description.toLowerCase().includes(q) : false;
        const matchProject = projectName.toLowerCase().includes(q);
        if (!matchTitle && !matchDesc && !matchProject) return false;
      }

      return true;
    });
  }, [allTasks, filterTab, query, projectsMap]);

  // Partition into the three primary domains (+ optional personal overflow)
  const startupTasks = useMemo(
    () => filteredTasks.filter((t) => t.area === "STARTUP"),
    [filteredTasks],
  );
  const internshipTasks = useMemo(
    () => filteredTasks.filter((t) => t.area === "INTERNSHIP"),
    [filteredTasks],
  );
  const collegeTasks = useMemo(
    () => filteredTasks.filter((t) => t.area === "COLLEGE"),
    [filteredTasks],
  );
  const personalTasks = useMemo(
    () => filteredTasks.filter((t) => t.area === "PERSONAL" || !t.area),
    [filteredTasks],
  );

  // Overall statistics
  const totalActive = allTasks.filter((t) => t.status !== "COMPLETED").length;
  const totalOverdue = allTasks.filter((t) => t.is_overdue && t.status !== "COMPLETED").length;
  const totalCompleted = allTasks.filter((t) => t.status === "COMPLETED").length;

  const handleOpenCreate = (area: LifeArea = "STARTUP") => {
    setDefaultArea(area);
    setCreateOpen(true);
  };

  return (
    <div className="space-y-6">
      {/* --- Page Header & Controls --- */}
      <header className="flex flex-col gap-4 border-b border-ops-line pb-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-baseline gap-3">
            <h1 className="font-[family-name:var(--font-display)] text-[24px] font-bold tracking-wide text-ink">
              TASKS
            </h1>
            <span className="font-[family-name:var(--font-telemetry)] text-[12px] text-ink-faint">
              {totalActive} active · {totalOverdue > 0 && <span className="text-critical">{totalOverdue} overdue · </span>}{totalCompleted} done
            </span>
          </div>

          <Button
            variant="go"
            size="sm"
            onClick={() => handleOpenCreate("STARTUP")}
            className="flex items-center gap-1.5 shadow-sm"
          >
            <Plus size={14} strokeWidth={2.5} />
            <span>Add Task</span>
          </Button>
        </div>

        {/* Filter Bar */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          {/* Quick Filters */}
          <div className="flex items-center gap-1.5 border border-ops-line bg-ops-panel/40 p-1">
            <FilterButton
              active={filterTab === "active"}
              label="Active"
              count={totalActive}
              onClick={() => setFilterTab("active")}
            />
            <FilterButton
              active={filterTab === "all"}
              label="All"
              count={allTasks.length}
              onClick={() => setFilterTab("all")}
            />
            <FilterButton
              active={filterTab === "overdue"}
              label="Overdue"
              count={totalOverdue}
              tone={totalOverdue > 0 ? "critical" : undefined}
              onClick={() => setFilterTab("overdue")}
            />
            <FilterButton
              active={filterTab === "completed"}
              label="Completed"
              count={totalCompleted}
              onClick={() => setFilterTab("completed")}
            />
          </div>

          {/* Search Box */}
          <div className="relative flex-1 sm:w-64 sm:flex-initial">
            <Search
              size={13}
              className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-faint"
            />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search tasks or projects…"
              aria-label="Search tasks"
              className="h-8 w-full pl-8 text-[13px]"
            />
          </div>
        </div>
      </header>

      {/* --- Main Content Grid --- */}
      {tasksQuery.isLoading ? (
        <div className="grid gap-5 md:grid-cols-2">
          <Skeleton className="h-64" />
          <Skeleton className="h-64" />
          <Skeleton className="h-64 md:col-span-2" />
        </div>
      ) : tasksQuery.error ? (
        <ErrorState message={(tasksQuery.error as Error).message} />
      ) : (
        <div className="space-y-6">
          {/* Top Row: STARTUP (Left) + INTERNSHIP (Right) */}
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            {/* 1. STARTUP SECTION */}
            <DomainSection
              title="STARTUP"
              subtitle="MARKETORY · NEXUS · Outreach · Distribution · Growth"
              tone="go"
              tasks={startupTasks}
              projectsMap={projectsMap}
              onAddTask={() => handleOpenCreate("STARTUP")}
              emptyMessage="No startup tasks yet."
              emptyHint="Add Marketory, NEXUS, outreach, or validation tasks."
            />

            {/* 2. INTERNSHIP SECTION */}
            <DomainSection
              title="INTERNSHIP"
              subtitle="AI Internship · Deliverables · Client Work · Reports"
              tone="caution"
              tasks={internshipTasks}
              projectsMap={projectsMap}
              onAddTask={() => handleOpenCreate("INTERNSHIP")}
              emptyMessage="No internship tasks yet."
              emptyHint="Add internship deliverables, client work, or sprint milestones."
            />
          </div>

          {/* Bottom Row: COLLEGE (Full Width) */}
          <div>
            <DomainSection
              title="COLLEGE"
              subtitle="Coursework · Compiler Design · Agentic AI · SPM · DSA · Exams"
              tone="ai"
              tasks={collegeTasks}
              projectsMap={projectsMap}
              onAddTask={() => handleOpenCreate("COLLEGE")}
              emptyMessage="No college tasks yet."
              emptyHint="Add assignments, lab submissions, exam preparation, or coursework."
            />
          </div>

          {/* Optional: PERSONAL OVERFLOW (if any tasks exist with personal area) */}
          {personalTasks.length > 0 && (
            <div className="border border-ops-line/60 bg-ops-panel/20 p-4">
              <div className="mb-3 flex items-center justify-between">
                <span className="font-[family-name:var(--font-display)] text-[13px] font-semibold uppercase tracking-wider text-ink-dim">
                  Personal & Administration ({personalTasks.length})
                </span>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => handleOpenCreate("PERSONAL")}
                  className="h-6 text-[11px]"
                >
                  <Plus size={12} /> Add
                </Button>
              </div>
              <ul className="divide-y divide-ops-line/60">
                {personalTasks.map((t) => (
                  <li key={t.id}>
                    <TaskItemRow task={t} projectsMap={projectsMap} />
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* --- Add Task Modal --- */}
      <CreateTaskDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        defaultArea={defaultArea}
      />
    </div>
  );
}

// --- Domain Section Component ------------------------------------------------

interface DomainSectionProps {
  title: string;
  subtitle: string;
  tone: "go" | "caution" | "ai" | "dim";
  tasks: TaskOut[];
  projectsMap: Map<number, string>;
  onAddTask: () => void;
  emptyMessage: string;
  emptyHint: string;
}

function DomainSection({
  title,
  subtitle,
  tone,
  tasks,
  projectsMap,
  onAddTask,
  emptyMessage,
  emptyHint,
}: DomainSectionProps) {
  const activeCount = tasks.filter((t) => t.status !== "COMPLETED").length;
  const overdueCount = tasks.filter((t) => t.is_overdue && t.status !== "COMPLETED").length;

  return (
    <section className="flex flex-col border border-ops-line bg-ops-panel/60 shadow-xs">
      {/* Section Header */}
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-ops-line bg-ops-raised/40 px-4 py-3">
        <div className="flex items-center gap-2.5">
          <Lamp tone={tone} />
          <div>
            <div className="flex items-center gap-2">
              <span className="font-[family-name:var(--font-display)] text-[15px] font-bold tracking-wider text-ink">
                {title}
              </span>
              <span className="font-[family-name:var(--font-telemetry)] text-[11px] text-ink-faint">
                ({activeCount} active{overdueCount > 0 && `, ${overdueCount} overdue`})
              </span>
            </div>
            <p className="hidden text-[11px] text-ink-faint sm:block">{subtitle}</p>
          </div>
        </div>

        <Button
          size="sm"
          variant="outline"
          onClick={onAddTask}
          className="h-7 gap-1 border-ops-line-bright px-2.5 text-[11px] hover:text-ink"
        >
          <Plus size={12} />
          <span>Add</span>
        </Button>
      </header>

      {/* Task List or Empty State */}
      <div className="flex-1 p-2 sm:p-3">
        {tasks.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-8 text-center">
            <p className="font-[family-name:var(--font-display)] text-[13px] text-ink-dim">
              {emptyMessage}
            </p>
            <p className="mt-1 text-[11px] text-ink-faint">{emptyHint}</p>
            <Button
              size="sm"
              variant="ghost"
              onClick={onAddTask}
              className="mt-3 text-[12px] text-caution hover:text-ink"
            >
              + Add {title.charAt(0) + title.slice(1).toLowerCase()} Task
            </Button>
          </div>
        ) : (
          <ul className="space-y-2">
            {tasks.map((task) => (
              <li key={task.id}>
                <TaskItemRow task={task} projectsMap={projectsMap} />
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

// --- Task Item Row Component -------------------------------------------------

function TaskItemRow({
  task,
  projectsMap,
}: {
  task: TaskOut;
  projectsMap: Map<number, string>;
}) {
  const complete = useCompleteTask();
  const updateTask = useUpdateTask();
  const del = useDeleteTask();

  const isDone = task.status === "COMPLETED";
  const isInProgress = task.status === "IN_PROGRESS";
  const urgency = task.deadline ? urgencyLabel(task.deadline) : null;
  const projectName = task.project_id ? projectsMap.get(task.project_id) : null;

  const handleToggle = () => {
    if (isDone) {
      // Re-open
      updateTask.mutate({
        id: task.id,
        patch: { status: "TODO" },
      });
    } else {
      // Complete
      complete.mutate({ id: task.id });
    }
  };

  return (
    <div
      className={cn(
        "group relative flex items-start gap-3 border border-ops-line/80 bg-ops-panel/40 p-2.5 transition-all",
        "hover:border-ops-line-bright hover:bg-ops-raised/40",
        isDone && "opacity-60 bg-ops-panel/20",
      )}
    >
      {/* Checkbox / Status Toggle */}
      <button
        onClick={handleToggle}
        aria-label={isDone ? `Reopen task "${task.title}"` : `Complete task "${task.title}"`}
        className={cn(
          "mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center border transition-colors",
          isDone
            ? "border-go bg-go-dim/40 text-go"
            : "border-ops-line-bright text-transparent hover:border-caution hover:text-caution/60",
        )}
      >
        {isDone ? <CheckCircle2 size={12} strokeWidth={2.5} /> : <Circle size={10} />}
      </button>

      {/* Task Content */}
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex items-baseline justify-between gap-2">
          <p
            className={cn(
              "text-[13px] leading-snug font-medium text-ink",
              isDone && "line-through text-ink-faint",
            )}
          >
            {task.title}
          </p>

          {/* Status Badge */}
          <span
            className={cn(
              "shrink-0 font-[family-name:var(--font-telemetry)] text-[10px] uppercase tracking-wider px-1.5 py-0.2",
              isDone
                ? "text-go bg-go-dim/30 border border-go-dim"
                : isInProgress
                  ? "text-caution bg-caution-dim/30 border border-caution-dim"
                  : "text-ink-faint border border-ops-line",
            )}
          >
            {task.status}
          </span>
        </div>

        {/* Task Metadata Row */}
        <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[11px] text-ink-faint">
          {/* Priority Lamp/Badge */}
          {(task.priority === "CRITICAL" || task.priority === "HIGH") && (
            <span
              className={cn(
                "inline-flex items-center gap-1 font-[family-name:var(--font-telemetry)] text-[10px] uppercase tracking-wider",
                task.priority === "CRITICAL" ? "text-critical font-bold" : "text-caution",
              )}
            >
              <Lamp tone={task.priority === "CRITICAL" ? "critical" : "caution"} pulse={!isDone} />
              {task.priority}
            </span>
          )}

          {/* Deadline / Urgency */}
          {urgency && (
            <span
              className={cn(
                "font-[family-name:var(--font-telemetry)] tnum flex items-center gap-1",
                task.is_overdue
                  ? "text-critical font-semibold"
                  : urgency.tone === "caution"
                    ? "text-caution"
                    : "text-ink-dim",
              )}
            >
              <Clock size={11} className="shrink-0" />
              {urgency.text}
            </span>
          )}

          {/* Duration */}
          {task.estimated_duration != null && task.estimated_duration > 0 && (
            <span className="font-[family-name:var(--font-telemetry)] tnum text-ink-dim">
              {humanDuration(task.estimated_duration)}
            </span>
          )}

          {/* Project Link */}
          {projectName && (
            <span className="flex items-center gap-1 border border-ops-line px-1 text-[10px] text-ink-dim">
              <FolderTree size={10} className="text-ai" />
              {projectName}
            </span>
          )}
        </div>

        {/* Description snippet if present */}
        {task.description && (
          <p className="line-clamp-1 text-[11px] text-ink-dim/80">{task.description}</p>
        )}
      </div>

      {/* Delete / Actions (Visible on hover/focus) */}
      <div className="shrink-0 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
        <button
          onClick={() => del.mutate(task.id)}
          aria-label={`Delete "${task.title}"`}
          title="Delete task"
          className="flex h-6 w-6 items-center justify-center text-ink-faint hover:text-critical transition-colors"
        >
          <Trash2 size={13} strokeWidth={1.5} />
        </button>
      </div>
    </div>
  );
}

// --- Filter Button -----------------------------------------------------------

function FilterButton({
  active,
  label,
  count,
  tone,
  onClick,
}: {
  active: boolean;
  label: string;
  count?: number;
  tone?: "critical" | "caution";
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "flex h-7 items-center gap-1.5 px-2.5 text-[11px] uppercase tracking-wider transition-colors",
        active
          ? "bg-ops-raised text-ink font-semibold border-b-2 border-caution"
          : "text-ink-dim hover:text-ink hover:bg-ops-panel",
        tone === "critical" && "text-critical",
      )}
    >
      <span>{label}</span>
      {count != null && (
        <span
          className={cn(
            "font-[family-name:var(--font-telemetry)] text-[10px] tnum",
            active ? "text-caution" : "text-ink-faint",
          )}
        >
          {count}
        </span>
      )}
    </button>
  );
}

// --- Create Task Dialog ------------------------------------------------------

export function CreateTaskDialog({
  open,
  onOpenChange,
  defaultArea = "STARTUP",
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  defaultArea?: LifeArea;
}) {
  const create = useCreateTask();
  const goals = useGoals();
  const projects = useProjects();

  const [form, setForm] = useState({
    title: "",
    description: "",
    area: defaultArea,
    priority: "MEDIUM" as TaskPriority,
    deadlineLocal: "",
    estimated_duration: "",
    energy_level: "",
    goal_id: "",
    project_id: "",
  });

  // Keep form area in sync with defaultArea prop when opened
  useMemo(() => {
    if (open) {
      setForm((f) => ({ ...f, area: defaultArea }));
    }
  }, [open, defaultArea]);

  const flatGoals = useMemo(() => flatten(goals.data ?? []), [goals.data]);

  const submit = () => {
    if (!form.title.trim()) return;
    create.mutate(
      {
        title: form.title.trim(),
        description: form.description || null,
        area: form.area,
        priority: form.priority,
        deadline: form.deadlineLocal ? new Date(form.deadlineLocal).toISOString() : null,
        estimated_duration: form.estimated_duration ? Number(form.estimated_duration) : null,
        energy_level: (form.energy_level || null) as never,
        goal_id: form.goal_id ? Number(form.goal_id) : null,
        project_id: form.project_id ? Number(form.project_id) : null,
      },
      {
        onSuccess: () => {
          onOpenChange(false);
          setForm({
            title: "",
            description: "",
            area: defaultArea,
            priority: "MEDIUM",
            deadlineLocal: "",
            estimated_duration: "",
            energy_level: "",
            goal_id: "",
            project_id: "",
          });
        },
      },
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="New task commitment">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
          className="space-y-4"
        >
          {/* Domain / Area Selector */}
          <div>
            <label className="label-caps mb-1.5 block text-[11px] text-ink-faint">
              Life / Work Domain
            </label>
            <div className="grid grid-cols-3 gap-2">
              <AreaOption
                selected={form.area === "STARTUP"}
                label="Startup"
                icon={<Rocket size={14} className="text-go" />}
                onClick={() => setForm({ ...form, area: "STARTUP" })}
              />
              <AreaOption
                selected={form.area === "INTERNSHIP"}
                label="Internship"
                icon={<Briefcase size={14} className="text-caution" />}
                onClick={() => setForm({ ...form, area: "INTERNSHIP" })}
              />
              <AreaOption
                selected={form.area === "COLLEGE"}
                label="College"
                icon={<GraduationCap size={14} className="text-ai" />}
                onClick={() => setForm({ ...form, area: "COLLEGE" })}
              />
            </div>
          </div>

          <Field label="Task Title">
            <Input
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
              placeholder={
                form.area === "COLLEGE"
                  ? "Compiler Design Lab Practical Submission"
                  : form.area === "INTERNSHIP"
                    ? "Client analytics report & model evaluation"
                    : "Reach out to 10 agency founders on LinkedIn"
              }
              required
              autoFocus
              maxLength={255}
            />
          </Field>

          <div className="grid grid-cols-2 gap-3">
            <Field label="Priority">
              <Select
                value={form.priority}
                onChange={(e) => setForm({ ...form, priority: e.target.value as TaskPriority })}
              >
                {TASK_PRIORITIES.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </Select>
            </Field>

            <Field label="Estimate (minutes)">
              <Input
                type="number"
                min={5}
                max={1440}
                step={5}
                value={form.estimated_duration}
                onChange={(e) => setForm({ ...form, estimated_duration: e.target.value })}
                placeholder="60"
              />
            </Field>

            <Field label="Deadline">
              <Input
                type="datetime-local"
                value={form.deadlineLocal}
                onChange={(e) => setForm({ ...form, deadlineLocal: e.target.value })}
              />
            </Field>

            <Field label="Project Container">
              <Select
                value={form.project_id}
                onChange={(e) => setForm({ ...form, project_id: e.target.value })}
              >
                <option value="">— None —</option>
                {(projects.data ?? []).map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} ({p.area})
                  </option>
                ))}
              </Select>
            </Field>

            <div className="col-span-2">
              <Field label="Strategic Goal Link">
                <Select
                  value={form.goal_id}
                  onChange={(e) => setForm({ ...form, goal_id: e.target.value })}
                >
                  <option value="">— None —</option>
                  {flatGoals.map((g) => (
                    <option key={g.id} value={g.id}>
                      {"· ".repeat(g.depth)}
                      {g.name}
                    </option>
                  ))}
                </Select>
              </Field>
            </div>
          </div>

          <Field label="Notes / Definition of Done">
            <Textarea
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              placeholder="Key requirements, links, checklist, notes…"
              rows={2}
            />
          </Field>

          <div className="flex justify-end gap-2 pt-2 border-t border-ops-line">
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button
              type="submit"
              variant="go"
              disabled={!form.title.trim() || create.isPending}
            >
              {create.isPending ? "Creating…" : "Commit Task"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function AreaOption({
  selected,
  label,
  icon,
  onClick,
}: {
  selected: boolean;
  label: string;
  icon: React.ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex items-center justify-center gap-2 border p-2 text-[12px] font-medium tracking-wide transition-colors",
        selected
          ? "border-caution bg-caution-dim/30 text-ink font-semibold"
          : "border-ops-line bg-ops-panel/60 text-ink-dim hover:text-ink hover:border-ops-line-bright",
      )}
    >
      {icon}
      <span>{label}</span>
    </button>
  );
}

interface FlatGoal {
  id: number;
  name: string;
  depth: number;
}
function flatten(
  nodes: { id: number; name: string; children?: unknown[] }[],
  depth = 0,
  acc: FlatGoal[] = [],
): FlatGoal[] {
  for (const n of nodes as { id: number; name: string; children?: never[] }[]) {
    acc.push({ id: n.id, name: n.name, depth });
    if (n.children?.length) flatten(n.children, depth + 1, acc);
  }
  return acc;
}
