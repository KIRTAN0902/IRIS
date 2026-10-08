import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ArrowDownRight, ArrowUpRight, ChevronLeft, ChevronRight, Plus, Search } from "lucide-react";
import { useBills, useFinanceSummary, usePayBill, useSavingsGoals, useTransactions } from "@/hooks/queries";
import { ErrorState, Skeleton } from "@/components/ui/Overlay";
import { cn } from "@/lib/format";
import type {
  BillOut,
  BudgetStatus,
  FinanceSummary,
  SavingsGoalOut,
  TransactionKind,
  TransactionOut,
} from "@/types/api";
import { BudgetState, CategoryBars, DailySpendChart, Meter, budgetTone } from "@/features/finance/charts";
import {
  AddMoneyDialog,
  BillDialog,
  BudgetDialog,
  SavingsGoalDialog,
  TransactionDialog,
} from "@/features/finance/dialogs";
import {
  currentMonth,
  dayHeading,
  dueLabel,
  fmtDay,
  inr,
  monthLabel,
  monthName,
  parseDay,
  shiftMonth,
  titleCase,
} from "@/features/finance/money";

/**
 * MONEY: where it goes, what's due, what's being saved. IRIS can do all of this
 * by chat or voice too ("spent 250 on lunch via UPI").
 */

type Tab = "overview" | "transactions" | "budgets" | "bills" | "savings";
const TABS: { id: Tab; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "transactions", label: "Transactions" },
  { id: "budgets", label: "Budgets" },
  { id: "bills", label: "Bills" },
  { id: "savings", label: "Savings" },
];

export function FinancePage() {
  const [params, setParams] = useSearchParams();
  const tab = (TABS.find((t) => t.id === params.get("tab"))?.id ?? "overview") as Tab;
  const [month, setMonth] = useState(currentMonth());
  const [editing, setEditing] = useState<{ tx: TransactionOut | null; kind?: TransactionKind } | null>(null);
  const isCurrent = month === currentMonth();

  const setTab = (id: Tab) => setParams(id === "overview" ? {} : { tab: id }, { replace: true });
  const addTransaction = (kind: TransactionKind = "EXPENSE") => setEditing({ tx: null, kind });

  return (
    <div className="mx-auto w-full max-w-[720px] pb-16">
      <header className="mb-5">
        <div className="flex items-end justify-between gap-3">
          <h1 className="text-[30px] font-bold leading-tight tracking-[-0.02em] text-ink">Finance</h1>
          <button
            onClick={() => addTransaction()}
            className="mb-1 hidden items-center gap-1 text-[14px] text-ai hover:underline cursor-pointer md:inline-flex"
          >
            <Plus size={14} /> Add transaction
          </button>
        </div>
        {(tab === "overview" || tab === "transactions" || tab === "budgets") && (
          <div className="mt-2 flex items-center gap-1 text-[14px]">
            <button
              onClick={() => setMonth(shiftMonth(month, -1))}
              aria-label="Previous month"
              className="rounded p-1 text-ink-faint hover:bg-ops-raised hover:text-ink cursor-pointer"
            >
              <ChevronLeft size={16} />
            </button>
            <span className="min-w-[120px] text-center text-ink-dim">{monthLabel(month)}</span>
            <button
              onClick={() => setMonth(shiftMonth(month, 1))}
              disabled={isCurrent}
              aria-label="Next month"
              className="rounded p-1 text-ink-faint hover:bg-ops-raised hover:text-ink disabled:opacity-30 cursor-pointer"
            >
              <ChevronRight size={16} />
            </button>
            {!isCurrent && (
              <button onClick={() => setMonth(currentMonth())} className="ml-1 text-[13px] text-ink-faint hover:text-ink cursor-pointer">
                This month
              </button>
            )}
          </div>
        )}
        <nav className="-mx-1 mt-4 flex gap-4 overflow-x-auto px-1 text-[14px]" aria-label="Finance sections">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              aria-current={tab === t.id ? "page" : undefined}
              className={cn(
                "shrink-0 border-b-2 pb-1.5 transition-colors cursor-pointer",
                tab === t.id ? "border-ink font-medium text-ink" : "border-transparent text-ink-faint hover:text-ink-dim",
              )}
            >
              {t.label}
            </button>
          ))}
        </nav>
      </header>

      {tab === "overview" && <Overview month={month} onEdit={(tx) => setEditing({ tx })} onAdd={addTransaction} onTab={setTab} />}
      {tab === "transactions" && <Transactions month={month} onEdit={(tx) => setEditing({ tx })} />}
      {tab === "budgets" && <Budgets month={month} />}
      {tab === "bills" && <Bills />}
      {tab === "savings" && <Savings />}

      {/* Phone: one-thumb add button above the tab bar. */}
      <button
        onClick={() => addTransaction()}
        aria-label="Add transaction"
        className="fixed bottom-20 right-5 z-30 flex h-14 w-14 items-center justify-center rounded-full bg-ink text-ops-ground shadow-[0_0_24px_rgba(255,255,255,0.25)] md:hidden cursor-pointer"
      >
        <Plus size={24} strokeWidth={2.5} />
      </button>

      <TransactionDialog
        open={editing !== null}
        onOpenChange={(o) => !o && setEditing(null)}
        transaction={editing?.tx ?? null}
        defaultKind={editing?.kind}
      />
    </div>
  );
}

