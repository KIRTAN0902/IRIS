import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import {
  Bell,
  Check,
  Copy,
  Download,
  HardDrive,
  Keyboard,
  Laptop,
  Lock,
  Maximize2,
  Mic,
  Minimize2,
  MousePointer,
  Pause,
  Play,
  RefreshCw,
  Send,
  Settings,
  Smartphone,
  Terminal,
  Trash2,
  Upload,
  Zap,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Panel, Lamp } from "@/components/ui/Panel";
import { api } from "@/api/client";
import { cn } from "@/lib/format";

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

interface VaultFile {
  name: string;
  size: number;
  url: string;
}

interface ContinuityPageProps {
  initialView?: "laptop" | "phone";
}

export function ContinuityPage({ initialView }: ContinuityPageProps) {
  const location = useLocation();
  const navigate = useNavigate();

  // Determine current active view:
  // If route is /laptop -> laptop; if /phone -> phone; otherwise detect or use initialView.
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

  // Data state
  const [pairedDevices, setPairedDevices] = useState<PairedDevice[]>([]);
  const [hostPower, setHostPower] = useState<HostPower | null>(null);
  const [hostOnline, setHostOnline] = useState<boolean>(true);
  const [clipboard, setClipboard] = useState("");
  const [newClip, setNewClip] = useState("");
  const [vaultFiles, setVaultFiles] = useState<VaultFile[]>([]);
  const [statusMsg, setStatusMsg] = useState("");
  const [copied, setCopied] = useState(false);

  // Screen streaming state
  const [isStreaming, setIsStreaming] = useState(true);
  const [snapshotTimestamp, setSnapshotTimestamp] = useState(Date.now());
  const [streamFullscreen, setStreamFullscreen] = useState(false);
  const [clickMode, setClickMode] = useState<"left" | "right">("left");
  const [clickRipple, setClickRipple] = useState<{ x: number; y: number } | null>(null);
  const screenImgRef = useRef<HTMLImageElement>(null);

  // Keyboard state
  const [keyInput, setKeyInput] = useState("");
  const [showKeyboardDrawer, setShowKeyboardDrawer] = useState(false);

  // Terminal state
  const [terminalCmd, setTerminalCmd] = useState("");
  const [terminalHistory, setTerminalHistory] = useState<
    { cmd: string; stdout: string; stderr: string; returncode: number; timestamp: string }[]
  >([
    {
      cmd: "Get-Location",
      stdout: "Path\n----\nC:\\kirtan\\IRIS",
      stderr: "",
      returncode: 0,
      timestamp: new Date().toLocaleTimeString(),
    },
  ]);
  const [isExecutingCmd, setIsExecutingCmd] = useState(false);
  const [isListeningVoice, setIsListeningVoice] = useState(false);
  const terminalBottomRef = useRef<HTMLDivElement>(null);

  // Polling data
  const loadData = async () => {
    try {
      const [devRes, pairRes, clipRes, filesRes] = await Promise.allSettled([
        api.get<{ host_power: HostPower | null; host_online?: boolean }>("/mesh/devices"),
        api.get<{ paired_devices: PairedDevice[] }>("/mesh/pair/devices"),
        api.get<{ text: string }>("/mesh/clipboard"),
        api.get<{ files: VaultFile[] }>("/mesh/files"),
      ]);

      if (devRes.status === "fulfilled") {
        setHostPower(devRes.value.host_power);
        if (devRes.value.host_online !== undefined) {
          setHostOnline(devRes.value.host_online);
        }
      }
      if (pairRes.status === "fulfilled") {
        setPairedDevices(pairRes.value.paired_devices || []);
      }
      if (clipRes.status === "fulfilled") {
        setClipboard(clipRes.value.text || "");
      }
      if (filesRes.status === "fulfilled") {
        setVaultFiles(filesRes.value.files || []);
      }
    } catch {
      // background refresh
    }
  };

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 4000);
    return () => clearInterval(interval);
  }, []);

  // Screen snapshot loop
  useEffect(() => {
    if (!isStreaming || view !== "laptop") return;
    const interval = setInterval(() => {
      setSnapshotTimestamp(Date.now());
    }, 400);
    return () => clearInterval(interval);
  }, [isStreaming, view]);

  // Mouse click on desktop stream
  const handleScreenClick = async (e: React.MouseEvent<HTMLImageElement>) => {
    if (!screenImgRef.current) return;
    const rect = screenImgRef.current.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const clickY = e.clientY - rect.top;
    const xRatio = Math.max(0, Math.min(1, clickX / rect.width));
    const yRatio = Math.max(0, Math.min(1, clickY / rect.height));

    setClickRipple({ x: clickX, y: clickY });
    setTimeout(() => setClickRipple(null), 400);

    try {
      await api.post("/mesh/screen/input/mouse", {
        action: "click",
        x: xRatio,
        y: yRatio,
        button: clickMode,
      });
      // Trigger snapshot refresh right after click to see feedback immediately
      setTimeout(() => setSnapshotTimestamp(Date.now()), 150);
    } catch {
      // ignore
    }
  };

  // Keyboard typing
  const handleSendText = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!keyInput) return;
    try {
      await api.post("/mesh/screen/input/keyboard", { text: keyInput });
      setKeyInput("");
      setStatusMsg("Sent text to laptop.");
      setTimeout(() => setStatusMsg(""), 2000);
      setTimeout(() => setSnapshotTimestamp(Date.now()), 200);
    } catch {
      setStatusMsg("Failed to send text.");
    }
  };

  const handleSendSpecialKey = async (key: string) => {
    try {
      await api.post("/mesh/screen/input/keyboard", { key });
      setStatusMsg(`Sent [${key.toUpperCase()}] key`);
      setTimeout(() => setStatusMsg(""), 1500);
      setTimeout(() => setSnapshotTimestamp(Date.now()), 200);
    } catch {
      // ignore
    }
  };

  // Clipboard sync
  const handleCopyClipboard = async () => {
    if (!clipboard) return;
    await navigator.clipboard.writeText(clipboard);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handlePushClipboard = async () => {
    if (!newClip.trim()) return;
    try {
      await api.post("/mesh/clipboard", {
        text: newClip,
        sender_device: view === "laptop" ? "remote_mobile" : "laptop_web",
      });
      setClipboard(newClip);
      setNewClip("");
      setStatusMsg("Synced to Universal Clipboard!");
      setTimeout(() => setStatusMsg(""), 3000);
    } catch {
      setStatusMsg("Failed to sync clipboard");
    }
  };

  // Lock Workstation
  const handleLockPC = async () => {
    if (!window.confirm("Lock Windows workstation now?")) return;
    try {
      await api.post("/mesh/command", { command: "LOCK_PC" });
      setStatusMsg("Windows Workstation locked.");
      setTimeout(() => setStatusMsg(""), 3000);
    } catch {
      setStatusMsg("Failed to lock PC");
    }
  };

  // Ring phone
  const handleRingPhone = async () => {
    try {
      await api.post("/mesh/command", { command: "RING_PHONE" });
      setStatusMsg("🚨 Ring chime sent to phone!");
      setTimeout(() => setStatusMsg(""), 4000);
    } catch {
      setStatusMsg("Failed to ring phone");
    }
  };

  // File drop
  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    form.append("sender_device", view === "laptop" ? "mobile_companion" : "laptop_web");
    try {
      await fetch("/api/mesh/files/upload", {
        method: "POST",
        body: form,
      });
      setStatusMsg(`Dropped ${file.name} to File Vault!`);
      loadData();
      setTimeout(() => setStatusMsg(""), 3000);
    } catch {
      setStatusMsg("Failed to upload file");
    }
  };

  // Remote Terminal execution
  const handleExecuteTerminal = async (cmdToRun?: string) => {
    const cmd = (cmdToRun || terminalCmd).trim();
    if (!cmd || isExecutingCmd) return;
    setIsExecutingCmd(true);
    try {
      const res = await api.post<{
        success: boolean;
        returncode: number;
        stdout: string;
        stderr: string;
        command: string;
        cwd: string;
      }>("/mesh/terminal/exec", { command: cmd, working_dir: "C:\\kirtan\\IRIS" });

      setTerminalHistory((prev) => [
        ...prev,
        {
          cmd,
          stdout: res.stdout,
          stderr: res.stderr,
          returncode: res.returncode,
          timestamp: new Date().toLocaleTimeString(),
        },
      ]);
      setTerminalCmd("");
      setTimeout(() => {
        terminalBottomRef.current?.scrollIntoView({ behavior: "smooth" });
      }, 100);
    } catch (err: any) {
      setTerminalHistory((prev) => [
        ...prev,
        {
          cmd,
          stdout: "",
          stderr: err?.message || "Execution error",
          returncode: 1,
          timestamp: new Date().toLocaleTimeString(),
        },
      ]);
    } finally {
      setIsExecutingCmd(false);
    }
  };

  const handleOpenLaptopTerminalGui = async () => {
    try {
      await api.post("/mesh/terminal/open");
      setStatusMsg("💻 Opened Windows Terminal on laptop desktop.");
      setTimeout(() => setStatusMsg(""), 3000);
    } catch {
      setStatusMsg("Failed to open terminal window.");
    }
  };

  const handleToggleVoiceTerminal = () => {
    const SpeechRecognition =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) {
      alert("Speech recognition is not supported in this browser. You can type commands directly.");
      return;
    }
    if (isListeningVoice) {
      setIsListeningVoice(false);
      return;
    }

    try {
      const recognition = new SpeechRecognition();
      recognition.continuous = false;
      recognition.interimResults = false;
      recognition.lang = "en-US";

      recognition.onstart = () => setIsListeningVoice(true);
      recognition.onend = () => setIsListeningVoice(false);
      recognition.onerror = () => setIsListeningVoice(false);
      recognition.onresult = (event: any) => {
        const transcript = event.results[0][0].transcript;
        if (transcript) {
          setTerminalCmd(transcript);
          handleExecuteTerminal(transcript);
        }
      };
      recognition.start();
    } catch {
      setIsListeningVoice(false);
    }
  };

  const primaryPhone = pairedDevices.find((d) => d.device_type === "phone_mobile") || pairedDevices[0];

  return (
    <div className="mx-auto max-w-4xl space-y-6 pb-16">
      {/* Top Header & View Switcher */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            {view === "laptop" ? (
              <Laptop size={26} className="text-ai" />
            ) : (
              <Smartphone size={26} className="text-ai" />
            )}
            <h1 className="text-[26px] font-bold tracking-tight text-ink">
              {view === "laptop" ? "Laptop Continuity" : "Phone Continuity"}
            </h1>
          </div>
          <p className="text-[13px] text-ink-dim">
            {view === "laptop"
              ? "Live screen mirroring, remote touch mouse & keyboard control for your Windows workstation."
              : "Paired mobile companion status, Find My Phone ring alert, and sovereign sync."}
          </p>
        </div>

        {/* View Toggle + Settings Link */}
        <div className="flex items-center gap-2">
          <div className="inline-flex rounded-lg border border-ops-line bg-ops-raised/60 p-1 text-[13px]">
            <button
              onClick={() => {
                setView("laptop");
                navigate("/laptop", { replace: true });
              }}
              className={cn(
                "flex items-center gap-1.5 rounded-md px-3 py-1.5 font-medium transition-colors cursor-pointer",
                view === "laptop"
                  ? "bg-ops-panel text-ink shadow-sm border border-ops-line-bright font-semibold"
                  : "text-ink-dim hover:text-ink",
              )}
            >
              <Laptop size={15} /> 💻 Laptop
            </button>
            <button
              onClick={() => {
                setView("phone");
                navigate("/phone", { replace: true });
              }}
              className={cn(
                "flex items-center gap-1.5 rounded-md px-3 py-1.5 font-medium transition-colors cursor-pointer",
                view === "phone"
                  ? "bg-ops-panel text-ink shadow-sm border border-ops-line-bright font-semibold"
                  : "text-ink-dim hover:text-ink",
              )}
            >
              <Smartphone size={15} /> 📱 Phone
            </button>
          </div>

          <Button
            size="sm"
            variant="outline"
            onClick={() => navigate("/settings?tab=mesh")}
            title="Mesh & Continuity Settings"
          >
            <Settings size={14} />
          </Button>
        </div>
      </div>

      {statusMsg && (
        <div className="rounded-lg bg-ai-dim border border-ai/20 px-4 py-2.5 text-[13px] text-ai font-medium animate-in fade-in">
          {statusMsg}
        </div>
      )}

      {/* ========================================================================= */}
      {/* LAPTOP VIEW                                                               */}
      {/* ========================================================================= */}
      {view === "laptop" && (
        <div className="space-y-6">
          {/* Laptop Status Strip */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="rounded-xl border border-ops-line bg-ops-panel p-3.5 flex items-center justify-between">
              <div>
                <p className="text-[11px] uppercase tracking-wider text-ink-faint font-semibold">Host Workstation</p>
                <p className="text-[14px] font-semibold text-ink flex items-center gap-1.5 mt-0.5">
                  <span
                    className={cn(
                      "h-2 w-2 rounded-full",
                      hostOnline ? "bg-go animate-pulse" : "bg-amber-400",
                    )}
                  />
                  {hostOnline ? "Windows Host Online (5G Relay)" : "Laptop Relay Waiting"}
                </p>
              </div>
              <Laptop size={22} className={cn("opacity-80", hostOnline ? "text-ai" : "text-ink-faint")} />
            </div>

            <div className="rounded-xl border border-ops-line bg-ops-panel p-3.5 flex items-center justify-between">
              <div>
                <p className="text-[11px] uppercase tracking-wider text-ink-faint font-semibold">Battery & AC Power</p>
                <p className="text-[14px] font-semibold text-ink mt-0.5">
                  {hostPower?.percent !== null && hostPower?.percent !== undefined
                    ? `${hostPower.percent}%`
                    : "AC Power"}{" "}
                  <span className="text-[12px] text-ink-dim font-normal">
                    ({hostPower?.ac_status || "Plugged In"})
                  </span>
                </p>
              </div>
              <Zap size={20} className="text-amber-400 opacity-80" />
            </div>

            <div className="rounded-xl border border-ops-line bg-ops-panel p-3.5 flex items-center justify-between">
              <div>
                <p className="text-[11px] uppercase tracking-wider text-ink-faint font-semibold">Security</p>
                <button
                  onClick={handleLockPC}
                  className="mt-1 inline-flex items-center gap-1.5 rounded-md bg-rose-500/15 border border-rose-500/30 px-2.5 py-1 text-[12px] font-medium text-rose-300 hover:bg-rose-500/25 transition-colors cursor-pointer"
                >
                  <Lock size={12} /> Lock Laptop
                </button>
              </div>
              <Button
                size="sm"
                variant="outline"
                onClick={() => setSnapshotTimestamp(Date.now())}
                className="h-8"
                title="Refresh Screen"
              >
                <RefreshCw size={13} />
              </Button>
            </div>
          </div>

          {/* Interactive Remote Desktop Screen Stream */}
          <Panel
            title="Live Desktop Screen Mirroring"
            lamp={<Lamp tone={isStreaming ? "go" : "dim"} pulse={isStreaming} />}
            actions={
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setIsStreaming((s) => !s)}
                  className="flex items-center gap-1 rounded px-2 py-1 text-[11px] font-medium text-ink-dim hover:text-ink hover:bg-ops-raised"
                >
                  {isStreaming ? <Pause size={12} /> : <Play size={12} />}
                  {isStreaming ? "Pause Stream" : "Resume"}
                </button>
                <button
                  onClick={() => setStreamFullscreen((f) => !f)}
                  className="rounded p-1 text-ink-dim hover:text-ink hover:bg-ops-raised"
                  title="Toggle Fullscreen"
                >
                  {streamFullscreen ? <Minimize2 size={13} /> : <Maximize2 size={13} />}
                </button>
              </div>
            }
          >
            <div className="space-y-3 pt-2">
              <div className="flex items-center justify-between text-[12px]">
                <span className="text-ink-dim flex items-center gap-1.5">
                  <MousePointer size={13} className="text-ai" /> Touch/click on screen sends mouse clicks
                </span>
                <div className="flex items-center gap-1 bg-ops-raised/60 rounded-md p-0.5 border border-ops-line">
                  <button
                    onClick={() => setClickMode("left")}
                    className={cn(
                      "px-2 py-0.5 rounded text-[11px] font-medium transition-colors",
                      clickMode === "left" ? "bg-ops-panel text-ink shadow-sm" : "text-ink-faint hover:text-ink",
                    )}
                  >
                    Left Click
                  </button>
                  <button
                    onClick={() => setClickMode("right")}
                    className={cn(
                      "px-2 py-0.5 rounded text-[11px] font-medium transition-colors",
                      clickMode === "right" ? "bg-ops-panel text-ink shadow-sm" : "text-ink-faint hover:text-ink",
                    )}
                  >
                    Right Click
                  </button>
                </div>
              </div>

              {/* Screen Stream Frame */}
              <div
                className={cn(
                  "relative overflow-hidden rounded-xl border border-ops-line-bright bg-black select-none touch-none",
                  streamFullscreen
                    ? "fixed inset-0 z-50 rounded-none border-none flex items-center justify-center bg-black/95 p-2"
                    : "aspect-[16/10] w-full",
                )}
              >
                {streamFullscreen && (
                  <button
                    onClick={() => setStreamFullscreen(false)}
                    className="absolute top-4 right-4 z-50 rounded-full bg-ops-panel/80 p-2.5 text-ink hover:bg-ops-panel border border-ops-line"
                  >
                    <Minimize2 size={18} />
                  </button>
                )}

                <img
                  ref={screenImgRef}
                  src={`/api/mesh/screen/snapshot?quality=75&scale=2&t=${snapshotTimestamp}`}
                  alt="Windows Workstation Screen"
                  onClick={handleScreenClick}
                  className="h-full w-full object-contain cursor-crosshair"
                />

                {/* Visual click feedback ripple */}
                {clickRipple && (
                  <span
                    className="pointer-events-none absolute h-6 w-6 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-ai bg-ai/30 animate-ping"
                    style={{ left: clickRipple.x, top: clickRipple.y }}
                  />
                )}
              </div>

              {/* Touch Control & Keyboard Bar */}
              <div className="space-y-2 pt-1">
                <div className="flex flex-wrap gap-1.5 items-center">
                  <Button
                    size="sm"
                    variant={showKeyboardDrawer ? "solid" : "outline"}
                    onClick={() => setShowKeyboardDrawer((k) => !k)}
                    className="gap-1.5"
                  >
                    <Keyboard size={13} /> {showKeyboardDrawer ? "Hide Keyboard" : "Show Keyboard"}
                  </Button>

                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => handleSendSpecialKey("enter")}
                    className="text-[12px] h-8"
                  >
                    Enter ↵
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => handleSendSpecialKey("backspace")}
                    className="text-[12px] h-8"
                  >
                    Backspace ⌫
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => handleSendSpecialKey("tab")}
                    className="text-[12px] h-8"
                  >
                    Tab ⇥
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => handleSendSpecialKey("escape")}
                    className="text-[12px] h-8"
                  >
                    Esc ⎋
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => handleSendSpecialKey("space")}
                    className="text-[12px] h-8"
                  >
                    Space ␣
                  </Button>
                </div>

                {/* Virtual Typing Input Drawer */}
                {showKeyboardDrawer && (
                  <form onSubmit={handleSendText} className="flex gap-2 pt-2 animate-in fade-in">
                    <input
                      type="text"
                      value={keyInput}
                      onChange={(e) => setKeyInput(e.target.value)}
                      placeholder="Type text to send to Windows desktop..."
                      className="flex-1 rounded-md border border-ops-line-bright bg-ops-ground px-3 py-2 text-[13px] text-ink outline-none focus:border-ai"
                      autoFocus
                    />
                    <Button type="submit" size="sm" disabled={!keyInput}>
                      <Send size={13} /> Send Text
                    </Button>
                  </form>
                )}
              </div>
            </div>
          </Panel>

          {/* Windows Terminal / PowerShell CLI */}
          <Panel
            title="Windows Terminal (PowerShell)"
            lamp={<Lamp tone="go" pulse={isExecutingCmd} />}
            actions={
              <div className="flex items-center gap-1.5">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleOpenLaptopTerminalGui}
                  className="h-7 text-[11px] gap-1"
                  title="Open physical terminal window on laptop desktop"
                >
                  <Terminal size={12} /> Launch Desktop GUI
                </Button>
                <button
                  onClick={() => setTerminalHistory([])}
                  className="rounded p-1 text-ink-dim hover:text-ink hover:bg-ops-raised"
                  title="Clear Console Output"
                >
                  <Trash2 size={13} />
                </button>
              </div>
            }
          >
            <div className="space-y-3 pt-2">
              <p className="text-[12px] text-ink-dim">
                Direct CLI and PowerShell execution on your Windows workstation. Speak or type commands from your phone.
              </p>

              {/* Quick Presets */}
              <div className="flex flex-wrap gap-1.5 items-center">
                <span className="text-[11px] uppercase tracking-wider text-ink-faint font-semibold mr-1">
                  Presets:
                </span>
                {["git status", "agy --version", "dir", "ipconfig", "tasklist", "whoami", "npm test"].map((preset) => (
                  <button
                    key={preset}
                    onClick={() => {
                      setTerminalCmd(preset);
                      handleExecuteTerminal(preset);
                    }}
                    disabled={isExecutingCmd}
                    className="rounded-md border border-ops-line-bright bg-ops-raised/40 px-2 py-0.5 font-mono text-[11px] text-ink hover:bg-ops-raised hover:border-ai transition-colors cursor-pointer"
                  >
                    {preset}
                  </button>
                ))}
              </div>

              {/* Terminal Screen Output Window */}
              <div className="relative rounded-xl border border-slate-800 bg-slate-950 p-3.5 font-mono text-[12px] shadow-inner">
                <div className="flex items-center justify-between pb-2 border-b border-slate-800/80 text-[11px] text-slate-500">
                  <span className="flex items-center gap-1.5">
                    <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
                    PowerShell Core · C:\kirtan\IRIS
                  </span>
                  <span>{isExecutingCmd ? "Executing..." : "Ready"}</span>
                </div>

                <div className="max-h-56 overflow-y-auto space-y-3 py-2 pr-1 select-text">
                  {terminalHistory.map((entry, idx) => (
                    <div key={idx} className="space-y-1">
                      <div className="flex items-center justify-between text-slate-400">
                        <span className="font-semibold text-emerald-400">
                          PS &gt; <span className="text-white">{entry.cmd}</span>
                        </span>
                        <span className="text-[10px] text-slate-500">{entry.timestamp}</span>
                      </div>
                      {entry.stdout && (
                        <pre className="whitespace-pre-wrap text-slate-300 pl-2 border-l border-slate-800 text-[11px]">
                          {entry.stdout}
                        </pre>
                      )}
                      {entry.stderr && (
                        <pre className="whitespace-pre-wrap text-rose-400 pl-2 border-l border-rose-900/60 text-[11px]">
                          {entry.stderr}
                        </pre>
                      )}
                      <div className="text-[10px] text-slate-600">
                        [Exit: {entry.returncode}]
                      </div>
                    </div>
                  ))}
                  <div ref={terminalBottomRef} />
                </div>
              </div>

              {/* Terminal Command Input & Voice Mic */}
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  handleExecuteTerminal();
                }}
                className="flex gap-2 items-center"
              >
                <div className="flex-1 relative flex items-center">
                  <span className="absolute left-3 font-mono text-[12px] text-emerald-400 select-none">
                    PS &gt;
                  </span>
                  <input
                    type="text"
                    value={terminalCmd}
                    onChange={(e) => setTerminalCmd(e.target.value)}
                    placeholder="Type or speak command (e.g. git status, dir, npm test)..."
                    disabled={isExecutingCmd}
                    className="w-full rounded-md border border-ops-line-bright bg-ops-raised/30 pl-14 pr-10 py-2 font-mono text-[13px] text-ink outline-none focus:border-ai"
                  />
                  <button
                    type="button"
                    onClick={handleToggleVoiceTerminal}
                    className={cn(
                      "absolute right-2 rounded p-1.5 transition-colors cursor-pointer",
                      isListeningVoice
                        ? "bg-rose-500 text-white animate-pulse"
                        : "text-ink-faint hover:text-ink hover:bg-ops-raised",
                    )}
                    title="Speak command"
                  >
                    <Mic size={14} />
                  </button>
                </div>

                <Button type="submit" size="sm" disabled={!terminalCmd.trim() || isExecutingCmd}>
                  {isExecutingCmd ? "Running..." : "Run ↵"}
                </Button>
              </form>
            </div>
          </Panel>

          {/* Universal Clipboard */}
          <Panel title="Universal Clipboard" lamp={<Lamp tone="ai" />}>
            <div className="space-y-3 pt-2">
              <p className="text-[12px] text-ink-dim">
                Real-time clipboard synchronizer between this mobile device and your laptop.
              </p>
              <div className="relative rounded-md border border-ops-line-bright bg-ops-ground/60 p-3">
                <pre className="min-h-[45px] whitespace-pre-wrap font-mono text-[13px] text-ink">
                  {clipboard || <span className="text-ink-faint italic">Clipboard is currently empty</span>}
                </pre>
                {clipboard && (
                  <button
                    onClick={handleCopyClipboard}
                    className="absolute right-2 top-2 rounded bg-ops-raised px-2 py-1 text-[11px] font-medium text-ink hover:bg-ops-raised/80 flex items-center gap-1 cursor-pointer"
                  >
                    {copied ? <Check size={12} className="text-go" /> : <Copy size={12} />}
                    {copied ? "Copied" : "Copy to Device"}
                  </button>
                )}
              </div>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={newClip}
                  onChange={(e) => setNewClip(e.target.value)}
                  placeholder="Push new text to laptop clipboard..."
                  className="flex-1 rounded-md border border-ops-line-bright bg-ops-raised/30 px-3 py-1.5 text-[13px] text-ink outline-none focus:border-ai"
                  onKeyDown={(e) => e.key === "Enter" && handlePushClipboard()}
                />
                <Button size="sm" onClick={handlePushClipboard} disabled={!newClip}>
                  Push to Laptop
                </Button>
              </div>
            </div>
          </Panel>

          {/* AirDrop File Vault */}
          <Panel title="AirDrop File Vault" lamp={<Lamp tone="go" />}>
            <div className="space-y-4 pt-2">
              <div className="flex items-center justify-between">
                <p className="text-[12px] text-ink-dim">
                  Direct sovereign file transfer to and from your laptop without size limits.
                </p>
                <label className="cursor-pointer">
                  <input type="file" className="hidden" onChange={handleFileUpload} />
                  <span className="inline-flex items-center gap-1.5 rounded-md bg-ops-raised px-3 py-1.5 text-[12px] font-medium text-ink hover:bg-ops-raised/80">
                    <Upload size={13} /> Drop File to Laptop
                  </span>
                </label>
              </div>

              <div className="space-y-2">
                {vaultFiles.length === 0 ? (
                  <p className="text-center py-4 text-[13px] text-ink-faint">Vault is empty.</p>
                ) : (
                  vaultFiles.map((file) => (
                    <div
                      key={file.name}
                      className="flex items-center justify-between rounded-md bg-ops-raised/30 px-3 py-2 text-[13px]"
                    >
                      <div className="flex items-center gap-2">
                        <HardDrive size={15} className="text-ink-faint" />
                        <span className="font-medium text-ink">{file.name}</span>
                        <span className="text-[11px] text-ink-faint">({Math.round(file.size / 1024)} KB)</span>
                      </div>
                      <a
                        href={file.url}
                        download={file.name}
                        className="flex items-center gap-1 text-[12px] text-ai hover:underline"
                      >
                        <Download size={13} /> Download
                      </a>
                    </div>
                  ))
                )}
              </div>
            </div>
          </Panel>
        </div>
      )}

      {/* ========================================================================= */}
      {/* PHONE VIEW                                                                */}
      {/* ========================================================================= */}
      {view === "phone" && (
        <div className="space-y-6">
          {/* Paired Phone Status Panel */}
          {primaryPhone ? (
            <div className="rounded-xl border border-ops-line bg-ops-panel p-5 space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="h-12 w-12 rounded-xl bg-ai/10 border border-ai/20 flex items-center justify-center text-ai">
                    <Smartphone size={24} />
                  </div>
                  <div>
                    <h2 className="text-[17px] font-semibold text-ink">{primaryPhone.device_name}</h2>
                    <p className="text-[12px] text-go font-medium flex items-center gap-1 mt-0.5">
                      <span className="h-2 w-2 rounded-full bg-go animate-pulse" />
                      Sovereign Cloud Relay Linked (5G Active)
                    </p>
                  </div>
                </div>

                <Button variant="outline" size="sm" onClick={handleRingPhone} className="gap-1.5 text-amber-400">
                  <Bell size={14} /> 🚨 Ring Phone (Find My)
                </Button>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 pt-2 border-t border-ops-line text-[12px]">
                <div className="rounded-lg bg-ops-raised/40 p-2.5">
                  <p className="text-ink-faint">Battery</p>
                  <p className="text-ink font-semibold mt-0.5">
                    {primaryPhone.battery_level != null ? `${primaryPhone.battery_level}%` : "Reporting via Relay"}
                  </p>
                </div>
                <div className="rounded-lg bg-ops-raised/40 p-2.5">
                  <p className="text-ink-faint">Device Type</p>
                  <p className="text-ink font-semibold mt-0.5">Mobile Companion (PWA)</p>
                </div>
                <div className="rounded-lg bg-ops-raised/40 p-2.5 col-span-2 sm:col-span-1">
                  <p className="text-ink-faint">Security Pairing</p>
                  <p className="text-go font-semibold mt-0.5">Permanent (Verified)</p>
                </div>
              </div>
            </div>
          ) : (
            <div className="rounded-xl border border-dashed border-ops-line-bright bg-ops-panel/50 p-8 text-center space-y-3">
              <Smartphone size={36} className="mx-auto text-ink-faint" />
              <div>
                <h3 className="text-[16px] font-semibold text-ink">No Mobile Phone Paired Yet</h3>
                <p className="text-[13px] text-ink-dim max-w-md mx-auto mt-1">
                  Pair your phone in 10 seconds with a 6-digit PIN. Your phone will stay connected forever.
                </p>
              </div>
              <Button onClick={() => navigate("/settings?tab=mesh")} className="mt-2">
                🔗 Pair Phone with 6-Digit PIN
              </Button>
            </div>
          )}

          {/* Universal Clipboard */}
          <Panel title="Universal Clipboard" lamp={<Lamp tone="ai" />}>
            <div className="space-y-3 pt-2">
              <p className="text-[12px] text-ink-dim">
                Text copied or typed here is pushed immediately to your phone over the sovereign relay.
              </p>
              <div className="relative rounded-md border border-ops-line-bright bg-ops-ground/60 p-3">
                <pre className="min-h-[45px] whitespace-pre-wrap font-mono text-[13px] text-ink">
                  {clipboard || <span className="text-ink-faint italic">Clipboard is currently empty</span>}
                </pre>
                {clipboard && (
                  <button
                    onClick={handleCopyClipboard}
                    className="absolute right-2 top-2 rounded bg-ops-raised px-2 py-1 text-[11px] font-medium text-ink hover:bg-ops-raised/80 flex items-center gap-1 cursor-pointer"
                  >
                    {copied ? <Check size={12} className="text-go" /> : <Copy size={12} />}
                    {copied ? "Copied" : "Copy"}
                  </button>
                )}
              </div>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={newClip}
                  onChange={(e) => setNewClip(e.target.value)}
                  placeholder="Type text to push to your phone..."
                  className="flex-1 rounded-md border border-ops-line-bright bg-ops-raised/30 px-3 py-1.5 text-[13px] text-ink outline-none focus:border-ai"
                  onKeyDown={(e) => e.key === "Enter" && handlePushClipboard()}
                />
                <Button size="sm" onClick={handlePushClipboard} disabled={!newClip}>
                  Push to Phone
                </Button>
              </div>
            </div>
          </Panel>

          {/* AirDrop File Vault */}
          <Panel title="AirDrop File Vault" lamp={<Lamp tone="go" />}>
            <div className="space-y-4 pt-2">
              <div className="flex items-center justify-between">
                <p className="text-[12px] text-ink-dim">
                  Drop documents, photos, or code snippets directly to your mobile device.
                </p>
                <label className="cursor-pointer">
                  <input type="file" className="hidden" onChange={handleFileUpload} />
                  <span className="inline-flex items-center gap-1.5 rounded-md bg-ops-raised px-3 py-1.5 text-[12px] font-medium text-ink hover:bg-ops-raised/80">
                    <Upload size={13} /> Drop File to Phone
                  </span>
                </label>
              </div>

              <div className="space-y-2">
                {vaultFiles.length === 0 ? (
                  <p className="text-center py-4 text-[13px] text-ink-faint">Vault is empty.</p>
                ) : (
                  vaultFiles.map((file) => (
                    <div
                      key={file.name}
                      className="flex items-center justify-between rounded-md bg-ops-raised/30 px-3 py-2 text-[13px]"
                    >
                      <div className="flex items-center gap-2">
                        <HardDrive size={15} className="text-ink-faint" />
                        <span className="font-medium text-ink">{file.name}</span>
                        <span className="text-[11px] text-ink-faint">({Math.round(file.size / 1024)} KB)</span>
                      </div>
                      <a
                        href={file.url}
                        download={file.name}
                        className="flex items-center gap-1 text-[12px] text-ai hover:underline"
                      >
                        <Download size={13} /> Download
                      </a>
                    </div>
                  ))
                )}
              </div>
            </div>
          </Panel>

          {/* Manage link */}
          <div className="rounded-xl border border-ops-line bg-ops-panel/40 p-4 flex items-center justify-between">
            <div>
              <p className="text-[13px] font-medium text-ink">Manage Sovereign Mesh & Pairing PINs</p>
              <p className="text-[12px] text-ink-dim">Add or revoke devices in the Settings page.</p>
            </div>
            <Button size="sm" variant="outline" onClick={() => navigate("/settings?tab=mesh")}>
              Mesh Settings &rarr;
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
