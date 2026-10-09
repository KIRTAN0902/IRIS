import { useEffect, useState } from "react";
import { ArrowDown, ArrowUp, ClipboardPaste, Plus, X } from "lucide-react";
import { useDeleteWorkout, useSaveWorkout } from "@/hooks/queries";
import { Button } from "@/components/ui/Button";
import { Dialog, DialogContent } from "@/components/ui/Overlay";
import { Field, Input, Textarea } from "@/components/ui/Field";
import { cn } from "@/lib/format";
import type { ExerciseIn, WorkoutOut } from "@/types/api";
import { parseWorkoutTable } from "@/features/gym/parseTable";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

type Row = ExerciseIn & { key: number };
let nextKey = 1;
const row = (e: Partial<ExerciseIn> = {}): Row => ({ key: nextKey++, name: "", ...e });

/** Create or edit a workout plan; exercises can be typed or pasted from Notion. */
export function WorkoutEditor({
  open,
  onOpenChange,
  workout,
  defaultDay,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  workout: WorkoutOut | null;
  defaultDay?: string;
}) {
  const save = useSaveWorkout();
  const del = useDeleteWorkout();
  const [name, setName] = useState("");
  const [focus, setFocus] = useState("");
  const [days, setDays] = useState<string[]>([]);
  // Days picked by hand win over a day named in a pasted table.
  const [daysTouched, setDaysTouched] = useState(false);
  const [duration, setDuration] = useState("");
  const [rows, setRows] = useState<Row[]>([]);
  const [pasting, setPasting] = useState(false);
  const [pasted, setPasted] = useState("");
  const [pasteNote, setPasteNote] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setName(workout?.name ?? "");
    setFocus(workout?.focus ?? "");
    setDays(workout ? workout.days_of_week.split(",").filter(Boolean) : defaultDay ? [defaultDay] : []);
    setDuration(workout?.duration ?? "");
    setDaysTouched(!!workout);
    setRows(workout?.exercises.length ? workout.exercises.map((e) => row(e)) : [row()]);
    setPasting(!workout);
    setPasted("");
    setPasteNote(null);
  }, [open, workout, defaultDay]);

  const applyPaste = () => {
    const { workout: meta, exercises } = parseWorkoutTable(pasted);
    if (!exercises.length) {
      setPasteNote("Couldn't find a table in that. Copy the whole table (with its header row) and paste again.");
      return;
    }
    if (meta.name && !name) setName(meta.name);
    if (meta.focus && !focus) setFocus(meta.focus);
    if (meta.duration && !duration) setDuration(meta.duration);
    if (meta.days_of_week && !daysTouched) setDays([meta.days_of_week]);
    setRows(exercises.map((e) => row(e)));
    setPasting(false);
    setPasteNote(`Added ${exercises.length} exercises. Check them below.`);
  };

  const edit = (key: number, patch: Partial<ExerciseIn>) => setRows((rs) => rs.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  const move = (i: number, by: number) =>
    setRows((rs) => {
      const next = [...rs];
      const [r] = next.splice(i, 1);
      next.splice(Math.max(0, Math.min(next.length, i + by)), 0, r);
      return next;
    });
  const toggleDay = (d: string) => {
    setDaysTouched(true);
    setDays((ds) => (ds.includes(d) ? ds.filter((x) => x !== d) : DAYS.filter((x) => ds.includes(x) || x === d)));
  };

  const exercises = rows.filter((r) => r.name.trim()).map(({ key: _key, ...e }) => e);
  const close = () => onOpenChange(false);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title={workout ? `Edit ${workout.name}` : "New workout"} className="max-w-2xl">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (!name.trim()) return;
            save.mutate(
              {
                id: workout?.id,
                body: { name: name.trim(), focus: focus.trim() || null, days_of_week: days.join(","), duration: duration.trim() || null, exercises },
              },
              { onSuccess: close },
            );
          }}
          className="space-y-4"
        >
          {pasting ? (
            <div className="rounded-xl border border-ops-line-bright p-3">
              <p className="text-[13px] text-ink-dim">
                Paste your workout table from Notion (select the table, copy, paste here). The title and “Total Time” lines are
                picked up too.
              </p>
              <Textarea
                value={pasted}
                onChange={(e) => setPasted(e.target.value)}
                rows={5}
                placeholder={"Sunday – CST (Chest, Shoulders, Triceps)\nExercise\tSets x Reps\tTime\tTargeted Muscles\tWeight\n…"}
                className="mt-2 font-mono text-[12px]"
              />
              <div className="mt-2 flex gap-2">
                <Button type="button" variant="solid" size="sm" onClick={applyPaste} disabled={!pasted.trim()}>
                  Use this table
                </Button>
                <Button type="button" variant="ghost" size="sm" onClick={() => setPasting(false)}>
                  Type it instead
                </Button>
              </div>
            </div>
          ) : (
            <button type="button" onClick={() => setPasting(true)} className="inline-flex items-center gap-1.5 text-[13px] text-ink-faint hover:text-ink cursor-pointer">
              <ClipboardPaste size={14} /> Paste from Notion
            </button>
          )}
          {pasteNote && <p className="text-[13px] text-ink-dim">{pasteNote}</p>}

          <div className="grid grid-cols-2 gap-3">
            <Field label="Name">
              <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="CST" maxLength={80} />
            </Field>
            <Field label="Duration">
              <Input value={duration} onChange={(e) => setDuration(e.target.value)} placeholder="75-85 min" maxLength={40} />
            </Field>
            <div className="col-span-2">
              <Field label="Focus">
                <Input value={focus} onChange={(e) => setFocus(e.target.value)} placeholder="Chest, Shoulders, Triceps" maxLength={160} />
              </Field>
            </div>
          </div>

          <div>
            <p className="mb-1.5 text-[12px] text-ink-faint">Days</p>
            <div className="flex gap-1.5">
              {DAYS.map((d) => (
                <button
                  key={d}
                  type="button"
                  onClick={() => toggleDay(d)}
                  aria-pressed={days.includes(d)}
                  className={cn(
                    "h-9 flex-1 rounded-full border text-[12px] transition-colors cursor-pointer",
                    days.includes(d) ? "border-ink bg-ink text-ops-ground" : "border-ops-line-bright text-ink-faint",
                  )}
                >
                  {d.slice(0, 2)}
                </button>
              ))}
            </div>
          </div>

          <div>
            <p className="mb-1.5 text-[12px] text-ink-faint">Exercises</p>
            <ol className="space-y-2">
              {rows.map((r, i) => (
                <li key={r.key} className="rounded-xl border border-ops-line p-2.5">
                  <div className="flex items-center gap-2">
                    <span className="tnum w-5 text-center text-[12px] text-ink-faint">{i + 1}</span>
                    <Input value={r.name} onChange={(e) => edit(r.key, { name: e.target.value })} placeholder="Exercise" maxLength={120} />
                    <div className="flex shrink-0">
                      <button type="button" onClick={() => move(i, -1)} disabled={i === 0} aria-label="Move up" className="rounded p-1 text-ink-faint hover:text-ink disabled:opacity-30 cursor-pointer">
                        <ArrowUp size={14} />
                      </button>
                      <button type="button" onClick={() => move(i, 1)} disabled={i === rows.length - 1} aria-label="Move down" className="rounded p-1 text-ink-faint hover:text-ink disabled:opacity-30 cursor-pointer">
                        <ArrowDown size={14} />
                      </button>
                      <button type="button" onClick={() => setRows((rs) => rs.filter((x) => x.key !== r.key))} aria-label="Remove exercise" className="rounded p-1 text-ink-faint hover:text-critical cursor-pointer">
                        <X size={14} />
                      </button>
                    </div>
                  </div>
                  <div className="mt-2 grid grid-cols-3 gap-2 pl-7">
                    <Input value={r.sets_reps ?? ""} onChange={(e) => edit(r.key, { sets_reps: e.target.value })} placeholder="Sets x reps" maxLength={40} />
                    <Input value={r.weight ?? ""} onChange={(e) => edit(r.key, { weight: e.target.value })} placeholder="Weight" maxLength={40} />
                    <Input value={r.time ?? ""} onChange={(e) => edit(r.key, { time: e.target.value })} placeholder="Time" maxLength={40} />
                    <div className="col-span-3">
                      <Input value={r.muscles ?? ""} onChange={(e) => edit(r.key, { muscles: e.target.value })} placeholder="Targeted muscles" maxLength={160} />
                    </div>
                  </div>
                </li>
              ))}
            </ol>
            <button type="button" onClick={() => setRows((rs) => [...rs, row()])} className="mt-2 inline-flex items-center gap-1 text-[13px] text-ink-faint hover:text-ink cursor-pointer">
              <Plus size={14} /> Add exercise
            </button>
          </div>

          <div className="flex items-center gap-2 border-t border-ops-line pt-3">
            {workout && (
              <Button
                type="button"
                variant="danger"
                disabled={del.isPending}
                onClick={() => window.confirm(`Delete ${workout.name}?`) && del.mutate(workout.id, { onSuccess: close })}
              >
                Delete
              </Button>
            )}
            <div className="ml-auto flex gap-2">
              <Button type="button" variant="ghost" onClick={close}>
                Cancel
              </Button>
              <Button type="submit" variant="solid" disabled={!name.trim() || save.isPending}>
                {save.isPending ? "Saving…" : workout ? "Save" : "Create"}
              </Button>
            </div>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
