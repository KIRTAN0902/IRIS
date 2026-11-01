import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { ArrowDown, ArrowUp, Check, ChevronDown, Clock3, GripVertical, LayoutDashboard, Lock, LockOpen, RotateCcw, Sparkles, X } from "lucide-react";
import { Link } from "react-router-dom";
import { useCheckHabit, useHabits, useSituation } from "@/hooks/queries";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/ui/Overlay";
import { cn } from "@/lib/format";
import { useUIContext, useCreateUIProposal, useDecideUIProposal, useRollbackUI, useSaveUILayout, useSaveUIPreferences, useUIState } from "@/features/home/useUIOrchestrator";
import type { Platform, UIProposal, UIState, WidgetLayoutItem } from "@/features/home/uiOrchestratorApi";

const WIDGETS: Record<string, { title: string; icon: string; route: string; help: string }> = {
  priorities: { title: "Priorities", icon: "◎", route: "/tasks", help: "Tasks needing attention" },
  schedule: { title: "Schedule", icon: "◷", route: "/schedule", help: "Your day at a glance" },
  routines: { title: "Routines", icon: "↗", route: "/today", help: "Routines scheduled today" },
  coworkers: { title: "Coworkers", icon: "✳", route: "/coworkers", help: "Work in progress" },
  progress: { title: "Day progress", icon: "◌", route: "/today", help: "Progress across today's plan" },
};
const WIDGET_ALIASES: Record<string, string[]> = {
  priorities: ["tasks", "task list", "to do", "todo", "urgent work"],
  schedule: ["agenda", "calendar", "events", "appointments"],
  routines: ["routine", "habits", "habit tracker"],
  coworkers: ["coworker activity", "agents", "team activity", "agent tasks"],
  progress: ["day progress", "how am i doing", "completion", "daily progress"],
};

function detectPlatform(): Platform {
  if (typeof window !== "undefined" && ((window as unknown as { Capacitor?: unknown }).Capacitor || /android/i.test(navigator.userAgent))) return "android";
  return "desktop";
}

