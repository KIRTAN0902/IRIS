import { useState } from "react";
import { ChevronRight, Plus } from "lucide-react";
import { useCreateGoal, useGoals, type GoalNode } from "@/hooks/queries";
import { Button } from "@/components/ui/Button";
import { Dialog, DialogContent, EmptyState, Skeleton } from "@/components/ui/Overlay";
import { Field, Input, Select } from "@/components/ui/Field";
import { Lamp, ProgressLadder } from "@/components/ui/Panel";
import { fmtDay } from "@/lib/format";

/** GOALS — the hierarchy from "build a startup" down to today's calls. */
export function GoalsPage() {
  const [area, setArea] = useState("");
  const goals = useGoals(area || undefined);
  const [createFor, setCreateFor] = useState<number | null>(null);
  const [createOpen, setCreateOpen] = useState(false);

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-center gap-4">
        <h1 className="text-[30px] font-bold leading-tight tracking-[-0.02em] text-ink">Goals</h1>
        <Select value={area} onChange={(e) => setArea(e.target.value)} aria-label="Filter area" className="h-8 w-auto pr-8">
          <option value="">All areas</option>
          {["STARTUP", "COLLEGE", "INTERNSHIP", "PERSONAL"].map((a) => <option key={a}>{a}</option>)}
        </Select>
        <Button
          size="sm"
          variant="go"
          className="ml-auto"
          onClick={() => {
            setCreateFor(null);
            setCreateOpen(true);
          }}
        >
          <Plus size={14} /> Root goal
        </Button>
      </header>

      {goals.isLoading ? (
        <Skeleton className="h-48" />
      ) : !goals.data?.length ? (
        <EmptyState message="No goals yet." hint="Start with the top of the tree: the thing you're actually building toward." />
      ) : (
        <div className="space-y-4">
          {(goals.data as GoalNode[]).map((root) => (
            <GoalBranch key={root.id} node={root} onAddChild={(id) => { setCreateFor(id); setCreateOpen(true); }} depth={0} />
          ))}
        </div>
      )}

      <CreateGoalDialog open={createOpen} onOpenChange={setCreateOpen} parentId={createFor} area={area || undefined} />
    </div>
  );
}

function GoalBranch({ node, onAddChild, depth }: { node: GoalNode; onAddChild: (id: number) => void; depth: number }) {
  const [openChildren, setOpenChildren] = useState(true);
  const achieved = node.status === "ACHIEVED";
  const tone = achieved ? "go" : node.status === "BEHIND" ? "caution" : "ai";

  return (
    <section className={depth === 0 ? "border border-ops-line bg-ops-panel/50" : ""}>
      <div className={`flex items-center gap-3 px-4 ${depth === 0 ? "py-4" : "py-2.5"} ${depth > 0 ? "border-t border-ops-line" : ""}`}>
        <Lamp tone={tone} pulse={!achieved && node.status !== "ACTIVE"} />
        <div className="min-w-0 flex-1">
          <p className={`truncate text-ink ${depth === 0 ? "text-[17px] font-semibold" : "text-[14px] font-medium"} ${achieved ? "line-through text-ink-faint" : ""}`}>
            {node.name}
          </p>
          <p className="tnum flex flex-wrap gap-x-3 text-[11px] text-ink-faint">
            {node.target_value != null && (
              <span>{node.current_value}/{node.target_value} {node.unit ?? ""}</span>
            )}
            {node.deadline && <span>by {fmtDay(node.deadline)}</span>}
            <span className="">{node.status}</span>
          </p>
        </div>
        {node.target_value != null && (
          <ProgressLadder fraction={node.progress_fraction} tone={tone} className="hidden w-40 sm:flex" />
        )}
        <Button
          size="sm"
          variant="ghost"
          aria-label={`Add sub-goal under ${node.name}`}
          title="Add sub-goal"
          onClick={() => onAddChild(node.id)}
        >
          <Plus size={13} />
        </Button>
      </div>

      {node.children.length > 0 && (
        <>
          <button
            onClick={() => setOpenChildren((v) => !v)}
            className="flex w-full items-center gap-1.5 px-4 pb-1 text-[11px] text-ink-faint hover:text-ink"
          >
            <ChevronRight size={12} className={`transition-transform duration-200 ${openChildren ? "rotate-90" : ""}`} />
            {openChildren ? "Collapse" : `Expand (${node.children.length})`}
          </button>
          {openChildren && (
            <div className="ml-6 border-l border-ops-line pl-2 pr-2">
              {node.children.map((child) => (
                <GoalBranch key={child.id} node={child} onAddChild={onAddChild} depth={depth + 1} />
              ))}
            </div>
          )}
        </>
      )}
    </section>
  );
}

function CreateGoalDialog({
  open,
  onOpenChange,
  parentId,
  area,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  parentId: number | null;
  area?: string;
}) {
  const create = useCreateGoal();
  const [form, setForm] = useState({
    name: "",
    area: (area ?? "STARTUP") as string,
    target_value: "",
    unit: "",
    deadlineLocal: "",
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title={parentId ? "New sub-goal" : "New root goal"}>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate(
              {
                name: form.name.trim(),
                parent_goal_id: parentId,
                area: (parentId ? undefined : (form.area as never)) ?? ("STARTUP" as never),
                target_value: form.target_value ? Number(form.target_value) : null,
                unit: form.unit || null,
                deadline: form.deadlineLocal ? new Date(form.deadlineLocal).toISOString() : null,
              },
              {
                onSuccess: () => {
                  onOpenChange(false);
                  setForm({ ...form, name: "", target_value: "", unit: "", deadlineLocal: "" });
                },
              },
            );
          }}
          className="space-y-3"
        >
          <Field label="Name">
            <Input required autoFocus value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Contact 100 prospects" />
          </Field>
          {!parentId && (
            <Field label="Area">
              <Select value={form.area} onChange={(e) => setForm({ ...form, area: e.target.value })}>
                {["STARTUP", "COLLEGE", "INTERNSHIP", "PERSONAL"].map((a) => <option key={a}>{a}</option>)}
              </Select>
            </Field>
          )}
          <div className="grid grid-cols-3 gap-3">
            <Field label="Target"><Input type="number" min={0} value={form.target_value} onChange={(e) => setForm({ ...form, target_value: e.target.value })} /></Field>
            <Field label="Unit"><Input value={form.unit} onChange={(e) => setForm({ ...form, unit: e.target.value })} placeholder="prospects" /></Field>
            <Field label="Deadline"><Input type="date" value={form.deadlineLocal} onChange={(e) => setForm({ ...form, deadlineLocal: e.target.value })} /></Field>
          </div>
          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" variant="go" disabled={!form.name.trim() || create.isPending}>Set goal</Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
