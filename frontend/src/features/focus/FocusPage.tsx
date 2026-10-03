import { useEffect, useState } from "react";
import { Play, Square, X } from "lucide-react";
import { useCompleteFocus, useFocusSessions, useStartFocus, useTasks } from "@/hooks/queries";
import { Button } from "@/components/ui/Button";
import { EmptyState, Skeleton } from "@/components/ui/Overlay";
import { Field, Select } from "@/components/ui/Field";
import { Lamp, Panel } from "@/components/ui/Panel";
import { fmtTime, humanDuration, parseUtc } from "@/lib/format";
import { useFocusStore } from "@/stores";

/** FOCUS — the deep-work console. Planned vs actual feeds IRIS's estimates. */
export function FocusPage() {
  const sessions = useFocusSessions();
  const running = useFocusStore((s) => s.running);
  const start = useStartFocus();
  const complete = useCompleteFocus();
  const openTasks = useTasks({ open_only: true, limit: 100 });

  const [taskId, setTaskId] = useState("");
  const [planned, setPlanned] = useState("50");

  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (!running) return;
    const startMs = parseUtc(running.started_at).getTime();
    const tick = () => setElapsed(Math.floor((Date.now() - startMs) / 1000));
    tick();
    const t = setInterval(tick, 1000);
    return () => clearInterval(t);
  }, [running]);

  const mm = String(Math.floor(elapsed / 60)).padStart(2, "0");
  const ss = String(elapsed % 60).padStart(2, "0");
  const plannedMin = Number(planned) || null;

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <h1 className="text-[30px] font-bold leading-tight tracking-[-0.02em] text-ink">Focus</h1>

      {/* Console */}
      <section className="border border-ops-line-bright bg-ops-panel/70 px-6 py-8 text-center">
        {running ? (
          <>
            <p className="label-caps mb-4 flex items-center justify-center gap-2">
              <Lamp tone="go" pulse /> Session running
            </p>
            <p className="tnum text-[64px] font-semibold leading-none tracking-tight text-ink tabular-nums">
              {mm}:{ss}
            </p>
            {running.task_id && (
              <p className="mt-3 text-[13px] text-ink-dim">
                Task #{running.task_id}
                {" — "}
                {(openTasks.data ?? []).find((t) => t.id === running.task_id)?.title ?? ""}
              </p>
            )}
            <div className="mt-7 flex justify-center gap-3">
              <Button variant="go" size="lg" onClick={() => complete.mutate({ id: running.id })} disabled={complete.isPending}>
                <Square size={14} /> Complete session
              </Button>
              <Button
                size="lg"
                variant="ghost"
                onClick={() => complete.mutate({ id: running.id, status: "PARTIAL" })}
                disabled={complete.isPending}
              >
                <X size={14} /> End early
              </Button>
            </div>
          </>
        ) : (
          <>
            <p className="label-caps mb-5">Arm a session</p>
            <div className="mx-auto grid max-w-md grid-cols-[1fr_auto_auto] items-end gap-3">
              <Field label="Task">
                <Select value={taskId} onChange={(e) => setTaskId(e.target.value)}>
                  <option value="">Unassigned focus</option>
                  {(openTasks.data ?? []).map((t) => (
                    <option key={t.id} value={t.id}>{t.title}</option>
                  ))}
                </Select>
              </Field>
              <Field label="Planned (m)">
                <Select value={planned} onChange={(e) => setPlanned(e.target.value)} className="w-24">
                  {["25", "50", "75", "90", "120"].map((v) => <option key={v}>{v}</option>)}
                </Select>
              </Field>
              <Button
                variant="go"
                size="lg"
                onClick={() =>
                  start.mutate({
                    task_id: taskId ? Number(taskId) : null,
                    planned_duration: plannedMin,
                  })
                }
                disabled={start.isPending}
              >
                <Play size={14} /> Start
              </Button>
            </div>
          </>
        )}
      </section>

      {/* History */}
      <Panel title="Session log" lamp={<Lamp tone="dim" />} bodyClassName="!p-0">
        {sessions.isLoading ? (
          <div className="p-4"><Skeleton className="h-24" /></div>
        ) : !sessions.data?.length ? (
          <div className="p-4"><EmptyState message="No sessions yet." hint="Actual durations teach IRIS your real pace." /></div>
        ) : (
          <ol className="divide-y divide-ops-line">
            {sessions.data.slice(0, 15).map((s) => {
              const variance =
                s.actual_duration != null && s.planned_duration != null && s.status !== "RUNNING"
                  ? s.actual_duration - s.planned_duration
                  : null;
              return (
                <li key={s.id} className="flex items-center gap-3 px-4 py-2.5">
                  <Lamp tone={s.status === "COMPLETED" ? "go" : s.status === "PARTIAL" ? "caution" : s.status === "ABANDONED" ? "critical" : "ai"} />
                  <span className="tnum w-28 shrink-0 text-[12px] text-ink-faint">{fmtTime(s.started_at)}</span>
                  <span className="min-w-0 flex-1 truncate text-[13px] text-ink-dim">
                    {(openTasks.data ?? []).find((t) => t.id === s.task_id)?.title ?? "Unassigned"}
                  </span>
                  {variance != null && (
                    <span className={`tnum text-[11px] ${variance >= 0 ? "text-go" : "text-caution"}`}>
                      {variance >= 0 ? "+" : ""}{humanDuration(variance)} vs plan
                    </span>
                  )}
                  <span className="tnum w-14 text-right text-[12px] text-ink">{humanDuration(s.actual_duration ?? 0)}</span>
                </li>
              );
            })}
          </ol>
        )}
      </Panel>
    </div>
  );
}