export function OrchestratedDashboard() {
  const platform = detectPlatform();
  const state = useUIState();
  const context = useUIContext();
  const habits = useHabits();
  const saveLayout = useSaveUILayout();
  const savePreferences = useSaveUIPreferences();
  const rollback = useRollbackUI();
  const createProposal = useCreateUIProposal();
  const decide = useDecideUIProposal();
  const [editing, setEditing] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [proposalError, setProposalError] = useState("");
  const [showHistory, setShowHistory] = useState(false);
  const [clock, setClock] = useState(Date.now());
  const layout = state.data?.layouts?.[platform] ?? [];
  const visible = layout.filter((item) => item.visible && (!item.expires_at || Date.parse(item.expires_at) > clock));
  const desktop = platform === "desktop";
  const suggestions: { id: string; text: string; reason: string }[] = [];
  if (context.data?.attention_count && !visible.some((item) => item.id === "priorities")) suggestions.push({ id: "priorities", text: `${context.data.attention_count} overdue item${context.data.attention_count === 1 ? " needs" : "s need"} attention.`, reason: "There are overdue items that may need attention." });
  if (context.data?.has_schedule && !visible.some((item) => item.id === "schedule")) suggestions.push({ id: "schedule", text: "You have schedule items today.", reason: "Show today's agenda on Home." });
  if ((habits.data ?? []).some((habit) => habit.active && habit.scheduled_today) && !visible.some((item) => item.id === "routines")) suggestions.push({ id: "routines", text: "Your routines are scheduled today.", reason: "Show today's routine progress on Home." });
  useEffect(() => { const timer = window.setInterval(() => setClock(Date.now()), 60_000); return () => window.clearInterval(timer); }, []);

  const proposeFromPrompt = () => {
    const value = prompt.trim().toLowerCase();
    if (!value || !state.data) return;
    const id = Object.keys(WIDGETS).find((key) =>
      [key, WIDGETS[key].title.toLowerCase(), ...WIDGET_ALIASES[key]].some((term) => value.includes(term)),
    );
    if (!id) {
      setProposalError("Try asking for your tasks, agenda, routines, coworker activity, or day progress.");
      return;
    }
    const current = layout.find((item) => item.id === id);
    const hides = /\b(hide|remove|take off)\b/.test(value);
    const makesWide = /\b(wide|wider|expand|full width)\b/.test(value);
    const makesCompact = /\b(compact|standard width|smaller)\b/.test(value);
    const moveDirection = /\b(move|reorder|put)\b/.test(value) ? (/\b(up|earlier|first)\b/.test(value) ? -1 : /\b(down|later|last)\b/.test(value) ? 1 : 0) : 0;
    if (current?.locked && (hides || makesWide || makesCompact || moveDirection)) {
      setProposalError(`${WIDGETS[id].title} is locked. Unlock it before changing its layout.`);
      return;
    }
    if (hides && !current) {
      setProposalError(`${WIDGETS[id].title} is not in this layout.`);
      return;
    }
    const temporary = /\b(temporary|temporarily|for a while|for today|for 6 hours)\b/.test(value);
    const lifecycle = temporary ? { lifecycle: "temporary" as const, expires_at: new Date(Date.now() + 6 * 60 * 60_000).toISOString() } : { lifecycle: "persistent" as const, expires_at: null };
    let next = [...layout];
    if (!current) next.push({ id, visible: true, size: "standard", locked: false, config: {}, ...lifecycle });
    else next = next.map((item) => item.id === id ? { ...item, visible: !hides, ...(makesWide ? { size: "wide" } : makesCompact ? { size: "standard" } : {}), ...(!hides && !makesWide && !makesCompact ? lifecycle : {}) } : item);
    let title = hides ? `Hide ${WIDGETS[id].title}` : makesWide ? `Expand ${WIDGETS[id].title}` : makesCompact ? `Resize ${WIDGETS[id].title}` : current ? `Show ${WIDGETS[id].title}` : `Add ${WIDGETS[id].title}`;
    if (moveDirection) {
      const visibleItems = next.filter((item) => item.visible);
      const position = visibleItems.findIndex((item) => item.id === id);
      const other = visibleItems[position + moveDirection];
      if (!other) { setProposalError(`${WIDGETS[id].title} is already at that end of the layout.`); return; }
      if (other.locked) { setProposalError(`${WIDGETS[other.id].title} is locked and cannot be moved.`); return; }
      const from = next.findIndex((item) => item.id === id); const to = next.findIndex((item) => item.id === other.id);
      [next[from], next[to]] = [next[to], next[from]]; title = `Reorder ${WIDGETS[id].title}`;
    }
    setProposalError("");
    createProposal.mutate({ platform, title, reason: prompt.trim(), widgets: next });
    setPrompt("");
  };

  const move = (widgetId: string, delta: number) => {
    if (!state.data) return;
    const next = [...layout];
    const visibleIndex = visible.findIndex((item) => item.id === widgetId);
    const other = visible[visibleIndex + delta];
    if (!other) return;
    const from = next.findIndex((item) => item.id === widgetId);
    const to = next.findIndex((item) => item.id === other.id);
    if (next[from].locked || next[to].locked) return;
    [next[from], next[to]] = [next[to], next[from]];
    saveLayout.mutate({ platform, version: state.data.version, widgets: next });
  };
  const updateWidget = (id: string, patch: Partial<WidgetLayoutItem>) => {
    if (!state.data) return;
    saveLayout.mutate({ platform, version: state.data.version, widgets: layout.map((item) => item.id === id ? { ...item, ...patch } : item) });
  };
  const decideProposal = (proposal: UIProposal, decision: "approve" | "reject") => decide.mutate({ id: proposal.id, decision });

  if (state.isError && !state.data) return <section className="mx-auto max-w-xl rounded-2xl border border-critical/30 bg-critical-dim p-5" role="alert"><h1 className="text-lg font-semibold">Home dashboard unavailable</h1><p className="mt-1 text-sm text-ink-dim">IRIS couldn’t load your saved widget layout. Your saved layout has not been changed.</p><button onClick={() => void state.refetch()} className="mt-3 rounded-lg bg-ai px-3 py-2 text-sm text-white">Retry</button></section>;
  if (state.isLoading || !state.data) return <div className="space-y-4 pt-2" aria-label="Loading Home dashboard"><Skeleton className="h-8 w-2/3"/><Skeleton className="h-32 w-full"/><Skeleton className="h-24 w-full"/></div>;

  return <section aria-label="Adaptive Home dashboard" className="pb-4">
    <header className="flex items-start justify-between gap-3">
      <div><h1 className="text-[26px] font-semibold leading-tight text-ink">Your day</h1><p className="mt-1 text-[14px] text-ink-faint">{context.data?.local_time ?? "A clear view of what matters now."}</p></div>
      <button type="button" onClick={() => setEditing((v) => !v)} aria-pressed={editing} className={cn("inline-flex items-center gap-2 rounded-xl border px-3 py-2 text-xs transition", editing ? "border-ai/50 bg-ai-dim text-ink" : "border-ops-line-bright text-ink-faint hover:text-ink")}><LayoutDashboard size={15}/>{editing ? "Done" : "Arrange"}</button>
    </header>

    {(state.isError || saveLayout.isError || savePreferences.isError || createProposal.isError || decide.isError || rollback.isError) && <div className="mt-4 flex flex-wrap items-center gap-2 rounded-xl border border-caution/30 bg-caution-dim px-3 py-2 text-sm text-ink-dim" role="alert"><span>Some dashboard changes may not have saved. Refresh the shared layout before editing again.</span><button onClick={() => void state.refetch()} className="font-medium text-ai underline">Refresh layout</button></div>}

    <DashboardRenderer platform={platform}>
      {visible.map((item, index) => <article key={item.id} className={cn("min-w-0 rounded-2xl border border-ops-line-bright bg-ops-panel p-4", item.size === "wide" && desktop && "lg:col-span-2")}>
        <div className="mb-3 flex items-center gap-2"><span className="text-ai">{WIDGETS[item.id]?.icon ?? "◈"}</span><Link to={WIDGETS[item.id]?.route ?? "/"} className="flex-1 text-sm font-semibold text-ink hover:underline">{WIDGETS[item.id]?.title ?? item.id}</Link>{item.lifecycle === "temporary" && <span className="rounded-full bg-ops-raised px-2 py-0.5 text-[10px] text-ink-faint">Temporary · {item.expires_at ? new Date(item.expires_at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) : ""}</span>}{editing && <div className="flex items-center gap-1">
          <button disabled={index === 0 || item.locked} onClick={() => move(item.id, -1)} className="rounded p-1 text-ink-faint hover:bg-ops-raised disabled:opacity-30" aria-label={`Move ${item.id} up`}><ArrowUp size={14}/></button>
          <button disabled={index === visible.length - 1 || item.locked} onClick={() => move(item.id, 1)} className="rounded p-1 text-ink-faint hover:bg-ops-raised disabled:opacity-30" aria-label={`Move ${item.id} down`}><ArrowDown size={14}/></button>
          <button disabled={item.locked} onClick={() => updateWidget(item.id, { visible: false })} className="rounded p-1 text-ink-faint hover:text-critical disabled:opacity-30" aria-label={`Hide ${item.id}`}><X size={14}/></button>
          {desktop && <button disabled={item.locked} onClick={() => updateWidget(item.id, { size: item.size === "wide" ? "standard" : "wide" })} className="rounded p-1 text-ink-faint hover:text-ink disabled:opacity-30" aria-label={`${item.size === "wide" ? "Make" : "Expand"} ${item.id} ${item.size === "wide" ? "standard width" : "wide"}`} title={item.size === "wide" ? "Standard width" : "Wide widget"}><LayoutDashboard size={14}/></button>}
          <button onClick={() => updateWidget(item.id, { locked: !item.locked })} className="rounded p-1 text-ink-faint hover:text-ink" aria-label={`${item.locked ? "Unlock" : "Lock"} ${item.id}`}>{item.locked ? <Lock size={14}/> : <LockOpen size={14}/>}</button>
        </div>}</div>
        <WidgetBody id={item.id}/>
      </article>)}
    </DashboardRenderer>

    {editing && <div className="mt-4 space-y-3 rounded-2xl border border-dashed border-ops-line-bright p-4">
      <div className="flex items-center gap-2"><GripVertical size={15} className="text-ink-faint"/><h2 className="text-sm font-semibold">Shape your Home</h2><span className="text-xs text-ink-faint">Changes sync across your devices</span></div>
      {!!suggestions.length && <div className="grid gap-2 sm:grid-cols-2">{suggestions.map((suggestion) => <SituationSuggestion key={suggestion.id} text={suggestion.text} onAdd={() => { const next = layout.map((item) => item.id === suggestion.id ? { ...item, visible: true } : item); createProposal.mutate({ platform, title: `Show ${WIDGETS[suggestion.id].title}`, reason: suggestion.reason, widgets: next }); }}/>)}</div>}
      <div className="flex flex-wrap gap-2">{layout.filter((item) => !visible.some((active) => active.id === item.id)).map((item) => <button key={item.id} onClick={() => updateWidget(item.id, { visible: true, lifecycle: "persistent", expires_at: null })} className="rounded-full border border-ops-line-bright px-3 py-1.5 text-xs text-ink-dim hover:border-ai/40">+ {WIDGETS[item.id]?.title ?? item.id}</button>)}
        <label className="flex items-center gap-2 text-xs text-ink-faint">Density <select aria-label="Dashboard density" value={state.data.preferences.density} onChange={(e) => savePreferences.mutate({ version: state.data!.version, preferences: { density: e.target.value as UIState["preferences"]["density"] } })} className="rounded-lg border border-ops-line-bright bg-ops-void px-2 py-1 text-ink"><option value="compact">Compact</option><option value="comfortable">Comfortable</option><option value="spacious">Spacious</option></select></label>
        <label className="flex items-center gap-2 text-xs text-ink-faint"><input type="checkbox" checked={state.data.preferences.interaction_learning} onChange={(e) => savePreferences.mutate({ version: state.data!.version, preferences: { interaction_learning: e.target.checked } })}/>Use my layout choices to shape future proposals</label>
      </div>
      <form onSubmit={(e) => { e.preventDefault(); proposeFromPrompt(); }} className="flex gap-2"><input value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder="Ask IRIS to add a widget, e.g. show my schedule" className="min-w-0 flex-1 rounded-xl border border-ops-line-bright bg-ops-void px-3 py-2 text-sm text-ink placeholder:text-ink-faint"/><Button type="submit" disabled={!prompt.trim() || createProposal.isPending}><Sparkles size={14}/> Propose</Button></form>
      {proposalError && <p role="status" className="text-xs text-caution">{proposalError}</p>}
      <p className="text-[11px] text-ink-faint">IRIS proposals are previews. Nothing changes until you approve.</p>
      {context.data?.active_coworker_tasks && !layout.find((item) => item.id === "coworkers")?.visible && <SituationSuggestion text={`${context.data.active_coworker_tasks} coworker task${context.data.active_coworker_tasks === 1 ? " is" : "s are"} active.`} onAdd={() => { const next = layout.map((item) => item.id === "coworkers" ? { ...item, visible: true } : item); createProposal.mutate({ platform, title: "Show coworker activity", reason: "There is active coworker work to review.", widgets: next }); }}/>}
      {!!state.data.history.length && <button onClick={() => setShowHistory((v) => !v)} className="inline-flex items-center gap-1 text-xs text-ink-faint hover:text-ink"><Clock3 size={13}/>Layout history <ChevronDown size={13}/></button>}
      {showHistory && <div className="flex items-center justify-between rounded-xl bg-ops-void px-3 py-2 text-xs"><span>{state.data.history.length} saved revisions</span><button disabled={rollback.isPending} onClick={() => rollback.mutate()} className="inline-flex items-center gap-1 text-ink-dim hover:text-ink"><RotateCcw size={13}/> Restore previous</button></div>}
    </div>}

    {!!state.data.proposals.length && <div className="mt-4 space-y-3">{state.data.proposals.map((proposal) => <ProposalCard key={proposal.id} proposal={proposal} current={state.data!.layouts[proposal.layout.platform]} onDecision={(decision) => decideProposal(proposal, decision)} busy={decide.isPending}/>)}</div>}
  </section>;
}

