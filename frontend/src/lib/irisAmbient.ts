import { registerPlugin } from "@capacitor/core";

export interface IrisAmbientPlugin {
  isAssistantRoleGranted(): Promise<{ granted: boolean }>;
  requestAssistantRole(): Promise<{ success: boolean; method: string }>;
  hasOverlayPermission(): Promise<{ granted: boolean }>;
  requestOverlayPermission(): Promise<{ success: boolean }>;
  triggerAmbientSession(): Promise<{ success: boolean }>;
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
