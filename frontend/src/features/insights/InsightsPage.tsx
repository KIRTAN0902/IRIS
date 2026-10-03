import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  useDecisionHistory,
  useProductivity,
  useSignals,
  useStartupTrends,
  useTimeAnalytics,
} from "@/hooks/queries";
import { Skeleton } from "@/components/ui/Overlay";
import { Lamp, Panel, ProvenanceChip } from "@/components/ui/Panel";
import { fmtTime } from "@/lib/format";

const AREA_COLORS: Record<string, string> = {
  COLLEGE: "var(--color-ai)",
  INTERNSHIP: "var(--color-caution)",
  STARTUP: "var(--color-go)",
  PERSONAL: "var(--color-ink-faint)",
};

/** INSIGHTS — few charts, high signal. Time allocation + startup trend + decision history + signals. */
export function InsightsPage() {
  const timeWeek = useTimeAnalytics("week");
  const prodMonth = useProductivity("month");
  const trends = useStartupTrends(8);
  const signals = useSignals({ limit: 10 });
  const decisions = useDecisionHistory({ limit: 10 });

  return (
    <div className="space-y-6">
      <h1 className="text-[30px] font-bold leading-tight tracking-[-0.02em] text-ink">Insights</h1>

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Focus minutes by area · this week" lamp={<span />}>
          {timeWeek.isLoading ? (
            <Skeleton className="h-56" />
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={chartData(timeWeek.data?.focused_minutes)} margin={{ top: 8, right: 8, left: -2, bottom: 0 }}>
                <CartesianGrid stroke="var(--color-ops-line)" strokeDasharray="2 4" vertical={false} />
                <XAxis dataKey="area" tick={{ fill: "var(--color-ink-faint)", fontSize: 11 }} axisLine={{ stroke: "var(--color-ops-line)" }} tickLine={false} />
                <YAxis tick={{ fill: "var(--color-ink-faint)", fontSize: 11 }} axisLine={false} tickLine={false} width={48} unit="m" />
                <Tooltip
                  cursor={{ fill: "var(--color-ops-raised)" }}
                  contentStyle={{ background: "var(--color-ops-void)", border: "1px solid var(--color-ops-line)", borderRadius: 8, fontFamily: "inherit", fontSize: 12 }}
                  labelStyle={{ color: "var(--color-ink)" }}
                  itemStyle={{ color: "var(--color-ink-faint)" }}
                />
                <Bar dataKey="minutes" radius={0} isAnimationActive={false}>
                  {(chartData(timeWeek.data?.focused_minutes) ?? []).map((d) => (
                    <Cell key={d.area} fill={AREA_COLORS[d.area]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
          <p className="mt-2 text-[11px] leading-snug text-ink-faint">
            Hours are inputs. The funnel below measures outcomes.
          </p>
        </Panel>

        <Panel title="Startup funnel · weekly" lamp={<span />}>
          {trends.isLoading ? (
            <Skeleton className="h-56" />
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={trends.data?.weeks ?? []} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
                <CartesianGrid stroke="var(--color-ops-line)" strokeDasharray="2 4" vertical={false} />
                <XAxis
                  dataKey="week_start"
                  tickFormatter={(v) => new Date(v).toLocaleDateString([], { day: "numeric", month: "short" })}
                  tick={{ fill: "var(--color-ink-faint)", fontSize: 11 }}
                  axisLine={{ stroke: "var(--color-ops-line)" }}
                  tickLine={false}
                />
                <YAxis tick={{ fill: "var(--color-ink-faint)", fontSize: 11 }} axisLine={false} tickLine={false} width={36} allowDecimals={false} />
                <Tooltip
                  contentStyle={{ background: "var(--color-ops-void)", border: "1px solid var(--color-ops-line)", borderRadius: 8, fontFamily: "inherit", fontSize: 12 }}
                  labelStyle={{ color: "var(--color-ink)" }}
                  itemStyle={{ color: "var(--color-ink-faint)" }}
                />
                <Line type="monotone" dataKey="outreach_sent" name="outreach" stroke="var(--color-ai)" strokeWidth={1.5} dot={false} isAnimationActive={false} />
                <Line type="monotone" dataKey="replies" name="replies" stroke="var(--color-caution)" strokeWidth={1.5} dot={false} isAnimationActive={false} />
                <Line type="monotone" dataKey="meetings" name="meetings" stroke="var(--color-go)" strokeWidth={1.5} dot={false} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </Panel>
      </div>

      {prodMonth.data && (
        <Panel title="Throughput · this month" lamp={<span />} bodyClassName="!py-4">
          <dl className="grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-4">
            {[
              ["Tasks completed", prodMonth.data.tasks_completed],
              ["Completion rate", `${prodMonth.data.completion_rate}%`],
              ["Avg task", `${prodMonth.data.average_task_duration_minutes}m`],
              ["Focus sessions", prodMonth.data.focus_sessions_count],
            ].map(([label, value]) => (
              <div key={String(label)}>
                <dd className="tnum text-[24px] font-semibold text-ink">{value}</dd>
                <dt className="text-[11px] text-ink-dim">{label}</dt>
              </div>
            ))}
          </dl>
        </Panel>
      )}

      {/* Intelligence & Cross-Domain telemetry */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Active Cross-Domain Signals" lamp={<Lamp tone="dim" />} bodyClassName="!p-0">
          {signals.isLoading ? (
            <div className="p-4"><Skeleton className="h-32" /></div>
          ) : !signals.data?.length ? (
            <div className="p-4"><p className="text-[13px] text-ink-faint">No active signals.</p></div>
          ) : (
            <ol className="divide-y divide-ops-line">
              {signals.data.map((s, idx) => (
                <li key={idx} className="flex items-center gap-3 px-4 py-2.5">
                  <Lamp tone={s.urgency >= 0.7 ? "critical" : "dim"} />
                  <div className="min-w-0 flex-1 truncate">
                    <p className="truncate text-[13px] font-medium text-ink">{s.title}</p>
                    <p className="truncate text-[11px] text-ink-faint">
                      {s.domain} · {s.provenance}
                      {s.summary ? ` — ${s.summary}` : ""}
                    </p>
                  </div>
                  <span className="tnum text-[11px] text-ink-dim">
                    imp {Math.round(s.importance * 100)}%
                  </span>
                </li>
              ))}
            </ol>
          )}
        </Panel>

        <Panel title="Decision Audit Log" lamp={<Lamp tone="ai" />} bodyClassName="!p-0">
          {decisions.isLoading ? (
            <div className="p-4"><Skeleton className="h-32" /></div>
          ) : !decisions.data?.length ? (
            <div className="p-4"><p className="text-[13px] text-ink-faint">No decisions recorded yet.</p></div>
          ) : (
            <ol className="divide-y divide-ops-line">
              {decisions.data.map((d) => (
                <li key={d.id} className="flex items-center gap-3 px-4 py-2.5">
                  <ProvenanceChip source={d.source as "AI" | "DETERMINISTIC"} />
                  <div className="min-w-0 flex-1 truncate">
                    <p className="truncate text-[13px] font-medium text-ink">{d.title}</p>
                    <p className="text-[11px] text-ink-faint">
                      {d.decision_type} · {fmtTime(d.created_at)}
                    </p>
                  </div>
                  {d.feedback && (
                    <span className="border border-ops-line bg-ops-raised px-1.5 py-0.5 text-[10px] text-ink-dim">
                      {d.feedback}
                    </span>
                  )}
                </li>
              ))}
            </ol>
          )}
        </Panel>
      </div>
    </div>
  );
}

function chartData(minutes?: { COLLEGE?: number; INTERNSHIP?: number; STARTUP?: number; PERSONAL?: number }) {
  return Object.entries(minutes ?? {}).map(([area, mins]) => ({ area, minutes: Math.round(mins ?? 0) }));
}

