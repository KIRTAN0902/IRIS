import { registerPlugin } from "@capacitor/core";

export interface AssistantCapabilityRow {
  title: string;
  value: string;
  supported: boolean;
  detail: string;
}

export interface AssistantCapabilities {
  device: string;
  android: string;
  isAssistant: boolean;
  microphone: boolean;
  overlay: boolean;
  notifications: boolean;
  batteryOptimized: boolean;
  screenPerception: boolean;
  displayState: string;
  language: string;
  hotwordState: number;
  hotwordLabel: string;
  hotwordDetail: string;
  rows: AssistantCapabilityRow[];
}

export interface IrisAmbientPlugin {
  isAssistantRoleGranted(): Promise<{ granted: boolean }>;
  requestAssistantRole(): Promise<{ success: boolean; method: string }>;
  hasOverlayPermission(): Promise<{ granted: boolean }>;
  requestOverlayPermission(): Promise<{ success: boolean }>;
  /** Launch the native assistant session, never the full dashboard. */
  triggerAmbientSession(): Promise<{ success: boolean }>;
  openAssistantSettings(): Promise<{ success: boolean }>;
  getAssistantCapabilities(): Promise<{ capabilities: AssistantCapabilities }>;
  refreshHotword(): Promise<{ success: boolean }>;
  captureScreenNative(): Promise<{ success: boolean; image_base64: string }>;
  // Legacy aliases kept so older bundles do not crash during an app update.
  triggerFloatingSphere(): Promise<{ success: boolean }>;
  stopFloatingSphere(): Promise<{ success: boolean }>;
  getPreferSphereMode(): Promise<{ preferSphereMode: boolean }>;
  setPreferSphereMode(options: { enabled: boolean }): Promise<{ success: boolean; preferSphereMode: boolean }>;
}

export const IrisAmbient = registerPlugin<IrisAmbientPlugin>("IrisAmbient");

function isNative(): boolean {
  return typeof window !== "undefined" && Boolean((window as unknown as { Capacitor?: unknown }).Capacitor);
}

export async function checkAssistantRole(): Promise<boolean> {
  try {
    if (isNative()) {
      const res = await IrisAmbient.isAssistantRoleGranted();
      return Boolean(res.granted);
    }
  } catch (e) {
    console.warn("checkAssistantRole error:", e);
  }
  return false;
}

export async function requestAssistantRole(): Promise<boolean> {
  try {
    if (isNative()) {
      const res = await IrisAmbient.requestAssistantRole();
      return Boolean(res.success);
    }
  } catch (e) {
    console.warn("requestAssistantRole error:", e);
  }
  return false;
}

export async function checkOverlayPermission(): Promise<boolean> {
  try {
    if (isNative()) {
      const res = await IrisAmbient.hasOverlayPermission();
      return Boolean(res.granted);
    }
  } catch (e) {
    console.warn("checkOverlayPermission error:", e);
  }
  return false;
}

export async function requestOverlayPermission(): Promise<boolean> {
  try {
    if (isNative()) {
      const res = await IrisAmbient.requestOverlayPermission();
      return Boolean(res.success);
    }
  } catch (e) {
    console.warn("requestOverlayPermission error:", e);
  }
  return false;
}

/** Opens the native assistant session over the current app. */
export async function triggerAmbientAssistant(): Promise<boolean> {
  try {
    if (isNative()) {
      const res = await IrisAmbient.triggerAmbientSession();
      return Boolean(res.success);
    }
  } catch (e) {
    console.warn("triggerAmbientAssistant error:", e);
  }
  return false;
}

export async function openAssistantSettings(): Promise<boolean> {
  try {
    if (isNative()) {
      const res = await IrisAmbient.openAssistantSettings();
      return Boolean(res.success);
    }
  } catch (e) {
    console.warn("openAssistantSettings error:", e);
  }
  return false;
}

export async function getAssistantCapabilities(): Promise<AssistantCapabilities | null> {
  try {
    if (isNative()) {
      const res = await IrisAmbient.getAssistantCapabilities();
      return res.capabilities ?? null;
    }
  } catch (e) {
    console.warn("getAssistantCapabilities error:", e);
  }
  return null;
}

export async function refreshHotwordStatus(): Promise<boolean> {
  try {
    if (isNative()) {
      const res = await IrisAmbient.refreshHotword();
      return Boolean(res.success);
    }
  } catch (e) {
    console.warn("refreshHotwordStatus error:", e);
  }
  return false;
}