// --- Overview ----------------------------------------------------------------------------

function Section({ title, action, children }: { title: string; action?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="mt-9">
      <header className="mb-3 flex items-baseline justify-between border-b border-ops-line pb-1.5">
        <h2 className="text-[17px] font-semibold text-ink">{title}</h2>
        {action}
      </header>
      {children}
    </section>
  );
}

function LinkButton({ onClick, children }: { onClick: () => void; children: React.ReactNode }) {
  return (
    <button onClick={onClick} className="text-[13px] text-ink-faint hover:text-ink cursor-pointer">
      {children}
    </button>
  );
}

function Loading() {
  return (
    <div className="space-y-3">
      <Skeleton className="h-12 w-1/2" />
      <Skeleton className="h-28 w-full" />
      <Skeleton className="h-4 w-5/6" />
    </div>
  );
}

function Overview({
  month,
  onEdit,
  onAdd,
  onTab,
}: {
  month: string;
  onEdit: (tx: TransactionOut) => void;
  onAdd: (kind?: TransactionKind) => void;
  onTab: (t: Tab) => void;
}) {
  const summary = useFinanceSummary(month);
  if (summary.isLoading) return <Loading />;
  if (summary.error) return <ErrorState message={(summary.error as Error).message} />;
  const s = summary.data!;
  const empty = !s.expense && !s.income && !s.budgets.length && !s.bills_due.length && !s.savings.length && !s.recent.length;

  if (empty)
    return (
      <div className="mt-10 text-center">
        <p className="text-[17px] text-ink">Nothing tracked yet.</p>
        <p className="mx-auto mt-2 max-w-[420px] text-[14px] leading-relaxed text-ink-faint">
          Add an expense here, or just tell IRIS — “spent 250 on lunch via UPI” or “add my rent, ₹12,000 due on the
          5th every month”.
        </p>
        <div className="mt-5 flex justify-center gap-2">
          <button onClick={() => onAdd("EXPENSE")} className="rounded-full bg-ink px-4 py-2 text-[14px] font-medium text-ops-ground cursor-pointer">
            Add expense
          </button>
          <button onClick={() => onAdd("INCOME")} className="rounded-full border border-ops-line-bright px-4 py-2 text-[14px] text-ink cursor-pointer">
            Add income
          </button>
        </div>
      </div>
    );

  return (
    <div>
      <Headline s={s} />
      {s.daily.some((d) => d.expense > 0) && (
        <div className="mt-8">
          <DailySpendChart daily={s.daily} today={s.today} />
        </div>
      )}

      {s.by_category.length > 0 && (
        <Section title="Where it went">
          <CategoryBars rows={s.by_category} />
        </Section>
      )}

      {s.budgets.length > 0 && (
        <Section title="Budgets" action={<LinkButton onClick={() => onTab("budgets")}>Manage</LinkButton>}>
          <BudgetList budgets={s.budgets} />
        </Section>
      )}

      {s.bills_due.length > 0 && (
        <Section title="Coming up" action={<LinkButton onClick={() => onTab("bills")}>All bills</LinkButton>}>
          <BillRows bills={s.bills_due} />
        </Section>
      )}

      {s.savings.length > 0 && (
        <Section title="Savings" action={<LinkButton onClick={() => onTab("savings")}>Manage</LinkButton>}>
          <ul className="space-y-4">
            {s.savings.map((g) => (
              <li key={g.id}>
                <div className="mb-1 flex items-baseline justify-between gap-3 text-[14px]">
                  <span className="truncate text-ink">{g.name}</span>
                  <span className="tnum text-ink-faint">
                    {inr(g.saved_amount)} / {inr(g.target_amount)}
                  </span>
                </div>
                <Meter percent={g.percent} tone={g.status === "ACHIEVED" ? "go" : "neutral"} />
              </li>
            ))}
          </ul>
        </Section>
      )}

      {s.recent.length > 0 && (
        <Section title="Recent" action={<LinkButton onClick={() => onTab("transactions")}>See all</LinkButton>}>
          <ul>
            {s.recent.map((t) => (
              <li key={t.id}>
                <TransactionRow tx={t} onClick={() => onEdit(t)} showDate />
              </li>
            ))}
          </ul>
        </Section>
      )}
    </div>
  );
}

