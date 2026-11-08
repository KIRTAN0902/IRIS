import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import {
  ArrowRight,
  Bot,
  Check,
  Clock,
  Code,
  FileText,
  LineChart,
  Plus,
  Search,
  Users,
} from "lucide-react";
import { api } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { Dialog, DialogContent } from "@/components/ui/Overlay";
import { cn } from "@/lib/format";
import { useLensStore } from "@/stores/lensStore";

const CoworkerChatPage = lazy(() =>
  import("@/features/coworkers/CoworkerChatPage").then((m) => ({ default: m.CoworkerChatPage })),
);

export type Coworker = {
  id: string;
  name: string;
  role: string;
  description: string;
  system_instructions: string;
  specialisation: string;
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

const CATEGORIES = [
  { id: "all", label: "All Specialists" },
  { id: "engineering", label: "Development" },
  { id: "research", label: "Research" },
  { id: "analysis", label: "Analysis" },
  { id: "writing", label: "Writing" },
  { id: "management", label: "Management" },
] as const;

export function FleetLens() {
  const { selectedCoworkerId, setSelectedCoworkerId } = useLensStore();

  const [coworkers, setCoworkers] = useState<Coworker[]>([]);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [search, setSearch] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<string>("all");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  // Creation modal state
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
        specialisation: formSpec.trim(),
        description: formDesc.trim(),
        allowed_capabilities: formCapabilities,
        system_instructions: `You are ${formName.trim()}, a specialized coworker operating within IRIS.`,
        permission_profile: {
          require_approval_for: ["execute_desktop_command", "git_push"],
        },
      });
      await refresh();
      setCreateModalOpen(false);
      setSelectedCoworkerId(c.id);
    } catch (e) {
      setError(String(e));
    } finally {
      setIsCreating(false);
    }
  };

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

  const filteredCoworkers = coworkers.filter((c) => {
    const matchesSearch =
      c.name.toLowerCase().includes(search.toLowerCase()) ||
      c.role.toLowerCase().includes(search.toLowerCase()) ||
      c.specialisation.toLowerCase().includes(search.toLowerCase());
    return matchesSearch && matchesCategory(c.role, c.specialisation, selectedCategory);
  });

  const activeCoworker = coworkers.find((c) => c.id === selectedCoworkerId);

  // If a coworker is selected, display their focused workspace with back button!
  if (selectedCoworkerId && activeCoworker) {
    return (
      <div className="flex h-[calc(100vh-3.5rem)] w-full flex-col overflow-hidden">
        <div className="flex h-11 shrink-0 items-center justify-between border-b border-ops-line px-4 bg-ops-panel/90 text-xs">
          <button
            type="button"
            onClick={() => setSelectedCoworkerId(null)}
            className="flex items-center gap-1.5 text-ai hover:underline font-semibold cursor-pointer"
          >
            ← Back to Fleet Overview
          </button>
          <div className="flex items-center gap-2">
            <span className="font-semibold text-ink">{activeCoworker.name}</span>
            <span className="text-ink-faint">({activeCoworker.role})</span>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto">
          <Suspense fallback={<div className="p-4 text-xs text-ink-faint animate-pulse">Loading Coworker Stage…</div>}>
            <CoworkerChatPage />
          </Suspense>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6 pb-12 p-4 md:p-6">
      {/* 1. Fleet Operations Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-ai/10 border border-ai/20 text-ai">
              <Users size={18} />
            </div>
            <div>
              <h1 className="text-2xl font-bold tracking-tight text-ink">Coworker Fleet</h1>
              <p className="text-xs text-ink-dim">
                Autonomous specialist agents coordinated by IRIS to execute engineering, research, and analysis.
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Button onClick={() => handleOpenCreateModal()} className="flex items-center gap-1.5 shadow-xs">
            <Plus size={14} />
            <span>Deploy Specialist</span>
          </Button>
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-critical/30 bg-critical/10 p-3 text-xs text-critical">
          {error}
        </div>
      )}

      {loading && (
        <div className="text-xs text-ink-faint animate-pulse">Synchronizing coworker fleet…</div>
      )}

      {/* 2. Pending Actions Approval Banner */}
      {approvals.length > 0 && (
        <section className="rounded-2xl border border-amber-500/30 bg-amber-500/10 p-4 shadow-xs space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="font-bold text-sm text-amber-500 flex items-center gap-2">
              <Clock size={16} />
              <span>Privileged Actions Awaiting Approval ({approvals.length})</span>
            </h2>
          </div>
          <div className="grid gap-3">
            {approvals.map((a) => (
              <div
                key={a.id}
                className="rounded-xl bg-ops-panel p-3.5 border border-amber-500/20 shadow-2xs space-y-2"
              >
                <div className="flex items-center justify-between text-xs">
                  <span className="font-semibold text-ink">
                    {coworkers.find((c) => c.id === a.coworker_id)?.name ?? "Specialist"} requests{" "}
                    <code className="rounded bg-ops-ground px-1.5 py-0.5 text-ai font-mono">
                      {a.capability}
                    </code>
                  </span>
                </div>
                <p className="text-xs text-ink-dim">{a.reason || "Executing task action requiring verification."}</p>
                <div className="flex gap-2 pt-1">
                  <Button
                    size="sm"
                    onClick={() =>
                      act(() => api.post(`/coworkers/approvals/${a.id}/decision?approved=true`, {}))
                    }
                  >
                    <Check size={13} />
                    <span>Approve</span>
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() =>
                      act(() =>
                        api.post(`/coworkers/approvals/${a.id}/decision?approved=false`, {
                          reason: "Denied in Fleet",
                        }),
                      )
                    }
                  >
                    Reject
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* 3. Search & Filter Pills */}
      <div className="flex flex-col sm:flex-row gap-3 items-stretch sm:items-center justify-between">
        <div className="flex h-10 w-full sm:w-72 items-center gap-2 rounded-xl border border-ops-line bg-ops-panel px-3 focus-within:border-ai transition">
          <Search size={15} className="text-ink-faint shrink-0" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search specialists…"
            className="w-full bg-transparent text-xs text-ink outline-none placeholder:text-ink-faint"
          />
          {search && (
            <button onClick={() => setSearch("")} className="text-xs text-ink-faint hover:text-ink cursor-pointer">
              ✕
            </button>
          )}
        </div>

        <div className="flex items-center gap-1 overflow-x-auto pb-1 sm:pb-0 scrollbar-none">
          {CATEGORIES.map((cat) => (
            <button
              key={cat.id}
              onClick={() => setSelectedCategory(cat.id)}
              className={cn(
                "rounded-xl px-3 py-1.5 text-xs font-medium transition cursor-pointer whitespace-nowrap",
                selectedCategory === cat.id
                  ? "bg-ai text-white shadow-xs"
                  : "bg-ops-panel border border-ops-line text-ink-dim hover:text-ink",
              )}
            >
              {cat.label}
            </button>
          ))}
        </div>
      </div>

      {/* 4. Coworker Roster Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {filteredCoworkers.map((c) => {
          const activeTasksCount = (c.tasks ?? []).filter((t) =>
            ["running", "queued", "working"].includes(t.status),
          ).length;
          const assignedProject = projects.find((p) => p.id === c.project_id);

          return (
            <div
              key={c.id}
              onClick={() => setSelectedCoworkerId(c.id)}
              className="group flex flex-col justify-between rounded-2xl border border-ops-line bg-ops-panel p-5 shadow-xs hover:border-ai/60 hover:shadow-md transition-all cursor-pointer"
            >
              <div className="space-y-3">
                <div className="flex items-start justify-between">
                  <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-ops-raised border border-ops-line group-hover:border-ai/30 transition text-ai">
                    {c.specialisation.includes("cod") || c.specialisation.includes("dev") ? (
                      <Code size={18} />
                    ) : c.specialisation.includes("analy") ? (
                      <LineChart size={18} />
                    ) : c.specialisation.includes("writ") ? (
                      <FileText size={18} />
                    ) : (
                      <Bot size={18} />
                    )}
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span
                      className={cn(
                        "h-2 w-2 rounded-full",
                        activeTasksCount > 0
                          ? "bg-ai animate-pulse"
                          : c.availability
                          ? "bg-emerald-500"
                          : "bg-gray-400",
                      )}
                    />
                    <span className="text-[11px] font-medium text-ink-dim capitalize">
                      {activeTasksCount > 0 ? "Working" : c.availability ? "Online" : c.status}
                    </span>
                  </div>
                </div>

                <div>
                  <h3 className="text-base font-bold text-ink group-hover:text-ai transition-colors">
                    {c.name}
                  </h3>
                  <p className="text-xs text-ai font-medium capitalize mt-0.5">
                    {c.role} · {c.specialisation}
                  </p>
                  {assignedProject && (
                    <span className="inline-block mt-1 text-[10px] text-ink-faint rounded bg-ops-raised px-1.5 py-0.5">
                      📁 {assignedProject.name}
                    </span>
                  )}
                  <p className="text-xs text-ink-dim mt-2 line-clamp-2 leading-relaxed">
                    {c.description || "Specialist agent ready for scoped execution."}
                  </p>
                </div>
              </div>

              <div className="mt-4 pt-3 border-t border-ops-line/60 flex items-center justify-between text-xs text-ink-faint">
                <span>{(c.tasks ?? []).length} tasks logged</span>
                <span className="inline-flex items-center gap-1 font-semibold text-ai group-hover:translate-x-0.5 transition-transform">
                  <span>Open</span>
                  <ArrowRight size={13} />
                </span>
              </div>
            </div>
          );
        })}
      </div>

      {/* 5. Pre-configured Specialists Section */}
      <div className="pt-6 border-t border-ops-line space-y-4">
        <div>
          <h2 className="text-sm font-bold uppercase tracking-wider text-ink-faint">
            Specialist Templates
          </h2>
          <p className="text-xs text-ink-dim mt-0.5">
            Deploy pre-configured agents for rapid workspace integration.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {templates.map((t) => (
            <div
              key={t.key}
              className="rounded-2xl border border-ops-line bg-ops-panel/60 p-4 space-y-3 flex flex-col justify-between"
            >
              <div>
                <h4 className="text-sm font-bold text-ink">{t.name}</h4>
                <p className="text-xs text-ai capitalize font-medium">{t.specialisation}</p>
                <p className="text-xs text-ink-dim mt-1.5 line-clamp-2">{t.description}</p>
              </div>

              <div className="flex items-center justify-between pt-2 border-t border-ops-line/60 text-xs">
                <span className="text-ink-faint text-[11px]">
                  {t.allowed_capabilities.length} tools granted
                </span>
                <Button size="sm" variant="outline" onClick={() => handleOpenCreateModal(t)}>
                  <Plus size={12} />
                  <span>Use Template</span>
                </Button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Creation Modal */}
      <Dialog open={createModalOpen} onOpenChange={setCreateModalOpen}>
        <DialogContent title="Deploy Specialist Coworker">
          <form onSubmit={handleCreateSubmit} className="space-y-4 pt-2">
            <div>
              <label className="block text-xs font-semibold text-ink mb-1">Coworker Name</label>
              <input
                type="text"
                required
                value={formName}
                onChange={(e) => setFormName(e.target.value)}
                placeholder="e.g. Athena, Hermes, Orion"
                className="w-full rounded-xl border border-ops-line bg-ops-void px-3 py-2 text-xs text-ink outline-none focus:border-ai"
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
                  placeholder="e.g. Lead Software Engineer"
                  className="w-full rounded-xl border border-ops-line bg-ops-void px-3 py-2 text-xs text-ink outline-none focus:border-ai"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-ink mb-1">Specialisation</label>
                <input
                  type="text"
                  required
                  value={formSpec}
                  onChange={(e) => setFormSpec(e.target.value)}
                  placeholder="e.g. backend, security, testing"
                  className="w-full rounded-xl border border-ops-line bg-ops-void px-3 py-2 text-xs text-ink outline-none focus:border-ai"
                />
              </div>
            </div>
            <div>
              <label className="block text-xs font-semibold text-ink mb-1">Mission / Description</label>
              <textarea
                rows={3}
                value={formDesc}
                onChange={(e) => setFormDesc(e.target.value)}
                placeholder="Describe what this specialist is responsible for…"
                className="w-full rounded-xl border border-ops-line bg-ops-void px-3 py-2 text-xs text-ink outline-none focus:border-ai"
              />
            </div>
            <div className="flex justify-end gap-2 pt-2 border-t border-ops-line">
              <Button type="button" variant="ghost" onClick={() => setCreateModalOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={isCreating}>
                {isCreating ? "Deploying…" : "Deploy Coworker"}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
