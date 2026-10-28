import { registerPlugin } from "@capacitor/core";

export interface AppLauncherPlugin {
  launchApp(options: { appName: string }): Promise<{ success: boolean; app?: string; package?: string; error?: string }>;
  getInstalledApps(): Promise<{ apps: Array<{ name: string; package: string }> }>;
}

export const AppLauncher = registerPlugin<AppLauncherPlugin>("AppLauncher");

export async function launchPhoneApp(appName: string): Promise<{ success: boolean; message: string }> {
  try {
    if (typeof window === "undefined" || !(window as unknown as { Capacitor?: unknown }).Capacitor) {
      return { success: false, message: "App launching is only available in the IRIS mobile app." };
    }
    const res = await AppLauncher.launchApp({ appName });
    if (res.success) {
      return { success: true, message: `Opened ${res.app || appName} on your phone.` };
    }
    return { success: false, message: res.error || `Could not find app ${appName}.` };
  } catch (err: unknown) {
    const errorMsg = err instanceof Error ? err.message : String(err);
    return { success: false, message: `Failed to launch app: ${errorMsg}` };
  }
}
