import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import {
  Bell,
  Copy,
  Eye,
  EyeOff,
  KeyRound,
  Laptop,
  Lock,
  MessageSquare,
  Radio,
  RefreshCw,
  Send,
  Smartphone,
  Sparkles,
  Unlock,
  Volume2,
  Zap,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Panel } from "@/components/ui/Panel";
import { api } from "@/api/client";
import { cn } from "@/lib/format";
import { launchPhoneApp } from "@/lib/appLauncher";

interface LaptopHostInfo {
  device_id: string;
  device_name: string;
  device_type: string;
  battery_level: number | null;
  is_charging: boolean | null;
  is_online: boolean;
  is_locked?: boolean;
  last_seen_at?: string | null;
}

interface PairedDevice {
  id: number;
  device_id: string;
  device_name: string;
  device_type: string;
  battery_level?: number | null;
  is_charging?: boolean | null;
  is_online?: boolean;
  paired_at: string;
  last_seen_at?: string | null;
}

interface ContinuityPageProps {
  initialView?: "laptop" | "phone";
}

// Generate or retrieve persistent local device ID
function getOrCreateDeviceId(): string {
  if (typeof window === "undefined") return "client_unknown";
  let devId = localStorage.getItem("iris_device_id");
  if (!devId) {
    const isMobile =
      /Android|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent) ||
      (window.innerWidth < 768 && ("ontouchstart" in window || navigator.maxTouchPoints > 0));
    devId = (isMobile ? "phone_" : "laptop_") + Math.random().toString(36).substring(2, 9);
    localStorage.setItem("iris_device_id", devId);
  }
  return devId;
}

// Play audible chime through Web Audio API
function playChime(frequency = 880) {
  try {
    const AudioCtx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    if (!AudioCtx) return;
    const ctx = new AudioCtx();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();

    osc.type = "sine";
    osc.frequency.setValueAtTime(frequency * 0.75, ctx.currentTime);
    osc.frequency.setValueAtTime(frequency, ctx.currentTime + 0.08);

    gain.gain.setValueAtTime(0.35, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.6);

    osc.connect(gain);
    gain.connect(ctx.destination);

    osc.start();
    osc.stop(ctx.currentTime + 0.6);
  } catch {
    // Ignore autoplay or audio context constraints
  }
}

