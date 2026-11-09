import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { useLensStore } from "@/stores/lensStore";
import { useVoiceSession } from "@/features/home/VoiceSession";
import { IrisSphere } from "@/features/home/IrisSphere";
import { cn } from "@/lib/format";

/**
 * PersistentIrisSphere:
 * A single, persistent application-level ambient intelligence presence.
 *
 * Smooth Route-Aware Physical Travel:
 * - On Home: Anchored at bottom-centre directly above the global chat composer.
 *   Visual size: 100px diameter (matching user reference screenshot).
 * - On Other Lenses (Chat, Horizon, Fleet, Vault, etc.): Physically travels to
 *   bottom-right corner at compact secondary size (60px diameter).
 * - Interpolates position, elevation, and scale continuously over 650ms.
 * - Internal kinetic rotation and 3D geometric state are NEVER interrupted.
 * - 100% transparent background (zero white circular disc, zero borders).
 */
export function PersistentIrisSphere() {
  const location = useLocation();
  const { activeLens } = useLensStore();
  const voice = useVoiceSession();
  const [isMobile, setIsMobile] = useState(false);
  const [reduceMotion, setReduceMotion] = useState(false);

  useEffect(() => {
    const checkMobile = () => {
      setIsMobile(window.innerWidth < 768);
    };
    const checkMotion = () => {
      setReduceMotion(window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false);
    };
    checkMobile();
    checkMotion();
    window.addEventListener("resize", checkMobile);
    return () => window.removeEventListener("resize", checkMobile);
  }, []);

  // Determine whether current view is the productivity homepage
  const isHome =
    (activeLens === "home" || !activeLens) &&
    (location.pathname === "/" || location.pathname === "");

  const active = voice.phase !== "off";
  const label =
    voice.phase === "off"
      ? "Ready · tap to speak"
      : voice.phase === "paused"
      ? "Paused · tap to resume"
      : voice.phase === "listening"
      ? "Listening…"
      : voice.phase === "speaking"
      ? "Speaking…"
      : voice.phase;

  const handleClick = () => {
    if (active) {
      voice.tap();
    } else {
      void voice.start();
    }
  };

  // Coordinated physical positions:
  // Home: Bottom-centre directly above the chat composer (118px bottom, 100px visual size)
  // Other Pages: Bottom-right corner (1.5rem bottom, 60px compact visual size)
  const sphereStyle: React.CSSProperties = {
    position: "fixed",
    zIndex: 40,
    left: isHome ? "50%" : isMobile ? "calc(100% - 2.5rem)" : "calc(100% - 3.25rem)",
    bottom: isHome
      ? isMobile
        ? "124px"
        : "118px"
      : isMobile
      ? "5.25rem" // above mobile dock
      : "1.5rem",
    transform: isHome
      ? "translate3d(-50%, 0, 0) scale(1)"
      : "translate3d(-50%, 0, 0) scale(0.6)",
    transformOrigin: "center center",
    transition: reduceMotion
      ? "none"
      : "left 650ms cubic-bezier(0.16, 1, 0.3, 1), bottom 650ms cubic-bezier(0.16, 1, 0.3, 1), transform 650ms cubic-bezier(0.16, 1, 0.3, 1)",
    willChange: "left, bottom, transform",
  };

  return (
    <div
      aria-label="IRIS Ambient Intelligence Presence"
      style={sphereStyle}
      className="pointer-events-none flex flex-col items-center select-none"
    >
      <button
        type="button"
        onClick={handleClick}
        aria-label={
          voice.phase === "off" ? "Start voice session with IRIS" : `IRIS status: ${voice.phase}`
        }
        title={isHome ? "Tap to speak with IRIS" : "IRIS Intelligence Core · Tap to speak"}
        className={cn(
          "pointer-events-auto group relative cursor-pointer focus-visible:outline-offset-4 focus:outline-hidden",
          "transition-transform duration-200 active:scale-95",
        )}
      >
        {/* 100% Transparent Container: Zero white background disc, zero borders */}
        <div className="relative flex items-center justify-center">
          {/* Active micro-indicator dot */}
          {active && (
            <span
              className={cn(
                "absolute top-1 right-1 h-2.5 w-2.5 rounded-full ring-2 ring-white/80 z-10",
                voice.phase === "listening"
                  ? "bg-ai animate-pulse"
                  : voice.phase === "speaking"
                  ? "bg-emerald-500 animate-pulse"
                  : "bg-amber-500",
              )}
            />
          )}

          {/* Constant 100px native canvas resolution: never remounted or resized during route travel */}
          <IrisSphere phase={voice.phase} level={voice.level} size={100} />
        </div>
      </button>

      {/* Status caption shown under sphere in Homepage mode */}
      <div
        className={cn(
          "mt-1 flex items-center gap-1.5 rounded-full bg-ops-panel/90 backdrop-blur-xs px-2.5 py-0.5 text-[10.5px] font-medium text-ink-dim border border-ops-line/60 shadow-2xs transition-all duration-300 whitespace-nowrap",
          isHome
            ? "opacity-100 translate-y-0"
            : "opacity-0 -translate-y-2 pointer-events-none h-0 overflow-hidden",
        )}
        role="status"
        aria-live="polite"
      >
        <span
          className={cn(
            "h-1.5 w-1.5 rounded-full transition-colors",
            active ? "bg-emerald-500 animate-pulse" : "bg-ai",
          )}
        />
        <span className="capitalize">{label}</span>
        {active && (
          <button
            onClick={voice.end}
            className="pointer-events-auto ml-1 underline decoration-ops-line-bright underline-offset-2 text-ink-faint hover:text-ink cursor-pointer"
            aria-label="End voice session"
          >
            End
          </button>
        )}
      </div>
    </div>
  );
}
