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
  COLLEGE: "#7dd3fc",
  INTERNSHIP: "#fbbf24",
  STARTUP: "#4ade80",
  PERSONAL: "#8fa3b0",
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
      <h1 className="font-[family-name:var(--font-display)] text-[22px] font-semibold tracking-wide">Insights</h1>

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Focus minutes by area · this week" lamp={<span />}>
          {timeWeek.isLoading ? (
            <Skeleton className="h-56" />
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={chartData(timeWeek.data?.focused_minutes)} margin={{ top: 8, right: 8, left: -2, bottom: 0 }}>
                <CartesianGrid stroke="#223041" strokeDasharray="2 4" vertical={false} />
                <XAxis dataKey="area" tick={{ fill: "#5c6f7c", fontSize: 11 }} axisLine={{ stroke: "#223041" }} tickLine={false} />
                <YAxis tick={{ fill: "#5c6f7c", fontSize: 11 }} axisLine={false} tickLine={false} width={48} unit="m" />
                <Tooltip
                  cursor={{ fill: "#18223066" }}
                  contentStyle={{ background: "#131b24", border: "1px solid #223041", borderRadius: 0, fontFamily: "JetBrains Mono", fontSize: 12 }}
                  labelStyle={{ color: "#e6edf3" }}
                  itemStyle={{ color: "#8fa3b0" }}
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
                <CartesianGrid stroke="#223041" strokeDasharray="2 4" vertical={false} />
                <XAxis
                  dataKey="week_start"
                  tickFormatter={(v) => new Date(v).toLocaleDateString([], { day: "numeric", month: "short" })}
                  tick={{ fill: "#5c6f7c", fontSize: 11 }}
                  axisLine={{ stroke: "#223041" }}
                  tickLine={false}
                />
                <YAxis tick={{ fill: "#5c6f7c", fontSize: 11 }} axisLine={false} tickLine={false} width={36} allowDecimals={false} />
                <Tooltip
                  contentStyle={{ background: "#131b24", border: "1px solid #223041", borderRadius: 0, fontFamily: "JetBrains Mono", fontSize: 12 }}
                  labelStyle={{ color: "#e6edf3" }}
                  itemStyle={{ color: "#8fa3b0" }}
                />
                <Line type="monotone" dataKey="outreach_sent" name="outreach" stroke="#7dd3fc" strokeWidth={1.5} dot={false} isAnimationActive={false} />
                <Line type="monotone" dataKey="replies" name="replies" stroke="#fbbf24" strokeWidth={1.5} dot={false} isAnimationActive={false} />
                <Line type="monotone" dataKey="meetings" name="meetings" stroke="#4ade80" strokeWidth={1.5} dot={false} isAnimationActive={false} />
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
                <dt className="text-[11px] uppercase tracking-[0.12em] text-ink-dim">{label}</dt>
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
                    <span className="border border-ops-line bg-ops-raised px-1.5 py-0.5 text-[10px] uppercase tracking-wider text-ink-dim">
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

