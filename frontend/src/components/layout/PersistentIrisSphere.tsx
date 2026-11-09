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
 * Clean Transparent 3D Intelligence Core:
 * - On Home: Positioned prominently at bottom-center with substantial size (220px desktop / 150px mobile).
 * - On Other Lenses (Chat, Horizon, Fleet, Vault, etc.): Glides smoothly
 *   into the bottom-right corner at compact 64px.
 * - Completely transparent background (zero white circular bezel, zero white card disc).
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

  // On Home, the prominent 220px 3D sphere is showcased in the Homepage Hero.
  // On all other views (Chat, Horizon, Fleet, Vault), PersistentIrisSphere provides the universal ambient presence.
  if (isHome) return null;

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

  // Clean fixed position in the bottom-right corner
  const sphereStyle: React.CSSProperties = {
    position: "fixed",
    zIndex: 40,
    right: isMobile ? "1.25rem" : "1.75rem",
    bottom: isMobile ? "5.25rem" : "1.75rem",
    transition: "transform 200ms ease-out",
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

          {/* 3D IRIS Sphere: Compact 64px ambient dock on other views */}
          <IrisSphere phase={voice.phase} level={voice.level} size={64} />
        </div>
      </button>

      {/* Status caption shown under sphere in Homepage mode */}
      <div
        className={cn(
          "mt-1.5 flex items-center gap-1.5 rounded-full bg-ops-panel/85 backdrop-blur-xs px-3 py-1 text-[11px] font-medium text-ink-dim border border-ops-line/60 shadow-2xs transition-all duration-300",
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