function DashboardRenderer({ platform, children }: { platform: Platform; children: ReactNode }) {
  return platform === "android" ? <AndroidDashboardRenderer>{children}</AndroidDashboardRenderer> : <DesktopDashboardRenderer>{children}</DesktopDashboardRenderer>;
}

function DesktopDashboardRenderer({ children }: { children: ReactNode }) {
  return <div className="mt-5 grid grid-cols-1 gap-3 lg:grid-cols-2">{children}</div>;
}

function AndroidDashboardRenderer({ children }: { children: ReactNode }) {
  return <div className="mt-4 flex flex-col gap-2.5">{children}</div>;
}

function SituationSuggestion({ text, onAdd }: { text: string; onAdd: () => void }) {
  const [dismissed, setDismissed] = useState(false);
  if (dismissed) return null;
  return <div className="flex items-center gap-2 rounded-xl border border-ops-line-bright bg-ops-void px-3 py-2 text-xs"><Sparkles size={13} className="shrink-0 text-ai"/><span className="flex-1 text-ink-dim">{text}</span><button type="button" onClick={onAdd} className="text-ink underline">Suggest widget</button><button type="button" onClick={() => setDismissed(true)} aria-label="Dismiss suggestion" className="text-ink-faint"><X size={13}/></button></div>;
}

