import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import {
  AlertCircle,
  ArrowRight,
  Bell,
  Briefcase,
  Check,
  CheckCircle2,
  Clock,
  Code,
  FileText,
  Loader2,
  RefreshCw,
  Search,
  ShieldAlert,
  Sparkles,
  Users,
} from "lucide-react";
import { api } from "@/api/client";
import { Button } from "@/components/ui/Button";
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
  status: "ready" | "needs_setup" | "busy" | "working" | "unavailable" | string;
  availability: boolean;
  setup_requirement?: string | null;
  message?: string | null;
  connected_services?: string[];
  execution_target?: string | null;
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

const STATUS_FILTERS = [
  { id: "all", label: "All Specialists (4)" },
  { id: "ready", label: "Ready & Active" },
  { id: "needs_setup", label: "Needs Setup" },
] as const;

export function FleetLens() {
  const { selectedCoworkerId, setSelectedCoworkerId } = useLensStore();

  const [coworkers, setCoworkers] = useState<Coworker[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [search, setSearch] = useState("");
  const [selectedFilter, setSelectedFilter] = useState<string>("all");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      setLoading(true);
      setError("");
      const [cs, ps, aps] = await Promise.all([
        api.get<Coworker[]>("/coworkers"),
        api.get<Project[]>("/coding/projects"),
        api.get<Approval[]>("/coworkers/approvals"),
      ]);
      // Ensure IRIS Core and BUBBA are never shown, only the 4 canonical specialists
      const validSpecialists = cs.filter(
        (c) =>
          !c.name.toLowerCase().includes("iris core") &&
          !c.name.toLowerCase().includes("bubba") &&
          c.id !== "00000000-0000-0000-0000-000000000001",
      );
      setCoworkers(validSpecialists);
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

  const filteredCoworkers = coworkers.filter((c) => {
    const matchesSearch =
      c.name.toLowerCase().includes(search.toLowerCase()) ||
      c.role.toLowerCase().includes(search.toLowerCase()) ||
      c.specialisation.toLowerCase().includes(search.toLowerCase()) ||
      (c.description ?? "").toLowerCase().includes(search.toLowerCase());

    if (!matchesSearch) return false;

    if (selectedFilter === "ready") {
      return c.status === "ready" || c.status === "busy" || c.availability;
    }
    if (selectedFilter === "needs_setup") {
      return c.status === "needs_setup" || (!c.availability && c.status !== "busy");
    }
    return true;
  });

  const activeCoworker = coworkers.find((c) => c.id === selectedCoworkerId);

  // If a coworker is selected, display their focused workspace with back button
  if (selectedCoworkerId && activeCoworker) {
    return (
      <div className="flex h-[calc(100vh-3.5rem)] w-full flex-col overflow-hidden bg-ops-ground">
        <div className="flex h-12 shrink-0 items-center justify-between border-b border-ops-line px-5 bg-ops-panel/95 backdrop-blur text-xs">
          <button
            type="button"
            onClick={() => setSelectedCoworkerId(null)}
            className="flex items-center gap-2 text-ai hover:underline font-semibold cursor-pointer transition-colors"
          >
            ← Back to Fleet Overview
          </button>
          <div className="flex items-center gap-3">
            <span className="font-bold text-ink">{activeCoworker.name}</span>
            <span className="text-ink-faint">·</span>
            <span className="text-ink-dim font-medium">{activeCoworker.role}</span>
            <span
              className={cn(
                "rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider",
                activeCoworker.status === "ready"
                  ? "bg-emerald-500/10 text-emerald-600 border border-emerald-500/20"
                  : activeCoworker.status === "needs_setup"
                  ? "bg-amber-500/10 text-amber-600 border border-amber-500/20"
                  : "bg-neutral-500/10 text-neutral-500 border border-neutral-500/20",
              )}
            >
              {activeCoworker.status === "needs_setup" ? "Setup Required" : activeCoworker.status}
            </span>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto">
          <Suspense
            fallback={
              <div className="flex items-center justify-center h-full p-8 text-xs text-ink-faint gap-2">
                <Loader2 size={16} className="animate-spin text-ai" />
                <span>Initializing Coworker Stage…</span>
              </div>
            }
          >
            <CoworkerChatPage />
          </Suspense>
        </div>
      </div>
    );
  }

  const getCoworkerIcon = (name: string, spec: string) => {
    const n = name.toLowerCase();
    const s = spec.toLowerCase();
    if (n.includes("developer") || s.includes("cod") || s.includes("soft")) {
      return <Code size={20} className="text-blue-600" />;
    }
    if (n.includes("workspace") || s.includes("work") || s.includes("prod")) {
      return <Briefcase size={20} className="text-emerald-600" />;
    }
    if (n.includes("notification") || s.includes("notif") || s.includes("event")) {
      return <Bell size={20} className="text-violet-600" />;
    }
    if (n.includes("scribe") || s.includes("writ") || s.includes("doc")) {
      return <FileText size={20} className="text-amber-600" />;
    }
    return <Sparkles size={20} className="text-ai" />;
  };

  return (
    <div className="mx-auto max-w-6xl space-y-6 pb-16 p-4 md:p-6">
      {/* 1. Fleet Operations Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-ai/10 border border-ai/20 text-ai shadow-2xs">
              <Users size={20} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-2xl font-bold tracking-tight text-ink">Specialized Coworkers</h1>
                <span className="rounded-full bg-ops-raised px-2 py-0.5 text-[11px] font-semibold text-ink-dim border border-ops-line">
                  4 Active Fleet Roles
                </span>
              </div>
              <p className="text-xs text-ink-dim mt-0.5">
                Specialized autonomous execution units governed, dispatched, and supervised under IRIS Core.
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => void refresh()}
            disabled={loading}
            className="flex items-center gap-1.5"
          >
            <RefreshCw size={13} className={cn(loading && "animate-spin")} />
            <span>Sync Fleet</span>
          </Button>
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-critical/30 bg-critical/10 p-3.5 text-xs text-critical flex items-center gap-2">
          <ShieldAlert size={15} />
          <span>{error}</span>
        </div>
      )}

      {/* 2. Pending Actions Approval Banner */}
      {approvals.length > 0 && (
        <section className="rounded-2xl border border-amber-500/30 bg-amber-500/10 p-4 shadow-xs space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="font-bold text-sm text-amber-600 flex items-center gap-2">
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

      {/* 3. Search & Operational Filter Bar */}
      <div className="flex flex-col sm:flex-row gap-3 items-stretch sm:items-center justify-between">
        <div className="flex h-10 w-full sm:w-80 items-center gap-2 rounded-xl border border-ops-line bg-ops-panel px-3 focus-within:border-ai transition">
          <Search size={15} className="text-ink-faint shrink-0" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search coworker abilities or tools…"
            className="w-full bg-transparent text-xs text-ink outline-none placeholder:text-ink-faint"
          />
          {search && (
            <button onClick={() => setSearch("")} className="text-xs text-ink-faint hover:text-ink cursor-pointer">
              ✕
            </button>
          )}
        </div>

        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 sm:pb-0 scrollbar-none">
          {STATUS_FILTERS.map((f) => (
            <button
              key={f.id}
              onClick={() => setSelectedFilter(f.id)}
              className={cn(
                "rounded-xl px-3.5 py-1.5 text-xs font-semibold transition cursor-pointer whitespace-nowrap",
                selectedFilter === f.id
                  ? "bg-ai text-white shadow-xs"
                  : "bg-ops-panel border border-ops-line text-ink-dim hover:text-ink hover:bg-ops-raised",
              )}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {/* 4. Specialized Coworkers Roster (Grid of 4) */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        {filteredCoworkers.map((c) => {
          const activeTasksCount = (c.tasks ?? []).filter((t) =>
            ["running", "queued", "working"].includes(t.status),
          ).length;
          const assignedProject = projects.find((p) => p.id === c.project_id);
          const isNeedsSetup = c.status === "needs_setup";
          const isReady = c.status === "ready" || c.availability;

          return (
            <div
              key={c.id}
              onClick={() => setSelectedCoworkerId(c.id)}
              className={cn(
                "group flex flex-col justify-between rounded-2xl border p-5 shadow-xs transition-all cursor-pointer",
                isNeedsSetup
                  ? "border-amber-500/30 bg-amber-500/[0.02] hover:border-amber-500/60 hover:shadow-md"
                  : "border-ops-line bg-ops-panel hover:border-ai/60 hover:shadow-md",
              )}
            >
              <div className="space-y-4">
                {/* Header: Icon, Name, and Status Badge */}
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-ops-raised border border-ops-line group-hover:border-ai/40 transition shadow-2xs">
                      {getCoworkerIcon(c.name, c.specialisation)}
                    </div>
                    <div>
                      <h3 className="text-base font-bold text-ink group-hover:text-ai transition-colors flex items-center gap-1.5">
                        <span>{c.name}</span>
                      </h3>
                      <p className="text-xs text-ink-dim font-medium mt-0.5">
                        {c.role}
                      </p>
                    </div>
                  </div>

                  {/* Real Availability Badge */}
                  <div className="flex items-center">
                    {activeTasksCount > 0 ? (
                      <span className="inline-flex items-center gap-1.5 rounded-full bg-ai/10 border border-ai/20 px-2.5 py-1 text-[11px] font-semibold text-ai">
                        <span className="h-2 w-2 rounded-full bg-ai animate-pulse" />
                        <span>Working ({activeTasksCount})</span>
                      </span>
                    ) : isReady ? (
                      <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 px-2.5 py-1 text-[11px] font-semibold text-emerald-600">
                        <CheckCircle2 size={12} />
                        <span>Ready</span>
                      </span>
                    ) : isNeedsSetup ? (
                      <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-500/10 border border-amber-500/20 px-2.5 py-1 text-[11px] font-semibold text-amber-600">
                        <AlertCircle size={12} />
                        <span>Needs Setup</span>
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1.5 rounded-full bg-neutral-500/10 border border-neutral-500/20 px-2.5 py-1 text-[11px] font-semibold text-neutral-500">
                        <span>{c.status}</span>
                      </span>
                    )}
                  </div>
                </div>

                {/* Description */}
                <p className="text-xs text-ink-dim leading-relaxed">
                  {c.description || "Autonomous specialist agent."}
                </p>

                {/* Setup Requirement or Connected Services Details */}
                {isNeedsSetup && c.setup_requirement && (
                  <div className="rounded-xl border border-amber-500/20 bg-amber-500/5 px-3 py-2 text-xs text-amber-700 flex items-start gap-2">
                    <AlertCircle size={14} className="shrink-0 mt-0.5 text-amber-600" />
                    <span>{c.setup_requirement}</span>
                  </div>
                )}

                {c.connected_services && c.connected_services.length > 0 && (
                  <div className="flex items-center gap-1.5 flex-wrap pt-0.5">
                    <span className="text-[11px] text-ink-faint">Connected:</span>
                    {c.connected_services.map((svc) => (
                      <span
                        key={svc}
                        className="rounded-md bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 text-[11px] font-semibold text-emerald-600"
                      >
                        {svc}
                      </span>
                    ))}
                  </div>
                )}

                {/* Tool Capabilities Badges */}
                {c.allowed_capabilities && c.allowed_capabilities.length > 0 && (
                  <div className="space-y-1.5 pt-1">
                    <div className="flex flex-wrap gap-1.5">
                      {c.allowed_capabilities.slice(0, 5).map((cap) => (
                        <span
                          key={cap}
                          className="rounded-lg bg-ops-raised border border-ops-line px-2 py-0.5 text-[10px] font-mono text-ink-dim"
                        >
                          {cap}
                        </span>
                      ))}
                      {c.allowed_capabilities.length > 5 && (
                        <span className="rounded-lg bg-ops-raised px-1.5 py-0.5 text-[10px] text-ink-faint">
                          +{c.allowed_capabilities.length - 5} more
                        </span>
                      )}
                    </div>
                  </div>
                )}

                {assignedProject && (
                  <div className="pt-1">
                    <span className="inline-block text-[11px] text-ink-faint rounded bg-ops-raised border border-ops-line px-2 py-0.5">
                      📁 Assigned Project: {assignedProject.name}
                    </span>
                  </div>
                )}
              </div>

              {/* Footer: Open Coworker Stage */}
              <div className="mt-5 pt-3.5 border-t border-ops-line/60 flex items-center justify-between text-xs text-ink-faint">
                <span>{(c.tasks ?? []).length} tasks recorded</span>
                <span className="inline-flex items-center gap-1 font-semibold text-ai group-hover:translate-x-1 transition-transform">
                  <span>Open Coworker Stage</span>
                  <ArrowRight size={14} />
                </span>
              </div>
            </div>
          );
        })}
      </div>

      {filteredCoworkers.length === 0 && !loading && (
        <div className="rounded-2xl border border-dashed border-ops-line p-10 text-center space-y-2">
          <p className="text-sm font-semibold text-ink">No coworkers match your filter</p>
          <p className="text-xs text-ink-dim">
            Switch filter or clear your search query to view the 4 specialized fleet coworkers.
          </p>
          <Button size="sm" variant="outline" onClick={() => { setSelectedFilter("all"); setSearch(""); }}>
            Reset Filters
          </Button>
        </div>
      )}
    </div>
  );
}
