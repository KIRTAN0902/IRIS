import { useEffect, useState } from "react";
import {
  AlertCircle,
  Bell,
  Camera,
  CheckCircle2,
  CreditCard,
  ExternalLink,
  Mic,
  ShieldCheck,
  Smartphone,
  Sparkles,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Lamp, Panel } from "@/components/ui/Panel";
import { checkNotificationAccess, requestNotificationAccess } from "@/features/finance/upiTracker";
import { openSystemAppSettings } from "@/lib/appLauncher";
import {
  checkAssistantRole,
  checkOverlayPermission,
  getAssistantCapabilities,
  openAssistantSettings,
  refreshHotwordStatus,
  requestAssistantRole,
  requestOverlayPermission,
  triggerAmbientAssistant,
  type AssistantCapabilities,
} from "@/lib/irisAmbient";

type PermissionStatus = "granted" | "denied" | "prompt" | "unknown";

export function PermissionsPanel() {
  const [micStatus, setMicStatus] = useState<PermissionStatus>("unknown");
  const [cameraStatus, setCameraStatus] = useState<PermissionStatus>("unknown");
  const [notificationStatus, setNotificationStatus] = useState<PermissionStatus>("unknown");
  const [upiListenerGranted, setUpiListenerGranted] = useState(false);
  const [assistantRoleGranted, setAssistantRoleGranted] = useState(false);
  const [overlayGranted, setOverlayGranted] = useState(false);
  const [capabilities, setCapabilities] = useState<AssistantCapabilities | null>(null);
  const [actionNotice, setActionNotice] = useState<string | null>(null);
  const [isRequestingAll, setIsRequestingAll] = useState(false);

  const isMobile =
    typeof window !== "undefined" &&
    (Boolean((window as unknown as { Capacitor?: unknown }).Capacitor) ||
      /Android|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent));

  const checkPermissions = async () => {
    // 1. Microphone
    if (typeof navigator !== "undefined" && navigator.permissions?.query) {
      try {
        const res = await navigator.permissions.query({ name: "microphone" as PermissionName });
        setMicStatus(res.state as PermissionStatus);
        res.onchange = () => setMicStatus(res.state as PermissionStatus);
      } catch {
        // Fallback
      }
    }

    // 2. Camera
    if (typeof navigator !== "undefined" && navigator.permissions?.query) {
      try {
        const res = await navigator.permissions.query({ name: "camera" as PermissionName });
        setCameraStatus(res.state as PermissionStatus);
        res.onchange = () => setCameraStatus(res.state as PermissionStatus);
      } catch {
        // Fallback
      }
    }

    // 3. Notifications
    if (typeof window !== "undefined" && "Notification" in window) {
      setNotificationStatus(
        Notification.permission === "granted"
          ? "granted"
          : Notification.permission === "denied"
          ? "denied"
          : "prompt"
      );
    }

    // 4. UPI / Payment Notification Listener
    const hasUpiAccess = await checkNotificationAccess();
    setUpiListenerGranted(hasUpiAccess);

    // 5. Digital Assistant Role & Overlay
    const hasAssistant = await checkAssistantRole();
    setAssistantRoleGranted(hasAssistant);
    const hasOverlay = await checkOverlayPermission();
    setOverlayGranted(hasOverlay);
    setCapabilities(await getAssistantCapabilities());
  };

  useEffect(() => {
    checkPermissions();
    // Periodically re-check (e.g. after user returns from Android Settings app)
    const onFocus = () => checkPermissions();
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, []);

  const requestMic = async () => {
    try {
      if (typeof navigator !== "undefined" && navigator.mediaDevices?.getUserMedia) {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        stream.getTracks().forEach((track) => track.stop());
        setMicStatus("granted");
        setActionNotice("Microphone permission granted successfully!");
      }
    } catch {
      setMicStatus("denied");
      setActionNotice("Microphone access was denied. You can enable it in system app settings.");
    }
  };

  const requestCamera = async () => {
    try {
      if (typeof navigator !== "undefined" && navigator.mediaDevices?.getUserMedia) {
        const stream = await navigator.mediaDevices.getUserMedia({ video: true });
        stream.getTracks().forEach((track) => track.stop());
        setCameraStatus("granted");
        setActionNotice("Camera permission granted successfully!");
      }
    } catch {
      setCameraStatus("denied");
      setActionNotice("Camera access was denied. You can enable it in system app settings.");
    }
  };

  const requestNotifications = async () => {
    try {
      if (typeof window !== "undefined" && "Notification" in window) {
        const permission = await Notification.requestPermission();
        setNotificationStatus(permission === "granted" ? "granted" : "denied");
        if (permission === "granted") {
          setActionNotice("Push notification permission granted!");
        } else {
          setActionNotice("Notification permission was not granted.");
        }
      }
    } catch (err: unknown) {
      console.warn("Notification request error:", err);
    }
  };

  const handleRequestAll = async () => {
    setIsRequestingAll(true);
    setActionNotice("Requesting permissions sequentially...");
    try {
      await requestNotifications();
      await requestMic();
      await requestCamera();
      await checkPermissions();
      setActionNotice("All primary runtime permissions requested!");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setActionNotice(`Permission request completed with note: ${msg}`);
    } finally {
      setIsRequestingAll(false);
    }
  };

  const handleTestAssistant = async () => {
    const started = await triggerAmbientAssistant();
    setActionNotice(
      started
        ? "Native IRIS session launched. Speak normally; the microphone closes when the session ends."
        : "Could not start the native assistant session. Check the microphone permission."
    );
  };

  const handleHotwordRefresh = async () => {
    await refreshHotwordStatus();
    await checkPermissions();
    setActionNotice("Asked Android for the current hardware hotword capability.");
  };

  const grantedCount =
    (micStatus === "granted" ? 1 : 0) +
    (cameraStatus === "granted" ? 1 : 0) +
    (notificationStatus === "granted" ? 1 : 0) +
    (upiListenerGranted ? 1 : 0);

  return (
    <div className="space-y-6">
      {/* Overview Banner */}
      <Panel
        title="Device Permissions & System Access"
        lamp={<Lamp tone={grantedCount >= 3 ? "go" : grantedCount > 0 ? "caution" : "critical"} pulse />}
      >
        <div className="space-y-4 pt-2">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 rounded-xl border border-ai/20 bg-ai/5 p-4">
            <div>
              <div className="flex items-center gap-2">
                <ShieldCheck size={20} className="text-ai" />
                <h3 className="text-[14px] font-semibold text-ink">
                  {grantedCount} of 4 Permissions Active
                </h3>
              </div>
              <p className="text-[12px] text-ink-dim mt-1 max-w-lg">
                IRIS uses native device permissions for real-time conversational voice, screen & camera perception, continuity alerts, and automatic UPI expense categorization.
              </p>
            </div>
            <Button
              variant="ai"
              size="sm"
              onClick={handleRequestAll}
              disabled={isRequestingAll}
              className="shrink-0 flex items-center gap-1.5"
            >
              <Sparkles size={14} />
              <span>{isRequestingAll ? "Requesting..." : "Allow All Permissions"}</span>
            </Button>
          </div>

          {actionNotice && (
            <div className="rounded-lg bg-ops-panel border border-ops-line-bright px-3.5 py-2.5 text-[12px] text-ink flex items-center justify-between">
              <span>{actionNotice}</span>
              <button
                type="button"
                onClick={() => setActionNotice(null)}
                className="text-ink-faint hover:text-ink text-[11px] underline ml-2"
              >
                Dismiss
              </button>
            </div>
          )}

          {/* List of Permissions */}
          <div className="space-y-3 pt-1">
            {/* 1. Microphone */}
            <div className="flex items-center justify-between p-3.5 rounded-xl border border-ops-line bg-ops-panel hover:border-ops-line-bright transition-colors">
              <div className="flex items-center gap-3">
                <div className="rounded-lg bg-ai/10 p-2 text-ai">
                  <Mic size={18} />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-[13px] font-medium text-ink">Microphone Access</span>
                    {micStatus === "granted" ? (
                      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-[11px] font-medium text-emerald-400 border border-emerald-500/20">
                        <CheckCircle2 size={11} /> Granted
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/10 px-2 py-0.5 text-[11px] font-medium text-amber-400 border border-amber-500/20">
                        <AlertCircle size={11} /> Required for Voice
                      </span>
                    )}
                  </div>
                  <p className="text-[11px] text-ink-dim mt-0.5">
                    Enables ultra-low latency conversational voice, Gemini Live, and hands-free voice commands.
                  </p>
                </div>
              </div>
              <Button
                variant={micStatus === "granted" ? "ghost" : "outline"}
                size="sm"
                onClick={requestMic}
                disabled={micStatus === "granted"}
                className="text-[12px]"
              >
                {micStatus === "granted" ? "Active" : "Allow"}
              </Button>
            </div>

            {/* 2. Camera */}
            <div className="flex items-center justify-between p-3.5 rounded-xl border border-ops-line bg-ops-panel hover:border-ops-line-bright transition-colors">
              <div className="flex items-center gap-3">
                <div className="rounded-lg bg-ai/10 p-2 text-ai">
                  <Camera size={18} />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-[13px] font-medium text-ink">Camera & Vision</span>
                    {cameraStatus === "granted" ? (
                      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-[11px] font-medium text-emerald-400 border border-emerald-500/20">
                        <CheckCircle2 size={11} /> Granted
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/10 px-2 py-0.5 text-[11px] font-medium text-amber-400 border border-amber-500/20">
                        <AlertCircle size={11} /> Not Enabled
                      </span>
                    )}
                  </div>
                  <p className="text-[11px] text-ink-dim mt-0.5">
                    Allows IRIS to analyze documents, whiteboard notes, physical objects, and screen photos.
                  </p>
                </div>
              </div>
              <Button
                variant={cameraStatus === "granted" ? "ghost" : "outline"}
                size="sm"
                onClick={requestCamera}
                disabled={cameraStatus === "granted"}
                className="text-[12px]"
              >
                {cameraStatus === "granted" ? "Active" : "Allow"}
              </Button>
            </div>

            {/* 3. Push Notifications */}
            <div className="flex items-center justify-between p-3.5 rounded-xl border border-ops-line bg-ops-panel hover:border-ops-line-bright transition-colors">
              <div className="flex items-center gap-3">
                <div className="rounded-lg bg-ai/10 p-2 text-ai">
                  <Bell size={18} />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-[13px] font-medium text-ink">Push Notifications</span>
                    {notificationStatus === "granted" ? (
                      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-[11px] font-medium text-emerald-400 border border-emerald-500/20">
                        <CheckCircle2 size={11} /> Granted
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/10 px-2 py-0.5 text-[11px] font-medium text-amber-400 border border-amber-500/20">
                        <AlertCircle size={11} /> Not Enabled
                      </span>
                    )}
                  </div>
                  <p className="text-[11px] text-ink-dim mt-0.5">
                    Delivers remote ring alerts (Find My Phone), coding task completion cards, and continuity updates.
                  </p>
                </div>
              </div>
              <Button
                variant={notificationStatus === "granted" ? "ghost" : "outline"}
                size="sm"
                onClick={requestNotifications}
                disabled={notificationStatus === "granted"}
                className="text-[12px]"
              >
                {notificationStatus === "granted" ? "Active" : "Allow"}
              </Button>
            </div>

            {/* 4. Payment & UPI Notification Listener */}
            <div className="flex items-center justify-between p-3.5 rounded-xl border border-ops-line bg-ops-panel hover:border-ops-line-bright transition-colors">
              <div className="flex items-center gap-3">
                <div className="rounded-lg bg-ai/10 p-2 text-ai">
                  <CreditCard size={18} />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-[13px] font-medium text-ink">UPI & Payment Listener</span>
                    {upiListenerGranted ? (
                      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-[11px] font-medium text-emerald-400 border border-emerald-500/20">
                        <CheckCircle2 size={11} /> Active
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 rounded-full bg-ops-raised px-2 py-0.5 text-[11px] font-medium text-ink-dim border border-ops-line">
                        Optional
                      </span>
                    )}
                  </div>
                  <p className="text-[11px] text-ink-dim mt-0.5">
                    Listens in the background for GPay, PhonePe, Paytm, and bank notifications to automatically log expenses.
                  </p>
                </div>
              </div>
              <Button
                variant={upiListenerGranted ? "ghost" : "outline"}
                size="sm"
                onClick={requestNotificationAccess}
                className="text-[12px] flex items-center gap-1"
              >
                <span>{upiListenerGranted ? "Settings" : "Enable"}</span>
                <ExternalLink size={12} />
              </Button>
            </div>
          </div>
        </div>
      </Panel>

      {/* Native Android assistant integration */}
      {isMobile && (
        <Panel title="Native Android Assistant" lamp={<Lamp tone={assistantRoleGranted ? "go" : "caution"} />}>
          <div className="space-y-4 pt-2 text-[13px]">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-gradient-to-r from-ai/10 via-ai/5 to-transparent border border-ai/30 rounded-xl p-4">
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <div className="p-1.5 rounded-full bg-ai/20 text-ai">
                    <Sparkles size={18} />
                  </div>
                  <h4 className="font-semibold text-ink text-[14px]">System-level IRIS assistant</h4>
                  <span className="inline-flex items-center gap-1 rounded-full bg-ai/15 px-2 py-0.5 text-[10px] font-semibold text-ai border border-ai/25">
                    Native
                  </span>
                </div>
                <p className="text-[12px] text-ink-dim max-w-xl">
                  IRIS runs as Android's digital assistant: a native voice session appears over the current app or lock
                  screen, without opening the full dashboard. Reasoning, tools, memory, vision and Gemini Live stay on
                  the existing IRIS backend.
                </p>
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 pt-1 text-[11px] text-ink-faint">
                  <span>
                    Language:{" "}
                    <span className="text-ai font-medium">{capabilities?.language ?? "en-IN"}</span>
                  </span>
                  <span>
                    Microphone:{" "}
                    <span className={capabilities?.microphone ? "text-emerald-400 font-medium" : "text-amber-400 font-medium"}>
                      {capabilities?.microphone ? "Granted" : "Needed"}
                    </span>
                  </span>
                  <span>
                    Screen perception:{" "}
                    <span className={capabilities?.screenPerception ? "text-emerald-400 font-medium" : "text-amber-400 font-medium"}>
                      {capabilities?.screenPerception ? "OS assist screenshot" : "Unavailable"}
                    </span>
                  </span>
                </div>
              </div>

              <div className="flex flex-wrap sm:flex-col items-stretch sm:items-end gap-2 shrink-0">
                <Button
                  variant={assistantRoleGranted ? "ghost" : "ai"}
                  size="sm"
                  onClick={async () => {
                    await requestAssistantRole();
                    await checkPermissions();
                  }}
                  className="text-[12px] justify-center gap-1.5"
                >
                  <ShieldCheck size={13} />
                  <span>{assistantRoleGranted ? "Assistant: Active" : "Set as Assistant"}</span>
                </Button>
                <div className="flex items-center gap-1.5">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleTestAssistant}
                    className="text-[11px] flex items-center gap-1"
                  >
                    <Mic size={12} className="text-ai" />
                    <span>Test Session</span>
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={async () => {
                      await openAssistantSettings();
                      await checkPermissions();
                    }}
                    className="text-[11px] flex items-center gap-1"
                  >
                    <span>Native Setup</span>
                    <ExternalLink size={11} />
                  </Button>
                </div>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div className="rounded-xl border border-ops-line bg-ops-panel p-3.5 space-y-2">
                <div className="flex items-center justify-between gap-2 text-ink font-semibold">
                  <div className="flex items-center gap-2">
                    <Smartphone size={16} className="text-ai" />
                    <span>Hey IRIS hotword</span>
                  </div>
                  <span
                    className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium border ${
                      capabilities?.hotwordState === 2
                        ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                        : "bg-amber-500/10 text-amber-400 border-amber-500/20"
                    }`}
                  >
                    {capabilities?.hotwordState === 2 ? "Hardware active" : "Device dependent"}
                  </span>
                </div>
                <p className="text-[11px] text-ink-dim leading-relaxed">
                  {capabilities?.hotwordLabel ?? "Not evaluated"} — {capabilities?.hotwordDetail ?? "Select IRIS as the assistant to let Android report the real DSP capability."}
                </p>
                <Button variant="outline" size="sm" onClick={handleHotwordRefresh} className="w-full justify-center text-[11px]">
                  Re-check hardware
                </Button>
              </div>

              <div className="rounded-xl border border-ops-line bg-ops-panel p-3.5 space-y-2">
                <div className="flex items-center gap-2 text-ink font-semibold">
                  <Sparkles size={16} className="text-ai" />
                  <span>Fallback session</span>
                </div>
                <p className="text-[11px] text-ink-dim leading-relaxed">
                  Overlay permission is only for the translucent native session used when IRIS is not the selected
                  assistant. There is no permanent floating sphere, background microphone, sensor polling or wake lock.
                </p>
                <Button
                  variant={overlayGranted ? "ghost" : "outline"}
                  size="sm"
                  onClick={async () => {
                    await requestOverlayPermission();
                    await checkPermissions();
                  }}
                  className="w-full justify-center gap-1 text-[11px]"
                >
                  <span>{overlayGranted ? "Overlay granted" : "Allow overlay"}</span>
                  <ExternalLink size={11} />
                </Button>
              </div>

              <div className="rounded-xl border border-ops-line bg-ops-panel p-3.5 space-y-2">
                <div className="flex items-center gap-2 text-ink font-semibold">
                  <ShieldCheck size={16} className="text-ai" />
                  <span>Battery & autolaunch</span>
                </div>
                <p className="text-[11px] text-ink-dim leading-relaxed">
                  realme UI may freeze background services. Exempt IRIS from battery optimisation and allow auto-launch
                  so Android can rebind the assistant service.
                </p>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={openSystemAppSettings}
                  className="w-full justify-center gap-1 text-[11px]"
                >
                  <span>App Info Settings</span>
                  <ExternalLink size={11} />
                </Button>
              </div>
            </div>

            <div className="rounded-xl border border-ops-line bg-ops-panel/60 p-3.5 text-[12px] space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-medium text-ink flex items-center gap-1.5">
                  <Smartphone size={14} className="text-ai" />
                  <span>Realme GT 7T activation guide</span>
                </span>
                <span className="text-[10px] text-ink-faint">realme UI 6 / Android 15</span>
              </div>
              <ol className="list-decimal list-inside space-y-1 text-ink-dim text-[11px]">
                <li>
                  Set <strong className="text-ink">IRIS</strong> as the digital assistant in Android Settings → Apps →
                  Default apps → Digital assistant app.
                </li>
                <li>
                  Enable the system assistant gesture (power-button long press or corner swipe). This is the reliable
                  pathway on realme UI.
                </li>
                <li>
                  Optional: add the <strong className="text-ink">Ask IRIS</strong> Quick Settings tile or home-screen
                  widget.
                </li>
                <li>
                  realme UI does not expose screen-off gesture events to third-party apps; drawing M/W cannot be wired
                  to IRIS without an OEM API.
                </li>
              </ol>
            </div>
          </div>
        </Panel>
      )}
    </div>
  );
}
