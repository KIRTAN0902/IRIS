import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Check, Plus, Search, Trash2, X } from "lucide-react";
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
import { cn, humanDuration, parseUtc, urgencyLabel } from "@/lib/format";
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
  const [editing, setEditing] = useState<TaskOut | null>(null);

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
        <p className="mt-1 text-[12px] text-ink-faint md:hidden">
          Swipe right to complete · left to delete · tap to edit
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
                onEdit={setEditing}
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
      <TaskDialog
        open={editing !== null}
        onOpenChange={(v) => !v && setEditing(null)}
        task={editing}
      />
    </div>
  );
}

// --- Area section ------------------------------------------------------------------

function AreaSection({
  title,
  tasks,
  projectsMap,
  onAdd,
  onEdit,
}: {
  title: string;
  tasks: TaskOut[];
  projectsMap: Map<number, string>;
  onAdd: () => void;
  onEdit: (task: TaskOut) => void;
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
              <TaskItemRow task={task} projectsMap={projectsMap} onEdit={onEdit} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

// --- Checklist row -------------------------------------------------------------------

/** How far (as a fraction of the row's width) a swipe must travel to count. */
const SWIPE_COMMIT = 0.35;
const UNDO_MS = 4000;

function TaskItemRow({
  task,
  projectsMap,
  onEdit,
}: {
  task: TaskOut;
  projectsMap: Map<number, string>;
  onEdit: (task: TaskOut) => void;
}) {
  const complete = useCompleteTask();
  const updateTask = useUpdateTask();
  const del = useDeleteTask();

  const isDone = task.status === "COMPLETED";
  const urgency = task.deadline && !isDone ? urgencyLabel(task.deadline) : null;
  const projectName = task.project_id ? projectsMap.get(task.project_id) : null;
  const priority =
    task.priority === "CRITICAL" ? "Critical" : task.priority === "HIGH" ? "High priority" : null;

  // --- swipe (touch only): right = done/reopen, left = delete with undo ---
  const rowRef = useRef<HTMLDivElement>(null);
  const drag = useRef<{ x: number; y: number; axis: "x" | "y" | null } | null>(null);
  const swiped = useRef(false);
  const [dx, setDx] = useState(0);
  const [dragging, setDragging] = useState(false);
  const [pendingDelete, setPendingDelete] = useState(false);
  const deleteTimer = useRef<number | undefined>(undefined);
  const deleteNow = useRef(() => {});
  deleteNow.current = () => del.mutate(task.id, { onError: () => setPendingDelete(false) });

  // The row slides back once the task's status changes (e.g. in the "All" view).
  useEffect(() => setDx(0), [task.status]);
  // Leaving the page mid-undo still deletes the task.
  useEffect(
    () => () => {
      if (deleteTimer.current !== undefined) {
        window.clearTimeout(deleteTimer.current);
        deleteNow.current();
      }
    },
    [],
  );

  const toggle = () => {
    const reset = { onError: () => setDx(0) };
    if (isDone) updateTask.mutate({ id: task.id, patch: { status: "TODO" } }, reset);
    else complete.mutate({ id: task.id }, reset);
  };

  const startDelete = () => {
    setPendingDelete(true);
    setDx(0);
    deleteTimer.current = window.setTimeout(() => {
      deleteTimer.current = undefined;
      deleteNow.current();
    }, UNDO_MS);
  };

  const undoDelete = () => {
    window.clearTimeout(deleteTimer.current);
    deleteTimer.current = undefined;
    setPendingDelete(false);
  };

  const onPointerDown = (e: React.PointerEvent) => {
    if (e.pointerType !== "touch") return;
    drag.current = { x: e.clientX, y: e.clientY, axis: null };
    swiped.current = false;
  };

  const onPointerMove = (e: React.PointerEvent) => {
    const d = drag.current;
    if (!d) return;
    const mx = e.clientX - d.x;
    const my = e.clientY - d.y;
    if (d.axis === null) {
      if (Math.abs(mx) > 10 && Math.abs(mx) > Math.abs(my)) {
        d.axis = "x";
        setDragging(true);
        e.currentTarget.setPointerCapture(e.pointerId);
      } else if (Math.abs(my) > 10) {
        drag.current = null; // vertical: let the page scroll
        return;
      }
    }
    if (d.axis === "x") setDx(mx);
  };

  const onPointerEnd = (e: React.PointerEvent) => {
    const d = drag.current;
    drag.current = null;
    if (!d || d.axis !== "x") return;
    swiped.current = true;
    setDragging(false);
    const width = rowRef.current?.offsetWidth ?? 320;
    const mx = e.type === "pointercancel" ? 0 : e.clientX - d.x;
    if (mx > width * SWIPE_COMMIT) {
      setDx(width);
      window.setTimeout(toggle, 180);
    } else if (mx < -width * SWIPE_COMMIT) {
      setDx(-width);
      window.setTimeout(startDelete, 180);
    } else {
      setDx(0);
    }
  };

  const openEditor = () => {
    if (swiped.current) {
      swiped.current = false;
      return;
    }
    onEdit(task);
  };

  if (pendingDelete) {
    return (
      <div className="flex items-center gap-3 py-2.5 text-[14px] text-ink-faint">
        <Trash2 size={14} strokeWidth={1.75} className="shrink-0 text-critical" />
        <span className="min-w-0 flex-1 truncate">Deleted “{task.title}”</span>
        <button onClick={undoDelete} className="font-medium text-ink hover:underline cursor-pointer">
          Undo
        </button>
      </div>
    );
  }

  return (
    <div ref={rowRef} className="relative overflow-hidden">
      {/* Revealed behind the row while swiping */}
      {dx !== 0 && (
        <div
          aria-hidden
          className={cn(
            "absolute inset-0 flex items-center px-4 text-[13px] font-medium",
            dx > 0 ? "justify-start bg-go-dim text-go" : "justify-end bg-critical-dim text-critical",
          )}
        >
          {dx > 0 ? (
            <span className="flex items-center gap-1.5">
              <Check size={15} strokeWidth={2.5} /> {isDone ? "Reopen" : "Done"}
            </span>
          ) : (
            <span className="flex items-center gap-1.5">
              Delete <Trash2 size={15} strokeWidth={2} />
            </span>
          )}
        </div>
      )}
    <div
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerEnd}
      onPointerCancel={onPointerEnd}
      style={{
        transform: dx ? `translateX(${dx}px)` : undefined,
        transition: dragging ? "none" : "transform 180ms ease-out",
      }}
      className="group relative flex touch-pan-y items-start gap-3 bg-ops-ground py-2"
    >
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

      <div
        role="button"
        tabIndex={0}
        onClick={openEditor}
        onKeyDown={(e) => e.key === "Enter" && onEdit(task)}
        aria-label={`Edit "${task.title}"`}
        className="min-w-0 flex-1 cursor-pointer select-none"
      >
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
        onClick={startDelete}
        aria-label={`Delete "${task.title}"`}
        title="Delete"
        className="mt-0.5 rounded p-1 text-ink-faint opacity-0 transition-opacity hover:text-critical group-hover:opacity-100 focus-visible:opacity-100 cursor-pointer"
      >
        <Trash2 size={14} strokeWidth={1.75} />
      </button>
    </div>
    </div>
  );
}

// --- Task dialog (create + edit) -----------------------------------------------

/** ISO (naive UTC from the API) -> value for <input type="datetime-local">. */
function toLocalInput(iso: string | null): string {
  if (!iso) return "";
  const d = parseUtc(iso);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

function formFrom(task: TaskOut | null, defaultArea: LifeArea) {
  return {
    title: task?.title ?? "",
    description: task?.description ?? "",
    area: (task?.area ?? defaultArea) as LifeArea,
    priority: (task?.priority ?? "MEDIUM") as TaskPriority,
    deadlineLocal: toLocalInput(task?.deadline ?? null),
    estimated_duration: task?.estimated_duration ? String(task.estimated_duration) : "",
    goal_id: task?.goal_id ? String(task.goal_id) : "",
    project_id: task?.project_id ? String(task.project_id) : "",
  };
}

export function CreateTaskDialog(props: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  defaultArea?: LifeArea;
}) {
  return <TaskDialog {...props} task={null} />;
}

/** Creates a task, or edits `task` when one is given. */
export function TaskDialog({
  open,
  onOpenChange,
  task,
  defaultArea = "STARTUP",
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  task: TaskOut | null;
  defaultArea?: LifeArea;
}) {
  const create = useCreateTask();
  const update = useUpdateTask();
  const del = useDeleteTask();
  const goals = useGoals();
  const projects = useProjects();
  const editing = task !== null;

  const [form, setForm] = useState(() => formFrom(task, defaultArea));
  // Load the task (or a blank form) each time the dialog opens.
  useEffect(() => {
    if (open) setForm(formFrom(task, defaultArea));
  }, [open, task, defaultArea]);

  const flatGoals = useMemo(() => flatten(goals.data ?? []), [goals.data]);
  const pending = create.isPending || update.isPending;

  const submit = () => {
    if (!form.title.trim()) return;
    const body = {
      title: form.title.trim(),
      description: form.description.trim() || null,
      area: form.area,
      priority: form.priority,
      deadline: form.deadlineLocal ? new Date(form.deadlineLocal).toISOString() : null,
      estimated_duration: form.estimated_duration ? Number(form.estimated_duration) : null,
      goal_id: form.goal_id ? Number(form.goal_id) : null,
      project_id: form.project_id ? Number(form.project_id) : null,
    };
    const done = { onSuccess: () => onOpenChange(false) };
    if (task) update.mutate({ id: task.id, patch: body }, done);
    else create.mutate(body, done);
  };

  const remove = () => {
    if (!task || !window.confirm(`Delete "${task.title}"?`)) return;
    del.mutate(task.id, { onSuccess: () => onOpenChange(false) });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title={editing ? "Edit task" : "New task"}>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
          className="space-y-4"
        >
          <Field label="Title">
            <Input
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
              placeholder="What needs doing?"
              required
              autoFocus={!editing}
              maxLength={255}
            />
          </Field>

          <Field label="Description">
            <Textarea
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              placeholder="Notes, links, definition of done…"
              rows={3}
            />
          </Field>

          <div className="grid grid-cols-2 gap-3">
            <Field label="Deadline">
              <div className="flex items-center gap-1">
                <Input
                  type="datetime-local"
                  value={form.deadlineLocal}
                  onChange={(e) => setForm({ ...form, deadlineLocal: e.target.value })}
                />
                {form.deadlineLocal && (
                  <button
                    type="button"
                    onClick={() => setForm({ ...form, deadlineLocal: "" })}
                    aria-label="Clear deadline"
                    title="Clear deadline"
                    className="shrink-0 rounded p-1 text-ink-faint hover:text-ink cursor-pointer"
                  >
                    <X size={14} />
                  </button>
                )}
              </div>
            </Field>

            <Field label="Priority">
              <Select
                value={form.priority}
                onChange={(e) => setForm({ ...form, priority: e.target.value as TaskPriority })}
              >
                {TASK_PRIORITIES.map((p) => (
                  <option key={p} value={p}>
                    {p.charAt(0) + p.slice(1).toLowerCase()}
                  </option>
                ))}
              </Select>
            </Field>

            <Field label="Area">
              <Select value={form.area} onChange={(e) => setForm({ ...form, area: e.target.value as LifeArea })}>
                {AREAS.map(({ area, title }) => (
                  <option key={area} value={area}>
                    {title}
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

            <Field label="Project">
              <Select value={form.project_id} onChange={(e) => setForm({ ...form, project_id: e.target.value })}>
                <option value="">None</option>
                {(projects.data ?? []).map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </Select>
            </Field>

            <Field label="Goal">
              <Select value={form.goal_id} onChange={(e) => setForm({ ...form, goal_id: e.target.value })}>
                <option value="">None</option>
                {flatGoals.map((g) => (
                  <option key={g.id} value={g.id}>
                    {"· ".repeat(g.depth)}
                    {g.name}
                  </option>
                ))}
              </Select>
            </Field>
          </div>

          <div className="flex items-center gap-2 border-t border-ops-line pt-3">
            {editing && (
              <Button type="button" variant="ghost" onClick={remove} disabled={del.isPending}>
                <span className="text-critical">Delete</span>
              </Button>
            )}
            <div className="ml-auto flex gap-2">
              <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" variant="go" disabled={!form.title.trim() || pending}>
                {pending ? "Saving…" : editing ? "Save" : "Add task"}
              </Button>
            </div>
          </div>
        </form>
      </DialogContent>
    </Dialog>
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
