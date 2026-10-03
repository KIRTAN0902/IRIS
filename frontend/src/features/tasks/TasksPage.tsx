import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Briefcase, Check, GraduationCap, Plus, Rocket, Search, Trash2 } from "lucide-react";
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
import { cn, humanDuration, urgencyLabel } from "@/lib/format";
import { TASK_PRIORITIES, type LifeArea, type TaskPriority } from "@/types/api";

type FilterTab = "active" | "all" | "completed" | "overdue";

const AREAS: { area: LifeArea; title: string }[] = [
  { area: "STARTUP", title: "Startup" },
  { area: "INTERNSHIP", title: "Internship" },
  { area: "COLLEGE", title: "College" },
  { area: "PERSONAL", title: "Personal" },
];

/**
 * TASKS: one checklist, grouped by area, the way a notes app does it.
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
    for (const p of projects.data ?? []) map.set(p.id, p.name);
    return map;
  }, [projects.data]);

  const tasksQuery = useTasks({ limit: 300 });
  const allTasks = tasksQuery.data ?? [];

  const filteredTasks = useMemo(() => {
    const q = query.trim().toLowerCase();
    return allTasks.filter((t) => {
      if (filterTab === "active" && t.status === "COMPLETED") return false;
      if (filterTab === "completed" && t.status !== "COMPLETED") return false;
      if (filterTab === "overdue" && (!t.is_overdue || t.status === "COMPLETED")) return false;
      if (q) {
        const projectName = t.project_id ? projectsMap.get(t.project_id) || "" : "";
        return [t.title, t.description ?? "", projectName].some((s) => s.toLowerCase().includes(q));
      }
      return true;
    });
  }, [allTasks, filterTab, query, projectsMap]);

  const totalActive = allTasks.filter((t) => t.status !== "COMPLETED").length;
  const totalOverdue = allTasks.filter((t) => t.is_overdue && t.status !== "COMPLETED").length;
  const totalCompleted = allTasks.filter((t) => t.status === "COMPLETED").length;

  const openCreate = (area: LifeArea = "STARTUP") => {
    setDefaultArea(area);
    setCreateOpen(true);
  };

  const tabs: { id: FilterTab; label: string; count: number }[] = [
    { id: "active", label: "Open", count: totalActive },
    { id: "overdue", label: "Overdue", count: totalOverdue },
    { id: "completed", label: "Done", count: totalCompleted },
    { id: "all", label: "All", count: allTasks.length },
  ];

  return (
    <div className="mx-auto w-full max-w-[680px]">
      <header className="mb-6">
        <div className="flex items-end justify-between gap-3">
          <h1 className="text-[30px] font-bold leading-tight tracking-[-0.02em] text-ink">Tasks</h1>
          <button
            onClick={() => openCreate("STARTUP")}
            className="mb-1 inline-flex items-center gap-1 text-[14px] text-ai hover:underline cursor-pointer"
          >
            <Plus size={14} /> New task
          </button>
        </div>
        <p className="mt-1 text-[14px] text-ink-faint">
          {totalActive} open
          {totalOverdue > 0 && <span className="text-critical"> · {totalOverdue} overdue</span>} · {totalCompleted} done
        </p>

        <div className="mt-5 flex flex-wrap items-center gap-x-5 gap-y-3">
          <nav className="flex items-center gap-4 text-[14px]" aria-label="Filter tasks">
            {tabs.map((t) => (
              <button
                key={t.id}
                onClick={() => setFilterTab(t.id)}
                className={cn(
                  "cursor-pointer transition-colors",
                  filterTab === t.id ? "font-medium text-ink" : "text-ink-faint hover:text-ink-dim",
                )}
              >
                {t.label}
                <span className="ml-1 text-[12px] text-ink-faint tnum">{t.count}</span>
              </button>
            ))}
          </nav>
          <label className="ml-auto flex min-w-[180px] flex-1 items-center gap-2 sm:max-w-[240px]">
            <Search size={14} className="shrink-0 text-ink-faint" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search"
              aria-label="Search tasks"
              className="w-full bg-transparent text-[14px] text-ink placeholder:text-ink-faint focus:outline-none"
            />
          </label>
        </div>
      </header>

      {tasksQuery.isLoading ? (
        <div className="space-y-3">
          <Skeleton className="h-5 w-1/4" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-5/6" />
        </div>
      ) : tasksQuery.error ? (
        <ErrorState message={(tasksQuery.error as Error).message} />
      ) : (
        <div className="space-y-9">
          {AREAS.map(({ area, title }) => {
            const tasks = filteredTasks.filter((t) => (t.area || "PERSONAL") === area);
            if (tasks.length === 0 && (filterTab !== "active" || area === "PERSONAL" || query)) return null;
            return (
              <AreaSection
                key={area}
                title={title}
                tasks={tasks}
                projectsMap={projectsMap}
                onAdd={() => openCreate(area)}
              />
            );
          })}
          {filteredTasks.length === 0 && (filterTab !== "active" || query) && (
            <p className="text-[15px] text-ink-faint">
              {query ? "No tasks match your search." : "Nothing here."}
            </p>
          )}
        </div>
      )}

      <CreateTaskDialog open={createOpen} onOpenChange={setCreateOpen} defaultArea={defaultArea} />
    </div>
  );
}

// --- Area section ------------------------------------------------------------------

function AreaSection({
  title,
  tasks,
  projectsMap,
  onAdd,
}: {
  title: string;
  tasks: TaskOut[];
  projectsMap: Map<number, string>;
  onAdd: () => void;
}) {
  const overdue = tasks.filter((t) => t.is_overdue && t.status !== "COMPLETED").length;
  return (
    <section className="group/section">
      <header className="mb-1 flex items-baseline gap-2 border-b border-ops-line pb-1.5">
        <h2 className="text-[17px] font-semibold text-ink">{title}</h2>
        <span className="text-[13px] text-ink-faint tnum">
          {tasks.length}
          {overdue > 0 && <span className="text-critical"> · {overdue} overdue</span>}
        </span>
        <button
          onClick={onAdd}
          aria-label={`Add ${title} task`}
          title={`Add ${title} task`}
          className="ml-auto rounded p-0.5 text-ink-faint opacity-0 transition-opacity hover:text-ink group-hover/section:opacity-100 focus-visible:opacity-100 cursor-pointer"
        >
          <Plus size={16} />
        </button>
      </header>
      {tasks.length === 0 ? (
        <button onClick={onAdd} className="py-2 text-[14px] text-ink-faint hover:text-ink-dim cursor-pointer">
          No tasks. Add one…
        </button>
      ) : (
        <ul>
          {tasks.map((task) => (
            <li key={task.id}>
              <TaskItemRow task={task} projectsMap={projectsMap} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

// --- Checklist row -------------------------------------------------------------------

function TaskItemRow({ task, projectsMap }: { task: TaskOut; projectsMap: Map<number, string> }) {
  const complete = useCompleteTask();
  const updateTask = useUpdateTask();
  const del = useDeleteTask();

  const isDone = task.status === "COMPLETED";
  const urgency = task.deadline && !isDone ? urgencyLabel(task.deadline) : null;
  const projectName = task.project_id ? projectsMap.get(task.project_id) : null;
  const priority =
    task.priority === "CRITICAL" ? "Critical" : task.priority === "HIGH" ? "High priority" : null;

  const toggle = () =>
    isDone ? updateTask.mutate({ id: task.id, patch: { status: "TODO" } }) : complete.mutate({ id: task.id });

  return (
    <div className="group flex items-start gap-3 py-2">
      <button
        onClick={toggle}
        aria-label={isDone ? `Reopen "${task.title}"` : `Mark "${task.title}" done`}
        className={cn(
          "mt-[3px] flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-full border-[1.5px] transition-colors cursor-pointer",
          isDone ? "border-go bg-go text-ops-ground" : "border-ops-line-bright hover:border-go hover:bg-go-dim",
        )}
      >
        {isDone && <Check size={11} strokeWidth={3} />}
      </button>

      <div className="min-w-0 flex-1">
        <p className={cn("text-[15px] leading-snug", isDone ? "text-ink-faint line-through" : "text-ink")}>
          {task.title}
          {task.status === "IN_PROGRESS" && <span className="ml-2 text-[12px] text-ai">in progress</span>}
          {task.status === "BLOCKED" && <span className="ml-2 text-[12px] text-caution">blocked</span>}
        </p>
        <p className="mt-0.5 flex flex-wrap items-center gap-x-2.5 text-[12px] text-ink-faint">
          {urgency && (
            <span
              className={cn(
                "tnum",
                task.is_overdue ? "text-critical" : urgency.tone === "caution" ? "text-caution" : undefined,
              )}
            >
              {urgency.text}
            </span>
          )}
          {priority && (
            <span className={task.priority === "CRITICAL" ? "text-critical" : undefined}>{priority}</span>
          )}
          {task.estimated_duration != null && task.estimated_duration > 0 && (
            <span className="tnum">{humanDuration(task.estimated_duration)}</span>
          )}
          {projectName && <span className="truncate">{projectName}</span>}
        </p>
        {task.description && !isDone && (
          <p className="mt-0.5 line-clamp-1 text-[13px] text-ink-faint">{task.description}</p>
        )}
      </div>

      <button
        onClick={() => del.mutate(task.id)}
        aria-label={`Delete "${task.title}"`}
        title="Delete"
        className="mt-0.5 rounded p-1 text-ink-faint opacity-0 transition-opacity hover:text-critical group-hover:opacity-100 focus-visible:opacity-100 cursor-pointer"
      >
        <Trash2 size={14} strokeWidth={1.75} />
      </button>
    </div>
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
        "flex items-center justify-center gap-2 border p-2 text-[12px] font-medium transition-colors",
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
