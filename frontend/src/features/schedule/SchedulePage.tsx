import { useMemo } from "react";
import { useAvailability, useCalendarEvents, useRecurringSchedules, useTimeBlocks } from "@/hooks/queries";
import { EmptyState, Skeleton } from "@/components/ui/Overlay";
import { Lamp, Panel } from "@/components/ui/Panel";
import { fmtTime24, humanDuration, parseUtc, toNaiveUtc } from "@/lib/format";

/** SCHEDULE — the day's equipment: events, committed blocks, free windows, and recurring routines. */
export function SchedulePage() {
  const now = new Date();
  const dayStart = new Date(now); dayStart.setHours(0, 0, 0, 0);
  const dayEnd = new Date(dayStart); dayEnd.setDate(dayEnd.getDate() + 1);

  // Backend wants naive UTC; approximate local-day window in ISO.
  const range = { start: toNaiveUtc(dayStart), end: toNaiveUtc(dayEnd) };
  const blocks = useTimeBlocks(range);
  const events = useCalendarEvents(range);
  const availability = useAvailability({ window_start: range.start, window_end: range.end });
  const recurring = useRecurringSchedules();

  const rows = useMemo(() => {
    type Row = { kind: "EVENT" | "BLOCK"; start: Date; end: Date; title: string; sub: string | null; cancelled?: boolean; task_id?: number | null };
    const list: Row[] = [
      ...(events.data ?? []).map((e) => ({
        kind: "EVENT" as const, start: parseUtc(e.start_time), end: parseUtc(e.end_time),
        title: e.title, sub: e.location,
      })),
      ...(blocks.data ?? []).map((b) => ({
        kind: "BLOCK" as const, start: parseUtc(b.start_time), end: parseUtc(b.end_time),
        title: b.type === "FOCUS" ? `Focus${b.task_id ? ` · task #${b.task_id}` : ""}` : b.type.toLowerCase(),
        sub: b.notes ?? null, cancelled: b.status === "CANCELLED", task_id: b.task_id,
      })),
    ];
    return list.sort((a, b) => a.start.getTime() - b.start.getTime());
  }, [events.data, blocks.data]);

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-baseline gap-4">
        <h1 className="text-[30px] font-bold leading-tight tracking-[-0.02em] text-ink">Schedule</h1>
        {availability.data && (
          <p className="tnum text-[12px] text-ink-dim">
            {humanDuration(availability.data.total_free_minutes)} free today
          </p>
        )}
      </header>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <Panel title="Today's timeline" lamp={<Lamp tone="dim" />} bodyClassName="!p-0">
            {blocks.isLoading || events.isLoading ? (
              <div className="p-4"><Skeleton className="h-40" /></div>
            ) : rows.length === 0 ? (
              <div className="p-4">
                <EmptyState
                  message="A clear board."
                  hint="Accept blocks from Today's plan draft or commit one from a task."
                />
              </div>
            ) : (
              <>
                {/* urgency axis: earliest at top */}
                <ol className="divide-y divide-ops-line">
                  {rows.map((r, i) => {
                    const past = r.end < now;
                    return (
                      <li key={i} className={`flex items-center gap-3 px-4 py-2.5 ${past ? "opacity-45" : ""}`}>
                        <span className="tnum w-24 shrink-0 text-[12px] text-ink-faint">
                          {fmtTime24(r.start.toISOString())}–{fmtTime24(r.end.toISOString())}
                        </span>
                        <Lamp tone={r.cancelled ? "dim" : r.kind === "EVENT" ? "caution" : "go"} pulse={!past && !r.cancelled} />
                        <span className={`min-w-0 flex-1 truncate text-[14px] ${r.cancelled ? "text-ink-faint line-through" : "text-ink"}`}>
                          {r.title}
                        </span>
                        {r.sub && <span className="hidden max-w-40 truncate text-[11px] text-ink-faint sm:block">{r.sub}</span>}
                      </li>
                    );
                  })}
                </ol>
              </>
            )}
          </Panel>
        </div>

        <div>
          <Panel title="Free windows · next 12h" lamp={<Lamp tone={availability.data?.total_free_minutes ? "go" : "critical"} />}>
            {availability.isLoading && <Skeleton className="h-24" />}
            {availability.data?.free_intervals.length ? (
              <ul className="space-y-2">
                {availability.data.free_intervals.map((iv, i) => (
                  <li key={i} className="flex items-baseline justify-between gap-2">
                    <span className="tnum text-[13px] text-ink">
                      {fmtTime24(iv.start)}–{fmtTime24(iv.end)}
                    </span>
                    <span className="tnum text-[12px] text-go">{humanDuration(iv.minutes)}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-[13px] text-ink-faint">
                Fully booked. IRIS won't invent time that isn't there.
              </p>
            )}
          </Panel>
        </div>
      </div>

      {/* Recurring Commitments & Routines */}
      <section className="space-y-2">
        <Panel
          title="Weekly recurring routines & constraints"
          lamp={<Lamp tone="dim" />}
          bodyClassName="!p-0"
        >
          {recurring.isLoading ? (
            <div className="p-4"><Skeleton className="h-24" /></div>
          ) : !recurring.data?.length ? (
            <div className="p-4"><p className="text-[13px] text-ink-faint">No recurring routines configured.</p></div>
          ) : (
            <ol className="divide-y divide-ops-line">
              {recurring.data.map((r) => (
                <li key={r.id} className="flex items-center gap-3 px-4 py-2.5">
                  <Lamp tone={r.is_hard_constraint ? "caution" : "dim"} />
                  <span className="tnum w-24 shrink-0 text-[12px] text-ink-faint">
                    {r.start_time}–{r.end_time}
                  </span>
                  <div className="min-w-0 flex-1 truncate">
                    <span className="text-[14px] font-medium text-ink">{r.name}</span>
                    <span className="ml-2 text-[11px] text-ink-faint">
                      {r.days_of_week}
                    </span>
                  </div>
                  <span className="border border-ops-line px-1.5 py-0.5 text-[10px] text-ink-faint">
                    {r.is_hard_constraint ? "Hard constraint" : "Flexible routine"}
                  </span>
                </li>
              ))}
            </ol>
          )}
        </Panel>
      </section>
    </div>
  );
}



