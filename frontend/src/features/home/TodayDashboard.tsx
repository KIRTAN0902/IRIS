import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Check, ChevronRight, Dumbbell, Flame, Plus } from "lucide-react";
import {
  useCheckHabit,
  useCompleteTask,
  useFinanceSummary,
  useHabits,
  useMe,
  useSituation,
  useWorkouts,
} from "@/hooks/queries";
import { Skeleton } from "@/components/ui/Overlay";
import { cn } from "@/lib/format";
import type { HabitOut, Situation, SituationTask, WorkoutOut } from "@/types/api";
import { inr } from "@/features/finance/money";
import { RoutineDialog } from "@/features/home/RoutineDialog";

/**
 * TODAY: the home screen. How the day is going, what's now and next, routines
 * to tick off, tasks left, and money - with IRIS one message away below.
 */

const SUGGESTED_ROUTINES = [
  { name: "Gym" },
  { name: "Yoga", time: "06:00" },
  { name: "Reading" },
  { name: "Meditation" },
  { name: "Walk" },
];

const minutes = (hhmm: string) => {
  const [h, m] = hhmm.split(":").map(Number);
  return h * 60 + m;
};

function greeting() {
  const h = new Date().getHours();
  return h >= 4 && h < 12 ? "Good morning" : h >= 12 && h < 17 ? "Good afternoon" : "Good evening";
}

/** Share of the waking day that has passed: from the end of sleep to bedtime. */
function wakingDay(s: Situation): number | null {
  const sleep = s.today_schedule.find((i) => /sleep/i.test(i.title));
  const bedtime = s.now.sleep_time ?? sleep?.start;
  const wake = sleep?.end ?? s.today_schedule[0]?.start;
  if (!bedtime || !wake) return null;
  const now = new Date();
  const cur = now.getHours() * 60 + now.getMinutes();
  let start = minutes(wake);
  let end = minutes(bedtime);
  if (end <= start) end += 24 * 60;
  const at = cur < start ? cur + 24 * 60 : cur;
  return Math.min(1, Math.max(0, (at - start) / (end - start)));
}

export function TodayDashboard() {
  const situation = useSituation();
  const habits = useHabits();
  const me = useMe();
  const workouts = useWorkouts();
  const now = useClock();
  const s = situation.data;

  if (situation.isLoading || !s) {
    return (
      <div className="space-y-4 pt-2">
        <Skeleton className="h-8 w-2/3" />
        <Skeleton className="h-28 w-full" />
        <Skeleton className="h-4 w-5/6" />
        <Skeleton className="h-4 w-3/4" />
      </div>
    );
  }

  const today = (habits.data ?? []).filter((h) => h.active && h.scheduled_today);
  const tasks = dedupe([...s.tasks.overdue, ...s.tasks.in_progress, ...s.tasks.due_today]);
  const routinesDone = today.filter((h) => h.done_today).length;
  const tasksDone = s.done.today.length;
  const total = today.length + tasks.length + tasksDone;
  const done = routinesDone + tasksDone;
  const firstName = me.data?.name?.split(" ")[0];
  const focus = spotlight(today, now);
  const workoutInSpotlight = !!focus && WORKOUT_ROUTINE.test(focus.habit.name) && (workouts.data ?? []).some((w) => w.is_today);

  return (
    <div className="pb-6">
      <header>
        <h1 className="text-[26px] font-semibold leading-tight text-ink">
          {greeting()}
          {firstName ? `, ${firstName}` : ""}
        </h1>
        <p className="mt-0.5 text-[14px] text-ink-faint">{s.now.local_time}</p>
      </header>

      <DayProgress done={done} total={total} routines={[routinesDone, today.length]} tasks={[tasksDone, tasks.length + tasksDone]} day={wakingDay(s)} />

      <NowNext s={s} />

      <Routines habits={habits.data ?? []} loading={habits.isLoading} workouts={workouts.data ?? []} now={now} />

      {!workoutInSpotlight && <TodaysWorkout />}

      <Tasks tasks={tasks} doneToday={s.done.today} />

      <Schedule items={s.today_schedule} />

      <Money />
    </div>
  );
}

function dedupe(list: SituationTask[]) {
  const seen = new Set<number>();
  return list.filter((t) => !seen.has(t.id) && seen.add(t.id));
}