function WidgetBody({ id }: { id: string }) {
  const situation = useSituation();
  const habits = useHabits();
  const checkHabit = useCheckHabit();
  const context = useUIContext();
  const s = situation.data;
  if ((id === "priorities" || id === "schedule" || id === "progress") && situation.isLoading) return <Skeleton className="h-20 w-full"/>;
  if (id === "routines" && habits.isLoading) return <Skeleton className="h-16 w-full"/>;
  if ((id === "priorities" || id === "schedule" || id === "progress") && situation.isError && !s) return <QueryFailure label="Today's situation" retry={() => void situation.refetch()}/>;
  if (id === "routines" && habits.isError && !habits.data) return <QueryFailure label="Your routines" retry={() => void habits.refetch()}/>;
  if (id === "priorities") {
    const tasks = [...(s?.tasks.overdue ?? []), ...(s?.tasks.in_progress ?? []), ...(s?.tasks.due_today ?? [])].slice(0, 4);
    return tasks.length ? <div className="space-y-2">{tasks.map((t) => <Link key={t.id} to="/tasks" className="flex items-center justify-between gap-2 text-sm text-ink-dim hover:text-ink"><span className="truncate">{t.title}</span><span className="shrink-0 text-[11px] text-ink-faint">{t.area}</span></Link>)}<Link to="/tasks" className="block pt-1 text-xs text-ink-faint">All priorities →</Link></div> : <p className="text-sm text-ink-faint">No urgent tasks right now.</p>;
  }
  if (id === "schedule") {
    const now = s?.now?.current_block; const next = s?.now?.next_commitment;
    return <div className="space-y-2 text-sm">{now && <p className="text-ink-dim"><span className="text-go">Now</span> · {now}</p>}{next && <p className="text-ink-dim"><span className="text-ink-faint">Next</span> · {next}</p>}{!now && !next && (s?.today_schedule ?? []).slice(0, 2).map((item, i) => <p key={`${item.start}-${i}`} className="text-ink-dim"><span className="text-ink-faint">{item.start}</span> · {item.title}</p>)}{!now && !next && !s?.today_schedule.length && <p className="text-ink-faint">Nothing scheduled at the moment.</p>}<Link to="/schedule" className="block pt-1 text-xs text-ink-faint">Open schedule →</Link></div>;
  }
  if (id === "routines") {
    const today = (habits.data ?? []).filter((h) => h.active && h.scheduled_today);
    return <div className="space-y-1">{today.slice(0, 5).map((h) => <div key={h.id} className="flex min-h-11 items-center gap-2 text-sm"><button type="button" onClick={() => checkHabit.mutate({ id: h.id, done: !h.done_today })} aria-label={`${h.done_today ? "Mark" : "Complete"} routine ${h.name}`} className={cn("grid h-8 w-8 shrink-0 place-items-center rounded-full border", h.done_today ? "border-go bg-go-dim text-go" : "border-ops-line-bright text-transparent hover:border-ai")}><Check size={14}/></button><span className={cn("min-w-0 flex-1 text-ink-dim", h.done_today && "text-ink-faint line-through")}>{h.name}</span><span className="shrink-0 text-xs text-ink-faint">{h.streak ? `${h.streak}d` : ""}</span></div>)}{!today.length && <p className="text-sm text-ink-faint">No routines planned today.</p>}<Link to="/today" className="block min-h-10 pt-2 text-xs text-ink-faint hover:text-ai">See all routines →</Link></div>;
  }
  if (id === "coworkers") return <div className="flex items-center justify-between"><p className="text-sm text-ink-dim">{context.data?.active_coworker_tasks ? `${context.data.active_coworker_tasks} active task${context.data.active_coworker_tasks === 1 ? "" : "s"}` : "No active coworker tasks"}</p><Link to="/coworkers" className="text-xs text-ink-faint">View coworkers →</Link></div>;
  const taskCount = [...(s?.tasks.overdue ?? []), ...(s?.tasks.in_progress ?? []), ...(s?.tasks.due_today ?? [])].length;
  const habitsToday = (habits.data ?? []).filter((h) => h.active && h.scheduled_today);
  const done = habitsToday.filter((h) => h.done_today).length + (s?.done.today.length ?? 0);
  const total = habitsToday.length + taskCount;
  return <div><p className="text-2xl font-semibold text-ink">{total ? Math.round(done / total * 100) : 100}%</p><p className="text-xs text-ink-faint">{done} of {total} planned items complete</p><div className="mt-3 h-1.5 overflow-hidden rounded-full bg-ops-raised"><div className="h-full rounded-full bg-go transition-all" style={{ width: `${total ? Math.min(100, done / total * 100) : 100}%` }}/></div></div>;
}

