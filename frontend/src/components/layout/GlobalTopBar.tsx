import { useState } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { Bell, CircleHelp, Search, Settings2, Wifi, WifiOff, X, AudioLines, Square, ShieldAlert } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { useAIStatus, useAttentionItems } from "@/hooks/queries";
import { useUiStore } from "@/stores";
import { cn } from "@/lib/format";
import { useVoiceSession } from "@/features/home/VoiceSession";
import { IrisMark } from "@/components/layout/Sidebar";

type Health = { status: string; service: string; version: string; database: string; ai: string };
type Mesh = { devices: { device_id: string; name: string }[]; host_power?: unknown };
type PendingApproval = { id: string; coworker_id: string; task_id: string; capability: string; reason: string };
type ComputerStatus = {
  session: {
    state: "background" | "active" | "paused" | "terminated";
    session_id: string;
    kill_switch_engaged: boolean;
    kill_switch_source?: string;
    reason: string;
  };
  is_windows: boolean;
  interactive_available: boolean;
  companion_online: boolean;
  message: string;
};

export function GlobalTopBar() {
  const setAskOpen = useUiStore((s) => s.setAskOpen);
  const navigate = useNavigate();
  const location = useLocation();
  const voice = useVoiceSession();
  const [panel, setPanel] = useState<"health" | "notifications" | null>(null);
  const health = useQuery({ queryKey: ["system-health"], queryFn: () => api.get<Health>("/health"), staleTime: 15_000, refetchInterval: 30_000, retry: 0 });
  const mesh = useQuery({ queryKey: ["system-health", "mesh"], queryFn: () => api.get<Mesh>("/mesh/devices"), staleTime: 15_000, refetchInterval: 30_000, retry: 0 });
  const ai = useAIStatus();
  const attention = useAttentionItems();
  const approvals = useQuery({ queryKey: ["coworker-approvals", "pending"], queryFn: () => api.get<PendingApproval[]>("/coworkers/approvals?status=pending"), staleTime: 15_000, refetchInterval: 30_000, retry: 0 });
  const computer = useQuery({
    queryKey: ["computer-status"],
    queryFn: () => api.get<ComputerStatus>("/computer/status"),
    staleTime: 5_000,
    refetchInterval: (query) => query.state.data?.session?.state === "active" ? 2_000 : 15_000,
    retry: 0,
  });

  const connected = health.isSuccess && health.data.status === "ok";
  const attentionCount = attention.data?.length ?? 0;
  const approvalCount = approvals.data?.length ?? 0;
  const count = attentionCount + approvalCount;
  const provider = [ai.data?.provider, ai.data?.model].filter(Boolean).join(" · ") || "Provider not reported";

  const handleEmergencyStop = async () => {
    try {
      const desktop = (window as unknown as { irisDesktop?: { triggerKillSwitch: (s: string) => Promise<boolean> } }).irisDesktop;
      if (desktop?.triggerKillSwitch) {
        await desktop.triggerKillSwitch("ui_emergency_button");
      }
      await api.post("/computer/kill-switch", { source: "ui_emergency_button" });
      await computer.refetch();
    } catch (err) {
      console.error("Emergency stop failed", err);
    }
  };

  const handleResetKillSwitch = async () => {
    try {
      const desktop = (window as unknown as { irisDesktop?: { resetKillSwitch?: () => Promise<boolean> } }).irisDesktop;
      if (desktop?.resetKillSwitch) {
        await desktop.resetKillSwitch();
      } else {
        await api.post("/computer/kill-switch/reset", {}, {
          headers: { "X-Computer-Auth-Token": "iris_colab_secret_2026" },
        });
      }
      await computer.refetch();
    } catch (err) {
      console.error("Kill switch reset failed", err);
    }
  };

  const isComputerActive = computer.data?.session?.state === "active";
  const isKillSwitchEngaged = Boolean(computer.data?.session?.kill_switch_engaged);

  return <header className="sticky top-0 z-30 flex h-14 shrink-0 items-center gap-3 border-b border-ops-line bg-ops-panel/95 px-4 backdrop-blur md:px-6">
    <NavLink to="/" aria-label="IRIS Home" className="flex shrink-0 items-center gap-2 text-ink md:hidden"><IrisMark size={20}/><span className="text-xs font-semibold tracking-[0.12em]">IRIS</span></NavLink>
    <button onClick={() => setAskOpen(true)} aria-label="Search IRIS" className="flex h-9 min-w-0 flex-1 items-center gap-2 rounded-xl border border-ops-line bg-ops-ground px-3 text-sm text-ink-faint hover:border-ops-line-bright md:max-w-[520px]">
      <Search size={16} aria-hidden /><span className="flex-1 text-left">Search IRIS</span><kbd className="hidden rounded border border-ops-line px-1.5 py-0.5 text-[10px] md:inline">Ctrl K</kbd>
    </button>
    <div className="ml-auto flex items-center gap-1.5">
      {/* Computer Control Emergency Stop / Indicator */}
      {isKillSwitchEngaged ? (
        <button
          onClick={handleResetKillSwitch}
          className="inline-flex h-9 items-center gap-1.5 rounded-xl border border-caution bg-caution-dim px-2.5 text-xs font-semibold text-caution hover:bg-caution/20"
          title="Emergency Kill-Switch is engaged. Click to reset to background mode."
        >
          <ShieldAlert size={14} />
          <span className="hidden sm:inline">Kill-Switch (Reset)</span>
        </button>
      ) : isComputerActive ? (
        <button
          onClick={handleEmergencyStop}
          className="inline-flex h-9 items-center gap-1.5 rounded-xl border border-caution bg-caution/15 px-2.5 text-xs font-semibold text-caution hover:bg-caution/25 animate-pulse"
          title="Active Computer Control session. Click to immediately abort operations."
        >
          <Square size={13} className="fill-current" />
          <span>Stop Computer</span>
        </button>
      ) : null}

      {voice.phase !== "off" && location.pathname !== "/" && <button onClick={() => navigate("/")} className="inline-flex h-10 items-center gap-2 rounded-xl bg-ai-dim px-3 text-xs font-medium text-ai" aria-label={`${voice.phase}, return to Home`} title="Voice session active. Return to Home"><AudioLines size={16} className={voice.phase === "listening" ? "animate-pulse" : ""}/><span className="hidden sm:inline capitalize">{voice.phase}</span></button>}
      <button onClick={() => setPanel(panel === "notifications" ? null : "notifications")} aria-label={`Notifications${count ? `, ${count} items` : ""}`} aria-expanded={panel === "notifications"} className="relative grid h-10 w-10 place-items-center rounded-xl text-ink-dim hover:bg-ops-raised">
        <Bell size={17}/>{count > 0 && <span className="absolute right-1 top-1 grid h-4 min-w-4 place-items-center rounded-full bg-ai px-1 text-[10px] text-white">{count > 9 ? "9+" : count}</span>}
      </button>
      <button onClick={() => setPanel(panel === "health" ? null : "health")} aria-label="System health" aria-expanded={panel === "health"} className="flex h-10 items-center gap-2 rounded-xl px-2 text-xs text-ink-dim hover:bg-ops-raised">
        {connected ? <Wifi size={16} className="text-go"/> : <WifiOff size={16} className="text-caution"/>}<span className="hidden sm:inline">{connected ? "Systems" : "Status"}</span>
      </button>
      <button onClick={() => navigate("/settings")} aria-label="Settings" className="grid h-10 w-10 place-items-center rounded-xl text-ink-dim hover:bg-ops-raised"><Settings2 size={17}/></button>
    </div>
    {panel && <>
      <button aria-label="Close panel" className="fixed inset-0 z-30 cursor-default" onClick={() => setPanel(null)} />
      <section aria-label={panel === "health" ? "System health details" : "Notifications"} className="absolute right-3 top-[calc(100%+8px)] z-40 w-[min(92vw,390px)] rounded-2xl border border-ops-line-bright bg-ops-panel p-4 shadow-xl">
        <div className="mb-3 flex items-center justify-between"><h2 className="text-sm font-semibold text-ink">{panel === "health" ? "System health" : "Needs your attention"}</h2><button aria-label="Close" onClick={() => setPanel(null)} className="rounded-lg p-1.5 text-ink-faint hover:bg-ops-raised"><X size={16}/></button></div>
        {panel === "health" ? <div className="space-y-2 text-sm">
          <StatusRow label="Backend" value={health.isLoading ? "Checking…" : health.isError ? "Unavailable" : health.data?.status ?? "Unknown"} ok={connected}/>
          <StatusRow label="Database" value={health.data?.database ?? (health.isError ? "Unavailable" : "Checking…")} ok={health.data?.database === "ok"}/>
          <StatusRow label="AI provider" value={ai.isLoading ? "Checking…" : ai.isError ? "Status unavailable" : ai.data?.responding ? provider : ai.data?.status ?? "Not responding"} ok={Boolean(ai.data?.responding)}/>
          <StatusRow label="Mesh" value={mesh.isLoading ? "Checking…" : mesh.isError ? "Unavailable" : `${mesh.data?.devices?.length ?? 0} connected device${mesh.data?.devices?.length === 1 ? "" : "s"}`} ok={!mesh.isError}/>
          <StatusRow
            label="Computer Control"
            value={
              computer.isLoading ? "Checking…" :
              computer.isError ? "Unavailable" :
              computer.data?.session?.kill_switch_engaged ? "🚨 Kill Switch Active" :
              computer.data?.session?.state === "active" ? "🟢 Session Active" :
              computer.data?.companion_online ? "Ready (Idle)" : "Companion Offline"
            }
            ok={Boolean(computer.data?.companion_online && !computer.data?.session?.kill_switch_engaged)}
          />
          {(health.isError || mesh.isError || ai.isError) && <p className="rounded-xl bg-caution-dim p-3 text-xs text-ink-dim">One or more services did not return health details. Retry when your connection is available.</p>}
        </div> : attention.isLoading || approvals.isLoading ? <p className="py-3 text-sm text-ink-faint">Loading updates…</p> : attention.isError && approvals.isError ? <p className="py-3 text-sm text-ink-faint">Notifications are temporarily unavailable.</p> : count === 0 ? <div className="flex items-center gap-2 py-3 text-sm text-ink-faint"><CircleHelp size={16}/>You're all caught up.</div> : <ul className="max-h-[55vh] space-y-2 overflow-y-auto">{approvals.data?.map((item) => <li key={item.id}><button onClick={() => { setPanel(null); navigate("/coworkers"); }} className="w-full rounded-xl border border-caution/30 bg-caution-dim p-3 text-left"><p className="text-sm font-medium text-ink">Approval needed · {item.capability}</p><p className="mt-1 text-xs text-ink-dim">{item.reason || "A coworker is waiting for your review."}</p><span className="mt-2 block text-xs font-medium text-ai">Review coworker action →</span></button></li>)}{attention.data?.map((item, i) => <li key={`${item.title}-${i}`} className="rounded-xl bg-ops-ground p-3"><p className="text-sm font-medium text-ink">{item.title}</p><p className="mt-1 text-xs text-ink-dim">{item.description}</p></li>)}</ul>}
      </section>
    </>}
  </header>;
}

function StatusRow({ label, value, ok }: { label: string; value: string; ok: boolean }) {
  return <div className="flex items-center justify-between gap-3 rounded-xl bg-ops-ground px-3 py-2"><span className="text-ink-faint">{label}</span><span className={cn("truncate text-right font-medium capitalize", ok ? "text-go" : "text-ink-dim")}>{value}</span></div>;
}
