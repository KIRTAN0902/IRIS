import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertCircle,
  ArrowLeft,
  ArrowUp,
  ChevronDown,
  ChevronUp,
  Cloud,
  Code2,
  FolderPlus,
  GitBranch,
  GitCommit,
  HardDrive,
  LineChart,
  ListChecks,
  Mic,
  MicOff,
  PenTool,
  RefreshCw,
  Search,
  Settings,
  SlidersHorizontal,
  Square,
  Terminal,
  UploadCloud,
  Zap,
} from "lucide-react";
import { api } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { Markdown } from "@/components/ui/Markdown";

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
};

export type RemoteWorkspace = {
  id: string;
  name: string;
  repo_url: string;
  branch: string;
  task_branch?: string | null;
  status: string;
  storage_type: string;
  engine_name: string;
  last_commit_sha?: string | null;
  uncommitted_patch?: string | null;
  companion_url?: string | null;
};

export type Project = {
  id: number;
  name: string;
  directory: string;
  is_active?: boolean;
  read_access?: boolean;
  write_access?: boolean;
  command_access?: boolean;
  allowed_commands?: string[];
  allowed_domains?: string[];
  network_access?: boolean;
};

export type MessageEvent = {
  id: number;
  type: string;
  payload: Record<string, unknown>;
  created_at: string;
};

export type MessageTurn = {
  id: string;
  role: "user" | "coworker";
  content: string;
  error?: string | null;
  status?: string;
  created_at?: string | null;
  ended_at?: string | null;
  task_id?: string;
  coding_task_id?: string | null;
  project_id?: number | null;
  remote_workspace_id?: string | null;
  task_branch?: string | null;
  agent_id?: string | null;
  worktree_path?: string | null;
  diff?: {
    changed_files: Array<{ path: string; status: string }>;
    stat?: string;
    diff?: string;
    total_files?: number;
  } | null;
  result?: Record<string, unknown> | null;
  verification?: Record<string, unknown> | null;
  events?: MessageEvent[];
};

interface CoworkerChatViewProps {
  coworker: Coworker;
  projects: Project[];
  activeProjectId: number | null;
  onSelectProject: (projectId: number | null) => void;
  onRefreshCoworkers: () => Promise<void>;
  onRefreshProjects: () => Promise<void>;
  onOpenSettings: () => void;
  onBack?: () => void;
}

