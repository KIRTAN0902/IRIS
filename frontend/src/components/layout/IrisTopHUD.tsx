import { useEffect, useState } from "react";
import {
  Bell,
  CheckCircle2,
  ChevronRight,
  Command,
  Moon,
  Search,
  Settings2,
  ShieldAlert,
  Square,
  Sun,
  Users,
  Wifi,
  WifiOff,
  X,
  Compass,
  Database,
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { useAIStatus, useAttentionItems } from "@/hooks/queries";
import { useUiStore } from "@/stores";
import { useLensStore, type IrisLens } from "@/stores/lensStore";
import { useUIState, useSaveUIPreferences } from "@/features/home/useUIOrchestrator";
import { cn } from "@/lib/format";
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

export function IrisTopHUD() {
  const { activeLens, setActiveLens, setSettingsOpen } = useLensStore();
  const setAskOpen = useUiStore((s) => s.setAskOpen);
  const uiState = useUIState();
  const saveUiPreferences = useSaveUIPreferences();

  const [panel, setPanel] = useState<"health" | "notifications" | null>(null);

  const health = useQuery({
    queryKey: ["system-health"],
    queryFn: () => api.get<Health>("/health"),
    staleTime: 15_000,
    refetchInterval: 30_000,
    retry: 0,
  });

  const mesh = useQuery({
    queryKey: ["system-health", "mesh"],
    queryFn: () => api.get<Mesh>("/mesh/devices"),
    staleTime: 15_000,
    refetchInterval: 30_000,
    retry: 0,
  });

  const ai = useAIStatus();
  const attention = useAttentionItems();
  const approvals = useQuery({
    queryKey: ["coworker-approvals", "pending"],
    queryFn: () => api.get<PendingApproval[]>("/coworkers/approvals?status=pending"),
    staleTime: 10_000,
    refetchInterval: 20_000,
    retry: 0,
  });

  const computer = useQuery({
    queryKey: ["computer-status"],
    queryFn: () => api.get<ComputerStatus>("/computer/status"),
    staleTime: 5_000,
    refetchInterval: (query) => (query.state.data?.session?.state === "active" ? 2_000 : 15_000),
    retry: 0,
  });

  const connected = health.isSuccess && health.data.status === "ok";
  const attentionCount = attention.data?.length ?? 0;
  const approvalCount = approvals.data?.length ?? 0;
  const totalCount = attentionCount + approvalCount;

  // Global hotkeys for lenses: Alt+1 / Alt+2 / Alt+3 / Alt+4
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setAskOpen(true);
      }
      if (e.altKey && e.key === "1") {
        e.preventDefault();
        setActiveLens("studio");
      }
      if (e.altKey && e.key === "2") {
        e.preventDefault();
        setActiveLens("horizon");
      }
      if (e.altKey && e.key === "3") {
        e.preventDefault();
        setActiveLens("fleet");
      }
      if (e.altKey && e.key === "4") {
        e.preventDefault();
        setActiveLens("vault");
      }
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [setActiveLens, setAskOpen]);

  const handleEmergencyStop = async () => {
    try {
      const desktop = (window as unknown as { irisDesktop?: { triggerKillSwitch: (s: string) => Promise<boolean> } })
        .irisDesktop;
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
      const desktop = (window as unknown as { irisDesktop?: { resetKillSwitch?: () => Promise<boolean> } })
        .irisDesktop;
      if (desktop?.resetKillSwitch) {
        await desktop.resetKillSwitch();
      } else {
        await api.post(
          "/computer/kill-switch/reset",
          {},
          { headers: { "X-Computer-Auth-Token": "iris_colab_secret_2026" } },
        );
      }
      await computer.refetch();
    } catch (err) {
      console.error("Kill switch reset failed", err);
    }
  };

  const isComputerActive = computer.data?.session?.state === "active";
  const isKillSwitchEngaged = Boolean(computer.data?.session?.kill_switch_engaged);

  const currentTheme = uiState.data?.preferences.theme ?? "dark";
  const toggleTheme = () => {
    if (!uiState.data) return;
    const next = currentTheme === "dark" ? "light" : "dark";
    saveUiPreferences.mutate({
      version: uiState.data.version,
      preferences: { theme: next },
    });
  };

  return (
    <header className="sticky top-0 z-40 flex h-14 shrink-0 items-center justify-between border-b border-ops-line bg-ops-panel/90 px-3.5 backdrop-blur-md transition-colors sm:px-6">
      {/* 1. Left: Brand & Ambient Orb */}
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => setActiveLens("studio")}
          className="group flex items-center gap-2.5 cursor-pointer text-left focus:outline-none"
          title="IRIS Intelligence Operating System"
        >
          <div className="relative flex h-8 w-8 items-center justify-center rounded-xl bg-ai/10 border border-ai/25 group-hover:border-ai/50 transition">
            <IrisMark size={20} />
            <span
              className={cn(
                "absolute -bottom-0.5 -right-0.5 h-2 w-2 rounded-full border border-ops-panel",
                connected ? "bg-emerald-500" : "bg-amber-400",
              )}
            />
          </div>
          <div className="hidden flex-col sm:flex">
            <span className="text-[13px] font-bold tracking-wider text-ink">IRIS</span>
            <span className="text-[10px] text-ink-faint tracking-tight font-medium -mt-0.5">PERSONAL OS</span>
          </div>
        </button>
      </div>

      {/* 2. Center: Spatial Lens Segmented Switcher */}
      <nav
        aria-label="Operating Lenses"
        className="flex items-center rounded-xl bg-ops-raised/60 p-1 border border-ops-line gap-0.5"
      >
        <LensTab
          id="studio"
          label="Studio"
          icon={Command}
          active={activeLens === "studio"}
          onClick={() => setActiveLens("studio")}
          shortcut="Alt 1"
        />
        <LensTab
          id="horizon"
          label="Horizon"
          icon={Compass}
          active={activeLens === "horizon"}
          onClick={() => setActiveLens("horizon")}
          shortcut="Alt 2"
        />
        <LensTab
          id="fleet"
          label="Fleet"
          icon={Users}
          active={activeLens === "fleet"}
          onClick={() => setActiveLens("fleet")}
          shortcut="Alt 3"
          badge={approvalCount > 0 ? approvalCount : undefined}
        />
        <LensTab
          id="vault"
          label="Vault"
          icon={Database}
          active={activeLens === "vault"}
          onClick={() => setActiveLens("vault")}
          shortcut="Alt 4"
        />
      </nav>

      {/* 3. Right: Telemetry, Universal Search & Sentinel Actions */}
      <div className="flex items-center gap-1.5 sm:gap-2">
        {/* Computer Control Sentinel Button */}
        {isKillSwitchEngaged ? (
          <button
            onClick={handleResetKillSwitch}
            className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-amber-500/40 bg-amber-500/10 px-2.5 text-[11px] font-semibold text-amber-500 hover:bg-amber-500/20 transition cursor-pointer"
            title="Emergency Kill-Switch is active. Click to reset."
          >
            <ShieldAlert size={13} />
            <span className="hidden md:inline">Reset Kill-Switch</span>
          </button>
        ) : isComputerActive ? (
          <button
            onClick={handleEmergencyStop}
            className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-critical bg-critical/15 px-2.5 text-[11px] font-semibold text-critical hover:bg-critical/25 animate-pulse transition cursor-pointer"
            title="Active Windows Desktop Session. Click to immediately abort."
          >
            <Square size={12} className="fill-current" />
            <span>Stop Computer</span>
          </button>
        ) : null}

        {/* Universal Search Command Bar Trigger */}
        <button
          onClick={() => setAskOpen(true)}
          aria-label="Universal Search & Intelligence"
          className="hidden sm:flex h-8 items-center gap-2 rounded-lg border border-ops-line bg-ops-void px-2.5 text-xs text-ink-faint hover:border-ops-line-bright hover:text-ink transition cursor-pointer"
        >
          <Search size={14} className="opacity-70" />
          <span className="text-[12px]">Ask IRIS</span>
          <kbd className="rounded border border-ops-line-bright bg-ops-raised px-1 py-0.2 text-[10px] font-mono text-ink-faint">
            Ctrl K
          </kbd>
        </button>

        {/* Notifications & Pending Approvals */}
        <button
          type="button"
          onClick={() => setPanel(panel === "notifications" ? null : "notifications")}
          aria-label={`Inbox and approvals (${totalCount})`}
          className="relative grid h-8 w-8 place-items-center rounded-lg text-ink-dim hover:bg-ops-raised transition cursor-pointer"
        >
          <Bell size={16} />
          {totalCount > 0 && (
            <span className="absolute -right-0.5 -top-0.5 grid h-4 min-w-4 place-items-center rounded-full bg-ai px-1 text-[9px] font-bold text-white shadow-xs">
              {totalCount > 9 ? "9+" : totalCount}
            </span>
          )}
        </button>

        {/* System Health Dropdown */}
        <button
          type="button"
          onClick={() => setPanel(panel === "health" ? null : "health")}
          aria-label="System Health"
          className="flex h-8 items-center gap-1.5 rounded-lg px-2 text-[12px] text-ink-dim hover:bg-ops-raised transition cursor-pointer"
        >
          {connected ? (
            <Wifi size={14} className="text-emerald-500" />
          ) : (
            <WifiOff size={14} className="text-amber-400" />
          )}
          <span className="hidden md:inline font-medium">{connected ? "Online" : "Offline"}</span>
        </button>

        {/* Theme Toggle Button */}
        <button
          type="button"
          onClick={toggleTheme}
          aria-label="Toggle theme"
          className="grid h-8 w-8 place-items-center rounded-lg text-ink-dim hover:bg-ops-raised transition cursor-pointer"
          title={`Switch to ${currentTheme === "dark" ? "light" : "dark"} mode`}
        >
          {currentTheme === "dark" ? <Sun size={15} /> : <Moon size={15} />}
        </button>

        {/* Settings Hub Trigger */}
        <button
          type="button"
          onClick={() => setSettingsOpen(true)}
          aria-label="Settings Hub"
          className="grid h-8 w-8 place-items-center rounded-lg text-ink-dim hover:bg-ops-raised transition cursor-pointer"
          title="System Settings & Infrastructure"
        >
          <Settings2 size={16} />
        </button>
      </div>

      {/* Flyout Panels (Notifications / Health) */}
      {panel && (
        <>
          <button
            aria-label="Close panel backdrop"
            className="fixed inset-0 z-40 cursor-default bg-black/10 backdrop-blur-2xs"
            onClick={() => setPanel(null)}
          />
          <section
            role="dialog"
            aria-label={panel === "health" ? "System Health Telemetry" : "Needs Attention & Approvals"}
            className="absolute right-3 top-[calc(100%+8px)] z-50 w-[min(92vw,390px)] rounded-2xl border border-ops-line-bright bg-ops-panel p-4 shadow-2xl animate-in fade-in zoom-in-95 duration-150"
          >
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-ink">
                {panel === "health" ? "System Telemetry" : "Action Inbox"}
              </h2>
              <button
                type="button"
                aria-label="Close"
                onClick={() => setPanel(null)}
                className="rounded-lg p-1 text-ink-faint hover:bg-ops-raised cursor-pointer"
              >
                <X size={15} />
              </button>
            </div>

            {panel === "health" ? (
              <div className="space-y-2 text-xs">
                <StatusRow
                  label="Backend API"
                  value={health.isLoading ? "Checking…" : health.isError ? "Offline" : health.data?.status ?? "Unknown"}
                  ok={connected}
                />
                <StatusRow
                  label="Supabase DB"
                  value={health.data?.database ?? (health.isError ? "Offline" : "Checking…")}
                  ok={health.data?.database === "ok"}
                />
                <StatusRow
                  label="Reasoning Engine"
                  value={ai.data?.model || "gemini-3.1-flash-lite"}
                  ok={Boolean(ai.data?.responding)}
                />
                <StatusRow
                  label="Sovereign Mesh"
                  value={
                    mesh.isLoading
                      ? "Querying…"
                      : mesh.isError
                      ? "Offline"
                      : `${mesh.data?.devices?.length ?? 0} connected`
                  }
                  ok={!mesh.isError}
                />
                <StatusRow
                  label="Computer Control"
                  value={
                    computer.data?.session?.kill_switch_engaged
                      ? "🚨 Kill Switch"
                      : computer.data?.session?.state === "active"
                      ? "🟢 Session Active"
                      : computer.data?.companion_online
                      ? "Ready (Idle)"
                      : "Companion Offline"
                  }
                  ok={Boolean(computer.data?.companion_online && !computer.data?.session?.kill_switch_engaged)}
                />
              </div>
            ) : totalCount === 0 ? (
              <div className="py-6 text-center text-xs text-ink-faint">
                <CheckCircle2 size={24} className="mx-auto mb-2 text-emerald-500 opacity-80" />
                <p className="font-medium text-ink">All caught up</p>
                <p className="mt-0.5 text-ink-dim">No pending coworker approvals or urgent alerts.</p>
              </div>
            ) : (
              <div className="max-h-[60vh] space-y-2 overflow-y-auto pr-1">
                {approvals.data?.map((item) => (
                  <div
                    key={item.id}
                    className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-left space-y-1.5"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-[11px] font-semibold text-amber-500 uppercase tracking-wider">
                        Approval Request
                      </span>
                      <code className="text-[10px] font-mono text-ai bg-ops-panel px-1.5 py-0.5 rounded">
                        {item.capability}
                      </code>
                    </div>
                    <p className="text-xs text-ink">{item.reason || "Coworker requested privileged capability."}</p>
                    <button
                      type="button"
                      onClick={() => {
                        setPanel(null);
                        setActiveLens("fleet");
                      }}
                      className="inline-flex items-center gap-1 text-[11px] font-semibold text-ai hover:underline cursor-pointer"
                    >
                      <span>Review in Fleet</span>
                      <ChevronRight size={12} />
                    </button>
                  </div>
                ))}
                {attention.data?.map((item, idx) => (
                  <div key={idx} className="rounded-xl bg-ops-ground p-3 space-y-1 border border-ops-line">
                    <p className="text-xs font-semibold text-ink">{item.title}</p>
                    <p className="text-[11px] text-ink-dim">{item.description}</p>
                  </div>
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </header>
  );
}

function LensTab({
  label,
  icon: Icon,
  active,
  onClick,
  shortcut,
  badge,
}: {
  id: IrisLens;
  label: string;
  icon: typeof Command;
  active: boolean;
  onClick: () => void;
  shortcut?: string;
  badge?: number;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "relative flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium transition-all cursor-pointer",
        active
          ? "bg-ops-panel text-ink shadow-xs border border-ops-line-bright font-semibold"
          : "text-ink-faint hover:text-ink hover:bg-ops-panel/40",
      )}
      title={`${label} Lens (${shortcut ?? ""})`}
    >
      <Icon size={14} className={cn(active ? "text-ai" : "opacity-75")} />
      <span>{label}</span>
      {badge !== undefined && badge > 0 && (
        <span className="grid h-4 min-w-4 place-items-center rounded-full bg-ai px-1 text-[9px] font-bold text-white">
          {badge}
        </span>
      )}
    </button>
  );
}

function StatusRow({ label, value, ok }: { label: string; value: string; ok: boolean }) {
  return (
    <div className="flex items-center justify-between gap-2 rounded-lg bg-ops-ground px-2.5 py-1.5">
      <span className="text-ink-faint">{label}</span>
      <span className={cn("truncate font-medium", ok ? "text-emerald-500" : "text-amber-500")}>{value}</span>
    </div>
  );
}
