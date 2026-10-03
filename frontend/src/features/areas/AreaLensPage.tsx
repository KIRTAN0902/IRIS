import { Link } from "react-router-dom";
import { useTasks, useTimeAnalytics } from "@/hooks/queries";
import type { LifeArea } from "@/types/api";
import { EmptyState, Skeleton } from "@/components/ui/Overlay";
import { Lamp, Panel } from "@/components/ui/Panel";
import { fmtDay } from "@/lib/format";
import { TaskRow } from "@/features/home/HomePage";

/**
 * AREA LENS — College and Internship are focused views over the same life
 * data (open work + where the hours actually went). Not separate silos.
 */
export function AreaLensPage({ area, title }: { area: LifeArea; title: string }) {
  const open = useTasks({ area, open_only: true, limit: 100 });
  const time = useTimeAnalytics("week");

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-baseline gap-4">
        <h1 className="text-[30px] font-bold leading-tight tracking-[-0.02em] text-ink">{title}</h1>
        <span className="tnum text-[12px] text-ink-faint">{open.data?.length ?? 0} open</span>
        <Link to="/tasks" className="ml-auto text-[12px] text-ink-faint underline-offset-4 hover:text-ink hover:underline">
          Full register →
        </Link>
      </header>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <Panel title={`Open work · ${title}`} lamp={<Lamp tone={area === "STARTUP" ? "go" : "dim"} />} bodyClassName="!p-0">
            {open.isLoading ? (
              <div className="p-4"><Skeleton className="h-32" /></div>
            ) : !open.data?.length ? (
              <div className="p-4"><EmptyState message={`${title} is clear.`} /></div>
            ) : (
              <ol className="divide-y divide-ops-line px-4">
                {open.data.map((t) => <TaskRow key={t.id} task={t} />)}
              </ol>
            )}
          </Panel>
        </div>

        <Panel title="Hours this week" lamp={<Lamp tone="dim" />}>
          {time.isLoading && <Skeleton className="h-16" />}
          {time.data ? (
            <>
              <p className="tnum text-[26px] font-semibold text-ink">
                {(time.data.focused_minutes[area] ?? 0) >= 60
                  ? `${Math.round((time.data.focused_minutes[area] ?? 0) / 6) / 10}h`
                  : `${time.data.focused_minutes[area] ?? 0}m`}
              </p>
              <p className="mt-1 text-[12px] text-ink-faint">from focus sessions · progress &gt; activity</p>
            </>
          ) : null}
        </Panel>
      </div>

      {/* Upcoming deadlines for this area live on the shared urgency axis */}
      <UpcomingForArea area={area} />
    </div>
  );
}

function UpcomingForArea({ area }: { area: LifeArea }) {
  const all = useTasks({ area, open_only: true, limit: 100 });
  const upcoming = (all.data ?? [])
    .filter((t) => t.deadline)
    .sort((a, b) => a.deadline!.localeCompare(b.deadline!))
    .slice(0, 5);

  if (!upcoming.length) return null;
  return (
    <Panel title="Next deadlines" lamp={<Lamp tone="caution" />} bodyClassName="!p-0">
      <ol className="divide-y divide-ops-line">
        {upcoming.map((t) => (
          <li key={t.id} className="flex items-center gap-3 px-4 py-2.5">
            <span className="tnum w-20 shrink-0 text-[12px] text-caution">{fmtDay(t.deadline!)}</span>
            <span className="min-w-0 flex-1 truncate text-[14px] text-ink">{t.title}</span>
            {t.estimated_duration != null && <span className="tnum text-[12px] text-ink-faint">{t.estimated_duration}m</span>}
          </li>
        ))}
      </ol>
    </Panel>
  );
}
