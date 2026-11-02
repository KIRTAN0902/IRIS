import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { CoworkerChatView } from "./CoworkerChatView";

type Coworker = {
  id: string; name: string; role: string; description: string; specialisation: string;
  responsibilities: string[]; system_instructions: string; preferred_provider?: string | null;
  preferred_model?: string | null; allowed_capabilities: string[]; project_id: number | null;
  permission_profile: Record<string, unknown>; status: string; availability: boolean;
  config_version: number; tasks?: Task[];
};
type Task = {
  id: string; coworker_id: string; instruction: string; status: string; objectives: string[];
  acceptance_criteria: string[]; dependencies: string[]; project_id: number | null;
  output?: string | null; error?: string | null; verification?: { state?: string; independently_verified?: boolean; unresolved_items?: string[] };
  session_id?: string | null; coding_task_id?: string | null; created_at: string;
};
type Template = { key: string; name: string; role: string; description: string; specialisation: string; responsibilities: string[]; allowed_capabilities: string[] };
type Project = { id: number; name: string; directory: string; read_access: boolean };
type Approval = { id: string; coworker_id: string; task_id: string; capability: string; action: Record<string, unknown>; reason: string; status: string };
type ComputerDemo = { provider: string; is_mock: boolean; status: string; evidence: Record<string, unknown>[]; events: { type: string; detail: Record<string, unknown> }[] };

const statusTone: Record<string, string> = {
  idle: "text-ink-dim", queued: "text-ink-dim", running: "text-ai", working: "text-ai",
  waiting_approval: "text-amber-700", failed: "text-red-700", interrupted: "text-amber-700",
  completed: "text-emerald-700", completed_with_issues: "text-amber-800", cancelled: "text-ink-faint", stopped: "text-ink-faint",
};

