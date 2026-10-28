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
import { openDigitalAssistantSettings, openSystemAppSettings } from "@/lib/appLauncher";

type PermissionStatus = "granted" | "denied" | "prompt" | "unknown";

export function PermissionsPanel() {
  const [micStatus, setMicStatus] = useState<PermissionStatus>("unknown");
  const [cameraStatus, setCameraStatus] = useState<PermissionStatus>("unknown");
  const [notificationStatus, setNotificationStatus] = useState<PermissionStatus>("unknown");
  const [upiListenerGranted, setUpiListenerGranted] = useState(false);
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

      {/* Advanced System Settings Panel */}
      {isMobile && (
        <Panel title="Advanced Android System Integration" lamp={<Lamp tone="go" />}>
          <div className="space-y-3 pt-2 text-[13px]">
            <p className="text-[12px] text-ink-dim">
              Configure system-level Android integrations to invoke IRIS with gestures or hardware buttons.
            </p>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
              {/* Default Assistant */}
              <div className="rounded-xl border border-ops-line bg-ops-panel p-4 flex flex-col justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2 text-ink font-semibold">
                    <Smartphone size={16} className="text-ai" />
                    <span>Default Digital Assistant</span>
                  </div>
                  <p className="text-[12px] text-ink-dim mt-1.5 leading-relaxed">
                    Set IRIS as your default phone assistant to invoke hands-free voice via power button long-press or corner swipe gestures.
                  </p>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={openDigitalAssistantSettings}
                  className="w-full justify-center gap-1.5 text-[12px]"
                >
                  <span>Set as Default Assistant</span>
                  <ExternalLink size={12} />
                </Button>
              </div>

              {/* System App Info */}
              <div className="rounded-xl border border-ops-line bg-ops-panel p-4 flex flex-col justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2 text-ink font-semibold">
                    <ShieldCheck size={16} className="text-ai" />
                    <span>All Permissions & Battery</span>
                  </div>
                  <p className="text-[12px] text-ink-dim mt-1.5 leading-relaxed">
                    Open Android's App Info page to toggle background battery optimization (unrestricted) or review all granted permissions.
                  </p>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={openSystemAppSettings}
                  className="w-full justify-center gap-1.5 text-[12px]"
                >
                  <span>Open App Info Settings</span>
                  <ExternalLink size={12} />
                </Button>
              </div>
            </div>
          </div>
        </Panel>
      )}
    </div>
  );
}
