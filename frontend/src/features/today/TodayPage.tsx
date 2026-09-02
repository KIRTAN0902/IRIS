import { useState } from "react";
import { CalendarClock, CheckCircle2, Clock, ListTree, ShieldAlert } from "lucide-react";
import {
  useCreateTimeBlock,
  useMe,
  usePlanDay,
  useTasks,
  useTimeBlocks,
  useTodayState,
} from "@/hooks/queries";
import type { PlanDayBlock } from "@/types/api";
import { Button } from "@/components/ui/Button";
import { EmptyState, Skeleton } from "@/components/ui/Overlay";
import { Lamp, Panel, ProvenanceChip } from "@/components/ui/Panel";
import { fmtTime, humanDuration, parseUtc } from "@/lib/format";
import { TaskRow } from "@/features/home/HomePage";

/** TODAY — coherent day state: real-time window status → constraints → urgent obligations → tasks. */
export function TodayPage() {
  const me = useMe();
  const todayState = useTodayState();
  const overdue = useTasks({ overdue_only: true });
  const allOpen = useTasks({ open_only: true, limit: 200 });

  const now = new Date();
  const localToday = new Date(now.getTime() - now.getTimezoneOffset() * 60000);
  const todayIsoEnd = new Date(localToday);
  todayIsoEnd.setHours(23, 59, 59);

  const dueToday = (allOpen.data ?? []).filter(
    (t) => t.deadline && parseUtc(t.deadline) <= todayIsoEnd && !t.is_overdue,
  );
  const noDeadline = (allOpen.data ?? []).filter((t) => !t.deadline);

  const win = todayState.data?.current_window;
  const urgentObligations = todayState.data?.urgent_obligations ?? [];
  const flexWindows = todayState.data?.flexible_windows ?? [];

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <div>
          <h1 className="font-[family-name:var(--font-display)] text-[22px] font-semibold tracking-wide">
            Today
          </h1>
          <p className="text-[13px] text-ink-faint">
            {now.toLocaleDateString([], { weekday: "long", day: "numeric", month: "long" })}
            {me.data ? ` · ${me.data.timezone}` : ""}
          </p>
        </div>
        {todayState.data && (
          <p className="tnum text-[12px] text-ink-dim">
            {humanDuration(todayState.data.available_minutes_today)} flexible time today
          </p>
        )}
      </header>

      {/* Real-time Context / Current Window Status */}
      {todayState.isLoading ? (
        <Skeleton className="h-16" />
      ) : win ? (
        <section className="flex flex-wrap items-center justify-between gap-3 border border-ops-line-bright bg-ops-panel/60 px-4 py-3">
          <div className="flex items-center gap-3">
            <Lamp
              tone={win.is_in_hard_constraint ? "caution" : win.is_in_flexible_window ? "go" : "dim"}
              pulse={win.is_in_hard_constraint || win.is_in_flexible_window}
            />
            <div>
              <p className="text-[14px] font-medium text-ink">
                {win.is_in_hard_constraint
                  ? `Active commitment: ${win.active_block_name ?? "Routine"}`
                  : win.is_in_flexible_window
                    ? "In flexible window · Free to focus"
                    : "Outside scheduled windows"}
              </p>
              <p className="tnum text-[11px] text-ink-faint">
                {win.is_in_hard_constraint && win.minutes_remaining_in_block != null
                  ? `${win.minutes_remaining_in_block}m remaining in block`
                  : win.next_hard_constraint_name
                    ? `Next: ${win.next_hard_constraint_name} in ${win.minutes_until_next_hard_constraint ?? 0}m`
                    : "No upcoming fixed constraints today"}
              </p>
            </div>
          </div>
          {flexWindows.length > 0 && (
            <div className="flex flex-wrap items-center gap-2 text-[11px] text-ink-dim">
              <Clock size={12} className="text-ink-faint" />
              <span>Windows:</span>
              {flexWindows.map((fw, i) => (
                <span key={i} className="tnum border border-ops-line bg-ops-raised px-1.5 py-0.5">
                  {fw.start}–{fw.end}
                </span>
              ))}
            </div>
          )}
        </section>
      ) : null}

      <PlanDayDraft />

      {/* Urgent Obligations (if detected by cross-domain context) */}
      {urgentObligations.length > 0 && (
        <section className="space-y-1">
          <h2 className="label-caps flex items-center gap-2 text-critical">
            <ShieldAlert size={12} /> Urgent Obligations
            <span className="tnum text-ink-faint">{urgentObligations.length}</span>
          </h2>
          <ol className="divide-y divide-ops-line border-y border-ops-line bg-critical-dim/10">
            {urgentObligations.map((o, idx) => (
              <li key={idx} className="flex items-center gap-3 px-3 py-2">
                <Lamp tone="critical" pulse />
                <span className="min-w-0 flex-1 text-[13px] font-medium text-ink">{o.title}</span>
                {o.deadline && <span className="tnum text-[11px] text-critical">{o.deadline}</span>}
                {o.area && (
                  <span className="border border-ops-line px-1 text-[10px] uppercase tracking-wider text-ink-faint">
                    {o.area}
                  </span>
                )}
              </li>
            ))}
          </ol>
        </section>
      )}

      <section className="space-y-1">
        <h2 className="label-caps flex items-center gap-2">
          <Lamp tone="critical" pulse={!!overdue.data?.length} /> Overdue
          <span className="tnum text-ink-faint">{overdue.data?.length ?? 0}</span>
        </h2>
        {overdue.isLoading ? (
          <Skeleton className="h-16" />
        ) : overdue.data?.length ? (
          <ol className="divide-y divide-ops-line border-y border-ops-line">
            {overdue.data.map((t) => (
              <li key={t.id}>
                <TaskRow task={t} />
              </li>
            ))}
          </ol>
        ) : (
          <p className="py-2 text-[13px] text-ink-faint">Nothing overdue.</p>
        )}
      </section>

      <section className="space-y-1">
        <h2 className="label-caps flex items-center gap-2">
          <CalendarClock size={12} /> Due today
          <span className="tnum text-ink-faint">{dueToday.length}</span>
        </h2>
        {dueToday.length ? (
          <ol className="divide-y divide-ops-line border-y border-ops-line">
            {dueToday.map((t) => (
              <li key={t.id}>
                <TaskRow task={t} />
              </li>
            ))}
          </ol>
        ) : (
          <EmptyState message="Nothing due today." hint="The GO panel knows best — check Home." />
        )}
      </section>

      <section className="space-y-1">
        <h2 className="label-caps flex items-center gap-2">
          <ListTree size={12} /> Open · no deadline
          <span className="tnum text-ink-faint">{noDeadline.length}</span>
        </h2>
        {noDeadline.length ? (
          <ol className="divide-y divide-ops-line border-y border-ops-line">
            {noDeadline.slice(0, 10).map((t) => (
              <li key={t.id}>
                <TaskRow task={t} />
              </li>
            ))}
          </ol>
        ) : (
          <p className="py-2 text-[13px] text-ink-faint">Every open task has a deadline. Disciplined.</p>
        )}
      </section>
    </div>
  );
}

