import { useCallback, useEffect, useState } from "react";
import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clock,
  Code2,
  GitBranch,
  GitCommit,
  HardDrive,
  Info,
  Play,
  RotateCcw,
  Shield,
  Square,
  Terminal,
  Trash2,
  UploadCloud,
} from "lucide-react";
import { api } from "@/api/client";
import { Button } from "@/components/ui/Button";

type Project = {
  id: number;
  name: string;
  directory: string;
  read_access?: boolean;
  write_access?: boolean;
  command_access?: boolean;
  allowed_commands?: string[];
  allowed_domains?: string[];
  network_access?: boolean;
};

type Agent = {
  id: string;
  name: string;
  available: boolean;
  version?: string | null;
  authenticated?: boolean;
};

type CodingTask = {
  id: string;
  project_id: number;
  agent_id: string;
  instruction: string;
  status: string;
  approval_state: string;
  brief: {
    objective?: string;
    task_branch?: string;
    worktree_path?: string;
    base_commit?: string;
    original_branch?: string;
    acceptance_criteria?: string[];
    tests?: string[];
    constraints?: string[];
  };
  session_id?: string | null;
  result?: {
    status?: string;
    summary?: string;
    changed_files?: Array<{ path: string; status: string; uncommitted?: boolean }>;
    changed_files_reported_by_tools?: string[];
    task_commit?: string;
    diff_stat?: string;
    diff_summary?: string;
    error?: string;
  } | null;
  verification?: {
    independently_verified?: boolean;
    tests_observed?: string[];
    test_results?: string;
    note?: string;
  } | null;
  events?: Array<{ type: string; at?: string; [key: string]: unknown }>;
};

type DiffInfo = {
  isolated_worktree: boolean;
  branch?: string;
  base_commit?: string;
  current_commit?: string;
  stat?: string;
  diff?: string;
  changed_files: Array<{ path: string; status: string }>;
  has_uncommitted_changes?: boolean;
  total_files?: number;
};

interface CodingCoworkerWorkspaceProps {
  coworkerId: string;
  coworkerName: string;
  selectedProjectId: number | null;
  onProjectChange: (projectId: number | null) => void;
  projects: Project[];
}

