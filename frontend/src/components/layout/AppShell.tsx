import { lazy, Suspense, useEffect } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { IrisTopHUD } from "@/components/layout/IrisTopHUD";
import { IrisBottomHUD } from "@/components/layout/IrisBottomHUD";
import { SettingsOverlay } from "@/components/layout/SettingsOverlay";
import { AgyDrawer } from "@/features/agy/AgyDrawer";
import { useFocusSessions } from "@/hooks/queries";
import { useUiStore } from "@/stores";
import { VoiceSessionProvider } from "@/features/home/VoiceSession";
import { useUIState } from "@/features/home/useUIOrchestrator";

const AskIrisConsole = lazy(() =>
  import("@/features/ai/AskIrisConsole").then((m) => ({ default: m.AskIrisConsole })),
);

/**
 * IRIS OS Shell:
 * An ambient, edge-to-edge personal AI operating system surface.
 * Replaces the traditional SaaS sidebar with the Top Intelligence HUD and Mobile Dock.
 */
export function AppShell() {
  const location = useLocation();
  const navigate = useNavigate();
  const setAskOpen = useUiStore((s) => s.setAskOpen);
  const uiState = useUIState();

  useEffect(() => {
    const preference = uiState.data?.preferences.theme ?? "dark";
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => {
      document.documentElement.dataset.theme =
        preference === "system" ? (media.matches ? "dark" : "light") : preference;
    };
    apply();
    if (preference === "system") media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, [uiState.data?.preferences.theme]);

  // Hydrate any running focus session once at boot.
  useFocusSessions();

  useEffect(() => {
    // Detect Capacitor native shell or Android PWA / mobile standalone mode
    const isCapacitor =
      typeof window !== "undefined" &&
      Boolean((window as unknown as { Capacitor?: unknown }).Capacitor);
    const isAndroid = typeof navigator !== "undefined" && /android/i.test(navigator.userAgent);
    const isStandalone =
      typeof window !== "undefined" && window.matchMedia("(display-mode: standalone)").matches;

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
      document.documentElement.style.setProperty("--safe-top", "38px");
      document.documentElement.style.setProperty("--safe-bottom", "14px");
    }
  }, []);

  useEffect(() => {
    const viewport = window.visualViewport;
    if (!viewport) return;
    const update = () => {
      const focused =
        document.activeElement instanceof HTMLTextAreaElement ||
        document.activeElement instanceof HTMLInputElement;
      const keyboard = focused
        ? Math.max(0, window.innerHeight - viewport.height - viewport.offsetTop)
        : 0;
      document.documentElement.style.setProperty("--keyboard-height", `${keyboard}px`);
    };
    viewport.addEventListener("resize", update);
    viewport.addEventListener("scroll", update);
    document.addEventListener("focusin", update);
    document.addEventListener("focusout", update);
    update();
    return () => {
      viewport.removeEventListener("resize", update);
      viewport.removeEventListener("scroll", update);
      document.removeEventListener("focusin", update);
      document.removeEventListener("focusout", update);
      document.documentElement.style.removeProperty("--keyboard-height");
    };
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setAskOpen(true);
      }
    };
    const onAutoVoice = () => {
      if (location.pathname !== "/") {
        navigate("/?mode=voice");
      } else {
        const voiceButton = document.querySelector<HTMLButtonElement>(
          'button[aria-label="Talk to IRIS"]',
        );
        voiceButton?.click();
      }
    };

    if (
      typeof window !== "undefined" &&
      (window as unknown as { __IRIS_AUTO_VOICE__?: boolean }).__IRIS_AUTO_VOICE__
    ) {
      (window as unknown as { __IRIS_AUTO_VOICE__?: boolean }).__IRIS_AUTO_VOICE__ = false;
      setTimeout(onAutoVoice, 200);
    }

    // Query native pending assistant trigger if running in Capacitor
    const checkNativePending = async () => {
      try {
        const cap = (
          window as unknown as {
            Capacitor?: {
              Plugins?: {
                AppLauncher?: { isVoicePending: () => Promise<{ pending: boolean }> };
              };
            };
          }
        ).Capacitor;
        const res = await cap?.Plugins?.AppLauncher?.isVoicePending?.();
        if (res?.pending) {
          onAutoVoice();
        }
      } catch {
        /* ignore */
      }
    };
    void checkNativePending();

    window.addEventListener("keydown", onKey);
    window.addEventListener("iris-auto-voice", onAutoVoice);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("iris-auto-voice", onAutoVoice);
    };
  }, [location.pathname, navigate, setAskOpen]);

  return (
    <VoiceSessionProvider>
      <div className="flex min-h-dvh flex-col bg-ops-ground text-ink selection:bg-ai/20 selection:text-ink">
        {/* Top Ambient Intelligence HUD */}
        <IrisTopHUD />

        {/* Operating Surface Canvas */}
        <main className="flex flex-1 flex-col overflow-hidden">
          <Outlet />
        </main>

        {/* Mobile Navigation Dock */}
        <IrisBottomHUD />

        {/* Universal Dialogs & Drawers */}
        <SettingsOverlay />
        <Suspense fallback={null}>
          <AskIrisConsole />
        </Suspense>
        <AgyDrawer />
      </div>
    </VoiceSessionProvider>
  );
}
