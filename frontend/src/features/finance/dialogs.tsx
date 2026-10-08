import { useEffect, useState } from "react";
import {
  useAddToSavings,
  useDeleteBill,
  useDeleteBudget,
  useDeleteSavingsGoal,
  useDeleteTransaction,
  useFinanceCategories,
  useSaveBill,
  useSaveSavingsGoal,
  useSaveTransaction,
  useSetBudget,
} from "@/hooks/queries";
import { Button } from "@/components/ui/Button";
import { Dialog, DialogContent } from "@/components/ui/Overlay";
import { Field, Input, Select } from "@/components/ui/Field";
import { cn } from "@/lib/format";
import {
  BILL_FREQUENCIES,
  PAYMENT_ACCOUNTS,
  type BillFrequency,
  type BillOut,
  type BudgetStatus,
  type PaymentAccount,
  type SavingsGoalOut,
  type TransactionKind,
  type TransactionOut,
} from "@/types/api";
import { inr, titleCase, todayIso } from "@/features/finance/money";

/** Shared open/close props for every finance dialog. */
interface DialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function Chips<T extends string>({
  options,
  value,
  onChange,
  label = (o) => o,
}: {
  options: readonly T[];
  value: T;
  onChange: (v: T) => void;
  label?: (o: T) => string;
}) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map((o) => (
        <button
          key={o}
          type="button"
          onClick={() => onChange(o)}
          aria-pressed={value === o}
          className={cn(
            "rounded-full border px-3 py-1 text-[13px] transition-colors cursor-pointer",
            value === o ? "border-ink bg-ink text-ops-ground" : "border-ops-line-bright text-ink-dim hover:text-ink",
          )}
        >
          {label(o)}
        </button>
      ))}
    </div>
  );
}

function AmountInput({ value, onChange, autoFocus }: { value: string; onChange: (v: string) => void; autoFocus?: boolean }) {
  return (
    <label className="flex items-baseline gap-1 border-b border-ops-line-bright pb-1 focus-within:border-ink">
      <span className="text-[28px] text-ink-faint">₹</span>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value.replace(/[^\d.]/g, ""))}
        inputMode="decimal"
        placeholder="0"
        autoFocus={autoFocus}
        aria-label="Amount in rupees"
        className="tnum w-full bg-transparent text-[32px] font-semibold text-ink placeholder:text-ink-faint focus:outline-none"
      />
    </label>
  );
}

const positive = (s: string) => {
  const n = Number(s);
  return Number.isFinite(n) && n > 0 ? Math.round(n * 100) / 100 : null;
};

function Footer({
  onDelete,
  deleting,
  saving,
  canSave,
  onCancel,
  saveLabel = "Save",
}: {
  onDelete?: () => void;
  deleting?: boolean;
  saving: boolean;
  canSave: boolean;
  onCancel: () => void;
  saveLabel?: string;
}) {
  return (
    <div className="flex items-center gap-2 border-t border-ops-line pt-3">
      {onDelete && (
        <Button type="button" variant="danger" onClick={onDelete} disabled={deleting}>
          Delete
        </Button>
      )}
      <div className="ml-auto flex gap-2">
        <Button type="button" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" variant="solid" disabled={!canSave || saving}>
          {saving ? "Saving…" : saveLabel}
        </Button>
      </div>
    </div>
  );
}

// --- Transaction ------------------------------------------------------------------------