export function CoworkerChatView({
  coworker,
  projects,
  activeProjectId,
  onSelectProject,
  onRefreshCoworkers,
  onRefreshProjects,
  onOpenSettings,
  onBack,
}: CoworkerChatViewProps) {
  const [messages, setMessages] = useState<MessageTurn[]>([]);
  const [inputText, setInputText] = useState("");
  const [selectedEngine, setSelectedEngine] = useState<string>("antigravity-cli");
  const [loading, setLoading] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [expandedTechnical, setExpandedTechnical] = useState<Record<string, boolean>>({});
  const [expandedDiff, setExpandedDiff] = useState<Record<string, boolean>>({});
  const [showWorkspaceModal, setShowWorkspaceModal] = useState(false);
  const [newWsName, setNewWsName] = useState("IRIS");
  const [newWsDir, setNewWsDir] = useState("C:\\kirtan\\IRIS");
  const [isRecording, setIsRecording] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  // Milestone H & UX Normalisation: Default to Remote Cloud Execution
  const [remoteWorkspaces, setRemoteWorkspaces] = useState<RemoteWorkspace[]>([]);
  const [selectedRemoteWorkspaceId, setSelectedRemoteWorkspaceId] = useState<string | null>(null);
  const [executionTarget, setExecutionTarget] = useState<"local" | "remote">("remote");
  const [showRemoteModal, setShowRemoteModal] = useState(false);
  const [showProjectDropdown, setShowProjectDropdown] = useState(false);
  const [showDiagnosticsModal, setShowDiagnosticsModal] = useState(false);
  const [newRemoteName, setNewRemoteName] = useState("IRIS Cloud Sandbox");
  const [newRemoteRepo, setNewRemoteRepo] = useState("https://github.com/KIRTAN0902/IRIS.git");
  const [newRemoteBranch, setNewRemoteBranch] = useState("main");
  const [newRemoteCompanionUrl, setNewRemoteCompanionUrl] = useState("");
  const [recoveringWs, setRecoveringWs] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const recognitionRef = useRef<any>(null);

  const fetchRemoteWorkspaces = useCallback(async () => {
    try {
      const wsList = await api.get<RemoteWorkspace[]>("/workspaces");
      setRemoteWorkspaces(wsList);
      if (wsList.length > 0 && !selectedRemoteWorkspaceId) {
        setSelectedRemoteWorkspaceId(wsList[0].id);
      }
    } catch {
      // Offline or local-only fallback
    }
  }, [selectedRemoteWorkspaceId]);

  useEffect(() => {
    void fetchRemoteWorkspaces();
  }, [fetchRemoteWorkspaces]);

  const isCodingCoworker = useMemo(() => {
    const role = (coworker.role || "").toLowerCase();
    return role.includes("coding") || role === "developer" || role === "software developer";
  }, [coworker.role]);

  const activeProject = useMemo(() => {
    return projects.find((p) => p.id === activeProjectId) ?? null;
  }, [projects, activeProjectId]);

  const composerPlaceholder = useMemo(() => {
    const role = (coworker.role || "").toLowerCase();
    const spec = (coworker.specialisation || "").toLowerCase();
    if (role.includes("dev") || role.includes("cod") || spec.includes("software")) {
      return activeProject
        ? `Ask ${coworker.name} to build, debug or improve something in ${activeProject.name}...`
        : `Ask ${coworker.name} to build, debug or improve something...`;
    }
    if (role.includes("research") || spec.includes("research")) {
      return `Ask ${coworker.name} to investigate something...`;
    }
    if (role.includes("analy") || spec.includes("data") || spec.includes("analy")) {
      return `Ask ${coworker.name} to analyse your data...`;
    }
    if (role.includes("scribe") || role.includes("writer") || spec.includes("writ") || spec.includes("doc")) {
      return `Ask ${coworker.name} to write or organise something...`;
    }
    if (role.includes("manager") || role.includes("lead") || spec.includes("plan")) {
      return `Ask ${coworker.name} to plan or coordinate tasks...`;
    }
    return `Ask ${coworker.name} to help with something...`;
  }, [coworker.name, coworker.role, coworker.specialisation, activeProject]);

  // Determine if there is an active running turn
  const activeRunningTurn = useMemo(() => {
    return messages.find((m) => m.role === "coworker" && ["running", "working", "queued"].includes(m.status || ""));
  }, [messages]);

  // Timer for active running turn
  useEffect(() => {
    let timer: number | undefined;
    if (activeRunningTurn) {
      timer = window.setInterval(() => {
        setElapsedSeconds((s) => s + 1);
      }, 1000);
    } else {
      setElapsedSeconds(0);
    }
    return () => {
      if (timer) clearInterval(timer);
    };
  }, [activeRunningTurn]);

  // Fetch messages from backend
  const fetchMessages = useCallback(async () => {
    try {
      const data = await api.get<MessageTurn[]>(`/coworkers/${coworker.id}/messages`);
      setMessages(data);
    } catch (err) {
      console.error("Failed to load coworker messages:", err);
    }
  }, [coworker.id]);

  useEffect(() => {
    void fetchMessages();
  }, [fetchMessages]);

  // Polling while active task is running or coworker is working
  useEffect(() => {
    const isBusy = activeRunningTurn || ["working", "running", "assigned"].includes(coworker.status);
    if (!isBusy) return;

    const interval = window.setInterval(() => {
      void fetchMessages();
      void onRefreshCoworkers();
    }, 2000);

    return () => window.clearInterval(interval);
  }, [activeRunningTurn, coworker.status, fetchMessages, onRefreshCoworkers]);

  // Auto-scroll to bottom
  const scrollToBottom = (smooth = true) => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: smooth ? "smooth" : "auto" });
    }
  };

  useEffect(() => {
    scrollToBottom(false);
  }, [coworker.id]);

  useEffect(() => {
    scrollToBottom(true);
  }, [messages.length, activeRunningTurn?.status]);

  // Send natural language message
  const handleSendMessage = async (textToSend?: string) => {
    const text = (textToSend || inputText).trim();
    if (!text || loading) return;

    setLoading(true);
    setInputText("");

    // Optimistically add user turn
    const tempUserTurn: MessageTurn = {
      id: `opt-${Date.now()}`,
      role: "user",
      content: text,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, tempUserTurn]);

    try {
      await api.post(`/coworkers/${coworker.id}/chat`, {
        message: text,
        project_id: activeProjectId,
        workspace_id: executionTarget === "remote" ? selectedRemoteWorkspaceId : undefined,
        engine: isCodingCoworker ? selectedEngine : undefined,
      });
      await fetchMessages();
      await onRefreshCoworkers();
    } catch (err: any) {
      console.error("Chat dispatch error:", err);
      // Re-fetch to synchronize state
      await fetchMessages();
    } finally {
      setLoading(false);
    }
  };

  // Immediate Stop execution handler
  const handleStopExecution = async () => {
    setStopping(true);
    try {
      await api.post(`/coworkers/${coworker.id}/stop`);
      await fetchMessages();
      await onRefreshCoworkers();
    } catch (err) {
      console.error("Failed to stop execution:", err);
    } finally {
      setStopping(false);
    }
  };

  // Commit worktree changes to task branch
  const handleCommitWorktree = async (codingTaskId: string) => {
    const msg = window.prompt("Commit message for task branch:", "feat: implement requested changes");
    if (!msg?.trim()) return;
    try {
      await api.post(`/coding/execution/tasks/${codingTaskId}/commit`, { message: msg.trim() });
      await fetchMessages();
      alert("Changes committed to task branch.");
    } catch (err: any) {
      alert(`Commit failed: ${err.message || err}`);
    }
  };

  // Push task branch to remote
  const handlePushBranch = async (codingTaskId: string) => {
    if (!window.confirm("Push isolated task branch to origin remote? (Protected branches remain untouched)")) return;
    try {
      await api.post(`/coding/execution/tasks/${codingTaskId}/push`, { remote: "origin" });
      await fetchMessages();
      alert("Branch pushed to origin remote.");
    } catch (err: any) {
      alert(`Push failed: ${err.message || err}`);
    }
  };

  // Milestone H: Create persistent remote workspace linked to GitHub
  const handleCreateRemoteWorkspace = async () => {
    if (!newRemoteRepo.trim()) return;
    try {
      const res = await api.post<RemoteWorkspace>("/workspaces", {
        name: newRemoteName.trim(),
        repo_url: newRemoteRepo.trim(),
        branch: newRemoteBranch.trim(),
        project_id: activeProjectId,
        companion_url: newRemoteCompanionUrl.trim() || undefined,
      });
      setShowRemoteModal(false);
      setNewRemoteCompanionUrl("");
      await fetchRemoteWorkspaces();
      setSelectedRemoteWorkspaceId(res.id);
      setExecutionTarget("remote");
      alert(`Remote workspace "${res.name}" connected.`);
    } catch (err: any) {
      alert(`Failed to create remote workspace: ${err.message || err}`);
    }
  };

  // Milestone H: Update companion URL (e.g. from Google Colab)
  const handleUpdateCompanionUrl = async (workspaceId: string) => {
    const ws = remoteWorkspaces.find((w) => w.id === workspaceId);
    const currentUrl = ws?.companion_url || "";
    const newUrl = window.prompt(
      "Enter new Companion URL (e.g. from Google Colab https://xxxx.trycloudflare.com):",
      currentUrl
    );
    if (newUrl === null) return;
    try {
      await api.patch(`/workspaces/${workspaceId}`, {
        companion_url: newUrl.trim() || null,
      });
      await fetchRemoteWorkspaces();
      alert("Companion URL updated successfully!");
    } catch (err: any) {
      alert(`Failed to update URL: ${err.message || err}`);
    }
  };

  // Milestone H: Recover sleeping/interrupted remote workspace
  const handleRecoverRemoteWorkspace = async (workspaceId: string) => {
    setRecoveringWs(true);
    try {
      await api.post(`/workspaces/${workspaceId}/recover`);
      await fetchRemoteWorkspaces();
      await fetchMessages();
      alert("Remote workspace recovered successfully from GitHub + checkpointed patch.");
    } catch (err: any) {
      alert(`Recovery failed: ${err.message || err}`);
    } finally {
      setRecoveringWs(false);
    }
  };

  // Milestone H: Commit changes to remote task branch
  const handleCommitRemote = async (workspaceId: string) => {
    const msg = window.prompt("Commit message for remote task branch:", "feat: implement requested changes");
    if (!msg?.trim()) return;
    try {
      await api.post(`/workspaces/${workspaceId}/commit`, { message: msg.trim() });
      await fetchMessages();
      await fetchRemoteWorkspaces();
      alert("Changes committed to remote task branch.");
    } catch (err: any) {
      alert(`Commit failed: ${err.message || err}`);
    }
  };

  // Milestone H: Push remote task branch to GitHub
  const handlePushRemote = async (workspaceId: string, branch: string) => {
    const pat = window.prompt("Enter GitHub Personal Access Token (PAT) for push approval:\n(Token is used for this request only and never stored in logs)", "");
    if (!pat?.trim()) return;
    try {
      await api.post(`/workspaces/${workspaceId}/push`, { branch, github_pat: pat.trim() });
      await fetchMessages();
      await fetchRemoteWorkspaces();
      alert(`Branch ${branch} pushed to GitHub successfully!`);
    } catch (err: any) {
      alert(`Push failed: ${err.message || err}`);
    }
  };

  // Register new project workspace inline
  const handleRegisterWorkspace = async () => {
    if (!newWsName.trim() || !newWsDir.trim()) return;
    try {
      const res = await api.post<Project>("/coding/projects", {
        name: newWsName.trim(),
        directory: newWsDir.trim(),
        aliases: [newWsName.toLowerCase(), "repo"],
      });
      await api.patch(`/coding/projects/${res.id}`, {
        write_access: true,
        command_access: true,
        allowed_commands: ["command(git)", "command(pytest)", "command(npm)"],
        is_active: true,
      });
      setShowWorkspaceModal(false);
      await onRefreshProjects();
      onSelectProject(res.id);
    } catch (err: any) {
      alert(`Failed to register workspace: ${err.message || err}`);
    }
  };

  // Save coworker recommendation or deliverable as a trackable IRIS Task
  const handleSaveAsTask = async (turn: MessageTurn) => {
    try {
      const firstLine = turn.content.split("\n")[0].replace(/^#+\s*/, "").slice(0, 100);
      const title = firstLine || `Follow-up from ${coworker.name}`;
      await api.post("/tasks", {
        title,
        description: turn.content.slice(0, 500),
        area: "STARTUP",
      });
      alert(`✨ Task "${title}" created in Tasks & Priorities!`);
    } catch (err: any) {
      alert(`Could not create task: ${err.message || err}`);
    }
  };

  // Speech Recognition dictation
  const toggleSpeechRecognition = () => {
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) {
      alert("Speech recognition is not supported in this browser. Please type your message.");
      return;
    }

    if (isRecording) {
      recognitionRef.current?.stop();
      setIsRecording(false);
      return;
    }

    try {
      const recognition = new SpeechRecognition();
      recognition.continuous = false;
      recognition.interimResults = false;
      recognition.lang = "en-US";

      recognition.onstart = () => setIsRecording(true);
      recognition.onend = () => setIsRecording(false);
      recognition.onerror = () => setIsRecording(false);
      recognition.onresult = (event: any) => {
        const transcript = event.results[0][0].transcript;
        if (transcript) {
          setInputText((prev) => (prev ? `${prev} ${transcript}` : transcript));
        }
      };

      recognitionRef.current = recognition;
      recognition.start();
    } catch (err) {
      console.error("Speech recognition error:", err);
      setIsRecording(false);
    }
  };

  // Render role icon
  const getRoleIcon = () => {
    const role = (coworker.role || "").toLowerCase();
    if (role.includes("coding") || role === "developer") return <Code2 size={18} />;
    if (role.includes("research")) return <Search size={18} />;
    if (role.includes("analyst")) return <LineChart size={18} />;
    if (role.includes("writer")) return <PenTool size={18} />;
    return <Zap size={18} />;
  };

  // Format seconds to mm:ss
  const formatTimer = (secs: number) => {
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    return `${m}:${s < 10 ? "0" : ""}${s}`;
  };

  return (
    <div className="flex flex-col h-[calc(100vh-140px)] min-h-[580px] rounded-2xl border border-ops-line bg-ops-panel overflow-hidden shadow-xs">
      {/* 1. Coworker Chat Header */}
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-ops-line bg-ops-panel px-4 py-3 shrink-0 sm:px-5">
        <div className="flex items-center gap-2.5 min-w-0 sm:gap-3">
          {onBack && (
            <button
              type="button"
              onClick={onBack}
              className="inline-flex items-center gap-1.5 rounded-xl border border-ops-line bg-ops-panel px-2.5 py-1.5 text-xs font-medium text-ink hover:bg-ops-raised hover:text-ai transition cursor-pointer shrink-0"
              title="Return to Coworkers directory"
            >
              <ArrowLeft size={14} />
              <span className="hidden sm:inline">Coworkers</span>
            </button>
          )}

          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-ink text-white shadow-xs sm:h-10 sm:w-10">
            {getRoleIcon()}
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h2 className="text-base font-bold text-ink truncate">{coworker.name}</h2>
              <span className="rounded-full bg-ai/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-ai">
                {coworker.role}
              </span>
              <span className="flex items-center gap-1 text-[11px] text-ink-faint">
                <span className={`inline-block h-2 w-2 rounded-full ${coworker.availability ? "bg-emerald-500" : "bg-gray-400"} ${activeRunningTurn ? "animate-ping" : ""}`} />
                {activeRunningTurn ? "Executing..." : coworker.availability ? "Online" : "Offline"}
              </span>
            </div>
            <p className="truncate text-xs text-ink-dim hidden sm:block">
              {coworker.description || coworker.specialisation}
            </p>
          </div>
        </div>

        {/* Header Action Controls */}
        <div className="flex items-center gap-2">
          {/* Primary Context Control: Codebase / Repository Selector for Coding Coworkers */}
          {isCodingCoworker && (
            <div className="relative">
              <button
                type="button"
                onClick={() => setShowProjectDropdown((v) => !v)}
                className="flex items-center gap-1.5 rounded-xl border border-line bg-ops-panel px-3 py-1.5 text-xs font-medium text-ink hover:bg-white hover:border-line-bright transition shadow-2xs cursor-pointer"
                title="Active codebase repository"
              >
                <Code2 size={13} className="text-ai" />
                <span className="font-semibold">{activeProject?.name || "IRIS"}</span>
                <span className="text-[11px] text-ink-faint hidden sm:inline">({remoteWorkspaces[0]?.branch || "main"})</span>
                <ChevronDown size={12} className="text-ink-faint" />
              </button>

              {showProjectDropdown && (
                <div className="absolute right-0 top-full mt-1.5 w-64 rounded-xl border border-line bg-white p-1.5 shadow-lg z-30 animate-in fade-in-50 zoom-in-95 duration-100">
                  <div className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-ink-faint">
                    Active Codebase
                  </div>
                  {projects.length === 0 ? (
                    <div className="px-2 py-1.5 text-xs text-ink-dim">No registered codebases</div>
                  ) : (
                    projects.map((p) => (
                      <button
                        key={p.id}
                        type="button"
                        onClick={() => {
                          onSelectProject(p.id);
                          setShowProjectDropdown(false);
                        }}
                        className={`flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-left text-xs transition cursor-pointer ${
                          p.id === activeProjectId ? "bg-ai/10 font-semibold text-ai" : "text-ink hover:bg-ops-panel"
                        }`}
                      >
                        <span className="truncate">{p.name}</span>
                        {p.id === activeProjectId && <span className="text-[10px] text-ai">Active</span>}
                      </button>
                    ))
                  )}
                  <div className="my-1 border-t border-line" />
                  <button
                    type="button"
                    onClick={() => {
                      setShowProjectDropdown(false);
                      setShowWorkspaceModal(true);
                    }}
                    className="flex w-full items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-left text-xs font-medium text-ai hover:bg-ai/5 transition cursor-pointer"
                  >
                    <FolderPlus size={13} />
                    <span>+ Register new codebase</span>
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Secondary Action: Advanced Workspace Diagnostics & Settings */}
          {isCodingCoworker ? (
            <button
              type="button"
              onClick={() => setShowDiagnosticsModal(true)}
              className="flex h-8 w-8 items-center justify-center rounded-xl border border-line bg-ops-panel text-ink-dim hover:bg-white hover:text-ink transition cursor-pointer"
              title="Advanced Diagnostics & Workspace Settings"
            >
              <Settings size={15} />
            </button>
          ) : (
            <button
              type="button"
              onClick={onOpenSettings}
              className="flex h-8 w-8 items-center justify-center rounded-xl border border-line bg-ops-panel text-ink-dim hover:bg-white hover:text-ink transition cursor-pointer"
              title="Coworker Settings"
            >
              <Settings size={15} />
            </button>
          )}
        </div>
      </header>

      {/* Workspace Register Modal */}
      {showWorkspaceModal && (
        <div className="border-b border-ai/20 bg-ai/5 px-5 py-3 text-xs space-y-2">
          <div className="flex items-center justify-between">
            <span className="font-semibold text-ai flex items-center gap-1.5">
              <FolderPlus size={14} /> Register Working Directory Workspace
            </span>
            <button onClick={() => setShowWorkspaceModal(false)} className="text-ink-faint hover:text-ink cursor-pointer">
              ✕
            </button>
          </div>
          <div className="flex flex-wrap gap-2">
            <input
              placeholder="Workspace Name (e.g. Portfolio)"
              value={newWsName}
              onChange={(e) => setNewWsName(e.target.value)}
              className="rounded-lg border border-line bg-white px-2.5 py-1 text-xs outline-none focus:border-ai"
            />
            <input
              placeholder="Directory (e.g. C:\Projects\MyPortfolio)"
              value={newWsDir}
              onChange={(e) => setNewWsDir(e.target.value)}
              className="flex-1 min-w-[240px] rounded-lg border border-line bg-white px-2.5 py-1 text-xs font-mono outline-none focus:border-ai"
            />
            <button
              type="button"
              onClick={() => { setNewWsName("IRIS"); setNewWsDir("C:\\kirtan\\IRIS"); }}
              className="text-[11px] text-ai hover:underline self-center"
            >
              Fill C:\kirtan\IRIS
            </button>
            <Button onClick={handleRegisterWorkspace} className="text-xs bg-ai text-white px-3 py-1">
              Save Workspace
            </Button>
          </div>
        </div>
      )}

      {/* Milestone H: Remote Cloud Workspace Register Modal */}
      {showRemoteModal && (
        <div className="border-b border-emerald-200 bg-emerald-50/70 px-5 py-3 text-xs space-y-2">
          <div className="flex items-center justify-between">
            <span className="font-semibold text-emerald-800 flex items-center gap-1.5">
              <Cloud size={14} /> Connect Persistent Cloud Workspace (GitHub / 24/7 $0)
            </span>
            <button onClick={() => setShowRemoteModal(false)} className="text-ink-faint hover:text-ink cursor-pointer">
              ✕
            </button>
          </div>
          <div className="flex flex-wrap gap-2">
            <input
              placeholder="Workspace Name (e.g. IRIS Cloud Sandbox)"
              value={newRemoteName}
              onChange={(e) => setNewRemoteName(e.target.value)}
              className="rounded-lg border border-line bg-white px-2.5 py-1 text-xs outline-none focus:border-emerald-600"
            />
            <input
              placeholder="GitHub Repository URL (e.g. https://github.com/KIRTAN0902/IRIS.git)"
              value={newRemoteRepo}
              onChange={(e) => setNewRemoteRepo(e.target.value)}
              className="flex-1 min-w-[260px] rounded-lg border border-line bg-white px-2.5 py-1 text-xs font-mono outline-none focus:border-emerald-600"
            />
            <input
              placeholder="Base Branch"
              value={newRemoteBranch}
              onChange={(e) => setNewRemoteBranch(e.target.value)}
              className="w-24 rounded-lg border border-line bg-white px-2.5 py-1 text-xs font-mono outline-none focus:border-emerald-600"
            />
            <input
              placeholder="Companion URL (e.g. from Colab https://xxx.trycloudflare.com or leave blank for default)"
              value={newRemoteCompanionUrl}
              onChange={(e) => setNewRemoteCompanionUrl(e.target.value)}
              className="flex-1 min-w-[300px] rounded-lg border border-line bg-white px-2.5 py-1 text-xs font-mono outline-none focus:border-emerald-600"
            />
            <Button onClick={handleCreateRemoteWorkspace} className="text-xs bg-emerald-700 hover:bg-emerald-800 text-white px-3 py-1">
              Connect Cloud Workspace
            </Button>
          </div>
          <p className="text-[11px] text-emerald-700">
            The remote container will clone this repository, isolate tasks on dedicated branches, and preserve uncommitted patches. Your local laptop can remain off.
          </p>
        </div>
      )}

      {/* Advanced Diagnostics & Settings Modal */}
      {showDiagnosticsModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4 animate-in fade-in duration-150">
          <div className="w-full max-w-lg rounded-2xl border border-line bg-white p-6 shadow-xl space-y-5 animate-in zoom-in-95 duration-150">
            <div className="flex items-center justify-between border-b border-line pb-3">
              <div className="flex items-center gap-2">
                <SlidersHorizontal size={17} className="text-ai" />
                <h3 className="font-semibold text-ink text-base">Advanced Workspace & Engine Settings</h3>
              </div>
              <button
                type="button"
                onClick={() => setShowDiagnosticsModal(false)}
                className="text-ink-dim hover:text-ink p-1 rounded-lg hover:bg-ops-panel transition cursor-pointer"
              >
                ✕
              </button>
            </div>

            {/* Execution Target Environment */}
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-ink-dim">Target Execution Environment</label>
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => setExecutionTarget("remote")}
                  className={`flex flex-col items-start gap-1 rounded-xl border p-3 text-left transition cursor-pointer ${
                    executionTarget === "remote"
                      ? "border-emerald-500 bg-emerald-50/70 text-emerald-950 shadow-2xs"
                      : "border-line bg-ops-panel text-ink hover:bg-white"
                  }`}
                >
                  <div className="flex items-center gap-1.5 text-xs font-semibold">
                    <Cloud size={14} className="text-emerald-700" />
                    <span>Remote Cloud (Default)</span>
                  </div>
                  <span className="text-[11px] text-ink-dim leading-tight">
                    Runs in persistent cloud container (https://irisforgecode.dpdns.org). Laptop can sleep.
                  </span>
                </button>
                <button
                  type="button"
                  onClick={() => setExecutionTarget("local")}
                  className={`flex flex-col items-start gap-1 rounded-xl border p-3 text-left transition cursor-pointer ${
                    executionTarget === "local"
                      ? "border-ai bg-ai/10 text-ink shadow-2xs"
                      : "border-line bg-ops-panel text-ink hover:bg-white"
                  }`}
                >
                  <div className="flex items-center gap-1.5 text-xs font-semibold">
                    <HardDrive size={14} className="text-ai" />
                    <span>Local PC Worktree</span>
                  </div>
                  <span className="text-[11px] text-ink-dim leading-tight">
                    Runs inside local PC Git worktree. Requires local CLI engine running.
                  </span>
                </button>
              </div>
            </div>

            {/* Engine Selection */}
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-ink-dim">Coding Engine</label>
              <select
                value={selectedEngine}
                onChange={(e) => setSelectedEngine(e.target.value)}
                className="w-full rounded-xl border border-line bg-ops-panel px-3 py-2 text-xs font-medium text-ink outline-none cursor-pointer"
              >
                <option value="antigravity-cli">Antigravity CLI (agy) — Primary Google Coding Engine</option>
                <option value="codex-cli">Codex CLI — Fallback Coding Engine</option>
              </select>
            </div>

            {/* Remote Cloud Endpoint & Status */}
            <div className="rounded-xl border border-line bg-ops-panel p-3.5 space-y-2 text-xs">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-ink flex items-center gap-1.5">
                  <Cloud size={13} className="text-emerald-700" /> Remote Companion
                </span>
                <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-semibold text-emerald-800">
                  Ready (https://irisforgecode.dpdns.org)
                </span>
              </div>
              <p className="text-[11px] text-ink-dim">
                Permanent Cloudflare Tunnel connected to Google Colab / Docker container.
              </p>
              {remoteWorkspaces.length > 0 && (
                <div className="pt-2 border-t border-line/60 flex items-center justify-between text-[11px]">
                  <span className="text-ink-dim">Sandbox: {remoteWorkspaces[0].name} ({remoteWorkspaces[0].branch})</span>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => handleRecoverRemoteWorkspace(remoteWorkspaces[0].id)}
                      disabled={recoveringWs}
                      className="text-emerald-700 hover:underline font-medium cursor-pointer inline-flex items-center gap-1"
                    >
                      <RefreshCw size={11} className={recoveringWs ? "animate-spin" : ""} />
                      {recoveringWs ? "Waking..." : "Wake / Ping"}
                    </button>
                    <button
                      type="button"
                      onClick={() => handleUpdateCompanionUrl(remoteWorkspaces[0].id)}
                      className="text-ink-dim hover:text-ink cursor-pointer"
                    >
                      Edit URL
                    </button>
                  </div>
                </div>
              )}
            </div>

            {/* Actions */}
            <div className="flex items-center justify-between pt-2 border-t border-line">
              <button
                type="button"
                onClick={() => {
                  setShowDiagnosticsModal(false);
                  onOpenSettings();
                }}
                className="text-xs text-ai hover:underline cursor-pointer"
              >
                Edit Coworker Capabilities →
              </button>
              <Button onClick={() => setShowDiagnosticsModal(false)}>
                Done
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* 2. Messages Conversation Stream */}
      <div className="flex-1 overflow-y-auto px-4 py-5 sm:px-6 space-y-5">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center py-12 px-4 max-w-md mx-auto">
            <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-ai/10 text-ai mb-4">
              {getRoleIcon()}
            </div>
            <h3 className="text-base font-bold text-ink">
              Start a conversation with {coworker.name}
            </h3>
            <p className="mt-1.5 text-xs text-ink-dim leading-relaxed">
              {isCodingCoworker
                ? "Describe what you want built, refactored, or fixed in your working directory. I will formulate a plan and execute it safely in an isolated branch."
                : "Ask questions, request research, or describe your task. I will operate within my granted role and capabilities."}
            </p>

            {/* Quick Starter Chips */}
            <div className="mt-6 flex flex-wrap justify-center gap-2">
              {isCodingCoworker ? (
                <>
                  <button
                    onClick={() => handleSendMessage("Inspect the repository architecture and summarize what it does")}
                    className="rounded-xl border border-line bg-ops-panel px-3 py-1.5 text-xs text-ink-dim hover:text-ink hover:border-ai/40 transition cursor-pointer"
                  >
                    Inspect repository architecture
                  </button>
                  <button
                    onClick={() => handleSendMessage("Add unit test coverage for recent modules")}
                    className="rounded-xl border border-line bg-ops-panel px-3 py-1.5 text-xs text-ink-dim hover:text-ink hover:border-ai/40 transition cursor-pointer"
                  >
                    + Add unit tests
                  </button>
                  <button
                    onClick={() => handleSendMessage("Create a responsive dark theme portfolio layout")}
                    className="rounded-xl border border-line bg-ops-panel px-3 py-1.5 text-xs text-ink-dim hover:text-ink hover:border-ai/40 transition cursor-pointer"
                  >
                    Build portfolio layout
                  </button>
                </>
              ) : (
                <>
                  <button
                    onClick={() => handleSendMessage("What can you assist me with in your role?")}
                    className="rounded-xl border border-line bg-ops-panel px-3 py-1.5 text-xs text-ink-dim hover:text-ink hover:border-ai/40 transition cursor-pointer"
                  >
                    Explain your capabilities
                  </button>
                  <button
                    onClick={() => handleSendMessage("Search memory for recent discussions and notes")}
                    className="rounded-xl border border-line bg-ops-panel px-3 py-1.5 text-xs text-ink-dim hover:text-ink hover:border-ai/40 transition cursor-pointer"
                  >
                    Search memory
                  </button>
                </>
              )}
            </div>
          </div>
        ) : (
          messages.map((turn) => {
            const isUser = turn.role === "user";
            const isRunning = turn.role === "coworker" && ["running", "working", "queued"].includes(turn.status || "");
            const hasDiff = turn.diff && (turn.diff.changed_files || []).length > 0;
            const isTechOpen = expandedTechnical[turn.id] ?? false;
            const isDiffOpen = expandedDiff[turn.id] ?? false;

            if (isUser) {
              return (
                <div key={turn.id} className="flex justify-end">
                  <div className="max-w-[85%] sm:max-w-[75%] rounded-2xl bg-ink px-4 py-3 text-white shadow-xs">
                    <p className="whitespace-pre-wrap text-sm leading-relaxed">{turn.content}</p>
                    {turn.created_at && (
                      <span className="mt-1 block text-right text-[10px] text-white/60">
                        {new Date(turn.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                      </span>
                    )}
                  </div>
                </div>
              );
            }

            return (
              <div key={turn.id} className="flex gap-3 max-w-[95%] sm:max-w-[88%]">
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-ai/10 text-ai mt-0.5">
                  {getRoleIcon()}
                </div>

                <div className="flex-1 space-y-3">
                  {/* Coworker Message Bubble */}
                  <div className="rounded-2xl border border-line bg-white p-4 shadow-xs text-ink space-y-3">
                    {/* Running State Card with Obvious Stop Button */}
                    {isRunning && (
                      <div className="rounded-xl border border-ai/30 bg-ai/5 p-3.5 space-y-3">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="flex items-center gap-2">
                            <span className="flex h-2.5 w-2.5 rounded-full bg-ai animate-ping" />
                            <span className="font-semibold text-xs text-ink">
                              {turn.agent_id ? `${turn.agent_id.replace('-cli', '').toUpperCase()} Engine Executing...` : "Coworker Processing..."}
                            </span>
                            <span className="rounded-md bg-ai/10 px-2 py-0.5 font-mono text-[11px] text-ai font-semibold">
                              {formatTimer(elapsedSeconds)}
                            </span>
                          </div>

                          {/* STOP BUTTON */}
                          <button
                            type="button"
                            onClick={handleStopExecution}
                            disabled={stopping}
                            className="inline-flex items-center gap-1.5 rounded-lg border border-red-300 bg-red-50 px-3 py-1.5 text-xs font-semibold text-red-700 hover:bg-red-100 transition cursor-pointer"
                          >
                            <Square size={12} className="fill-red-600 text-red-600" />
                            <span>{stopping ? "Stopping..." : "Stop Execution"}</span>
                          </button>
                        </div>

                        {turn.task_branch && (
                          <div className="flex items-center gap-1.5 text-xs font-mono text-ink-dim">
                            <GitBranch size={13} className="text-ai shrink-0" />
                            <span>Branch: {turn.task_branch}</span>
                          </div>
                        )}

                        {/* Latest progress event ticker */}
                        {turn.events && turn.events.length > 0 && (
                          <div className="text-[11px] text-ink-dim font-mono bg-white/60 rounded-lg px-2.5 py-1.5 truncate border border-ai/20">
                            {turn.events[turn.events.length - 1]?.payload?.state
                              ? `Status: ${String(turn.events[turn.events.length - 1].payload.state)}`
                              : turn.events[turn.events.length - 1]?.type.replace(/_/g, " ")}
                          </div>
                        )}
                      </div>
                    )}

                    {/* Markdown Content */}
                    {turn.content && (
                      <div className="text-sm leading-relaxed text-ink space-y-2">
                        <Markdown text={turn.content} />
                      </div>
                    )}

                    {/* Error display */}
                    {turn.error && (
                      <div className="flex items-start gap-2 rounded-xl bg-red-50 p-3 text-xs text-red-800 border border-red-200">
                        <AlertCircle size={15} className="mt-0.5 shrink-0" />
                        <span>{turn.error}</span>
                      </div>
                    )}

                    {/* Changed Files Pill Strip */}
                    {hasDiff && (
                      <div className="pt-2 border-t border-line space-y-2.5">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-semibold uppercase tracking-wider text-ink-faint">
                            Changed Files ({turn.diff?.changed_files?.length})
                          </span>
                          <button
                            type="button"
                            onClick={() => setExpandedDiff((prev) => ({ ...prev, [turn.id]: !isDiffOpen }))}
                            className="text-xs text-ai hover:underline cursor-pointer flex items-center gap-1"
                          >
                            <span>{isDiffOpen ? "Hide Diff Patch" : "Inspect Diff Patch"}</span>
                            {isDiffOpen ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
                          </button>
                        </div>

                        <div className="flex flex-wrap gap-1.5">
                          {turn.diff?.changed_files?.slice(0, 8).map((f, i) => (
                            <span
                              key={i}
                              className="inline-flex items-center gap-1 rounded-md bg-ops-panel px-2 py-1 text-[11px] font-mono text-ink-dim"
                            >
                              <span className={`h-1.5 w-1.5 rounded-full ${f.status === "A" ? "bg-emerald-500" : "bg-blue-500"}`} />
                              <span className="truncate max-w-[180px]">{f.path}</span>
                            </span>
                          ))}
                          {(turn.diff?.changed_files?.length || 0) > 8 && (
                            <span className="text-[11px] text-ink-faint self-center">
                              +{(turn.diff?.changed_files?.length || 0) - 8} more
                            </span>
                          )}
                        </div>

                        {/* Expandable Unified Diff Viewer */}
                        {isDiffOpen && turn.diff?.diff && (
                          <pre className="max-h-72 overflow-auto rounded-xl bg-[#0B0D13] p-3 text-[11px] font-mono text-gray-200 whitespace-pre">
                            {turn.diff.diff}
                          </pre>
                        )}

                        {/* Git Actions (Commit, Push) */}
                        {(turn.coding_task_id || turn.remote_workspace_id) && (
                          <div className="flex flex-wrap gap-2 pt-1">
                            <Button
                              variant="outline"
                              onClick={() => {
                                if (turn.remote_workspace_id) {
                                  handleCommitRemote(turn.remote_workspace_id);
                                } else if (turn.coding_task_id) {
                                  handleCommitWorktree(turn.coding_task_id);
                                }
                              }}
                              className="text-xs h-8 px-2.5"
                            >
                              <GitCommit size={13} className="mr-1" /> Commit to Task Branch
                            </Button>
                            <Button
                              variant="outline"
                              onClick={() => {
                                if (turn.remote_workspace_id) {
                                  handlePushRemote(turn.remote_workspace_id, turn.task_branch || "iris/task");
                                } else if (turn.coding_task_id) {
                                  handlePushBranch(turn.coding_task_id);
                                }
                              }}
                              className="text-xs h-8 px-2.5 text-ai border-ai/40 hover:bg-ai/10"
                            >
                              <UploadCloud size={13} className="mr-1" /> Push Branch to Remote
                            </Button>
                          </div>
                        )}
                      </div>
                    )}

                    {/* Expandable Technical Details Drawer & Quick Actions */}
                    <div className="pt-1">
                      <div className="flex items-center justify-between">
                        <button
                          type="button"
                          onClick={() => setExpandedTechnical((prev) => ({ ...prev, [turn.id]: !isTechOpen }))}
                          className="flex items-center gap-1 text-[11px] text-ink-faint hover:text-ink cursor-pointer"
                        >
                          <Terminal size={11} />
                          <span>Technical Details</span>
                          {isTechOpen ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
                        </button>

                        <button
                          type="button"
                          onClick={() => handleSaveAsTask(turn)}
                          className="flex items-center gap-1 text-[11px] text-ink-faint hover:text-ai transition cursor-pointer"
                          title="Save this coworker deliverable as a trackable task in IRIS Tasks"
                        >
                          <ListChecks size={12} />
                          <span>Save as Task</span>
                        </button>
                      </div>

                      {isTechOpen && (
                        <div className="mt-2 space-y-2 rounded-xl bg-ops-panel p-3 text-[11px] font-mono text-ink-dim border border-line">
                          {turn.task_id && <div>Task ID: {turn.task_id}</div>}
                          {turn.task_branch && <div>Branch: {turn.task_branch}</div>}
                          {turn.worktree_path && <div>Worktree: {turn.worktree_path}</div>}
                          {turn.events && turn.events.length > 0 && (
                            <div>
                              <p className="font-semibold text-ink">Events ({turn.events.length}):</p>
                              <div className="max-h-36 overflow-auto space-y-1 mt-1">
                                {turn.events.map((e) => (
                                  <div key={e.id} className="text-[10px]">
                                    <span className="text-ink-faint">{new Date(e.created_at).toLocaleTimeString()}: </span>
                                    <span>{e.type}</span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            );
          })
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* 3. Bottom Composer */}
      <footer className="border-t border-ops-line bg-ops-panel p-4 shrink-0 space-y-2.5">
        {/* Active running task banner with immediate Stop button */}
        {activeRunningTurn && (
          <div className="flex items-center justify-between rounded-xl bg-amber-500/10 border border-amber-500/30 px-3.5 py-1.5 text-xs text-amber-900">
            <span className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-amber-500 animate-pulse" />
              <span>
                Task executing ({formatTimer(elapsedSeconds)}) — You can say <b>"Stop"</b> or press Stop anytime
              </span>
            </span>
            <button
              type="button"
              onClick={handleStopExecution}
              disabled={stopping}
              className="font-semibold text-critical hover:underline cursor-pointer"
            >
              Stop Execution
            </button>
          </div>
        )}

        {/* Input box */}
        <div className="flex items-end gap-2 rounded-2xl border border-ops-line bg-ops-void p-2.5 shadow-xs focus-within:border-ai transition">
          <textarea
            rows={1}
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void handleSendMessage();
              }
            }}
            placeholder={composerPlaceholder}
            className="flex-1 resize-none bg-transparent px-2 py-1 text-sm text-ink outline-none max-h-32 placeholder:text-ink-faint"
          />

          {/* Voice Input Button */}
          <button
            type="button"
            onClick={toggleSpeechRecognition}
            className={`p-2 rounded-xl transition cursor-pointer ${isRecording ? "bg-red-500 text-white animate-pulse" : "text-ink-faint hover:text-ink hover:bg-ops-ground"}`}
            title={isRecording ? "Stop voice dictation" : "Voice dictation"}
          >
            {isRecording ? <MicOff size={16} /> : <Mic size={16} />}
          </button>

          {/* Send Button */}
          <button
            type="button"
            onClick={() => void handleSendMessage()}
            disabled={!inputText.trim() || loading}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-ink text-white disabled:opacity-40 hover:bg-ink/90 transition cursor-pointer"
          >
            <ArrowUp size={16} />
          </button>
        </div>

        {/* Workspace directory indicator */}
        <div className="flex items-center justify-between text-[11px] text-ink-faint px-1">
          <span className="truncate">
            Working Context:{" "}
            {activeProject ? (
              <span className="font-medium text-ink">
                {activeProject.name} ({activeProject.directory})
              </span>
            ) : (
              <span className="italic text-amber-700">No project workspace assigned</span>
            )}
          </span>
          <span className="text-[10px]">Enter to send · Shift+Enter for new line</span>
        </div>
      </footer>
    </div>
  );
}
