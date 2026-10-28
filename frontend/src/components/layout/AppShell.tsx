import { useEffect } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { Search } from "lucide-react";
import { MobileBottomNav } from "@/components/layout/TopStrip";
import { MobileTopBar, Sidebar } from "@/components/layout/Sidebar";
import { AskIrisConsole } from "@/features/ai/AskIrisConsole";
import { AgyDrawer } from "@/features/agy/AgyDrawer";
import { useFocusSessions } from "@/hooks/queries";
import { useUiStore } from "@/stores";

/**
 * Notes-style shell: a quiet sidebar and one centred reading column.
 * Cmd/Ctrl+K opens Ask IRIS from anywhere.
 */
export function AppShell() {
  const location = useLocation();
  const setAskOpen = useUiStore((s) => s.setAskOpen);

  // Hydrate any running focus session once at boot.
  useFocusSessions();

  useEffect(() => {
    // Detect Capacitor native shell or Android PWA / mobile standalone mode
    const isCapacitor = typeof window !== "undefined" && Boolean((window as unknown as { Capacitor?: unknown }).Capacitor);
    const isAndroid = typeof navigator !== "undefined" && /android/i.test(navigator.userAgent);
    const isStandalone = typeof window !== "undefined" && window.matchMedia("(display-mode: standalone)").matches;

    // Check if the browser natively supplies a non-zero CSS safe-area-inset-top
    let hasNativeTopInset = false;
    if (typeof document !== "undefined") {
      const probe = document.createElement("div");
      probe.style.paddingTop = "env(safe-area-inset-top, 0px)";
      document.body.appendChild(probe);
      hasNativeTopInset = parseFloat(window.getComputedStyle(probe).paddingTop) > 0;
      document.body.removeChild(probe);
    }

    if (!hasNativeTopInset && (isCapacitor || isAndroid || isStandalone)) {
      // 38px provides comfortable clearance below mobile status bars and camera punch-holes
      document.documentElement.style.setProperty("--safe-top", "38px");
      document.documentElement.style.setProperty("--safe-bottom", "14px");
    }
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setAskOpen(true);
      }
    };
    const onAutoVoice = () => {
      const voiceButton = document.querySelector<HTMLButtonElement>('button[aria-label="Talk to IRIS"]');
      if (voiceButton) {
        voiceButton.click();
      } else {
        setAskOpen(true);
      }
    };
    if (typeof window !== "undefined" && (window as unknown as { __IRIS_AUTO_VOICE__?: boolean }).__IRIS_AUTO_VOICE__) {
      (window as unknown as { __IRIS_AUTO_VOICE__?: boolean }).__IRIS_AUTO_VOICE__ = false;
      setTimeout(onAutoVoice, 400);
    }
    window.addEventListener("keydown", onKey);
    window.addEventListener("iris-auto-voice", onAutoVoice);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("iris-auto-voice", onAutoVoice);
    };
  }, [setAskOpen]);

  return (
    <div className="flex min-h-dvh bg-ops-ground">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <MobileTopBar
          askTrigger={
            <button
              onClick={() => setAskOpen(true)}
              aria-label="Ask IRIS"
              className="rounded-md p-1.5 text-ink-faint hover:bg-ops-raised hover:text-ink"
            >
              <Search size={16} strokeWidth={1.75} />
            </button>
          }
        />
        <main className="mx-auto flex w-full min-w-0 max-w-[920px] flex-1 flex-col px-4 pb-28 pt-4 md:px-12 md:pb-10 md:pt-12">
          <Outlet key={location.pathname} />
        </main>
      </div>
      <MobileBottomNav />
      <AskIrisConsole />
      <AgyDrawer />
    </div>
  );
}
