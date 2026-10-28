import { registerPlugin } from "@capacitor/core";

export interface AppLauncherPlugin {
  launchApp(options: { appName: string }): Promise<{ success: boolean; app?: string; package?: string; error?: string }>;
  getInstalledApps(): Promise<{ apps: Array<{ name: string; package: string }> }>;
  openAppSettings?(): Promise<{ success: boolean }>;
  openAssistantSettings?(): Promise<{ success: boolean }>;
}

export const AppLauncher = registerPlugin<AppLauncherPlugin>("AppLauncher");

export async function openSystemAppSettings(): Promise<{ success: boolean; message: string }> {
  try {
    if (typeof window !== "undefined" && (window as unknown as { Capacitor?: unknown }).Capacitor) {
      if (typeof AppLauncher.openAppSettings === "function") {
        await AppLauncher.openAppSettings();
        return { success: true, message: "Opened application details settings." };
      }
      await AppLauncher.launchApp({ appName: "settings" });
      return { success: true, message: "Opened system settings." };
    }
    return { success: false, message: "App settings can only be opened from the mobile app." };
  } catch (err: unknown) {
    const errorMsg = err instanceof Error ? err.message : String(err);
    return { success: false, message: `Could not open settings: ${errorMsg}` };
  }
}

export async function openDigitalAssistantSettings(): Promise<{ success: boolean; message: string }> {
  try {
    if (typeof window !== "undefined" && (window as unknown as { Capacitor?: unknown }).Capacitor) {
      if (typeof AppLauncher.openAssistantSettings === "function") {
        await AppLauncher.openAssistantSettings();
        return { success: true, message: "Opened digital assistant settings." };
      }
      await AppLauncher.launchApp({ appName: "settings" });
      return { success: true, message: "Opened system settings." };
    }
    return { success: false, message: "Settings can only be opened from the mobile app." };
  } catch (err: unknown) {
    const errorMsg = err instanceof Error ? err.message : String(err);
    return { success: false, message: `Could not open assistant settings: ${errorMsg}` };
  }
}

export async function launchPhoneApp(appName: string): Promise<{ success: boolean; message: string }> {
  try {
    if (typeof window === "undefined" || !(window as unknown as { Capacitor?: unknown }).Capacitor) {
      return { success: false, message: "App launching is only available in the IRIS mobile app." };
    }
    const cleanName = appName.replace(/[\*\_'"`]/g, "").trim();
    if (!cleanName) {
      return { success: false, message: "No app name specified." };
    }
    const res = await AppLauncher.launchApp({ appName: cleanName });
    if (res.success) {
      return { success: true, message: `Opened ${res.app || cleanName} on your phone.` };
    }
    return { success: false, message: res.error || `Could not find app ${cleanName}.` };
  } catch (err: unknown) {
    const errorMsg = err instanceof Error ? err.message : String(err);
    return { success: false, message: `Failed to launch app: ${errorMsg}` };
  }
}
