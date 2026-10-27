import { registerPlugin } from "@capacitor/core";

export interface PaymentListenerPlugin {
  isNotificationAccessGranted(): Promise<{ granted: boolean }>;
  openNotificationSettings(): Promise<{ success: boolean }>;
}

export const PaymentListener = registerPlugin<PaymentListenerPlugin>("PaymentListener");

export async function checkNotificationAccess(): Promise<boolean> {
  try {
    if (typeof window === "undefined" || !(window as unknown as { Capacitor?: unknown }).Capacitor) {
      return false;
    }
    const res = await PaymentListener.isNotificationAccessGranted();
    return Boolean(res.granted);
  } catch {
    return false;
  }
}

export async function requestNotificationAccess(): Promise<void> {
  try {
    await PaymentListener.openNotificationSettings();
  } catch (err) {
    console.warn("Could not open notification settings:", err);
  }
}
