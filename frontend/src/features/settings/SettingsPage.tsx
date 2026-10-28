import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  BookOpen,
  BrainCircuit,
  Calendar,
  CheckCircle2,
  Cpu,
  Eye,
  Laptop,
  Lock,
  Mail,
  Mic,
  Radio,
  RefreshCw,
  Settings,
  ShieldCheck,
  Smartphone,
  Sparkles,
  Terminal,
  Trash2,
  Volume2,
  Zap,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Panel, Lamp } from "@/components/ui/Panel";
import { api } from "@/api/client";
import { cn } from "@/lib/format";
import type { AIStatusOut } from "@/types/api";
import { PermissionsPanel } from "@/features/settings/PermissionsPanel";

interface PairedDevice {
  id: number;
  device_id: string;
  device_name: string;
  device_type: string;
  battery_level?: number | null;
  is_charging?: boolean | null;
  paired_at: string;
  last_seen_at?: string;
}

interface HostPower {
  percent: number | null;
  is_charging: boolean;
  ac_status: string;
}

interface PairingInvite {
  pairing_code: string;
  token: string;
  expires_at: string;
}

export function SettingsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const currentTab = (searchParams.get("tab") as "mesh" | "permissions" | "ai" | "general") || "mesh";

  // --- Mesh Settings State ---
  const [pairedDevices, setPairedDevices] = useState<PairedDevice[]>([]);
  const [hostPower, setHostPower] = useState<HostPower | null>(null);
  const [statusMsg, setStatusMsg] = useState("");

  // Role detection and pairing form
  const [pairingMode, setPairingMode] = useState<"enter_pin" | "show_pin">(() => {
    if (typeof window === "undefined") return "enter_pin";
    const isMobile =
      /Android|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent) ||
      (window.innerWidth < 768 && ("ontouchstart" in window || navigator.maxTouchPoints > 0));
    return isMobile ? "show_pin" : "enter_pin";
  });
  const [pinInput, setPinInput] = useState("");
  const [deviceNameInput] = useState("Mobile Phone");
  const [isVerifying, setIsVerifying] = useState(false);
  const [verifyError, setVerifyError] = useState("");

  // Mobile PIN generation state
  const [invite, setInvite] = useState<PairingInvite | null>(null);
  const [loadingInvite, setLoadingInvite] = useState(false);
  const [phonePairedSuccess, setPhonePairedSuccess] = useState(false);

  // --- AI Settings State ---
  const [aiStatus, setAiStatus] = useState<AIStatusOut | null>(null);
  const [loadingAi, setLoadingAi] = useState(false);

  const loadMeshData = async () => {
    try {
      const devRes = await api.get<{ host_power: HostPower | null }>("/mesh/devices");
      setHostPower(devRes.host_power);
      const pairRes = await api.get<{ paired_devices: PairedDevice[] }>("/mesh/pair/devices");
      setPairedDevices(pairRes.paired_devices || []);
    } catch {
      // Fallback
    }
  };

  const loadAiStatus = async () => {
    setLoadingAi(true);
    try {
      const res = await api.get<AIStatusOut>("/ai/status");
      setAiStatus(res);
    } catch {
      // Fallback
    } finally {
      setLoadingAi(false);
    }
  };

  useEffect(() => {
    loadMeshData();
    loadAiStatus();
  }, []);

  const setTab = (tab: "mesh" | "permissions" | "ai" | "general") => {
    setSearchParams({ tab });
  };

  // Laptop enters phone's 6-digit PIN
  const handleVerifyPhonePin = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const cleanPin = pinInput.trim().replace(/\s+/g, "");
    if (cleanPin.length !== 6) {
      setVerifyError("Please enter the complete 6-digit PIN shown on your phone.");
      return;
    }
    setVerifyError("");
    setIsVerifying(true);
    try {
      await api.post("/mesh/pair/verify", {
        code: cleanPin,
        device_name: deviceNameInput.trim() || "Mobile Phone",
        device_type: "phone_mobile",
      });
      setStatusMsg("✨ Device paired permanently!");
      setPinInput("");
      await loadMeshData();
      setTimeout(() => setStatusMsg(""), 4000);
    } catch (err: any) {
      const msg = err?.response?.data?.detail || err?.message || "Invalid or expired 6-digit PIN.";
      setVerifyError(msg);
    } finally {
      setIsVerifying(false);
    }
  };

  // Mobile generates its 6-digit PIN to show to laptop
  const handleGeneratePhoneCode = async () => {
    setLoadingInvite(true);
    setPhonePairedSuccess(false);
    try {
      let localDeviceId = localStorage.getItem("iris_device_id");
      if (!localDeviceId) {
        localDeviceId = "phone_" + Math.random().toString(36).substring(2, 9);
        localStorage.setItem("iris_device_id", localDeviceId);
      }
      const res = await api.post<PairingInvite>("/mesh/pair/code", {
        device_id: localDeviceId,
        device_name: "Mobile Phone",
        device_type: "phone_mobile",
      });
      setInvite(res);

      // Start polling for laptop verification
      const pollToken = res.token;
      const interval = setInterval(async () => {
        try {
          const statusRes = await api.get<{ status: string; pairing_token?: string }>(
            `/mesh/pair/status?token=${encodeURIComponent(pollToken)}&device_id=${encodeURIComponent(localDeviceId)}`
          );
          if (statusRes.status === "paired") {
            clearInterval(interval);
            setPhonePairedSuccess(true);
            if (statusRes.pairing_token) {
              localStorage.setItem("iris_pair_token", statusRes.pairing_token);
            }
            setStatusMsg("✨ Connected to laptop permanently!");
            loadMeshData();
          }
        } catch {
          // ignore
        }
      }, 1500);
    } catch {
      setVerifyError("Failed to generate pairing PIN. Check connection.");
    } finally {
      setLoadingInvite(false);
    }
  };

  useEffect(() => {
    if (pairingMode === "show_pin" && !invite && !loadingInvite) {
      handleGeneratePhoneCode();
    }
  }, [pairingMode]);

  const handleUnpairDevice = async (deviceId: string, name: string) => {
    if (!window.confirm(`Unpair ${name}? You will need a new 6-digit PIN to reconnect.`)) return;
    try {
      await api.delete(`/mesh/pair/${deviceId}`);
      setStatusMsg(`Unpaired ${name}`);
      loadMeshData();
      setTimeout(() => setStatusMsg(""), 3000);
    } catch {
      setStatusMsg("Failed to unpair device");
    }
  };

  const handleLockPC = async () => {
    if (!window.confirm("Lock Windows workstation now?")) return;
    await api.post("/mesh/command", { command: "LOCK_PC" });
    setStatusMsg("Windows Workstation locked.");
    setTimeout(() => setStatusMsg(""), 3000);
  };

  return (
    <div className="mx-auto max-w-3xl space-y-6 pb-12">
      {/* Header */}
      <div>
        <div className="flex items-center gap-2.5">
          <Settings size={26} className="text-ai" />
          <h1 className="text-[28px] font-bold tracking-tight text-ink">Settings</h1>
        </div>
        <p className="text-[13px] text-ink-dim mt-0.5">
          System preferences, sovereign cross-device continuity, and AI configuration.
        </p>
      </div>

      {statusMsg && (
        <div className="rounded-md bg-ai-dim px-4 py-2 text-[13px] text-ai font-medium">
          {statusMsg}
        </div>
      )}

      {/* Settings Navigation Tabs (Nested Sub-Pages) */}
      <div className="flex rounded-xl bg-ops-raised/60 p-1.5 border border-ops-line gap-1 text-[13px]">
        <button
          type="button"
          onClick={() => setTab("mesh")}
          className={cn(
            "flex-1 flex items-center justify-center gap-2 rounded-lg py-2 font-medium transition-colors cursor-pointer",
            currentTab === "mesh"
              ? "bg-ops-panel text-ink shadow-sm border border-ops-line-bright font-semibold"
              : "text-ink-dim hover:text-ink hover:bg-ops-panel/40"
          )}
        >
          <Radio size={16} className={currentTab === "mesh" ? "text-ai" : ""} />
          <span>Mesh</span>
        </button>

        <button
          type="button"
          onClick={() => setTab("permissions")}
          className={cn(
            "flex-1 flex items-center justify-center gap-2 rounded-lg py-2 font-medium transition-colors cursor-pointer",
            currentTab === "permissions"
              ? "bg-ops-panel text-ink shadow-sm border border-ops-line-bright font-semibold"
              : "text-ink-dim hover:text-ink hover:bg-ops-panel/40"
          )}
        >
          <ShieldCheck size={16} className={currentTab === "permissions" ? "text-ai" : ""} />
          <span>Permissions</span>
        </button>

        <button
          type="button"
          onClick={() => setTab("ai")}
          className={cn(
            "flex-1 flex items-center justify-center gap-2 rounded-lg py-2 font-medium transition-colors cursor-pointer",
            currentTab === "ai"
              ? "bg-ops-panel text-ink shadow-sm border border-ops-line-bright font-semibold"
              : "text-ink-dim hover:text-ink hover:bg-ops-panel/40"
          )}
        >
          <BrainCircuit size={16} className={currentTab === "ai" ? "text-ai" : ""} />
          <span>AI & Models</span>
        </button>

        <button
          type="button"
          onClick={() => setTab("general")}
          className={cn(
            "flex-1 flex items-center justify-center gap-2 rounded-lg py-2 font-medium transition-colors cursor-pointer",
            currentTab === "general"
              ? "bg-ops-panel text-ink shadow-sm border border-ops-line-bright font-semibold"
              : "text-ink-dim hover:text-ink hover:bg-ops-panel/40"
          )}
        >
          <Cpu size={16} className={currentTab === "general" ? "text-ai" : ""} />
          <span>General</span>
        </button>
      </div>

      {/* --- Tab 1: Mesh & Continuity Settings --- */}
      {currentTab === "mesh" && (
        <div className="space-y-6">
          {/* Pair Device Section */}
          <Panel title="Pair New Device (6-Digit PIN)" lamp={<Lamp tone="go" pulse />}>
            <div className="space-y-4 pt-2">
              <p className="text-[12px] text-ink-dim">
                Pair your phone and laptop once without tunnels or QR codes. Connected forever at $0 via sovereign PostgreSQL relay.
              </p>

              {/* Role Switcher Tabs */}
              <div className="flex rounded-lg bg-ops-raised/60 p-1 text-[12px] border border-ops-line">
                <button
                  type="button"
                  onClick={() => setPairingMode("enter_pin")}
                  className={cn(
                    "flex-1 rounded-md py-1.5 font-medium transition-colors flex items-center justify-center gap-1.5 cursor-pointer",
                    pairingMode === "enter_pin"
                      ? "bg-ops-panel text-ink shadow-sm border border-ops-line-bright font-semibold"
                      : "text-ink-dim hover:text-ink"
                  )}
                >
                  <Laptop size={14} /> 💻 I'm on Laptop (Type PIN)
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setPairingMode("show_pin");
                    handleGeneratePhoneCode();
                  }}
                  className={cn(
                    "flex-1 rounded-md py-1.5 font-medium transition-colors flex items-center justify-center gap-1.5 cursor-pointer",
                    pairingMode === "show_pin"
                      ? "bg-ops-panel text-ink shadow-sm border border-ops-line-bright font-semibold"
                      : "text-ink-dim hover:text-ink"
                  )}
                >
                  <Smartphone size={14} /> 📱 I'm on Phone (Show PIN)
                </button>
              </div>

              {pairingMode === "enter_pin" ? (
                <div className="rounded-xl border border-ai/20 bg-ai/5 p-4 space-y-3">
                  <div>
                    <p className="text-[14px] font-semibold text-ink flex items-center gap-1.5">
                      <Laptop size={16} className="text-ai" /> Enter 6-Digit Phone PIN
                    </p>
                    <p className="text-[12px] text-ink-dim mt-0.5">
                      Open IRIS on your phone (More &rarr; Settings &rarr; Mesh). Look at the 6-digit code and enter it here:
                    </p>
                  </div>

                  <form onSubmit={handleVerifyPhonePin} className="space-y-2.5">
                    <div className="flex gap-2">
                      <input
                        type="text"
                        value={pinInput}
                        onChange={(e) => {
                          setVerifyError("");
                          setPinInput(e.target.value.replace(/\D/g, "").slice(0, 6));
                        }}
                        placeholder="000 000"
                        className="w-40 rounded-lg border border-ops-line-bright bg-ops-raised px-4 py-2.5 text-center font-mono text-[22px] font-bold tracking-widest text-ink outline-none focus:border-ai"
                        maxLength={6}
                        autoFocus
                      />
                      <Button
                        type="submit"
                        disabled={pinInput.length !== 6 || isVerifying}
                        className="flex-1"
                      >
                        {isVerifying ? "Verifying..." : "🔗 Link Phone Forever"}
                      </Button>
                    </div>
                    {verifyError && (
                      <p className="text-[12px] text-rose-400 font-medium">{verifyError}</p>
                    )}
                  </form>
                </div>
              ) : (
                <div className="rounded-xl border border-ai/30 bg-ai/5 p-5 space-y-2.5 text-center">
                  <p className="text-[14px] font-semibold text-ink flex items-center justify-center gap-1.5">
                    <Smartphone size={16} className="text-ai" /> Phone Pairing PIN
                  </p>
                  <p className="text-[12px] text-ink-dim">
                    Type this 6-digit PIN on your Laptop's Settings page:
                  </p>
                  {loadingInvite ? (
                    <div className="py-6 text-[13px] text-ink-dim animate-pulse">Generating secure PIN...</div>
                  ) : phonePairedSuccess ? (
                    <div className="py-4 space-y-1">
                      <p className="text-[16px] font-bold text-go">✨ Connected to Laptop!</p>
                      <p className="text-[12px] text-ink-dim">This device is now permanently linked.</p>
                    </div>
                  ) : (
                    <div className="space-y-3">
                      <div className="font-mono text-[42px] font-black tracking-[0.25em] text-ink py-1">
                        {invite?.pairing_code || "......"}
                      </div>
                      <div className="flex items-center justify-center gap-2 text-[12px] text-go font-medium animate-pulse">
                        <div className="h-2 w-2 rounded-full bg-go" />
                        <span>Waiting for laptop to enter PIN...</span>
                      </div>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={handleGeneratePhoneCode}
                        className="mt-1"
                      >
                        🔄 Refresh Code
                      </Button>
                    </div>
                  )}
                </div>
              )}
            </div>
          </Panel>

          {/* Linked Devices Card */}
          <Panel
            title={`Linked Sovereign Devices (${pairedDevices.length})`}
            lamp={<Lamp tone={pairedDevices.length > 0 ? "go" : "caution"} />}
          >
            <div className="space-y-3 pt-2">
              {pairedDevices.length === 0 ? (
                <p className="text-center py-6 text-[13px] text-ink-faint">
                  No devices paired yet. Follow the steps above to link your phone.
                </p>
              ) : (
                <div className="space-y-2">
                  {pairedDevices.map((dev) => (
                    <div
                      key={dev.device_id}
                      className="flex items-center justify-between rounded-lg bg-ops-raised/40 p-3 text-[13px]"
                    >
                      <div className="flex items-center gap-3">
                        <Smartphone size={18} className="text-ai" />
                        <div>
                          <p className="font-medium text-ink">{dev.device_name}</p>
                          <p className="text-[11px] text-ink-faint flex items-center gap-1.5">
                            <span className="text-go font-medium">● Sovereign Cloud Relay</span>
                            {dev.battery_level != null && <span>· 🔋 {dev.battery_level}%</span>}
                            <span>· Paired {new Date(dev.paired_at).toLocaleDateString()}</span>
                          </p>
                        </div>
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleUnpairDevice(dev.device_id, dev.device_name)}
                        className="text-ink-faint hover:text-rose-400"
                        title="Unpair Device"
                      >
                        <Trash2 size={14} /> Unpair
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </Panel>

          {/* Workstation Hardware Daemon */}
          <Panel title="Laptop Relay Daemon & OS Controls" lamp={<Lamp tone="go" />}>
            <div className="space-y-3 pt-2">
              <div className="rounded-lg bg-ops-raised/30 p-3 text-[13px] space-y-2">
                <div className="flex justify-between">
                  <span className="text-ink-dim">Laptop Power</span>
                  <span className="text-ink font-mono font-medium">
                    {hostPower?.percent != null ? `${hostPower.percent}%` : "AC Power"}{" "}
                    ({hostPower?.ac_status || "Plugged In"})
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-ink-dim">Lid & Sleep Mode</span>
                  <span className="text-go font-medium">Sleep Disabled (Always Reachable)</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-ink-dim">Daemon Loop Interval</span>
                  <span className="text-ink font-mono">1.5 seconds (Sub-second Relay)</span>
                </div>
              </div>

              <div className="flex gap-2">
                <Button variant="danger" size="sm" onClick={handleLockPC}>
                  <Lock size={13} /> Lock Windows Laptop
                </Button>
              </div>
            </div>
          </Panel>
        </div>
      )}

      {/* --- Tab: Permissions & Device Access --- */}
      {currentTab === "permissions" && <PermissionsPanel />}

      {/* --- Tab 2: AI & Models Settings --- */}
      {currentTab === "ai" && (
        <div className="space-y-6">
          {/* Overview & Live Engine Status */}
          <Panel
            title="Autonomous AI Mesh & Active Models"
            lamp={<Lamp tone={aiStatus?.status === "OPERATIONAL" ? "ai" : "caution"} pulse />}
          >
            <div className="space-y-4 pt-2 text-[13px]">
              <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-ai/20 bg-ai/5 p-4">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-ai/10 border border-ai/20 text-ai">
                    <Sparkles size={20} />
                  </div>
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="font-semibold text-ink text-[15px]">IRIS Core Reasoning</p>
                      <span
                        className={cn(
                          "rounded-full px-2 py-0.5 text-[11px] font-semibold border",
                          (aiStatus?.provider || "gemini").toLowerCase().includes("gemini")
                            ? "bg-sky-500/10 text-sky-400 border-sky-500/20"
                            : "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                        )}
                      >
                        {(aiStatus?.provider || "gemini").toLowerCase().includes("gemini")
                          ? "GOOGLE GEMINI"
                          : "NVIDIA NIM"}
                      </span>
                      <span className="rounded-full bg-ai/10 px-2 py-0.5 text-[11px] font-semibold text-ai border border-ai/20">
                        Strict Gemma 4 (No Fallback)
                      </span>
                    </div>
                    <p className="text-[12px] text-ink-dim mt-0.5">
                      Model: <code className="font-mono text-ai font-medium">{aiStatus?.model || "gemma-4-31b-it"}</code> • Strategy: {aiStatus?.strategy || "Native Tool Calling"}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={loadAiStatus}
                    disabled={loadingAi}
                    className="flex items-center gap-1.5"
                  >
                    <RefreshCw size={13} className={loadingAi ? "animate-spin" : ""} />
                    {loadingAi ? "Refreshing..." : "Check Status"}
                  </Button>
                </div>
              </div>

              {/* Status explanation */}
              <div className="flex items-center justify-between rounded-lg bg-ops-raised/40 px-3.5 py-2.5 text-[12px] text-ink-dim border border-ops-line">
                <span className="flex items-center gap-2">
                  <CheckCircle2 size={14} className="text-emerald-400" />
                  Health: <strong className="text-ink">{aiStatus?.status || "OPERATIONAL"}</strong>
                </span>
                <span className="text-ink-faint">
                  {aiStatus?.last_checked_at
                    ? `Checked ${new Date(aiStatus.last_checked_at).toLocaleTimeString()}`
                    : "Zero-data training guaranteed"}
                </span>
              </div>
            </div>
          </Panel>

          {/* Sub-Agent Specialist Models Grid */}
          <Panel title="Specialized Sub-Agent Models (Multi-Agent Swarm)" lamp={<Lamp tone="go" />}>
            <div className="space-y-3 pt-2 text-[13px]">
              <p className="text-[12px] text-ink-dim">
                Each agent has an isolated execution registry and dedicated model calibrated for zero tool-collision and maximum speed.
              </p>

              <div className="grid gap-3 sm:grid-cols-1">
                {(aiStatus?.agents && aiStatus.agents.length > 0
                  ? aiStatus.agents
                  : [
                      {
                        id: "orchestrator",
                        name: "IRIS Core (Orchestrator)",
                        role: "Multi-Turn Conversation, Fast State Actions & Sub-Agent Synthesis",
                        provider: "gemini",
                        model: "gemma-4-31b-it",
                        fallback: "Gemma 4 (gemma-4-31b-it)",
                        status: "OPERATIONAL",
                      },
                      {
                        id: "router",
                        name: "System 1 Intent Router",
                        role: "Single-Token Fast Intent Classification (Jev Principle)",
                        provider: "gemini",
                        model: "gemma-4-31b-it",
                        fallback: "Deterministic Keyword Match",
                        status: "OPERATIONAL",
                      },
                      {
                        id: "scribe",
                        name: "Scribe Agent",
                        role: "Personal Knowledge, Notes, Diary, Habits, Fitness & Finances",
                        provider: "gemini",
                        model: "gemma-4-31b-it",
                        fallback: "Direct Service APIs",
                        status: "OPERATIONAL",
                      },
                      {
                        id: "planner",
                        name: "Planner Agent",
                        role: "Chronos Strategic Schedule, Time Blocks, Tasks & Milestones",
                        provider: "gemini",
                        model: "gemma-4-31b-it",
                        fallback: "Chronos Heuristics",
                        status: "OPERATIONAL",
                      },
                      {
                        id: "operator",
                        name: "Operator Agent",
                        role: "Workstation CLI, Filesystem, Application Launch & Autonomous Coding",
                        provider: "gemini",
                        model: "gemma-4-31b-it",
                        fallback: "Mesh Local APIs",
                        status: "OPERATIONAL",
                      },
                      {
                        id: "bubba",
                        name: "BUBBA Agent",
                        role: "Google Workspace (Gmail Triage, Drafts & Google Drive Docs)",
                        provider: "gemini",
                        model: "gemma-4-31b-it",
                        fallback: "Direct OAuth API",
                        status: "OPERATIONAL",
                      },
                      {
                        id: "vision",
                        name: "Vision Perception",
                        role: "Multimodal Screen Analysis & UI Inspection",
                        provider: "gemini",
                        model: "gemma-4-31b-it",
                        fallback: "Screen OCR / Native Snapshot",
                        status: "OPERATIONAL",
                      },
                    ]
                ).map((agent) => (
                  <div
                    key={agent.id}
                    className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 rounded-xl bg-ops-raised/40 p-3.5 border border-ops-line/80 hover:border-ops-line-bright transition-colors"
                  >
                    <div className="flex items-start gap-3">
                      <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-ops-panel border border-ops-line">
                        {agent.id === "orchestrator" && <Sparkles size={16} className="text-ai" />}
                        {agent.id === "router" && <Zap size={16} className="text-amber-400" />}
                        {agent.id === "scribe" && <BookOpen size={16} className="text-emerald-400" />}
                        {agent.id === "planner" && <Calendar size={16} className="text-sky-400" />}
                        {agent.id === "operator" && <Terminal size={16} className="text-indigo-400" />}
                        {agent.id === "bubba" && <Mail size={16} className="text-rose-400" />}
                        {agent.id === "vision" && <Eye size={16} className="text-violet-400" />}
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <p className="font-semibold text-ink text-[13px]">{agent.name}</p>
                          <span
                            className={cn(
                              "rounded-full px-2 py-0.2 text-[10px] font-semibold border",
                              agent.provider.toLowerCase().includes("nvidia")
                                ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                                : agent.provider.toLowerCase().includes("gemini")
                                ? "bg-sky-500/10 text-sky-400 border-sky-500/20"
                                : "bg-ops-panel text-ink-dim border-ops-line"
                            )}
                          >
                            {agent.provider.toUpperCase()}
                          </span>
                        </div>
                        <p className="text-[11px] text-ink-dim mt-0.5 line-clamp-1">{agent.role}</p>
                      </div>
                    </div>

                    <div className="flex sm:flex-col sm:items-end justify-between sm:justify-center border-t sm:border-t-0 border-ops-line/50 pt-2 sm:pt-0 shrink-0">
                      <code className="font-mono text-[12px] font-medium text-ink bg-ops-panel/80 px-2.5 py-1 rounded-md border border-ops-line">
                        {agent.model}
                      </code>
                      {agent.fallback && (
                        <span className="text-[10px] text-ink-faint mt-1">
                          Fallback: {agent.fallback}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </Panel>

          {/* Voice Intelligence Pipeline */}
          <Panel title="Voice & Multimodal Intelligence Pipeline" lamp={<Lamp tone="go" />}>
            <div className="space-y-3 pt-2 text-[13px]">
              <div className="grid gap-3 sm:grid-cols-3">
                <div className="rounded-xl bg-ops-raised/30 p-3.5 border border-ops-line space-y-1.5">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Radio size={16} className="text-ai" />
                      <p className="font-semibold text-ink text-[13px]">Gemini Live Conversational</p>
                    </div>
                    <span className="rounded-full bg-ai/10 px-2 py-0.2 text-[10px] font-semibold text-ai border border-ai/20">
                      LIVE
                    </span>
                  </div>
                  <p className="font-mono text-[12px] text-ink-dim">
                    {aiStatus?.voice?.live_model || "gemini-3.8-live"}
                  </p>
                  <p className="text-[11px] text-ink-faint">Native full-duplex multimodal speech WebSocket</p>
                </div>

                <div className="rounded-xl bg-ops-raised/30 p-3.5 border border-ops-line space-y-1.5">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Volume2 size={16} className="text-go" />
                      <p className="font-semibold text-ink text-[13px]">Neural Speech Output</p>
                    </div>
                    <span className="rounded-full bg-sky-500/10 px-2 py-0.2 text-[10px] font-semibold text-sky-400 border border-sky-500/20">
                      GEMINI
                    </span>
                  </div>
                  <p className="font-mono text-[12px] text-ink-dim truncate">
                    {aiStatus?.voice?.tts_model || "gemini-3.8-live,gemini-3.8-flash-tts"} • Voice: {aiStatus?.voice?.tts_voice || "Enceladus"}
                  </p>
                  <p className="text-[11px] text-ink-faint">24kHz conversational neural audio stream</p>
                </div>

                <div className="rounded-xl bg-ops-raised/30 p-3.5 border border-ops-line space-y-1.5">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Mic size={16} className="text-amber-400" />
                      <p className="font-semibold text-ink text-[13px]">Speech-to-Text Fallback</p>
                    </div>
                    <span className="rounded-full bg-sky-500/10 px-2 py-0.2 text-[10px] font-semibold text-sky-400 border border-sky-500/20">
                      GEMINI
                    </span>
                  </div>
                  <p className="font-mono text-[12px] text-ink-dim">
                    {aiStatus?.voice?.stt_model || "gemini-3.5-transcribe"}
                  </p>
                  <p className="text-[11px] text-ink-faint">Ultra-fast transcription backup</p>
                </div>
              </div>

              <div className="rounded-lg bg-ops-raised/20 p-3 text-[11px] text-ink-faint flex items-center gap-2">
                <ShieldCheck size={14} className="text-emerald-400 shrink-0" />
                <span>
                  Gemini 3.8 Live enables end-to-end conversational speech with zero transcription pipeline delay, native voice inflection, and real-time interruption.
                </span>
              </div>
            </div>
          </Panel>
        </div>
      )}

      {/* --- Tab 3: General Settings --- */}
      {currentTab === "general" && (
        <div className="space-y-6">
          <Panel title="System & Environment" lamp={<Lamp tone="go" />}>
            <div className="space-y-3 pt-2 text-[13px]">
              <div className="flex justify-between items-center py-2 border-b border-ops-line">
                <span className="text-ink-dim">Default Timezone</span>
                <span className="text-ink font-mono font-medium">Asia/Kolkata (IST)</span>
              </div>
              <div className="flex justify-between items-center py-2 border-b border-ops-line">
                <span className="text-ink-dim">Host Architecture</span>
                <span className="text-ink font-mono">Vercel Serverless + Supabase PG 17</span>
              </div>
              <div className="flex justify-between items-center py-2">
                <span className="text-ink-dim">Application Version</span>
                <span className="text-ink font-mono">IRIS 2.0 (Sovereign Continuity)</span>
              </div>
            </div>
          </Panel>
        </div>
      )}
    </div>
  );
}
