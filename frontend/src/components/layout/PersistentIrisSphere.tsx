import { useLocation } from "react-router-dom";
import { useLensStore } from "@/stores/lensStore";
import { useVoiceSession } from "@/features/home/VoiceSession";
import { IrisSphere } from "@/features/home/IrisSphere";
import { cn } from "@/lib/format";

export function PersistentIrisSphere() {
  const location = useLocation();
  const { activeLens } = useLensStore();
  const voice = useVoiceSession();

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

  return (
    <div
      aria-label="IRIS Ambient Intelligence Presence"
      className={cn(
        "pointer-events-none fixed z-30 flex flex-col items-center transition-all duration-500 ease-[cubic-bezier(0.16,1,0.3,1)]",
        isHome
          ? "left-1/2 -translate-x-1/2 bottom-[116px] sm:bottom-[112px]"
          : "right-4 sm:right-6 bottom-20 md:bottom-6 translate-x-0",
      )}
    >
      <button
        type="button"
        onClick={handleClick}
        aria-label={voice.phase === "off" ? "Start voice session with IRIS" : `IRIS status: ${voice.phase}`}
        title={isHome ? "Tap to speak with IRIS" : "IRIS Presence · Tap to speak"}
        className={cn(
          "pointer-events-auto group relative rounded-full transition-transform duration-300 focus-visible:outline-offset-4 cursor-pointer",
          isHome ? "hover:scale-105 active:scale-95" : "hover:scale-110 active:scale-90 shadow-lg",
        )}
      >
        {/* Soft radial glow */}
        <span
          className={cn(
            "pointer-events-none absolute -inset-2 rounded-full blur-xl transition opacity-70 group-hover:opacity-100",
            active ? "bg-emerald-500/25 animate-pulse" : "bg-ai/15",
          )}
          aria-hidden
        />

        {/* Sphere Container */}
        <div
          className={cn(
            "rounded-full transition-all duration-500 flex items-center justify-center border",
            isHome
              ? "border-ai/20 bg-ops-panel/60 backdrop-blur-xs p-1"
              : "border-ai/30 bg-ops-panel/95 backdrop-blur-md p-1 shadow-md hover:border-ai",
          )}
        >
          <IrisSphere
            phase={voice.phase}
            level={voice.level}
            size={isHome ? 80 : 48}
          />
        </div>
      </button>

      {/* Status caption shown under sphere in Homepage mode */}
      {isHome && (
        <div
          className="mt-1 flex items-center gap-1.5 text-[11px] font-medium text-ink-dim transition-opacity duration-300"
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
      )}
    </div>
  );
}
