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
  Smartphone,
  Upload,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Panel, Lamp } from "@/components/ui/Panel";
import { api } from "@/api/client";

interface MeshDevice {
  device_id: string;
  device_type: string;
  name: string;
  battery_level?: number | null;
  is_charging?: boolean | null;
  connected_at: string;
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

export function MeshPage() {
  const [devices, setDevices] = useState<MeshDevice[]>([]);
  const [hostPower, setHostPower] = useState<HostPower | null>(null);
  const [clipboard, setClipboard] = useState("");
  const [newClip, setNewClip] = useState("");
  const [vaultFiles, setVaultFiles] = useState<VaultFile[]>([]);
  const [copied, setCopied] = useState(false);
  const [statusMsg, setStatusMsg] = useState("");

  const loadData = async () => {
    try {
      const devRes = await api.get<{ devices: MeshDevice[]; host_power: HostPower | null }>("/mesh/devices");
      setDevices(devRes.devices);
      setHostPower(devRes.host_power);

      const clipRes = await api.get<{ text: string }>("/mesh/clipboard");
      setClipboard(clipRes.text || "");

      const filesRes = await api.get<{ files: VaultFile[] }>("/mesh/files");
      setVaultFiles(filesRes.files || []);
    } catch {
      // Fallback if network idle
    }
  };

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 4000);
    return () => clearInterval(interval);
  }, []);

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

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-[28px] font-bold tracking-tight text-ink">IRIS Mesh</h1>
          <p className="text-[13px] text-ink-dim">
            Apple-like device continuity, Universal Clipboard, and remote control.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Lamp tone="go" pulse />
          <span className="text-[12px] font-medium text-ink-dim">Mesh Active</span>
        </div>
      </div>

      {statusMsg && (
        <div className="rounded-md bg-ai-dim px-4 py-2 text-[13px] text-ai font-medium">
          {statusMsg}
        </div>
      )}

      {/* Connected Devices Grid */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Panel title="Windows Laptop (Host)" lamp={<Lamp tone="go" />}>
          <div className="space-y-3 pt-2">
            <div className="flex items-center gap-3">
              <Laptop size={20} className="text-ai" />
              <div>
                <p className="text-[14px] font-medium text-ink">Workstation</p>
                <p className="text-[12px] text-ink-faint">Headless / Closed Lid Support</p>
              </div>
            </div>
            <div className="rounded-md bg-ops-raised/40 p-2.5 text-[12px] space-y-1">
              <div className="flex justify-between">
                <span className="text-ink-dim">Power Status</span>
                <span className="text-ink font-mono">
                  {hostPower?.percent !== null ? `${hostPower?.percent}%` : "AC Power"} ({hostPower?.ac_status || "Plugged In"})
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-ink-dim">State</span>
                <span className="text-go">Running (Sleep disabled)</span>
              </div>
            </div>
            <Button variant="danger" size="sm" onClick={handleLockPC} className="w-full">
              <Lock size={13} /> Lock Laptop Workstation
            </Button>
          </div>
        </Panel>

        <Panel title="Mobile Companion" lamp={<Lamp tone={devices.length > 0 ? "go" : "caution"} />}>
          <div className="space-y-3 pt-2">
            <div className="flex items-center gap-3">
              <Smartphone size={20} className="text-go" />
              <div>
                <p className="text-[14px] font-medium text-ink">
                  {devices.find((d) => d.device_type === "phone_mobile")?.name || "Mobile Device"}
                </p>
                <p className="text-[12px] text-ink-faint">
                  {devices.length > 0 ? "Connected via WebSocket" : "Waiting for companion connect..."}
                </p>
              </div>
            </div>
            <div className="rounded-md bg-ops-raised/40 p-2.5 text-[12px] space-y-1">
              <div className="flex justify-between">
                <span className="text-ink-dim">Phone Battery</span>
                <span className="text-ink font-mono">
                  {devices.find((d) => d.battery_level != null)?.battery_level ?? "--"}%
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-ink-dim">Companion URL</span>
                <a
                  href="/companion"
                  target="_blank"
                  rel="noreferrer"
                  className="text-ai hover:underline flex items-center gap-1"
                >
                  /companion <ExternalLink size={10} />
                </a>
              </div>
            </div>
            <Button variant="outline" size="sm" onClick={handleRingPhone} className="w-full">
              <Bell size={13} /> Ring Phone (Find My Phone)
            </Button>
          </div>
        </Panel>
      </div>

      {/* Universal Clipboard */}
      <Panel title="Universal Clipboard" lamp={<Lamp tone="ai" />}>
        <div className="space-y-3 pt-2">
          <p className="text-[12px] text-ink-dim">
            Anything copied here syncs immediately to your phone, and vice-versa.
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
              Fast, direct local file drops between your laptop and phone.
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
    </div>
  );
}
