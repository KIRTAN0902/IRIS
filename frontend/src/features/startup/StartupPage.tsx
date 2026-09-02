import { useMemo, useState } from "react";
import { FlaskConical, Plus, Send } from "lucide-react";
import {
  useCreateLead,
  useExperiments,
  useLeads,
  useLogOutreach,
  useOutreach,
  useStartup,
  useStartupAnalytics,
  useUpdateExperiment,
  useUpdateLead,
} from "@/hooks/queries";
import { LEAD_STATUSES, OUTREACH_RESULTS, type LeadOut, type LeadStatus, type OutreachResult, type StartupAnalytics } from "@/types/api";
import { Button } from "@/components/ui/Button";
import { Dialog, DialogContent, EmptyState, Skeleton } from "@/components/ui/Overlay";
import { Field, Input, Select, Textarea } from "@/components/ui/Field";
import { Lamp, Panel, ProgressLadder } from "@/components/ui/Panel";
import { fmtDay } from "@/lib/format";

/** STARTUP — distribution is the objective. Funnel → pipeline → experiments. */
export function StartupPage() {
  const startup = useStartup();
  const metrics = useStartupAnalytics();

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="font-[family-name:var(--font-display)] text-[22px] font-semibold tracking-wide">
          {startup.data?.name ?? "Startup"}
        </h1>
        <p className="text-[13px] text-ink-dim">
          <span className="label-caps mr-2">Objective</span>
          {startup.data?.current_objective ?? "—"}
        </p>
      </header>

      <FunnelPanel metrics={metrics.data} isLoading={metrics.isLoading} />
      <GoalsBehind goals={metrics.data?.goals_behind ?? []} />
      <PipelineSection startupId={startup.data?.id} />

      <section className="grid gap-6 xl:grid-cols-2">
        <ExperimentsPanel startupId={startup.data?.id} />
        <OutreachJournal startupId={startup.data?.id} />
      </section>
    </div>
  );
}

// --- Funnel ------------------------------------------------------------------------

function FunnelPanel({ metrics, isLoading }: { metrics?: StartupAnalytics; isLoading: boolean }) {
  if (isLoading || !metrics) return <Skeleton className="h-36" />;
  const o = metrics.outreach;
  return (
    <Panel
      title="Distribution funnel · all time"
      lamp={<Lamp tone={o.total > 0 ? "go" : "caution"} />}
      bodyClassName="grid gap-x-8 gap-y-4 sm:grid-cols-2"
    >
      {[
        { label: "Outreach sent", value: o.sent, ladder: null as number | null },
        { label: "Replies", value: o.replies, ladder: o.reply_rate / 100, tone: "ai" as const },
        { label: "Meetings booked", value: o.meetings_booked, ladder: o.meeting_rate / 100, tone: "caution" as const },
        { label: "Customers", value: o.conversions, ladder: o.conversion_rate / 100, tone: "go" as const },
      ].map((row) => (
        <div key={row.label}>
          <div className="mb-1 flex items-baseline justify-between gap-3">
            <span className="text-[12px] uppercase tracking-[0.1em] text-ink-dim">{row.label}</span>
            <span className="tnum text-[20px] font-semibold text-ink">{row.value}</span>
          </div>
          {row.ladder != null && (
            <ProgressLadder fraction={row.ladder} tone={row.tone} label={`${Math.round(row.ladder * 100)}%`} />
          )}
        </div>
      ))}
      <p className="tnum col-span-full border-t border-ops-line pt-3 text-[11px] text-ink-faint">
        reply rate {o.reply_rate}% · meeting rate {o.meeting_rate}% · conversion {o.conversion_rate}% — derived from{" "}
        {o.total} logged activities
      </p>
    </Panel>
  );
}

// --- Goals behind ---------------------------------------------------------------------

function GoalsBehind({ goals }: { goals: string[] }) {
  if (!goals.length) return null;
  return (
    <div className="border border-caution-dim bg-caution-dim/20 px-4 py-3">
      <p className="flex items-center gap-2 text-[13px] text-caution">
        <Lamp tone="caution" pulse /> Behind target: {goals.join(" · ")}
      </p>
    </div>
  );
}

// --- Pipeline -----------------------------------------------------------------------------

const STATUS_TONE: Partial<Record<LeadStatus, "go" | "caution" | "critical" | "ai" | "dim">> = {
  CUSTOMER: "go",
  MEETING: "go",
  INTERESTED: "ai",
  REPLIED: "ai",
  CONTACTED: "caution",
  LEAD: "dim",
  NOT_INTERESTED: "critical",
  LOST: "critical",
};

