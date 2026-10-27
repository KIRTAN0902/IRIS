import { useEffect, useState } from "react";
import { Zap, CheckCircle2, ChevronRight } from "lucide-react";
import { checkNotificationAccess, requestNotificationAccess } from "./upiTracker";

export function AutoTrackingBanner() {
  const [granted, setGranted] = useState<boolean | null>(null);
  const [isMobileApp, setIsMobileApp] = useState(false);

  const refreshStatus = () => {
    checkNotificationAccess().then(setGranted);
  };

  useEffect(() => {
    const isCap = typeof window !== "undefined" && Boolean((window as unknown as { Capacitor?: unknown }).Capacitor);
    setIsMobileApp(isCap);
    if (isCap) {
      refreshStatus();
      const onFocus = () => refreshStatus();
      window.addEventListener("focus", onFocus);
      return () => window.removeEventListener("focus", onFocus);
    }
  }, []);

  if (!isMobileApp) return null;

  return (
    <div className="mt-3 flex items-center justify-between rounded-xl border border-ops-line bg-ops-void px-3.5 py-2.5 text-[13px]">
      <div className="flex items-center gap-2.5">
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-ops-raised text-ink">
          {granted ? <CheckCircle2 size={16} className="text-go" /> : <Zap size={16} className="text-caution" />}
        </div>
        <div>
          <p className="font-medium text-ink">
            {granted ? "UPI Auto-Tracking Active" : "Auto-Log GPay & UPI Payments"}
          </p>
          <p className="text-[11px] text-ink-faint">
            {granted
              ? "Payments on Google Pay, PhonePe & Paytm log automatically"
              : "Enable background payment detection on your phone"}
          </p>
        </div>
      </div>
      {!granted && (
        <button
          onClick={requestNotificationAccess}
          className="flex shrink-0 items-center gap-1 rounded-lg bg-ops-raised px-2.5 py-1.5 text-[12px] font-medium text-ink hover:bg-ops-line-bright cursor-pointer"
        >
          <span>Enable</span>
          <ChevronRight size={14} />
        </button>
      )}
    </div>
  );
}
