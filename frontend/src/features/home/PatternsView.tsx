import { ArrowDownRight, ArrowUpRight, Minus, Sparkles } from "lucide-react";
import { useBehavior } from "@/hooks/queries";
import { cn } from "@/lib/format";
import type { Behavior, BehaviorTrend } from "@/types/api";
import { inr } from "@/features/finance/money";

/**
 * What IRIS has learned from how the user actually follows through, and how it
 * adapts because of it. Patterns appear once there's enough evidence.
 */

const CONFIDENCE: Record<Behavior["confidence"], string> = {
  early: "Still learning - a few weeks of tasks, routines and workouts sharpen this.",
  growing: "Getting to know you - patterns firm up as more days are logged.",
  solid: "Based on plenty of history.",
};

function Trend({ t }: { t?: BehaviorTrend | null }) {
  if (!t) return null;
  const Icon = t.direction === "improving" ? ArrowUpRight : t.direction === "slipping" ? ArrowDownRight : Minus;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-0.5 text-[12px]",
        t.direction === "improving" ? "text-go" : t.direction === "slipping" ? "text-caution" : "text-ink-faint",
      )}
    >
      <Icon size={13} />
      {t.direction} ({t.prior_pct}% → {t.recent_pct}%)
    </span>
  );
}

function Bar({ pct, tone = "ink" }: { pct: number; tone?: "ink" | "go" | "caution" | "critical" }) {
  const fill = { ink: "bg-ink", go: "bg-go", caution: "bg-caution", critical: "bg-critical" }[tone];
  return (
    <div className="h-1.5 overflow-hidden rounded-full bg-ops-raised">
      <div className={cn("h-full rounded-full", fill)} style={{ width: `${Math.max(2, Math.min(100, pct))}%` }} />
    </div>
  );
}

const tone = (pct: number) => (pct >= 80 ? "go" : pct >= 50 ? "ink" : pct >= 30 ? "caution" : "critical");

function Card({ title, right, children }: { title: string; right?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border border-ops-line p-3.5">
      <header className="mb-2 flex items-baseline justify-between gap-2">
        <h3 className="text-[14px] font-semibold text-ink">{title}</h3>
        {right}
      </header>
      {children}
    </section>
  );
}

function Learning({ have, need, what }: { have: number; need: number; what: string }) {
  return (
    <p className="text-[13px] text-ink-faint">
      Learning… {have} of {need} {what} so far.
    </p>
  );
}

export function PatternsView() {
  const q = useBehavior();
  if (q.isLoading) return <p className="py-8 text-center text-[13px] text-ink-dim">Looking at your history…</p>;
  const b = q.data;
  if (!b) return <p className="py-8 text-center text-[13px] text-ink-dim">Couldn't load patterns.</p>;
  const d = b.deadlines;
  const r = b.routines;
  const w = b.workouts;
  const m = b.money;

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-4 rounded-xl border border-ops-line-bright bg-ops-panel p-4">
        <div className="text-center">
          <p className="tnum text-[34px] font-semibold leading-none text-ink">{b.consistency_score ?? "–"}</p>
          <p className="mt-1 text-[11px] uppercase tracking-[0.15em] text-ink-faint">consistency</p>
        </div>
        <div className="min-w-0 flex-1 text-[13px] text-ink-dim">
          <p>{CONFIDENCE[b.confidence]}</p>
          <p className="mt-1 text-ink-faint">
            Last {b.window_days} days · active with IRIS {b.engagement.active_days} of {b.engagement.of_days} days
          </p>
        </div>
      </div>

      {b.adapt.length > 0 && (
        <Card title="How IRIS adjusts to you" right={<Sparkles size={14} className="text-ink-faint" />}>
          <ul className="space-y-1.5">
            {b.adapt.map((a, i) => (
              <li key={i} className="text-[13px] leading-relaxed text-ink-dim">
                {a.you}
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card title="Deadlines" right={d?.enough ? <Trend t={d.trend} /> : undefined}>
        {d?.enough ? (
          <>
            <div className="mb-1 flex items-baseline justify-between text-[13px]">
              <span className="text-ink">{d.on_time_pct}% on time</span>
              <span className="tnum text-ink-faint">
                {d.on_time} on time · {d.late} late · {d.missed} missed
              </span>
            </div>
            <Bar pct={d.on_time_pct ?? 0} tone={tone(d.on_time_pct ?? 0)} />
            <p className="mt-1.5 text-[12px] text-ink-faint">
              {d.typical_delay && `Late ones by ~${d.typical_delay}. `}
              {d.slipping_area && `Slips most in ${d.slipping_area.toLowerCase()}.`}
            </p>
          </>
        ) : (
          <Learning have={d?.samples ?? 0} need={5} what="past deadlines" />
        )}
      </Card>

      <Card title="Routines" right={r?.enough ? <Trend t={r.trend} /> : undefined}>
        {r?.enough ? (
          <>
            <p className="mb-2 text-[13px] text-ink">{r.pct}% done on scheduled days</p>
            <ul className="space-y-2">
              {r.routines.map((x) => (
                <li key={x.name}>
                  <div className="mb-0.5 flex justify-between text-[12px]">
                    <span className="text-ink-dim">{x.name}</span>
                    <span className="tnum text-ink-faint">
                      {x.done}/{x.scheduled}
                    </span>
                  </div>
                  <Bar pct={x.pct} tone={tone(x.pct)} />
                </li>
              ))}
            </ul>
            {(r.weakest_day || r.strongest_day) && (
              <p className="mt-2 text-[12px] text-ink-faint">
                {r.strongest_day && `Best on ${r.strongest_day.day} (${r.strongest_day.pct}%). `}
                {r.weakest_day && `Weakest on ${r.weakest_day.day} (${r.weakest_day.pct}%).`}
              </p>
            )}
          </>
        ) : r ? (
          <Learning have={r.samples} need={5} what="routine days" />
        ) : (
          <p className="text-[13px] text-ink-faint">Add routines on the home screen to see your consistency.</p>
        )}
      </Card>

      {w && (
        <Card title="Workouts">
          {w.enough ? (
            <>
              <div className="mb-1 flex items-baseline justify-between text-[13px]">
                <span className="text-ink">{w.pct}% follow-through</span>
                <span className="tnum text-ink-faint">
                  {w.full} full · {w.partial} partial · {w.skipped} skipped
                </span>
              </div>
              <Bar pct={w.pct ?? 0} tone={tone(w.pct ?? 0)} />
            </>
          ) : (
            <Learning have={w.samples} need={3} what="planned workout days" />
          )}
        </Card>
      )}

      {m && (
        <Card title="Money">
          {m.enough ? (
            <p className="text-[13px] text-ink-dim">
              {inr(m.month_so_far ?? 0)} this month
              {m.change_pct != null && (
                <span className={m.change_pct > 0 ? "text-caution" : "text-go"}>
                  {" "}
                  ({m.change_pct > 0 ? "+" : ""}
                  {m.change_pct}% vs last month at this point)
                </span>
              )}
              . Most goes to {m.top_category}
              {m.weekend_heavier ? "; you spend more on weekends." : "."}
            </p>
          ) : (
            <Learning have={m.samples} need={8} what="expenses" />
          )}
        </Card>
      )}
    </div>
  );
}
