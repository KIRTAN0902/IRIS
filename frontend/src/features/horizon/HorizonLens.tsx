import { lazy, Suspense } from "react";
import {
  Calendar,
  CheckCircle2,
  Compass,
  CreditCard,
  Dumbbell,
  FolderGit2,
  ListTodo,
  Play,
  Repeat,
  BookOpen,
} from "lucide-react";
import {
  useCheckHabit,
  useHabits,
  useSituation,
  useCompleteTask,
  useStartFocus,
  useCompleteFocus,
} from "@/hooks/queries";
import { useFocusStore } from "@/stores";
import { useLensStore } from "@/stores/lensStore";
import { cn } from "@/lib/format";

// Sub-pages for direct tabs
const TasksPage = lazy(() => import("@/features/tasks/TasksPage").then((m) => ({ default: m.TasksPage })));
const SchedulePage = lazy(() => import("@/features/schedule/SchedulePage").then((m) => ({ default: m.SchedulePage })));
const ProjectsPage = lazy(() => import("@/features/projects/ProjectsPage").then((m) => ({ default: m.ProjectsPage })));
const FinancePage = lazy(() => import("@/features/finance/FinancePage").then((m) => ({ default: m.FinancePage })));
const WorkoutsPage = lazy(() => import("@/features/gym/WorkoutsPage").then((m) => ({ default: m.WorkoutsPage })));
const DiaryPage = lazy(() => import("@/features/diary/DiaryPage").then((m) => ({ default: m.DiaryPage })));
const TodayPage = lazy(() => import("@/features/today/TodayPage").then((m) => ({ default: m.TodayPage })));

export function HorizonLens() {
  const { horizonTab, setHorizonTab } = useLensStore();

  return (
    <div className="flex h-[calc(100vh-3.5rem)] w-full flex-col overflow-hidden">
      {/* 1. Horizon Sub-Navigation Bar */}
      <div className="flex h-12 shrink-0 items-center justify-between border-b border-ops-line/80 px-4 md:px-6 bg-ops-panel/60 backdrop-blur-xs">
        <div className="flex items-center gap-1 overflow-x-auto scrollbar-none py-1">
          <TabButton
            active={horizonTab === "overview"}
            onClick={() => setHorizonTab("overview")}
            label="Overview"
            icon={Compass}
          />
          <TabButton
            active={horizonTab === "priorities"}
            onClick={() => setHorizonTab("priorities")}
            label="Priorities"
            icon={ListTodo}
          />
          <TabButton
            active={horizonTab === "schedule"}
            onClick={() => setHorizonTab("schedule")}
            label="Schedule"
            icon={Calendar}
          />
          <TabButton
            active={horizonTab === "routines"}
            onClick={() => setHorizonTab("routines")}
            label="Routines"
            icon={Repeat}
          />
          <TabButton
            active={horizonTab === "projects"}
            onClick={() => setHorizonTab("projects")}
            label="Projects"
            icon={FolderGit2}
          />
          <TabButton
            active={horizonTab === "finance"}
            onClick={() => setHorizonTab("finance")}
            label="Finance"
            icon={CreditCard}
          />
          <TabButton
            active={horizonTab === "fitness"}
            onClick={() => setHorizonTab("fitness")}
            label="Fitness"
            icon={Dumbbell}
          />
          <TabButton
            active={horizonTab === "diary"}
            onClick={() => setHorizonTab("diary")}
            label="Diary"
            icon={BookOpen}
          />
        </div>
      </div>

      {/* 2. Content Canvas */}
      <div className="flex-1 overflow-y-auto p-4 md:p-6">
        <Suspense fallback={<div className="text-xs text-ink-faint animate-pulse">Loading Horizon view…</div>}>
          {horizonTab === "overview" && <HorizonOverview onSelectTab={setHorizonTab} />}
          {horizonTab === "priorities" && <TasksPage />}
          {horizonTab === "schedule" && <SchedulePage />}
          {horizonTab === "routines" && <TodayPage />}
          {horizonTab === "projects" && <ProjectsPage />}
          {horizonTab === "finance" && <FinancePage />}
          {horizonTab === "fitness" && <WorkoutsPage />}
          {horizonTab === "diary" && <DiaryPage />}
        </Suspense>
      </div>
    </div>
  );
}

