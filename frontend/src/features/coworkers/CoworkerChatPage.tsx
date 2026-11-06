import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { AlertCircle, ArrowLeft, RefreshCw, X } from "lucide-react";
import { api } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { CoworkerChatView, type Coworker, type Project } from "./CoworkerChatView";

export function CoworkerChatPage() {
  const { coworkerId } = useParams<{ coworkerId: string }>();
  const navigate = useNavigate();

  const [coworker, setCoworker] = useState<Coworker | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);

  const loadData = useCallback(async () => {
    if (!coworkerId) return;
    setLoading(true);
    setError(null);
    try {
      const [c, ps] = await Promise.all([
        api.get<Coworker>(`/coworkers/${coworkerId}`),
        api.get<Project[]>("/coding/projects"),
      ]);
      if (!c.project_id && ps.length > 0) {
        c.project_id = ps[0].id;
        void api.patch(`/coworkers/${coworkerId}`, { project_id: ps[0].id });
      }
      setCoworker(c);
      setProjects(ps);
      document.title = `${c.name} · Coworker Chat · IRIS`;
    } catch (err) {
      console.error("Failed to load coworker chat:", err);
      setError("Coworker could not be found or failed to load.");
    } finally {
      setLoading(false);
    }
  }, [coworkerId]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const handleUpdateProject = async (projectId: number | null) => {
    if (!coworker) return;
    try {
      await api.patch(`/coworkers/${coworker.id}`, { project_id: projectId });
      setCoworker((prev) => (prev ? { ...prev, project_id: projectId } : null));
    } catch (err) {
      console.error("Failed to update project workspace:", err);
    }
  };

  const handleRefreshCoworker = async () => {
    if (!coworkerId) return;
    try {
      const c = await api.get<Coworker>(`/coworkers/${coworkerId}`);
      setCoworker(c);
    } catch (err) {
      console.error("Failed to refresh coworker:", err);
    }
  };

  const handleRefreshProjects = async () => {
    try {
      const ps = await api.get<Project[]>("/coding/projects");
      setProjects(ps);
    } catch (err) {
      console.error("Failed to refresh projects:", err);
    }
  };

  const editProfile = async () => {
    if (!coworker) return;
    const name = window.prompt("Coworker name:", coworker.name);
    if (name === null) return;
    const role = window.prompt("Role:", coworker.role);
    if (role === null) return;
    const specialisation = window.prompt("Specialisation:", coworker.specialisation);
    if (specialisation === null) return;
    const system_instructions = window.prompt("Additional role instructions:", coworker.system_instructions);
    if (system_instructions === null) return;
    const capabilities = window.prompt(
      "Granted IRIS capability names (comma separated):",
      coworker.allowed_capabilities.join(", ")
    );
    if (capabilities === null) return;

    try {
      await api.patch(`/coworkers/${coworker.id}`, {
        name,
        role,
        specialisation,
        system_instructions,
        allowed_capabilities: capabilities.split(",").map((x) => x.trim()).filter(Boolean),
      });
      await handleRefreshCoworker();
    } catch (err) {
      alert("Failed to update coworker profile: " + String(err));
    }
  };

  const editResponsibilities = async () => {
    if (!coworker) return;
    const value = window.prompt("Responsibilities (one per line):", coworker.responsibilities.join("\n"));
    if (value === null) return;
    try {
      await api.patch(`/coworkers/${coworker.id}`, {
        responsibilities: value.split("\n").map((x) => x.trim()).filter(Boolean),
      });
      await handleRefreshCoworker();
    } catch (err) {
      alert("Failed to update responsibilities: " + String(err));
    }
  };

  if (loading) {
    return (
      <div className="mx-auto w-full max-w-5xl space-y-4 py-2">
        <div className="flex items-center gap-3">
          <div className="h-9 w-24 animate-pulse rounded-xl bg-ops-raised" />
          <div className="h-9 w-48 animate-pulse rounded-xl bg-ops-raised" />
        </div>
        <div className="h-[calc(100vh-160px)] min-h-[580px] w-full animate-pulse rounded-2xl bg-ops-raised" />
      </div>
    );
  }

  if (error || !coworker) {
    return (
      <div className="mx-auto w-full max-w-xl py-12 text-center">
        <div className="rounded-2xl border border-ops-line bg-ops-panel p-8 shadow-sm">
          <AlertCircle size={32} className="mx-auto text-amber-600 mb-3" />
          <h2 className="text-lg font-semibold text-ink">Coworker Not Found</h2>
          <p className="mt-1 text-sm text-ink-dim">
            {error || "The requested coworker does not exist or may have been deleted."}
          </p>
          <div className="mt-6 flex justify-center gap-3">
            <Button variant="outline" onClick={() => void loadData()}>
              <RefreshCw size={14} className="mr-1.5" /> Retry
            </Button>
            <Button onClick={() => navigate("/coworkers")}>
              <ArrowLeft size={14} className="mr-1.5" /> Back to Coworkers
            </Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-5xl flex-1 flex flex-col min-h-0">
      <CoworkerChatView
        coworker={coworker}
        projects={projects}
        activeProjectId={coworker.project_id}
        onSelectProject={handleUpdateProject}
        onRefreshCoworkers={handleRefreshCoworker}
        onRefreshProjects={handleRefreshProjects}
        onOpenSettings={() => setEditing((v) => !v)}
        onBack={() => navigate("/coworkers")}
      />

      {/* Coworker Profile & Settings Modal */}
      {editing && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4 animate-in fade-in duration-150">
          <div className="w-full max-w-xl rounded-2xl border border-ops-line bg-white p-6 shadow-xl max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between pb-3 border-b border-ops-line">
              <div>
                <h3 className="font-semibold text-ink">Coworker Profile & Governance</h3>
                <p className="text-xs text-ink-dim">
                  {coworker.name} · {coworker.role}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setEditing(false)}
                className="rounded-lg p-1 text-ink-dim hover:text-ink hover:bg-ops-ground transition cursor-pointer"
              >
                <X size={18} />
              </button>
            </div>

            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <div className="rounded-xl bg-ops-ground p-3">
                <p className="text-[11px] uppercase tracking-wider text-ink-faint">Availability</p>
                <p className="mt-1 text-sm font-medium text-ink">
                  {coworker.availability ? "Available" : "Unavailable"}
                </p>
              </div>
              <div className="rounded-xl bg-ops-ground p-3">
                <p className="text-[11px] uppercase tracking-wider text-ink-faint">Configuration</p>
                <p className="mt-1 text-sm font-medium text-ink">Version {coworker.config_version}</p>
              </div>
              <div className="rounded-xl bg-ops-ground p-3">
                <p className="text-[11px] uppercase tracking-wider text-ink-faint">Provider Preference</p>
                <p className="mt-1 text-sm font-medium text-ink">
                  {coworker.preferred_provider ?? "IRIS Default"}
                  {coworker.preferred_model ? ` · ${coworker.preferred_model}` : ""}
                </p>
              </div>
              <div className="rounded-xl bg-ops-ground p-3">
                <p className="text-[11px] uppercase tracking-wider text-ink-faint">Workspace Assignment</p>
                <p className="mt-1 text-sm font-medium text-ink">
                  {projects.find((p) => p.id === coworker.project_id)?.name ?? "None"}
                </p>
              </div>
            </div>

            <div className="mt-4 rounded-xl bg-ops-ground p-4">
              <label className="block text-xs font-medium text-ink-dim">Assigned project workspace</label>
              <select
                value={coworker.project_id ?? ""}
                onChange={(e) => handleUpdateProject(e.target.value ? Number(e.target.value) : null)}
                className="mt-1.5 w-full rounded-lg border border-ops-line bg-white p-2 text-sm text-ink outline-none"
              >
                <option value="">No project assigned</option>
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} · {p.directory}
                  </option>
                ))}
              </select>
              <p className="mt-1.5 text-xs text-ink-faint">
                Project permissions are enforced by the backend. Coworkers do not automatically receive write,
                command, or network access.
              </p>

              <div className="mt-4 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={editProfile}
                  className="rounded-lg border border-ops-line bg-white px-3 py-2 text-xs font-medium text-ink hover:bg-ops-surface transition cursor-pointer"
                >
                  Edit identity & capabilities
                </button>
                <button
                  type="button"
                  onClick={editResponsibilities}
                  className="rounded-lg border border-ops-line bg-white px-3 py-2 text-xs font-medium text-ink hover:bg-ops-surface transition cursor-pointer"
                >
                  Edit responsibilities
                </button>
              </div>

              <div className="mt-4 pt-3 border-t border-ops-line/60">
                <p className="text-xs text-ink-faint">
                  <span className="font-medium text-ink-dim">Granted capabilities:</span>{" "}
                  {coworker.allowed_capabilities.length ? coworker.allowed_capabilities.join(", ") : "none"}.
                </p>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
