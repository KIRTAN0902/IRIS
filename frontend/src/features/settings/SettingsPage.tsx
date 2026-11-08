import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  BookOpen,
  BrainCircuit,
  CheckCircle2,
  Library,
  Mic,
  Radio,
  RefreshCw,
  Settings,
  ShieldCheck,
  Sparkles,
  Volume2,
  Zap,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Panel, Lamp } from "@/components/ui/Panel";
import { api } from "@/api/client";
import { cn } from "@/lib/format";
import type { AIStatusOut } from "@/types/api";
import { PermissionsPanel } from "@/features/settings/PermissionsPanel";
import { KnowledgePage } from "@/features/knowledge/KnowledgePage";
import { MeshPage } from "@/features/mesh/MeshPage";

export type SettingsTab = "general" | "knowledge" | "mesh" | "ai" | "permissions";

const SETTINGS_SECTIONS: { id: SettingsTab; label: string; icon: typeof Settings; description: string }[] = [
  { id: "general", label: "General", icon: Settings, description: "Theme and appearance preferences" },
  { id: "knowledge", label: "Knowledge", icon: Library, description: "Vault, graph, claims and history" },
  { id: "mesh", label: "Devices & Mesh", icon: Radio, description: "Cross-device pairing and continuity" },
  { id: "ai", label: "AI & Models", icon: BrainCircuit, description: "Reasoning engine and specialist models" },
  { id: "permissions", label: "Permissions", icon: ShieldCheck, description: "Device capabilities and access profile" },
];

