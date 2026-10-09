import { useState } from "react";
import { Check, Clock, Pencil, Plus } from "lucide-react";
import { useCheckExercise, useCheckHabit, useHabits, useUpdateExercise, useWorkouts } from "@/hooks/queries";
import { ErrorState, Skeleton } from "@/components/ui/Overlay";
import { cn } from "@/lib/format";
import type { ExerciseOut, WorkoutOut } from "@/types/api";
import { WorkoutEditor } from "@/features/gym/WorkoutEditor";
import { fmtDay } from "@/features/finance/money";

/**
 * GYM: the week's workout plans, with today's open by default - big cards to
 * tick off between sets, and weights you can bump on the spot.
 */

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const todayName = () => DAYS[(new Date().getDay() + 6) % 7];

export function WorkoutsPage() {
  const workouts = useWorkouts();
  const [day, setDay] = useState(todayName());
  const [editing, setEditing] = useState<{ workout: WorkoutOut | null } | null>(null);

  const list = workouts.data ?? [];
  const forDay = list.filter((w) => w.days_of_week.split(",").includes(day));
  const unscheduled = list.filter((w) => !w.days_of_week);
  const isToday = day === todayName();

  return (
    <div className="mx-auto w-full max-w-[720px] pb-10">
      <header className="mb-4 flex items-end justify-between gap-3">
        <h1 className="text-[30px] font-bold leading-tight tracking-[-0.02em] text-ink">Gym</h1>
        <button onClick={() => setEditing({ workout: null })} className="mb-1 inline-flex items-center gap-1 text-[14px] text-ai hover:underline cursor-pointer">
          <Plus size={14} /> New workout
        </button>
      </header>

      <nav className="grid grid-cols-7 gap-1.5" aria-label="Days of the week">
        {DAYS.map((d) => {
          const plan = list.find((w) => w.days_of_week.split(",").includes(d));
          return (
            <button
              key={d}
              onClick={() => setDay(d)}
              aria-current={d === day ? "date" : undefined}
              className={cn(
                "flex flex-col items-center rounded-xl border px-1 py-2 transition-colors cursor-pointer",
                d === day ? "border-ink bg-ink text-ops-ground" : "border-ops-line text-ink-dim hover:border-ops-line-bright",
              )}
            >
              <span className={cn("text-[11px]", d === day ? "font-semibold" : d === todayName() ? "text-ink" : "text-ink-faint")}>
                {d === todayName() ? "Today" : d}
              </span>
              <span className="mt-0.5 w-full truncate text-center text-[12px] font-medium">{plan?.name ?? "Rest"}</span>
            </button>
          );
        })}
      </nav>

      <div className="mt-6">
        {workouts.isLoading ? (
          <div className="space-y-3">
            <Skeleton className="h-8 w-1/2" />
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-20 w-full" />
          </div>
        ) : workouts.error ? (
          <ErrorState message={(workouts.error as Error).message} />
        ) : forDay.length === 0 ? (
          <div className="py-8 text-center">
            <p className="text-[16px] text-ink">{list.length ? `Rest day${isToday ? " today" : ""}.` : "No workouts yet."}</p>
            <p className="mx-auto mt-2 max-w-[380px] text-[14px] text-ink-faint">
              {list.length
                ? `Nothing planned for ${day}.`
                : "Add your plan from Notion — copy the table and paste it — or tell IRIS: “save my Sunday workout” with the table."}
            </p>
            <button onClick={() => setEditing({ workout: null })} className="mt-4 rounded-full border border-ops-line-bright px-4 py-2 text-[14px] text-ink hover:bg-ops-raised cursor-pointer">
              Add a workout for {day}
            </button>
          </div>
        ) : (
          forDay.map((w) => <WorkoutCard key={w.id} workout={w} live={isToday} onEdit={() => setEditing({ workout: w })} />)
        )}

        {unscheduled.length > 0 && (
          <section className="mt-10">
            <h2 className="border-b border-ops-line pb-1.5 text-[15px] font-semibold text-ink-dim">Other workouts</h2>
            <ul>
              {unscheduled.map((w) => (
                <li key={w.id}>
                  <button onClick={() => setEditing({ workout: w })} className="flex w-full items-baseline justify-between py-2.5 text-left cursor-pointer">
                    <span className="text-[15px] text-ink">{w.name}</span>
                    <span className="text-[12px] text-ink-faint">{w.exercises.length} exercises</span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>

      <WorkoutEditor
        open={editing !== null}
        onOpenChange={(o) => !o && setEditing(null)}
        workout={editing?.workout ?? null}
        defaultDay={day}
      />
    </div>
  );
}

function WorkoutCard({ workout: w, live, onEdit }: { workout: WorkoutOut; live: boolean; onEdit: () => void }) {
  const total = w.exercises.length;
  const done = live ? w.done_count : 0;
  return (
    <section className="mb-8">
      <header className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <h2 className="text-[24px] font-semibold leading-tight text-ink">{w.name}</h2>
          {w.focus && <p className="mt-0.5 text-[14px] text-ink-dim">{w.focus}</p>}
          <p className="mt-1 flex flex-wrap items-center gap-x-3 text-[12px] text-ink-faint">
            {w.duration && (
              <span className="inline-flex items-center gap-1">
                <Clock size={12} /> {w.duration}
              </span>
            )}
            <span>{total} exercises</span>
            {w.last_done_on && <span>last done {fmtDay(w.last_done_on)}</span>}
          </p>
        </div>
        <button onClick={onEdit} aria-label={`Edit ${w.name}`} className="rounded-full p-2 text-ink-faint hover:bg-ops-raised hover:text-ink cursor-pointer">
          <Pencil size={16} />
        </button>
      </header>

      {live && total > 0 && (
        <div className="mt-4">
          <div className="h-1.5 overflow-hidden rounded-full bg-ops-raised">
            <div
              className="h-full rounded-full bg-ink shadow-[0_0_8px_rgba(255,255,255,0.5)] transition-[width] duration-300"
              style={{ width: `${(done / total) * 100}%` }}
            />
          </div>
          <p className="tnum mt-1 text-[12px] text-ink-faint">
            {done}/{total} done
          </p>
        </div>
      )}

      <ol className="mt-4 space-y-2.5">
        {w.exercises.map((e, i) => (
          <ExerciseCard key={e.id} workoutId={w.id} exercise={e} index={i} live={live} />
        ))}
      </ol>

      {live && total > 0 && done === total && <Finished workout={w} />}
    </section>
  );
}

function ExerciseCard({ workoutId, exercise: e, index, live }: { workoutId: number; exercise: ExerciseOut; index: number; live: boolean }) {
  const check = useCheckExercise();
  const update = useUpdateExercise();
  const [editingWeight, setEditingWeight] = useState(false);
  const [weight, setWeight] = useState(e.weight ?? "");
  const done = live && e.done_today;

  const saveWeight = (value: string) => {
    setEditingWeight(false);
    const next = value.trim() || null;
    if (next !== (e.weight ?? null)) update.mutate({ id: workoutId, exerciseId: e.id, body: { weight: next } });
  };

  return (
    <li className={cn("flex items-center gap-3 rounded-2xl border px-3.5 py-3 transition-colors", done ? "border-ops-line bg-ops-panel/40" : "border-ops-line-bright bg-ops-panel")}>
      {live ? (
        <button
          onClick={() => check.mutate({ id: workoutId, exerciseId: e.id, done: !e.done_today })}
          aria-label={done ? `Mark ${e.name} not done` : `Mark ${e.name} done`}
          aria-pressed={done}
          className={cn(
            "flex h-9 w-9 shrink-0 items-center justify-center rounded-full border-2 transition-colors cursor-pointer",
            done ? "border-ink bg-ink text-ops-ground shadow-[0_0_12px_rgba(255,255,255,0.4)]" : "border-ops-line-bright hover:border-ink",
          )}
        >
          {done ? <Check size={18} strokeWidth={3} /> : <span className="tnum text-[12px] text-ink-faint">{index + 1}</span>}
        </button>
      ) : (
        <span className="tnum flex h-9 w-9 shrink-0 items-center justify-center text-[13px] text-ink-faint">{index + 1}</span>
      )}

      <div className="min-w-0 flex-1">
        <p className={cn("text-[16px] font-medium leading-snug", done ? "text-ink-faint line-through" : "text-ink")}>{e.name}</p>
        {e.muscles && <p className="truncate text-[12px] text-ink-faint">{e.muscles}</p>}
        {e.time && <p className="text-[12px] text-ink-faint">{e.time}</p>}
      </div>

      <div className="flex shrink-0 flex-col items-end gap-1">
        {e.sets_reps && <span className="tnum text-[17px] font-semibold text-ink">{e.sets_reps.replace(/x/gi, " × ")}</span>}
        {editingWeight ? (
          <input
            value={weight}
            onChange={(ev) => setWeight(ev.target.value)}
            onBlur={(ev) => saveWeight(ev.currentTarget.value)}
            onKeyDown={(ev) => ev.key === "Enter" && (ev.target as HTMLInputElement).blur()}
            autoFocus
            aria-label={`Weight for ${e.name}`}
            className="tnum w-20 rounded-md border border-ink bg-ops-ground px-2 py-0.5 text-right text-[13px] text-ink focus:outline-none"
          />
        ) : (
          <button
            onClick={() => {
              setWeight(e.weight ?? "");
              setEditingWeight(true);
            }}
            className="tnum rounded-md border border-ops-line-bright px-2 py-0.5 text-[13px] text-ink-dim hover:border-ink hover:text-ink cursor-pointer"
            title="Tap to change the weight"
          >
            {e.weight ?? "+ weight"}
          </button>
        )}
      </div>
    </li>
  );
}

/** All exercises done: offer to tick the matching daily routine (e.g. "Gym"). */
function Finished({ workout }: { workout: WorkoutOut }) {
  const habits = useHabits();
  const check = useCheckHabit();
  const routine = (habits.data ?? []).find((h) => h.active && h.scheduled_today && /gym|workout|lift|training/i.test(h.name));
  return (
    <div className="mt-5 rounded-2xl border border-ink/40 px-4 py-3 text-center shadow-[0_0_20px_rgba(255,255,255,0.08)]">
      <p className="text-[15px] font-semibold text-ink">{workout.name} complete</p>
      {routine && !routine.done_today && (
        <button
          onClick={() => check.mutate({ id: routine.id, done: true })}
          className="mt-2 rounded-full bg-ink px-4 py-1.5 text-[13px] font-medium text-ops-ground cursor-pointer"
        >
          Tick “{routine.name}” for today
        </button>
      )}
      {routine?.done_today && <p className="mt-1 text-[13px] text-ink-faint">{routine.name} ticked · {routine.streak}-day streak</p>}
    </div>
  );
}