export function ContinuityPage({ initialView }: ContinuityPageProps) {
  const location = useLocation();
  const navigate = useNavigate();

  // Active view: "laptop" means viewing the laptop's state (as seen on mobile),
  // Active view: "laptop" means viewing the laptop's state (as seen on mobile),
  // "phone" means viewing the mobile phone's state (as seen on laptop).
  const [view, setView] = useState<"laptop" | "phone">(() => {
    if (initialView) return initialView;
    if (location.pathname.startsWith("/laptop")) return "laptop";
    if (location.pathname.startsWith("/phone")) return "phone";
    if (typeof window !== "undefined") {
      const isMobile =
        /Android|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent) ||
        (window.innerWidth < 768 && ("ontouchstart" in window || navigator.maxTouchPoints > 0));
      return isMobile ? "laptop" : "phone";
    }
    return "laptop";
  });

  useEffect(() => {
    if (location.pathname.startsWith("/laptop")) {
      setView("laptop");
    } else if (location.pathname.startsWith("/phone")) {
      setView("phone");
    }
  }, [location.pathname]);

  // Mesh & Telemetry state
  const [myDeviceId] = useState<string>(getOrCreateDeviceId);
  const [myBattery, setMyBattery] = useState<{ level: number | null; charging: boolean | null }>({
    level: null,
    charging: null,
  });
  const [laptopHost, setLaptopHost] = useState<LaptopHostInfo | null>(null);
  const [pairedDevices, setPairedDevices] = useState<PairedDevice[]>([]);
  const [statusMsg, setStatusMsg] = useState("");
  const [quickNote, setQuickNote] = useState("");
  const [receivedNotes, setReceivedNotes] = useState<string[]>([]);
  const [isPhoneLocked, setIsPhoneLocked] = useState(false);
  const [isLaptopLocked, setIsLaptopLocked] = useState(false);
  const [isPhoneRemotelyLocked, setIsPhoneRemotelyLocked] = useState(false);
  const [savedPassword, setSavedPassword] = useState(() => {
    return (typeof window !== "undefined" && localStorage.getItem("iris_laptop_pwd")) || "";
  });
  const [isUnlockModalOpen, setIsUnlockModalOpen] = useState(false);
  const [inputPassword, setInputPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [rememberPassword, setRememberPassword] = useState(true);
  const [pairingCode, setPairingCode] = useState<string | null>(null);
  const [isGeneratingCode, setIsGeneratingCode] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const isMobileClient =
    typeof window !== "undefined" &&
    (/Android|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent) ||
      (window.innerWidth < 768 && ("ontouchstart" in window || navigator.maxTouchPoints > 0)));

  // Identify the primary phone from paired devices
  const primaryPhone = pairedDevices.find(
    (d) => d.device_type === "phone_mobile" || d.device_id.startsWith("phone_")
  ) || pairedDevices[0];

  // 1. Report local device telemetry & battery to backend every 8s
  const reportLocalTelemetry = async () => {
    let batLevel = myBattery.level;
    let isCharging = myBattery.charging;

    if (typeof navigator !== "undefined" && "getBattery" in navigator) {
      try {
        const b = await (navigator as unknown as { getBattery: () => Promise<{ level: number; charging: boolean; addEventListener: (t: string, fn: () => void) => void }> }).getBattery();
        batLevel = Math.round(b.level * 100);
        isCharging = Boolean(b.charging);
        setMyBattery({ level: batLevel, charging: isCharging });
      } catch {
        // Battery API not permitted
      }
    }

    try {
      await api.post("/mesh/telemetry", {
        device_id: myDeviceId,
        device_name: isMobileClient ? "Mobile Companion" : "Workstation Browser",
        device_type: isMobileClient ? "phone_mobile" : "laptop_windows",
        battery_level: batLevel,
        is_charging: isCharging,
      });
    } catch {
      // Background retry
    }
  };

  // 2. Fetch Mesh state (laptop host + paired devices)
  const loadMeshState = async () => {
    try {
      const res = await api.get<{
        laptop_host: LaptopHostInfo;
        paired_devices: PairedDevice[];
      }>("/mesh/pair/devices");

      if (res.laptop_host) {
        setLaptopHost(res.laptop_host);
        if (typeof res.laptop_host.is_locked === "boolean") {
          setIsLaptopLocked(res.laptop_host.is_locked);
        }
      }
      if (res.paired_devices) {
        setPairedDevices(res.paired_devices);
      }
    } catch {
      // Ignore background fetch error
    }
  };

  // 3. Poll for incoming remote commands (PING, LOCK, UNLOCK, etc.)
  const pollIncomingRelay = async () => {
    try {
      const res = await api.get<{
        messages: {
          id: number;
          msg_type: string;
          sender_device_id: string;
          payload: Record<string, unknown>;
        }[];
      }>(`/mesh/relay/poll?device_id=${encodeURIComponent(myDeviceId)}`);

      if (res.messages && res.messages.length > 0) {
        for (const msg of res.messages) {
          if (msg.msg_type === "REMOTE_COMMAND") {
            const cmd = msg.payload?.command;
            if (cmd === "PING_PHONE" || cmd === "RING_PHONE" || cmd === "PING_ALERT") {
              playChime(950);
              if (typeof navigator !== "undefined" && "vibrate" in navigator) {
                navigator.vibrate([200, 100, 200, 100, 300]);
              }
              setStatusMsg("🔔 Inbound ping received from Laptop!");
              setTimeout(() => setStatusMsg(""), 5000);
            } else if (cmd === "LOCK_PHONE") {
              setIsPhoneLocked(true);
              setStatusMsg("🔒 Screen locked remotely by Laptop.");
            } else if (cmd === "UNLOCK_PHONE") {
              setIsPhoneLocked(false);
              playChime(1050);
              setStatusMsg("🔓 Phone unlocked remotely by Laptop!");
              setTimeout(() => setStatusMsg(""), 4000);
            } else if (cmd === "LAUNCH_APP") {
              const app = (msg.payload?.app as string) || "";
              if (app) launchPhoneApp(app);
            }
          } else if (msg.msg_type === "LAUNCH_APP") {
            const app = (msg.payload?.app as string) || "";
            if (app) launchPhoneApp(app);
          } else if (msg.msg_type === "CLIPBOARD_SYNC") {
            const text = String(msg.payload?.text || "");
            if (text) {
              setReceivedNotes((prev) => [text, ...prev.slice(0, 4)]);
              setStatusMsg(`💬 Received note: "${text.substring(0, 30)}"`);
              playChime(660);
              setTimeout(() => setStatusMsg(""), 4000);
            }
          }
        }
      }
    } catch {
      // Ignore background poll error
    }
  };

  // Lifecycle loops
  useEffect(() => {
    reportLocalTelemetry();
    loadMeshState();
    handleGeneratePairCode();

    const telemetryInterval = setInterval(reportLocalTelemetry, 10000);
    const meshInterval = setInterval(loadMeshState, 3000);
    const relayInterval = setInterval(pollIncomingRelay, 2500);

    return () => {
      clearInterval(telemetryInterval);
      clearInterval(meshInterval);
      clearInterval(relayInterval);
    };
  }, [myDeviceId]);

  // Action: Lock Windows Laptop
  const handleLockLaptop = async () => {
    setIsLoading(true);
    try {
      await api.post("/mesh/command", {
        command: "LOCK_PC",
        parameters: { mode: "shield" },
      });
      setIsLaptopLocked(true);
      setStatusMsg("🔒 Sovereign Privacy Shield engaged: Laptop display locked!");
      setTimeout(() => setStatusMsg(""), 4000);
    } catch {
      setStatusMsg("Failed to send lock command.");
    } finally {
      setIsLoading(false);
    }
  };

  // Open password prompt modal
  const handleOpenUnlockModal = () => {
    setInputPassword(savedPassword);
    setIsUnlockModalOpen(true);
  };

  // Submit unlock with entered password
  const handleConfirmUnlock = async (pwdOverride?: string) => {
    const pwd = pwdOverride !== undefined ? pwdOverride : inputPassword;
    setIsLoading(true);
    setIsUnlockModalOpen(false);

    if (rememberPassword && pwd) {
      setSavedPassword(pwd);
      localStorage.setItem("iris_laptop_pwd", pwd);
    }

    try {
      const res = await api.post<{
        command: string;
        executed?: { success: boolean; error?: string; message?: string } | boolean;
      }>("/mesh/command", {
        command: "UNLOCK_PC",
        parameters: {
          pin: pwd.trim() || undefined,
          password: pwd.trim() || undefined,
        },
      });

      if (res && typeof res.executed === "object" && res.executed.success === false) {
        setStatusMsg(`❌ Unlock failed: ${res.executed.error || "Incorrect password"}`);
        setIsLaptopLocked(true);
        setTimeout(() => setStatusMsg(""), 4500);
        return;
      }

      setIsLaptopLocked(false);
      setStatusMsg("🔓 Sovereign Privacy Shield unlocked successfully!");
      setTimeout(() => setStatusMsg(""), 4500);
    } catch {
      setStatusMsg("Failed to send unlock command.");
    } finally {
      setIsLoading(false);
    }
  };

  // Action: Ping Windows Laptop (Audible chime)
  const handlePingLaptop = async () => {
    setIsLoading(true);
    try {
      await api.post("/mesh/command", { command: "PING_LAPTOP" });
      setStatusMsg("🔔 Playing alert chime on laptop!");
      setTimeout(() => setStatusMsg(""), 4000);
    } catch {
      setStatusMsg("Failed to ping laptop.");
    } finally {
      setIsLoading(false);
    }
  };

  // Action: Ring / Ping Phone
  const handlePingPhone = async () => {
    setIsLoading(true);
    try {
      await api.post("/mesh/command", {
        command: "PING_PHONE",
        target_device: primaryPhone?.device_id || null,
      });
      setStatusMsg("🔔 Ping chime sent to phone!");
      setTimeout(() => setStatusMsg(""), 4000);
    } catch {
      setStatusMsg("Failed to ring phone.");
    } finally {
      setIsLoading(false);
    }
  };

  // Action: Lock Phone Screen
  const handleLockPhone = async () => {
    setIsLoading(true);
    try {
      await api.post("/mesh/command", {
        command: "LOCK_PHONE",
        target_device: primaryPhone?.device_id || null,
      });
      setIsPhoneRemotelyLocked(true);
      setStatusMsg("🔒 Lock signal sent to phone!");
      setTimeout(() => setStatusMsg(""), 4000);
    } catch {
      setStatusMsg("Failed to lock phone.");
    } finally {
      setIsLoading(false);
    }
  };

  // Action: Unlock Phone Screen
  const handleUnlockPhone = async () => {
    setIsLoading(true);
    try {
      await api.post("/mesh/command", {
        command: "UNLOCK_PHONE",
        target_device: primaryPhone?.device_id || null,
      });
      setIsPhoneRemotelyLocked(false);
      setStatusMsg("🔓 Unlock signal sent to phone!");
      setTimeout(() => setStatusMsg(""), 4000);
    } catch {
      setStatusMsg("Failed to unlock phone.");
    } finally {
      setIsLoading(false);
    }
  };

  // Action: Send Quick Note
  const handleSendNote = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!quickNote.trim()) return;
    try {
      await api.post("/mesh/clipboard", {
        text: quickNote,
        sender_device: myDeviceId,
      });
      setStatusMsg(`💬 Sent note: "${quickNote.substring(0, 24)}..."`);
      setQuickNote("");
      setTimeout(() => setStatusMsg(""), 3000);
    } catch {
      setStatusMsg("Failed to send note.");
    }
  };

  // Action: Generate 6-Digit Pairing PIN
  const handleGeneratePairCode = async () => {
    setIsGeneratingCode(true);
    try {
      const res = await api.post<{ pairing_code: string; token?: string }>("/mesh/pair/code", {
        device_id: myDeviceId,
        device_name: "Mobile Phone",
        device_type: "phone_mobile",
      });
      setPairingCode(res.pairing_code);

      if (res.token) {
        const pollToken = res.token;
        const interval = setInterval(async () => {
          try {
            const statusRes = await api.get<{ status: string; pairing_token?: string }>(
              `/mesh/pair/status?token=${encodeURIComponent(pollToken)}&device_id=${encodeURIComponent(myDeviceId)}`
            );
            if (statusRes.status === "paired") {
              clearInterval(interval);
              if (statusRes.pairing_token) {
                localStorage.setItem("iris_pair_token", statusRes.pairing_token);
              }
              setStatusMsg("✨ Connected to laptop permanently!");
              loadMeshState();
            }
          } catch {
            // ignore
          }
        }, 1500);
      }
    } catch {
      setStatusMsg("Failed to generate code.");
    } finally {
      setIsGeneratingCode(false);
    }
  };

  // Render battery gauge helper
  const renderBatteryGauge = (percent: number | null | undefined, isCharging: boolean | null | undefined) => {
    const pct = percent != null ? Math.max(0, Math.min(100, percent)) : null;
    return (
      <div className="flex items-center gap-3">
        <div className="relative flex items-center">
          <div className="h-7 w-14 rounded-md border-2 border-ops-line-bright bg-ops-ground p-0.5 flex items-center">
            {pct != null ? (
              <div
                className={cn(
                  "h-full rounded-sm transition-all duration-500",
                  pct > 40
                    ? "bg-emerald-500"
                    : pct > 15
                    ? "bg-amber-400"
                    : "bg-red-500"
                )}
                style={{ width: `${pct}%` }}
              />
            ) : (
              <div className="w-full text-center text-[10px] text-ink-faint">--</div>
            )}
          </div>
          <div className="h-3 w-1 rounded-r-sm bg-ops-line-bright" />
          {isCharging && (
            <div className="absolute inset-0 flex items-center justify-center text-emerald-400 drop-shadow">
              <Zap size={14} className="fill-emerald-400" />
            </div>
          )}
        </div>

        <div>
          <div className="flex items-center gap-1.5">
            <span className="text-2xl font-bold tracking-tight text-ink">
              {pct != null ? `${pct}%` : "AC Power"}
            </span>
            {isCharging && (
              <span className="inline-flex items-center gap-1 rounded bg-emerald-500/15 px-1.5 py-0.5 text-[11px] font-medium text-emerald-400">
                <Zap size={10} className="fill-emerald-400" /> Charging
              </span>
            )}
          </div>
          <p className="text-[11px] text-ink-faint">
            {isCharging
              ? "Plugged in & Charging"
              : pct != null
              ? "Running on Battery"
              : "Desktop / Constant Power"}
          </p>
        </div>
      </div>
    );
  };

  return (
    <div className="mx-auto w-full max-w-3xl space-y-6 pb-20 pt-2 animate-fade-in">
      {/* Remote Phone Lock Overlay */}
      {isPhoneLocked && (
        <div className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-black/90 p-6 text-center backdrop-blur-md">
          <div className="mb-4 rounded-full bg-red-500/20 p-5 text-red-400 ring-2 ring-red-500/50">
            <Lock size={40} />
          </div>
          <h2 className="text-2xl font-bold text-white">Device Locked Remotely</h2>
          <p className="mt-2 max-w-xs text-sm text-ink-faint">
            This screen was locked from your connected Windows laptop via Sovereign Mesh.
          </p>
          <div className="mt-8">
            <Button
              onClick={() => setIsPhoneLocked(false)}
              className="bg-emerald-600 hover:bg-emerald-500 text-white font-medium px-6 py-2.5 rounded-xl shadow-lg"
            >
              <Unlock size={16} className="mr-2" /> Unlock Screen
            </Button>
          </div>
        </div>
      )}

      {/* Remote Laptop Unlock Password Prompt Modal */}
      {isUnlockModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-sm rounded-2xl border border-ops-line-bright bg-ops-panel p-6 shadow-2xl">
            <div className="flex items-center gap-3 mb-4">
              <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-emerald-500/15 text-emerald-400 border border-emerald-500/25">
                <KeyRound size={22} />
              </div>
              <div>
                <h3 className="text-base font-semibold text-ink">Unlock Windows Laptop</h3>
                <p className="text-xs text-ink-faint">Enter your Windows PIN or password</p>
              </div>
            </div>

            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleConfirmUnlock();
              }}
              className="space-y-4"
            >
              <div>
                <label className="text-xs font-medium text-ink block mb-1.5">
                  Laptop Password / PIN
                </label>
                <div className="relative">
                  <input
                    type={showPassword ? "text" : "password"}
                    value={inputPassword}
                    onChange={(e) => setInputPassword(e.target.value)}
                    placeholder="Enter Windows PIN / Password"
                    autoFocus
                    className="w-full rounded-xl border border-ops-line bg-ops-surface px-3.5 py-2.5 pr-10 text-sm text-ink placeholder:text-ink-faint focus:border-ops-accent focus:outline-none"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((s) => !s)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-ink-faint hover:text-ink"
                    tabIndex={-1}
                  >
                    {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>
                <p className="mt-1.5 text-[11px] text-ink-faint">
                  IRIS will verify your credentials and dismiss the Sovereign Privacy Shield instantly.
                </p>
              </div>

              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="rememberPwd"
                  checked={rememberPassword}
                  onChange={(e) => setRememberPassword(e.target.checked)}
                  className="rounded border-ops-line text-emerald-500 focus:ring-0"
                />
                <label htmlFor="rememberPwd" className="text-xs text-ink-faint cursor-pointer">
                  Remember on this phone for quick unlock
                </label>
              </div>

              <div className="flex gap-2 pt-2">
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => setIsUnlockModalOpen(false)}
                  className="flex-1 justify-center rounded-xl py-2.5 text-xs text-ink-faint"
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  disabled={isLoading}
                  className="flex-1 justify-center bg-emerald-600 hover:bg-emerald-500 text-white font-medium rounded-xl py-2.5 text-xs shadow-md"
                >
                  <Unlock size={14} className="mr-1.5" /> Unlock Laptop
                </Button>
              </div>

              <div className="border-t border-ops-line/60 pt-3 text-center">
                <button
                  type="button"
                  onClick={() => handleConfirmUnlock("")}
                  className="text-[11px] text-ink-faint hover:text-ink underline"
                >
                  Just wake monitor without password
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Top Header & Switcher */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between border-b border-ops-line pb-4">
        <div>
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-ops-accent/15 text-ops-accent">
              <Radio size={18} />
            </div>
            <h1 className="text-xl font-semibold tracking-tight text-ink">Continuity Hub</h1>
          </div>
          <p className="mt-1 text-xs text-ink-faint">
            Live hardware telemetry, battery sync, and secure remote control between Phone and Laptop.
          </p>
        </div>

        {/* View Switch Segmented Control */}
        <div className="flex items-center gap-1 rounded-xl border border-ops-line bg-ops-surface p-1">
          <button
            onClick={() => {
              setView("laptop");
              navigate("/laptop");
            }}
            className={cn(
              "flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-all",
              view === "laptop"
                ? "bg-ops-raised text-ink shadow-sm"
                : "text-ink-faint hover:text-ink"
            )}
          >
            <Laptop size={14} />
            <span>Laptop View</span>
          </button>
          <button
            onClick={() => {
              setView("phone");
              navigate("/phone");
            }}
            className={cn(
              "flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-all",
              view === "phone"
                ? "bg-ops-raised text-ink shadow-sm"
                : "text-ink-faint hover:text-ink"
            )}
          >
            <Smartphone size={14} />
            <span>Phone View</span>
          </button>
          <button
            onClick={() => {
              reportLocalTelemetry();
              loadMeshState();
              setStatusMsg("Telemetry refreshed.");
              setTimeout(() => setStatusMsg(""), 2000);
            }}
            title="Refresh connection status"
            className="rounded-lg p-1.5 text-ink-faint hover:bg-ops-raised hover:text-ink"
          >
            <RefreshCw size={13} />
          </button>
        </div>
      </div>

      {/* Status Feedback Banner */}
      {statusMsg && (
        <div className="flex items-center justify-between rounded-xl border border-ops-accent/30 bg-ops-accent/10 px-4 py-2.5 text-xs font-medium text-ops-accent shadow-sm animate-slide-down">
          <span>{statusMsg}</span>
          <button onClick={() => setStatusMsg("")} className="text-ops-accent/70 hover:text-ops-accent">
            ✕
          </button>
        </div>
      )}

      {/* MAIN VIEW: MOBILE PERSPECTIVE (Looking at Laptop) */}
      {view === "laptop" && (
        <div className="space-y-6">
          {/* Primary Card: Windows Laptop */}
          <Panel className="relative overflow-hidden border-ops-line-bright bg-ops-panel p-6 shadow-md">
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-3">
                <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-ops-raised text-ink border border-ops-line">
                  <Laptop size={24} />
                </div>
                <div>
                  <h2 className="text-base font-semibold text-ink">
                    {laptopHost?.device_name || "Windows Laptop"}
                  </h2>
                  <div className="mt-1 flex items-center gap-2">
                    {laptopHost?.is_online ? (
                      <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-500/15 px-2.5 py-0.5 text-[11px] font-semibold text-emerald-400">
                        <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
                        Windows Host Online
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1.5 rounded-full bg-zinc-700/40 px-2.5 py-0.5 text-[11px] font-medium text-zinc-400">
                        <span className="h-1.5 w-1.5 rounded-full bg-zinc-500" />
                        Laptop Waiting / Sleeping
                      </span>
                    )}
                    <span className="text-[11px] text-ink-faint">Sovereign Relay</span>
                  </div>
                </div>
              </div>

              <span className="text-[11px] text-ink-faint hidden sm:inline">
                {laptopHost?.last_seen_at ? "Active now" : "Background Daemon"}
              </span>
            </div>

            {/* Phone Pairing PIN Card (Shown on mobile for easy one-time pairing) */}
            <div className="mt-5 rounded-2xl border border-ai/30 bg-ai/5 p-4 text-center">
              <div className="flex items-center justify-center gap-2 text-ink font-semibold text-[13px]">
                <Smartphone size={16} className="text-ai" />
                <span>Phone Pairing PIN</span>
              </div>
              <p className="text-[12px] text-ink-dim mt-1 max-w-sm mx-auto">
                Enter this 6-digit PIN on your Laptop at <span className="text-ink font-medium">Settings &rarr; Mesh</span>:
              </p>

              {pairingCode ? (
                <div className="mt-2.5 space-y-2">
                  <div className="font-mono text-[36px] font-black tracking-[0.25em] text-ink py-1">
                    {pairingCode}
                  </div>
                  <div className="flex items-center justify-center gap-1.5 text-[11px] text-go font-medium animate-pulse">
                    <div className="h-2 w-2 rounded-full bg-go" />
                    <span>Waiting for laptop to enter PIN...</span>
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleGeneratePairCode}
                    className="mt-1 text-[11px]"
                  >
                    🔄 Refresh PIN
                  </Button>
                </div>
              ) : (
                <div className="py-4 text-[12px] text-ink-dim animate-pulse">
                  Generating 6-digit PIN...
                </div>
              )}
            </div>

            {/* Laptop Battery Section */}
            <div className="mt-6 rounded-2xl border border-ops-line bg-ops-surface/80 p-4">
              <p className="text-[11px] uppercase tracking-wider text-ink-faint font-semibold mb-3">
                Laptop Power & Battery
              </p>
              {renderBatteryGauge(laptopHost?.battery_level, laptopHost?.is_charging)}
            </div>

            {/* Laptop Remote Controls */}
            <div className="mt-6">
              <p className="text-[11px] uppercase tracking-wider text-ink-faint font-semibold mb-3">
                Remote Controls
              </p>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {isLaptopLocked ? (
                  <Button
                    onClick={handleOpenUnlockModal}
                    disabled={isLoading}
                    className="w-full justify-center bg-emerald-600 hover:bg-emerald-500 text-white py-3 rounded-xl font-medium shadow-md transition-transform active:scale-[0.98]"
                  >
                    <Unlock size={16} className="mr-2" />
                    Unlock Laptop
                  </Button>
                ) : (
                  <Button
                    onClick={handleLockLaptop}
                    disabled={isLoading}
                    className="w-full justify-center bg-ops-raised hover:bg-ops-surface text-ink border border-ops-line py-3 rounded-xl font-medium"
                  >
                    <Lock size={16} className="mr-2 text-amber-400" />
                    Lock Laptop Screen
                  </Button>
                )}

                <Button
                  onClick={handlePingLaptop}
                  disabled={isLoading}
                  className="w-full justify-center bg-ops-raised hover:bg-ops-surface text-ink border border-ops-line py-3 rounded-xl font-medium"
                >
                  <Volume2 size={16} className="mr-2 text-emerald-400" />
                  Ping Laptop (Play Sound)
                </Button>
              </div>

              {/* Quick option to unlock even if status was already unlocked */}
              {!isLaptopLocked && (
                <div className="mt-2.5 text-center">
                  <button
                    type="button"
                    onClick={handleOpenUnlockModal}
                    className="inline-flex items-center gap-1.5 text-xs text-ops-accent hover:underline font-medium"
                  >
                    <Unlock size={13} /> Unlock Laptop with Password
                  </button>
                </div>
              )}

              {/* IRIS Voice & Chat Controlled Station Callout */}
              <div className="mt-5 rounded-2xl border border-ops-line bg-ops-surface/60 p-4">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-ops-accent/15 text-ops-accent shrink-0">
                    <Sparkles size={20} />
                  </div>
                  <div>
                    <h4 className="text-xs font-semibold text-ink">Voice & Chat Controlled Station</h4>
                    <p className="text-[11px] text-ink-faint">
                      Ask IRIS anytime via voice or chat to <span className="text-ink font-medium">"Open Antigravity IDE"</span>, <span className="text-ink font-medium">"Surf files"</span>, or run commands on your laptop remotely.
                    </p>
                  </div>
                </div>
              </div>
            </div>

            {/* Quick Note to Laptop */}
            <form onSubmit={handleSendNote} className="mt-5 flex gap-2">
              <input
                type="text"
                value={quickNote}
                onChange={(e) => setQuickNote(e.target.value)}
                placeholder="Send a quick note or link to laptop..."
                className="flex-1 rounded-xl border border-ops-line bg-ops-surface px-3.5 py-2 text-xs text-ink placeholder:text-ink-faint focus:border-ops-accent focus:outline-none"
              />
              <Button type="submit" className="rounded-xl px-4 text-xs font-medium">
                <Send size={13} className="mr-1.5" /> Send
              </Button>
            </form>
          </Panel>

          {/* Secondary Card: This Mobile Phone */}
          <Panel className="border-ops-line bg-ops-surface/60 p-5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-ops-raised text-ink">
                  <Smartphone size={20} />
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-ink">This Mobile Phone</h3>
                  <p className="text-[11px] text-ink-faint">
                    {myDeviceId} • Reporting live telemetry
                  </p>
                </div>
              </div>

              <div className="text-right">
                <div className="flex items-center gap-1.5 justify-end">
                  <span className="text-sm font-bold text-ink">
                    {myBattery.level != null ? `${myBattery.level}%` : "Reporting"}
                  </span>
                  {myBattery.charging && <Zap size={13} className="text-emerald-400 fill-emerald-400" />}
                </div>
                <span className="inline-flex items-center gap-1 text-[10px] text-emerald-400">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                  Broadcasting
                </span>
              </div>
            </div>
          </Panel>
        </div>
      )}

      {/* MAIN VIEW: LAPTOP PERSPECTIVE (Looking at Phone) */}
      {view === "phone" && (
        <div className="space-y-6">
          {/* Primary Card: Mobile Phone */}
          <Panel className="relative overflow-hidden border-ops-line-bright bg-ops-panel p-6 shadow-md">
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-3">
                <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-ops-raised text-ink border border-ops-line">
                  <Smartphone size={24} />
                </div>
                <div>
                  <h2 className="text-base font-semibold text-ink">
                    {primaryPhone?.device_name || "Mobile Phone"}
                  </h2>
                  <div className="mt-1 flex items-center gap-2">
                    {primaryPhone?.is_online ? (
                      <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-500/15 px-2.5 py-0.5 text-[11px] font-semibold text-emerald-400">
                        <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
                        Phone Online & Active
                      </span>
                    ) : primaryPhone ? (
                      <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-500/15 px-2.5 py-0.5 text-[11px] font-medium text-amber-400">
                        <span className="h-1.5 w-1.5 rounded-full bg-amber-400" />
                        Phone Idle / Connected
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1.5 rounded-full bg-zinc-700/40 px-2.5 py-0.5 text-[11px] font-medium text-zinc-400">
                        No Paired Phone
                      </span>
                    )}
                    <span className="text-[11px] text-ink-faint">5G / Wi-Fi Mesh</span>
                  </div>
                </div>
              </div>

              {primaryPhone && (
                <span className="text-[11px] text-ink-faint hidden sm:inline">
                  {primaryPhone.device_id}
                </span>
              )}
            </div>

            {/* Phone Battery Section */}
            <div className="mt-6 rounded-2xl border border-ops-line bg-ops-surface/80 p-4">
              <p className="text-[11px] uppercase tracking-wider text-ink-faint font-semibold mb-3">
                Phone Power & Battery
              </p>
              {primaryPhone ? (
                renderBatteryGauge(primaryPhone.battery_level, primaryPhone.is_charging)
              ) : (
                <div className="py-2 text-xs text-ink-faint">
                  Pair a phone below to monitor its live battery and charging state.
                </div>
              )}
            </div>

            {/* Phone Remote Controls */}
            {primaryPhone && (
              <div className="mt-6">
                <p className="text-[11px] uppercase tracking-wider text-ink-faint font-semibold mb-3">
                  Remote Actions
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <Button
                    onClick={handlePingPhone}
                    disabled={isLoading}
                    className="w-full justify-center bg-ops-raised hover:bg-ops-surface text-ink border border-ops-line py-3 rounded-xl font-medium"
                  >
                    <Bell size={16} className="mr-2 text-emerald-400" />
                    Ring / Ping Phone
                  </Button>

                  {isPhoneRemotelyLocked ? (
                    <Button
                      onClick={handleUnlockPhone}
                      disabled={isLoading}
                      className="w-full justify-center bg-emerald-600 hover:bg-emerald-500 text-white py-3 rounded-xl font-medium shadow-md"
                    >
                      <Unlock size={16} className="mr-2" />
                      Unlock Phone Screen
                    </Button>
                  ) : (
                    <Button
                      onClick={handleLockPhone}
                      disabled={isLoading}
                      className="w-full justify-center bg-ops-raised hover:bg-ops-surface text-ink border border-ops-line py-3 rounded-xl font-medium"
                    >
                      <Lock size={16} className="mr-2 text-amber-400" />
                      Lock Phone Screen
                    </Button>
                  )}
                </div>
              </div>
            )}

            {/* Quick Note to Phone */}
            <form onSubmit={handleSendNote} className="mt-5 flex gap-2">
              <input
                type="text"
                value={quickNote}
                onChange={(e) => setQuickNote(e.target.value)}
                placeholder="Send a quick note or link to phone..."
                className="flex-1 rounded-xl border border-ops-line bg-ops-surface px-3.5 py-2 text-xs text-ink placeholder:text-ink-faint focus:border-ops-accent focus:outline-none"
              />
              <Button type="submit" className="rounded-xl px-4 text-xs font-medium">
                <Send size={13} className="mr-1.5" /> Send
              </Button>
            </form>
          </Panel>

          {/* Secondary Card: This Windows Laptop */}
          <Panel className="border-ops-line bg-ops-surface/60 p-5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-ops-raised text-ink">
                  <Laptop size={20} />
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-ink">
                    {laptopHost?.device_name || "Windows Laptop (Host)"}
                  </h3>
                  <p className="text-[11px] text-ink-faint">
                    Local Machine • Daemon Active
                  </p>
                </div>
              </div>

              <div className="text-right">
                <div className="flex items-center gap-1.5 justify-end">
                  <span className="text-sm font-bold text-ink">
                    {laptopHost?.battery_level != null ? `${laptopHost.battery_level}%` : "AC Power"}
                  </span>
                  {laptopHost?.is_charging && <Zap size={13} className="text-emerald-400 fill-emerald-400" />}
                </div>
                <span className="inline-flex items-center gap-1 text-[10px] text-emerald-400">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                  Host Online
                </span>
              </div>
            </div>
          </Panel>

          {/* Pairing Code Card (if user wants to link new device) */}
          {!primaryPhone && (
            <Panel className="border-dashed border-ops-line-bright bg-ops-surface/30 p-6 text-center">
              <h3 className="text-sm font-semibold text-ink">Connect Your Phone</h3>
              <p className="mt-1 text-xs text-ink-faint max-w-sm mx-auto">
                Generate a 6-digit sovereign pairing PIN to link your mobile phone directly.
              </p>

              {pairingCode ? (
                <div className="mt-4 flex flex-col items-center">
                  <div className="rounded-xl border border-ops-accent/40 bg-ops-accent/10 px-6 py-3 font-mono text-2xl font-bold tracking-[0.3em] text-ops-accent">
                    {pairingCode}
                  </div>
                  <p className="mt-2 text-[11px] text-ink-faint">
                    Open <span className="text-ink">https://irisai.runs-on.dev</span> on your phone and enter this PIN.
                  </p>
                </div>
              ) : (
                <Button
                  onClick={handleGeneratePairCode}
                  disabled={isGeneratingCode}
                  className="mt-4 text-xs font-medium rounded-xl px-5"
                >
                  Generate 6-Digit PIN
                </Button>
              )}
            </Panel>
          )}
        </div>
      )}

      {/* Inbound Notes Stream (Recent communication) */}
      {receivedNotes.length > 0 && (
        <Panel className="border-ops-line bg-ops-surface/40 p-4">
          <div className="flex items-center gap-2 mb-2">
            <MessageSquare size={14} className="text-ink-faint" />
            <h4 className="text-xs font-semibold text-ink uppercase tracking-wider">
              Recent Inbound Notes
            </h4>
          </div>
          <div className="space-y-1.5">
            {receivedNotes.map((note, idx) => (
              <div
                key={idx}
                className="flex items-center justify-between rounded-lg bg-ops-raised/60 px-3 py-2 text-xs text-ink border border-ops-line/50"
              >
                <span>{note}</span>
                <button
                  onClick={() => {
                    navigator.clipboard.writeText(note);
                    setStatusMsg("Copied note to clipboard.");
                    setTimeout(() => setStatusMsg(""), 2000);
                  }}
                  className="text-ink-faint hover:text-ink ml-2"
                  title="Copy"
                >
                  <Copy size={12} />
                </button>
              </div>
            ))}
          </div>
        </Panel>
      )}
    </div>
  );
}