function QueryFailure({ label, retry }: { label: string; retry: () => void }) {
  return <div className="rounded-xl bg-caution-dim p-3 text-sm text-ink-dim" role="status"><p>{label} could not load.</p><button onClick={retry} className="mt-1 min-h-10 text-ai underline">Retry</button></div>;
}

function ProposalCard({ proposal, current, onDecision, busy }: { proposal: UIProposal; current: WidgetLayoutItem[]; onDecision: (decision: "approve" | "reject") => void; busy: boolean }) {
  const after = proposal.layout.widgets.filter((w) => w.visible).map((w) => `${WIDGETS[w.id]?.title ?? w.id}${w.lifecycle === "temporary" ? " (temporary)" : ""}`);
  const before = current.filter((w) => w.visible).map((w) => `${WIDGETS[w.id]?.title ?? w.id}${w.lifecycle === "temporary" ? " (temporary)" : ""}`);
  return <article className="rounded-2xl border border-ai/25 bg-ai-dim/40 p-4"><div className="flex items-start gap-3"><Sparkles size={16} className="mt-1 shrink-0 text-ai"/><div className="min-w-0 flex-1"><h2 className="text-sm font-semibold">{proposal.title}</h2><p className="mt-1 text-xs text-ink-faint">{proposal.reason}</p><div className="mt-3 grid grid-cols-2 gap-2 text-xs"><div className="rounded-lg bg-ops-void p-2"><span className="text-ink-faint">Before</span><p className="mt-1 text-ink-dim">{before.join(" · ") || "Empty"}</p></div><div className="rounded-lg bg-ops-void p-2"><span className="text-ink-faint">After</span><p className="mt-1 text-ink-dim">{after.join(" · ") || "Empty"}</p></div></div><div className="mt-3 flex gap-2"><Button size="sm" onClick={() => onDecision("approve")} disabled={busy}><Check size={14}/> Approve</Button><Button size="sm" variant="ghost" onClick={() => onDecision("reject")} disabled={busy}><X size={14}/> Reject</Button></div></div></div></article>;
}