export function SettingsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const currentTab = (searchParams.get("tab") as SettingsTab) || "general";

  // --- AI Settings State ---
  const [aiStatus, setAiStatus] = useState<AIStatusOut | null>(null);
  const [loadingAi, setLoadingAi] = useState(false);

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
    if (currentTab === "ai") {
      void loadAiStatus();
    }
  }, [currentTab]);

  const setTab = (tab: SettingsTab) => {
    setSearchParams({ tab });
  };

  const isWideSection = currentTab === "knowledge" || currentTab === "mesh";

  return (
    <div className={cn("mx-auto space-y-6 pb-12 w-full", isWideSection ? "max-w-6xl" : "max-w-3xl")}>
      {/* Header */}
      <div>
        <div className="flex items-center gap-2.5">
          <Settings size={26} className="text-ai" />
          <h1 className="text-[28px] font-bold tracking-tight text-ink">Settings</h1>
        </div>
        <p className="text-[13px] text-ink-dim mt-0.5">
          System preferences, sovereign cross-device continuity, knowledge infrastructure, and AI configuration.
        </p>
      </div>

      {/* Settings Navigation Tabs (Nested Sub-Pages) */}
      <nav aria-label="Settings Sections" className="flex flex-wrap rounded-xl bg-ops-raised/60 p-1.5 border border-ops-line gap-1 text-[13px]">
        {SETTINGS_SECTIONS.map((section) => {
          const Icon = section.icon;
          const active = currentTab === section.id;
          return (
            <button
              key={section.id}
              type="button"
              onClick={() => setTab(section.id)}
              className={cn(
                "flex-1 min-w-[120px] flex items-center justify-center gap-2 rounded-lg py-2 px-3 font-medium transition-colors cursor-pointer text-center",
                active
                  ? "bg-ops-panel text-ink shadow-sm border border-ops-line-bright font-semibold"
                  : "text-ink-dim hover:text-ink hover:bg-ops-panel/40",
              )}
            >
              <Icon size={16} className={active ? "text-ai" : "opacity-70"} />
              <span>{section.label}</span>
            </button>
          );
        })}
      </nav>

      {/* --- Section 1: General Preferences --- */}
      {currentTab === "general" && (
        <div className="space-y-6">
          <Panel title="Appearance & Visual Identity">
            <div className="space-y-4 pt-2 text-[13px]">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="font-semibold text-ink text-[14px]">Operating Visual Theme</p>
                  <p className="mt-0.5 text-xs text-ink-faint">
                    Precision light palette with Alpine Sage accents and ceramic alabaster surfaces.
                  </p>
                </div>
                <div className="flex items-center gap-2 rounded-xl border border-ops-line-bright bg-ops-raised px-3 py-2 text-ink text-xs font-semibold">
                  <span className="h-2.5 w-2.5 rounded-full bg-ai" />
                  <span>Daylight Palette (Light Only)</span>
                </div>
              </div>
            </div>
          </Panel>
        </div>
      )}

      {/* --- Section 2: Knowledge Subsystem --- */}
      {currentTab === "knowledge" && (
        <div className="space-y-4">
          <KnowledgePage />
        </div>
      )}

      {/* --- Section 3: Devices & Mesh Subsystem --- */}
      {currentTab === "mesh" && (
        <div className="space-y-4">
          <MeshPage />
        </div>
      )}

      {/* --- Section 4: AI & Models Settings --- */}
      {currentTab === "ai" && (
        <div className="space-y-6">
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
                            : "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
                        )}
                      >
                        {(aiStatus?.provider || "gemini").toLowerCase().includes("gemini")
                          ? "GOOGLE GEMINI"
                          : "NVIDIA NIM"}
                      </span>
                      <span className="rounded-full bg-ai/10 px-2 py-0.5 text-[11px] font-semibold text-ai border border-ai/20">
                        Primary Model
                      </span>
                    </div>
                    <p className="text-[12px] text-ink-dim mt-0.5">
                      Model: <code className="font-mono text-ai font-medium">{aiStatus?.model || "gemini-3.1-flash-lite"}</code> • Strategy: {aiStatus?.strategy || "Native Tool Calling"}
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

              <div className="flex items-center justify-between rounded-lg bg-ops-raised/40 px-3.5 py-2.5 text-[12px] text-ink-dim border border-ops-line">
                <span className="flex items-center gap-2">
                  <CheckCircle2 size={14} className="text-emerald-400" />
                  Health: <strong className="text-ink">{aiStatus?.status || "OPERATIONAL"}</strong>
                </span>
                <span className="text-ink-faint">
                  {aiStatus?.last_checked_at
                    ? `Checked ${new Date(aiStatus.last_checked_at).toLocaleTimeString()}`
                    : "Live inference pipeline"}
                </span>
              </div>
            </div>
          </Panel>

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
                        model: "gemini-3.1-flash-lite",
                        fallback: "Fallback Engine",
                        status: "OPERATIONAL",
                      },
                      {
                        id: "router",
                        name: "System 1 Intent Router",
                        role: "Single-Token Fast Intent Classification (Jev Principle)",
                        provider: "gemini",
                        model: "gemini-3.1-flash-lite",
                        fallback: "Deterministic Keyword Match",
                        status: "OPERATIONAL",
                      },
                      {
                        id: "scribe",
                        name: "Scribe Agent",
                        role: "Personal Knowledge, Notes, Diary, Habits, Fitness & Finances",
                        provider: "gemini",
                        model: "gemini-3.1-flash-lite",
                        fallback: "Direct Service APIs",
                        status: "OPERATIONAL",
                      },
                    ]
                ).map((agent) => (
                  <div
                    key={agent.id}
                    className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 rounded-xl border border-ops-line bg-ops-raised/20 p-3 hover:bg-ops-raised/40 transition-colors"
                  >
                    <div className="flex items-start gap-3">
                      <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-ops-panel border border-ops-line">
                        {agent.id === "orchestrator" && <Sparkles size={16} className="text-ai" />}
                        {agent.id === "router" && <Zap size={16} className="text-amber-400" />}
                        {agent.id === "scribe" && <BookOpen size={16} className="text-emerald-400" />}
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
                                : "bg-ops-panel text-ink-dim border-ops-line",
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
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </Panel>

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
                    {aiStatus?.voice?.live_model || "gemini-2.0-flash-exp"}
                  </p>
                  <p className="text-[11px] text-ink-faint">Native multimodal speech session</p>
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
                    {aiStatus?.voice?.tts_model || "gemini-speech"}
                  </p>
                  <p className="text-[11px] text-ink-faint">Conversational audio stream</p>
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
                    {aiStatus?.voice?.stt_model || "gemini-transcribe"}
                  </p>
                  <p className="text-[11px] text-ink-faint">Fast transcription backup</p>
                </div>
              </div>
            </div>
          </Panel>
        </div>
      )}

      {/* --- Section 5: Permissions & Device Access --- */}
      {currentTab === "permissions" && <PermissionsPanel />}
    </div>
  );
}