export function TransactionDialog({
  open,
  onOpenChange,
  transaction,
  defaultKind = "EXPENSE",
}: DialogProps & { transaction: TransactionOut | null; defaultKind?: TransactionKind }) {
  const save = useSaveTransaction();
  const del = useDeleteTransaction();
  const categories = useFinanceCategories();
  const [kind, setKind] = useState<TransactionKind>(defaultKind);
  const [amount, setAmount] = useState("");
  const [category, setCategory] = useState("");
  const [account, setAccount] = useState<PaymentAccount>("UPI");
  const [day, setDay] = useState(todayIso());
  const [note, setNote] = useState("");

  useEffect(() => {
    if (!open) return;
    setKind(transaction?.kind ?? defaultKind);
    setAmount(transaction ? String(transaction.amount) : "");
    setCategory(transaction?.category ?? "");
    setAccount(transaction?.account ?? "UPI");
    setDay(transaction?.occurred_on ?? todayIso());
    setNote(transaction?.note ?? "");
  }, [open, transaction, defaultKind]);

  const options = (kind === "EXPENSE" ? categories.data?.expense : categories.data?.income) ?? [];
  const value = positive(amount);
  const close = () => onOpenChange(false);
  const submit = () => {
    if (!value || !category) return;
    save.mutate(
      {
        id: transaction?.id,
        body: { kind, amount: value, category, account, occurred_on: day || null, note: note.trim() || null },
      },
      { onSuccess: close },
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title={transaction ? "Edit transaction" : "Add transaction"}>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
          className="space-y-4"
        >
          <Chips
            options={["EXPENSE", "INCOME"] as const}
            value={kind}
            onChange={(k) => {
              setKind(k);
              setCategory("");
            }}
            label={(k) => (k === "EXPENSE" ? "Expense" : "Income")}
          />
          <AmountInput value={amount} onChange={setAmount} autoFocus={!transaction} />
          <div>
            <p className="mb-1.5 text-[12px] text-ink-faint">Category</p>
            <Chips options={options} value={category} onChange={setCategory} />
            <Input
              value={options.includes(category) ? "" : category}
              onChange={(e) => setCategory(e.target.value)}
              placeholder="…or type your own"
              maxLength={60}
              className="mt-2"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Paid with">
              <Select value={account} onChange={(e) => setAccount(e.target.value as PaymentAccount)}>
                {PAYMENT_ACCOUNTS.map((a) => (
                  <option key={a} value={a}>
                    {a === "UPI" ? "UPI" : titleCase(a)}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Date">
              <Input type="date" value={day} onChange={(e) => setDay(e.target.value)} max={todayIso()} />
            </Field>
          </div>
          <Field label="Note">
            <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Lunch with team" maxLength={255} />
          </Field>
          <Footer
            onDelete={
              transaction
                ? () => window.confirm("Delete this transaction?") && del.mutate(transaction.id, { onSuccess: close })
                : undefined
            }
            deleting={del.isPending}
            saving={save.isPending}
            canSave={!!value && !!category.trim()}
            onCancel={close}
            saveLabel={transaction ? "Save" : "Add"}
          />
        </form>
      </DialogContent>
    </Dialog>
  );
}

// --- Budget -------------------------------------------------------------------------------

export function BudgetDialog({ open, onOpenChange, budget }: DialogProps & { budget: BudgetStatus | null }) {
  const set = useSetBudget();
  const del = useDeleteBudget();
  const categories = useFinanceCategories();
  const [category, setCategory] = useState("");
  const [limit, setLimit] = useState("");

  useEffect(() => {
    if (!open) return;
    setCategory(budget?.category ?? "");
    setLimit(budget ? String(budget.monthly_limit) : "");
  }, [open, budget]);

  const value = positive(limit);
  const close = () => onOpenChange(false);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title={budget ? `${budget.category} budget` : "New monthly budget"}>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (value && category) set.mutate({ category, limit: value }, { onSuccess: close });
          }}
          className="space-y-4"
        >
          {!budget && (
            <Field label="Category">
              <Select value={category} onChange={(e) => setCategory(e.target.value)}>
                <option value="">Choose…</option>
                {(categories.data?.expense ?? []).map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </Select>
            </Field>
          )}
          <div>
            <p className="mb-1 text-[12px] text-ink-faint">Monthly limit</p>
            <AmountInput value={limit} onChange={setLimit} autoFocus />
          </div>
          <Footer
            onDelete={
              budget
                ? () => window.confirm(`Remove the ${budget.category} budget?`) && del.mutate(budget.id, { onSuccess: close })
                : undefined
            }
            deleting={del.isPending}
            saving={set.isPending}
            canSave={!!value && !!category}
            onCancel={close}
          />
        </form>
      </DialogContent>
    </Dialog>
  );
}

// --- Bill -----------------------------------------------------------------------------------

export function BillDialog({ open, onOpenChange, bill }: DialogProps & { bill: BillOut | null }) {
  const save = useSaveBill();
  const del = useDeleteBill();
  const categories = useFinanceCategories();
  const [name, setName] = useState("");
  const [amount, setAmount] = useState("");
  const [category, setCategory] = useState("Bills & Utilities");
  const [account, setAccount] = useState<PaymentAccount>("UPI");
  const [frequency, setFrequency] = useState<BillFrequency>("MONTHLY");
  const [due, setDue] = useState(todayIso());
  const [active, setActive] = useState(true);

  useEffect(() => {
    if (!open) return;
    setName(bill?.name ?? "");
    setAmount(bill ? String(bill.amount) : "");
    setCategory(bill?.category ?? "Bills & Utilities");
    setAccount(bill?.account ?? "UPI");
    setFrequency(bill?.frequency ?? "MONTHLY");
    setDue(bill?.next_due ?? todayIso());
    setActive(bill?.active ?? true);
  }, [open, bill]);

  const value = positive(amount);
  const close = () => onOpenChange(false);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title={bill ? "Edit bill" : "New bill or subscription"}>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (!value || !name.trim() || !due) return;
            save.mutate(
              { id: bill?.id, body: { name: name.trim(), amount: value, category, account, frequency, next_due: due, active } },
              { onSuccess: close },
            );
          }}
          className="space-y-4"
        >
          <Field label="Name">
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Rent, Netflix, Jio recharge…" maxLength={120} autoFocus={!bill} />
          </Field>
          <AmountInput value={amount} onChange={setAmount} />
          <div className="grid grid-cols-2 gap-3">
            <Field label="Repeats">
              <Select value={frequency} onChange={(e) => setFrequency(e.target.value as BillFrequency)}>
                {BILL_FREQUENCIES.map((f) => (
                  <option key={f} value={f}>
                    {f === "ONCE" ? "Just once" : titleCase(f)}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Next due">
              <Input type="date" value={due} onChange={(e) => setDue(e.target.value)} />
            </Field>
            <Field label="Category">
              <Select value={category} onChange={(e) => setCategory(e.target.value)}>
                {(categories.data?.expense ?? [category]).map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Paid with">
              <Select value={account} onChange={(e) => setAccount(e.target.value as PaymentAccount)}>
                {PAYMENT_ACCOUNTS.map((a) => (
                  <option key={a} value={a}>
                    {a === "UPI" ? "UPI" : titleCase(a)}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          {bill && (
            <label className="flex items-center gap-2 text-[14px] text-ink-dim">
              <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} className="accent-white" />
              Active (uncheck to pause reminders)
            </label>
          )}
          <Footer
            onDelete={bill ? () => window.confirm(`Delete ${bill.name}?`) && del.mutate(bill.id, { onSuccess: close }) : undefined}
            deleting={del.isPending}
            saving={save.isPending}
            canSave={!!value && !!name.trim() && !!due}
            onCancel={close}
            saveLabel={bill ? "Save" : "Add"}
          />
        </form>
      </DialogContent>
    </Dialog>
  );
}

// --- Savings goal ------------------------------------------------------------------------------

export function SavingsGoalDialog({ open, onOpenChange, goal }: DialogProps & { goal: SavingsGoalOut | null }) {
  const save = useSaveSavingsGoal();
  const del = useDeleteSavingsGoal();
  const [name, setName] = useState("");
  const [target, setTarget] = useState("");
  const [saved, setSaved] = useState("");
  const [deadline, setDeadline] = useState("");

  useEffect(() => {
    if (!open) return;
    setName(goal?.name ?? "");
    setTarget(goal ? String(goal.target_amount) : "");
    setSaved(goal ? String(goal.saved_amount) : "");
    setDeadline(goal?.deadline ?? "");
  }, [open, goal]);

  const value = positive(target);
  const close = () => onOpenChange(false);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title={goal ? "Edit savings goal" : "New savings goal"}>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (!value || !name.trim()) return;
            save.mutate(
              {
                id: goal?.id,
                body: {
                  name: name.trim(),
                  target_amount: value,
                  saved_amount: Number(saved) || 0,
                  deadline: deadline || null,
                },
              },
              { onSuccess: close },
            );
          }}
          className="space-y-4"
        >
          <Field label="What are you saving for?">
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="New laptop" maxLength={120} autoFocus={!goal} />
          </Field>
          <div>
            <p className="mb-1 text-[12px] text-ink-faint">Target</p>
            <AmountInput value={target} onChange={setTarget} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Saved so far (₹)">
              <Input value={saved} onChange={(e) => setSaved(e.target.value.replace(/[^\d.]/g, ""))} inputMode="decimal" placeholder="0" />
            </Field>
            <Field label="By (optional)">
              <Input type="date" value={deadline} onChange={(e) => setDeadline(e.target.value)} />
            </Field>
          </div>
          <Footer
            onDelete={goal ? () => window.confirm(`Delete ${goal.name}?`) && del.mutate(goal.id, { onSuccess: close }) : undefined}
            deleting={del.isPending}
            saving={save.isPending}
            canSave={!!value && !!name.trim()}
            onCancel={close}
            saveLabel={goal ? "Save" : "Create"}
          />
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function AddMoneyDialog({ open, onOpenChange, goal }: DialogProps & { goal: SavingsGoalOut | null }) {
  const add = useAddToSavings();
  const [amount, setAmount] = useState("");
  const [withdraw, setWithdraw] = useState(false);
  useEffect(() => {
    if (open) {
      setAmount("");
      setWithdraw(false);
    }
  }, [open]);
  const value = positive(amount);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title={goal ? goal.name : "Savings"}>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (goal && value) add.mutate({ id: goal.id, amount: withdraw ? -value : value }, { onSuccess: () => onOpenChange(false) });
          }}
          className="space-y-4"
        >
          {goal && (
            <p className="text-[13px] text-ink-faint">
              {inr(goal.saved_amount)} of {inr(goal.target_amount)} saved
            </p>
          )}
          <Chips
            options={["add", "withdraw"] as const}
            value={withdraw ? "withdraw" : "add"}
            onChange={(v) => setWithdraw(v === "withdraw")}
            label={(v) => (v === "add" ? "Add money" : "Take out")}
          />
          <AmountInput value={amount} onChange={setAmount} autoFocus />
          <Footer saving={add.isPending} canSave={!!value} onCancel={() => onOpenChange(false)} saveLabel={withdraw ? "Take out" : "Add"} />
        </form>
      </DialogContent>
    </Dialog>
  );
}
