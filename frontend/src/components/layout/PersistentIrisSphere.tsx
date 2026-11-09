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
 * Continuous Transition System:
 * - On Home: Anchored at bottom-center directly above the chat composer.
 * - On Other Lenses (Chat, Horizon, Fleet, Vault, etc.): Glides smoothly
 *   horizontally and vertically into the bottom-right corner.
 * - Canvas internal state and 60fps kinetic rotation are NEVER interrupted.
 */
export function PersistentIrisSphere() {
  const location = useLocation();
  const { activeLens } = useLensStore();
  const voice = useVoiceSession();
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    const checkMobile = () => {
      setIsMobile(window.innerWidth < 768);
    };
    checkMobile();
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

  // Coordinated physical positions (using identical CSS properties for continuous interpolation)
  const sphereStyle: React.CSSProperties = {
    position: "fixed",
    zIndex: 40,
    left: isHome ? "50%" : isMobile ? "calc(100% - 3.75rem)" : "calc(100% - 4.25rem)",
    bottom: isHome
      ? isMobile
        ? "118px"
        : "112px"
      : isMobile
      ? "5.25rem" // above mobile dock
      : "1.5rem",
    transform: isHome
      ? "translate3d(-50%, 0, 0) scale(1)"
      : "translate3d(0, 0, 0) scale(0.72)",
    transformOrigin: "center bottom",
    transition:
      "left 650ms cubic-bezier(0.16, 1, 0.3, 1), bottom 650ms cubic-bezier(0.16, 1, 0.3, 1), transform 650ms cubic-bezier(0.16, 1, 0.3, 1)",
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
          "pointer-events-auto group relative rounded-full cursor-pointer focus-visible:outline-offset-4",
          "transition-transform duration-200 active:scale-95",
        )}
      >
        {/* Sleek, precision dark bezel container */}
        <div
          className={cn(
            "relative rounded-full p-1 transition-all duration-300 flex items-center justify-center",
            "border bg-ops-panel/95 backdrop-blur-md shadow-sm",
            active
              ? "border-ai/50 ring-2 ring-ai/20 shadow-md"
              : "border-zinc-300/80 hover:border-zinc-500/80 hover:shadow-md",
          )}
        >
          {/* Active micro-indicator dot */}
          {active && (
            <span
              className={cn(
                "absolute top-0 right-0 h-2 w-2 rounded-full",
                voice.phase === "listening"
                  ? "bg-ai animate-pulse"
                  : voice.phase === "speaking"
                  ? "bg-emerald-500 animate-pulse"
                  : "bg-amber-500",
              )}
            />
          )}

          {/* Constant 64px canvas resolution: never destroyed or remounted */}
          <IrisSphere phase={voice.phase} level={voice.level} size={64} />
        </div>
      </button>

      {/* Status caption shown under sphere in Homepage mode */}
      <div
        className={cn(
          "mt-1.5 flex items-center gap-1.5 text-[11px] font-medium text-ink-dim transition-all duration-300",
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
