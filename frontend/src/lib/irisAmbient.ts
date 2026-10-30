import { registerPlugin } from "@capacitor/core";

export interface IrisAmbientPlugin {
  isAssistantRoleGranted(): Promise<{ granted: boolean }>;
  requestAssistantRole(): Promise<{ success: boolean; method: string }>;
  hasOverlayPermission(): Promise<{ granted: boolean }>;
  requestOverlayPermission(): Promise<{ success: boolean }>;
  triggerAmbientSession(): Promise<{ success: boolean }>;
  triggerFloatingSphere(): Promise<{ success: boolean }>;
  stopFloatingSphere(): Promise<{ success: boolean }>;
  getPreferSphereMode(): Promise<{ preferSphereMode: boolean }>;
  setPreferSphereMode(options: { enabled: boolean }): Promise<{ success: boolean; preferSphereMode: boolean }>;
  captureScreenNative(): Promise<{ success: boolean; image_base64: string }>;
}

export const IrisAmbient = registerPlugin<IrisAmbientPlugin>("IrisAmbient");

export async function checkAssistantRole(): Promise<boolean> {
  try {
    if (typeof window !== "undefined" && (window as unknown as { Capacitor?: unknown }).Capacitor) {
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
    if (typeof window !== "undefined" && (window as unknown as { Capacitor?: unknown }).Capacitor) {
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
    if (typeof window !== "undefined" && (window as unknown as { Capacitor?: unknown }).Capacitor) {
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
    if (typeof window !== "undefined" && (window as unknown as { Capacitor?: unknown }).Capacitor) {
      const res = await IrisAmbient.requestOverlayPermission();
      return Boolean(res.success);
    }
  } catch (e) {
    console.warn("requestOverlayPermission error:", e);
  }
  return false;
}

export async function triggerAmbientAssistant(): Promise<boolean> {
  try {
    if (typeof window !== "undefined" && (window as unknown as { Capacitor?: unknown }).Capacitor) {
      const res = await IrisAmbient.triggerAmbientSession();
      return Boolean(res.success);
    }
  } catch (e) {
    console.warn("triggerAmbientAssistant error:", e);
  }
  return false;
}

export async function triggerFloatingSphere(): Promise<boolean> {
  try {
    if (typeof window !== "undefined" && (window as unknown as { Capacitor?: unknown }).Capacitor) {
      const res = await IrisAmbient.triggerFloatingSphere();
      return Boolean(res.success);
    }
  } catch (e) {
    console.warn("triggerFloatingSphere error:", e);
  }
  return false;
}

export async function stopFloatingSphere(): Promise<boolean> {
  try {
    if (typeof window !== "undefined" && (window as unknown as { Capacitor?: unknown }).Capacitor) {
      const res = await IrisAmbient.stopFloatingSphere();
      return Boolean(res.success);
    }
  } catch (e) {
    console.warn("stopFloatingSphere error:", e);
  }
  return false;
}

export async function getPreferSphereMode(): Promise<boolean> {
  try {
    if (typeof window !== "undefined" && (window as unknown as { Capacitor?: unknown }).Capacitor) {
      const res = await IrisAmbient.getPreferSphereMode();
      return Boolean(res.preferSphereMode);
    }
  } catch (e) {
    console.warn("getPreferSphereMode error:", e);
  }
  return true; // Default to true for ambient experience
}

export async function setPreferSphereMode(enabled: boolean): Promise<boolean> {
  try {
    if (typeof window !== "undefined" && (window as unknown as { Capacitor?: unknown }).Capacitor) {
      const res = await IrisAmbient.setPreferSphereMode({ enabled });
      return Boolean(res.success);
    }
  } catch (e) {
    console.warn("setPreferSphereMode error:", e);
  }
  return false;
}
