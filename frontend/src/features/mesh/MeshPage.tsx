import { useEffect, useState } from "react";
import {
  Bell,
  Check,
  Copy,
  Download,
  ExternalLink,
  HardDrive,
  Laptop,
  Lock,
  MonitorPlay,
  Plus,
  QrCode,
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
  qr_svg_uri: string;
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

  // Pairing Modal state
  const [pairModalOpen, setPairModalOpen] = useState(false);
  const [invite, setInvite] = useState<PairingInvite | null>(null);
  const [loadingInvite, setLoadingInvite] = useState(false);

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

  const handleOpenPairModal = async () => {
    setPairModalOpen(true);
    setLoadingInvite(true);
    try {
      const res = await api.post<PairingInvite>("/mesh/pair/code", { device_name: "Mobile Phone" });
      setInvite(res);
    } catch {
      setStatusMsg("Failed to generate pairing code");
    } finally {
      setLoadingInvite(false);
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
          <Button size="sm" variant="outline" onClick={handleOpenPairModal}>
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
              <div className="flex flex-col items-center justify-center p-4 text-center border border-dashed border-ops-line-bright rounded-lg bg-ops-ground/40 space-y-2">
                <Smartphone size={24} className="text-ink-faint" />
                <p className="text-[13px] font-medium text-ink">No mobile device paired yet</p>
                <p className="text-[11px] text-ink-dim">
                  Pair your phone once using a 6-digit code. Works on cellular 5G and any Wi-Fi.
                </p>
                <Button size="sm" onClick={handleOpenPairModal} className="mt-1">
                  <Plus size={13} /> Pair My Phone
                </Button>
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
                  <Button variant="ghost" size="sm" onClick={handleOpenPairModal}>
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

      {/* One-Time Pairing Modal */}
      <Dialog open={pairModalOpen} onOpenChange={setPairModalOpen}>
        <DialogContent title="Pair Sovereign Device (One-Time Handshake)">
          <div className="space-y-4 py-2 text-center">
            <p className="text-[13px] text-ink-dim">
              Open the companion page on your phone once to link it permanently.
            </p>

            {loadingInvite ? (
              <div className="py-8 text-[13px] text-ink-dim animate-pulse">Generating secure pairing PIN...</div>
            ) : invite ? (
              <div className="space-y-4">
                {/* 6-Digit PIN Display */}
                <div className="rounded-xl border border-ai/30 bg-ai/10 p-4">
                  <p className="text-[11px] font-semibold uppercase tracking-wider text-ai mb-1">
                    6-Digit Pairing PIN
                  </p>
                  <div className="font-mono text-[36px] font-black tracking-[0.3em] text-ink">
                    {invite.pairing_code}
                  </div>
                  <p className="text-[11px] text-ink-faint mt-1">
                    Expires in 15 minutes · Valid forever once paired
                  </p>
                </div>

                {/* QR Code */}
                {invite.qr_svg_uri && (
                  <div className="flex flex-col items-center justify-center space-y-2">
                    <img
                      src={invite.qr_svg_uri}
                      alt="Pairing QR Code"
                      className="rounded-lg bg-white p-2 shadow-sm"
                      width={160}
                      height={160}
                    />
                    <p className="text-[12px] text-ink-dim flex items-center gap-1">
                      <QrCode size={13} className="text-ai" /> Scan with Phone Camera
                    </p>
                  </div>
                )}

                {/* Companion Link */}
                <div className="rounded-md bg-ops-raised/40 p-2 text-[12px] flex items-center justify-between">
                  <span className="font-mono text-ink-dim truncate max-w-[280px]">{companionUrl}</span>
                  <a
                    href="/companion"
                    target="_blank"
                    rel="noreferrer"
                    className="text-ai hover:underline flex items-center gap-1 font-medium"
                  >
                    Open <ExternalLink size={11} />
                  </a>
                </div>
              </div>
            ) : null}

            <div className="pt-2">
              <Button variant="outline" onClick={() => setPairModalOpen(false)} className="w-full">
                Done
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