function PipelineSection({ startupId }: { startupId?: number }) {
  const leads = useLeads({ startup_id: startupId });
  const update = useUpdateLead();
  const [logFor, setLogFor] = useState<LeadOut | null>(null);
  const [addOpen, setAddOpen] = useState(false);

  return (
    <Panel
      title={`Pipeline · ${leads.data?.length ?? 0} leads`}
      lamp={<Lamp tone="dim" />}
      actions={
        <Button size="sm" variant="ghost" onClick={() => setAddOpen(true)}>
          <Plus size={13} /> Lead
        </Button>
      }
      bodyClassName="!p-0"
    >
      {leads.isLoading ? (
        <div className="p-4"><Skeleton className="h-32" /></div>
      ) : !leads.data?.length ? (
        <div className="p-4"><EmptyState message="No leads yet." hint="Research prospects and add them here." /></div>
      ) : (
        <ol className="divide-y divide-ops-line">
          {leads.data.map((lead) => (
            <li key={lead.id} className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-2.5">
              <Lamp tone={STATUS_TONE[lead.status] ?? "dim"} pulse={lead.status === "CUSTOMER"} />
              <div className="min-w-40 flex-1">
                <p className="truncate text-[14px] font-medium text-ink">{lead.name}</p>
                <p className="truncate text-[11px] text-ink-faint">
                  {[lead.role, lead.company].filter(Boolean).join(" · ") || "—"}
                </p>
              </div>
              {lead.last_contacted && (
                <span className="tnum hidden text-[11px] text-ink-faint sm:block">
                  last {fmtDay(lead.last_contacted)}
                </span>
              )}
              <Select
                aria-label={`Status for ${lead.name}`}
                value={lead.status}
                onChange={(e) => update.mutate({ id: lead.id, patch: { status: e.target.value } })}
                className="h-7 w-auto pr-7 text-[12px]"
              >
                {LEAD_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
              </Select>
              <Button size="sm" variant="outline" onClick={() => setLogFor(lead)}>
                <Send size={12} /> Log
              </Button>
            </li>
          ))}
        </ol>
      )}

      <AddLeadDialog open={addOpen} onOpenChange={setAddOpen} startupId={startupId} />
      {logFor && (
        <LogOutreachDialog
          open
          onOpenChange={(v) => {
            if (!v) setLogFor(null);
          }}
          lead={logFor}
          startupId={logFor.startup_id}
        />
      )}
    </Panel>
  );
}

// --- Outreach journal -------------------------------------------------------------------------

function OutreachJournal({ startupId }: { startupId?: number }) {
  const outreach = useOutreach(startupId ? { startup_id: startupId } : {});
  const leads = useLeads({ startup_id: startupId });
  const nameFor = (id: number) => (leads.data ?? []).find((l) => l.id === id)?.name;

  const rows = useMemo(() => (outreach.data ?? []).slice(0, 12), [outreach.data]);

  return (
    <Panel title="Outreach journal · latest" lamp={<Lamp tone="dim" />} bodyClassName="!p-0">
      {!rows.length ? (
        <div className="p-4"><EmptyState message="No outreach logged yet." /></div>
      ) : (
        <ol className="divide-y divide-ops-line">
          {rows.map((a) => (
            <li key={a.id} className="flex items-center gap-3 px-4 py-2">
              <span className="tnum w-16 shrink-0 text-[11px] text-ink-faint">{fmtDay(a.timestamp)}</span>
              <span className="min-w-0 flex-1 truncate text-[13px] text-ink">{nameFor(a.lead_id) ?? `Lead #${a.lead_id}`}</span>
              <span className="text-[11px] uppercase tracking-wide text-ink-faint">{a.type}</span>
              <ResultTag result={a.result} />
            </li>
          ))}
        </ol>
      )}
    </Panel>
  );
}

function ResultTag({ result }: { result: OutreachResult | null }) {
  if (!result) return <span className="tnum text-[11px] text-ink-faint">—</span>;
  const positive = ["REPLIED", "MEETING_BOOKED", "CONVERTED"].includes(result);
  return (
    <span className={`tnum w-28 shrink-0 text-right text-[11px] ${positive ? "text-go" : result === "NOT_INTERESTED" ? "text-critical" : "text-ink-faint"}`}>
      {result.replace("_", " ").toLowerCase()}
    </span>
  );
}

// --- Experiments --------------------------------------------------------------------------------

function ExperimentsPanel(_props: { startupId?: number }) {
  const running = useExperiments({ status: "RUNNING" });
  const planned = useExperiments({ status: "PLANNED" });
  const completed = useExperiments({});
  const update = useUpdateExperiment();
  const rows = [...(running.data ?? []), ...(planned.data ?? [])].concat(
    (completed.data ?? []).filter((e) => e.status === "COMPLETED").slice(0, 3),
  );

  return (
    <Panel title="Growth experiments" lamp={<Lamp tone="ai" pulse={!!running.data?.length} />} bodyClassName="!p-0 space-y-0">
      {!rows.length ? (
        <div className="p-4"><EmptyState message="No experiments yet." hint="Treat growth as hypotheses to test." /></div>
      ) : (
        <ol className="divide-y divide-ops-line">
          {rows.map((e) => (
            <li key={e.id} className="px-4 py-3">
              <div className="flex items-center gap-2.5">
                <FlaskConical size={13} className={e.status === "RUNNING" ? "text-ai" : "text-ink-faint"} strokeWidth={1.75} />
                <span className="min-w-0 flex-1 truncate text-[14px] font-medium text-ink">{e.name}</span>
                <Select
                  aria-label={`Status for ${e.name}`}
                  value={e.status}
                  onChange={(ev) => update.mutate({ id: e.id, patch: { status: ev.target.value } })}
                  className="h-7 w-auto pr-7 text-[11px]"
                >
                  {["PLANNED", "RUNNING", "COMPLETED", "CANCELLED"].map((s) => <option key={s}>{s}</option>)}
                </Select>
              </div>
              {e.hypothesis && <p className="mt-1 pl-6 text-[12px] leading-snug text-ink-dim">{e.hypothesis}</p>}
              {e.conclusion && (
                <p className="mt-1 pl-6 text-[12px] leading-snug text-go">→ {e.conclusion}</p>
              )}
            </li>
          ))}
        </ol>
      )}
    </Panel>
  );
}

// --- Dialogs ---------------------------------------------------------------------------------------

function AddLeadDialog({ open, onOpenChange, startupId }: { open: boolean; onOpenChange: (v: boolean) => void; startupId?: number }) {
  const create = useCreateLead();
  const [form, setForm] = useState({ name: "", company: "", role: "", email: "" });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="New lead">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate(
              {
                startup_id: startupId!,
                name: form.name.trim(),
                company: form.company || null,
                role: form.role || null,
                email: form.email || null,
                source: "MANUAL",
              },
              { onSuccess: () => onOpenChange(false) },
            );
          }}
          className="space-y-3"
        >
          <Field label="Name"><Input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Role"><Input value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })} /></Field>
            <Field label="Company"><Input value={form.company} onChange={(e) => setForm({ ...form, company: e.target.value })} /></Field>
          </div>
          <Field label="Email"><Input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></Field>
          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" variant="go" disabled={!form.name.trim() || create.isPending}>Add lead</Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function LogOutreachDialog({
  open,
  onOpenChange,
  lead,
  startupId,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  lead: LeadOut;
  startupId: number;
}) {
  const log = useLogOutreach();
  const [type, setType] = useState("EMAIL");
  const [result, setResult] = useState<OutreachResult>("SENT");
  const [notes, setNotes] = useState("");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title={`Log outreach · ${lead.name}`}>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            log.mutate(
              { lead_id: lead.id, startup_id: startupId, type, result, notes: notes || null },
              { onSuccess: () => onOpenChange(false) },
            );
          }}
          className="space-y-3"
        >
          <div className="grid grid-cols-2 gap-3">
            <Field label="Channel">
              <Select value={type} onChange={(e) => setType(e.target.value)}>
                {["EMAIL", "LINKEDIN", "CALL", "WHATSAPP", "OTHER"].map((t) => <option key={t}>{t}</option>)}
              </Select>
            </Field>
            <Field label="Result">
              <Select value={result} onChange={(e) => setResult(e.target.value as OutreachResult)}>
                {OUTREACH_RESULTS.map((r) => <option key={r}>{r}</option>)}
              </Select>
            </Field>
          </div>
          <Field label="Notes">
            <Textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="What happened?" />
          </Field>
          <p className="text-[11px] leading-snug text-ink-faint">
            Logging advances the lead's pipeline stage automatically when the result warrants it.
          </p>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" variant="go" disabled={log.isPending}>Record</Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

