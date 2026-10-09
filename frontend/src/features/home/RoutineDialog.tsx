import { useEffect, useState } from "react";
import { useDeleteHabit, useSaveHabit } from "@/hooks/queries";
import { Button } from "@/components/ui/Button";
import { Dialog, DialogContent } from "@/components/ui/Overlay";
import { Field, Input } from "@/components/ui/Field";
import { cn } from "@/lib/format";
import type { HabitOut } from "@/types/api";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

/** Add or edit a routine: name, usual time, which days. */
export function RoutineDialog({
  open,
  onOpenChange,
  habit,
  suggestion,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  habit: HabitOut | null;
  suggestion?: { name: string; time?: string };
}) {
  const save = useSaveHabit();
  const del = useDeleteHabit();
  const [name, setName] = useState("");
  const [time, setTime] = useState("");
  const [days, setDays] = useState<string[]>(DAYS);
  const [active, setActive] = useState(true);

  useEffect(() => {
    if (!open) return;
    setName(habit?.name ?? suggestion?.name ?? "");
    setTime(habit?.time ?? suggestion?.time ?? "");
    setDays(habit ? habit.days_of_week.split(",") : DAYS);
    setActive(habit?.active ?? true);
  }, [open, habit, suggestion]);

  const toggle = (d: string) => setDays((cur) => (cur.includes(d) ? cur.filter((x) => x !== d) : DAYS.filter((x) => cur.includes(x) || x === d)));
  const close = () => onOpenChange(false);
  const canSave = name.trim() && days.length > 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title={habit ? "Edit routine" : "New routine"}>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (!canSave) return;
            save.mutate(
              { id: habit?.id, body: { name: name.trim(), time: time || null, days_of_week: days.join(","), active } },
              { onSuccess: close },
            );
          }}
          className="space-y-4"
        >
          <Field label="Routine">
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Gym, Yoga, Reading…" maxLength={80} autoFocus={!habit} />
          </Field>
          <Field label="Usual time (optional)">
            <Input type="time" value={time} onChange={(e) => setTime(e.target.value)} />
          </Field>
          <div>
            <p className="mb-1.5 text-[12px] text-ink-faint">Days</p>
            <div className="flex gap-1.5">
              {DAYS.map((d) => (
                <button
                  key={d}
                  type="button"
                  onClick={() => toggle(d)}
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
          {habit && (
            <label className="flex items-center gap-2 text-[14px] text-ink-dim">
              <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} className="accent-white" />
              Active (uncheck to pause it)
            </label>
          )}
          <div className="flex items-center gap-2 border-t border-ops-line pt-3">
            {habit && (
              <Button
                type="button"
                variant="danger"
                disabled={del.isPending}
                onClick={() => window.confirm(`Delete ${habit.name} and its history?`) && del.mutate(habit.id, { onSuccess: close })}
              >
                Delete
              </Button>
            )}
            <div className="ml-auto flex gap-2">
              <Button type="button" variant="ghost" onClick={close}>
                Cancel
              </Button>
              <Button type="submit" variant="solid" disabled={!canSave || save.isPending}>
                {save.isPending ? "Saving…" : habit ? "Save" : "Add"}
              </Button>
            </div>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
