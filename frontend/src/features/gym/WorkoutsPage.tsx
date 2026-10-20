import { useState } from "react";
import { Check, Clock, Dumbbell, Flower2, Pencil, Plus } from "lucide-react";
import { useCheckExercise, useCheckHabit, useHabits, useSaveWorkout, useUpdateExercise, useWorkouts } from "@/hooks/queries";
import { ErrorState, Skeleton } from "@/components/ui/Overlay";
import { cn } from "@/lib/format";
import type { ExerciseOut, WorkoutOut } from "@/types/api";
import { WorkoutEditor } from "@/features/gym/WorkoutEditor";
import { fmtDay } from "@/features/finance/money";

/**
 * GYM & YOGA:
 * - Gym: weekday split workout plans (Mon-Sun), with today's open by default.
 * - Yoga: unified daily yoga routine for all days of the week, with asana tick-offs,
 *   breath/hold timings, alignment cues, and routine streak tracking.
 */

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const todayName = () => DAYS[(new Date().getDay() + 6) % 7];

export function isYogaWorkout(w: WorkoutOut): boolean {
  const text = `${w.name} ${w.focus ?? ""} ${w.notes ?? ""}`.toLowerCase();
  return text.includes("yoga") || text.includes("asana") || text.includes("pranayama") || text.includes("surya");
}

const DEFAULT_YOGA_FLOW = {
  name: "Daily Yoga Routine",
  focus: "Flexibility, Mobility & Breathwork",
  days_of_week: "Mon,Tue,Wed,Thu,Fri,Sat,Sun",
  duration: "25-30 min",
  notes: "Same daily yoga routine for all days of the week.",
  exercises: [
    {
      name: "Surya Namaskar (Sun Salutations)",
      sets_reps: "5 rounds",
      time: "5 min",
      muscles: "Full body mobility, spine & cardiovascular warmth",
      notes: "Flow through the 12 postures synchronizing each movement with inhale and exhale.",
    },
    {
      name: "Adho Mukha Svanasana (Downward Dog)",
      sets_reps: "5 deep breaths",
      time: "90s",
      muscles: "Hamstrings, calves, shoulders & spine lengthening",
      notes: "Spread fingers wide, press firmly through knuckles, lengthen spine upward.",
    },
    {
      name: "Virabhadrasana II (Warrior II Flow)",
      sets_reps: "5 breaths / side",
      time: "2 min",
      muscles: "Quadriceps, hip flexors, shoulders & core stability",
      notes: "Front knee stacked over ankle at 90°, arms outstretched parallel, steady gaze.",
    },
    {
      name: "Trikonasana (Triangle Pose)",
      sets_reps: "5 breaths / side",
      time: "2 min",
      muscles: "Hamstrings, groin, spine lengthening & chest opening",
      notes: "Keep both sides of torso long; gaze up toward the lifted fingertips.",
    },
    {
      name: "Bhujangasana (Cobra Pose)",
      sets_reps: "3-5 breaths",
      time: "1 min",
      muscles: "Spinal extensors, chest & lung capacity",
      notes: "Gently lift the sternum forward and up using back strength; keep shoulders relaxed.",
    },
    {
      name: "Balasana (Child's Pose)",
      sets_reps: "Restorative hold",
      time: "2 min",
      muscles: "Hips, lower back release & nervous system calming",
      notes: "Knees wide, big toes touch, forehead resting gently on the mat, deep belly breaths.",
    },
    {
      name: "Ardha Matsyendrasana (Half Lord of the Fishes)",
      sets_reps: "5 breaths / side",
      time: "2 min",
      muscles: "Spinal rotation, digestive stimulation & shoulder release",
      notes: "Inhale to sit tall and lengthen spine; exhale gently rotate from mid-back.",
    },
    {
      name: "Savasana & Pranayama (Final Relaxation)",
      sets_reps: "Stillness hold",
      time: "5 min",
      muscles: "Full body autonomic relaxation & mental stillness",
      notes: "Lie flat on your back, eyes closed, release all effort and let the practice integrate.",
    },
  ],
};