/**
 * PLAN MY DAY — AI drafts blocks inside real free time; nothing persists
 * until you accept each block.
 */
function PlanDayDraft() {
  const planDay = usePlanDay();
  const createBlock = useCreateTimeBlock();
  const [draft, setDraft] = useState<Awaited<ReturnType<ReturnType<typeof usePlanDay>["mutateAsync"]>> | null>(null);
  const [acceptedIds, setAccepted] = useState<Set<number>>(new Set());
  const timeBlocks = useTimeBlocks();
  const openTasks = useTasks({ open_only: true, limit: 200 });
  const titleFor = (id: number) => (openTasks.data ?? []).find((t) => t.id === id)?.title;

  const run = async () => {
    const result = await planDay.mutateAsync(undefined);
    setDraft(result);
    setAccepted(new Set());
  };

  const accept = (b: PlanDayBlock) => {
    if (b.task_id == null || acceptedIds.has(b.task_id)) return;
    createBlock.mutate(
      {
        task_id: b.task_id,
        start_time: b.start,
        end_time: b.end,
        type: "FOCUS",
        notes: b.reason,
      },
      {
        onSuccess: () => {
          setAccepted((prev) => new Set(prev).add(b.task_id!));
        },
      },
    );
  };

  const acceptAll = () => {
    for (const b of draft?.blocks ?? []) accept(b);
  };

  const existingFor = (taskId: number) =>
    (timeBlocks.data ?? []).some(
      (tb) =>
        tb.task_id === taskId &&
        tb.status !== "CANCELLED" &&
        draft?.blocks.some((b) => b.task_id === taskId),
    );

  return (
    <Panel
      title="Draft day plan"
      lamp={<Lamp tone="ai" />}
      actions={
        draft?.source ? <ProvenanceChip source={draft.source} /> : undefined
      }
    >
      {!draft && (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="max-w-xl text-[13px] leading-relaxed text-ink-dim">
            IRIS fits your highest-priority tasks into the free windows actually available today.
            The plan is a proposal — you accept each block before it lands on your schedule.
          </p>
          <Button variant="outline" onClick={run} disabled={planDay.isPending}>
            <ListTree size={13} />
            {planDay.isPending ? "Drafting…" : "Generate draft"}
          </Button>
        </div>
      )}

      {draft && (
        <div className="space-y-3">
          {draft.summary && <p className="text-[13px] text-ink-dim">{draft.summary}</p>}
          {draft.blocks.length === 0 ? (
            <p className="text-[13px] text-caution">No workable free window found for today.</p>
          ) : (
            <ol className="divide-y divide-ops-line border-y border-ops-line">
              {draft.blocks.map((b, i) => {
                const isBreakBlock = b.task_id == null;
                const done = b.task_id != null && acceptedIds.has(b.task_id);
                return (
                  <li key={i} className="flex items-center gap-3 py-2">
                    <span className="tnum w-28 shrink-0 text-[12px] text-ink-faint">
                      {fmtTime(b.start)}–{fmtTime(b.end)}
                    </span>
                    <Lamp tone={isBreakBlock ? "dim" : done ? "go" : "caution"} />
                    <span className={`min-w-0 flex-1 truncate text-[14px] ${isBreakBlock ? "text-ink-faint" : done ? "text-ink-faint line-through" : "text-ink"}`}>
                      {isBreakBlock
                        ? "Break"
                        : `${titleFor(b.task_id!) ?? `Task #${b.task_id}`} — ${b.reason}`}
                    </span>
                    {!isBreakBlock && !done && (
                      <Button size="sm" variant="go" onClick={() => accept(b)} disabled={createBlock.isPending || existingFor(b.task_id!)}>
                        Accept
                      </Button>
                    )}
                    {!isBreakBlock && done && <CheckCircle2 size={15} className="text-go" />}
                  </li>
                );
              })}
            </ol>
          )}
          <div className="flex flex-wrap gap-2">
            {draft.unscheduled_task_ids.length > 0 && (
              <p className="tnum mr-auto self-center text-[11px] text-caution">
                {draft.unscheduled_task_ids.length} task(s) don't fit today's windows — realistic, not forced.
              </p>
            )}
            <Button size="sm" variant="ghost" onClick={() => setDraft(null)}>
              Discard
            </Button>
            <Button size="sm" variant="go" onClick={acceptAll} disabled={createBlock.isPending}>
              Accept all
            </Button>
          </div>
        </div>
      )}
    </Panel>
  );
}
