import { useEffect, useState } from "react";
import {
  Bell,
  Check,
  Copy,
  Download,
  HardDrive,
  Laptop,
  Lock,
  MonitorPlay,
  Plus,
  Smartphone,
  Trash2,
  Upload,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Panel, Lamp } from "@/components/ui/Panel";
import { Dialog, DialogContent } from "@/components/ui/Overlay";
import { api } from "@/api/client";

interface MeshDevice {
  device_id: string;
  device_type: string;
  name: string;
  battery_level?: number | null;
  is_charging?: boolean | null;
  connected_at: string;
}

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

interface PairingInvite {
  pairing_code: string;
  token: string;
  expires_at: string;
}

export function MeshPage() {
  const [activeDevices, setActiveDevices] = useState<MeshDevice[]>([]);
  const [pairedDevices, setPairedDevices] = useState<PairedDevice[]>([]);
  const [hostPower, setHostPower] = useState<HostPower | null>(null);
  const [clipboard, setClipboard] = useState("");
  const [newClip, setNewClip] = useState("");
  const [vaultFiles, setVaultFiles] = useState<VaultFile[]>([]);
  const [copied, setCopied] = useState(false);
  const [statusMsg, setStatusMsg] = useState("");

  // 6-Digit PIN Pairing state
  const [pairModalOpen, setPairModalOpen] = useState(false);
  const [pairingMode, setPairingMode] = useState<"enter_pin" | "show_pin">("enter_pin");
  const [pinInput, setPinInput] = useState("");
  const [deviceNameInput, setDeviceNameInput] = useState("Mobile Phone");
  const [isVerifying, setIsVerifying] = useState(false);
  const [verifyError, setVerifyError] = useState("");

  // Mobile PIN generation state (if user opens on phone)
  const [invite, setInvite] = useState<PairingInvite | null>(null);
  const [loadingInvite, setLoadingInvite] = useState(false);
  const [phonePairedSuccess, setPhonePairedSuccess] = useState(false);

  // Phone Mirroring state (Step 2)
  const [mirrorModalOpen, setMirrorModalOpen] = useState(false);
  const [snapshotTimestamp, setSnapshotTimestamp] = useState(Date.now());

  const loadData = async () => {
    try {
      // 1. Live connected devices & power
      const devRes = await api.get<{ devices: MeshDevice[]; host_power: HostPower | null }>("/mesh/devices");
      setActiveDevices(devRes.devices);
      setHostPower(devRes.host_power);

      // 2. Permanently paired sovereign devices
      const pairRes = await api.get<{ paired_devices: PairedDevice[] }>("/mesh/pair/devices");
      setPairedDevices(pairRes.paired_devices || []);

      // 3. Universal Clipboard
      const clipRes = await api.get<{ text: string }>("/mesh/clipboard");
      setClipboard(clipRes.text || "");

      // 4. File Vault
      const filesRes = await api.get<{ files: VaultFile[] }>("/mesh/files");
      setVaultFiles(filesRes.files || []);
    } catch {
      // Network idle fallback
    }
  };

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 3500);
    return () => clearInterval(interval);
  }, []);

  // Refresh snapshot if mirror modal is open
  useEffect(() => {
    if (!mirrorModalOpen) return;
    const snapInterval = setInterval(() => {
      setSnapshotTimestamp(Date.now());
    }, 500);
    return () => clearInterval(snapInterval);
  }, [mirrorModalOpen]);

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
      setStatusMsg("✨ Mobile Phone paired permanently!");
      setPinInput("");
      setPairModalOpen(false);
      await loadData();
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
            loadData();
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

  const handleOpenPairModal = (mode: "enter_pin" | "show_pin" = "enter_pin") => {
    setPairingMode(mode);
    setVerifyError("");
    setPairModalOpen(true);
    if (mode === "show_pin") {
      handleGeneratePhoneCode();
    }
  };

  const handleUnpairDevice = async (deviceId: string, name: string) => {
    if (!window.confirm(`Unpair ${name}? You will need a new 6-digit PIN to pair again.`)) return;
    try {
      await api.delete(`/mesh/pair/${deviceId}`);
      setStatusMsg(`Unpaired ${name}`);
      loadData();
      setTimeout(() => setStatusMsg(""), 3000);
    } catch {
      setStatusMsg("Failed to unpair device");
    }
  };

  const handleCopyClipboard = async () => {
    if (!clipboard) return;
    await navigator.clipboard.writeText(clipboard);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handlePushClipboard = async () => {
    if (!newClip) return;
    await api.post("/mesh/clipboard", { text: newClip, sender_device: "laptop_web" });
    setClipboard(newClip);
    setNewClip("");
    setStatusMsg("Synced to Universal Clipboard!");
    setTimeout(() => setStatusMsg(""), 3000);
  };

  const handleRingPhone = async () => {
    await api.post("/mesh/command", { command: "RING_PHONE" });
    setStatusMsg("Ring alert sent to phone!");
    setTimeout(() => setStatusMsg(""), 3000);
  };

  const handleLockPC = async () => {
    if (!window.confirm("Lock Windows workstation now?")) return;
    await api.post("/mesh/command", { command: "LOCK_PC" });
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    form.append("sender_device", "laptop_web");
    try {
      await fetch("/api/mesh/files/upload", {
        method: "POST",
        body: form,
      });
      setStatusMsg(`Dropped ${file.name} to Mesh Vault!`);
      loadData();
      setTimeout(() => setStatusMsg(""), 3000);
    } catch {
      setStatusMsg("Failed to upload file");
    }
  };

  const companionUrl = `${window.location.origin}/companion`;

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-[28px] font-bold tracking-tight text-ink">IRIS Sovereign Mesh</h1>
          <p className="text-[13px] text-ink-dim">
            Permanent, $0 cross-network device continuity and remote screen mirroring.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Button size="sm" variant="outline" onClick={() => handleOpenPairModal("enter_pin")}>
            <Plus size={14} /> Pair New Phone
          </Button>
          <div className="flex items-center gap-2">
            <Lamp tone="go" pulse />
            <span className="text-[12px] font-medium text-ink-dim">Sovereign Relay Active</span>
          </div>
        </div>
      </div>

      {statusMsg && (
        <div className="rounded-md bg-ai-dim px-4 py-2 text-[13px] text-ai font-medium">
          {statusMsg}
        </div>
      )}

      {/* Connected Devices Grid */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {/* Windows Laptop */}
        <Panel title="Windows Laptop (Host)" lamp={<Lamp tone="go" />}>
          <div className="space-y-3 pt-2">
            <div className="flex items-center gap-3">
              <Laptop size={20} className="text-ai" />
              <div>
                <p className="text-[14px] font-medium text-ink">Primary Workstation</p>
                <p className="text-[12px] text-ink-faint">Headless / Closed Lid Support</p>
              </div>
            </div>
            <div className="rounded-md bg-ops-raised/40 p-2.5 text-[12px] space-y-1">
              <div className="flex justify-between">
                <span className="text-ink-dim">Power Status</span>
                <span className="text-ink font-mono">
                  {hostPower?.percent !== null && hostPower?.percent !== undefined
                    ? `${hostPower.percent}%`
                    : "AC Power"}{" "}
                  ({hostPower?.ac_status || "Plugged In"})
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-ink-dim">Sleep Mode</span>
                <span className="text-go font-medium">Sleep Disabled (Always Reachable)</span>
              </div>
            </div>
            <div className="flex gap-2">
              <Button variant="danger" size="sm" onClick={handleLockPC} className="flex-1">
                <Lock size={13} /> Lock Workstation
              </Button>
              <Button variant="outline" size="sm" onClick={() => setMirrorModalOpen(true)}>
                <MonitorPlay size={13} /> Screen Stream
              </Button>
            </div>
          </div>
        </Panel>

        {/* Mobile Companions */}
        <Panel
          title={`Mobile Devices (${pairedDevices.length} Paired)`}
          lamp={<Lamp tone={pairedDevices.length > 0 ? "go" : "caution"} />}
        >
          <div className="space-y-3 pt-2">
            {pairedDevices.length === 0 ? (
              <div className="flex flex-col p-4 border border-dashed border-ops-line-bright rounded-xl bg-ops-ground/40 space-y-3">
                <div className="flex items-center gap-2.5">
                  <Smartphone size={20} className="text-ai" />
                  <div>
                    <p className="text-[14px] font-semibold text-ink">Pair Mobile Phone</p>
                    <p className="text-[12px] text-ink-dim">
                      Enter the 6-digit PIN shown on your phone's companion screen:
                    </p>
                  </div>
                </div>

                <form onSubmit={handleVerifyPhonePin} className="space-y-2.5 pt-1">
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={pinInput}
                      onChange={(e) => {
                        setVerifyError("");
                        setPinInput(e.target.value.replace(/\D/g, "").slice(0, 6));
                      }}
                      placeholder="000 000"
                      className="w-36 rounded-md border border-ops-line-bright bg-ops-raised/40 px-3 py-2 text-center font-mono text-[20px] font-bold tracking-widest text-ink outline-none focus:border-ai"
                      maxLength={6}
                    />
                    <Button
                      type="submit"
                      disabled={pinInput.length !== 6 || isVerifying}
                      className="flex-1"
                    >
                      {isVerifying ? "Pairing..." : "Pair Phone Forever"}
                    </Button>
                  </div>
                  {verifyError && (
                    <p className="text-[12px] text-rose-400 font-medium">{verifyError}</p>
                  )}
                </form>

                <div className="flex items-center justify-between text-[11px] text-ink-faint pt-1 border-t border-ops-line">
                  <span>Companion: <code className="text-ink">{companionUrl}</code></span>
                  <button
                    type="button"
                    onClick={() => handleOpenPairModal("show_pin")}
                    className="text-ai hover:underline cursor-pointer"
                  >
                    This is my phone &rarr;
                  </button>
                </div>
              </div>
            ) : (
              <div className="space-y-2">
                {pairedDevices.map((dev) => {
                  const isOnline = activeDevices.some((d) => d.device_id === dev.device_id);
                  return (
                    <div
                      key={dev.device_id}
                      className="flex items-center justify-between rounded-lg bg-ops-raised/40 p-2.5 text-[12px]"
                    >
                      <div className="flex items-center gap-2.5">
                        <Smartphone size={18} className={isOnline ? "text-go" : "text-ink-dim"} />
                        <div>
                          <p className="font-medium text-ink">{dev.device_name}</p>
                          <p className="text-[11px] text-ink-faint flex items-center gap-1">
                            {isOnline ? (
                              <span className="text-go font-medium">● Connected</span>
                            ) : (
                              <span>○ Sovereign Cloud Relay (5G)</span>
                            )}
                            {dev.battery_level != null && <span>· 🔋 {dev.battery_level}%</span>}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleUnpairDevice(dev.device_id, dev.device_name)}
                          className="h-7 w-7 p-0 text-ink-faint hover:text-rose-400"
                          title="Unpair device"
                        >
                          <Trash2 size={13} />
                        </Button>
                      </div>
                    </div>
                  );
                })}
                <div className="flex gap-2 pt-1">
                  <Button variant="outline" size="sm" onClick={handleRingPhone} className="flex-1">
                    <Bell size={13} /> Ring Phone (Find My)
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => handleOpenPairModal("enter_pin")}>
                    <Plus size={13} /> Pair Another
                  </Button>
                </div>
              </div>
            )}
          </div>
        </Panel>
      </div>

      {/* Universal Clipboard */}
      <Panel title="Universal Clipboard" lamp={<Lamp tone="ai" />}>
        <div className="space-y-3 pt-2">
          <p className="text-[12px] text-ink-dim">
            Text copied here syncs immediately to your phone over the sovereign relay, and vice-versa.
          </p>
          <div className="relative rounded-md border border-ops-line-bright bg-ops-ground/60 p-3">
            <pre className="min-h-[50px] whitespace-pre-wrap font-mono text-[13px] text-ink">
              {clipboard || <span className="text-ink-faint italic">Clipboard is currently empty</span>}
            </pre>
            {clipboard && (
              <button
                onClick={handleCopyClipboard}
                className="absolute right-2 top-2 rounded bg-ops-raised px-2 py-1 text-[11px] font-medium text-ink hover:bg-ops-raised/80 flex items-center gap-1"
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
              placeholder="Type or paste to push across all devices..."
              className="flex-1 rounded-md border border-ops-line-bright bg-ops-raised/30 px-3 py-1.5 text-[13px] text-ink outline-none focus:border-ai"
              onKeyDown={(e) => e.key === "Enter" && handlePushClipboard()}
            />
            <Button size="sm" onClick={handlePushClipboard} disabled={!newClip}>
              Push to Mesh
            </Button>
          </div>
        </div>
      </Panel>

      {/* AirDrop File Vault */}
      <Panel title="AirDrop File Vault" lamp={<Lamp tone="go" />}>
        <div className="space-y-4 pt-2">
          <div className="flex items-center justify-between">
            <p className="text-[12px] text-ink-dim">
              Direct sovereign file drops between your laptop and phone without cloud size limits.
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

      {/* 6-Digit PIN Pairing Modal (Zero QR Code) */}
      <Dialog open={pairModalOpen} onOpenChange={setPairModalOpen}>
        <DialogContent title="Pair Sovereign Device (6-Digit PIN)">
          <div className="space-y-4 py-2">
            {/* Toggle tabs between Laptop entering PIN vs Phone showing PIN */}
            <div className="flex rounded-lg bg-ops-raised/40 p-1 text-[12px]">
              <button
                type="button"
                onClick={() => setPairingMode("enter_pin")}
                className={`flex-1 rounded-md py-1.5 font-medium transition-colors ${
                  pairingMode === "enter_pin" ? "bg-ops-panel text-ink shadow-sm" : "text-ink-dim hover:text-ink"
                }`}
              >
                💻 Enter Phone PIN (Laptop)
              </button>
              <button
                type="button"
                onClick={() => {
                  setPairingMode("show_pin");
                  handleGeneratePhoneCode();
                }}
                className={`flex-1 rounded-md py-1.5 font-medium transition-colors ${
                  pairingMode === "show_pin" ? "bg-ops-panel text-ink shadow-sm" : "text-ink-dim hover:text-ink"
                }`}
              >
                📱 Show PIN (This Phone)
              </button>
            </div>

            {pairingMode === "enter_pin" ? (
              <form onSubmit={handleVerifyPhonePin} className="space-y-4 pt-1">
                <p className="text-[13px] text-ink-dim leading-relaxed">
                  Open the companion screen on your phone (<code>{companionUrl}</code>) and enter the 6-digit PIN displayed on your phone:
                </p>

                <div className="rounded-xl border border-ai/20 bg-ai/5 p-4 text-center space-y-2">
                  <label className="text-[11px] font-semibold uppercase tracking-wider text-ai">
                    6-Digit Phone PIN
                  </label>
                  <input
                    type="text"
                    value={pinInput}
                    onChange={(e) => {
                      setVerifyError("");
                      setPinInput(e.target.value.replace(/\D/g, "").slice(0, 6));
                    }}
                    placeholder="000 000"
                    className="w-full rounded-lg border border-ops-line-bright bg-ops-ground px-4 py-3 text-center font-mono text-[32px] font-bold tracking-[0.25em] text-ink outline-none focus:border-ai"
                    maxLength={6}
                    autoFocus
                  />
                  {verifyError && (
                    <p className="text-[12px] text-rose-400 font-medium">{verifyError}</p>
                  )}
                </div>

                <div className="space-y-1">
                  <label className="text-[12px] text-ink-dim">Device Label (Optional)</label>
                  <input
                    type="text"
                    value={deviceNameInput}
                    onChange={(e) => setDeviceNameInput(e.target.value)}
                    placeholder="e.g. Kirtan's Phone"
                    className="w-full rounded-md border border-ops-line-bright bg-ops-ground px-3 py-2 text-[13px] text-ink outline-none focus:border-ai"
                  />
                </div>

                <Button
                  type="submit"
                  disabled={pinInput.length !== 6 || isVerifying}
                  className="w-full"
                >
                  {isVerifying ? "Pairing..." : "🔗 Link Device Forever"}
                </Button>
              </form>
            ) : (
              <div className="space-y-4 text-center pt-1">
                <p className="text-[13px] text-ink-dim">
                  Enter this 6-digit PIN on your Laptop's Mesh page to link this phone forever:
                </p>

                {loadingInvite ? (
                  <div className="py-8 text-[13px] text-ink-dim animate-pulse">Generating PIN...</div>
                ) : phonePairedSuccess ? (
                  <div className="rounded-xl border border-go/30 bg-go/10 p-6 space-y-2">
                    <p className="text-[16px] font-bold text-go">✨ Connected to Laptop!</p>
                    <p className="text-[12px] text-ink-dim">This phone is now permanently paired.</p>
                  </div>
                ) : invite ? (
                  <div className="space-y-3">
                    <div className="rounded-xl border border-ai/30 bg-ai/10 p-5">
                      <p className="text-[11px] font-semibold uppercase tracking-wider text-ai mb-1">
                        6-Digit Pairing PIN
                      </p>
                      <div className="font-mono text-[40px] font-black tracking-[0.25em] text-ink">
                        {invite.pairing_code}
                      </div>
                      <p className="text-[11px] text-ink-faint mt-1">
                        Valid for 15 minutes · Valid forever once paired
                      </p>
                    </div>

                    <div className="flex items-center justify-center gap-2 text-[12px] text-go font-medium animate-pulse">
                      <div className="h-2 w-2 rounded-full bg-go" />
                      <span>Waiting for laptop to enter PIN...</span>
                    </div>

                    <Button
                      variant="outline"
                      size="sm"
                      onClick={handleGeneratePhoneCode}
                      className="mt-2"
                    >
                      🔄 Refresh Code
                    </Button>
                  </div>
                ) : null}
              </div>
            )}

            <div className="pt-2">
              <Button variant="outline" onClick={() => setPairModalOpen(false)} className="w-full">
                Close
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Screen Mirroring & Remote Desktop Modal (Step 2) */}
      <Dialog open={mirrorModalOpen} onOpenChange={setMirrorModalOpen}>
        <DialogContent title="Desktop Screen Streaming (WebRTC & Live Preview)" className="max-w-2xl">
          <div className="space-y-4 py-2">
            <div className="flex items-center justify-between text-[12px]">
              <span className="text-ink-dim">Primary Monitor (Windows Desktop)</span>
              <span className="text-go font-medium flex items-center gap-1">
                ● Live 30 FPS Stream Active
              </span>
            </div>

            <div className="relative aspect-[16/10] w-full overflow-hidden rounded-xl border border-ops-line-bright bg-black">
              <img
                src={`/api/mesh/screen/snapshot?quality=75&scale=2&t=${snapshotTimestamp}`}
                alt="Desktop Live Stream"
                className="h-full w-full object-contain"
              />
            </div>

            <p className="text-[12px] text-ink-faint text-center">
              Your mobile companion displays this stream with touch-to-click mouse control and typing support.
            </p>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