function Headline({ s }: { s: FinanceSummary }) {
  const prev = s.previous_month_expense;
  const change = prev > 0 ? Math.round(((s.expense - prev) / prev) * 100) : null;
  const prevName = monthName(shiftMonth(s.month, -1));
  return (
    <div>
      <p className="text-[13px] text-ink-faint">Spent in {monthName(s.month)}</p>
      <p className="tnum mt-1 text-[48px] font-semibold leading-none tracking-[-0.02em] text-ink">{inr(s.expense)}</p>
      {change !== null && (
        <p className={cn("mt-2 inline-flex items-center gap-1 text-[13px]", change > 0 ? "text-caution" : "text-go")}>
          {change > 0 ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
          {Math.abs(change)}% {change > 0 ? "more" : "less"} than {prevName}
        </p>
      )}
      <dl className="mt-6 grid grid-cols-2 gap-4 border-t border-ops-line pt-4">
        <div>
          <dt className="text-[13px] text-ink-faint">Earned</dt>
          <dd className="tnum mt-0.5 text-[22px] font-semibold text-ink">{inr(s.income)}</dd>
        </div>
        <div>
          <dt className="text-[13px] text-ink-faint">{s.net >= 0 ? "Left over" : "Overspent"}</dt>
          <dd className={cn("tnum mt-0.5 text-[22px] font-semibold", s.net >= 0 ? "text-ink" : "text-critical")}>
            {inr(Math.abs(s.net))}
          </dd>
        </div>
      </dl>
    </div>
  );
}

// --- Transactions ---------------------------------------------------------------------------

function TransactionRow({ tx, onClick, showDate }: { tx: TransactionOut; onClick: () => void; showDate?: boolean }) {
  const income = tx.kind === "INCOME";
  return (
    <button onClick={onClick} className="flex w-full items-center gap-3 py-2.5 text-left hover:bg-ops-raised/30 cursor-pointer">
      <div className="min-w-0 flex-1">
        <p className="truncate text-[15px] text-ink">{tx.note || tx.category}</p>
        <p className="truncate text-[12px] text-ink-faint">
          {tx.note ? `${tx.category} · ` : ""}
          {tx.account === "UPI" ? "UPI" : titleCase(tx.account)}
          {showDate && ` · ${dayHeading(tx.occurred_on)}`}
        </p>
      </div>
      <span className={cn("tnum shrink-0 text-[15px] font-medium", income ? "text-go" : "text-ink")}>
        {income ? "+" : "−"}
        {inr(tx.amount)}
      </span>
    </button>
  );
}

function Transactions({ month, onEdit }: { month: string; onEdit: (tx: TransactionOut) => void }) {
  const [kind, setKind] = useState<TransactionKind | undefined>(undefined);
  const [query, setQuery] = useState("");
  const txs = useTransactions({ month, kind, q: query.trim() || undefined });

  const days = useMemo(() => {
    const groups = new Map<string, TransactionOut[]>();
    for (const t of txs.data ?? []) groups.set(t.occurred_on, [...(groups.get(t.occurred_on) ?? []), t]);
    return [...groups.entries()];
  }, [txs.data]);

  return (
    <div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
        <nav className="flex gap-4 text-[14px]" aria-label="Filter transactions">
          {([undefined, "EXPENSE", "INCOME"] as const).map((k) => (
            <button
              key={k ?? "all"}
              onClick={() => setKind(k)}
              className={cn("cursor-pointer", kind === k ? "font-medium text-ink" : "text-ink-faint hover:text-ink-dim")}
            >
              {k === undefined ? "All" : k === "EXPENSE" ? "Spent" : "Earned"}
            </button>
          ))}
        </nav>
        <label className="ml-auto flex min-w-[160px] flex-1 items-center gap-2 sm:max-w-[220px]">
          <Search size={14} className="shrink-0 text-ink-faint" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search"
            aria-label="Search transactions"
            className="w-full bg-transparent text-[14px] text-ink placeholder:text-ink-faint focus:outline-none"
          />
        </label>
      </div>

      {txs.isLoading ? (
        <div className="mt-6">
          <Loading />
        </div>
      ) : txs.error ? (
        <ErrorState message={(txs.error as Error).message} />
      ) : days.length === 0 ? (
        <p className="mt-8 text-[15px] text-ink-faint">{query ? "Nothing matches." : `No transactions in ${monthLabel(month)}.`}</p>
      ) : (
        <div className="mt-4 space-y-6">
          {days.map(([day, items]) => {
            const spent = items.filter((t) => t.kind === "EXPENSE").reduce((s, t) => s + t.amount, 0);
            return (
              <section key={day}>
                <header className="flex items-baseline justify-between border-b border-ops-line pb-1 text-[13px]">
                  <span className="font-medium text-ink-dim">{dayHeading(day)}</span>
                  {spent > 0 && <span className="tnum text-ink-faint">−{inr(spent)}</span>}
                </header>
                <ul>
                  {items.map((t) => (
                    <li key={t.id}>
                      <TransactionRow tx={t} onClick={() => onEdit(t)} />
                    </li>
                  ))}
                </ul>
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
}

// --- Budgets ------------------------------------------------------------------------------------

function BudgetList({ budgets, onEdit }: { budgets: BudgetStatus[]; onEdit?: (b: BudgetStatus) => void }) {
  return (
    <ul className="space-y-4">
      {budgets.map((b) => (
        <li key={b.id}>
          <button
            onClick={onEdit ? () => onEdit(b) : undefined}
            disabled={!onEdit}
            className="w-full text-left enabled:cursor-pointer"
          >
            <div className="mb-1 flex items-baseline justify-between gap-3 text-[14px]">
              <span className="truncate text-ink">{b.category}</span>
              <span className="tnum shrink-0 text-ink-faint">
                {inr(b.spent)} of {inr(b.monthly_limit)}
              </span>
            </div>
            <Meter percent={b.percent} tone={budgetTone(b.percent)} />
            <p className="mt-1 text-[12px]">
              <BudgetState remaining={b.remaining} percent={b.percent} />
            </p>
          </button>
        </li>
      ))}
    </ul>
  );
}

function Budgets({ month }: { month: string }) {
  const summary = useFinanceSummary(month);
  const [editing, setEditing] = useState<BudgetStatus | null | undefined>(undefined);
  if (summary.isLoading) return <Loading />;
  const budgets = summary.data?.budgets ?? [];
  const total = budgets.reduce((s, b) => s + b.monthly_limit, 0);
  const spent = budgets.reduce((s, b) => s + b.spent, 0);
  return (
    <div>
      <div className="mb-5 flex items-baseline justify-between">
        <p className="text-[14px] text-ink-faint">
          {budgets.length ? `${inr(spent)} of ${inr(total)} budgeted in ${monthName(month)}` : "Set a monthly limit per category."}
        </p>
        <LinkButton onClick={() => setEditing(null)}>+ New budget</LinkButton>
      </div>
      {budgets.length ? (
        <BudgetList budgets={budgets} onEdit={setEditing} />
      ) : (
        <p className="text-[15px] text-ink-faint">No budgets yet. Try Food & Dining or Shopping first.</p>
      )}
      <BudgetDialog open={editing !== undefined} onOpenChange={(o) => !o && setEditing(undefined)} budget={editing ?? null} />
    </div>
  );
}

// --- Bills ----------------------------------------------------------------------------------------

function BillRows({ bills, onEdit }: { bills: BillOut[]; onEdit?: (b: BillOut) => void }) {
  const pay = usePayBill();
  return (
    <ul className="divide-y divide-ops-line">
      {bills.map((b) => {
        const due = dueLabel(b.days_until_due);
        return (
          <li key={b.id} className={cn("flex items-center gap-3 py-2.5", !b.active && "opacity-50")}>
            <button onClick={onEdit ? () => onEdit(b) : undefined} disabled={!onEdit} className="min-w-0 flex-1 text-left enabled:cursor-pointer">
              <p className="truncate text-[15px] text-ink">{b.name}</p>
              <p className="text-[12px]">
                {b.active ? (
                  <span className={cn(due.tone === "critical" ? "text-critical" : due.tone === "caution" ? "text-caution" : "text-ink-faint")}>
                    {due.text}
                  </span>
                ) : (
                  <span className="text-ink-faint">Paused</span>
                )}
                <span className="text-ink-faint">
                  {" "}
                  · {fmtDay(b.next_due)} · {b.frequency === "ONCE" ? "once" : titleCase(b.frequency)}
                </span>
              </p>
            </button>
            <span className="tnum shrink-0 text-[15px] text-ink">{inr(b.amount)}</span>
            {b.active && (
              <button
                onClick={() => pay.mutate({ id: b.id })}
                disabled={pay.isPending && pay.variables?.id === b.id}
                className="shrink-0 rounded-full border border-ops-line-bright px-3 py-1 text-[13px] text-ink hover:bg-ops-raised disabled:opacity-40 cursor-pointer"
              >
                Paid
              </button>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function Bills() {
  const bills = useBills();
  const [editing, setEditing] = useState<BillOut | null | undefined>(undefined);
  if (bills.isLoading) return <Loading />;
  const list = bills.data ?? [];
  const monthly = list
    .filter((b) => b.active)
    .reduce((s, b) => s + b.amount * ({ WEEKLY: 52 / 12, MONTHLY: 1, QUARTERLY: 1 / 3, YEARLY: 1 / 12, ONCE: 0 }[b.frequency] ?? 0), 0);
  return (
    <div>
      <div className="mb-3 flex items-baseline justify-between">
        <p className="text-[14px] text-ink-faint">
          {list.length ? `About ${inr(Math.round(monthly))} a month in recurring bills` : "Rent, EMIs, subscriptions, recharges."}
        </p>
        <LinkButton onClick={() => setEditing(null)}>+ New bill</LinkButton>
      </div>
      {list.length ? (
        <BillRows bills={list} onEdit={setEditing} />
      ) : (
        <p className="text-[15px] text-ink-faint">No bills yet. Mark one “Paid” and IRIS logs the expense and moves it to the next due date.</p>
      )}
      <BillDialog open={editing !== undefined} onOpenChange={(o) => !o && setEditing(undefined)} bill={editing ?? null} />
    </div>
  );
}

// --- Savings ----------------------------------------------------------------------------------------

function perMonthNeeded(g: SavingsGoalOut): string | null {
  if (!g.deadline || g.status !== "ACTIVE") return null;
  const left = g.target_amount - g.saved_amount;
  const now = new Date();
  const end = parseDay(g.deadline);
  const months = (end.getFullYear() - now.getFullYear()) * 12 + (end.getMonth() - now.getMonth()) + 1;
  if (months <= 0) return "Deadline passed";
  return `${inr(Math.ceil(left / months))}/month to reach it by ${fmtDay(g.deadline)}`;
}

function Savings() {
  const goals = useSavingsGoals();
  const [editing, setEditing] = useState<SavingsGoalOut | null | undefined>(undefined);
  const [adding, setAdding] = useState<SavingsGoalOut | null>(null);
  if (goals.isLoading) return <Loading />;
  const list = goals.data ?? [];
  return (
    <div>
      <div className="mb-5 flex items-baseline justify-between">
        <p className="text-[14px] text-ink-faint">
          {list.length ? `${inr(list.reduce((s, g) => s + g.saved_amount, 0))} saved across ${list.length} goal${list.length > 1 ? "s" : ""}` : "Save toward something specific."}
        </p>
        <LinkButton onClick={() => setEditing(null)}>+ New goal</LinkButton>
      </div>
      {list.length ? (
        <ul className="space-y-6">
          {list.map((g) => {
            const hint = perMonthNeeded(g);
            return (
              <li key={g.id} className={cn(g.status === "ARCHIVED" && "opacity-50")}>
                <div className="flex items-baseline justify-between gap-3">
                  <button onClick={() => setEditing(g)} className="min-w-0 truncate text-left text-[16px] font-medium text-ink cursor-pointer">
                    {g.name}
                  </button>
                  <span className="tnum shrink-0 text-[14px] text-ink-faint">{g.percent}%</span>
                </div>
                <p className="tnum mb-2 text-[14px] text-ink-dim">
                  {inr(g.saved_amount)} <span className="text-ink-faint">of {inr(g.target_amount)}</span>
                </p>
                <Meter percent={g.percent} tone={g.status === "ACHIEVED" ? "go" : "neutral"} />
                <div className="mt-2 flex items-center justify-between gap-3 text-[12px]">
                  <span className={g.status === "ACHIEVED" ? "text-go" : "text-ink-faint"}>
                    {g.status === "ACHIEVED" ? "Goal reached" : (hint ?? "No deadline")}
                  </span>
                  {g.status !== "ARCHIVED" && (
                    <button
                      onClick={() => setAdding(g)}
                      className="shrink-0 rounded-full border border-ops-line-bright px-3 py-1 text-[13px] text-ink hover:bg-ops-raised cursor-pointer"
                    >
                      Add money
                    </button>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="text-[15px] text-ink-faint">No savings goals yet — a laptop, a trip, an emergency fund.</p>
      )}
      <SavingsGoalDialog open={editing !== undefined} onOpenChange={(o) => !o && setEditing(undefined)} goal={editing ?? null} />
      <AddMoneyDialog open={adding !== null} onOpenChange={(o) => !o && setAdding(null)} goal={adding} />
    </div>
  );
}