export function WorkoutsPage() {
  const workouts = useWorkouts();
  const save = useSaveWorkout();
  const [activeTab, setActiveTab] = useState<"gym" | "yoga">("gym");
  const [day, setDay] = useState(todayName());
  const [editing, setEditing] = useState<{ workout: WorkoutOut | null; mode?: "gym" | "yoga" } | null>(null);

  const list = workouts.data ?? [];
  const gymList = list.filter((w) => !isYogaWorkout(w));
  const yogaList = list.filter(isYogaWorkout);

  const forDay = gymList.filter((w) => w.days_of_week.split(",").includes(day));
  const unscheduledGym = gymList.filter((w) => !w.days_of_week);
  const isToday = day === todayName();

  const primaryYoga = yogaList[0] ?? null;
  const otherYoga = yogaList.slice(1);

  return (
    <div className="mx-auto w-full max-w-[760px] pb-12">
      {/* Header & Section Navigation */}
      <header className="mb-6 flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
          <h1 className="text-[30px] font-bold leading-tight tracking-[-0.02em] text-ink">Gym & Yoga</h1>
          <p className="text-[13px] text-ink-dim mt-0.5">Physical training, weekday gym splits & daily yoga flow</p>
        </div>

        <div className="flex items-center gap-2">
          {/* Section Tabs: Gym vs Yoga */}
          <div className="inline-flex rounded-xl border border-ops-line bg-ops-panel p-1">
            <button
              onClick={() => setActiveTab("gym")}
              className={cn(
                "flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-[13px] font-medium transition-all cursor-pointer",
                activeTab === "gym" ? "bg-ink text-ops-ground shadow-sm font-semibold" : "text-ink-dim hover:text-ink"
              )}
            >
              <Dumbbell size={15} /> Gym
            </button>
            <button
              onClick={() => setActiveTab("yoga")}
              className={cn(
                "flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-[13px] font-medium transition-all cursor-pointer",
                activeTab === "yoga" ? "bg-ink text-ops-ground shadow-sm font-semibold" : "text-ink-dim hover:text-ink"
              )}
            >
              <Flower2 size={15} /> Yoga
            </button>
          </div>

          <button
            onClick={() => setEditing({ workout: null, mode: activeTab })}
            className="inline-flex items-center gap-1.5 rounded-xl border border-ops-line-bright bg-ops-panel px-3 py-2 text-[13px] font-medium text-ai hover:bg-ops-raised cursor-pointer"
          >
            <Plus size={14} /> {activeTab === "yoga" ? "New yoga routine" : "New workout"}
          </button>
        </div>
      </header>

      {/* --- TAB 1: GYM SECTION --- */}
      {activeTab === "gym" && (
        <div className="space-y-6">
          {/* Weekday Switcher */}
          <nav className="grid grid-cols-7 gap-1.5" aria-label="Days of the week">
            {DAYS.map((d) => {
              const plan = gymList.find((w) => w.days_of_week.split(",").includes(d));
              return (
                <button
                  key={d}
                  onClick={() => setDay(d)}
                  aria-current={d === day ? "date" : undefined}
                  className={cn(
                    "flex flex-col items-center rounded-xl border px-1 py-2 transition-colors cursor-pointer",
                    d === day ? "border-ink bg-ink text-ops-ground font-medium" : "border-ops-line text-ink-dim hover:border-ops-line-bright",
                  )}
                >
                  <span className={cn("text-[11px]", d === day ? "font-semibold" : d === todayName() ? "text-ink font-medium" : "text-ink-faint")}>
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
              <div className="rounded-2xl border border-ops-line bg-ops-panel/40 py-10 text-center">
                <p className="text-[17px] font-medium text-ink">{gymList.length ? `Rest day${isToday ? " today" : ""}.` : "No gym workouts configured."}</p>
                <p className="mx-auto mt-2 max-w-[400px] text-[14px] text-ink-faint leading-relaxed">
                  {gymList.length
                    ? `Nothing scheduled for ${day}. Enjoy your recovery, or log an extra workout session.`
                    : "Add your workout split from Notion — paste your exercise table — or ask IRIS: “save my chest & triceps workout”."}
                </p>
                <button
                  onClick={() => setEditing({ workout: null, mode: "gym" })}
                  className="mt-5 rounded-full border border-ops-line-bright px-5 py-2 text-[14px] font-medium text-ink hover:bg-ops-raised cursor-pointer"
                >
                  Add a workout for {day}
                </button>
              </div>
            ) : (
              forDay.map((w) => <WorkoutCard key={w.id} workout={w} live={isToday} onEdit={() => setEditing({ workout: w, mode: "gym" })} />)
            )}

            {unscheduledGym.length > 0 && (
              <section className="mt-10">
                <h2 className="border-b border-ops-line pb-1.5 text-[15px] font-semibold text-ink-dim">Unscheduled Gym Workouts</h2>
                <ul className="divide-y divide-ops-line">
                  {unscheduledGym.map((w) => (
                    <li key={w.id}>
                      <button onClick={() => setEditing({ workout: w, mode: "gym" })} className="flex w-full items-baseline justify-between py-3 text-left hover:text-ai cursor-pointer">
                        <span className="text-[15px] font-medium text-ink">{w.name}</span>
                        <span className="text-[12px] text-ink-faint">{w.exercises.length} exercises</span>
                      </button>
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </div>
        </div>
      )}

      {/* --- TAB 2: YOGA SECTION --- */}
      {activeTab === "yoga" && (
        <div className="space-y-6">
          {workouts.isLoading ? (
            <div className="space-y-3">
              <Skeleton className="h-8 w-1/2" />
              <Skeleton className="h-28 w-full" />
              <Skeleton className="h-28 w-full" />
            </div>
          ) : workouts.error ? (
            <ErrorState message={(workouts.error as Error).message} />
          ) : primaryYoga ? (
            <YogaRoutineSection
              routine={primaryYoga}
              onEdit={() => setEditing({ workout: primaryYoga, mode: "yoga" })}
            />
          ) : (
            /* Empty State for Yoga */
            <div className="rounded-2xl border border-ops-line bg-ops-panel/40 p-8 text-center">
              <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-ai/10 text-ai mb-4">
                <Flower2 size={28} />
              </div>
              <h2 className="text-[20px] font-bold text-ink">Daily Yoga Routine</h2>
              <p className="mx-auto mt-2 max-w-[460px] text-[14px] text-ink-dim leading-relaxed">
                You have the same routine for yoga all week. Start with our classical 8-asana daily flow or build your own custom sequence.
              </p>

              <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
                <button
                  onClick={() => save.mutate({ body: DEFAULT_YOGA_FLOW })}
                  disabled={save.isPending}
                  className="rounded-full bg-ink px-5 py-2.5 text-[14px] font-semibold text-ops-ground hover:bg-ink/90 transition-all cursor-pointer shadow-sm"
                >
                  {save.isPending ? "Setting up flow…" : "Start with Classical Flow (8 Asanas)"}
                </button>
                <button
                  onClick={() => setEditing({ workout: null, mode: "yoga" })}
                  className="rounded-full border border-ops-line-bright px-5 py-2.5 text-[14px] font-medium text-ink hover:bg-ops-raised cursor-pointer"
                >
                  Create Custom Sequence
                </button>
              </div>
            </div>
          )}

          {/* Other Yoga Practices (e.g. Evening Yoga, Pranayama) */}
          {otherYoga.length > 0 && (
            <section className="mt-10">
              <h2 className="border-b border-ops-line pb-1.5 text-[15px] font-semibold text-ink-dim">Other Yoga Routines</h2>
              <div className="mt-4 space-y-4">
                {otherYoga.map((y) => (
                  <YogaRoutineSection
                    key={y.id}
                    routine={y}
                    onEdit={() => setEditing({ workout: y, mode: "yoga" })}
                  />
                ))}
              </div>
            </section>
          )}
        </div>
      )}

      {/* Shared Modal Editor */}
      <WorkoutEditor
        open={editing !== null}
        onOpenChange={(o) => !o && setEditing(null)}
        workout={editing?.workout ?? null}
        defaultDay={day}
        mode={editing?.mode ?? activeTab}
      />
    </div>
  );
}

// --- Yoga Routine Card & Asana List -----------------------------------------

function YogaRoutineSection({ routine: y, onEdit }: { routine: WorkoutOut; onEdit: () => void }) {
  const total = y.exercises.length;
  const done = y.done_count;
  const allDone = total > 0 && done === total;

  return (
    <section className="rounded-2xl border border-ops-line bg-ops-panel p-6 shadow-sm">
      {/* Yoga Routine Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-[24px] font-bold tracking-tight text-ink">{y.name}</h2>
            <span className="rounded-full bg-ai/10 border border-ai/20 px-2.5 py-0.5 text-[11px] font-semibold text-ai">
              Everyday • Mon–Sun
            </span>
            {allDone && (
              <span className="rounded-full bg-emerald-500/10 border border-emerald-500/20 px-2.5 py-0.5 text-[11px] font-semibold text-emerald-400">
                Completed Today 🧘
              </span>
            )}
          </div>

          {y.focus && <p className="mt-1 text-[14px] text-ink-dim font-medium">{y.focus}</p>}

          <p className="mt-2 flex flex-wrap items-center gap-x-4 text-[12px] text-ink-faint">
            {y.duration && (
              <span className="inline-flex items-center gap-1 text-ink-dim">
                <Clock size={13} /> {y.duration}
              </span>
            )}
            <span>{total} asanas / poses</span>
            {y.last_done_on && <span>Last practiced {fmtDay(y.last_done_on)}</span>}
          </p>
        </div>

        <button
          onClick={onEdit}
          aria-label={`Edit ${y.name}`}
          className="rounded-xl border border-ops-line-bright p-2.5 text-ink-dim hover:bg-ops-raised hover:text-ink cursor-pointer"
          title="Edit Yoga Routine"
        >
          <Pencil size={16} />
        </button>
      </div>

      {/* Progress Bar */}
      {total > 0 && (
        <div className="mt-5">
          <div className="flex items-center justify-between text-[12px] text-ink-dim mb-1.5">
            <span>Today's Daily Practice</span>
            <span className="font-semibold text-ink">{done}/{total} asanas complete</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-ops-ground border border-ops-line">
            <div
              className={cn(
                "h-full rounded-full transition-[width] duration-300",
                allDone ? "bg-emerald-400 shadow-[0_0_10px_rgba(52,211,153,0.5)]" : "bg-ai shadow-[0_0_8px_rgba(255,255,255,0.4)]"
              )}
              style={{ width: `${(done / total) * 100}%` }}
            />
          </div>
        </div>
      )}

      {/* Asana Sequence */}
      <ol className="mt-6 space-y-3">
        {y.exercises.map((e, i) => (
          <YogaAsanaCard key={e.id} routineId={y.id} asana={e} index={i} />
        ))}
      </ol>

      {/* Completion Banner */}
      {allDone && <Finished workout={y} routineType="yoga" />}
    </section>
  );
}

function YogaAsanaCard({ routineId, asana: e, index }: { routineId: number; asana: ExerciseOut; index: number }) {
  const check = useCheckExercise();
  const done = e.done_today;

  return (
    <li
      className={cn(
        "flex items-start gap-3.5 rounded-xl border p-3.5 transition-all",
        done ? "border-ops-line bg-ops-ground/60 opacity-80" : "border-ops-line-bright bg-ops-raised/40 hover:border-ink/40"
      )}
    >
      {/* Checkoff Circle */}
      <button
        onClick={() => check.mutate({ id: routineId, exerciseId: e.id, done: !e.done_today })}
        aria-label={done ? `Mark ${e.name} incomplete` : `Mark ${e.name} done`}
        aria-pressed={done}
        className={cn(
          "flex h-9 w-9 shrink-0 items-center justify-center rounded-full border-2 transition-all cursor-pointer mt-0.5",
          done
            ? "border-emerald-400 bg-emerald-400 text-ops-ground shadow-[0_0_12px_rgba(52,211,153,0.4)]"
            : "border-ops-line-bright hover:border-ink text-ink-dim"
        )}
      >
        {done ? <Check size={18} strokeWidth={3} /> : <span className="text-[12px] font-semibold">{index + 1}</span>}
      </button>

      {/* Asana Details */}
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline gap-2">
          <p className={cn("text-[16px] font-semibold leading-snug", done ? "text-ink-faint line-through" : "text-ink")}>
            {e.name}
          </p>
          {e.sets_reps && (
            <span className="rounded-md bg-ops-panel border border-ops-line px-2 py-0.5 text-[11px] font-semibold text-ai">
              {e.sets_reps}
            </span>
          )}
          {e.time && (
            <span className="text-[12px] text-ink-faint">
              ⏱ {e.time}
            </span>
          )}
        </div>

        {e.muscles && <p className="mt-1 text-[13px] text-ink-dim font-medium">{e.muscles}</p>}
        {e.notes && <p className="mt-1 text-[12px] text-ink-faint italic leading-relaxed">{e.notes}</p>}
      </div>
    </li>
  );
}

// --- Gym Workout Card --------------------------------------------------------

function WorkoutCard({ workout: w, live, onEdit }: { workout: WorkoutOut; live: boolean; onEdit: () => void }) {
  const total = w.exercises.length;
  const done = live ? w.done_count : 0;
  return (
    <section className="mb-8 rounded-2xl border border-ops-line bg-ops-panel p-6 shadow-sm">
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

      {live && total > 0 && done === total && <Finished workout={w} routineType="gym" />}
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

/** Routine or workout complete: offer to tick the matching daily habit. */
function Finished({ workout, routineType = "gym" }: { workout: WorkoutOut; routineType?: "gym" | "yoga" }) {
  const habits = useHabits();
  const check = useCheckHabit();
  const pattern = routineType === "yoga" ? /yoga|asana|pranayama|stretch/i : /gym|workout|lift|training/i;
  const routine = (habits.data ?? []).find((h) => h.active && h.scheduled_today && pattern.test(h.name));

  return (
    <div className="mt-5 rounded-2xl border border-ink/40 px-4 py-3 text-center shadow-[0_0_20px_rgba(255,255,255,0.08)] bg-ops-ground/40">
      <p className="text-[15px] font-semibold text-ink">
        {routineType === "yoga" ? `🧘 Namaste! ${workout.name} complete` : `💪 ${workout.name} complete`}
      </p>
      {routine && !routine.done_today && (
        <button
          onClick={() => check.mutate({ id: routine.id, done: true })}
          className="mt-2 rounded-full bg-ink px-4 py-1.5 text-[13px] font-medium text-ops-ground cursor-pointer hover:bg-ink/90 transition-all"
        >
          Tick “{routine.name}” for today
        </button>
      )}
      {routine?.done_today && <p className="mt-1 text-[13px] text-ink-faint">{routine.name} ticked · {routine.streak}-day streak</p>}
    </div>
  );
}
