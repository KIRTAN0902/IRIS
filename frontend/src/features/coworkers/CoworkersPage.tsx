import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowRight,
  Bot,
  Clock,
  Code2,
  FolderKanban,
  LineChart,
  MessageSquare,
  PenTool,
  Plus,
  Search,
  UsersRound,
} from "lucide-react";
import { api } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { Dialog, DialogContent } from "@/components/ui/Overlay";

export type Coworker = {
  id: string;
  name: string;
  role: string;
  description: string;
  specialisation: string;
  responsibilities: string[];
  system_instructions: string;
  preferred_provider?: string | null;
  preferred_model?: string | null;
  allowed_capabilities: string[];
  project_id: number | null;
  permission_profile: Record<string, unknown>;
  status: string;
  availability: boolean;
  config_version: number;
  tasks?: Task[];
};

export type Task = {
  id: string;
  coworker_id: string;
  instruction: string;
  status: string;
  objectives: string[];
  acceptance_criteria: string[];
  dependencies: string[];
  project_id: number | null;
  output?: string | null;
  error?: string | null;
  verification?: { state?: string; independently_verified?: boolean; unresolved_items?: string[] };
  session_id?: string | null;
  coding_task_id?: string | null;
  created_at: string;
};

export type Template = {
  key: string;
  name: string;
  role: string;
  description: string;
  specialisation: string;
  responsibilities: string[];
  allowed_capabilities: string[];
};

export type Project = {
  id: number;
  name: string;
  directory: string;
  read_access: boolean;
};

export type Approval = {
  id: string;
  coworker_id: string;
  task_id: string;
  capability: string;
  action: Record<string, unknown>;
  reason: string;
  status: string;
};

export type ComputerDemo = {
  provider: string;
  is_mock: boolean;
  status: string;
  evidence: Record<string, unknown>[];
  events: { type: string; detail: Record<string, unknown> }[];
};

const CATEGORIES = [
  { id: "all", label: "All" },
  { id: "engineering", label: "Development" },
  { id: "research", label: "Research" },
  { id: "analysis", label: "Analysis" },
  { id: "writing", label: "Writing" },
  { id: "management", label: "Management" },
] as const;