function TabButton({
  active,
  onClick,
  label,
  icon: Icon,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
  icon: typeof Compass;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-medium transition cursor-pointer whitespace-nowrap",
        active
          ? "bg-ops-raised text-ink font-semibold border border-ops-line-bright shadow-2xs"
          : "text-ink-faint hover:text-ink hover:bg-ops-raised/50",
      )}
    >
      <Icon size={13} className={active ? "text-ai" : "opacity-70"} />
      <span>{label}</span>
    </button>
  );
}

// --- Overview Dashboard -------------------------------------------------------------

function HorizonOverview({
  onSelectTab,
}: {
  onSelectTab: (tab: "overview" | "priorities" | "schedule" | "routines" | "projects" | "finance" | "fitness" | "diary") => void;
}) {
  const situation = useSituation();
  const habits = useHabits();
  const checkHabit = useCheckHabit();
  const completeTask = useCompleteTask();
  const runningFocus = useFocusStore((s) => s.running);
  const startFocus = useStartFocus();
  const completeFocus = useCompleteFocus();

  const s = situation.data;
  const nowBlock = s?.now?.current_block;
  const nextCommitment = s?.now?.next_commitment;

  const urgentTasks = [
    ...(s?.tasks.overdue ?? []),
    ...(s?.tasks.in_progress ?? []),
    ...(s?.tasks.due_today ?? []),
  ].slice(0, 5);

  const habitsToday = (habits.data ?? []).filter((h) => h.active && h.scheduled_today);
  const habitsDone = habitsToday.filter((h) => h.done_today).length;
  const habitsTotal = habitsToday.length;

  return (
    <div className="mx-auto max-w-6xl space-y-6 pb-12">
      {/* 1. Now & Temporal Horizon Banner */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Now & Next Block */}
        <div className="md:col-span-2 rounded-2xl border border-ops-line bg-ops-panel p-5 shadow-xs space-y-4">
          <div className="flex items-start justify-between">
            <div>
              <span className="text-[10px] font-bold uppercase tracking-wider text-ai">
                Active Horizon
              </span>
              <h2 className="text-xl font-bold text-ink mt-0.5">
                {nowBlock || "No current calendar block"}
              </h2>
              {nextCommitment && (
                <p className="text-xs text-ink-dim mt-1">
                  Next commitment: <span className="font-medium text-ink">{nextCommitment}</span>
                </p>
              )}
            </div>

            {/* Focus Session Trigger */}
            {runningFocus ? (
              <button
                type="button"
                onClick={() => completeFocus.mutate({ id: runningFocus.id })}
                className="inline-flex items-center gap-1.5 rounded-xl bg-critical text-white px-3 py-1.5 text-xs font-semibold hover:bg-critical/90 shadow-xs cursor-pointer animate-pulse"
              >
                <span>End Focus Session</span>
              </button>
            ) : (
              <button
                type="button"
                onClick={() =>
                  startFocus.mutate({
                    planned_duration: 25,
                    notes: "Focus session started from Horizon",
                  })
                }
                className="inline-flex items-center gap-1.5 rounded-xl bg-ai text-white px-3 py-1.5 text-xs font-semibold hover:bg-ai/90 shadow-xs cursor-pointer"
              >
                <Play size={12} className="fill-current" />
                <span>25m Focus</span>
              </button>
            )}
          </div>

          <div className="flex items-center justify-between border-t border-ops-line/60 pt-3 text-xs text-ink-faint">
            <span>{s?.now?.local_time ? `Local Time: ${s.now.local_time}` : "Temporal Sync Active"}</span>
            <button
              type="button"
              onClick={() => onSelectTab("schedule")}
              className="font-medium text-ai hover:underline cursor-pointer"
            >
              Open Full Schedule →
            </button>
          </div>
        </div>

        {/* Day Cadence & Progress */}
        <div className="rounded-2xl border border-ops-line bg-ops-panel p-5 shadow-xs flex flex-col justify-between">
          <div>
            <span className="text-[10px] font-bold uppercase tracking-wider text-ink-faint">
              Routines Cadence
            </span>
            <h3 className="text-2xl font-bold text-ink mt-1">
              {habitsTotal ? Math.round((habitsDone / habitsTotal) * 100) : 100}%
            </h3>
            <p className="text-xs text-ink-dim mt-0.5">
              {habitsDone} of {habitsTotal} routines completed today
            </p>
          </div>

          <div className="space-y-2 pt-4">
            <div className="h-2 w-full rounded-full bg-ops-raised overflow-hidden">
              <div
                className="h-full rounded-full bg-emerald-500 transition-all duration-300"
                style={{ width: `${habitsTotal ? (habitsDone / habitsTotal) * 100 : 100}%` }}
              />
            </div>
            <button
              type="button"
              onClick={() => onSelectTab("routines")}
              className="text-xs font-medium text-ai hover:underline cursor-pointer block text-right"
            >
              View Routines →
            </button>
          </div>
        </div>
      </div>

      {/* 2. Dual Stage: High-Impact Priorities & Habits Today */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Priorities Section */}
        <section className="rounded-2xl border border-ops-line bg-ops-panel p-5 shadow-xs space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <ListTodo size={17} className="text-ai" />
              <h3 className="text-base font-bold text-ink">Urgent Priorities</h3>
            </div>
            <button
              type="button"
              onClick={() => onSelectTab("priorities")}
              className="text-xs text-ai font-medium hover:underline cursor-pointer"
            >
              All Tasks →
            </button>
          </div>

          {urgentTasks.length === 0 ? (
            <p className="py-8 text-center text-xs text-ink-faint">
              No urgent tasks right now. You're completely caught up.
            </p>
          ) : (
            <div className="space-y-2">
              {urgentTasks.map((t) => (
                <div
                  key={t.id}
                  className="group flex items-center justify-between rounded-xl bg-ops-void p-3 border border-ops-line/80 hover:border-ai/40 transition"
                >
                  <div className="flex items-center gap-2.5 min-w-0 flex-1">
                    <button
                      type="button"
                      onClick={() => completeTask.mutate({ id: t.id })}
                      className="h-5 w-5 rounded-md border border-ops-line-bright flex items-center justify-center text-transparent hover:text-emerald-500 hover:border-emerald-500 transition cursor-pointer shrink-0"
                    >
                      <CheckCircle2 size={14} />
                    </button>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-ink truncate">{t.title}</p>
                      <span className="text-[10px] text-ink-faint font-medium uppercase tracking-wider">
                        {t.area || "Task"}
                      </span>
                    </div>
                  </div>
                  {t.priority && (
                    <span className="rounded-full bg-ai/10 px-2 py-0.5 text-[10px] font-semibold text-ai shrink-0">
                      {t.priority}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>

        {/* Habits Today Section */}
        <section className="rounded-2xl border border-ops-line bg-ops-panel p-5 shadow-xs space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Repeat size={17} className="text-emerald-500" />
              <h3 className="text-base font-bold text-ink">Daily Routines</h3>
            </div>
            <button
              type="button"
              onClick={() => onSelectTab("routines")}
              className="text-xs text-ai font-medium hover:underline cursor-pointer"
            >
              Manage →
            </button>
          </div>

          {habitsToday.length === 0 ? (
            <p className="py-8 text-center text-xs text-ink-faint">
              No routines scheduled for today.
            </p>
          ) : (
            <div className="space-y-2">
              {habitsToday.map((h) => (
                <div
                  key={h.id}
                  className="flex items-center justify-between rounded-xl bg-ops-void p-3 border border-ops-line/80"
                >
                  <div className="flex items-center gap-2.5 min-w-0 flex-1">
                    <button
                      type="button"
                      onClick={() => checkHabit.mutate({ id: h.id, done: !h.done_today })}
                      className={cn(
                        "h-6 w-6 rounded-full border flex items-center justify-center transition cursor-pointer shrink-0",
                        h.done_today
                          ? "bg-emerald-500 border-emerald-500 text-white"
                          : "border-ops-line-bright text-transparent hover:border-ai",
                      )}
                    >
                      <CheckCircle2 size={14} />
                    </button>
                    <span
                      className={cn(
                        "text-sm font-medium truncate",
                        h.done_today ? "line-through text-ink-faint" : "text-ink",
                      )}
                    >
                      {h.name}
                    </span>
                  </div>
                  {h.streak > 0 && (
                    <span className="rounded-full bg-amber-500/10 text-amber-500 px-2 py-0.5 text-[10px] font-bold">
                      🔥 {h.streak}d
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