// --- Progress ------------------------------------------------------------------------

function Ring({ fraction }: { fraction: number }) {
  const r = 34;
  const c = 2 * Math.PI * r;
  return (
    <svg width="84" height="84" viewBox="0 0 84 84" className="shrink-0 -rotate-90" aria-hidden>
      <circle cx="42" cy="42" r={r} fill="none" stroke="var(--color-ops-raised)" strokeWidth="7" />
      <circle
        cx="42"
        cy="42"
        r={r}
        fill="none"
        stroke="var(--color-ink)"
        strokeWidth="7"
        strokeLinecap="round"
        strokeDasharray={`${c * fraction} ${c}`}
        style={{ filter: "drop-shadow(0 0 6px rgba(255,255,255,0.45))", transition: "stroke-dasharray 400ms ease-out" }}
      />
    </svg>
  );
}

function DayProgress({
  done,
  total,
  routines,
  tasks,
  day,
}: {
  done: number;
  total: number;
  routines: [number, number];
  tasks: [number, number];
  day: number | null;
}) {
  const fraction = total ? done / total : 0;
  return (
    <section className="mt-5 rounded-2xl border border-ops-line-bright bg-ops-panel p-4" aria-label="Today's progress">
      <div className="flex items-center gap-4">
        <div className="relative">
          <Ring fraction={fraction} />
          <span className="tnum absolute inset-0 flex items-center justify-center text-[17px] font-semibold text-ink">
            {Math.round(fraction * 100)}%
          </span>
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-[17px] font-semibold text-ink">
            {total ? `${done} of ${total} done` : "Nothing planned yet"}
          </p>
          <p className="mt-1 text-[13px] text-ink-faint">
            Routines {routines[0]}/{routines[1]} · Tasks {tasks[0]}/{tasks[1]}
          </p>
          {day !== null && (
            <div className="mt-2.5">
              <div className="h-1 overflow-hidden rounded-full bg-ops-raised">
                <div className="h-full rounded-full bg-ink-faint" style={{ width: `${day * 100}%` }} />
              </div>
              <p className="mt-1 text-[11px] text-ink-faint">{Math.round(day * 100)}% of your waking day gone</p>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

// --- Now / next -------------------------------------------------------------------------

function NowNext({ s }: { s: Situation }) {
  const now = s.today_schedule.find((i) => i.status === "now");
  const next = s.today_schedule.find((i) => i.status === "upcoming" && !/sleep/i.test(i.title));
  if (!now && !next) return null;
  return (
    <section className="mt-3 grid grid-cols-2 gap-3">
      <div className="rounded-2xl border border-ops-line bg-ops-panel px-4 py-3">
        <p className="text-[11px] uppercase tracking-[0.18em] text-ink-faint">Now</p>
        <p className="mt-1 truncate text-[15px] font-medium text-ink">{now?.title ?? "Free time"}</p>
        <p className="tnum text-[12px] text-ink-faint">
          {now ? (s.now.minutes_left_in_block != null ? `${s.now.minutes_left_in_block} min left` : `until ${now.end}`) : ""}
        </p>
      </div>
      <div className="rounded-2xl border border-ops-line bg-ops-panel px-4 py-3">
        <p className="text-[11px] uppercase tracking-[0.18em] text-ink-faint">Next</p>
        <p className="mt-1 truncate text-[15px] font-medium text-ink">{next?.title ?? "Nothing else"}</p>
        <p className="tnum text-[12px] text-ink-faint">{next ? `at ${next.start}` : ""}</p>
      </div>
    </section>
  );
}

// --- Sections ---------------------------------------------------------------------------

function Section({ title, meta, action, children }: { title: string; meta?: string; action?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="mt-8">
      <header className="mb-2 flex items-baseline gap-2 border-b border-ops-line pb-1.5">
        <h2 className="text-[17px] font-semibold text-ink">{title}</h2>
        {meta && <span className="tnum text-[13px] text-ink-faint">{meta}</span>}
        <div className="ml-auto">{action}</div>
      </header>
      {children}
    </section>
  );
}

function CheckCircle({ done, onClick, label }: { done: boolean; onClick: () => void; label: string }) {
  return (
    <button
      onClick={onClick}
      aria-label={label}
      aria-pressed={done}
      className={cn(
        "flex h-[22px] w-[22px] shrink-0 items-center justify-center rounded-full border-[1.5px] transition-colors cursor-pointer",
        done ? "border-ink bg-ink text-ops-ground shadow-[0_0_10px_rgba(255,255,255,0.35)]" : "border-ops-line-bright hover:border-ink",
      )}
    >
      {done && <Check size={13} strokeWidth={3} />}
    </button>
  );
}

// --- Routines ----------------------------------------------------------------------------

/** Minutes since midnight, re-read every 30s so "now" moves with the clock. */
function useClock() {
  const read = () => {
    const d = new Date();
    return d.getHours() * 60 + d.getMinutes();
  };
  const [now, setNow] = useState(read);
  useEffect(() => {
    const t = setInterval(() => setNow(read()), 30_000);
    return () => clearInterval(t);
  }, []);
  return now;
}

/** Routines without a set duration count as "now" for this long. */
const DEFAULT_ROUTINE_MIN = 30;
const WORKOUT_ROUTINE = /gym|workout|lift|training|exercise/i;

function routineWindow(h: HabitOut): [number, number] | null {
  if (!h.time) return null;
  const start = minutes(h.time);
  return [start, start + (h.duration_min ?? DEFAULT_ROUTINE_MIN)];
}

const hhmm = (m: number) => `${String(Math.floor(m / 60) % 24).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;

function timeRange(h: HabitOut) {
  const w = routineWindow(h);
  if (!w) return null;
  return h.duration_min ? `${hhmm(w[0])}–${hhmm(w[1])}` : hhmm(w[0]);
}

function inHowLong(mins: number) {
  if (mins < 60) return `in ${mins} min`;
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return `in ${h}h${m ? ` ${m}m` : ""}`;
}

/** The routine happening now (by its time and duration), else the next one still to do. */
function spotlight(today: HabitOut[], now: number): { habit: HabitOut; mode: "now" | "next"; startsIn: number } | null {
  const timed = today.filter((h) => h.time).sort((x, y) => minutes(x.time!) - minutes(y.time!));
  const current = timed.find((h) => {
    const [start, end] = routineWindow(h)!;
    return now >= start && now < end;
  });
  if (current) return { habit: current, mode: "now", startsIn: 0 };
  const next = timed.find((h) => !h.done_today && minutes(h.time!) > now);
  return next ? { habit: next, mode: "next", startsIn: minutes(next.time!) - now } : null;
}

function Routines({ habits, loading, workouts, now }: { habits: HabitOut[]; loading: boolean; workouts: WorkoutOut[]; now: number }) {
  const check = useCheckHabit();
  const [editing, setEditing] = useState<{ habit: HabitOut | null; suggestion?: { name: string; time?: string } } | null>(null);
  const today = habits.filter((h) => h.active && h.scheduled_today);
  const rest = habits.filter((h) => h.active && !h.scheduled_today);
  const done = today.filter((h) => h.done_today).length;
  const focus = spotlight(today, now);

  return (
    <Section
      title="Routines"
      meta={today.length ? `${done}/${today.length}` : undefined}
      action={
        <button onClick={() => setEditing({ habit: null })} aria-label="Add routine" className="rounded p-1 text-ink-faint hover:text-ink cursor-pointer">
          <Plus size={16} />
        </button>
      }
    >
      {loading ? (
        <Skeleton className="h-10 w-full" />
      ) : habits.length === 0 ? (
        <div className="py-2">
          <p className="text-[14px] text-ink-faint">Track the things you want to do every day.</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {SUGGESTED_ROUTINES.map((r) => (
              <button
                key={r.name}
                onClick={() => setEditing({ habit: null, suggestion: r })}
                className="rounded-full border border-ops-line-bright px-3 py-1 text-[13px] text-ink-dim hover:text-ink cursor-pointer"
              >
                + {r.name}
              </button>
            ))}
          </div>
        </div>
      ) : (
        <>
          {focus && (
            <RoutineSpotlight
              habit={focus.habit}
              mode={focus.mode}
              startsIn={focus.startsIn}
              workout={WORKOUT_ROUTINE.test(focus.habit.name) ? workouts.find((w) => w.is_today) : undefined}
              onToggle={() => check.mutate({ id: focus.habit.id, done: !focus.habit.done_today })}
              onEdit={() => setEditing({ habit: focus.habit })}
            />
          )}
          <ul>
            {today.map((h) => {
              const isNow = focus?.mode === "now" && focus.habit.id === h.id;
              return (
                <li key={h.id} className="flex items-center gap-3 py-2.5">
                  <CheckCircle
                    done={h.done_today}
                    onClick={() => check.mutate({ id: h.id, done: !h.done_today })}
                    label={h.done_today ? `Mark ${h.name} not done` : `Mark ${h.name} done`}
                  />
                  <button onClick={() => setEditing({ habit: h })} className="min-w-0 flex-1 text-left cursor-pointer">
                    <p className={cn("truncate text-[15px]", h.done_today ? "text-ink-dim" : "text-ink", isNow && "font-semibold")}>
                      {h.name}
                      {isNow && <span className="ml-2 text-[11px] font-normal uppercase tracking-[0.15em] text-ink-faint">now</span>}
                    </p>
                    <WeekDots days={h.last_7} />
                  </button>
                  {timeRange(h) && <span className="tnum text-[13px] text-ink-faint">{timeRange(h)}</span>}
                  <span
                    className={cn("tnum flex w-10 items-center justify-end gap-0.5 text-[13px]", h.streak ? "text-ink" : "text-ink-faint")}
                    title={`Best streak: ${h.best_streak} days`}
                  >
                    <Flame size={13} className={h.streak && h.done_today ? "text-caution" : "text-ink-faint"} />
                    {h.streak}
                  </span>
                </li>
              );
            })}
            {rest.length > 0 && (
              <li className="pt-1 text-[12px] text-ink-faint">
                Not today: {rest.map((h) => h.name).join(", ")}
              </li>
            )}
          </ul>
        </>
      )}
      <RoutineDialog
        open={editing !== null}
        onOpenChange={(o) => !o && setEditing(null)}
        habit={editing?.habit ?? null}
        suggestion={editing?.suggestion}
      />
    </Section>
  );
}

/** The routine for this moment: what to do, from its description or today's workout plan. */
function RoutineSpotlight({
  habit: h,
  mode,
  startsIn,
  workout,
  onToggle,
  onEdit,
}: {
  habit: HabitOut;
  mode: "now" | "next";
  startsIn: number;
  workout?: WorkoutOut;
  onToggle: () => void;
  onEdit: () => void;
}) {
  const live = mode === "now";
  const preview = workout?.exercises.slice(0, 4) ?? [];
  return (
    <div
      className={cn(
        "mb-2 mt-1 rounded-2xl border px-4 py-3",
        live ? "border-ink/50 bg-ops-panel shadow-[0_0_24px_rgba(255,255,255,0.07)]" : "border-ops-line bg-ops-panel/60",
      )}
    >
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-[11px] uppercase tracking-[0.18em] text-ink-faint">
            {live ? "Now" : "Up next"} · {timeRange(h)}
            {!live && ` · ${inHowLong(startsIn)}`}
          </p>
          <button onClick={onEdit} className="mt-0.5 text-left text-[18px] font-semibold text-ink cursor-pointer">
            {h.name}
          </button>
        </div>
        {live && (
          <CheckCircle done={h.done_today} onClick={onToggle} label={h.done_today ? `Mark ${h.name} not done` : `Mark ${h.name} done`} />
        )}
      </div>

      {h.description && <p className="mt-1.5 whitespace-pre-line text-[14px] leading-relaxed text-ink-dim">{h.description}</p>}

      {workout && (
        <div className="mt-2.5 border-t border-ops-line pt-2.5">
          <p className="text-[13px] text-ink">
            {workout.name}
            {workout.focus && <span className="text-ink-faint"> · {workout.focus}</span>}
            {workout.exercises.length > 0 && (
              <span className="tnum text-ink-faint">
                {" "}
                · {workout.done_count}/{workout.exercises.length}
              </span>
            )}
          </p>
          <ol className="mt-1.5 space-y-1">
            {preview.map((e, i) => (
              <li key={e.id} className={cn("flex items-baseline gap-2 text-[13px]", e.done_today ? "text-ink-faint line-through" : "text-ink-dim")}>
                <span className="tnum w-4 shrink-0 text-ink-faint">{i + 1}</span>
                <span className="min-w-0 flex-1 truncate">{e.name}</span>
                {e.sets_reps && <span className="tnum shrink-0">{e.sets_reps}</span>}
                {e.weight && <span className="tnum shrink-0 text-ink-faint">{e.weight}</span>}
              </li>
            ))}
          </ol>
          <Link to="/gym" className="mt-2 inline-flex items-center text-[13px] font-medium text-ink hover:underline">
            {workout.exercises.length > preview.length ? `+${workout.exercises.length - preview.length} more · ` : ""}
            {live ? "Start workout" : "Open workout"} <ChevronRight size={14} />
          </Link>
        </div>
      )}

      {!h.description && !workout && (
        <button onClick={onEdit} className="mt-1 text-[12px] text-ink-faint hover:text-ink cursor-pointer">
          + Add what to do in this routine
        </button>
      )}
    </div>
  );
}

/** Last 7 days: filled = done, ring = missed, faint dot = rest day. */
function WeekDots({ days }: { days: HabitOut["last_7"] }) {
  return (
    <span className="mt-1 flex gap-1" aria-label={`Last 7 days: ${days.filter((d) => d.done).length} done`}>
      {days.map((d, i) => (
        <span
          key={d.day}
          className={cn(
            "h-1.5 w-1.5 rounded-full",
            d.done ? "bg-ink" : d.scheduled ? (i === days.length - 1 ? "border border-ink-faint" : "border border-ops-line-bright") : "bg-ops-raised",
          )}
        />
      ))}
    </span>
  );
}

// --- Workout ------------------------------------------------------------------------------

function TodaysWorkout() {
  const workouts = useWorkouts();
  const today = (workouts.data ?? []).filter((w) => w.is_today);
  if (!today.length) return null;
  return (
    <>
      {today.map((w) => {
        const total = w.exercises.length;
        return (
          <Link
            key={w.id}
            to="/gym"
            className="mt-4 flex items-center gap-3 rounded-2xl border border-ops-line-bright bg-ops-panel px-4 py-3 hover:border-ink-faint"
          >
            <Dumbbell size={20} className="shrink-0 text-ink-dim" />
            <div className="min-w-0 flex-1">
              <p className="text-[11px] uppercase tracking-[0.18em] text-ink-faint">Today's workout</p>
              <p className="truncate text-[15px] font-medium text-ink">
                {w.name}
                {w.focus && <span className="font-normal text-ink-faint"> · {w.focus}</span>}
              </p>
              {total > 0 && (
                <div className="mt-1.5 flex items-center gap-2">
                  <div className="h-1 flex-1 overflow-hidden rounded-full bg-ops-raised">
                    <div className="h-full rounded-full bg-ink" style={{ width: `${(w.done_count / total) * 100}%` }} />
                  </div>
                  <span className="tnum text-[12px] text-ink-faint">
                    {w.done_count}/{total}
                  </span>
                </div>
              )}
            </div>
            <ChevronRight size={16} className="shrink-0 text-ink-faint" />
          </Link>
        );
      })}
    </>
  );
}

// --- Tasks -----------------------------------------------------------------------------------

function Tasks({ tasks, doneToday }: { tasks: SituationTask[]; doneToday: Situation["done"]["today"] }) {
  const complete = useCompleteTask();
  return (
    <Section
      title="Tasks"
      meta={`${tasks.length} left · ${doneToday.length} done`}
      action={
        <Link to="/tasks" className="flex items-center text-[13px] text-ink-faint hover:text-ink">
          All <ChevronRight size={14} />
        </Link>
      }
    >
      {tasks.length === 0 && doneToday.length === 0 ? (
        <p className="py-2 text-[14px] text-ink-faint">Nothing due today.</p>
      ) : (
        <ul>
          {tasks.map((t) => {
            const overdue = t.due?.toLowerCase().includes("overdue");
            return (
              <li key={t.id} className="flex items-center gap-3 py-2.5">
                <CheckCircle done={false} onClick={() => complete.mutate({ id: t.id })} label={`Mark ${t.title} done`} />
                <span className="min-w-0 flex-1 truncate text-[15px] text-ink">{t.title}</span>
                {t.due && (
                  <span className={cn("shrink-0 text-[12px]", overdue ? "text-critical" : "text-ink-faint")}>
                    {t.due.charAt(0).toUpperCase() + t.due.slice(1)}
                  </span>
                )}
              </li>
            );
          })}
          {doneToday.map((t, i) => (
            <li key={`done-${i}`} className="flex items-center gap-3 py-2">
              <CheckCircle done onClick={() => {}} label={`${t.title} is done`} />
              <span className="min-w-0 flex-1 truncate text-[15px] text-ink-faint line-through">{t.title}</span>
              <span className="tnum text-[12px] text-ink-faint">{t.at}</span>
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}

// --- Schedule -----------------------------------------------------------------------------------

function Schedule({ items }: { items: Situation["today_schedule"] }) {
  const [open, setOpen] = useState(false);
  if (!items.length) return null;
  const nowIndex = items.findIndex((i) => i.status === "now");
  const shown = open ? items : items.slice(Math.max(0, nowIndex === -1 ? 0 : nowIndex), Math.max(0, nowIndex === -1 ? 0 : nowIndex) + 4);
  return (
    <Section
      title="Schedule"
      action={
        <button onClick={() => setOpen((o) => !o)} className="text-[13px] text-ink-faint hover:text-ink cursor-pointer">
          {open ? "Less" : "Full day"}
        </button>
      }
    >
      <ol className="relative ml-1.5 border-l border-ops-line-bright">
        {shown.map((i) => (
          <li key={`${i.start}-${i.title}`} className="relative py-1.5 pl-4">
            <span
              className={cn(
                "absolute -left-[4.5px] top-[13px] h-2 w-2 rounded-full",
                i.status === "now" ? "bg-ink shadow-[0_0_8px_rgba(255,255,255,0.7)]" : i.status === "done" ? "bg-ink-faint" : "border border-ink-faint bg-ops-ground",
              )}
            />
            <p className={cn("flex items-baseline gap-3 text-[14px]", i.status === "done" ? "text-ink-faint" : "text-ink")}>
              <span className="tnum w-11 shrink-0 text-[12px] text-ink-faint">{i.start}</span>
              <span className={cn("truncate", i.status === "now" && "font-medium")}>{i.title}</span>
              <span className="tnum ml-auto shrink-0 text-[12px] text-ink-faint">{i.end}</span>
            </p>
          </li>
        ))}
      </ol>
    </Section>
  );
}

// --- Money --------------------------------------------------------------------------------------

function Money() {
  const summary = useFinanceSummary();
  const s = summary.data;
  if (!s || (!s.expense && !s.income && !s.budgets.length && !s.bills_due.length)) return null;
  const today = s.daily.find((d) => d.day === s.today)?.expense ?? 0;
  const tight = s.budgets.filter((b) => b.percent >= 80);
  const dueSoon = s.bills_due.filter((b) => b.days_until_due <= 3);
  return (
    <Section
      title="Money"
      action={
        <Link to="/finance" className="flex items-center text-[13px] text-ink-faint hover:text-ink">
          Finance <ChevronRight size={14} />
        </Link>
      }
    >
      <div className="grid grid-cols-2 gap-3 py-1">
        <div>
          <p className="text-[12px] text-ink-faint">Spent today</p>
          <p className="tnum text-[20px] font-semibold text-ink">{inr(today)}</p>
        </div>
        <div>
          <p className="text-[12px] text-ink-faint">This month</p>
          <p className="tnum text-[20px] font-semibold text-ink">{inr(s.expense)}</p>
        </div>
      </div>
      {tight.map((b) => (
        <p key={b.id} className={cn("mt-1 text-[13px]", b.remaining < 0 ? "text-critical" : "text-caution")}>
          {b.category} budget {b.remaining < 0 ? `over by ${inr(-b.remaining)}` : `${b.percent}% used, ${inr(b.remaining)} left`}
        </p>
      ))}
      {dueSoon.map((b) => (
        <p key={b.id} className={cn("mt-1 text-[13px]", b.days_until_due < 0 ? "text-critical" : "text-caution")}>
          {b.name} {inr(b.amount)} {b.days_until_due < 0 ? "is overdue" : b.days_until_due === 0 ? "is due today" : `due in ${b.days_until_due}d`}
        </p>
      ))}
    </Section>
  );
}