export function CoworkersPage() {
  const navigate = useNavigate();
  const [coworkers, setCoworkers] = useState<Coworker[]>([]);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [search, setSearch] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<string>("all");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  // In-page creation modal state
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [formName, setFormName] = useState("");
  const [formRole, setFormRole] = useState("Specialist");
  const [formSpec, setFormSpec] = useState("general");
  const [formDesc, setFormDesc] = useState("");
  const [formCapabilities, setFormCapabilities] = useState<string[]>([]);
  const [isCreating, setIsCreating] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setLoading(true);
      setError("");
      const [cs, ts, ps, aps] = await Promise.all([
        api.get<Coworker[]>("/coworkers"),
        api.get<Template[]>("/coworkers/templates"),
        api.get<Project[]>("/coding/projects"),
        api.get<Approval[]>("/coworkers/approvals"),
      ]);
      setCoworkers(cs);
      setTemplates(ts);
      setProjects(ps);
      setApprovals(aps);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const act = async (fn: () => Promise<unknown>) => {
    setError("");
    try {
      await fn();
      await refresh();
    } catch (e) {
      setError(String(e));
    }
  };

  const handleOpenCreateModal = (template?: Template) => {
    if (template) {
      setFormName(template.name);
      setFormRole(template.role);
      setFormSpec(template.specialisation);
      setFormDesc(template.description);
      setFormCapabilities(template.allowed_capabilities ?? []);
    } else {
      setFormName("");
      setFormRole("Specialist");
      setFormSpec("general");
      setFormDesc("");
      setFormCapabilities(["web_search", "workspace_read"]);
    }
    setCreateModalOpen(true);
  };

  const handleCreateSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formName.trim() || !formRole.trim() || isCreating) return;

    setIsCreating(true);
    setError("");
    try {
      const c = await api.post<Coworker>("/coworkers", {
        name: formName.trim(),
        role: formRole.trim(),
        description: formDesc.trim(),
        specialisation: formSpec.trim() || "general",
        responsibilities: [],
        allowed_capabilities: formCapabilities,
        project_id: null,
        permission_profile: {},
      });
      setCreateModalOpen(false);
      navigate(`/coworkers/${c.id}/chat`);
    } catch (e) {
      setError(String(e));
    } finally {
      setIsCreating(false);
    }
  };

  // Categorisation helper
  const matchesCategory = (roleStr: string, specStr: string, cat: string) => {
    if (cat === "all") return true;
    const combined = `${roleStr} ${specStr}`.toLowerCase();
    if (cat === "engineering") return combined.includes("dev") || combined.includes("cod") || combined.includes("software") || combined.includes("engineer");
    if (cat === "research") return combined.includes("research") || combined.includes("search") || combined.includes("investigat");
    if (cat === "analysis") return combined.includes("analy") || combined.includes("data") || combined.includes("metrics");
    if (cat === "writing") return combined.includes("writ") || combined.includes("scribe") || combined.includes("doc");
    if (cat === "management") return combined.includes("manage") || combined.includes("project") || combined.includes("coord") || combined.includes("plan");
    return true;
  };

  // Filtered coworkers
  const filteredCoworkers = useMemo(() => {
    const q = search.trim().toLowerCase();
    return coworkers.filter((c) => {
      const matchesSearch =
        !q ||
        c.name.toLowerCase().includes(q) ||
        c.role.toLowerCase().includes(q) ||
        c.specialisation.toLowerCase().includes(q) ||
        c.description.toLowerCase().includes(q);
      const matchesCat = matchesCategory(c.role, c.specialisation, selectedCategory);
      return matchesSearch && matchesCat;
    });
  }, [coworkers, search, selectedCategory]);

  // Filtered templates
  const filteredTemplates = useMemo(() => {
    const q = search.trim().toLowerCase();
    return templates.filter((t) => {
      const matchesSearch =
        !q ||
        t.name.toLowerCase().includes(q) ||
        t.role.toLowerCase().includes(q) ||
        t.specialisation.toLowerCase().includes(q) ||
        t.description.toLowerCase().includes(q);
      const matchesCat = matchesCategory(t.role, t.specialisation, selectedCategory);
      return matchesSearch && matchesCat;
    });
  }, [templates, search, selectedCategory]);

  // Role icon helper
  const getRoleIcon = (role: string, spec = "") => {
    const s = `${role} ${spec}`.toLowerCase();
    if (s.includes("dev") || s.includes("cod") || s.includes("software")) return <Code2 size={20} className="text-ai" />;
    if (s.includes("research") || s.includes("investigat")) return <Search size={20} className="text-sky-600" />;
    if (s.includes("analy") || s.includes("data")) return <LineChart size={20} className="text-emerald-600" />;
    if (s.includes("writ") || s.includes("scribe")) return <PenTool size={20} className="text-amber-600" />;
    if (s.includes("manage") || s.includes("project")) return <FolderKanban size={20} className="text-purple-600" />;
    return <Bot size={20} className="text-ink" />;
  };

  return (
    <div className="mx-auto w-full max-w-5xl space-y-7 pb-12">
      {/* 1. Header */}
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight text-ink">Coworkers</h1>
          <p className="mt-1.5 max-w-2xl text-sm text-ink-dim">
            Your specialised AI team. Each coworker has its own expertise, responsibilities and workspace.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2.5">
          <Button onClick={() => handleOpenCreateModal()}>
            <Plus size={16} className="mr-1.5" /> Create custom coworker
          </Button>
        </div>
      </header>

      {/* Error alert */}
      {error && (
        <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          {error}
        </div>
      )}

      {/* Actions waiting for approval */}
      {approvals.length > 0 && (
        <section className="rounded-2xl border border-amber-300 bg-amber-50/80 p-4 shadow-xs">
          <h2 className="font-semibold text-sm text-amber-950 flex items-center gap-2">
            <Clock size={16} className="text-amber-700" />
            Actions waiting for approval ({approvals.length})
          </h2>
          <div className="mt-3 grid gap-3">
            {approvals.map((a) => (
              <div key={a.id} className="rounded-xl bg-white p-3.5 border border-amber-200 shadow-2xs">
                <p className="text-sm font-medium text-ink">
                  {coworkers.find((c) => c.id === a.coworker_id)?.name ?? "Coworker"} requests{" "}
                  <code className="rounded-md bg-ops-ground px-1.5 py-0.5 text-xs text-ai font-mono">
                    {a.capability}
                  </code>
                </p>
                <pre className="mt-2 max-h-32 overflow-auto whitespace-pre-wrap text-xs text-ink-dim bg-ops-panel p-2.5 rounded-lg border border-line">
                  {JSON.stringify(a.action, null, 2)}
                </pre>
                <p className="mt-2 text-xs text-ink-dim">{a.reason}</p>
                <div className="mt-3 flex gap-2">
                  <Button onClick={() => act(() => api.post(`/coworkers/approvals/${a.id}/decision?approved=true`, {}))}>
                    Approve action
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => act(() => api.post(`/coworkers/approvals/${a.id}/decision?approved=false`, { reason: "Rejected in IRIS" }))}
                  >
                    Reject
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* 2. Search & Category Filters */}
      <div className="flex flex-col sm:flex-row gap-3 items-stretch sm:items-center justify-between">
        {/* Search */}
        <label className="flex h-10 w-full sm:w-72 items-center gap-2 rounded-xl border border-ops-line bg-ops-panel px-3 focus-within:border-ai transition">
          <Search size={15} className="text-ink-faint shrink-0" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search coworkers..."
            className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-ink-faint"
            aria-label="Search coworkers"
          />
          {search && (
            <button
              onClick={() => setSearch("")}
              className="text-xs text-ink-faint hover:text-ink cursor-pointer"
            >
              ✕
            </button>
          )}
        </label>

        {/* Category Pills */}
        <div className="flex items-center gap-1 overflow-x-auto pb-1 sm:pb-0 scrollbar-none">
          {CATEGORIES.map((cat) => (
            <button
              key={cat.id}
              onClick={() => setSelectedCategory(cat.id)}
              className={`rounded-xl px-3 py-1.5 text-xs font-medium transition cursor-pointer whitespace-nowrap ${
                selectedCategory === cat.id
                  ? "bg-ai text-white shadow-xs"
                  : "bg-ops-panel border border-ops-line text-ink-dim hover:text-ink hover:bg-white"
              }`}
            >
              {cat.label}
            </button>
          ))}
        </div>
      </div>

      {/* 3. Coworker Cards Section */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-ink-faint">
            Your Coworkers {filteredCoworkers.length > 0 && `(${filteredCoworkers.length})`}
          </h2>
        </div>

        {loading ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-44 rounded-2xl bg-ops-raised animate-pulse" />
            ))}
          </div>
        ) : filteredCoworkers.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-ops-line-bright bg-ops-panel p-8 text-center">
            <UsersRound size={32} className="mx-auto text-ink-faint mb-2.5" />
            <h3 className="text-base font-semibold text-ink">
              {search ? "No matching coworkers" : "No coworkers configured yet"}
            </h3>
            <p className="mt-1 text-xs text-ink-dim max-w-sm mx-auto">
              {search
                ? "Try adjusting your search or category filter."
                : "Create your first coworker from the templates below to start collaborating."}
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {filteredCoworkers.map((c) => {
              const activeTasksCount = (c.tasks ?? []).filter((t) => ["running", "queued", "working"].includes(t.status)).length;
              const hasActiveConvo = (c.tasks ?? []).length > 0;
              const assignedProject = projects.find((p) => p.id === c.project_id);

              return (
                <div
                  key={c.id}
                  onClick={() => navigate(`/coworkers/${c.id}/chat`)}
                  className="group relative flex flex-col justify-between rounded-2xl border border-ops-line bg-white p-5 shadow-xs hover:border-ai/50 hover:shadow-md hover:-translate-y-0.5 transition-all cursor-pointer"
                >
                  <div>
                    {/* Card Header: Avatar & Status */}
                    <div className="flex items-start justify-between gap-2 mb-3">
                      <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-ops-panel border border-ops-line/80 group-hover:border-ai/30 transition">
                        {getRoleIcon(c.role, c.specialisation)}
                      </div>
                      <div className="flex items-center gap-1.5">
                        <span
                          className={`inline-block h-2 w-2 rounded-full ${
                            c.status === "working" || activeTasksCount > 0
                              ? "bg-ai animate-pulse"
                              : c.availability
                              ? "bg-emerald-500"
                              : "bg-gray-400"
                          }`}
                        />
                        <span className="text-[11px] font-medium capitalize text-ink-dim">
                          {activeTasksCount > 0 ? "Executing" : c.availability ? "Online" : c.status}
                        </span>
                      </div>
                    </div>

                    {/* Coworker Identity */}
                    <div className="flex items-center gap-2">
                      <h3 className="text-base font-bold text-ink group-hover:text-ai transition-colors truncate">
                        {c.name}
                      </h3>
                      {hasActiveConvo && (
                        <span
                          className="flex items-center gap-1 rounded-full bg-ai/10 px-2 py-0.5 text-[10px] font-medium text-ai shrink-0"
                          title="Has active conversation history"
                        >
                          <MessageSquare size={10} />
                          <span>Active</span>
                        </span>
                      )}
                    </div>

                    <div className="flex items-center gap-2 mt-0.5">
                      <p className="text-xs font-medium text-ai/90 capitalize truncate">
                        {c.role} · {c.specialisation}
                      </p>
                      {assignedProject && (
                        <span className="text-[10px] text-ink-faint rounded-md bg-ops-panel px-1.5 py-0.5 truncate max-w-[120px]">
                          📁 {assignedProject.name}
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-ink-dim mt-2 line-clamp-2 leading-relaxed">
                      {c.description || c.system_instructions || "Ready to assist with scoped project tasks and execution."}
                    </p>
                  </div>

                  {/* Card Footer: Metadata & Open Chat Button */}
                  <div className="mt-5 pt-3.5 border-t border-ops-line/60 flex items-center justify-between text-xs">
                    <div className="flex items-center gap-2 text-[11px] text-ink-faint">
                      <span>{(c.tasks ?? []).length} tasks</span>
                      <span>·</span>
                      <span>{c.allowed_capabilities.length} capabilities</span>
                    </div>
                    <span className="inline-flex items-center gap-1 text-xs font-semibold text-ai group-hover:translate-x-0.5 transition-transform">
                      <span>Chat</span>
                      <ArrowRight size={13} />
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>

      {/* 4. Available Templates Section */}
      <section className="space-y-4 pt-4 border-t border-ops-line">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wider text-ink-faint">
            Available Templates
          </h2>
          <p className="mt-1 text-xs text-ink-dim">
            Launch pre-configured specialists for engineering, research, data analysis, and technical documentation.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredTemplates.map((t) => (
            <div
              key={t.key}
              className="flex flex-col justify-between rounded-2xl border border-ops-line bg-ops-panel/60 p-4.5 hover:bg-white hover:border-ops-line-bright transition shadow-2xs"
            >
              <div>
                <div className="flex items-center justify-between gap-2 mb-2">
                  <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-ops-raised">
                    {getRoleIcon(t.role, t.specialisation)}
                  </div>
                  <span className="rounded-full bg-ops-raised px-2 py-0.5 text-[10px] font-semibold text-ink-dim uppercase">
                    Template
                  </span>
                </div>
                <h4 className="text-sm font-bold text-ink">{t.name}</h4>
                <p className="text-[11px] font-medium text-ai capitalize mt-0.5">{t.specialisation}</p>
                <p className="mt-2 text-xs text-ink-dim line-clamp-2 leading-relaxed">
                  {t.description}
                </p>
              </div>

              <div className="mt-4 pt-3 border-t border-ops-line/60 flex items-center justify-between">
                <span className="text-[11px] text-ink-faint">
                  {t.allowed_capabilities.length} granted tools
                </span>
                <button
                  type="button"
                  onClick={() => handleOpenCreateModal(t)}
                  className="inline-flex items-center gap-1 rounded-xl bg-ai/10 border border-ai/20 px-2.5 py-1 text-xs font-semibold text-ai hover:bg-ai hover:text-white transition cursor-pointer"
                >
                  <Plus size={13} />
                  <span>Use template</span>
                </button>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Create Coworker Dialog */}
      <Dialog open={createModalOpen} onOpenChange={setCreateModalOpen}>
        <DialogContent title="Create Coworker">
          <form onSubmit={handleCreateSubmit} className="space-y-4 pt-1">
            <div>
              <label className="block text-xs font-semibold text-ink mb-1">Coworker Name</label>
              <input
                type="text"
                required
                value={formName}
                onChange={(e) => setFormName(e.target.value)}
                placeholder="e.g. Atlas, Maya, Scribe"
                className="w-full rounded-xl border border-ops-line bg-ops-panel px-3 py-2 text-sm text-ink outline-none focus:border-ai transition"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-semibold text-ink mb-1">Role Title</label>
                <input
                  type="text"
                  required
                  value={formRole}
                  onChange={(e) => setFormRole(e.target.value)}
                  placeholder="e.g. Lead Engineer"
                  className="w-full rounded-xl border border-ops-line bg-ops-panel px-3 py-2 text-sm text-ink outline-none focus:border-ai transition"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-ink mb-1">Specialisation</label>
                <input
                  type="text"
                  value={formSpec}
                  onChange={(e) => setFormSpec(e.target.value)}
                  placeholder="e.g. frontend, backend, research"
                  className="w-full rounded-xl border border-ops-line bg-ops-panel px-3 py-2 text-sm text-ink outline-none focus:border-ai transition"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-ink mb-1">Description & Purpose</label>
              <textarea
                rows={3}
                value={formDesc}
                onChange={(e) => setFormDesc(e.target.value)}
                placeholder="What does this coworker help you accomplish?"
                className="w-full rounded-xl border border-ops-line bg-ops-panel px-3 py-2 text-sm text-ink outline-none focus:border-ai transition resize-none"
              />
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <Button type="button" variant="ghost" onClick={() => setCreateModalOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={!formName.trim() || !formRole.trim() || isCreating}>
                {isCreating ? "Creating…" : "Create Coworker"}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