export function CoworkersPage() {
  const [coworkers, setCoworkers] = useState<Coworker[]>([]);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState(false);
  const [computerDemo, setComputerDemo] = useState<ComputerDemo | null>(null);
  const selected = useMemo(() => coworkers.find((c) => c.id === selectedId) ?? null, [coworkers, selectedId]);

  const refresh = useCallback(async () => {
    try {
      const [cs, ts, ps, aps] = await Promise.all([
        api.get<Coworker[]>("/coworkers"), api.get<Template[]>("/coworkers/templates"),
        api.get<Project[]>("/coding/projects"), api.get<Approval[]>("/coworkers/approvals"),
      ]);
      setCoworkers(cs); setTemplates(ts); setProjects(ps); setApprovals(aps);
      setSelectedId((current) => current && cs.some((c) => c.id === current) ? current : cs[0]?.id ?? null);
    } catch (e) { setError(String(e)); }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => {
    if (!selectedId) return;
    let active = true;
    const load = async () => {
      try {
        const c = await api.get<Coworker>(`/coworkers/${selectedId}`);
        if (active) setCoworkers((xs) => xs.map((x) => x.id === selectedId ? c : x));
      } catch (e) { if (active) setError(String(e)); }
    };
    void load(); const timer = window.setInterval(() => { void refresh(); void load(); }, 4000);
    return () => { active = false; window.clearInterval(timer); };
  }, [selectedId, refresh]);

  const act = async (fn: () => Promise<unknown>) => { setError(""); try { await fn(); await refresh(); } catch (e) { setError(String(e)); } };
  const createFrom = (template?: Template) => {
    const name = window.prompt(template ? `Name this ${template.name.toLowerCase()}:` : "Coworker name:", template?.name ?? "");
    if (!name?.trim()) return;
    const role = template?.role ?? window.prompt("Coworker role:", "Specialist");
    if (!role) return;
    void act(async () => {
      const c = await api.post<Coworker>("/coworkers", {
        name: name.trim(), role, description: template?.description ?? "", specialisation: template?.specialisation ?? "general",
        responsibilities: template?.responsibilities ?? [], allowed_capabilities: template?.allowed_capabilities ?? [],
        project_id: null, permission_profile: {},
      });
      setSelectedId(c.id);
    });
  };
  const updateProject = (value: string) => {
    if (!selected) return;
    void act(() => api.patch(`/coworkers/${selected.id}`, { project_id: value ? Number(value) : null }));
  };
  const editResponsibilities = () => {
    if (!selected) return;
    const value = window.prompt("Responsibilities (one per line):", selected.responsibilities.join("\n"));
    if (value === null) return;
    void act(() => api.patch(`/coworkers/${selected.id}`, { responsibilities: value.split("\n").map((x) => x.trim()).filter(Boolean) }));
  };
  const editProfile = () => {
    if (!selected) return;
    const name = window.prompt("Coworker name:", selected.name); if (name === null) return;
    const role = window.prompt("Role:", selected.role); if (role === null) return;
    const specialisation = window.prompt("Specialisation:", selected.specialisation); if (specialisation === null) return;
    const system_instructions = window.prompt("Additional role instructions:", selected.system_instructions); if (system_instructions === null) return;
    const capabilities = window.prompt("Granted IRIS capability names (comma separated):", selected.allowed_capabilities.join(", ")); if (capabilities === null) return;
    void act(() => api.patch(`/coworkers/${selected.id}`, { name, role, specialisation, system_instructions,
      allowed_capabilities: capabilities.split(",").map((x) => x.trim()).filter(Boolean) }));
  };
  const runComputerDemo = () => void act(async () => {
    const result = await api.post<ComputerDemo>("/coworkers/computer-use/demo", { task_id: crypto.randomUUID() });
    setComputerDemo(result);
  });

  return <div className="space-y-6">
    <header className="flex flex-wrap items-start justify-between gap-3">
      <div><p className="text-xs uppercase tracking-[.2em] text-ai">IRIS / execution</p><h1 className="mt-2 text-3xl font-semibold text-ink">Coworkers</h1><p className="mt-2 max-w-2xl text-sm text-ink-dim">Specialised workers operate within IRIS task and permission boundaries. IRIS Supervisor remains the orchestrator.</p></div>
      <div className="flex flex-wrap gap-2"><Button variant="outline" onClick={runComputerDemo}>Run CUA mock demo</Button><Button onClick={() => createFrom()}>Create custom coworker</Button></div>
    </header>
    {error && <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</div>}
    {computerDemo && <section className="rounded-2xl border border-ai/30 bg-ai-dim/30 p-4"><div className="flex flex-wrap items-center justify-between gap-2"><h2 className="font-semibold">Computer-use contract demonstration</h2><span className="rounded-full bg-white px-2 py-1 text-xs text-amber-800">Mock only · no desktop controlled</span></div><p className="mt-1 text-sm text-ink-dim">Provider: {computerDemo.provider} · {computerDemo.events.length} recorded lifecycle events · {computerDemo.status}</p><pre className="mt-2 max-h-36 overflow-auto whitespace-pre-wrap rounded-lg bg-white p-3 text-xs">{JSON.stringify(computerDemo.evidence,null,2)}</pre></section>}
    {approvals.length > 0 && <section className="rounded-2xl border border-amber-300 bg-amber-50 p-4">
      <h2 className="font-semibold text-amber-950">Actions waiting for approval ({approvals.length})</h2>
      <div className="mt-3 grid gap-3">{approvals.map((a) => <div key={a.id} className="rounded-xl bg-white p-3 ring-1 ring-amber-200">
        <p className="font-medium">{coworkers.find((c) => c.id === a.coworker_id)?.name ?? "Coworker"} requests <code>{a.capability}</code></p>
        <pre className="mt-2 max-h-36 overflow-auto whitespace-pre-wrap text-xs text-ink-dim">{JSON.stringify(a.action, null, 2)}</pre>
        <p className="mt-2 text-sm text-ink-dim">{a.reason} Approval applies only to this recorded action.</p>
        <div className="mt-3 flex gap-2"><Button onClick={() => act(() => api.post(`/coworkers/approvals/${a.id}/decision?approved=true`, {}))}>Approve this action</Button><Button variant="outline" onClick={() => act(() => api.post(`/coworkers/approvals/${a.id}/decision?approved=false`, { reason: "Rejected in IRIS" }))}>Reject</Button></div>
      </div>)}</div>
    </section>}
    <div className="grid gap-5 lg:grid-cols-[minmax(240px,0.75fr)_minmax(0,1.65fr)]">
      <section className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-ink-faint">Your coworkers</h2>
        {coworkers.map((c) => <button key={c.id} onClick={() => setSelectedId(c.id)} className={`w-full rounded-2xl border p-4 text-left transition ${selectedId === c.id ? "border-ai/40 bg-white shadow-sm" : "border-ops-line bg-ops-panel hover:bg-white"}`}>
          <span className="flex items-center justify-between gap-2"><strong className="text-ink">{c.name}</strong><span className={`text-xs capitalize ${statusTone[c.status] ?? "text-ink-dim"}`}>{c.status.replaceAll("_", " ")}</span></span>
          <span className="mt-1 block text-sm text-ink-dim">{c.role} · {c.specialisation}</span><span className="mt-2 block text-xs text-ink-faint">{(c.tasks ?? []).length} recent tasks · {c.allowed_capabilities.length} granted capabilities</span>
        </button>)}
        <h3 className="pt-3 text-xs font-semibold uppercase tracking-wider text-ink-faint">Create from a template</h3>
        <div className="grid grid-cols-2 gap-2">{templates.map((t) => <button key={t.key} onClick={() => createFrom(t)} className="rounded-xl border border-ops-line bg-white p-3 text-left hover:border-ai/40"><span className="block text-sm font-medium">{t.name}</span><span className="mt-1 block text-xs text-ink-faint">{t.specialisation}</span></button>)}</div>
      </section>
      {selected ? (
        <section className="min-w-0 flex-1 space-y-4">
          <CoworkerChatView
            coworker={selected}
            projects={projects}
            activeProjectId={selected.project_id}
            onSelectProject={(pid) => updateProject(pid ? String(pid) : "")}
            onRefreshCoworkers={refresh}
            onRefreshProjects={refresh}
            onOpenSettings={() => setEditing((v) => !v)}
          />
          {editing && (
            <div className="rounded-2xl border border-ops-line bg-white p-4 shadow-sm sm:p-6">
              <div className="flex items-center justify-between pb-3 border-b border-ops-line">
                <div>
                  <h3 className="font-semibold text-ink">Coworker Profile & Settings</h3>
                  <p className="text-xs text-ink-dim">Inspect capabilities, system instructions, and boundaries</p>
                </div>
                <button
                  onClick={() => setEditing(false)}
                  className="rounded-lg border border-ops-line px-2.5 py-1 text-xs text-ink-dim hover:text-ink cursor-pointer"
                >
                  Close settings
                </button>
              </div>
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                <Info label="Availability" value={selected.availability ? "Available" : "Unavailable"} />
                <Info label="Configuration" value={`Version ${selected.config_version}`} />
                <Info label="Provider preference" value={`${selected.preferred_provider ?? "IRIS default"}${selected.preferred_model ? ` · ${selected.preferred_model}` : ""}`} />
                <Info label="Workspace" value={projects.find((p) => p.id === selected.project_id)?.name ?? "None"} />
              </div>
              <div className="mt-4 rounded-xl bg-ops-ground p-4">
                <label className="block text-xs font-medium text-ink-dim">Assigned project workspace</label>
                <select
                  value={selected.project_id ?? ""}
                  onChange={(e) => updateProject(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-ops-line bg-white p-2 text-sm"
                >
                  <option value="">No project assigned</option>
                  {projects.map((p) => (
                    <option key={p.id} value={p.id}>{p.name} · {p.directory}</option>
                  ))}
                </select>
                <p className="mt-1 text-xs text-ink-faint">
                  Project permissions are enforced by the backend. Coworkers do not automatically receive write, command, or network access.
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <button onClick={editProfile} className="rounded-lg border border-ops-line bg-white px-3 py-2 text-sm hover:bg-ops-surface cursor-pointer">
                    Edit identity, instructions and capabilities
                  </button>
                  <button onClick={editResponsibilities} className="rounded-lg border border-ops-line bg-white px-3 py-2 text-sm hover:bg-ops-surface cursor-pointer">
                    Edit responsibilities
                  </button>
                </div>
                <p className="mt-3 text-xs text-ink-faint">
                  Granted capabilities: {selected.allowed_capabilities.length ? selected.allowed_capabilities.join(", ") : "none"}. Host command, email, drive and device capabilities remain denied without a scoped adapter.
                </p>
              </div>
            </div>
          )}
        </section>
      ) : (
        <section className="rounded-2xl border border-dashed border-ops-line bg-ops-panel p-8 text-center">
          <h2 className="text-lg font-medium">Start with a coworker</h2>
          <p className="mt-2 text-sm text-ink-dim">Create one from a template or define a custom role and responsibilities.</p>
        </section>
      )}
    </div>
  </div>;
}

function Info({ label, value }: { label: string; value: string }) { return <div className="rounded-xl bg-ops-ground p-3"><p className="text-[11px] uppercase tracking-wider text-ink-faint">{label}</p><p className="mt-1 break-words text-sm text-ink">{value}</p></div>; }
