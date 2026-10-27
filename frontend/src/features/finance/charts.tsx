import { useState } from "react";
import { AlertTriangle, ArrowRight, Check, ChevronRight } from "lucide-react";
import { cn } from "@/lib/format";
import { Skeleton } from "@/components/ui/Overlay";
import { useTransactions } from "@/hooks/queries";
import type { FinanceSummary, TransactionOut } from "@/types/api";
import { fmtDay, inr, inrShort, titleCase } from "@/features/finance/money";

/**
 * Finance charts. One series each, so identity comes from text labels; color is
 * reserved for status (budget meters) and for marking "today".
 */

// --- Daily spending columns ---------------------------------------------------------

export function DailySpendChart({ daily, today }: { daily: FinanceSummary["daily"]; today: string }) {
  const [hover, setHover] = useState<number | null>(null);
  const H = 120;
  const n = Math.max(daily.length, 1);
  const max = Math.max(...daily.map((d) => d.expense), 1);
  const slot = 100 / n;
  const total = daily.reduce((s, d) => s + d.expense, 0);
  const active = hover !== null ? daily[hover] : null;

  return (
    <figure className="relative">
      <figcaption className="mb-2 flex items-baseline justify-between text-[13px]">
        <span className="text-ink-dim">Spending by day</span>
        <span className="tnum text-ink-faint">peak {inrShort(max === 1 && !total ? 0 : max)}</span>
      </figcaption>
      <div className="relative" style={{ height: H }} onPointerLeave={() => setHover(null)}>
        <svg viewBox={`0 0 100 ${H}`} preserveAspectRatio="none" className="absolute inset-0 h-full w-full" aria-hidden>
          <line x1="0" x2="100" y1={H - 0.5} y2={H - 0.5} stroke="var(--color-ops-line-bright)" strokeWidth="1" vectorEffect="non-scaling-stroke" />
        </svg>
        <div className="absolute inset-0 flex items-end">
          {daily.map((d, i) => {
            const h = d.expense ? Math.max(3, (d.expense / max) * (H - 4)) : 0;
            const isToday = d.day === today;
            return (
              <button
                key={d.day}
                type="button"
                onPointerEnter={() => setHover(i)}
                onFocus={() => setHover(i)}
                onClick={() => setHover(i)}
                aria-label={`${fmtDay(d.day)}: ${inr(d.expense)} spent`}
                className="flex h-full items-end justify-center focus:outline-none"
                style={{ width: `${slot}%` }}
              >
                <span
                  className={cn(
                    "block rounded-t-[4px] transition-opacity",
                    isToday ? "bg-ink" : "bg-ink-faint",
                    hover !== null && hover !== i && "opacity-40",
                  )}
                  style={{ height: h, width: "min(24px, calc(100% - 2px))" }}
                />
              </button>
            );
          })}
        </div>
        {active && hover !== null && (
          <div
            role="status"
            className="pointer-events-none absolute -top-2 z-10 -translate-x-1/2 -translate-y-full whitespace-nowrap rounded-md border border-ops-line-bright bg-ops-void px-2.5 py-1.5 text-[12px] shadow-lg"
            style={{ left: `${Math.min(Math.max((hover + 0.5) * slot, 12), 88)}%` }}
          >
            <p className="tnum font-semibold text-ink">{inr(active.expense)}</p>
            <p className="text-ink-faint">{fmtDay(active.day)}</p>
          </div>
        )}
      </div>
      <div className="mt-1 flex justify-between text-[11px] text-ink-faint tnum">
        <span>{daily[0] ? Number(daily[0].day.slice(8)) : ""}</span>
        <span>{daily.length > 1 ? Number(daily[daily.length - 1].day.slice(8)) : ""}</span>
      </div>
      <table className="sr-only">
        <caption>Spending by day</caption>
        <tbody>
          {daily.map((d) => (
            <tr key={d.day}>
              <th>{fmtDay(d.day)}</th>
              <td>{inr(d.expense)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}

// --- Category bars ----------------------------------------------------------------------

function CategoryTransactionsDetail({
  month,
  category,
  onEdit,
  onViewCategory,
}: {
  month: string;
  category: string;
  onEdit?: (tx: TransactionOut) => void;
  onViewCategory?: (category: string) => void;
}) {
  const txQuery = useTransactions({ month, category, kind: "EXPENSE" });

  if (txQuery.isLoading) {
    return (
      <div className="mt-2.5 ml-5 space-y-2 py-1">
        <Skeleton className="h-5 w-3/4" />
        <Skeleton className="h-5 w-1/2" />
      </div>
    );
  }

  if (txQuery.error) {
    return (
      <p className="mt-2.5 ml-5 text-[12px] text-critical">
        Failed to load transactions for {category}.
      </p>
    );
  }

  const items = txQuery.data ?? [];

  if (items.length === 0) {
    return (
      <div className="mt-2.5 ml-5 rounded-md border border-ops-line/60 bg-ops-raised/20 px-3 py-2 text-[12px] text-ink-faint">
        No recorded expenses for {category} in {month}.
      </div>
    );
  }

  return (
    <div className="mt-2.5 ml-5 rounded-lg border border-ops-line bg-ops-void/80 p-2.5">
      <div className="mb-1.5 flex items-center justify-between text-[11px] text-ink-faint border-b border-ops-line/40 pb-1">
        <span>
          {items.length} {items.length === 1 ? "transaction" : "transactions"} · {inr(items.reduce((s, t) => s + t.amount, 0))}
        </span>
        {onViewCategory && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onViewCategory(category);
            }}
            className="inline-flex items-center gap-1 text-ai hover:underline cursor-pointer"
          >
            Filter in Transactions <ArrowRight size={11} />
          </button>
        )}
      </div>
      <ul className="divide-y divide-ops-line/40">
        {items.map((tx) => (
          <li key={tx.id}>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onEdit?.(tx);
              }}
              className="flex w-full items-center justify-between py-1.5 px-1.5 text-left rounded hover:bg-ops-raised/50 cursor-pointer transition-colors"
            >
              <div className="min-w-0 flex-1 pr-2">
                <p className="truncate text-[13px] text-ink font-medium">
                  {tx.note || tx.category}
                </p>
                <p className="truncate text-[11px] text-ink-faint">
                  {fmtDay(tx.occurred_on)} · {tx.account === "UPI" ? "UPI" : titleCase(tx.account)}
                </p>
              </div>
              <span className="tnum shrink-0 text-[13px] font-medium text-ink">
                −{inr(tx.amount)}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function CategoryBars({
  rows,
  month,
  onEdit,
  onViewCategory,
}: {
  rows: FinanceSummary["by_category"];
  month?: string;
  onEdit?: (tx: TransactionOut) => void;
  onViewCategory?: (category: string) => void;
}) {
  const [expanded, setExpanded] = useState<string | null>(null);
  const max = Math.max(...rows.map((r) => Math.max(r.amount, r.budget ?? 0)), 1);

  return (
    <ul className="space-y-3">
      {rows.map((r) => {
        const isExpanded = expanded === r.category;
        const over = r.budget != null && r.amount > r.budget;
        return (
          <li key={r.category} className="rounded-lg transition-colors">
            <button
              type="button"
              onClick={() => setExpanded(isExpanded ? null : r.category)}
              className="w-full text-left -mx-2 px-2 py-1.5 rounded-md hover:bg-ops-raised/40 transition-colors group cursor-pointer"
              aria-expanded={isExpanded}
              aria-label={`${r.category}: ${inr(r.amount)}. Click to ${isExpanded ? "collapse" : "view transactions"}`}
            >
              <div className="mb-1.5 flex items-baseline justify-between gap-3 text-[14px]">
                <span className="flex items-center gap-1.5 font-medium text-ink truncate group-hover:text-ai transition-colors">
                  <ChevronRight
                    size={14}
                    className={cn(
                      "shrink-0 text-ink-faint transition-transform duration-200",
                      isExpanded && "rotate-90 text-ink"
                    )}
                  />
                  <span className="truncate">{r.category}</span>
                </span>
                <span className="tnum shrink-0 text-ink">
                  {inr(r.amount)}
                  {r.budget != null && <span className="text-ink-faint"> / {inrShort(r.budget)}</span>}
                </span>
              </div>
              <div className="relative h-2">
                <div
                  className={cn("h-2 rounded-r-[4px] transition-all", over ? "bg-critical" : "bg-ink-dim group-hover:bg-ink")}
                  style={{ width: `${Math.max(1, (r.amount / max) * 100)}%` }}
                />
                {r.budget != null && (
                  <span
                    className="absolute -top-1 h-4 w-0.5 rounded bg-ink"
                    style={{ left: `calc(${(r.budget / max) * 100}% - 1px)` }}
                    title={`Budget ${inr(r.budget)}`}
                  />
                )}
              </div>
            </button>

            {isExpanded && month && (
              <CategoryTransactionsDetail
                month={month}
                category={r.category}
                onEdit={onEdit}
                onViewCategory={onViewCategory}
              />
            )}
          </li>
        );
      })}
    </ul>
  );
}

// --- Meters -------------------------------------------------------------------------------

/** Progress toward a limit or target. ``tone`` follows status; text always states it too. */
export function Meter({ percent, tone }: { percent: number; tone: "go" | "caution" | "critical" | "neutral" }) {
  const fill = { go: "bg-go", caution: "bg-caution", critical: "bg-critical", neutral: "bg-ink-dim" }[tone];
  return (
    <div className="h-2 overflow-hidden rounded-full bg-ops-raised" role="presentation">
      <div className={cn("h-full rounded-full", fill)} style={{ width: `${Math.min(100, Math.max(percent, 2))}%` }} />
    </div>
  );
}

export function budgetTone(percent: number) {
  return percent > 100 ? "critical" : percent >= 80 ? "caution" : "go";
}

export function BudgetState({ remaining, percent }: { remaining: number; percent: number }) {
  if (remaining < 0)
    return (
      <span className="inline-flex items-center gap-1 text-critical">
        <AlertTriangle size={12} /> {inr(-remaining)} over
      </span>
    );
  return (
    <span className={cn("inline-flex items-center gap-1", percent >= 80 ? "text-caution" : "text-ink-faint")}>
      {percent >= 80 ? <AlertTriangle size={12} /> : <Check size={12} />} {inr(remaining)} left
    </span>
  );
}
