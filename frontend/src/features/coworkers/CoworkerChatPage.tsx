import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { AlertCircle, ArrowLeft, Check, RefreshCw, X } from "lucide-react";
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

  // Form edit states
  const [editName, setEditName] = useState("");
  const [editRole, setEditRole] = useState("");
  const [editSpec, setEditSpec] = useState("");
  const [editInstructions, setEditInstructions] = useState("");
  const [editCapabilities, setEditCapabilities] = useState("");
  const [editResponsibilities, setEditResponsibilities] = useState("");
  const [isSavingProfile, setIsSavingProfile] = useState(false);
  const [profileSaveSuccess, setProfileSaveSuccess] = useState(false);

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

  useEffect(() => {
    if (coworker && editing) {
      setEditName(coworker.name);
      setEditRole(coworker.role);
      setEditSpec(coworker.specialisation);
      setEditInstructions(coworker.system_instructions || "");
      setEditCapabilities(coworker.allowed_capabilities.join(", "));
      setEditResponsibilities(coworker.responsibilities.join("\n"));
      setProfileSaveSuccess(false);
    }
  }, [coworker, editing]);

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

  const handleSaveProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!coworker || isSavingProfile) return;
    setIsSavingProfile(true);
    try {
      await api.patch(`/coworkers/${coworker.id}`, {
        name: editName.trim(),
        role: editRole.trim(),
        specialisation: editSpec.trim(),
        system_instructions: editInstructions.trim(),
        allowed_capabilities: editCapabilities.split(",").map((x) => x.trim()).filter(Boolean),
        responsibilities: editResponsibilities.split("\n").map((x) => x.trim()).filter(Boolean),
      });
      await handleRefreshCoworker();
      setProfileSaveSuccess(true);
      setTimeout(() => setProfileSaveSuccess(false), 2500);
    } catch (err) {
      console.error("Failed to update profile:", err);
    } finally {
      setIsSavingProfile(false);
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
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-xs p-4 animate-in fade-in duration-150">
          <div className="w-full max-w-xl rounded-2xl border border-ops-line bg-ops-ground p-6 shadow-2xl max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between pb-3 border-b border-ops-line">
              <div>
                <h3 className="text-base font-semibold text-ink">Coworker Profile & Settings</h3>
                <p className="text-xs text-ink-dim">
                  {coworker.name} · {coworker.role}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setEditing(false)}
                className="rounded-lg p-1 text-ink-faint hover:text-ink hover:bg-ops-raised transition cursor-pointer"
                aria-label="Close"
              >
                <X size={18} />
              </button>
            </div>

            {/* Quick Status Cards */}
            <div className="mt-4 grid gap-2.5 sm:grid-cols-2 text-xs">
              <div className="rounded-xl border border-ops-line bg-ops-panel p-3">
                <span className="text-[11px] uppercase tracking-wider text-ink-faint">Availability</span>
                <p className="mt-0.5 text-sm font-semibold text-ink">
                  {coworker.availability ? "🟢 Active & Available" : "⚪ Offline"}
                </p>
              </div>
              <div className="rounded-xl border border-ops-line bg-ops-panel p-3">
                <span className="text-[11px] uppercase tracking-wider text-ink-faint">Assigned Codebase</span>
                <p className="mt-0.5 text-sm font-semibold text-ink truncate">
                  {projects.find((p) => p.id === coworker.project_id)?.name ?? "None (Global)"}
                </p>
              </div>
            </div>

            {/* Project Workspace Selector */}
            <div className="mt-4 rounded-xl border border-ops-line bg-ops-panel p-3.5 space-y-2">
              <label className="block text-xs font-semibold text-ink">Assigned Project Workspace</label>
              <select
                value={coworker.project_id ?? ""}
                onChange={(e) => handleUpdateProject(e.target.value ? Number(e.target.value) : null)}
                className="w-full rounded-lg border border-ops-line bg-ops-ground p-2 text-xs text-ink outline-none focus:border-ai transition"
              >
                <option value="">No project assigned</option>
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} · {p.directory}
                  </option>
                ))}
              </select>
            </div>

            {/* Profile Edit Form */}
            <form onSubmit={handleSaveProfile} className="mt-4 space-y-3.5 border-t border-ops-line pt-4">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-ink mb-1">Name</label>
                  <input
                    type="text"
                    required
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                    className="w-full rounded-lg border border-ops-line bg-ops-ground px-3 py-1.5 text-xs text-ink outline-none focus:border-ai transition"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-ink mb-1">Role Title</label>
                  <input
                    type="text"
                    required
                    value={editRole}
                    onChange={(e) => setEditRole(e.target.value)}
                    className="w-full rounded-lg border border-ops-line bg-ops-ground px-3 py-1.5 text-xs text-ink outline-none focus:border-ai transition"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-ink mb-1">Specialisation</label>
                <input
                  type="text"
                  value={editSpec}
                  onChange={(e) => setEditSpec(e.target.value)}
                  className="w-full rounded-lg border border-ops-line bg-ops-ground px-3 py-1.5 text-xs text-ink outline-none focus:border-ai transition"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-ink mb-1">System Instructions</label>
                <textarea
                  rows={3}
                  value={editInstructions}
                  onChange={(e) => setEditInstructions(e.target.value)}
                  className="w-full rounded-lg border border-ops-line bg-ops-ground p-2 text-xs text-ink outline-none focus:border-ai transition resize-none font-mono"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-ink mb-1">Allowed Capabilities (comma-separated)</label>
                <input
                  type="text"
                  value={editCapabilities}
                  onChange={(e) => setEditCapabilities(e.target.value)}
                  placeholder="e.g. workspace_read, workspace_write, web_search"
                  className="w-full rounded-lg border border-ops-line bg-ops-ground px-3 py-1.5 text-xs text-ink outline-none focus:border-ai transition font-mono"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-ink mb-1">Responsibilities (one per line)</label>
                <textarea
                  rows={3}
                  value={editResponsibilities}
                  onChange={(e) => setEditResponsibilities(e.target.value)}
                  className="w-full rounded-lg border border-ops-line bg-ops-ground p-2 text-xs text-ink outline-none focus:border-ai transition resize-none"
                />
              </div>

              <div className="flex items-center justify-between pt-2">
                {profileSaveSuccess ? (
                  <span className="flex items-center gap-1.5 text-xs font-medium text-go">
                    <Check size={14} /> Profile updated successfully!
                  </span>
                ) : <span />}

                <div className="flex gap-2">
                  <Button type="button" variant="ghost" size="sm" onClick={() => setEditing(false)}>
                    Close
                  </Button>
                  <Button type="submit" size="sm" disabled={isSavingProfile}>
                    {isSavingProfile ? "Saving…" : "Save Changes"}
                  </Button>
                </div>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