export function CodingCoworkerWorkspace({
  coworkerId,
  coworkerName,
  selectedProjectId,
  onProjectChange,
  projects,
}: CodingCoworkerWorkspaceProps) {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [selectedAgent, setSelectedAgent] = useState<string>("antigravity-cli");
  const [tasks, setTasks] = useState<CodingTask[]>([]);
  const [activeTask, setActiveTask] = useState<CodingTask | null>(null);
  const [instruction, setInstruction] = useState("");
  const [followupPrompt, setFollowupPrompt] = useState("");
  const [commitMessage, setCommitMessage] = useState("");
  const [diffData, setDiffData] = useState<DiffInfo | null>(null);
  const [rawOutput, setRawOutput] = useState<string>("");
  const [showTechnicalDetails, setShowTechnicalDetails] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successNotice, setSuccessNotice] = useState<string | null>(null);

  // Load available coding agents
  const refreshAgents = useCallback(async () => {
    try {
      const data = await api.get<Agent[]>("/coding/agents");
      setAgents(data);
      if (data.length > 0 && !data.some((a) => a.id === selectedAgent)) {
        const preferred = data.find((a) => a.available) ?? data[0];
        setSelectedAgent(preferred.id);
      }
    } catch (err) {
      console.error("Failed to load coding engines:", err);
    }
  }, [selectedAgent]);

  // Load tasks for active project
  const refreshTasks = useCallback(async () => {
    try {
      const allTasks = await api.get<CodingTask[]>("/coding/execution/tasks");
      const filtered = selectedProjectId
        ? allTasks.filter((t) => t.project_id === selectedProjectId)
        : allTasks;
      setTasks(filtered);

      // Keep active task up-to-date
      if (activeTask) {
        const updated = filtered.find((t) => t.id === activeTask.id);
        if (updated) {
          setActiveTask(updated);
        }
      } else if (filtered.length > 0) {
        setActiveTask(filtered[0]);
      }
    } catch (err) {
      console.error("Failed to load tasks:", err);
    }
  }, [selectedProjectId, activeTask]);

  // Polling for active task session updates
  useEffect(() => {
    if (!activeTask) return;
    let cancelled = false;

    const pollSession = async () => {
      try {
        if (activeTask.session_id) {
          const sess = await api.get<{ session?: { recent_output?: string }; task?: CodingTask }>(
            `/coding/execution/tasks/${activeTask.id}/session`,
          );
          if (cancelled) return;
          if (sess.session?.recent_output) {
            setRawOutput(sess.session.recent_output);
          }
          if (sess.task) {
            setActiveTask(sess.task);
          }
        }

        // Fetch diff if worktree exists and status is completed or running
        if (
          activeTask.brief?.worktree_path ||
          activeTask.status === "completed" ||
          activeTask.status === "running"
        ) {
          const diffRes = await api.get<DiffInfo>(`/coding/execution/tasks/${activeTask.id}/diff`);
          if (cancelled) return;
          setDiffData(diffRes);
        }
      } catch (err) {
        // silent polling error
      }
    };

    void pollSession();
    const interval = window.setInterval(pollSession, 2500);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [activeTask?.id, activeTask?.session_id, activeTask?.status]);

  useEffect(() => {
    void refreshAgents();
    void refreshTasks();
  }, [refreshAgents, refreshTasks]);

  const activeProject = projects.find((p) => p.id === selectedProjectId) ?? null;

  // Plan a new task via Coding Coworker
  const handlePlanTask = async () => {
    if (!selectedProjectId || !instruction.trim()) return;
    setLoading(true);
    setError(null);
    setSuccessNotice(null);

    try {
      const criteria = [
        `Implement requested objective: ${instruction.trim()}`,
        "Execute strictly within isolated Git worktree",
        "Preserve existing repository state on primary branch",
      ];
      const brief = {
        objective: instruction.trim(),
        project_id: selectedProjectId,
        agent_id: selectedAgent,
        architecture:
          activeProject?.directory
            ? `Target workspace: ${activeProject.directory}. Inspect repository structure and conform to existing conventions.`
            : "Follow established repository architecture.",
        constraints: [
          "Execute strictly in assigned Git worktree.",
          "Never push to main, master, or original branch.",
          "Preserve existing user changes.",
        ],
        implementation: instruction.trim(),
        expected_behavior: "Fulfill objective with minimal, well-tested diff.",
        acceptance_criteria: criteria,
        tests: ["Run relevant test suites and report concrete outputs."],
        restrictions: ["Do not expose secrets.", "Do not modify files outside workspace."],
      };

      const created = await api.post<CodingTask>("/coding/execution/tasks", {
        project_id: selectedProjectId,
        agent_id: selectedAgent,
        instruction: instruction.trim(),
        brief,
      });

      setInstruction("");
      await refreshTasks();
      setActiveTask(created);
      setSuccessNotice("Implementation plan formulated. Review details and approve execution.");
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  };

  // Approve plan and launch agent in isolated worktree
  const handleApprove = async () => {
    if (!activeTask) return;
    setLoading(true);
    setError(null);
    setSuccessNotice(null);

    try {
      const promptText =
        activeTask.brief?.objective || activeTask.instruction;
      const approved = await api.post<CodingTask>(
        `/coding/execution/tasks/${activeTask.id}/approve`,
        { prompt: promptText },
      );
      setActiveTask(approved);
      await refreshTasks();
      setSuccessNotice("Isolated Git worktree created and coding engine launched!");
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  };

  // Follow-up prompt
  const handleFollowup = async () => {
    if (!activeTask || !followupPrompt.trim()) return;
    setLoading(true);
    setError(null);

    try {
      await api.post(`/coding/execution/tasks/${activeTask.id}/follow-up`, {
        prompt: followupPrompt.trim(),
      });
      setFollowupPrompt("");
      await refreshTasks();
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  };

  // Stop running session
  const handleStop = async () => {
    if (!activeTask) return;
    try {
      await api.post(`/coding/execution/tasks/${activeTask.id}/stop`);
      await refreshTasks();
    } catch (err) {
      setError(String(err));
    }
  };

  // Commit worktree changes
  const handleCommit = async () => {
    if (!activeTask || !commitMessage.trim()) return;
    setLoading(true);
    try {
      await api.post(`/coding/execution/tasks/${activeTask.id}/commit`, {
        message: commitMessage.trim(),
      });
      setCommitMessage("");
      setSuccessNotice("Worktree changes committed to task branch.");
      await refreshTasks();
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  };

  // Push branch to remote
  const handlePush = async () => {
    if (!activeTask) return;
    if (
      !window.confirm(
        `Push isolated branch '${activeTask.brief?.task_branch}' to remote origin?\n\nNote: Protected branches (main/master) are strictly protected by IRIS backend.`,
      )
    ) {
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await api.post<{ branch: string; remote: string }>(
        `/coding/execution/tasks/${activeTask.id}/push`,
        { remote: "origin" },
      );
      setSuccessNotice(`Successfully pushed branch '${res.branch}' to remote ${res.remote}.`);
      await refreshTasks();
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  };

  // Cleanup worktree
  const handleCleanup = async () => {
    if (!activeTask) return;
    if (!window.confirm("Remove isolated Git worktree directory from disk? The task branch ref will remain intact.")) {
      return;
    }
    setLoading(true);
    try {
      await api.post(`/coding/execution/tasks/${activeTask.id}/cleanup`, {
        delete_branch: false,
      });
      setSuccessNotice("Isolated worktree removed safely.");
      await refreshTasks();
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "awaiting_approval":
        return <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-700 ring-1 ring-amber-300"><Clock size={12} /> Plan Awaiting Approval</span>;
      case "running":
        return <span className="inline-flex items-center gap-1 rounded-full bg-blue-50 px-2.5 py-1 text-xs font-medium text-blue-700 ring-1 ring-blue-300 animate-pulse"><Play size={12} /> Agent Executing</span>;
      case "waiting_for_user":
        return <span className="inline-flex items-center gap-1 rounded-full bg-purple-50 px-2.5 py-1 text-xs font-medium text-purple-700 ring-1 ring-purple-300"><Info size={12} /> Awaiting User Feedback</span>;
      case "completed":
        return <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700 ring-1 ring-emerald-300"><CheckCircle2 size={12} /> Ready for Review</span>;
      case "failed":
        return <span className="inline-flex items-center gap-1 rounded-full bg-red-50 px-2.5 py-1 text-xs font-medium text-red-700 ring-1 ring-red-300"><AlertCircle size={12} /> Task Failed</span>;
      case "interrupted":
        return <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-700 ring-1 ring-amber-300"><RotateCcw size={12} /> Interrupted</span>;
      default:
        return <span className="inline-flex items-center gap-1 rounded-full bg-gray-50 px-2.5 py-1 text-xs font-medium text-gray-600 ring-1 ring-gray-300">{status}</span>;
    }
  };

  return (
    <div className="space-y-6">
      {/* Coworker Header */}
      <section className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-line bg-surface p-5 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-ink text-white shadow">
            <Code2 size={24} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-xl font-bold text-ink">{coworkerName}</h2>
              <span className="rounded-full bg-ai/10 px-2 py-0.5 text-xs font-medium text-ai">
                Coding Coworker
              </span>
              <span className="text-[10px] text-ink-faint">({coworkerId})</span>
            </div>
            <p className="text-xs text-ink-dim">
              Single point of interaction for development, plan formulation, and multi-agent coordination.
            </p>
          </div>
        </div>

        {/* Target Workspace & Engine Pickers */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-1.5 text-xs">
            <HardDrive size={14} className="text-ink-faint" />
            <select
              aria-label="Target Project Workspace"
              className="rounded-lg border border-line bg-surface px-2.5 py-1.5 text-xs font-medium text-ink shadow-sm outline-none focus:border-ai"
              value={selectedProjectId ?? ""}
              onChange={(e) => onProjectChange(e.target.value ? Number(e.target.value) : null)}
            >
              <option value="">Select Project Workspace</option>
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} ({p.directory})
                </option>
              ))}
            </select>
          </div>

          <div className="flex items-center gap-1.5 text-xs">
            <Terminal size={14} className="text-ink-faint" />
            <select
              aria-label="Coding Engine"
              className="rounded-lg border border-line bg-surface px-2.5 py-1.5 text-xs font-medium text-ink shadow-sm outline-none focus:border-ai"
              value={selectedAgent}
              onChange={(e) => setSelectedAgent(e.target.value)}
            >
              {agents.map((a) => (
                <option key={a.id} value={a.id} disabled={!a.available}>
                  {a.name} {a.available ? (a.version ? `(${a.version})` : "✓") : "(Unavailable)"}
                </option>
              ))}
            </select>
          </div>
        </div>
      </section>

      {/* Notifications */}
      {error && (
        <div role="alert" className="flex items-center gap-2 rounded-xl border border-red-200 bg-red-50 p-3.5 text-sm text-red-800">
          <AlertCircle size={16} className="shrink-0" />
          <span>{error}</span>
        </div>
      )}
      {successNotice && (
        <div role="status" className="flex items-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50 p-3.5 text-sm text-emerald-800">
          <CheckCircle2 size={16} className="shrink-0" />
          <span>{successNotice}</span>
        </div>
      )}

      {/* Main Grid: Left Task Stream & Active Task Details */}
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.75fr)_minmax(280px,1fr)]">
        {/* Main Column */}
        <div className="space-y-6">
          {/* Active Task Details & Approval Card */}
          {activeTask ? (
            <article className="space-y-5 rounded-2xl border border-line bg-surface p-5 shadow-sm">
              <div className="flex flex-wrap items-start justify-between gap-2 border-b border-line pb-4">
                <div>
                  <p className="text-xs font-medium uppercase tracking-wider text-ink-faint">
                    Active Development Task
                  </p>
                  <h3 className="mt-1 text-lg font-bold text-ink">{activeTask.instruction}</h3>
                </div>
                <div>{getStatusBadge(activeTask.status)}</div>
              </div>

              {/* Worktree & Branch Isolation Badge */}
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="flex items-start gap-2.5 rounded-xl bg-ops-panel p-3">
                  <GitBranch size={16} className="mt-0.5 text-ai shrink-0" />
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-semibold text-ink">Isolated Task Branch</p>
                    <p className="truncate font-mono text-xs text-ink-dim" title={activeTask.brief?.task_branch || "iris/task/pending"}>
                      {activeTask.brief?.task_branch || "iris/task/pending"}
                    </p>
                    <p className="mt-1 text-[11px] text-ink-faint">
                      Base: <span className="font-mono">{activeTask.brief?.base_commit?.slice(0, 8) || "HEAD"}</span> · Protected branches safe
                    </p>
                  </div>
                </div>

                <div className="flex items-start gap-2.5 rounded-xl bg-ops-panel p-3">
                  <Shield size={16} className="mt-0.5 text-emerald-600 shrink-0" />
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-semibold text-ink">Git Worktree Isolation</p>
                    <p className="truncate font-mono text-xs text-ink-dim" title={activeTask.brief?.worktree_path || "Created on plan approval"}>
                      {activeTask.brief?.worktree_path ? ".iris_worktrees/..." : "Created on plan approval"}
                    </p>
                    <p className="mt-1 text-[11px] text-ink-faint">
                      Primary user working tree remains untouched
                    </p>
                  </div>
                </div>
              </div>

              {/* Implementation Plan Details */}
              {activeTask.brief?.acceptance_criteria && (
                <div className="rounded-xl border border-line/70 bg-ops-panel/50 p-4">
                  <h4 className="text-xs font-semibold uppercase tracking-wider text-ink-faint">
                    Acceptance Criteria & Plan
                  </h4>
                  <ul className="mt-2 space-y-1.5 text-xs text-ink">
                    {activeTask.brief.acceptance_criteria.map((item, idx) => (
                      <li key={idx} className="flex items-start gap-2">
                        <CheckCircle2 size={13} className="mt-0.5 text-ai shrink-0" />
                        <span>{item}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Plan Approval Banner */}
              {activeTask.status === "awaiting_approval" && (
                <div className="rounded-xl border border-amber-200 bg-amber-50/70 p-4">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <h4 className="text-sm font-semibold text-amber-900">
                        Human Governance Approval Required
                      </h4>
                      <p className="mt-1 text-xs text-amber-800">
                        Approve execution to create the isolated Git worktree and launch {activeTask.agent_id}. No files will be modified on your active branch.
                      </p>
                    </div>
                    <Button onClick={handleApprove} disabled={loading} className="bg-ink hover:bg-ink/90 text-white font-medium text-xs px-4 py-2">
                      Approve Plan & Launch Engine
                    </Button>
                  </div>
                </div>
              )}

              {/* Live Event Milestones */}
              {activeTask.events && activeTask.events.length > 0 && (
                <div className="space-y-2">
                  <h4 className="text-xs font-semibold uppercase tracking-wider text-ink-faint">
                    Execution Milestones
                  </h4>
                  <div className="space-y-1.5 max-h-48 overflow-y-auto">
                    {activeTask.events.slice(-6).map((ev, i) => (
                      <div key={i} className="flex items-center gap-2 text-xs rounded-lg bg-ops-panel px-3 py-1.5 text-ink-dim">
                        <span className="h-1.5 w-1.5 rounded-full bg-ai shrink-0" />
                        <span className="font-medium text-ink capitalize">
                          {ev.type.replaceAll("_", " ")}
                        </span>
                        {ev.at && (
                          <span className="ml-auto text-[10px] text-ink-faint">
                            {new Date(ev.at).toLocaleTimeString()}
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Result & Diff Summary */}
              {diffData && diffData.changed_files?.length > 0 && (
                <div className="space-y-3 rounded-xl border border-line bg-surface p-4">
                  <div className="flex items-center justify-between">
                    <h4 className="text-xs font-semibold uppercase tracking-wider text-ink-faint">
                      Changed Files ({diffData.changed_files.length})
                    </h4>
                    <span className="font-mono text-xs text-ink-dim">
                      {diffData.stat?.split("\n").pop() || ""}
                    </span>
                  </div>
                  <div className="grid gap-1.5">
                    {diffData.changed_files.map((file, i) => (
                      <div key={i} className="flex items-center justify-between rounded-lg bg-ops-panel px-3 py-1.5 text-xs font-mono">
                        <span className="truncate">{file.path}</span>
                        <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${file.status === "A" ? "bg-emerald-100 text-emerald-800" : "bg-blue-100 text-blue-800"}`}>
                          {file.status}
                        </span>
                      </div>
                    ))}
                  </div>

                  {/* Actions for Completed Task */}
                  <div className="flex flex-wrap gap-2 pt-2 border-t border-line">
                    <Button variant="outline" onClick={handleCommit} disabled={loading} className="text-xs">
                      <GitCommit size={14} className="mr-1" /> Commit to Task Branch
                    </Button>
                    <Button variant="outline" onClick={handlePush} disabled={loading} className="text-xs text-ai border-ai/40 hover:bg-ai/10">
                      <UploadCloud size={14} className="mr-1" /> Push Isolated Branch
                    </Button>
                    <Button variant="ghost" onClick={handleCleanup} disabled={loading} className="text-xs text-red-600 hover:bg-red-50">
                      <Trash2 size={14} className="mr-1" /> Remove Worktree
                    </Button>
                  </div>
                </div>
              )}

              {/* Follow-up / Additional Instructions Bar */}
              {["running", "waiting_for_user", "completed"].includes(activeTask.status) && (
                <div className="flex gap-2 pt-2">
                  <input
                    aria-label="Follow-up guidance"
                    className="min-w-0 flex-1 rounded-xl border border-line px-3.5 py-2 text-xs outline-none focus:border-ai"
                    placeholder={
                      activeTask.status === "waiting_for_user"
                        ? "Answer agent question or resolve permission..."
                        : "Send follow-up instruction to coding coworker..."
                    }
                    value={followupPrompt}
                    onChange={(e) => setFollowupPrompt(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && void handleFollowup()}
                  />
                  <Button onClick={handleFollowup} disabled={!followupPrompt.trim() || loading} className="text-xs">
                    Send
                  </Button>
                  {activeTask.status === "running" && (
                    <Button variant="outline" onClick={handleStop} className="text-xs text-red-600">
                      <Square size={13} className="mr-1" /> Stop
                    </Button>
                  )}
                </div>
              )}

              {/* Technical Details Toggle */}
              <div className="border-t border-line pt-3">
                <button
                  onClick={() => setShowTechnicalDetails((v) => !v)}
                  className="flex items-center gap-1.5 text-xs text-ink-dim hover:text-ink cursor-pointer"
                >
                  <Terminal size={13} />
                  <span>Technical Diagnostics & Raw Output</span>
                  {showTechnicalDetails ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                </button>
                {showTechnicalDetails && (
                  <div className="mt-3 space-y-2">
                    <pre className="max-h-60 overflow-auto whitespace-pre-wrap rounded-xl bg-[#0B0D13] p-4 font-mono text-xs text-gray-200">
                      {rawOutput || "No process output captured yet."}
                    </pre>
                  </div>
                )}
              </div>
            </article>
          ) : (
            <div className="rounded-2xl border border-dashed border-line bg-surface p-8 text-center text-ink-dim">
              <Code2 size={36} className="mx-auto text-ink-faint" />
              <h3 className="mt-3 font-semibold text-ink">Ready to Code</h3>
              <p className="mt-1 text-xs">
                Select a workspace and describe what you want built. The Coding Coworker will create a structured plan and execute it safely in an isolated branch.
              </p>
            </div>
          )}

          {/* Natural Language Task Composer */}
          <section className="space-y-3 rounded-2xl border border-line bg-surface p-5 shadow-sm">
            <h3 className="text-sm font-semibold text-ink">Describe Development Task</h3>
            <textarea
              aria-label="Development Task Description"
              rows={3}
              className="w-full resize-none rounded-xl border border-line p-3 text-sm outline-none focus:border-ai placeholder:text-ink-faint"
              placeholder="e.g. Add an authentication notification drawer, fix the bug in finance calculator, or implement a responsive layout..."
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
            />
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex flex-wrap gap-1.5 text-xs">
                <button
                  type="button"
                  onClick={() => setInstruction("Add unit tests for recent changes")}
                  className="rounded-lg bg-ops-panel px-2.5 py-1 text-ink-dim hover:text-ink hover:bg-ops-raised"
                >
                  + Add unit tests
                </button>
                <button
                  type="button"
                  onClick={() => setInstruction("Refactor component to TypeScript")}
                  className="rounded-lg bg-ops-panel px-2.5 py-1 text-ink-dim hover:text-ink hover:bg-ops-raised"
                >
                  + Refactor to TS
                </button>
                <button
                  type="button"
                  onClick={() => setInstruction("Fix reported runtime exception")}
                  className="rounded-lg bg-ops-panel px-2.5 py-1 text-ink-dim hover:text-ink hover:bg-ops-raised"
                >
                  + Fix exception
                </button>
              </div>

              <Button
                onClick={handlePlanTask}
                disabled={!selectedProjectId || instruction.trim().length < 3 || loading}
                className="bg-ink hover:bg-ink/90 text-white font-medium text-xs px-4 py-2"
              >
                Formulate Implementation Plan <ArrowRight size={14} className="ml-1" />
              </Button>
            </div>
          </section>
        </div>

        {/* Right Sidebar: Task History & Project Status */}
        <aside className="space-y-4">
          <div className="rounded-2xl border border-line bg-surface p-4 shadow-sm">
            <h4 className="text-xs font-semibold uppercase tracking-wider text-ink-faint">
              Recent Coding Tasks ({tasks.length})
            </h4>
            <div className="mt-3 space-y-2 max-h-[600px] overflow-y-auto">
              {tasks.map((t) => (
                <button
                  key={t.id}
                  onClick={() => setActiveTask(t)}
                  className={`w-full rounded-xl border p-3 text-left transition cursor-pointer ${
                    activeTask?.id === t.id
                      ? "border-ai bg-ai/5 shadow-sm"
                      : "border-line bg-surface hover:bg-ops-panel"
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <span className="line-clamp-2 text-xs font-semibold text-ink">
                      {t.instruction}
                    </span>
                  </div>
                  <div className="mt-2 flex items-center justify-between text-[11px] text-ink-faint">
                    <span className="font-mono truncate max-w-[120px]">
                      {t.brief?.task_branch ? t.brief.task_branch.replace("iris/task/", "") : "plan"}
                    </span>
                    <span className="capitalize">{t.status.replaceAll("_", " ")}</span>
                  </div>
                </button>
              ))}
              {tasks.length === 0 && (
                <p className="p-4 text-center text-xs text-ink-faint">No tasks in this workspace yet.</p>
              )}
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
